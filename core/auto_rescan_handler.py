"""
Auto Rescan Handler - RANK_DROPPED 이벤트 기반 자동 재스캔
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 4-1-A] 순위 급락 자동 재스캔 트리거
- RANK_DROPPED 이벤트 구독 (5위 이상 하락 감지)
- 동일 키워드 30분 쿨다운 적용
- high/critical 우선순위 키워드만 재스캔
- 비동기 subprocess로 단일 키워드 스캔 실행
"""

import os
import sys
import json
import logging
import subprocess
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Set

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.event_bus import EventType, Event, subscribe_event, get_event_bus

logger = logging.getLogger(__name__)


class AutoRescanHandler:
    """
    순위 급락 자동 재스캔 핸들러

    RANK_DROPPED 이벤트 발생 시:
    1. 5위 이상 하락 여부 확인
    2. 쿨다운 체크 (30분)
    3. 키워드 우선순위 체크 (high/critical만)
    4. 자동 재스캔 트리거
    """

    def __init__(self, min_drop: int = 5, cooldown_minutes: int = 30):
        """
        Args:
            min_drop: 재스캔 트리거 최소 순위 하락 값
            cooldown_minutes: 동일 키워드 재스캔 대기 시간 (분)
        """
        self.min_drop = min_drop
        self.cooldown_minutes = cooldown_minutes
        self.rescan_cooldown: Dict[str, datetime] = {}
        self.rescan_history: list = []
        self.max_history = 100

        # 설정 파일 경로
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_path = os.path.join(self.root_dir, 'config', 'keywords.json')
        self.targets_path = os.path.join(self.root_dir, 'config', 'targets.json')

        # 이벤트 구독
        self._register_handlers()

        logger.info(f"AutoRescanHandler initialized (min_drop={min_drop}, cooldown={cooldown_minutes}min)")

    def _register_handlers(self):
        """이벤트 핸들러 등록"""
        event_bus = get_event_bus()
        event_bus.subscribe(EventType.RANK_DROPPED, self._handle_rank_dropped)
        logger.debug("Registered handler for RANK_DROPPED event")

    def _handle_rank_dropped(self, event: Event):
        """
        RANK_DROPPED 이벤트 핸들러 (동기)

        비동기 처리가 필요한 경우 새 스레드에서 실행
        """
        try:
            keyword = event.data.get("keyword")
            change = abs(event.data.get("change", 0))
            previous_rank = event.data.get("previous_rank", 0)
            current_rank = event.data.get("current_rank", 0)
            severity = event.data.get("severity", "warning")

            logger.info(
                f"🚨 [AutoRescan] RANK_DROPPED detected: {keyword} "
                f"({previous_rank}위 → {current_rank}위, 하락: {change}위)"
            )

            # 1. 최소 하락폭 체크
            if change < self.min_drop:
                logger.debug(f"Skip: drop {change} < min_drop {self.min_drop}")
                return

            # 2. 쿨다운 체크
            if self._is_in_cooldown(keyword):
                logger.info(f"⏰ [AutoRescan] {keyword} is in cooldown, skipping")
                return

            # 3. 우선순위 체크
            priority = self._get_keyword_priority(keyword)
            if priority not in ("critical", "high"):
                logger.info(f"📋 [AutoRescan] {keyword} priority is {priority}, skipping (only high/critical)")
                return

            # 4. 재스캔 트리거
            reason = f"순위 급락 ({previous_rank}위 → {current_rank}위, {change}위 하락)"
            self._trigger_rescan(keyword, reason, severity)

        except Exception as e:
            logger.error(f"Error handling RANK_DROPPED event: {e}")

    def _is_in_cooldown(self, keyword: str) -> bool:
        """키워드가 쿨다운 중인지 확인"""
        if keyword not in self.rescan_cooldown:
            return False

        last_rescan = self.rescan_cooldown[keyword]
        cooldown_until = last_rescan + timedelta(minutes=self.cooldown_minutes)

        if datetime.now() < cooldown_until:
            remaining = (cooldown_until - datetime.now()).total_seconds() / 60
            logger.debug(f"Keyword {keyword} in cooldown for {remaining:.1f} more minutes")
            return True

        return False

    def _get_keyword_priority(self, keyword: str) -> str:
        """
        키워드 우선순위 조회

        우선순위 결정 기준:
        1. keyword_lifecycle 테이블의 grade
        2. keyword_insights 테이블의 grade
        3. 기본값: medium
        """
        try:
            from db.database import DatabaseManager
            db = DatabaseManager()

            # keyword_lifecycle에서 조회
            db.cursor.execute('''
                SELECT grade FROM keyword_lifecycle WHERE keyword = ?
            ''', (keyword,))
            row = db.cursor.fetchone()

            if row and row[0]:
                grade = row[0].lower()
                if grade in ('s', 'a'):
                    return "critical"
                elif grade == 'b':
                    return "high"
                elif grade == 'c':
                    return "medium"
                else:
                    return "low"

            # keyword_insights에서 조회
            db.cursor.execute('''
                SELECT grade FROM keyword_insights WHERE keyword = ?
            ''', (keyword,))
            row = db.cursor.fetchone()

            if row and row[0]:
                grade = row[0].lower()
                if grade in ('s', 'a'):
                    return "critical"
                elif grade == 'b':
                    return "high"
                elif grade == 'c':
                    return "medium"
                else:
                    return "low"

            # 기본값
            return "medium"

        except Exception as e:
            logger.warning(f"Failed to get keyword priority: {e}")
            return "medium"

    def _trigger_rescan(self, keyword: str, reason: str, severity: str = "warning"):
        """
        단일 키워드 재스캔 트리거

        subprocess로 scraper_naver_place.py --keyword 실행
        """
        logger.info(f"🔄 [AutoRescan] Triggering rescan for: {keyword}")
        logger.info(f"   Reason: {reason}")

        # 쿨다운 타임스탬프 업데이트
        self.rescan_cooldown[keyword] = datetime.now()

        # 히스토리 기록
        self._add_to_history(keyword, reason, severity)

        # 스크래퍼 경로
        scraper_path = os.path.join(self.root_dir, 'scrapers', 'scraper_naver_place.py')

        if not os.path.exists(scraper_path):
            logger.error(f"Scraper not found: {scraper_path}")
            return

        try:
            # subprocess로 단일 키워드 스캔 실행 (백그라운드)
            cmd = [
                sys.executable,
                scraper_path,
                "--keyword", keyword,
                "--device", "both",
                "--skip-reviews"
            ]

            logger.info(f"   Command: {' '.join(cmd)}")

            # 로그 파일 경로
            log_dir = os.path.join(self.root_dir, 'logs')
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'auto_rescan.log')

            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*50}\n")
                f.write(f"[{datetime.now().isoformat()}] Auto-rescan triggered\n")
                f.write(f"Keyword: {keyword}\n")
                f.write(f"Reason: {reason}\n")
                f.write(f"{'='*50}\n")

                # 비동기로 실행 (결과를 기다리지 않음)
                subprocess.Popen(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    cwd=self.root_dir
                )

            logger.info(f"✅ [AutoRescan] Rescan started for: {keyword}")

            # 알림 발송 (선택적)
            self._send_rescan_notification(keyword, reason, severity)

        except Exception as e:
            logger.error(f"Failed to trigger rescan: {e}")

    def _add_to_history(self, keyword: str, reason: str, severity: str):
        """재스캔 히스토리 추가"""
        entry = {
            "keyword": keyword,
            "reason": reason,
            "severity": severity,
            "triggered_at": datetime.now().isoformat()
        }

        self.rescan_history.append(entry)

        # 최대 히스토리 초과 시 오래된 것 제거
        if len(self.rescan_history) > self.max_history:
            self.rescan_history = self.rescan_history[-self.max_history:]

    def _send_rescan_notification(self, keyword: str, reason: str, severity: str):
        """재스캔 알림 발송"""
        try:
            from alert_bot import AlertSystem
            alert = AlertSystem()

            emoji = "🚨" if severity == "critical" else "⚠️"
            message = f"{emoji} [자동 재스캔] {keyword}\n{reason}"

            alert.bot.send_message(message)
            logger.debug(f"Rescan notification sent for: {keyword}")

        except Exception as e:
            logger.debug(f"Failed to send rescan notification: {e}")

    def get_status(self) -> Dict[str, Any]:
        """현재 상태 조회"""
        active_cooldowns = {}
        now = datetime.now()

        for keyword, last_rescan in self.rescan_cooldown.items():
            cooldown_until = last_rescan + timedelta(minutes=self.cooldown_minutes)
            if now < cooldown_until:
                remaining = (cooldown_until - now).total_seconds() / 60
                active_cooldowns[keyword] = {
                    "last_rescan": last_rescan.isoformat(),
                    "cooldown_until": cooldown_until.isoformat(),
                    "remaining_minutes": round(remaining, 1)
                }

        return {
            "min_drop": self.min_drop,
            "cooldown_minutes": self.cooldown_minutes,
            "active_cooldowns": active_cooldowns,
            "recent_rescans": self.rescan_history[-10:],
            "total_rescans": len(self.rescan_history)
        }

    def clear_cooldown(self, keyword: str = None):
        """
        쿨다운 초기화

        Args:
            keyword: 특정 키워드만 초기화 (None이면 전체)
        """
        if keyword:
            if keyword in self.rescan_cooldown:
                del self.rescan_cooldown[keyword]
                logger.info(f"Cooldown cleared for: {keyword}")
        else:
            self.rescan_cooldown.clear()
            logger.info("All cooldowns cleared")


# 싱글톤 인스턴스
_auto_rescan_handler: Optional[AutoRescanHandler] = None


def get_auto_rescan_handler() -> AutoRescanHandler:
    """AutoRescanHandler 싱글톤 인스턴스 반환"""
    global _auto_rescan_handler
    if _auto_rescan_handler is None:
        _auto_rescan_handler = AutoRescanHandler()
    return _auto_rescan_handler


def initialize_auto_rescan():
    """
    AutoRescanHandler 초기화

    앱 시작 시 호출하여 이벤트 핸들러 등록
    """
    handler = get_auto_rescan_handler()
    logger.info("AutoRescanHandler ready")
    return handler

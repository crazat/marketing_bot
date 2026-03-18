"""
Keyword Priority Scheduler - 키워드 우선순위 기반 스캔 주기 관리
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 4-1-B] 키워드 우선순위별 스캔 주기 차등화
- CRITICAL: 검색량 5000+, 전환 3+ → 4시간
- HIGH: 검색량 1000+, 순위 변동 빈번 → 8시간
- MEDIUM: 검색량 300+ → 12시간
- LOW: 그 외 → 24시간
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class KeywordPriority(Enum):
    """키워드 우선순위"""
    CRITICAL = "critical"   # 4시간마다 스캔
    HIGH = "high"           # 8시간마다 스캔
    MEDIUM = "medium"       # 12시간마다 스캔
    LOW = "low"             # 24시간마다 스캔


# 우선순위별 스캔 간격 (시간)
PRIORITY_INTERVALS = {
    KeywordPriority.CRITICAL: 4,
    KeywordPriority.HIGH: 8,
    KeywordPriority.MEDIUM: 12,
    KeywordPriority.LOW: 24,
}


@dataclass
class KeywordScheduleInfo:
    """키워드 스케줄 정보"""
    keyword: str
    priority: KeywordPriority
    interval_hours: int
    last_scan: Optional[datetime] = None
    next_scan: Optional[datetime] = None
    scan_count: int = 0
    rank_changes: int = 0
    conversions: int = 0
    search_volume: int = 0
    priority_score: float = 0.0


class KeywordPriorityScheduler:
    """
    키워드 우선순위 기반 스케줄러

    각 키워드의 우선순위를 동적으로 계산하고,
    우선순위에 따라 스캔 주기를 차등화
    """

    def __init__(self):
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.schedule_file = os.path.join(self.root_dir, 'db', 'keyword_schedule.json')
        self.keyword_schedules: Dict[str, KeywordScheduleInfo] = {}

        self._load_schedules()
        logger.info("KeywordPriorityScheduler initialized")

    def _load_schedules(self):
        """저장된 스케줄 로드"""
        if os.path.exists(self.schedule_file):
            try:
                with open(self.schedule_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for keyword, info in data.items():
                        # JSON에서 복원
                        priority = KeywordPriority(info.get('priority', 'medium'))
                        last_scan = None
                        if info.get('last_scan'):
                            last_scan = datetime.fromisoformat(info['last_scan'])

                        self.keyword_schedules[keyword] = KeywordScheduleInfo(
                            keyword=keyword,
                            priority=priority,
                            interval_hours=info.get('interval_hours', 12),
                            last_scan=last_scan,
                            scan_count=info.get('scan_count', 0),
                            rank_changes=info.get('rank_changes', 0),
                            conversions=info.get('conversions', 0),
                            search_volume=info.get('search_volume', 0),
                            priority_score=info.get('priority_score', 0.0)
                        )
            except Exception as e:
                logger.warning(f"Failed to load keyword schedules: {e}")

    def _save_schedules(self):
        """스케줄 저장"""
        try:
            os.makedirs(os.path.dirname(self.schedule_file), exist_ok=True)
            data = {}

            for keyword, info in self.keyword_schedules.items():
                data[keyword] = {
                    'priority': info.priority.value,
                    'interval_hours': info.interval_hours,
                    'last_scan': info.last_scan.isoformat() if info.last_scan else None,
                    'scan_count': info.scan_count,
                    'rank_changes': info.rank_changes,
                    'conversions': info.conversions,
                    'search_volume': info.search_volume,
                    'priority_score': info.priority_score
                }

            with open(self.schedule_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Failed to save keyword schedules: {e}")

    def calculate_priority(self, keyword: str) -> Tuple[KeywordPriority, float]:
        """
        키워드 우선순위 동적 계산

        우선순위 점수 계산:
        - 검색량: 최대 5점 (search_volume / 1000, cap at 5)
        - 전환 수: 최대 3점 (conversions, cap at 3)
        - 순위 변동 횟수: 최대 2점 (rank_changes / 2, cap at 2)

        점수 → 우선순위:
        - 7+ → CRITICAL
        - 4+ → HIGH
        - 2+ → MEDIUM
        - 그 외 → LOW
        """
        try:
            from db.database import DatabaseManager
            db = DatabaseManager()

            # 검색량 조회
            search_volume = 0
            db.cursor.execute('''
                SELECT search_volume FROM keyword_insights WHERE keyword = ?
            ''', (keyword,))
            row = db.cursor.fetchone()
            if row and row[0]:
                search_volume = row[0]

            # 전환 수 조회 (최근 30일)
            conversions = 0
            db.cursor.execute('''
                SELECT COUNT(*) FROM lead_conversions lc
                JOIN mentions m ON lc.lead_id = m.id
                WHERE m.keyword = ? AND lc.converted_at >= date('now', '-30 days')
            ''', (keyword,))
            row = db.cursor.fetchone()
            if row:
                conversions = row[0]

            # 순위 변동 횟수 조회 (최근 7일)
            rank_changes = 0
            db.cursor.execute('''
                SELECT COUNT(*) FROM rank_history
                WHERE keyword = ? AND scanned_date >= date('now', '-7 days')
                AND status = 'found'
            ''', (keyword,))
            row = db.cursor.fetchone()
            if row:
                # 변동 횟수 = 스캔 횟수 기반 추정 (더 정교한 로직 필요)
                rank_changes = min(row[0], 10)

            # 점수 계산
            score = 0.0
            score += min(search_volume / 1000, 5)  # 최대 5점
            score += min(conversions, 3)            # 최대 3점
            score += min(rank_changes / 2, 2)       # 최대 2점

            # 우선순위 결정
            if score >= 7:
                priority = KeywordPriority.CRITICAL
            elif score >= 4:
                priority = KeywordPriority.HIGH
            elif score >= 2:
                priority = KeywordPriority.MEDIUM
            else:
                priority = KeywordPriority.LOW

            # 스케줄 정보 업데이트
            if keyword not in self.keyword_schedules:
                self.keyword_schedules[keyword] = KeywordScheduleInfo(
                    keyword=keyword,
                    priority=priority,
                    interval_hours=PRIORITY_INTERVALS[priority]
                )

            info = self.keyword_schedules[keyword]
            info.priority = priority
            info.interval_hours = PRIORITY_INTERVALS[priority]
            info.search_volume = search_volume
            info.conversions = conversions
            info.rank_changes = rank_changes
            info.priority_score = round(score, 2)

            return priority, score

        except Exception as e:
            logger.error(f"Failed to calculate priority for {keyword}: {e}")
            return KeywordPriority.MEDIUM, 0.0

    def get_keywords_to_scan(self) -> List[str]:
        """
        현재 스캔해야 할 키워드 목록 반환

        스캔 조건:
        - last_scan이 None (처음 스캔)
        - last_scan + interval_hours < now (스캔 주기 초과)
        """
        # 먼저 모든 키워드의 우선순위 업데이트
        self._refresh_all_priorities()

        now = datetime.now()
        keywords_to_scan = []

        for keyword, info in self.keyword_schedules.items():
            should_scan = False

            if info.last_scan is None:
                should_scan = True
            else:
                next_scan_time = info.last_scan + timedelta(hours=info.interval_hours)
                if now >= next_scan_time:
                    should_scan = True

            if should_scan:
                keywords_to_scan.append(keyword)

        # 우선순위 높은 순으로 정렬
        keywords_to_scan.sort(
            key=lambda k: (
                list(KeywordPriority).index(self.keyword_schedules[k].priority),
                -self.keyword_schedules[k].priority_score
            )
        )

        logger.info(f"Keywords to scan: {len(keywords_to_scan)}")
        return keywords_to_scan

    def _refresh_all_priorities(self):
        """모든 등록된 키워드의 우선순위 갱신"""
        try:
            # keywords.json에서 키워드 목록 로드
            keywords_path = os.path.join(self.root_dir, 'config', 'keywords.json')
            if os.path.exists(keywords_path):
                with open(keywords_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    keywords = data.get('naver_place', [])

                for keyword in keywords:
                    self.calculate_priority(keyword)

        except Exception as e:
            logger.error(f"Failed to refresh priorities: {e}")

    def record_scan(self, keyword: str):
        """스캔 완료 기록"""
        if keyword not in self.keyword_schedules:
            self.calculate_priority(keyword)

        info = self.keyword_schedules[keyword]
        info.last_scan = datetime.now()
        info.next_scan = info.last_scan + timedelta(hours=info.interval_hours)
        info.scan_count += 1

        self._save_schedules()
        logger.debug(f"Recorded scan for {keyword}, next scan at {info.next_scan}")

    def get_schedule_summary(self) -> Dict[str, Any]:
        """스케줄 요약 정보 반환"""
        self._refresh_all_priorities()

        summary = {
            "total_keywords": len(self.keyword_schedules),
            "by_priority": {
                "critical": [],
                "high": [],
                "medium": [],
                "low": []
            },
            "pending_scans": [],
            "last_updated": datetime.now().isoformat()
        }

        now = datetime.now()

        for keyword, info in self.keyword_schedules.items():
            priority_key = info.priority.value
            summary["by_priority"][priority_key].append({
                "keyword": keyword,
                "interval_hours": info.interval_hours,
                "last_scan": info.last_scan.isoformat() if info.last_scan else None,
                "priority_score": info.priority_score,
                "search_volume": info.search_volume,
                "conversions": info.conversions
            })

            # 스캔 대기 중인 키워드
            if info.last_scan is None:
                summary["pending_scans"].append(keyword)
            else:
                next_scan = info.last_scan + timedelta(hours=info.interval_hours)
                if now >= next_scan:
                    summary["pending_scans"].append(keyword)

        # 각 우선순위별 개수
        summary["counts"] = {
            priority: len(keywords)
            for priority, keywords in summary["by_priority"].items()
        }

        return summary

    def get_keyword_info(self, keyword: str) -> Optional[Dict[str, Any]]:
        """특정 키워드의 스케줄 정보 반환"""
        if keyword not in self.keyword_schedules:
            self.calculate_priority(keyword)

        if keyword in self.keyword_schedules:
            info = self.keyword_schedules[keyword]
            return {
                "keyword": info.keyword,
                "priority": info.priority.value,
                "interval_hours": info.interval_hours,
                "last_scan": info.last_scan.isoformat() if info.last_scan else None,
                "next_scan": (
                    (info.last_scan + timedelta(hours=info.interval_hours)).isoformat()
                    if info.last_scan else None
                ),
                "scan_count": info.scan_count,
                "priority_score": info.priority_score,
                "search_volume": info.search_volume,
                "conversions": info.conversions,
                "rank_changes": info.rank_changes
            }

        return None

    def set_manual_priority(self, keyword: str, priority: str):
        """
        키워드 우선순위 수동 설정

        Args:
            keyword: 키워드
            priority: "critical", "high", "medium", "low"
        """
        try:
            priority_enum = KeywordPriority(priority.lower())

            if keyword not in self.keyword_schedules:
                self.keyword_schedules[keyword] = KeywordScheduleInfo(
                    keyword=keyword,
                    priority=priority_enum,
                    interval_hours=PRIORITY_INTERVALS[priority_enum]
                )
            else:
                self.keyword_schedules[keyword].priority = priority_enum
                self.keyword_schedules[keyword].interval_hours = PRIORITY_INTERVALS[priority_enum]

            self._save_schedules()
            logger.info(f"Manual priority set: {keyword} → {priority}")

        except ValueError:
            logger.error(f"Invalid priority: {priority}")


# 싱글톤 인스턴스
_keyword_priority_scheduler: Optional[KeywordPriorityScheduler] = None


def get_keyword_priority_scheduler() -> KeywordPriorityScheduler:
    """KeywordPriorityScheduler 싱글톤 인스턴스 반환"""
    global _keyword_priority_scheduler
    if _keyword_priority_scheduler is None:
        _keyword_priority_scheduler = KeywordPriorityScheduler()
    return _keyword_priority_scheduler

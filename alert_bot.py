"""
Alert Bot - Actionable Alerts System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 1.4] 고도화된 알림 시스템
- 우선순위화 (Critical/Warning/Info)
- 원인 분석 + 권장 조치 포함
- 알림 피로도 관리 (중복 억제, 요약)
"""

import requests
import os
import sys
import json
import glob
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from enum import Enum
from utils import ConfigManager, logger

# Windows console encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# [Phase 2.1] Event Bus Integration
try:
    from core.event_bus import publish_event, EventType
    HAS_EVENT_BUS = True
except ImportError:
    HAS_EVENT_BUS = False


class AlertPriority(Enum):
    """알림 우선순위"""
    CRITICAL = "critical"  # 즉시 조치 필요
    WARNING = "warning"    # 주의 필요
    INFO = "info"          # 정보성


class TelegramBot:
    """
    Handles sending alerts via Telegram.
    Supports 'Mock Mode' if no token is provided.
    """
    def __init__(self, token=None, chat_id=None):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage" if self.token else None

    def send_message(self, message: str, priority: AlertPriority = AlertPriority.INFO):
        """
        Sends a text message to the configured chat_id.
        If no token, logs to console (Mock Mode).
        """
        # 우선순위에 따른 이모지 추가
        priority_prefix = {
            AlertPriority.CRITICAL: "🔴",
            AlertPriority.WARNING: "🟡",
            AlertPriority.INFO: "🔵"
        }
        prefix = priority_prefix.get(priority, "🔵")

        if not self.token or not self.chat_id:
            print(f"\n[{prefix} MOCK ALERT - {priority.value.upper()}]\n{message}\n" + "-"*30)
            return True

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }

        try:
            response = requests.post(self.base_url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info(f"{prefix} Alert Sent [{priority.value}]: {message[:50]}...")
                return True
            else:
                # Markdown 파싱 실패 시 parse_mode 없이 재시도
                if "can't parse entities" in response.text:
                    payload_plain = {
                        "chat_id": self.chat_id,
                        "text": message
                    }
                    retry = requests.post(self.base_url, json=payload_plain, timeout=10)
                    if retry.status_code == 200:
                        logger.info(f"{prefix} Alert Sent (plain) [{priority.value}]: {message[:50]}...")
                        return True
                logger.error(f"Telegram API Error: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Connection Error sending alert: {e}")
            return False


class ActionableAlert:
    """
    [Phase 1.4] 실행 가능한 알림 구조
    원인 분석 + 권장 조치를 포함하는 알림
    """
    def __init__(
        self,
        priority: AlertPriority,
        title: str,
        situation: str,
        analysis: str = None,
        actions: List[str] = None,
        deep_link: str = None,
        category: str = "general"
    ):
        self.priority = priority
        self.title = title
        self.situation = situation
        self.analysis = analysis or ""
        self.actions = actions or []
        self.deep_link = deep_link
        self.category = category
        self.timestamp = datetime.now()

    def format_message(self) -> str:
        """Telegram/콘솔 출력용 메시지 포맷"""
        priority_emoji = {
            AlertPriority.CRITICAL: "🔴 [CRITICAL]",
            AlertPriority.WARNING: "🟡 [WARNING]",
            AlertPriority.INFO: "🔵 [INFO]"
        }

        lines = [
            f"{priority_emoji.get(self.priority, '🔵')} *{self.title}*",
            "",
            f"📊 *상황:*",
            f"{self.situation}",
        ]

        if self.analysis:
            lines.extend([
                "",
                f"🔍 *원인 분석:*",
                f"{self.analysis}"
            ])

        if self.actions:
            lines.extend([
                "",
                f"✅ *권장 조치:*"
            ])
            for i, action in enumerate(self.actions, 1):
                lines.append(f"  {i}. {action}")

        if self.deep_link:
            lines.extend([
                "",
                f"🔗 [상세 보기]({self.deep_link})"
            ])

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """JSON 저장용 딕셔너리 변환"""
        return {
            "priority": self.priority.value,
            "title": self.title,
            "situation": self.situation,
            "analysis": self.analysis,
            "actions": self.actions,
            "deep_link": self.deep_link,
            "category": self.category,
            "timestamp": self.timestamp.isoformat()
        }


class AlertAggregator:
    """
    [Phase 1.4] 알림 피로도 관리
    - 중복 알림 억제
    - 유사 알림 그룹화
    """
    def __init__(self, history_file: str, suppression_window_hours: int = 24):
        self.history_file = history_file
        self.suppression_window = timedelta(hours=suppression_window_hours)
        self.recent_alerts: List[Dict[str, Any]] = []
        self._load_history()

    def _load_history(self):
        """최근 알림 이력 로드"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 최근 24시간 내 알림만 유지
                    cutoff = datetime.now() - self.suppression_window
                    self.recent_alerts = [
                        a for a in data
                        if datetime.fromisoformat(a.get('timestamp', '2000-01-01')) > cutoff
                    ]
            except Exception as e:
                logger.warning(f"Failed to load alert history: {e}")
                self.recent_alerts = []

    def _save_history(self):
        """알림 이력 저장"""
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.recent_alerts, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save alert history: {e}")

    def _get_alert_hash(self, alert: ActionableAlert) -> str:
        """알림 고유 해시 생성 (중복 감지용)"""
        content = f"{alert.category}|{alert.title}|{alert.situation[:100]}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def should_send(self, alert: ActionableAlert) -> bool:
        """
        알림을 보낼지 여부 결정
        - Critical은 항상 전송
        - 동일 알림은 24시간 내 중복 전송 안함
        """
        if alert.priority == AlertPriority.CRITICAL:
            return True

        alert_hash = self._get_alert_hash(alert)

        for recent in self.recent_alerts:
            if recent.get('hash') == alert_hash:
                # 같은 알림이 24시간 내에 있음
                logger.debug(f"Suppressing duplicate alert: {alert.title}")
                return False

        return True

    def record_alert(self, alert: ActionableAlert):
        """전송된 알림 기록"""
        record = alert.to_dict()
        record['hash'] = self._get_alert_hash(alert)
        self.recent_alerts.append(record)
        self._save_history()

    def get_daily_summary(self) -> Dict[str, int]:
        """일일 알림 요약 통계"""
        summary = {
            'critical': 0,
            'warning': 0,
            'info': 0,
            'total': 0
        }

        today = datetime.now().date()
        for alert in self.recent_alerts:
            try:
                alert_date = datetime.fromisoformat(alert.get('timestamp', '')).date()
                if alert_date == today:
                    priority = alert.get('priority', 'info')
                    summary[priority] = summary.get(priority, 0) + 1
                    summary['total'] += 1
            except Exception:
                pass

        return summary


class AlertSystem:
    """
    [Phase 1.4] 고도화된 알림 시스템
    """
    def __init__(self):
        self.config = ConfigManager()
        self.data_dir = os.path.join(self.config.root_dir, 'scraped_data')

        # Create data dir if not exists
        os.makedirs(self.data_dir, exist_ok=True)

        # Load credentials from secrets via ConfigManager
        secrets = self.config.load_secrets()
        self.bot_token = secrets.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = secrets.get("TELEGRAM_CHAT_ID", "")

        self.bot = TelegramBot(self.bot_token, self.chat_id)
        self.history_file = os.path.join(self.data_dir, 'alert_history.json')
        self.aggregator = AlertAggregator(self.history_file)

    def send_actionable_alert(self, alert: ActionableAlert) -> bool:
        """
        Actionable Alert 전송
        - 중복 체크 후 전송
        - 이력 기록
        - [Phase 2.1] 이벤트 발행
        """
        if not self.aggregator.should_send(alert):
            return False

        message = alert.format_message()
        success = self.bot.send_message(message, alert.priority)

        if success:
            self.aggregator.record_alert(alert)

            # [Phase 2.1] 알림 전송 이벤트 발행
            if HAS_EVENT_BUS:
                try:
                    publish_event(
                        EventType.ALERT_SENT,
                        {
                            "priority": alert.priority.value,
                            "title": alert.title,
                            "category": alert.category,
                            "actions_count": len(alert.actions)
                        },
                        source="alert_bot"
                    )
                except Exception as e:
                    logger.debug(f"Failed to publish alert event: {e}")

        return success

    def check_rank_changes(self) -> List[ActionableAlert]:
        """순위 변동 체크 및 알림 생성"""
        alerts = []

        try:
            from db.database import DatabaseManager
            db = DatabaseManager()

            # 최근 2일 순위 데이터 조회
            db.cursor.execute("""
                SELECT keyword, rank, status, checked_at
                FROM rank_history
                WHERE date(checked_at) >= date('now', '-2 days')
                ORDER BY keyword, checked_at DESC
            """)
            rows = db.cursor.fetchall()

            # 키워드별로 그룹화하여 변동 분석
            keyword_ranks = {}
            for row in rows:
                keyword, rank, status, checked_at = row
                if keyword not in keyword_ranks:
                    keyword_ranks[keyword] = []
                keyword_ranks[keyword].append({'rank': rank, 'status': status, 'date': checked_at})

            for keyword, ranks in keyword_ranks.items():
                if len(ranks) >= 2:
                    current = ranks[0]
                    previous = ranks[1]

                    if current['rank'] and previous['rank']:
                        delta = current['rank'] - previous['rank']

                        # 5위 이상 급락
                        if delta >= 5:
                            alert = ActionableAlert(
                                priority=AlertPriority.CRITICAL,
                                title=f"순위 급락 감지: {keyword}",
                                situation=f"'{keyword}' 키워드가 {previous['rank']}위 → {current['rank']}위로 {delta}계단 하락했습니다.",
                                analysis="경쟁사 활동 증가 또는 네이버 알고리즘 변동이 원인일 수 있습니다.",
                                actions=[
                                    "경쟁사 활동 확인 (Battle Intelligence)",
                                    f"'{keyword}' 관련 블로그 콘텐츠 발행",
                                    "키워드 변형으로 분산 공략"
                                ],
                                deep_link="http://localhost:3000/battle",
                                category="rank_change"
                            )
                            alerts.append(alert)

                        # 3위 이상 급등
                        elif delta <= -3:
                            alert = ActionableAlert(
                                priority=AlertPriority.INFO,
                                title=f"순위 상승: {keyword}",
                                situation=f"'{keyword}' 키워드가 {previous['rank']}위 → {current['rank']}위로 {abs(delta)}계단 상승했습니다.",
                                analysis="최근 콘텐츠 발행 효과로 보입니다.",
                                actions=[
                                    "상승 모멘텀 유지를 위해 추가 콘텐츠 발행"
                                ],
                                category="rank_change"
                            )
                            alerts.append(alert)

        except Exception as e:
            logger.error(f"순위 변동 체크 실패: {e}")

        return alerts

    def check_competitor_activity(self) -> List[ActionableAlert]:
        """경쟁사 활동 체크 및 알림 생성"""
        alerts = []

        try:
            from db.database import DatabaseManager
            db = DatabaseManager()

            # 오늘 수집된 경쟁사 리뷰 수 확인
            db.cursor.execute("""
                SELECT competitor_name, COUNT(*) as count
                FROM competitor_reviews
                WHERE date(scraped_at) = date('now')
                GROUP BY competitor_name
                HAVING count >= 10
            """)
            rows = db.cursor.fetchall()

            for row in rows:
                competitor, count = row
                alert = ActionableAlert(
                    priority=AlertPriority.WARNING,
                    title=f"경쟁사 활발한 활동: {competitor}",
                    situation=f"'{competitor}'에서 오늘 {count}개의 새 리뷰/활동이 감지되었습니다.",
                    analysis="적극적인 마케팅 캠페인이 진행 중일 수 있습니다.",
                    actions=[
                        "경쟁사 약점 분석 실행",
                        "대응 콘텐츠 전략 수립"
                    ],
                    deep_link="http://localhost:3000/competitors",
                    category="competitor_activity"
                )
                alerts.append(alert)

        except Exception as e:
            logger.error(f"경쟁사 활동 체크 실패: {e}")

        return alerts

    def check_hot_leads(self) -> List[ActionableAlert]:
        """Hot Lead 발견 알림"""
        alerts = []

        try:
            from db.database import DatabaseManager
            db = DatabaseManager()

            # 오늘 발견된 mentions 중 특정 키워드 포함된 것
            db.cursor.execute("""
                SELECT title, source, url
                FROM mentions
                WHERE date(scraped_at) = date('now')
                  AND (title LIKE '%추천%' OR title LIKE '%한의원%' OR title LIKE '%다이어트%')
                  AND status = 'New'
                LIMIT 5
            """)
            rows = db.cursor.fetchall()

            if rows:
                titles = [r[0][:30] for r in rows]
                alert = ActionableAlert(
                    priority=AlertPriority.INFO,
                    title=f"새로운 리드 {len(rows)}개 발견",
                    situation=f"오늘 발견된 주요 리드:\n• " + "\n• ".join(titles),
                    actions=[
                        "Lead Manager에서 확인 및 우선순위 평가"
                    ],
                    deep_link="http://localhost:3000/leads",
                    category="new_leads"
                )
                alerts.append(alert)

        except Exception as e:
            logger.error(f"Hot Lead 체크 실패: {e}")

        return alerts

    def check_alerts(self):
        """모든 알림 체크 실행"""
        print(f"[{datetime.now()}] 🔔 Checking for actionable alerts...")

        all_alerts = []

        # 각 체크 실행
        all_alerts.extend(self.check_rank_changes())
        all_alerts.extend(self.check_competitor_activity())
        all_alerts.extend(self.check_hot_leads())

        # 우선순위별 정렬 (Critical > Warning > Info)
        priority_order = {AlertPriority.CRITICAL: 0, AlertPriority.WARNING: 1, AlertPriority.INFO: 2}
        all_alerts.sort(key=lambda a: priority_order.get(a.priority, 2))

        # 알림 전송
        sent_count = 0
        for alert in all_alerts:
            if self.send_actionable_alert(alert):
                sent_count += 1

        # 일일 요약
        summary = self.aggregator.get_daily_summary()
        print(f">> Alerts today: {summary['total']} (Critical: {summary['critical']}, Warning: {summary['warning']}, Info: {summary['info']})")
        print(f">> New alerts sent: {sent_count}")

        return all_alerts

    def send_daily_summary(self):
        """일일 요약 알림 전송"""
        summary = self.aggregator.get_daily_summary()

        if summary['total'] == 0:
            return

        message = f"""📋 *일일 알림 요약*

오늘 발생한 알림:
• 🔴 Critical: {summary['critical']}건
• 🟡 Warning: {summary['warning']}건
• 🔵 Info: {summary['info']}건

총 {summary['total']}건의 알림이 발생했습니다.
"""
        self.bot.send_message(message, AlertPriority.INFO)


if __name__ == "__main__":
    system = AlertSystem()
    system.check_alerts()

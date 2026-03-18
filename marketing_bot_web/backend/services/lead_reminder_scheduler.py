"""
Lead Reminder Scheduler - Hot Lead 골든타임 재알림 시스템
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 4-2-A] Hot Lead 재알림 (4시간마다)
- 재알림 간격: 4시간 → 8시간 → 16시간 → 24시간 → 48시간 (최대 5회)
- 긴급도 레벨별 메시지 차등화
- 텔레그램/카카오톡 알림 발송
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# 프로젝트 루트 경로 설정
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger(__name__)

# DB 경로
DB_PATH = os.path.join(PROJECT_ROOT, 'db', 'marketing_data.db')


class UrgencyLevel(Enum):
    """긴급도 레벨"""
    NORMAL = "normal"         # 🟢 새 Hot Lead
    REMINDER = "reminder"     # 🟢 리마인더
    WARNING = "warning"       # 🟡 주의
    URGENT = "urgent"         # 🟠 긴급
    CRITICAL = "critical"     # 🔴 위험


# 재알림 간격 (시간)
REMINDER_INTERVALS = [4, 8, 16, 24, 48]  # 1~5회차 재알림

# 긴급도 레벨 결정 기준 (시간)
URGENCY_THRESHOLDS = {
    4: UrgencyLevel.NORMAL,      # 4시간 미만
    12: UrgencyLevel.REMINDER,   # 4-12시간
    24: UrgencyLevel.WARNING,    # 12-24시간
    48: UrgencyLevel.URGENT,     # 24-48시간
    float('inf'): UrgencyLevel.CRITICAL  # 48시간+
}


@dataclass
class HotLeadReminder:
    """Hot Lead 재알림 정보"""
    lead_id: int
    lead_type: str  # 'mention' or 'viral_target'
    platform: str
    author: str
    content: str
    score: int
    created_at: datetime
    last_reminder_at: Optional[datetime]
    reminder_count: int
    hours_elapsed: float
    urgency_level: UrgencyLevel
    next_reminder_in_hours: Optional[float]


class LeadReminderScheduler:
    """
    Hot Lead 재알림 스케줄러

    미응답 Hot Lead에 대해 주기적으로 재알림을 발송
    """

    def __init__(self, min_score: int = 70, max_reminders: int = 5):
        """
        Args:
            min_score: Hot Lead 최소 점수
            max_reminders: 최대 재알림 횟수
        """
        self.min_score = min_score
        self.max_reminders = max_reminders

        logger.info(f"LeadReminderScheduler initialized (min_score={min_score}, max_reminders={max_reminders})")

    def get_pending_reminders(self) -> List[HotLeadReminder]:
        """
        재알림이 필요한 Hot Lead 목록 조회

        조건:
        - score >= min_score
        - status = 'pending' (미응답)
        - reminder_count < max_reminders
        - 재알림 간격 초과
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        pending_leads = []

        try:
            now = datetime.now()

            # mentions 테이블에서 Hot Lead 조회
            cursor.execute('''
                SELECT
                    id,
                    'mention' as lead_type,
                    source as platform,
                    author,
                    content,
                    COALESCE(score, 0) as score,
                    scraped_at,
                    last_reminder_at,
                    COALESCE(reminder_count, 0) as reminder_count
                FROM mentions
                WHERE status = 'pending'
                AND COALESCE(score, 0) >= ?
                AND COALESCE(reminder_count, 0) < ?
            ''', (self.min_score, self.max_reminders))

            for row in cursor.fetchall():
                lead_id, lead_type, platform, author, content, score, scraped_at, last_reminder_at, reminder_count = row

                # 시간 파싱
                created_at = datetime.fromisoformat(scraped_at) if scraped_at else now
                last_reminder = datetime.fromisoformat(last_reminder_at) if last_reminder_at else None

                # 경과 시간 계산
                hours_elapsed = (now - created_at).total_seconds() / 3600

                # 긴급도 레벨 결정
                urgency_level = self._determine_urgency(hours_elapsed)

                # 다음 재알림까지 남은 시간 계산
                next_reminder_in = self._calculate_next_reminder(
                    created_at, last_reminder, reminder_count
                )

                # 재알림이 필요한지 확인
                if next_reminder_in is not None and next_reminder_in <= 0:
                    pending_leads.append(HotLeadReminder(
                        lead_id=lead_id,
                        lead_type=lead_type,
                        platform=platform or 'unknown',
                        author=author or 'Unknown',
                        content=content[:100] if content else '',
                        score=score,
                        created_at=created_at,
                        last_reminder_at=last_reminder,
                        reminder_count=reminder_count,
                        hours_elapsed=hours_elapsed,
                        urgency_level=urgency_level,
                        next_reminder_in_hours=0
                    ))

        except Exception as e:
            logger.error(f"Failed to get pending reminders: {e}")

        finally:
            conn.close()

        # 긴급도 높은 순으로 정렬
        urgency_order = [UrgencyLevel.CRITICAL, UrgencyLevel.URGENT, UrgencyLevel.WARNING, UrgencyLevel.REMINDER, UrgencyLevel.NORMAL]
        pending_leads.sort(key=lambda x: (urgency_order.index(x.urgency_level), -x.hours_elapsed))

        return pending_leads

    def _determine_urgency(self, hours_elapsed: float) -> UrgencyLevel:
        """경과 시간에 따른 긴급도 결정"""
        for threshold, level in URGENCY_THRESHOLDS.items():
            if hours_elapsed < threshold:
                return level
        return UrgencyLevel.CRITICAL

    def _calculate_next_reminder(
        self,
        created_at: datetime,
        last_reminder: Optional[datetime],
        reminder_count: int
    ) -> Optional[float]:
        """
        다음 재알림까지 남은 시간 계산

        Returns:
            남은 시간 (시간), 0 이하면 재알림 필요
            None이면 재알림 불필요 (최대 횟수 초과)
        """
        if reminder_count >= self.max_reminders:
            return None

        now = datetime.now()

        if reminder_count == 0:
            # 첫 재알림: 생성 후 4시간
            next_reminder_time = created_at + timedelta(hours=REMINDER_INTERVALS[0])
        else:
            # 이후 재알림: 마지막 재알림 기준
            if last_reminder is None:
                return 0  # 즉시 재알림

            interval_index = min(reminder_count, len(REMINDER_INTERVALS) - 1)
            interval = REMINDER_INTERVALS[interval_index]
            next_reminder_time = last_reminder + timedelta(hours=interval)

        return (next_reminder_time - now).total_seconds() / 3600

    def send_reminders(self) -> Dict[str, Any]:
        """
        재알림 발송

        Returns:
            {
                "sent": 발송 성공 수,
                "failed": 발송 실패 수,
                "details": [각 리드별 결과]
            }
        """
        pending = self.get_pending_reminders()
        result = {
            "sent": 0,
            "failed": 0,
            "details": [],
            "timestamp": datetime.now().isoformat()
        }

        if not pending:
            logger.info("No pending reminders to send")
            return result

        logger.info(f"Sending {len(pending)} reminders...")

        for lead in pending:
            try:
                # 알림 메시지 생성
                message = self._create_reminder_message(lead)

                # 알림 발송
                success = self._send_notification(lead, message)

                if success:
                    # DB 업데이트
                    self._update_reminder_status(lead)
                    result["sent"] += 1
                    result["details"].append({
                        "lead_id": lead.lead_id,
                        "status": "sent",
                        "urgency": lead.urgency_level.value
                    })
                else:
                    result["failed"] += 1
                    result["details"].append({
                        "lead_id": lead.lead_id,
                        "status": "failed",
                        "error": "Notification send failed"
                    })

            except Exception as e:
                logger.error(f"Failed to send reminder for lead {lead.lead_id}: {e}")
                result["failed"] += 1
                result["details"].append({
                    "lead_id": lead.lead_id,
                    "status": "error",
                    "error": str(e)
                })

        logger.info(f"Reminders sent: {result['sent']}, failed: {result['failed']}")
        return result

    def _create_reminder_message(self, lead: HotLeadReminder) -> str:
        """긴급도별 재알림 메시지 생성"""
        urgency_emojis = {
            UrgencyLevel.NORMAL: "🟢",
            UrgencyLevel.REMINDER: "🟢",
            UrgencyLevel.WARNING: "🟡",
            UrgencyLevel.URGENT: "🟠",
            UrgencyLevel.CRITICAL: "🔴"
        }

        urgency_messages = {
            UrgencyLevel.NORMAL: "새 Hot Lead가 발견되었습니다!",
            UrgencyLevel.REMINDER: "아직 연락하지 않았습니다",
            UrgencyLevel.WARNING: "골든타임이 지나고 있습니다!",
            UrgencyLevel.URGENT: "즉시 연락이 필요합니다!",
            UrgencyLevel.CRITICAL: "기회를 놓칠 수 있습니다!"
        }

        emoji = urgency_emojis[lead.urgency_level]
        urgency_msg = urgency_messages[lead.urgency_level]

        hours = int(lead.hours_elapsed)
        reminder_num = lead.reminder_count + 1

        message = f"""
{emoji} [Hot Lead 재알림 {reminder_num}회차]
━━━━━━━━━━━━━━━━
⚠️ {urgency_msg}

📍 플랫폼: {lead.platform}
👤 작성자: {lead.author}
💯 점수: {lead.score}점
⏰ 경과: {hours}시간

📝 내용 미리보기:
{lead.content[:80]}...

👉 대시보드에서 확인해주세요!
""".strip()

        return message

    def _send_notification(self, lead: HotLeadReminder, message: str) -> bool:
        """알림 발송"""
        try:
            # 텔레그램 알림 시도
            from alert_bot import AlertSystem
            alert = AlertSystem()
            alert.bot.send_message(message)
            return True

        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False

    def _update_reminder_status(self, lead: HotLeadReminder):
        """재알림 상태 업데이트"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        try:
            now = datetime.now().isoformat()
            new_count = lead.reminder_count + 1

            # mentions 테이블 업데이트
            if lead.lead_type == 'mention':
                cursor.execute('''
                    UPDATE mentions
                    SET last_reminder_at = ?, reminder_count = ?
                    WHERE id = ?
                ''', (now, new_count, lead.lead_id))

            # 재알림 이력 저장
            cursor.execute('''
                INSERT INTO lead_reminder_history
                (lead_id, lead_type, sent_at, reminder_number, urgency_level, channel, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                lead.lead_id,
                lead.lead_type,
                now,
                new_count,
                lead.urgency_level.value,
                'telegram',
                'sent'
            ))

            conn.commit()
            logger.debug(f"Updated reminder status for lead {lead.lead_id}")

        except Exception as e:
            logger.error(f"Failed to update reminder status: {e}")
            conn.rollback()

        finally:
            conn.close()

    def get_reminder_stats(self) -> Dict[str, Any]:
        """재알림 통계 조회"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        stats = {
            "pending_count": 0,
            "by_urgency": {},
            "total_reminders_sent": 0,
            "recent_reminders": []
        }

        try:
            # 대기 중인 Hot Lead 수
            cursor.execute('''
                SELECT COUNT(*) FROM mentions
                WHERE status = 'pending' AND COALESCE(score, 0) >= ?
            ''', (self.min_score,))
            stats["pending_count"] = cursor.fetchone()[0]

            # 최근 재알림 이력
            cursor.execute('''
                SELECT
                    lead_id, lead_type, sent_at, reminder_number, urgency_level, channel
                FROM lead_reminder_history
                ORDER BY sent_at DESC
                LIMIT 10
            ''')
            for row in cursor.fetchall():
                stats["recent_reminders"].append({
                    "lead_id": row[0],
                    "lead_type": row[1],
                    "sent_at": row[2],
                    "reminder_number": row[3],
                    "urgency_level": row[4],
                    "channel": row[5]
                })

            # 총 발송 횟수
            cursor.execute('SELECT COUNT(*) FROM lead_reminder_history')
            stats["total_reminders_sent"] = cursor.fetchone()[0]

        except Exception as e:
            logger.error(f"Failed to get reminder stats: {e}")

        finally:
            conn.close()

        return stats


# 편의 함수
def run_lead_reminders() -> Dict[str, Any]:
    """Hot Lead 재알림 실행"""
    scheduler = LeadReminderScheduler()
    return scheduler.send_reminders()


def get_reminder_status() -> Dict[str, Any]:
    """재알림 상태 조회"""
    scheduler = LeadReminderScheduler()
    return {
        "pending_reminders": [
            {
                "lead_id": r.lead_id,
                "platform": r.platform,
                "author": r.author,
                "score": r.score,
                "hours_elapsed": round(r.hours_elapsed, 1),
                "urgency_level": r.urgency_level.value,
                "reminder_count": r.reminder_count
            }
            for r in scheduler.get_pending_reminders()
        ],
        "stats": scheduler.get_reminder_stats()
    }

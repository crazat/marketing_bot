"""
Lead Status Automator - 리드 상태 자동 전이 시스템
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 4-2-B] 리드 상태 자동 전이
- contacted → rejected (7일 미응답)
- pending → archived (14일 미처리)
- replied → pending_review (30일 경과)

실행 스케줄: 매일 06:00
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

# 프로젝트 루트 경로 설정
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger(__name__)

# DB 경로
DB_PATH = os.path.join(PROJECT_ROOT, 'db', 'marketing_data.db')


@dataclass
class StatusTransitionRule:
    """상태 전이 규칙"""
    from_status: str
    to_status: str
    days_threshold: int
    reason: str
    applies_to: List[str]  # 적용 대상 테이블 ['mentions', 'viral_targets']


# 상태 전이 규칙 정의
TRANSITION_RULES = [
    StatusTransitionRule(
        from_status="contacted",
        to_status="rejected",
        days_threshold=7,
        reason="7일간 응답 없음",
        applies_to=["mentions"]
    ),
    StatusTransitionRule(
        from_status="pending",
        to_status="archived",
        days_threshold=14,
        reason="14일간 미처리",
        applies_to=["mentions"]
    ),
    StatusTransitionRule(
        from_status="replied",
        to_status="pending_review",
        days_threshold=30,
        reason="30일 경과 - 결과 확인 필요",
        applies_to=["mentions"]
    ),
    # viral_targets용 규칙
    StatusTransitionRule(
        from_status="commented",
        to_status="expired",
        days_threshold=30,
        reason="30일간 반응 없음",
        applies_to=["viral_targets"]
    ),
    StatusTransitionRule(
        from_status="pending",
        to_status="expired",
        days_threshold=14,
        reason="14일간 미처리",
        applies_to=["viral_targets"]
    ),
]


class LeadStatusAutomator:
    """
    리드 상태 자동 전이 시스템

    정의된 규칙에 따라 일정 기간 동안 변화가 없는 리드의 상태를 자동 전이
    """

    def __init__(self, dry_run: bool = False):
        """
        Args:
            dry_run: True면 실제 DB 변경 없이 시뮬레이션만 수행
        """
        self.dry_run = dry_run
        self.rules = TRANSITION_RULES

        logger.info(f"LeadStatusAutomator initialized (dry_run={dry_run})")

    def run_transitions(self) -> Dict[str, Any]:
        """
        모든 전이 규칙 실행

        Returns:
            {
                "total_transitioned": 총 전이 수,
                "by_rule": {규칙별 전이 수},
                "details": [각 전이 상세]
            }
        """
        result = {
            "total_transitioned": 0,
            "by_rule": {},
            "details": [],
            "dry_run": self.dry_run,
            "timestamp": datetime.now().isoformat()
        }

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        try:
            for rule in self.rules:
                rule_key = f"{rule.from_status}_to_{rule.to_status}"
                rule_result = self._apply_rule(cursor, rule)

                result["by_rule"][rule_key] = rule_result["count"]
                result["total_transitioned"] += rule_result["count"]
                result["details"].extend(rule_result["details"])

            if not self.dry_run:
                conn.commit()
                logger.info(f"Committed {result['total_transitioned']} status transitions")
            else:
                logger.info(f"Dry run: would transition {result['total_transitioned']} leads")

        except Exception as e:
            logger.error(f"Error during status transitions: {e}")
            conn.rollback()
            result["error"] = str(e)

        finally:
            conn.close()

        return result

    def _apply_rule(self, cursor: sqlite3.Cursor, rule: StatusTransitionRule) -> Dict[str, Any]:
        """개별 전이 규칙 적용"""
        result = {
            "count": 0,
            "details": []
        }

        cutoff_date = (datetime.now() - timedelta(days=rule.days_threshold)).isoformat()

        for table in rule.applies_to:
            try:
                # 상태 전이 대상 조회
                if table == "mentions":
                    date_column = "scraped_at"
                    status_column = "status"
                else:  # viral_targets
                    date_column = "created_at"
                    status_column = "comment_status"

                # 전이 대상 조회
                cursor.execute(f'''
                    SELECT id, {status_column}, {date_column}
                    FROM {table}
                    WHERE {status_column} = ?
                    AND {date_column} < ?
                ''', (rule.from_status, cutoff_date))

                rows = cursor.fetchall()

                for row in rows:
                    lead_id, current_status, date_value = row

                    # 상태 전이 실행
                    if not self.dry_run:
                        cursor.execute(f'''
                            UPDATE {table}
                            SET {status_column} = ?
                            WHERE id = ?
                        ''', (rule.to_status, lead_id))

                        # 전이 이력 저장
                        self._save_transition_history(
                            cursor, lead_id, table,
                            rule.from_status, rule.to_status, rule.reason
                        )

                    result["count"] += 1
                    result["details"].append({
                        "lead_id": lead_id,
                        "table": table,
                        "from_status": rule.from_status,
                        "to_status": rule.to_status,
                        "reason": rule.reason,
                        "days_inactive": rule.days_threshold
                    })

                    logger.debug(
                        f"{'[DRY RUN] ' if self.dry_run else ''}"
                        f"Transition: {table}#{lead_id} {rule.from_status} → {rule.to_status}"
                    )

            except Exception as e:
                logger.error(f"Error applying rule to {table}: {e}")

        return result

    def _save_transition_history(
        self,
        cursor: sqlite3.Cursor,
        lead_id: int,
        table: str,
        from_status: str,
        to_status: str,
        reason: str
    ):
        """전이 이력 저장"""
        try:
            lead_type = 'mention' if table == 'mentions' else 'viral_target'

            cursor.execute('''
                INSERT INTO lead_status_transition_history
                (lead_id, lead_type, from_status, to_status, reason, transitioned_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (lead_id, lead_type, from_status, to_status, reason, datetime.now().isoformat()))

        except Exception as e:
            logger.warning(f"Failed to save transition history: {e}")

    def get_transition_candidates(self) -> Dict[str, Any]:
        """
        전이 대상 후보 조회 (dry run과 유사하지만 미리보기용)
        """
        result = {
            "total_candidates": 0,
            "by_rule": {},
            "details": []
        }

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        try:
            for rule in self.rules:
                rule_key = f"{rule.from_status}_to_{rule.to_status}"
                cutoff_date = (datetime.now() - timedelta(days=rule.days_threshold)).isoformat()

                candidates = []

                for table in rule.applies_to:
                    if table == "mentions":
                        date_column = "scraped_at"
                        status_column = "status"
                    else:
                        date_column = "created_at"
                        status_column = "comment_status"

                    cursor.execute(f'''
                        SELECT id, {status_column}, {date_column}
                        FROM {table}
                        WHERE {status_column} = ?
                        AND {date_column} < ?
                    ''', (rule.from_status, cutoff_date))

                    for row in cursor.fetchall():
                        lead_id, status, date_value = row
                        days_ago = (datetime.now() - datetime.fromisoformat(date_value)).days if date_value else 0

                        candidates.append({
                            "lead_id": lead_id,
                            "table": table,
                            "current_status": status,
                            "days_inactive": days_ago,
                            "will_transition_to": rule.to_status,
                            "reason": rule.reason
                        })

                result["by_rule"][rule_key] = len(candidates)
                result["total_candidates"] += len(candidates)
                result["details"].extend(candidates)

        except Exception as e:
            logger.error(f"Error getting transition candidates: {e}")
            result["error"] = str(e)

        finally:
            conn.close()

        return result

    def get_transition_history(self, days: int = 7, limit: int = 100) -> List[Dict[str, Any]]:
        """최근 전이 이력 조회"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        history = []

        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()

            cursor.execute('''
                SELECT
                    id, lead_id, lead_type, from_status, to_status, reason, transitioned_at
                FROM lead_status_transition_history
                WHERE transitioned_at >= ?
                ORDER BY transitioned_at DESC
                LIMIT ?
            ''', (cutoff, limit))

            for row in cursor.fetchall():
                history.append({
                    "id": row[0],
                    "lead_id": row[1],
                    "lead_type": row[2],
                    "from_status": row[3],
                    "to_status": row[4],
                    "reason": row[5],
                    "transitioned_at": row[6]
                })

        except Exception as e:
            logger.error(f"Error getting transition history: {e}")

        finally:
            conn.close()

        return history

    def get_status_summary(self) -> Dict[str, Any]:
        """리드 상태 요약 통계"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        summary = {
            "mentions": {},
            "viral_targets": {},
            "transition_history": {
                "today": 0,
                "week": 0,
                "total": 0
            }
        }

        try:
            # mentions 상태별 카운트
            cursor.execute('''
                SELECT status, COUNT(*) FROM mentions GROUP BY status
            ''')
            for row in cursor.fetchall():
                summary["mentions"][row[0] or "unknown"] = row[1]

            # viral_targets 상태별 카운트
            cursor.execute('''
                SELECT comment_status, COUNT(*) FROM viral_targets GROUP BY comment_status
            ''')
            for row in cursor.fetchall():
                summary["viral_targets"][row[0] or "unknown"] = row[1]

            # 전이 이력 통계
            cursor.execute('''
                SELECT COUNT(*) FROM lead_status_transition_history
                WHERE transitioned_at >= date('now')
            ''')
            summary["transition_history"]["today"] = cursor.fetchone()[0]

            cursor.execute('''
                SELECT COUNT(*) FROM lead_status_transition_history
                WHERE transitioned_at >= date('now', '-7 days')
            ''')
            summary["transition_history"]["week"] = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM lead_status_transition_history')
            summary["transition_history"]["total"] = cursor.fetchone()[0]

        except Exception as e:
            logger.error(f"Error getting status summary: {e}")

        finally:
            conn.close()

        return summary


# 편의 함수
def run_status_transitions(dry_run: bool = False) -> Dict[str, Any]:
    """리드 상태 자동 전이 실행"""
    automator = LeadStatusAutomator(dry_run=dry_run)
    return automator.run_transitions()


def get_transition_preview() -> Dict[str, Any]:
    """전이 대상 미리보기"""
    automator = LeadStatusAutomator(dry_run=True)
    return automator.get_transition_candidates()


def get_lead_status_summary() -> Dict[str, Any]:
    """리드 상태 요약"""
    automator = LeadStatusAutomator()
    return automator.get_status_summary()

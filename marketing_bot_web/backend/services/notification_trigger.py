"""
Notification Trigger Service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Marketing Enhancement 2.0] 이벤트 감지 및 알림 트리거
- 순위 급락 감지 (5위+ 하락)
- 신규 Hot Lead 감지 (70점+)
- 경쟁사 활동 감지
- 시스템 오류 알림

주기적으로 실행되어 조건에 맞는 이벤트 발생 시 알림 발송
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import asyncio

from .notification_sender import get_notification_sender, NotificationType

logger = logging.getLogger(__name__)

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / 'db' / 'marketing_data.db'


class NotificationTrigger:
    """알림 트리거 서비스"""

    def __init__(self):
        self.sender = get_notification_sender()
        self._last_check = {}

    def _get_settings(self) -> Dict[str, Any]:
        """알림 설정 조회"""
        conn = None
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM notification_settings LIMIT 1")
            row = cursor.fetchone()
            return dict(row) if row else {}
        except Exception as e:
            logger.error(f"알림 설정 조회 실패: {e}")
            return {}
        finally:
            if conn:
                conn.close()

    async def check_rank_drops(self) -> List[Dict[str, Any]]:
        """
        순위 급락 감지

        설정된 임계값(기본 5위) 이상 하락한 키워드 감지
        """
        settings = self._get_settings()
        if not (settings.get('telegram_enabled') or settings.get('kakao_enabled')):
            return []

        threshold = settings.get('rank_drop_threshold', 5)
        alerts = []
        conn = None

        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 오늘과 어제 순위 비교
            cursor.execute("""
                SELECT
                    r1.keyword,
                    r1.rank as current_rank,
                    r2.rank as prev_rank,
                    (r2.rank - r1.rank) as rank_change,
                    r1.device_type
                FROM rank_history r1
                JOIN rank_history r2 ON r1.keyword = r2.keyword
                    AND r1.device_type = r2.device_type
                WHERE r1.scanned_date = date('now')
                    AND r2.scanned_date = date('now', '-1 day')
                    AND r1.status = 'found'
                    AND r2.status = 'found'
                    AND (r1.rank - r2.rank) >= ?
                ORDER BY (r1.rank - r2.rank) DESC
                LIMIT 10
            """, (threshold,))

            rows = cursor.fetchall()

            for row in rows:
                keyword = row['keyword']
                drop = row['current_rank'] - row['prev_rank']

                # 이미 알림 보낸 키워드인지 확인 (1시간 내 중복 방지)
                cache_key = f"rank_drop_{keyword}_{row['device_type']}"
                if cache_key in self._last_check:
                    if datetime.now() - self._last_check[cache_key] < timedelta(hours=1):
                        continue

                alert = {
                    'keyword': keyword,
                    'current_rank': row['current_rank'],
                    'prev_rank': row['prev_rank'],
                    'drop': drop,
                    'device_type': row['device_type']
                }
                alerts.append(alert)

                # 알림 발송
                result = await self.sender.send(
                    title=f"순위 급락: {keyword}",
                    message=f"키워드 '{keyword}'의 순위가 {drop}위 하락했습니다.\n"
                            f"이전: {row['prev_rank']}위 → 현재: {row['current_rank']}위\n"
                            f"디바이스: {row['device_type']}",
                    notification_type='rank_drop',
                    metadata=alert
                )

                if result.get('success'):
                    self._last_check[cache_key] = datetime.now()
                    logger.info(f"순위 급락 알림 발송: {keyword}")

        except Exception as e:
            logger.error(f"순위 급락 감지 오류: {e}")
        finally:
            if conn:
                conn.close()

        return alerts

    async def check_new_hot_leads(self) -> List[Dict[str, Any]]:
        """
        신규 Hot Lead 감지

        설정된 최소 점수(기본 70점) 이상의 신규 리드 감지
        """
        settings = self._get_settings()
        if not (settings.get('telegram_enabled') or settings.get('kakao_enabled')):
            return []

        min_score = settings.get('new_lead_min_score', 70)
        alerts = []
        conn = None

        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 최근 1시간 내 고점수 리드
            cursor.execute("""
                SELECT
                    id, author, content, score, platform, url,
                    created_at
                FROM mentions
                WHERE score >= ?
                    AND status = 'pending'
                    AND created_at > datetime('now', '-1 hour')
                ORDER BY score DESC
                LIMIT 5
            """, (min_score,))

            rows = cursor.fetchall()

            for row in rows:
                lead_id = row['id']

                # 이미 알림 보낸 리드인지 확인
                cache_key = f"new_lead_{lead_id}"
                if cache_key in self._last_check:
                    continue

                alert = {
                    'lead_id': lead_id,
                    'author': row['author'],
                    'score': row['score'],
                    'platform': row['platform'],
                    'url': row['url']
                }
                alerts.append(alert)

                # 알림 발송
                content_preview = (row['content'] or '')[:100]
                result = await self.sender.send(
                    title=f"Hot Lead 발견! (점수: {row['score']})",
                    message=f"새로운 고점수 리드가 발견되었습니다.\n\n"
                            f"작성자: {row['author']}\n"
                            f"플랫폼: {row['platform']}\n"
                            f"내용: {content_preview}...\n"
                            f"URL: {row['url']}",
                    notification_type='new_lead',
                    metadata=alert
                )

                if result.get('success'):
                    self._last_check[cache_key] = datetime.now()
                    logger.info(f"Hot Lead 알림 발송: ID {lead_id}")

        except Exception as e:
            logger.error(f"Hot Lead 감지 오류: {e}")
        finally:
            if conn:
                conn.close()

        return alerts

    async def check_competitor_activity(self) -> List[Dict[str, Any]]:
        """
        경쟁사 활동 감지

        경쟁사 순위 상승, 새 바이럴 콘텐츠 등 감지
        """
        settings = self._get_settings()
        if not settings.get('competitor_activity_alert'):
            return []
        if not (settings.get('telegram_enabled') or settings.get('kakao_enabled')):
            return []

        alerts = []
        conn = None

        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 경쟁사 순위 5위+ 상승 감지
            cursor.execute("""
                SELECT
                    r1.competitor_name,
                    r1.keyword,
                    r1.rank as current_rank,
                    r2.rank as prev_rank
                FROM competitor_rankings r1
                JOIN competitor_rankings r2
                    ON r1.competitor_name = r2.competitor_name
                    AND r1.keyword = r2.keyword
                WHERE r1.scanned_date = date('now')
                    AND r2.scanned_date = date('now', '-1 day')
                    AND (r2.rank - r1.rank) >= 5
                ORDER BY (r2.rank - r1.rank) DESC
                LIMIT 5
            """)

            rows = cursor.fetchall()

            for row in rows:
                cache_key = f"competitor_{row['competitor_name']}_{row['keyword']}"
                if cache_key in self._last_check:
                    if datetime.now() - self._last_check[cache_key] < timedelta(hours=6):
                        continue

                improvement = row['prev_rank'] - row['current_rank']
                alert = {
                    'competitor': row['competitor_name'],
                    'keyword': row['keyword'],
                    'current_rank': row['current_rank'],
                    'prev_rank': row['prev_rank'],
                    'improvement': improvement
                }
                alerts.append(alert)

                result = await self.sender.send(
                    title=f"경쟁사 순위 상승: {row['competitor_name']}",
                    message=f"경쟁사 '{row['competitor_name']}'의 순위가 상승했습니다.\n\n"
                            f"키워드: {row['keyword']}\n"
                            f"이전: {row['prev_rank']}위 → 현재: {row['current_rank']}위\n"
                            f"({improvement}위 상승)",
                    notification_type='competitor_activity',
                    metadata=alert
                )

                if result.get('success'):
                    self._last_check[cache_key] = datetime.now()

        except Exception as e:
            logger.error(f"경쟁사 활동 감지 오류: {e}")
        finally:
            if conn:
                conn.close()

        return alerts

    async def send_system_error(
        self,
        error_title: str,
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        시스템 오류 알림 발송

        Args:
            error_title: 오류 제목
            error_message: 오류 메시지
            error_details: 상세 정보

        Returns:
            발송 결과
        """
        settings = self._get_settings()
        if not settings.get('system_error_alert'):
            return {'success': False, 'error': '시스템 오류 알림이 비활성화되어 있습니다'}

        return await self.sender.send(
            title=f"시스템 오류: {error_title}",
            message=error_message,
            notification_type='system_error',
            metadata=error_details,
            ignore_quiet_hours=True  # 시스템 오류는 항상 발송
        )

    async def run_all_checks(self) -> Dict[str, List[Dict[str, Any]]]:
        """모든 트리거 체크 실행"""
        results = {}

        results['rank_drops'] = await self.check_rank_drops()
        results['new_leads'] = await self.check_new_hot_leads()
        results['competitor_activity'] = await self.check_competitor_activity()

        total = sum(len(v) for v in results.values())
        if total > 0:
            logger.info(f"알림 트리거 실행 완료: {total}개 알림 발송")

        return results


# 싱글톤 인스턴스
_notification_trigger = None


def get_notification_trigger() -> NotificationTrigger:
    """알림 트리거 서비스 인스턴스 반환"""
    global _notification_trigger
    if _notification_trigger is None:
        _notification_trigger = NotificationTrigger()
    return _notification_trigger


async def run_notification_checks() -> Dict[str, List[Dict[str, Any]]]:
    """알림 트리거 체크 실행 편의 함수"""
    trigger = get_notification_trigger()
    return await trigger.run_all_checks()


# 테스트용
if __name__ == "__main__":
    async def test():
        trigger = NotificationTrigger()
        results = await trigger.run_all_checks()
        print(f"결과: {json.dumps(results, ensure_ascii=False, indent=2)}")

    asyncio.run(test())

"""
Notification Sender Service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Marketing Enhancement 2.0] 실시간 알림 발송 서비스
- 텔레그램 Bot API 연동
- 카카오톡 알림톡 연동

지원하는 알림 유형:
- rank_drop: 순위 급락 알림
- new_lead: 신규 Hot Lead 알림
- competitor_activity: 경쟁사 활동 감지
- system_error: 시스템 오류 알림
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime, time
from typing import Dict, Any, Optional, Literal
import httpx
import asyncio

logger = logging.getLogger(__name__)

# 프로젝트 루트 (services -> backend -> marketing_bot_web -> marketing_bot)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / 'db' / 'marketing_data.db'

NotificationChannel = Literal['telegram', 'kakao', 'all']
NotificationType = Literal['rank_drop', 'new_lead', 'competitor_activity', 'system_error', 'test']


class NotificationSender:
    """알림 발송 서비스"""

    def __init__(self):
        self.settings = self._load_settings()

    def _load_settings(self) -> Dict[str, Any]:
        """알림 설정 로드"""
        conn = None
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM notification_settings LIMIT 1")
            row = cursor.fetchone()

            if row:
                return dict(row)
            return {
                'telegram_enabled': 0,
                'kakao_enabled': 0,
                'rank_drop_threshold': 5,
                'new_lead_min_score': 70,
            }
        except Exception as e:
            logger.error(f"알림 설정 로드 실패: {e}")
            return {}
        finally:
            if conn:
                conn.close()

    def reload_settings(self):
        """설정 새로고침"""
        self.settings = self._load_settings()

    def is_quiet_hours(self) -> bool:
        """방해금지 시간대인지 확인"""
        try:
            quiet_start = self.settings.get('alert_quiet_start', '22:00')
            quiet_end = self.settings.get('alert_quiet_end', '08:00')

            now = datetime.now().time()
            start = time(*map(int, quiet_start.split(':')))
            end = time(*map(int, quiet_end.split(':')))

            # 자정을 넘어가는 경우 (예: 22:00 ~ 08:00)
            if start > end:
                return now >= start or now <= end
            else:
                return start <= now <= end
        except Exception:
            return False

    async def send_telegram(
        self,
        title: str,
        message: str,
        notification_type: NotificationType = 'system_error',
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """텔레그램 메시지 발송"""
        if not self.settings.get('telegram_enabled'):
            return {'success': False, 'error': '텔레그램 알림이 비활성화되어 있습니다'}

        bot_token = self.settings.get('telegram_bot_token')
        chat_id = self.settings.get('telegram_chat_id')

        if not bot_token or not chat_id:
            return {'success': False, 'error': '텔레그램 설정이 완료되지 않았습니다'}

        # 메시지 포맷팅
        emoji_map = {
            'rank_drop': '📉',
            'new_lead': '🎯',
            'competitor_activity': '🔔',
            'system_error': '⚠️',
            'test': '🔔'
        }
        emoji = emoji_map.get(notification_type, '📢')

        formatted_message = f"{emoji} *{title}*\n\n{message}"
        if metadata:
            formatted_message += f"\n\n_상세정보: {json.dumps(metadata, ensure_ascii=False)}_"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": formatted_message,
                        "parse_mode": "Markdown"
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get('ok'):
                        self._log_notification(notification_type, 'telegram', title, message, 'sent', metadata)
                        return {'success': True, 'message_id': result.get('result', {}).get('message_id')}
                    else:
                        error = result.get('description', '알 수 없는 오류')
                        self._log_notification(notification_type, 'telegram', title, message, 'failed', metadata, error)
                        return {'success': False, 'error': error}
                else:
                    error = f"HTTP {response.status_code}"
                    self._log_notification(notification_type, 'telegram', title, message, 'failed', metadata, error)
                    return {'success': False, 'error': error}

        except httpx.TimeoutException:
            self._log_notification(notification_type, 'telegram', title, message, 'failed', metadata, '타임아웃')
            return {'success': False, 'error': '요청 시간 초과'}
        except Exception as e:
            self._log_notification(notification_type, 'telegram', title, message, 'failed', metadata, str(e))
            return {'success': False, 'error': str(e)}

    async def send_kakao(
        self,
        title: str,
        message: str,
        notification_type: NotificationType = 'system_error',
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """카카오톡 메시지 발송 (카카오 나에게 보내기 API 사용)"""
        if not self.settings.get('kakao_enabled'):
            return {'success': False, 'error': '카카오톡 알림이 비활성화되어 있습니다'}

        access_token = self.settings.get('kakao_access_token')

        if not access_token:
            return {'success': False, 'error': '카카오톡 설정이 완료되지 않았습니다'}

        # 텍스트 템플릿 메시지
        template_object = {
            "object_type": "text",
            "text": f"[{title}]\n\n{message}",
            "link": {
                "web_url": "http://localhost:8000",
                "mobile_web_url": "http://localhost:8000"
            }
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://kapi.kakao.com/v2/api/talk/memo/default/send",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    data={
                        "template_object": json.dumps(template_object, ensure_ascii=False)
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get('result_code') == 0:
                        self._log_notification(notification_type, 'kakao', title, message, 'sent', metadata)
                        return {'success': True}
                    else:
                        error = result.get('result_message', '알 수 없는 오류')
                        self._log_notification(notification_type, 'kakao', title, message, 'failed', metadata, error)
                        return {'success': False, 'error': error}
                elif response.status_code == 401:
                    error = '카카오톡 액세스 토큰이 만료되었습니다. 재인증이 필요합니다.'
                    self._log_notification(notification_type, 'kakao', title, message, 'failed', metadata, error)
                    return {'success': False, 'error': error}
                else:
                    error = f"HTTP {response.status_code}"
                    self._log_notification(notification_type, 'kakao', title, message, 'failed', metadata, error)
                    return {'success': False, 'error': error}

        except httpx.TimeoutException:
            self._log_notification(notification_type, 'kakao', title, message, 'failed', metadata, '타임아웃')
            return {'success': False, 'error': '요청 시간 초과'}
        except Exception as e:
            self._log_notification(notification_type, 'kakao', title, message, 'failed', metadata, str(e))
            return {'success': False, 'error': str(e)}

    async def send(
        self,
        title: str,
        message: str,
        notification_type: NotificationType,
        channel: NotificationChannel = 'all',
        metadata: Optional[Dict[str, Any]] = None,
        ignore_quiet_hours: bool = False
    ) -> Dict[str, Any]:
        """
        알림 발송 (통합)

        Args:
            title: 알림 제목
            message: 알림 메시지
            notification_type: 알림 유형
            channel: 발송 채널 ('telegram', 'kakao', 'all')
            metadata: 추가 메타데이터
            ignore_quiet_hours: 방해금지 시간 무시 여부

        Returns:
            발송 결과
        """
        # 방해금지 시간 체크 (시스템 오류는 항상 발송)
        if not ignore_quiet_hours and notification_type != 'system_error':
            if self.is_quiet_hours():
                return {
                    'success': False,
                    'error': '방해금지 시간입니다',
                    'skipped': True
                }

        results = {}

        if channel in ('telegram', 'all'):
            results['telegram'] = await self.send_telegram(
                title, message, notification_type, metadata
            )

        if channel in ('kakao', 'all'):
            results['kakao'] = await self.send_kakao(
                title, message, notification_type, metadata
            )

        # 성공 여부 판단
        success = any(r.get('success') for r in results.values())

        return {
            'success': success,
            'results': results
        }

    def _log_notification(
        self,
        notification_type: str,
        channel: str,
        title: str,
        message: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ):
        """알림 발송 이력 기록"""
        conn = None
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO notification_history
                (notification_type, channel, title, message, metadata, status, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                notification_type,
                channel,
                title,
                message,
                json.dumps(metadata) if metadata else '{}',
                status,
                error_message
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"알림 이력 기록 실패: {e}")
        finally:
            if conn:
                conn.close()


# 싱글톤 인스턴스
_notification_sender = None


def get_notification_sender() -> NotificationSender:
    """알림 발송 서비스 인스턴스 반환"""
    global _notification_sender
    if _notification_sender is None:
        _notification_sender = NotificationSender()
    return _notification_sender


async def send_notification(
    title: str,
    message: str,
    notification_type: NotificationType,
    channel: NotificationChannel = 'all',
    metadata: Optional[Dict[str, Any]] = None,
    ignore_quiet_hours: bool = False
) -> Dict[str, Any]:
    """알림 발송 편의 함수"""
    sender = get_notification_sender()
    return await sender.send(
        title=title,
        message=message,
        notification_type=notification_type,
        channel=channel,
        metadata=metadata,
        ignore_quiet_hours=ignore_quiet_hours
    )


# 테스트용
if __name__ == "__main__":
    async def test():
        sender = NotificationSender()
        result = await sender.send(
            title="테스트 알림",
            message="이것은 테스트 메시지입니다.",
            notification_type="test",
            channel="all"
        )
        print(f"결과: {result}")

    asyncio.run(test())

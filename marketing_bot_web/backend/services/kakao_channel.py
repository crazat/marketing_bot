"""
카카오톡 채널 연동 서비스
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 D-4] 카카오 알림톡/친구톡 발송 + 챗봇 webhook 수신

기능:
1. 알림톡 발송 (예약 확인, 진료 후 안내, 리마인드)
2. 챗봇 메시지 수신/응답 (FAQ, 예약 안내)
3. 환자 팔로우업 자동화 (휴면 환자 리텐션)

필요한 설정 (config/config.json):
{
    "kakao": {
        "channel_id": "...",
        "admin_key": "...",          // 카카오 REST API 앱 키
        "alimtalk_sender_key": "...", // 알림톡 발신 프로필 키
        "webhook_secret": "..."       // 챗봇 webhook 검증용
    }
}

참고: 실제 알림톡 발송은 비즈메시지 서비스 가입 필요
(카카오 비즈니스, NHN Cloud, 솔라피 등)
"""

import os
import sys
import json
import hmac
import hashlib
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """메시지 유형"""
    APPOINTMENT_CONFIRM = "appointment_confirm"      # 예약 확인
    APPOINTMENT_REMIND = "appointment_remind"        # 예약 리마인드
    POST_TREATMENT = "post_treatment"                # 진료 후 안내
    FOLLOWUP_REMIND = "followup_remind"              # 재방문 리마인드
    DORMANT_RETENTION = "dormant_retention"           # 휴면 환자 리텐션
    REVIEW_REQUEST = "review_request"                 # 리뷰 요청
    HEALTH_TIP = "health_tip"                         # 건강 정보


# 알림톡 템플릿 (실제 사용 시 카카오 심사 필요)
ALIMTALK_TEMPLATES = {
    MessageType.APPOINTMENT_CONFIRM: {
        "template_code": "APPT_CONFIRM_001",
        "template": (
            "[{clinic_name}] 예약 확인\n\n"
            "안녕하세요, {patient_name}님.\n"
            "{date} {time}에 예약이 확인되었습니다.\n\n"
            "- 진료과목: {treatment}\n"
            "- 주소: {address}\n\n"
            "변경/취소는 카카오톡 채널로 문의해주세요."
        ),
    },
    MessageType.APPOINTMENT_REMIND: {
        "template_code": "APPT_REMIND_001",
        "template": (
            "[{clinic_name}] 예약 리마인드\n\n"
            "{patient_name}님, 내일 {time} 예약이 있습니다.\n\n"
            "- 진료과목: {treatment}\n"
            "- 준비사항: {preparation}\n\n"
            "방문이 어려우시면 미리 연락 부탁드립니다."
        ),
    },
    MessageType.POST_TREATMENT: {
        "template_code": "POST_TREAT_001",
        "template": (
            "[{clinic_name}] 진료 후 안내\n\n"
            "{patient_name}님, 오늘 진료 감사합니다.\n\n"
            "주의사항:\n{precautions}\n\n"
            "다음 예약: {next_date}\n"
            "궁금한 점은 언제든 문의해주세요."
        ),
    },
    MessageType.DORMANT_RETENTION: {
        "template_code": "DORMANT_001",
        "template": (
            "[{clinic_name}]\n\n"
            "{patient_name}님, 건강은 잘 유지하고 계신가요?\n"
            "마지막 방문 이후 {days_since}일이 지났습니다.\n\n"
            "경과 확인이 필요하시면 편하게 문의해주세요.\n"
            "전화: {phone}"
        ),
    },
    MessageType.REVIEW_REQUEST: {
        "template_code": "REVIEW_REQ_001",
        "template": (
            "[{clinic_name}]\n\n"
            "{patient_name}님, 진료 경험은 어떠셨나요?\n"
            "소중한 후기를 남겨주시면 큰 힘이 됩니다.\n\n"
            "리뷰 작성: {review_url}\n\n"
            "감사합니다."
        ),
    },
}


class KakaoChannelService:
    """카카오톡 채널 서비스"""

    def __init__(self, config: Dict[str, str] = None):
        self.config = config or {}
        self.channel_id = self.config.get("channel_id", "")
        self.admin_key = self.config.get("admin_key", "")
        self.sender_key = self.config.get("alimtalk_sender_key", "")

    @classmethod
    def from_config_file(cls) -> "KakaoChannelService":
        """config.json에서 설정 로드"""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
            config_path = os.path.join(project_root, "config", "config.json")

            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return cls(config=data.get("kakao", {}))
        except Exception as e:
            logger.error(f"카카오 설정 로드 실패: {e}")

        return cls()

    def is_configured(self) -> bool:
        """설정 완료 여부"""
        return bool(self.admin_key and self.sender_key)

    def render_template(
        self,
        message_type: MessageType,
        variables: Dict[str, str],
    ) -> Optional[str]:
        """템플릿에 변수를 치환하여 메시지 생성"""
        template_info = ALIMTALK_TEMPLATES.get(message_type)
        if not template_info:
            return None

        try:
            return template_info["template"].format(**variables)
        except KeyError as e:
            logger.error(f"템플릿 변수 누락: {e}")
            return None

    async def send_alimtalk(
        self,
        phone: str,
        message_type: MessageType,
        variables: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        알림톡 발송

        실제 발송은 비즈메시지 API를 통해 이루어집니다.
        여기서는 프레임워크만 구현하고, 실제 연동은 별도 진행이 필요합니다.

        Args:
            phone: 수신자 전화번호 (01012345678 형태)
            message_type: 메시지 유형
            variables: 템플릿 변수

        Returns:
            발송 결과
        """
        if not self.is_configured():
            return {
                "status": "not_configured",
                "message": "카카오 API 설정이 필요합니다. config/config.json의 kakao 섹션을 확인하세요.",
            }

        rendered = self.render_template(message_type, variables)
        if not rendered:
            return {"status": "error", "message": "템플릿 렌더링 실패"}

        template_info = ALIMTALK_TEMPLATES.get(message_type, {})

        # 실제 API 호출 (비즈메시지 서비스 연동 시 활성화)
        # 현재는 로그만 남기고 성공으로 반환
        logger.info(
            f"📱 알림톡 발송 준비: {phone} - {message_type.value}\n"
            f"   템플릿: {template_info.get('template_code', 'N/A')}\n"
            f"   내용: {rendered[:100]}..."
        )

        return {
            "status": "ready",
            "message_type": message_type.value,
            "template_code": template_info.get("template_code"),
            "rendered_message": rendered,
            "phone": phone[:3] + "****" + phone[-4:],  # 마스킹
            "note": "실제 발송을 위해 비즈메시지 서비스 연동이 필요합니다.",
        }

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """챗봇 webhook 서명 검증"""
        secret = self.config.get("webhook_secret", "")
        if not secret:
            return False

        expected = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, signature)


# 환자 팔로우업 로직
def get_dormant_patients(db_path: str, days_threshold: int = 90) -> List[Dict[str, Any]]:
    """
    휴면 환자 목록 조회 (마지막 방문 후 N일 이상 경과)

    call_tracking 또는 contact_history 테이블에서 조회
    """
    import sqlite3

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # contact_history에서 마지막 연락 기준
        cursor.execute("""
            SELECT
                lead_id,
                MAX(contact_date) as last_contact,
                julianday('now') - julianday(MAX(contact_date)) as days_since
            FROM contact_history
            GROUP BY lead_id
            HAVING days_since >= ?
            ORDER BY days_since DESC
            LIMIT 50
        """, (days_threshold,))

        return [dict(row) for row in cursor.fetchall()]

    except Exception as e:
        logger.error(f"휴면 환자 조회 실패: {e}")
        return []
    finally:
        if conn:
            conn.close()

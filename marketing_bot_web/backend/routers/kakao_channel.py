"""
Kakao Channel API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 D-4] 카카오톡 채널 연동 API
- 알림톡 발송 (예약 확인, 진료 후 안내, 리마인드)
- 챗봇 webhook 수신
- 환자 팔로우업 자동화
"""

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import sys
import json
from pathlib import Path

parent_dir = str(Path(__file__).parent.parent.parent.parent)
backend_dir = str(Path(__file__).parent.parent)
sys.path.insert(0, parent_dir)
sys.path.insert(0, backend_dir)

from db.database import DatabaseManager
from backend_utils.error_handlers import handle_exceptions

router = APIRouter()


class AlimtalkRequest(BaseModel):
    phone: str
    message_type: str  # appointment_confirm, post_treatment, dormant_retention, etc.
    variables: Dict[str, str]


class ChatbotResponse(BaseModel):
    reply: str
    quick_replies: Optional[List[Dict[str, str]]] = None


@router.get("/status")
@handle_exceptions
async def get_kakao_channel_status() -> Dict[str, Any]:
    """카카오 채널 연동 상태 확인"""
    from services.kakao_channel import KakaoChannelService, ALIMTALK_TEMPLATES, MessageType

    service = KakaoChannelService.from_config_file()

    return {
        "configured": service.is_configured(),
        "channel_id": service.channel_id or "(미설정)",
        "available_templates": [
            {
                "type": mt.value,
                "template_code": info.get("template_code"),
            }
            for mt, info in ALIMTALK_TEMPLATES.items()
        ],
        "setup_guide": (
            "config/config.json에 kakao 섹션을 추가하세요: "
            '{"kakao": {"channel_id": "...", "admin_key": "...", "alimtalk_sender_key": "..."}}'
        ) if not service.is_configured() else None,
    }


@router.post("/send-alimtalk")
@handle_exceptions
async def send_alimtalk(request: AlimtalkRequest) -> Dict[str, Any]:
    """
    알림톡 발송

    Body:
        phone: "01012345678"
        message_type: "appointment_confirm"
        variables: {"clinic_name": "규림한의원", "patient_name": "홍길동", ...}
    """
    from services.kakao_channel import KakaoChannelService, MessageType

    service = KakaoChannelService.from_config_file()

    try:
        msg_type = MessageType(request.message_type)
    except ValueError:
        valid_types = [mt.value for mt in MessageType]
        raise HTTPException(400, f"유효하지 않은 메시지 유형. 허용: {valid_types}")

    result = await service.send_alimtalk(
        phone=request.phone,
        message_type=msg_type,
        variables=request.variables,
    )

    return result


@router.post("/webhook")
async def kakao_chatbot_webhook(request: Request) -> Dict[str, Any]:
    """
    카카오 챗봇 webhook 수신 엔드포인트

    카카오 i 오픈빌더에서 스킬(Skill) 서버로 등록하여 사용.
    사용자 발화를 수신하고 응답을 반환합니다.
    """
    try:
        body = await request.json()

        # 카카오 i 오픈빌더 스킬 형식
        user_request = body.get("userRequest", {})
        utterance = user_request.get("utterance", "")
        user_id = user_request.get("user", {}).get("id", "unknown")

        # 간단한 FAQ 응답 (실제로는 AI 에이전트 연동 가능)
        reply, quick_replies = _handle_chatbot_message(utterance)

        # 카카오 i 오픈빌더 응답 형식
        response = {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": reply
                        }
                    }
                ],
            }
        }

        if quick_replies:
            response["template"]["quickReplies"] = quick_replies

        return response

    except Exception as e:
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {"simpleText": {"text": "죄송합니다. 잠시 후 다시 시도해주세요."}}
                ]
            }
        }


@router.get("/dormant-patients")
@handle_exceptions
async def get_dormant_patients(
    days: int = Query(default=90, ge=30, le=365, description="휴면 기준 일수"),
) -> Dict[str, Any]:
    """
    휴면 환자 목록 (마지막 연락 후 N일 이상 경과)

    리텐션 캠페인 대상자 추출
    """
    from services.kakao_channel import get_dormant_patients as get_dormants

    db = DatabaseManager()
    patients = get_dormants(db.db_path, days_threshold=days)

    return {
        "count": len(patients),
        "threshold_days": days,
        "patients": patients,
    }


@router.post("/preview-message")
@handle_exceptions
async def preview_alimtalk(request: AlimtalkRequest) -> Dict[str, Any]:
    """알림톡 메시지 미리보기 (발송하지 않고 렌더링만)"""
    from services.kakao_channel import KakaoChannelService, MessageType

    service = KakaoChannelService.from_config_file()

    try:
        msg_type = MessageType(request.message_type)
    except ValueError:
        raise HTTPException(400, "유효하지 않은 메시지 유형")

    rendered = service.render_template(msg_type, request.variables)
    if not rendered:
        raise HTTPException(400, "템플릿 렌더링 실패 - 필요한 변수를 확인하세요.")

    return {
        "message_type": request.message_type,
        "rendered": rendered,
        "character_count": len(rendered),
    }


def _handle_chatbot_message(utterance: str) -> tuple:
    """
    챗봇 메시지 처리 (기본 FAQ)

    실제 운영 시 AI 에이전트(C-1) 연동으로 확장 가능
    """
    utterance_lower = utterance.strip().lower()

    FAQ = {
        "진료시간": ("평일 09:00 ~ 18:00, 토요일 09:00 ~ 13:00\n일요일/공휴일 휴진입니다.", None),
        "예약": (
            "전화 또는 네이버 예약으로 접수 가능합니다.\n전화: 043-XXX-XXXX",
            [
                {"messageText": "네이버 예약", "action": "message", "label": "네이버 예약"},
                {"messageText": "전화 예약", "action": "message", "label": "전화 예약"},
            ]
        ),
        "주차": ("건물 지하 주차장을 이용하실 수 있습니다. (1시간 무료)", None),
        "위치": ("충북 청주시 상당구 ... (상세 주소)\n네이버 지도에서 '규림한의원'을 검색해주세요.", None),
        "보험": ("한방 건강보험 적용됩니다.\n침, 뜸, 부항, 추나 등 다양한 치료에 보험이 적용됩니다.", None),
    }

    for keyword, (reply, qr) in FAQ.items():
        if keyword in utterance_lower:
            return reply, qr

    # 기본 응답
    return (
        "안녕하세요, 규림한의원입니다.\n"
        "궁금하신 사항을 말씀해주세요.\n\n"
        "자주 묻는 질문: 진료시간, 예약, 주차, 위치, 보험",
        [
            {"messageText": "진료시간", "action": "message", "label": "진료시간"},
            {"messageText": "예약", "action": "message", "label": "예약하기"},
            {"messageText": "위치", "action": "message", "label": "오시는 길"},
        ]
    )

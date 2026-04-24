"""
시즌별 캠페인 자동화
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 V2-5] 한의원 마케팅에 최적화된 계절별 캠페인 자동 제안

6개 시즌 캠페인:
1. 봄 알레르기 (3-5월)
2. 여름 보양 (6-8월)
3. 가을 환절기 (9-10월)
4. 겨울 면역 (11-2월)
5. 수능 시즌 (10-11월)
6. 신학기 (2-3월)

날씨 트리거(V2-1)와 연동하여 기상 조건에 따라 캠페인 가속/지연 가능
"""

from typing import Dict, Any, List
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시즌별 캠페인 정의
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SEASONAL_CAMPAIGNS = {
    "spring_allergy": {
        "name": "봄 알레르기 캠페인",
        "icon": "🌸",
        "months": [3, 4, 5],
        "keywords": [
            "봄철 알레르기", "비염 한의원", "알레르기 한방치료",
            "꽃가루 알레르기", "피부 알레르기 한의원", "환절기 비염",
        ],
        "content_themes": [
            {"title": "봄철 알레르기 비염, 체질 개선으로 근본 해결", "type": "blog", "priority": "high"},
            {"title": "꽃가루 시즌! 한방 비염 관리 5가지", "type": "blog", "priority": "medium"},
            {"title": "1분 건강팁: 봄 알레르기 예방법", "type": "shorts", "priority": "high"},
            {"title": "비염 환자 급증! 한의원에서 해결하세요", "type": "instagram", "priority": "medium"},
        ],
        "target_audience": "알레르기 비염, 아토피, 피부 질환 환자",
        "weather_boost": "spring_allergy",  # V2-1 날씨 트리거와 연동
    },
    "summer_vitality": {
        "name": "여름 보양 캠페인",
        "icon": "☀️",
        "months": [6, 7, 8],
        "keywords": [
            "여름 보양 한약", "더위 한의원", "여름 다이어트",
            "보양식 대신 한약", "여름철 피로 회복", "냉방병 한의원",
        ],
        "content_themes": [
            {"title": "폭염 속 기력 회복, 한방 보양이 답입니다", "type": "blog", "priority": "high"},
            {"title": "여름 다이어트 한약, 효과적인 관리법", "type": "blog", "priority": "high"},
            {"title": "냉방병 vs 더위병, 한의원 치료법 비교", "type": "blog", "priority": "medium"},
            {"title": "1분 건강팁: 여름철 기력 보충법", "type": "shorts", "priority": "high"},
        ],
        "target_audience": "체력 저하, 식욕 부진, 다이어트",
        "weather_boost": "heat_wave",
    },
    "autumn_immune": {
        "name": "가을 환절기 캠페인",
        "icon": "🍂",
        "months": [9, 10],
        "keywords": [
            "환절기 면역력", "가을 한의원", "면역력 한약",
            "감기 예방 한방", "환절기 건강 관리",
        ],
        "content_themes": [
            {"title": "환절기 면역력 강화, 한방 관리법 총정리", "type": "blog", "priority": "high"},
            {"title": "가을 감기 예방을 위한 한약 처방", "type": "blog", "priority": "medium"},
            {"title": "1분 건강팁: 환절기 면역 관리", "type": "shorts", "priority": "high"},
        ],
        "target_audience": "면역력 저하, 잦은 감기, 피로",
        "weather_boost": "cold_snap",
    },
    "winter_health": {
        "name": "겨울 면역/관절 캠페인",
        "icon": "❄️",
        "months": [11, 12, 1, 2],
        "keywords": [
            "겨울 관절 한의원", "면역력 한약", "겨울 건강 관리",
            "한방 온열치료", "동절기 관절 통증", "겨울 한약",
        ],
        "content_themes": [
            {"title": "추운 겨울, 관절 통증 악화 전 한방 치료", "type": "blog", "priority": "high"},
            {"title": "겨울 면역 한약, 올바른 선택 가이드", "type": "blog", "priority": "high"},
            {"title": "한방 온열치료로 겨울 관절 건강 지키세요", "type": "blog", "priority": "medium"},
            {"title": "1분 건강팁: 겨울 면역력 강화법", "type": "shorts", "priority": "high"},
        ],
        "target_audience": "관절 질환, 어르신, 냉증, 면역 저하",
        "weather_boost": "cold_wave",
    },
    "exam_season": {
        "name": "수능 시즌 캠페인",
        "icon": "📚",
        "months": [10, 11],
        "keywords": [
            "수험생 건강 한의원", "집중력 한약", "수능 체력 관리",
            "수험생 면역", "시험 스트레스 한방",
        ],
        "content_themes": [
            {"title": "수능 D-30! 수험생 체력·집중력 한방 관리", "type": "blog", "priority": "high"},
            {"title": "수험생 면역력, 한약으로 지키세요", "type": "blog", "priority": "medium"},
            {"title": "1분 건강팁: 수험생 스트레스 관리법", "type": "shorts", "priority": "medium"},
        ],
        "target_audience": "수험생, 학부모",
    },
    "new_semester": {
        "name": "신학기 캠페인",
        "icon": "🎒",
        "months": [2, 3],
        "keywords": [
            "성장클리닉 한의원", "어린이 체력 한약", "신학기 건강검진",
            "성장 한약", "키성장 한의원",
        ],
        "content_themes": [
            {"title": "신학기 맞이! 우리 아이 성장 한방 관리", "type": "blog", "priority": "high"},
            {"title": "성장기 체력 관리, 한약의 효과", "type": "blog", "priority": "medium"},
            {"title": "1분 건강팁: 아이 성장 관리법", "type": "shorts", "priority": "high"},
        ],
        "target_audience": "학부모, 성장기 어린이/청소년",
    },
}


def get_active_campaigns(
    target_date: date = None,
    include_upcoming: bool = True,
    upcoming_days: int = 14,
) -> Dict[str, Any]:
    """
    현재 활성 캠페인 + 임박 캠페인 반환

    Args:
        target_date: 기준 날짜 (None이면 오늘)
        include_upcoming: 임박 캠페인 포함 여부
        upcoming_days: 임박 기준 일수

    Returns:
        {active_campaigns, upcoming_campaigns, recommended_actions}
    """
    today = target_date or date.today()
    current_month = today.month

    active = []
    upcoming = []

    for campaign_id, campaign in SEASONAL_CAMPAIGNS.items():
        months = campaign["months"]

        if current_month in months:
            # 현재 활성
            # 캠페인 내 위치 (시작/중반/종료)
            idx = months.index(current_month)
            phase = "시작" if idx == 0 else "종료" if idx == len(months) - 1 else "진행"

            active.append({
                "id": campaign_id,
                "name": campaign["name"],
                "icon": campaign["icon"],
                "phase": phase,
                "keywords": campaign["keywords"],
                "content_themes": campaign["content_themes"],
                "target_audience": campaign["target_audience"],
                "weather_boost": campaign.get("weather_boost"),
            })

        elif include_upcoming:
            # 임박 캠페인 체크
            next_month = (current_month % 12) + 1
            if next_month in months:
                upcoming.append({
                    "id": campaign_id,
                    "name": campaign["name"],
                    "icon": campaign["icon"],
                    "starts_in": f"다음 달부터",
                    "keywords": campaign["keywords"][:3],
                    "preparation_tips": [
                        "키워드 콘텐츠 미리 준비",
                        "블로그 포스팅 2-3편 예약 발행",
                        "SNS 콘텐츠 캘린더 수립",
                    ],
                })

    # 추천 액션 생성
    actions = []
    for camp in active:
        high_priority = [t for t in camp["content_themes"] if t.get("priority") == "high"]
        if high_priority:
            actions.append({
                "campaign": camp["name"],
                "action": f"우선 콘텐츠 작성: {high_priority[0]['title']}",
                "type": high_priority[0]["type"],
                "keywords": camp["keywords"][:3],
            })

    return {
        "current_date": today.isoformat(),
        "current_month": current_month,
        "active_campaigns": active,
        "active_count": len(active),
        "upcoming_campaigns": upcoming,
        "recommended_actions": actions,
    }


def get_campaign_content_calendar(campaign_id: str, weeks: int = 4) -> Dict[str, Any]:
    """특정 캠페인의 주간 콘텐츠 캘린더"""
    campaign = SEASONAL_CAMPAIGNS.get(campaign_id)
    if not campaign:
        return {"error": f"캠페인을 찾을 수 없습니다: {campaign_id}"}

    themes = campaign["content_themes"]
    keywords = campaign["keywords"]

    calendar = []
    for week in range(1, weeks + 1):
        week_plan = {
            "week": week,
            "blog": themes[(week - 1) % len(themes)] if themes else None,
            "suggested_keyword": keywords[(week - 1) % len(keywords)] if keywords else None,
            "social_post": f"{campaign['icon']} {campaign['name']} 관련 SNS 콘텐츠",
        }
        calendar.append(week_plan)

    return {
        "campaign": campaign["name"],
        "icon": campaign["icon"],
        "weeks": weeks,
        "calendar": calendar,
        "target_audience": campaign["target_audience"],
    }

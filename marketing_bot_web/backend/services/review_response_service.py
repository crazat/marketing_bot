"""
리뷰 자동 응답 서비스
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 B-4] 경쟁사/자사 리뷰에 대한 자동 응답 초안 생성

워크플로우:
1. 새 리뷰 감지 → generate_response_draft() 호출
2. Gemini로 감성 분류 + 응답 초안 생성
3. review_responses 테이블에 저장
4. 텔레그램으로 초안 전송 (원장님 확인/수정 후 게시)
"""

import sqlite3
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


# 리뷰 감성 키워드 (한국어)
POSITIVE_KEYWORDS = [
    "좋아", "좋았", "추천", "친절", "최고", "감사", "효과", "만족",
    "편안", "꼼꼼", "정성", "다시 갈", "재방문", "호전", "나았",
]
NEGATIVE_KEYWORDS = [
    "별로", "불친절", "비싸", "대기", "기다", "불만", "아쉬",
    "실망", "효과 없", "불편", "안내", "설명 부족",
]

# 주제 분류 키워드 맵
TOPIC_KEYWORDS = {
    "서비스": ["친절", "불친절", "안내", "설명", "상담", "응대", "배려"],
    "효과": ["효과", "호전", "나았", "좋아졌", "변화", "개선", "치료"],
    "가격": ["비싸", "가격", "비용", "합리적", "저렴", "부담"],
    "대기": ["대기", "기다", "예약", "오래", "빠르", "시간"],
    "시설": ["깨끗", "청결", "인테리어", "편안", "쾌적", "시설"],
    "접근성": ["주차", "위치", "찾기", "교통", "가까"],
}


def classify_sentiment(content: str) -> str:
    """단순 키워드 기반 감성 분류"""
    content_lower = content.lower()
    pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in content_lower)
    neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in content_lower)

    if pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    return "neutral"


def extract_topics(content: str) -> List[str]:
    """리뷰에서 주제 추출"""
    topics = []
    content_lower = content.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in content_lower for kw in keywords):
            topics.append(topic)
    return topics if topics else ["일반"]


async def generate_response_draft(
    review_content: str,
    sentiment: str,
    star_rating: Optional[float] = None,
    clinic_name: str = "한의원",
) -> str:
    """
    Gemini AI로 리뷰 응답 초안 생성

    Args:
        review_content: 리뷰 내용
        sentiment: 감성 (positive/neutral/negative)
        star_rating: 별점 (1.0~5.0)
        clinic_name: 한의원 이름

    Returns:
        응답 초안 텍스트
    """
    try:
        from services.ai_client import ai_generate

        star_info = f"별점: {star_rating}/5.0" if star_rating else ""
        sentiment_guide = {
            "positive": "감사함을 표현하고 재방문을 유도하세요.",
            "neutral": "관심에 감사하고 궁금한 점이 있으면 연락 달라고 안내하세요.",
            "negative": "진심으로 공감하고, 개선 의지를 보여주며, 직접 연락 부탁을 안내하세요.",
        }

        prompt = f"""당신은 {clinic_name}의 원장님입니다.
아래 환자 리뷰에 대한 답변을 작성해주세요.

[리뷰]
{review_content}

[감성]: {sentiment} {star_info}
[가이드]: {sentiment_guide.get(sentiment, "")}

[작성 규칙]
- 2~4문장으로 간결하게
- 존댓말 사용
- 의료광고 규정 준수 (치료 효과 단정 금지)
- 진심 어린 톤
- 이모지 사용 금지
"""

        return ai_generate(prompt, temperature=0.7, max_tokens=300)

    except Exception as e:
        logger.error(f"AI 응답 생성 실패: {e}")
        return _generate_template_response(sentiment, review_content)


def _generate_template_response(sentiment: str, content: str) -> str:
    """Gemini 실패 시 템플릿 기반 응답"""
    if sentiment == "positive":
        return "소중한 후기 감사합니다. 더 나은 진료를 위해 노력하겠습니다. 건강한 하루 보내세요."
    elif sentiment == "negative":
        return ("불편을 드려 진심으로 죄송합니다. "
                "말씀해주신 부분 개선하도록 하겠습니다. "
                "추가 상담이 필요하시면 언제든 연락 주세요.")
    else:
        return "방문해주셔서 감사합니다. 궁금하신 점이 있으시면 편하게 문의해 주세요."


def save_review_response(
    db_path: str,
    review_id: Optional[int],
    competitor_name: str,
    review_content: str,
    star_rating: Optional[float],
    sentiment: str,
    topics: List[str],
    draft_response: str,
) -> Optional[int]:
    """리뷰 응답 초안을 DB에 저장"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO review_responses
            (review_id, competitor_name, review_content, star_rating,
             sentiment, topics, draft_response, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')
        """, (
            review_id, competitor_name, review_content, star_rating,
            sentiment, json.dumps(topics, ensure_ascii=False), draft_response,
        ))

        conn.commit()
        return cursor.lastrowid

    except Exception as e:
        logger.error(f"리뷰 응답 저장 실패: {e}")
        return None
    finally:
        if conn:
            conn.close()


def get_pending_responses(db_path: str, limit: int = 20) -> List[Dict[str, Any]]:
    """대기 중인 응답 초안 목록 조회"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM review_responses
            WHERE status = 'draft'
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))

        return [dict(row) for row in cursor.fetchall()]

    except Exception as e:
        logger.error(f"대기 응답 조회 실패: {e}")
        return []
    finally:
        if conn:
            conn.close()


def update_response_status(
    db_path: str,
    response_id: int,
    status: str,
    final_response: str = None,
) -> bool:
    """응답 상태 업데이트 (draft → approved → posted)"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if status == "approved" and final_response:
            cursor.execute("""
                UPDATE review_responses
                SET status = ?, final_response = ?, approved_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, final_response, response_id))
        elif status == "posted":
            cursor.execute("""
                UPDATE review_responses
                SET status = ?, posted_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, response_id))
        else:
            cursor.execute("""
                UPDATE review_responses SET status = ? WHERE id = ?
            """, (status, response_id))

        conn.commit()
        return cursor.rowcount > 0

    except Exception as e:
        logger.error(f"응답 상태 업데이트 실패: {e}")
        return False
    finally:
        if conn:
            conn.close()

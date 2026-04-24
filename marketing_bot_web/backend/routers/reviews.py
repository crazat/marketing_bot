"""
Review Response Assistant API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 5.3] 리뷰 응대 도우미
- 리뷰 분류 (긍정/부정/중립)
- AI 응답 초안 생성
- 응답 템플릿 관리
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import sys
import os
from pathlib import Path
import sqlite3
import json
from datetime import datetime

# 상위 디렉토리를 path에 추가
parent_dir = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, parent_dir)

from db.database import DatabaseManager
from backend_utils.error_handlers import handle_exceptions

router = APIRouter()


class ReviewResponseTemplate(BaseModel):
    sentiment: str  # positive, negative, neutral
    template_name: str
    content: str
    variables: Optional[List[str]] = None  # 치환 가능한 변수들


class GenerateResponseRequest(BaseModel):
    review_content: str
    reviewer_name: Optional[str] = None
    rating: Optional[int] = None
    sentiment: Optional[str] = None  # positive, negative, neutral
    tone: str = "professional"  # professional, friendly, empathetic
    include_promotion: bool = False


# 응답 템플릿 기본값
DEFAULT_TEMPLATES = {
    "positive": [
        {
            "name": "감사 인사",
            "content": "안녕하세요, {reviewer_name}님! 규림한의원입니다.\n소중한 후기 감사드립니다. {reviewer_name}님의 건강을 위해 더욱 노력하겠습니다.\n감사합니다! 🙏",
            "variables": ["reviewer_name"]
        },
        {
            "name": "재방문 유도",
            "content": "안녕하세요, {reviewer_name}님! 따뜻한 후기 정말 감사합니다.\n앞으로도 {reviewer_name}님의 건강한 일상을 위해 최선을 다하겠습니다.\n언제든 편하게 방문해주세요! 😊",
            "variables": ["reviewer_name"]
        }
    ],
    "negative": [
        {
            "name": "진심 어린 사과",
            "content": "안녕하세요, {reviewer_name}님. 규림한의원 원장입니다.\n불편을 드려 진심으로 죄송합니다.\n말씀해주신 부분 꼼꼼히 검토하여 개선하겠습니다.\n다시 한번 사과의 말씀 드리며, 더 나은 서비스로 보답하겠습니다.",
            "variables": ["reviewer_name"]
        },
        {
            "name": "문제 해결 제안",
            "content": "안녕하세요, {reviewer_name}님. 규림한의원입니다.\n불편한 경험을 하셨군요. 정말 죄송합니다.\n자세한 상황을 여쭙고 싶습니다. 연락처를 남겨주시면 직접 연락드려 해결 방안을 찾아보겠습니다.\n감사합니다.",
            "variables": ["reviewer_name"]
        }
    ],
    "neutral": [
        {
            "name": "일반 감사",
            "content": "안녕하세요, {reviewer_name}님! 규림한의원입니다.\n소중한 의견 감사드립니다.\n더 좋은 서비스로 보답하겠습니다. 감사합니다!",
            "variables": ["reviewer_name"]
        }
    ]
}


@router.get("/templates")
async def get_response_templates() -> Dict[str, Any]:
    """
    리뷰 응답 템플릿 목록 조회
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 테이블 생성 (없으면)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS review_response_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sentiment TEXT NOT NULL,
                template_name TEXT NOT NULL,
                content TEXT NOT NULL,
                variables TEXT,
                use_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 기존 템플릿 조회
        cursor.execute("""
            SELECT id, sentiment, template_name, content, variables, use_count
            FROM review_response_templates
            ORDER BY sentiment, use_count DESC
        """)
        rows = cursor.fetchall()

        if not rows:
            # 기본 템플릿 삽입
            for sentiment, templates in DEFAULT_TEMPLATES.items():
                for tmpl in templates:
                    cursor.execute("""
                        INSERT INTO review_response_templates
                        (sentiment, template_name, content, variables)
                        VALUES (?, ?, ?, ?)
                    """, (
                        sentiment,
                        tmpl["name"],
                        tmpl["content"],
                        json.dumps(tmpl.get("variables", []))
                    ))
            conn.commit()

            # 다시 조회
            cursor.execute("""
                SELECT id, sentiment, template_name, content, variables, use_count
                FROM review_response_templates
                ORDER BY sentiment, use_count DESC
            """)
            rows = cursor.fetchall()

        # 감정별로 그룹화
        templates = {"positive": [], "negative": [], "neutral": []}
        for row in rows:
            sentiment = row["sentiment"]
            if sentiment in templates:
                templates[sentiment].append({
                    "id": row["id"],
                    "name": row["template_name"],
                    "content": row["content"],
                    "variables": json.loads(row["variables"] or "[]"),
                    "use_count": row["use_count"]
                })

        return {
            "templates": templates,
            "total": len(rows)
        }

    except Exception as e:
        print(f"[Review Templates] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.post("/templates")
async def create_response_template(template: ReviewResponseTemplate) -> Dict[str, Any]:
    """
    새 응답 템플릿 추가
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO review_response_templates
            (sentiment, template_name, content, variables)
            VALUES (?, ?, ?, ?)
        """, (
            template.sentiment,
            template.template_name,
            template.content,
            json.dumps(template.variables or [])
        ))

        template_id = cursor.lastrowid
        conn.commit()

        return {
            "status": "success",
            "message": "템플릿이 추가되었습니다",
            "id": template_id
        }

    except Exception as e:
        print(f"[Create Template] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.post("/templates/{template_id}/use")
async def use_template(template_id: int) -> Dict[str, Any]:
    """
    템플릿 사용 횟수 증가
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE review_response_templates
            SET use_count = use_count + 1,
                updated_at = datetime('now')
            WHERE id = ?
        """, (template_id,))

        conn.commit()

        return {"status": "success"}

    except Exception as e:
        print(f"[Use Template] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.delete("/templates/{template_id}")
async def delete_template(template_id: int) -> Dict[str, Any]:
    """
    템플릿 삭제
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM review_response_templates WHERE id = ?", (template_id,))
        conn.commit()

        return {"status": "success", "message": "템플릿이 삭제되었습니다"}

    except Exception as e:
        print(f"[Delete Template] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.post("/generate-response")
async def generate_ai_response(request: GenerateResponseRequest) -> Dict[str, Any]:
    """
    [Phase 5.3] AI 기반 리뷰 응답 생성

    리뷰 내용을 분석하여 적절한 응답 초안을 생성합니다.
    """
    try:
        from services.ai_client import ai_generate

        # 감정 분석 (sentiment가 없으면 자동 분석)
        sentiment = request.sentiment
        if not sentiment:
            if request.rating:
                if request.rating >= 4:
                    sentiment = "positive"
                elif request.rating <= 2:
                    sentiment = "negative"
                else:
                    sentiment = "neutral"
            else:
                # AI로 감정 분석
                sentiment_prompt = f"""다음 리뷰의 감정을 분석해주세요.

리뷰: {request.review_content}

positive, negative, neutral 중 하나만 답변하세요. 다른 설명 없이 단어 하나만 출력하세요."""

                sentiment_result = ai_generate(sentiment_prompt, temperature=0.3)
                sentiment = sentiment_result.strip().lower()
                if sentiment not in ["positive", "negative", "neutral"]:
                    sentiment = "neutral"

        # 톤 설정
        tone_guide = {
            "professional": "전문적이고 정중한 톤으로",
            "friendly": "친근하고 따뜻한 톤으로",
            "empathetic": "공감하고 이해하는 톤으로"
        }

        promotion_text = ""
        if request.include_promotion:
            promotion_text = "\n- 자연스럽게 규림한의원의 강점이나 서비스를 언급"

        reviewer_name = request.reviewer_name or "고객"

        prompt = f"""당신은 청주 규림한의원의 원장입니다. 다음 리뷰에 대한 응답을 작성해주세요.

리뷰 내용: {request.review_content}
리뷰어: {reviewer_name}님
평점: {request.rating or '미제공'}점
감정: {sentiment}

응답 작성 가이드:
- {tone_guide.get(request.tone, tone_guide['professional'])} 작성
- 200자 이내로 간결하게
- 리뷰 내용에 구체적으로 언급
- 진정성 있게 작성
- 이모지는 1-2개만 적절히 사용{promotion_text}

응답만 작성하세요. 다른 설명은 불필요합니다."""

        generated_response = ai_generate(prompt, temperature=0.7, max_tokens=500)

        # 응답 로그 저장
        conn = None
        try:
            db = DatabaseManager()
            conn = sqlite3.connect(db.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS review_response_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_content TEXT,
                    reviewer_name TEXT,
                    rating INTEGER,
                    sentiment TEXT,
                    generated_response TEXT,
                    tone TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                INSERT INTO review_response_log
                (review_content, reviewer_name, rating, sentiment, generated_response, tone)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                request.review_content,
                request.reviewer_name,
                request.rating,
                sentiment,
                generated_response,
                request.tone
            ))

            conn.commit()
        finally:
            if conn:
                conn.close()

        return {
            "sentiment": sentiment,
            "response": generated_response,
            "tone": request.tone,
            "reviewer_name": reviewer_name,
            "generated_at": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Generate Response] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_response_history(limit: int = 20) -> Dict[str, Any]:
    """
    응답 생성 히스토리 조회
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 테이블 존재 확인
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='review_response_log'
        """)
        if not cursor.fetchone():
            return {"history": [], "total": 0}

        cursor.execute("""
            SELECT id, review_content, reviewer_name, rating, sentiment,
                   generated_response, tone, created_at
            FROM review_response_log
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))

        history = [dict(row) for row in cursor.fetchall()]

        return {
            "history": history,
            "total": len(history)
        }

    except Exception as e:
        print(f"[Response History] Error: {e}")
        return {"history": [], "total": 0}
    finally:
        if conn:
            conn.close()


class ClassifyRequest(BaseModel):
    review_content: str
    rating: Optional[int] = None


@router.post("/classify")
async def classify_review(request: ClassifyRequest) -> Dict[str, Any]:
    """
    [Phase 7.1] AI 기반 리뷰 분류

    리뷰 내용을 분석하여 감정, 주제, 긴급도를 분류합니다.

    Args:
        review_content: 리뷰 내용
        rating: 평점 (선택)

    Returns:
        분류 결과 (sentiment, topics, urgency, keywords)
    """
    try:
        from services.ai_client import ai_generate_json

        # 분류 프롬프트
        prompt = f"""다음 한의원 리뷰를 분석해주세요.

리뷰: {request.review_content}
평점: {request.rating or '미제공'}점

다음 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "sentiment": "positive|negative|neutral 중 하나",
  "sentiment_score": 0.0~1.0 사이 숫자 (0=매우부정, 1=매우긍정),
  "topics": ["치료효과", "서비스", "시설", "가격", "대기시간", "의료진" 중 해당하는 것들],
  "urgency": "high|medium|low 중 하나 (부정적 리뷰의 경우 대응 긴급도)",
  "keywords": ["리뷰에서 추출한 핵심 키워드 3-5개"],
  "summary": "리뷰 내용 한줄 요약"
}}"""

        classification = ai_generate_json(prompt, temperature=0.3, max_tokens=500)

        if not classification:
            # JSON 파싱 실패 시 기본값
            classification = {
                "sentiment": "neutral",
                "sentiment_score": 0.5,
                "topics": [],
                "urgency": "low",
                "keywords": [],
                "summary": "분석 실패"
            }

        # 평점 기반 보정
        if request.rating:
            if request.rating >= 4 and classification.get('sentiment') == 'negative':
                classification['sentiment'] = 'positive'
            elif request.rating <= 2 and classification.get('sentiment') == 'positive':
                classification['sentiment'] = 'negative'

        # 분류 로그 저장
        conn = None
        try:
            db = DatabaseManager()
            conn = sqlite3.connect(db.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS review_classification_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_content TEXT,
                    rating INTEGER,
                    sentiment TEXT,
                    sentiment_score REAL,
                    topics TEXT,
                    urgency TEXT,
                    keywords TEXT,
                    summary TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                INSERT INTO review_classification_log
                (review_content, rating, sentiment, sentiment_score, topics, urgency, keywords, summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request.review_content,
                request.rating,
                classification.get('sentiment'),
                classification.get('sentiment_score'),
                json.dumps(classification.get('topics', [])),
                classification.get('urgency'),
                json.dumps(classification.get('keywords', [])),
                classification.get('summary')
            ))

            conn.commit()
        finally:
            if conn:
                conn.close()

        return {
            "classification": classification,
            "review_preview": request.review_content[:100] + '...' if len(request.review_content) > 100 else request.review_content,
            "rating": request.rating,
            "classified_at": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Classify Review] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_response_stats() -> Dict[str, Any]:
    """
    리뷰 응답 통계
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 테이블 존재 확인
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='review_response_log'
        """)
        if not cursor.fetchone():
            return {
                "total_responses": 0,
                "by_sentiment": {},
                "by_tone": {},
                "today_count": 0
            }

        # 총 응답 수
        cursor.execute("SELECT COUNT(*) FROM review_response_log")
        total = cursor.fetchone()[0]

        # 감정별 통계
        cursor.execute("""
            SELECT sentiment, COUNT(*) as cnt
            FROM review_response_log
            GROUP BY sentiment
        """)
        by_sentiment = {row[0]: row[1] for row in cursor.fetchall()}

        # 톤별 통계
        cursor.execute("""
            SELECT tone, COUNT(*) as cnt
            FROM review_response_log
            GROUP BY tone
        """)
        by_tone = {row[0]: row[1] for row in cursor.fetchall()}

        # 오늘 생성 수
        cursor.execute("""
            SELECT COUNT(*)
            FROM review_response_log
            WHERE date(created_at) = date('now')
        """)
        today_count = cursor.fetchone()[0]

        return {
            "total_responses": total,
            "by_sentiment": by_sentiment,
            "by_tone": by_tone,
            "today_count": today_count
        }

    except Exception as e:
        print(f"[Response Stats] Error: {e}")
        return {
            "total_responses": 0,
            "by_sentiment": {},
            "by_tone": {},
            "today_count": 0
        }
    finally:
        if conn:
            conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [고도화 B-4] 리뷰 자동 응답 시스템
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AutoResponseRequest(BaseModel):
    review_content: str
    competitor_name: Optional[str] = None
    star_rating: Optional[float] = None
    review_id: Optional[int] = None


class UpdateResponseStatusRequest(BaseModel):
    status: str  # approved, posted, dismissed
    final_response: Optional[str] = None


@router.post("/auto-response/generate")
@handle_exceptions
async def generate_auto_response(request: AutoResponseRequest) -> Dict[str, Any]:
    """
    [고도화 B-4] 리뷰에 대한 자동 응답 초안 생성

    1. 감성 분류 (positive/neutral/negative)
    2. 주제 추출 (서비스, 효과, 가격, 대기 등)
    3. Gemini AI로 응답 초안 생성
    4. review_responses 테이블에 저장
    """
    try:
        backend_dir = str(Path(__file__).parent.parent)
        sys.path.insert(0, backend_dir)
        from services.review_response_service import (
            classify_sentiment, extract_topics,
            generate_response_draft, save_review_response
        )

        # 감성 분류 및 주제 추출
        sentiment = classify_sentiment(request.review_content)
        topics = extract_topics(request.review_content)

        # AI 응답 초안 생성
        draft = await generate_response_draft(
            review_content=request.review_content,
            sentiment=sentiment,
            star_rating=request.star_rating,
        )

        # DB 저장
        db = DatabaseManager()
        response_id = save_review_response(
            db_path=db.db_path,
            review_id=request.review_id,
            competitor_name=request.competitor_name or "자사",
            review_content=request.review_content,
            star_rating=request.star_rating,
            sentiment=sentiment,
            topics=topics,
            draft_response=draft,
        )

        return {
            "id": response_id,
            "sentiment": sentiment,
            "topics": topics,
            "draft_response": draft,
            "status": "draft",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"자동 응답 생성 실패: {str(e)}")


@router.get("/auto-response/pending")
@handle_exceptions
async def get_pending_auto_responses(
    limit: int = 20
) -> Dict[str, Any]:
    """[고도화 B-4] 대기 중인 응답 초안 목록"""
    try:
        backend_dir = str(Path(__file__).parent.parent)
        sys.path.insert(0, backend_dir)
        from services.review_response_service import get_pending_responses

        db = DatabaseManager()
        responses = get_pending_responses(db.db_path, limit=limit)

        # topics 필드 JSON 파싱
        for r in responses:
            if isinstance(r.get('topics'), str):
                try:
                    r['topics'] = json.loads(r['topics'])
                except (json.JSONDecodeError, TypeError):
                    r['topics'] = []

        return {
            "count": len(responses),
            "responses": responses,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"대기 응답 조회 실패: {str(e)}")


@router.put("/auto-response/{response_id}/status")
@handle_exceptions
async def update_auto_response_status(
    response_id: int,
    request: UpdateResponseStatusRequest
) -> Dict[str, Any]:
    """[고도화 B-4] 응답 상태 업데이트 (draft → approved → posted)"""
    try:
        backend_dir = str(Path(__file__).parent.parent)
        sys.path.insert(0, backend_dir)
        from services.review_response_service import update_response_status

        valid_statuses = {"approved", "posted", "dismissed"}
        if request.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"유효하지 않은 상태: {request.status}. 허용: {valid_statuses}"
            )

        db = DatabaseManager()
        success = update_response_status(
            db_path=db.db_path,
            response_id=response_id,
            status=request.status,
            final_response=request.final_response,
        )

        if not success:
            raise HTTPException(status_code=404, detail=f"응답 ID {response_id}를 찾을 수 없습니다")

        return {"id": response_id, "status": request.status, "updated": True}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"응답 상태 업데이트 실패: {str(e)}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [고도화 C-5] 의료광고 규정 체크
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ComplianceCheckRequest(BaseModel):
    content: str
    content_type: str = "blog"  # blog, instagram, youtube, tiktok
    title: Optional[str] = None
    url: Optional[str] = None
    use_ai: bool = False  # AI 정밀 분석 여부


@router.post("/compliance/check")
@handle_exceptions
async def check_content_compliance_api(request: ComplianceCheckRequest) -> Dict[str, Any]:
    """
    [고도화 C-5] 콘텐츠 의료광고 규정 준수 체크

    키워드 기반 사전 체크 + (선택) Gemini AI 정밀 분석
    """
    try:
        backend_dir = str(Path(__file__).parent.parent)
        sys.path.insert(0, backend_dir)
        from services.content_compliance import (
            check_content_compliance, check_with_ai, save_compliance_check
        )

        if request.use_ai:
            result = await check_with_ai(request.content, request.content_type)
        else:
            result = check_content_compliance(request.content, request.content_type)

        # DB 저장
        db = DatabaseManager()
        check_id = save_compliance_check(
            db_path=db.db_path,
            content_type=request.content_type,
            content_title=request.title or "",
            content_url=request.url,
            content_text=request.content,
            result=result,
        )

        result["id"] = check_id
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"규정 체크 실패: {str(e)}")


@router.get("/compliance/history")
@handle_exceptions
async def get_compliance_history(
    limit: int = 20,
    result_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """[고도화 C-5] 규정 체크 이력 조회"""
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='content_compliance_checks'"
        )
        if not cursor.fetchone():
            return {"checks": [], "total": 0}

        query = "SELECT * FROM content_compliance_checks"
        params = []

        if result_filter:
            query += " WHERE ai_check_result = ?"
            params.append(result_filter)

        query += " ORDER BY checked_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        checks = []
        for row in cursor.fetchall():
            check = dict(row)
            if isinstance(check.get('compliance_issues'), str):
                try:
                    check['compliance_issues'] = json.loads(check['compliance_issues'])
                except (json.JSONDecodeError, TypeError):
                    check['compliance_issues'] = []
            checks.append(check)

        return {"checks": checks, "total": len(checks)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이력 조회 실패: {str(e)}")
    finally:
        if conn:
            conn.close()

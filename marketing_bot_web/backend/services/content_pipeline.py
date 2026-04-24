"""
블로그 콘텐츠 생성 파이프라인
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 V2-8] 키워드 → 아웃라인 → 초안 → SEO → 규정체크 → 승인 → 발행

파이프라인 단계:
1. 키워드 선정 (keyword_insights 기반)
2. 아웃라인 생성 (Gemini)
3. 초안 작성 (Gemini)
4. AEO 최적화 점수화
5. 의료광고 규정 체크 (C-5 content_compliance 연동)
6. Schema Markup 자동 삽입 (V2-7 schema_markup 연동)
7. 텔레그램 승인 요청 (V2-2 인라인 키보드)
8. (향후) 네이버 블로그 API 발행
"""

import os
import sys
import json
import sqlite3
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ContentPipeline:
    """블로그 콘텐츠 자동 생성 파이프라인"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def generate_outline(
        self,
        keyword: str,
        content_type: str = "blog",
        target_audience: str = "일반 환자",
    ) -> Dict[str, Any]:
        """
        Step 1-2: 키워드 기반 블로그 아웃라인 생성

        Returns:
            {title, outline, keywords, estimated_words, aeo_tips}
        """
        from services.ai_client import ai_generate_json

        prompt = f"""한의원 블로그 포스팅 아웃라인을 생성해주세요.

[핵심 키워드]: {keyword}
[콘텐츠 유형]: {content_type}
[타겟 독자]: {target_audience}

[작성 규칙]
1. AEO (Answer Engine Optimization) 최적화:
   - 첫 문단에 핵심 답변 배치 (AI 스니펫 노출용)
   - FAQ 섹션 필수 포함 (4-6개)
   - 구조화된 소제목 (H2/H3)
2. 의료광고법 준수:
   - "완치", "100% 효과" 등 단정적 표현 금지
   - "도움이 될 수 있습니다", "개선 효과가 기대됩니다" 표현 사용
3. E-E-A-T 신호:
   - 전문가(한의사) 관점의 경험 기반 콘텐츠
   - 참고 문헌/근거 표시 섹션

[응답 형식 - JSON]
{{
    "title": "블로그 제목 (SEO 최적화)",
    "meta_description": "메타 설명 (155자 이내)",
    "outline": [
        {{"h2": "소제목", "points": ["포인트1", "포인트2"], "estimated_words": 200}},
    ],
    "faqs": [
        {{"question": "질문", "answer": "답변 (2-3문장)"}},
    ],
    "target_keywords": ["메인 키워드", "롱테일1", "롱테일2"],
    "estimated_total_words": 1500,
    "aeo_score_tips": ["팁1", "팁2"]
}}
"""

        try:
            outline = ai_generate_json(prompt, temperature=0.7, max_tokens=2000)
            if not outline:
                return {"error": "AI JSON 생성 실패"}
            outline["keyword"] = keyword
            outline["stage"] = "outline"
            return outline

        except Exception as e:
            logger.error(f"아웃라인 생성 실패: {e}")
            return {"error": str(e)}

    async def generate_draft(
        self,
        outline: Dict[str, Any],
        clinic_name: str = "한의원",
        doctor_name: str = "원장",
    ) -> Dict[str, Any]:
        """
        Step 3: 아웃라인 기반 초안 작성

        Returns:
            {title, content, word_count, faqs, schema_markup}
        """
        from services.ai_client import ai_generate

        outline_text = json.dumps(outline, ensure_ascii=False, indent=2)

        prompt = f"""아래 아웃라인에 따라 한의원 블로그 포스팅 전문을 작성해주세요.

[아웃라인]
{outline_text}

[작성 규칙]
1. {doctor_name} 한의사의 전문적이고 따뜻한 톤
2. 각 섹션은 아웃라인의 포인트를 충실히 반영
3. 실제 진료 경험에서 나온 듯한 자연스러운 표현
4. 의료광고법 준수 (단정적 표현 금지)
5. FAQ 섹션은 Q&A 형식으로 자연스럽게
6. 총 1,200-1,800자
7. 마지막에 CTA (내원 안내) 포함

한국어로 작성해주세요.
"""

        try:
            content = ai_generate(prompt, temperature=0.8, max_tokens=3000)
            title = outline.get("title", "")
            faqs = outline.get("faqs", [])

            # Schema Markup 자동 생성
            from services.schema_markup import generate_blog_post_schemas
            schema_html = generate_blog_post_schemas(
                title=title,
                author_name=doctor_name,
                date_published=datetime.now().strftime("%Y-%m-%d"),
                description=outline.get("meta_description", ""),
                faqs=faqs,
            )

            return {
                "title": title,
                "content": content,
                "word_count": len(content),
                "meta_description": outline.get("meta_description", ""),
                "keywords": outline.get("target_keywords", []),
                "faqs": faqs,
                "schema_markup": schema_html,
                "stage": "draft",
            }

        except Exception as e:
            logger.error(f"초안 생성 실패: {e}")
            return {"error": str(e)}

    async def check_compliance(self, content: str) -> Dict[str, Any]:
        """
        Step 5: 의료광고 규정 체크 (C-5 연동)
        """
        try:
            from services.content_compliance import check_content_compliance
            return check_content_compliance(content, content_type="blog")
        except Exception as e:
            return {"result": "error", "error": str(e)}

    async def full_pipeline(
        self,
        keyword: str,
        clinic_name: str = "한의원",
        doctor_name: str = "원장",
        target_audience: str = "일반 환자",
    ) -> Dict[str, Any]:
        """
        전체 파이프라인 실행

        키워드 → 아웃라인 → 초안 → 규정체크 → 결과 반환
        """
        result = {"keyword": keyword, "stages": {}}

        # Step 1-2: 아웃라인 생성
        outline = await self.generate_outline(keyword, target_audience=target_audience)
        result["stages"]["outline"] = {"status": "error" if "error" in outline else "completed"}
        if "error" in outline:
            result["error"] = outline["error"]
            return result

        # Step 3: 초안 생성
        draft = await self.generate_draft(outline, clinic_name, doctor_name)
        result["stages"]["draft"] = {"status": "error" if "error" in draft else "completed"}
        if "error" in draft:
            result["error"] = draft["error"]
            return result

        # Step 5: 규정 체크
        compliance = await self.check_compliance(draft.get("content", ""))
        result["stages"]["compliance"] = {
            "status": "completed",
            "result": compliance.get("result"),
            "severity": compliance.get("severity"),
            "issues_count": len(compliance.get("issues", [])),
        }

        # 최종 결과
        result.update({
            "title": draft["title"],
            "content": draft["content"],
            "word_count": draft["word_count"],
            "meta_description": draft["meta_description"],
            "keywords": draft["keywords"],
            "faqs": draft["faqs"],
            "schema_markup": draft["schema_markup"],
            "compliance": compliance,
            "status": "ready_for_review" if compliance.get("result") != "violation" else "compliance_issue",
        })

        # DB 저장 (향후 이력 관리용)
        self._save_draft(result)

        return result

    def _save_draft(self, result: Dict[str, Any]):
        """생성된 초안을 DB에 저장"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS content_drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT,
                    title TEXT,
                    content TEXT,
                    meta_description TEXT,
                    schema_markup TEXT,
                    compliance_result TEXT,
                    status TEXT DEFAULT 'draft',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                INSERT INTO content_drafts
                (keyword, title, content, meta_description, schema_markup, compliance_result, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                result.get("keyword"),
                result.get("title"),
                result.get("content"),
                result.get("meta_description"),
                result.get("schema_markup"),
                json.dumps(result.get("compliance", {}), ensure_ascii=False),
                result.get("status", "draft"),
            ))

            conn.commit()
            result["draft_id"] = cursor.lastrowid

        except Exception as e:
            logger.error(f"초안 저장 실패: {e}")
        finally:
            if conn:
                conn.close()

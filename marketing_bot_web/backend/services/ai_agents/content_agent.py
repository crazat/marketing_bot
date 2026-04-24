"""
Content Strategy Agent - 콘텐츠 전략 에이전트
"""

from typing import Dict, Any
from services.ai_agents.base_agent import BaseAgent


class ContentAgent(BaseAgent):
    def __init__(self, db_path: str = None):
        super().__init__(
            name="Content Strategist",
            role="한의원 콘텐츠 마케팅 전략가",
            goal="블로그, SNS 콘텐츠 전략을 수립하고 AEO/GEO 최적화를 지원합니다",
            db_path=db_path,
        )

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        action = task.get("action", "suggest_topics")

        if action == "suggest_topics":
            return await self._suggest_topics()
        elif action == "optimize_for_aeo":
            return await self._optimize_for_aeo(task.get("content", ""))
        elif action == "content_calendar":
            return await self._content_calendar(task.get("weeks", 4))
        else:
            return {"error": f"Unknown action: {action}"}

    async def _suggest_topics(self) -> Dict[str, Any]:
        """트렌딩 키워드 기반 콘텐츠 주제 제안"""
        trending = self.query_db("""
            SELECT keyword, search_volume, grade
            FROM keyword_insights
            WHERE grade IN ('S', 'A')
            ORDER BY search_volume DESC
            LIMIT 15
        """)

        community = self.query_db("""
            SELECT keyword, COUNT(*) as mentions
            FROM community_mentions
            WHERE created_at >= datetime('now', '-7 days')
            GROUP BY keyword
            ORDER BY mentions DESC
            LIMIT 10
        """)

        trending_text = ", ".join(f"{t['keyword']}({t['grade']}급)" for t in trending)
        community_text = ", ".join(f"{c['keyword']}({c['mentions']}건)" for c in community)

        suggestions = await self.think(f"""
한의원 블로그와 SNS에 올릴 콘텐츠 주제를 제안해주세요.

[고검색량 키워드]
{trending_text or "(데이터 없음)"}

[최근 커뮤니티 화제]
{community_text or "(데이터 없음)"}

[제안 요청]
1. 블로그 포스팅 주제 5개 (AEO 최적화 고려)
2. 인스타그램 릴스 주제 3개
3. 유튜브 쇼츠 주제 3개
4. 각 주제의 핵심 메시지와 타겟 키워드
""", max_tokens=1500)

        return {"suggestions": suggestions}

    async def _optimize_for_aeo(self, content: str) -> Dict[str, Any]:
        """콘텐츠 AEO 최적화 분석"""
        if not content:
            return {"error": "분석할 콘텐츠를 제공해주세요."}

        analysis = await self.think(f"""
아래 한의원 블로그 콘텐츠를 네이버 AI 브리핑(AEO) 노출에 최적화하기 위해 분석해주세요.

[콘텐츠]
{content[:3000]}

[분석 항목]
1. 현재 AEO 점수 (0-100)
2. 구조화 수준 (소제목, 불릿, FAQ 포함 여부)
3. 시맨틱 깊이 (주제 포괄성)
4. AI 스니펫 노출 가능성
5. 구체적 개선 제안 5가지
""", max_tokens=1500)

        return {"analysis": analysis}

    async def _content_calendar(self, weeks: int = 4) -> Dict[str, Any]:
        """콘텐츠 캘린더 생성"""
        keywords = self.query_db("""
            SELECT keyword, grade, category
            FROM keyword_insights
            WHERE grade IN ('S', 'A', 'B')
            ORDER BY search_volume DESC
            LIMIT 20
        """)

        kw_text = "\n".join(
            f"- {k['keyword']} ({k['grade']}급, {k.get('category', '미분류')})"
            for k in keywords
        )

        calendar = await self.think(f"""
향후 {weeks}주간의 한의원 콘텐츠 캘린더를 작성해주세요.

[활용 가능 키워드]
{kw_text or "(키워드 데이터 없음)"}

[캘린더 형식]
각 주마다:
- 블로그 2편 (제목, 핵심 키워드, 예상 검색량)
- 인스타 릴스 1편 (주제, 포맷)
- 유튜브 쇼츠 1편 (주제, 포맷)

의료광고 사전심의가 필요한 콘텐츠는 표시해주세요.
""", max_tokens=2000)

        return {"calendar": calendar, "weeks": weeks}

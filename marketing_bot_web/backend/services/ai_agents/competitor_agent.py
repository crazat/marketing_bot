"""
Competitor Intelligence Agent - 경쟁사 분석 에이전트
"""

from typing import Dict, Any
from services.ai_agents.base_agent import BaseAgent


class CompetitorAgent(BaseAgent):
    def __init__(self, db_path: str = None):
        super().__init__(
            name="Competitor Analyst",
            role="한의원 경쟁사 인텔리전스 분석가",
            goal="경쟁사의 활동을 모니터링하고 약점과 기회를 파악합니다",
            db_path=db_path,
        )

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        action = task.get("action", "analyze_competitors")

        if action == "analyze_competitors":
            return await self._analyze_competitors()
        elif action == "find_opportunities":
            return await self._find_opportunities()
        elif action == "threat_assessment":
            return await self._threat_assessment()
        else:
            return {"error": f"Unknown action: {action}"}

    async def _analyze_competitors(self) -> Dict[str, Any]:
        """경쟁사 종합 분석"""
        reviews = self.query_db("""
            SELECT
                competitor_name,
                COUNT(*) as total,
                COUNT(CASE WHEN sentiment='positive' THEN 1 END) as positive,
                COUNT(CASE WHEN sentiment='negative' THEN 1 END) as negative,
                AVG(star_rating) as avg_rating
            FROM competitor_reviews
            WHERE review_date >= date('now', '-30 days')
            GROUP BY competitor_name
            ORDER BY total DESC
            LIMIT 10
        """)

        changes = self.query_db("""
            SELECT competitor_name, change_type, details, detected_at
            FROM competitor_changes
            WHERE detected_at >= datetime('now', '-14 days')
            ORDER BY detected_at DESC
            LIMIT 15
        """)

        review_summary = "\n".join(
            f"- {r['competitor_name']}: 리뷰 {r['total']}건 (긍정 {r['positive']}, 부정 {r['negative']}, 평점 {r['avg_rating'] or 'N/A'})"
            for r in reviews
        )

        change_summary = "\n".join(
            f"- {c['competitor_name']}: {c['change_type']} - {c['details'][:80]}"
            for c in changes[:10]
        ) if changes else "(최근 변경 감지 없음)"

        analysis = await self.think(f"""
경쟁사 분석 보고서를 작성해주세요.

[최근 30일 리뷰 현황]
{review_summary or "(데이터 없음)"}

[최근 14일 변경 감지]
{change_summary}

[분석 요청]
1. 가장 위협적인 경쟁사와 이유
2. 경쟁사 약점에서 파생되는 기회
3. 우리가 차별화할 수 있는 포인트
""", max_tokens=1500)

        return {"analysis": analysis, "competitors": len(reviews), "changes": len(changes)}

    async def _find_opportunities(self) -> Dict[str, Any]:
        """경쟁사 약점 기반 기회 발굴"""
        weaknesses = self.query_db("""
            SELECT competitor_name, weakness_type, description, severity
            FROM competitor_weaknesses
            ORDER BY created_at DESC
            LIMIT 20
        """)

        negative_reviews = self.query_db("""
            SELECT competitor_name, content
            FROM competitor_reviews
            WHERE sentiment = 'negative'
              AND review_date >= date('now', '-30 days')
            ORDER BY review_date DESC
            LIMIT 10
        """)

        weakness_text = "\n".join(
            f"- {w['competitor_name']}: [{w['weakness_type']}] {w['description'][:80]}"
            for w in weaknesses[:10]
        ) if weaknesses else "(약점 데이터 없음)"

        negative_text = "\n".join(
            f"- {r['competitor_name']}: {r['content'][:100]}"
            for r in negative_reviews[:5]
        ) if negative_reviews else "(부정 리뷰 데이터 없음)"

        opportunities = await self.think(f"""
경쟁사 약점에서 마케팅 기회를 도출해주세요.

[약점 분석]
{weakness_text}

[경쟁사 부정 리뷰]
{negative_text}

[요청]
1. 즉시 활용 가능한 기회 3가지
2. 각 기회에 대한 구체적 마케팅 액션
3. 블로그/SNS 콘텐츠 주제 제안
""", max_tokens=1200)

        return {"opportunities": opportunities}

    async def _threat_assessment(self) -> Dict[str, Any]:
        """위협 평가"""
        # 경쟁사 순위 변동
        comp_rankings = self.query_db("""
            SELECT target_name, keyword, rank, scanned_at
            FROM rank_history
            WHERE target_name != '규림한의원'
              AND status = 'found' AND rank > 0
              AND scanned_at >= datetime('now', '-7 days')
            ORDER BY rank ASC
            LIMIT 30
        """)

        ranking_text = "\n".join(
            f"- {r['target_name']}: {r['keyword']} {r['rank']}위"
            for r in comp_rankings[:15]
        ) if comp_rankings else "(경쟁사 순위 데이터 없음)"

        assessment = await self.think(f"""
경쟁사 위협 수준을 평가해주세요.

[경쟁사 순위 현황 (최근 7일)]
{ranking_text}

[평가 요청]
1. 위협 수준 (높음/중간/낮음) 및 근거
2. 가장 공격적인 경쟁사
3. 방어 전략 제안
""")

        return {"assessment": assessment, "tracked_competitors": len(set(r['target_name'] for r in comp_rankings))}

"""
SEO Agent - 키워드 분석 및 순위 전략 에이전트
"""

from typing import Dict, Any
from services.ai_agents.base_agent import BaseAgent


class SEOAgent(BaseAgent):
    def __init__(self, db_path: str = None):
        super().__init__(
            name="SEO Analyst",
            role="한의원 전문 SEO 분석가",
            goal="키워드 순위를 분석하고 상위 노출을 위한 전략을 제안합니다",
            db_path=db_path,
        )

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        action = task.get("action", "analyze_rankings")

        if action == "analyze_rankings":
            return await self._analyze_rankings()
        elif action == "suggest_keywords":
            return await self._suggest_keywords(task.get("category", ""))
        elif action == "weekly_report":
            return await self._weekly_seo_report()
        else:
            return {"error": f"Unknown action: {action}"}

    async def _analyze_rankings(self) -> Dict[str, Any]:
        """현재 순위 분석 및 개선 제안"""
        rankings = self.query_db("""
            SELECT keyword, rank, status, device_type,
                   scanned_at
            FROM rank_history
            WHERE scanned_at >= datetime('now', '-7 days')
              AND status = 'found'
            ORDER BY scanned_at DESC
            LIMIT 50
        """)

        if not rankings:
            return {"analysis": "최근 7일간 순위 데이터가 없습니다.", "suggestions": []}

        summary = f"최근 7일간 {len(rankings)}건의 순위 데이터:\n"
        for r in rankings[:20]:
            summary += f"- {r['keyword']}: {r['rank']}위 ({r['device_type']})\n"

        analysis = await self.think(f"""
다음 한의원의 네이버 플레이스 순위 데이터를 분석하고 전략을 제안해주세요.

{summary}

분석 요청:
1. 상위 유지 키워드와 하락 키워드 구분
2. 모바일/데스크톱 순위 차이가 큰 키워드
3. 순위 개선을 위한 구체적 액션 3가지
""")

        return {"analysis": analysis, "data_count": len(rankings)}

    async def _suggest_keywords(self, category: str) -> Dict[str, Any]:
        """새 키워드 제안"""
        existing = self.query_db(
            "SELECT keyword, grade FROM keyword_insights ORDER BY created_at DESC LIMIT 30"
        )

        existing_list = ", ".join(k['keyword'] for k in existing[:20])

        suggestions = await self.think(f"""
현재 한의원이 추적 중인 키워드: {existing_list}

카테고리: {category or '전체'}

아직 추적하지 않지만 잠재적으로 가치 있는 키워드 10개를 제안해주세요.
각 키워드에 대해 추천 이유를 간단히 설명해주세요.
""")

        return {"suggestions": suggestions, "existing_count": len(existing)}

    async def _weekly_seo_report(self) -> Dict[str, Any]:
        """주간 SEO 보고서 생성"""
        stats = self.query_db("""
            SELECT
                keyword,
                MIN(rank) as best_rank,
                MAX(rank) as worst_rank,
                AVG(rank) as avg_rank,
                COUNT(*) as scan_count
            FROM rank_history
            WHERE scanned_at >= datetime('now', '-7 days')
              AND status = 'found' AND rank > 0
            GROUP BY keyword
            ORDER BY avg_rank ASC
        """)

        if not stats:
            return {"report": "주간 데이터 없음"}

        data_summary = "\n".join(
            f"- {s['keyword']}: 평균 {s['avg_rank']:.0f}위 (최고 {s['best_rank']}위)"
            for s in stats[:15]
        )

        report = await self.think(f"""
주간 SEO 보고서를 작성해주세요.

[데이터]
{data_summary}

[포함 사항]
1. 주간 순위 요약 (상승/하락 키워드)
2. 핵심 인사이트 3가지
3. 다음 주 액션 플랜
""", max_tokens=1500)

        return {"report": report, "keywords_tracked": len(stats)}

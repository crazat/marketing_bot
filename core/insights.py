"""
Cross-Module Insights Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 2.5] 모듈 간 인사이트 생성
- 키워드-순위 상관관계 분석
- 경쟁사-리드 연결 분석
- 종합 마케팅 기회 발굴
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


@dataclass
class MarketingInsight:
    """마케팅 인사이트"""
    category: str  # keyword, competitor, lead, viral, opportunity
    title: str
    description: str
    data: Dict[str, Any]
    priority: str  # high, medium, low
    actions: List[str]
    related_modules: List[str]
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "data": self.data,
            "priority": self.priority,
            "actions": self.actions,
            "related_modules": self.related_modules,
            "created_at": self.created_at.isoformat()
        }


class CrossModuleInsightsEngine:
    """
    모듈 간 인사이트 생성 엔진

    여러 데이터 소스를 통합하여 마케팅 기회 발굴
    """

    def __init__(self):
        self.db = None
        self._init_db()
        self.insights_cache: List[MarketingInsight] = []
        logger.info("CrossModuleInsightsEngine initialized")

    def _init_db(self):
        """DB 연결"""
        try:
            from db.database import DatabaseManager
            self.db = DatabaseManager()
        except Exception as e:
            logger.error(f"Failed to initialize DB: {e}")

    # ============================================================
    # 키워드-순위 상관관계 분석
    # ============================================================

    def analyze_keyword_rank_correlation(self) -> List[MarketingInsight]:
        """
        발굴된 키워드와 순위 데이터 상관관계 분석

        발굴된 S/A 등급 키워드 중 순위 체크가 안 된 것들 식별
        """
        insights = []

        if not self.db:
            return insights

        try:
            # S/A 등급 키워드 중 순위 미체크
            self.db.cursor.execute('''
                SELECT ki.keyword, ki.grade, ki.search_volume
                FROM keyword_insights ki
                LEFT JOIN (
                    SELECT DISTINCT keyword FROM rank_history
                    WHERE checked_at >= date('now', '-7 days')
                ) rh ON ki.keyword = rh.keyword
                WHERE ki.grade IN ('S', 'A')
                  AND rh.keyword IS NULL
                ORDER BY ki.search_volume DESC
                LIMIT 10
            ''')

            unchecked = self.db.cursor.fetchall()

            if unchecked:
                keywords = [row[0] for row in unchecked]
                insights.append(MarketingInsight(
                    category="keyword",
                    title=f"고가치 키워드 {len(unchecked)}개 순위 미체크",
                    description="S/A 등급 키워드 중 최근 7일간 순위 체크가 되지 않은 키워드가 있습니다.",
                    data={
                        "keywords": keywords[:5],
                        "total_count": len(unchecked)
                    },
                    priority="high",
                    actions=[
                        "해당 키워드를 keywords.json에 추가",
                        "Place Sniper 스캔 실행",
                        "순위 모니터링 시작"
                    ],
                    related_modules=["pathfinder", "battle"]
                ))

            # 순위 상승 중인 키워드
            self.db.cursor.execute('''
                SELECT r1.keyword,
                       r1.rank as current_rank,
                       r2.rank as prev_rank,
                       (r2.rank - r1.rank) as improvement
                FROM (
                    SELECT keyword, rank
                    FROM rank_history
                    WHERE date(checked_at) = date('now')
                      AND status = 'found'
                ) r1
                JOIN (
                    SELECT keyword, rank
                    FROM rank_history
                    WHERE date(checked_at) = date('now', '-7 days')
                      AND status = 'found'
                ) r2 ON r1.keyword = r2.keyword
                WHERE r2.rank > r1.rank
                ORDER BY improvement DESC
                LIMIT 5
            ''')

            improving = self.db.cursor.fetchall()

            if improving:
                insights.append(MarketingInsight(
                    category="opportunity",
                    title=f"순위 상승 중인 키워드 {len(improving)}개 발견",
                    description="최근 7일간 순위가 상승한 키워드입니다. 추가 콘텐츠로 모멘텀을 유지하세요.",
                    data={
                        "keywords": [
                            {"keyword": row[0], "current": row[1], "improvement": row[3]}
                            for row in improving
                        ]
                    },
                    priority="medium",
                    actions=[
                        "상승 키워드 관련 블로그 포스팅 작성",
                        "네이버 플레이스 정보 업데이트"
                    ],
                    related_modules=["battle", "pathfinder"]
                ))

        except Exception as e:
            logger.error(f"Keyword-rank correlation analysis failed: {e}")

        return insights

    # ============================================================
    # 경쟁사-기회 연결 분석
    # ============================================================

    def analyze_competitor_opportunities(self) -> List[MarketingInsight]:
        """
        경쟁사 약점과 마케팅 기회 연결

        경쟁사 부정 리뷰에서 우리의 강점으로 공략할 키워드 발굴
        """
        insights = []

        if not self.db:
            return insights

        try:
            # 경쟁사별 부정 리뷰 키워드
            self.db.cursor.execute('''
                SELECT competitor_name,
                       COUNT(*) as negative_count,
                       GROUP_CONCAT(DISTINCT content) as samples
                FROM competitor_reviews
                WHERE sentiment = 'negative'
                  AND scraped_at >= date('now', '-30 days')
                GROUP BY competitor_name
                HAVING negative_count >= 3
                ORDER BY negative_count DESC
            ''')

            results = self.db.cursor.fetchall()

            weakness_keywords = {
                "대기": "빠른 진료",
                "비싸": "합리적인 가격",
                "불친절": "친절한 상담",
                "효과없": "검증된 효과",
                "오래": "신속한 치료"
            }

            for competitor, count, samples in results:
                detected_weaknesses = []
                opportunity_keywords = []

                sample_text = samples or ""
                for weakness, opportunity in weakness_keywords.items():
                    if weakness in sample_text:
                        detected_weaknesses.append(weakness)
                        opportunity_keywords.append(opportunity)

                if detected_weaknesses:
                    insights.append(MarketingInsight(
                        category="competitor",
                        title=f"{competitor} 약점 공략 기회",
                        description=f"{competitor}의 부정 리뷰에서 '{', '.join(detected_weaknesses)}' 관련 불만이 감지되었습니다.",
                        data={
                            "competitor": competitor,
                            "negative_count": count,
                            "weaknesses": detected_weaknesses,
                            "opportunities": opportunity_keywords
                        },
                        priority="high" if count >= 10 else "medium",
                        actions=[
                            f"'{opportunity_keywords[0]}' 강조 콘텐츠 제작",
                            f"경쟁사 대비 차별점 블로그 포스팅",
                            "리뷰 마케팅 강화"
                        ],
                        related_modules=["competitors", "viral"]
                    ))

        except Exception as e:
            logger.error(f"Competitor opportunities analysis failed: {e}")

        return insights

    # ============================================================
    # 리드-바이럴 연결 분석
    # ============================================================

    def analyze_lead_viral_synergy(self) -> List[MarketingInsight]:
        """
        리드와 바이럴 타겟 시너지 분석

        Hot Lead가 많이 발견된 플랫폼에서 바이럴 활동 강화 권장
        """
        insights = []

        if not self.db:
            return insights

        try:
            # 플랫폼별 리드 수
            self.db.cursor.execute('''
                SELECT source, COUNT(*) as lead_count
                FROM mentions
                WHERE scraped_at >= date('now', '-30 days')
                  AND status = 'New'
                GROUP BY source
                ORDER BY lead_count DESC
            ''')

            lead_sources = self.db.cursor.fetchall()

            # 플랫폼별 바이럴 타겟 수
            self.db.cursor.execute('''
                SELECT source, COUNT(*) as viral_count
                FROM viral_targets
                WHERE discovered_at >= date('now', '-30 days')
                GROUP BY source
            ''')

            viral_sources = {row[0]: row[1] for row in self.db.cursor.fetchall()}

            for source, lead_count in lead_sources[:5]:
                viral_count = viral_sources.get(source, 0)

                if lead_count >= 10 and viral_count < 5:
                    insights.append(MarketingInsight(
                        category="lead",
                        title=f"{source}에서 바이럴 활동 강화 권장",
                        description=f"{source}에서 {lead_count}개의 리드가 발견되었지만 바이럴 활동({viral_count}개)이 부족합니다.",
                        data={
                            "source": source,
                            "lead_count": lead_count,
                            "viral_count": viral_count,
                            "gap": lead_count - viral_count
                        },
                        priority="medium",
                        actions=[
                            f"{source} 바이럴 타겟 추가 발굴",
                            "Viral Hunter로 해당 플랫폼 스캔",
                            "맞춤형 댓글/콘텐츠 전략 수립"
                        ],
                        related_modules=["leads", "viral"]
                    ))

        except Exception as e:
            logger.error(f"Lead-viral synergy analysis failed: {e}")

        return insights

    # ============================================================
    # 종합 인사이트 생성
    # ============================================================

    def generate_all_insights(self) -> List[MarketingInsight]:
        """모든 분석 실행 및 인사이트 생성"""
        all_insights = []

        # 각 분석 실행
        all_insights.extend(self.analyze_keyword_rank_correlation())
        all_insights.extend(self.analyze_competitor_opportunities())
        all_insights.extend(self.analyze_lead_viral_synergy())

        # 우선순위 순 정렬
        priority_order = {"high": 0, "medium": 1, "low": 2}
        all_insights.sort(key=lambda x: priority_order.get(x.priority, 2))

        # 캐시 업데이트
        self.insights_cache = all_insights

        logger.info(f"Generated {len(all_insights)} cross-module insights")
        return all_insights

    def get_insights_summary(self) -> Dict[str, Any]:
        """인사이트 요약 반환"""
        if not self.insights_cache:
            self.generate_all_insights()

        by_category = defaultdict(list)
        by_priority = defaultdict(int)

        for insight in self.insights_cache:
            by_category[insight.category].append(insight.title)
            by_priority[insight.priority] += 1

        return {
            "total_insights": len(self.insights_cache),
            "by_priority": dict(by_priority),
            "by_category": {k: len(v) for k, v in by_category.items()},
            "top_insights": [
                insight.to_dict() for insight in self.insights_cache[:5]
            ],
            "generated_at": datetime.now().isoformat()
        }

    def get_actionable_recommendations(self) -> List[Dict[str, Any]]:
        """실행 가능한 권장사항 목록 반환"""
        if not self.insights_cache:
            self.generate_all_insights()

        recommendations = []

        for insight in self.insights_cache:
            for action in insight.actions[:2]:  # 인사이트당 상위 2개 액션
                recommendations.append({
                    "action": action,
                    "source_insight": insight.title,
                    "priority": insight.priority,
                    "related_modules": insight.related_modules
                })

        return recommendations[:10]  # 상위 10개

    def generate_daily_briefing(self) -> str:
        """일일 브리핑 텍스트 생성"""
        insights = self.generate_all_insights()

        if not insights:
            return "오늘 발견된 주요 인사이트가 없습니다."

        lines = [
            "═" * 50,
            "📊 일일 마케팅 인사이트 브리핑",
            f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "═" * 50,
            ""
        ]

        # 우선순위별 그룹화
        high_priority = [i for i in insights if i.priority == "high"]
        medium_priority = [i for i in insights if i.priority == "medium"]

        if high_priority:
            lines.append("🔴 [높은 우선순위]")
            for insight in high_priority[:3]:
                lines.append(f"  • {insight.title}")
                lines.append(f"    → 권장: {insight.actions[0]}")
            lines.append("")

        if medium_priority:
            lines.append("🟡 [중간 우선순위]")
            for insight in medium_priority[:3]:
                lines.append(f"  • {insight.title}")
            lines.append("")

        lines.extend([
            "─" * 50,
            f"총 {len(insights)}개 인사이트 발견",
            "상세 내용은 대시보드에서 확인하세요.",
            "═" * 50
        ])

        return "\n".join(lines)


# 싱글톤 인스턴스
_insights_engine = None


def get_insights_engine() -> CrossModuleInsightsEngine:
    """CrossModuleInsightsEngine 싱글톤 인스턴스 반환"""
    global _insights_engine
    if _insights_engine is None:
        _insights_engine = CrossModuleInsightsEngine()
    return _insights_engine

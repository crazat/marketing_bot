"""
Priority Score Calculator Service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 6.2] Viral Hunter priority_score 계산 로직 통합

여러 곳에 분산된 priority_score 계산 로직을 단일 서비스로 통합:
- 기본 점수 계산 (질문, 건강, Hot Lead, 즉시 행동)
- 플랫폼별 가중치
- 키워드 티어별 점수
- 광고 키워드 감점
- 경쟁사 탐지 보너스
- 침투 적합도 보너스
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PriorityScoreResult:
    """우선순위 점수 계산 결과"""
    score: int
    tags: List[str]
    breakdown: Dict[str, int]  # 점수 상세 분해


class PriorityScorer:
    """
    바이럴 타겟 우선순위 점수 계산기

    점수 구성 (최대 150점):
    - 질문글 보너스: +30점
    - 건강 관련: +25점
    - Hot Lead: +25점
    - 즉시 행동 신호: +15점
    - 플랫폼별 가중치: +8~22점
    - 키워드 티어: +5~40점
    - 경쟁사 탐지: +25점
    - 침투 적합도: +25점
    - 광고 키워드: -5점/키워드
    """

    # 질문 키워드 패턴
    INQUIRY_KEYWORDS = [
        "추천", "어디", "좋은", "알려", "괜찮", "어떤", "어느",
        "잘하는", "유명한", "소문", "평판", "후기", "리뷰",
        "경험", "해보신", "아시는", "알려주", "?", "궁금",
        "좋을까", "할까", "될까", "있을까", "볼까"
    ]

    # 건강 관련 키워드
    HEALTH_KEYWORDS = [
        "한의원", "한방", "침", "뜸", "한약", "보약", "다이어트",
        "살", "몸무게", "체중", "비만", "다한증", "땀", "면역",
        "피부", "여드름", "아토피", "알레르기", "두통", "편두통",
        "불면", "수면", "어지럼", "이명", "소화", "위장",
        "변비", "설사", "생리통", "갱년기", "교통사고", "추나",
        "디스크", "허리", "목", "어깨", "무릎", "관절"
    ]

    # Hot Lead 키워드 (구매/전환 의향 높음)
    HOT_LEAD_KEYWORDS = [
        "예약", "전화", "상담", "문의", "방문", "가격", "비용",
        "얼마", "할인", "이벤트", "프로모션", "결정", "선택",
        "비교", "추천좀", "알려주세요", "해주세요"
    ]

    # 즉시 행동 신호 키워드
    READY_TO_ACT_KEYWORDS = [
        "예약", "전화", "상담", "문의", "가격", "비용",
        "방문", "예정", "결정", "선택", "비교"
    ]

    # SOFT 광고 키워드 (감점 대상)
    SOFT_AD_KEYWORDS = [
        "협찬", "제공", "광고", "체험단", "원고료", "무료체험",
        "이벤트참여", "서포터즈", "인플루언서"
    ]

    # 플랫폼별 가중치 (전환율 기반)
    PLATFORM_WEIGHTS = {
        'cafe': 22,       # 맘카페 = 고전환율
        'blog': 18,       # 블로그 = 신뢰 정보원
        'youtube': 16,    # YouTube = 영상 신뢰도
        'kin': 15,        # 지식인 = 질문 많지만 전환 낮음
        'instagram': 12,  # Instagram = 참여도 높지만 전환 낮음
        'tiktok': 10,     # TikTok = 단기 트렌드
        'karrot': 8,      # 당근마켓 = 지역 기반
    }

    # 키워드 티어 정의
    KEYWORD_TIERS = {
        'tier1': [
            "청주 한의원", "청주 다이어트", "청주 교통사고",
            "청주 추나", "청주 보약"
        ],
        'tier2': [
            "청주 여드름", "청주 안면비대칭", "청주 피부",
            "청주 탈모", "청주 갱년기"
        ],
        'tier3': [
            "청주 두통", "청주 불면증", "청주 소화불량"
        ]
    }

    # 티어별 점수
    TIER_SCORES = {
        'tier1': 15,
        'tier2': 10,
        'tier3': 5
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        초기화

        Args:
            config: 커스텀 설정 (키워드, 가중치 오버라이드 가능)
        """
        self.config = config or {}

        # 커스텀 설정 적용
        if 'platform_weights' in self.config:
            self.PLATFORM_WEIGHTS.update(self.config['platform_weights'])
        if 'keyword_tiers' in self.config:
            self.KEYWORD_TIERS.update(self.config['keyword_tiers'])

    def calculate_score(
        self,
        text: str,
        platform: str,
        matched_keywords: Optional[List[str]] = None,
        has_competitor_mention: bool = False,
        is_highly_infiltrable: bool = False
    ) -> PriorityScoreResult:
        """
        우선순위 점수 계산

        Args:
            text: 분석할 텍스트 (제목 + 본문)
            platform: 플랫폼명 (cafe, blog, kin 등)
            matched_keywords: 매칭된 키워드 목록
            has_competitor_mention: 경쟁사 언급 여부 (AI 분석 결과)
            is_highly_infiltrable: 침투 적합도 높음 여부 (AI 분석 결과)

        Returns:
            PriorityScoreResult: 점수, 태그, 상세 분해
        """
        score = 0
        tags = []
        breakdown = {}

        text_lower = text.lower()

        # 1. 질문글 보너스
        is_inquiry = any(kw in text for kw in self.INQUIRY_KEYWORDS)
        if is_inquiry:
            inquiry_score = 30
            score += inquiry_score
            tags.append("❓질문")
            breakdown['inquiry'] = inquiry_score

        # 2. 건강 관련 보너스
        is_health = any(kw in text_lower for kw in self.HEALTH_KEYWORDS)
        if is_health:
            health_score = 25
            score += health_score
            tags.append("🏥건강")
            breakdown['health'] = health_score

        # 3. Hot Lead 감지
        hot_lead_matched = [kw for kw in self.HOT_LEAD_KEYWORDS if kw in text]
        if hot_lead_matched:
            hot_score = 25
            score += hot_score
            tags.append("🔥HOT")
            breakdown['hot_lead'] = hot_score

        # 4. 즉시 행동 신호
        has_ready_signal = any(kw in text for kw in self.READY_TO_ACT_KEYWORDS)
        if has_ready_signal and "🔥HOT" not in tags:  # Hot Lead와 중복 방지
            ready_score = 15
            score += ready_score
            tags.append("⚡즉시")
            breakdown['ready_to_act'] = ready_score

        # 5. 플랫폼별 가중치
        platform_score = self.PLATFORM_WEIGHTS.get(platform, 10)
        score += platform_score
        breakdown['platform'] = platform_score

        # 6. 키워드 티어 점수 (최대 40점)
        if matched_keywords:
            keyword_score = self._calculate_keyword_tier_score(matched_keywords)
            score += keyword_score
            breakdown['keyword_tier'] = keyword_score

        # 7. 광고 키워드 감점
        ad_penalty = self._calculate_ad_penalty(text)
        if ad_penalty < 0:
            score += ad_penalty
            tags.append("⚠️광고")
            breakdown['ad_penalty'] = ad_penalty

        # 8. 경쟁사 탐지 보너스 (AI 분석 결과)
        if has_competitor_mention:
            competitor_score = 25
            score += competitor_score
            tags.append("🎯경쟁사")
            breakdown['competitor'] = competitor_score

        # 9. 침투 적합도 보너스 (AI 분석 결과)
        if is_highly_infiltrable:
            infiltrate_score = 25
            score += infiltrate_score
            tags.append("✅적합")
            breakdown['infiltrable'] = infiltrate_score

        # 점수 캡 적용 (0~150)
        final_score = max(0, min(score, 150))
        breakdown['raw_total'] = score
        breakdown['final'] = final_score

        return PriorityScoreResult(
            score=final_score,
            tags=tags,
            breakdown=breakdown
        )

    def _calculate_keyword_tier_score(self, keywords: List[str]) -> int:
        """
        키워드 티어별 점수 계산 (최대 40점)
        """
        total = 0

        for keyword in keywords[:4]:  # 최대 4개까지
            keyword_lower = keyword.lower()

            if any(t1.lower() in keyword_lower for t1 in self.KEYWORD_TIERS.get('tier1', [])):
                total += self.TIER_SCORES['tier1']
            elif any(t2.lower() in keyword_lower for t2 in self.KEYWORD_TIERS.get('tier2', [])):
                total += self.TIER_SCORES['tier2']
            elif any(t3.lower() in keyword_lower for t3 in self.KEYWORD_TIERS.get('tier3', [])):
                total += self.TIER_SCORES['tier3']
            else:
                total += 5  # 기본 점수

        return min(total, 40)  # 최대 40점

    def _calculate_ad_penalty(self, text: str) -> int:
        """
        광고 키워드 감점 계산
        """
        penalty = 0
        for kw in self.SOFT_AD_KEYWORDS:
            if kw in text:
                penalty -= 5
        return max(penalty, -25)  # 최대 -25점

    def get_tags_string(self, tags: List[str]) -> str:
        """태그 목록을 문자열로 변환"""
        return " ".join(tags) if tags else ""

    def explain_score(self, result: PriorityScoreResult) -> str:
        """
        점수 상세 설명 생성
        """
        lines = [f"총점: {result.score}점"]

        if result.breakdown:
            lines.append("\n점수 상세:")
            for key, value in result.breakdown.items():
                if key not in ('raw_total', 'final') and value != 0:
                    lines.append(f"  - {key}: {value:+d}점")

        if result.tags:
            lines.append(f"\n태그: {self.get_tags_string(result.tags)}")

        return "\n".join(lines)


# 싱글톤 인스턴스
_scorer_instance: Optional[PriorityScorer] = None


def get_priority_scorer(config: Optional[Dict[str, Any]] = None) -> PriorityScorer:
    """PriorityScorer 싱글톤 인스턴스 반환"""
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = PriorityScorer(config)
    return _scorer_instance


def calculate_priority_score(
    text: str,
    platform: str,
    matched_keywords: Optional[List[str]] = None,
    has_competitor_mention: bool = False,
    is_highly_infiltrable: bool = False
) -> int:
    """
    간편 함수: 우선순위 점수만 반환
    """
    scorer = get_priority_scorer()
    result = scorer.calculate_score(
        text=text,
        platform=platform,
        matched_keywords=matched_keywords,
        has_competitor_mention=has_competitor_mention,
        is_highly_infiltrable=is_highly_infiltrable
    )
    return result.score

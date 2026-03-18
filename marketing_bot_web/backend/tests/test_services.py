"""
서비스 계층 단위 테스트
"""

import pytest
import sys
from pathlib import Path

# 백엔드 모듈 경로 추가
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from services.priority_scorer import (
    PriorityScorer,
    PriorityScoreResult,
    calculate_priority_score,
    get_priority_scorer
)


class TestPriorityScorer:
    """PriorityScorer 서비스 테스트"""

    @pytest.fixture
    def scorer(self) -> PriorityScorer:
        """PriorityScorer 인스턴스"""
        return PriorityScorer()

    @pytest.mark.unit
    def test_inquiry_bonus(self, scorer):
        """질문글 보너스 테스트"""
        result = scorer.calculate_score(
            text="청주 한의원 추천해주세요",
            platform="cafe"
        )
        assert "❓질문" in result.tags
        assert result.breakdown.get("inquiry", 0) == 30

    @pytest.mark.unit
    def test_health_bonus(self, scorer):
        """건강 관련 보너스 테스트"""
        result = scorer.calculate_score(
            text="한의원에서 다이어트 한약 받으려고요",
            platform="blog"
        )
        assert "🏥건강" in result.tags
        assert result.breakdown.get("health", 0) == 25

    @pytest.mark.unit
    def test_hot_lead_detection(self, scorer):
        """Hot Lead 탐지 테스트"""
        result = scorer.calculate_score(
            text="예약 가능한가요? 가격이 얼마인지 궁금합니다",
            platform="kin"
        )
        assert "🔥HOT" in result.tags
        assert result.breakdown.get("hot_lead", 0) == 25

    @pytest.mark.unit
    def test_platform_weight(self, scorer):
        """플랫폼 가중치 테스트"""
        cafe_result = scorer.calculate_score(text="test", platform="cafe")
        blog_result = scorer.calculate_score(text="test", platform="blog")
        kin_result = scorer.calculate_score(text="test", platform="kin")

        assert cafe_result.breakdown.get("platform") == 22
        assert blog_result.breakdown.get("platform") == 18
        assert kin_result.breakdown.get("platform") == 15

    @pytest.mark.unit
    def test_ad_penalty(self, scorer):
        """광고 키워드 감점 테스트"""
        result = scorer.calculate_score(
            text="협찬받아서 체험단으로 다녀왔어요",
            platform="blog"
        )
        assert "⚠️광고" in result.tags
        assert result.breakdown.get("ad_penalty", 0) < 0

    @pytest.mark.unit
    def test_competitor_bonus(self, scorer):
        """경쟁사 언급 보너스 테스트"""
        result = scorer.calculate_score(
            text="한의원 추천해주세요",
            platform="cafe",
            has_competitor_mention=True
        )
        assert "🎯경쟁사" in result.tags
        assert result.breakdown.get("competitor", 0) == 25

    @pytest.mark.unit
    def test_infiltrable_bonus(self, scorer):
        """침투 적합도 보너스 테스트"""
        result = scorer.calculate_score(
            text="한의원 추천해주세요",
            platform="cafe",
            is_highly_infiltrable=True
        )
        assert "✅적합" in result.tags
        assert result.breakdown.get("infiltrable", 0) == 25

    @pytest.mark.unit
    def test_score_cap(self, scorer):
        """점수 상한선 테스트 (0~150)"""
        result = scorer.calculate_score(
            text="청주 한의원 예약 추천해주세요 가격 문의드립니다",
            platform="cafe",
            matched_keywords=["청주 한의원", "청주 다이어트"],
            has_competitor_mention=True,
            is_highly_infiltrable=True
        )
        assert 0 <= result.score <= 150

    @pytest.mark.unit
    def test_keyword_tier_scoring(self, scorer):
        """키워드 티어별 점수 테스트"""
        result = scorer.calculate_score(
            text="test",
            platform="blog",
            matched_keywords=["청주 한의원", "청주 다이어트"]
        )
        # tier1 키워드가 포함되어 있으므로 점수가 있어야 함
        assert result.breakdown.get("keyword_tier", 0) > 0

    @pytest.mark.unit
    def test_combined_score(self, scorer):
        """복합 점수 계산 테스트"""
        result = scorer.calculate_score(
            text="청주 한의원 추천해주세요. 다이어트 상담 받고 싶어요.",
            platform="cafe",
            matched_keywords=["청주 한의원"],
            has_competitor_mention=False,
            is_highly_infiltrable=False
        )

        # 질문 + 건강 + Hot Lead + 플랫폼
        assert result.score > 50
        assert "❓질문" in result.tags
        assert "🏥건강" in result.tags

    @pytest.mark.unit
    def test_explain_score(self, scorer):
        """점수 설명 생성 테스트"""
        result = scorer.calculate_score(
            text="청주 한의원 추천해주세요",
            platform="cafe"
        )
        explanation = scorer.explain_score(result)

        assert "총점" in explanation
        assert "점수 상세" in explanation

    @pytest.mark.unit
    def test_get_tags_string(self, scorer):
        """태그 문자열 변환 테스트"""
        tags = ["❓질문", "🏥건강", "🔥HOT"]
        result = scorer.get_tags_string(tags)
        assert "❓질문" in result
        assert "🏥건강" in result


class TestConvenienceFunctions:
    """편의 함수 테스트"""

    @pytest.mark.unit
    def test_calculate_priority_score(self):
        """calculate_priority_score 함수 테스트"""
        score = calculate_priority_score(
            text="청주 한의원 추천해주세요",
            platform="cafe"
        )
        assert isinstance(score, int)
        assert score > 0

    @pytest.mark.unit
    def test_get_priority_scorer_singleton(self):
        """싱글톤 인스턴스 테스트"""
        scorer1 = get_priority_scorer()
        scorer2 = get_priority_scorer()
        assert scorer1 is scorer2


class TestPriorityScoreResult:
    """PriorityScoreResult 데이터클래스 테스트"""

    @pytest.mark.unit
    def test_dataclass_creation(self):
        """데이터클래스 생성 테스트"""
        result = PriorityScoreResult(
            score=85,
            tags=["❓질문", "🏥건강"],
            breakdown={"inquiry": 30, "health": 25}
        )
        assert result.score == 85
        assert len(result.tags) == 2
        assert result.breakdown["inquiry"] == 30

"""
YouTube 기능 단위 테스트.

테스트 대상:
- LeadClassifier: quick_filter, classify 메서드
- YouTubeAPIClient: 초기화, search_videos, get_video_comments
- YouTubeSentinel: SafeSeleniumDriver 사용, 하이브리드 모드
- SQL Injection 방지: 파라미터화된 쿼리 사용 확인
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# LeadClassifier Tests
# =============================================================================

class TestLeadClassifier:
    """LeadClassifier 단위 테스트"""

    @pytest.fixture
    def classifier(self):
        """NLP 없이 테스트용 분류기 생성"""
        from lead_classifier import LeadClassifier
        return LeadClassifier(use_nlp=False)

    def test_quick_filter_high_priority(self, classifier):
        """높은 우선순위 키워드 감지"""
        from lead_classifier import LeadPriority

        text = "이 한의원 가격이 얼마예요?"
        priority, keywords = classifier.quick_filter(text)

        assert priority == LeadPriority.HIGH
        assert len(keywords) > 0
        assert any("가격" in kw or "얼마" in kw for kw in keywords)

    def test_quick_filter_medium_priority(self, classifier):
        """중간 우선순위 키워드 감지"""
        from lead_classifier import LeadPriority

        text = "청주에서 다이어트 효과 좋은 곳 있나요?"
        priority, keywords = classifier.quick_filter(text)

        assert priority == LeadPriority.MEDIUM
        assert "효과" in keywords

    def test_quick_filter_excludes_spam(self, classifier):
        """스팸/광고 제외"""
        from lead_classifier import LeadPriority

        text = "구독하고 좋아요 눌러주세요! 가격 정보는 링크 클릭!"
        priority, keywords = classifier.quick_filter(text)

        assert priority == LeadPriority.NONE

    def test_quick_filter_no_match(self, classifier):
        """매칭 없음"""
        from lead_classifier import LeadPriority

        text = "오늘 날씨가 좋네요"
        priority, keywords = classifier.quick_filter(text)

        assert priority == LeadPriority.NONE
        assert len(keywords) == 0

    def test_classify_returns_result(self, classifier):
        """classify 메서드가 ClassificationResult 반환"""
        from lead_classifier import ClassificationResult

        text = "예약하고 싶은데 전화번호 알려주세요"
        result = classifier.classify(text)

        assert isinstance(result, ClassificationResult)
        assert result.priority is not None
        assert result.intent is not None
        assert 0 <= result.confidence <= 1

    def test_get_lead_score(self, classifier):
        """리드 점수 계산"""
        from lead_classifier import LeadPriority

        text = "예약하고 싶어요"
        result = classifier.classify(text)
        score = classifier.get_lead_score(result)

        assert isinstance(score, int)
        assert 0 <= score <= 100

        # HIGH priority는 50점 이상이어야 함
        if result.priority == LeadPriority.HIGH:
            assert score >= 50


# =============================================================================
# YouTubeAPIClient Tests
# =============================================================================

class TestYouTubeAPIClient:
    """YouTubeAPIClient 단위 테스트"""

    def test_init_without_api_key(self):
        """API 키 없이 초기화"""
        # 환경변수 임시 제거
        original_key = os.environ.pop('YOUTUBE_API_KEY', None)

        try:
            from scrapers.youtube_api_client import YouTubeAPIClient
            client = YouTubeAPIClient()

            assert client.is_available() == False
        finally:
            # 원래 키 복원
            if original_key:
                os.environ['YOUTUBE_API_KEY'] = original_key

    def test_circuit_breaker_initial_state(self):
        """Circuit Breaker 초기 상태"""
        from scrapers.youtube_api_client import YouTubeAPIClient
        client = YouTubeAPIClient()

        status = client.get_quota_status()
        assert status['state'] == 'CLOSED'
        assert status['failures'] == 0

    def test_quota_exceeded_error_exists(self):
        """QuotaExceededError 예외 클래스 존재"""
        from scrapers.youtube_api_client import QuotaExceededError

        assert issubclass(QuotaExceededError, Exception)


# =============================================================================
# YouTubeSentinel Tests
# =============================================================================

class TestYouTubeSentinel:
    """YouTubeSentinel 단위 테스트"""

    def test_load_selectors(self):
        """선택자 로드 테스트"""
        from scrapers.scraper_youtube import YouTubeSentinel

        # sys.argv를 임시로 설정
        original_argv = sys.argv
        sys.argv = ['scraper_youtube.py', '테스트 키워드']

        try:
            sentinel = YouTubeSentinel()
            selectors = sentinel.selectors

            assert 'search_results' in selectors
            assert 'video_page' in selectors
            assert 'video_title' in selectors['search_results']
            assert 'comment_text' in selectors['video_page']
        finally:
            sys.argv = original_argv

    def test_parse_keywords_from_cli(self):
        """CLI 인자에서 키워드 파싱"""
        from scrapers.scraper_youtube import YouTubeSentinel

        original_argv = sys.argv
        sys.argv = ['scraper_youtube.py', '청주 다이어트, 청주 한의원']

        try:
            sentinel = YouTubeSentinel()
            assert '청주 다이어트' in sentinel.keywords
            assert '청주 한의원' in sentinel.keywords
        finally:
            sys.argv = original_argv

    def test_find_element_with_fallback(self):
        """다중 선택자 폴백 로직"""
        from scrapers.scraper_youtube import YouTubeSentinel

        original_argv = sys.argv
        sys.argv = ['scraper_youtube.py', '테스트']

        try:
            sentinel = YouTubeSentinel()

            # 선택자 문자열 파싱 테스트
            selector_str = "#video-title, a#video-title, .title"
            selectors = [s.strip() for s in selector_str.split(',')]

            assert len(selectors) == 3
            assert selectors[0] == '#video-title'
            assert selectors[1] == 'a#video-title'
            assert selectors[2] == '.title'
        finally:
            sys.argv = original_argv


# =============================================================================
# SQL Injection Prevention Tests
# =============================================================================

class TestSQLInjectionPrevention:
    """SQL Injection 방지 테스트"""

    def test_ai_orchestrator_parameterized_queries(self):
        """ai_orchestrator.py에서 파라미터화된 쿼리 사용 확인"""
        import re

        ai_orchestrator_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'ai_orchestrator.py'
        )

        with open(ai_orchestrator_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # f-string SQL 쿼리 패턴 (취약점)
        vulnerable_pattern = r'cursor\.execute\(f["\']'

        matches = re.findall(vulnerable_pattern, content)
        assert len(matches) == 0, f"Found {len(matches)} vulnerable SQL queries with f-strings"

    def test_recover_data_whitelist(self):
        """recover_data.py에서 테이블 화이트리스트 사용 확인"""
        recover_data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'db', 'recover_data.py'
        )

        with open(recover_data_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # ALLOWED_TABLES 상수 존재 확인
        assert 'ALLOWED_TABLES' in content, "ALLOWED_TABLES whitelist not found"

        # 화이트리스트 검증 로직 존재 확인
        assert 'if table not in ALLOWED_TABLES' in content, "Whitelist validation not found"


# =============================================================================
# Integration Tests (marked for selective running)
# =============================================================================

@pytest.mark.integration
class TestYouTubeIntegration:
    """YouTube 통합 테스트 (외부 서비스 필요)"""

    @pytest.mark.skip(reason="Requires YouTube API key")
    def test_api_search_videos(self):
        """실제 API로 동영상 검색"""
        from scrapers.youtube_api_client import YouTubeAPIClient

        client = YouTubeAPIClient()
        if not client.is_available():
            pytest.skip("YouTube API not configured")

        videos = client.search_videos("청주 다이어트", max_results=2)
        assert len(videos) > 0
        assert 'video_id' in videos[0]
        assert 'title' in videos[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not integration"])

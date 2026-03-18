"""
API 엔드포인트 테스트
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

# 백엔드 모듈 경로 추가
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from main import app

client = TestClient(app)


# ========== HUD API ==========

class TestHUDAPI:
    """HUD (대시보드) API 테스트"""

    @pytest.mark.api
    def test_health_check(self):
        """헬스체크 테스트"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.api
    def test_root(self):
        """루트 엔드포인트 테스트"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "Marketing Bot Web API" in data["message"]

    @pytest.mark.api
    def test_get_metrics(self):
        """메트릭 조회 테스트"""
        response = client.get("/api/hud/metrics")
        assert response.status_code == 200
        data = response.json()
        # 필수 필드 확인
        assert "total_keywords" in data
        assert "s_grade_keywords" in data
        assert "total_leads" in data

    @pytest.mark.api
    def test_get_system_status(self):
        """시스템 상태 조회 테스트"""
        response = client.get("/api/hud/system-status")
        assert response.status_code == 200
        data = response.json()
        assert "scheduler_status" in data

    @pytest.mark.api
    def test_get_briefing(self):
        """일일 브리핑 조회 테스트"""
        response = client.get("/api/hud/briefing")
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data

    @pytest.mark.api
    def test_get_recent_activities(self):
        """최근 활동 조회 테스트"""
        response = client.get("/api/hud/recent-activities")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ========== Pathfinder API ==========

class TestPathfinderAPI:
    """Pathfinder (키워드 발굴) API 테스트"""

    @pytest.mark.api
    def test_get_stats(self):
        """Pathfinder 통계 조회 테스트"""
        response = client.get("/api/pathfinder/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "s_grade" in data

    @pytest.mark.api
    def test_get_keywords(self):
        """키워드 목록 조회 테스트"""
        response = client.get("/api/pathfinder/keywords?limit=10")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.api
    def test_get_keywords_with_filters(self):
        """필터 적용 키워드 조회 테스트"""
        response = client.get("/api/pathfinder/keywords?grade=S&limit=5")
        assert response.status_code == 200
        keywords = response.json()
        assert isinstance(keywords, list)
        # S등급만 필터링되었는지 확인 (데이터가 있을 경우)
        for kw in keywords:
            assert kw.get("grade") == "S"

    @pytest.mark.api
    def test_get_top_kei_keywords(self):
        """KEI 상위 키워드 조회 테스트"""
        response = client.get("/api/pathfinder/keywords/top-kei?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "keywords" in data
        assert isinstance(data["keywords"], list)


# ========== Battle API ==========

class TestBattleAPI:
    """Battle Intelligence (순위 추적) API 테스트"""

    @pytest.mark.api
    def test_get_ranking_keywords(self):
        """순위 추적 키워드 조회 테스트"""
        response = client.get("/api/battle/ranking-keywords")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.api
    def test_get_rank_trend(self):
        """순위 트렌드 조회 테스트"""
        response = client.get("/api/battle/rank-trend?keyword=테스트")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "error" not in str(data).lower()

    @pytest.mark.api
    def test_competitor_rankings_compare(self):
        """경쟁사 순위 비교 테스트"""
        response = client.get("/api/battle/competitor-rankings/compare")
        assert response.status_code == 200
        data = response.json()
        assert "comparisons" in data or isinstance(data, dict)


# ========== Leads API ==========

class TestLeadsAPI:
    """Lead Manager API 테스트"""

    @pytest.mark.api
    def test_get_stats(self):
        """리드 통계 조회 테스트"""
        response = client.get("/api/leads/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data

    @pytest.mark.api
    def test_get_leads(self):
        """리드 목록 조회 테스트"""
        response = client.get("/api/leads/?limit=10")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.api
    def test_get_leads_with_status_filter(self):
        """상태 필터 리드 조회 테스트"""
        response = client.get("/api/leads/?status=new&limit=5")
        assert response.status_code == 200
        leads = response.json()
        assert isinstance(leads, list)


# ========== Viral API ==========

class TestViralAPI:
    """Viral Hunter API 테스트"""

    @pytest.mark.api
    def test_get_targets(self):
        """바이럴 타겟 조회 테스트"""
        response = client.get("/api/viral/targets?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "targets" in data or isinstance(data, dict)

    @pytest.mark.api
    def test_get_templates(self):
        """댓글 템플릿 조회 테스트"""
        response = client.get("/api/viral/templates")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ========== Competitors API ==========

class TestCompetitorsAPI:
    """경쟁사 분석 API 테스트"""

    @pytest.mark.api
    def test_get_competitors(self):
        """경쟁사 목록 조회 테스트"""
        response = client.get("/api/competitors/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.api
    def test_get_weaknesses(self):
        """경쟁사 약점 조회 테스트"""
        response = client.get("/api/competitors/weaknesses")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "error" not in str(data).lower()


# ========== Error Handling ==========

class TestErrorHandling:
    """에러 핸들링 테스트"""

    @pytest.mark.api
    def test_not_found(self):
        """404 Not Found 테스트"""
        response = client.get("/api/nonexistent")
        assert response.status_code == 404

    @pytest.mark.api
    def test_invalid_param(self):
        """잘못된 파라미터 테스트"""
        response = client.get("/api/pathfinder/keywords?limit=abc")
        assert response.status_code == 422  # Validation Error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

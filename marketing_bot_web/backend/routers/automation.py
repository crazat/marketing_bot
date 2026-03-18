"""
Automation API Router
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase C] 자동화 확장 API
- 리드 자동 분류
- 바이럴 타겟 추천
- 경쟁사 대응
- 일일 브리핑
"""

from fastapi import APIRouter, Query
from typing import Dict, Any, Optional
import logging

from services.automation import (
    get_marketing_automation,
    LeadAutoClassifier,
    ViralTargetRecommender,
    CompetitorResponseAutomation,
    DailyBriefingGenerator
)
from schemas.response import success_response, error_response
from backend_utils.error_handlers import handle_exceptions

logger = logging.getLogger(__name__)
router = APIRouter(tags=["automation"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# C-1: 리드 자동 분류 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/leads/classify")
async def classify_leads():
    """
    신규 리드 자동 분류 실행

    - Hot/Warm 리드 감지
    - 자동 점수 계산
    - 알림 생성
    """
    try:
        classifier = LeadAutoClassifier()
        results = classifier.classify_new_leads()
        return success_response(results, f"{results['total_processed']}개 리드 분류 완료")
    except Exception as e:
        logger.error(f"[Automation API] 리드 분류 오류: {e}")
        return error_response(str(e))


@router.get("/leads/priority-queue")
async def get_priority_queue(
    limit: int = Query(default=20, ge=1, le=100, description="조회할 리드 수")
):
    """
    우선순위 리드 큐 조회

    Args:
        limit: 조회할 리드 수 (기본 20, 최대 100)
    """
    try:
        classifier = LeadAutoClassifier()
        queue = classifier.get_priority_queue(limit)
        return success_response({
            'queue': queue,
            'total': len(queue)
        })
    except Exception as e:
        logger.error(f"[Automation API] 우선순위 큐 조회 오류: {e}")
        return error_response(str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# C-2: 바이럴 타겟 추천 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/viral/recommended-targets")
async def get_recommended_viral_targets(
    limit: int = Query(default=10, ge=1, le=50, description="조회할 타겟 수")
):
    """
    추천 바이럴 타겟 조회

    Args:
        limit: 조회할 타겟 수 (기본 10, 최대 50)
    """
    try:
        recommender = ViralTargetRecommender()
        targets = recommender.get_recommended_targets(limit)
        return success_response({
            'targets': targets,
            'total': len(targets)
        })
    except Exception as e:
        logger.error(f"[Automation API] 바이럴 타겟 추천 오류: {e}")
        return error_response(str(e))


@router.get("/viral/keyword-opportunities")
async def get_keyword_opportunities():
    """
    키워드 기반 바이럴 기회 분석

    - 순위 방어 필요 키워드
    - 모멘텀 유지 필요 키워드
    """
    try:
        recommender = ViralTargetRecommender()
        opportunities = recommender.get_keyword_opportunities()
        return success_response({
            'opportunities': opportunities,
            'total': len(opportunities)
        })
    except Exception as e:
        logger.error(f"[Automation API] 키워드 기회 분석 오류: {e}")
        return error_response(str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# C-3: 경쟁사 대응 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/competitors/threats")
async def get_competitor_threats():
    """
    경쟁사 위협 분석

    - 순위 급상승 경쟁사 감지
    - 대응 전략 자동 생성
    """
    try:
        competitor_response = CompetitorResponseAutomation()
        threats = competitor_response.analyze_competitor_threats()
        return success_response({
            'threats': threats,
            'total': len(threats),
            'critical_count': sum(1 for t in threats if t.get('threat_level') == 'critical')
        })
    except Exception as e:
        logger.error(f"[Automation API] 경쟁사 위협 분석 오류: {e}")
        return error_response(str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# C-4: 일일 브리핑 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/briefing/generate")
async def generate_briefing():
    """
    일일 브리핑 생성

    - 순위 변동 요약
    - 리드 현황 요약
    - 경쟁사 동향
    - AI 추천 액션
    """
    try:
        generator = DailyBriefingGenerator()
        briefing = generator.generate_briefing()
        return success_response(briefing, "일일 브리핑 생성 완료")
    except Exception as e:
        logger.error(f"[Automation API] 브리핑 생성 오류: {e}")
        return error_response(str(e))


@router.get("/briefing/latest")
async def get_latest_briefing():
    """
    최신 일일 브리핑 조회
    """
    try:
        generator = DailyBriefingGenerator()
        briefing = generator.get_latest_briefing()
        if briefing:
            return success_response(briefing)
        else:
            return success_response({'message': '브리핑이 아직 생성되지 않았습니다.'})
    except Exception as e:
        logger.error(f"[Automation API] 브리핑 조회 오류: {e}")
        return error_response(str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 통합 자동화 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/run-daily")
async def run_daily_automation():
    """
    일일 자동화 작업 전체 실행

    - 리드 자동 분류
    - 경쟁사 위협 분석
    - 일일 브리핑 생성
    """
    try:
        automation = get_marketing_automation()
        results = automation.run_daily_automation()

        summary = {
            'leads_processed': results.get('lead_classification', {}).get('total_processed', 0),
            'hot_leads_found': len(results.get('lead_classification', {}).get('hot_leads', [])),
            'threats_detected': len(results.get('competitor_analysis', [])),
            'briefing_generated': results.get('briefing') is not None,
            'errors': results.get('errors', [])
        }

        return success_response(summary, "일일 자동화 작업 완료")
    except Exception as e:
        logger.error(f"[Automation API] 일일 자동화 오류: {e}")
        return error_response(str(e))


@router.get("/status")
async def get_automation_status():
    """
    자동화 시스템 상태 조회
    """
    try:
        from services.automation import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()

        status = {
            'lead_classification': {
                'enabled': True,
                'last_run': None,
                'pending_leads': 0
            },
            'viral_recommendation': {
                'enabled': True,
                'pending_targets': 0
            },
            'competitor_monitoring': {
                'enabled': True,
                'active_threats': 0
            },
            'daily_briefing': {
                'enabled': True,
                'last_generated': None
            }
        }

        # 대기 중 리드 수
        cursor.execute("SELECT COUNT(*) FROM mentions WHERE status IN ('New', 'pending')")
        status['lead_classification']['pending_leads'] = cursor.fetchone()[0] or 0

        # 대기 중 바이럴 타겟 수
        cursor.execute("SELECT COUNT(*) FROM viral_targets WHERE comment_status IS NULL OR comment_status = 'pending'")
        status['viral_recommendation']['pending_targets'] = cursor.fetchone()[0] or 0

        # 최근 브리핑 시간
        cursor.execute("SELECT generated_at FROM daily_briefings ORDER BY generated_at DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            status['daily_briefing']['last_generated'] = row[0]

        conn.close()

        return success_response(status)
    except Exception as e:
        logger.error(f"[Automation API] 상태 조회 오류: {e}")
        return error_response(str(e))

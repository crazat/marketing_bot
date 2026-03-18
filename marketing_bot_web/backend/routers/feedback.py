"""
Feedback API Router
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase D] 피드백 루프 API
- 성과 피드백 분석
- 예측 정확도 검증
- ROI 추적
- 성과 리포트
"""

from fastapi import APIRouter
from typing import Dict, Any, Optional
import logging

from services.feedback import (
    get_feedback_system,
    PerformanceFeedbackLoop,
    PredictionAccuracyValidator,
    KeywordROITracker,
    PerformanceReportGenerator
)
from schemas.response import success_response, error_response
from backend_utils.error_handlers import handle_exceptions

logger = logging.getLogger(__name__)
router = APIRouter(tags=["feedback"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# D-1: 성과 피드백 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/conversion-analysis")
async def analyze_conversions():
    """
    전환 특성 분석

    - 플랫폼별 전환율
    - 점수 구간별 전환율
    - 전환까지 소요 시간
    - 가중치 조정 제안
    """
    try:
        feedback = PerformanceFeedbackLoop()
        analysis = feedback.analyze_conversion_characteristics()
        return success_response(analysis, "전환 특성 분석 완료")
    except Exception as e:
        logger.error(f"[Feedback API] 전환 분석 오류: {e}")
        return error_response(str(e))


@router.get("/weight-adjustments")
async def get_weight_adjustments():
    """
    스코어링 가중치 조정 제안 조회
    """
    try:
        feedback = PerformanceFeedbackLoop()
        analysis = feedback.analyze_conversion_characteristics()
        return success_response({
            'adjustments': analysis.get('recommended_adjustments', []),
            'total': len(analysis.get('recommended_adjustments', []))
        })
    except Exception as e:
        logger.error(f"[Feedback API] 가중치 조정 조회 오류: {e}")
        return error_response(str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# D-2: 예측 정확도 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/validate-predictions")
async def validate_predictions():
    """
    예측 정확도 검증 실행

    - 순위 예측 정확도 검증
    - 신뢰도별/트렌드별 정확도 분석
    - 개선 추천
    """
    try:
        validator = PredictionAccuracyValidator()
        result = validator.validate_rank_predictions()
        return success_response(result, "예측 정확도 검증 완료")
    except Exception as e:
        logger.error(f"[Feedback API] 정확도 검증 오류: {e}")
        return error_response(str(e))


@router.get("/prediction-accuracy")
async def get_prediction_accuracy():
    """
    최근 예측 정확도 조회
    """
    try:
        validator = PredictionAccuracyValidator()
        result = validator.validate_rank_predictions()
        summary = {
            'overall_accuracy': result.get('overall_accuracy', 0),
            'verified_count': result.get('verified_predictions', 0),
            'accurate_count': result.get('accurate_predictions', 0),
            'by_confidence': result.get('accuracy_by_confidence', {}),
            'recommendations': result.get('recommendations', [])
        }
        return success_response(summary)
    except Exception as e:
        logger.error(f"[Feedback API] 정확도 조회 오류: {e}")
        return error_response(str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# D-3: ROI 추적 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/roi")
async def get_keyword_roi(period_days: int = 30):
    """
    키워드별 ROI 분석

    Args:
        period_days: 분석 기간 (기본 30일)
    """
    try:
        tracker = KeywordROITracker()
        result = tracker.calculate_keyword_roi(period_days)
        return success_response(result)
    except Exception as e:
        logger.error(f"[Feedback API] ROI 분석 오류: {e}")
        return error_response(str(e))


@router.get("/roi/top-performers")
async def get_top_performers(limit: int = 10):
    """
    상위 성과 키워드 조회
    """
    try:
        tracker = KeywordROITracker()
        result = tracker.calculate_keyword_roi(30)
        return success_response({
            'top_performers': result.get('top_performers', [])[:limit],
            'summary': result.get('summary', {})
        })
    except Exception as e:
        logger.error(f"[Feedback API] 상위 성과 조회 오류: {e}")
        return error_response(str(e))


@router.get("/roi/underperformers")
async def get_underperformers():
    """
    저성과 키워드 조회 (전환 0건)
    """
    try:
        tracker = KeywordROITracker()
        result = tracker.calculate_keyword_roi(30)
        return success_response({
            'underperformers': result.get('underperformers', []),
            'total': len(result.get('underperformers', []))
        })
    except Exception as e:
        logger.error(f"[Feedback API] 저성과 조회 오류: {e}")
        return error_response(str(e))


@router.get("/roi/trends")
async def get_roi_trends(keyword: str = None):
    """
    ROI 트렌드 조회

    Args:
        keyword: 특정 키워드 (없으면 전체)
    """
    try:
        tracker = KeywordROITracker()
        result = tracker.get_roi_trends(keyword)
        return success_response(result)
    except Exception as e:
        logger.error(f"[Feedback API] ROI 트렌드 조회 오류: {e}")
        return error_response(str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# D-4: 성과 리포트 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/reports/weekly")
async def generate_weekly_report():
    """
    주간 성과 리포트 생성
    """
    try:
        generator = PerformanceReportGenerator()
        report = generator.generate_weekly_report()
        return success_response(report, "주간 리포트 생성 완료")
    except Exception as e:
        logger.error(f"[Feedback API] 주간 리포트 오류: {e}")
        return error_response(str(e))


@router.post("/reports/monthly")
async def generate_monthly_report():
    """
    월간 성과 리포트 생성
    """
    try:
        generator = PerformanceReportGenerator()
        report = generator.generate_monthly_report()
        return success_response(report, "월간 리포트 생성 완료")
    except Exception as e:
        logger.error(f"[Feedback API] 월간 리포트 오류: {e}")
        return error_response(str(e))


@router.get("/reports/latest")
async def get_latest_report(report_type: str = "weekly"):
    """
    최신 리포트 조회

    Args:
        report_type: 리포트 유형 (weekly/monthly)
    """
    try:
        generator = PerformanceReportGenerator()
        report = generator.get_latest_report(report_type)
        if report:
            return success_response(report)
        else:
            return success_response({'message': f'{report_type} 리포트가 아직 생성되지 않았습니다.'})
    except Exception as e:
        logger.error(f"[Feedback API] 리포트 조회 오류: {e}")
        return error_response(str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 통합 피드백 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/run-cycle")
async def run_feedback_cycle():
    """
    전체 피드백 사이클 실행

    - 전환 특성 분석
    - 예측 정확도 검증
    - ROI 분석
    - 주간 리포트 생성
    """
    try:
        feedback = get_feedback_system()
        results = feedback.run_full_feedback_cycle()

        summary = {
            'conversion_analysis': {
                'total_conversions': results.get('conversion_analysis', {}).get('total_conversions', 0),
                'adjustments_count': len(results.get('conversion_analysis', {}).get('recommended_adjustments', []))
            },
            'prediction_accuracy': {
                'overall': results.get('prediction_accuracy', {}).get('overall_accuracy', 0),
                'verified': results.get('prediction_accuracy', {}).get('verified_predictions', 0)
            },
            'roi_analysis': {
                'keywords_analyzed': len(results.get('roi_analysis', {}).get('keywords', [])),
                'top_performers': len(results.get('roi_analysis', {}).get('top_performers', []))
            },
            'weekly_report': {
                'generated': results.get('weekly_report') is not None,
                'highlights_count': len(results.get('weekly_report', {}).get('highlights', []))
            },
            'errors': results.get('errors', [])
        }

        return success_response(summary, "피드백 사이클 완료")
    except Exception as e:
        logger.error(f"[Feedback API] 피드백 사이클 오류: {e}")
        return error_response(str(e))


@router.get("/summary")
async def get_feedback_summary():
    """
    피드백 시스템 요약 조회
    """
    try:
        from services.feedback import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()

        summary = {
            'last_conversion_analysis': None,
            'last_accuracy_check': None,
            'last_roi_calculation': None,
            'last_weekly_report': None,
            'overall_accuracy': None,
            'total_conversions_30d': 0
        }

        # 최근 분석 일자
        cursor.execute("""
            SELECT created_at FROM feedback_analysis
            ORDER BY created_at DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            summary['last_conversion_analysis'] = row[0]

        # 최근 정확도 검증
        cursor.execute("""
            SELECT created_at, overall_accuracy FROM accuracy_reports
            ORDER BY created_at DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            summary['last_accuracy_check'] = row[0]
            summary['overall_accuracy'] = row[1]

        # 최근 ROI 계산
        cursor.execute("""
            SELECT MAX(calculated_at) FROM keyword_roi_stats
        """)
        row = cursor.fetchone()
        if row:
            summary['last_roi_calculation'] = row[0]

        # 최근 주간 리포트
        cursor.execute("""
            SELECT generated_at FROM performance_reports
            WHERE report_type = 'weekly'
            ORDER BY generated_at DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            summary['last_weekly_report'] = row[0]

        # 30일 전환 수
        cursor.execute("""
            SELECT COUNT(*) FROM lead_conversions
            WHERE converted_at >= datetime('now', '-30 days')
        """)
        summary['total_conversions_30d'] = cursor.fetchone()[0] or 0

        conn.close()

        return success_response(summary)
    except Exception as e:
        logger.error(f"[Feedback API] 요약 조회 오류: {e}")
        return error_response(str(e))

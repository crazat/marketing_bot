"""
Intelligence Data API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 9] Intelligence Enhancement - 정보 수집 고도화 데이터 조회 API

SmartPlace 통계, 리뷰 인텔리전스, 블로그/카카오 순위,
HIRA 의료기관, 경쟁사 변경 감지, 콜 추적, 상권 분석,
지오그리드, 네이버 광고 키워드, 커뮤니티 멘션 등
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
import sys
import os
from pathlib import Path
import sqlite3
import json
import logging

# Path setup - routers -> backend -> marketing_bot_web -> marketing_bot (root)
parent_dir = str(Path(__file__).parent.parent.parent.parent)
backend_dir = str(Path(__file__).parent.parent)
sys.path.insert(0, parent_dir)
sys.path.insert(0, backend_dir)

from db.database import DatabaseManager
from backend_utils.error_handlers import handle_exceptions
from backend_utils.cache import cached, invalidate_cache
from schemas.response import success_response, error_response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["intelligence"])

VALID_SMARTPLACE_METRICS = {"impressions", "clicks", "calls", "directions", "saves"}
VALID_SEVERITY_LEVELS = {"high", "medium", "low"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SmartPlace Stats
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/smartplace/stats")
@cached(ttl=120)
@handle_exceptions
async def get_smartplace_stats(
    days: int = Query(default=30, ge=1, le=365, description="조회 기간 (일)")
):
    """
    스마트플레이스 통계 조회 (기간별)

    Returns:
        일별 통계 리스트 + 요약 메트릭
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM smartplace_stats
            WHERE stat_date >= date('now', ?)
            ORDER BY stat_date DESC
        """, (f"-{days} days",))

        rows = cursor.fetchall()
        records = [dict(row) for row in rows]

        # Summary metrics
        summary = {
            "total_impressions": sum(r.get("impressions", 0) or 0 for r in records),
            "total_clicks": sum(r.get("clicks", 0) or 0 for r in records),
            "total_calls": sum(r.get("calls", 0) or 0 for r in records),
            "total_directions": sum(r.get("directions", 0) or 0 for r in records),
            "total_saves": sum(r.get("saves", 0) or 0 for r in records),
            "avg_daily_impressions": round(
                sum(r.get("impressions", 0) or 0 for r in records) / max(len(records), 1), 1
            ),
            "avg_daily_clicks": round(
                sum(r.get("clicks", 0) or 0 for r in records) / max(len(records), 1), 1
            ),
            "days_with_data": len(records),
        }

        return success_response({
            "records": records,
            "summary": summary,
            "days": days,
        })


@router.get("/smartplace/trend/{metric}")
@handle_exceptions
async def get_smartplace_trend(
    metric: str,
    days: int = Query(default=90, ge=1, le=365, description="조회 기간 (일)")
):
    """
    스마트플레이스 특정 메트릭 트렌드 조회

    Path params:
        metric: impressions | clicks | calls | directions | saves
    """
    if metric not in VALID_SMARTPLACE_METRICS:
        return error_response(
            f"유효하지 않은 메트릭입니다: {metric}. "
            f"사용 가능: {', '.join(sorted(VALID_SMARTPLACE_METRICS))}"
        )

    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # metric is validated above against a whitelist, safe for interpolation
        cursor.execute(f"""
            SELECT stat_date, {metric} as value
            FROM smartplace_stats
            WHERE stat_date >= date('now', ?)
            ORDER BY stat_date ASC
        """, (f"-{days} days",))

        rows = cursor.fetchall()
        records = [dict(row) for row in rows]

        values = [r["value"] or 0 for r in records]
        trend_summary = {
            "metric": metric,
            "min": min(values) if values else 0,
            "max": max(values) if values else 0,
            "avg": round(sum(values) / max(len(values), 1), 1),
            "latest": values[-1] if values else 0,
            "data_points": len(values),
        }

        return success_response({
            "trend": records,
            "summary": trend_summary,
            "days": days,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Review Intelligence
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/reviews/intelligence")
@handle_exceptions
async def get_review_intelligence(
    days: int = Query(default=30, ge=1, le=365, description="조회 기간 (일)"),
    competitor: Optional[str] = Query(default=None, description="경쟁사 이름 필터")
):
    """
    리뷰 인텔리전스 데이터 조회 (경쟁사별 리뷰 메타데이터 추적)

    Returns:
        경쟁사별 리뷰 인텔리전스 레코드 (트렌드 포함)
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
            SELECT *
            FROM review_intelligence
            WHERE collected_at >= datetime('now', ?)
        """
        params: list = [f"-{days} days"]

        if competitor:
            query += " AND competitor_name = ?"
            params.append(competitor)

        query += " ORDER BY collected_at DESC, competitor_name ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        records = [dict(row) for row in rows]

        # Parse JSON fields
        for r in records:
            for field in ("rating_distribution", "suspicious_patterns"):
                if isinstance(r.get(field), str):
                    try:
                        r[field] = json.loads(r[field])
                    except (json.JSONDecodeError, TypeError):
                        pass

        return success_response({
            "records": records,
            "total": len(records),
            "days": days,
        })


@router.get("/reviews/intelligence/summary")
@cached(ttl=300)
@handle_exceptions
async def get_review_intelligence_summary():
    """
    리뷰 인텔리전스 요약 (전체 경쟁사 집계)

    Returns:
        평균 응답률, 평균 평점, 의심스러운 리뷰 수 등
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Latest record per competitor (most recent collected_at)
        cursor.execute("""
            SELECT
                ri.competitor_name,
                ri.avg_rating,
                ri.response_rate,
                ri.suspicious_score,
                ri.total_reviews,
                ri.new_reviews_since_last,
                ri.photo_review_ratio,
                ri.collected_at
            FROM review_intelligence ri
            INNER JOIN (
                SELECT competitor_name, MAX(collected_at) as max_date
                FROM review_intelligence
                GROUP BY competitor_name
            ) latest ON ri.competitor_name = latest.competitor_name
                     AND ri.collected_at = latest.max_date
        """)

        rows = cursor.fetchall()
        competitors = [dict(row) for row in rows]

        if competitors:
            avg_response_rate = round(
                sum(c.get("response_rate", 0) or 0 for c in competitors) / len(competitors), 2
            )
            avg_rating = round(
                sum(c.get("avg_rating", 0) or 0 for c in competitors) / len(competitors), 2
            )
            total_suspicious = sum(c.get("suspicious_score", 0) or 0 for c in competitors)
        else:
            avg_response_rate = 0
            avg_rating = 0
            total_suspicious = 0

        return success_response({
            "avg_response_rate": avg_response_rate,
            "avg_rating": avg_rating,
            "total_suspicious_score": total_suspicious,
            "competitor_count": len(competitors),
            "competitors": competitors,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Blog Rankings
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/blog/rankings")
@handle_exceptions
async def get_blog_rankings(
    days: int = Query(default=30, ge=1, le=365, description="조회 기간 (일)"),
    keyword: Optional[str] = Query(default=None, description="키워드 필터")
):
    """
    블로그 VIEW 탭 순위 이력 조회

    Returns:
        블로그 순위 레코드 리스트
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
            SELECT *
            FROM blog_rank_history
            WHERE tracked_at >= datetime('now', ?)
        """
        params: list = [f"-{days} days"]

        if keyword:
            query += " AND keyword = ?"
            params.append(keyword)

        query += " ORDER BY tracked_at DESC, keyword ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        records = [dict(row) for row in rows]

        return success_response({
            "records": records,
            "total": len(records),
            "days": days,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HIRA Clinics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/hira/clinics")
@handle_exceptions
async def get_hira_clinics(
    sigungu: str = Query(default="청주", description="시군구 필터"),
    category: str = Query(default="한의원", description="의료기관 카테고리")
):
    """
    HIRA 건강보험심사평가원 의료기관 데이터 조회

    Returns:
        의료기관 목록 (주소, 전화, 의사수, 전문과목 등)
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM hira_clinics
            WHERE sigungu LIKE ? AND category = ?
            ORDER BY name ASC
        """, (f"%{sigungu}%", category))

        rows = cursor.fetchall()
        records = [dict(row) for row in rows]

        # Parse JSON fields
        for r in records:
            if isinstance(r.get("specialty"), str):
                try:
                    r["specialty"] = json.loads(r["specialty"])
                except (json.JSONDecodeError, TypeError):
                    pass

        return success_response({
            "clinics": records,
            "total": len(records),
            "sigungu": sigungu,
            "category": category,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Medical Platform Reviews
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/medical-reviews")
@handle_exceptions
async def get_medical_platform_reviews(
    platform: Optional[str] = Query(default=None, description="플랫폼 필터 (modoodoc, goodoc 등)"),
    clinic_name: Optional[str] = Query(default=None, description="병원명 필터"),
    days: int = Query(default=30, ge=1, le=365, description="조회 기간 (일)")
):
    """
    의료 리뷰 플랫폼 데이터 조회 (모두닥, 굿닥, 강남언니 등)

    Returns:
        리뷰 리스트
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
            SELECT *
            FROM medical_platform_reviews
            WHERE scanned_at >= datetime('now', ?)
        """
        params: list = [f"-{days} days"]

        if platform:
            query += " AND platform = ?"
            params.append(platform)

        if clinic_name:
            query += " AND clinic_name LIKE ?"
            params.append(f"%{clinic_name}%")

        query += " ORDER BY scanned_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        records = [dict(row) for row in rows]

        return success_response({
            "reviews": records,
            "total": len(records),
            "days": days,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Competitor Changes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/competitor-changes")
@handle_exceptions
async def get_competitor_changes(
    days: int = Query(default=30, ge=1, le=365, description="조회 기간 (일)"),
    severity: Optional[str] = Query(default=None, description="심각도 필터 (high/medium/low)")
):
    """
    경쟁사 변경 감지 이력 조회

    Returns:
        변경 사항 리스트 (최신순)
    """
    if severity and severity not in VALID_SEVERITY_LEVELS:
        return error_response(
            f"유효하지 않은 심각도입니다: {severity}. "
            f"사용 가능: {', '.join(sorted(VALID_SEVERITY_LEVELS))}"
        )

    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
            SELECT *
            FROM competitor_changes
            WHERE detected_at >= datetime('now', ?)
        """
        params: list = [f"-{days} days"]

        if severity:
            query += " AND severity = ?"
            params.append(severity)

        query += " ORDER BY detected_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        records = [dict(row) for row in rows]

        return success_response({
            "changes": records,
            "total": len(records),
            "days": days,
            "unnotified": sum(1 for r in records if not r.get("notified")),
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KakaoMap Rankings
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/kakao/rankings")
@handle_exceptions
async def get_kakao_rankings(
    days: int = Query(default=30, ge=1, le=365, description="조회 기간 (일)"),
    keyword: Optional[str] = Query(default=None, description="키워드 필터")
):
    """
    카카오맵 순위 이력 조회

    Returns:
        순위 레코드 리스트
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
            SELECT *
            FROM kakao_rank_history
            WHERE scanned_at >= datetime('now', ?)
        """
        params: list = [f"-{days} days"]

        if keyword:
            query += " AND keyword = ?"
            params.append(keyword)

        query += " ORDER BY scanned_at DESC, keyword ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        records = [dict(row) for row in rows]

        return success_response({
            "records": records,
            "total": len(records),
            "days": days,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Call Tracking
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/call-tracking")
@handle_exceptions
async def get_call_tracking(
    days: int = Query(default=30, ge=1, le=365, description="조회 기간 (일)")
):
    """
    전화/전환 추적 데이터 조회

    Returns:
        일별 콜 데이터 + 요약 (총 콜수, 일평균, 예약 전환율)
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM call_tracking
            WHERE stat_date >= date('now', ?)
            ORDER BY stat_date DESC
        """, (f"-{days} days",))

        rows = cursor.fetchall()
        records = [dict(row) for row in rows]

        total_calls = sum(r.get("total_calls", 0) or 0 for r in records)
        days_with_data = len(records)

        summary = {
            "total_calls": total_calls,
            "avg_calls_per_day": round(total_calls / max(days_with_data, 1), 1),
            "total_naver_search_calls": sum(r.get("naver_search_calls", 0) or 0 for r in records),
            "avg_call_duration": round(
                sum(r.get("duration_seconds", 0) or 0 for r in records) / max(days_with_data, 1), 0
            ),
            "days_with_data": days_with_data,
        }

        return success_response({
            "records": records,
            "summary": summary,
            "days": days,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Commercial District
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/commercial/data")
@handle_exceptions
async def get_commercial_district_data():
    """
    소상공인 상권 분석 데이터 조회

    Returns:
        상권 데이터 + 경쟁 지수
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM commercial_district_data
            ORDER BY created_at DESC
        """)

        rows = cursor.fetchall()
        records = [dict(row) for row in rows]

        return success_response({
            "districts": records,
            "total": len(records),
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Geo Grid
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/geo-grid/latest")
@handle_exceptions
async def get_geo_grid_latest(
    keyword: Optional[str] = Query(default=None, description="키워드 필터")
):
    """
    최신 지오그리드 스캔 결과 조회

    Returns:
        그리드 포인트 (위경도 + 순위) + ARP (Average Ranking Position)
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Find the latest scan session
        session_query = """
            SELECT scan_session_id, keyword, scanned_at
            FROM geo_grid_rankings
        """
        session_params: list = []

        if keyword:
            session_query += " WHERE keyword = ?"
            session_params.append(keyword)

        session_query += " ORDER BY scanned_at DESC LIMIT 1"

        cursor.execute(session_query, session_params)
        latest = cursor.fetchone()

        if not latest:
            return success_response({
                "points": [],
                "session_id": None,
                "keyword": keyword,
                "arp": None,
                "scanned_at": None,
            })

        session_id = latest["scan_session_id"]

        # Fetch all grid points for that session
        cursor.execute("""
            SELECT *
            FROM geo_grid_rankings
            WHERE scan_session_id = ?
            ORDER BY grid_lat DESC, grid_lng ASC
        """, (session_id,))

        rows = cursor.fetchall()
        points = [dict(row) for row in rows]

        # Calculate ARP (Average Ranking Position) - only for found results
        found_ranks = [
            p["rank"] for p in points
            if p.get("status") == "found" and p.get("rank") is not None
        ]
        arp = round(sum(found_ranks) / max(len(found_ranks), 1), 1) if found_ranks else None

        return success_response({
            "points": points,
            "session_id": session_id,
            "keyword": latest["keyword"],
            "scanned_at": latest["scanned_at"],
            "arp": arp,
            "total_points": len(points),
            "found_count": len(found_ranks),
        })


@router.get("/geo-grid/sessions")
@handle_exceptions
async def get_geo_grid_sessions():
    """
    지오그리드 스캔 세션 목록

    Returns:
        세션 ID, 날짜, 키워드 목록
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                scan_session_id,
                keyword,
                scanned_at,
                COUNT(*) as point_count,
                SUM(CASE WHEN status = 'found' THEN 1 ELSE 0 END) as found_count
            FROM geo_grid_rankings
            GROUP BY scan_session_id
            ORDER BY scanned_at DESC
        """)

        rows = cursor.fetchall()
        sessions = [dict(row) for row in rows]

        return success_response({
            "sessions": sessions,
            "total": len(sessions),
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Naver Ad Keywords
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/naver-ads/keywords")
@handle_exceptions
async def get_naver_ad_keywords(
    keyword: Optional[str] = Query(default=None, description="키워드 필터"),
    days: int = Query(default=30, ge=1, le=365, description="조회 기간 (일)")
):
    """
    네이버 광고 API 키워드 데이터 조회

    Returns:
        키워드 메트릭 (검색량, CTR, 경쟁도)
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
            SELECT *
            FROM naver_ad_keyword_data
            WHERE collected_date >= date('now', ?)
        """
        params: list = [f"-{days} days"]

        if keyword:
            query += " AND keyword LIKE ?"
            params.append(f"%{keyword}%")

        query += " ORDER BY collected_date DESC, keyword ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        records = [dict(row) for row in rows]

        return success_response({
            "keywords": records,
            "total": len(records),
            "days": days,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Community Mentions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/community/mentions")
@handle_exceptions
async def get_community_mentions(
    platform: Optional[str] = Query(default=None, description="플랫폼 필터 (daangn, openchat 등)"),
    days: int = Query(default=30, ge=1, le=365, description="조회 기간 (일)"),
    is_lead: Optional[bool] = Query(default=None, description="리드 후보만 필터")
):
    """
    커뮤니티 멘션 데이터 조회

    Returns:
        멘션 리스트 (리드 후보 포함)
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
            SELECT *
            FROM community_mentions
            WHERE scanned_at >= datetime('now', ?)
        """
        params: list = [f"-{days} days"]

        if platform:
            query += " AND platform = ?"
            params.append(platform)

        if is_lead is not None:
            query += " AND is_lead_candidate = ?"
            params.append(1 if is_lead else 0)

        query += " ORDER BY scanned_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        records = [dict(row) for row in rows]

        return success_response({
            "mentions": records,
            "total": len(records),
            "lead_candidates": sum(1 for r in records if r.get("is_lead_candidate")),
            "days": days,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dashboard Summary (combined intelligence)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/behavior/trend")
@cached(ttl=300)
@handle_exceptions
async def get_behavior_trend(
    days: int = Query(default=30, ge=7, le=365, description="조회 기간 (일)")
):
    """
    [고도화 B-3] 네이버 플레이스 행동 데이터 트렌드

    smartplace_stats 테이블에서 전화/길찾기/예약/저장 클릭 트렌드 조회.
    네이버 플레이스 4대 지표(적합도/인기도/최신성/신뢰성)의 '인기도' 산출 근거.

    Returns:
        - daily: 일별 행동 데이터
        - summary: 기간 합계 및 증감률
        - scores: 인기도/최신성 점수
    """
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # smartplace_stats에서 행동 데이터 조회
        cursor.execute("""
            SELECT
                date,
                COALESCE(total_views, 0) as total_views,
                COALESCE(place_views, 0) as place_views,
                COALESCE(search_views, 0) as search_views,
                COALESCE(phone_clicks, 0) as phone_clicks,
                COALESCE(direction_clicks, 0) as direction_clicks,
                COALESCE(save_clicks, 0) as save_clicks,
                COALESCE(share_clicks, 0) as share_clicks,
                COALESCE(review_clicks, 0) as review_clicks,
                COALESCE(website_clicks, 0) as website_clicks,
                COALESCE(booking_clicks, 0) as booking_clicks
            FROM smartplace_stats
            WHERE date >= date('now', ? || ' days')
            ORDER BY date ASC
        """, (f"-{days}",))

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return success_response({
                "daily": [],
                "summary": {},
                "scores": {"popularity": 0, "freshness": 0},
                "message": "SmartPlace 통계 데이터가 없습니다. CSV 임포트가 필요합니다."
            })

        daily = [dict(row) for row in rows]

        # 기간 합계
        total_phone = sum(r['phone_clicks'] for r in daily)
        total_direction = sum(r['direction_clicks'] for r in daily)
        total_booking = sum(r['booking_clicks'] for r in daily)
        total_save = sum(r['save_clicks'] for r in daily)
        total_views = sum(r['total_views'] for r in daily)

        # 전반기/후반기 비교 (증감률)
        mid = len(daily) // 2
        if mid > 0:
            first_half_actions = sum(
                r['phone_clicks'] + r['direction_clicks'] + r['booking_clicks'] + r['save_clicks']
                for r in daily[:mid]
            )
            second_half_actions = sum(
                r['phone_clicks'] + r['direction_clicks'] + r['booking_clicks'] + r['save_clicks']
                for r in daily[mid:]
            )
            growth_rate = round(
                ((second_half_actions - first_half_actions) / max(first_half_actions, 1)) * 100, 1
            )
        else:
            growth_rate = 0

        # 인기도 점수 (행동 클릭의 총 조회 대비 비율 × 100)
        total_actions = total_phone + total_direction + total_booking + total_save
        popularity_score = round(
            (total_actions / max(total_views, 1)) * 100, 1
        )

        # 최신성 점수 (최근 7일 업데이트 빈도)
        recent_7d = [r for r in daily if r['date'] >= daily[-1]['date'][:8] + '01'][-7:] if daily else []
        freshness_score = min(round(len(recent_7d) / 7 * 100, 1), 100)

        return success_response({
            "daily": daily,
            "summary": {
                "total_views": total_views,
                "total_phone": total_phone,
                "total_direction": total_direction,
                "total_booking": total_booking,
                "total_save": total_save,
                "total_actions": total_actions,
                "growth_rate": growth_rate,
                "days": len(daily),
            },
            "scores": {
                "popularity": min(popularity_score, 100),
                "freshness": freshness_score,
            }
        })

    except Exception as e:
        logger.error(f"behavior-trend 오류: {str(e)}", exc_info=True)
        return error_response(f"행동 데이터 조회 실패: {str(e)}", status_code=500)


@router.get("/weather/triggers")
@cached(ttl=1800)
@handle_exceptions
async def get_weather_triggers():
    """
    [고도화 V2-1] 현재 날씨 기반 마케팅 트리거

    기온/미세먼지/습도 등을 분석하여 자동 발동되는 마케팅 트리거 반환.
    각 트리거에 추천 키워드, 콘텐츠 주제, 타겟 고객층 포함.
    """
    try:
        from services.weather_trigger import check_weather_triggers

        db = DatabaseManager()
        result = await check_weather_triggers(db.db_path)

        if "error" in result:
            return success_response(result)

        return success_response(result)

    except Exception as e:
        logger.error(f"weather-triggers 오류: {e}", exc_info=True)
        return error_response(f"날씨 트리거 조회 실패: {str(e)}", status_code=500)


@router.get("/dashboard")
@handle_exceptions
async def get_intelligence_dashboard():
    """
    통합 인텔리전스 대시보드 데이터 (단일 호출)

    Returns:
        smartplace_latest, review_alerts, competitor_changes_count,
        blog_rank_summary, kakao_rank_summary, call_trend,
        new_community_leads
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        dashboard: Dict[str, Any] = {}

        # 1. SmartPlace Latest (most recent stats)
        try:
            cursor.execute("""
                SELECT * FROM smartplace_stats
                ORDER BY stat_date DESC LIMIT 1
            """)
            row = cursor.fetchone()
            dashboard["smartplace_latest"] = dict(row) if row else None
        except Exception:
            dashboard["smartplace_latest"] = None

        # 2. Review Alerts (suspicious scores or rating drops)
        try:
            cursor.execute("""
                SELECT
                    ri.competitor_name,
                    ri.avg_rating,
                    ri.suspicious_score,
                    ri.response_rate,
                    ri.collected_at
                FROM review_intelligence ri
                INNER JOIN (
                    SELECT competitor_name, MAX(collected_at) as max_date
                    FROM review_intelligence
                    GROUP BY competitor_name
                ) latest ON ri.competitor_name = latest.competitor_name
                         AND ri.collected_at = latest.max_date
                WHERE ri.suspicious_score > 0
                   OR ri.avg_rating < 3.5
                ORDER BY ri.suspicious_score DESC
            """)
            rows = cursor.fetchall()
            dashboard["review_alerts"] = [dict(row) for row in rows]
        except Exception:
            dashboard["review_alerts"] = []

        # 3. Competitor Changes Count (unnotified)
        try:
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM competitor_changes
                WHERE notified = 0
            """)
            row = cursor.fetchone()
            dashboard["competitor_changes_count"] = row["count"] if row else 0
        except Exception:
            dashboard["competitor_changes_count"] = 0

        # 4. Blog Rank Summary (keywords found / not found)
        try:
            cursor.execute("""
                SELECT
                    COUNT(DISTINCT keyword) as total_keywords,
                    COUNT(DISTINCT CASE WHEN found = 1 THEN keyword END) as ranked_keywords
                FROM blog_rank_history
                WHERE DATE(tracked_at) = (
                    SELECT DATE(MAX(tracked_at)) FROM blog_rank_history
                )
            """)
            row = cursor.fetchone()
            if row:
                dashboard["blog_rank_summary"] = {
                    "total_keywords": row["total_keywords"] or 0,
                    "ranked_keywords": row["ranked_keywords"] or 0,
                    "not_ranked": (row["total_keywords"] or 0) - (row["ranked_keywords"] or 0),
                }
            else:
                dashboard["blog_rank_summary"] = {
                    "total_keywords": 0, "ranked_keywords": 0, "not_ranked": 0
                }
        except Exception:
            dashboard["blog_rank_summary"] = {
                "total_keywords": 0, "ranked_keywords": 0, "not_ranked": 0
            }

        # 5. Kakao Rank Summary
        try:
            cursor.execute("""
                SELECT
                    COUNT(DISTINCT keyword) as total_keywords,
                    COUNT(DISTINCT CASE WHEN status = 'found' THEN keyword END) as ranked_keywords
                FROM kakao_rank_history
                WHERE DATE(scanned_at) = (
                    SELECT DATE(MAX(scanned_at)) FROM kakao_rank_history
                )
            """)
            row = cursor.fetchone()
            if row:
                dashboard["kakao_rank_summary"] = {
                    "total_keywords": row["total_keywords"] or 0,
                    "ranked_keywords": row["ranked_keywords"] or 0,
                    "not_ranked": (row["total_keywords"] or 0) - (row["ranked_keywords"] or 0),
                }
            else:
                dashboard["kakao_rank_summary"] = {
                    "total_keywords": 0, "ranked_keywords": 0, "not_ranked": 0
                }
        except Exception:
            dashboard["kakao_rank_summary"] = {
                "total_keywords": 0, "ranked_keywords": 0, "not_ranked": 0
            }

        # 6. Call Trend (last 7 days)
        try:
            cursor.execute("""
                SELECT stat_date, total_calls, naver_search_calls
                FROM call_tracking
                WHERE stat_date >= date('now', '-7 days')
                ORDER BY stat_date ASC
            """)
            rows = cursor.fetchall()
            dashboard["call_trend"] = [dict(row) for row in rows]
        except Exception:
            dashboard["call_trend"] = []

        # 7. New Community Leads (last 7 days lead candidates)
        try:
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM community_mentions
                WHERE is_lead_candidate = 1
                  AND scanned_at >= datetime('now', '-7 days')
            """)
            row = cursor.fetchone()
            dashboard["new_community_leads"] = row["count"] if row else 0
        except Exception:
            dashboard["new_community_leads"] = 0

        return success_response(dashboard)

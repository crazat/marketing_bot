"""
AI Intelligence API (Phase B)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AI 기반 지능화 - 전환 패턴, 댓글 효과, 순위 예측, 타이밍 분석

엔드포인트:
- GET  /insights                          대시보드 인사이트
- POST /analyze                           전체 AI 분석 실행
- GET  /conversion-patterns               전환 패턴 조회
- POST /conversion-patterns/learn         전환 패턴 학습
- POST /conversion-patterns/predict       전환 확률 예측
- GET  /comment-effectiveness             댓글 효과 분석
- POST /comment-effectiveness/analyze     댓글 효과 분석 실행
- GET  /rank-predictions                  순위 예측 조회
- GET  /rank-predictions/accuracy         예측 정확도
- GET  /timing                            타이밍 분석
- GET  /timing/now                        현재 시점 추천
- POST /timing/analyze                    타이밍 분석 실행
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import sys
import os
from pathlib import Path
import sqlite3
import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict

# Path setup - routers -> backend -> marketing_bot_web -> marketing_bot (root)
parent_dir = str(Path(__file__).parent.parent.parent.parent)
backend_dir = str(Path(__file__).parent.parent)
sys.path.insert(0, parent_dir)
sys.path.insert(0, backend_dir)

from db.database import DatabaseManager
from backend_utils.error_handlers import handle_exceptions
from schemas.response import success_response, error_response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Intelligence"])

# Day-of-week names (Korean)
DAY_NAMES = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Request Models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ConversionPredictRequest(BaseModel):
    platform: Optional[str] = None
    keyword: Optional[str] = None
    score: Optional[float] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helper: safe DB query
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _safe_query(conn, query: str, params: tuple = (), fetch_one: bool = False):
    """Execute a query safely, returning empty list/None on error."""
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetch_one:
            return cursor.fetchone()
        return cursor.fetchall()
    except Exception as e:
        logger.warning(f"Query failed (graceful fallback): {e}")
        return None if fetch_one else []


def _table_exists(conn, table_name: str) -> bool:
    """Check if a table exists in the database."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return cursor.fetchone() is not None
    except Exception:
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. GET /insights - Dashboard Insights
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/insights")
@handle_exceptions
async def get_insights():
    """
    대시보드 인사이트 조회

    Returns:
        platform_conversion_rates, high_performing_keywords,
        rank_warnings, timing_recommendations
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row

        # 1. Platform conversion rates from lead_conversions
        platform_conversion_rates: Dict[str, float] = {}
        try:
            rows = _safe_query(conn, """
                SELECT platform, COUNT(*) as total,
                       SUM(CASE WHEN revenue > 0 THEN 1 ELSE 0 END) as converted
                FROM lead_conversions
                WHERE platform IS NOT NULL
                GROUP BY platform
            """)
            for row in rows:
                r = dict(row)
                total = r.get("total", 0) or 0
                converted = r.get("converted", 0) or 0
                if total > 0:
                    platform_conversion_rates[r["platform"]] = round(converted / total * 100, 1)
        except Exception as e:
            logger.warning(f"Platform conversion rates query failed: {e}")

        # Also try conversion_patterns table for platform patterns
        if not platform_conversion_rates:
            try:
                rows = _safe_query(conn, """
                    SELECT pattern_key, conversion_rate
                    FROM conversion_patterns
                    WHERE pattern_type = 'platform'
                """)
                for row in rows:
                    r = dict(row)
                    platform_conversion_rates[r["pattern_key"]] = round(
                        (r.get("conversion_rate", 0) or 0) * 100, 1
                    )
            except Exception:
                pass

        # 2. High performing keywords from lead_conversions
        high_performing_keywords: List[Dict[str, Any]] = []
        try:
            rows = _safe_query(conn, """
                SELECT keyword,
                       COUNT(*) as leads,
                       SUM(CASE WHEN revenue > 0 THEN 1 ELSE 0 END) as conversions
                FROM lead_conversions
                WHERE keyword IS NOT NULL AND keyword != ''
                GROUP BY keyword
                ORDER BY conversions DESC, leads DESC
                LIMIT 10
            """)
            for row in rows:
                r = dict(row)
                leads = r.get("leads", 0) or 0
                conversions = r.get("conversions", 0) or 0
                rate = round(conversions / leads * 100, 1) if leads > 0 else 0.0
                high_performing_keywords.append({
                    "keyword": r["keyword"],
                    "conversion_rate": rate,
                    "leads": leads,
                })
        except Exception as e:
            logger.warning(f"High performing keywords query failed: {e}")

        # Also try conversion_patterns for keyword patterns
        if not high_performing_keywords:
            try:
                rows = _safe_query(conn, """
                    SELECT pattern_key, conversion_rate, sample_count
                    FROM conversion_patterns
                    WHERE pattern_type = 'keyword'
                    ORDER BY conversion_rate DESC
                    LIMIT 10
                """)
                for row in rows:
                    r = dict(row)
                    high_performing_keywords.append({
                        "keyword": r["pattern_key"],
                        "conversion_rate": round((r.get("conversion_rate", 0) or 0) * 100, 1),
                        "leads": r.get("sample_count", 0) or 0,
                    })
            except Exception:
                pass

        # 3. Rank warnings from rank_history (recent trend analysis)
        rank_warnings: List[Dict[str, Any]] = []
        try:
            rows = _safe_query(conn, """
                SELECT keyword, rank, status, checked_at
                FROM rank_history
                WHERE status = 'found'
                  AND checked_at >= datetime('now', '-14 days')
                ORDER BY keyword, checked_at DESC
            """)
            if rows:
                keyword_ranks: Dict[str, List[int]] = defaultdict(list)
                for row in rows:
                    r = dict(row)
                    if r.get("rank") is not None:
                        keyword_ranks[r["keyword"]].append(r["rank"])

                for kw, ranks in keyword_ranks.items():
                    if len(ranks) < 2:
                        continue
                    current = ranks[0]
                    previous = ranks[-1]
                    diff = current - previous

                    if diff > 5:
                        warning_level = "critical" if diff > 15 else "warning"
                        rank_warnings.append({
                            "keyword": kw,
                            "current_rank": current,
                            "trend": "falling",
                            "warning_level": warning_level,
                        })
                    elif diff > 2:
                        rank_warnings.append({
                            "keyword": kw,
                            "current_rank": current,
                            "trend": "declining",
                            "warning_level": "info",
                        })

                rank_warnings.sort(
                    key=lambda x: 0 if x["warning_level"] == "critical" else 1
                )
        except Exception as e:
            logger.warning(f"Rank warnings query failed: {e}")

        # 4. Timing recommendations
        timing_recommendations: List[Dict[str, Any]] = []
        try:
            rows = _safe_query(conn, """
                SELECT category, sub_category, conversion_rate, total_count
                FROM timing_analytics
                WHERE analysis_type = 'platform_hour'
                  AND conversion_rate > 0
                ORDER BY conversion_rate DESC
                LIMIT 5
            """)
            for row in rows:
                r = dict(row)
                timing_recommendations.append({
                    "platform": r.get("category", "unknown"),
                    "recommended_action": f"{r.get('sub_category', '')}시에 활동 추천",
                    "confidence": min(round((r.get("conversion_rate", 0) or 0) * 100, 1), 100.0),
                })
        except Exception as e:
            logger.warning(f"Timing recommendations query failed: {e}")

        return success_response({
            "platform_conversion_rates": platform_conversion_rates,
            "high_performing_keywords": high_performing_keywords,
            "rank_warnings": rank_warnings,
            "timing_recommendations": timing_recommendations,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. POST /analyze - Full Analysis
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/analyze")
@handle_exceptions
async def run_full_analysis():
    """
    전체 AI 분석 실행

    conversion_patterns, comment_effectiveness, rank_predictions,
    timing_analysis를 순차적으로 실행하고 결과 요약을 반환
    """
    errors: List[str] = []
    summary: Dict[str, Any] = {
        "conversion_patterns": {
            "platform_count": 0,
            "keyword_count": 0,
            "total_leads": 0,
            "total_conversions": 0,
        },
        "comment_effectiveness": {
            "length_analysis": False,
            "style_analysis": False,
            "recommendations_count": 0,
        },
        "rank_predictions": {
            "keywords_predicted": 0,
            "rising_count": 0,
            "falling_count": 0,
        },
        "timing_analysis": {
            "recommendations_count": 0,
        },
        "errors": errors,
    }

    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row

        # 1. Conversion pattern analysis
        try:
            _analyze_conversion_patterns(conn)
            rows = _safe_query(conn, """
                SELECT pattern_type, COUNT(*) as cnt
                FROM conversion_patterns
                GROUP BY pattern_type
            """)
            for row in rows:
                r = dict(row)
                pt = r.get("pattern_type", "")
                cnt = r.get("cnt", 0) or 0
                if pt == "platform":
                    summary["conversion_patterns"]["platform_count"] = cnt
                elif pt == "keyword":
                    summary["conversion_patterns"]["keyword_count"] = cnt

            total_row = _safe_query(conn, """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN revenue > 0 THEN 1 ELSE 0 END) as converted
                FROM lead_conversions
            """, fetch_one=False)
            if total_row:
                t = dict(total_row[0]) if total_row else {}
                summary["conversion_patterns"]["total_leads"] = t.get("total", 0) or 0
                summary["conversion_patterns"]["total_conversions"] = t.get("converted", 0) or 0
        except Exception as e:
            errors.append(f"Conversion pattern analysis failed: {str(e)}")
            logger.error(f"Conversion pattern analysis error: {e}")

        # 2. Comment effectiveness analysis
        try:
            _analyze_comment_effectiveness(conn)
            rows = _safe_query(conn, """
                SELECT DISTINCT analysis_type FROM comment_effectiveness
            """)
            types_found = {dict(row).get("analysis_type", "") for row in rows}
            summary["comment_effectiveness"]["length_analysis"] = "length" in types_found
            summary["comment_effectiveness"]["style_analysis"] = "style" in types_found

            rec_count = 0
            if summary["comment_effectiveness"]["length_analysis"]:
                rec_count += 1
            if summary["comment_effectiveness"]["style_analysis"]:
                rec_count += 1
            summary["comment_effectiveness"]["recommendations_count"] = rec_count
        except Exception as e:
            errors.append(f"Comment effectiveness analysis failed: {str(e)}")
            logger.error(f"Comment effectiveness analysis error: {e}")

        # 3. Rank predictions
        try:
            _generate_rank_predictions(conn)
            rows = _safe_query(conn, """
                SELECT trend, COUNT(*) as cnt
                FROM rank_predictions
                WHERE predicted_at >= datetime('now', '-1 day')
                GROUP BY trend
            """)
            total_predicted = 0
            for row in rows:
                r = dict(row)
                cnt = r.get("cnt", 0) or 0
                total_predicted += cnt
                trend = r.get("trend", "")
                if trend == "rising":
                    summary["rank_predictions"]["rising_count"] = cnt
                elif trend == "falling":
                    summary["rank_predictions"]["falling_count"] = cnt

            if total_predicted == 0:
                # Use all predictions if none from today
                rows = _safe_query(conn, """
                    SELECT trend, COUNT(*) as cnt
                    FROM rank_predictions
                    GROUP BY trend
                """)
                for row in rows:
                    r = dict(row)
                    cnt = r.get("cnt", 0) or 0
                    total_predicted += cnt
                    trend = r.get("trend", "")
                    if trend == "rising":
                        summary["rank_predictions"]["rising_count"] = cnt
                    elif trend == "falling":
                        summary["rank_predictions"]["falling_count"] = cnt

            summary["rank_predictions"]["keywords_predicted"] = total_predicted
        except Exception as e:
            errors.append(f"Rank prediction failed: {str(e)}")
            logger.error(f"Rank prediction error: {e}")

        # 4. Timing analysis
        try:
            _analyze_timing(conn)
            rows = _safe_query(conn, """
                SELECT COUNT(*) as cnt FROM timing_analytics
                WHERE conversion_rate > 0
            """)
            if rows:
                summary["timing_analysis"]["recommendations_count"] = (
                    dict(rows[0]).get("cnt", 0) or 0
                )
        except Exception as e:
            errors.append(f"Timing analysis failed: {str(e)}")
            logger.error(f"Timing analysis error: {e}")

    return success_response(summary)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. GET /conversion-patterns
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/conversion-patterns")
@handle_exceptions
async def get_conversion_patterns():
    """
    전환 패턴 조회

    Returns:
        patterns (platform, keyword, time, score), pattern_types, total_patterns
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row

        patterns: Dict[str, Dict[str, float]] = {
            "platform_patterns": {},
            "keyword_patterns": {},
            "time_patterns": {},
            "score_patterns": {},
        }
        pattern_types: List[str] = []
        total_patterns = 0

        # From conversion_patterns table
        try:
            rows = _safe_query(conn, """
                SELECT pattern_type, pattern_key, conversion_rate, sample_count
                FROM conversion_patterns
                ORDER BY pattern_type, conversion_rate DESC
            """)
            for row in rows:
                r = dict(row)
                pt = r.get("pattern_type", "")
                key = r.get("pattern_key", "")
                rate = r.get("conversion_rate", 0) or 0

                target_key = f"{pt}_patterns"
                if target_key in patterns:
                    patterns[target_key][key] = round(rate, 4)
                    total_patterns += 1
                    if pt not in pattern_types:
                        pattern_types.append(pt)
        except Exception as e:
            logger.warning(f"Conversion patterns query failed: {e}")

        # Fallback: compute from lead_conversions if conversion_patterns is empty
        if total_patterns == 0:
            try:
                # Platform patterns
                rows = _safe_query(conn, """
                    SELECT platform, COUNT(*) as cnt,
                           SUM(CASE WHEN revenue > 0 THEN 1 ELSE 0 END) as converted
                    FROM lead_conversions
                    WHERE platform IS NOT NULL
                    GROUP BY platform
                """)
                for row in rows:
                    r = dict(row)
                    cnt = r.get("cnt", 0) or 0
                    converted = r.get("converted", 0) or 0
                    if cnt > 0:
                        patterns["platform_patterns"][r["platform"]] = round(
                            converted / cnt, 4
                        )
                        total_patterns += 1
                if patterns["platform_patterns"]:
                    pattern_types.append("platform")

                # Keyword patterns
                rows = _safe_query(conn, """
                    SELECT keyword, COUNT(*) as cnt,
                           SUM(CASE WHEN revenue > 0 THEN 1 ELSE 0 END) as converted
                    FROM lead_conversions
                    WHERE keyword IS NOT NULL AND keyword != ''
                    GROUP BY keyword
                """)
                for row in rows:
                    r = dict(row)
                    cnt = r.get("cnt", 0) or 0
                    converted = r.get("converted", 0) or 0
                    if cnt > 0:
                        patterns["keyword_patterns"][r["keyword"]] = round(
                            converted / cnt, 4
                        )
                        total_patterns += 1
                if patterns["keyword_patterns"]:
                    pattern_types.append("keyword")
            except Exception as e:
                logger.warning(f"Fallback conversion pattern computation failed: {e}")

        return success_response({
            "patterns": patterns,
            "pattern_types": pattern_types,
            "total_patterns": total_patterns,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. POST /conversion-patterns/learn
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/conversion-patterns/learn")
@handle_exceptions
async def learn_conversion_patterns():
    """
    전환 패턴 학습 실행

    lead_conversions 데이터를 분석하여 conversion_patterns 테이블 갱신
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row

        try:
            _analyze_conversion_patterns(conn)
            conn.commit()
        except Exception as e:
            logger.error(f"Conversion pattern learning failed: {e}")
            return error_response(f"패턴 학습 실패: {str(e)}")

        # Count learned patterns
        rows = _safe_query(conn, """
            SELECT COUNT(*) as cnt FROM conversion_patterns
        """)
        count = dict(rows[0]).get("cnt", 0) if rows else 0

        return success_response({
            "message": f"전환 패턴 학습 완료 ({count}개 패턴)",
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. POST /conversion-patterns/predict
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/conversion-patterns/predict")
@handle_exceptions
async def predict_conversion(request: ConversionPredictRequest):
    """
    전환 확률 예측

    platform, keyword, score를 기반으로 전환 확률 및 영향 요인 반환
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row

        factors: List[Dict[str, Any]] = []
        probability = 0.0
        weight_sum = 0.0

        # Platform factor
        if request.platform:
            try:
                row = _safe_query(conn, """
                    SELECT conversion_rate, sample_count
                    FROM conversion_patterns
                    WHERE pattern_type = 'platform' AND pattern_key = ?
                """, (request.platform,), fetch_one=True)
                if row:
                    r = dict(row)
                    rate = r.get("conversion_rate", 0) or 0
                    sample = r.get("sample_count", 0) or 0
                    weight = min(sample / 10, 1.0)  # More samples = more confidence
                    probability += rate * weight
                    weight_sum += weight
                    factors.append({
                        "factor": f"플랫폼 ({request.platform})",
                        "impact": round(rate * 100, 1),
                    })
                else:
                    factors.append({
                        "factor": f"플랫폼 ({request.platform})",
                        "impact": 0,
                    })
            except Exception:
                pass

        # Keyword factor
        if request.keyword:
            try:
                row = _safe_query(conn, """
                    SELECT conversion_rate, sample_count
                    FROM conversion_patterns
                    WHERE pattern_type = 'keyword' AND pattern_key = ?
                """, (request.keyword,), fetch_one=True)
                if row:
                    r = dict(row)
                    rate = r.get("conversion_rate", 0) or 0
                    sample = r.get("sample_count", 0) or 0
                    weight = min(sample / 10, 1.0)
                    probability += rate * weight
                    weight_sum += weight
                    factors.append({
                        "factor": f"키워드 ({request.keyword})",
                        "impact": round(rate * 100, 1),
                    })
                else:
                    factors.append({
                        "factor": f"키워드 ({request.keyword})",
                        "impact": 0,
                    })
            except Exception:
                pass

        # Score factor
        if request.score is not None:
            score_impact = min(request.score / 100, 1.0)
            weight = 0.5
            probability += score_impact * weight
            weight_sum += weight
            factors.append({
                "factor": f"우선순위 점수 ({request.score})",
                "impact": round(score_impact * 100, 1),
            })

        # Normalize probability
        if weight_sum > 0:
            probability = round(probability / weight_sum * 100, 1)
        else:
            probability = 0.0

        # Clamp to 0-100
        probability = max(0.0, min(100.0, probability))

        return success_response({
            "probability": probability,
            "factors": factors,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. GET /comment-effectiveness
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/comment-effectiveness")
@handle_exceptions
async def get_comment_effectiveness():
    """
    댓글 효과 분석 조회

    Returns:
        length_analysis, style_analysis, recommendations
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row

        length_analysis = {
            "optimal_length": 0,
            "length_distribution": {},
        }
        style_analysis = {
            "best_styles": [],
            "style_effectiveness": {},
        }
        recommendations: List[str] = []

        # Length analysis from comment_effectiveness table
        try:
            rows = _safe_query(conn, """
                SELECT category, total_count, conversion_count, conversion_rate
                FROM comment_effectiveness
                WHERE analysis_type = 'length'
                ORDER BY conversion_rate DESC
            """)
            if rows:
                best_rate = 0.0
                best_length = ""
                for row in rows:
                    r = dict(row)
                    cat = r.get("category", "")
                    rate = r.get("conversion_rate", 0) or 0
                    total = r.get("total_count", 0) or 0
                    length_analysis["length_distribution"][cat] = total
                    if rate > best_rate:
                        best_rate = rate
                        best_length = cat

                if best_length:
                    # Parse optimal length from category string (e.g., "50-100")
                    try:
                        parts = best_length.split("-")
                        if len(parts) == 2:
                            length_analysis["optimal_length"] = int(
                                (int(parts[0]) + int(parts[1])) / 2
                            )
                        else:
                            length_analysis["optimal_length"] = int(best_length)
                    except (ValueError, IndexError):
                        length_analysis["optimal_length"] = 100

                    recommendations.append(
                        f"최적 댓글 길이: {best_length}자 (전환율 {round(best_rate * 100, 1)}%)"
                    )
        except Exception as e:
            logger.warning(f"Length analysis query failed: {e}")

        # Fallback: compute from viral_targets if comment_effectiveness is empty
        if not length_analysis["length_distribution"]:
            try:
                rows = _safe_query(conn, """
                    SELECT
                        CASE
                            WHEN LENGTH(generated_comment) < 50 THEN 'short'
                            WHEN LENGTH(generated_comment) < 100 THEN 'medium'
                            WHEN LENGTH(generated_comment) < 200 THEN 'long'
                            ELSE 'very_long'
                        END as length_cat,
                        COUNT(*) as cnt,
                        SUM(CASE WHEN comment_status = 'posted' THEN 1 ELSE 0 END) as posted
                    FROM viral_targets
                    WHERE generated_comment IS NOT NULL AND generated_comment != ''
                    GROUP BY length_cat
                """)
                best_rate = 0.0
                for row in rows:
                    r = dict(row)
                    cat = r.get("length_cat", "")
                    cnt = r.get("cnt", 0) or 0
                    posted = r.get("posted", 0) or 0
                    length_analysis["length_distribution"][cat] = cnt
                    rate = posted / cnt if cnt > 0 else 0
                    if rate > best_rate:
                        best_rate = rate
                        length_analysis["optimal_length"] = {
                            "short": 25, "medium": 75, "long": 150, "very_long": 250
                        }.get(cat, 100)

                if best_rate > 0:
                    recommendations.append(
                        f"게시된 댓글 기준 최적 길이 분석 완료 (전환율 {round(best_rate * 100, 1)}%)"
                    )
            except Exception as e:
                logger.warning(f"Fallback length analysis failed: {e}")

        # Style analysis from comment_effectiveness table
        try:
            rows = _safe_query(conn, """
                SELECT category, total_count, conversion_count, conversion_rate
                FROM comment_effectiveness
                WHERE analysis_type = 'style'
                ORDER BY conversion_rate DESC
            """)
            if rows:
                for row in rows:
                    r = dict(row)
                    cat = r.get("category", "")
                    rate = r.get("conversion_rate", 0) or 0
                    style_analysis["style_effectiveness"][cat] = round(rate * 100, 1)

                # Top styles
                style_analysis["best_styles"] = [
                    dict(row).get("category", "")
                    for row in rows[:3]
                    if (dict(row).get("conversion_rate", 0) or 0) > 0
                ]

                if style_analysis["best_styles"]:
                    recommendations.append(
                        f"효과적인 댓글 스타일: {', '.join(style_analysis['best_styles'])}"
                    )
        except Exception as e:
            logger.warning(f"Style analysis query failed: {e}")

        # Fallback: compute from viral_targets by platform
        if not style_analysis["style_effectiveness"]:
            try:
                rows = _safe_query(conn, """
                    SELECT platform, COUNT(*) as cnt,
                           SUM(CASE WHEN comment_status = 'posted' THEN 1 ELSE 0 END) as posted
                    FROM viral_targets
                    WHERE generated_comment IS NOT NULL AND generated_comment != ''
                    GROUP BY platform
                    ORDER BY posted DESC
                """)
                for row in rows:
                    r = dict(row)
                    platform = r.get("platform", "unknown")
                    cnt = r.get("cnt", 0) or 0
                    posted = r.get("posted", 0) or 0
                    rate = round(posted / cnt * 100, 1) if cnt > 0 else 0.0
                    style_analysis["style_effectiveness"][platform] = rate

                best_platforms = sorted(
                    style_analysis["style_effectiveness"].items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
                style_analysis["best_styles"] = [p[0] for p in best_platforms[:3] if p[1] > 0]
            except Exception:
                pass

        if not recommendations:
            recommendations.append("데이터가 부족합니다. 더 많은 댓글 활동을 통해 효과를 분석해보세요.")

        return success_response({
            "length_analysis": length_analysis,
            "style_analysis": style_analysis,
            "recommendations": recommendations,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. POST /comment-effectiveness/analyze
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/comment-effectiveness/analyze")
@handle_exceptions
async def analyze_comment_effectiveness():
    """
    댓글 효과 분석 실행

    viral_targets 데이터를 기반으로 comment_effectiveness 테이블 갱신 후 결과 반환
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row

        try:
            _analyze_comment_effectiveness(conn)
            conn.commit()
        except Exception as e:
            logger.error(f"Comment effectiveness analysis failed: {e}")
            return error_response(f"댓글 효과 분석 실패: {str(e)}")

    # Return the updated results via the GET endpoint logic
    return await get_comment_effectiveness()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. GET /rank-predictions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/rank-predictions")
@handle_exceptions
async def get_rank_predictions(
    days_ahead: int = Query(default=7, ge=1, le=30, description="예측 일수")
):
    """
    순위 예측 조회

    Returns:
        predictions list, days_ahead, rising/falling/stable counts
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row

        predictions: List[Dict[str, Any]] = []
        rising_count = 0
        falling_count = 0
        stable_count = 0

        try:
            # Get latest predictions for requested days_ahead
            rows = _safe_query(conn, """
                SELECT rp.*
                FROM rank_predictions rp
                INNER JOIN (
                    SELECT keyword, MAX(predicted_at) as max_at
                    FROM rank_predictions
                    WHERE days_ahead = ?
                    GROUP BY keyword
                ) latest ON rp.keyword = latest.keyword
                         AND rp.predicted_at = latest.max_at
                         AND rp.days_ahead = ?
                ORDER BY rp.keyword
            """, (days_ahead, days_ahead))

            for row in rows:
                r = dict(row)
                trend = r.get("trend", "stable") or "stable"
                confidence_raw = r.get("confidence", "low") or "low"

                # Map string confidence to numeric if needed
                if isinstance(confidence_raw, str):
                    confidence_map = {
                        "low": 0.3, "medium": 0.6, "high": 0.85, "very_high": 0.95
                    }
                    confidence_val = confidence_map.get(confidence_raw, 0.5)
                else:
                    confidence_val = float(confidence_raw)

                pred = {
                    "keyword": r.get("keyword", ""),
                    "current_rank": r.get("current_rank"),
                    "predicted_rank": r.get("predicted_rank"),
                    "trend": trend,
                    "confidence": round(confidence_val, 2),
                    "factors": [],
                }

                # Generate factors based on trend
                current = r.get("current_rank")
                predicted = r.get("predicted_rank")
                if current and predicted:
                    diff = current - predicted
                    if diff > 0:
                        pred["factors"].append(f"순위 {diff}단계 상승 예측")
                    elif diff < 0:
                        pred["factors"].append(f"순위 {abs(diff)}단계 하락 예측")
                    else:
                        pred["factors"].append("현재 순위 유지 예측")

                predictions.append(pred)

                if trend == "rising":
                    rising_count += 1
                elif trend == "falling":
                    falling_count += 1
                else:
                    stable_count += 1

        except Exception as e:
            logger.warning(f"Rank predictions query failed: {e}")

        # If no predictions exist for requested days_ahead, try generating from rank_history
        if not predictions:
            try:
                predictions, rising_count, falling_count, stable_count = (
                    _compute_predictions_from_history(conn, days_ahead)
                )
            except Exception as e:
                logger.warning(f"Fallback rank prediction failed: {e}")

        return success_response({
            "predictions": predictions,
            "days_ahead": days_ahead,
            "total_keywords": len(predictions),
            "rising_count": rising_count,
            "falling_count": falling_count,
            "stable_count": stable_count,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. GET /rank-predictions/accuracy
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/rank-predictions/accuracy")
@handle_exceptions
async def get_prediction_accuracy():
    """
    예측 정확도 조회

    Returns:
        overall_accuracy, verified/accurate predictions, by_confidence, by_trend
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row

        overall_accuracy = 0.0
        verified_predictions = 0
        accurate_predictions = 0
        by_confidence: Dict[str, float] = {}
        by_trend: Dict[str, float] = {}

        try:
            # Count verified predictions (those with actual_rank filled in)
            rows = _safe_query(conn, """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN ABS(predicted_rank - actual_rank) <= 3 THEN 1 ELSE 0 END) as accurate,
                    confidence,
                    trend
                FROM rank_predictions
                WHERE accuracy_checked = 1 AND actual_rank IS NOT NULL
                GROUP BY confidence, trend
            """)

            total_verified = 0
            total_accurate = 0
            confidence_stats: Dict[str, Dict[str, int]] = defaultdict(
                lambda: {"total": 0, "accurate": 0}
            )
            trend_stats: Dict[str, Dict[str, int]] = defaultdict(
                lambda: {"total": 0, "accurate": 0}
            )

            for row in rows:
                r = dict(row)
                total = r.get("total", 0) or 0
                accurate = r.get("accurate", 0) or 0
                conf = r.get("confidence", "unknown") or "unknown"
                trend = r.get("trend", "unknown") or "unknown"

                total_verified += total
                total_accurate += accurate

                confidence_stats[conf]["total"] += total
                confidence_stats[conf]["accurate"] += accurate
                trend_stats[trend]["total"] += total
                trend_stats[trend]["accurate"] += accurate

            verified_predictions = total_verified
            accurate_predictions = total_accurate

            if total_verified > 0:
                overall_accuracy = round(total_accurate / total_verified * 100, 1)

            for conf, stats in confidence_stats.items():
                if stats["total"] > 0:
                    by_confidence[conf] = round(
                        stats["accurate"] / stats["total"] * 100, 1
                    )

            for trend, stats in trend_stats.items():
                if stats["total"] > 0:
                    by_trend[trend] = round(
                        stats["accurate"] / stats["total"] * 100, 1
                    )

        except Exception as e:
            logger.warning(f"Prediction accuracy query failed: {e}")

        return success_response({
            "overall_accuracy": overall_accuracy,
            "verified_predictions": verified_predictions,
            "accurate_predictions": accurate_predictions,
            "by_confidence": by_confidence,
            "by_trend": by_trend,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. GET /timing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/timing")
@handle_exceptions
async def get_timing_analysis():
    """
    타이밍 분석 조회

    Returns:
        platform_timing (best_hours, best_days, avg_engagement per platform),
        recommendations
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row

        platform_timing: Dict[str, Dict[str, Any]] = {}
        recommendations: List[Dict[str, Any]] = []

        # Platform-hour analysis
        try:
            rows = _safe_query(conn, """
                SELECT category as platform, sub_category as hour,
                       conversion_rate, total_count
                FROM timing_analytics
                WHERE analysis_type = 'platform_hour'
                ORDER BY category, conversion_rate DESC
            """)
            for row in rows:
                r = dict(row)
                platform = r.get("platform", "unknown")
                hour_str = r.get("hour", "0")
                rate = r.get("conversion_rate", 0) or 0
                count = r.get("total_count", 0) or 0

                if platform not in platform_timing:
                    platform_timing[platform] = {
                        "best_hours": [],
                        "best_days": [],
                        "avg_engagement": 0.0,
                    }

                try:
                    hour = int(hour_str)
                    if rate > 0 and len(platform_timing[platform]["best_hours"]) < 5:
                        platform_timing[platform]["best_hours"].append(hour)
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            logger.warning(f"Platform-hour analysis query failed: {e}")

        # Platform-day analysis
        try:
            rows = _safe_query(conn, """
                SELECT category as platform, sub_category as day_name,
                       conversion_rate, total_count
                FROM timing_analytics
                WHERE analysis_type = 'platform_day'
                ORDER BY category, conversion_rate DESC
            """)
            for row in rows:
                r = dict(row)
                platform = r.get("platform", "unknown")
                day_name = r.get("day_name", "")
                rate = r.get("conversion_rate", 0) or 0

                if platform not in platform_timing:
                    platform_timing[platform] = {
                        "best_hours": [],
                        "best_days": [],
                        "avg_engagement": 0.0,
                    }

                if rate > 0 and day_name and len(platform_timing[platform]["best_days"]) < 3:
                    platform_timing[platform]["best_days"].append(day_name)
        except Exception as e:
            logger.warning(f"Platform-day analysis query failed: {e}")

        # Avg engagement per platform
        try:
            rows = _safe_query(conn, """
                SELECT category as platform,
                       AVG(conversion_rate) as avg_rate
                FROM timing_analytics
                WHERE analysis_type IN ('platform_hour', 'platform_day')
                GROUP BY category
            """)
            for row in rows:
                r = dict(row)
                platform = r.get("platform", "unknown")
                avg_rate = r.get("avg_rate", 0) or 0
                if platform in platform_timing:
                    platform_timing[platform]["avg_engagement"] = round(avg_rate * 100, 1)
        except Exception:
            pass

        # Fallback: compute from viral_targets
        if not platform_timing:
            try:
                rows = _safe_query(conn, """
                    SELECT platform,
                           CAST(strftime('%H', discovered_at) AS INTEGER) as hour,
                           COUNT(*) as cnt,
                           SUM(CASE WHEN comment_status = 'posted' THEN 1 ELSE 0 END) as posted
                    FROM viral_targets
                    WHERE discovered_at IS NOT NULL AND platform IS NOT NULL
                    GROUP BY platform, hour
                    ORDER BY platform, posted DESC
                """)
                for row in rows:
                    r = dict(row)
                    platform = r.get("platform", "unknown")
                    hour = r.get("hour")
                    cnt = r.get("cnt", 0) or 0
                    posted = r.get("posted", 0) or 0

                    if platform not in platform_timing:
                        platform_timing[platform] = {
                            "best_hours": [],
                            "best_days": [],
                            "avg_engagement": round(posted / cnt * 100, 1) if cnt > 0 else 0.0,
                        }

                    if hour is not None and len(platform_timing[platform]["best_hours"]) < 5:
                        platform_timing[platform]["best_hours"].append(hour)
            except Exception:
                pass

        # Generate recommendations
        for platform, timing in platform_timing.items():
            best_hours = timing.get("best_hours", [])
            if best_hours:
                hours_str = ", ".join(f"{h}시" for h in best_hours[:3])
                recommendations.append({
                    "platform": platform,
                    "action": f"{hours_str}에 활동 집중",
                    "timing": hours_str,
                    "confidence": min(timing.get("avg_engagement", 50.0), 100.0),
                })

        return success_response({
            "platform_timing": platform_timing,
            "recommendations": recommendations,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 11. GET /timing/now
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/timing/now")
@handle_exceptions
async def get_current_timing_recommendations():
    """
    현재 시점 타이밍 추천

    현재 시각/요일을 기반으로 활동 추천 반환
    """
    now = datetime.now()
    current_hour = now.hour
    current_day = DAY_NAMES[now.weekday()]

    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row

        recs: List[Dict[str, str]] = []

        # Find platforms that perform well at current hour
        try:
            rows = _safe_query(conn, """
                SELECT category as platform, conversion_rate, total_count
                FROM timing_analytics
                WHERE analysis_type = 'platform_hour'
                  AND sub_category = ?
                  AND conversion_rate > 0
                ORDER BY conversion_rate DESC
            """, (str(current_hour),))

            for row in rows:
                r = dict(row)
                platform = r.get("platform", "unknown")
                rate = r.get("conversion_rate", 0) or 0
                recs.append({
                    "platform": platform,
                    "action": f"지금 {platform}에서 활동하세요",
                    "reason": f"현재 시간대({current_hour}시) 전환율 {round(rate * 100, 1)}%",
                })
        except Exception as e:
            logger.warning(f"Timing now (hour) query failed: {e}")

        # Find platforms that perform well on current day
        try:
            rows = _safe_query(conn, """
                SELECT category as platform, conversion_rate
                FROM timing_analytics
                WHERE analysis_type = 'platform_day'
                  AND sub_category = ?
                  AND conversion_rate > 0
                ORDER BY conversion_rate DESC
            """, (current_day,))

            for row in rows:
                r = dict(row)
                platform = r.get("platform", "unknown")
                rate = r.get("conversion_rate", 0) or 0
                # Only add if not already recommended by hour
                if not any(rec["platform"] == platform for rec in recs):
                    recs.append({
                        "platform": platform,
                        "action": f"오늘({current_day}) {platform} 활동 추천",
                        "reason": f"{current_day} 전환율 {round(rate * 100, 1)}%",
                    })
        except Exception as e:
            logger.warning(f"Timing now (day) query failed: {e}")

        # Default recommendation if none found
        if not recs:
            # General recommendations based on time of day
            if 9 <= current_hour <= 11:
                recs.append({
                    "platform": "naver",
                    "action": "오전 시간대 네이버 활동 추천",
                    "reason": "일반적으로 오전 활동이 효과적입니다",
                })
            elif 13 <= current_hour <= 15:
                recs.append({
                    "platform": "youtube",
                    "action": "오후 시간대 YouTube 활동 추천",
                    "reason": "점심 이후 콘텐츠 소비가 활발합니다",
                })
            elif 19 <= current_hour <= 22:
                recs.append({
                    "platform": "instagram",
                    "action": "저녁 시간대 Instagram 활동 추천",
                    "reason": "저녁 시간 SNS 활동이 활발합니다",
                })
            else:
                recs.append({
                    "platform": "all",
                    "action": "콘텐츠 준비 및 분석 추천",
                    "reason": f"현재 {current_hour}시 - 콘텐츠 준비에 적합한 시간입니다",
                })

        return success_response({
            "recommendations": recs,
            "has_recommendations": len(recs) > 0,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 12. POST /timing/analyze
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/timing/analyze")
@handle_exceptions
async def analyze_timing():
    """
    타이밍 분석 실행

    viral_targets / lead_conversions 데이터를 기반으로 timing_analytics 테이블 갱신
    """
    db = DatabaseManager()
    with db.get_new_connection() as conn:
        conn.row_factory = sqlite3.Row

        try:
            _analyze_timing(conn)
            conn.commit()
        except Exception as e:
            logger.error(f"Timing analysis failed: {e}")
            return error_response(f"타이밍 분석 실패: {str(e)}")

    # Return the updated results
    return await get_timing_analysis()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Internal analysis functions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _analyze_conversion_patterns(conn):
    """Analyze lead_conversions and update conversion_patterns table."""
    cursor = conn.cursor()

    # Ensure table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversion_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT NOT NULL,
            pattern_key TEXT NOT NULL,
            conversion_rate REAL DEFAULT 0,
            sample_count INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(pattern_type, pattern_key)
        )
    """)

    # Check if lead_conversions has data
    row = _safe_query(conn, "SELECT COUNT(*) as cnt FROM lead_conversions", fetch_one=True)
    if not row or (dict(row).get("cnt", 0) or 0) == 0:
        logger.info("No lead_conversions data for pattern analysis")
        return

    # Platform patterns
    rows = _safe_query(conn, """
        SELECT platform, COUNT(*) as total,
               SUM(CASE WHEN revenue > 0 THEN 1 ELSE 0 END) as converted
        FROM lead_conversions
        WHERE platform IS NOT NULL
        GROUP BY platform
    """)
    for row in rows:
        r = dict(row)
        total = r.get("total", 0) or 0
        converted = r.get("converted", 0) or 0
        rate = converted / total if total > 0 else 0
        cursor.execute("""
            INSERT INTO conversion_patterns (pattern_type, pattern_key, conversion_rate, sample_count, updated_at)
            VALUES ('platform', ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(pattern_type, pattern_key) DO UPDATE SET
                conversion_rate = excluded.conversion_rate,
                sample_count = excluded.sample_count,
                updated_at = datetime('now', 'localtime')
        """, (r["platform"], round(rate, 4), total))

    # Keyword patterns
    rows = _safe_query(conn, """
        SELECT keyword, COUNT(*) as total,
               SUM(CASE WHEN revenue > 0 THEN 1 ELSE 0 END) as converted
        FROM lead_conversions
        WHERE keyword IS NOT NULL AND keyword != ''
        GROUP BY keyword
    """)
    for row in rows:
        r = dict(row)
        total = r.get("total", 0) or 0
        converted = r.get("converted", 0) or 0
        rate = converted / total if total > 0 else 0
        cursor.execute("""
            INSERT INTO conversion_patterns (pattern_type, pattern_key, conversion_rate, sample_count, updated_at)
            VALUES ('keyword', ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(pattern_type, pattern_key) DO UPDATE SET
                conversion_rate = excluded.conversion_rate,
                sample_count = excluded.sample_count,
                updated_at = datetime('now', 'localtime')
        """, (r["keyword"], round(rate, 4), total))

    # Time patterns (hour of conversion)
    rows = _safe_query(conn, """
        SELECT CAST(strftime('%H', conversion_date) AS TEXT) as hour,
               COUNT(*) as total,
               SUM(CASE WHEN revenue > 0 THEN 1 ELSE 0 END) as converted
        FROM lead_conversions
        WHERE conversion_date IS NOT NULL
        GROUP BY hour
    """)
    for row in rows:
        r = dict(row)
        total = r.get("total", 0) or 0
        converted = r.get("converted", 0) or 0
        rate = converted / total if total > 0 else 0
        hour_key = r.get("hour", "0") or "0"
        cursor.execute("""
            INSERT INTO conversion_patterns (pattern_type, pattern_key, conversion_rate, sample_count, updated_at)
            VALUES ('time', ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(pattern_type, pattern_key) DO UPDATE SET
                conversion_rate = excluded.conversion_rate,
                sample_count = excluded.sample_count,
                updated_at = datetime('now', 'localtime')
        """, (hour_key, round(rate, 4), total))

    conn.commit()
    logger.info("Conversion patterns analysis completed")


def _analyze_comment_effectiveness(conn):
    """Analyze viral_targets comments and update comment_effectiveness table."""
    cursor = conn.cursor()

    # Ensure table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comment_effectiveness (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_type TEXT NOT NULL,
            category TEXT NOT NULL,
            total_count INTEGER DEFAULT 0,
            conversion_count INTEGER DEFAULT 0,
            conversion_rate REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(analysis_type, category)
        )
    """)

    # Length analysis from viral_targets
    rows = _safe_query(conn, """
        SELECT
            CASE
                WHEN LENGTH(generated_comment) < 50 THEN '0-50'
                WHEN LENGTH(generated_comment) < 100 THEN '50-100'
                WHEN LENGTH(generated_comment) < 200 THEN '100-200'
                ELSE '200+'
            END as length_cat,
            COUNT(*) as total,
            SUM(CASE WHEN comment_status = 'posted' THEN 1 ELSE 0 END) as posted
        FROM viral_targets
        WHERE generated_comment IS NOT NULL AND generated_comment != ''
        GROUP BY length_cat
    """)
    for row in rows:
        r = dict(row)
        total = r.get("total", 0) or 0
        posted = r.get("posted", 0) or 0
        rate = posted / total if total > 0 else 0
        cursor.execute("""
            INSERT INTO comment_effectiveness (analysis_type, category, total_count, conversion_count, conversion_rate, updated_at)
            VALUES ('length', ?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(analysis_type, category) DO UPDATE SET
                total_count = excluded.total_count,
                conversion_count = excluded.conversion_count,
                conversion_rate = excluded.conversion_rate,
                updated_at = datetime('now', 'localtime')
        """, (r.get("length_cat", "unknown"), total, posted, round(rate, 4)))

    # Style analysis by platform
    rows = _safe_query(conn, """
        SELECT platform,
               COUNT(*) as total,
               SUM(CASE WHEN comment_status = 'posted' THEN 1 ELSE 0 END) as posted
        FROM viral_targets
        WHERE generated_comment IS NOT NULL AND generated_comment != ''
          AND platform IS NOT NULL
        GROUP BY platform
    """)
    for row in rows:
        r = dict(row)
        total = r.get("total", 0) or 0
        posted = r.get("posted", 0) or 0
        rate = posted / total if total > 0 else 0
        cursor.execute("""
            INSERT INTO comment_effectiveness (analysis_type, category, total_count, conversion_count, conversion_rate, updated_at)
            VALUES ('style', ?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(analysis_type, category) DO UPDATE SET
                total_count = excluded.total_count,
                conversion_count = excluded.conversion_count,
                conversion_rate = excluded.conversion_rate,
                updated_at = datetime('now', 'localtime')
        """, (r.get("platform", "unknown"), total, posted, round(rate, 4)))

    conn.commit()
    logger.info("Comment effectiveness analysis completed")


def _generate_rank_predictions(conn):
    """Generate rank predictions from rank_history trends."""
    cursor = conn.cursor()

    # Ensure table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rank_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            current_rank INTEGER,
            predicted_rank INTEGER,
            trend TEXT,
            confidence TEXT,
            days_ahead INTEGER DEFAULT 7,
            predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actual_rank INTEGER,
            accuracy_checked INTEGER DEFAULT 0
        )
    """)

    # Get recent rank history per keyword (last 14 days)
    rows = _safe_query(conn, """
        SELECT keyword, rank, checked_at
        FROM rank_history
        WHERE status = 'found'
          AND rank IS NOT NULL
          AND checked_at >= datetime('now', '-14 days')
        ORDER BY keyword, checked_at DESC
    """)

    if not rows:
        logger.info("No recent rank history for predictions")
        return

    keyword_ranks: Dict[str, List[int]] = defaultdict(list)
    for row in rows:
        r = dict(row)
        kw = r.get("keyword", "")
        rank = r.get("rank")
        if kw and rank is not None:
            keyword_ranks[kw].append(rank)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for keyword, ranks in keyword_ranks.items():
        if len(ranks) < 2:
            current = ranks[0]
            predicted = current
            trend = "stable"
            confidence = "low"
        else:
            current = ranks[0]
            oldest = ranks[-1]
            diff = oldest - current  # positive = rank improved (lower number)

            # Simple linear extrapolation
            avg_change_per_check = diff / len(ranks)
            predicted = max(1, round(current - avg_change_per_check * 2))  # Extrapolate

            if diff > 3:
                trend = "rising"
                confidence = "high" if diff > 10 else "medium"
            elif diff < -3:
                trend = "falling"
                confidence = "high" if diff < -10 else "medium"
            else:
                trend = "stable"
                confidence = "medium" if len(ranks) >= 5 else "low"

        cursor.execute("""
            INSERT INTO rank_predictions
            (keyword, current_rank, predicted_rank, trend, confidence, days_ahead, predicted_at)
            VALUES (?, ?, ?, ?, ?, 7, ?)
        """, (keyword, current, predicted, trend, confidence, now_str))

    conn.commit()
    logger.info(f"Generated rank predictions for {len(keyword_ranks)} keywords")


def _compute_predictions_from_history(
    conn, days_ahead: int
) -> tuple:
    """Compute predictions directly from rank_history when no predictions exist."""
    predictions = []
    rising = 0
    falling = 0
    stable = 0

    rows = _safe_query(conn, """
        SELECT keyword, rank, checked_at
        FROM rank_history
        WHERE status = 'found'
          AND rank IS NOT NULL
          AND checked_at >= datetime('now', '-14 days')
        ORDER BY keyword, checked_at DESC
    """)

    keyword_ranks: Dict[str, List[int]] = defaultdict(list)
    for row in rows:
        r = dict(row)
        kw = r.get("keyword", "")
        rank = r.get("rank")
        if kw and rank is not None:
            keyword_ranks[kw].append(rank)

    for kw, ranks in keyword_ranks.items():
        current = ranks[0]
        if len(ranks) >= 2:
            oldest = ranks[-1]
            diff = oldest - current
            rate = diff / max(len(ranks), 1)
            predicted = max(1, round(current - rate * days_ahead / 7))

            if diff > 3:
                trend = "rising"
                conf = 0.7 if diff > 10 else 0.5
            elif diff < -3:
                trend = "falling"
                conf = 0.7 if diff < -10 else 0.5
            else:
                trend = "stable"
                conf = 0.6
        else:
            predicted = current
            trend = "stable"
            conf = 0.3

        factors = []
        if trend == "rising":
            factors.append(f"최근 {abs(current - ranks[-1]) if len(ranks) > 1 else 0}단계 상승 추세")
        elif trend == "falling":
            factors.append(f"최근 {abs(current - ranks[-1]) if len(ranks) > 1 else 0}단계 하락 추세")
        else:
            factors.append("안정적인 순위 유지")

        predictions.append({
            "keyword": kw,
            "current_rank": current,
            "predicted_rank": predicted,
            "trend": trend,
            "confidence": round(conf, 2),
            "factors": factors,
        })

        if trend == "rising":
            rising += 1
        elif trend == "falling":
            falling += 1
        else:
            stable += 1

    return predictions, rising, falling, stable


def _analyze_timing(conn):
    """Analyze timing patterns and update timing_analytics table."""
    cursor = conn.cursor()

    # Ensure table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS timing_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_type TEXT NOT NULL,
            category TEXT NOT NULL,
            sub_category TEXT,
            total_count INTEGER DEFAULT 0,
            conversion_count INTEGER DEFAULT 0,
            conversion_rate REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(analysis_type, category, sub_category)
        )
    """)

    # Platform-hour analysis from viral_targets
    rows = _safe_query(conn, """
        SELECT platform,
               CAST(strftime('%H', discovered_at) AS TEXT) as hour,
               COUNT(*) as total,
               SUM(CASE WHEN comment_status = 'posted' THEN 1 ELSE 0 END) as posted
        FROM viral_targets
        WHERE discovered_at IS NOT NULL AND platform IS NOT NULL
        GROUP BY platform, hour
    """)
    for row in rows:
        r = dict(row)
        total = r.get("total", 0) or 0
        posted = r.get("posted", 0) or 0
        rate = posted / total if total > 0 else 0
        cursor.execute("""
            INSERT INTO timing_analytics
            (analysis_type, category, sub_category, total_count, conversion_count, conversion_rate, updated_at)
            VALUES ('platform_hour', ?, ?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(analysis_type, category, sub_category) DO UPDATE SET
                total_count = excluded.total_count,
                conversion_count = excluded.conversion_count,
                conversion_rate = excluded.conversion_rate,
                updated_at = datetime('now', 'localtime')
        """, (r.get("platform", "unknown"), r.get("hour", "0"), total, posted, round(rate, 4)))

    # Platform-day analysis from viral_targets
    rows = _safe_query(conn, """
        SELECT platform,
               CAST(strftime('%w', discovered_at) AS INTEGER) as day_num,
               COUNT(*) as total,
               SUM(CASE WHEN comment_status = 'posted' THEN 1 ELSE 0 END) as posted
        FROM viral_targets
        WHERE discovered_at IS NOT NULL AND platform IS NOT NULL
        GROUP BY platform, day_num
    """)
    day_map = {0: "일요일", 1: "월요일", 2: "화요일", 3: "수요일",
               4: "목요일", 5: "금요일", 6: "토요일"}
    for row in rows:
        r = dict(row)
        total = r.get("total", 0) or 0
        posted = r.get("posted", 0) or 0
        rate = posted / total if total > 0 else 0
        day_num = r.get("day_num", 0) or 0
        day_name = day_map.get(day_num, "unknown")
        cursor.execute("""
            INSERT INTO timing_analytics
            (analysis_type, category, sub_category, total_count, conversion_count, conversion_rate, updated_at)
            VALUES ('platform_day', ?, ?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(analysis_type, category, sub_category) DO UPDATE SET
                total_count = excluded.total_count,
                conversion_count = excluded.conversion_count,
                conversion_rate = excluded.conversion_rate,
                updated_at = datetime('now', 'localtime')
        """, (r.get("platform", "unknown"), day_name, total, posted, round(rate, 4)))

    conn.commit()
    logger.info("Timing analysis completed")

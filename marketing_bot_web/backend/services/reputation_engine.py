"""
통합 평판 점수 엔진
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 V2-3] 멀티 플랫폼 평판 통합 점수

가중치:
- 네이버 플레이스: 40% (핵심 유입 채널)
- 구글 리뷰: 20%
- 카카오맵: 15%
- 커뮤니티 감성: 25% (블로그/카페/지식인)

점수 산출:
- 각 플랫폼: (긍정 비율 × 0.5) + (평균 별점/5 × 0.3) + (리뷰 활성도 × 0.2)
- 최종 = 가중 합산 (0~100점)
"""

import sqlite3
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# 플랫폼별 가중치
PLATFORM_WEIGHTS = {
    "naver_place": 0.40,
    "google": 0.20,
    "kakao": 0.15,
    "community": 0.25,
}


def calculate_reputation_score(db_path: str, target_name: str = None, days: int = 30) -> Dict[str, Any]:
    """
    통합 평판 점수 산출

    Args:
        db_path: DB 경로
        target_name: 대상 업체명 (None이면 자사 + 경쟁사 전체)
        days: 분석 기간

    Returns:
        {overall_score, platform_scores, competitor_comparison}
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. 네이버 플레이스 점수 (competitor_reviews + review_intelligence)
        naver_score = _calc_naver_score(cursor, target_name, days)

        # 2. 커뮤니티 감성 점수 (community_mentions)
        community_score = _calc_community_score(cursor, target_name, days)

        # 3. 경쟁사 비교
        competitors = _get_competitor_scores(cursor, days)

        # 가중 합산
        platform_scores = {
            "naver_place": naver_score,
            "google": {"score": 0, "note": "Google Business Profile API 연동 시 활성화"},
            "kakao": {"score": 0, "note": "카카오맵 API 연동 시 활성화"},
            "community": community_score,
        }

        active_weight_sum = PLATFORM_WEIGHTS["naver_place"] + PLATFORM_WEIGHTS["community"]
        overall = 0
        if active_weight_sum > 0:
            overall = (
                naver_score["score"] * PLATFORM_WEIGHTS["naver_place"]
                + community_score["score"] * PLATFORM_WEIGHTS["community"]
            ) / active_weight_sum * 100

        return {
            "target": target_name or "전체",
            "overall_score": round(overall, 1),
            "grade": _score_to_grade(overall),
            "platform_scores": platform_scores,
            "competitor_comparison": competitors,
            "period_days": days,
            "calculated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"평판 점수 산출 실패: {e}", exc_info=True)
        return {"error": str(e), "overall_score": 0}
    finally:
        if conn:
            conn.close()


def _calc_naver_score(cursor, target_name: Optional[str], days: int) -> Dict[str, Any]:
    """네이버 플레이스 리뷰 기반 점수"""
    try:
        where = "WHERE review_date >= date('now', ? || ' days')"
        params = [f"-{days}"]

        if target_name:
            where += " AND competitor_name LIKE ?"
            params.append(f"%{target_name}%")

        cursor.execute(f"""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN sentiment='positive' THEN 1 END) as positive,
                COUNT(CASE WHEN sentiment='negative' THEN 1 END) as negative,
                AVG(CASE WHEN star_rating IS NOT NULL THEN star_rating END) as avg_rating,
                COUNT(CASE WHEN star_rating IS NOT NULL THEN 1 END) as rated
            FROM competitor_reviews
            {where}
        """, params)

        row = cursor.fetchone()
        if not row or row["total"] == 0:
            return {"score": 0, "total_reviews": 0, "note": "리뷰 데이터 없음"}

        total = row["total"]
        positive_ratio = row["positive"] / total if total > 0 else 0
        avg_rating = row["avg_rating"] or 0
        rating_norm = avg_rating / 5.0 if avg_rating > 0 else 0.5

        # 활성도: 최근 기간 대비 리뷰 밀도
        activity = min(total / (days * 0.5), 1.0)  # 하루 0.5건 이상이면 100%

        score = (positive_ratio * 0.5 + rating_norm * 0.3 + activity * 0.2)

        return {
            "score": round(score, 3),
            "total_reviews": total,
            "positive_ratio": round(positive_ratio * 100, 1),
            "avg_rating": round(avg_rating, 1) if avg_rating else None,
            "activity_level": round(activity * 100, 1),
        }

    except Exception as e:
        logger.debug(f"네이버 점수 산출 실패: {e}")
        return {"score": 0, "error": str(e)}


def _calc_community_score(cursor, target_name: Optional[str], days: int) -> Dict[str, Any]:
    """커뮤니티 멘션 감성 기반 점수"""
    try:
        cursor.execute("""
            SELECT name FROM sqlite_master WHERE type='table' AND name='community_mentions'
        """)
        if not cursor.fetchone():
            return {"score": 0, "note": "community_mentions 테이블 없음"}

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN is_our_mention = 1 THEN 1 END) as our_mentions,
                COUNT(CASE WHEN is_lead_candidate = 1 THEN 1 END) as leads
            FROM community_mentions
            WHERE created_at >= datetime('now', ? || ' days')
        """, (f"-{days}",))

        row = cursor.fetchone()
        total = row["total"] if row else 0
        our = row["our_mentions"] if row else 0

        if total == 0:
            return {"score": 0.5, "total_mentions": 0}

        # 자사 멘션 비율이 높을수록 좋음
        our_ratio = our / total if total > 0 else 0
        activity = min(total / (days * 2), 1.0)

        score = (our_ratio * 0.6 + activity * 0.4)

        return {
            "score": round(score, 3),
            "total_mentions": total,
            "our_mentions": our,
            "lead_candidates": row["leads"] if row else 0,
        }

    except Exception as e:
        logger.debug(f"커뮤니티 점수 산출 실패: {e}")
        return {"score": 0, "error": str(e)}


def _get_competitor_scores(cursor, days: int) -> List[Dict[str, Any]]:
    """경쟁사별 평판 점수"""
    try:
        cursor.execute("""
            SELECT
                competitor_name,
                COUNT(*) as total,
                COUNT(CASE WHEN sentiment='positive' THEN 1 END) as positive,
                AVG(CASE WHEN star_rating IS NOT NULL THEN star_rating END) as avg_rating
            FROM competitor_reviews
            WHERE review_date >= date('now', ? || ' days')
            GROUP BY competitor_name
            HAVING total >= 3
            ORDER BY total DESC
            LIMIT 10
        """, (f"-{days}",))

        results = []
        for row in cursor.fetchall():
            total = row["total"]
            pos_ratio = row["positive"] / total if total > 0 else 0
            avg_r = row["avg_rating"] or 0
            score = (pos_ratio * 0.5 + (avg_r / 5.0 if avg_r > 0 else 0.5) * 0.3 + min(total / (days * 0.5), 1.0) * 0.2) * 100

            results.append({
                "name": row["competitor_name"],
                "score": round(score, 1),
                "total_reviews": total,
                "positive_ratio": round(pos_ratio * 100, 1),
                "avg_rating": round(avg_r, 1) if avg_r else None,
            })

        return sorted(results, key=lambda x: x["score"], reverse=True)

    except Exception:
        return []


def _score_to_grade(score: float) -> str:
    """점수를 등급으로 변환"""
    if score >= 85:
        return "A+"
    elif score >= 75:
        return "A"
    elif score >= 65:
        return "B+"
    elif score >= 55:
        return "B"
    elif score >= 45:
        return "C"
    else:
        return "D"

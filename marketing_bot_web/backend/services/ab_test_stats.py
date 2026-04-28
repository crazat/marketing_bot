"""
A/B Test Statistical Significance (chi-square)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

scipy.stats.chi2_contingency 기반 2-variant A/B 테스트 유의성 검정.

대상 테이블 (실제 스키마):
- ab_experiments  (id, name, status, sample_size_target, confidence_level, ...)
- ab_variants     (id, experiment_id, name, impressions, engagements, conversions,
                   engagement_rate, conversion_rate, is_control)
- ab_assignments  (id, experiment_id, variant_id, target_id, engaged, converted)

CLAUDE.md 정책: 자동 게시 X. 통계 보고만.
"""

from __future__ import annotations

import logging
import math
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 프로젝트 루트 (backend -> marketing_bot_web -> root)
_DEFAULT_DB = Path(__file__).resolve().parent.parent.parent.parent / "db" / "marketing_data.db"


def _wilson_ci(success: int, total: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score interval (95% by default). 0건 안전."""
    if total <= 0:
        return (0.0, 0.0)
    p = success / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = (z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))) / denom
    lo = max(0.0, centre - half)
    hi = min(1.0, centre + half)
    return (round(lo, 4), round(hi, 4))


def _min_sample_for_significance(p_a: float, p_b: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """대략적 N 추정 (per-arm). 두 비율 p_a, p_b, 유의수준 0.05, 검정력 0.8.

    공식: n = (z_alpha + z_beta)^2 * (p_a*(1-p_a) + p_b*(1-p_b)) / (p_a-p_b)^2
    z_0.05/2 = 1.96, z_0.2 = 0.84
    """
    if p_a == p_b:
        return 0
    z_a, z_b = 1.96, 0.84
    diff_sq = (p_a - p_b) ** 2
    if diff_sq < 1e-9:
        return 0
    var = p_a * (1 - p_a) + p_b * (1 - p_b)
    n = ((z_a + z_b) ** 2) * var / diff_sq
    return int(math.ceil(n))


def compute_significance(
    variant_a_success: int,
    variant_a_total: int,
    variant_b_success: int,
    variant_b_total: int,
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """2x2 chi-square 검정.

    Returns dict with:
      - p_value, chi2, dof
      - rate_a, rate_b, lift_pct
      - confidence_interval_a, confidence_interval_b (Wilson 95%)
      - min_sample_for_significance (per-arm 추가 필요량)
      - conclusion (한국어)
    """
    a_fail = max(0, variant_a_total - variant_a_success)
    b_fail = max(0, variant_b_total - variant_b_success)
    rate_a = (variant_a_success / variant_a_total) if variant_a_total else 0.0
    rate_b = (variant_b_success / variant_b_total) if variant_b_total else 0.0
    lift = ((rate_b - rate_a) / rate_a * 100) if rate_a > 0 else None

    ci_a = _wilson_ci(variant_a_success, variant_a_total)
    ci_b = _wilson_ci(variant_b_success, variant_b_total)

    chi2: Optional[float] = None
    p_value: Optional[float] = None
    dof: Optional[int] = None

    if variant_a_total < 5 or variant_b_total < 5:
        conclusion = (
            f"샘플 부족 (A={variant_a_total}, B={variant_b_total}). "
            "각 그룹 최소 5건 이상부터 검정 가능."
        )
    else:
        try:
            from scipy.stats import chi2_contingency  # type: ignore

            table = [[variant_a_success, a_fail], [variant_b_success, b_fail]]
            chi2_v, p_v, dof_v, _ = chi2_contingency(table, correction=True)
            chi2 = float(chi2_v)
            p_value = float(p_v)
            dof = int(dof_v)
        except Exception as e:  # pragma: no cover
            logger.warning(f"chi2_contingency 실패: {e}")
            conclusion = f"통계 검정 오류 ({type(e).__name__})"
            return {
                "p_value": None,
                "chi2": None,
                "dof": None,
                "rate_a": round(rate_a, 4),
                "rate_b": round(rate_b, 4),
                "lift_pct": round(lift, 2) if lift is not None else None,
                "confidence_interval_a": ci_a,
                "confidence_interval_b": ci_b,
                "min_sample_for_significance": None,
                "conclusion": conclusion,
            }

        if p_value is not None and p_value < alpha:
            winner = "B" if rate_b > rate_a else "A"
            conclusion = (
                f"유의함 (p={p_value:.4f} < {alpha}). "
                f"승자: 변형 {winner} (전환율 A={rate_a:.2%} → B={rate_b:.2%})."
            )
        else:
            n_needed = _min_sample_for_significance(rate_a, rate_b)
            already = max(variant_a_total, variant_b_total)
            extra = max(0, n_needed - already)
            conclusion = (
                f"유의 미달 (p={p_value:.4f} ≥ {alpha}). "
                f"각 그룹 약 {n_needed}건 필요 (현재 max {already}건, "
                f"추가 약 {extra}건)."
            )

    n_needed_calc = _min_sample_for_significance(rate_a, rate_b) if rate_a != rate_b else 0

    return {
        "p_value": round(p_value, 6) if p_value is not None else None,
        "chi2": round(chi2, 4) if chi2 is not None else None,
        "dof": dof,
        "rate_a": round(rate_a, 4),
        "rate_b": round(rate_b, 4),
        "lift_pct": round(lift, 2) if lift is not None else None,
        "confidence_interval_a": ci_a,
        "confidence_interval_b": ci_b,
        "min_sample_for_significance": n_needed_calc,
        "conclusion": conclusion,
    }


def summarize_ab_test(test_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
    """ab_experiments + ab_variants 읽어 자동 분석.

    test_id: ab_experiments.id

    실제 metric 우선순위:
      1) ab_assignments.converted (target_id 기준)
      2) ab_variants.conversions / impressions
    """
    db = Path(db_path) if db_path else _DEFAULT_DB
    if not db.exists():
        return {"error": f"DB 파일 없음: {db}"}

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute(
            "SELECT id, name, status, confidence_level, sample_size_target "
            "FROM ab_experiments WHERE id = ?",
            (test_id,),
        )
        exp = cur.fetchone()
        if not exp:
            return {"error": f"실험 id={test_id} 없음"}

        cur.execute(
            "SELECT id, name, is_control, impressions, engagements, conversions "
            "FROM ab_variants WHERE experiment_id = ? ORDER BY is_control DESC, id ASC",
            (test_id,),
        )
        variants = cur.fetchall()
        if len(variants) < 2:
            return {
                "experiment_id": test_id,
                "experiment_name": exp["name"],
                "error": f"변형이 2개 미만 ({len(variants)}개). 검정 불가.",
            }

        # 실시간 집계 (ab_assignments 우선)
        per_variant: List[Dict[str, Any]] = []
        for v in variants:
            cur.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(converted), 0) AS conv, "
                "COALESCE(SUM(engaged), 0) AS eng "
                "FROM ab_assignments WHERE experiment_id = ? AND variant_id = ?",
                (test_id, v["id"]),
            )
            row = cur.fetchone()
            n_assigned = int(row["n"]) if row else 0
            n_conv = int(row["conv"]) if row else 0
            n_eng = int(row["eng"]) if row else 0

            # ab_assignments 비어있으면 ab_variants 누적값 사용
            if n_assigned == 0:
                n_assigned = int(v["impressions"] or 0)
                n_conv = int(v["conversions"] or 0)
                n_eng = int(v["engagements"] or 0)

            per_variant.append(
                {
                    "variant_id": v["id"],
                    "name": v["name"],
                    "is_control": bool(v["is_control"]),
                    "total": n_assigned,
                    "conversions": n_conv,
                    "engagements": n_eng,
                }
            )

        # 첫 2개만 chi-square (멀티-arm은 별도 처리 필요 — 향후 확장)
        a, b = per_variant[0], per_variant[1]
        # control이 두 번째에 있으면 swap (보고 시 일관성)
        if not a["is_control"] and b["is_control"]:
            a, b = b, a

        alpha = 1.0 - float(exp["confidence_level"] or 0.95)
        sig = compute_significance(
            variant_a_success=a["conversions"],
            variant_a_total=a["total"],
            variant_b_success=b["conversions"],
            variant_b_total=b["total"],
            alpha=alpha,
        )

        return {
            "experiment_id": test_id,
            "experiment_name": exp["name"],
            "status": exp["status"],
            "alpha": alpha,
            "variants_analyzed": [a, b],
            "all_variants": per_variant,
            "metric": "conversion_rate (conversions / total)",
            **sig,
        }

    finally:
        if conn is not None:
            conn.close()


__all__ = ["compute_significance", "summarize_ab_test"]

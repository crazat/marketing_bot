"""Curated seed builder for the Pathfinder Legion -> Viral Hunter pipeline.

The Viral Hunter should not read the whole historical keyword pool by default.
It should consume a bounded, recent Legion scan with category quotas so the
comment queue stays aligned with the clinic's current focus.
"""

from __future__ import annotations

import os
import re
import json
import sqlite3
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional, Tuple

from core_services.gyulim_keyword_profile import ACTIVE_KEYWORD_PROFILE as GYULIM_KEYWORD_PROFILE


DEFAULT_CATEGORY_QUOTAS: Dict[str, int] = {
    "흉터/여드름흉터": 12,
    "피부/여드름": 10,
    "다이어트": 12,
    "안면비대칭": 10,
    "체형교정": 7,
    "교통사고": 8,
    "통증/디스크": 6,
    "리프팅/탄력": 5,
    "탈모/두피": 4,
    "두통/어지럼": 3,
    "소화/위장": 3,
    "호흡기/알레르기": 3,
    "갱년기/여성": 2,
    "수면/피로": 2,
    "스트레스/자율신경": 2,
    "여성/산후": 2,
    "다한증/냉증": 2,
    "수험생/집중력": 2,
    "면역/보약": 2,
}

# ---------------------------------------------------------------------------
# 진료축(카테고리) 단위 수요 게이트 — 플랫폼/구조 수율 게이트와 동일 철학을
# 카테고리 예산에 적용. 직원이 실제로 작업(posted/approved)하는 비율(=드러난 수요)이
# 입증된 저조 진료축은 디스커버리 시드 예산을 줄이고(절대 0이 아닌 프로브 플로어),
# 절감분을 공급 부족한 시그니처 축으로 재배분한다. _staff_outcome_adjustment 는
# 카테고리 안에서 순서만 바꿀 뿐 quota 자체는 줄이지 못해(설계상) 제로수요 축이
# 계속 quota·AI예산·pending 큐를 점유하던 구조적 누수를 막는다(2026-06-13 라이브 감사).
#
# PROTECTED: 시그니처/미용 축 + 교통사고(고LTV 자보 입원, 사용자 명시 보호) + 역공략.
#            낮은 acceptance여도 절대 게이트하지 않음.
CATEGORY_DEMAND_PROTECTED_AXES = frozenset({
    "흉터/여드름흉터",
    "피부/여드름",
    "다이어트",
    "안면비대칭",
    "체형교정",
    "리프팅/탄력",
    "교통사고",
    "경쟁사_역공략",
})
# 절감분을 흘려보낼 공급 부족 시그니처 축(흉터=새살침, 안면비대칭=로랑/데이릴 경쟁).
CATEGORY_DEMAND_SIGNATURE_BOOST_AXES = ("흉터/여드름흉터", "안면비대칭")
# Rule A: staff 결정 표본이 이 이상일 때만 acceptance로 판단(저표본 축은 탐사 유지).
CATEGORY_DEMAND_MIN_DECIDED = 25
# Rule B: 충분한 공급에도 한 번도 작업되지 않음(posted==0) — 표본이 얇어도 폐기 신호.
CATEGORY_DEMAND_ZERO_CONV_MIN_TOTAL = 150
# 프로브 플로어: 게이트되어도 최소 1 시드 유지 → acceptance 회복 시 예산 자동 복귀.
CATEGORY_DEMAND_PROBE_FLOOR = 1
# 축당 시그니처 부스트 상한(공급이 얇으면 선택이 알아서 적게 뽑으므로 무해).
CATEGORY_DEMAND_SIGNATURE_BOOST_CAP = 6

DEFAULT_EXCLUDE_PATTERNS = [
    "전후",
    "다이어트댄스",
    "다이어트 댄스",
    "줌바",
    "댄스학원",
    "엔도",
    "내과",
    "자보 다이어트",
    "실비 다이어트",
    "보험 다이어트",
    "피부과",
    "프락셀",
    "치아교정",
    "임플란트",
    "골프",
]

DIET_NON_HANBANG_SEED_PATTERNS = (
    "다이어트주사",
    "다이어트 주사",
    "지방분해주사",
    "지방 분해 주사",
    "윤곽주사",
    "윤곽 주사",
    "비만주사",
    "비만 주사",
    "달걀주사",
    "달걀 주사",
    "비비주사",
    "비비 주사",
    "바디톡신",
    "클라투",
    "지방융해술",
    "비만클리닉",
    "삭센다",
    "위고비",
    "마운자로",
)

DIET_HANBANG_SEED_RESCUE_PATTERNS = (
    "다이어트한약",
    "다이어트 한약",
    "한약",
    "한의원",
    "한방",
    "탕약",
    "감비",
    "감비환",
    "비움탕",
    "체질",
    "부항",
    "약침",
)

DEFAULT_MAX_PER_INTENT_PER_CATEGORY = 4
DEFAULT_MAX_PER_CLUSTER_PER_CATEGORY = 2
DEFAULT_MAX_PER_REGION_PER_CATEGORY = 4

# Live scan evidence (scan 67 era, 14d window): seeds shaped "neighborhood + service
# + transactional suffix" discovered 7,734 posts but converted only 22 to pending
# (0.3%) with 51% advertorial-filtered, while plain "청주 + service" seeds converted
# 5.2%. Legion templates mint fresh suffix permutations every scan, so per-keyword
# history never catches them; structure buckets let new permutations inherit the
# structural verdict.
TRANSACTIONAL_SUFFIX_TOKENS: Tuple[str, ...] = (
    "가능한곳",
    "가능한",
    "치료비",
    "주의사항",
    "진료시간",
    "예약",
    "비용",
    "가격",
    "얼마",
    "문의",
    "상담",
    "야간",
    "주말",
    "당일",
    "가능",
)

_SUFFIX_STRIP_ORDER: Tuple[str, ...] = tuple(
    sorted(TRANSACTIONAL_SUFFIX_TOKENS, key=len, reverse=True)
)


def _region_tokens() -> Tuple[str, ...]:
    profile = GYULIM_KEYWORD_PROFILE
    return tuple(
        dict.fromkeys(
            list(getattr(profile, "neighborhoods", ()) or ())
            + list(getattr(profile, "cheongju_regions", ()) or ())
            + list(getattr(profile, "nearby_regions", ()) or ())
        )
    )


def _strip_suffix_tokens(text: str) -> str:
    kept: List[str] = []
    for token in (text or "").split():
        core = token
        changed = True
        while core and changed:
            changed = False
            for suffix in _SUFFIX_STRIP_ORDER:
                if core == suffix or (core.endswith(suffix) and len(core) > len(suffix)):
                    core = core[: len(core) - len(suffix)]
                    changed = True
                    break
        if core:
            kept.append(core)
    if kept and kept[-1] == "곳":
        kept.pop()
    return " ".join(kept)


def strip_transactional_suffix(keyword: str) -> str:
    """Return a community-surface core query with transactional suffix tokens removed.

    Falls back to the original keyword when stripping would leave no service token
    (e.g. a bare neighborhood name), so callers can always search the result.
    """
    text = re.sub(r"\s+", " ", (keyword or "").strip())
    if not text:
        return keyword or ""
    stripped = _strip_suffix_tokens(text)
    if not stripped or stripped == text:
        return text
    region_tokens = _region_tokens()
    has_service_token = any(
        all(region not in token for region in region_tokens)
        for token in stripped.split()
    )
    if not has_service_token:
        return text
    return stripped


def strip_region_tokens(keyword: str) -> str:
    """Return a region-free service query for non-regional patient-question surfaces.

    KIN/community patient questions usually omit the region from searchable text,
    so region-anchored queries structurally miss them. Returns "" when nothing
    but region tokens remain — callers must skip such seeds instead of searching
    an empty query.
    """
    text = re.sub(r"\s+", " ", (keyword or "").strip())
    if not text:
        return ""
    region_tokens = _region_tokens()

    def _is_region(token: str) -> bool:
        if token in region_tokens or token.startswith("청주"):
            return True
        # 행정 접미 변형(오창읍/상당구 등): 지역명 + 1글자까지만 지역으로 본다.
        return any(
            len(region) >= 2 and token.startswith(region) and len(token) <= len(region) + 1
            for region in region_tokens
        )

    kept = [token for token in text.split() if not _is_region(token)]
    return " ".join(kept).strip()


def normalize_seed_keyword_text(keyword: str) -> str:
    """Clean mechanical seed artifacts before they become search queries."""
    text = re.sub(r"\s+", " ", (keyword or "").strip())
    if not text:
        return ""

    anchor = str(getattr(GYULIM_KEYWORD_PROFILE, "service_query_anchor", "") or "").strip()
    if anchor:
        anchor_re = re.escape(anchor)
        for _ in range(3):
            text = re.sub(rf"({anchor_re})\s*{anchor_re}", anchor, text)
        for suffix in tuple(dict.fromkeys(TRANSACTIONAL_SUFFIX_TOKENS + ("후기", "추천", "부작용", "치료기간"))):
            if suffix and suffix != anchor:
                text = re.sub(rf"({anchor_re})({re.escape(suffix)})", rf"\1 {suffix}", text)

    return re.sub(r"\s+", " ", text).strip()


def keyword_structure_features(keyword: str, category: str = "") -> Dict[str, object]:
    """Classify a seed's query structure for bucket-level yield feedback."""
    text = normalize_seed_keyword_text(keyword)
    has_suffix = bool(text) and _strip_suffix_tokens(text) != text
    neighborhoods = tuple(getattr(GYULIM_KEYWORD_PROFILE, "neighborhoods", ()) or ())
    has_neighborhood = any(token and token in text for token in neighborhoods)
    normalized_category = _canonical_category_for_keyword(keyword, category)
    structure_key = (
        f"structure:{normalized_category}:"
        f"{'suffix' if has_suffix else 'plain'}:"
        f"{'neigh' if has_neighborhood else 'city'}"
    )
    return {
        "has_transactional_suffix": has_suffix,
        "has_neighborhood_token": has_neighborhood,
        "structure_key": structure_key,
    }


def canonical_category_for_keyword(keyword: str, category: str = "") -> str:
    """Resolve stale or aliased category labels against the active clinic profile."""
    normalized = GYULIM_KEYWORD_PROFILE.normalize_category(category or "기타")
    detected = GYULIM_KEYWORD_PROFILE.normalize_category(
        GYULIM_KEYWORD_PROFILE.detect_category(keyword or "", default=normalized)
    )
    if detected in {"", "기타"}:
        return normalized

    stale_or_generic = normalized in {"", "기타", "한의원일반"}
    scar_split_from_legacy_skin = (
        normalized == "피부/여드름"
        and detected == "흉터/여드름흉터"
        and GYULIM_KEYWORD_PROFILE.profile_for(detected)
    )
    if stale_or_generic or scar_split_from_legacy_skin:
        return detected
    return normalized


def _canonical_category_for_keyword(keyword: str, category: str = "") -> str:
    return canonical_category_for_keyword(keyword, category)


def _coerce_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def is_qualified_viral_outcome(
    comment_status: str,
    clinic_fit: float,
    worksite_efficiency: float,
    priority_score: float,
) -> bool:
    """Single definition of a 'workable/converted' viral target outcome.

    Shared by ViralSeedBuilder._load_keyword_feedback (per-bucket quality_rate) and
    load_proven_dead_structures (the Pathfinder grade-promotion gate) so both layers
    judge viral yield by the exact same rule — keep this the only place the rule lives.
    """
    return (
        comment_status in {"posted", "completed", "approved", "ai_approved"}
        or (clinic_fit >= 75.0 and worksite_efficiency >= 70.0)
        or (priority_score >= 120.0 and clinic_fit >= 60.0 and worksite_efficiency >= 60.0)
    )


def load_proven_dead_structures(conn: sqlite3.Connection) -> set:
    """Return the set of query-structure keys the Viral Hunter has proven produce
    ZERO workable targets.

    Uses the SAME derivative gate + thresholds as
    ``ViralSeedBuilder._structure_proven_zero_yield`` and the SAME qualified rule as
    ``_load_keyword_feedback`` (via ``is_qualified_viral_outcome``). Pathfinder Legion
    consumes this to gate execution-fit grade promotion so a floor-volume keyword is
    never inflated to S/A inside a structure downstream viral discovery already proved
    dead. The seed builder still hard-blocks the same structures from discovery; this
    closes the loop one layer upstream at GRADING.

    Fail-soft: returns an empty set on any sqlite error or missing table/columns, so
    grading is unchanged until viral evidence accumulates (same no-op-without-data
    philosophy as the variant/platform/structure yield gates).
    """
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(viral_targets)").fetchall()}
    except sqlite3.Error:
        return set()
    if not {"matched_keyword", "comment_status"} <= columns:
        return set()

    matched_cat_expr = (
        "matched_keyword_category"
        if "matched_keyword_category" in columns
        else ("category" if "category" in columns else "''")
    )
    target_cat_expr = "category" if "category" in columns else "''"
    score_expr = "score_breakdown" if "score_breakdown" in columns else "''"
    priority_expr = "priority_score" if "priority_score" in columns else "0"

    try:
        rows = conn.execute(
            f"""
            SELECT matched_keyword,
                   {matched_cat_expr} AS matched_keyword_category,
                   {target_cat_expr} AS target_category,
                   comment_status,
                   {score_expr} AS score_breakdown,
                   {priority_expr} AS priority_score
            FROM viral_targets
            WHERE matched_keyword IS NOT NULL AND TRIM(matched_keyword) != ''
            """
        ).fetchall()
    except sqlite3.Error:
        return set()

    agg: Dict[str, dict] = {}
    for matched_keyword, matched_cat, target_cat, status, score_raw, priority in rows:
        try:
            score_breakdown = json.loads(score_raw) if score_raw else {}
            if not isinstance(score_breakdown, dict):
                score_breakdown = {}
        except (ValueError, TypeError):
            score_breakdown = {}
        source_keyword = normalize_seed_keyword_text(
            str(score_breakdown.get("pathfinder_source_keyword") or "").strip()
            or str(matched_keyword or "")
        )
        if not source_keyword:
            continue
        category = canonical_category_for_keyword(
            source_keyword, str(matched_cat or target_cat or "")
        )
        features = keyword_structure_features(source_keyword, category)
        structure_key = features.get("structure_key")
        if not structure_key:
            continue
        qualified = is_qualified_viral_outcome(
            str(status or "pending"),
            _coerce_float(score_breakdown.get("clinic_treatment_fit_score")),
            _coerce_float(score_breakdown.get("worksite_efficiency_score")),
            _coerce_float(priority),
        )
        bucket = agg.setdefault(
            structure_key,
            {
                "total_count": 0,
                "qualified_count": 0,
                "has_neighborhood_token": bool(features.get("has_neighborhood_token")),
                "has_transactional_suffix": bool(features.get("has_transactional_suffix")),
            },
        )
        bucket["total_count"] += 1
        bucket["qualified_count"] += 1 if qualified else 0

    dead: set = set()
    for structure_key, bucket in agg.items():
        total = int(bucket["total_count"] or 0)
        qualified = int(bucket["qualified_count"] or 0)
        feedback = {
            "total_count": total,
            "qualified_count": qualified,
            "quality_rate": (qualified / total) if total else 0.0,
        }
        if ViralSeedBuilder._structure_proven_zero_yield(bucket, feedback):
            dead.add(structure_key)
    return dead


def default_category_quotas() -> Dict[str, int]:
    """Return quota defaults that only include categories in the active profile.

    The constant above expresses the Gyulim operating preference.  This helper
    normalizes aliases and fills any newly-added focus categories with a small
    exploratory quota so Viral Hunter does not silently ignore real services.
    """
    normalized: Dict[str, int] = {}
    for raw_category, quota in DEFAULT_CATEGORY_QUOTAS.items():
        category = GYULIM_KEYWORD_PROFILE.normalize_category(raw_category)
        if not GYULIM_KEYWORD_PROFILE.profile_for(category):
            continue
        normalized[category] = normalized.get(category, 0) + int(quota or 0)

    for category in getattr(GYULIM_KEYWORD_PROFILE, "focus_categories", ()):
        if category in normalized:
            continue
        profile = GYULIM_KEYWORD_PROFILE.profile_for(category)
        if not profile:
            continue
        exploratory_quota = int(round(2.0 + max(0.0, float(profile.strategic_weight or 1.0))))
        normalized[category] = max(2, min(4, exploratory_quota))
    return normalized


@dataclass(frozen=True)
class ViralSeed:
    keyword: str
    scan_run_id: int
    category: str
    grade: str
    search_volume: int
    document_count: int
    kei: float
    priority_v3: float
    search_intent: str
    novelty_score: float = 0.0
    historical_target_count: int = 0
    historical_qualified_count: int = 0
    historical_revisit_rate: float = 0.0
    historical_quality_rate: float = 0.0
    historical_avg_clinic_fit: float = 0.0
    historical_avg_worksite_efficiency: float = 0.0
    historical_axis_lens_target_count: int = 0
    historical_axis_lens_quality_rate: float = 0.0
    historical_axis_lens_avg_lens_fit: float = 0.0
    keyword_structure: str = ""
    historical_structure_target_count: int = 0
    historical_structure_quality_rate: float = 0.0
    structure_yield_adjustment: float = 0.0
    historical_staff_reviewed_count: int = 0
    historical_staff_accept_rate: float = 0.0
    staff_outcome_adjustment: float = 0.0
    longtail_score: float = 0.0
    business_value_score: float = 0.0
    high_value_longtail: bool = False
    viral_readiness_score: float = 0.0
    local_service_fit_score: float = 0.0
    content_actionability_score: float = 0.0
    medical_ad_risk_score: float = 0.0
    community_signal: float = 0.0
    conversion_signal: float = 0.0
    profile_action_signal: float = 0.0
    availability_intent_score: float = 0.0
    payment_coverage_score: float = 0.0
    access_convenience_score: float = 0.0
    preferred_search_surface: str = ""
    recommended_content_type: str = ""
    brand_intent_type: str = "generic"
    review_intent_type: str = "none"
    quality_flags_json: str = "[]"
    source_signals_json: str = "[]"
    execution_lens: str = "service"

    def to_context(self) -> dict:
        return asdict(self)


class ViralSeedBuilder:
    """Builds a stable, explainable seed list from the latest Legion scan."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(root, "db", "marketing_data.db")
        self.db_path = db_path

    def latest_completed_legion_scan_id(self) -> Optional[int]:
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                if not self._table_exists(conn, "scan_runs"):
                    return None
                columns = self._table_columns(conn, "scan_runs")
                lineage_filters = []
                if "scan_type" in columns:
                    lineage_filters.append("scan_type = 'legion'")
                if "mode" in columns:
                    lineage_filters.append("mode LIKE '%legion%'")
                if not lineage_filters:
                    return None
                completed_order = "completed_at DESC, id DESC" if "completed_at" in columns else "id DESC"
                row = conn.execute(
                    f"""
                    SELECT id
                    FROM scan_runs
                    WHERE status = 'completed'
                      AND ({" OR ".join(lineage_filters)})
                    ORDER BY {completed_order}
                    LIMIT 1
                    """
                ).fetchone()
        except sqlite3.Error:
            return None
        return int(row[0]) if row else None

    def build(
        self,
        scan_run_id: Optional[int] = None,
        quotas: Optional[Dict[str, int]] = None,
        exclude_patterns: Optional[Iterable[str]] = None,
        include_grades: Iterable[str] = ("S", "A", "B"),
        max_per_intent_per_category: int = DEFAULT_MAX_PER_INTENT_PER_CATEGORY,
        max_per_cluster_per_category: int = DEFAULT_MAX_PER_CLUSTER_PER_CATEGORY,
        max_per_region_per_category: int = DEFAULT_MAX_PER_REGION_PER_CATEGORY,
        fill_profile_gaps: Optional[bool] = None,
    ) -> List[ViralSeed]:
        scan_id = scan_run_id or self.latest_completed_legion_scan_id()
        if not scan_id:
            return []

        use_default_quotas = quotas is None
        explicit_gap_fill = fill_profile_gaps is not None
        if fill_profile_gaps is None:
            fill_profile_gaps = use_default_quotas
        quotas = self._normalize_quota_map(quotas or default_category_quotas())
        excludes = list(exclude_patterns or DEFAULT_EXCLUDE_PATTERNS)
        grades = tuple(include_grades)

        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                if not self._table_exists(conn, "keyword_insights"):
                    return []
                columns = self._table_columns(conn, "keyword_insights")
                placeholders = ",".join("?" for _ in grades)
                grade_clause = f"AND grade IN ({placeholders})" if "grade" in columns else ""
                grade_params = list(grades) if "grade" in columns else []
                status_clause = "AND COALESCE(status, 'active') = 'active'" if "status" in columns else ""
                document_clause = "AND COALESCE(document_count, 0) > 0" if "document_count" in columns else ""
                business_core_clause = "AND COALESCE(business_core, 0) = 1" if "business_core" in columns else ""
                scan_filter = "1=1"
                scan_params: List[int] = []
                if "last_scan_run_id" in columns and "scan_run_id" in columns:
                    scan_filter = "COALESCE(last_scan_run_id, scan_run_id, 0) = ?"
                    scan_params.append(scan_id)
                elif "last_scan_run_id" in columns:
                    scan_filter = "COALESCE(last_scan_run_id, 0) = ?"
                    scan_params.append(scan_id)
                elif "scan_run_id" in columns:
                    scan_filter = "COALESCE(scan_run_id, 0) = ?"
                    scan_params.append(scan_id)
                select_cols = [
                    self._select_expr(columns, "keyword", "''"),
                    self._select_expr(columns, "category", "'기타'"),
                    self._select_expr(columns, "grade", "'C'"),
                    self._select_expr(columns, "search_volume", "0"),
                    self._select_expr(columns, "document_count", "0"),
                    self._select_expr(columns, "kei", "0"),
                    self._select_expr(columns, "priority_v3", "0"),
                    self._select_expr(columns, "search_intent", "'unknown'"),
                ]
                high_value_expr = self._select_expr(columns, "high_value_longtail", "0")
                longtail_expr = self._select_expr(columns, "longtail_score", "0")
                business_value_expr = self._select_expr(columns, "business_value_score", "0")
                execution_cols = [
                    self._select_expr(columns, "local_service_fit_score", "0"),
                    self._select_expr(columns, "content_actionability_score", "0"),
                    self._select_expr(columns, "medical_ad_risk_score", "0"),
                    self._select_expr(columns, "community_signal", "0"),
                    self._select_expr(columns, "conversion_signal", "0"),
                    self._select_expr(columns, "profile_action_signal", "0"),
                    self._select_expr(columns, "local_surface_score", "0"),
                    self._select_expr(columns, "review_surface_score", "0"),
                    self._select_expr(columns, "reputation_risk_score", "0"),
                    self._select_expr(columns, "competitor_brand_risk_score", "0"),
                    self._select_expr(columns, "availability_intent_score", "0"),
                    self._select_expr(columns, "payment_coverage_score", "0"),
                    self._select_expr(columns, "access_convenience_score", "0"),
                    self._select_expr(columns, "verification_score", "0"),
                    self._select_expr(columns, "novelty_score", "0", alias="pathfinder_novelty_score"),
                    self._select_expr(columns, "preferred_search_surface", "''"),
                    self._select_expr(columns, "recommended_content_type", "''"),
                    self._select_expr(columns, "brand_intent_type", "'generic'"),
                    self._select_expr(columns, "review_intent_type", "'none'"),
                    self._select_expr(columns, "quality_flags_json", "'[]'"),
                    self._select_expr(columns, "source_signals_json", "'[]'"),
                ]
                order_terms = []
                if "grade" in columns:
                    order_terms.append("CASE grade WHEN 'S' THEN 0 WHEN 'A' THEN 1 WHEN 'B' THEN 2 ELSE 3 END")
                for column in ("priority_v3", "kei", "search_volume"):
                    if column in columns:
                        order_terms.append(f"COALESCE({column}, 0) DESC")
                order_clause = ", ".join(order_terms) or "keyword ASC"
                rows = conn.execute(
                    f"""
                    SELECT {", ".join(select_cols)},
                           {high_value_expr},
                           {longtail_expr},
                           {business_value_expr},
                           {", ".join(execution_cols)}
                    FROM keyword_insights
                    WHERE {scan_filter}
                      {grade_clause}
                      {status_clause}
                      {document_clause}
                      {business_core_clause}
                    ORDER BY {order_clause}
                    """,
                    (*scan_params, *grade_params),
                ).fetchall()
        except sqlite3.Error:
            return []

        feedback = self._load_keyword_feedback()
        # 카테고리 수요 게이트: 드러난 직원 작업 수요로 진료축 예산을 재배분
        # (저수요 축 축소 → 시그니처 축 재투입). main 선택 루프와 gap-fill 모두
        # 이 quotas 를 소비하므로 단일 지점에서 한 번만 적용한다.
        quotas = self._apply_category_demand_gate(quotas, feedback)
        scored_rows = []
        # 구조 수율 하드블록 집계 (런 단위). 변형/플랫폼 수율 게이트와 같은 철학을
        # 구조(category×suffix×neigh/city) 단위로 확장 — 증명된 제로수율 파생 구조는
        # 선택에서 제외해 SERP/AI 예산 낭비를 막는다.
        self._structure_blocked_buckets: Dict[str, int] = {}
        for row in rows:
            raw_keyword = row["keyword"] or ""
            keyword = normalize_seed_keyword_text(raw_keyword)
            if self._is_excluded_keyword(keyword, excludes):
                continue
            row_data = dict(row)
            row_data["keyword"] = keyword
            row_data["category"] = self._canonical_category_for_keyword(
                keyword,
                row_data.get("category") or "기타",
            )
            if self._is_non_hanbang_diet_seed(row_data):
                continue
            fb = self._feedback_for_keyword(feedback, keyword)
            if not fb and raw_keyword != keyword:
                fb = self._feedback_for_keyword(feedback, raw_keyword)
            axis_lens_fb = self._feedback_for_axis_lens(feedback, row_data)
            axis_lens_feedback_adjustment = self._axis_lens_feedback_adjustment(axis_lens_fb)
            structure = keyword_structure_features(keyword, row_data["category"])
            structure_fb = feedback.get(str(structure["structure_key"])) or {}
            # 제로수율이 증명된 파생 구조(동네/거래형 접미사)는 하드블록. 기본 plain:city
            # 레인은 항상 보존하므로 어떤 진료축도 기본 탐사를 잃지 않는다.
            if self._structure_proven_zero_yield(structure, structure_fb):
                bucket = str(structure["structure_key"])
                self._structure_blocked_buckets[bucket] = (
                    self._structure_blocked_buckets.get(bucket, 0) + 1
                )
                continue
            structure_yield_adjustment = self._structure_yield_adjustment(structure_fb)
            staff_fb = self._staff_feedback_bucket(
                fb,
                axis_lens_fb,
                feedback.get(f"axis:{row_data['category']}") or {},
            )
            staff_outcome_adjustment = self._staff_outcome_adjustment(staff_fb)
            final_gate_count = fb.get("final_gate_count", 0)
            skip_rate = fb.get("skip_rate", 0.0)
            total_count = fb.get("total_count", 0)
            revisit_rate = fb.get("revisit_rate", 0.0)
            qualified_count = fb.get("qualified_count", 0)
            quality_rate = fb.get("quality_rate", 0.0)
            avg_clinic_fit = fb.get("avg_clinic_fit", 0.0)
            avg_worksite_efficiency = fb.get("avg_worksite_efficiency", 0.0)
            unproductive_count = max(0, int(total_count or 0) - int(qualified_count or 0))
            feedback_penalty = (
                min(24.0, final_gate_count * 3.0)
                + min(18.0, skip_rate * 18.0)
                + min(22.0, unproductive_count * 0.9)
            )
            history_penalty = min(28.0, unproductive_count * 1.0) + min(25.0, revisit_rate * 25.0)
            quality_bonus = (
                min(30.0, qualified_count * 2.5)
                + min(18.0, quality_rate * 18.0)
                + min(12.0, max(0.0, float(avg_clinic_fit or 0.0) - 70.0) * 0.18)
                + min(12.0, max(0.0, float(avg_worksite_efficiency or 0.0) - 70.0) * 0.18)
            )
            viral_readiness_score = self._viral_readiness_score(row_data)
            execution_risk_penalty = self._viral_execution_risk_penalty(row_data)
            adjusted_priority = (
                float(row["priority_v3"] or 0)
                + quality_bonus
                + min(46.0, viral_readiness_score * 0.52)
                + axis_lens_feedback_adjustment
                + structure_yield_adjustment
                + staff_outcome_adjustment
                - feedback_penalty
                - history_penalty
                - execution_risk_penalty
            )
            novelty_score = max(
                0.0,
                100.0
                - min(55.0, unproductive_count * 2.0)
                - min(25.0, revisit_rate * 25.0)
                - min(20.0, skip_rate * 20.0),
            )
            novelty_score = min(100.0, novelty_score + min(18.0, qualified_count * 1.5))
            if float(row_data.get("pathfinder_novelty_score") or 0.0) >= 65.0:
                novelty_score = min(100.0, novelty_score + 6.0)
            learned_quality_rate, learned_evidence = self._best_learned_quality_rate(
                fb, axis_lens_fb, structure_fb
            )
            viral_seed_fit_score = self._viral_seed_fit_score(
                row_data,
                adjusted_priority=adjusted_priority,
                viral_readiness_score=viral_readiness_score,
                execution_risk_penalty=execution_risk_penalty,
                learned_quality_rate=learned_quality_rate,
                learned_evidence=learned_evidence,
            )
            viral_seed_fit_score = max(
                0.0,
                round(viral_seed_fit_score + axis_lens_feedback_adjustment * 1.35, 2),
            )
            viral_seed_fit_score = max(
                0.0,
                round(viral_seed_fit_score + structure_yield_adjustment * 1.1, 2),
            )
            viral_seed_fit_score = max(
                0.0,
                round(viral_seed_fit_score + staff_outcome_adjustment * 1.1, 2),
            )
            candidate_item = {
                "adjusted_priority": adjusted_priority,
                "novelty_score": novelty_score,
                "viral_readiness_score": viral_readiness_score,
                "viral_seed_fit_score": viral_seed_fit_score,
                "execution_risk_penalty": execution_risk_penalty,
                "axis_lens_feedback": axis_lens_fb,
                "axis_lens_feedback_adjustment": axis_lens_feedback_adjustment,
                "structure": structure,
                "structure_feedback": structure_fb,
                "structure_yield_adjustment": structure_yield_adjustment,
                "staff_feedback": staff_fb,
                "staff_outcome_adjustment": staff_outcome_adjustment,
                "feedback": fb,
                "row": row_data,
            }
            if self._should_suppress_weak_execution_lens(candidate_item):
                continue
            scored_rows.append(candidate_item)

        scored_rows.sort(
            key=lambda item: (
                -item["viral_seed_fit_score"],
                {"S": 0, "A": 1, "B": 2}.get(item["row"]["grade"], 3),
                -int(item["row"]["high_value_longtail"] or 0),
                -float(item["row"]["business_value_score"] or 0),
                -float(item["row"]["longtail_score"] or 0),
                -item["viral_readiness_score"],
                -item["adjusted_priority"],
                -item["novelty_score"],
                -float(item["row"]["kei"] or 0),
                -int(item["row"]["search_volume"] or 0),
            )
        )

        by_category: Dict[str, List[dict]] = {}
        for item in scored_rows:
            row = item["row"]
            by_category.setdefault(row["category"] or "기타", []).append(item)

        selected: List[ViralSeed] = []
        seen = set()
        for category, quota in quotas.items():
            category_rows = self._select_diverse_rows(
                by_category.get(category, []),
                quota,
                max_per_intent_per_category,
                max_per_cluster_per_category,
                max_per_region_per_category,
            )
            for item in category_rows:
                row = item["row"]
                keyword = row["keyword"]
                if keyword in seen:
                    continue
                fb = item["feedback"]
                axis_lens_fb = item.get("axis_lens_feedback") or {}
                selected.append(
                    ViralSeed(
                        keyword=keyword,
                        scan_run_id=scan_id,
                        category=row["category"] or "기타",
                        grade=row["grade"] or "C",
                        search_volume=int(row["search_volume"] or 0),
                        document_count=int(row["document_count"] or 0),
                        kei=float(row["kei"] or 0),
                        priority_v3=float(row["priority_v3"] or 0),
                        search_intent=row["search_intent"] or "unknown",
                        novelty_score=float(item["novelty_score"] or 0),
                        historical_target_count=int(fb.get("total_count", 0) or 0),
                        historical_qualified_count=int(fb.get("qualified_count", 0) or 0),
                        historical_revisit_rate=float(fb.get("revisit_rate", 0.0) or 0.0),
                        historical_quality_rate=float(fb.get("quality_rate", 0.0) or 0.0),
                        historical_avg_clinic_fit=float(fb.get("avg_clinic_fit", 0.0) or 0.0),
                        historical_avg_worksite_efficiency=float(fb.get("avg_worksite_efficiency", 0.0) or 0.0),
                        historical_axis_lens_target_count=int(axis_lens_fb.get("total_count", 0) or 0),
                        historical_axis_lens_quality_rate=float(axis_lens_fb.get("quality_rate", 0.0) or 0.0),
                        historical_axis_lens_avg_lens_fit=float(axis_lens_fb.get("avg_lens_fit", 0.0) or 0.0),
                        keyword_structure=str((item.get("structure") or {}).get("structure_key") or ""),
                        historical_structure_target_count=int(
                            (item.get("structure_feedback") or {}).get("total_count", 0) or 0
                        ),
                        historical_structure_quality_rate=float(
                            (item.get("structure_feedback") or {}).get("quality_rate", 0.0) or 0.0
                        ),
                        structure_yield_adjustment=float(item.get("structure_yield_adjustment") or 0.0),
                        historical_staff_reviewed_count=int(
                            (item.get("staff_feedback") or {}).get("staff_reviewed_count", 0) or 0
                        ),
                        historical_staff_accept_rate=float(
                            (item.get("staff_feedback") or {}).get("staff_accept_rate", 0.0) or 0.0
                        ),
                        staff_outcome_adjustment=float(item.get("staff_outcome_adjustment") or 0.0),
                        longtail_score=float(row["longtail_score"] or 0),
                        business_value_score=float(row["business_value_score"] or 0),
                        high_value_longtail=bool(row["high_value_longtail"] or 0),
                        viral_readiness_score=float(item["viral_readiness_score"] or 0),
                        local_service_fit_score=float(row["local_service_fit_score"] or 0),
                        content_actionability_score=float(row["content_actionability_score"] or 0),
                        medical_ad_risk_score=float(row["medical_ad_risk_score"] or 0),
                        community_signal=float(row["community_signal"] or 0),
                        conversion_signal=float(row["conversion_signal"] or 0),
                        profile_action_signal=float(row["profile_action_signal"] or 0),
                        availability_intent_score=float(row["availability_intent_score"] or 0),
                        payment_coverage_score=float(row["payment_coverage_score"] or 0),
                        access_convenience_score=float(row["access_convenience_score"] or 0),
                        preferred_search_surface=row["preferred_search_surface"] or "",
                        recommended_content_type=row["recommended_content_type"] or "",
                        brand_intent_type=row["brand_intent_type"] or "generic",
                        review_intent_type=row["review_intent_type"] or "none",
                        quality_flags_json=row["quality_flags_json"] or "[]",
                        source_signals_json=row["source_signals_json"] or "[]",
                        execution_lens=self._keyword_execution_lens(row),
                    )
                )
                seen.add(keyword)

        observed_categories = {
            seed.category
            for seed in selected
            if GYULIM_KEYWORD_PROFILE.profile_for(seed.category)
        }
        broad_enough_for_default_gap_fill = len(observed_categories) >= 3
        if fill_profile_gaps and (explicit_gap_fill or broad_enough_for_default_gap_fill):
            self._append_profile_gap_fill_seeds(
                selected,
                seen,
                quotas,
                scan_id,
                excludes,
                max_per_cluster_per_category=max_per_cluster_per_category,
                max_per_region_per_category=max_per_region_per_category,
            )

        return self._interleave_seed_portfolio(selected)

    @staticmethod
    def _normalize_quota_map(quotas: Dict[str, int]) -> Dict[str, int]:
        """Merge alias quotas into the active profile's canonical categories."""
        normalized: Dict[str, int] = {}
        for raw_category, quota in (quotas or {}).items():
            category = GYULIM_KEYWORD_PROFILE.normalize_category(raw_category)
            normalized[category] = normalized.get(category, 0) + int(quota or 0)
        return normalized

    @staticmethod
    def _canonical_category_for_keyword(keyword: str, category: str = "") -> str:
        return _canonical_category_for_keyword(keyword, category)

    def _append_profile_gap_fill_seeds(
        self,
        selected: List[ViralSeed],
        seen: set,
        quotas: Dict[str, int],
        scan_id: int,
        excludes: Iterable[str],
        *,
        max_per_cluster_per_category: int,
        max_per_region_per_category: int,
    ) -> None:
        """Fill quota holes with profile exploration seeds after DB-backed seeds.

        Pathfinder scan rows remain the source of truth.  This only prevents a
        real treatment axis from disappearing from Viral Hunter when a recent
        scan has too few eligible rows, including zero surviving rows, for that
        axis.
        """
        category_counts = Counter(seed.category for seed in selected)
        normalized_seen = {
            self._keyword_feedback_key(seed.keyword)
            for seed in selected
        }
        normalized_seen.update(self._keyword_feedback_key(keyword) for keyword in seen)

        for raw_category, quota in quotas.items():
            category = GYULIM_KEYWORD_PROFILE.normalize_category(raw_category)
            needed = int(quota or 0) - int(category_counts.get(category, 0) or 0)
            if needed <= 0:
                continue
            profile = GYULIM_KEYWORD_PROFILE.profile_for(category)
            if not profile:
                continue

            candidates = self._profile_gap_seed_candidates(category, max(needed * 12, 48))
            cluster_counts: Counter = Counter(
                self._keyword_cluster_key(seed.keyword, seed.category)
                for seed in selected
                if seed.category == category
            )
            region_counts: Counter = Counter(
                self._keyword_region_key(seed.keyword)
                for seed in selected
                if seed.category == category
            )

            added = 0
            for row in candidates:
                keyword = row["keyword"]
                normalized_keyword = self._keyword_feedback_key(keyword)
                if not keyword or normalized_keyword in normalized_seen:
                    continue
                if self._is_excluded_keyword(keyword, excludes):
                    continue
                if self._is_non_hanbang_diet_seed(row):
                    continue

                cluster = self._keyword_cluster_key(keyword, category)
                region = self._keyword_region_key(keyword)
                if cluster_counts[cluster] >= max(1, max_per_cluster_per_category):
                    continue
                if region_counts[region] >= max(1, max_per_region_per_category):
                    continue

                selected.append(self._profile_gap_seed_from_row(row, scan_id))
                normalized_seen.add(normalized_keyword)
                seen.add(keyword)
                category_counts[category] += 1
                cluster_counts[cluster] += 1
                region_counts[region] += 1
                added += 1
                if added >= needed:
                    break

    def _profile_gap_seed_candidates(self, category: str, limit: int) -> List[dict]:
        raw_keywords = GYULIM_KEYWORD_PROFILE.build_exploration_seed_keywords(
            categories=[category],
            max_terms_per_category=6,
            max_suffixes_per_category=6,
            max_contexts_per_category=3,
            max_neighborhoods_per_category=5,
        )
        rows: List[dict] = []
        for raw_keyword in raw_keywords:
            keyword = normalize_seed_keyword_text(raw_keyword)
            canonical = self._canonical_category_for_keyword(keyword, category)
            if canonical != category:
                continue
            row = self._profile_gap_seed_row(keyword, canonical)
            rows.append(row)

        rows.sort(
            key=lambda row: (
                -self._profile_gap_seed_score(row),
                self._keyword_execution_lens(row) not in {"review", "community", "consultation"},
                len(str(row.get("keyword") or "")),
            )
        )
        return rows[:limit]

    @staticmethod
    def _profile_gap_seed_row(keyword: str, category: str) -> dict:
        compact = re.sub(r"\s+", "", (keyword or "").lower())
        has_recommendation = any(term in compact for term in ("추천", "어디", "잘하는곳", "괜찮은곳", "후기"))
        has_consult = any(term in compact for term in ("상담", "문의", "처방", "진단"))
        has_cost = any(term in compact for term in ("비용", "가격", "얼마"))
        has_access = any(term in compact for term in ("예약", "야간", "주말", "진료시간", "주차", "근처"))
        has_safety = any(term in compact for term in ("부작용", "주의사항", "치료기간", "회복", "통증", "재발"))

        community = 42.0 if has_recommendation else 28.0
        conversion = 38.0 if has_consult or has_cost else 22.0
        availability = 56.0 if has_access else 28.0
        review_surface = 58.0 if has_recommendation else 35.0
        recommended_type = "faq_safety" if has_safety else "proof_safe_guide"
        review_intent = "community_recommendation" if has_recommendation else "none"

        return {
            "keyword": keyword,
            "category": category,
            "grade": "B",
            "search_volume": 0,
            "document_count": 0,
            "kei": 0.0,
            "priority_v3": 58.0,
            "search_intent": "commercial" if has_recommendation else ("transactional" if has_cost or has_consult else "informational"),
            "high_value_longtail": 1,
            "longtail_score": 76.0,
            "business_value_score": 74.0,
            "local_service_fit_score": 82.0,
            "content_actionability_score": 72.0,
            "medical_ad_risk_score": 12.0 if not has_safety else 18.0,
            "community_signal": community,
            "conversion_signal": conversion,
            "profile_action_signal": 30.0 if has_access else 18.0,
            "local_surface_score": 62.0,
            "review_surface_score": review_surface,
            "reputation_risk_score": 8.0,
            "competitor_brand_risk_score": 0.0,
            "availability_intent_score": availability,
            "payment_coverage_score": 55.0 if has_cost else 25.0,
            "access_convenience_score": 50.0 if has_access else 20.0,
            "verification_score": 58.0,
            "pathfinder_novelty_score": 82.0,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": recommended_type,
            "brand_intent_type": "generic",
            "review_intent_type": review_intent,
            "quality_flags_json": "[]",
            "source_signals_json": json.dumps(["profile_gap_fill"], ensure_ascii=False),
        }

    @staticmethod
    def _profile_gap_seed_score(row: dict) -> float:
        keyword = str(row.get("keyword") or "")
        compact = re.sub(r"\s+", "", keyword)
        score = 40.0 + ViralSeedBuilder._axis_execution_query_bonus(row)
        if any(term in compact for term in ("추천", "어디", "괜찮은곳", "잘하는곳")):
            score += 24.0
        if "한의원" in compact or "한방" in compact:
            score += 16.0
        if any(term in compact for term in ("상담", "비용", "후기")):
            score += 10.0
        if GYULIM_KEYWORD_PROFILE.is_target_region(keyword, include_nearby=True):
            score += 8.0
        if any(term in compact for term in ("예약", "진료시간", "주차")) and not any(
            term in compact for term in ("추천", "어디", "괜찮은곳", "잘하는곳")
        ):
            score -= 10.0
        return score

    @staticmethod
    def _profile_gap_seed_from_row(row: dict, scan_id: int) -> ViralSeed:
        keyword = str(row.get("keyword") or "")
        category = _canonical_category_for_keyword(keyword, str(row.get("category") or ""))
        structure = keyword_structure_features(keyword, category)
        return ViralSeed(
            keyword=keyword,
            scan_run_id=scan_id,
            category=category,
            grade=str(row.get("grade") or "B"),
            search_volume=0,
            document_count=0,
            kei=0.0,
            priority_v3=float(row.get("priority_v3") or 0.0),
            search_intent=str(row.get("search_intent") or "informational"),
            novelty_score=88.0,
            keyword_structure=str(structure.get("structure_key") or ""),
            longtail_score=float(row.get("longtail_score") or 0.0),
            business_value_score=float(row.get("business_value_score") or 0.0),
            high_value_longtail=bool(row.get("high_value_longtail") or 0),
            viral_readiness_score=ViralSeedBuilder._viral_readiness_score(row),
            local_service_fit_score=float(row.get("local_service_fit_score") or 0.0),
            content_actionability_score=float(row.get("content_actionability_score") or 0.0),
            medical_ad_risk_score=float(row.get("medical_ad_risk_score") or 0.0),
            community_signal=float(row.get("community_signal") or 0.0),
            conversion_signal=float(row.get("conversion_signal") or 0.0),
            profile_action_signal=float(row.get("profile_action_signal") or 0.0),
            availability_intent_score=float(row.get("availability_intent_score") or 0.0),
            payment_coverage_score=float(row.get("payment_coverage_score") or 0.0),
            access_convenience_score=float(row.get("access_convenience_score") or 0.0),
            preferred_search_surface=str(row.get("preferred_search_surface") or ""),
            recommended_content_type=str(row.get("recommended_content_type") or ""),
            brand_intent_type=str(row.get("brand_intent_type") or "generic"),
            review_intent_type=str(row.get("review_intent_type") or "none"),
            quality_flags_json=str(row.get("quality_flags_json") or "[]"),
            source_signals_json=str(row.get("source_signals_json") or "[]"),
            execution_lens=ViralSeedBuilder._keyword_execution_lens(row),
        )

    @staticmethod
    def _interleave_seed_portfolio(seeds: List[ViralSeed]) -> List[ViralSeed]:
        """Return seeds round-robin by treatment axis so partial runs stay broad."""
        if len(seeds) <= 1:
            return seeds

        by_category: Dict[str, List[ViralSeed]] = {}
        category_order: List[str] = []
        for seed in seeds:
            if seed.category not in by_category:
                by_category[seed.category] = []
                category_order.append(seed.category)
            by_category[seed.category].append(seed)

        interleaved: List[ViralSeed] = []
        while len(interleaved) < len(seeds):
            progressed = False
            for category in category_order:
                bucket = by_category.get(category) or []
                if bucket:
                    interleaved.append(bucket.pop(0))
                    progressed = True
            if not progressed:
                break
        return interleaved

    @staticmethod
    def _is_excluded_keyword(keyword: str, excludes: Iterable[str]) -> bool:
        """Apply broad excludes, with a narrow rescue for clinic-comparison scar searches."""
        text = keyword or ""
        for pattern in excludes:
            if not pattern or pattern not in text:
                continue
            if ViralSeedBuilder._allow_contextual_skin_comparison(text, pattern):
                continue
            return True
        return False

    @staticmethod
    def _keyword_feedback_key(keyword: str) -> str:
        return re.sub(r"\s+", "", (keyword or "").strip().lower())

    @staticmethod
    def _feedback_for_keyword(feedback: Dict[str, dict], keyword: str) -> dict:
        normalized_key = f"norm:{ViralSeedBuilder._keyword_feedback_key(keyword)}"
        return feedback.get(normalized_key) or feedback.get(keyword) or {}

    @staticmethod
    def _feedback_keywords_from_row(matched_keyword: object, matched_keywords: object) -> List[str]:
        keywords: List[str] = []

        def add(value: object) -> None:
            text = str(value or "").strip()
            if text:
                keywords.append(text)
                cleaned = normalize_seed_keyword_text(text)
                if cleaned and cleaned != text:
                    keywords.append(cleaned)

        add(matched_keyword)
        if isinstance(matched_keywords, list):
            for item in matched_keywords:
                add(item)
        elif isinstance(matched_keywords, str):
            raw = matched_keywords.strip()
            if raw:
                parsed = None
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    for item in parsed:
                        add(item)
                else:
                    for item in raw.split(","):
                        add(item)

        return list(dict.fromkeys(keywords))

    @staticmethod
    def _feedback_for_axis_lens(feedback: Dict[str, dict], row: dict) -> dict:
        category = _canonical_category_for_keyword(str(row.get("keyword") or ""), str(row.get("category") or ""))
        execution_lens = ViralSeedBuilder._keyword_execution_lens(row)
        return feedback.get(f"axis_lens:{category}:{execution_lens}") or feedback.get(f"axis:{category}") or {}

    @staticmethod
    def _axis_lens_feedback_adjustment(feedback: dict) -> float:
        """Small closed-loop correction from recent Viral Hunter axis/lens outcomes."""
        total = int(feedback.get("total_count", 0) or 0)
        if total < 3:
            return 0.0

        evidence_weight = min(1.0, total / 8.0)
        quality_rate = ViralSeedBuilder._as_float(feedback.get("quality_rate"))
        lens_match_rate = ViralSeedBuilder._as_float(feedback.get("lens_match_rate"))
        lens_mismatch_rate = ViralSeedBuilder._as_float(feedback.get("lens_mismatch_rate"))
        avg_lens_fit = ViralSeedBuilder._as_float(feedback.get("avg_lens_fit"))
        skip_rate = ViralSeedBuilder._as_float(feedback.get("skip_rate"))
        final_gate_rate = float(feedback.get("final_gate_count", 0) or 0) / max(1, total)

        adjustment = 0.0
        if quality_rate >= 0.45:
            adjustment += min(10.0, quality_rate * 12.0)
        if lens_match_rate >= 0.45:
            adjustment += min(9.0, lens_match_rate * 11.0)
        if avg_lens_fit >= 68.0:
            adjustment += min(8.0, (avg_lens_fit - 58.0) * 0.25)

        if final_gate_rate >= 0.30:
            adjustment -= min(12.0, final_gate_rate * 16.0)
        if lens_mismatch_rate >= 0.30:
            adjustment -= min(12.0, lens_mismatch_rate * 16.0)
        if skip_rate >= 0.45:
            adjustment -= min(8.0, skip_rate * 10.0)

        if total >= 40 and quality_rate < 0.015:
            adjustment -= 18.0
        if total >= 100 and quality_rate < 0.006:
            adjustment -= 12.0
        if total >= 100 and lens_match_rate < 0.03 and avg_lens_fit < 45.0:
            adjustment -= 10.0

        return round(max(-48.0, min(22.0, adjustment)) * evidence_weight, 2)

    @staticmethod
    def _structure_proven_zero_yield(structure: dict, feedback: dict) -> bool:
        """Hard-block a seed whose query STRUCTURE bucket has overwhelming zero-yield
        evidence — but only DERIVATIVE structures (neighborhood token or transactional
        suffix). The base plain+city lane per category is always preserved, so no axis
        loses its base exploration; `_structure_yield_adjustment` (ranking penalty)
        still handles weaker/under-evidenced cases.

        Why a hard block on top of the ranking penalty: the penalty only reorders
        within a category, so when an axis's only available supply is a dead-structure
        permutation it still fills the quota and burns budget. Live basis (2026-06-13):
        neighborhood+suffix permutations (봉명동 침리프팅 상담 가능한곳 예약, 복대동 교통사고
        입원 한의원 자동차보험 등) — 92 such seeds burned 10.4k discoveries / 0 pending in
        30d. Mirrors the variant/platform yield gates' evidence-gated philosophy;
        thresholds are conservative so a genuinely thin axis is never blocked early.
        """
        is_derivative = bool(
            structure.get("has_neighborhood_token") or structure.get("has_transactional_suffix")
        )
        if not is_derivative:
            return False
        total = int(feedback.get("total_count", 0) or 0)
        qualified = int(feedback.get("qualified_count", 0) or 0)
        quality_rate = ViralSeedBuilder._as_float(feedback.get("quality_rate"))
        if total >= 150 and qualified == 0:
            return True
        if total >= 300 and quality_rate < 0.005:
            return True
        return False

    @staticmethod
    def _structure_yield_adjustment(feedback: dict) -> float:
        """Bucket-level yield verdict for a seed's query structure.

        Per-keyword feedback cannot catch Legion's fresh suffix permutations (each
        new combination starts with a clean history and a novelty bonus), so
        structurally identical seeds share one verdict once the bucket has enough
        evidence. The penalty reorders seeds within a category; quotas still fill,
        so thin axes are not starved.
        """
        total = int(feedback.get("total_count", 0) or 0)
        if total < 80:
            return 0.0
        quality_rate = ViralSeedBuilder._as_float(feedback.get("quality_rate"))
        evidence_weight = min(1.0, total / 400.0)
        if quality_rate < 0.01:
            return round(-30.0 * evidence_weight, 2)
        if quality_rate < 0.02:
            return round(-18.0 * evidence_weight, 2)
        if quality_rate >= 0.05:
            return round(min(12.0, 6.0 + quality_rate * 60.0) * evidence_weight, 2)
        return 0.0

    @staticmethod
    def _staff_outcome_adjustment(feedback: dict) -> float:
        """Staff-decision verdict for a seed lane (posted vs skipped + explicit ratings).

        Discovery-time statuses can look healthy while staff reject nearly every
        target during review (live data: traffic-accident accept 4.5% vs diet
        18.3%), and model-score "qualified" proxies cannot see that gap. This is
        the only human-grounded signal in the loop. Evidence-weighted and bounded
        so it reorders lanes without starving category quotas.
        """
        reviewed = int(feedback.get("staff_reviewed_count", 0) or 0)
        if reviewed < 8:
            return 0.0
        accept_rate = ViralSeedBuilder._as_float(feedback.get("staff_accept_rate"))
        evidence_weight = min(1.0, reviewed / 40.0)
        if accept_rate < 0.05:
            return round(-14.0 * evidence_weight, 2)
        if accept_rate < 0.10:
            return round(-8.0 * evidence_weight, 2)
        if accept_rate >= 0.30:
            return round(min(12.0, 6.0 + accept_rate * 12.0) * evidence_weight, 2)
        if accept_rate >= 0.20:
            return round(5.0 * evidence_weight, 2)
        return 0.0

    @staticmethod
    def _category_demand_factor(stats: dict) -> Tuple[float, str]:
        """Per-axis discovery-budget factor from revealed staff conversion.

        Mirrors `_acceptance_to_yield_factor` (platform yield gate) but at the
        category level and with two evidence rules so genuinely thin axes are
        never punished for low sample size:

        - Rule B (zero-conversion-despite-supply): ample all-time supply yet
          never once worked by staff -> probe floor. Catches profile gap-fill
          axes (호흡기/다한증/여성·산후/갱년기/소화 …) that produce hundreds of
          discoveries but 0 posts, even when their decided sample is tiny.
        - Rule A (low acceptance with evidence): enough staff decisions to
          trust acceptance -> map acceptance to a factor.

        Returns (factor, reason). factor==1.0 means "do not gate".
        """
        total = int(stats.get("total_count", 0) or 0)
        positive = int(stats.get("staff_positive_count", 0) or 0)
        reviewed = int(stats.get("staff_reviewed_count", 0) or 0)
        accept = ViralSeedBuilder._as_float(stats.get("staff_accept_rate"))
        # Rule B — never once worked despite ample supply.
        if positive == 0 and total >= CATEGORY_DEMAND_ZERO_CONV_MIN_TOTAL:
            return 0.2, f"zero_conversion(total={total},posted=0)"
        # Rule A — enough staff decisions to judge revealed demand.
        if reviewed >= CATEGORY_DEMAND_MIN_DECIDED:
            if accept >= 0.12:
                return 1.0, ""
            if accept >= 0.06:
                return 0.6, f"low_demand(accept={accept * 100:.1f}%)"
            if accept >= 0.02:
                return 0.4, f"low_demand(accept={accept * 100:.1f}%)"
            return 0.25, f"near_zero_demand(accept={accept * 100:.1f}%)"
        # Under-evidenced (thin sample, some conversion) — keep exploring.
        return 1.0, ""

    def _apply_category_demand_gate(
        self,
        quotas: Dict[str, int],
        feedback: Dict[str, dict],
    ) -> Dict[str, int]:
        """Reweight per-category seed quota by revealed staff conversion.

        Protected signature/primary axes (incl. high-LTV 교통사고) are never
        reduced; proven low-demand axes shrink toward a probe floor (>=1,
        recoverable); the freed budget flows to supply-starved signature axes.
        Records decisions on the instance for the scan summary + audit, reset
        every build() (single source, like `_structure_blocked_buckets`).
        """
        self._category_demand_adjustments: Dict[str, dict] = {}
        self._category_demand_boosts: Dict[str, int] = {}
        if not quotas or not feedback:
            return quotas

        adjusted = dict(quotas)
        freed = 0
        for category, original_quota in quotas.items():
            original = int(original_quota or 0)
            if original <= 0 or category in CATEGORY_DEMAND_PROTECTED_AXES:
                continue
            stats = feedback.get(f"axis:{category}") or {}
            factor, reason = self._category_demand_factor(stats)
            if factor >= 1.0:
                continue
            new_quota = min(
                original,
                max(CATEGORY_DEMAND_PROBE_FLOOR, int(round(original * factor))),
            )
            if new_quota >= original:
                continue
            adjusted[category] = new_quota
            freed += original - new_quota
            self._category_demand_adjustments[category] = {
                "original": original,
                "adjusted": new_quota,
                "factor": factor,
                "reason": reason,
                "accept_rate": ViralSeedBuilder._as_float(stats.get("staff_accept_rate")),
                "reviewed": int(stats.get("staff_reviewed_count", 0) or 0),
                "total": int(stats.get("total_count", 0) or 0),
            }

        # Redirect freed budget to supply-starved signature axes. Raising the
        # ceiling is harmless when scar/asymmetry supply is thin — selection
        # only ever picks rows that exist (extra slots fall to profile gap-fill
        # exploration, which is the desired remediation for the scar famine).
        if freed > 0:
            boost_targets = [c for c in CATEGORY_DEMAND_SIGNATURE_BOOST_AXES if c in adjusted]
            if boost_targets:
                per_axis = max(1, freed // len(boost_targets))
                for category in boost_targets:
                    add = min(per_axis, CATEGORY_DEMAND_SIGNATURE_BOOST_CAP)
                    if add <= 0:
                        continue
                    adjusted[category] = int(adjusted.get(category, 0)) + add
                    self._category_demand_boosts[category] = add
        return adjusted

    @staticmethod
    def _staff_feedback_bucket(
        keyword_fb: dict,
        axis_lens_fb: dict,
        axis_fb: dict,
    ) -> dict:
        """Most granular bucket with enough staff-review evidence to be meaningful."""
        if int(keyword_fb.get("staff_reviewed_count", 0) or 0) >= 8:
            return keyword_fb
        if int(axis_lens_fb.get("staff_reviewed_count", 0) or 0) >= 12:
            return axis_lens_fb
        if int(axis_fb.get("staff_reviewed_count", 0) or 0) >= 20:
            return axis_fb
        return {}

    @staticmethod
    def _allow_contextual_skin_comparison(keyword: str, blocked_pattern: str) -> bool:
        """Keep scar/acne queries that compare 피부과/laser options with Gyulim-relevant care."""
        if blocked_pattern not in {"피부과", "프락셀"}:
            return False

        category = GYULIM_KEYWORD_PROFILE.normalize_category(
            GYULIM_KEYWORD_PROFILE.detect_category(keyword, default="")
        )
        if category not in {"흉터/여드름흉터", "피부/여드름"}:
            return False

        profile = GYULIM_KEYWORD_PROFILE.profile_for(category)
        if not profile:
            return False

        compact = re.sub(r"\s+", "", keyword.lower())
        has_clinic_anchor = any(
            re.sub(r"\s+", "", anchor.lower()) in compact
            for anchor in (
                tuple(getattr(GYULIM_KEYWORD_PROFILE, "hanbang_indicators", ()))
                + tuple(profile.direct_service_anchors)
            )
        )
        has_comparison_intent = any(
            token in compact
            for token in (
                "말고",
                "대신",
                "비교",
                "차이",
                "한의원",
                "한방",
                "새살침",
                "흉터치료",
                "상담",
            )
        )
        return has_clinic_anchor and has_comparison_intent

    @staticmethod
    def _is_non_hanbang_diet_seed(row: dict) -> bool:
        """Exclude diet seeds for injection/obesity-clinic care outside Gyulim's hanbang lane."""
        category = _canonical_category_for_keyword(str(row.get("keyword") or ""), str(row.get("category") or ""))
        if category != "다이어트":
            return False

        compact = re.sub(r"\s+", "", str(row.get("keyword") or "").lower())
        has_non_hanbang = any(
            re.sub(r"\s+", "", term.lower()) in compact
            for term in DIET_NON_HANBANG_SEED_PATTERNS
        )
        if not has_non_hanbang:
            return False
        has_hanbang_rescue = any(
            re.sub(r"\s+", "", term.lower()) in compact
            for term in DIET_HANBANG_SEED_RESCUE_PATTERNS
        )
        return not has_hanbang_rescue

    @staticmethod
    def _as_float(value: object, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _json_list(value: object) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return [value] if value else []
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item is not None]
        return []

    @staticmethod
    def _viral_readiness_score(row: dict) -> float:
        """Score whether a Pathfinder keyword is suitable for Viral Hunter execution."""
        score = 0.0
        community = ViralSeedBuilder._as_float(row.get("community_signal"))
        conversion = ViralSeedBuilder._as_float(row.get("conversion_signal"))
        profile_action = ViralSeedBuilder._as_float(row.get("profile_action_signal"))
        local_service_fit = ViralSeedBuilder._as_float(row.get("local_service_fit_score"))
        content_actionability = ViralSeedBuilder._as_float(row.get("content_actionability_score"))
        local_surface = ViralSeedBuilder._as_float(row.get("local_surface_score"))
        review_surface = ViralSeedBuilder._as_float(row.get("review_surface_score"))
        availability = ViralSeedBuilder._as_float(row.get("availability_intent_score"))
        payment = ViralSeedBuilder._as_float(row.get("payment_coverage_score"))
        access = ViralSeedBuilder._as_float(row.get("access_convenience_score"))
        verification = ViralSeedBuilder._as_float(row.get("verification_score"))
        pathfinder_novelty = ViralSeedBuilder._as_float(row.get("pathfinder_novelty_score"))
        preferred_surface = str(row.get("preferred_search_surface") or "")
        recommended_type = str(row.get("recommended_content_type") or "")
        review_intent_type = str(row.get("review_intent_type") or "none")
        source_signals = set(ViralSeedBuilder._json_list(row.get("source_signals_json")))

        if community >= 40.0:
            score += min(18.0, community / 4.2)
        if conversion >= 35.0:
            score += min(16.0, conversion / 4.4)
        if profile_action >= 35.0:
            score += min(16.0, profile_action / 4.8)
        if local_service_fit >= 65.0:
            score += min(14.0, (local_service_fit - 55.0) * 0.34)
        if content_actionability >= 60.0:
            score += min(14.0, (content_actionability - 50.0) * 0.28)
        if local_surface >= 55.0:
            score += min(10.0, (local_surface - 45.0) * 0.22)
        if review_surface >= 55.0:
            score += min(8.0, (review_surface - 45.0) * 0.18)
        if availability >= 55.0:
            score += min(7.0, (availability - 45.0) * 0.16)
        if payment >= 55.0:
            score += min(7.0, (payment - 45.0) * 0.16)
        if access >= 55.0:
            score += min(7.0, (access - 45.0) * 0.16)
        if verification >= 65.0:
            score += min(6.0, (verification - 55.0) * 0.12)
        if pathfinder_novelty >= 65.0:
            score += min(5.0, (pathfinder_novelty - 55.0) * 0.10)

        surface_bonus = {
            "hybrid_local_content": 7.0,
            "web_content": 5.0,
            "local_pack": 5.0,
            "profile_action": 6.0,
        }
        score += surface_bonus.get(preferred_surface, 0.0)
        if recommended_type in {"faq_safety", "service_landing", "access_landing"}:
            score += 6.0
        if review_intent_type not in {"", "none"}:
            score += 4.0
        if len(source_signals) >= 2:
            score += 5.0
        elif source_signals:
            score += 2.0
        if "community_demand" in source_signals:
            score += 4.0
        if "profile_action_conversion" in source_signals:
            score += 4.0

        return round(max(0.0, min(100.0, score)), 2)

    @staticmethod
    def _best_learned_quality_rate(
        keyword_fb: dict, axis_lens_fb: dict, structure_fb: dict
    ) -> Tuple[float, int]:
        """Best-available LEARNED viral-workable yield for a seed, preferring the most
        granular bucket with enough evidence (keyword -> axis_lens -> structure).

        The live bridge audit (2026-06-14) found this is the ONLY signal that POSITIVELY
        predicts viral workability — per-(axis,lens)/structure `quality_rate` discriminates
        (community lens 18% vs safety 2.5%; 교통사고 consultation 35%), whereas demand
        grade/KEI ANTI-predict (grade A 3.4% converts WORSE than B 8.3%). Returns
        (quality_rate, evidence_total), or (0.0, 0) when no bucket has enough evidence —
        a no-op that leaves selection on the other signals until data accumulates.
        """
        for bucket, min_total in ((keyword_fb, 8), (axis_lens_fb, 8), (structure_fb, 12)):
            total = int((bucket or {}).get("total_count") or 0)
            if total >= min_total:
                return ViralSeedBuilder._as_float((bucket or {}).get("quality_rate")), total
        return 0.0, 0

    @staticmethod
    def _viral_seed_fit_score(
        row: dict,
        *,
        adjusted_priority: float,
        viral_readiness_score: float,
        execution_risk_penalty: float,
        learned_quality_rate: float = 0.0,
        learned_evidence: int = 0,
    ) -> float:
        """Rank seed keywords for Viral Hunter execution, not just search demand.

        Pathfinder grades are strong demand signals, but Viral Hunter needs posts
        where a natural reply can be found. Community/review signals therefore
        lead this score, while pure local-profile purchase terms are demoted.
        """
        community = ViralSeedBuilder._as_float(row.get("community_signal"))
        conversion = ViralSeedBuilder._as_float(row.get("conversion_signal"))
        profile_action = ViralSeedBuilder._as_float(row.get("profile_action_signal"))
        local_service_fit = ViralSeedBuilder._as_float(row.get("local_service_fit_score"))
        content_actionability = ViralSeedBuilder._as_float(row.get("content_actionability_score"))
        preferred_surface = str(row.get("preferred_search_surface") or "")
        recommended_type = str(row.get("recommended_content_type") or "")
        review_intent_type = str(row.get("review_intent_type") or "none")
        keyword = str(row.get("keyword") or "")
        category = _canonical_category_for_keyword(keyword, str(row.get("category") or ""))
        execution_lens = ViralSeedBuilder._keyword_execution_lens(row)

        score = 0.0
        score += max(0.0, min(100.0, float(viral_readiness_score or 0.0)))
        score += min(80.0, max(0.0, community) * 0.75)
        score += min(30.0, max(0.0, conversion) * 0.35)
        score += min(16.0, max(0.0, profile_action) * 0.18)
        score += min(24.0, max(0.0, float(adjusted_priority or 0.0)) * 0.14)

        if community >= 60.0:
            score += 18.0
        elif community >= 40.0:
            score += 12.0
        elif community <= 5.0:
            score -= 8.0

        if review_intent_type not in {"", "none"}:
            score += 12.0

        if preferred_surface in {"hybrid_local_content", "web_content"}:
            score += 10.0
        elif preferred_surface in {"profile_action", "local_pack"}:
            score += 3.0

        if recommended_type in {"proof_safe_guide", "educational_article"}:
            score += 10.0
        elif recommended_type in {"faq_safety", "service_landing", "access_landing"}:
            score += 4.0

        if local_service_fit >= 75.0 and content_actionability >= 70.0:
            score += 8.0
        elif local_service_fit >= 60.0 and content_actionability >= 55.0:
            score += 4.0

        if execution_lens in {"safety", "availability"} and category in {"체형교정", "리프팅/탄력", "안면비대칭"}:
            score -= 18.0
        if execution_lens == "safety" and category in {"교통사고", "체형교정"}:
            score -= 16.0
        if execution_lens == "cost" and category in {"체형교정", "리프팅/탄력"}:
            score -= 16.0

        score += ViralSeedBuilder._axis_execution_query_bonus(row)

        # Learned viral-workable yield is the ONE signal the live bridge audit found to
        # POSITIVELY predict workability. Trust it directly as a primary term (evidence-
        # gated; 0 -> no-op). 8% -> +12.8, 15% -> +24 (capped).
        if learned_evidence > 0 and learned_quality_rate > 0.0:
            score += min(24.0, learned_quality_rate * 160.0)

        # Demand grade does NOT positively predict viral workability (live: A 3.4% < B 8.3%,
        # S 6.3% < B 8.3% — A/S are ~entirely execution-fit promotions of floor-volume
        # longtails). The old {S:8,A:5,B:2} bonus rewarded the WORSE-converting tier MORE.
        # Reward only GENUINE KEI-earned demand, slightly, so an inflated promotion gets no
        # unearned edge over a real B converter.
        kei_val = ViralSeedBuilder._as_float(row.get("kei"))
        if kei_val >= 500.0:
            score += 4.0
        elif kei_val >= 200.0:
            score += 2.0

        pure_profile_term = (
            community < 15.0
            and conversion < 10.0
            and profile_action < 25.0
            and preferred_surface in {"profile_action", "local_pack"}
            and review_intent_type in {"", "none"}
        )
        if pure_profile_term:
            score -= 18.0

        if community < 20.0 and review_intent_type in {"", "none"}:
            compact = re.sub(r"\s+", "", keyword)
            if any(term in compact for term in ("예약", "진료시간", "주차", "위치")):
                score -= 8.0

        score -= max(0.0, float(execution_risk_penalty or 0.0)) * 0.55
        return round(max(0.0, score), 2)

    @staticmethod
    def _axis_execution_query_bonus(row: dict) -> float:
        """Prefer query shapes that actually produce workable posts for body/asymmetry axes."""
        category = _canonical_category_for_keyword(str(row.get("keyword") or ""), str(row.get("category") or ""))
        if category not in {
            "흉터/여드름흉터",
            "피부/여드름",
            "안면비대칭",
            "체형교정",
            "다이어트",
            "리프팅/탄력",
            "교통사고",
        }:
            return 0.0

        keyword = str(row.get("keyword") or "")
        compact = re.sub(r"\s+", "", keyword.lower())
        preferred_surface = str(row.get("preferred_search_surface") or "")
        community = ViralSeedBuilder._as_float(row.get("community_signal"))

        recommendation_terms = (
            "추천", "어디", "괜찮은곳", "잘하는곳", "좋은곳",
            "해보신", "가보신", "아시는분", "아시는 분",
        )
        clinic_terms = (
            "한의원", "한방", "병원", "추나", "턱관절", "골반교정",
            "자세교정", "체형교정", "안면비대칭교정", "얼굴비대칭교정",
        )
        decision_terms = ("비용", "가격", "얼마", "상담")
        booking_terms = ("예약", "야간", "주차", "진료시간", "위치")
        axis_terms = (
            ("안면비대칭", "얼굴비대칭", "턱관절", "비대칭")
            if category == "안면비대칭"
            else (
                ("다이어트", "비만", "감량", "체중", "식욕", "한약")
                if category == "다이어트"
                else (
                    ("리프팅", "한방리프팅", "매선", "탄력", "주름")
                    if category == "리프팅/탄력"
                    else (
                        ("교통사고", "자동차사고", "입원", "후유증", "자보", "자동차보험")
                        if category == "교통사고"
                        else ("체형교정", "골반교정", "자세교정", "추나")
                    )
                )
            )
        )

        has_recommendation = any(term.replace(" ", "") in compact for term in recommendation_terms)
        has_clinic = any(term in compact for term in clinic_terms)
        has_decision = any(term in compact for term in decision_terms)
        has_booking = any(term in compact for term in booking_terms)
        has_axis = any(term in compact for term in axis_terms)
        region_key = ViralSeedBuilder._keyword_region_key(keyword)
        has_local = region_key != "unknown" or "청주" in compact

        bonus = 0.0
        if has_recommendation:
            bonus += 34.0
            if has_clinic:
                bonus += 24.0
            if "청주" in compact:
                bonus += 8.0
        elif has_decision and has_clinic:
            bonus += 10.0

        if category == "안면비대칭" and "턱관절" in compact and has_recommendation and has_clinic:
            bonus += 22.0
        if category == "흉터/여드름흉터":
            has_scar_axis = any(
                term in compact
                for term in (
                    "여드름흉터", "패인흉터", "모공흉터", "수두흉터", "수술흉터",
                    "상처흉터", "켈로이드", "새살침", "흉터치료", "여드름자국",
                    "붉은자국", "피부재생",
                )
            )
            has_scar_clinic = any(
                term in compact
                for term in ("한의원", "한방", "새살침", "흉터치료", "피부재생", "상담", "치료")
            )
            product_noise = any(
                term in compact
                for term in ("화장품", "연고", "패치", "홈케어", "올리브영", "마스크팩", "압출기")
            )
            western_only = any(term in compact for term in ("피부과", "레이저", "프락셀")) and not has_scar_clinic
            if has_scar_axis and has_scar_clinic and (has_recommendation or has_decision):
                bonus += 24.0
            if "새살침" in compact and (has_recommendation or has_decision or "상담" in compact):
                bonus += 16.0
            if has_scar_axis and has_recommendation:
                bonus += 10.0
            if product_noise and not has_scar_clinic:
                bonus -= 42.0
            if western_only:
                bonus -= 22.0
            if has_booking and not (has_recommendation or has_scar_clinic):
                bonus -= 16.0
        if category == "피부/여드름":
            has_skin_axis = any(
                term in compact
                for term in (
                    "여드름", "성인여드름", "피부질환", "아토피", "지루성피부염",
                    "습진", "두드러기", "건선", "홍조", "피부트러블",
                )
            )
            has_skin_clinic = any(term in compact for term in ("한의원", "한방", "피부질환", "상담", "치료"))
            product_noise = any(
                term in compact
                for term in ("화장품", "폼클렌징", "클렌징", "홈케어", "올리브영", "마스크팩")
            )
            if has_skin_axis and has_skin_clinic and (has_recommendation or has_decision):
                bonus += 18.0
            if has_skin_axis and has_recommendation:
                bonus += 8.0
            if product_noise and not has_skin_clinic:
                bonus -= 34.0
        if category == "안면비대칭":
            has_hanbang_or_tmj = any(
                term in compact
                for term in (
                    "턱관절", "한의원", "한방", "추나", "안면비대칭교정",
                    "얼굴비대칭교정", "턱교정", "비대칭교정",
                )
            )
            if has_axis and has_hanbang_or_tmj and (has_recommendation or has_decision):
                bonus += 18.0
            if "턱관절" in compact and "한의원" in compact and (has_recommendation or has_decision):
                bonus += 12.0
            face_shape_only = any(term in compact for term in ("얼굴형", "윤곽", "페이스라인", "얼굴라인"))
            if face_shape_only and not has_hanbang_or_tmj:
                bonus -= 24.0
            if has_decision and not has_hanbang_or_tmj:
                bonus -= 14.0
            if has_booking and not (has_recommendation or has_hanbang_or_tmj):
                bonus -= 22.0
        if category == "다이어트":
            non_hanbang_medical_noise = any(
                re.sub(r"\s+", "", term.lower()) in compact
                for term in DIET_NON_HANBANG_SEED_PATTERNS
            )
            hanbang_diet_intent = any(
                re.sub(r"\s+", "", term.lower()) in compact
                for term in DIET_HANBANG_SEED_RESCUE_PATTERNS
            )
            has_medical_diet = any(
                term in compact
                for term in (
                    "다이어트한약", "한약", "한의원", "한방", "비만", "감량",
                    "체중", "식욕", "요요", "부종", "처방", "상담", "진료",
                    "치료", "주사", "의원", "병원", "클리닉", "탕약",
                )
            )
            activity_noise = any(
                term in compact
                for term in (
                    "태권도", "째즈댄스", "재즈댄스", "댄스학원", "피트니스",
                    "헬스장", "헬스클럽", "스포랜드", "스포츠센터", "운동할만한곳",
                    "운동추천", "운동루틴", "pt샵", "필라테스", "요가", "복싱장",
                    "수영장", "점핑", "크로스핏",
                )
            )
            if non_hanbang_medical_noise and not hanbang_diet_intent:
                bonus -= 80.0
            if has_medical_diet and (has_recommendation or has_decision):
                bonus += 20.0
            if ("한의원" in compact or "한약" in compact) and (has_recommendation or has_decision):
                bonus += 16.0
            if has_axis and has_local and not (has_medical_diet or has_recommendation or has_decision):
                bonus -= 30.0
            if activity_noise and not has_medical_diet:
                bonus -= 42.0
            if has_booking and not has_medical_diet:
                bonus -= 16.0
        if category == "체형교정" and ("추나" in compact or "체형교정" in compact) and has_recommendation:
            bonus += 8.0
        if category == "체형교정":
            has_body_clinic = any(term in compact for term in ("한의원", "한방", "추나", "체형교정", "골반교정", "자세교정"))
            has_body_axis = any(term in compact for term in ("체형교정", "골반교정", "자세교정", "추나", "일자목", "거북목", "측만"))
            has_safety = any(term in compact for term in ("부작용", "주의사항", "치료기간", "기간", "재발"))
            if has_body_axis and has_body_clinic and (has_recommendation or has_decision):
                bonus += 18.0
            if "추나" in compact and ("한의원" in compact or has_recommendation):
                bonus += 10.0
            if has_decision and not has_recommendation:
                bonus -= 18.0
            if has_safety and not has_recommendation:
                bonus -= 26.0
        if category == "리프팅/탄력":
            has_lifting_clinic = any(term in compact for term in ("한방리프팅", "매선", "한의원", "한방", "리프팅", "탄력", "주름"))
            has_lifting_axis = any(term in compact for term in ("한방리프팅", "매선", "리프팅", "탄력", "주름"))
            has_profile_action = any(term in compact for term in ("예약", "진료시간", "위치", "주차"))
            if has_lifting_axis and has_lifting_clinic and has_recommendation:
                bonus += 20.0
            if has_lifting_axis and has_lifting_clinic and has_decision and has_recommendation:
                bonus += 8.0
            if has_decision and not has_recommendation:
                bonus -= 24.0
            if has_profile_action and not has_recommendation:
                bonus -= 24.0
        if category == "교통사고":
            has_traffic_clinic = any(term in compact for term in ("교통사고", "자동차사고", "자보", "자동차보험", "입원", "후유증", "한의원", "한방병원", "추나"))
            has_traffic_recovery = any(term in compact for term in ("입원", "후유증", "통증", "치료", "자보", "자동차보험"))
            has_safety = any(term in compact for term in ("부작용", "주의사항", "합병증", "치료기간", "기간"))
            has_profile_action = any(term in compact for term in ("예약", "진료시간", "위치", "주차"))
            if has_traffic_clinic and has_traffic_recovery and has_recommendation:
                bonus += 18.0
            if has_traffic_clinic and has_decision and has_recommendation:
                bonus += 8.0
            if has_safety and not has_recommendation:
                bonus -= 30.0
            if has_profile_action and not has_recommendation:
                bonus -= 20.0
        if category == "안면비대칭":
            has_weak_service = (
                not has_recommendation
                and not has_decision
                and not any(term in compact for term in ("턱관절", "한의원", "한방", "추나", "교정", "상담"))
            )
            if has_weak_service:
                bonus -= 28.0
        if has_decision and not has_recommendation:
            bonus -= 8.0

        pure_local_axis = has_local and has_axis and not (has_recommendation or has_clinic or has_decision or has_booking)
        if pure_local_axis:
            bonus -= 34.0

        profile_booking = has_booking and not has_recommendation
        if profile_booking:
            bonus -= 18.0
            if preferred_surface in {"profile_action", "local_pack"}:
                bonus -= 8.0
        elif has_booking and has_recommendation:
            bonus -= 6.0

        testimonial_profile = (
            "후기" in compact
            and not has_recommendation
            and community < 20.0
            and preferred_surface in {"profile_action", "local_pack"}
        )
        if testimonial_profile:
            bonus -= 14.0

        return bonus

    @staticmethod
    def _viral_execution_risk_penalty(row: dict) -> float:
        """Penalize Pathfinder keywords that need research or legal review before viral work."""
        penalty = 0.0
        medical_risk = ViralSeedBuilder._as_float(row.get("medical_ad_risk_score"))
        content_actionability = ViralSeedBuilder._as_float(row.get("content_actionability_score"))
        local_service_fit = ViralSeedBuilder._as_float(row.get("local_service_fit_score"))
        reputation_risk = ViralSeedBuilder._as_float(row.get("reputation_risk_score"))
        competitor_brand_risk = ViralSeedBuilder._as_float(row.get("competitor_brand_risk_score"))
        brand_intent = str(row.get("brand_intent_type") or "generic")
        quality_flags = set(ViralSeedBuilder._json_list(row.get("quality_flags_json")))

        if medical_risk >= 70.0:
            penalty += 32.0
        elif medical_risk >= 50.0:
            penalty += 16.0
        elif medical_risk >= 40.0:
            penalty += 7.0

        if content_actionability and content_actionability < 45.0:
            penalty += 24.0
        elif content_actionability and content_actionability < 60.0:
            penalty += 9.0

        if local_service_fit and local_service_fit < 45.0:
            penalty += 24.0
        elif local_service_fit and local_service_fit < 60.0:
            penalty += 10.0

        if reputation_risk >= 70.0:
            penalty += 22.0
        elif reputation_risk >= 40.0:
            penalty += 9.0

        if competitor_brand_risk >= 70.0:
            penalty += 22.0
        elif competitor_brand_risk >= 50.0:
            penalty += 10.0

        if brand_intent in {"competitor_brand", "competitor_comparison", "own_vs_competitor"}:
            penalty += 12.0
        elif brand_intent == "own_brand_defense":
            penalty += 4.0

        high_risk_flags = {
            "medical_ad_high_risk",
            "medical_ad_high_risk_content",
            "hard_negative_intent",
            "content_low_actionability",
            "local_service_low_fit",
            "service_fit_review",
            "reputation_high_risk",
            "competitor_brand_high_risk",
        }
        review_flags = {
            "medical_ad_review_required",
            "medical_ad_review_content",
            "content_review_required",
            "competitor_brand_policy_review",
            "reputation_review_required",
        }
        penalty += min(18.0, len(quality_flags & high_risk_flags) * 6.0)
        penalty += min(10.0, len(quality_flags & review_flags) * 2.5)

        return round(max(0.0, min(90.0, penalty)), 2)

    def keyword_context_for(self, keywords: Iterable[str]) -> Dict[str, dict]:
        """Return Pathfinder lineage context for exact keywords.

        This is used when Viral Hunter runs with legacy or custom keywords. The
        default curated seed path already carries context, but the fallback path
        still needs scan id, grade, KEI and category attached to discovered
        targets so the queue remains traceable.
        """
        unique_keywords = [
            keyword
            for keyword in dict.fromkeys(str(item).strip() for item in keywords if item)
            if keyword
        ]
        if not unique_keywords:
            return {}

        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                if not self._table_exists(conn, "keyword_insights"):
                    return {}
                columns = self._table_columns(conn, "keyword_insights")
                status_clause = "AND COALESCE(status, 'active') != 'archived'" if "status" in columns else ""
                scan_expr = self._scan_id_expr(columns)
                select_cols = [
                    self._select_expr(columns, "keyword", "''"),
                    self._select_expr(columns, "category", "'기타'"),
                    self._select_expr(columns, "grade", "'C'"),
                    self._select_expr(columns, "search_volume", "0"),
                    self._select_expr(columns, "document_count", "0"),
                    self._select_expr(columns, "kei", "0"),
                    self._select_expr(columns, "priority_v3", "0"),
                    self._select_expr(columns, "search_intent", "'unknown'"),
                    self._select_expr(columns, "longtail_score", "0"),
                    self._select_expr(columns, "business_value_score", "0"),
                    self._select_expr(columns, "high_value_longtail", "0"),
                    self._select_expr(columns, "local_service_fit_score", "0"),
                    self._select_expr(columns, "content_actionability_score", "0"),
                    self._select_expr(columns, "medical_ad_risk_score", "0"),
                    self._select_expr(columns, "community_signal", "0"),
                    self._select_expr(columns, "conversion_signal", "0"),
                    self._select_expr(columns, "profile_action_signal", "0"),
                    self._select_expr(columns, "local_surface_score", "0"),
                    self._select_expr(columns, "review_surface_score", "0"),
                    self._select_expr(columns, "reputation_risk_score", "0"),
                    self._select_expr(columns, "competitor_brand_risk_score", "0"),
                    self._select_expr(columns, "availability_intent_score", "0"),
                    self._select_expr(columns, "payment_coverage_score", "0"),
                    self._select_expr(columns, "access_convenience_score", "0"),
                    self._select_expr(columns, "verification_score", "0"),
                    self._select_expr(columns, "novelty_score", "0", alias="pathfinder_novelty_score"),
                    self._select_expr(columns, "preferred_search_surface", "''"),
                    self._select_expr(columns, "recommended_content_type", "''"),
                    self._select_expr(columns, "brand_intent_type", "'generic'"),
                    self._select_expr(columns, "review_intent_type", "'none'"),
                    self._select_expr(columns, "quality_flags_json", "'[]'"),
                    self._select_expr(columns, "source_signals_json", "'[]'"),
                    scan_expr,
                ]

                rows: List[sqlite3.Row] = []
                for start in range(0, len(unique_keywords), 500):
                    chunk = unique_keywords[start:start + 500]
                    placeholders = ",".join("?" for _ in chunk)
                    rows.extend(
                        conn.execute(
                            f"""
                            SELECT {", ".join(select_cols)}
                            FROM keyword_insights
                            WHERE keyword IN ({placeholders})
                              {status_clause}
                            """,
                            chunk,
                        ).fetchall()
                    )
        except sqlite3.Error:
            return {}

        context: Dict[str, dict] = {}
        for row in rows:
            keyword = row["keyword"]
            if not keyword:
                continue
            context[keyword] = ViralSeed(
                keyword=keyword,
                scan_run_id=int(row["scan_run_id"] or 0),
                category=self._canonical_category_for_keyword(keyword, row["category"] or "기타"),
                grade=row["grade"] or "C",
                search_volume=int(row["search_volume"] or 0),
                document_count=int(row["document_count"] or 0),
                kei=float(row["kei"] or 0),
                priority_v3=float(row["priority_v3"] or 0),
                search_intent=row["search_intent"] or "unknown",
                longtail_score=float(row["longtail_score"] or 0),
                business_value_score=float(row["business_value_score"] or 0),
                high_value_longtail=bool(row["high_value_longtail"] or 0),
                viral_readiness_score=self._viral_readiness_score(dict(row)),
                local_service_fit_score=float(row["local_service_fit_score"] or 0),
                content_actionability_score=float(row["content_actionability_score"] or 0),
                medical_ad_risk_score=float(row["medical_ad_risk_score"] or 0),
                community_signal=float(row["community_signal"] or 0),
                conversion_signal=float(row["conversion_signal"] or 0),
                profile_action_signal=float(row["profile_action_signal"] or 0),
                availability_intent_score=float(row["availability_intent_score"] or 0),
                payment_coverage_score=float(row["payment_coverage_score"] or 0),
                access_convenience_score=float(row["access_convenience_score"] or 0),
                preferred_search_surface=row["preferred_search_surface"] or "",
                recommended_content_type=row["recommended_content_type"] or "",
                brand_intent_type=row["brand_intent_type"] or "generic",
                review_intent_type=row["review_intent_type"] or "none",
                quality_flags_json=row["quality_flags_json"] or "[]",
                source_signals_json=row["source_signals_json"] or "[]",
                execution_lens=self._keyword_execution_lens(dict(row)),
            ).to_context()
        return context

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        try:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
                (table_name,),
            ).fetchone()
        except sqlite3.Error:
            return False
        return row is not None

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
        try:
            return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
        except sqlite3.Error:
            return set()

    @staticmethod
    def _select_expr(columns: set[str], column_name: str, default_sql: str, alias: Optional[str] = None) -> str:
        output_name = alias or column_name
        if column_name in columns:
            return f"COALESCE({column_name}, {default_sql}) AS {output_name}"
        return f"{default_sql} AS {output_name}"

    @staticmethod
    def _scan_id_expr(columns: set[str]) -> str:
        if "last_scan_run_id" in columns and "scan_run_id" in columns:
            return "COALESCE(last_scan_run_id, scan_run_id, 0) AS scan_run_id"
        if "last_scan_run_id" in columns:
            return "COALESCE(last_scan_run_id, 0) AS scan_run_id"
        if "scan_run_id" in columns:
            return "COALESCE(scan_run_id, 0) AS scan_run_id"
        return "0 AS scan_run_id"

    @staticmethod
    def _table_has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
        try:
            rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        except sqlite3.Error:
            return False
        return any(row[1] == column_name for row in rows)

    @staticmethod
    def _select_diverse_rows(
        items: List[dict],
        quota: int,
        max_per_intent: int,
        max_per_cluster: int = DEFAULT_MAX_PER_CLUSTER_PER_CATEGORY,
        max_per_region: int = DEFAULT_MAX_PER_REGION_PER_CATEGORY,
    ) -> List[dict]:
        if quota <= 0 or not items:
            return []

        selected: List[dict] = []
        deferred: List[dict] = []
        lens_deferred: List[dict] = []
        intent_counts: Counter = Counter()
        cluster_counts: Counter = Counter()
        region_counts: Counter = Counter()
        execution_lens_counts: Counter = Counter()
        available_execution_lenses = {
            ViralSeedBuilder._keyword_execution_lens(item.get("row", {}))
            for item in items
            if ViralSeedBuilder._is_viable_execution_lens(item)
        }
        target_execution_lens_count = min(quota, len(available_execution_lenses), 4)

        for item in items:
            intent = item["row"]["search_intent"] or "unknown"
            keyword = item["row"]["keyword"] or ""
            category = item["row"]["category"] or "기타"
            cluster = ViralSeedBuilder._keyword_cluster_key(keyword, category)
            region = ViralSeedBuilder._keyword_region_key(keyword)
            execution_lens = ViralSeedBuilder._keyword_execution_lens(item["row"])
            viable_execution_lens = ViralSeedBuilder._is_viable_execution_lens(item)

            within_intent_cap = intent_counts[intent] < max_per_intent
            within_cluster_cap = cluster_counts[cluster] < max_per_cluster
            within_region_cap = region == "unknown" or region_counts[region] < max_per_region
            needs_new_execution_lens = (
                viable_execution_lens
                and
                target_execution_lens_count > len(execution_lens_counts)
                and execution_lens_counts[execution_lens] > 0
            )

            within_portfolio_caps = within_intent_cap and within_cluster_cap and within_region_cap

            if within_portfolio_caps and not needs_new_execution_lens:
                selected.append(item)
                intent_counts[intent] += 1
                cluster_counts[cluster] += 1
                execution_lens_counts[execution_lens] += 1
                if region != "unknown":
                    region_counts[region] += 1
            elif within_portfolio_caps and needs_new_execution_lens:
                lens_deferred.append(item)
            else:
                deferred.append(item)

            if len(selected) >= quota:
                return selected[:quota]

        if len(selected) < quota:
            fallback = lens_deferred + deferred
            selected.extend(fallback[: quota - len(selected)])

        return selected[:quota]

    @staticmethod
    def _should_suppress_weak_execution_lens(item: dict) -> bool:
        """Drop axis/lens query shapes that repeatedly create non-workable posts."""
        row = item.get("row", {}) if isinstance(item, dict) else {}
        feedback = item.get("axis_lens_feedback", {}) if isinstance(item, dict) else {}
        category = _canonical_category_for_keyword(str(row.get("keyword") or ""), str(row.get("category") or ""))
        lens = ViralSeedBuilder._keyword_execution_lens(row)
        weak_lenses = {
            "흉터/여드름흉터": {"safety"},
            "피부/여드름": {"safety"},
            "체형교정": {"cost", "safety", "availability", "service", "consultation", "community"},
            "리프팅/탄력": {"cost", "safety", "availability", "service", "consultation", "community"},
            "교통사고": {"safety", "availability"},
            "안면비대칭": {"availability", "service", "community"},
        }
        if lens not in weak_lenses.get(category, set()):
            return False

        total = int(feedback.get("total_count", 0) or 0)
        min_evidence = 20 if (category, lens) in {
            ("리프팅/탄력", "community"),
            ("체형교정", "community"),
        } else 40
        if total < min_evidence:
            return False

        keyword = str(row.get("keyword") or "")
        compact = re.sub(r"\s+", "", keyword.lower())
        community = ViralSeedBuilder._as_float(row.get("community_signal"))
        review_intent = str(row.get("review_intent_type") or "none")
        quality_rate = ViralSeedBuilder._as_float(feedback.get("quality_rate"))
        lens_match_rate = ViralSeedBuilder._as_float(feedback.get("lens_match_rate"))
        avg_lens_fit = ViralSeedBuilder._as_float(feedback.get("avg_lens_fit"))

        has_recommendation = any(
            term in compact
            for term in ("추천", "어디", "괜찮은곳", "잘하는곳", "좋은곳", "해보신", "가보신")
        )
        has_user_question = any(term in compact for term in ("후기", "궁금", "있나요", "어때", "문의", "상담"))
        has_clinic_axis = any(
            term in compact
            for term in (
                "한의원", "한방", "추나", "교정", "턱관절", "체형교정", "골반교정",
                "안면비대칭", "한방리프팅", "매선", "교통사고", "입원", "후유증",
            )
        )
        rescue = (
            has_recommendation
            and (has_clinic_axis or community >= 35.0 or review_intent not in {"", "none"})
        )
        if rescue:
            return False

        structurally_weak = quality_rate < 0.03 or (lens_match_rate < 0.04 and avg_lens_fit < 55.0)
        no_workable_signal = not has_recommendation and not (has_user_question and has_clinic_axis and community >= 35.0)
        return structurally_weak or no_workable_signal

    @staticmethod
    def _is_viable_execution_lens(item: dict) -> bool:
        """Do not force a lens into the portfolio when recent outcomes show it is structurally weak."""
        if ViralSeedBuilder._should_suppress_weak_execution_lens(item):
            return False
        row = item.get("row", {}) if isinstance(item, dict) else {}
        feedback = item.get("axis_lens_feedback", {}) if isinstance(item, dict) else {}
        category = _canonical_category_for_keyword(str(row.get("keyword") or ""), str(row.get("category") or ""))
        lens = ViralSeedBuilder._keyword_execution_lens(row)
        total = int(feedback.get("total_count", 0) or 0)
        quality_rate = ViralSeedBuilder._as_float(feedback.get("quality_rate"))
        lens_match_rate = ViralSeedBuilder._as_float(feedback.get("lens_match_rate"))
        avg_lens_fit = ViralSeedBuilder._as_float(feedback.get("avg_lens_fit"))

        weak_axis_lens = (
            total >= 40
            and quality_rate < 0.015
            and lens in {"safety", "availability", "cost", "service"}
            and category in {"체형교정", "리프팅/탄력", "안면비대칭", "교통사고"}
        )
        if weak_axis_lens:
            return False
        if total >= 80 and lens in {"safety", "availability"} and lens_match_rate < 0.03 and avg_lens_fit < 45.0:
            return False
        return True

    @staticmethod
    def _keyword_region_key(keyword: str) -> str:
        compact = re.sub(r"\s+", "", (keyword or "").lower())
        for region in sorted(
            GYULIM_KEYWORD_PROFILE.neighborhoods + GYULIM_KEYWORD_PROFILE.cheongju_regions,
            key=len,
            reverse=True,
        ):
            region_key = re.sub(r"\s+", "", region.lower())
            if region_key and region_key in compact:
                return region
        return "unknown"

    @staticmethod
    def _keyword_cluster_key(keyword: str, category: str = "") -> str:
        compact = re.sub(r"\s+", "", (keyword or "").lower())
        normalized_category = GYULIM_KEYWORD_PROFILE.normalize_category(category)
        profile = GYULIM_KEYWORD_PROFILE.profile_for(normalized_category)
        core = "generic"
        if profile:
            for term in sorted(profile.core_tokens + profile.category_terms, key=len, reverse=True):
                token = re.sub(r"\s+", "", term.lower())
                if token and token in compact:
                    core = term
                    break

        journey = "general"
        if any(term in compact for term in ("주차", "야간", "주말", "진료시간")):
            journey = "access"
        elif any(term in compact for term in ("부작용", "주의사항", "재발", "치료기간", "기간")):
            journey = "safety"
        elif any(term in compact for term in ("후기", "추천", "괜찮은곳", "잘하는곳")):
            journey = "validation"
        elif any(term in compact for term in ("비용", "가격", "상담", "예약")):
            journey = "decision"

        return f"{normalized_category}:{core}:{journey}"

    @staticmethod
    def _keyword_execution_lens(row: dict) -> str:
        """Classify why this seed should be hunted: review, cost, consult, access, or safety."""
        keyword = str(row.get("keyword") or "")
        compact = re.sub(r"\s+", "", keyword.lower())
        review_intent_type = str(row.get("review_intent_type") or "none")
        recommended_type = str(row.get("recommended_content_type") or "")
        preferred_surface = str(row.get("preferred_search_surface") or "")
        source_signals = set(ViralSeedBuilder._json_list(row.get("source_signals_json")))

        def has_terms(*terms: str) -> bool:
            return any(term and re.sub(r"\s+", "", term.lower()) in compact for term in terms)

        if (
            review_intent_type not in {"", "none"}
            or ViralSeedBuilder._as_float(row.get("review_surface_score")) >= 55.0
            or has_terms(
                "\ucd94\ucc9c",
                "\ud6c4\uae30",
                "\uc798\ud558\ub294",
                "\uad1c\ucc2e",
                "\uc5b4\ub514",
                "\uacbd\ud5d8",
                "review",
                "recommend",
            )
        ):
            return "review"

        if (
            ViralSeedBuilder._as_float(row.get("payment_coverage_score")) >= 55.0
            or has_terms(
                "\ube44\uc6a9",
                "\uac00\uaca9",
                "\uc5bc\ub9c8",
                "\uc2e4\ube44",
                "\ubcf4\ud5d8",
                "\uc790\ubcf4",
                "cost",
                "price",
                "insurance",
            )
        ):
            return "cost"

        if (
            ViralSeedBuilder._as_float(row.get("conversion_signal")) >= 45.0
            or has_terms(
                "\uc0c1\ub2f4",
                "\ubb38\uc758",
                "\ucc98\ubc29",
                "\uc9c4\ub2e8",
                "consult",
                "consultation",
                "inquiry",
            )
        ):
            return "consultation"

        if (
            ViralSeedBuilder._as_float(row.get("availability_intent_score")) >= 55.0
            or ViralSeedBuilder._as_float(row.get("access_convenience_score")) >= 55.0
            or has_terms(
                "\uc608\uc57d",
                "\uc57c\uac04",
                "\uc8fc\ub9d0",
                "\uc9c4\ub8cc\uc2dc\uac04",
                "\uc704\uce58",
                "\uadfc\ucc98",
                "booking",
                "appointment",
                "near",
                "hours",
            )
        ):
            return "availability"

        if (
            recommended_type == "faq_safety"
            or has_terms(
                "\ubd80\uc791\uc6a9",
                "\uc8fc\uc758",
                "\uce58\ub8cc\uae30\uac04",
                "\uae30\uac04",
                "\ud1b5\uc99d",
                "\ud68c\ubcf5",
                "\uc7ac\ubc1c",
                "\uc548\uc804",
                "sideeffect",
                "side-effect",
                "recovery",
                "safety",
            )
        ):
            return "safety"

        if (
            ViralSeedBuilder._as_float(row.get("community_signal")) >= 40.0
            or preferred_surface == "hybrid_local_content"
            or "community_demand" in source_signals
        ):
            return "community"

        return "service"

    def _load_keyword_feedback(self) -> Dict[str, dict]:
        """Summarize Viral Hunter outcomes by matched keyword for seed ranking."""
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                if not self._table_exists(conn, "viral_targets"):
                    return {}
                columns = self._table_columns(conn, "viral_targets")
                if "matched_keyword" not in columns and "matched_keywords" not in columns:
                    return {}
                matched_keyword_expr = self._select_expr(columns, "matched_keyword", "''")
                matched_keywords_expr = self._select_expr(columns, "matched_keywords", "'[]'")
                scan_count_expr = "COALESCE(scan_count, 1)"
                if "scan_count" not in columns:
                    scan_count_expr = "1"
                generated_expr = "generated_comment"
                if "generated_comment" not in columns:
                    generated_expr = "''"
                status_expr = "COALESCE(comment_status, 'pending')"
                if "comment_status" not in columns:
                    status_expr = "'pending'"
                score_breakdown_expr = "score_breakdown"
                if "score_breakdown" not in columns:
                    score_breakdown_expr = "'{}'"
                priority_expr = "COALESCE(priority_score, 0)"
                if "priority_score" not in columns:
                    priority_expr = "0"
                matched_category_expr = self._select_expr(columns, "matched_keyword_category", "''")
                target_category_expr = self._select_expr(columns, "category", "''", alias="target_category")
                target_id_expr = self._select_expr(columns, "id", "''", alias="target_id")
                keyword_where = "1=1"
                if "matched_keyword" in columns and "matched_keywords" in columns:
                    keyword_where = """
                    (
                        (matched_keyword IS NOT NULL AND TRIM(matched_keyword) != '')
                        OR (matched_keywords IS NOT NULL AND TRIM(matched_keywords) NOT IN ('', '[]'))
                    )
                    """
                elif "matched_keyword" in columns:
                    keyword_where = "matched_keyword IS NOT NULL AND TRIM(matched_keyword) != ''"
                elif "matched_keywords" in columns:
                    keyword_where = "matched_keywords IS NOT NULL AND TRIM(matched_keywords) NOT IN ('', '[]')"
                rows = conn.execute(
                    f"""
                    SELECT {matched_keyword_expr},
                           {matched_keywords_expr},
                           {status_expr} AS comment_status,
                           {generated_expr} AS generated_comment,
                           {scan_count_expr} AS scan_count,
                           {score_breakdown_expr} AS score_breakdown,
                           {priority_expr} AS priority_score,
                           {matched_category_expr},
                           {target_category_expr},
                           {target_id_expr}
                    FROM viral_targets
                    WHERE {keyword_where}
                    """
                ).fetchall()
                staff_ratings = self._load_staff_rating_map(conn)
        except sqlite3.Error:
            return {}

        buckets: Dict[str, dict] = {}

        def bucket_for(key: str) -> dict:
            return buckets.setdefault(
                key,
                {
                    "total_count": 0,
                    "skipped_count": 0,
                    "final_gate_count": 0,
                    "revisited_count": 0,
                    "qualified_count": 0,
                    "clinic_fit_sum": 0.0,
                    "worksite_efficiency_sum": 0.0,
                    "score_count": 0,
                    "lens_fit_sum": 0.0,
                    "lens_score_count": 0,
                    "lens_match_count": 0,
                    "lens_mismatch_count": 0,
                    "priority_sum": 0.0,
                    "priority_count": 0,
                    "staff_positive_count": 0,
                    "staff_negative_count": 0,
                },
            )

        for row in rows:
            keywords = self._feedback_keywords_from_row(row["matched_keyword"], row["matched_keywords"])
            if not keywords:
                continue

            comment_status = str(row["comment_status"] or "pending")
            generated_comment = str(row["generated_comment"] or "")
            scan_count = int(row["scan_count"] or 1)
            score_breakdown = self._parse_score_breakdown(row["score_breakdown"])
            clinic_fit = self._score_breakdown_number(score_breakdown, "clinic_treatment_fit_score")
            worksite_efficiency = self._score_breakdown_number(score_breakdown, "worksite_efficiency_score")
            lens_fit = self._score_breakdown_number(score_breakdown, "pathfinder_lens_fit_score")
            lens_tier = str(score_breakdown.get("pathfinder_lens_fit_tier") or "")
            source_keyword = normalize_seed_keyword_text(
                str(score_breakdown.get("pathfinder_source_keyword") or "").strip() or keywords[0]
            )
            raw_category = row["matched_keyword_category"] or row["target_category"] or ""
            category = self._canonical_category_for_keyword(source_keyword, raw_category)
            execution_lens = str(score_breakdown.get("pathfinder_execution_lens") or "").strip().lower()
            if not execution_lens:
                execution_lens = self._keyword_execution_lens({"keyword": source_keyword, "category": category})
            priority_score = float(row["priority_score"] or 0.0)
            is_final_gate = generated_comment.startswith("final_gate:") or comment_status.startswith("filtered_out_")
            is_skipped = comment_status == "skipped"
            target_rating = staff_ratings.get(str(row["target_id"] or ""), "")
            is_staff_positive = (
                comment_status in {"posted", "completed", "approved"} or target_rating == "good"
            )
            is_staff_negative = not is_staff_positive and (is_skipped or target_rating == "bad")
            is_lens_match = lens_fit >= 70.0 or lens_tier == "strong"
            is_lens_mismatch = (0.0 < lens_fit < 45.0) or lens_tier == "mismatch"
            is_qualified = is_qualified_viral_outcome(
                comment_status, clinic_fit, worksite_efficiency, priority_score
            )

            feedback_keys: List[str] = []
            for keyword in keywords:
                norm_key = self._keyword_feedback_key(keyword)
                if not norm_key:
                    continue
                feedback_keys.extend([keyword, f"norm:{norm_key}"])
            if category:
                feedback_keys.append(f"axis:{category}")
                if execution_lens:
                    feedback_keys.append(f"axis_lens:{category}:{execution_lens}")
            structure = keyword_structure_features(source_keyword, category)
            feedback_keys.append(str(structure["structure_key"]))

            for key in dict.fromkeys(feedback_keys):
                bucket = bucket_for(key)
                bucket["total_count"] += 1
                bucket["skipped_count"] += 1 if is_skipped else 0
                bucket["final_gate_count"] += 1 if is_final_gate else 0
                bucket["revisited_count"] += 1 if scan_count > 1 else 0
                bucket["qualified_count"] += 1 if is_qualified else 0
                if clinic_fit or worksite_efficiency:
                    bucket["clinic_fit_sum"] += clinic_fit
                    bucket["worksite_efficiency_sum"] += worksite_efficiency
                    bucket["score_count"] += 1
                if lens_fit:
                    bucket["lens_fit_sum"] += lens_fit
                    bucket["lens_score_count"] += 1
                bucket["lens_match_count"] += 1 if is_lens_match else 0
                bucket["lens_mismatch_count"] += 1 if is_lens_mismatch else 0
                if priority_score:
                    bucket["priority_sum"] += priority_score
                    bucket["priority_count"] += 1
                bucket["staff_positive_count"] += 1 if is_staff_positive else 0
                bucket["staff_negative_count"] += 1 if is_staff_negative else 0

        feedback: Dict[str, dict] = {}
        for key, bucket in buckets.items():
            total = int(bucket["total_count"] or 0)
            skipped = int(bucket["skipped_count"] or 0)
            revisited = int(bucket["revisited_count"] or 0)
            qualified = int(bucket["qualified_count"] or 0)
            score_count = int(bucket["score_count"] or 0)
            lens_score_count = int(bucket["lens_score_count"] or 0)
            priority_count = int(bucket["priority_count"] or 0)
            staff_positive = int(bucket["staff_positive_count"] or 0)
            staff_negative = int(bucket["staff_negative_count"] or 0)
            staff_reviewed = staff_positive + staff_negative
            feedback[key] = {
                "total_count": total,
                "skipped_count": skipped,
                "final_gate_count": int(bucket["final_gate_count"] or 0),
                "skip_rate": (skipped / total) if total else 0.0,
                "revisited_count": revisited,
                "revisit_rate": (revisited / total) if total else 0.0,
                "qualified_count": qualified,
                "quality_rate": (qualified / total) if total else 0.0,
                "lens_match_count": int(bucket["lens_match_count"] or 0),
                "lens_mismatch_count": int(bucket["lens_mismatch_count"] or 0),
                "lens_match_rate": (float(bucket["lens_match_count"]) / total) if total else 0.0,
                "lens_mismatch_rate": (float(bucket["lens_mismatch_count"]) / total) if total else 0.0,
                "avg_lens_fit": (float(bucket["lens_fit_sum"]) / lens_score_count) if lens_score_count else 0.0,
                "avg_clinic_fit": (float(bucket["clinic_fit_sum"]) / score_count) if score_count else 0.0,
                "avg_worksite_efficiency": (
                    float(bucket["worksite_efficiency_sum"]) / score_count
                ) if score_count else 0.0,
                "avg_priority_score": (float(bucket["priority_sum"]) / priority_count) if priority_count else 0.0,
                "staff_positive_count": staff_positive,
                "staff_negative_count": staff_negative,
                "staff_reviewed_count": staff_reviewed,
                "staff_accept_rate": (staff_positive / staff_reviewed) if staff_reviewed else 0.0,
            }
        return feedback

    def _load_staff_rating_map(self, conn) -> Dict[str, str]:
        """Latest explicit staff rating per target ('good'/'bad'; 'needs_edit' is neutral)."""
        try:
            if not self._table_exists(conn, "viral_target_feedback"):
                return {}
            rows = conn.execute(
                """
                SELECT target_id, rating
                FROM viral_target_feedback
                WHERE rating IN ('good', 'bad')
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()
        except sqlite3.Error:
            return {}
        ratings: Dict[str, str] = {}
        for row in rows:
            target_id = row["target_id"] if hasattr(row, "keys") else row[0]
            rating = row["rating"] if hasattr(row, "keys") else row[1]
            if target_id and rating:
                ratings[str(target_id)] = str(rating)
        return ratings

    @staticmethod
    def _parse_score_breakdown(value: object) -> dict:
        if isinstance(value, dict):
            return value
        if not value:
            return {}
        try:
            parsed = json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _score_breakdown_number(score_breakdown: dict, key: str) -> float:
        try:
            value = score_breakdown.get(key, 0)
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

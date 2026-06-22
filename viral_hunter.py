#!/usr/bin/env python3
"""
Viral Hunter - 네이버 통합 검색 기반 커뮤니티 댓글 응대 시스템

기능:
- 네이버 카페 + 블로그 + 지식인 통합 검색
- 댓글 가능 게시물 필터링
- AI 기반 맞춤 댓글 생성
- 우선순위 기반 타겟 관리

Phase: Viral Hunter V1
"""

import sys
import os

# [고도화 A-1] Sentry 에러 모니터링
try:
    from scrapers.sentry_init import init_sentry
    init_sentry("viral_hunter")
except Exception:
    pass
import json
import socket
import sqlite3
socket.setdefaulttimeout(15)
import time
import re
import math
import hashlib
import logging
import argparse
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple
from datetime import datetime, timedelta
from urllib.parse import quote, urljoin
import requests
from bs4 import BeautifulSoup

# Path setup
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Add backend to path for ai_client import
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'marketing_bot_web', 'backend'))

from db.database import DatabaseManager
from utils import ConfigManager, logger
from utils.json_io import atomic_write_json
from services.ai_client import ai_generate, ai_generate_korean
from core_services.viral_url_canonicalizer import canonicalize_viral_url
from core_services.viral_seed_builder import (
    ViralSeedBuilder,
    canonical_category_for_keyword,
    keyword_structure_features,
    strip_region_tokens,
    strip_transactional_suffix,
)
from core_services.pathfinder_insight_broker import load_pathfinder_prompt_context
from core_services.gyulim_keyword_profile import ACTIVE_KEYWORD_PROFILE as GYULIM_KEYWORD_PROFILE
from core_services.semantic_axis_matcher import SemanticAxisMatcher, semantic_discovery_enabled

# 의미기반 진료축 매처 싱글톤 — 기본은 비활성(opt-in env + 모델 필요)이라 no-op.
# 테스트는 이 전역을 주입형 fake 매처로 교체해 모델 없이 의미 구제를 검증한다.
_SEMANTIC_AXIS_MATCHER = SemanticAxisMatcher()

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')


AI_CATEGORY_MIN_QUOTAS: Dict[str, int] = {
    "흉터/여드름흉터": 50,
    "피부": 50,
    "교통사고": 50,
    "다이어트": 40,
    "안면비대칭": 25,
    "체형교정": 20,
    "경쟁사_역공략": 20,
    "리프팅/탄력": 10,
}

AI_CATEGORY_FLOOR_PRIORITY: Tuple[str, ...] = (
    "흉터/여드름흉터",
    "안면비대칭",
    "피부/여드름",
    "다이어트",
    "교통사고",
    "체형교정",
    "리프팅/탄력",
    "경쟁사_역공략",
)

AI_CATEGORY_ALIASES: Dict[str, str] = {
    "흉터": "흉터/여드름흉터",
    "여드름흉터": "흉터/여드름흉터",
    "피부": "피부/여드름",
    "비대칭/교정": "안면비대칭",
    "통증/디스크": "체형교정",
}


def _canonical_ai_category(raw_category: str) -> str:
    aliased = AI_CATEGORY_ALIASES.get(raw_category, raw_category)
    return GYULIM_KEYWORD_PROFILE.normalize_category(aliased)


def _ai_quota_category(target: "ViralTarget") -> str:
    """Return the category bucket used for balanced AI target selection."""
    category = _canonical_ai_category(str(getattr(target, "category", "") or ""))
    matched_category = _canonical_ai_category(str(getattr(target, "matched_keyword_category", "") or ""))
    generic_categories = {"", "기타", "general", "unknown", "uncategorized"}
    core_handoff_categories = {
        "흉터/여드름흉터", "피부/여드름", "교통사고", "다이어트", "안면비대칭", "체형교정", "리프팅/탄력"
    }
    if matched_category in core_handoff_categories:
        return matched_category
    if category not in generic_categories:
        return category
    if matched_category not in generic_categories:
        return matched_category
    return _canonical_ai_category("기타")


PATHFINDER_AXIS_COMPANION_GENERIC_TERMS: Dict[str, set[str]] = {
    "흉터/여드름흉터": {
        "흉터", "여드름흉터", "흉터치료", "흉터새살침", "새살침", "피부재생",
    },
    "피부/여드름": {
        "피부", "피부관리", "피부질환", "피부트러블", "트러블", "여드름",
    },
    "다이어트": {
        "다이어트", "다이어트한약", "다이어트 한약", "한방다이어트",
        "비만", "체중", "감량",
    },
    "안면비대칭": {
        "안면비대칭", "얼굴비대칭", "턱비대칭", "비대칭교정", "안면교정",
    },
    "체형교정": {
        "체형교정", "자세교정", "척추교정",
    },
    "리프팅/탄력": {
        "리프팅", "탄력", "한방리프팅", "매선리프팅",
    },
    "교통사고": {
        "교통사고", "자동차사고", "교통사고한의원", "자동차사고한의원",
    },
}

PATHFINDER_AXIS_SHORT_SPECIFIC_TERMS: Dict[str, set[str]] = {
    "다이어트": {"산후", "요요"},
    "교통사고": {"입원", "자보"},
}

PATHFINDER_AXIS_COMPANION_VARIANT_PREFIX: Dict[str, str] = {
    "흉터/여드름흉터": "axis_scar",
    "피부/여드름": "axis_skin",
    "다이어트": "axis_diet",
    "안면비대칭": "axis_asymmetry",
    "체형교정": "axis_body",
    "리프팅/탄력": "axis_lifting",
    "교통사고": "axis_traffic",
}


def _compact_query_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def _pathfinder_axis_specific_terms_for_keyword(keyword: str, category: str, limit: int = 2) -> List[str]:
    """Specific treatment/context terms from the active Pathfinder profile."""
    profile = GYULIM_KEYWORD_PROFILE.profile_for(category)
    if not profile:
        return []

    compact_keyword = _compact_query_text(keyword)
    generic_terms = {
        _compact_query_text(term)
        for term in PATHFINDER_AXIS_COMPANION_GENERIC_TERMS.get(category, set())
    }
    low_value_terms = {
        _compact_query_text(term)
        for term in getattr(profile, "low_business_value_terms", ()) or ()
    }
    region_terms = {
        _compact_query_text(term)
        for term in (
            list(getattr(GYULIM_KEYWORD_PROFILE, "cheongju_regions", ()) or ())
            + list(getattr(GYULIM_KEYWORD_PROFILE, "neighborhoods", ()) or ())
            + list(getattr(GYULIM_KEYWORD_PROFILE, "nearby_regions", ()) or ())
        )
    }
    generic_anchor_terms = {
        _compact_query_text(term)
        for term in ("한의원", "한방", "한약", "치료", "상담", "예약", "추천", "후기")
    }
    short_specific_terms = {
        _compact_query_text(term)
        for term in PATHFINDER_AXIS_SHORT_SPECIFIC_TERMS.get(category, set())
    }

    ordered_terms: List[str] = []
    ordered_terms.extend(getattr(profile, "longtail_contexts", ()) or ())
    ordered_terms.extend(getattr(profile, "core_tokens", ()) or ())
    ordered_terms.extend(getattr(profile, "category_terms", ()) or ())

    scored: List[Tuple[int, int, str]] = []
    seen: set[str] = set()
    for index, raw_term in enumerate(ordered_terms):
        term = str(raw_term or "").strip()
        compact = _compact_query_text(term)
        if not compact or compact in seen:
            continue
        if compact not in compact_keyword:
            continue
        if len(compact) < 3 and compact not in short_specific_terms:
            continue
        if compact in generic_terms or compact in low_value_terms:
            continue
        if compact in region_terms or compact in generic_anchor_terms:
            continue
        seen.add(compact)
        scored.append((index, -len(compact), term))

    scored.sort()
    return [term for _, __, term in scored[:max(0, int(limit or 0))]]


def _normalized_ai_category_quotas(quotas: Dict[str, int]) -> Dict[str, int]:
    normalized: Dict[str, int] = {}
    for raw_category, quota in (quotas or {}).items():
        category = _canonical_ai_category(raw_category)
        normalized[category] = normalized.get(category, 0) + int(quota or 0)
    return normalized


def _ordered_ai_floor_categories(quotas: Dict[str, int]) -> List[str]:
    priority_index = {category: idx for idx, category in enumerate(AI_CATEGORY_FLOOR_PRIORITY)}

    def sort_key(category: str) -> Tuple[int, float, int, str]:
        profile = GYULIM_KEYWORD_PROFILE.profile_for(category)
        weight = float(getattr(profile, "strategic_weight", 1.0) or 1.0) if profile else 1.0
        return (
            priority_index.get(category, len(priority_index)),
            -weight,
            -int(quotas.get(category, 0) or 0),
            category,
        )

    return sorted(
        [category for category, quota in (quotas or {}).items() if int(quota or 0) > 0],
        key=sort_key,
    )


def _ai_target_execution_lens(target: "ViralTarget") -> str:
    breakdown = getattr(target, "score_breakdown", None) or {}
    if not isinstance(breakdown, dict):
        breakdown = {}
    lens = str(breakdown.get("pathfinder_execution_lens") or "").strip().lower()
    return lens or "service"


def _ai_target_breakdown_float(target: "ViralTarget", key: str) -> float:
    breakdown = getattr(target, "score_breakdown", None) or {}
    if not isinstance(breakdown, dict):
        return 0.0
    try:
        return float(breakdown.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _ai_target_selection_score(target: "ViralTarget") -> float:
    """AI budget ordering that favors Pathfinder-fit, clinic-fit candidates."""
    priority = float(getattr(target, "priority_score", 0.0) or 0.0)
    axis_fit = _ai_target_breakdown_float(target, "pathfinder_axis_fit_score")
    lens_fit = _ai_target_breakdown_float(target, "pathfinder_lens_fit_score")
    clinic_fit = _ai_target_breakdown_float(target, "clinic_treatment_fit_score")
    worksite_fit = _ai_target_breakdown_float(target, "worksite_efficiency_score")
    readiness = _ai_target_breakdown_float(target, "pathfinder_viral_readiness_score")
    actionability = _ai_target_breakdown_float(target, "pathfinder_content_actionability_score")

    fit_bonus = 0.0
    if axis_fit:
        fit_bonus += max(-18.0, min(18.0, (axis_fit - 55.0) * 0.16))
    if lens_fit:
        fit_bonus += max(-14.0, min(14.0, (lens_fit - 55.0) * 0.12))
    if clinic_fit:
        fit_bonus += max(-16.0, min(16.0, (clinic_fit - 55.0) * 0.12))
    if worksite_fit:
        fit_bonus += max(-12.0, min(12.0, (worksite_fit - 55.0) * 0.10))
    if readiness:
        fit_bonus += max(-6.0, min(8.0, (readiness - 60.0) * 0.08))
    if actionability:
        fit_bonus += max(-6.0, min(8.0, (actionability - 60.0) * 0.08))
    return round(priority + fit_bonus, 4)


def _ai_target_sort_key(target: "ViralTarget") -> Tuple[float, float, float, float, float, str]:
    return (
        _ai_target_selection_score(target),
        float(getattr(target, "priority_score", 0.0) or 0.0),
        _ai_target_breakdown_float(target, "pathfinder_axis_fit_score"),
        _ai_target_breakdown_float(target, "pathfinder_lens_fit_score"),
        _ai_target_breakdown_float(target, "clinic_treatment_fit_score"),
        str(getattr(target, "url", "") or getattr(target, "id", "")),
    )


def _ai_target_venue_key(target: "ViralTarget") -> str:
    """카페/블로거 venue 식별자(author). KIN(author='')·미상은 캡 제외 — 읽기 큐의
    `_venue_diversity_key` 와 동일 규칙(공급자-venue 게이트 의도적 제외와 일관)."""
    author = str(getattr(target, "author", "") or "").strip().lower()
    platform = str(getattr(target, "platform", "") or "").lower()
    if not author or platform in {"kin", "naver_kin"}:
        return ""
    return author


def _select_category_floor_targets(
    targets: List["ViralTarget"],
    *,
    category: str,
    quota: int,
    selected_urls: set[str],
) -> List["ViralTarget"]:
    """Pick a category floor while preserving Pathfinder execution-lens variety."""
    if quota <= 0:
        return []

    candidates = [
        target
        for target in targets
        if (target.url or target.id) not in selected_urls
        and _ai_quota_category(target) == category
    ]
    if not candidates:
        return []
    candidates = sorted(candidates, key=_ai_target_sort_key, reverse=True)

    picked: List[ViralTarget] = []
    local_urls: set[str] = set()
    covered_lenses: set[str] = set()

    # First reserve one high-ranked target per non-generic lens. This keeps
    # Pathfinder's cost/consultation/safety discoveries from being crowded out
    # by one dominant review lane inside the same treatment axis.
    for target in candidates:
        if len(picked) >= quota:
            break
        lens = _ai_target_execution_lens(target)
        if lens == "service" or lens in covered_lenses:
            continue
        url = target.url or target.id
        picked.append(target)
        local_urls.add(url)
        covered_lenses.add(lens)

    for target in candidates:
        if len(picked) >= quota:
            break
        url = target.url or target.id
        if url in local_urls:
            continue
        picked.append(target)
        local_urls.add(url)

    return picked


def split_ai_targets_with_category_floor(
    targets: List["ViralTarget"],
    top_n: int,
    category_min_quotas: Optional[Dict[str, int]] = None,
) -> Tuple[List["ViralTarget"], List["ViralTarget"]]:
    """Split AI candidates while keeping minority core categories represented.

    `targets` is already score-sorted. A pure global top-N can starve categories
    like asymmetry/body correction when skin or traffic-accident results flood
    the scan. Reserve a small floor per core category, then fill the rest by the
    original priority order.
    """
    if top_n <= 0:
        return [], list(targets)
    if len(targets) <= top_n:
        return list(targets), []

    quotas = _normalized_ai_category_quotas(category_min_quotas or AI_CATEGORY_MIN_QUOTAS)
    selected: List[ViralTarget] = []
    selected_urls: set[str] = set()
    per_category_floor_cap = max(1, math.ceil(top_n * 0.4)) if len(quotas) > 1 else top_n
    selected_category_counts: Dict[str, int] = {}
    ordered_categories = _ordered_ai_floor_categories(quotas)

    # First pass: when the AI budget is small, guarantee one candidate for each
    # available strategic axis before any high-volume category consumes its full
    # floor. This prevents scar/asymmetry/diet/skin handoffs from being crowded
    # out by whichever category appears first in the quota map.
    for category in ordered_categories:
        if len(selected) >= top_n:
            break
        target = next(
            iter(
                _select_category_floor_targets(
                    targets,
                    category=category,
                    quota=1,
                    selected_urls=selected_urls,
                )
            ),
            None,
        )
        if target is None:
            continue
        selected.append(target)
        selected_urls.add(target.url or target.id)
        selected_category_counts[category] = selected_category_counts.get(category, 0) + 1

    for category in ordered_categories:
        if len(selected) >= top_n:
            break
        quota = int(quotas.get(category, 0) or 0)
        already_selected = int(selected_category_counts.get(category, 0) or 0)
        remaining_quota = min(quota, per_category_floor_cap, top_n - len(selected))
        remaining_quota = max(0, remaining_quota - already_selected)
        for target in _select_category_floor_targets(
            targets,
            category=category,
            quota=remaining_quota,
            selected_urls=selected_urls,
        ):
            selected.append(target)
            selected_urls.add(target.url or target.id)
            selected_category_counts[category] = selected_category_counts.get(category, 0) + 1
            if len(selected) >= top_n:
                break

    # 잔여 AI 예산 채우기 — venue(카페/블로거) 다양성 선호. 카테고리 플로어(축 보장)는
    # 위에서 이미 확정됐고, 잔여 채움이 순수 점수순이면 한 메가카페가 AI 예산을 독점해
    # pending 풀 자체가 한 venue 로 쏠린다(라이브: cafe pending ~50%가 상위 2개 카페).
    # pass1 은 venue 캡을 선호하되, pass2 로 예산을 굶기지 않게 보충한다 — 읽기 큐의
    # 하드 캡과 달리 발견 풀 활용/AI 예산 소진이 우선이다(과도한 한-venue 작업은 읽기
    # 큐의 venue 캡이 막는다). KIN(author='')은 캡 제외.
    ranked_rest = sorted(targets, key=_ai_target_sort_key, reverse=True)
    venue_counts: Dict[str, int] = {}
    for target in selected:
        vk = _ai_target_venue_key(target)
        if vk:
            venue_counts[vk] = venue_counts.get(vk, 0) + 1
    ai_venue_cap = max(3, math.ceil(top_n * 0.15))
    for target in ranked_rest:
        if len(selected) >= top_n:
            break
        url = target.url or target.id
        if url in selected_urls:
            continue
        vk = _ai_target_venue_key(target)
        if vk and venue_counts.get(vk, 0) >= ai_venue_cap:
            continue
        selected.append(target)
        selected_urls.add(url)
        if vk:
            venue_counts[vk] = venue_counts.get(vk, 0) + 1
    if len(selected) < top_n:
        for target in ranked_rest:
            if len(selected) >= top_n:
                break
            url = target.url or target.id
            if url in selected_urls:
                continue
            selected.append(target)
            selected_urls.add(url)

    selected.sort(key=_ai_target_sort_key, reverse=True)
    rest = [target for target in targets if (target.url or target.id) not in selected_urls]
    return selected, rest


# ============================================
# 데이터 클래스
# ============================================
@dataclass
class ViralTarget:
    """바이럴 마케팅 타겟"""
    platform: str           # cafe, blog, kin
    url: str
    title: str
    content_preview: str = ""
    matched_keywords: List[str] = field(default_factory=list)
    category: str = "기타"
    is_commentable: bool = True
    generated_comment: str = ""
    priority_score: float = 0.0
    author: str = ""
    date_str: str = ""
    like_count: int = 0
    comment_count: int = 0
    view_count: int = 0
    comment_status: str = "pending"
    discovered_at: str = ""
    first_seen_at: str = ""
    last_scanned_at: str = ""
    scan_count: int = 0
    source_scan_run_id: int = 0
    matched_keyword_grade: str = ""
    matched_keyword_kei: float = 0.0
    matched_keyword_priority: float = 0.0
    matched_keyword_category: str = ""
    exposure_score: float = 0.0
    workability_score: float = 0.0
    conversion_fit_score: float = 0.0
    score_breakdown: Dict[str, Any] = field(default_factory=dict)
    search_sort: str = ""
    search_rank: int = 0
    search_start: int = 0
    search_total: int = 0
    sort_appearances: List[str] = field(default_factory=list)
    ai_reviewed: bool = False
    ai_infiltration_score: float = 0.0
    ai_post_type: str = ""
    ai_competitor: bool = False
    ai_competitor_name: str = ""
    canonical_url: str = ""

    def __post_init__(self):
        # [Q11/2026-04-28] 카테고리 자동 정규화 — title까지 보고 미용 카테고리(다이어트/피부/비대칭) 정확히 분류.
        # 시드 키워드만 보면 "산후조리원/지역명"이 모두 "기타"로 떨어지는 문제 해결.
        try:
            from services.category_normalizer import normalize_category, STANDARD_CATEGORIES
        except ImportError:
            return

        if self.category and self.category != "기타" and self.category in STANDARD_CATEGORIES:
            return  # 명시적 표준 카테고리 그대로

        # 비표준 값이면 정규화
        if self.category and self.category != "기타":
            self.category = normalize_category(self.category)
            if self.category in STANDARD_CATEGORIES and self.category != "기타":
                return

        # "기타" 폴백 — title + matched_keywords[0] 둘 다 시도, 미용 카테고리 우선
        candidates = []
        if self.title:
            candidates.append(self.title)
        if self.matched_keywords:
            candidates.append(self.matched_keywords[0])

        for raw in candidates:
            cat = normalize_category(raw)
            if cat != "기타":
                self.category = cat
                return
        self.category = "기타"

    @property
    def id(self) -> str:
        """URL 기반 고유 ID 생성"""
        identity_url = canonicalize_viral_url(self.url) or self.url
        return hashlib.md5(identity_url.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        """DB 저장용 딕셔너리 변환"""
        return {
            'id': self.id,
            'platform': self.platform,
            'url': self.url,
            'canonical_url': canonicalize_viral_url(self.url),
            'title': self.title,
            'content_preview': self.content_preview,
            'matched_keywords': self.matched_keywords,
            'category': self.category,
            'is_commentable': self.is_commentable,
            'generated_comment': self.generated_comment,
            'priority_score': self.priority_score,
            'author': self.author,
            'date_str': self.date_str,
            'like_count': self.like_count,
            'comment_count': self.comment_count,
            'view_count': self.view_count,
            'comment_status': self.comment_status,
            'discovered_at': self.discovered_at,
            'first_seen_at': self.first_seen_at,
            'last_scanned_at': self.last_scanned_at,
            'scan_count': self.scan_count,
            'source_scan_run_id': self.source_scan_run_id,
            'matched_keyword_grade': self.matched_keyword_grade,
            'matched_keyword_kei': self.matched_keyword_kei,
            'matched_keyword_priority': self.matched_keyword_priority,
            'matched_keyword_category': self.matched_keyword_category,
            'exposure_score': self.exposure_score,
            'workability_score': self.workability_score,
            'conversion_fit_score': self.conversion_fit_score,
            'score_breakdown': self.score_breakdown,
            'search_sort': self.search_sort,
            'search_rank': self.search_rank,
            'search_start': self.search_start,
            'search_total': self.search_total,
            'sort_appearances': self.sort_appearances,
            'ai_reviewed': self.ai_reviewed,
            'ai_infiltration_score': self.ai_infiltration_score,
            'ai_post_type': self.ai_post_type,
            'ai_competitor': self.ai_competitor,
            'ai_competitor_name': self.ai_competitor_name,
        }


# ============================================
# 검색 결과 캐시 클래스
# ============================================
class SearchCache:
    """
    검색 결과 캐싱 (SQLite 기반, 24시간 유효)
    - 동일 키워드 재검색 방지
    - API 호출 70% 감소 효과
    """

    def __init__(self, cache_hours: int = 24):
        self.cache_hours = cache_hours
        self.config = ConfigManager()
        self.cache_path = os.path.join(self.config.root_dir, 'db', 'search_cache.db')
        self._init_db()

    def _init_db(self):
        """캐시 DB 초기화"""
        import sqlite3
        try:
            with sqlite3.connect(self.cache_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS search_cache (
                        cache_key TEXT PRIMARY KEY,
                        platform TEXT,
                        keyword TEXT,
                        results TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_created ON search_cache(created_at)")
                # 오래된 캐시 정리
                conn.execute(f"DELETE FROM search_cache WHERE created_at < datetime('now', '-{self.cache_hours} hours')")
                conn.commit()
        except Exception as e:
            logger.debug(f"SearchCache init failed: {e}")

    def get(self, platform: str, keyword: str) -> Optional[List[dict]]:
        """캐시에서 검색 결과 조회"""
        import sqlite3
        cache_key = f"{platform}:{keyword}"
        try:
            with sqlite3.connect(self.cache_path) as conn:
                cursor = conn.execute(
                    f"SELECT results FROM search_cache WHERE cache_key = ? AND created_at > datetime('now', '-{self.cache_hours} hours')",
                    (cache_key,)
                )
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
        except Exception as e:
            logger.debug(f"SearchCache get failed: {e}")
        return None

    def set(self, platform: str, keyword: str, results: List[dict]):
        """검색 결과 캐시 저장"""
        import sqlite3
        cache_key = f"{platform}:{keyword}"
        try:
            with sqlite3.connect(self.cache_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO search_cache (cache_key, platform, keyword, results) VALUES (?, ?, ?, ?)",
                    (cache_key, platform, keyword, json.dumps(results, ensure_ascii=False))
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"SearchCache set failed: {e}")

    def get_stats(self) -> dict:
        """캐시 통계"""
        import sqlite3
        try:
            with sqlite3.connect(self.cache_path) as conn:
                total = conn.execute("SELECT COUNT(*) FROM search_cache").fetchone()[0]
                valid = conn.execute(
                    f"SELECT COUNT(*) FROM search_cache WHERE created_at > datetime('now', '-{self.cache_hours} hours')"
                ).fetchone()[0]
                return {"total": total, "valid": valid}
        except Exception:
            return {"total": 0, "valid": 0}


# ============================================
# 네이버 통합 검색 클래스
# ============================================
class NaverUnifiedSearch:
    """
    네이버 카페 + 블로그 + 지식인 통합 검색

    기존 naver_serp_analyzer.py 패턴 재사용:
    - HTTP 세션 관리
    - User-Agent 로테이션
    - Rate limiting
    - Exponential backoff 재시도
    - 429/503 에러 자동 대기
    - 검색 결과 캐싱 (24시간)
    """

    # 공식 Naver Search API 엔드포인트
    API_ENDPOINTS = {
        'cafe': 'https://openapi.naver.com/v1/search/cafearticle.json',
        'blog': 'https://openapi.naver.com/v1/search/blog.json',
        'kin':  'https://openapi.naver.com/v1/search/kin.json',
    }
    SORT_OPTIONS = {
        'cafe': ('sim', 'date'),
        'blog': ('sim', 'date'),
        'kin': ('sim', 'point', 'date'),
    }
    SORT_WEIGHTS = {
        'sim': 28,
        'point': 24,
        'date': 12,
    }

    def __init__(self, delay: float = 0.3, max_retries: int = 3, use_cache: bool = True):
        self.delay = delay
        self.max_retries = max_retries
        self.session = requests.Session()
        self._last_call = 0
        self._request_count = 0
        self._error_count = 0
        self._cache_hits = 0

        # 캐싱
        self.use_cache = use_cache
        self.cache = SearchCache() if use_cache else None

        # 네이버 공식 API 키 로테이션 (최대 5개)
        cfg = ConfigManager()
        self.api_keys = cfg.get_api_key_list("NAVER_SEARCH_KEYS")
        if not self.api_keys:
            cid = cfg.get_api_key("NAVER_CLIENT_ID")
            sec = cfg.get_api_key("NAVER_CLIENT_SECRET")
            if cid and sec:
                self.api_keys = [{"id": cid, "secret": sec}]
        self._key_index = 0
        if self.api_keys:
            logger.info(f"✅ Naver Search API 키 {len(self.api_keys)}개 로드 (공식 API 모드)")
        else:
            logger.error("❌ Naver Search API 키가 없습니다 (.env NAVER_SEARCH_CLIENT_ID_1 등 확인)")

        # 하위 호환용 (사용 안 하지만 get_stats 등이 참조)
        self.user_agents = []
        self.ua_index = 0
        self._consecutive_empty_results = 0
        self._total_searches = 0
        self._successful_searches = 0
        self._is_blocked = False
        self._adaptive_delay = delay

    def _rotate_key(self):
        if self.api_keys:
            self._key_index = (self._key_index + 1) % len(self.api_keys)

    def _api_headers(self) -> dict:
        key = self.api_keys[self._key_index]
        return {
            "X-Naver-Client-Id": key["id"],
            "X-Naver-Client-Secret": key["secret"],
        }

    @staticmethod
    def _strip_html(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', '', text)
        # HTML entity 디코드
        import html as _html
        return _html.unescape(text).strip()

    def _api_fetch(self, platform: str, keyword: str, display: int = 100,
                   start: int = 1, sort: str = "date") -> List[dict]:
        """공식 API 호출. 실패 시 키 로테이션 + 재시도."""
        if not self.api_keys:
            return []
        endpoint = self.API_ENDPOINTS.get(platform)
        if not endpoint:
            return []

        params = {"query": keyword, "display": display, "start": start, "sort": sort}
        max_attempts = min(len(self.api_keys) + 1, 6)

        for attempt in range(max_attempts):
            self._rate_limit()
            self._request_count += 1
            try:
                r = self.session.get(endpoint, headers=self._api_headers(),
                                     params=params, timeout=10)
                if r.status_code == 200:
                    return r.json().get("items", [])
                if r.status_code in (401, 403, 429):
                    logger.warning(f"[API] {platform} '{keyword}' {r.status_code} → 키 로테이션")
                    self._error_count += 1
                    self._rotate_key()
                    time.sleep(0.5)
                    continue
                logger.warning(f"[API] {platform} '{keyword}' {r.status_code}: {r.text[:120]}")
                self._error_count += 1
                break
            except requests.exceptions.Timeout:
                self._error_count += 1
                time.sleep(1.0)
            except requests.exceptions.RequestException as e:
                self._error_count += 1
                logger.warning(f"[API] 요청 예외 {platform}/{keyword}: {e}")
                break
        return []

    def _calculate_dynamic_limit(self, keyword: str, platform: str, search_volume: int = None) -> int:
        """
        [Phase 2 개선] 검색량 및 키워드 특성 기반 동적 수집 제한 계산

        Args:
            keyword: 검색 키워드
            platform: 플랫폼 (cafe, blog, kin)
            search_volume: 월간 검색량 (있으면 활용)

        Returns:
            동적으로 계산된 max_results 값
        """
        # 플랫폼별 기본값
        base_limits = {
            'cafe': 200,
            'blog': 200,
            'kin': 100,
        }
        base_limit = base_limits.get(platform, 200)

        # 검색량 기반 조정
        if search_volume:
            if search_volume >= 1000:
                base_limit = int(base_limit * 2.5)  # 고인기 키워드: 2.5배
            elif search_volume >= 300:
                base_limit = int(base_limit * 1.75)
            elif search_volume >= 100:
                base_limit = int(base_limit * 1.25)

        # 의도 키워드 포함 시 추가 확장
        intent_keywords = ['추천', '후기', '비교', '가격', '비용', '어디', '질문']
        if any(kw in keyword for kw in intent_keywords):
            base_limit = int(base_limit * 1.3)  # 정보탐색형 +30%

        # 플랫폼별 최대값 제한
        max_limits = {
            'cafe': 500,
            'blog': 500,
            'kin': 300,
        }

        return min(base_limit, max_limits.get(platform, 500))

    def _get_headers(self) -> dict:
        """헤더 생성 (User-Agent 로테이션)"""
        ua = self.user_agents[self.ua_index % len(self.user_agents)]
        self.ua_index += 1

        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://www.naver.com/",
            "Cache-Control": "no-cache",
        }

    def _rate_limit(self):
        """API 호출 간격 제어 (적응형)"""
        elapsed = time.time() - self._last_call
        if elapsed < self._adaptive_delay:
            time.sleep(self._adaptive_delay - elapsed)
        self._last_call = time.time()

    def _validate_response(self, response: requests.Response, platform: str) -> bool:
        """
        🛡️ 응답 검증: 네이버가 차단/빈 페이지를 반환하는지 체크

        검증 항목:
        1. HTML 최소 길이 (10KB 이상) - 롱테일 키워드는 응답이 작을 수 있음
        2. "검색결과가 없습니다" 메시지 확인 (정상 응답)
        3. 네이버 검색 페이지 기본 구조 존재 (느슨하게)

        Returns:
            True: 정상 응답 (결과 없음 포함), False: 차단 의심
        """
        if not response or not response.text:
            return False

        html = response.text

        # 1. 최소 길이 체크 (10KB 미만이면 명백히 비정상)
        if len(html) < 10000:  # 10KB 미만
            logger.warning(f"⚠️ 응답이 너무 작습니다: {len(html):,} bytes (차단 의심)")
            return False

        # 2. "검색결과가 없습니다" 메시지가 있으면 정상 (결과 없는 것뿐)
        no_result_indicators = [
            '검색결과가 없습니다',
            '검색 결과가 없습니다',
            '결과가 없습니다',
            'no_result',
            '_result_none'
        ]

        if any(indicator in html for indicator in no_result_indicators):
            logger.debug(f"[{platform}] 검색 결과 없음 (정상 응답)")
            return True

        # 3. 주요 검색 결과 영역 또는 네이버 기본 구조 체크
        # 롱테일 키워드는 main_pack이 없을 수 있으므로 느슨하게 체크
        naver_indicators = [
            'main_pack', 'api_subject_bx', 'total_wrap',
            'naver.com', 'search_list', 'result_list',
            'content_search', 'section_head'
        ]

        found_any = any(indicator in html for indicator in naver_indicators)

        if not found_any:
            logger.warning(f"⚠️ 네이버 검색 페이지 구조를 찾을 수 없습니다 (차단 의심)")
            return False

        return True

    def _check_blocking_status(self, results_count: int):
        """
        🛡️ 차단 상태 감지 및 적응형 대응

        연속으로 N개 키워드에서 0개 결과 → 차단 의심
        - 5개 연속 0개: 경고 + delay 증가
        - 10개 연속 0개: 차단 플래그 + 장시간 대기
        """
        self._total_searches += 1

        if results_count > 0:
            self._successful_searches += 1
            self._consecutive_empty_results = 0
            # 성공률이 높으면 delay 감소
            if self._successful_searches > 10:
                self._adaptive_delay = max(1.0, self._adaptive_delay * 0.95)
        else:
            self._consecutive_empty_results += 1

            error_rate = self._error_count / max(1, self._request_count)

            if self._consecutive_empty_results == 5:
                logger.info(
                    "Naver API returned zero results for 5 consecutive keyword/platform checks; "
                    "treating this as sparse long-tail demand unless API errors rise."
                )

            elif self._consecutive_empty_results >= 10:
                if error_rate >= 0.20:
                    self._is_blocked = True
                    logger.warning(
                        "Naver block suspected from zero-result streak plus API errors "
                        f"(empty={self._consecutive_empty_results}, error_rate={error_rate:.1%})."
                    )
                    self._adaptive_delay = max(self._adaptive_delay, self.delay * 3)
                    self._is_blocked = False
                else:
                    logger.info(
                        "Zero-result streak reached 10 with low API error rate; "
                        "continuing without long sleep."
                    )
                    self._consecutive_empty_results = 0

    def _request_with_retry(self, url: str, params: dict) -> Optional[requests.Response]:
        """
        Exponential backoff 재시도 로직

        - 429 Too Many Requests: 60초 대기 후 재시도
        - 503 Service Unavailable: 30초 대기 후 재시도
        - 기타 에러: 점진적 대기 (2초, 4초, 8초)
        """
        for attempt in range(self.max_retries):
            try:
                self._rate_limit()
                self._request_count += 1

                response = self.session.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    timeout=20
                )

                # 429 Too Many Requests
                if response.status_code == 429:
                    wait_time = 60 + (attempt * 30)  # 60초, 90초, 120초
                    logger.warning(f"⚠️ 429 Too Many Requests - {wait_time}초 대기 중...")
                    self._error_count += 1
                    time.sleep(wait_time)
                    continue

                # 503 Service Unavailable
                if response.status_code == 503:
                    wait_time = 30 + (attempt * 15)  # 30초, 45초, 60초
                    logger.warning(f"⚠️ 503 Service Unavailable - {wait_time}초 대기 중...")
                    self._error_count += 1
                    time.sleep(wait_time)
                    continue

                # 403 Forbidden (IP 차단 가능성)
                if response.status_code == 403:
                    if attempt == 0:
                        # 첫 번째 403: 즉시 5분 대기
                        wait_time = 300  # 5분
                        logger.error(f"🚨 403 Forbidden - 네이버 IP 차단 감지!")
                        logger.error(f"   → {wait_time}초 (5분) 대기 후 재시도...")
                    else:
                        # 재시도에도 403: 10분 대기
                        wait_time = 600  # 10분
                        logger.error(f"🚨 403 Forbidden 재발생 - {wait_time}초 (10분) 대기...")

                    self._error_count += 1
                    self._is_blocked = True  # 차단 플래그 설정
                    time.sleep(wait_time)
                    self._is_blocked = False
                    self._adaptive_delay = self.delay * 5  # delay 5배 증가
                    continue

                response.raise_for_status()
                return response

            except requests.exceptions.Timeout:
                wait_time = 5 * (attempt + 1)
                logger.warning(f"⚠️ Timeout - {wait_time}초 후 재시도 ({attempt+1}/{self.max_retries})")
                self._error_count += 1
                time.sleep(wait_time)

            except requests.exceptions.RequestException as e:
                wait_time = 2 ** (attempt + 1)  # 2초, 4초, 8초
                logger.warning(f"⚠️ Request failed: {e} - {wait_time}초 후 재시도 ({attempt+1}/{self.max_retries})")
                self._error_count += 1
                time.sleep(wait_time)

        logger.error(f"❌ 최대 재시도 횟수 초과: {url}")
        return None

    def get_stats(self) -> dict:
        """API 호출 통계 (차단 감지 정보 포함)"""
        cache_stats = self.cache.get_stats() if self.cache else {"total": 0, "valid": 0}
        success_rate = (self._successful_searches / max(1, self._total_searches)) * 100

        return {
            "requests": self._request_count,
            "errors": self._error_count,
            "cache_hits": self._cache_hits,
            "cache_entries": cache_stats.get("valid", 0),
            "error_rate": f"{(self._error_count / max(1, self._request_count)) * 100:.1f}%",
            # 🛡️ 차단 감지 정보
            "total_searches": self._total_searches,
            "successful_searches": self._successful_searches,
            "success_rate": f"{success_rate:.1f}%",
            "consecutive_failures": self._consecutive_empty_results,
            "is_blocked": self._is_blocked,
            "current_delay": f"{self._adaptive_delay:.1f}초"
        }

    def _cache_namespace(self, platform: str) -> str:
        return f"{platform}:sortmix_v2"

    def _sorts_for_platform(self, platform: str) -> Tuple[str, ...]:
        return self.SORT_OPTIONS.get(platform, ("date",))

    def _estimate_exposure_score(
        self,
        platform: str,
        rank: int,
        sort_type: str,
        appearances: int = 1,
        view_count: int = 0,
        like_count: int = 0,
        comment_count: int = 0,
    ) -> float:
        rank = max(1, int(rank or 999))
        if rank <= 100:
            rank_score = max(0.0, 82.0 - ((rank - 1) * 0.75))
        else:
            rank_score = max(0.0, 15.0 - ((rank - 100) * 0.08))

        sort_bonus = self.SORT_WEIGHTS.get(sort_type, 10)
        cross_sort_bonus = min(26.0, max(0, appearances - 1) * 13.0)
        platform_bonus = {
            'cafe': 8.0,
            'kin': 6.0,
            'blog': 4.0,
            'instagram': 8.0,
            'tiktok': 8.0,
            'youtube': 7.0,
        }.get(platform, 4.0)

        engagement_bonus = (
            math.log10(max(0, view_count) + 1) * 7.0
            + math.log10(max(0, like_count) + 1) * 6.0
            + math.log10(max(0, comment_count) + 1) * 10.0
        )
        return round(min(150.0, rank_score + sort_bonus + cross_sort_bonus + platform_bonus + engagement_bonus), 2)

    def _merge_sort_results(self, targets: List[ViralTarget], max_results: int) -> List[ViralTarget]:
        merged: Dict[str, ViralTarget] = {}

        for target in targets:
            if not target.url:
                continue
            if not target.sort_appearances:
                target.sort_appearances = [target.search_sort] if target.search_sort else []

            current = merged.get(target.url)
            if current is None:
                merged[target.url] = target
                continue

            for keyword in target.matched_keywords:
                if keyword not in current.matched_keywords:
                    current.matched_keywords.append(keyword)

            appearances = list(dict.fromkeys((current.sort_appearances or []) + (target.sort_appearances or [])))
            current.sort_appearances = appearances

            if target.exposure_score > (current.exposure_score or 0):
                current.title = target.title or current.title
                current.content_preview = target.content_preview or current.content_preview
                current.search_sort = target.search_sort or current.search_sort
                current.search_rank = target.search_rank or current.search_rank
                current.search_start = target.search_start or current.search_start
                current.author = target.author or current.author
                current.date_str = target.date_str or current.date_str

            best_rank = min(
                [r for r in [current.search_rank or 0, target.search_rank or 0] if r > 0],
                default=current.search_rank or target.search_rank or 0,
            )
            current.search_rank = best_rank
            current.exposure_score = max(
                current.exposure_score or 0,
                target.exposure_score or 0,
                self._estimate_exposure_score(
                    current.platform,
                    best_rank or 999,
                    current.search_sort or target.search_sort or "date",
                    appearances=len(appearances),
                ),
            )
            current.score_breakdown = {
                **(current.score_breakdown or {}),
                "exposure": current.exposure_score,
                "sort_appearances": float(len(appearances)),
            }

        merged_targets = list(merged.values())
        merged_targets.sort(
            key=lambda t: (
                t.exposure_score or 0,
                -(t.search_rank or 9999),
                t.priority_score or 0,
            ),
            reverse=True,
        )
        return merged_targets[:max_results]

    def _api_collect_multi_sort(self, platform: str, keyword: str, max_results: int) -> List[ViralTarget]:
        all_targets: List[ViralTarget] = []
        for sort_type in self._sorts_for_platform(platform):
            all_targets.extend(self._api_collect(platform, keyword, max_results, sort_type=sort_type))
        return self._merge_sort_results(all_targets, max_results)

    def _api_collect(self, platform: str, keyword: str, max_results: int,
                     sort_type: str = "date") -> List[ViralTarget]:
        """공식 API로 N개까지 수집. 페이지당 display=100, start는 1/101/201…"""
        targets: List[ViralTarget] = []
        seen = set()
        display = 100
        # Naver API는 start + display ≤ 1000까지만 허용
        max_results = min(max_results, 900)

        start = 1
        while len(targets) < max_results and start <= 1000:
            fetch_n = min(display, max_results - len(targets), 1001 - start)
            if fetch_n <= 0:
                break
            items = self._api_fetch(platform, keyword, display=fetch_n, start=start, sort=sort_type)
            if not items:
                break

            before_add_count = len(targets)

            for idx, item in enumerate(items):
                link = item.get('link', '') or ''
                if not link or link in seen:
                    continue
                title = self._strip_html(item.get('title', ''))
                if not title or len(title) < 5:
                    continue
                desc = self._strip_html(item.get('description', ''))

                if platform == 'cafe':
                    author = item.get('cafename', '') or ''
                elif platform == 'blog':
                    author = item.get('bloggername', '') or ''
                else:
                    author = ''

                seen.add(link)
                rank = start + idx
                exposure_score = self._estimate_exposure_score(platform, rank, sort_type)
                targets.append(ViralTarget(
                    platform=platform,
                    url=link,
                    title=title,
                    content_preview=desc[:300],
                    matched_keywords=[keyword],
                    author=author,
                    date_str=item.get('postdate', '') or '',
                    exposure_score=exposure_score,
                    search_sort=sort_type,
                    search_rank=rank,
                    search_start=start,
                    sort_appearances=[sort_type],
                    score_breakdown={"exposure": exposure_score},
                ))
                if len(targets) >= max_results:
                    break

            # 이번 배치에서 추가된 유효 타겟이 하나도 없다면, 무의미한 페이징 호출 중단을 위해 조기 탈출
            if len(targets) == before_add_count:
                logger.info(f"[{platform}] '{keyword}' {sort_type} 스캔 조기 종료: 신규 유효 타겟 없음 (누적: {len(targets)}/{max_results})")
                break

            if len(items) < fetch_n:
                break  # 결과 끝
            start += fetch_n

        return targets

    def search_cafe(self, keyword: str, max_results: int = 200, max_pages: int = 10) -> List[ViralTarget]:
        """
        네이버 카페 전용 검색 (페이지네이션 지원)

        Args:
            keyword: 검색 키워드
            max_results: 최대 결과 수
            max_pages: 최대 페이지 수 (1페이지=10개)
        """
        # 캐시 체크
        if self.use_cache and self.cache:
            cached = self.cache.get(self._cache_namespace("cafe"), keyword)
            if cached:
                self._cache_hits += 1
                logger.debug(f"[Cafe] '{keyword}' 캐시 히트")
                # id는 property이므로 제거 후 복원
                return [ViralTarget(**{k: v for k, v in item.items() if k != 'id'}) for item in cached]

        targets = self._api_collect_multi_sort("cafe", keyword, max_results)

        # 캐시 저장
        if self.use_cache and self.cache and targets:
            self.cache.set(self._cache_namespace("cafe"), keyword, [t.to_dict() for t in targets])

        self._check_blocking_status(len(targets))
        logger.info(f"[Cafe] '{keyword}' -> {len(targets)}개 발견")
        return targets

    def search_blog(self, keyword: str, max_results: int = 200, max_pages: int = 10) -> List[ViralTarget]:
        """
        네이버 블로그 검색 (페이지네이션 지원)

        Args:
            keyword: 검색 키워드
            max_results: 최대 결과 수
            max_pages: 최대 페이지 수
        """
        # 캐시 체크
        if self.use_cache and self.cache:
            cached = self.cache.get(self._cache_namespace("blog"), keyword)
            if cached:
                self._cache_hits += 1
                logger.debug(f"[Blog] '{keyword}' 캐시 히트")
                # id는 property이므로 제거 후 복원
                return [ViralTarget(**{k: v for k, v in item.items() if k != 'id'}) for item in cached]

        targets = self._api_collect_multi_sort("blog", keyword, max_results)

        if self.use_cache and self.cache and targets:
            self.cache.set(self._cache_namespace("blog"), keyword, [t.to_dict() for t in targets])

        self._check_blocking_status(len(targets))
        logger.info(f"[Blog] '{keyword}' -> {len(targets)}개 발견")
        return targets

    def search_kin(self, keyword: str, max_results: int = 100, max_pages: int = 5) -> List[ViralTarget]:
        """
        네이버 지식인 검색 (페이지네이션 지원)

        Args:
            keyword: 검색 키워드
            max_results: 최대 결과 수
            max_pages: 최대 페이지 수
        """
        # 캐시 체크
        if self.use_cache and self.cache:
            cached = self.cache.get(self._cache_namespace("kin"), keyword)
            if cached:
                self._cache_hits += 1
                logger.debug(f"[Kin] '{keyword}' 캐시 히트")
                # id는 property이므로 제거 후 복원
                return [ViralTarget(**{k: v for k, v in item.items() if k != 'id'}) for item in cached]

        targets = self._api_collect_multi_sort("kin", keyword, max_results)

        if self.use_cache and self.cache and targets:
            self.cache.set(self._cache_namespace("kin"), keyword, [t.to_dict() for t in targets])

        self._check_blocking_status(len(targets))
        logger.info(f"[Kin] '{keyword}' -> {len(targets)}개 발견")
        return targets

    def search_all(
        self,
        keyword: str,
        max_per_platform: int = 100,
        include_blog: bool = True,
        platform_limits: Optional[Dict[str, int]] = None,
    ) -> List[ViralTarget]:
        """카페·블로그·지식인 통합 검색.

        [Q10] blog는 본인 광고 글 비율이 높고 게시 전환율 0.02%로 효율 낮음.
        다만 검색 노출 커버리지를 위해 기본 수집하되 플랫폼 가중치는 낮게 둔다.
        """
        all_targets = []
        platform_limits = platform_limits or {}
        cafe_limit = int(platform_limits.get("cafe", max_per_platform) or 0)
        blog_limit = int(platform_limits.get("blog", max_per_platform) or 0)
        kin_limit = int(platform_limits.get("kin", max_per_platform) or 0)

        cafe_results = self.search_cafe(keyword, cafe_limit) if cafe_limit > 0 else []
        all_targets.extend(cafe_results)

        blog_results: List[ViralTarget] = []
        if include_blog and blog_limit > 0:
            blog_results = self.search_blog(keyword, blog_limit)
            all_targets.extend(blog_results)

        kin_results = self.search_kin(keyword, kin_limit) if kin_limit > 0 else []
        all_targets.extend(kin_results)

        logger.info(
            f"[통합] '{keyword}' -> 총 {len(all_targets)}개 "
            f"(카페:{len(cafe_results)}, 블로그:{len(blog_results)}, 지식인:{len(kin_results)})"
        )
        return all_targets


# ============================================
# 공개 표면 본문 취득 (KIN/blog — 로그인 불필요)
# ============================================
NAVER_BODY_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}


def blog_postview_url(url: str) -> Optional[str]:
    """blog.naver.com 글 URL을 iframe 없는 PostView URL로 변환. 비대상이면 None."""
    text = url or ""
    if "blog.naver.com" not in text:
        return None
    if "PostView.naver" in text and "blogId=" in text and "logNo=" in text:
        return text
    m = re.search(r"blog\.naver\.com/([^/?#]+)/(\d{6,})", text)
    if not m:
        m = re.search(r"blogId=([^&#]+).*?logNo=(\d{6,})", text)
    if not m:
        return None
    return f"https://blog.naver.com/PostView.naver?blogId={m.group(1)}&logNo={m.group(2)}"


def _fetched_node_text(node) -> str:
    if node is None:
        return ""
    text = node.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def extract_kin_body_from_html(
    html: str,
    max_answers: int = 2,
    question_chars: int = 600,
    answer_chars: int = 260,
) -> str:
    """지식인 상세 HTML에서 질문 본문 + 상위 답변 요약을 추출.

    답변 텍스트를 함께 싣는 이유: KIN 광고/업체 답변 신호 대부분이 질문이 아닌
    답변 영역에 있어, snippet만으로는 광고 게이트와 AI 판정이 보지 못한다.
    """
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return ""
    question = _fetched_node_text(soup.select_one(".questionDetail"))[:question_chars]
    parts: List[str] = []
    if question:
        parts.append(question)
    for idx, node in enumerate(soup.select(".answerDetail")[:max_answers], 1):
        answer = _fetched_node_text(node)[:answer_chars]
        if answer:
            parts.append(f"[기존답변{idx}] {answer}")
    return " ".join(parts).strip()


def extract_blog_body_from_html(html: str, max_chars: int = 900) -> str:
    """블로그 PostView HTML에서 본문 텍스트를 추출 (스마트에디터/구버전 모두)."""
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return ""
    node = soup.select_one(".se-main-container") or soup.select_one("#postViewArea")
    return _fetched_node_text(node)[:max_chars]


# 게시일 표기: "2026.05.25", "2026. 6. 10. 2:49" 등 (라이브 검증 2026-06-13)
NAVER_POST_DATE_RE = re.compile(r"(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})")


def _yyyymmdd_from_text(text: str) -> str:
    m = NAVER_POST_DATE_RE.search(text or "")
    if not m:
        return ""
    try:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        datetime(year, month, day)
    except ValueError:
        return ""
    return f"{year:04d}{month:02d}{day:02d}"


def extract_kin_post_date_from_html(html: str) -> str:
    """지식인 상세 HTML에서 질문 작성일을 YYYYMMDD로 추출 (없으면 빈 문자열).

    질문 메타: <span class="infoItem"><span class="blind">작성일</span>2026.05.25</span>
    검색 API는 KIN 게시일을 주지 않아 sim 정렬로 발굴된 수년 전 질문이
    '방금 발견 = 신선' 보너스를 받아왔다 — enrichment에서 실제 날짜를 복원한다.
    """
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return ""
    for node in soup.select(".infoItem"):
        blind = node.select_one(".blind")
        if blind and "작성일" in blind.get_text():
            return _yyyymmdd_from_text(node.get_text(" ", strip=True))
    m = re.search(r"작성일</span>\s*([0-9.\s]{8,14})", html)
    if m:
        return _yyyymmdd_from_text(m.group(1))
    return ""


def extract_kin_view_count_from_html(html: str) -> Optional[int]:
    """지식인 질문 메타의 '조회수 N'을 추출 (없으면 None)."""
    if not html:
        return None
    m = re.search(r"조회수[^0-9]{0,10}([\d,]+)", html)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def extract_blog_post_date_from_html(html: str) -> str:
    """블로그 PostView HTML에서 게시일을 YYYYMMDD로 추출 (없으면 빈 문자열)."""
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return ""
    node = soup.select_one(".se_publishDate") or soup.select_one(".date")
    return _yyyymmdd_from_text(_fetched_node_text(node))


def cafe_article_api_url(url: str) -> Optional[str]:
    """카페 글 URL을 공개 article JSON API URL로 변환. 비대상이면 None.

    공개 카페는 로그인 없이 200 + contentHtml을 주고, 멤버 전용 카페는 401을
    반환한다(라이브 검증: 청주맘 계열 공개 / cjcjmommy 멤버 전용) — 호출자는
    빈 결과로 fail-soft한다.
    """
    text = url or ""
    if "cafe.naver.com" not in text:
        return None
    m = re.search(r"clubid=(\d+).*?articleid=(\d+)", text, re.IGNORECASE)
    if m:
        return (
            "https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/"
            f"cafes/{m.group(1)}/articles/{m.group(2)}?useCafeId=true"
        )
    m = re.search(r"cafe\.naver\.com/(?:ca-fe/web/cafes/)?([\w.-]+)(?:/articles)?/(\d{3,})", text)
    if not m:
        return None
    return (
        "https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/"
        f"cafes/{m.group(1)}/articles/{m.group(2)}?useCafeId=false"
    )


def _cafe_article_from_json(json_text: str) -> Dict[str, Any]:
    """카페 article API 응답(JSON)에서 result.article dict를 추출 (실패 시 {})."""
    if not json_text:
        return {}
    try:
        data = json.loads(json_text)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    article = (data.get("result") or {}).get("article") or {}
    return article if isinstance(article, dict) else {}


def extract_cafe_body_from_json(json_text: str, max_chars: int = 900) -> str:
    """카페 article API 응답(JSON)에서 본문 텍스트를 추출."""
    article = _cafe_article_from_json(json_text)
    content = article.get("contentHtml") or article.get("content") or ""
    if not content:
        return ""
    try:
        soup = BeautifulSoup(str(content), "html.parser")
    except Exception:
        return ""
    return _fetched_node_text(soup)[:max_chars]


def extract_cafe_post_date_from_json(json_text: str) -> str:
    """카페 article API의 writeDate(epoch ms)를 YYYYMMDD로 변환 (없으면 빈 문자열)."""
    write_date = _cafe_article_from_json(json_text).get("writeDate")
    try:
        millis = float(write_date)
    except (TypeError, ValueError):
        return ""
    if millis <= 0:
        return ""
    try:
        return datetime.fromtimestamp(millis / 1000.0).strftime("%Y%m%d")
    except (OSError, OverflowError, ValueError):
        return ""


def fetch_naver_post_detail(
    url: str,
    platform: str,
    timeout: float = 8.0,
    fetcher=None,
) -> Dict[str, Any]:
    """KIN/blog/공개 cafe 페이지에서 본문 + 게시일 + 참여 지표를 한 번의 fetch로 취득.

    반환: {"body": str, "posted_date": "YYYYMMDD"|"" , "comment_count": int|None,
           "view_count": int|None}. 실패는 빈 값으로 fail-soft.
    게시일/참여 지표가 필요한 이유: 검색 API는 KIN/cafe 게시일을 주지 않아
    타이밍 윈도우 게이트가 구조적으로 장님이었다 (sim 정렬이 끌어온 수년 전
    글이 '발견 직후 = 신선' 보너스를 받음 — 라이브 검증 2026-06-13).
    """
    platform = (platform or "").lower()
    detail: Dict[str, Any] = {
        "body": "", "posted_date": "", "comment_count": None, "view_count": None,
    }

    def _default_fetch(target_url: str) -> str:
        headers = dict(NAVER_BODY_FETCH_HEADERS)
        if "apis.naver.com" in target_url:
            headers["Referer"] = "https://cafe.naver.com/"
        response = requests.get(target_url, headers=headers, timeout=timeout)
        if response.status_code != 200:
            return ""
        return response.text or ""

    fetch = fetcher or _default_fetch
    try:
        if platform == "kin":
            html = fetch(url)
            detail["body"] = extract_kin_body_from_html(html)
            detail["posted_date"] = extract_kin_post_date_from_html(html)
            detail["view_count"] = extract_kin_view_count_from_html(html)
            if html:
                try:
                    answer_nodes = BeautifulSoup(html, "html.parser").select(".answerDetail")
                    detail["comment_count"] = len(answer_nodes)
                except Exception:
                    pass
        elif platform == "blog":
            postview = blog_postview_url(url)
            if postview:
                html = fetch(postview)
                detail["body"] = extract_blog_body_from_html(html)
                detail["posted_date"] = extract_blog_post_date_from_html(html)
        elif platform in {"cafe", "naver_cafe"}:
            api_url = cafe_article_api_url(url)
            if api_url:
                payload = fetch(api_url)
                detail["body"] = extract_cafe_body_from_json(payload)
                detail["posted_date"] = extract_cafe_post_date_from_json(payload)
                article = _cafe_article_from_json(payload)
                for src_key, dst_key in (("commentCount", "comment_count"), ("readCount", "view_count")):
                    try:
                        detail[dst_key] = int(article.get(src_key))
                    except (TypeError, ValueError):
                        pass
    except Exception as e:
        logger.debug(f"본문 취득 실패({platform}, {url[:60]}): {e}")
    return detail


def fetch_naver_post_body(
    url: str,
    platform: str,
    timeout: float = 8.0,
    fetcher=None,
) -> str:
    """KIN/blog/공개 cafe 페이지에서 본문 텍스트 취득. 실패는 빈 문자열로 fail-soft."""
    return fetch_naver_post_detail(url, platform, timeout=timeout, fetcher=fetcher)["body"]


# pending 큐 체류 TTL (일). 게시물 나이는 발견/enrichment 게이트(_assess_timing_window)가
# 판정하고, 여기는 '큐에 들어온 뒤 직원이 손대지 않은 기간'만 판정한다 — 책임 분리.
# cafe 댓글 스레드가 가장 빨리 식고, KIN은 검색 유입이 오래 가서 더 길다.
# 라이브 근거(2026-06-13): pending 4,002건 중 3,484건(87%)이 31~90일 적체,
# 그중 2,510건은 2026-04 분류 개선 이전의 '기타' 레거시 — TTL 부재가 원인.
PENDING_TTL_DAYS = {
    "cafe": 30,
    "naver_cafe": 30,
    "blog": 45,
    "kin": 45,
    "naver_kin": 45,
}
PENDING_TTL_DEFAULT_DAYS = 45

# 게시물 자체 나이 상한. posted_at이 알려진 pending이 이 일수보다 오래된 글이면
# 발견 시점(discovered_at)과 무관하게 만료한다 — 댓글 적시성 윈도우가 명백히 지난
# 글. 라이브 근거(2026-06-13): 검색 sim 정렬이 2007~2016년 KIN 질문을 끌어와
# pending에 잔류(53/73 이미 답변 완료). 270일은 보수적(계절성 후기 재유입 여지를
# 남기되 1년+ 묵은 글은 확실히 차단).
PENDING_POST_AGE_TTL_DAYS = 270

# 디스커버리 감사의 "제로수율 시드" 판정 최소 신규 발견 수.
# 한 런의 발견은 ~88%가 REdiscovery(이미 판정된 안정 상태 URL의 재발견)이므로
# 전체 discovered 로 제로수율을 판정하면 신규 SERP 영역을 전혀 탐색하지 않고
# 옛 URL만 재발견한 시드(예: 라이브 scan80에서 `청주 자동차사고 한의원` 발견 241/
# 신규 0)나, 재발견된 posted 로 이미 가치를 실현한 성숙 시드(`청주 체형교정 추천`
# 전체기간 23%·16건 posted)까지 "제로수율"로 잘못 표시된다(라이브: 25건 중 21건
# 오탐). 신규 발견(fresh_discovered)이 이 임계 이상이고 작업 가능 산출(pending
# 버킷=posted 포함)이 0인 시드만 — 즉 "실제 신규 영역을 탐색했는데 전환 0" 시드만 —
# 제로수율로 본다. pending==0 조건이 재발견-posted 로 성숙한 시드를 그대로 보호한다.
ZERO_YIELD_MIN_FRESH_DISCOVERED = 20


def expire_stale_pending_targets(
    db_path: str,
    now: Optional[datetime] = None,
    ttl_days: Optional[Dict[str, int]] = None,
    default_ttl_days: int = PENDING_TTL_DEFAULT_DAYS,
    post_age_ttl_days: int = PENDING_POST_AGE_TTL_DAYS,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """댓글 적시성 윈도우가 지난 pending 행을 filtered_out_stale_window로 만료.

    두 축으로 만료한다 (책임 분리):
    - queue-dwell: 발견 후 직원이 손대지 않은 채 plataform TTL(cafe 30 / blog·kin 45)이 지남
    - post-age: posted_at이 알려졌고 게시물 자체가 post_age_ttl_days(270)보다 오래됨
      — 검색 sim 정렬이 끌어온 수년 전 글이 enrichment fetch 예산/길이 가드를 비껴가
      pending에 잔류하던 갭을 메운다.

    rescue 레인은 raw_backlog/needs_ai_retry만 소비하므로 만료 행이 자동
    재승격되는 루프는 없다. lineage는 score_breakdown에 보존한다 (삭제 금지).
    """
    now = now or datetime.now()
    ttl_map = dict(PENDING_TTL_DAYS)
    if ttl_days:
        ttl_map.update(ttl_days)

    stats: Dict[str, Any] = {
        "checked": 0, "expired": 0, "expired_dwell": 0, "expired_post_age": 0,
        "by_platform": {}, "by_category": {},
    }
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, platform, category, discovered_at, first_seen_at,
                   posted_at, score_breakdown
              FROM viral_targets
             WHERE comment_status = 'pending'
            """
        ).fetchall()
        stats["checked"] = len(rows)
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        for row in rows:
            discovered = CommentableFilter._parse_datetime(
                row["discovered_at"] or row["first_seen_at"], now
            )
            ttl = ttl_map.get((row["platform"] or "").lower(), default_ttl_days)
            dwell_age = (now - discovered).total_seconds() / 86400.0 if discovered else None

            posted = CommentableFilter._parse_datetime(row["posted_at"], now)
            post_age = (now - posted).total_seconds() / 86400.0 if posted else None

            reason = None
            if dwell_age is not None and dwell_age > ttl:
                reason = "pending_ttl"
            elif post_age is not None and post_age > post_age_ttl_days:
                reason = "pending_post_age"
            if reason is None:
                continue

            stats["expired"] += 1
            stats["expired_dwell" if reason == "pending_ttl" else "expired_post_age"] += 1
            platform = (row["platform"] or "?").lower()
            category = row["category"] or "기타"
            stats["by_platform"][platform] = stats["by_platform"].get(platform, 0) + 1
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1
            if dry_run:
                continue
            try:
                breakdown = json.loads(row["score_breakdown"] or "{}") or {}
            except (TypeError, ValueError):
                breakdown = {}
            breakdown.update({
                "expired_from": "pending",
                "expired_reason": reason,
                "pending_age_days": round(dwell_age, 1) if dwell_age is not None else None,
                "post_age_days": round(post_age, 1) if post_age is not None else None,
                "pending_ttl_days": ttl,
                "expired_at": now_str,
            })
            conn.execute(
                """
                UPDATE viral_targets
                   SET comment_status = 'filtered_out_stale_window',
                       is_commentable = 0,
                       score_breakdown = ?,
                       updated_at = ?
                 WHERE id = ? AND comment_status = 'pending'
                """,
                (json.dumps(breakdown, ensure_ascii=False), now_str, row["id"]),
            )
        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return stats


# ============================================
# 댓글 가능 필터 클래스
# ============================================
class CommentableFilter:
    """
    댓글 가능 게시물 필터링

    필터링 기준:
    - 광고/홍보글 제외 (cafe_spy.py AD_EXCLUDE_KEYWORDS 참조)
    - 질문글/고민글 우선
    - 건강 관련 키워드 매칭
    """

    # [Phase 2 개선] 광고 필터 분리: STRICT(제외) vs SOFT(감점만) vs NON_RELEVANT(제외)

    # STRICT: 명확한 광고/홍보글 - 무조건 제외
    STRICT_AD_PATTERNS = [
        "체험단", "협력업체", "입점", "모집", "프리마켓",
        "동행인사", "인사드립니다", "입점했습니다",
        "#광고", "#협찬", "제공받아", "원고료",
    ]

    # SOFT: 구매 의도 포함 가능 - 감점만 하고 제외하지 않음
    SOFT_AD_INDICATORS = [
        "할인", "이벤트", "무료", "증정", "쿠폰"
    ]

    # 질문/후기가 아니라 병의원 랜딩/SEO 홍보문처럼 보이는 표현
    PROMOTIONAL_MEDICAL_PATTERNS = [
        "최고의 선택", "맞춤 프로그램", "패키지", "건강한 변화", "성공하세요",
        "도와드립니다", "안내드립니다", "소개합니다", "부담 없는", "요요없이",
        "안전한 맞춤", "최적의", "체계적인 관리", "꼼꼼한 진료", "맞춤 진료",
        "이런 분께 추천", "이런 분들에게", "본원에서는", "저희 병원",
        "저희 한의원", "내원해보세요", "예약하세요",
    ]

    # 자체 제작 랜딩/가이드형 의료 SEO 문서. Q&A라는 단어가 있어도 실제 질문글이 아니다.
    STRICT_MEDICAL_PROMO_PATTERNS = [
        "자주 묻는 질문", "q&a", "faq", "목표 설정", "전략 수립",
        "가장 큰 장점", "개인별 맞춤", "맞춤형 다이어트 계획", "단계별 관리",
        "시술 과정", "치료 과정", "관리 프로그램", "프로그램 안내",
        "최고의 선택", "맞춤 프로그램", "건강한 변화", "성공하세요",
        "부담 없는", "요요없이", "패키지 나왔", "최신 프로그램",
        "건강한 다이어트", "건강하고 안정적인 감량", "건강하고 안전한 맞춤",
        "배고플땐 먹기", "음식엔 죄가 없다", "빠지고 있다",
        "순서만 잘 지켜도", "왜 먹는데", "성공 비법", "이제 가능합니다",
        "부담없이 건강하게",
        "차앤차는 전국", "전국 지점이 위치", "전국 지점",
    ]

    KIN_PROVIDER_ANSWER_PATTERNS = [
        "닥톡-네이버 지식in 상담", "닥톡-네이버 지식iN 상담".lower(),
        "상담한의사", "상담의사", "상담의", "대표원장입니다", "원장입니다",
        "# 병원 위치", "# 진료 예약", "# 병원 홈페이지", "# 프로필 보기",
        "[병원 위치]", "[진료 예약]", "[병원 홈페이지]", "[프로필 보기]",
        "문의 전화", "병원 위치 | 진료 예약", "진료 예약 | 병원 홈페이지",
        "답변에 도움이 되셨기를", "도움이 되셨길 바랍니다", "답변이 도움이",
        "원장이었습니다", "대표원장 |", "프로필 보기",
    ]

    KIN_ANSWER_AD_PATTERNS = [
        "질문자님", "질문하신", "질문하신 내용", "문의 주셨", "문의주셨",
        "문의 해주신", "문의해주신", "말씀 주신", "말씀주신", "답변해드리",
        "답변 드리", "답변드립니다", "의 순서로 답변", "안녕하세요, 닥톡",
        "안녕하세요. 닥톡", "정확한 진단", "정확한 검사", "내원하셔서",
        "가까운 한의원에 방문", "가까운 병원에 방문", "개개인의 체질",
        "맞춤형으로 처방", "맞춤 처방", "단계별로 체계적인", "체계적인 감량",
        "처방 한약을 통해", "한의원에서는", "치료법에 관심", "치료를 받아야",
        "자동차보험 적용 대상", "개인비용 부담없이", "치료를 받을수가 있습니다",
        "질문하신 청주교통사고병원에 대한", "믿을수 있는", "믿을 수 있는",
        "약침으로 치료할 경우", "추나.보약.약침", "추나 보약 약침",
        "치료할 경우", "약 6개월", "비용은 매월", "대부분이며 비용",
        "치료 비용에서", "동일하게 치료", "치료를 처방 받을 수",
        "알아보실때에는", "알아보실 때", "중요한 것은 바로", "내원하지",
        "진단 받는것", "진단 받는 것", "정말 효과를 줄 수",
        "식이 조절에 효과적", "부족한 영양을 보강", "치료 집중적으로 받으세요",
        "클리닉도 따로", "체계적으로 치료 받기", "주로 하고 있는",
        "부담없이 오세요", "외래환자", "실비받다가", "한도가 되서",
        "상담문의 :", "상담 문의 :", "open.kakao.com", "카카오톡 오픈채팅",
        "현재 할인가", "구입할수 있는 방법", "영양제 한눈에 보기", "필수 <다이어트>",
        "운영 중인", "전문블로거", "결론부터", "연락주시",
        "환자분이 내원", "환자분이 내원해주시면", "처방 한의원",
        "만족도가 상당히", "일반적으로 3개월", "3단계에 걸쳐",
        "비용 절감 혜택", "네이버에서", "검색하셔서", "전화 상담",
        "전화상담", "상담받아 보세요", "상담 받아 보세요",
        "방문해서 상담", "전문의 소견", "방치하면 만성",
        "초기에 한의원", "비용 부담 없이", "자동차보험으로 상담",
        "차앤차는 전국", "전국 지점이 위치", "전국 지점",
        "교통사고보험한의원", "교통사고후물리치료", "자보한의원",
    ]

    KIN_RECOMMENDATION_SPAM_PATTERNS = [
        "후기 잘보고", "부작용없고 효과", "효과 좋은 곳", "꼭 가보시길",
        "가격이 부담스럽지도", "무지 유명한 곳", "입소문난", "유명 다이어트한의원",
        "확실하게 좋은 곳", "도움 받았다는", "도움을 받았다는", "관리좀 받으려",
        "효과 좋아요", "효과 좋았", "추천드려요", "추천드립니다",
        "가격도 괜찮", "친절하고 가격", "금액이 대박", "무제한으로",
        "비만패키지", "할인이벤트", "할인 이벤트", "잘 봐주시는",
        "꼼꼼하고 친절", "상담 한번 받아", "상담받아 보세요",
        "방문해서 상담", "유명하니", "유명한 곳으로",
    ]

    COMMERCIAL_CTA_PATTERNS = [
        "진료 예약", "예약하기", "예약 문의", "상담 신청", "상담문의", "문의주세요",
        "문의 주세요", "언제든 문의", "내원해보세요", "방문해보세요", "전화상담",
        "홈페이지", "바로가기", "지금 바로", "상담 가능", "방문 상담 가능",
        "카카오톡 상담", "네이버 예약", "온라인 예약", "전화로 예약",
        "예약제로 운영", "문의하시면", "연락주세요", "상담 한번",
        "상담받아 보세요", "상담 받아보세요", "검색하셔서",
    ]

    LOCAL_SEO_FOOTER_PATTERNS = [
        "다양한 지역에서 문의", "다양한 지역에서 내원", "주변 지역에서도",
        "인근 주변 지역", "근처 인근 주변", "등 다양한 지역", "전 지역 상담 가능",
        "사직동", "사창동", "모충동", "산남동", "분평동", "수곡동", "복대동",
    ]

    BLOG_AD_STRUCTURAL_PATTERNS = [
        "진료과목", "운영시간", "주차", "메뉴가격", "메뉴 가격", "리뷰 바로가기",
        "출처 ogq", "출처 unsplash", "출처 pixabay", "©", "저희 병원", "저희 한의원",
        "본원에서는", "본원은", "치료를 진행", "치료 프로그램", "맞춤 처방",
        "회복을 위한", "관리가 가능한", "관리 가능한", "치료와 관리",
        "치료와 후유증 관리", "전인적", "종합적 관리", "한의치료",
        "주소", "오시는 길", "오시는길", "진료시간", "영업시간",
        "대표원장", "의료진 소개", "둘러보기", "위치 안내",
    ]

    ANSWER_SNIPPET_AD_REGEXES = [
        r"(?:저도|저는|제가).{0,50}"
        r"(?:효과\s*좋|먹고|복용|상담받고\s*치료|상담\s*받고\s*치료|"
        r"치료받았|치료\s*받았|다녔|추천(?:드려|드립니다|합니다|하게|해요))",
        r"(?<![가-힣A-Za-z0-9ㄱ-ㅎ])"
        r"(?!(?:어느|어디|무슨|좋은|잘하는|근처|가까운)(?:한의원|한방병원|병원|내과|클리닉))"
        r"[가-힣A-Za-z0-9ㄱ-ㅎ]{2,}(?:한의원|한방병원|병원|내과|클리닉)"
        r"(?:이|가|은|는|도|에서|쪽|점).{0,80}"
        r"(?:상담\s*한번|상담받아|방문해서\s*상담|네이버에서|검색하셔서|전화\s*상담|"
        r"비용\s*부담\s*없이|자동차보험으로|잘\s*봐주|유명하니)",
        r"(?:할인이벤트|할인\s*이벤트|비만패키지|금액이\s*대박|무제한|현재\s*할인가|"
        r"비용\s*절감\s*혜택|최저가|할인\s*혜택).{0,80}"
        r"(?:한의원|병원|카복시|고주파|다이어트|한약)",
        r"(?:운동없이|운동\s*없이|요요없는|요요\s*없는).{0,60}"
        r"(?:비만도\s*질병|무조건\s*빨리|전화\s*상담|검색하셔서)",
        r"(?:규림한의원|ㄱㄹ한의원).{0,80}"
        r"(?:추천|상담|치료|꼼꼼|친절|자동차보험|방문)",
    ]

    MEDICAL_PROVIDER_TERMS = [
        "병원", "한방병원", "한의원", "의원", "피부과", "클리닉",
        "한약", "다이어트한약", "비만클리닉",
    ]

    MEDICAL_PROMO_TITLE_PATTERNS = [
        "회복을 위한", "관리를 위한", "관리 가능한", "관리가 가능한",
        "치료와 관리", "통증치료", "통증 치료", "후유증 관리",
        "한의치료", "맞춤치료", "맞춤 치료", "체계적인", "꼼꼼한",
        "야간진료", "야간 진료", "주말진료", "주말 진료",
        "예약가능", "예약 가능", "예약 가능해요", "진료 예약", "진료예약",
        "결정적인 실수", "올바른 식습관", "건강을 잃기전에", "건강을 잃기 전에",
        "찾아오세요", "유명한곳", "유명한 곳",
    ]

    BLOG_MEDICAL_SEO_TITLE_PATTERNS = [
        "문제가 아닌", "이유", "원인", "증상", "필요성", "개선",
        "치료 방법", "치료방법", "치료법", "관리법", "알아보기", "알아보세요",
        "되찾", "균형", "체계적인", "정확한", "건강을 위한",
    ]

    LEGAL_PROMO_PATTERNS = [
        "교통사고변호사", "교통사고전문변호사", "변호사선임비용", "선임비용",
        "무료법률상담", "무료 법률상담", "교통법률상담", "교통변호사",
        "소송비용", "승소 사례", "합의금", "뺑소니합의금", "무보험사고",
    ]

    BRAND_PROMO_PATTERNS = [
        "쥬비스", "인치 감량", "부작용없는", "업력", "최저가로 파는",
        "처방병원", "비댓문의", "비댓 문의", "카페는 위고비", "나만의닥터",
        "차앤차",
    ]

    STRONG_USER_INQUIRY_PATTERNS = [
        "아시는분", "아시는 분", "알려주세요", "추천해주세요", "추천 부탁",
        "어디가", "어디로", "궁금해요", "궁금합니다", "가보신", "해보신",
        "먹어도", "가야 하나", "가야할까요", "괜찮을까요", "괜찮은곳",
        "찾고 있어요", "찾고있어요", "고민입니다", "고민이에요",
    ]

    MIN_VIRAL_NEED_SCORE = 35

    RECOMMENDATION_REQUEST_PATTERNS = [
        "추천해주세요", "추천 해주세요", "추천 부탁", "추천좀", "추천 좀",
        "추천부탁", "추천드려요", "추천해주", "추천 해주", "추천받", "추천 받",
        "아시는분", "아시는 분", "알려주세요", "알려 주세요", "소개해주세요",
        "공유 부탁", "공유부탁", "부탁드려요", "부탁드립니다",
        "괜찮은곳", "괜찮은 곳", "잘하는곳", "잘하는 곳", "어디가 좋",
        "어디가 괜찮", "어디로 가", "어디 병원", "어디 한의원",
        "병원추천", "병원 추천", "한의원추천", "한의원 추천",
    ]

    READY_TO_ACT_PATTERNS = [
        "예약", "방문", "내원", "상담", "문의", "처방", "검사", "입원",
        "치료받", "치료 받", "가보려", "먹어보려", "받아보려", "시작하려",
        "오늘", "내일", "이번주", "이번 주", "급해", "빨리", "당장",
    ]

    COST_DECISION_PATTERNS = [
        "비용", "가격", "얼마", "견적", "실비", "보험", "자동차보험", "자보",
        "할인", "최저가", "저렴", "비싸", "부담",
    ]

    PAIN_URGENCY_PATTERNS = [
        "힘들", "스트레스", "걱정", "불안", "고민", "불편", "아파", "통증",
        "심해", "계속", "반복", "재발", "부작용", "효과 없", "낫지",
        "살이", "빠지", "여드름", "흉터", "후유증", "불면", "두통",
    ]

    PROBLEM_INTENT_PATTERNS = [
        "힘들", "스트레스", "걱정", "불안", "고민", "불편", "아파", "통증",
        "심해", "계속", "반복", "재발", "부작용", "효과 없", "낫지",
        "안 빠", "안빠", "불면", "두통",
    ]

    SERVICE_ACTION_PATTERNS = [
        "치료", "병원", "한의원", "내원", "입원", "처방", "상담", "관리", "개선",
    ]

    CONDITION_TERMS = [
        "여드름", "흉터", "후유증", "비만", "체중", "통증", "불면", "두통", "아토피",
    ]

    # 1인칭 환자 경험담(직접 받아본 후기) 표지. 규림 바이럴 댓글은 '저도 다녀왔는데 좋았어요'
    # 톤의 또래 경험 공유이므로, 질문/결정 의도가 없더라도 진짜 경험 공유 글은 댓글을 달
    # 좋은 대상이다. 단독으로 의도 점수를 주지 않고 반드시 진료축 앵커와 함께만 가산한다
    # (flat global prior 금지 — per-axis 증거).
    FIRST_PERSON_EXPERIENCE_PATTERNS = [
        "내돈내산",
        "다녀왔", "다녀온", "다녔는데", "다녔어",
        "받아봤", "받았는데", "받았어요", "받고나서", "받은 후", "받은후",
        "치료받았", "치료했어", "맞아봤", "맞았어", "먹어봤", "해봤어", "해봤는데",
        "효과 봤", "효과봤", "효과 좋았", "효과좋았", "후기 남겨", "후기남겨",
        "후기 올려", "경험담", "성공후기", "성공 후기",
    ]

    COMPARISON_EVALUATION_PATTERNS = [
        "나을까요", "좋을까요", "괜찮을까요", "효과", "후기", "비교",
        "피부과", "한의원", "병원", "한약", "양약", "보톡스", "위고비",
        "마운자로", "삭센다", "vs", " or ", "아니면",
    ]

    LOW_ACTIONABILITY_PATTERNS = [
        "뜻", "정의", "무엇인가요", "무엇인가", "왜 그런가요", "원인만",
        "가능한가요?", "상식", "뉴스", "논문", "과제", "숙제",
    ]

    MIN_REPLY_OPPORTUNITY_SCORE = 32
    MIN_TIMING_WINDOW_SCORE = 28
    MIN_JOURNEY_FIT_SCORE = 35
    MIN_QUALIFICATION_FIT_SCORE = 30
    MIN_CLINIC_TREATMENT_FIT_SCORE = 34
    MIN_WORKSITE_EFFICIENCY_SCORE = 36
    FINAL_REJECT_STATUSES = {
        "advertorial": "filtered_out_ad",
        "medical_promo": "filtered_out_ad",
        "non_relevant": "filtered_out",
        "off_domain": "filtered_out",
        "route_navigation": "filtered_out",
        "region_mismatch": "filtered_out",
        "domain_mismatch": "filtered_out",
        "source_context_mismatch": "filtered_out",
        "lens_mismatch": "filtered_out",
        "marketplace_sale": "filtered_out",
        "response_restricted": "filtered_out",
        "self_target": "filtered_out",
    }

    INTERROGATIVE_PATTERNS = [
        "?", "어디", "어떻게", "어떤", "뭐", "무엇", "왜", "언제", "얼마",
        "될까요", "되나요", "인가요", "나요", "까요", "맞나요",
    ]

    HELP_REQUEST_PATTERNS = [
        "도와주세요", "도움", "알려주세요", "알려 주세요", "추천", "부탁",
        "조언", "상담", "문의", "궁금", "고민", "찾고", "찾아보고",
        "아시는분", "아시는 분", "해보신", "가보신",
    ]

    PERSONAL_CONTEXT_PATTERNS = [
        "제가", "저는", "저희", "우리", "아이", "남편", "아내", "부모님",
        "엄마", "아빠", "가족", "친구", "사고 후", "사고후", "출산 후",
        "산후", "어제", "오늘", "내일", "며칠", "몇일", "개월", "년째",
    ]

    BROAD_RESEARCH_PATTERNS = [
        "원리", "성분", "논문", "자료", "뉴스", "과제", "숙제", "정의",
        "뜻", "무엇인가요", "무엇인가", "원인이 뭔가요", "왜 생기나요",
        "원인 알려", "상식", "요약",
    ]

    RESOLVED_OR_CLOSED_PATTERNS = [
        "해결했습니다", "해결됐", "해결되었", "다녀왔어요", "다녀왔습니다",
        "결정했어요", "결정했습니다", "구했습니다", "마감", "완료",
        "답변 채택", "채택된 답변", "답변완료", "후기입니다",
    ]

    LOW_COMMUNITY_FIT_PATTERNS = [
        "잡담", "썰", "웃긴", "투표", "설문", "공유해요", "홍보합니다",
        "정보 공유", "정보공유", "기사", "보도자료",
    ]

    MARKETPLACE_SALE_PATTERNS = [
        "팔아요", "팔아봅니다", "팝니다", "판매합니다", "판매해요",
        "판매중", "판매 중", "판매완료", "판매 완료",
        "양도합니다", "양도해요", "양도완료", "양도 완료",
        "무료나눔", "무료 나눔", "나눔합니다",
        "직거래", "택배거래", "택배 거래", "반값택배",
        "당근거래", "당근 거래", "중고나라", "번개장터",
        "가격네고", "가격 네고", "네고가능", "네고 가능",
        "쿨거래", "급처",
    ]
    MARKETPLACE_SALE_REGEXES = [
        r"(?:^|[\s\)\]\}.,!?])(?:판매|양도)\s*(?:완료|중|합니다|해요)",
        r"(?:직|택배)\s*거래\s*(?:가능|원해요|합니다)?",
        r"(?:가격\s*)?네고\s*(?:가능|불가)?",
    ]

    ROUTE_NAVIGATION_PATTERNS = [
        "어떻게 가나요", "어떻게가나요", "가는법", "가는 법", "교통편",
        "버스", "지하철", "노선", "환승", "터미널", "기차", "고속버스",
        "소요시간", "몇 분", "몇분", "길찾기", "길 찾기",
    ]

    SAME_DAY_ACTION_PATTERNS = [
        "오늘", "금일", "지금", "바로", "당장", "급해", "급합니다",
        "빨리", "내일", "이번주", "이번 주", "주말", "예약", "방문 예정",
    ]

    STALE_TIME_PATTERNS = [
        "작년에", "몇 년 전", "몇년 전", "예전에", "오래전", "오래 전",
        "이미", "현재는 괜찮", "지금은 괜찮", "나중에 후기",
    ]

    AWARENESS_STAGE_PATTERNS = [
        "뜻", "정의", "원인", "왜 생", "왜 그런", "무엇인가", "뭔가요",
        "차이", "종류", "성분", "원리", "논문", "자료", "뉴스", "상식",
        "가능한가요", "되나요", "해야 하나요", "문제인가요",
    ]

    CONSIDERATION_STAGE_PATTERNS = [
        "추천", "어디", "어느", "괜찮", "좋은 곳", "좋은곳", "잘하는 곳",
        "잘하는곳", "후기", "경험", "해보신", "가보신", "비교", "vs",
        "나을까요", "좋을까요", "피부과", "한의원", "병원", "클리닉",
    ]

    DECISION_STAGE_PATTERNS = [
        "예약", "방문", "내원", "상담", "문의", "비용", "가격", "얼마",
        "실비", "보험", "자보", "입원", "통원", "오늘", "내일", "이번주",
        "당장", "빨리", "근처", "가까운", "전화", "처방", "받으려고",
    ]

    POST_SERVICE_STAGE_PATTERNS = [
        "후기입니다", "후기 남", "다녀왔어요", "다녀왔습니다", "받고 왔",
        "해결했습니다", "해결됐", "결정했어요", "결정했습니다", "공유해요",
        "정보공유", "정보 공유", "내돈내산", "추천합니다",
    ]

    RESPONSE_PERMISSION_POSITIVE_PATTERNS = [
        "댓글", "답변", "알려주세요", "부탁", "공유 부탁", "쪽지", "비댓",
        "정보 부탁", "추천", "아시는분", "아시는 분", "도움",
    ]

    RESPONSE_PERMISSION_NEGATIVE_PATTERNS = [
        "홍보 금지", "홍보금지", "광고 금지", "광고금지", "업체 사절",
        "업체사절", "광고 사절", "광고사절", "쪽지 사절", "쪽지사절",
        "댓글 사절", "댓글사절", "영업 사절", "영업사절",
    ]
    RESPONSE_HARD_REJECTION_PATTERNS = [
        "댓글 사절", "댓글사절", "댓글 달지", "댓글달지", "답글 사절",
        "답글사절", "답변 사절", "답변사절", "쪽지 사절", "쪽지사절",
        "쪽지 보내지", "비댓 사절", "비댓사절", "비밀댓글 사절",
        "업체 사절", "업체사절", "업체분 사절", "업체분들 사절",
        "병원 관계자 사절", "한의원 관계자 사절", "관계자 사절",
        "브로커 사절", "영업 사절", "영업사절", "홍보 금지",
        "홍보금지", "홍보 사절", "홍보사절", "광고 금지",
        "광고금지", "광고 사절", "광고사절",
    ]

    DECISION_ACTOR_PATTERNS = [
        "제가", "저는", "제 ", "저희", "우리", "남편", "아내", "엄마", "아빠",
        "어머니", "아버지", "부모님", "아이", "아들", "딸", "가족", "본인",
    ]

    QUALIFICATION_CONSTRAINT_PATTERNS = [
        "직장", "학생", "육아", "출산", "산후", "시간", "야간", "주말",
        "근처", "가까운", "거리", "통원", "입원", "실비", "보험", "자보",
        "자동차보험", "비용", "가격", "부담", "예산", "할부", "부작용",
    ]

    JTBD_PROGRESS_PATTERNS = [
        "빼고 싶", "감량", "체중", "낫고 싶", "나아지고", "개선", "치료하고",
        "관리하고", "없애고", "줄이고", "회복", "복귀", "일상생활", "잠을 못",
        "효과 보고", "효과있는", "효과 있는", "안 아프", "좋아지고",
    ]

    SWITCHING_TRIGGER_PATTERNS = [
        "효과 없", "효과가 없", "안 나아", "낫지", "재발", "반복", "계속",
        "다른 곳", "다른곳", "옮기", "바꿔", "실패", "포기", "더 심",
        "약 먹어도", "해도 안", "관리해도", "병원 다녀도",
    ]

    LOW_QUALIFICATION_PATTERNS = [
        "숙제", "과제", "리포트", "보고서", "논문", "자료 조사", "자료조사",
        "뉴스", "기사", "정책", "통계", "단순 궁금", "그냥 궁금", "심심해서",
        "잡지식", "검정고시", "자격증", "차체수리", "보수도장",
        "변호사", "법률", "소송", "재판", "구속영장", "음주운전", "삼진아웃",
        "합의금", "합의 및", "형사사건",
        "예방법", "예방 법", "관리법", "운동법", "자가관리", "홈케어",
    ]

    QUALIFIED_SERVICE_LINE_PATTERNS = [
        "한의원", "한방병원", "한약", "한방", "교통사고", "후유증", "입원치료",
        "통원치료", "추나", "다이어트", "비만", "감량", "식욕억제",
        "여드름", "흉터", "탈모", "비염", "체형교정", "골반교정",
        "안면비대칭", "얼굴비대칭", "새살침", "리프팅", "피부", "통증",
    ]

    NON_SERVICE_BEAUTY_PATTERNS = [
        "붙임머리", "남자파마", "파마잘하는", "미용실", "헤어샵", "헤어클리닉",
        "펌 잘하는", "염색", "두피케어", "네일", "속눈썹", "왁싱",
        "보톡스", "땀주사", "두피주사", "모발이식",
        "피부관리실", "피부관리샵", "피부샵", "에스테틱", "관리실",
        "윤곽관리", "얼굴관리", "경락", "약손", "작은얼굴", "얼굴축소",
        "눈썹문신", "반영구", "아이라인문신", "입술문신",
        "led 마스크", "led마스크", "LED 마스크", "LED마스크", "마스크팩",
    ]

    ASYMMETRY_HARD_OFF_AXIS_PATTERNS = [
        "눈썹문신", "반영구", "아이라인문신", "입술문신", "속눈썹",
        "미용실", "헤어샵", "메이크업", "왁싱", "네일",
    ]
    ASYMMETRY_BEAUTY_MANAGEMENT_PATTERNS = [
        "윤곽관리", "얼굴관리", "경락", "약손", "작은얼굴", "얼굴축소",
        "에스테틱", "피부관리실", "피부관리샵", "관리실", "관리샵",
        "마사지", "마사지샵", "미다스뷰티", "비율에스테틱",
    ]
    ASYMMETRY_DENTAL_OR_ORTHO_NOISE_PATTERNS = [
        "치과", "치아", "치열", "치아교정", "치열교정", "교정치과",
        "덧니", "돌출입", "부정교합", "브라켓", "인비절라인",
        "반듯한 배열", "치아 배열", "교정추천",
    ]
    ASYMMETRY_STRONG_AXIS_PATTERNS = [
        "안면비대칭", "얼굴비대칭", "턱비대칭", "좌우비대칭", "두상비대칭",
        "광대비대칭", "광대 비대칭", "광대좌우차이", "광대 좌우 차이",
        "얼굴좌우차이", "얼굴 좌우 차이", "머리비대칭", "머리 비대칭",
        "턱관절", "턱 교정", "턱교정", "안면교정", "얼굴교정",
        "비대칭교정", "비대칭 교정", "얼굴 틀어짐", "얼굴틀어짐",
        "턱 틀어짐", "턱틀어짐",
    ]
    ASYMMETRY_CLINIC_ACTION_PATTERNS = [
        "한의원", "한방", "추나", "추나요법", "치료", "진료", "검사",
        "상담", "교정", "병원", "의원", "클리닉",
    ]

    DIET_ACTIVITY_NOISE_PATTERNS = [
        "태권도", "태권도장", "째즈댄스", "재즈댄스", "댄스학원",
        "댄스 학원", "피트니스", "헬스장", "헬스클럽", "스포랜드",
        "스포츠센터", "운동할만한곳", "운동 할만한곳", "운동 추천",
        "운동 루틴", "pt샵", "pt 샵", "필라테스", "요가", "복싱장",
        "복싱", "체육관", "수영장", "점핑", "크로스핏", "도장",
        "줌바", "줌바댄스", "다이어트댄스", "다이어트 댄스",
    ]
    DIET_MEDICAL_INTENT_PATTERNS = [
        "다이어트한약", "다이어트 한약", "한약", "한의원", "한방",
        "비만", "감량", "체중", "식욕", "요요", "부종", "처방",
        "상담", "진료", "치료", "약", "주사", "의원", "병원",
        "클리닉", "탕약",
    ]
    DIET_NON_HANBANG_MEDICAL_NOISE_PATTERNS = [
        "지방분해주사", "지방 분해 주사", "윤곽주사", "윤곽 주사",
        "비만주사", "비만 주사", "다이어트주사", "다이어트 주사",
        "달걀주사", "달걀 주사", "비비주사", "비비 주사",
        "바디톡신", "클라투", "지방융해술", "비만클리닉",
        "삭센다", "위고비", "마운자로",
    ]
    DIET_HANBANG_INTENT_PATTERNS = [
        "다이어트한약", "다이어트 한약", "한약", "한의원", "한방",
        "탕약", "감비", "감비환", "비움탕", "체질", "부항",
        "침", "약침",
    ]
    SKIN_SALON_OR_INCIDENTAL_NOISE_PATTERNS = [
        "스킨스파", "스킨앤스파", "hakskin", "학스킨", "피부관리실",
        "피부관리샵", "피부샵", "에스테틱", "림프마사지", "마사지",
        "피부 스케일링", "스킨케어", "압출관리", "피지관리",
        "피부영양", "피부 영양",
    ]
    SKIN_HARD_SALON_PATTERNS = [
        "스킨스파", "스킨앤스파", "hakskin", "학스킨", "림프마사지",
        "피부관리실", "피부관리샵", "피부샵", "에스테틱",
    ]
    SKIN_CLINIC_RESCUE_PATTERNS = [
        "한의원", "피부과", "병원", "의원", "클리닉", "치료",
        "진료", "처방", "새살침", "약침", "침치료", "한약",
        "여드름흉터", "패인흉터", "편평사마귀", "지루성피부염",
    ]
    SKIN_WESTERN_RX_NOISE_PATTERNS = [
        "이소티논", "로아큐탄", "니메겐", "이소트레티노인", "isotretinoin",
        "피지조절제", "피지 조절제", "여드름약", "여드름 약",
        "피부과약", "피부과 약", "항생제", "독시사이클린", "미노씬",
        "스티바", "디페린", "에피듀오", "크레오신",
        "약처방", "약 처방", "처방전", "처방 병원", "처방해주는",
        "처방 해주는", "처방받", "처방 받",
    ]
    SKIN_HANBANG_SERVICE_RESCUE_PATTERNS = [
        "한의원", "피부한의원", "한방", "한약", "약침", "침치료",
        "새살침", "침", "한방치료", "한방 치료", "규림",
    ]
    SCAR_USER_AXIS_ANCHOR_PATTERNS = [
        "흉터", "여드름흉터", "여드름 흉터", "여드름자국", "여드름 자국",
        "패인흉터", "패인 흉터", "모공흉터", "모공 흉터", "수두흉터",
        "수두 흉터", "수술흉터", "수술 흉터", "상처흉터", "상처 흉터",
        "켈로이드", "새살침", "흉터치료", "흉터 치료", "흉터새살침",
        "피부재생", "색소침착", "붉은자국", "붉은 자국", "갈색자국",
        "갈색 자국", "패인 자국", "패인자국",
    ]
    SKIN_USER_AXIS_ANCHOR_PATTERNS = [
        "여드름", "성인여드름", "성인 여드름", "피부질환", "피부 질환",
        "아토피", "지루성피부염", "지루성 피부염", "사마귀", "편평사마귀",
        "편평 사마귀", "트러블", "피부염", "습진",
    ]
    LEGAL_OR_SCHOOL_VIOLENCE_PATTERNS = [
        "학폭", "학교폭력", "피해학생", "가해학생", "법승", "변호사",
        "법률", "소송", "고소", "신고", "재판", "합의", "형사",
    ]
    TRAFFIC_REPAIR_OR_PROPERTY_NOISE_PATTERNS = [
        "광택", "코팅", "유리막", "판금", "도색", "공업사", "정비소",
        "수리비", "차량수리", "차량 수리", "차체수리", "보수도장",
        "렌트비", "렌터카", "렌트카", "대물", "대물보상", "부품값",
        "블랙박스", "사고차", "보험료 할증", "할증", "폐차",
    ]
    TRAFFIC_LEGAL_COMPENSATION_NOISE_PATTERNS = [
        "합의금", "합의건", "합의 건", "과실비율", "과실 비율", "손해보험사",
        "손해 보험사", "휴업손해", "위자료", "보상받", "보상 받", "손해배상",
        "소송", "민사", "형사", "변호사", "법률", "구상권", "분쟁조정",
    ]
    TRAFFIC_MEDICAL_CARE_RESCUE_PATTERNS = [
        "입원", "통원", "통원치료", "입원치료", "한의원", "한방병원", "병원",
        "정형외과", "재활의학과", "치료", "진료", "후유증", "통증", "아파",
        "목통증", "허리통증", "어깨통증", "다리통증", "염좌", "추나",
        "물리치료", "도수치료", "약침", "침치료", "한약", "엑스레이", "x-ray",
        "mri", "응급실", "보험접수", "보험 접수",
    ]
    TRAFFIC_ACTIVE_CARE_INTENT_PATTERNS = [
        "입원가능", "입원 가능", "입원할수", "입원 할수", "통원치료",
        "치료받", "치료 받", "진료받", "진료 받", "병원 추천", "한의원 추천",
        "어디", "알려주세요", "아시는", "추천", "가야", "가볼", "받고싶",
        "통증", "후유증", "아파", "목", "허리", "어깨",
    ]
    TRAFFIC_ANIMAL_OR_VET_NOISE_PATTERNS = [
        "동물병원", "동물 병원", "수의사", "반려동물", "반려 동물",
        "반려견", "강아지", "고양이", "애견", "펫병원", "펫 병원",
        "닥스훈트", "말티즈", "푸들", "시츄", "포메라니안",
    ]
    BODY_USER_AXIS_ANCHOR_PATTERNS = [
        "체형", "체형교정", "골반", "골반교정", "자세", "자세교정",
        "거북목", "일자목", "척추", "측만", "추나", "추나요법",
        "도수", "도수치료", "허리", "허리통증", "허리디스크",
        "목디스크", "디스크", "경추", "어깨통증", "휜다리",
        "라운드숄더",
    ]
    BODY_COMPANION_OFF_AXIS_PATTERNS = [
        "adhd", "틱", "불안장애", "공황장애", "우울", "자율신경",
        "두전증", "어지럼증", "두통", "편두통", "수면장애", "불면",
        "감기", "비염", "소화불량", "소화", "피로", "보약", "공진단",
        "아이한약", "어린이한약", "어린이 한약", "소아", "성장",
        "한약 잘하는", "스트레스성두통", "이명", "족지간신경종",
        "발목", "손목", "교통사고", "자동차보험", "자보", "사고후",
        "사고 후", "입원", "통원",
    ]
    BODY_FITNESS_PROVIDER_NOISE_PATTERNS = [
        "닥터짐", "헬스장", "헬스클럽", "pt", "피티", "퍼스널트레이닝",
        "퍼스널 트레이닝", "스피닝", "운동센터", "운동은어디서",
        "회원권", "센터 회원", "카카오톡 문의", "오픈카톡",
    ]
    BODY_MEDICAL_RESCUE_PATTERNS = [
        "한의원", "한방", "추나", "추나요법", "도수치료", "도수 치료",
        "정형외과", "재활의학과", "병원", "의원", "치료", "진료",
        "통증", "디스크", "검사", "상담받", "상담 받",
    ]
    ASYMMETRY_USER_AXIS_ANCHOR_PATTERNS = ASYMMETRY_STRONG_AXIS_PATTERNS + [
        "얼굴형", "턱", "광대", "교정",
    ]
    LIFTING_USER_AXIS_ANCHOR_PATTERNS = [
        "리프팅", "한방리프팅", "매선", "탄력", "피부탄력",
        "주름", "팔자", "처짐", "노화", "동안",
    ]
    LIFTING_NON_HANBANG_DEVICE_PATTERNS = [
        "울쎄라", "써마지", "슈링크", "인모드", "실리프팅",
        "실 리프팅", "필러", "보톡스", "엘란쎄", "리쥬란",
        "쥬베룩", "스킨부스터", "레이저", "피부과",
    ]
    LIFTING_HANBANG_SERVICE_RESCUE_PATTERNS = [
        "한방리프팅", "한방 리프팅", "한방성형", "한방 성형",
        "매선", "매선침", "매선 리프팅", "한의원", "침치료",
        "약침",
    ]
    LIFTING_INCIDENTAL_COMMERCE_NOISE_PATTERNS = [
        "홈플러스", "당당치킨", "강정", "식품 브랜드", "매장 성장",
        "브랜드 출시", "론칭", "론칭제", "솥솥", "젠틀몬스터",
        "안경", "패션", "신제품", "프랜차이즈",
    ]
    EXPLICIT_HANBANG_EXCLUSION_PATTERNS = [
        "한의원은 추천안", "한의원은 추천 안", "한의원 추천안",
        "한의원 추천 안", "한의원은 제외", "한의원 제외",
        "한의원 말고", "한방 말고", "한약 말고", "침 말고",
        "추나 말고", "한의원 상담이나 치료를 찾는 건 아니",
        "한의원 상담이나 치료를 찾는건 아니",
    ]
    MULTI_REGION_ANSWER_FOOTER_REGIONS = [
        "강남", "노원", "신림", "수원", "안양", "일산", "부천", "인천",
        "대전", "청주", "천안", "광주", "대구", "부산", "울산", "포항",
        "진주", "제주", "창원", "춘천", "구미", "전주", "원주",
    ]
    KIN_PROVIDER_FOOTER_PATTERNS = [
        "피부 네트워크", "23지점", "전국 지점", "지점 의 피부",
        "강남, 노원", "대전, 청주, 천안", "구미, 전주, 원주",
    ]
    PROVIDER_INFO_POST_PATTERNS = [
        "치료비용입니다", "치료 비용입니다", "오셔서", "진행해보시길",
        "진행해 보시길", "대표적인 한방 프로그램", "프로그램으로는",
        "한의사입니다", "한의원입니다", "한의원에서는", "가격 차이",
        "정리해봤습니다", "정리해 봤습니다", "브랜드 비용",
        "운영 방식에 따라", "상담과 관리", "치료를 진행",
        "치료를 진행해", "관리해드립니다", "관리해 드립니다",
        "청주점에서는", "카카오톡 상담", "오픈카톡", "#청주한의원",
        "전신을 바로잡", "최고 효과", "본 한의원", "의료진들은",
        "풍부한 임상경험", "풍부한 임상 경험", "추천해 드리고 싶습니다",
        "추천해드리고 싶습니다", "안심하시고 받으실",
    ]
    PROVIDER_INFO_TITLE_PATTERNS = [
        "정리해봤습니다", "정리해 봤습니다", "가격 차이", "치료비용",
        "치료 비용", "추나요법이란", "요법이란", "전신을 바로잡아",
        "효과는 무엇일까", "통증을 사로잡는다", "차이점", "필요할까",
        "어떤 상황에서", " - ",
    ]
    PROVIDER_BODY_AUTHOR_PATTERNS = [
        "본원", "본 한의원", "저희 병원", "저희 한의원", "저희 의원",
        "저희 클리닉", "청주점에서는", "한의원입니다", "한의사입니다",
        "대표원장", "의료진", "내원해보세요", "예약하세요",
        "관리해드립니다", "관리해 드립니다",
    ]
    PROVIDER_BODY_REAL_USER_ASK_PATTERNS = [
        "광고 말고", "업체 말고", "홍보 말고", "직접 경험", "경험 있으",
        "해보신 분", "해보신분", "받아보신 분", "받아보신분",
        "가보신 분", "가보신분", "다녀보신 분", "다녀보신분",
        "아시는 분", "아시는분", "추천 부탁", "추천부탁",
        "후기 부탁", "정보 부탁",
    ]
    # 카페 글은 author=카페명, 블로그는 author=블로거명 → 이 필드가 곧 '글이 올라온
    # 곳의 정체성'이다. 카페명/블로거가 경쟁 의료기관(한의원/의원/클리닉 등)이거나
    # 병원 디렉터리/홍보 카페면 환자 질문이 아니라 공급자 마케팅 표면이다. 본문 CTA가
    # 미리보기(≈230자) 밖에 있어 _provider_cta_body_signal 을 빠져나가는 soft-SEO 글이
    # 키워드가 풍부해 골든큐 최상위(점수 130~150)에 올라오던 문제를 막는다
    # (2026-06-13 local-venue-anchor 의 공급자 측 대칭 — 그쪽은 커뮤니티 카페를 '가점',
    # 이쪽은 공급자 카페를 '광고 처리').
    PROVIDER_VENUE_AUTHOR_PATTERNS = [
        "한의원", "한방병원", "의원", "클리닉", "피부과", "성형외과", "치과",
        "길라잡이", "전국병원", "병원정보", "병원 정보", "병원추천", "병원 추천",
        "의료정보", "병원안내", "병원 안내", "병원홍보", "닥터스",
    ]
    # 환자/지역 커뮤니티 카페는 공급자 토큰이 들어 있어도 보존(거짓양성 차단).
    # 예: 척추질환 환우모임, 두통환우카페, 알고가자 동네병원, 메디컬정보 커뮤니티,
    # 피부인 대표 피부카페. 가드를 먼저 검사해 과차단을 방지한다.
    PROVIDER_VENUE_AUTHOR_COMMUNITY_GUARD = [
        "환우", "환자회", "환자 모임", "동호회", "맘", "카페", "스터디",
        "주민", "모여", "동네", "지역", "클럽", "모임", "커뮤니티", "회원", "육아",
    ]
    TRAFFIC_USER_CARE_ANCHOR_PATTERNS = [
        "교통사고", "자동차사고", "차사고", "사고 후", "사고후",
        "입원", "통원", "치료", "진료", "후유증", "염좌", "통증",
        "목", "허리", "어깨", "자보", "자동차보험", "보험접수",
    ]
    TRAFFIC_TITLE_HARD_NOISE_PATTERNS = [
        "보험료할증", "보험료 할증", "할증", "과실비율", "합의금",
        "합의건", "합의 건", "광택", "코팅", "수리비", "대물",
        "렌트비", "렌터카", "렌트카", "판금", "도색",
    ]

    # NON_RELEVANT: 비관련 업종 - 무조건 제외
    NON_RELEVANT_EXCLUDE = [
        # 기존
        "강아지", "반려견", "동물병원", "동물 병원", "수의사",
        "반려동물", "반려 동물", "고양이", "애견", "펫병원",
        "성형외과", "분양", "아파트",
        "주식", "코인", "부동산", "매매", "임대",
        "케이크", "베이커리", "맛집",
        "성형", "쌍수", "코수술", "지방흡입",
        # 확장 - 업계 외
        "대출", "신용", "보증", "카지노", "바카라", "슬롯", "도박", "토토",
        "분양권", "청약", "경매", "전세", "월세",
        "취업", "구인", "알바", "채용공고",
        "중고", "판매합니다", "나눔", "양도",
        "자동차보험료", "자차보험", "차보험 견적",
        "자탐 모임", "템플스테이", "조계사", "수녀님", "교역자 필독서",
        "정책뉴스", "자격증취득", "국비지원무료교육",
        "화상영어", "전화영어", "아이엘츠", "영어공부", "영어작문",
        "작문 부탁", "내공50", "내공 50",
        "배드민턴", "코트 대관", "천기저귀", "소창기저귀",
        "광목", "커텐", "커튼", "이불",
    ]

    # 검색어는 맞지만 실제 상담 영역이 다른 글. 예: "교정"이 치과 교정 글에 걸리는 경우.
    OFF_DOMAIN_PATTERNS = {
        "dental": [
            "치과", "임플란트", "치아교정", "치열교정", "교정치과", "덧니",
            "돌출입", "부정교합", "양악", "크라운", "라미네이트", "스케일링",
            "신경치료", "충치", "잇몸", "사랑니", "치아", "브라켓", "인비절라인",
        ],
        "golf": [
            "골프", "골프레슨", "골프연습장", "스크린골프", "필드레슨",
            "골프장", "드라이버", "아이언", "퍼팅", "골프채",
        ],
        "cosmetic_clinic": [
            "피부과", "프락셀", "레이저", "레이저토닝", "토닝", "필러",
            "보톡스", "슈링크", "인모드", "울쎄라", "리쥬란", "스킨부스터",
            "쥬베룩", "엘란쎄", "포텐자", "피코토닝", "두피주사", "땀주사",
        ],
        "fitness": [
            "홈트레이닝", "홈트", "pt", "퍼스널트레이닝", "헬스장", "헬스",
            "필라테스", "요가", "복싱", "무에타이", "킥복싱", "골프레슨",
            "스포츠상해",
        ],
        "surgery": [
            "지방이식", "가슴성형", "눈성형", "코성형", "쌍수", "양악",
            "성형외과", "지방흡입", "윤곽수술", "모발이식",
        ],
        "urology": [
            "전립선", "비뇨기", "요실금", "방광염", "발기부전", "prostate",
        ],
    }

    DOMAIN_ANCHORS = {
        "diet": [
            "다이어트", "감량", "체중", "비만", "살빼", "식욕", "요요",
            "한약", "다이어트약", "체지방", "뱃살", "허벅지", "한의원", "한방",
            "의원", "클리닉", "처방", "삭센다", "위고비", "마운자로",
        ],
        "traffic": [
            "교통사고", "자동차사고", "차사고", "사고", "자보", "자동차보험",
            "입원", "후유증", "염좌", "추나", "한의원", "한방병원",
        ],
        "scar_skin": [
            "여드름", "흉터", "여드름흉터", "패인흉터", "모공흉터",
            "수두흉터", "수술흉터", "상처흉터", "켈로이드", "새살침",
            "흉터치료", "트러블", "피부", "자국", "한의원", "한방",
            "의원", "클리닉", "피부과", "레이저", "시술", "스킨부스터",
            "리쥬란", "쥬베룩", "포텐자",
        ],
        "asymmetry": [
            "안면비대칭", "얼굴비대칭", "턱비대칭", "비대칭", "턱관절",
            "얼굴", "광대", "턱", "추나", "한의원", "한방",
            "의원", "클리닉", "상담", "분석", "검사",
        ],
        "body": [
            "체형", "체형교정", "골반", "골반교정", "척추", "측만", "자세",
            "거북목", "일자목", "추나", "통증", "한의원", "한방",
            "의원", "클리닉", "바디라인", "승모근",
        ],
        "lifting": [
            "리프팅", "탄력", "주름", "매선", "한방리프팅", "피부탄력",
            "노화", "한의원", "한방", "의원", "클리닉", "피부과",
            "레이저", "스킨부스터", "리쥬란", "쥬베룩",
        ],
    }
    STRICT_DOMAIN_ANCHORS = {
        "asymmetry": [
            "안면비대칭", "얼굴비대칭", "턱비대칭", "비대칭", "턱관절",
            "턱 교정", "턱교정", "얼굴형", "광대비대칭", "광대 비대칭",
            "광대좌우차이", "광대 좌우 차이", "좌우비대칭", "좌우 비대칭",
            "얼굴좌우차이", "얼굴 좌우 차이", "두상비대칭", "두상 비대칭",
            "머리비대칭", "머리 비대칭",
            # 환자 어휘 — 키워드 용어(턱관절/비대칭) 없이 증상을 서술하는 질문 구제
            # (라이브: '아래턱이 오른쪽으로 움직이는' 턱 틀어짐 질문이 앵커 미스로
            # domain_mismatch). 치과 고착 글은 선행 dental off_domain 게이트가 거른다.
            "아래턱", "턱이 돌아", "턱 돌아", "턱이 틀어", "턱 틀어",
            "얼굴이 틀어", "얼굴 틀어", "턱이 비뚤", "얼굴 비뚤",
        ],
        "body": [
            "체형", "체형교정", "골반", "골반교정", "자세", "자세교정",
            "거북목", "일자목", "척추", "측만", "추나", "추나요법",
            "도수", "도수치료", "어깨", "목통증", "허리통증", "목디스크",
            "허리디스크", "디스크", "경추", "휜다리", "라운드숄더",
        ],
        "lifting": [
            "리프팅", "한방리프팅", "매선", "탄력", "피부탄력",
            "주름", "팔자", "처짐", "노화",
        ],
    }

    # 사업 권역 지역 키워드 (제목 또는 본문에 하나 이상 포함돼야 통과)
    REGION_KEYWORDS = list(dict.fromkeys(
        list(getattr(GYULIM_KEYWORD_PROFILE, "cheongju_regions", ()))
        + list(getattr(GYULIM_KEYWORD_PROFILE, "neighborhoods", ()))
        + list(getattr(GYULIM_KEYWORD_PROFILE, "nearby_regions", ()))
    ))
    AMBIGUOUS_CHEONGJU_REGION_STEMS = {"상당", "서원", "청원"}
    DISTANT_REGION_KEYWORDS = [
        "서울", "부산", "대구", "인천", "대전", "대전광역시", "광주", "광주광역시", "울산",
        "수원", "천안", "전주", "강남", "분당", "판교", "유성", "도안", "둔산", "노은",
        "평택", "성남", "용인", "화성", "안산", "안양", "부천", "고양", "의정부",
        "파주", "김포", "남양주", "하남", "의왕", "군포", "시흥", "오산", "광명",
        "구리", "장안동", "아산", "탕정", "탕정면", "배방", "배방읍", "장재리",
        "달서구",
        "쌍용동", "불당동", "신불당동", "공주", "논산", "당진", "서산", "충주", "제천",
        "홍성", "예산", "태안", "계룡", "부여", "서천", "금산",
        # 서울/수도권 동네명 — 닥톡류 '(지역 카테고리)' 템플릿 질문이 city명 없이
        # 동네명만 달고 들어와 지역 게이트를 통과하는 누수를 막는다 (라이브: 잠실).
        "잠실", "잠원동", "압구정", "청담동", "신사동", "역삼동", "서초동", "송파",
        "노원", "천호동", "목동", "왕십리", "건대", "영등포", "일산", "동탄",
        "청라", "송도", "평촌", "산본",
        "도봉구", "강북구", "관악구", "구로구", "동작구", "성북구", "중랑구",
        "광진구", "강동구", "양천구",
        "감삼동", "수성구", "동성로", "서면", "해운대",
    ]

    # 최소 본문 길이 (API content_preview는 300자 잘림이므로 100자면 충분한 의미)
    MIN_CONTENT_LENGTH = 100

    GENERIC_CATEGORY_NAMES = {"기타", "general", "unknown", "uncategorized", ""}
    GENERIC_CATEGORY_PENALTY = -12

    URGENT_MEDICAL_KEYWORDS = [
        "응급", "119", "응급실", "구급차", "호흡곤란", "숨이 안", "흉통", "가슴통증",
        "마비", "실신", "의식불명", "발작", "경련", "과다출혈", "피가 안 멈", "자살", "자해",
    ]
    SENSITIVE_MEDICAL_KEYWORDS = [
        "임신", "수유", "소아", "아기", "영유아", "아이", "청소년", "약 부작용",
        "부작용", "스테로이드", "항생제", "당뇨", "고혈압", "암", "간수치", "신장",
        "신부전", "심장", "알레르기", "두드러기", "쇼크", "수술 후", "수술후",
    ]
    MEDICATION_ADVICE_PATTERNS = [
        "먹어도 되", "먹어도될", "복용해도 되", "복용해도될", "복용 가능",
        "같이 먹", "같이 복용", "함께 먹", "함께 복용", "병용", "동시에 먹",
        "계속 먹어도", "계속 복용", "끊어야", "중단해야", "중단할까요",
        "용량", "몇 알", "몇알", "하루 몇", "처방받아도", "처방 받아도",
        "먹고 있는데", "복용 중", "복용중", "약 먹는 중", "약먹는중",
    ]
    ACUTE_SIDE_EFFECT_PATTERNS = [
        "심장 두근", "두근거림", "두근거려", "가슴 두근", "숨이 답답",
        "숨차", "호흡이 답답", "어지러", "어지럼", "실신", "기절",
        "발진", "붓기", "부어오", "두드러기", "쇼크",
    ]
    TESTIMONIAL_SENSITIVE_KEYWORDS = [
        "후기", "경험담", "치료 경험", "효과", "완치", "보장", "전후", "비포애프터",
    ]

    # 기존 호환용 (STRICT + NON_RELEVANT)
    AD_EXCLUDE = STRICT_AD_PATTERNS + NON_RELEVANT_EXCLUDE

    # 질문글 패턴 (확장)
    INQUIRY_PATTERNS = [
        # 추천/질문
        "추천", "어디", "궁금", "있을까요", "있나요", "알려주세요",
        "가봤는데", "다니시는분", "해보신분", "경험", "후기",
        "좋은곳", "잘하는", "괜찮은", "어떤가요", "어때요",
        "고민", "도움", "상담", "문의", "질문",
        # 추가 패턴
        "어디로", "어떻게", "뭐가", "효과", "가격", "비용",
        "병원", "의원", "치료", "시술", "원장", "진료",
        "예약", "상담", "방문", "다녀", "받았", "받고",
        "좋았", "괜찮", "만족", "불만", "실망", "추천드",
        "알아보", "찾고", "찾는중", "구해", "필요", "원해", "하고싶",
        "해보려고", "하려고", "할까", "고민중", "고민 중",
    ]

    # 의료 명사(병원/치료/진료 등)를 제외한 실제 질문·탐색 신호
    REAL_INQUIRY_PATTERNS = [
        "추천", "어디", "궁금", "있을까요", "있나요", "알려주세요",
        "다니시는분", "해보신분", "경험", "후기", "좋은곳", "잘하는",
        "괜찮은", "어떤가요", "어때요", "고민", "도움", "상담", "문의", "질문",
        "어디로", "어떻게", "뭐가", "효과", "가격", "비용", "예약",
        "다녀", "받았", "받고", "좋았", "만족", "불만", "실망",
        "알아보", "찾고", "찾는중", "구해", "필요", "원해", "하고싶",
        "해보려고", "하려고", "할까", "고민중", "고민 중",
        "?", "？",
    ]

    # 🔥 Hot Lead 키워드 (긴급/높은 전환율)
    HOT_LEAD_KEYWORDS = [
        # 추천 요청 (직접적)
        "추천해주세요", "추천부탁", "추천좀", "어디가 좋을까요", "어디로 가야",
        "알려주세요", "소개해주세요", "있을까요",
        # 긴급
        "급해요", "급합니다", "급함", "빨리", "당장", "오늘", "내일", "이번주",
        # 고민/걱정
        "고민이에요", "고민입니다", "걱정", "어떡해", "어떻게 해야", "힘들어요",
        # 직접 경험 요청
        "해보신 분", "다녀보신 분", "경험 있으신", "아시는 분", "가보신 분",
        # 비교/선택
        "어디가 나을까", "뭐가 좋을까", "고르기", "선택",
        # 가격 민감
        "가격", "비용", "얼마", "저렴", "착한", "합리적"
    ]

    # 🎯 경쟁사 참조는 더 이상 여기에 하드코딩하지 않는다 (stale 목록이 로랑/데이릴
    # 같은 핵심 경쟁사를 누락시켜 역공략 레인을 무력화한 이력). 단일 소스는
    # config/competitors.json이며 AICommentGenerator._load_curated_competitors()가
    # 로드해 AI 프롬프트에 주입한다.

    # 건강 관련 키워드 (대폭 확장 - 양치기용)
    HEALTH_KEYWORDS = [
        # 다이어트
        "다이어트", "살빼기", "체중", "비만", "뱃살", "허벅지", "팔뚝",
        "식단", "운동", "헬스", "필라테스", "PT", "감량", "체형",
        # 안면/교정
        "비대칭", "안면비대칭", "얼굴비대칭", "골반", "교정", "체형교정",
        "턱", "광대", "사각턱", "거북목", "일자목", "척추", "측만",
        # 통증/디스크
        "허리", "목", "어깨", "무릎", "통증", "디스크", "추나", "도수",
        "관절", "근육", "인대", "염좌", "삐끗", "담", "뻐근", "결림",
        # 교통사고
        "교통사고", "자동차사고", "자보", "입원", "사고", "후유증",
        # 피부
        "여드름", "피부", "흉터", "트러블", "새살침", "모공", "기미",
        "주름", "리프팅", "탄력", "노화", "잡티", "색소", "홍조",
        # 한의원 일반
        "한의원", "한방", "침", "뜸", "한약", "보약", "공진단", "경옥고",
        "체질", "사상", "면역", "보양", "기력", "피로", "무기력",
        # 여성건강
        "생리통", "생리", "갱년기", "폐경", "산후", "산후조리", "임신",
        "자궁", "난소", "호르몬", "냉증", "수족냉증",
        # 기타 증상
        "불면", "수면", "두통", "어지럼", "소화", "위염", "역류",
        "비염", "알레르기", "아토피", "탈모", "다한증", "땀",
        "스트레스", "우울", "불안", "긴장", "화병",
    ]
    HEALTH_KEYWORDS = list(dict.fromkeys(
        HEALTH_KEYWORDS
        + list(getattr(GYULIM_KEYWORD_PROFILE, "hanbang_keywords", ()))
        + REGION_KEYWORDS
    ))

    # [Phase 2 개선] 키워드 티어별 가치 차등화
    KEYWORD_TIER1 = [  # 핵심 상품 (15점)
        "다이어트한약", "안면비대칭", "새살침", "체형교정", "골반교정",
        "여드름흉터", "패인흉터", "모공흉터", "수두흉터", "흉터치료",
        "얼굴비대칭", "입원치료"
    ]
    KEYWORD_TIER2 = [  # 주요 서비스 (10점)
        "교통사고", "다이어트", "여드름", "피부질환", "아토피", "지루성피부염",
        "탈모", "비염", "갱년기", "추나", "디스크", "산후조리", "공진단"
    ]
    KEYWORD_TIER3 = [  # 일반 (5점)
        "한의원", "한약", "침", "뜸", "부항", "한방", "체질", "보약"
    ]

    def _calculate_keyword_tier_score(self, matched_keywords: List[str]) -> int:
        """키워드 티어별 차등 점수 계산 (최대 40점)"""
        score = 0
        for kw in matched_keywords:
            kw_lower = kw.lower()
            if any(t in kw_lower for t in self.KEYWORD_TIER1):
                score += 15
            elif any(t in kw_lower for t in self.KEYWORD_TIER2):
                score += 10
            else:
                score += 5
        return min(score, 40)  # 최대 40점

    @staticmethod
    def _score_breakdown_float(target: ViralTarget, key: str, default: float = 0.0) -> float:
        try:
            value = (target.score_breakdown or {}).get(key, default)
            if value is None or value == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _score_breakdown_text(target: ViralTarget, key: str, default: str = "") -> str:
        value = (target.score_breakdown or {}).get(key, default)
        return default if value is None else str(value)

    @classmethod
    def _pathfinder_execution_context(cls, target: ViralTarget) -> Dict[str, Any]:
        """Return Pathfinder execution signals attached to this candidate post."""
        return {
            "viral_readiness": cls._score_breakdown_float(target, "pathfinder_viral_readiness_score"),
            "local_service_fit": cls._score_breakdown_float(target, "pathfinder_local_service_fit_score"),
            "content_actionability": cls._score_breakdown_float(target, "pathfinder_content_actionability_score"),
            "medical_ad_risk": cls._score_breakdown_float(target, "pathfinder_medical_ad_risk_score"),
            "community_signal": cls._score_breakdown_float(target, "pathfinder_community_signal"),
            "conversion_signal": cls._score_breakdown_float(target, "pathfinder_conversion_signal"),
            "profile_action_signal": cls._score_breakdown_float(target, "pathfinder_profile_action_signal"),
            "availability_intent_score": cls._score_breakdown_float(target, "pathfinder_availability_intent_score"),
            "payment_coverage_score": cls._score_breakdown_float(target, "pathfinder_payment_coverage_score"),
            "access_convenience_score": cls._score_breakdown_float(target, "pathfinder_access_convenience_score"),
            "preferred_surface": cls._score_breakdown_text(target, "pathfinder_preferred_search_surface"),
            "recommended_type": cls._score_breakdown_text(target, "pathfinder_recommended_content_type"),
            "brand_intent_type": cls._score_breakdown_text(target, "pathfinder_brand_intent_type", "generic"),
            "review_intent_type": cls._score_breakdown_text(target, "pathfinder_review_intent_type", "none"),
            "execution_lens": cls._score_breakdown_text(target, "pathfinder_execution_lens"),
        }

    @classmethod
    def _pathfinder_lens_post_fit(
        cls,
        target: ViralTarget,
        *,
        platform: Optional[str] = None,
        text: str = "",
    ) -> Tuple[float, str, List[str]]:
        """Score whether a candidate post matches the Pathfinder seed's execution lens."""
        lens = str(cls._pathfinder_execution_context(target).get("execution_lens") or "").strip().lower()
        if not lens or lens == "service":
            return 50.0, "neutral", []

        text_lc = (text or "").lower()
        platform_key = (platform or target.platform or "").lower()
        lens_terms = {
            "review": (
                "\ucd94\ucc9c", "\ud6c4\uae30", "\uc798\ud558\ub294", "\uad1c\ucc2e", "\uc5b4\ub514",
                "\uacbd\ud5d8", "\uac00\ubcf8", "\uc544\uc2dc\ub294", "review", "recommend",
            ),
            "community": (
                "\ucd94\ucc9c", "\ud6c4\uae30", "\uc5b4\ub514", "\uacbd\ud5d8", "\uac00\ubcf8",
                "\uc544\uc2dc\ub294", "\ubd84\ub4e4", "\uac19\uc740", "\uad81\uae08", "review", "recommend",
            ),
            "cost": (
                "\ube44\uc6a9", "\uac00\uaca9", "\uc5bc\ub9c8", "\uc2e4\ube44", "\ubcf4\ud5d8",
                "\uc790\ubcf4", "\uce58\ub8cc\ube44", "\ubd80\ub2f4", "cost", "price", "insurance",
            ),
            "consultation": (
                "\uc0c1\ub2f4", "\ubb38\uc758", "\ucc98\ubc29", "\uc9c4\ub2e8",
                "\uc0c1\ub2f4\ubc1b", "\uce58\ub8cc\ubc1b", "\uac80\uc0ac\ubc1b",
                "\uad81\uae08", "\uc54c\uace0\uc2f6", "consult", "consultation", "inquiry",
            ),
            "availability": (
                "\uc608\uc57d", "\uc608\uc57d\uac00\ub2a5", "\uc57c\uac04", "\uc8fc\ub9d0",
                "\uc9c4\ub8cc\uc2dc\uac04", "\ub2f9\uc77c\uc9c4\ub8cc",
                "\uc624\ub298", "\ub2f9\uc77c", "booking", "appointment",
                "\uc704\uce58", "\uae38\ucc3e\uae30", "\uc8fc\ucc28", "\ub3c4\ubcf4",
                "\uc5d8\ub9ac\ubca0\uc774\ud130", "\ud720\uccb4\uc5b4", "\ub300\uc911\uad50\ud1b5",
                "\uadfc\ucc98", "\uac00\uae4c\uc6b4", "near", "hours", "parking",
            ),
            "safety": (
                "\ubd80\uc791\uc6a9", "\uc8fc\uc758", "\uce58\ub8cc\uae30\uac04", "\ud1b5\uc99d", "\ud68c\ubcf5",
                "\uc7ac\ubc1c", "\uc548\uc804", "\ud6a8\uacfc", "\uac71\uc815", "sideeffect", "side-effect",
                "recovery", "safety",
            ),
        }
        terms = lens_terms.get(lens)
        if not terms:
            return 50.0, "neutral", []

        matched_terms = [term for term in terms if term and term in text_lc]
        community_bridge_terms = (
            "추천", "후기", "어디", "경험", "가본", "가보신", "해보신",
            "아시는", "궁금", "부탁", "괜찮", "잘하는",
        )
        bridge_term_hits = [term for term in community_bridge_terms if term and term in text_lc]
        query_variant = cls._pathfinder_query_variant(target)
        bridge_variant = (
            query_variant.startswith(f"{lens}_community:")
            or (
                lens in {"cost", "consultation", "availability", "safety"}
                and (
                    query_variant.startswith("axis_")
                    or query_variant == "patient_voice_kin"
                )
            )
        )
        signals: List[str] = []
        score = 45.0

        if matched_terms:
            score += min(35.0, 18.0 + len(matched_terms) * 4.0)
            signals.append(f"pathfinder_lens_{lens}_match")
            if platform_key in {"cafe", "naver_cafe", "kin", "naver_kin"}:
                score += 8.0
                signals.append("pathfinder_lens_surface_match")
        elif bridge_variant and bridge_term_hits:
            score += min(22.0, 10.0 + len(bridge_term_hits) * 3.0)
            signals.append(f"pathfinder_lens_{lens}_community_bridge")
            if platform_key in {"cafe", "naver_cafe", "kin", "naver_kin"}:
                score += 6.0
                signals.append("pathfinder_lens_surface_match")
        else:
            score -= 18.0
            signals.append(f"pathfinder_lens_{lens}_mismatch")
            if platform_key == "blog" and lens in {"review", "community", "cost"}:
                score -= 6.0
                signals.append("pathfinder_lens_blog_weak_match")

        if lens in {"review", "community"} and platform_key in {"cafe", "naver_cafe", "kin", "naver_kin"}:
            score += 5.0
        if lens in {"cost", "consultation", "availability"} and cls._contains_region_terms(text_lc, cls.REGION_KEYWORDS):
            score += 4.0

        score = round(max(0.0, min(100.0, score)), 2)
        if score >= 75.0:
            tier = "strong"
        elif score >= 55.0:
            tier = "acceptable"
        elif score >= 40.0:
            tier = "weak"
        else:
            tier = "mismatch"
        return score, tier, list(dict.fromkeys(signals))

    @classmethod
    def _pathfinder_source_specific_terms(cls, target: ViralTarget, category: str) -> List[str]:
        """Specific source-seed terms that should survive into the candidate post."""
        breakdown = target.score_breakdown or {}
        seed_terms: List[str] = []
        raw_sources = breakdown.get("pathfinder_source_keywords")
        if isinstance(raw_sources, list):
            seed_terms.extend(str(item) for item in raw_sources if str(item or "").strip())
        elif raw_sources:
            seed_terms.append(str(raw_sources))
        raw_source = breakdown.get("pathfinder_source_keyword")
        if raw_source:
            seed_terms.append(str(raw_source))
        seed_terms.extend(target.matched_keywords or [])
        terms: List[str] = []
        for seed_keyword in dict.fromkeys(seed_terms):
            if not seed_keyword:
                continue
            terms.extend(_pathfinder_axis_specific_terms_for_keyword(seed_keyword, category, limit=3))
        return list(dict.fromkeys(terms))

    @classmethod
    def _pathfinder_primary_source_specific_terms(cls, target: ViralTarget, category: str) -> List[str]:
        """Specific terms from the primary Pathfinder seed, used for strict source-fit gates."""
        breakdown = target.score_breakdown or {}
        seed_keyword = str(breakdown.get("pathfinder_source_keyword") or "").strip()
        if not seed_keyword:
            raw_sources = breakdown.get("pathfinder_source_keywords")
            if isinstance(raw_sources, list):
                seed_keyword = str(next((item for item in raw_sources if str(item or "").strip()), "")).strip()
            elif raw_sources:
                seed_keyword = str(raw_sources or "").strip()
        if not seed_keyword and target.matched_keywords:
            seed_keyword = str(target.matched_keywords[0] or "").strip()
        if not seed_keyword:
            return []
        return _pathfinder_axis_specific_terms_for_keyword(seed_keyword, category, limit=3)

    PATHFINDER_SOURCE_TERM_ALIASES: Dict[str, Tuple[str, ...]] = {
        "자동차보험": ("자동차 보험", "자보", "보험접수", "보험 접수", "자보처리", "자보 처리"),
        "자보": ("자동차보험", "자동차 보험", "보험접수", "보험 접수", "자보처리", "자보 처리"),
        "여드름자국": ("여드름 자국", "붉은자국", "붉은 자국", "갈색자국", "갈색 자국", "색소침착"),
        "붉은자국": ("붉은 자국", "여드름자국", "여드름 자국", "색소침착", "갈색자국", "갈색 자국"),
        "갈색자국": ("갈색 자국", "여드름자국", "여드름 자국", "색소침착", "붉은자국", "붉은 자국"),
        "안면비대칭": ("얼굴비대칭", "얼굴 비대칭", "턱비대칭", "턱 비대칭", "좌우비대칭", "좌우 비대칭"),
        "얼굴비대칭": ("얼굴 비대칭", "안면비대칭", "턱비대칭", "턱 비대칭", "좌우비대칭", "좌우 비대칭"),
        "턱비대칭": ("턱 비대칭", "안면비대칭", "얼굴비대칭", "얼굴 비대칭", "좌우비대칭", "좌우 비대칭"),
        "광대비대칭": ("광대 비대칭", "광대좌우차이", "광대 좌우 차이"),
        "광대좌우차이": ("광대 좌우 차이", "광대비대칭", "광대 비대칭"),
        "좌우비대칭": ("좌우 비대칭", "얼굴좌우차이", "얼굴 좌우 차이"),
        "얼굴좌우차이": ("얼굴 좌우 차이", "좌우비대칭", "좌우 비대칭"),
        "두상비대칭": ("두상 비대칭", "머리비대칭", "머리 비대칭"),
        "머리비대칭": ("머리 비대칭", "두상비대칭", "두상 비대칭"),
        "턱관절": ("턱 관절", "턱관절통증", "턱관절 통증", "턱통증", "턱 통증"),
        "다이어트한약": ("다이어트 한약", "한방다이어트", "한방 다이어트", "감량한약", "감량 한약"),
        "한방다이어트": ("한방 다이어트", "다이어트한약", "다이어트 한약", "감량한약", "감량 한약"),
        "편평사마귀": ("편평 사마귀",),
    }
    PATHFINDER_SOURCE_NEGATION_AFTER_RE = re.compile(
        r"^(?:은|는|이|가|도|쪽|쪽은|관련|관련은|치료|치료는|상담|상담은)?"
        r"(?:아니고|아니라|아님|아닌|아닙|아니에|아니었|말고|말구|제외|빼고|"
        r"안하고|안하|안되|안돼|안됨|못하|불가)"
    )
    PATHFINDER_SOURCE_NEGATION_BEFORE_TERMS: Tuple[str, ...] = (
        "말고",
        "말구",
        "제외",
        "제외하고",
        "빼고",
    )
    PATHFINDER_STRICT_SOURCE_CONTEXT_TERMS: Dict[str, Tuple[str, ...]] = {
        "흉터/여드름흉터": (
            "여드름자국", "여드름 자국", "붉은자국", "붉은 자국",
            "갈색자국", "갈색 자국", "색소침착", "수술흉터", "수술 흉터",
            "수두흉터", "수두 흉터", "켈로이드", "패인흉터", "패인 흉터",
            "모공흉터", "모공 흉터", "상처흉터", "상처 흉터",
        ),
        "피부/여드름": (
            "성인여드름", "성인 여드름", "아토피", "지루성피부염",
            "지루성 피부염", "편평사마귀", "편평 사마귀", "색소침착",
        ),
        "교통사고": (
            "입원", "자보", "자동차보험", "자동차 보험", "보험접수", "보험 접수",
            "후유증", "목통증", "허리통증",
        ),
        "안면비대칭": (
            "턱관절", "턱 관절", "턱비대칭", "턱 비대칭", "광대비대칭",
            "광대 비대칭", "광대좌우차이", "광대 좌우 차이",
            "좌우비대칭", "좌우 비대칭", "얼굴좌우차이", "얼굴 좌우 차이",
            "두상비대칭", "두상 비대칭", "머리비대칭", "머리 비대칭",
        ),
        "다이어트": (
            "산후", "요요", "감량한약", "감량 한약",
        ),
    }

    @classmethod
    def _pathfinder_source_context_is_negated(
        cls,
        candidate: str,
        *,
        compact_text: str,
        start_idx: int,
    ) -> bool:
        compact = _compact_query_text(candidate)
        if not compact or start_idx < 0:
            return False
        before = compact_text[max(0, start_idx - 12):start_idx]
        after = compact_text[start_idx + len(compact): start_idx + len(compact) + 16]
        if cls.PATHFINDER_SOURCE_NEGATION_AFTER_RE.match(after):
            return True
        return any(before.endswith(_compact_query_text(term)) for term in cls.PATHFINDER_SOURCE_NEGATION_BEFORE_TERMS)

    @classmethod
    def _pathfinder_source_fit_text(cls, target: ViralTarget, text: str = "") -> str:
        """Use user-authored text for source-specific fit so KIN answers do not inflate it."""
        platform = (getattr(target, "platform", "") or "").lower()
        preview = getattr(target, "content_preview", "") or ""
        if platform in {"kin", "naver_kin"} or "[기존답변" in preview or "[기존 답변" in preview:
            user_text = cls._user_need_text(target).lower()
            if user_text:
                return user_text
        return (text or "").lower()

    @classmethod
    def _pathfinder_source_specific_term_matches(
        cls,
        term: str,
        *,
        text_lc: str,
        compact_text: str,
    ) -> bool:
        """Match a source-specific concept, allowing clinic-domain synonyms."""
        candidates = [str(term or "").strip()]
        candidates.extend(cls.PATHFINDER_SOURCE_TERM_ALIASES.get(str(term or "").strip(), ()))
        for candidate in candidates:
            clean = str(candidate or "").strip().lower()
            if not clean:
                continue
            compact = re.sub(r"\s+", "", clean)
            if not compact:
                continue
            start = 0
            while True:
                idx = compact_text.find(compact, start)
                if idx < 0:
                    break
                if not cls._pathfinder_source_context_is_negated(
                    clean,
                    compact_text=compact_text,
                    start_idx=idx,
                ):
                    return True
                start = idx + max(1, len(compact))
        return False

    @classmethod
    def _pathfinder_source_specific_coverage(
        cls,
        target: ViralTarget,
        category: str,
        *,
        text_lc: str,
        compact_text: str,
        source_specific_terms: Optional[List[str]] = None,
    ) -> Tuple[List[str], List[str]]:
        terms = list(dict.fromkeys(source_specific_terms or cls._pathfinder_source_specific_terms(target, category)))
        hits = [
            term for term in terms
            if cls._pathfinder_source_specific_term_matches(
                term,
                text_lc=text_lc,
                compact_text=compact_text,
            )
        ]
        return terms, list(dict.fromkeys(hits))

    @classmethod
    def _pathfinder_source_specific_strict_gap(
        cls,
        target: ViralTarget,
        category: str,
        *,
        text_lc: str,
        compact_text: str,
    ) -> bool:
        strict_terms = cls.PATHFINDER_STRICT_SOURCE_CONTEXT_TERMS.get(category, ())
        if not strict_terms:
            return False
        strict_compacts = {_compact_query_text(term) for term in strict_terms if str(term or "").strip()}
        source_terms = cls._pathfinder_primary_source_specific_terms(target, category)
        strict_source_terms = [
            term for term in source_terms
            if _compact_query_text(term) in strict_compacts
        ]
        if not strict_source_terms:
            return False
        _, strict_hits = cls._pathfinder_source_specific_coverage(
            target,
            category,
            text_lc=text_lc,
            compact_text=compact_text,
            source_specific_terms=strict_source_terms,
        )
        if len(strict_source_terms) >= 2:
            return len(strict_hits) < len(strict_source_terms)
        return not strict_hits

    @classmethod
    def _pathfinder_axis_post_fit(
        cls,
        target: ViralTarget,
        *,
        domain: str,
        text: str = "",
    ) -> Tuple[float, str, List[str]]:
        """Score whether the visible post body matches the Pathfinder treatment axis."""
        raw_category = (
            getattr(target, "matched_keyword_category", "") or
            getattr(target, "category", "") or
            GYULIM_KEYWORD_PROFILE.detect_category(" ".join(target.matched_keywords or []), default="")
        )
        category = GYULIM_KEYWORD_PROFILE.normalize_category(raw_category)
        profile = GYULIM_KEYWORD_PROFILE.profile_for(category)
        if not profile:
            return 50.0, "neutral", []

        text_lc = (text or "").lower()
        compact_text = re.sub(r"\s+", "", text_lc)
        source_text_lc = cls._pathfinder_source_fit_text(target, text_lc)
        source_compact_text = re.sub(r"\s+", "", source_text_lc)

        def matching_terms(terms: Iterable[str]) -> List[str]:
            matches: List[str] = []
            for term in terms:
                clean = str(term or "").strip().lower()
                if not clean:
                    continue
                compact = re.sub(r"\s+", "", clean)
                if clean in text_lc or (compact and compact in compact_text):
                    matches.append(str(term))
            return list(dict.fromkeys(matches))

        category_hits = matching_terms(profile.category_terms)
        core_hits = matching_terms(profile.core_tokens)
        anchor_hits = matching_terms(profile.direct_service_anchors)
        low_value_hits = matching_terms(profile.low_business_value_terms)
        primary_hits = list(dict.fromkeys(category_hits + core_hits))
        source_specific_terms, source_specific_hits = cls._pathfinder_source_specific_coverage(
            target,
            category,
            text_lc=source_text_lc,
            compact_text=source_compact_text,
        )
        strict_source_gap = cls._pathfinder_source_specific_strict_gap(
            target,
            category,
            text_lc=source_text_lc,
            compact_text=source_compact_text,
        )

        score = 35.0
        signals: List[str] = []
        if category_hits:
            score += min(28.0, 14.0 + len(category_hits) * 3.5)
            signals.append("pathfinder_axis_category_match")
        if core_hits:
            score += min(24.0, 10.0 + len(core_hits) * 4.0)
            signals.append("pathfinder_axis_core_match")
        if anchor_hits:
            score += min(12.0, 4.0 + len(anchor_hits) * 2.5)
            signals.append("pathfinder_axis_service_anchor")
        if low_value_hits:
            score -= min(24.0, 10.0 + len(low_value_hits) * 5.0)
            signals.append("pathfinder_axis_low_value_context")
        if not primary_hits:
            score -= 20.0
            signals.append("pathfinder_axis_no_primary_terms")
        if source_specific_terms:
            if not source_specific_hits:
                score -= 28.0
                signals.append("pathfinder_axis_specific_context_missing")
            else:
                hit_count = len(source_specific_hits)
                total_specific = max(1, len(source_specific_terms))
                coverage = hit_count / total_specific
                if hit_count == total_specific or coverage >= 0.8:
                    score += min(14.0, 8.0 + hit_count * 3.0)
                    signals.append("pathfinder_axis_specific_context_match")
                    if total_specific > 1:
                        signals.append("pathfinder_axis_specific_context_complete")
                else:
                    score += min(6.0, 2.0 + hit_count * 1.5)
                    score -= min(14.0, (total_specific - hit_count) * 4.0)
                    signals.append("pathfinder_axis_specific_context_partial")
        if strict_source_gap:
            score -= 18.0
            signals.append("pathfinder_axis_specific_context_strict_gap")

        region_score, region_signals = cls._region_fit_signal(
            text_lc, local_venue=cls._has_local_venue_anchor(target)
        )
        if region_score > 0:
            score += min(6.0, region_score * 0.20)
            signals.append("pathfinder_axis_local_context")

        competing_hits = 0
        competing_categories: List[str] = []
        for other_profile in getattr(GYULIM_KEYWORD_PROFILE, "profiles", ()):
            if other_profile.category == profile.category:
                continue
            other_hits = matching_terms(other_profile.category_terms + other_profile.core_tokens)
            if other_hits:
                competing_hits += len(other_hits)
                competing_categories.append(other_profile.category)
        if competing_hits > max(1, len(primary_hits) + 1):
            score -= min(18.0, 8.0 + competing_hits * 2.0)
            signals.append("pathfinder_axis_cross_axis_noise")
            if competing_categories:
                signals.append(
                    "pathfinder_axis_competes_with:" + ",".join(list(dict.fromkeys(competing_categories))[:3])
                )

        if domain != "general" and cls._has_domain_anchor(domain, text_lc):
            score += 4.0
            signals.append("pathfinder_axis_domain_anchor")

        if strict_source_gap:
            score = min(score, 54.0)

        score = round(max(0.0, min(100.0, score)), 2)
        if score >= 75.0:
            tier = "strong"
        elif score >= 55.0:
            tier = "acceptable"
        elif score >= 38.0:
            tier = "weak"
        else:
            tier = "mismatch"
        return score, tier, list(dict.fromkeys(signals + region_signals[:1]))

    @classmethod
    def _pathfinder_execution_adjustment(
        cls,
        target: ViralTarget,
        *,
        platform: Optional[str] = None,
        text: str = "",
    ) -> Tuple[float, List[str]]:
        """Translate Pathfinder keyword readiness into post-level scoring signals."""
        ctx = cls._pathfinder_execution_context(target)
        readiness = float(ctx["viral_readiness"] or 0.0)
        actionability = float(ctx["content_actionability"] or 0.0)
        medical_risk = float(ctx["medical_ad_risk"] or 0.0)
        local_fit = float(ctx["local_service_fit"] or 0.0)
        community = float(ctx["community_signal"] or 0.0)
        conversion = float(ctx["conversion_signal"] or 0.0)
        profile_action = float(ctx["profile_action_signal"] or 0.0)
        preferred_surface = str(ctx["preferred_surface"] or "")
        recommended_type = str(ctx["recommended_type"] or "")
        review_intent_type = str(ctx["review_intent_type"] or "none")
        platform_key = (platform or target.platform or "").lower()
        text_lc = (text or "").lower()

        adjustment = 0.0
        signals: List[str] = []

        if readiness >= 75.0:
            adjustment += min(12.0, (readiness - 60.0) * 0.32)
            signals.append("pathfinder_ready_keyword")
        elif 0.0 < readiness < 35.0:
            adjustment -= min(10.0, (35.0 - readiness) * 0.28)
            signals.append("pathfinder_low_readiness")

        if actionability >= 75.0:
            adjustment += min(8.0, (actionability - 60.0) * 0.24)
            signals.append("pathfinder_actionable_content")
        elif 0.0 < actionability < 45.0:
            adjustment -= min(12.0, (45.0 - actionability) * 0.32)
            signals.append("pathfinder_low_actionability")

        if local_fit >= 75.0 and cls._contains_region_terms(text_lc, cls.REGION_KEYWORDS):
            adjustment += min(6.0, (local_fit - 60.0) * 0.18)
            signals.append("pathfinder_local_service_fit")
        elif 0.0 < local_fit < 40.0:
            adjustment -= min(10.0, (40.0 - local_fit) * 0.24)
            signals.append("pathfinder_local_service_weak")

        if community >= 60.0 and platform_key in {"cafe", "naver_cafe", "kin", "naver_kin"}:
            adjustment += min(7.0, (community - 50.0) * 0.20)
            signals.append("pathfinder_community_surface_fit")
        if conversion >= 55.0:
            adjustment += min(6.0, (conversion - 45.0) * 0.18)
            signals.append("pathfinder_conversion_signal")
        if profile_action >= 55.0:
            adjustment += min(5.0, (profile_action - 45.0) * 0.16)
            signals.append("pathfinder_profile_action_signal")

        if preferred_surface in {"hybrid_local_content", "profile_action", "local_pack"}:
            if platform_key in {"cafe", "naver_cafe", "kin", "naver_kin"}:
                adjustment += 4.0
                signals.append("pathfinder_surface_match")
            elif platform_key == "blog":
                adjustment += 1.5
                signals.append("pathfinder_surface_partial_match")
        if recommended_type in {"faq_safety", "service_landing", "access_landing"}:
            adjustment += 3.0
            signals.append("pathfinder_content_type_fit")
        if review_intent_type not in {"", "none"} and platform_key in {"cafe", "naver_cafe", "kin", "naver_kin"}:
            adjustment += 3.0
            signals.append("pathfinder_review_intent_surface")

        if medical_risk >= 70.0:
            adjustment -= 18.0
            signals.append("pathfinder_high_medical_ad_risk")
        elif medical_risk >= 40.0:
            adjustment -= 7.0
            signals.append("pathfinder_medical_ad_review")

        return round(max(-28.0, min(28.0, adjustment)), 2), list(dict.fromkeys(signals))

    @classmethod
    def _keyword_domain(cls, matched_keywords: List[str], category: str = "") -> str:
        """검색 키워드가 어느 진료 축에 속하는지 추정한다."""
        joined = " ".join(matched_keywords or []).lower()
        if any(k in joined for k in ["교통사고", "자동차사고", "자보", "입원"]):
            return "traffic"
        if any(k in joined for k in ["다이어트", "다이어트한약", "한약", "비만", "감량", "체중"]):
            return "diet"
        if any(k in joined for k in ["여드름", "흉터", "새살침", "패인흉터", "모공"]):
            return "scar_skin"
        if any(k in joined for k in ["안면비대칭", "얼굴비대칭", "비대칭", "턱관절", "턱교정", "두상비대칭"]):
            return "asymmetry"
        if any(k in joined for k in ["체형", "골반", "척추", "측만", "자세"]):
            return "body"
        if any(k in joined for k in ["리프팅", "탄력", "매선", "주름"]):
            return "lifting"
        category_key = GYULIM_KEYWORD_PROFILE.normalize_category(category)
        category_domain_map = {
            "흉터/여드름흉터": "scar_skin",
            "피부/여드름": "scar_skin",
            "다이어트": "diet",
            "안면비대칭": "asymmetry",
            "체형교정": "body",
            "통증/디스크": "body",
            "교통사고": "traffic",
            "리프팅/탄력": "lifting",
        }
        if category_key in category_domain_map:
            return category_domain_map[category_key]
        return "general"

    @classmethod
    def _target_domain(cls, target: ViralTarget) -> str:
        category = (
            getattr(target, "matched_keyword_category", "") or
            getattr(target, "category", "") or
            ""
        )
        return cls._keyword_domain(getattr(target, "matched_keywords", []) or [], category=category)

    @classmethod
    def _own_content_domain(cls, target: ViralTarget) -> str:
        """글 자체 텍스트로 감지한 진료축 도메인 (시드 lineage와 무관)."""
        detected = cls._own_content_category(target)
        if not detected:
            return ""
        return cls._keyword_domain([], category=detected)

    @classmethod
    def _own_content_category(cls, target: ViralTarget) -> str:
        """글 자체 텍스트로 감지한 활성 프로필 진료축 카테고리."""
        detected = GYULIM_KEYWORD_PROFILE.normalize_category(
            GYULIM_KEYWORD_PROFILE.detect_category(
                f"{target.title or ''} {target.content_preview or ''}",
                default="",
            )
        )
        if not detected or not GYULIM_KEYWORD_PROFILE.profile_for(detected):
            return ""
        return detected

    @classmethod
    def _cross_axis_reject_reason(cls, target: ViralTarget, *, seed_domain: str) -> Optional[str]:
        """교차축 후보를 자기 축 기준으로 1회 재귀 평가.

        시드 lineage를 글 자체 카테고리로 바꾼 clone에 전체 최종 게이트를 다시
        돌린다 — 자기 축의 노이즈/광고/지역 검사를 전부 통과해야 None. 자기 축이
        감지되지 않거나 시드 축과 같으면(재귀 종료 조건) 구제하지 않는다.
        """
        if (target.score_breakdown or {}).get("_cross_axis_eval"):
            return "domain_mismatch"
        # 사용자 질문 표면만 — blog 교차축 후보는 라이브 리뷰 결과 대부분 업체
        # SEO/홍보 콘텐츠였다 (블로그는 자기 축 전용 레인으로만 들어온다).
        if (target.platform or "").lower() not in {"cafe", "naver_cafe", "kin", "naver_kin"}:
            return "domain_mismatch"
        own_category = cls._own_content_category(target)
        if not own_category:
            return "domain_mismatch"
        own_domain = cls._keyword_domain([], category=own_category)
        if not own_domain or own_domain == seed_domain:
            return "domain_mismatch"
        import copy as _copy
        clone = _copy.copy(target)
        clone.matched_keyword_category = own_category
        clone.category = own_category
        # 시드 키워드 lineage를 비워 클론 도메인이 자기 카테고리로만 풀리게 한다 —
        # 원본 키워드(예: 다이어트 시드)가 남으면 도메인이 다시 시드 축으로 돌아간다.
        clone.matched_keywords = []
        clone.score_breakdown = {**(target.score_breakdown or {}), "_cross_axis_eval": True}
        # 자기 축의 user-axis 앵커(축별 정선 패턴)까지 요구 — detect_category의
        # 우발 매칭(성형/운동 글의 체형·비대칭 단어 등)이 구제되는 것을 막는다.
        if not cls._has_user_axis_anchor(clone, domain=own_domain, category=own_category):
            return "domain_mismatch"
        return cls.final_reject_reason(clone)

    @classmethod
    def _profile_categories_for_target(cls, target: ViralTarget, domain: str) -> List[str]:
        """Return Pathfinder clinic profile categories that can explain this target."""
        candidates = [
            getattr(target, "matched_keyword_category", "") or "",
            getattr(target, "category", "") or "",
        ]
        domain_map = {
            "diet": "다이어트",
            "traffic": "교통사고",
            "asymmetry": "안면비대칭",
            "body": "체형교정",
            "lifting": "리프팅/탄력",
        }
        if domain == "scar_skin":
            candidates.extend(["흉터/여드름흉터", "피부/여드름"])
        if domain in domain_map:
            candidates.append(domain_map[domain])

        normalized: List[str] = []
        for raw in candidates:
            category = GYULIM_KEYWORD_PROFILE.normalize_category(raw)
            if category and category not in normalized:
                normalized.append(category)
            profile = GYULIM_KEYWORD_PROFILE.profile_for(raw)
            if profile and profile.category not in normalized:
                normalized.append(profile.category)
        return normalized

    _LOCAL_VENUE_TOKENS_CACHE: Optional[List[str]] = None

    @classmethod
    def _local_venue_tokens(cls) -> List[str]:
        """청주 로컬 커뮤니티 식별 토큰(시·구·동). nearby(진천/증평 등)는 제외 —
        진료권 정밀도를 위해 청주 본권만. 1글자/모호 토큰은 카페명 오매칭 방지로 제외."""
        if cls._LOCAL_VENUE_TOKENS_CACHE is None:
            toks: set = set()
            for raw in (
                list(GYULIM_KEYWORD_PROFILE.cheongju_regions)
                + list(GYULIM_KEYWORD_PROFILE.neighborhoods)
            ):
                token = (raw or "").strip()
                if len(token) >= 2 and token not in cls.AMBIGUOUS_CHEONGJU_REGION_STEMS:
                    toks.add(token)
            cls._LOCAL_VENUE_TOKENS_CACHE = sorted(toks, key=len, reverse=True)
        return cls._LOCAL_VENUE_TOKENS_CACHE

    @classmethod
    def _has_local_venue_anchor(cls, target: ViralTarget) -> bool:
        """카페 식별명이 청주 로컬 커뮤니티임을 나타내면 True.

        환자는 user-surface 축(흉터/피부/비대칭) 질문에 지역을 거의 안 적지만,
        '청주맘스캠프'·'러브인오송' 같은 카페 정체성 자체가 강한 지역 신호다.
        텍스트-온리 지역 판정이 구조적으로 놓치던 recall 공백을 메운다(라이브
        감사 2026-06-13: 핵심축 청주-카페 글 362건이 본문 무지역으로 저평가).
        cafe만 사용 — 블로그 bloggername은 업체 SEO 비중이 높아 제외.
        """
        platform = (getattr(target, "platform", "") or "").lower()
        if platform not in {"cafe", "naver_cafe"}:
            return False
        venue = getattr(target, "author", "") or ""
        if not venue:
            return False
        return cls._contains_any(venue, cls._local_venue_tokens())

    @classmethod
    def _region_fit_signal(cls, text: str, local_venue: bool = False) -> Tuple[int, List[str]]:
        """Score how close the post is to the clinic's real operating area."""
        score = 0
        signals: List[str] = []
        area_signal = getattr(GYULIM_KEYWORD_PROFILE, "area_signal", "target_area")
        neighborhood_signal = getattr(GYULIM_KEYWORD_PROFILE, "neighborhood_signal", "target_neighborhood")
        if cls._contains_region_terms(text, list(GYULIM_KEYWORD_PROFILE.cheongju_regions)):
            score += 18
            signals.append(area_signal)
        if cls._contains_region_terms(text, list(GYULIM_KEYWORD_PROFILE.neighborhoods)):
            score += 12
            signals.append(neighborhood_signal)
        if cls._contains_region_terms(text, list(GYULIM_KEYWORD_PROFILE.nearby_regions)):
            score += 7
            signals.append("nearby_region")

        # 카페 정체성 기반 로컬 앵커 — 본문에 지역 토큰이 없을 때만 보강(중복 가산 방지).
        # '청주맘카페' 글이 지역명 없이도 로컬로 정당하게 평가받게 한다.
        if local_venue and area_signal not in signals and neighborhood_signal not in signals:
            score += 15
            signals.append(area_signal)
            signals.append("local_venue_anchor")

        active_local_terms = set(GYULIM_KEYWORD_PROFILE.cheongju_regions) | set(GYULIM_KEYWORD_PROFILE.neighborhoods) | set(GYULIM_KEYWORD_PROFILE.nearby_regions)
        distant_regions = list(cls.DISTANT_REGION_KEYWORDS)
        distant_regions = [region for region in distant_regions if region not in active_local_terms]
        has_primary = any(s in signals for s in (area_signal, neighborhood_signal))
        if distant_regions and cls._contains_any(text, distant_regions) and not has_primary:
            score -= 24
            signals.append("distant_region")
        return score, signals

    @classmethod
    def _is_distant_local_target(cls, title: str, text: str, local_venue: bool = False) -> bool:
        """Reject posts whose visible target market is outside the active clinic area."""
        active_local_terms = (
            set(GYULIM_KEYWORD_PROFILE.cheongju_regions)
            | set(GYULIM_KEYWORD_PROFILE.neighborhoods)
            | set(GYULIM_KEYWORD_PROFILE.nearby_regions)
        )
        distant_regions = [region for region in cls.DISTANT_REGION_KEYWORDS if region not in active_local_terms]
        if not distant_regions:
            return False

        title_has_distant = cls._contains_any(title, distant_regions)
        title_has_active = cls._contains_region_terms(title, active_local_terms)
        if title_has_distant and not title_has_active:
            # 제목이 명시적으로 타지역을 타겟 — 카페가 로컬이어도 그 글은 타지역 글.
            return True

        # 청주 로컬 카페 글은 본문이 우연히 타지역을 언급해도 로컬로 간주한다(앵커
        # = 카페 정체성). 제목 명시 타겟 킬은 위에서 이미 처리했고, 업체 답변/광고
        # 침투는 advertorial 게이트가 별도로 잡으므로 여기서 구멍이 나지 않는다.
        if local_venue:
            return False

        text_has_distant = cls._contains_any(text, distant_regions)
        text_has_active = cls._contains_region_terms(text, active_local_terms)
        explicit_cheongju = cls._contains_region_terms(text, ["청주", "충북", "충청북도"])
        if text_has_distant and not explicit_cheongju:
            return True
        return bool(text_has_distant and not text_has_active)

    @classmethod
    def _assess_clinic_treatment_fit(
        cls,
        target: ViralTarget,
        domain: str,
        text: str,
        is_health: bool,
    ) -> Tuple[int, str, List[str]]:
        """Score whether the post fits the active clinic's actual treatment portfolio."""
        score, signals = cls._region_fit_signal(
            text, local_venue=cls._has_local_venue_anchor(target)
        )
        categories = cls._profile_categories_for_target(target, domain)
        profiles = [
            GYULIM_KEYWORD_PROFILE.profile_for(category)
            for category in categories
        ]
        profiles = [profile for profile in profiles if profile]

        if profiles:
            best_profile_score = 0.0
            compact_text = re.sub(r"\s+", "", text)

            def matching_terms(terms: Iterable[str]) -> List[str]:
                matches: List[str] = []
                for term in terms:
                    if not term:
                        continue
                    term_lower = term.lower()
                    term_compact = re.sub(r"\s+", "", term_lower)
                    if term_lower in text or (term_compact and term_compact in compact_text):
                        matches.append(term)
                return matches

            for profile in profiles:
                category_hits = matching_terms(profile.category_terms)
                anchor_hits = matching_terms(profile.direct_service_anchors)
                core_hits = matching_terms(profile.core_tokens)
                low_value_hits = matching_terms(profile.low_business_value_terms)

                profile_score = 0.0
                if category_hits:
                    profile_score += min(22.0, 8.0 + len(set(category_hits)) * 4.0)
                if core_hits:
                    profile_score += min(18.0, 6.0 + len(set(core_hits)) * 4.0)
                if anchor_hits:
                    profile_score += min(20.0, 8.0 + len(set(anchor_hits)) * 4.0)
                if low_value_hits:
                    profile_score -= min(28.0, 10.0 + len(set(low_value_hits)) * 6.0)
                profile_score *= max(0.7, min(1.35, float(profile.strategic_weight or 1.0)))
                best_profile_score = max(best_profile_score, profile_score)

            score += int(round(best_profile_score))
            signals.append(getattr(GYULIM_KEYWORD_PROFILE, "profile_match_signal", "clinic_profile_match"))
            signals.append("clinic_profile_match")
        elif domain != "general" and cls._has_domain_anchor(domain, text):
            score += 24
            signals.append("domain_anchor_match")
        else:
            score -= 18
            signals.append("no_profile_match")

        explicit_not_service = cls._contains_any(text, [
            "치료를 찾는 건 아니", "치료를 찾는건 아니",
            "상담이나 치료를 찾는 건 아니", "상담이나 치료를 찾는건 아니",
            "한의원 상담이나 치료를 찾는 건 아니", "한의원 상담이나 치료를 찾는건 아니",
        ])
        product_only_context = cls._contains_any(text, [
            "홈케어", "화장품", "제품 위주", "제품위주", "올리브영",
        ]) and not cls._contains_any(text, [
            "말고 한의원", "대신 한의원", "한의원으로", "한의원 상담",
            "한의원 치료", "한의원 알아", "새살침", "한약", "치료받",
            "치료 받", "상담받", "상담 받", "안 돼서", "안돼서",
            "효과 없어서", "효과없어서",
        ])
        non_service_request = explicit_not_service or product_only_context
        if non_service_request:
            score -= 24
            signals.append("non_service_request")

        if cls._contains_any(text, list(GYULIM_KEYWORD_PROFILE.hanbang_indicators)) and not non_service_request:
            score += 12
            signals.append("hanbang_service_anchor")
        if cls._contains_any(text, list(GYULIM_KEYWORD_PROFILE.high_intent_terms)):
            score += 10
            signals.append("high_intent_modifier")
        if target.matched_keyword_grade in {"S", "A"}:
            score += 8
            signals.append("pathfinder_top_grade")
        elif target.matched_keyword_grade == "B":
            score += 4
            signals.append("pathfinder_b_grade")
        if target.matched_keyword_priority >= 100:
            score += 8
            signals.append("pathfinder_high_priority")
        elif target.matched_keyword_priority >= 70:
            score += 4
            signals.append("pathfinder_priority")
        if is_health:
            score += 4
            signals.append("health_context")

        if cls._contains_any(text, list(GYULIM_KEYWORD_PROFILE.medical_general_tokens)):
            hanbang_skin_context = (
                cls._contains_any(
                    text,
                    list(GYULIM_KEYWORD_PROFILE.hanbang_indicators)
                    + ["한의원", "한방", "새살침", "침", "한약", "의원", "클리닉", "피부과", "레이저", "시술"],
                )
                and not non_service_request
            )
            if not hanbang_skin_context:
                score -= 18
                signals.append("western_provider_bias")

        score = max(0, min(100, score))
        if score >= 75:
            tier = "excellent"
        elif score >= 55:
            tier = "strong"
        elif score >= cls.MIN_CLINIC_TREATMENT_FIT_SCORE:
            tier = "acceptable"
        else:
            tier = "weak"
        return score, tier, list(dict.fromkeys(signals))

    @classmethod
    def _assess_worksite_efficiency(
        cls,
        target: ViralTarget,
        clinic_treatment_fit_score: int,
        viral_need_score: int,
        viral_need_signals: List[str],
        reply_opportunity_score: int,
        reply_opportunity_signals: List[str],
        timing_window_score: int,
        timing_window_signals: List[str],
        journey_fit_score: int,
        journey_stage: str,
        qualification_fit_score: int,
        risk_flags: List[str],
    ) -> Tuple[int, str, List[str]]:
        """Score how efficient this exact public surface is for a helpful reply."""
        platform = (target.platform or "").lower()
        score = 30
        signals: List[str] = []
        need_set = set(viral_need_signals or [])
        reply_set = set(reply_opportunity_signals or [])
        timing_set = set(timing_window_signals or [])

        if platform in {"cafe", "naver_cafe"}:
            score += 18
            signals.append("community_surface")
        elif platform in {"kin", "naver_kin"}:
            score += 15
            signals.append("qa_surface")
        elif platform == "blog":
            score -= 12
            signals.append("blog_low_comment_efficiency")
        elif platform in {"instagram", "tiktok", "youtube"}:
            score -= 6
            signals.append("social_thread_lower_intent")

        comment_count = max(0, int(getattr(target, "comment_count", 0) or 0))
        view_count = max(0, int(getattr(target, "view_count", 0) or 0))
        if comment_count == 0:
            score += 16
            signals.append("unanswered_thread")
        elif comment_count <= 2:
            score += 9
            signals.append("low_response_thread")
        elif comment_count >= 8:
            score -= 16
            signals.append("saturated_thread")
        if view_count >= 100 and comment_count <= 2:
            score += 8
            signals.append("visible_gap")

        if clinic_treatment_fit_score >= 75:
            score += 14
            signals.append("excellent_clinic_fit")
        elif clinic_treatment_fit_score >= 55:
            score += 8
            signals.append("strong_clinic_fit")
        elif clinic_treatment_fit_score < cls.MIN_CLINIC_TREATMENT_FIT_SCORE:
            score -= 22
            signals.append("weak_clinic_fit")

        if reply_opportunity_score >= 75:
            score += 12
            signals.append("reply_welcome")
        elif reply_opportunity_score < 45:
            score -= 12
            signals.append("weak_reply_opening")
        if timing_window_score >= 75:
            score += 12
            signals.append("fresh_response_window")
        elif timing_window_score < 45:
            score -= 12
            signals.append("aging_response_window")
        if journey_stage == "decision":
            score += 10
            signals.append("decision_stage")
        elif journey_stage == "consideration":
            score += 6
            signals.append("consideration_stage")
        elif journey_stage in {"awareness", "post_service"}:
            score -= 14
            signals.append("low_conversion_stage")
        if qualification_fit_score >= 75:
            score += 10
            signals.append("qualified_lead_context")
        elif qualification_fit_score < 45:
            score -= 10
            signals.append("thin_lead_context")

        if need_set & {"recommendation_request", "ready_to_act", "cost_decision"}:
            score += 8
            signals.append("actionable_need")
        if "help_request_language" in reply_set or "clear_question_shape" in reply_set:
            score += 6
            signals.append("natural_reply_opening")
        if "anti_ad_request" in need_set or "anti_ad_request" in reply_set:
            score -= 6
            signals.append("transparency_sensitive")
        if cls._is_response_restricted_surface(target):
            score -= 45
            signals.append("response_restricted_surface")
        if "posted_over_30d" in timing_set or "stale_language" in timing_set:
            score -= 14
            signals.append("stale_context")
        if risk_flags:
            score -= min(22, 7 * len(risk_flags))
            signals.append("medical_guardrail_load")

        score = max(0, min(100, score))
        if score >= 75:
            tier = "high_efficiency"
        elif score >= 55:
            tier = "efficient"
        elif score >= cls.MIN_WORKSITE_EFFICIENCY_SCORE:
            tier = "manual_selective"
        else:
            tier = "inefficient"
        return score, tier, list(dict.fromkeys(signals))

    @staticmethod
    def _contains_any(text: str, patterns: List[str]) -> bool:
        return any(pattern in text for pattern in patterns)

    @classmethod
    def _is_marketplace_sale(cls, text: str) -> bool:
        if cls._contains_any(text, cls.MARKETPLACE_SALE_PATTERNS):
            return True
        compact = re.sub(r"\s+", "", text)
        if cls._contains_any(compact, ["판매중", "판매완료", "양도완료", "무료나눔", "가격네고", "네고가능"]):
            return True
        return any(re.search(pattern, text) for pattern in cls.MARKETPLACE_SALE_REGEXES)

    @classmethod
    def _region_term_matches(cls, text: str, term: str) -> bool:
        """Match local tokens without treating common Korean words as Cheongju areas."""
        text_lc = (text or "").lower()
        term_lc = str(term or "").strip().lower()
        if not term_lc:
            return False
        if term_lc in cls.AMBIGUOUS_CHEONGJU_REGION_STEMS:
            escaped = re.escape(term_lc)
            return bool(
                re.search(rf"(?:청주(?:시)?\s*)?{escaped}구", text_lc)
                or re.search(rf"청주(?:시)?\s*{escaped}(?:\s|$|쪽|일대|근처|지역)", text_lc)
            )
        return term_lc in text_lc

    @classmethod
    def _contains_region_terms(cls, text: str, patterns: Iterable[str]) -> bool:
        return any(cls._region_term_matches(text, pattern) for pattern in patterns if pattern)

    @classmethod
    def _has_ambiguous_region_false_positive(cls, text: str) -> bool:
        text_lc = (text or "").lower()
        return any(
            stem in text_lc and not cls._region_term_matches(text_lc, stem)
            for stem in cls.AMBIGUOUS_CHEONGJU_REGION_STEMS
        )

    @classmethod
    def _has_active_region_anchor(
        cls,
        target: Optional[ViralTarget],
        text: str,
        *,
        local_venue: Optional[bool] = None,
    ) -> bool:
        active_terms = (
            list(getattr(GYULIM_KEYWORD_PROFILE, "cheongju_regions", ()))
            + list(getattr(GYULIM_KEYWORD_PROFILE, "neighborhoods", ()))
            + list(getattr(GYULIM_KEYWORD_PROFILE, "nearby_regions", ()))
        )
        if cls._contains_region_terms(text, active_terms):
            return True
        if local_venue is None and target is not None:
            local_venue = cls._has_local_venue_anchor(target)
        return bool(local_venue)

    @staticmethod
    def _strip_internal_labels(text: str) -> str:
        """Remove scanner-added leading labels so old queued rows are judged by real post text."""
        return re.sub(r"^\s*(?:\[[^\]]+\]\s*)+", "", text or "").strip()

    @classmethod
    def _user_need_text(cls, target: ViralTarget) -> str:
        """Return the part most likely written by the person asking for help."""
        body = target.content_preview or ""
        platform = (target.platform or "").lower()
        if platform in {"kin", "naver_kin"}:
            hard_split_markers = [
                "[기존답변",
                "[기존 답변",
                "기존답변",
                "# 병원 위치", "# 진료 예약", "# 병원 홈페이지", "# 프로필 보기",
                "안녕하세요, 닥톡", "안녕하세요. 닥톡",
                "답변드립니다", "답변 드립니다",
            ]
            soft_split_markers = ["안녕하세요,", "안녕하세요."]
            body_lc = body.lower()
            cut_points = [body_lc.find(marker.lower()) for marker in hard_split_markers]
            cut_points = [idx for idx in cut_points if idx >= 0]
            cut_points.extend(
                idx for idx in (body_lc.find(marker.lower()) for marker in soft_split_markers)
                if idx > 20
            )
            if cut_points:
                body = body[:min(cut_points)]
        body = cls._strip_internal_labels(body)
        return f"{target.title or ''} {body}".strip()

    @classmethod
    def _is_response_restricted_surface(cls, target: ViralTarget, text: str = "") -> bool:
        """Reject posts where the author explicitly closes public/provider responses."""
        user_text = cls._user_need_text(target).lower()
        evidence = f"{text or ''} {user_text}".lower()
        return cls._contains_any(evidence, cls.RESPONSE_HARD_REJECTION_PATTERNS)

    @classmethod
    def _axis_user_segment_text(cls, target: ViralTarget, *, max_body_chars: int = 150) -> str:
        """Short user-authored segment used for strict axis checks.

        Search snippets can include answer/provider text. For Pathfinder companion
        queries, full-snippet anchors are too permissive, so use title plus the
        opening body segment before giving a low-supply axis rescue.
        """
        title = (target.title or "").lower()
        body = cls._strip_internal_labels(target.content_preview or "").lower()
        platform = (target.platform or "").lower()
        if platform in {"kin", "naver_kin"}:
            # Naver Kin snippets often append provider answers; axis checks should
            # stay close to the asker's own wording.
            user_text = cls._user_need_text(target).lower()
            if title and user_text.startswith(title):
                body = user_text[len(title):].strip()
            else:
                body = user_text
            max_body_chars = min(max_body_chars, 70)
        return f"{title} {body[:max_body_chars]}".strip()

    @classmethod
    def _pathfinder_query_variant(cls, target: ViralTarget) -> str:
        return cls._score_breakdown_text(target, "pathfinder_query_variant", "")

    @classmethod
    def _is_axis_companion_variant(cls, target: ViralTarget, prefix: str) -> bool:
        return cls._pathfinder_query_variant(target).startswith(prefix)

    @classmethod
    def _has_user_axis_anchor(
        cls,
        target: ViralTarget,
        *,
        domain: str,
        category: str,
    ) -> bool:
        user_text = cls._axis_user_segment_text(target)
        if category == "체형교정" or domain == "body":
            return cls._contains_any(user_text, cls.BODY_USER_AXIS_ANCHOR_PATTERNS)
        if category == "안면비대칭" or domain == "asymmetry":
            return cls._contains_any(user_text, cls.ASYMMETRY_USER_AXIS_ANCHOR_PATTERNS)
        if category == "리프팅/탄력" or domain == "lifting":
            return cls._contains_any(user_text, cls.LIFTING_USER_AXIS_ANCHOR_PATTERNS)
        if category == "교통사고" or domain == "traffic":
            return cls._contains_any(user_text, cls.TRAFFIC_USER_CARE_ANCHOR_PATTERNS)
        if category == "흉터/여드름흉터":
            return cls._contains_any(user_text, cls.SCAR_USER_AXIS_ANCHOR_PATTERNS)
        if category == "피부/여드름":
            return cls._contains_any(user_text, cls.SKIN_USER_AXIS_ANCHOR_PATTERNS)
        return True

    @classmethod
    def _assess_viral_need(
        cls,
        target: ViralTarget,
        domain: str,
        is_inquiry: bool,
        is_health: bool,
    ) -> Tuple[int, str, List[str]]:
        """Score whether a post needs a helpful human reply now."""
        user_text = cls._user_need_text(target).lower()
        platform = (target.platform or "").lower()
        score = 0
        signals: List[str] = []

        def has(patterns: List[str]) -> bool:
            return any(pattern.lower() in user_text for pattern in patterns if pattern)

        compact_recommendation = (
            "추천" in user_text
            and any(marker in user_text for marker in ["부탁", "해주", "좀", "병원", "한의원", "피부과"])
        )
        recommendation_request = has(cls.RECOMMENDATION_REQUEST_PATTERNS) or compact_recommendation
        ready_to_act = has(cls.READY_TO_ACT_PATTERNS)
        cost_decision = has(cls.COST_DECISION_PATTERNS)
        pain_urgency = has(cls.PAIN_URGENCY_PATTERNS)
        comparison_eval = has(cls.COMPARISON_EVALUATION_PATTERNS)
        service_intent = recommendation_request or ready_to_act or cost_decision or comparison_eval
        problem_intent = pain_urgency and (
            has(cls.PROBLEM_INTENT_PATTERNS)
            or (
                cls._contains_any(user_text, cls.CONDITION_TERMS)
                and cls._contains_any(user_text, cls.SERVICE_ACTION_PATTERNS)
            )
        )
        high_intent = service_intent or problem_intent

        # 또래 경험담 기회: 1인칭 경험 공유 글(다녀왔/받아봤/효과 봤 + 진료축 앵커)은
        # 질문/결정 의도가 없어도 '저도 다녀왔는데...' 댓글이 자연스럽게 붙는 좋은 대상이다.
        # 진료축 앵커(증상어 OR 도메인)와 함께만 인정해 flat prior 가 되지 않게 한다.
        first_person_experience = (
            cls._contains_any(user_text, cls.FIRST_PERSON_EXPERIENCE_PATTERNS)
            and (
                cls._contains_any(user_text, cls.CONDITION_TERMS)
                or (domain != "general" and cls._has_domain_anchor(domain, user_text))
            )
        )

        if recommendation_request:
            score += 32
            signals.append("recommendation_request")
        if ready_to_act:
            score += 20
            signals.append("ready_to_act")
        if cost_decision:
            score += 16
            signals.append("cost_decision")
        if pain_urgency:
            score += 16
            signals.append("pain_or_urgency")
            if not problem_intent:
                signals.append("condition_only")
        if comparison_eval:
            score += 12
            signals.append("comparison_or_evaluation")
        if first_person_experience:
            score += 12
            signals.append("peer_experience_opportunity")
        if is_inquiry:
            score += 10
            signals.append("explicit_question")
        if is_health:
            score += 6
            signals.append("domain_health")
        if cls._contains_region_terms(user_text, cls.REGION_KEYWORDS):
            score += 8
            signals.append("local_fit")
        if cls._has_domain_anchor(domain, user_text):
            score += 8
            signals.append("domain_fit")

        if platform in {"kin", "naver_kin", "cafe", "naver_cafe"}:
            score += 6
            signals.append("reply_surface")
        elif platform == "blog":
            score -= 6
            signals.append("blog_lower_reply_fit")

        if "광고사절" in user_text or "업체 말고" in user_text:
            score += 8
            signals.append("anti_ad_request")

        if len(user_text) < 80:
            if high_intent:
                score -= 6
                signals.append("short_but_actionable")
            else:
                score -= 18
                signals.append("thin_context")
        if has(cls.LOW_ACTIONABILITY_PATTERNS) and not high_intent:
            score -= 14
            signals.append("low_actionability_question")
        if (target.category or "").strip() in cls.GENERIC_CATEGORY_NAMES:
            score -= 8
            signals.append("generic_category")
        if (
            not high_intent
            and not (is_inquiry and cls._has_domain_anchor(domain, user_text))
            and not first_person_experience
        ):
            score -= 12
            signals.append("no_clear_need")

        score = max(0, min(100, score))
        if score >= 75:
            tier = "hot"
        elif score >= 55:
            tier = "warm"
        elif score >= cls.MIN_VIRAL_NEED_SCORE:
            tier = "monitor"
        else:
            tier = "low"
        return score, tier, signals

    @classmethod
    def _assess_reply_opportunity(
        cls,
        target: ViralTarget,
        domain: str,
        is_inquiry: bool,
        is_health: bool,
        viral_need_score: int,
        viral_need_signals: List[str],
    ) -> Tuple[int, str, List[str]]:
        """Score whether a public reply is likely to be useful and welcome."""
        user_text = cls._user_need_text(target).lower()
        platform = (target.platform or "").lower()
        score = 0
        signals: List[str] = []
        need_signal_set = set(viral_need_signals or [])

        def has(patterns: List[str]) -> bool:
            return any(pattern.lower() in user_text for pattern in patterns if pattern)

        decision_signal = bool(
            need_signal_set
            & {"recommendation_request", "ready_to_act", "cost_decision", "comparison_or_evaluation"}
        )
        problem_signal = "pain_or_urgency" in need_signal_set and "condition_only" not in need_signal_set

        help_request = has(cls.HELP_REQUEST_PATTERNS)

        if is_inquiry or has(cls.INTERROGATIVE_PATTERNS):
            score += 12
            signals.append("clear_question_shape")
        if help_request:
            score += 14
            signals.append("help_request_language")
        if decision_signal:
            score += 18
            signals.append("decision_or_service_task")
        if problem_signal:
            score += 12
            signals.append("situational_problem")
        if cls._contains_region_terms(user_text, cls.REGION_KEYWORDS):
            score += 10
            signals.append("local_actionable")
        if domain != "general" and cls._has_domain_anchor(domain, user_text):
            score += 8
            signals.append("service_match")
        if is_health:
            score += 6
            signals.append("health_context")
        if has(cls.PERSONAL_CONTEXT_PATTERNS):
            score += 8
            signals.append("personal_context")
        if "광고사절" in user_text or "업체 말고" in user_text:
            score += 8
            signals.append("anti_ad_request")

        if platform in {"kin", "naver_kin", "cafe", "naver_cafe"}:
            score += 10
            signals.append("public_reply_surface")
            if getattr(target, "comment_count", 0) == 0:
                score += 8
                signals.append("unanswered_or_low_response")
            elif getattr(target, "comment_count", 0) <= 2:
                score += 3
                signals.append("low_response_count")
            elif getattr(target, "comment_count", 0) >= 8:
                score -= 10
                signals.append("crowded_thread")
        elif platform == "blog":
            score -= 12
            signals.append("blog_low_reply_surface")
        elif platform in {"instagram", "tiktok"}:
            score -= 8
            signals.append("feed_low_reply_surface")

        if len(user_text) >= 80:
            score += 6
            signals.append("enough_context")
        elif viral_need_score >= 55:
            score += 4
            signals.append("concise_actionable")
        else:
            score -= 12
            signals.append("too_thin_to_answer")

        if has(cls.BROAD_RESEARCH_PATTERNS) and not decision_signal and not help_request:
            score -= 18
            signals.append("research_only")
        if has(cls.RESOLVED_OR_CLOSED_PATTERNS) and not help_request:
            score -= 35
            signals.append("already_resolved_or_closed")
        if has(cls.LOW_COMMUNITY_FIT_PATTERNS) and not decision_signal and not help_request:
            score -= 14
            signals.append("low_community_fit")
        if (target.category or "").strip() in cls.GENERIC_CATEGORY_NAMES and target.matched_keyword_grade not in {"S", "A"}:
            score -= 6
            signals.append("generic_category")
        if not decision_signal and not problem_signal and not help_request:
            score -= 10
            signals.append("no_direct_ask")

        score = max(0, min(100, score))
        if score >= 75:
            tier = "assist_now"
        elif score >= 55:
            tier = "good"
        elif score >= cls.MIN_REPLY_OPPORTUNITY_SCORE:
            tier = "watch"
        else:
            tier = "low"
        return score, tier, signals

    @staticmethod
    def _parse_datetime(value: Any, now: Optional[datetime] = None) -> Optional[datetime]:
        """Parse common Naver/API/SQLite date strings into a naive local datetime."""
        if not value:
            return None
        now = now or datetime.now()
        raw = str(value).strip()
        if not raw:
            return None

        relative_patterns = [
            (r"(\d+)\s*분\s*전", "minutes"),
            (r"(\d+)\s*시간\s*전", "hours"),
            (r"(\d+)\s*일\s*전", "days"),
            (r"(\d+)\s*주\s*전", "weeks"),
            (r"(\d+)\s*개월\s*전", "months"),
            (r"(\d+)\s*달\s*전", "months"),
            (r"(\d+)\s*년\s*전", "years"),
        ]
        if raw in {"방금", "방금 전", "방금전", "지금"}:
            return now
        relative_day_time = re.fullmatch(
            r"(오늘|어제|그제)(?:\s*작성)?\s+(?:(오전|오후)\s*)?(\d{1,2})\s*:\s*(\d{2})",
            raw,
        )
        if relative_day_time:
            day_word, ampm, hour_text, minute_text = relative_day_time.groups()
            day_delta = {"오늘": 0, "어제": 1, "그제": 2}.get(day_word, 0)
            hour = int(hour_text)
            minute = int(minute_text)
            if ampm == "오후" and hour < 12:
                hour += 12
            if ampm == "오전" and hour == 12:
                hour = 0
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                base = now - timedelta(days=day_delta)
                return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if raw in {"오늘", "오늘 작성"}:
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if raw in {"어제", "어제 작성"}:
            return now - timedelta(days=1)
        if raw in {"그제", "그제 작성"}:
            return now - timedelta(days=2)

        time_only = re.fullmatch(r"(?:(오전|오후)\s*)?(\d{1,2})\s*:\s*(\d{2})", raw)
        if time_only:
            ampm, hour_text, minute_text = time_only.groups()
            hour = int(hour_text)
            minute = int(minute_text)
            if ampm == "오후" and hour < 12:
                hour += 12
            if ampm == "오전" and hour == 12:
                hour = 0
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        for pattern, unit in relative_patterns:
            match = re.search(pattern, raw)
            if not match:
                continue
            amount = int(match.group(1))
            if unit == "minutes":
                return now - timedelta(minutes=amount)
            if unit == "hours":
                return now - timedelta(hours=amount)
            if unit == "days":
                return now - timedelta(days=amount)
            if unit == "weeks":
                return now - timedelta(weeks=amount)
            if unit == "months":
                return now - timedelta(days=amount * 30)
            if unit == "years":
                return now - timedelta(days=amount * 365)

        compact = re.sub(r"\s+", " ", raw.replace("T", " ").replace("Z", "")).strip()
        if re.fullmatch(r"\d{8}", compact):
            try:
                return datetime.strptime(compact, "%Y%m%d")
            except ValueError:
                return None
        naver_date = NAVER_POST_DATE_RE.search(compact)
        if naver_date:
            try:
                year = int(naver_date.group(1))
                month = int(naver_date.group(2))
                day = int(naver_date.group(3))
                date_base = datetime(year, month, day)
            except ValueError:
                return None
            tail = compact[naver_date.end():].strip(" .")
            tail_time = re.match(r"(?:(오전|오후)\s*)?(\d{1,2})\s*:\s*(\d{2})(?::\s*(\d{2}))?", tail)
            if tail_time:
                ampm, hour_text, minute_text, second_text = tail_time.groups()
                hour = int(hour_text)
                minute = int(minute_text)
                second = int(second_text or 0)
                if ampm == "오후" and hour < 12:
                    hour += 12
                if ampm == "오전" and hour == 12:
                    hour = 0
                if 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59:
                    return date_base.replace(hour=hour, minute=minute, second=second)
            return date_base
        compact = compact.rstrip(".")
        for fmt in (
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y.%m.%d %H:%M:%S",
            "%Y.%m.%d %H:%M",
            "%Y.%m.%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
        ):
            try:
                return datetime.strptime(compact, fmt)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(compact)
            return parsed.replace(tzinfo=None)
        except ValueError:
            return None

    @classmethod
    def _hours_since(cls, value: Any, now: Optional[datetime] = None) -> Optional[float]:
        now = now or datetime.now()
        parsed = cls._parse_datetime(value, now)
        if not parsed:
            return None
        return max(0.0, (now - parsed).total_seconds() / 3600.0)

    @classmethod
    def _assess_timing_window(
        cls,
        target: ViralTarget,
        viral_need_signals: List[str],
        reply_opportunity_signals: List[str],
        now: Optional[datetime] = None,
    ) -> Tuple[int, str, List[str]]:
        """Score whether the post is still inside a practical response window."""
        now = now or datetime.now()
        user_text = cls._user_need_text(target).lower()
        platform = (target.platform or "").lower()
        score = 35
        signals: List[str] = []

        posted_source = target.date_str or getattr(target, "posted_at", "") or ""
        posted_hours = cls._hours_since(posted_source, now)
        # 게시물 자체가 post-age TTL(PENDING_POST_AGE_TTL_DAYS=270d)을 넘으면 댓글 적시성이
        # 없다 — 미답변/노출 같은 참여 신호로 되살리지 않고 즉시 하드페일한다. (>30d 페널티가
        # -34로 평탄해, 17년 전 글도 unanswered_gap+qa_window_fit 등으로 MIN(28)을 넘겨
        # pending에 진입하던 갭. 이제 enrichment 단계에서 차단해 post-age TTL의 270d
        # 하드컷과 정합.) posted_hours가 None(날짜 미상)이면 영향 없음 — dwell TTL이 별도 보호.
        if posted_hours is not None and posted_hours > PENDING_POST_AGE_TTL_DAYS * 24:
            return 0, "stale", ["post_age_exceeds_ttl"]
        discovered_hours = cls._hours_since(target.discovered_at or target.first_seen_at, now)
        last_scanned_hours = cls._hours_since(target.last_scanned_at, now)
        comment_count = max(0, int(getattr(target, "comment_count", 0) or 0))
        view_count = max(0, int(getattr(target, "view_count", 0) or 0))
        scan_count = max(0, int(getattr(target, "scan_count", 0) or 0))
        need_signal_set = set(viral_need_signals or [])
        reply_signal_set = set(reply_opportunity_signals or [])

        if posted_hours is None:
            signals.append("no_post_date")
            if discovered_hours is not None and discovered_hours <= 24:
                score += 8
                signals.append("recently_discovered_no_postdate")
            else:
                score -= 6
        elif posted_hours <= 6:
            score += 28
            signals.append("posted_under_6h")
        elif posted_hours <= 24:
            score += 22
            signals.append("posted_under_24h")
        elif posted_hours <= 72:
            score += 14
            signals.append("posted_under_3d")
        elif posted_hours <= 168:
            score += 6
            signals.append("posted_under_7d")
        elif posted_hours <= 336:
            score -= 8
            signals.append("posted_7_14d")
        elif posted_hours <= 720:
            score -= 18
            signals.append("posted_14_30d")
        else:
            score -= 34
            signals.append("posted_over_30d")

        if discovered_hours is not None:
            if discovered_hours <= 12:
                score += 8
                signals.append("freshly_discovered")
            elif discovered_hours <= 72:
                score += 4
                signals.append("recently_discovered")
            elif discovered_hours > 720:
                score -= 8
                signals.append("old_in_queue")

        if last_scanned_hours is not None and last_scanned_hours <= 24:
            score += 3
            signals.append("recently_rescanned")

        if comment_count == 0:
            score += 18
            signals.append("unanswered_gap")
        elif comment_count <= 2:
            score += 9
            signals.append("low_answer_count")
        elif comment_count <= 6:
            score += 1
            signals.append("moderate_answer_count")
        elif comment_count <= 12:
            score -= 10
            signals.append("crowded_answers")
        else:
            score -= 18
            signals.append("saturated_answers")

        if view_count >= 100 and comment_count <= 1:
            score += 8
            signals.append("visible_unanswered")
        elif view_count >= 500 and comment_count >= 8:
            score -= 6
            signals.append("visible_but_saturated")

        if scan_count <= 1:
            score += 5
            signals.append("newly_seen")
        elif scan_count <= 4:
            score += 3
            signals.append("recurring_candidate")
        elif scan_count >= 10:
            score -= 6
            signals.append("over_rescanned")

        if cls._contains_any(user_text, cls.SAME_DAY_ACTION_PATTERNS):
            score += 12
            signals.append("time_sensitive_language")
            if posted_hours is not None and posted_hours > 168:
                score -= 18
                signals.append("expired_time_phrase")
        if cls._contains_any(user_text, cls.STALE_TIME_PATTERNS):
            score -= 16
            signals.append("stale_language")

        if "ready_to_act" in need_signal_set:
            score += 8
            signals.append("ready_to_act_timing")
        if "pain_or_urgency" in need_signal_set and "condition_only" not in need_signal_set:
            score += 5
            signals.append("problem_urgency_timing")
        if "already_resolved_or_closed" in reply_signal_set:
            score -= 18
            signals.append("closed_thread_timing")

        if platform == "blog":
            score -= 8
            signals.append("blog_slower_window")
            if posted_hours is not None and posted_hours > 168:
                score -= 10
                signals.append("old_blog_window")
        elif platform in {"kin", "naver_kin", "cafe", "naver_cafe"}:
            score += 5
            signals.append("qa_window_fit")

        score = max(0, min(100, score))
        if score >= 75:
            tier = "now"
        elif score >= 55:
            tier = "fresh"
        elif score >= cls.MIN_TIMING_WINDOW_SCORE:
            tier = "aging"
        else:
            tier = "stale"
        return score, tier, signals

    @classmethod
    def _assess_journey_fit(
        cls,
        target: ViralTarget,
        domain: str,
        is_inquiry: bool,
        viral_need_signals: List[str],
        reply_opportunity_signals: List[str],
        timing_window_score: int,
    ) -> Tuple[int, str, List[str]]:
        """Classify journey stage and score whether outreach is appropriate now."""
        user_text = cls._user_need_text(target).lower()
        platform = (target.platform or "").lower()
        score = 0
        signals: List[str] = []

        def has(patterns: List[str]) -> bool:
            return any(pattern.lower() in user_text for pattern in patterns if pattern)

        awareness = has(cls.AWARENESS_STAGE_PATTERNS)
        consideration = has(cls.CONSIDERATION_STAGE_PATTERNS)
        decision = has(cls.DECISION_STAGE_PATTERNS)
        post_service = has(cls.POST_SERVICE_STAGE_PATTERNS)
        positive_permission = has(cls.RESPONSE_PERMISSION_POSITIVE_PATTERNS)
        negative_permission = has(cls.RESPONSE_PERMISSION_NEGATIVE_PATTERNS)
        need_signal_set = set(viral_need_signals or [])
        reply_signal_set = set(reply_opportunity_signals or [])

        if decision or ("ready_to_act" in need_signal_set) or ("cost_decision" in need_signal_set):
            score += 38
            signals.append("journey_decision")
        if consideration or ("recommendation_request" in need_signal_set) or ("comparison_or_evaluation" in need_signal_set):
            score += 28
            signals.append("journey_consideration")
        if awareness and not (consideration or decision):
            score -= 22
            signals.append("journey_awareness_only")
        elif awareness:
            score += 4
            signals.append("journey_education_plus_consideration")
        if post_service and not positive_permission:
            score -= 28
            signals.append("journey_post_service_closed")

        if "situational_problem" in reply_signal_set:
            score += 12
            signals.append("problem_context")
        if "local_actionable" in reply_signal_set:
            score += 10
            signals.append("local_service_path")
        if "service_match" in reply_signal_set:
            score += 8
            signals.append("matched_service_path")
        if is_inquiry:
            score += 8
            signals.append("ask_present")
        if positive_permission:
            score += 8
            signals.append("response_permission_positive")
        if negative_permission:
            score -= 12
            signals.append("response_permission_restrictive")
            if positive_permission:
                score += 5
                signals.append("transparent_help_possible")

        if timing_window_score >= 75:
            score += 8
            signals.append("journey_window_now")
        elif timing_window_score < 40:
            score -= 10
            signals.append("journey_window_weak")

        if platform in {"kin", "naver_kin", "cafe", "naver_cafe"}:
            score += 6
            signals.append("journey_reply_surface")
        elif platform == "blog":
            score -= 10
            signals.append("journey_blog_lower_fit")

        if (target.category or "").strip() in cls.GENERIC_CATEGORY_NAMES and domain == "general":
            score -= 8
            signals.append("journey_generic_match")

        if not any(s in signals for s in ("journey_decision", "journey_consideration", "problem_context")):
            score -= 12
            signals.append("journey_no_action_stage")

        score = max(0, min(100, score))
        if "journey_post_service_closed" in signals and score < 55:
            stage = "post_service"
        elif "journey_decision" in signals:
            stage = "decision"
        elif "journey_consideration" in signals:
            stage = "consideration"
        elif "journey_awareness_only" in signals:
            stage = "awareness"
        else:
            stage = "unknown"
        return score, stage, signals

    @classmethod
    def _assess_qualification_fit(
        cls,
        target: ViralTarget,
        domain: str,
        is_health: bool,
        viral_need_signals: List[str],
        reply_opportunity_signals: List[str],
        timing_window_score: int,
        journey_fit_score: int,
        journey_stage: str,
    ) -> Tuple[int, str, List[str]]:
        """Score whether the mention is a qualified, actionable lead."""
        user_text = cls._user_need_text(target).lower()
        platform = (target.platform or "").lower()
        score = 0
        signals: List[str] = []
        need_signal_set = set(viral_need_signals or [])
        reply_signal_set = set(reply_opportunity_signals or [])

        def has(patterns: List[str]) -> bool:
            return any(pattern.lower() in user_text for pattern in patterns if pattern)

        local_fit = cls._contains_region_terms(user_text, cls.REGION_KEYWORDS)
        service_line_context = cls._contains_any(user_text, cls.QUALIFIED_SERVICE_LINE_PATTERNS)
        service_fit = (domain != "general" and cls._has_domain_anchor(domain, user_text)) or service_line_context
        actor_context = has(cls.DECISION_ACTOR_PATTERNS) or bool(
            re.search(r"(10대|20대|30대|40대|50대|60대|남성|여성|남 |여 |/남|/여)", user_text)
        )
        challenge_signal = (
            "situational_problem" in reply_signal_set
            or ("pain_or_urgency" in need_signal_set and "condition_only" not in need_signal_set)
            or has(cls.SWITCHING_TRIGGER_PATTERNS)
        )
        intent_signal = bool(
            need_signal_set
            & {"recommendation_request", "ready_to_act", "cost_decision", "comparison_or_evaluation"}
        )
        budget_signal = has(cls.COST_DECISION_PATTERNS) or has(["실비", "보험", "자보", "자동차보험", "비용", "가격"])
        timing_signal = timing_window_score >= 55 or has(cls.SAME_DAY_ACTION_PATTERNS)
        constraint_signal = has(cls.QUALIFICATION_CONSTRAINT_PATTERNS)
        progress_signal = has(cls.JTBD_PROGRESS_PATTERNS)
        switching_signal = has(cls.SWITCHING_TRIGGER_PATTERNS)
        low_quality_signal = has(cls.LOW_QUALIFICATION_PATTERNS)
        non_service_beauty = has(cls.NON_SERVICE_BEAUTY_PATTERNS)

        if local_fit:
            score += 14
            signals.append("qualified_local_fit")
        if service_fit:
            score += 14
            signals.append("qualified_service_fit")
        if actor_context:
            score += 10
            signals.append("decision_actor_context")
        elif local_fit and service_line_context and intent_signal:
            score += 4
            signals.append("community_decision_proxy")
        else:
            score -= 8
            signals.append("no_actor_context")
        if challenge_signal:
            score += 16
            signals.append("clear_challenge")
        if intent_signal:
            score += 14
            signals.append("qualified_intent")
        if budget_signal:
            score += 10
            signals.append("budget_or_coverage_signal")
        if timing_signal:
            score += 8
            signals.append("qualified_timing")
        if constraint_signal:
            score += 8
            signals.append("constraint_signal")
        if progress_signal:
            score += 8
            signals.append("jtbd_progress")
        if switching_signal:
            score += 8
            signals.append("switching_trigger")
        if is_health:
            score += 4
            signals.append("health_service_context")
        if platform in {"kin", "naver_kin", "cafe", "naver_cafe"}:
            score += 4
            signals.append("reachable_surface")
        elif platform == "blog":
            score -= 8
            signals.append("qualification_blog_lower_fit")

        if journey_stage == "decision":
            score += 10
            signals.append("journey_decision_qualified")
        elif journey_stage == "consideration":
            score += 5
            signals.append("journey_consideration_qualified")
        elif journey_stage in {"awareness", "post_service"}:
            score -= 16
            signals.append("journey_low_qualification")

        if journey_fit_score < 45:
            score -= 8
            signals.append("weak_journey_fit")
        if timing_window_score < 40:
            score -= 8
            signals.append("weak_timing_fit")
        if low_quality_signal:
            score -= 20
            signals.append("research_or_school_task")
            if not (challenge_signal or budget_signal or progress_signal):
                score -= 40
                signals.append("hard_unqualified_context")
        if non_service_beauty:
            score -= 24
            signals.append("non_service_beauty")
        if not local_fit and not service_fit:
            score -= 12
            signals.append("missing_fit_core")
        if not challenge_signal and not intent_signal and not progress_signal:
            score -= 14
            signals.append("missing_need_or_job")
        if not any(s in signals for s in ("budget_or_coverage_signal", "constraint_signal", "qualified_timing", "decision_actor_context")):
            score -= 6
            signals.append("thin_qualification_context")

        score = max(0, min(100, score))
        if score >= 75:
            tier = "qualified_hot"
        elif score >= 55:
            tier = "qualified"
        elif score >= cls.MIN_QUALIFICATION_FIT_SCORE:
            tier = "light"
        else:
            tier = "unqualified"
        return score, tier, signals

    @classmethod
    def _provider_cta_body_signal(cls, target: ViralTarget, text: str) -> Tuple[bool, List[str]]:
        """Detect provider-authored blog/cafe bodies that wear question/review titles."""
        platform = (target.platform or "").lower()
        if platform not in {"blog", "cafe", "naver_cafe"}:
            return False, []

        body = cls._strip_internal_labels(target.content_preview or "").lower()
        signal_text = body or text
        if not signal_text:
            return False, []

        def hits(patterns: List[str]) -> List[str]:
            return [pattern for pattern in patterns if pattern and pattern.lower() in signal_text]

        provider_info = hits(cls.PROVIDER_INFO_POST_PATTERNS)
        provider_author = hits(cls.PROVIDER_BODY_AUTHOR_PATTERNS)
        cta = hits(cls.COMMERCIAL_CTA_PATTERNS)
        medical_promo = hits(cls.PROMOTIONAL_MEDICAL_PATTERNS)
        blog_structural = hits(cls.BLOG_AD_STRUCTURAL_PATTERNS)

        groups = {
            "provider_info": provider_info,
            "provider_author": provider_author,
            "commercial_cta": cta,
            "medical_promo": medical_promo,
            "blog_ad_structure": blog_structural,
        }
        present_groups = [name for name, values in groups.items() if values]
        has_provider_voice = bool(provider_info or provider_author or (medical_promo and blog_structural))
        has_action_or_footer = bool(cta or blog_structural)
        if not (has_provider_voice and has_action_or_footer and len(present_groups) >= 2):
            return False, []

        user_text = cls._user_need_text(target).lower()
        real_user_ask = cls._contains_any(user_text, cls.PROVIDER_BODY_REAL_USER_ASK_PATTERNS)
        if real_user_ask and not provider_author:
            return False, []

        return True, present_groups

    @classmethod
    def _provider_venue_author_signal(cls, target: ViralTarget) -> Tuple[bool, str]:
        """카페명/블로거 정체성이 공급자(경쟁 의료기관·병원 디렉터리)면 광고 신호로 본다.

        지식인은 author=질문자 닉네임이라 제외(환자가 어떤 닉네임이든 가능). 카페/블로그만
        author 가 '글이 올라온 곳의 정체성'이므로 적용한다. 커뮤니티 가드를 먼저 검사해
        환우모임·맘카페·동네 정보 커뮤니티 같은 진짜 환자 공간은 보존한다.
        """
        platform = (target.platform or "").lower()
        if platform not in {"blog", "cafe", "naver_cafe"}:
            return False, ""
        author = (getattr(target, "author", "") or "").lower()
        if not author:
            return False, ""
        if any(guard.lower() in author for guard in cls.PROVIDER_VENUE_AUTHOR_COMMUNITY_GUARD):
            return False, ""
        for token in cls.PROVIDER_VENUE_AUTHOR_PATTERNS:
            if token and token.lower() in author:
                return True, token
        return False, ""

    @classmethod
    def _detect_advertorial(cls, target: ViralTarget, text: str) -> Tuple[bool, List[str], int]:
        """Detect provider/SEO/brand ads that imitate question or review posts."""
        platform = (target.platform or "").lower()
        signals: List[str] = []
        score = 0
        domain = cls._target_domain(target)

        def matched(patterns: List[str]) -> List[str]:
            return [pattern for pattern in patterns if pattern and pattern.lower() in text]

        clean_body = cls._strip_internal_labels(target.content_preview or "").lower()
        title_text = (target.title or "").lower()
        strong_inquiry = matched(cls.STRONG_USER_INQUIRY_PATTERNS)

        kin_provider = matched(cls.KIN_PROVIDER_ANSWER_PATTERNS)
        if platform == "kin" and kin_provider:
            signals.append("kin_provider_answer")
            score += 6

        kin_answer_ad = matched(cls.KIN_ANSWER_AD_PATTERNS)
        if platform == "kin" and kin_answer_ad:
            signals.append("kin_answer_ad_copy")
            score += 3 + min(5, len(kin_answer_ad))

        kin_answer_transition = False
        if platform == "kin":
            hello_at = clean_body.find("안녕하세요")
            if hello_at > 20:
                signals.append("kin_answer_transition")
                kin_answer_transition = True
                score += 4

        kin_recommendation_spam = matched(cls.KIN_RECOMMENDATION_SPAM_PATTERNS)
        if platform == "kin" and kin_recommendation_spam:
            signals.append("kin_recommendation_spam")
            score += 3 + min(3, len(kin_recommendation_spam))

        answer_snippet_ads = [
            pattern for pattern in cls.ANSWER_SNIPPET_AD_REGEXES
            if re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        ]
        if answer_snippet_ads:
            signals.append("answer_snippet_ad")
            score += 4 + min(5, len(answer_snippet_ads) * 2)

        if platform in {"blog", "cafe", "naver_cafe"}:
            provider_bracket_title = bool(
                re.search(r"[\[\(【][^\]\)】]{0,30}(?:병원|한방병원|한의원|의원|피부과|클리닉)[^\]\)】]{0,30}[\]\)】]", title_text)
            )
            if provider_bracket_title:
                signals.append("provider_bracket_title")
                score += 2 if strong_inquiry else 5

            local_provider_domain_title = (
                cls._contains_region_terms(title_text, cls.REGION_KEYWORDS)
                and cls._contains_any(title_text, cls.MEDICAL_PROVIDER_TERMS)
                and cls._has_domain_anchor(domain, text)
            )
            local_provider_promo_title = (
                local_provider_domain_title
                and cls._contains_any(title_text, cls.MEDICAL_PROMO_TITLE_PATTERNS)
            )
            if local_provider_promo_title:
                signals.append("local_provider_promo_title")
                score += 2 if strong_inquiry else 5

            blog_medical_seo_title = (
                platform == "blog"
                and local_provider_domain_title
                and cls._contains_any(title_text, cls.BLOG_MEDICAL_SEO_TITLE_PATTERNS)
                and not strong_inquiry
            )
            if blog_medical_seo_title:
                signals.append("blog_medical_seo_title")
                score += 5

            title_question_like = bool(re.search(r"[?？]", title_text)) or cls._contains_any(
                title_text,
                cls.RECOMMENDATION_REQUEST_PATTERNS,
            )
            local_provider_service_title = (
                platform in {"blog", "cafe", "naver_cafe"}
                and local_provider_domain_title
                and not strong_inquiry
                and not title_question_like
            )
            if local_provider_service_title:
                signals.append(
                    "blog_local_provider_service_title"
                    if platform == "blog"
                    else "local_provider_service_title"
                )
                score += 4 if platform == "blog" else 5

        legal = matched(cls.LEGAL_PROMO_PATTERNS)
        if legal:
            signals.append("legal_promo")
            score += 6

        brand = matched(cls.BRAND_PROMO_PATTERNS)
        if brand:
            signals.append("brand_promo")
            score += 4

        cta = matched(cls.COMMERCIAL_CTA_PATTERNS)
        if cta:
            signals.append("commercial_cta")
            score += 2 + min(3, len(cta))

        medical_promo = matched(cls.PROMOTIONAL_MEDICAL_PATTERNS)
        if medical_promo:
            signals.append("medical_promo_copy")
            score += 2 + min(2, len(medical_promo))

        blog_structural = matched(cls.BLOG_AD_STRUCTURAL_PATTERNS)
        if blog_structural:
            signals.append("blog_ad_structure")
            score += 2 + min(3, len(blog_structural))

        provider_cta_body, provider_cta_groups = cls._provider_cta_body_signal(target, text)
        if provider_cta_body:
            signals.append("provider_cta_body")
            score += 5
            if provider_cta_groups:
                signals.extend(f"provider_cta_body_{group}" for group in provider_cta_groups)

        # 카페명/블로거 정체성이 공급자면 본문 CTA가 미리보기 밖에 있어도 광고로 본다.
        # 클리닉 브랜드 카페는 질문을 흉내 낸 SEO 글이어도 환자 글이 아니므로 strong_inquiry
        # 감점(-2)을 넘어 무조건 임계값을 넘기도록 강한 점수(+7)를 준다.
        provider_venue_author, provider_venue_token = cls._provider_venue_author_signal(target)
        if provider_venue_author:
            signals.append("provider_venue_author")
            signals.append(f"provider_venue_author_{provider_venue_token}")
            score += 7

        diet_provider_context = domain == "diet" and cls._contains_any(
            text,
            ["한의원", "한약", "다이어트한약", "비움탕", "감비환", "비만클리닉"],
        )
        diet_testimonial_marker = cls._contains_any(
            text,
            ["내돈내산", "성공후기", "성공 후기", "다이어트후기", "다이어트 후기", "감량 후기"],
        ) or bool(re.search(r"\d+\s*(?:kg|키로|킬로).{0,20}(?:성공|후기|감량|빠졌)", text))
        if diet_provider_context and diet_testimonial_marker and not strong_inquiry:
            # 1인칭 환자 본인 후기('제가/저는 ... 받았어요')이면서 광고 보강신호(공급자
            # 브랜드 카페·본문 CTA)가 없으면 광고가 아니라 또래 경험 공유 글일 확률이 높다 —
            # 규림이 댓글을 달 대상이므로 광고 가산을 보류한다. 진짜 어드버토리얼은
            # provider_venue_author(+7)/provider_cta_body(+5)가 이미 임계값을 넘긴다.
            genuine_first_person = (
                cls._contains_any(text, ["제가", "저는", "저도", "제 경험", "직접"])
                and not provider_venue_author
                and not provider_cta_body
            )
            if not genuine_first_person:
                signals.append("diet_testimonial_promo")
                score += 5

        medical_price_event_context = cls._contains_any(
            text,
            [
                "치료", "시술", "한의원", "병원", "의원", "피부과", "클리닉",
                "여드름", "흉터", "사마귀", "다이어트", "한약", "리프팅",
            ],
        )
        medical_price_event_marker = cls._contains_any(
            text,
            ["무제한", "성지", "할인이벤트", "할인 이벤트", "이벤트", "최저가"],
        ) or bool(re.search(r"\d+\s*만원.{0,20}(?:이벤트|혜택|할인|무제한)", text))
        if medical_price_event_context and medical_price_event_marker and not strong_inquiry:
            signals.append("medical_price_event_promo")
            score += 5

        local_footer_hits = matched(cls.LOCAL_SEO_FOOTER_PATTERNS)
        local_area_hits = [hit for hit in local_footer_hits if hit in cls.REGION_KEYWORDS]
        local_phrase_hits = [hit for hit in local_footer_hits if hit not in cls.REGION_KEYWORDS]
        if local_phrase_hits or len(set(local_area_hits)) >= 4:
            signals.append("local_seo_footer")
            score += 4

        kin_answer_like = platform == "kin" and (
            bool(kin_provider)
            or bool(kin_answer_ad)
            or bool(kin_recommendation_spam)
            or bool(answer_snippet_ads)
            or kin_answer_transition
        )
        if strong_inquiry and not kin_answer_like:
            score -= 2
        if platform == "kin" and ("광고사절" in text or "업체 말고" in text) and not kin_answer_like:
            score -= 2

        if platform == "blog" and not strong_inquiry:
            score += 1
        if platform == "cafe" and (legal or brand):
            score += 2

        threshold = 5
        if platform == "blog":
            threshold = 4
        if platform == "kin" and kin_provider:
            threshold = 4
        if platform == "kin" and (kin_answer_ad or kin_recommendation_spam or kin_answer_transition):
            threshold = 4
        if legal:
            threshold = 4

        return score >= threshold, signals, score

    @classmethod
    def _has_domain_anchor(cls, domain: str, text: str) -> bool:
        """'교정'처럼 넓은 단어만으로 통과하지 않도록 핵심 맥락을 요구한다."""
        if domain == "general":
            return True
        if domain in cls.STRICT_DOMAIN_ANCHORS:
            return cls._contains_any(text, cls.STRICT_DOMAIN_ANCHORS[domain])
        return cls._contains_any(text, cls.DOMAIN_ANCHORS.get(domain, []))

    SCAR_PATIENT_EXPLORATION_PATTERNS = [
        "고민", "할지", "싶어서", "싶은데", "싶어요", "추천", "후기", "어떡", "어쩌",
        "방법", "알려주", "찾고", "찾아보", "스트레스", "자신감",
    ]

    @classmethod
    def _is_scar_patient_exploration(cls, text: str, title: str = "") -> bool:
        """흉터 환자의 탐색 질문 구제 — 시술 단어가 본문 비교 맥락으로만 등장하는 경우.

        흉터 환자가 한방 용어를 자발적으로 쓰는 일은 드물다. '레이저 종류도 많고'
        같은 탐색 언급까지 모두 잘라내면 새살침 대안을 소개할 핵심 공급이 사라진다
        (라이브 리뷰: 흉터 축 전 기간 91건, 68% filtered_out — 이 규칙이 1순위
        축 기근의 구조 원인이었다). 제목 자체가 시술/피부과 주제인 글(프락셀 후기
        요청 등)은 구제하지 않는다. 광고/지역/한방거부/AI 게이트는 이후 단계에서
        계속 돈다.
        """
        if not cls._contains_any(text, cls.SCAR_USER_AXIS_ANCHOR_PATTERNS):
            return False
        if title and cls._contains_any(title, cls.OFF_DOMAIN_PATTERNS["cosmetic_clinic"]):
            return False
        return cls._contains_any(text, cls.INTERROGATIVE_PATTERNS) or cls._contains_any(
            text, cls.SCAR_PATIENT_EXPLORATION_PATTERNS
        )

    @classmethod
    def _is_off_domain(cls, domain: str, text: str, title: str = "") -> bool:
        """핵심 키워드와 무관한 업종/시술 글을 저장 전 제외한다."""
        if cls._contains_any(text, cls.OFF_DOMAIN_PATTERNS["dental"]):
            return domain in {"asymmetry", "body", "general"}
        if cls._contains_any(text, cls.OFF_DOMAIN_PATTERNS["golf"]):
            return domain in {"body", "general"}
        if cls._contains_any(text, cls.OFF_DOMAIN_PATTERNS["cosmetic_clinic"]):
            if getattr(GYULIM_KEYWORD_PROFILE, "cosmetic_clinic_terms_on_scope", False):
                recover_skin_context = cls._contains_any(
                    text,
                    [
                        "흉터", "여드름", "피부", "모공", "색소", "리프팅", "탄력",
                        "주름", "스킨부스터", "리쥬란", "쥬베룩", "레이저", "클리닉", "의원",
                    ],
                )
                return domain not in {"scar_skin", "lifting", "general"} and not recover_skin_context
            if domain in {"asymmetry", "body", "traffic", "diet"}:
                return True
            hanbang_skin_context = cls._contains_any(text, ["새살침", "한의원", "한방", "침치료"])
            if domain not in {"scar_skin", "lifting", "general"} or hanbang_skin_context:
                return False
            if domain == "scar_skin" and cls._is_scar_patient_exploration(text, title):
                return False
            return True
        if cls._contains_any(text, cls.OFF_DOMAIN_PATTERNS["fitness"]):
            medical_diet_context = cls._contains_any(
                text, ["한약", "한의원", "한방", "처방", "마운자로", "위고비", "삭센다", "비만"]
            )
            if domain == "diet":
                return not medical_diet_context
            return domain in {"body", "general"}
        if cls._contains_any(text, cls.OFF_DOMAIN_PATTERNS["surgery"]):
            if getattr(GYULIM_KEYWORD_PROFILE, "cosmetic_clinic_terms_on_scope", False):
                post_surgery_scar_context = cls._contains_any(
                    text,
                    ["수술흉터", "수술 흉터", "흉터", "켈로이드", "절개흉터", "상처자국"],
                )
                if post_surgery_scar_context and domain in {"scar_skin", "general"}:
                    return False
            return True
        if cls._contains_any(text, cls.OFF_DOMAIN_PATTERNS["urology"]):
            return True
        return False

    @classmethod
    def _is_non_service_beauty_target(cls, domain: str, text: str) -> bool:
        """Exclude home-care or salon beauty posts that are not clinic-service leads."""
        if domain not in {"scar_skin", "asymmetry", "body", "lifting", "general"}:
            return False
        if not cls._contains_any(text, cls.NON_SERVICE_BEAUTY_PATTERNS):
            return False

        service_rescue = cls._contains_any(
            text,
            [
                "한의원", "한방", "한약", "새살침", "침치료", "추나", "치료",
                "상담", "병원", "의원", "클리닉",
            ],
        )
        product_or_salon_context = cls._contains_any(
            text,
            [
                "제품", "홈케어", "마스크팩", "led", "피부관리실", "피부관리샵",
                "피부샵", "에스테틱", "관리실", "미용실", "헤어샵", "네일",
            ],
        )
        return bool(product_or_salon_context or not service_rescue)

    @classmethod
    def _is_asymmetry_axis_noise(cls, target: ViralTarget, text: str) -> bool:
        """Reject face/asymmetry seeds that actually point to beauty, brow, dental, or esthetic services."""
        domain = cls._target_domain(target)
        category = GYULIM_KEYWORD_PROFILE.normalize_category(
            getattr(target, "matched_keyword_category", "") or getattr(target, "category", "")
        )
        if domain != "asymmetry" and category != "안면비대칭":
            return False

        text_lc = (text or "").lower()
        compact = re.sub(r"\s+", "", text_lc)

        def has_any(terms: Iterable[str]) -> bool:
            for term in terms:
                clean = str(term or "").strip().lower()
                if not clean:
                    continue
                if clean in text_lc:
                    return True
                compact_term = re.sub(r"\s+", "", clean)
                if compact_term and compact_term in compact:
                    return True
            return False

        if has_any(cls.ASYMMETRY_HARD_OFF_AXIS_PATTERNS):
            return True

        strong_axis = has_any(cls.ASYMMETRY_STRONG_AXIS_PATTERNS)
        clinic_action = has_any(cls.ASYMMETRY_CLINIC_ACTION_PATTERNS)

        if has_any(cls.ASYMMETRY_DENTAL_OR_ORTHO_NOISE_PATTERNS) and not strong_axis:
            return True
        if has_any(cls.ASYMMETRY_BEAUTY_MANAGEMENT_PATTERNS) and not (strong_axis and clinic_action):
            return True

        ambiguous_face_shape = has_any(["얼굴형", "윤곽", "페이스라인", "얼굴라인"])
        if ambiguous_face_shape and not strong_axis and not clinic_action:
            return True

        if cls._is_axis_companion_variant(target, "axis_asymmetry:") and not cls._has_user_axis_anchor(
            target,
            domain=domain,
            category=category,
        ):
            return True

        return False

    @classmethod
    def _is_body_axis_noise(cls, target: ViralTarget, text: str) -> bool:
        """Reject broad body/Chuna companion hits whose user question is really another condition."""
        domain = cls._target_domain(target)
        category = GYULIM_KEYWORD_PROFILE.normalize_category(
            getattr(target, "matched_keyword_category", "") or getattr(target, "category", "")
        )
        if domain != "body" and category != "체형교정":
            return False

        user_text = cls._axis_user_segment_text(target)
        title_text = (target.title or "").lower()
        title_has_body_anchor = cls._contains_any(title_text, cls.BODY_USER_AXIS_ANCHOR_PATTERNS)
        user_has_body_anchor = cls._contains_any(user_text, cls.BODY_USER_AXIS_ANCHOR_PATTERNS)
        has_fitness_provider_noise = cls._contains_any(text, cls.BODY_FITNESS_PROVIDER_NOISE_PATTERNS)
        has_medical_rescue = cls._contains_any(text, cls.BODY_MEDICAL_RESCUE_PATTERNS)

        if has_fitness_provider_noise and not has_medical_rescue:
            return True

        if cls._contains_any(title_text, cls.BODY_COMPANION_OFF_AXIS_PATTERNS) and not title_has_body_anchor:
            return True
        if cls._contains_any(user_text, cls.BODY_COMPANION_OFF_AXIS_PATTERNS) and not title_has_body_anchor:
            return True
        if cls._is_axis_companion_variant(target, "axis_body:") and not user_has_body_anchor:
            return True
        return False

    @classmethod
    def _is_diet_axis_noise(cls, target: ViralTarget, text: str) -> bool:
        """Reject broad diet seeds that are actually gyms, sports classes, or exercise venue questions."""
        domain = cls._target_domain(target)
        category = GYULIM_KEYWORD_PROFILE.normalize_category(
            getattr(target, "matched_keyword_category", "") or getattr(target, "category", "")
        )
        if domain != "diet" and category != "다이어트":
            return False

        has_non_hanbang_medical_noise = cls._contains_any(text, cls.DIET_NON_HANBANG_MEDICAL_NOISE_PATTERNS)
        if has_non_hanbang_medical_noise and not cls._contains_any(text, cls.DIET_HANBANG_INTENT_PATTERNS):
            return True

        has_activity_noise = cls._contains_any(text, cls.DIET_ACTIVITY_NOISE_PATTERNS)
        if not has_activity_noise:
            return False
        has_medical_intent = cls._contains_any(text, cls.DIET_MEDICAL_INTENT_PATTERNS)
        return not has_medical_intent

    @classmethod
    def _is_skin_axis_noise(cls, target: ViralTarget, text: str) -> bool:
        """Reject skin/acne seeds where the skin term is incidental or salon-only."""
        domain = cls._target_domain(target)
        category = GYULIM_KEYWORD_PROFILE.normalize_category(
            getattr(target, "matched_keyword_category", "") or getattr(target, "category", "")
        )
        if domain != "scar_skin" and category not in {"흉터/여드름흉터", "피부/여드름"}:
            return False

        user_has_axis_anchor = cls._has_user_axis_anchor(target, domain=domain, category=category)
        if category == "흉터/여드름흉터" and not user_has_axis_anchor:
            return True
        if cls._is_axis_companion_variant(target, "axis_skin:") and not user_has_axis_anchor:
            return True

        if cls._contains_any(text, cls.SKIN_WESTERN_RX_NOISE_PATTERNS):
            return not cls._contains_any(text, cls.SKIN_HANBANG_SERVICE_RESCUE_PATTERNS)

        if cls._contains_any(text, cls.LEGAL_OR_SCHOOL_VIOLENCE_PATTERNS):
            has_clinic_rescue = cls._contains_any(text, cls.SKIN_CLINIC_RESCUE_PATTERNS)
            return not has_clinic_rescue

        if cls._contains_any(text, cls.SKIN_HARD_SALON_PATTERNS):
            return True

        has_salon_noise = cls._contains_any(text, cls.SKIN_SALON_OR_INCIDENTAL_NOISE_PATTERNS)
        if not has_salon_noise:
            return False
        has_clinic_rescue = cls._contains_any(text, cls.SKIN_CLINIC_RESCUE_PATTERNS)
        return not has_clinic_rescue

    @classmethod
    def _is_lifting_axis_noise(cls, target: ViralTarget, text: str) -> bool:
        """Reject lifting companion hits unless the user text is actually about lifting/elasticity."""
        domain = cls._target_domain(target)
        category = GYULIM_KEYWORD_PROFILE.normalize_category(
            getattr(target, "matched_keyword_category", "") or getattr(target, "category", "")
        )
        if domain != "lifting" and category != "리프팅/탄력":
            return False
        if cls._contains_any(text, cls.LIFTING_INCIDENTAL_COMMERCE_NOISE_PATTERNS) and not cls._contains_any(
            text,
            cls.LIFTING_HANBANG_SERVICE_RESCUE_PATTERNS,
        ):
            return True
        if cls._contains_any(text, cls.LIFTING_NON_HANBANG_DEVICE_PATTERNS) and not cls._contains_any(
            text,
            cls.LIFTING_HANBANG_SERVICE_RESCUE_PATTERNS,
        ):
            return True
        return not cls._has_user_axis_anchor(target, domain=domain, category=category)

    @classmethod
    def _is_explicit_hanbang_exclusion(cls, target: ViralTarget, text: str) -> bool:
        """Reject targets where the asker explicitly excludes Korean-medicine care."""
        domain = cls._target_domain(target)
        category = GYULIM_KEYWORD_PROFILE.normalize_category(
            getattr(target, "matched_keyword_category", "") or getattr(target, "category", "")
        )
        if domain not in {"diet", "scar_skin", "asymmetry", "body", "lifting", "traffic"} and category not in {
            "다이어트", "흉터/여드름흉터", "피부/여드름", "안면비대칭", "체형교정", "리프팅/탄력", "교통사고",
        }:
            return False

        user_text = cls._user_need_text(target).lower()
        check_text = user_text or text
        return cls._contains_any(check_text, cls.EXPLICIT_HANBANG_EXCLUSION_PATTERNS)

    @classmethod
    def _is_kin_answer_footer_region_noise(cls, target: ViralTarget, text: str) -> bool:
        """Reject Kin hits where Cheongju appears only in a provider's multi-branch footer."""
        if (target.platform or "").lower() not in {"kin", "naver_kin"}:
            return False

        user_opening = cls._axis_user_segment_text(target, max_body_chars=70)
        if cls._contains_region_terms(user_opening, cls.REGION_KEYWORDS):
            return False

        footer_region_hits = sum(1 for region in cls.MULTI_REGION_ANSWER_FOOTER_REGIONS if region in text)
        footer_shape = footer_region_hits >= 6 or cls._contains_any(text, cls.KIN_PROVIDER_FOOTER_PATTERNS)
        return bool(footer_shape and cls._contains_region_terms(text, cls.REGION_KEYWORDS))

    @classmethod
    def _is_provider_info_without_user_ask(cls, target: ViralTarget, text: str) -> bool:
        """Reject provider-authored info/price posts that are not natural public reply targets."""
        platform = (target.platform or "").lower()
        if platform not in {"blog", "cafe", "naver_cafe"}:
            return False

        title = (target.title or "").lower()
        user_text = cls._user_need_text(target).lower()
        has_provider_cta_body, _ = cls._provider_cta_body_signal(target, text)
        if has_provider_cta_body:
            return True

        has_provider_info = cls._contains_any(text, cls.PROVIDER_INFO_POST_PATTERNS)
        has_info_title = cls._contains_any(title, cls.PROVIDER_INFO_TITLE_PATTERNS)
        if not (has_provider_info or has_info_title):
            return False

        direct_ask = cls._contains_any(
            user_text,
            cls.RECOMMENDATION_REQUEST_PATTERNS
            + cls.HELP_REQUEST_PATTERNS
            + cls.READY_TO_ACT_PATTERNS
            + cls.COST_DECISION_PATTERNS
            + cls.INTERROGATIVE_PATTERNS,
        )
        testimonial_context = cls._contains_any(user_text, ["내돈내산", "후기", "경험", "해보신", "가보신"])
        if direct_ask and testimonial_context and not has_info_title:
            return False
        return True

    @classmethod
    def _is_traffic_axis_noise(cls, target: ViralTarget, text: str) -> bool:
        """Reject accident seeds that are about vehicle repair, property damage, or legal settlement."""
        domain = cls._target_domain(target)
        category = GYULIM_KEYWORD_PROFILE.normalize_category(
            getattr(target, "matched_keyword_category", "") or getattr(target, "category", "")
        )
        if domain != "traffic" and category != "교통사고":
            return False

        title_text = (target.title or "").lower()
        user_text = cls._axis_user_segment_text(target)
        if cls._contains_any(f"{title_text} {user_text}", cls.TRAFFIC_ANIMAL_OR_VET_NOISE_PATTERNS):
            return True
        if cls._contains_any(title_text, cls.TRAFFIC_TITLE_HARD_NOISE_PATTERNS) and not cls._contains_any(
            user_text,
            cls.TRAFFIC_ACTIVE_CARE_INTENT_PATTERNS,
        ):
            return True

        has_repair_noise = cls._contains_any(user_text, cls.TRAFFIC_REPAIR_OR_PROPERTY_NOISE_PATTERNS)
        has_legal_noise = cls._contains_any(user_text, cls.TRAFFIC_LEGAL_COMPENSATION_NOISE_PATTERNS)
        has_medical_context = cls._contains_any(user_text, cls.TRAFFIC_MEDICAL_CARE_RESCUE_PATTERNS)
        has_active_care_intent = cls._contains_any(user_text, cls.TRAFFIC_ACTIVE_CARE_INTENT_PATTERNS)

        if has_repair_noise and not has_medical_context:
            return True
        if has_legal_noise and not has_active_care_intent:
            return True
        return False

    @classmethod
    def _semantic_axis_rescue(cls, target: ViralTarget, *, text: str, category: str, domain: str) -> bool:
        """어휘로는 진료축 mismatch 인 글을 의미 유사도(BGE-M3)로 구제할지 판정.

        구어/패러프레이즈 환자글('얼굴 짝짝이'=안면비대칭, '팬자국/구덩이'=흉터)을 회수한다.
        매처가 비활성(모델 부재/opt-in off)이면 즉시 False → 완전 no-op (어휘 동작 그대로).
        진료축 어휘 불일치만 덮으며 region/광고/self/noise 게이트는 호출부에서 그대로 적용.
        """
        matcher = _SEMANTIC_AXIS_MATCHER
        if matcher is None or not matcher.available():
            return False
        axis = (category or "").strip()
        if not axis:
            return False
        profile = GYULIM_KEYWORD_PROFILE.profile_for(axis)
        if not profile:
            return False
        ref_terms = tuple(
            dict.fromkeys(
                tuple(getattr(profile, "core_tokens", ()) or ())
                + tuple(getattr(profile, "category_terms", ()) or ())
            )
        )[:12]
        if not ref_terms:
            return False
        user_text = (text or cls._user_need_text(target) or "").strip()
        if not user_text:
            return False
        sim = matcher.similarity(user_text, ref_terms, ref_key=f"axis::{axis}")
        if sim is None:
            return False
        rescued = bool(sim >= matcher.threshold)
        target.score_breakdown = {
            **(target.score_breakdown or {}),
            "semantic_axis_score": round(float(sim), 4),
            "semantic_axis_rescue": rescued,
        }
        return rescued

    @classmethod
    def _pathfinder_fit_reject_reason(
        cls,
        target: ViralTarget,
        *,
        domain: str,
        text: str,
        axis_fit_score: Optional[float] = None,
        axis_fit_tier: str = "",
        lens_fit_score: Optional[float] = None,
        lens_fit_tier: str = "",
    ) -> Optional[str]:
        """Final Pathfinder axis/lens fit gate for lanes that historically over-collect noise."""
        if cls._is_asymmetry_axis_noise(target, text):
            return "off_domain"
        if cls._is_body_axis_noise(target, text):
            return "off_domain"
        if cls._is_diet_axis_noise(target, text):
            return "off_domain"
        if cls._is_skin_axis_noise(target, text):
            return "off_domain"
        if cls._is_lifting_axis_noise(target, text):
            return "off_domain"
        if cls._is_traffic_axis_noise(target, text):
            return "off_domain"

        ctx = cls._pathfinder_execution_context(target)
        lens = str(ctx.get("execution_lens") or "").strip().lower()
        category = GYULIM_KEYWORD_PROFILE.normalize_category(
            getattr(target, "matched_keyword_category", "") or getattr(target, "category", "")
        )
        axis_score = float(axis_fit_score if axis_fit_score is not None else 0.0)
        lens_score = float(lens_fit_score if lens_fit_score is not None else 0.0)
        axis_tier = str(axis_fit_tier or "")
        lens_tier = str(lens_fit_tier or "")
        text_lc = (text or "").lower()
        compact_text = re.sub(r"\s+", "", text_lc)
        source_text_lc = cls._pathfinder_source_fit_text(target, text_lc)
        source_compact_text = re.sub(r"\s+", "", source_text_lc)

        conversion_lens = lens in {"cost", "consultation", "availability"}
        guarded_lens = lens in {"cost", "consultation", "availability", "safety"}
        community_rescue = cls._contains_any(
            text,
            [
                "추천", "어디", "괜찮은", "잘하는", "경험", "해보신",
                "가보신", "아시는", "궁금", "후기", "부탁",
            ],
        )
        lens_mismatch = guarded_lens and (lens_tier == "mismatch" or (0.0 < lens_score < 50.0))
        if lens_mismatch and not community_rescue:
            return "lens_mismatch"
        is_advertorial, _, _ = cls._detect_advertorial(target, text)
        if (
            not is_advertorial
            and cls._has_domain_anchor(domain, text_lc)
            and cls._pathfinder_source_specific_strict_gap(
            target,
            category,
            text_lc=source_text_lc,
            compact_text=source_compact_text,
            )
        ):
            return "source_context_mismatch"

        # 의미기반 진료축 구제(BGE-M3): 어휘로는 mismatch 여도 글이 해당 축과 의미적으로
        # 가까우면 구어/패러프레이즈 환자글('얼굴 짝짝이'=안면비대칭, '팬자국'=흉터)을 회수.
        # mismatch 가 실제 발생할 때만 1회 계산(지연 평가·캐시) → 비활성 시 비용 0,
        # 정상 통과글은 임베딩하지 않는다. axis 어휘 불일치만 덮고 noise/region/ad 는 위에서
        # 이미 적용됨(정밀도 보존).
        _sem_cache: Dict[str, bool] = {}

        def _semantic_rescue() -> bool:
            if "v" not in _sem_cache:
                _sem_cache["v"] = cls._semantic_axis_rescue(
                    target,
                    text=cls._user_need_text(target),
                    category=category,
                    domain=domain,
                )
            return _sem_cache["v"]

        if category == "안면비대칭" or domain == "asymmetry":
            has_strong_axis_text = cls._contains_any(text, cls.ASYMMETRY_STRONG_AXIS_PATTERNS)
            if (axis_tier == "mismatch" or (0.0 < axis_score < 55.0 and not has_strong_axis_text)) and not _semantic_rescue():
                return "domain_mismatch"
            if conversion_lens and axis_score and axis_score < 60.0 and not _semantic_rescue():
                return "domain_mismatch"

        if category in {"체형교정", "리프팅/탄력", "교통사고"} or domain in {"body", "lifting", "traffic"}:
            has_axis_anchor = cls._has_domain_anchor(domain, text)
            has_user_axis_anchor = cls._has_user_axis_anchor(target, domain=domain, category=category)
            axis_rescue = (
                has_axis_anchor
                and has_user_axis_anchor
                and community_rescue
                and lens in {"review", "community", "consultation"}
            )
            if axis_tier == "mismatch" and not axis_rescue and not _semantic_rescue():
                return "domain_mismatch"
            if 0.0 < axis_score < 55.0 and not has_axis_anchor and not _semantic_rescue():
                return "domain_mismatch"
            if guarded_lens and axis_score and axis_score < 60.0 and not axis_rescue and not _semantic_rescue():
                return "domain_mismatch"

        if category in {"흉터/여드름흉터", "피부/여드름"} or domain == "scar_skin":
            has_axis_anchor = cls._has_user_axis_anchor(target, domain=domain, category=category)
            if axis_tier == "mismatch" and not has_axis_anchor and not _semantic_rescue():
                return "domain_mismatch"
            if guarded_lens and axis_score and axis_score < 55.0 and not has_axis_anchor and not _semantic_rescue():
                return "domain_mismatch"

        return None

    @classmethod
    def _non_relevant_exclude_terms(cls, text: str = "") -> List[str]:
        terms = list(cls.NON_RELEVANT_EXCLUDE)
        if getattr(GYULIM_KEYWORD_PROFILE, "cosmetic_clinic_terms_on_scope", False):
            scar_context = cls._contains_any(
                text,
                [
                    "흉터", "수술흉터", "수술 흉터", "절개흉터", "절개 흉터",
                    "켈로이드", "상처자국", "상처 자국", "패인흉터", "여드름흉터",
                ],
            )
            allowed_cosmetic_context_terms = {"성형외과"}
            if scar_context:
                allowed_cosmetic_context_terms.update({"성형", "쌍수", "코수술", "지방흡입"})
            terms = [term for term in terms if term not in allowed_cosmetic_context_terms]
        return terms

    @classmethod
    def _is_route_navigation(cls, text: str) -> bool:
        """Exclude public transit/directions posts that pollute traffic-accident searches."""
        route_shape = "에서" in text and "까지" in text
        route_terms = cls._contains_any(text, cls.ROUTE_NAVIGATION_PATTERNS)
        accident_or_health_context = cls._contains_any(text, [
            "교통사고", "차사고", "자동차사고", "후유증", "입원", "통원",
            "통증", "치료", "병원", "한의원", "보험", "자보",
        ])
        return bool(route_terms and route_shape and not accident_or_health_context)

    @classmethod
    def final_reject_reason(cls, target: ViralTarget) -> Optional[str]:
        """AI 적합 판정 이후 DB 저장 직전의 마지막 품질 게이트."""
        # 보강된 KIN 본문의 [기존답변N] 구간은 글쓴이가 아닌 기존 답변이다. 답변 속
        # 업체/치과/광고 텍스트가 자연 질문을 오살하지 않도록 게이트는 질문 세그먼트만
        # 평가한다 — 하위 게이트 함수 다수가 target에서 텍스트를 재유도하므로 shallow
        # clone의 preview를 질문 세그먼트로 바꿔 모든 경로(레스큐/사전 게이트/정화
        # 스크립트 포함)에서 일관되게 만든다. 라벨 없는 검색 snippet 연결(미보강)은
        # 전체가 평가되고, planted Q&A·광고답변 판단은 AI 레이어가 담당한다.
        preview = target.content_preview or ""
        if (target.platform or "").lower() in {"kin", "naver_kin"} and "[기존답변" in preview:
            question_segment = preview.split("[기존답변", 1)[0].strip()
            import copy as _copy
            target = _copy.copy(target)
            target.content_preview = question_segment
        title = (target.title or "").lower()
        body = cls._strip_internal_labels(target.content_preview or "").lower()
        text = f"{title} {body}"
        domain = cls._target_domain(target)

        if cls._is_self_target(target):
            return "self_target"
        if cls._is_marketplace_sale(text):
            return "marketplace_sale"
        if cls._is_off_domain(domain, text, title=title):
            return "off_domain"
        if cls._is_non_service_beauty_target(domain, text):
            return "off_domain"
        if cls._is_explicit_hanbang_exclusion(target, text):
            return "off_domain"
        if cls._is_kin_answer_footer_region_noise(target, text):
            return "region_mismatch"
        if cls._is_provider_info_without_user_ask(target, text):
            return "advertorial"
        if cls._is_response_restricted_surface(target, text):
            return "response_restricted"
        if cls._has_ambiguous_region_false_positive(text) and not cls._has_active_region_anchor(target, text):
            return "region_mismatch"
        pathfinder_reason = cls._pathfinder_fit_reject_reason(
            target,
            domain=domain,
            text=text,
            axis_fit_score=cls._score_breakdown_float(target, "pathfinder_axis_fit_score", 0.0),
            axis_fit_tier=cls._score_breakdown_text(target, "pathfinder_axis_fit_tier", ""),
            lens_fit_score=cls._score_breakdown_float(target, "pathfinder_lens_fit_score", 0.0),
            lens_fit_tier=cls._score_breakdown_text(target, "pathfinder_lens_fit_tier", ""),
        )
        if pathfinder_reason:
            return pathfinder_reason
        if cls._is_route_navigation(text):
            return "route_navigation"
        if cls._is_distant_local_target(title, text, local_venue=cls._has_local_venue_anchor(target)):
            return "region_mismatch"
        if cls._contains_any(text, cls._non_relevant_exclude_terms(text)):
            return "non_relevant"
        is_advertorial, _, _ = cls._detect_advertorial(target, text)
        if is_advertorial:
            return "advertorial"
        if not cls._has_domain_anchor(domain, text):
            # 교차축 발견 구제 — 시드 축과 다르더라도 글 자체가 다른 핵심 진료축의
            # 글이면 유효한 발견이다 (라이브: 다이어트 시드가 찾은 청주 추나/자세
            # 질문이 diet 앵커 미스로 탈락). 단, 자기 축 기준으로 전체 게이트를
            # 1회 재귀 평가시켜 그 축의 노이즈 검사(필라테스/헬스/성형 등)까지
            # 통과해야 구제한다 — 앵커만 보면 운동/성형 노이즈가 부활한다.
            own_reject = cls._cross_axis_reject_reason(target, seed_domain=domain)
            if own_reject is not None:
                return "domain_mismatch"
        if cls._contains_any(text, cls.STRICT_MEDICAL_PROMO_PATTERNS):
            return "medical_promo"
        return None

    @classmethod
    def apply_final_reject(cls, target: ViralTarget) -> Optional[str]:
        """Apply final gate result to the target so DB upsert persists the rejection."""
        reason = cls.final_reject_reason(target)
        if not reason:
            return None

        title = (target.title or "").lower()
        body = cls._strip_internal_labels(target.content_preview or "").lower()
        text = f"{title} {body}"
        _is_ad, ad_signals, ad_signal_score = cls._detect_advertorial(target, text)

        target.is_commentable = False
        target.comment_status = cls.FINAL_REJECT_STATUSES.get(reason, "filtered_out")
        target.score_breakdown = {
            **(target.score_breakdown or {}),
            "final_reject_reason": reason,
            "ad_signal_score": float(ad_signal_score),
            "ad_signals": ",".join(ad_signals),
        }
        return reason

    @staticmethod
    @staticmethod
    def _load_self_exclusion() -> Dict[str, List[str]]:
        """business_profile.json에서 자기 업체 제외 규칙 로드 (모듈 시작 시 1회)."""
        import json as _json
        import os as _os
        try:
            here = _os.path.dirname(_os.path.abspath(__file__))
            cfg_path = _os.path.join(here, "config", "business_profile.json")
            if not _os.path.exists(cfg_path):
                return {"blog_authors": [], "url_patterns": [], "title_keywords": []}
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            se = data.get("self_exclusion", {}) or {}
            return {
                "blog_authors": [a.lower() for a in se.get("blog_authors", [])],
                "url_patterns": [u.lower() for u in se.get("url_patterns", [])],
                "title_keywords": [k.lower() for k in se.get("title_keywords", [])],
            }
        except Exception as e:
            logger.warning(f"[CommentableFilter] self_exclusion 로드 실패: {e}")
            return {"blog_authors": [], "url_patterns": [], "title_keywords": []}

    @classmethod
    def _self_exclusion_rules(cls) -> Dict[str, List[str]]:
        if not hasattr(cls, "_self_exclusion"):
            cls._self_exclusion = cls._load_self_exclusion()
        return cls._self_exclusion

    @classmethod
    def _is_self_target(cls, target: 'ViralTarget') -> bool:
        """자기 한의원 블로그/콘텐츠인지 검사 (어뷰징 방지)."""
        se = cls._self_exclusion_rules()
        url = (target.url or "").lower()
        title = (target.title or "").lower()
        author = (target.author or "").lower() if hasattr(target, "author") else ""
        if any(p in url for p in se["url_patterns"]):
            return True
        if any(a in author for a in se["blog_authors"]):
            return True
        if any(k in title for k in se["title_keywords"]):
            return True
        return False

    @classmethod
    def _assess_reply_risk(cls, text: str, target: 'ViralTarget') -> Tuple[int, List[str], bool]:
        """Return score penalty, audit flags, and whether the target must be human-only."""
        flags: List[str] = []
        penalty = 0

        urgent_matches = [kw for kw in cls.URGENT_MEDICAL_KEYWORDS if kw in text]
        if urgent_matches:
            flags.append("urgent_medical")
            penalty -= 60

        sensitive_matches = [kw for kw in cls.SENSITIVE_MEDICAL_KEYWORDS if kw in text]
        if sensitive_matches:
            flags.append("sensitive_medical")
            penalty -= 22

        medication_advice_matches = [kw for kw in cls.MEDICATION_ADVICE_PATTERNS if kw in text]
        if sensitive_matches and medication_advice_matches:
            flags.append("medication_advice_request")
            penalty -= 45

        acute_side_effect_matches = [kw for kw in cls.ACUTE_SIDE_EFFECT_PATTERNS if kw in text]
        if acute_side_effect_matches and (
            sensitive_matches or cls._contains_any(text, ["한약", "약", "복용", "먹고", "처방"])
        ):
            flags.append("acute_side_effect")
            penalty -= 55

        testimonial_matches = [kw for kw in cls.TESTIMONIAL_SENSITIVE_KEYWORDS if kw in text]
        if testimonial_matches:
            flags.append("testimonial_sensitive")
            penalty -= 10

        category = (target.category or "").strip()
        if category in cls.GENERIC_CATEGORY_NAMES and target.matched_keyword_grade not in {"S", "A"}:
            flags.append("generic_category")
            penalty += cls.GENERIC_CATEGORY_PENALTY

        human_only = bool(urgent_matches or (sensitive_matches and medication_advice_matches) or acute_side_effect_matches)
        return penalty, flags, human_only

    @staticmethod
    def _fallback_exposure_score(target: ViralTarget) -> float:
        engagement = (
            math.log10(max(0, getattr(target, "view_count", 0)) + 1) * 7.0
            + math.log10(max(0, getattr(target, "like_count", 0)) + 1) * 6.0
            + math.log10(max(0, getattr(target, "comment_count", 0)) + 1) * 10.0
        )
        platform_base = {
            'cafe': 54.0,
            'kin': 48.0,
            'blog': 38.0,
            'youtube': 55.0,
            'instagram': 52.0,
            'tiktok': 52.0,
            'karrot': 35.0,
        }.get(target.platform, 35.0)
        return round(min(150.0, platform_base + engagement), 2)

    @staticmethod
    def _compose_priority_score(
        exposure_score: float,
        workability_score: float,
        conversion_fit_score: float,
        clinic_treatment_fit_score: Optional[float] = None,
        worksite_efficiency_score: Optional[float] = None,
    ) -> float:
        if clinic_treatment_fit_score is not None or worksite_efficiency_score is not None:
            clinic_scaled = min(150.0, max(0.0, float(clinic_treatment_fit_score or 0.0)) * 1.5)
            worksite_scaled = min(150.0, max(0.0, float(worksite_efficiency_score or 0.0)) * 1.5)
            return round(
                max(0.0, min(
                    150.0,
                    (exposure_score * 0.35)
                    + (workability_score * 0.25)
                    + (conversion_fit_score * 0.20)
                    + (clinic_scaled * 0.12)
                    + (worksite_scaled * 0.08),
                )),
                2,
            )
        return round(
            max(0.0, min(
                150.0,
                (exposure_score * 0.45)
                + (workability_score * 0.35)
                + (conversion_fit_score * 0.20),
            )),
            2,
        )

    def filter(self, targets: List[ViralTarget]) -> List[ViralTarget]:
        """
        타겟 필터링 및 우선순위 점수 계산

        Returns:
            댓글 가능한 타겟만 (priority_score 계산됨)
        """
        filtered = []
        stats = {'self_excluded': 0, 'ad': 0, 'non_relevant': 0, 'too_short': 0,
                 'no_region': 0, 'title_only': 0, 'domain_mismatch': 0,
                 'off_domain': 0, 'not_inquiry_health': 0, 'medical_risk': 0,
                 'advertorial': 0, 'low_intent': 0, 'low_opportunity': 0,
                 'stale_window': 0, 'journey_mismatch': 0, 'unqualified': 0,
                 'clinic_mismatch': 0, 'low_worksite_efficiency': 0,
                 'pathfinder_mismatch': 0, 'response_restricted': 0,
                 'marketplace_sale': 0}

        for target in targets:
            # 0. [의료광고법 + 어뷰징 방지] 자기 업체 자동 제외 (최우선)
            if self._is_self_target(target):
                stats['self_excluded'] += 1
                target.is_commentable = False
                target.comment_status = self.FINAL_REJECT_STATUSES.get("self_target", "filtered_out")
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "final_reject_reason": "self_target",
                }
                continue

            title_lower = (target.title or '').lower()
            body_clean = self._strip_internal_labels(target.content_preview or '')
            body_lower = body_clean.lower()
            text = f"{title_lower} {body_lower}"
            domain = self._target_domain(target)
            early_is_inquiry = any(pat in text for pat in self.REAL_INQUIRY_PATTERNS)

            if self._is_marketplace_sale(text):
                stats['marketplace_sale'] += 1
                target.is_commentable = False
                target.comment_status = self.FINAL_REJECT_STATUSES.get("marketplace_sale", "filtered_out")
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "final_reject_reason": "marketplace_sale",
                }
                continue

            # 1. 광고글 제외 (STRICT만 제외, SOFT는 감점)
            if any(ad in text for ad in self.STRICT_AD_PATTERNS):
                stats['ad'] += 1
                continue
            if any(ad in text for ad in self.STRICT_MEDICAL_PROMO_PATTERNS):
                stats['ad'] += 1
                continue
            if not early_is_inquiry and any(ad in text for ad in self.PROMOTIONAL_MEDICAL_PATTERNS):
                stats['ad'] += 1
                continue
            is_advertorial, ad_signals, ad_signal_score = self._detect_advertorial(target, text)
            if is_advertorial:
                stats['advertorial'] += 1
                target.is_commentable = False
                target.comment_status = "filtered_out_ad"
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "ad_signal_score": float(ad_signal_score),
                    "ad_signals": ",".join(ad_signals),
                }
                continue
            if any(ad in text for ad in self._non_relevant_exclude_terms(text)):
                stats['non_relevant'] += 1
                continue
            if self._is_off_domain(domain, text, title=(target.title or "").lower()):
                stats['off_domain'] += 1
                continue
            if self._is_non_service_beauty_target(domain, text):
                stats['off_domain'] += 1
                continue
            if self._is_explicit_hanbang_exclusion(target, text):
                stats['off_domain'] += 1
                continue
            if self._is_kin_answer_footer_region_noise(target, text):
                stats['no_region'] += 1
                continue
            if self._is_provider_info_without_user_ask(target, text):
                stats['advertorial'] += 1
                continue
            if self._is_response_restricted_surface(target, text):
                stats['response_restricted'] += 1
                target.is_commentable = False
                target.comment_status = "filtered_out"
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "final_reject_reason": "response_restricted",
                }
                continue
            if self._is_asymmetry_axis_noise(target, text):
                stats['off_domain'] += 1
                continue
            if self._is_route_navigation(text):
                stats['non_relevant'] += 1
                continue
            if self._is_distant_local_target(title_lower, text, local_venue=self._has_local_venue_anchor(target)):
                stats['no_region'] += 1
                continue

            early_is_health = any(kw in text for kw in self.HEALTH_KEYWORDS)
            early_viral_need_score, early_viral_need_tier, early_viral_need_signals = self._assess_viral_need(
                target, domain, early_is_inquiry, early_is_health
            )
            pathfinder_ctx = self._pathfinder_execution_context(target)
            pathfinder_short_actionable = (
                float(pathfinder_ctx.get("viral_readiness") or 0.0) >= 78.0
                and float(pathfinder_ctx.get("content_actionability") or 0.0) >= 70.0
                and float(pathfinder_ctx.get("medical_ad_risk") or 0.0) < 40.0
                and (
                    float(pathfinder_ctx.get("community_signal") or 0.0) >= 60.0
                    or float(pathfinder_ctx.get("conversion_signal") or 0.0) >= 50.0
                )
                and self._has_active_region_anchor(target, text)
                and (domain != "general" or target.matched_keyword_grade in {"S", "A"})
            )
            short_actionable = (
                early_viral_need_score >= 55
                and any(
                    signal in early_viral_need_signals
                    for signal in ("recommendation_request", "ready_to_act", "cost_decision")
                )
            ) or pathfinder_short_actionable

            # 2. 본문 최소 길이
            if len(body_clean) < self.MIN_CONTENT_LENGTH and not short_actionable:
                stats['too_short'] += 1
                continue

            # 3. 지역 키워드 필수 (제목 OR 본문)
            if not self._has_active_region_anchor(target, text):
                stats['no_region'] += 1
                continue

            # 4. 제목-본문 동시 매칭 (검색 키워드가 본문에도 있어야 의미 있음)
            if target.matched_keywords:
                base_kw = target.matched_keywords[0].lower()
                # 키워드 토큰화 (공백 기준)하여 주요 토큰 하나라도 본문에 있으면 통과
                tokens = [t for t in base_kw.split() if len(t) >= 2]
                if tokens and not any(tok in body_lower for tok in tokens):
                    if not (short_actionable and any(tok in title_lower for tok in tokens)):
                        stats['title_only'] += 1
                        continue
                if not self._has_domain_anchor(domain, text):
                    stats['domain_mismatch'] += 1
                    continue

            # SOFT 광고 키워드와 약한 advertorial 신호는 감점만
            soft_ad_penalty = sum(-5 for kw in self.SOFT_AD_INDICATORS if kw in text)
            if ad_signal_score > 0:
                soft_ad_penalty -= min(25, ad_signal_score * 4)

            # 5. 질문글 여부
            is_inquiry = early_is_inquiry

            # 6. 건강 관련 여부
            is_health = early_is_health

            # 7. 댓글 가능 여부 결정
            if not (is_inquiry or is_health):
                stats['not_inquiry_health'] += 1
                target.is_commentable = False
                continue

            risk_penalty, risk_flags, human_only = self._assess_reply_risk(text, target)
            if human_only:
                stats['medical_risk'] += 1
                target.is_commentable = False
                target.comment_status = "manual_review"
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "reply_risk_penalty": float(risk_penalty),
                    "manual_review": 1.0,
                    "reply_risk_flags": ",".join(risk_flags),
                }
                continue

            viral_need_score = early_viral_need_score
            viral_need_tier = early_viral_need_tier
            viral_need_signals = early_viral_need_signals
            if viral_need_score < self.MIN_VIRAL_NEED_SCORE:
                stats['low_intent'] += 1
                target.is_commentable = False
                target.comment_status = "filtered_out_low_intent"
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "viral_need_score": float(viral_need_score),
                    "viral_need_tier": viral_need_tier,
                    "viral_need_signals": ",".join(viral_need_signals),
                }
                continue

            reply_opportunity_score, reply_opportunity_tier, reply_opportunity_signals = self._assess_reply_opportunity(
                target,
                domain,
                is_inquiry,
                is_health,
                viral_need_score,
                viral_need_signals,
            )
            if reply_opportunity_score < self.MIN_REPLY_OPPORTUNITY_SCORE:
                stats['low_opportunity'] += 1
                target.is_commentable = False
                target.comment_status = "filtered_out_low_opportunity"
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "viral_need_score": float(viral_need_score),
                    "viral_need_tier": viral_need_tier,
                    "viral_need_signals": ",".join(viral_need_signals),
                    "reply_opportunity_score": float(reply_opportunity_score),
                    "reply_opportunity_tier": reply_opportunity_tier,
                    "reply_opportunity_signals": ",".join(reply_opportunity_signals),
                }
                continue

            timing_window_score, timing_window_tier, timing_window_signals = self._assess_timing_window(
                target,
                viral_need_signals,
                reply_opportunity_signals,
            )
            if timing_window_score < self.MIN_TIMING_WINDOW_SCORE:
                stats['stale_window'] += 1
                target.is_commentable = False
                target.comment_status = "filtered_out_stale_window"
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "viral_need_score": float(viral_need_score),
                    "viral_need_tier": viral_need_tier,
                    "viral_need_signals": ",".join(viral_need_signals),
                    "reply_opportunity_score": float(reply_opportunity_score),
                    "reply_opportunity_tier": reply_opportunity_tier,
                    "reply_opportunity_signals": ",".join(reply_opportunity_signals),
                    "timing_window_score": float(timing_window_score),
                    "timing_window_tier": timing_window_tier,
                    "timing_window_signals": ",".join(timing_window_signals),
                }
                continue

            journey_fit_score, journey_stage, journey_signals = self._assess_journey_fit(
                target,
                domain,
                is_inquiry,
                viral_need_signals,
                reply_opportunity_signals,
                timing_window_score,
            )
            if journey_fit_score < self.MIN_JOURNEY_FIT_SCORE:
                stats['journey_mismatch'] += 1
                target.is_commentable = False
                target.comment_status = "filtered_out_journey_mismatch"
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "viral_need_score": float(viral_need_score),
                    "viral_need_tier": viral_need_tier,
                    "viral_need_signals": ",".join(viral_need_signals),
                    "reply_opportunity_score": float(reply_opportunity_score),
                    "reply_opportunity_tier": reply_opportunity_tier,
                    "reply_opportunity_signals": ",".join(reply_opportunity_signals),
                    "timing_window_score": float(timing_window_score),
                    "timing_window_tier": timing_window_tier,
                    "timing_window_signals": ",".join(timing_window_signals),
                    "journey_fit_score": float(journey_fit_score),
                    "journey_stage": journey_stage,
                    "journey_signals": ",".join(journey_signals),
                }
                continue

            qualification_fit_score, qualification_tier, qualification_signals = self._assess_qualification_fit(
                target,
                domain,
                is_health,
                viral_need_signals,
                reply_opportunity_signals,
                timing_window_score,
                journey_fit_score,
                journey_stage,
            )
            if qualification_fit_score < self.MIN_QUALIFICATION_FIT_SCORE:
                stats['unqualified'] += 1
                target.is_commentable = False
                target.comment_status = "filtered_out_unqualified_lead"
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "viral_need_score": float(viral_need_score),
                    "viral_need_tier": viral_need_tier,
                    "viral_need_signals": ",".join(viral_need_signals),
                    "reply_opportunity_score": float(reply_opportunity_score),
                    "reply_opportunity_tier": reply_opportunity_tier,
                    "reply_opportunity_signals": ",".join(reply_opportunity_signals),
                    "timing_window_score": float(timing_window_score),
                    "timing_window_tier": timing_window_tier,
                    "timing_window_signals": ",".join(timing_window_signals),
                    "journey_fit_score": float(journey_fit_score),
                    "journey_stage": journey_stage,
                    "journey_signals": ",".join(journey_signals),
                    "qualification_fit_score": float(qualification_fit_score),
                    "qualification_tier": qualification_tier,
                    "qualification_signals": ",".join(qualification_signals),
                }
                continue

            clinic_treatment_fit_score, clinic_treatment_fit_tier, clinic_treatment_fit_signals = self._assess_clinic_treatment_fit(
                target,
                domain,
                text,
                is_health,
            )
            if clinic_treatment_fit_score < self.MIN_CLINIC_TREATMENT_FIT_SCORE:
                stats['clinic_mismatch'] += 1
                target.is_commentable = False
                target.comment_status = "filtered_out_clinic_mismatch"
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "viral_need_score": float(viral_need_score),
                    "viral_need_tier": viral_need_tier,
                    "viral_need_signals": ",".join(viral_need_signals),
                    "reply_opportunity_score": float(reply_opportunity_score),
                    "reply_opportunity_tier": reply_opportunity_tier,
                    "reply_opportunity_signals": ",".join(reply_opportunity_signals),
                    "timing_window_score": float(timing_window_score),
                    "timing_window_tier": timing_window_tier,
                    "timing_window_signals": ",".join(timing_window_signals),
                    "journey_fit_score": float(journey_fit_score),
                    "journey_stage": journey_stage,
                    "journey_signals": ",".join(journey_signals),
                    "qualification_fit_score": float(qualification_fit_score),
                    "qualification_tier": qualification_tier,
                    "qualification_signals": ",".join(qualification_signals),
                    "clinic_treatment_fit_score": float(clinic_treatment_fit_score),
                    "clinic_treatment_fit_tier": clinic_treatment_fit_tier,
                    "clinic_treatment_fit_signals": ",".join(clinic_treatment_fit_signals),
                }
                continue

            worksite_efficiency_score, worksite_efficiency_tier, worksite_efficiency_signals = self._assess_worksite_efficiency(
                target,
                clinic_treatment_fit_score,
                viral_need_score,
                viral_need_signals,
                reply_opportunity_score,
                reply_opportunity_signals,
                timing_window_score,
                timing_window_signals,
                journey_fit_score,
                journey_stage,
                qualification_fit_score,
                risk_flags,
            )
            if worksite_efficiency_score < self.MIN_WORKSITE_EFFICIENCY_SCORE:
                stats['low_worksite_efficiency'] += 1
                target.is_commentable = False
                target.comment_status = "filtered_out_low_worksite_efficiency"
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "viral_need_score": float(viral_need_score),
                    "viral_need_tier": viral_need_tier,
                    "viral_need_signals": ",".join(viral_need_signals),
                    "reply_opportunity_score": float(reply_opportunity_score),
                    "reply_opportunity_tier": reply_opportunity_tier,
                    "reply_opportunity_signals": ",".join(reply_opportunity_signals),
                    "timing_window_score": float(timing_window_score),
                    "timing_window_tier": timing_window_tier,
                    "timing_window_signals": ",".join(timing_window_signals),
                    "journey_fit_score": float(journey_fit_score),
                    "journey_stage": journey_stage,
                    "journey_signals": ",".join(journey_signals),
                    "qualification_fit_score": float(qualification_fit_score),
                    "qualification_tier": qualification_tier,
                    "qualification_signals": ",".join(qualification_signals),
                    "clinic_treatment_fit_score": float(clinic_treatment_fit_score),
                    "clinic_treatment_fit_tier": clinic_treatment_fit_tier,
                    "clinic_treatment_fit_signals": ",".join(clinic_treatment_fit_signals),
                    "worksite_efficiency_score": float(worksite_efficiency_score),
                    "worksite_efficiency_tier": worksite_efficiency_tier,
                    "worksite_efficiency_signals": ",".join(worksite_efficiency_signals),
                }
                continue

            # 5. 우선순위 점수 계산 (개선됨: 150점 캡, 세분화된 가중치)
            score = 0
            tags = []  # 태그 수집

            # 질문글 보너스 (정보 탐색 중인 사용자)
            if is_inquiry:
                score += 30
                tags.append("❓질문")

            # 건강 관련 보너스
            if is_health:
                score += 25
                tags.append("🏥건강")

            # 🔥 Hot Lead 감지 (조정: 35→25, 점수 포화 방지)
            hot_lead_matched = [kw for kw in self.HOT_LEAD_KEYWORDS if kw in text]
            if hot_lead_matched:
                score += 25  # Hot Lead 가산 (조정됨)
                tags.append("🔥HOT")
                logger.debug(f"🔥 Hot Lead 감지: {target.title[:30]}... ({hot_lead_matched[:2]})")

            # 🎯 즉시 행동 신호 (예약, 결정 관련 키워드)
            ready_to_act_keywords = [
                "예약", "전화", "상담", "문의", "가격", "비용",
                "방문", "예정", "결정", "선택", "비교"
            ]
            ready_to_act_matched = any(kw in text for kw in ready_to_act_keywords)
            if ready_to_act_matched:
                score += 15  # 즉시 행동 가능성
                if "⚡즉시" not in str(tags):
                    tags.append("⚡즉시")

            # 🎯 경쟁사 탐지는 AI가 수행 (filter 후 별도 호출)
            # AI 탐지 결과는 target.category와 priority_score에 반영됨

            # [Phase 2 개선] 플랫폼별 가중치 (전환율 기반 재조정)
            # [Q10] blog 18->5: 본인 광고 글 비중 높고 게시 전환율 0.02%로 매우 낮음.
            #       search_all에서 디폴트 비수집이지만, 외부 호출 대비 가중치도 다운.
            platform_weights = {
                'cafe': 22,       # 맘카페 = 고전환율
                'blog': 5,        # 블로그 = 신뢰도 낮음 (이전 18)
                'youtube': 16,    # YouTube = 영상 신뢰도
                'kin': 15,        # 지식인 = 질문 많지만 전환 낮음 (20→15)
                'instagram': 12,  # Instagram = 참여도 높지만 전환 낮음 (18→12)
                'tiktok': 10,     # TikTok = 단기 트렌드
                'karrot': 8,      # 당근마켓 = 지역 기반
            }
            score += platform_weights.get(target.platform, 10)

            # [Phase 2 개선] 키워드 티어별 차등 점수 (최대 40점)
            keyword_bonus = self._calculate_keyword_tier_score(target.matched_keywords)
            score += keyword_bonus

            # [Phase 2] SOFT 광고 키워드 감점 적용
            viral_need_bonus = min(35, viral_need_score * 0.35)
            reply_opportunity_adjustment = max(-18, min(18, (reply_opportunity_score - 50) * 0.35))
            timing_window_adjustment = max(-20, min(18, (timing_window_score - 50) * 0.35))
            journey_fit_adjustment = max(-16, min(10, (journey_fit_score - 50) * 0.22))
            qualification_fit_adjustment = max(-18, min(12, (qualification_fit_score - 50) * 0.24))
            clinic_treatment_adjustment = max(-24, min(18, (clinic_treatment_fit_score - 55) * 0.32))
            worksite_efficiency_adjustment = max(-20, min(20, (worksite_efficiency_score - 55) * 0.35))
            pathfinder_axis_fit_score, pathfinder_axis_fit_tier, pathfinder_axis_fit_signals = (
                self._pathfinder_axis_post_fit(
                    target,
                    domain=domain,
                    text=text,
                )
            )
            pathfinder_axis_adjustment = 0.0
            if pathfinder_axis_fit_tier != "neutral":
                pathfinder_axis_adjustment = max(-18.0, min(12.0, (pathfinder_axis_fit_score - 55.0) * 0.28))
            pathfinder_lens_fit_score, pathfinder_lens_fit_tier, pathfinder_lens_fit_signals = (
                self._pathfinder_lens_post_fit(
                    target,
                    platform=target.platform,
                    text=text,
                )
            )
            pathfinder_lens_adjustment = 0.0
            if pathfinder_lens_fit_tier != "neutral":
                pathfinder_lens_adjustment = max(-14.0, min(12.0, (pathfinder_lens_fit_score - 55.0) * 0.30))
            pathfinder_execution_adjustment, pathfinder_execution_signals = self._pathfinder_execution_adjustment(
                target,
                platform=target.platform,
                text=text,
            )
            pathfinder_fit_reject_reason = self._pathfinder_fit_reject_reason(
                target,
                domain=domain,
                text=text,
                axis_fit_score=pathfinder_axis_fit_score,
                axis_fit_tier=pathfinder_axis_fit_tier,
                lens_fit_score=pathfinder_lens_fit_score,
                lens_fit_tier=pathfinder_lens_fit_tier,
            )
            if pathfinder_fit_reject_reason:
                stats['pathfinder_mismatch'] += 1
                target.is_commentable = False
                target.comment_status = self.FINAL_REJECT_STATUSES.get(pathfinder_fit_reject_reason, "filtered_out")
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "final_reject_reason": pathfinder_fit_reject_reason,
                    "pathfinder_axis_fit_score": float(pathfinder_axis_fit_score),
                    "pathfinder_axis_fit_tier": pathfinder_axis_fit_tier,
                    "pathfinder_axis_fit_signals": ",".join(pathfinder_axis_fit_signals),
                    "pathfinder_lens_fit_score": float(pathfinder_lens_fit_score),
                    "pathfinder_lens_fit_tier": pathfinder_lens_fit_tier,
                    "pathfinder_lens_fit_signals": ",".join(pathfinder_lens_fit_signals),
                }
                continue
            score += soft_ad_penalty  # 음수 값이므로 감점됨
            score += risk_penalty
            score += viral_need_bonus
            score += reply_opportunity_adjustment
            score += timing_window_adjustment
            score += journey_fit_adjustment
            score += qualification_fit_adjustment
            score += clinic_treatment_adjustment
            score += worksite_efficiency_adjustment
            score += pathfinder_axis_adjustment
            score += pathfinder_execution_adjustment
            score += pathfinder_lens_adjustment

            if reply_opportunity_score >= 75:
                tags.append("🎯도움")
            if timing_window_score >= 75:
                tags.append("⏱️신속")
            if journey_stage == "decision":
                tags.append("🧭결정")
            if qualification_fit_score >= 75:
                tags.append("✅자격")
            if clinic_treatment_fit_score >= 75:
                tags.append("🏷️진료적합")
            if worksite_efficiency_score >= 75:
                tags.append("📍작업효율")

            # 태그 정보 저장 (content_preview 앞에 추가)
            if tags:
                tag_str = " ".join(tags)
                target.content_preview = f"[{tag_str}] {body_clean}"

            # Workability is the operational "can we comment here?" score.
            target.workability_score = max(0, min(score, 150))
            if not target.exposure_score:
                target.exposure_score = self._fallback_exposure_score(target)

            conversion_fit = 0
            if is_inquiry:
                conversion_fit += 25
            if is_health:
                conversion_fit += 15
            if hot_lead_matched:
                conversion_fit += 35
            if ready_to_act_matched:
                conversion_fit += 25
            conversion_fit += min(50, keyword_bonus * 1.25)
            if target.matched_keyword_grade in {"S", "A"}:
                conversion_fit += 20
            if risk_penalty:
                conversion_fit += max(-45, risk_penalty * 0.6)
            conversion_fit += min(40, viral_need_score * 0.40)
            conversion_fit += min(30, reply_opportunity_score * 0.30)
            conversion_fit += min(24, timing_window_score * 0.24)
            conversion_fit += min(14, journey_fit_score * 0.14)
            conversion_fit += min(22, qualification_fit_score * 0.22)
            conversion_fit += min(30, clinic_treatment_fit_score * 0.30)
            conversion_fit += min(22, worksite_efficiency_score * 0.22)
            if pathfinder_axis_fit_tier != "neutral":
                conversion_fit += max(-18, min(18, (pathfinder_axis_fit_score - 55) * 0.22))
            if pathfinder_lens_fit_tier != "neutral":
                conversion_fit += max(-18, min(18, (pathfinder_lens_fit_score - 55) * 0.24))
            target.conversion_fit_score = max(0, min(conversion_fit, 150))

            target.score_breakdown = {
                **(target.score_breakdown or {}),
                "exposure": target.exposure_score,
                "workability": target.workability_score,
                "conversion_fit": target.conversion_fit_score,
                "keyword_bonus": float(keyword_bonus),
                "soft_ad_penalty": float(soft_ad_penalty),
                "ad_signal_score": float(ad_signal_score),
                "ad_signals": ",".join(ad_signals),
                "viral_need_score": float(viral_need_score),
                "viral_need_tier": viral_need_tier,
                "viral_need_signals": ",".join(viral_need_signals),
                "reply_opportunity_score": float(reply_opportunity_score),
                "reply_opportunity_tier": reply_opportunity_tier,
                "reply_opportunity_signals": ",".join(reply_opportunity_signals),
                "reply_opportunity_adjustment": float(reply_opportunity_adjustment),
                "timing_window_score": float(timing_window_score),
                "timing_window_tier": timing_window_tier,
                "timing_window_signals": ",".join(timing_window_signals),
                "timing_window_adjustment": float(timing_window_adjustment),
                "journey_fit_score": float(journey_fit_score),
                "journey_stage": journey_stage,
                "journey_signals": ",".join(journey_signals),
                "journey_fit_adjustment": float(journey_fit_adjustment),
                "qualification_fit_score": float(qualification_fit_score),
                "qualification_tier": qualification_tier,
                "qualification_signals": ",".join(qualification_signals),
                "qualification_fit_adjustment": float(qualification_fit_adjustment),
                "clinic_treatment_fit_score": float(clinic_treatment_fit_score),
                "clinic_treatment_fit_tier": clinic_treatment_fit_tier,
                "clinic_treatment_fit_signals": ",".join(clinic_treatment_fit_signals),
                "clinic_treatment_adjustment": float(clinic_treatment_adjustment),
                "worksite_efficiency_score": float(worksite_efficiency_score),
                "worksite_efficiency_tier": worksite_efficiency_tier,
                "worksite_efficiency_signals": ",".join(worksite_efficiency_signals),
                "worksite_efficiency_adjustment": float(worksite_efficiency_adjustment),
                "pathfinder_axis_fit_score": float(pathfinder_axis_fit_score),
                "pathfinder_axis_fit_tier": pathfinder_axis_fit_tier,
                "pathfinder_axis_fit_signals": ",".join(pathfinder_axis_fit_signals),
                "pathfinder_axis_adjustment": float(pathfinder_axis_adjustment),
                "pathfinder_lens_fit_score": float(pathfinder_lens_fit_score),
                "pathfinder_lens_fit_tier": pathfinder_lens_fit_tier,
                "pathfinder_lens_fit_signals": ",".join(pathfinder_lens_fit_signals),
                "pathfinder_lens_adjustment": float(pathfinder_lens_adjustment),
                "pathfinder_execution_adjustment": float(pathfinder_execution_adjustment),
                "pathfinder_execution_signals": ",".join(pathfinder_execution_signals),
                "reply_risk_penalty": float(risk_penalty),
                "manual_review": 1.0 if risk_flags else 0.0,
                "reply_risk_flags": ",".join(risk_flags),
            }
            target.priority_score = self._compose_priority_score(
                target.exposure_score,
                target.workability_score,
                target.conversion_fit_score,
                clinic_treatment_fit_score,
                worksite_efficiency_score,
            )
            if timing_window_score < 55:
                timing_priority_adjustment = -min(22.0, (55 - timing_window_score) * 0.75)
            elif timing_window_score >= 75:
                timing_priority_adjustment = min(8.0, (timing_window_score - 75) * 0.25)
            else:
                timing_priority_adjustment = 0.0
            if journey_fit_score < 55:
                journey_priority_adjustment = -min(18.0, (55 - journey_fit_score) * 0.55)
            elif journey_stage == "decision":
                journey_priority_adjustment = min(4.0, (journey_fit_score - 70) * 0.12)
            else:
                journey_priority_adjustment = 0.0
            if qualification_fit_score < 55:
                qualification_priority_adjustment = -min(16.0, (55 - qualification_fit_score) * 0.50)
            elif qualification_fit_score >= 75:
                qualification_priority_adjustment = min(5.0, (qualification_fit_score - 75) * 0.16)
            else:
                qualification_priority_adjustment = 0.0
            pathfinder_priority_adjustment = max(
                -18.0,
                min(
                    14.0,
                    pathfinder_execution_adjustment * 0.45
                    + pathfinder_lens_adjustment * 0.35
                    + pathfinder_axis_adjustment * 0.30,
                ),
            )
            target.priority_score = round(
                max(
                    0.0,
                    min(
                        150.0,
                        target.priority_score
                        + timing_priority_adjustment
                        + journey_priority_adjustment
                        + qualification_priority_adjustment
                        + pathfinder_priority_adjustment,
                    ),
                ),
                2,
            )
            target.score_breakdown["timing_priority_adjustment"] = float(timing_priority_adjustment)
            target.score_breakdown["journey_priority_adjustment"] = float(journey_priority_adjustment)
            target.score_breakdown["qualification_priority_adjustment"] = float(qualification_priority_adjustment)
            target.score_breakdown["pathfinder_priority_adjustment"] = float(pathfinder_priority_adjustment)
            target.is_commentable = True
            filtered.append(target)

        # 우선순위로 정렬
        filtered.sort(key=lambda x: x.priority_score, reverse=True)

        logger.info(
            f"✅ 필터링 완료: {len(targets)}개 -> {len(filtered)}개 (댓글 가능) "
            f"[제외: 광고 {stats['ad']}, 비관련 {stats['non_relevant']}, "
            f"단문 {stats['too_short']}, 지역외 {stats['no_region']}, "
            f"제목만 {stats['title_only']}, 축불일치 {stats['domain_mismatch']}, "
            f"오프도메인 {stats['off_domain']}, 무관 {stats['not_inquiry_health']}, "
            f"의료주의 {stats['medical_risk']}, 광고성 {stats['advertorial']}, "
            f"저의도 {stats['low_intent']}, 저응답적합 {stats['low_opportunity']}, "
            f"타이밍만료 {stats['stale_window']}, 여정불일치 {stats['journey_mismatch']}, "
            f"자격부족 {stats['unqualified']}, 진료불일치 {stats['clinic_mismatch']}, "
            f"응답거부 {stats['response_restricted']}, "
            f"거래글 {stats['marketplace_sale']}, "
            f"작업효율낮음 {stats['low_worksite_efficiency']}, "
            f"Pathfinder불일치 {stats['pathfinder_mismatch']}]"
        )
        # 디스커버리 정직성: 퍼널 거절 사유를 인스턴스에 누적해 영속 감사에서 가시화한다.
        # (조용한 continue 거절도 stats 에 집계되지만 지금까지 로그로만 흘러가 사라졌다.)
        cum = getattr(self, "cumulative_reject_stats", None)
        if cum is None:
            cum = {}
            self.cumulative_reject_stats = cum
        for _reason, _count in stats.items():
            cum[_reason] = cum.get(_reason, 0) + int(_count)
        self.filter_input_count = int(getattr(self, "filter_input_count", 0) or 0) + len(targets)
        self.filter_survivor_count = int(getattr(self, "filter_survivor_count", 0) or 0) + len(filtered)
        return filtered


# ── 바이럴 댓글 표현 변주 (댓글 간 중복/스팸지문 방지) ─────────────────────
# 동일 업체의 댓글들이 같은 상투구·지역어를 반복하면 (1) 네이버 스팸/조작후기 탐지에
# 지문이 잡혀 삭제·페널티 위험, (2) '실제 다녀온 후기' 신뢰도 저하. 댓글 톤(1인칭 경험담)
# 은 건드리지 않고 표현·지역어·구조만 타겟마다 결정적으로 변주해 중복을 줄인다.
# 라이브 근거(2026-06-19): "성안길" 49.9% / "꼼꼼하게 봐주" 9.9% / "체질에 맞춰" 6.1%
# / "상담받아" 18.3% / "만족" 12.2% 의 상투구 반복.
VIRAL_COMMENT_OVERUSED_PHRASES = [
    "원장님이 꼼꼼", "꼼꼼하게 봐주", "꼼꼼하게 잘", "체질에 맞춰",
    "상담 한번 받아보", "만족도가 높", "도움 되실", "입소문", "세심하게 봐",
]
# 규림한의원 실제 위치(청주 성안길/중앙동, 상당구 시내)를 사실 범위 안에서 다르게 표현.
VIRAL_COMMENT_LOCATION_VARIANTS = [
    "성안길 쪽", "청주 시내", "시내 중심가", "청주 상당구 쪽", "성안길 근처", "청주 성안길",
]
VIRAL_COMMENT_PHRASING_ANGLES = [
    "문장 구조와 어휘를 흔한 한의원 댓글과 다르게 잡아 변주하세요.",
    "상투적 추천 문구 대신, 작성자 글의 구체적 단서 한 가지에 반응하세요.",
    "1~2문장으로 짧고 담백하게, 군더더기 수식어를 빼세요.",
    "지역·접근성 언급보다 상담 때 확인할 포인트를 먼저 자연스럽게 녹이세요.",
    "뻔한 공감 표현(예: 'ㅠㅠ 고민되시죠')은 피하고, 공감은 한 번만 자연스럽게 쓰세요.",
]
# 1인칭 경험담 프레임 자체가 매번 같은 구조('저도 ... 다녀왔는데 좋았어요')로 수렴하면
# 네이버 조작후기 탐지 지문이 된다(1인칭을 켠 2026-06-21 이후 신규 리스크). 페르소나
# (1인칭 환자 경험담·정식 명칭 규림한의원)는 유지하되, '시작 방식·전개 순서'만 회전해
# 프레임 중복 지문을 줄인다.
VIRAL_COMMENT_PERSONA_FRAMES = [
    "1인칭 경험을 '저도 비슷한 고민으로 다녀왔던' 맥락으로 시작하세요.",
    "1인칭 경험을 '저 갔을 때는 ~했어요' 식 담담한 회상 톤으로 쓰세요.",
    "결론('좋았어요')부터 말하지 말고 '고민 → 방문 → 느낀 점' 순서로 풀어내세요.",
    "1인칭 경험을 '저는 ~한 편이었는데' 식으로 단정 없이 표현하세요.",
    "방문 경험은 길게 늘어놓지 말고 한 가지 인상만 짧게 언급하세요.",
    "작성자 글의 구체적 단서에 먼저 반응한 뒤 1인칭 경험을 자연스럽게 녹이세요.",
]

# 시그니처(차별화) 진료축 — routers/viral.py SIGNATURE_ROUTING_AXES 와 동일 집합(레이어
# 분리상 의도적 중복; 수정 시 양쪽 동기화). 로컬 환자 글이 구조적으로 희소해 일반 백로그
# 레스큐(category-blind + 21일 윈도우)에서 굶는 축이다. raw_backlog는 이미 commentable
# 게이트를 통과한 '예산-기아' 공급이므로, 확장 윈도우 + 카테고리 우선 별도 레인으로 끌어오면
# 전환 효율이 높다. _load_backlog_rescue_targets(categories=, days=) 로 공급한다.
SIGNATURE_BACKLOG_AXES = ("흉터/여드름흉터", "안면비대칭")
# 시그니처 레인 최근성 윈도우(일) — 일반 레스큐(21일)보다 길게. 시그니처 글은 드물어
# 오래된 raw_backlog도 직원 작업가치가 유지된다(빈도<신선도 우선).
SIGNATURE_BACKLOG_RESCUE_DAYS = 180

# AI 생성 실패/차단 sentinel 문자열. 이것이 댓글로 저장되면 (1) 직원이 "[AI] generation
# blocked…" 같은 오류문을 댓글로 보게 되고 (2) comment_status가 'generated'로 바뀌며
# 골든큐(pending)에서 사라져 실제 바이럴 타겟이 조용히 유실된다. generate()는 이런
# 결과를 빈 문자열로 반환해, 모든 호출부(if comment 가드)가 저장·상태전환을 건너뛰고
# 타겟을 pending으로 보존하도록 한다.
VIRAL_COMMENT_FAILED_SENTINELS = (
    "[ai error]",
    "[생성 실패]",
    "generation blocked",
    "blocked by medical advertising",
    "codex cli is unavailable",
    "생성 차단됨",
)


# ============================================
# AI 댓글 생성 클래스
# ============================================
class AICommentGenerator:
    """
    AI 기반 맞춤 댓글 생성

    Centralized ai_client 사용
    카테고리별 프롬프트 템플릿
    """

    UNIFIED_ANALYSIS_PREVIEW_CHARS = 700
    UNIFIED_AD_SAFETY_NOTE = """

[추가 제외 기준]
- 검색 스니펫이 원 질문 뒤에 기존 답변/댓글을 라벨 없이 이어 붙인 경우, 뒤쪽 답변에 특정 병원/한의원/제품 추천, 예약/위치/전화/상담/가격/이벤트/홈페이지/카카오톡 안내가 보이면 SUITABLE=false로 판정하세요.
- 단, 본문에 "[기존답변N]" 라벨이 있으면 질문과 이미 달린 답변이 구분된 것입니다. 이때 SUITABLE 판단은 라벨 앞의 질문 부분 기준입니다: 질문이 자연스러운 환자 글이면 답변에 업체 홍보가 있어도 SUITABLE=true일 수 있습니다. 답변에 특정 한의원/병원 추천이 보이면 COMPETITOR=true와 COMPETITOR_NAME으로 보고하세요.
- 질문 자체가 특정 업체를 칭찬하거나, 질문과 답변이 같은 업체를 짜맞춘 자문자답 마케팅으로 보이면 SUITABLE=false.
- "저도 ... 효과", "성안길/지웰시티 쪽 OO한의원", "상담 한번 받아보세요", "네이버에서 검색", "비용 부담 없이", "할인이벤트/무제한/패키지" 같은 문구는 자연 질문이 아니라 광고성 답변 스니펫 신호입니다.
- 제목이 질문형이어도 본문 대부분이 매끄러운 병원 홍보, 후기 가장, 기존 답변 추천이면 promotion/review/other로 제외하세요.
"""

    def __init__(self):
        self.cfg = ConfigManager()
        logger.info("✅ AI Client 초기화 완료 (centralized ai_client)")

    def _load_prompts(self) -> dict:
        """prompts.json에서 viral_hunter 프롬프트 로드"""
        try:
            prompts = self.cfg.load_prompts()
            return prompts.get('viral_hunter', {})
        except Exception:
            return {}

    # 경쟁사 탐지 참조는 단일 소스(config/competitors.json)에서 로드한다. 과거에는
    # 프롬프트에 하드코딩된 stale 목록(로랑·데이릴 누락)을 AI에 줘서, 사용자의 #1
    # 경쟁사(로랑/데이릴 안면비대칭)를 한 번도 못 잡고 엉뚱한 한의원만 플래그했다.
    _curated_competitors_cache: Optional[Dict[str, Any]] = None

    @classmethod
    def _load_curated_competitors(cls) -> Dict[str, Any]:
        """config/competitors.json + business_profile.json에서 경쟁사/자기업체 참조 로드.

        반환: {'critical': [...], 'others': [...], 'self': [...], 'all': set(lower)}.
        rank tracking·competitor analysis와 동일 소스라 목록이 다시 stale되지 않는다.
        """
        if cls._curated_competitors_cache is not None:
            return cls._curated_competitors_cache
        import os as _os
        here = _os.path.dirname(_os.path.abspath(__file__))
        critical: List[str] = []
        others: List[str] = []
        self_names: List[str] = []
        try:
            with open(_os.path.join(here, "config", "competitors.json"), encoding="utf-8") as f:
                data = json.load(f)
            for _cat, info in (data.get("category_competitors") or {}).items():
                for comp in (info.get("main_competitors") or []):
                    name = str(comp.get("name") or "").strip()
                    if not name:
                        continue
                    bucket = critical if comp.get("priority") == "critical" else others
                    if name not in bucket:
                        bucket.append(name)
        except Exception as e:
            logger.warning(f"[AICommentGenerator] competitors.json 로드 실패: {e}")
        try:
            with open(_os.path.join(here, "config", "business_profile.json"), encoding="utf-8") as f:
                profile = json.load(f)
            se = profile.get("self_exclusion", {}) or {}
            self_names = [str(k).strip() for k in (se.get("title_keywords") or []) if str(k).strip()]
        except Exception as e:
            logger.warning(f"[AICommentGenerator] business_profile.json 로드 실패: {e}")
        if not self_names:
            self_names = ["규림", "kyurim"]
        # critical에 들어간 이름이 others에 중복되지 않게
        others = [n for n in others if n not in critical]
        all_lower = {n.lower() for n in critical + others}
        cls._curated_competitors_cache = {
            "critical": critical,
            "others": others,
            "self": self_names,
            "all": all_lower,
        }
        return cls._curated_competitors_cache

    @classmethod
    def _classify_competitor_name(cls, name: str) -> str:
        """detected COMPETITOR_NAME → 'self' | 'critical' | 'known' | 'unknown'.

        자기 업체 추천은 역공략 대상이 아니므로 분리하고, 큐레이트된 critical
        경쟁사(로랑/데이릴 등)는 우선순위 부스트 대상으로 표시한다.
        """
        raw = (name or "").strip().lower()
        if not raw or raw in {"n/a", "na", "none", "없음", "-"}:
            return "unknown"
        data = cls._load_curated_competitors()
        for self_token in data["self"]:
            if self_token and self_token.lower() in raw:
                return "self"

        def _matches(curated: List[str]) -> bool:
            for c in curated:
                cl = c.lower().strip()
                if not cl:
                    continue
                core = cl.split()[0]  # "자연과한의원 청주점" → "자연과한의원"
                if cl in raw or raw in cl or (len(core) >= 3 and core in raw):
                    return True
            return False

        if _matches(data["critical"]):
            return "critical"
        if _matches(data["others"]):
            return "known"
        return "unknown"

    @staticmethod
    def _competitor_name_is_identifiable(name: str) -> bool:
        """역공략(경쟁사 카운터)은 '어느 경쟁사를 카운터할지' 아는 것이 핵심이다.

        AI가 COMPETITOR=true 를 보고해도 식별 가능한 경쟁사명이 없으면(N/A·빈값·미상)
        카운터할 대상 자체가 없으므로 역공략이 성립하지 않는다 — 이때 프리미엄
        경쟁사_역공략 레인 승격과 우선순위 가산(최대 +25)을 적용하면 안 된다.
        라이브 근거: 전체 ai_competitor=true 706건 중 30%(211건)가 무명(N/A) competitor
        였고 그중 164건이 직원에게 skip 되었다(레인 오염 + 미획득 부스트).
        단, 큐레이트 목록에 없는 실제 한의원/병원명(_classify_competitor_name='unknown')은
        유효한 역공략 대상이므로 통과시킨다 — placeholder 토큰만 거른다.
        """
        raw = (name or "").strip().lower()
        if len(raw) < 2:
            return False
        placeholders = {
            "n/a", "na", "none", "null", "unknown", "없음", "미상", "해당없음",
            "불명", "알수없음", "확인불가", "확인안됨", "기타", "etc", "-", "--",
        }
        return raw not in placeholders

    @classmethod
    def _competitor_reference_note(cls) -> str:
        """AI 프롬프트에 덧붙일 권위 있는 경쟁사 참조 블록 (자기업체 제외 지시 포함)."""
        data = cls._load_curated_competitors()
        critical = ", ".join(data["critical"]) or "(없음)"
        others = ", ".join(data["others"]) or "(없음)"
        self_names = ", ".join(data["self"]) or "규림"
        return (
            "\n\n[청주 경쟁사 참조 — 아래 목록을 권위 기준으로 사용]\n"
            f"- 최우선 역공략 경쟁사(언급 시 COMPETITOR=true, COMPETITOR_NAME에 정식명 그대로): {critical}\n"
            f"- 기타 청주 경쟁사: {others}\n"
            f"- 목록에 없는 다른 한의원/병원이 추천돼도 COMPETITOR=true로 보고하되 COMPETITOR_NAME에 실제명을 적으세요.\n"
            f"- ※ 다음은 '우리 한의원'입니다. 절대 COMPETITOR로 보고하지 마세요: {self_names}. "
            "우리 한의원이 추천된 글은 COMPETITOR=false로 두세요.\n"
        )

    def _build_unified_prompt(self, template: str, posts_formatted: str) -> str:
        """통합 분석 프롬프트 조립 — 두 호출 경로(순차/병렬)가 공유.

        competitor_reference 플레이스홀더가 있으면 채우고, 없으면(구버전 템플릿)
        권위 블록을 안전하게 append 한다. 광고 안전 노트도 항상 덧붙인다.
        """
        comp_note = self._competitor_reference_note()
        try:
            body = template.format(
                posts_formatted=posts_formatted,
                competitor_reference=comp_note,
            )
            if "{competitor_reference}" not in template:
                body += comp_note
        except (KeyError, IndexError):
            body = template.format(posts_formatted=posts_formatted) + comp_note
        return body + self.UNIFIED_AD_SAFETY_NOTE

    @classmethod
    def _format_unified_target(cls, post_id: int, target: ViralTarget) -> str:
        body = CommentableFilter._strip_internal_labels(target.content_preview or "")
        body = re.sub(r"\s+", " ", body).strip()
        preview = body[:cls.UNIFIED_ANALYSIS_PREVIEW_CHARS] if body else "(없음)"
        breakdown = target.score_breakdown or {}
        pathfinder_lines = []
        if target.matched_keywords:
            pathfinder_lines.append(f"PATHFINDER_KEYWORD: {', '.join(target.matched_keywords[:3])}")
        if target.matched_keyword_category or target.category:
            pathfinder_lines.append(
                f"PATHFINDER_CATEGORY: {target.matched_keyword_category or target.category}"
            )
        search_query = str(breakdown.get("pathfinder_search_query") or "").strip()
        context_keyword = str(breakdown.get("pathfinder_context_keyword") or "").strip()
        source_keyword = str(breakdown.get("pathfinder_source_keyword") or "").strip()
        query_variant = str(breakdown.get("pathfinder_query_variant") or "").strip()
        source_keywords = cls._score_breakdown_terms(breakdown.get("pathfinder_source_keywords"), limit=4)
        query_variants = cls._score_breakdown_terms(breakdown.get("pathfinder_query_variants"), limit=4)
        if any((search_query, context_keyword, source_keyword, query_variant, source_keywords, query_variants)):
            search_parts = []
            if source_keyword:
                search_parts.append(f"source={source_keyword}")
            if search_query:
                search_parts.append(f"query={search_query}")
            if query_variant:
                search_parts.append(f"variant={query_variant}")
            if context_keyword and context_keyword not in {source_keyword, search_query}:
                search_parts.append(f"context={context_keyword}")
            if source_keywords and len(source_keywords) > 1:
                search_parts.append(f"sources={', '.join(source_keywords)}")
            if query_variants and len(query_variants) > 1:
                search_parts.append(f"variants={', '.join(query_variants)}")
            collision_count = breakdown.get("pathfinder_context_collision_count")
            if collision_count not in (None, "", 0, 0.0):
                search_parts.append(f"collisions={collision_count}")
            pathfinder_lines.append("PATHFINDER_SEARCH: " + "; ".join(search_parts[:7]))
        readiness = breakdown.get("pathfinder_viral_readiness_score")
        actionability = breakdown.get("pathfinder_content_actionability_score")
        medical_risk = breakdown.get("pathfinder_medical_ad_risk_score")
        if any(value not in (None, "", 0, 0.0) for value in (readiness, actionability, medical_risk)):
            pathfinder_lines.append(
                "PATHFINDER_EXECUTION: "
                f"readiness={readiness or 0}, "
                f"actionability={actionability or 0}, "
                f"medical_ad_risk={medical_risk or 0}, "
                f"surface={breakdown.get('pathfinder_preferred_search_surface') or ''}, "
                f"type={breakdown.get('pathfinder_recommended_content_type') or ''}, "
                f"lens={breakdown.get('pathfinder_execution_lens') or ''}"
            )
        source_signals = cls._score_breakdown_list(breakdown.get("pathfinder_source_signals"))
        quality_flags = cls._score_breakdown_list(breakdown.get("pathfinder_quality_flags"))
        if source_signals or quality_flags:
            pathfinder_lines.append(
                "PATHFINDER_SIGNALS: "
                f"sources={', '.join(source_signals[:4]) or 'none'}; "
                f"flags={', '.join(quality_flags[:3]) or 'none'}"
            )
        insight_brief = str(breakdown.get("pathfinder_insight_brief") or "").strip()
        if insight_brief:
            pathfinder_lines.append(f"PATHFINDER_BRIEF: {insight_brief}")
        axis_score = breakdown.get("pathfinder_axis_fit_score")
        lens_score = breakdown.get("pathfinder_lens_fit_score")
        if any(value not in (None, "", 0, 0.0) for value in (axis_score, lens_score)):
            axis_tier = str(breakdown.get("pathfinder_axis_fit_tier") or "").strip()
            lens_tier = str(breakdown.get("pathfinder_lens_fit_tier") or "").strip()
            axis_signals = cls._score_breakdown_terms(breakdown.get("pathfinder_axis_fit_signals"), limit=3)
            lens_signals = cls._score_breakdown_terms(breakdown.get("pathfinder_lens_fit_signals"), limit=3)
            fit_parts = []
            if axis_score not in (None, "", 0, 0.0):
                fit_parts.append(f"axis={axis_score}/{axis_tier or 'unknown'}")
            if lens_score not in (None, "", 0, 0.0):
                fit_parts.append(f"lens={lens_score}/{lens_tier or 'unknown'}")
            if axis_signals:
                fit_parts.append(f"axis_signals={', '.join(axis_signals)}")
            if lens_signals:
                fit_parts.append(f"lens_signals={', '.join(lens_signals)}")
            pathfinder_lines.append("PATHFINDER_FIT: " + "; ".join(fit_parts))
        pathfinder_context = ("\n" + "\n".join(pathfinder_lines)) if pathfinder_lines else ""
        return (
            f"\n---\nPOST_ID: {post_id}\n플랫폼: {target.platform}\n"
            f"제목: {target.title}\n"
            f"내용: {preview}{pathfinder_context}\n---\n"
        )

    @staticmethod
    def _score_breakdown_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item not in (None, "")]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return [value] if value.strip() else []
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item not in (None, "")]
            if parsed:
                return [str(parsed)]
        return [str(value)] if value else []

    @classmethod
    def _score_breakdown_terms(cls, value: Any, limit: int = 6) -> List[str]:
        terms: List[str] = []
        for item in cls._score_breakdown_list(value):
            for part in re.split(r"[,;]", str(item)):
                clean = part.strip()
                if clean:
                    terms.append(clean)
        return list(dict.fromkeys(terms))[: max(0, int(limit or 0))]

    @staticmethod
    def _compliance_guardrail(target: ViralTarget) -> str:
        risk_flags = ""
        if target.score_breakdown:
            risk_flags = str(target.score_breakdown.get("reply_risk_flags", ""))
        clinic_name = "리커버의원" if GYULIM_KEYWORD_PROFILE.profile_key == "recover_gangnam" else "규림한의원"
        return f"""
[필수 운영 원칙]
- 댓글은 도움이 되는 정보성·경험 공유 답변이어야 하며, 광고처럼 보이거나 업체 소속을 숨긴 잠입·사칭(이름을 가린 제3자 추천)처럼 보이면 안 됩니다.
- '저도 {clinic_name} 다녀왔는데...' 같은 1인칭 방문·경험담 톤은 사용해도 되지만(정식 명칭 노출), 구체적 수치(몇 kg·며칠)·전후 결과·단정적 효과는 지어내지 마세요.
- 병원/의원/한의원 이름을 숨기기 위해 초성, 은어, 모호한 표현을 쓰지 마세요.
- {clinic_name}을 언급할 때는 정식 명칭을 사용하고, 소속을 숨긴 제3자 추천처럼 쓰지 마세요.
- 의료 효능 보장, 완치, 전후 비교, 최상급/비교 우위, 가격 유인, 이벤트성 문구를 쓰지 마세요.
- 진단·처방처럼 단정하지 말고, 증상이 있으면 자격 있는 전문가 상담을 권하세요.
- 댓글은 1~2문장으로 짧게 쓰고, AI/광고 고지 문구는 생성 후 자동 첨부되므로 제거를 유도하지 마세요.
- 민감 신호: {risk_flags or "없음"}
"""

    @staticmethod
    def _normalize_transparency_terms(comment: str) -> str:
        """Replace old stealth-style clinic references with explicit naming."""
        if GYULIM_KEYWORD_PROFILE.profile_key == "recover_gangnam":
            replacements = (
                (r"강남\s*ㄹㅋㅂ\s*(?:의원|클리닉)?", "리커버의원"),
                (r"ㄹㅋㅂ\s*(?:의원|클리닉)?", "리커버의원"),
                (r"리커버\s*클리닉", "리커버의원"),
                (r"리커버\s*강남", "리커버의원"),
            )
        else:
            replacements = (
                (r"성안길\s*ㄱㄹ\s*한의원", "규림한의원"),
                (r"시내\s*ㄱㄹ\s*한의원", "규림한의원"),
                (r"ㄱㄹ\s*한의원", "규림한의원"),
                (r"성안길\s*ㄱㄹ", "규림한의원"),
                (r"시내\s*ㄱㄹ", "규림한의원"),
                (r"ㄱ으로\s*시작하는\s*한의원", "규림한의원"),
                (r"ㄱ자\s*한의원", "규림한의원"),
                (r"성안길\s*쪽\s*한의원", "규림한의원"),
                (r"시내\s*그\s*한의원", "규림한의원"),
                (r"(?<![가-힣A-Za-z0-9])ㄱㄹ(?![가-힣A-Za-z0-9])", "규림한의원"),
            )
        normalized = comment
        for pattern, replacement in replacements:
            normalized = re.sub(pattern, replacement, normalized)
        normalized = re.sub(
            r"(완전|진짜|적극|강력|강추)\s*추천(?:해요|합니다|드려요|드립니다|!)?",
            "확인해보실 수 있어요",
            normalized,
        )
        normalized = re.sub(
            r"후회\s*안\s*하실\s*거예요",
            "상담 기준을 확인해보시면 좋겠습니다",
            normalized,
        )
        normalized = re.sub(
            r"(친구|지인|엄마|가족|언니|동생)[^.!?\n]{0,60}(빠졌|감량|좋아졌|나아졌|효과)[^.!?\n]*(?:[.!?]|$)",
            "개인차가 있어서 상담 때 상태를 확인해보는 게 좋습니다.",
            normalized,
        )
        normalized = re.sub(
            r"확실히\s*(좋아졌어요|좋아졌|나아졌어요|나아졌|효과\s*봤어요|효과)",
            "도움이 될 수 있습니다",
            normalized,
        )
        normalized = re.sub(
            r"\d+\s*kg\s*(빠졌|감량)",
            "체중 관리 방향을 확인",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = normalized.replace("도움이 될 수어요", "도움이 될 수 있습니다")
        normalized = re.sub(r"(규림한의원|리커버의원)(?:\s*(?:도|이랑|와|과)?\s*)\1", r"\1", normalized)
        return normalized

    @staticmethod
    def _is_failed_comment_text(text: str) -> bool:
        """AI 생성 실패/차단 sentinel(또는 빈 결과)인지 판별. 댓글로 저장되어선 안 되며
        (오류문 노출 + 'generated' 상태전환으로 타겟 유실), generate()에서 ''로 치환된다."""
        if not text or not text.strip():
            return True
        low = text.strip().lower()
        return any(s in low for s in VIRAL_COMMENT_FAILED_SENTINELS)

    @staticmethod
    def _phrasing_variation_directive(target: "ViralTarget") -> str:
        """타겟마다 결정적으로 회전하는 표현-변주 지시.

        댓글 톤/페르소나(1인칭 경험담)는 건드리지 않고 상투구·지역어·구조만 다양화해
        댓글 간 중복 지문을 줄인다. target id/url 기반 안정 해시로 회전 → 같은 글은 항상
        같은 변주, 다른 글끼리는 고르게 분산.
        """
        seed_src = str(
            getattr(target, "id", "") or getattr(target, "url", "") or getattr(target, "title", "")
        )
        seed = int(hashlib.md5(seed_src.encode("utf-8")).hexdigest(), 16) if seed_src else 0
        loc = VIRAL_COMMENT_LOCATION_VARIANTS[seed % len(VIRAL_COMMENT_LOCATION_VARIANTS)]
        angle = VIRAL_COMMENT_PHRASING_ANGLES[(seed // 7) % len(VIRAL_COMMENT_PHRASING_ANGLES)]
        frame = VIRAL_COMMENT_PERSONA_FRAMES[(seed // 13) % len(VIRAL_COMMENT_PERSONA_FRAMES)]
        banned = ", ".join(f'"{p}"' for p in VIRAL_COMMENT_OVERUSED_PHRASES)
        return (
            "\n[표현 변주 — 댓글 간 중복/스팸지문 방지]\n"
            f"- 다음 상투구는 그대로 반복하지 말고 매번 다른 말로 표현하세요: {banned}.\n"
            f"- 규림한의원 위치를 언급한다면 이번엔 '{loc}' 식으로 표현하세요(매번 같은 지역어 반복 금지).\n"
            f"- {angle}\n"
            f"- 1인칭 경험담 시작 방식 변주: {frame} (단, 정식 명칭 '규림한의원'은 유지)\n"
        )

    @staticmethod
    def _comment_input_text(target: "ViralTarget", max_chars: int = 500) -> str:
        """댓글 프롬프트에 넣을 사용자 질문 본문.

        KIN `[기존답변N]` 이후의 경쟁사/타인 답변을 잘라낸다 — 댓글은 '사용자 질문'에
        응답해야 하는데, raw content_preview[:300]는 (1) 짧은 질문일 때 창이 경쟁사 답변으로
        채워져 댓글이 답변에 휩쓸리거나 경쟁사 정보를 끌어오고, (2) 긴 질문(>300자)은 잘려
        맥락이 누락됐다. 게이트의 질문-세그먼트 분리(2026-06-12)와 동일 철학을 댓글 생성에도
        적용해, 질문 세그먼트를 더 넉넉히(max_chars) 전달한다. `[기존답변]`이 없으면 전체
        preview를 사용하고, 세그먼트가 비정상적으로 짧으면 원본으로 폴백(fail-soft)."""
        preview = (getattr(target, "content_preview", "") or "")
        question = preview.split("[기존답변", 1)[0].strip()
        if len(question) < 10:
            question = preview.strip()
        return question[:max_chars]

    def generate(self, target: ViralTarget, style: str = "default") -> str:
        """
        단일 타겟에 대한 맞춤 댓글 생성

        Args:
            target: ViralTarget 객체
            style: 댓글 스타일 (default, empathy, informative, experience, question, recommendation)

        Returns:
            생성된 댓글 텍스트
        """
        prompts = self._load_prompts()
        comment_config = prompts.get('comment_generation', {})
        prompt_template = comment_config.get('template', '')

        # 스타일별 suffix 가져오기
        style_suffix = ""
        styles = comment_config.get('styles', {})
        if style and style in styles:
            style_suffix = styles[style].get('suffix', '')

        if not prompt_template:
            # 기본 프롬프트 (config/prompts.json 미로드 시 폴백)
            prompt_template = """다음 게시글에 자연스럽고 도움이 되는 댓글 초안을 작성해주세요.

[게시글 정보]
플랫폼: {platform}
제목: {title}
내용 미리보기: {content_preview}
관련 키워드: {keywords}

[댓글 작성 가이드]
1. 작성자 고민에 먼저 공감하고, 확인하면 좋은 기준을 한 가지만 알려주세요.
2. 규림한의원을 언급할 때는 정식 명칭을 쓰고 소속을 숨긴 추천처럼 쓰지 마세요.
3. '저도 규림한의원 다녀왔는데...' 같은 1인칭 방문 경험담 톤은 괜찮지만, 구체 수치·전후 결과·단정 효과는 꾸며내지 마세요.
4. 효과를 단정하지 말고 가능성 표현으로 1~2문장만 작성하세요.

댓글:"""

        try:
            prompt = prompt_template.format(
                platform=target.platform,
                title=target.title,
                # 사용자 질문 세그먼트만 전달([기존답변] 경쟁사 답변 제거, 질문은 더 넉넉히).
                content_preview=self._comment_input_text(target),
                keywords=', '.join(target.matched_keywords)
            )

            # 스타일별 suffix 추가
            if style_suffix:
                prompt += style_suffix

            guardrail = self._compliance_guardrail(target)
            try:
                topic = " ".join([target.title or "", " ".join(target.matched_keywords or [])]).strip()
                db_path = os.path.join(ConfigManager().root_dir, "db", "marketing_data.db")
                pathfinder_context = load_pathfinder_prompt_context(
                    db_path,
                    agent="viral_hunter_agent",
                    topic=topic,
                    limit=5,
                )
            except Exception as e:
                pathfinder_context = f"[Pathfinder Insight Handoff unavailable: {e}]"
            variation = self._phrasing_variation_directive(target)
            prompt = (
                f"{guardrail}\n{prompt}\n"
                f"{variation}"
                f"\n[Pathfinder Insight Handoff]\n{pathfinder_context}\n"
                "[최종 확인] 위 필수 운영 원칙을 우선 적용하고, 허위 경험담/사칭/은폐성 광고는 절대 작성하지 마세요."
            )
            comment = ai_generate_korean(
                prompt,
                # 표현 다양성을 위해 약간 높임(0.6→0.72). 컴플라이언스 스크린/재시도가 계속 가드.
                temperature=0.72,
                max_tokens=800,
                task="viral_comment",
                call_site="viral_hunter.generate",
            )

            # 댓글 정제
            comment = comment.replace("댓글:", "").strip()
            comment = comment.replace("답변:", "").strip()
            comment = comment.replace("```", "").strip()
            comment = self._normalize_transparency_terms(comment)

            # AI 에러/컴플라이언스 차단 sentinel을 댓글로 저장하지 않는다 — 빈 문자열을
            # 반환하면 호출부(if comment 가드)가 저장·'generated' 전환을 건너뛰고 타겟을
            # pending으로 보존(재시도 가능). web UI 단건은 500 "댓글 생성 실패"로 응답.
            if self._is_failed_comment_text(comment):
                logger.warning("댓글 생성 실패/차단 sentinel 감지 — 빈 결과 반환(타겟 pending 보존)")
                return ""

            return comment

        except Exception as e:
            logger.error(f"댓글 생성 실패: {e}")
            return ""

    def batch_generate(self, targets: List[ViralTarget], limit: int = 10) -> List[ViralTarget]:
        """
        대량 댓글 생성

        Args:
            targets: 타겟 리스트
            limit: 최대 생성 수

        Returns:
            댓글이 생성된 타겟 리스트
        """
        generated = []

        for i, target in enumerate(targets[:limit], 1):
            logger.info(f"[{i}/{min(len(targets), limit)}] 댓글 생성 중: {target.title[:30]}...")

            comment = self.generate(target)
            target.generated_comment = comment
            generated.append(target)

            # Rate limiting
            time.sleep(0.5)

        logger.info(f"✅ 댓글 생성 완료: {len(generated)}개")
        return generated

    def detect_competitors(self, targets: List[ViralTarget], batch_size: int = 10) -> List[ViralTarget]:
        """
        AI 기반 경쟁사 탐지 (배치 처리)

        Args:
            targets: 분석할 타겟 리스트
            batch_size: 한 번에 분석할 개수

        Returns:
            경쟁사 탐지 결과가 반영된 타겟 리스트
        """
        prompts = self._load_prompts()
        competitor_config = prompts.get('competitor_detection', {})
        template = competitor_config.get('template', '')

        if not template:
            logger.warning("⚠️ competitor_detection 프롬프트 없음")
            return targets

        logger.info(f"🎯 AI 경쟁사 탐지 시작: {len(targets)}개 타겟")

        # 배치 처리
        for batch_start in range(0, len(targets), batch_size):
            batch = targets[batch_start:batch_start + batch_size]

            # 게시글 포맷팅
            posts_formatted = ""
            for i, target in enumerate(batch, 1):
                posts_formatted += f"""
---
POST_ID: {i}
플랫폼: {target.platform}
제목: {target.title}
내용 미리보기: {target.content_preview[:200] if target.content_preview else '(없음)'}
---
"""

            try:
                prompt = template.format(posts_formatted=posts_formatted)
                result_text = ai_generate(prompt, temperature=0.3, task="structured")

                # 결과 파싱
                self._parse_competitor_results(batch, result_text)

                logger.info(f"   ✅ 배치 {batch_start // batch_size + 1} 완료 ({len(batch)}개)")

                # Rate limiting
                time.sleep(1.0)

            except Exception as e:
                logger.error(f"경쟁사 탐지 배치 실패: {e}")
                continue

        # 결과 요약
        competitor_count = sum(1 for t in targets if t.category == "경쟁사_역공략")
        if competitor_count > 0:
            logger.info(f"⚔️ 경쟁사 역공략 기회 발견: {competitor_count}개")

        return targets

    def _parse_competitor_results(self, targets: List[ViralTarget], result_text: str):
        """
        AI 경쟁사 탐지 결과 파싱

        결과 형식:
        POST_ID: 1
        COMPETITOR_DETECTED: true
        COMPETITOR_TYPE: direct/indirect/recommendation_risk/complaint/none
        COMPETITOR_NAME: 자연과한의원
        COUNTER_OPPORTUNITY: 75
        REASON: 이유 설명
        ---
        """
        # 각 POST 결과 분리
        posts = result_text.split('---')

        for post_result in posts:
            if not post_result.strip():
                continue

            # POST_ID 추출
            post_id_match = re.search(r'POST_ID:\s*(\d+)', post_result)
            if not post_id_match:
                continue

            post_id = int(post_id_match.group(1)) - 1  # 0-indexed
            if post_id < 0 or post_id >= len(targets):
                continue

            target = targets[post_id]

            # COMPETITOR_DETECTED 추출
            detected_match = re.search(r'COMPETITOR_DETECTED:\s*(true|false)', post_result, re.IGNORECASE)
            if not detected_match:
                continue

            is_detected = detected_match.group(1).lower() == 'true'

            if is_detected:
                # COUNTER_OPPORTUNITY 점수 추출
                score_match = re.search(r'COUNTER_OPPORTUNITY:\s*(\d+)', post_result)
                counter_score = int(score_match.group(1)) if score_match else 50

                # COMPETITOR_TYPE 추출
                type_match = re.search(r'COMPETITOR_TYPE:\s*(\w+)', post_result)
                comp_type = type_match.group(1) if type_match else "unknown"

                # COMPETITOR_NAME 추출
                name_match = re.search(r'COMPETITOR_NAME:\s*(.+?)(?:\n|$)', post_result)
                comp_name = name_match.group(1).strip() if name_match else "N/A"

                # 식별 가능한 경쟁사명이 없거나(N/A·빈값) 자기 업체(규림/리커버)면
                # 역공략이 성립하지 않으므로 프리미엄 레인 승격·우선순위 가산을 생략한다
                # (글은 본래 진료축 카테고리를 유지).
                if (not self._competitor_name_is_identifiable(comp_name)
                        or self._classify_competitor_name(comp_name) == "self"):
                    continue

                # 타겟 업데이트
                target.category = "경쟁사_역공략"

                # 우선순위 점수 가산 (역공략 기회 점수 기반)
                bonus = min(counter_score // 4, 25)  # 최대 25점 가산
                target.priority_score = min((target.priority_score or 0) + bonus, 150)

                # content_preview에 태그 추가
                if "⚔️경쟁사" not in target.content_preview:
                    if comp_name and comp_name != "N/A":
                        target.content_preview = f"[⚔️{comp_name}] {target.content_preview}"
                    else:
                        target.content_preview = f"[⚔️경쟁사감지] {target.content_preview}"

                logger.debug(f"⚔️ 경쟁사 탐지: {target.title[:30]}... ({comp_type}: {comp_name}, 점수+{bonus})")

    def evaluate_infiltration(self, targets: List[ViralTarget], batch_size: int = 10) -> List[ViralTarget]:
        """
        AI 기반 댓글 응대 적합도 평가 (배치 처리)

        투명한 댓글 응대에 적합한 글인지 평가:
        - 적합: 추천요청, 고민상담, 경험질문, 정보요청
        - 부적합: 홍보글, 후기글, 뉴스, 이미 해결된 글

        Args:
            targets: 평가할 타겟 리스트
            batch_size: 한 번에 분석할 개수

        Returns:
            댓글 응대 적합도가 평가된 타겟 리스트 (적합한 것만 반환)
        """
        prompts = self._load_prompts()
        eval_config = prompts.get('infiltration_evaluation', {})
        template = eval_config.get('template', '')

        if not template:
            logger.warning("⚠️ infiltration_evaluation 프롬프트 없음")
            return targets

        logger.info(f"🔍 AI 댓글 응대 적합도 평가 시작: {len(targets)}개 타겟")

        suitable_targets = []
        unsuitable_count = 0

        # 배치 처리
        for batch_start in range(0, len(targets), batch_size):
            batch = targets[batch_start:batch_start + batch_size]

            # 게시글 포맷팅
            posts_formatted = ""
            for i, target in enumerate(batch, 1):
                posts_formatted += f"""
---
POST_ID: {i}
플랫폼: {target.platform}
제목: {target.title}
내용 미리보기: {target.content_preview[:200] if target.content_preview else '(없음)'}
---
"""

            try:
                prompt = template.format(posts_formatted=posts_formatted)
                result_text = ai_generate(prompt, temperature=0.3, task="structured")

                # 결과 파싱
                batch_suitable, batch_unsuitable = self._parse_infiltration_results(batch, result_text)
                suitable_targets.extend(batch_suitable)
                unsuitable_count += batch_unsuitable

                logger.info(f"   ✅ 배치 {batch_start // batch_size + 1} 완료 (적합: {len(batch_suitable)}, 부적합: {batch_unsuitable})")

                # Rate limiting
                time.sleep(1.0)

            except Exception as e:
                logger.error(f"댓글 응대 적합도 평가 배치 실패: {e}")
                # 실패한 배치는 큐에 넣지 않고 재시도 대상으로 남긴다.
                for target in batch:
                    target.comment_status = "needs_ai_retry"
                continue

        # 결과 요약
        logger.info(f"✅ 댓글 응대 적합도 평가 완료: {len(targets)}개 → 적합 {len(suitable_targets)}개, 부적합 {unsuitable_count}개")

        # 적합한 타겟만 우선순위순 정렬
        suitable_targets.sort(key=lambda x: x.priority_score, reverse=True)

        return suitable_targets

    def unified_analysis(self, targets: List[ViralTarget], batch_size: int = 25) -> List[ViralTarget]:
        """
        통합 AI 분석 (경쟁사 탐지 + 댓글 응대 적합도 평가를 하나로)

        기존: detect_competitors() + evaluate_infiltration() = API 2회
        통합: unified_analysis() = API 1회 (50% 감소)

        Args:
            targets: 분석할 타겟 리스트
            batch_size: 한 번에 분석할 개수 (기본 25개, 기존 10개에서 증가)

        Returns:
            분석 완료된 타겟 리스트 (댓글 응대에 적합한 것만)
        """
        # AI client is always available via centralized ai_client

        prompts = self._load_prompts()
        unified_config = prompts.get('unified_analysis', {})
        template = unified_config.get('template', '')

        if not template:
            # 통합 프롬프트 없으면 기존 방식 사용
            logger.warning("⚠️ unified_analysis 프롬프트 없음, 기존 방식 사용")
            targets = self.detect_competitors(targets, batch_size=10)
            return self.evaluate_infiltration(targets, batch_size=10)

        # 설정에서 배치 크기 로드 (기본값 25)
        batch_size = unified_config.get('batch_size', batch_size)

        logger.info(f"🔬 AI 통합 분석 시작: {len(targets)}개 타겟 (배치 크기: {batch_size})")

        suitable_targets = []
        unsuitable_count = 0
        competitor_count = 0

        total_batches = (len(targets) + batch_size - 1) // batch_size

        # 배치 처리
        for batch_idx, batch_start in enumerate(range(0, len(targets), batch_size), 1):
            batch = targets[batch_start:batch_start + batch_size]

            # 게시글 포맷팅
            posts_formatted = ""
            for i, target in enumerate(batch, 1):
                posts_formatted += self._format_unified_target(i, target)

            try:
                prompt = self._build_unified_prompt(template, posts_formatted)
                result_text = ai_generate(prompt, temperature=0.3, task="structured")

                # 결과 파싱
                batch_suitable, batch_unsuitable, batch_competitor = self._parse_unified_results(batch, result_text)
                final_suitable = []
                for target in batch_suitable:
                    if CommentableFilter.apply_final_reject(target):
                        batch_unsuitable += 1
                        continue
                    final_suitable.append(target)
                batch_suitable = final_suitable
                suitable_targets.extend(batch_suitable)
                unsuitable_count += batch_unsuitable
                competitor_count += batch_competitor

                logger.info(f"   ✅ 배치 {batch_idx}/{total_batches} 완료 (적합: {len(batch_suitable)}, 부적합: {batch_unsuitable}, 경쟁사: {batch_competitor})")

                # Rate limiting
                time.sleep(0.8)

            except Exception as e:
                logger.error(f"통합 분석 배치 실패: {e}")
                # 실패한 배치는 큐에 넣지 않고 재시도 대상으로 남긴다.
                for target in batch:
                    target.comment_status = "needs_ai_retry"
                continue

        # 결과 요약
        logger.info(f"✅ 통합 분석 완료: {len(targets)}개 → 적합 {len(suitable_targets)}개, 부적합 {unsuitable_count}개")
        if competitor_count > 0:
            logger.info(f"⚔️ 경쟁사 역공략 기회 발견: {competitor_count}개")

        # 적합한 타겟만 우선순위순 정렬
        suitable_targets.sort(key=lambda x: x.priority_score, reverse=True)

        return suitable_targets

    def unified_analysis_parallel(
        self,
        targets: List[ViralTarget],
        batch_size: int = 25,
        max_workers: int = 5,
        db=None,
        skip_batch_indices: Optional[set] = None,
        on_batch_done=None,
    ) -> List[ViralTarget]:
        """
        병렬 + 증분 저장 버전의 unified_analysis.

        배치 단위 Qwen 호출을 ThreadPoolExecutor로 병렬 처리하고,
        매 N배치마다 `db.insert_viral_target()`으로 즉시 저장한다.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        prompts = self._load_prompts()
        unified_config = prompts.get('unified_analysis', {})
        template = unified_config.get('template', '')
        if not template:
            logger.warning("⚠️ unified_analysis 프롬프트 없음 — 순차 모드로 폴백")
            return self.unified_analysis(targets, batch_size=batch_size)

        batch_size = unified_config.get('batch_size', batch_size)
        total_batches = (len(targets) + batch_size - 1) // batch_size
        skip = skip_batch_indices or set()
        self.last_failed_ai_batches = set()

        logger.info(
            f"🔬 AI 통합 분석 시작(병렬): {len(targets)}개, 배치 {batch_size}, "
            f"총 {total_batches}배치, 동시 {max_workers}, 건너뛸 배치 {len(skip)}"
        )

        def run_batch(batch_idx: int, batch: List[ViralTarget]):
            posts_formatted = ""
            for i, t in enumerate(batch, 1):
                posts_formatted += self._format_unified_target(i, t)
            try:
                prompt = self._build_unified_prompt(template, posts_formatted)
                result_text = ai_generate(prompt, temperature=0.3, task="structured")
                suitable, unsuit, comp = self._parse_unified_results(batch, result_text)
                return batch_idx, suitable, unsuit, comp, None, list(batch)
            except Exception as e:
                return batch_idx, [], 0, 0, e, list(batch)

        suitable_all: List[ViralTarget] = []
        done_batches = set(skip)
        lock = threading.Lock()
        save_every = 10  # 10배치마다 체크포인트 + DB 저장 로그

        # 제출할 배치만 선별
        pending = []
        for batch_idx, batch_start in enumerate(range(0, len(targets), batch_size), 1):
            if batch_idx in skip:
                continue
            pending.append((batch_idx, targets[batch_start:batch_start + batch_size]))

        processed_since_checkpoint = 0

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(run_batch, idx, b): idx for idx, b in pending}
            for fut in as_completed(futures):
                result = fut.result()
                if len(result) == 5:
                    batch_idx, suitable, unsuit, comp, err = result
                    batch_targets = []
                else:
                    batch_idx, suitable, unsuit, comp, err, batch_targets = result
                failed_batch = batch_targets if err else []
                if err:
                    self.last_failed_ai_batches.add(batch_idx)
                    retry_saved = 0
                    if db is not None:
                        for t in failed_batch:
                            t.comment_status = "needs_ai_retry"
                            try:
                                if db.insert_viral_target(t.to_dict()):
                                    retry_saved += 1
                            except Exception as save_err:
                                logger.warning(f"AI 재시도 대상 저장 실패: {save_err}")
                    logger.warning(
                        f"   ⚠️ 배치 {batch_idx} 실패({err}) → pending 제외, "
                        f"needs_ai_retry {retry_saved}개 저장"
                    )
                    continue

                # AI 부적합 판정 영속화 — 침묵 폐기하면 부적합 행이 DB에 남지 않아
                # 구조/시드 수율 피드백의 분모와 디스커버리 감사가 왜곡되고,
                # 레스큐된 raw_backlog 행은 매 런 재레스큐되는 루프가 생긴다.
                ai_unsuitable_saved = 0
                if db is not None and batch_targets:
                    parsed_suitable_keys = {(t.url or t.id) for t in suitable}
                    for t in batch_targets:
                        if (t.url or t.id) in parsed_suitable_keys:
                            continue
                        t.ai_reviewed = True
                        t.is_commentable = False
                        t.comment_status = "filtered_out_ai"
                        t.score_breakdown = {
                            **(t.score_breakdown or {}),
                            "ai_verdict": "unsuitable",
                        }
                        try:
                            if db.insert_viral_target(t.to_dict()):
                                ai_unsuitable_saved += 1
                        except Exception as e:
                            logger.warning(f"AI 부적합 상태 저장 실패: {e}")

                final_suitable = []
                final_rejected = 0
                final_reject_saved = 0
                for t in suitable:
                    reject_reason = CommentableFilter.apply_final_reject(t)
                    if reject_reason:
                        final_rejected += 1
                        if db is not None:
                            try:
                                if db.insert_viral_target(t.to_dict()):
                                    final_reject_saved += 1
                            except Exception as e:
                                logger.warning(f"최종 게이트 제외 상태 저장 실패: {e}")
                        logger.debug(f"최종 게이트 제외({reject_reason}): {t.title[:60]}")
                        continue
                    final_suitable.append(t)
                suitable = final_suitable

                # 즉시 DB 저장
                newly_saved = 0
                if db is not None:
                    for t in suitable:
                        try:
                            if db.insert_viral_target(t.to_dict()):
                                newly_saved += 1
                        except Exception as e:
                            logger.warning(f"DB 저장 실패: {e}")

                with lock:
                    suitable_all.extend(suitable)
                    done_batches.add(batch_idx)
                    processed_since_checkpoint += 1
                    logger.info(
                        f"   ✅ 배치 {batch_idx}/{total_batches} 완료 "
                        f"(적합 {len(suitable)}, 최종제외 {final_rejected}, "
                        f"최종제외저장 {final_reject_saved}, 부적합 {unsuit}, "
                        f"부적합저장 {ai_unsuitable_saved}, "
                        f"경쟁사 {comp}, 저장 {newly_saved}) "
                        f"[누적 {len(done_batches)}/{total_batches}]"
                    )
                    # 체크포인트 저장
                    if on_batch_done and processed_since_checkpoint >= save_every:
                        try:
                            on_batch_done(done_batches.copy())
                            processed_since_checkpoint = 0
                        except Exception as e:
                            logger.warning(f"체크포인트 콜백 실패: {e}")

        # 마지막 체크포인트
        if on_batch_done:
            try:
                on_batch_done(done_batches.copy())
            except Exception:
                pass

        suitable_all.sort(key=lambda x: x.priority_score, reverse=True)
        logger.info(f"✅ 병렬 통합 분석 완료: 적합 {len(suitable_all)}개")
        return suitable_all

    def _parse_unified_results(self, targets: List[ViralTarget], result_text: str) -> tuple:
        """
        통합 분석 결과 파싱

        결과 형식:
        POST_ID: 1
        SUITABLE: true/false
        SCORE: 85
        TYPE: recommendation_request
        COMPETITOR: true/false
        COMPETITOR_NAME: 자연과한의원
        COUNTER_SCORE: 75
        REASON: 추천 요청글, 경쟁사 언급 있음
        ---
        """
        suitable = []
        unsuitable_count = 0
        competitor_count = 0

        # 각 POST 결과 분리
        posts = result_text.split('---')

        # 처리된 POST_ID 추적
        processed_ids = set()

        for post_result in posts:
            if not post_result.strip():
                continue

            # POST_ID 추출
            post_id_match = re.search(r'POST_ID:\s*(\d+)', post_result)
            if not post_id_match:
                continue

            post_id = int(post_id_match.group(1)) - 1  # 0-indexed
            if post_id < 0 or post_id >= len(targets):
                continue

            # 중복 처리 방지
            if post_id in processed_ids:
                continue
            processed_ids.add(post_id)

            target = targets[post_id]

            # SUITABLE 추출
            suitable_match = re.search(r'SUITABLE:\s*(true|false)', post_result, re.IGNORECASE)
            is_suitable = suitable_match.group(1).lower() == 'true' if suitable_match else False

            # SCORE 추출
            score_match = re.search(r'SCORE:\s*(\d+)', post_result)
            infiltration_score = int(score_match.group(1)) if score_match else 50

            # TYPE 추출
            type_match = re.search(r'TYPE:\s*(\w+)', post_result)
            post_type = type_match.group(1) if type_match else "unknown"

            # COMPETITOR 추출
            competitor_match = re.search(r'COMPETITOR:\s*(true|false)', post_result, re.IGNORECASE)
            has_competitor = competitor_match.group(1).lower() == 'true' if competitor_match else False

            # COMPETITOR_NAME 추출
            name_match = re.search(r'COMPETITOR_NAME:\s*(.+?)(?:\n|$)', post_result)
            comp_name = name_match.group(1).strip() if name_match else "N/A"

            # 식별 가능한 경쟁사명이 없으면(N/A·빈값) 역공략이 성립하지 않는다 —
            # 카운터할 대상이 없는데 프리미엄 레인 승격·우선순위 가산이 붙던 결함 방지.
            # 글 자체는 SUITABLE이면 본래 진료축에서 정상 노출된다(공급 손실 없음).
            if has_competitor and not self._competitor_name_is_identifiable(comp_name):
                has_competitor = False
            # 자기 업체(규림/리커버) 추천은 역공략 대상이 아니다 — competitor 플래그 해제.
            # critical(로랑/데이릴 등)은 우선순위 부스트 대상으로 분류.
            comp_class = self._classify_competitor_name(comp_name) if has_competitor else "unknown"
            if comp_class == "self":
                has_competitor = False

            # COUNTER_SCORE 추출
            counter_match = re.search(r'COUNTER_SCORE:\s*(\d+)', post_result)
            counter_score = int(counter_match.group(1)) if counter_match else 0

            if is_suitable:
                target.ai_reviewed = True
                target.ai_infiltration_score = infiltration_score
                target.ai_post_type = post_type
                target.ai_competitor = has_competitor
                target.ai_competitor_name = comp_name if has_competitor else ""

                # 적합한 글: 점수 반영 및 태그 추가
                bonus = min(infiltration_score // 5, 20)  # 최대 20점 가산
                target.priority_score = min((target.priority_score or 0) + bonus, 150)
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "ai_infiltration_bonus": float(bonus),
                    "ai_infiltration_score": float(infiltration_score),
                }

                # 타입별 태그 추가
                type_tags = {
                    "recommendation_request": "💡추천요청",
                    "consultation": "💬고민상담",
                    "experience_question": "❓경험질문",
                    "info_request": "ℹ️정보요청"
                }
                tag = type_tags.get(post_type, "✅적합")

                if tag not in target.content_preview:
                    target.content_preview = f"[{tag}] {target.content_preview}"

                # 경쟁사 탐지 결과 반영
                if has_competitor:
                    competitor_count += 1
                    target.category = "경쟁사_역공략"

                    # 역공략 점수 가산
                    counter_bonus = min(counter_score // 4, 25)
                    target.priority_score = min((target.priority_score or 0) + counter_bonus, 150)
                    target.score_breakdown = {
                        **(target.score_breakdown or {}),
                        "ai_counter_bonus": float(counter_bonus),
                        "ai_counter_score": float(counter_score),
                        "competitor_class": comp_class,
                    }

                    # 큐레이트된 critical 경쟁사(사용자 #1 위협: 로랑/데이릴 안면비대칭 등)
                    # 가로채기는 직원 큐 최상단으로 끌어올린다.
                    if comp_class == "critical":
                        crit_boost = 10
                        target.priority_score = min((target.priority_score or 0) + crit_boost, 150)
                        target.score_breakdown["competitor_critical_boost"] = float(crit_boost)

                    if comp_name and comp_name != "N/A" and "⚔️" not in target.content_preview:
                        flag = "⚔️🎯" if comp_class == "critical" else "⚔️"
                        target.content_preview = f"[{flag}{comp_name}] {target.content_preview}"

                suitable.append(target)
            else:
                unsuitable_count += 1

        # 파싱되지 않은 타겟은 pending에 넣지 않는다.
        for i, target in enumerate(targets):
            if i not in processed_ids:
                unsuitable_count += 1

        return suitable, unsuitable_count, competitor_count

    def _parse_infiltration_results(self, targets: List[ViralTarget], result_text: str) -> tuple:
        """
        AI 댓글 응대 적합도 평가 결과 파싱

        결과 형식:
        POST_ID: 1
        SUITABLE: true/false
        SCORE: 85
        TYPE: recommendation_request
        REASON: 추천 요청글
        ---
        """
        suitable = []
        unsuitable_count = 0

        # 각 POST 결과 분리
        posts = result_text.split('---')

        # 처리된 POST_ID 추적
        processed_ids = set()

        for post_result in posts:
            if not post_result.strip():
                continue

            # POST_ID 추출
            post_id_match = re.search(r'POST_ID:\s*(\d+)', post_result)
            if not post_id_match:
                continue

            post_id = int(post_id_match.group(1)) - 1  # 0-indexed
            if post_id < 0 or post_id >= len(targets):
                continue

            # 중복 처리 방지
            if post_id in processed_ids:
                continue
            processed_ids.add(post_id)

            target = targets[post_id]

            # SUITABLE 추출
            suitable_match = re.search(r'SUITABLE:\s*(true|false)', post_result, re.IGNORECASE)
            if not suitable_match:
                unsuitable_count += 1
                continue

            is_suitable = suitable_match.group(1).lower() == 'true'

            # SCORE 추출
            score_match = re.search(r'SCORE:\s*(\d+)', post_result)
            infiltration_score = int(score_match.group(1)) if score_match else 50

            # TYPE 추출
            type_match = re.search(r'TYPE:\s*(\w+)', post_result)
            post_type = type_match.group(1) if type_match else "unknown"

            if is_suitable:
                target.ai_reviewed = True
                target.ai_infiltration_score = infiltration_score
                target.ai_post_type = post_type

                # 적합한 글: 점수 반영 및 태그 추가
                bonus = min(infiltration_score // 5, 20)  # 최대 20점 가산
                target.priority_score = min((target.priority_score or 0) + bonus, 150)
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "ai_infiltration_bonus": float(bonus),
                    "ai_infiltration_score": float(infiltration_score),
                }

                # 타입별 태그 추가
                type_tags = {
                    "recommendation_request": "💡추천요청",
                    "consultation": "💬고민상담",
                    "experience_question": "❓경험질문",
                    "info_request": "ℹ️정보요청"
                }
                tag = type_tags.get(post_type, "✅적합")

                if tag not in target.content_preview:
                    target.content_preview = f"[{tag}] {target.content_preview}"

                suitable.append(target)
                logger.debug(f"✅ 응대적합: {target.title[:30]}... ({post_type}, 점수: {infiltration_score})")
            else:
                # 부적합한 글: 제외
                unsuitable_count += 1
                logger.debug(f"❌ 응대부적합: {target.title[:30]}... ({post_type})")

        # 파싱되지 않은 타겟은 pending에 넣지 않는다.
        for i, target in enumerate(targets):
            if i not in processed_ids:
                unsuitable_count += 1

        return suitable, unsuitable_count


# ============================================
# 메인 오케스트레이터 클래스
# ============================================
class ViralHunter:
    """
    Viral Hunter 메인 클래스

    기능:
    - 타겟 발굴 (hunt)
    - 댓글 생성 (generate_comments)
    - DB 저장/조회
    """
    USER_SURFACE_HEAVY_CATEGORIES = {
        "흉터/여드름흉터",
        "피부/여드름",
        "다이어트",
        "안면비대칭",
        "체형교정",
        "리프팅/탄력",
    }
    AXIS_COMPANION_EXPANDED_CATEGORIES = {
        "흉터/여드름흉터",
        "피부/여드름",
        "다이어트",
        "안면비대칭",
        "체형교정",
        "리프팅/탄력",
        "교통사고",
    }

    # 의미기반 발견 2단계(구어 쿼리 확장): 환자가 임상어 없이 쓰는 구어/패러프레이즈로
    # Naver 가 구어 환자글을 애초에 반환하도록 쿼리를 넓힌다('얼굴 짝짝이'=안면비대칭).
    # 시드당 +1 슬롯으로 순환 추가되고 변형 yield 게이트가 자기조절(무수율 시 폐기)하므로
    # 노이즈는 자동 가지치기된다. opt-in(MARKETING_BOT_SEMANTIC_DISCOVERY) — 사용자가
    # 진료축 구어 어휘를 직접 확장/검수할 수 있도록 여기 단일 지점에 둔다.
    COLLOQUIAL_AXIS_TERMS: Dict[str, Tuple[str, ...]] = {
        "안면비대칭": ("얼굴 짝짝이", "얼굴 비뚤어짐", "턱 틀어짐", "얼굴 좌우 비대칭"),
        "흉터/여드름흉터": ("여드름 자국", "얼굴 팬자국", "피부 구덩이", "여드름 흉터 자국"),
        "피부/여드름": ("얼굴 트러블", "성인 여드름 고민", "피부 뒤집어짐"),
        "다이어트": ("살이 안빠져요", "뱃살 빼는 법", "체중 안줄어"),
        "체형교정": ("자세 틀어짐", "골반 틀어짐", "어깨 비대칭"),
        "리프팅/탄력": ("얼굴 처짐", "피부 탄력 저하", "팔자주름 고민"),
    }

    def __init__(self):
        self.db = DatabaseManager()
        self.cfg = ConfigManager()
        self.searcher = NaverUnifiedSearch()
        self.filter = CommentableFilter()
        self.generator = AICommentGenerator()
        self.seed_builder = ViralSeedBuilder()
        self.keyword_context: Dict[str, dict] = {}

    def _load_keywords(
        self,
        use_latest_legion: bool = True,
        source_scan_run_id: Optional[int] = None,
    ) -> List[str]:
        """
        Pathfinder 전용 모드 - 검증된 키워드만 사용

        campaigns.json 비활성화:
        - 65.3% 미검증 키워드 제거
        - 100% Pathfinder 검증 키워드만 사용
        - 자동 업데이트 지원
        """
        if use_latest_legion:
            seeds = self.seed_builder.build(scan_run_id=source_scan_run_id)
            if seeds:
                self.keyword_context = {seed.keyword: seed.to_context() for seed in seeds}
                scan_id = seeds[0].scan_run_id
                categories = {}
                for seed in seeds:
                    categories[seed.category] = categories.get(seed.category, 0) + 1
                logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                logger.info(f"🎯 최신 Legion scan #{scan_id} 기반 Viral seed {len(seeds)}개 로드")
                for category, count in categories.items():
                    logger.info(f"   • {category}: {count}개")
                logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                return [seed.keyword for seed in seeds]
            if source_scan_run_id:
                logger.warning(f"Pathfinder scan #{source_scan_run_id} produced no Viral seeds; falling back to legacy keyword loader")
            logger.warning("⚠️ 최신 Legion 기반 seed를 찾지 못해 legacy keyword loader로 폴백합니다")

        keywords = set()
        keyword_sources = {
            'targets_json': 0,
            'pathfinder_sa': 0,
            'pathfinder_b': 0,
            'trending': 0
        }

        # 1. targets.json의 community_scan_keywords (핵심 키워드만)
        try:
            targets = self.cfg.load_targets()
            for kw in targets.get('community_scan_keywords', []):
                keywords.add(kw)
                keyword_sources['targets_json'] += 1
        except Exception as e:
            logger.warning(f"targets.json 로드 실패: {e}")

        # 2. campaigns.json - 비활성화됨 ⚠️
        # 이유: 65.3% 미검증 키워드, 품질 혼재
        # Pathfinder로 대체 (아래 참조)
        """
        try:
            campaigns_path = os.path.join(self.cfg.root_dir, 'config', 'campaigns.json')
            if os.path.exists(campaigns_path):
                with open(campaigns_path, 'r', encoding='utf-8') as f:
                    campaigns = json.load(f)
                for target in campaigns.get('targets', []):
                    for seed in target.get('seeds', []):
                        keywords.add(seed)
                        keyword_sources['campaigns_json'] += 1
        except Exception as e:
            logger.warning(f"campaigns.json 로드 실패: {e}")
        """

        # 3. Pathfinder S/A급 키워드 (최고 품질) ⭐
        try:
            import sqlite3
            db_path = os.path.join(self.cfg.root_dir, 'db', 'marketing_data.db')

            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path, timeout=10)
                cursor = conn.cursor()

                # S/A급 키워드 전체
                cursor.execute("""
                    SELECT keyword
                    FROM keyword_insights
                    WHERE grade IN ('S', 'A')
                    ORDER BY priority_v3 DESC
                """)

                pathfinder_sa = cursor.fetchall()
                for row in pathfinder_sa:
                    keywords.add(row[0])
                    keyword_sources['pathfinder_sa'] += 1

                conn.close()

                if keyword_sources['pathfinder_sa'] > 0:
                    logger.info(f"✅ Pathfinder S/A급: {keyword_sources['pathfinder_sa']}개")
                else:
                    logger.warning("⚠️ Pathfinder에서 S/A급 키워드를 찾지 못했습니다")

        except Exception as e:
            logger.warning(f"Pathfinder S/A급 로드 실패: {e}")

        # 4. Pathfinder B급 키워드 (품질 확장) ⭐ 신규
        try:
            import sqlite3
            db_path = os.path.join(self.cfg.root_dir, 'db', 'marketing_data.db')

            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path, timeout=10)
                cursor = conn.cursor()

                # B급 상위 100개 (우선순위 높은 순)
                cursor.execute("""
                    SELECT keyword
                    FROM keyword_insights
                    WHERE grade = 'B'
                    ORDER BY priority_v3 DESC
                    LIMIT 100
                """)

                pathfinder_b = cursor.fetchall()
                for row in pathfinder_b:
                    keywords.add(row[0])
                    keyword_sources['pathfinder_b'] += 1

                conn.close()

                if keyword_sources['pathfinder_b'] > 0:
                    logger.info(f"✅ Pathfinder B급 (상위): {keyword_sources['pathfinder_b']}개")

        except Exception as e:
            logger.warning(f"Pathfinder B급 로드 실패: {e}")

        # 5. 트렌드 rising 키워드 (선택적) ⭐
        try:
            import sqlite3
            db_path = os.path.join(self.cfg.root_dir, 'db', 'marketing_data.db')

            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path, timeout=10)
                cursor = conn.cursor()

                # 트렌드 상승 중인 A/B급 키워드
                cursor.execute("""
                    SELECT keyword
                    FROM keyword_insights
                    WHERE trend_status = 'rising'
                    AND grade IN ('A', 'B')
                    LIMIT 30
                """)

                trending_keywords = cursor.fetchall()
                for row in trending_keywords:
                    keywords.add(row[0])
                    keyword_sources['trending'] += 1

                conn.close()

                if keyword_sources['trending'] > 0:
                    logger.info(f"📈 트렌드 키워드: {keyword_sources['trending']}개")

        except Exception as e:
            logger.warning(f"트렌드 키워드 로드 실패: {e}")

        # 기본 키워드 (비어있을 경우)
        if not keywords:
            keywords = {"청주 한의원", "청주 다이어트"}

        # 통계 출력
        total = len(keywords)
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"📊 Pathfinder 전용 모드 - 키워드 로드 완료")
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"   • targets.json: {keyword_sources['targets_json']}개")
        logger.info(f"   • Pathfinder S/A급: {keyword_sources['pathfinder_sa']}개")
        logger.info(f"   • Pathfinder B급: {keyword_sources['pathfinder_b']}개")
        logger.info(f"   • 트렌드: {keyword_sources['trending']}개")
        logger.info(f"   • 총 {total}개 (중복 제거 후)")
        logger.info(f"   • 검증률: 100% (모두 Pathfinder 검증)")
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        return list(keywords)

    def _load_keyword_context(self, keywords: Optional[List[str]] = None):
        """Load Pathfinder lineage for latest, legacy, or custom keyword runs."""
        if keywords:
            missing_keywords = [
                keyword
                for keyword in keywords
                if keyword and keyword not in self.keyword_context
            ]
            if missing_keywords:
                self.keyword_context.update(self.seed_builder.keyword_context_for(missing_keywords))
            return

        if self.keyword_context:
            return
        seeds = self.seed_builder.build()
        self.keyword_context = {seed.keyword: seed.to_context() for seed in seeds}

    @staticmethod
    def _handoff_lane_key(ctx: Dict[str, Any]) -> str:
        """Group a seed by the treatment axis and execution lens it should cover."""
        category = GYULIM_KEYWORD_PROFILE.normalize_category(str(ctx.get("category") or "unknown"))
        lens = str(ctx.get("execution_lens") or "service").strip().lower() or "service"
        return f"{category}::{lens}"

    def _order_keywords_for_handoff_coverage(
        self,
        keywords: List[str],
        *,
        boost_categories: Optional[Iterable[str]] = None,
        boost_lenses: Optional[Iterable[str]] = None,
    ) -> List[str]:
        """Round-robin keywords by Pathfinder handoff lane before applying run limits."""
        if len(keywords) <= 1:
            return list(keywords or [])

        boosted_categories = {
            GYULIM_KEYWORD_PROFILE.normalize_category(str(category or ""))
            for category in (boost_categories or [])
            if str(category or "").strip()
        }
        boosted_lenses = {
            str(lens or "").strip().lower()
            for lens in (boost_lenses or [])
            if str(lens or "").strip()
        }
        lanes: Dict[str, List[str]] = {}
        ranked_lanes: List[str] = []
        boosted_lane_keys: set[str] = set()
        missing_context = 0
        for keyword in keywords:
            ctx = self.keyword_context.get(keyword) or {}
            if not ctx:
                missing_context += 1
            lane_key = self._handoff_lane_key(ctx)
            category = GYULIM_KEYWORD_PROFILE.normalize_category(str(ctx.get("category") or "unknown"))
            lens = str(ctx.get("execution_lens") or "service").strip().lower() or "service"
            if lane_key not in lanes:
                lanes[lane_key] = []
                ranked_lanes.append(lane_key)
            if category in boosted_categories or lens in boosted_lenses:
                boosted_lane_keys.add(lane_key)
            lanes[lane_key].append(keyword)

        if len(ranked_lanes) <= 1 or missing_context == len(keywords):
            return list(keywords)

        if boosted_lane_keys:
            lane_order = {lane_key: idx for idx, lane_key in enumerate(ranked_lanes)}
            ranked_lanes.sort(key=lambda lane_key: (0 if lane_key in boosted_lane_keys else 1, lane_order[lane_key]))

        ordered: List[str] = []
        while len(ordered) < len(keywords):
            progressed = False
            for lane_key in ranked_lanes:
                bucket = lanes.get(lane_key) or []
                if not bucket:
                    continue
                ordered.append(bucket.pop(0))
                progressed = True
            if not progressed:
                break

        return ordered

    @staticmethod
    def _checkpoint_boost_categories(categories: Optional[Iterable[str]]) -> List[str]:
        return sorted(
            {
                GYULIM_KEYWORD_PROFILE.normalize_category(str(category or ""))
                for category in (categories or [])
                if str(category or "").strip()
            }
        )

    @staticmethod
    def _checkpoint_boost_lenses(lenses: Optional[Iterable[str]]) -> List[str]:
        return sorted(
            {
                str(lens or "").strip().lower()
                for lens in (lenses or [])
                if str(lens or "").strip()
            }
        )

    def _checkpoint_hash_for_run(
        self,
        keywords: List[str],
        *,
        max_per_platform: int,
        source_scan_run_id: Optional[int] = None,
        boost_categories: Optional[Iterable[str]] = None,
        boost_lenses: Optional[Iterable[str]] = None,
    ) -> str:
        """Hash the exact Pathfinder handoff execution signature for resume safety."""
        query_plans: List[Dict[str, Any]] = []
        for idx, keyword in enumerate(keywords):
            ctx = self._planning_context_for_keyword(keyword)
            category = GYULIM_KEYWORD_PROFILE.normalize_category(str(ctx.get("category") or "unknown"))
            lens = str(ctx.get("execution_lens") or "service").strip().lower() or "service"
            context_scan_id = int(ctx.get("scan_run_id") or source_scan_run_id or 0)
            for plan in self._search_queries_for_keyword(keyword, max_per_platform):
                query_plans.append({
                    "position": idx,
                    "keyword": keyword,
                    "query": str(plan.get("query") or keyword),
                    "variant": str(plan.get("variant") or "base"),
                    "category": category,
                    "execution_lens": lens,
                    "scan_run_id": context_scan_id,
                    "include_blog": bool(plan.get("include_blog")),
                    "platform_limits": dict(plan.get("platform_limits") or {}),
                })

        signature = {
            "version": 4,
            "max_per_platform": int(max_per_platform or 0),
            "source_scan_run_id": int(source_scan_run_id or 0),
            "boost_categories": self._checkpoint_boost_categories(boost_categories),
            "boost_lenses": self._checkpoint_boost_lenses(boost_lenses),
            "query_plans": query_plans,
        }
        raw = json.dumps(signature, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _context_float(ctx: Dict[str, Any], key: str, default: float = 0.0) -> float:
        try:
            return float(ctx.get(key, default) or default)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _context_list(ctx: Dict[str, Any], key: str, limit: int = 6) -> List[str]:
        values = ViralSeedBuilder._json_list(ctx.get(key))
        return list(dict.fromkeys(value for value in values if value))[:limit]

    @staticmethod
    def _pathfinder_candidate_insight_brief(
        ctx: Dict[str, Any],
        source_signals: List[str],
        quality_flags: List[str],
    ) -> str:
        """Compact why-this-seed-matters brief for per-target AI and audits."""
        category = str(ctx.get("category") or "").strip()
        lens = str(ctx.get("execution_lens") or "").strip().lower() or "service"
        parts = []
        if category:
            parts.append(f"axis={category}")
        parts.append(f"lens={lens}")
        if ViralHunter._context_float(ctx, "community_signal") >= 40.0:
            parts.append("community_demand")
        if ViralHunter._context_float(ctx, "conversion_signal") >= 35.0:
            parts.append("conversion_intent")
        if ViralHunter._context_float(ctx, "profile_action_signal") >= 45.0:
            parts.append("profile_action")
        if source_signals:
            parts.append("sources=" + ",".join(source_signals[:3]))
        if quality_flags:
            parts.append("flags=" + ",".join(quality_flags[:2]))
        return "; ".join(parts[:7])

    @staticmethod
    def _inferred_execution_lens_for_keyword(keyword: str, ctx: Optional[Dict[str, Any]] = None) -> str:
        """Infer an execution lens from the keyword when Pathfinder context is partial."""
        ctx = ctx or {}
        row = {
            "keyword": keyword,
            "category": ctx.get("category") or "",
            "review_intent_type": ctx.get("review_intent_type") or "none",
            "recommended_content_type": ctx.get("recommended_content_type") or "",
            "preferred_search_surface": ctx.get("preferred_search_surface") or "",
            "community_signal": ctx.get("community_signal") or 0,
            "conversion_signal": ctx.get("conversion_signal") or 0,
            "availability_intent_score": ctx.get("availability_intent_score") or 0,
            "payment_coverage_score": ctx.get("payment_coverage_score") or 0,
            "access_convenience_score": ctx.get("access_convenience_score") or 0,
            "source_signals_json": ctx.get("source_signals_json") or "[]",
        }
        return ViralSeedBuilder._keyword_execution_lens(row)

    def _planning_context_for_keyword(self, keyword: str) -> Dict[str, Any]:
        """Return usable query-planning context even for manual or legacy keywords."""
        ctx = dict(self.keyword_context.get(keyword) or {})
        category = canonical_category_for_keyword(keyword, str(ctx.get("category") or ""))
        if category not in {"", "기타"}:
            ctx["category"] = category

        execution_lens = str(ctx.get("execution_lens") or "").strip().lower()
        if execution_lens in {"", "service"}:
            inferred_lens = self._inferred_execution_lens_for_keyword(keyword, ctx)
            if inferred_lens and (inferred_lens != "service" or not execution_lens):
                ctx["execution_lens"] = inferred_lens

        if ctx:
            existing = self.keyword_context.get(keyword)
            if existing != ctx:
                self.keyword_context[keyword] = ctx
        return ctx

    def _search_plan_for_keyword(self, keyword: str, max_per_platform: int) -> Dict[str, Any]:
        """Tune discovery depth by Pathfinder execution signals without changing the public API."""
        base_limit = max(1, int(max_per_platform or 100))
        ctx = self._planning_context_for_keyword(keyword)
        category = GYULIM_KEYWORD_PROFILE.normalize_category(str(ctx.get("category") or ""))
        readiness = self._context_float(ctx, "viral_readiness_score")
        community = self._context_float(ctx, "community_signal")
        conversion = self._context_float(ctx, "conversion_signal")
        profile_action = self._context_float(ctx, "profile_action_signal")
        medical_risk = self._context_float(ctx, "medical_ad_risk_score")
        content_actionability = self._context_float(ctx, "content_actionability_score")
        preferred_surface = str(ctx.get("preferred_search_surface") or "")
        recommended_type = str(ctx.get("recommended_content_type") or "")
        review_intent_type = str(ctx.get("review_intent_type") or "none")
        execution_lens = str(ctx.get("execution_lens") or "")

        multiplier = 1.0
        if readiness >= 80.0 or community >= 60.0 or conversion >= 50.0 or profile_action >= 60.0:
            multiplier = 1.8
        elif readiness >= 60.0 or community >= 40.0 or conversion >= 35.0 or profile_action >= 35.0:
            multiplier = 1.35

        if medical_risk >= 70.0 or (0.0 < content_actionability < 45.0):
            multiplier = min(multiplier, 0.7)
        elif medical_risk >= 50.0:
            multiplier = min(multiplier, 1.0)

        expanded_limit = max(20, min(320, int(round(base_limit * multiplier))))
        conservative_limit = max(15, min(base_limit, int(round(base_limit * 0.65))))

        if medical_risk >= 70.0 or (0.0 < content_actionability < 45.0):
            limits = {
                "cafe": conservative_limit,
                "blog": max(10, int(round(conservative_limit * 0.5))),
                "kin": conservative_limit,
            }
            include_blog = recommended_type in {"faq_safety", "service_landing", "access_landing"}
        elif execution_lens in {"review", "community"} or community >= 40.0 or review_intent_type not in {"", "none"}:
            limits = {
                "cafe": expanded_limit,
                "blog": max(
                    20,
                    min(
                        expanded_limit,
                        int(round(base_limit * (0.65 if execution_lens in {"review", "community"} else 0.9))),
                    ),
                ),
                "kin": expanded_limit,
            }
            include_blog = True
        elif execution_lens in {"cost", "consultation", "availability", "safety"}:
            limits = {
                "cafe": expanded_limit,
                "blog": max(20, min(expanded_limit, int(round(base_limit * 0.65)))),
                "kin": expanded_limit,
            }
            include_blog = True
        elif preferred_surface in {"profile_action", "local_pack", "hybrid_local_content"}:
            limits = {
                "cafe": expanded_limit,
                "blog": max(20, min(expanded_limit, int(round(base_limit * 0.75)))),
                "kin": expanded_limit,
            }
            include_blog = True
        elif recommended_type in {"faq_safety", "service_landing", "access_landing"}:
            limits = {
                "cafe": max(base_limit, int(round(expanded_limit * 0.8))),
                "blog": expanded_limit,
                "kin": max(base_limit, int(round(expanded_limit * 0.8))),
            }
            include_blog = True
        else:
            limits = {"cafe": expanded_limit, "blog": base_limit, "kin": expanded_limit}
            include_blog = True

        if category in self.USER_SURFACE_HEAVY_CATEGORIES:
            # These axes are flooded by blog/provider SEO; cafe/Kin user questions are more workable.
            limits["blog"] = max(10, min(int(limits.get("blog", 0) or 0), int(round(base_limit * 0.35))))
            if execution_lens in {"review", "community", "consultation"} or review_intent_type not in {"", "none"}:
                user_surface_limit = max(20, min(240, int(round(base_limit * 1.5))))
                limits["cafe"] = max(int(limits.get("cafe", 0) or 0), user_surface_limit)
                limits["kin"] = max(int(limits.get("kin", 0) or 0), user_surface_limit)

        # 플랫폼 수율 게이트(증거 기반): 위의 카테고리/렌즈 튜닝 결과에 직원 수용률
        # 가중치를 곱한다. 카테고리 룰이 못 보는 플랫폼-단위 ROI 격차(blog 0.4% 등)를
        # 보정 — 카테고리 무관하게 적용되고, 바닥 limit가 탐사를 유지한다.
        limits = self._apply_platform_yield_factors(limits)

        return {
            "include_blog": include_blog,
            "platform_limits": limits,
            "readiness": readiness,
            "medical_risk": medical_risk,
            "preferred_surface": preferred_surface,
            "recommended_content_type": recommended_type,
            "execution_lens": execution_lens,
        }

    @staticmethod
    def _scaled_platform_limits(limits: Dict[str, int], factor: float, *, minimum: int = 10, maximum: int = 140) -> Dict[str, int]:
        scaled: Dict[str, int] = {}
        for platform, value in (limits or {}).items():
            limit = int(value or 0)
            scaled[platform] = 0 if limit <= 0 else max(minimum, min(maximum, int(round(limit * factor))))
        return scaled

    @staticmethod
    def _compact_query_text(text: str) -> str:
        return re.sub(r"\s+", "", (text or "").lower())

    def _load_variant_yield_history(self, max_runs: int = 12) -> Dict[str, Dict[str, int]]:
        """최근 viral_scan_audits 런들의 query-variant 수율을 합산해 캐시.

        전역 variant 수율과 category/lens/variant 수율을 함께 읽는다. 같은
        `cost_community:추천`이라도 흉터 cost와 체형 cost의 수율은 다를 수
        있으므로, 다음 런 게이트는 가능한 한 세분화된 증거를 먼저 쓴다.
        """
        cached = getattr(self, "_variant_yield_cache", None)
        if cached is not None:
            return cached
        history: Dict[str, Dict[str, int]] = {}
        rows = []
        try:
            import sqlite3 as _sql
            conn = _sql.connect(self.db.db_path)
            rows = conn.execute(
                "SELECT audit_json FROM viral_scan_audits ORDER BY id DESC LIMIT ?",
                (int(max_runs),),
            ).fetchall()
            conn.close()
        except Exception:
            rows = []
        for (audit_json,) in rows:
            try:
                audit = json.loads(audit_json or "{}")
            except (TypeError, ValueError):
                continue
            per_variant = audit.get("per_query_variant") if isinstance(audit, dict) else None
            if isinstance(per_variant, dict):
                for variant, entry in per_variant.items():
                    if not isinstance(entry, dict):
                        continue
                    bucket = history.setdefault(
                        str(variant),
                        {
                            "discovered": 0,
                            "fresh_discovered": 0,
                            "pending": 0,
                            "fresh_pending": 0,
                            "rediscovered": 0,
                            "rediscovered_pending": 0,
                            "ad_filtered": 0,
                            "runs": 0,
                        },
                    )
                    bucket["discovered"] += int(entry.get("discovered", 0) or 0)
                    bucket["fresh_discovered"] += int(entry.get("fresh_discovered", 0) or 0)
                    bucket["pending"] += int(entry.get("pending", 0) or 0)
                    bucket["fresh_pending"] += int(entry.get("fresh_pending", 0) or 0)
                    bucket["rediscovered"] += int(entry.get("rediscovered", 0) or 0)
                    bucket["rediscovered_pending"] += int(entry.get("rediscovered_pending", 0) or 0)
                    bucket["ad_filtered"] += int(entry.get("ad_filtered", 0) or 0)
                    if int(entry.get("discovered", 0) or 0) > 0:
                        bucket["runs"] += 1
            per_lane_variant = audit.get("per_category_lens_query_variant") if isinstance(audit, dict) else None
            if not isinstance(per_lane_variant, dict):
                continue
            for lane_variant, entry in per_lane_variant.items():
                if not isinstance(entry, dict):
                    continue
                bucket = history.setdefault(
                    f"category_lens_variant:{lane_variant}",
                    {
                        "discovered": 0,
                        "fresh_discovered": 0,
                        "pending": 0,
                        "fresh_pending": 0,
                        "rediscovered": 0,
                        "rediscovered_pending": 0,
                        "ad_filtered": 0,
                        "runs": 0,
                    },
                )
                bucket["discovered"] += int(entry.get("discovered", 0) or 0)
                bucket["fresh_discovered"] += int(entry.get("fresh_discovered", 0) or 0)
                bucket["pending"] += int(entry.get("pending", 0) or 0)
                bucket["fresh_pending"] += int(entry.get("fresh_pending", 0) or 0)
                bucket["rediscovered"] += int(entry.get("rediscovered", 0) or 0)
                bucket["rediscovered_pending"] += int(entry.get("rediscovered_pending", 0) or 0)
                bucket["ad_filtered"] += int(entry.get("ad_filtered", 0) or 0)
                if int(entry.get("discovered", 0) or 0) > 0:
                    bucket["runs"] += 1
        self._variant_yield_cache = history
        return history

    @staticmethod
    def _category_lens_variant_history_key(category: str, lens: str, variant: str) -> str:
        category_key = GYULIM_KEYWORD_PROFILE.normalize_category(str(category or ""))
        lens_key = str(lens or "service").strip().lower() or "service"
        variant_key = str(variant or "").strip()
        return f"category_lens_variant:{category_key}::{lens_key}::{variant_key}"

    @classmethod
    def _variant_gate_should_drop(
        cls,
        history: Dict[str, Dict[str, int]],
        *,
        category: str,
        lens: str,
        variant: str,
    ) -> bool:
        """동반 변형을 다음 런에서 보낼지(차단할지) 결정.

        granular한 per-(category,lens,variant) lane 증거를 우선하되, lane 버킷이
        아직 cold-start(pending==0 & 제로수율 미증명)일 때 누적 글로벌 증거를
        *버리지 않는다*. 그렇지 않으면 최근 도입된 lane 버킷이, 글로벌이 이미
        제로수율로 증명한 변형을 조용히 재활성화(un-gate)한다 — variant 수율
        게이트 전체를 무력화하는 회귀. base/community_base 기준 변형은 호출
        자체가 안 되므로(첫 슬롯 항상 유지) 여기서 다루지 않는다.
        """
        variant = str(variant or "")

        # patient_voice_kin은 진료축이 아니라 '질문 표면(지역어 제거 + KIN)' 자체가
        # 수율을 좌우하는 CATEGORY-AGNOSTIC 변형이다. per-(category,lens) lane으로
        # 쪼개면 증거가 사실상 누적되지 않으므로(여러 lens로 분산) 글로벌 누적으로
        # 판정한다. 2-run cold-start는 _variant_proven_zero_yield_for_gate가 유지.
        if variant == "patient_voice_kin":
            glob = history.get(variant)
            return bool(glob) and cls._variant_proven_zero_yield_for_gate(variant, glob)

        lane_key = cls._category_lens_variant_history_key(category, lens, variant)
        lane = history.get(lane_key)

        # 진짜 진료축-특정 질의 모양(axis ':specific_*')은 lane 증거로만 판정.
        if ":specific_" in variant:
            return bool(lane) and cls._variant_proven_zero_yield_for_gate(variant, lane)

        # 동반/렌즈 변형: granular lane 우선, 단 lane cold-start면 글로벌로 폴백.
        if lane:
            if cls._variant_proven_zero_yield_for_gate(variant, lane):
                return True  # lane이 제로수율 증명 → 차단
            if int(lane.get("pending", 0) or 0) > 0:
                return False  # lane이 실수율 보유 → 죽은 글로벌보다 우선 보존(심슨 역설 방어)
            # lane은 있으나 pending==0 & 제로수율 미증명(cold start) → 글로벌 폴백.
        glob = history.get(variant)
        return bool(glob) and cls._variant_proven_zero_yield_for_gate(variant, glob)

    @staticmethod
    def _variant_requires_lane_specific_yield(variant: str) -> bool:
        variant = str(variant or "").strip()
        return variant == "patient_voice_kin" or ":specific_" in variant

    @staticmethod
    def _variant_proven_zero_yield(stats: Dict[str, int]) -> bool:
        """충분한 누적 증거가 있고 pending 전환이 사실상 0인 변형만 True.

        보수적 임계 — 신생 변형의 탐사를 조기에 죽이지 않는다.
        """
        discovered = int(stats.get("discovered", 0) or 0)
        pending = int(stats.get("pending", 0) or 0)
        fresh_discovered = int(stats.get("fresh_discovered", 0) or 0)
        fresh_pending = int(stats.get("fresh_pending", 0) or 0)
        rediscovered = int(stats.get("rediscovered", 0) or 0)

        # A query variant that mostly re-finds old URLs is not a fresh hunting
        # surface, even if those old rows still sit in pending. Only apply this
        # when the audit has enough fresh evidence; older audits without the
        # fresh_* fields keep the legacy pending/discovered gate below.
        if fresh_discovered >= 60 and fresh_pending == 0:
            return True
        if fresh_discovered >= 150 and (fresh_pending / fresh_discovered) < 0.004:
            return True
        if (
            discovered >= 150
            and fresh_discovered >= 40
            and fresh_pending == 0
            and (rediscovered / discovered) >= 0.75
        ):
            return True

        if discovered >= 60 and pending == 0:
            return True
        if discovered >= 150 and (pending / discovered) < 0.004:
            return True
        return False

    @classmethod
    def _variant_proven_zero_yield_for_gate(cls, variant: str, stats: Dict[str, int]) -> bool:
        """Zero-yield gate with extra cold-start protection for exploratory variants."""
        if cls._variant_requires_lane_specific_yield(variant) and int(stats.get("runs", 0) or 0) < 2:
            return False
        return cls._variant_proven_zero_yield(stats)

    # 플랫폼별 staff 수용률 → 발견 예산 가중치. 변형 수율 게이트의 철학을
    # 플랫폼 단위로 확장: 직원이 실제로 작업하는 비율(posted/generated vs skipped)에
    # 발견 예산을 비례시킨다. 라이브 근거(2026-06-13): blog 0.4% vs kin 19.7%
    # 수용률인데 발견량은 blog가 최대(21일 9,536)·kin이 최소(7,841)로 역전.
    PLATFORM_YIELD_MIN_SAMPLE = 40   # 이 미만 staff 액션은 미개입(1.0)
    PLATFORM_YIELD_FLOOR_LIMIT = 12  # 가중 후에도 최소 이만큼은 탐사 (완전 블라인드 방지)

    @staticmethod
    def _acceptance_to_yield_factor(accept_rate: float) -> float:
        """staff 수용률을 발견 예산 가중치[0.2, 1.0]로 매핑 (증거 기반·바닥 보장)."""
        if accept_rate >= 0.15:
            return 1.0
        if accept_rate >= 0.08:
            return 0.85
        if accept_rate >= 0.04:
            return 0.6
        if accept_rate >= 0.015:
            return 0.35
        return 0.2

    def _load_platform_yield_factors(self) -> Dict[str, float]:
        """플랫폼별 staff 수용률로 발견 예산 가중치를 산출 (런 단위 캐시).

        수용률 = posted+generated / (posted+generated+skipped) — 직원에게 노출된
        타겟 중 실제 작업 비율. 표본<MIN_SAMPLE 플랫폼은 dict에서 제외(=미개입,
        1.0 취급). blog처럼 구조적으로 댓글 가치가 낮은 표면은 자동으로 바닥
        가중치로 수렴하고, 바닥 limit가 탐사를 유지해 갑자기 가치가 생기면
        수용률이 올라 가중치도 회복된다 (영구 사장 방지).
        """
        cached = getattr(self, "_platform_yield_cache", None)
        if cached is not None:
            return cached
        factors: Dict[str, float] = {}
        rows = []
        try:
            import sqlite3 as _sql
            conn = _sql.connect(self.db.db_path)
            rows = conn.execute(
                """
                SELECT LOWER(COALESCE(platform, '')) p,
                       SUM(CASE WHEN comment_status IN ('posted', 'generated') THEN 1 ELSE 0 END) good,
                       SUM(CASE WHEN comment_status = 'skipped' THEN 1 ELSE 0 END) skipped
                FROM viral_targets
                WHERE comment_status IN ('posted', 'generated', 'skipped')
                GROUP BY LOWER(COALESCE(platform, ''))
                """
            ).fetchall()
            conn.close()
        except Exception:
            rows = []
        for platform, good, skipped in rows:
            good = int(good or 0)
            skipped = int(skipped or 0)
            sample = good + skipped
            if not platform or sample < self.PLATFORM_YIELD_MIN_SAMPLE:
                continue
            factor = self._acceptance_to_yield_factor(good / sample)
            if factor < 1.0:
                factors[platform] = factor
        self._platform_yield_cache = factors
        return factors

    def _apply_platform_yield_factors(self, limits: Dict[str, int]) -> Dict[str, int]:
        """발견 예산에 플랫폼 수율 가중치를 적용. 차단량은 _platform_drop_counts에 집계."""
        factors = self._load_platform_yield_factors()
        if not factors:
            return limits
        drop_counts = getattr(self, "_platform_drop_counts", None)
        if drop_counts is None:
            drop_counts = {}
            self._platform_drop_counts = drop_counts
        for platform in list(limits.keys()):
            original = int(limits.get(platform, 0) or 0)
            factor = factors.get(platform)
            if not factor or original <= 0:
                continue
            scaled = max(self.PLATFORM_YIELD_FLOOR_LIMIT, int(round(original * factor)))
            scaled = min(original, scaled)
            if scaled < original:
                drop_counts[platform] = drop_counts.get(platform, 0) + (original - scaled)
                limits[platform] = scaled
        return limits

    def _patient_voice_kin_variant(
        self,
        keyword: str,
        category: str,
        core_query: str,
    ) -> Optional[Dict[str, Any]]:
        """지역 앵커 없는 환자 질문(지식인) 표면 탐사 변형.

        지식인 질문 대부분은 제목/검색 텍스트에 지역명이 없어 청주-앵커 쿼리로는
        구조적으로 잡히지 않는다. 사용자-표면 중심 축에 한해 지역 토큰을 제거한
        서비스 코어를 kin 위주로 1변형만 보낸다. 수율은 안정된 변형 이름
        (patient_voice_kin)으로 측정되며, 제로수율이 증명되면 변형 수율 게이트가
        자동으로 끈다.
        """
        if category not in self.USER_SURFACE_HEAVY_CATEGORIES:
            return None
        stripped = strip_region_tokens(core_query)
        if not stripped or len(self._compact_query_text(stripped)) < 4:
            return None
        if self._compact_query_text(stripped) == self._compact_query_text(core_query):
            return None  # 지역 토큰이 없던 시드 — 이미 비지역 쿼리라 중복
        return {
            "query": stripped,
            "variant": "patient_voice_kin",
            "source_keyword": keyword,
            "surface_override": {"cafe": 15, "blog": 0, "kin": 40},
        }

    AXIS_COMPANION_GENERIC_TERMS = PATHFINDER_AXIS_COMPANION_GENERIC_TERMS
    AXIS_COMPANION_VARIANT_PREFIX = PATHFINDER_AXIS_COMPANION_VARIANT_PREFIX

    @staticmethod
    def _axis_specific_terms_for_keyword(keyword: str, category: str, limit: int = 2) -> List[str]:
        """Return specific treatment/context terms from the active Pathfinder profile.

        Fixed companion queries cover the canonical axis. This keeps newer Pathfinder
        discoveries such as 수술흉터, 켈로이드, 아토피, 산후, 라운드숄더, 팔자주름 from
        being collapsed back to a generic category companion.
        """
        return _pathfinder_axis_specific_terms_for_keyword(keyword, category, limit=limit)

    @staticmethod
    def _axis_specific_companion_query(keyword: str, category: str, term: str) -> str:
        term = re.sub(r"\s+", " ", str(term or "").strip())
        compact_keyword = ViralHunter._compact_query_text(keyword)
        if not term:
            return ""

        if category == "흉터/여드름흉터":
            service = term
            if "새살침" in compact_keyword and "새살침" not in ViralHunter._compact_query_text(term):
                service = f"{term} 새살침"
            elif "한의원" not in ViralHunter._compact_query_text(term):
                service = f"{term} 한의원"
            return f"청주 {service} 후기"

        if category == "피부/여드름":
            service = term if "한의원" in ViralHunter._compact_query_text(term) else f"{term} 한의원"
            return f"청주 {service} 후기"

        if category == "다이어트":
            if "식욕" in term:
                service = f"{term} 한약"
            elif "다이어트" in term:
                service = term
            else:
                service = f"{term} 다이어트 한약"
            return f"청주 {service} 후기"

        if category == "안면비대칭":
            if "턱관절" in term:
                service = f"{term} 안면비대칭 한의원"
            elif "교정" in term:
                service = f"{term} 한의원"
            else:
                service = f"{term} 안면비대칭 한의원"
            return f"청주 {service} 추천"

        if category == "체형교정":
            service = term if "한의원" in ViralHunter._compact_query_text(term) else f"{term} 추나 한의원"
            return f"청주 {service} 추천"

        if category == "리프팅/탄력":
            if "리프팅" in term:
                service = term
            else:
                service = f"{term} 한방리프팅"
            return f"청주 {service} 후기"

        if category == "교통사고":
            compact_term = ViralHunter._compact_query_text(term)
            if compact_term in {"입원", "입원가능한"}:
                service = "교통사고 입원 한의원"
            elif compact_term in {"자보", "자동차보험"}:
                service = "교통사고 자동차보험 한의원"
            elif "후유증" in compact_term:
                service = "교통사고 후유증 한의원"
            elif "합의" in compact_term:
                service = "교통사고 합의전 한의원"
            elif compact_term in {"목통증", "허리통증", "두통"}:
                service = f"교통사고 {term} 한의원"
            else:
                service = f"교통사고 {term} 한의원"
            return f"청주 {service} 추천"

        return f"청주 {term} 한의원 추천"

    @staticmethod
    def _dynamic_axis_companion_query_variants(keyword: str, category: str) -> List[Dict[str, Any]]:
        prefix = ViralHunter.AXIS_COMPANION_VARIANT_PREFIX.get(category)
        if not prefix:
            return []
        variants: List[Dict[str, Any]] = []
        for term in ViralHunter._axis_specific_terms_for_keyword(keyword, category):
            query = ViralHunter._axis_specific_companion_query(keyword, category, term)
            query_compact = ViralHunter._compact_query_text(query)
            if not query_compact:
                continue
            term_key = re.sub(r"\s+", "", term)
            variants.append({
                "query": query,
                "variant": f"{prefix}:specific_{term_key}",
                "source_keyword": keyword,
            })
        return variants

    def _search_query_variants_for_keyword(self, keyword: str) -> List[Dict[str, Any]]:
        """Create a bounded set of lens-aware search queries for one Pathfinder seed."""
        ctx = self._planning_context_for_keyword(keyword)
        execution_lens = str(ctx.get("execution_lens") or "")
        category = GYULIM_KEYWORD_PROFILE.normalize_category(str(ctx.get("category") or ""))

        # Live scan evidence (14d window): transactional-suffix queries (예약/비용/
        # 상담 가능한곳 등) surfaced 51% advertorial supply with 0.3% pending yield,
        # while the same service cores in plain form converted at plain-seed rates.
        # The suffix keeps driving lens scoring and lineage; only the search surface
        # sent to Naver changes.
        core_query = strip_transactional_suffix(keyword)
        base_variant = "community_base" if core_query != keyword else "base"
        compact = self._compact_query_text(core_query)
        variants: List[Dict[str, Any]] = [{"query": core_query, "variant": base_variant, "source_keyword": keyword}]

        # Decision lenses (cost/consultation/availability/safety) probe the community
        # surface too: their literal companions (비용/예약/상담/부작용) measured 0~0.5%
        # pending vs 4.5~31.7% for 추천-style companions in the same scans.
        lens_terms = {
            "review": ("추천", "후기", "어디"),
            "community": ("추천", "후기", "어디"),
            "cost": ("추천", "후기"),
            "consultation": ("추천", "어디"),
            "availability": ("추천", "어디"),
            "safety": ("후기", "추천"),
        }
        community_lens_labels = {
            "cost": "cost_community",
            "consultation": "consultation_community",
            "availability": "availability_community",
            "safety": "safety_community",
        }
        terms = lens_terms.get(execution_lens, ())
        lens_label = community_lens_labels.get(execution_lens, execution_lens or "conversion")
        if not terms and float(ctx.get("conversion_signal") or 0.0) >= 55.0:
            terms = ("추천",)
            lens_label = "conversion_community"

        if not any(self._compact_query_text(term) in compact for term in terms):
            for term in terms:
                term_compact = self._compact_query_text(term)
                if term_compact and term_compact not in compact:
                    variants.append({
                        "query": f"{core_query} {term}",
                        "variant": f"{lens_label}:{term}",
                        "source_keyword": keyword,
                    })
                    break

        max_variants = 3 if category in self.AXIS_COMPANION_EXPANDED_CATEGORIES else 2
        for variant in self._axis_companion_query_variants(keyword, category):
            if len(variants) >= max_variants:
                break
            query_compact = self._compact_query_text(variant["query"])
            if query_compact and all(query_compact != self._compact_query_text(item["query"]) for item in variants):
                variants.append(variant)
        variants = variants[:max_variants]

        # 비지역 환자 질문 표면은 별도 +1 슬롯 — kin 위주 한정 예산이라 SERP 비용이 작다.
        patient_voice = self._patient_voice_kin_variant(keyword, category, core_query)
        if patient_voice is not None:
            pv_compact = self._compact_query_text(patient_voice["query"])
            if pv_compact and all(pv_compact != self._compact_query_text(item["query"]) for item in variants):
                variants.append(patient_voice)

        # 의미기반 발견 2단계: 구어/패러프레이즈 쿼리 +1 슬롯(opt-in). Naver 가 임상어 없는
        # 구어 환자글을 반환하도록 넓힌다. 변형 yield 게이트가 자기조절하므로 무수율 표현은
        # 다음 런부터 자동 폐기된다(매칭측 의미 구제와 시너지 — 끌어온 구어글이 어휘 게이트에
        # 다시 안 잘린다).
        if semantic_discovery_enabled():
            for colloquial in self._colloquial_query_variants(keyword, category, core_query):
                cq_compact = self._compact_query_text(colloquial["query"])
                if cq_compact and all(cq_compact != self._compact_query_text(item["query"]) for item in variants):
                    variants.append(colloquial)

        # 변형 수율 게이트 — 누적 증거로 제로수율이 증명된 동반 변형은 보내지 않는다.
        # 기준(base/community_base) 변형은 절대 끄지 않는다.
        history = self._load_variant_yield_history()
        if history and len(variants) > 1:
            kept = [variants[0]]
            for variant in variants[1:]:
                name = str(variant.get("variant") or "")
                if self._variant_gate_should_drop(
                    history,
                    category=category,
                    lens=execution_lens,
                    variant=name,
                ):
                    drop_counts = getattr(self, "_variant_drop_counts", None)
                    if drop_counts is None:
                        drop_counts = {}
                        self._variant_drop_counts = drop_counts
                    drop_counts[name] = drop_counts.get(name, 0) + 1
                    continue
                kept.append(variant)
            variants = kept

        return variants

    @staticmethod
    def _context_rank_value(ctx: Dict[str, Any]) -> Tuple[float, float, float, float, float]:
        """Rank Pathfinder contexts when multiple seeds produce the same query variant."""
        def num(key: str) -> float:
            try:
                return float((ctx or {}).get(key) or 0.0)
            except (TypeError, ValueError):
                return 0.0

        return (
            num("priority_v3"),
            num("viral_readiness_score"),
            num("content_actionability_score"),
            num("local_service_fit_score"),
            num("community_signal") + num("conversion_signal") + num("profile_action_signal"),
        )

    @staticmethod
    def _context_lineage_values(ctx: Dict[str, Any], list_key: str, single_key: str) -> List[str]:
        values: List[str] = []
        raw_list = (ctx or {}).get(list_key)
        if isinstance(raw_list, list):
            values.extend(str(item) for item in raw_list if str(item or "").strip())
        elif raw_list:
            values.append(str(raw_list))
        raw_single = (ctx or {}).get(single_key)
        if raw_single:
            values.append(str(raw_single))
        return [value for value in dict.fromkeys(values) if value]

    def _register_variant_keyword_context(
        self,
        *,
        source_keyword: str,
        query: str,
        query_variant: str,
    ) -> None:
        """Store variant query context without losing stronger source-seed lineage."""
        if not query or query == source_keyword or source_keyword not in self.keyword_context:
            return

        new_context = dict(self.keyword_context[source_keyword])
        new_context["pathfinder_source_keyword"] = source_keyword
        new_context["pathfinder_query_variant"] = query_variant
        existing = self.keyword_context.get(query)

        if not isinstance(existing, dict):
            new_context["pathfinder_source_keywords"] = [source_keyword]
            new_context["pathfinder_query_variants"] = [query_variant]
            new_context["pathfinder_context_collision_count"] = 1
            self.keyword_context[query] = new_context
            return

        sources = list(dict.fromkeys(
            self._context_lineage_values(existing, "pathfinder_source_keywords", "pathfinder_source_keyword")
            + [source_keyword]
        ))
        variants = list(dict.fromkeys(
            self._context_lineage_values(existing, "pathfinder_query_variants", "pathfinder_query_variant")
            + [query_variant]
        ))
        prefer_new = self._context_rank_value(new_context) > self._context_rank_value(existing)
        merged = {**existing, **new_context} if prefer_new else dict(existing)
        merged["pathfinder_source_keywords"] = sources
        merged["pathfinder_query_variants"] = variants
        merged["pathfinder_context_collision_count"] = len(sources)
        if prefer_new:
            merged["pathfinder_source_keyword"] = source_keyword
            merged["pathfinder_query_variant"] = query_variant
        self.keyword_context[query] = merged

    @staticmethod
    def _colloquial_query_variants(keyword: str, category: str, core_query: str) -> List[Dict[str, Any]]:
        """구어/패러프레이즈 환자 표현으로 1개 지역 앵커 쿼리 생성(의미기반 발견 2단계).

        시드별로 구어 표현을 순환 선택 → 시드 포트폴리오 전체에서 모든 구어 변형을 커버하되
        시드당 +1 쿼리로 비용을 묶는다. 반환 변형은 `colloquial:` 로 명명돼 변형 yield
        게이트가 추적/자기조절한다(무수율 시 폐기). 진료축에 구어 어휘가 없으면 빈 리스트.
        """
        terms = ViralHunter.COLLOQUIAL_AXIS_TERMS.get(category)
        if not terms:
            return []
        region = str(getattr(GYULIM_KEYWORD_PROFILE, "primary_region", "청주") or "청주").strip()
        core_compact = ViralHunter._compact_query_text(core_query)
        # 결정적 시드 회전(파이썬 hash 는 런마다 솔트되므로 안정적 합 사용).
        rotate = sum(ord(ch) for ch in (keyword or ""))
        n = len(terms)
        for i in range(n):
            term = terms[(rotate + i) % n]
            term_compact = ViralHunter._compact_query_text(term)
            if not term_compact or term_compact in core_compact:
                continue
            query = f"{region} {term}".strip() if region else term
            return [{
                "query": query,
                "variant": f"colloquial:{term.replace(' ', '')}",
                "source_keyword": keyword,
            }]
        return []

    @staticmethod
    def _axis_companion_query_variants(keyword: str, category: str) -> List[Dict[str, Any]]:
        """Add one axis-specific user-question query for categories with thin organic supply."""
        compact = ViralHunter._compact_query_text(keyword)
        candidates: List[Tuple[str, str]] = []
        if category == "흉터/여드름흉터":
            candidates = [
                ("청주 여드름흉터 새살침 후기", "axis_scar:새살침후기"),
                ("청주 패인흉터 한의원 추천", "axis_scar:패인흉터추천"),
                ("청주 여드름자국 흉터 한의원 추천", "axis_scar:여드름자국추천"),
            ]
        elif category == "피부/여드름":
            candidates = [
                ("청주 여드름 한의원 추천", "axis_skin:여드름추천"),
                ("청주 피부질환 한의원 추천", "axis_skin:피부질환추천"),
                ("청주 아토피 한의원 후기", "axis_skin:아토피후기"),
            ]
        elif category == "다이어트":
            candidates = [
                ("청주 다이어트한약 후기", "axis_diet:한약후기"),
                ("청주 한방다이어트 한의원 추천", "axis_diet:한방다이어트추천"),
                ("청주 감량 한약 상담 후기", "axis_diet:감량상담후기"),
            ]
        elif category == "체형교정":
            candidates = [
                ("청주 체형교정 추나 한의원 추천", "axis_body:체형추나추천"),
                ("청주 골반교정 추나 한의원 추천", "axis_body:골반교정추천"),
                ("청주 거북목 일자목 한의원 추천", "axis_body:거북목추천"),
            ]
        elif category == "안면비대칭":
            candidates = [
                ("청주 턱관절 안면비대칭 한의원 추천", "axis_asymmetry:턱관절비대칭추천"),
                ("청주 안면비대칭 교정 한의원 추천", "axis_asymmetry:교정추천"),
            ]
        elif category == "리프팅/탄력":
            candidates = [
                ("청주 매선 한방리프팅 후기", "axis_lifting:매선한방후기"),
                ("청주 팔자주름 한방리프팅 후기", "axis_lifting:팔자주름후기"),
                ("청주 피부탄력 매선 리프팅 후기", "axis_lifting:피부탄력매선후기"),
            ]
        elif category == "교통사고":
            candidates = [
                ("청주 교통사고 후유증 한의원 추천", "axis_traffic:후유증추천"),
                ("청주 교통사고 입원 한의원 추천", "axis_traffic:입원추천"),
                ("청주 자동차보험 한의원 상담", "axis_traffic:자동차보험상담"),
            ]

        variants: List[Dict[str, Any]] = []
        for dynamic_variant in ViralHunter._dynamic_axis_companion_query_variants(keyword, category):
            query_compact = ViralHunter._compact_query_text(str(dynamic_variant.get("query") or ""))
            if query_compact and query_compact != compact:
                variants.append(dynamic_variant)
        for query, variant_name in candidates:
            query_compact = ViralHunter._compact_query_text(query)
            if query_compact and query_compact != compact:
                variants.append({
                    "query": query,
                    "variant": variant_name,
                    "source_keyword": keyword,
                })
        return variants

    def _search_queries_for_keyword(self, keyword: str, max_per_platform: int) -> List[Dict[str, Any]]:
        """Return query plans for a seed while preserving its Pathfinder lineage."""
        base_plan = self._search_plan_for_keyword(keyword, max_per_platform)
        variants = self._search_query_variants_for_keyword(keyword)
        plans: List[Dict[str, Any]] = []

        for idx, variant in enumerate(variants):
            plan = dict(base_plan)
            plan.update(variant)
            if idx > 0:
                surface_override = variant.get("surface_override")
                if surface_override:
                    # kin 전용 등 표면 지정 변형은 비율 스케일 대신 고정 한도를 쓴다.
                    plan["platform_limits"] = dict(surface_override)
                else:
                    plan["platform_limits"] = self._scaled_platform_limits(
                        base_plan.get("platform_limits") or {},
                        0.45,
                    )
                plan["query_variant_of"] = keyword
            self._register_variant_keyword_context(
                source_keyword=keyword,
                query=variant["query"],
                query_variant=variant["variant"],
            )
            plans.append(plan)

        return plans

    @staticmethod
    def _attach_search_query_lineage(
        target: ViralTarget,
        *,
        source_keyword: str,
        search_query: str,
        query_variant: str,
    ) -> ViralTarget:
        lineage_keywords = [source_keyword]
        if search_query and search_query != source_keyword:
            lineage_keywords.append(search_query)
        target.matched_keywords = [
            keyword
            for keyword in dict.fromkeys(lineage_keywords + list(target.matched_keywords or []))
            if keyword
        ]
        target.score_breakdown = {
            **(target.score_breakdown or {}),
            "pathfinder_source_keyword": source_keyword or "",
            "pathfinder_search_query": search_query or "",
            "pathfinder_query_variant": query_variant or "base",
        }
        return target

    @staticmethod
    def _pathfinder_variant_strength(variant: str) -> int:
        variant = str(variant or "").strip()
        if ":specific_" in variant:
            return 55
        if variant.startswith("axis_"):
            return 45
        if variant and variant not in {"base", "community_base", "(none)"}:
            return 30
        if variant == "community_base":
            return 20
        if variant == "base":
            return 10
        return 0

    @staticmethod
    def _breakdown_lineage_values(
        breakdown: Dict[str, Any],
        list_key: str,
        single_key: str,
    ) -> List[str]:
        values: List[str] = []
        raw_list = (breakdown or {}).get(list_key)
        if isinstance(raw_list, list):
            values.extend(str(item) for item in raw_list if str(item or "").strip())
        elif raw_list:
            values.append(str(raw_list))
        raw_single = (breakdown or {}).get(single_key)
        if raw_single:
            values.append(str(raw_single))
        return [item for item in dict.fromkeys(values) if item]

    @classmethod
    def _merge_duplicate_search_target(
        cls,
        current: ViralTarget,
        incoming: ViralTarget,
    ) -> ViralTarget:
        """Merge an in-run duplicate URL without losing query-variant lineage."""
        current_breakdown = current.score_breakdown or {}
        incoming_breakdown = incoming.score_breakdown or {}
        current_variant = str(current_breakdown.get("pathfinder_query_variant") or "base")
        incoming_variant = str(incoming_breakdown.get("pathfinder_query_variant") or "base")
        current_strength = cls._pathfinder_variant_strength(current_variant)
        incoming_strength = cls._pathfinder_variant_strength(incoming_variant)
        prefer_incoming = (
            incoming_strength > current_strength
            or (
                incoming_strength == current_strength
                and (incoming.exposure_score or incoming.priority_score or 0)
                > (current.exposure_score or current.priority_score or 0)
            )
        )
        preferred_breakdown = incoming_breakdown if prefer_incoming else current_breakdown

        variants = list(dict.fromkeys(
            cls._breakdown_lineage_values(current_breakdown, "pathfinder_query_variants", "pathfinder_query_variant")
            + cls._breakdown_lineage_values(incoming_breakdown, "pathfinder_query_variants", "pathfinder_query_variant")
        ))
        queries = list(dict.fromkeys(
            cls._breakdown_lineage_values(current_breakdown, "pathfinder_search_queries", "pathfinder_search_query")
            + cls._breakdown_lineage_values(incoming_breakdown, "pathfinder_search_queries", "pathfinder_search_query")
        ))
        sources = list(dict.fromkeys(
            cls._breakdown_lineage_values(current_breakdown, "pathfinder_source_keywords", "pathfinder_source_keyword")
            + cls._breakdown_lineage_values(incoming_breakdown, "pathfinder_source_keywords", "pathfinder_source_keyword")
        ))

        primary_source = str(preferred_breakdown.get("pathfinder_source_keyword") or "")
        primary_query = str(preferred_breakdown.get("pathfinder_search_query") or "")
        primary_keywords = [primary_source]
        if primary_query and primary_query != primary_source:
            primary_keywords.append(primary_query)
        current.matched_keywords = [
            keyword
            for keyword in dict.fromkeys(
                primary_keywords + list(current.matched_keywords or []) + list(incoming.matched_keywords or [])
            )
            if keyword
        ]

        appearances = list(dict.fromkeys((current.sort_appearances or []) + (incoming.sort_appearances or [])))
        current.sort_appearances = appearances
        best_rank = min(
            [rank for rank in (current.search_rank or 0, incoming.search_rank or 0) if rank > 0],
            default=current.search_rank or incoming.search_rank or 0,
        )
        current.search_rank = best_rank
        current.exposure_score = max(current.exposure_score or 0, incoming.exposure_score or 0)
        current.priority_score = max(current.priority_score or 0, incoming.priority_score or 0)
        current.like_count = max(current.like_count or 0, incoming.like_count or 0)
        current.comment_count = max(current.comment_count or 0, incoming.comment_count or 0)
        current.view_count = max(current.view_count or 0, incoming.view_count or 0)
        current.search_total = max(current.search_total or 0, incoming.search_total or 0)
        if prefer_incoming:
            current.title = incoming.title or current.title
            current.content_preview = incoming.content_preview or current.content_preview
            current.search_sort = incoming.search_sort or current.search_sort
            current.search_start = incoming.search_start or current.search_start
            current.author = incoming.author or current.author
            current.date_str = incoming.date_str or current.date_str

        merged_breakdown = {**current_breakdown, **incoming_breakdown}
        if not prefer_incoming:
            for key in ("pathfinder_source_keyword", "pathfinder_search_query", "pathfinder_query_variant"):
                if key in current_breakdown:
                    merged_breakdown[key] = current_breakdown[key]
        for key in ("pathfinder_source_keyword", "pathfinder_search_query", "pathfinder_query_variant"):
            if key in preferred_breakdown:
                merged_breakdown[key] = preferred_breakdown[key]
        merged_breakdown["pathfinder_query_variants"] = variants
        merged_breakdown["pathfinder_search_queries"] = queries
        merged_breakdown["pathfinder_source_keywords"] = sources
        merged_breakdown["pathfinder_duplicate_query_count"] = len(variants)
        current.score_breakdown = merged_breakdown
        return current

    def _apply_keyword_context(self, target: ViralTarget) -> ViralTarget:
        """Attach Pathfinder lineage to a search result before filtering/storage."""
        if not target.matched_keywords:
            return target

        ctx = None
        source_keyword = ""
        for keyword in target.matched_keywords:
            ctx = self.keyword_context.get(keyword)
            if ctx:
                source_keyword = keyword
                break
        if not ctx:
            if hasattr(self, "seed_builder") and self.seed_builder:
                self.keyword_context.update(self.seed_builder.keyword_context_for(target.matched_keywords))
            for keyword in target.matched_keywords:
                ctx = self.keyword_context.get(keyword)
                if ctx:
                    source_keyword = keyword
                    break
        if not ctx:
            for keyword in target.matched_keywords:
                ctx = self._planning_context_for_keyword(keyword)
                if ctx:
                    source_keyword = keyword
                    break
        if not ctx:
            return target
        context_keyword = source_keyword or (target.matched_keywords[0] if target.matched_keywords else "")
        context_source_keyword = str(ctx.get("pathfinder_source_keyword") or "").strip()
        source_keyword = context_source_keyword or context_keyword
        if source_keyword and source_keyword not in (target.matched_keywords or []):
            target.matched_keywords = [
                keyword
                for keyword in dict.fromkeys([source_keyword] + list(target.matched_keywords or []))
                if keyword
            ]
        source_signals = self._context_list(ctx, "source_signals_json")
        quality_flags = self._context_list(ctx, "quality_flags_json")
        insight_brief = self._pathfinder_candidate_insight_brief(ctx, source_signals, quality_flags)
        existing_breakdown = target.score_breakdown or {}
        target.source_scan_run_id = int(ctx.get("scan_run_id") or 0)
        target.matched_keyword_grade = ctx.get("grade") or ""
        target.matched_keyword_kei = float(ctx.get("kei") or 0)
        target.matched_keyword_priority = float(ctx.get("priority_v3") or 0)
        target.matched_keyword_category = canonical_category_for_keyword(
            source_keyword,
            ctx.get("category") or "",
        )
        current_category = GYULIM_KEYWORD_PROFILE.normalize_category(target.category or "")
        canonical_target_category = canonical_category_for_keyword(
            source_keyword,
            current_category,
        )
        if (
            target.matched_keyword_category
            and (
                not target.category
                or current_category in {"기타", "한의원일반"}
                or canonical_target_category == target.matched_keyword_category
                or not GYULIM_KEYWORD_PROFILE.profile_for(current_category)
            )
        ):
            target.category = target.matched_keyword_category
        target.score_breakdown = {
            **existing_breakdown,
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_context_keyword": context_keyword,
            "pathfinder_search_query": (
                existing_breakdown.get("pathfinder_search_query")
                or (context_keyword if context_keyword != source_keyword else "")
            ),
            "pathfinder_query_variant": (
                existing_breakdown.get("pathfinder_query_variant")
                or ctx.get("pathfinder_query_variant")
                or ""
            ),
            "pathfinder_viral_readiness_score": float(ctx.get("viral_readiness_score") or 0),
            "pathfinder_local_service_fit_score": float(ctx.get("local_service_fit_score") or 0),
            "pathfinder_content_actionability_score": float(ctx.get("content_actionability_score") or 0),
            "pathfinder_medical_ad_risk_score": float(ctx.get("medical_ad_risk_score") or 0),
            "pathfinder_community_signal": float(ctx.get("community_signal") or 0),
            "pathfinder_conversion_signal": float(ctx.get("conversion_signal") or 0),
            "pathfinder_profile_action_signal": float(ctx.get("profile_action_signal") or 0),
            "pathfinder_availability_intent_score": float(ctx.get("availability_intent_score") or 0),
            "pathfinder_payment_coverage_score": float(ctx.get("payment_coverage_score") or 0),
            "pathfinder_access_convenience_score": float(ctx.get("access_convenience_score") or 0),
            "pathfinder_preferred_search_surface": ctx.get("preferred_search_surface") or "",
            "pathfinder_recommended_content_type": ctx.get("recommended_content_type") or "",
            "pathfinder_brand_intent_type": ctx.get("brand_intent_type") or "generic",
            "pathfinder_review_intent_type": ctx.get("review_intent_type") or "none",
            "pathfinder_execution_lens": ctx.get("execution_lens") or "",
            "pathfinder_source_signals": source_signals,
            "pathfinder_quality_flags": quality_flags,
            "pathfinder_insight_brief": insight_brief,
            "pathfinder_staff_reviewed_count": int(ctx.get("historical_staff_reviewed_count") or 0),
            "pathfinder_staff_accept_rate": float(ctx.get("historical_staff_accept_rate") or 0.0),
            "pathfinder_staff_outcome_adjustment": float(ctx.get("staff_outcome_adjustment") or 0.0),
        }
        return target

    # ── 체크포인트 유틸 ────────────────────────────────────────────────

    def _checkpoint_path(self) -> str:
        return os.path.join(self.cfg.root_dir, 'db', 'viral_hunter_checkpoint.json')

    def _save_checkpoint(self, keywords_hash: str, processed: List[str],
                         all_targets: List[ViralTarget], seen_urls: set):
        """체크포인트 저장 (raw 검색 결과 + 진행 상태)."""
        try:
            data = {
                'keywords_hash': keywords_hash,
                'total_keywords': len(processed) if processed else 0,
                'processed_keywords': processed,
                'seen_urls': list(seen_urls),
                'all_targets': [t.to_dict() for t in all_targets],
                'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            }
            atomic_write_json(self._checkpoint_path(), data, indent=None)
        except Exception as e:
            logger.warning(f"체크포인트 저장 실패: {e}")

    def _load_checkpoint(self, keywords_hash: str) -> Optional[dict]:
        """동일 키워드 세트의 체크포인트 로드, 없으면 None."""
        path = self._checkpoint_path()
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('keywords_hash') != keywords_hash:
                logger.info(f"체크포인트 키워드 세트 불일치 → 무시")
                return None
            return data
        except Exception as e:
            logger.warning(f"체크포인트 로드 실패: {e}")
            return None

    def _clear_checkpoint(self):
        path = self._checkpoint_path()
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                logger.warning(f"체크포인트 삭제 실패: {e}")

    @staticmethod
    def _viral_target_from_dict(d: dict) -> ViralTarget:
        """체크포인트 복원용. to_dict()의 'id'는 property이므로 제외."""
        return ViralTarget(
            platform=d.get('platform', ''),
            url=d.get('url', ''),
            title=d.get('title', ''),
            content_preview=d.get('content_preview', ''),
            matched_keywords=d.get('matched_keywords') or [],
            category=d.get('category', '기타'),
            is_commentable=d.get('is_commentable', True),
            generated_comment=d.get('generated_comment', ''),
            priority_score=d.get('priority_score', 0.0),
            author=d.get('author', ''),
            date_str=d.get('date_str', ''),
            comment_status=d.get('comment_status', 'pending') or 'pending',
            discovered_at=d.get('discovered_at', '') or '',
            first_seen_at=d.get('first_seen_at', '') or '',
            last_scanned_at=d.get('last_scanned_at', '') or '',
            scan_count=d.get('scan_count', 0) or 0,
            source_scan_run_id=d.get('source_scan_run_id', 0) or 0,
            matched_keyword_grade=d.get('matched_keyword_grade', '') or '',
            matched_keyword_kei=d.get('matched_keyword_kei', 0.0) or 0.0,
            matched_keyword_priority=d.get('matched_keyword_priority', 0.0) or 0.0,
            matched_keyword_category=d.get('matched_keyword_category', '') or '',
            like_count=d.get('like_count', 0) or 0,
            comment_count=d.get('comment_count', 0) or 0,
            view_count=d.get('view_count', 0) or 0,
            exposure_score=d.get('exposure_score', 0.0) or 0.0,
            workability_score=d.get('workability_score', 0.0) or 0.0,
            conversion_fit_score=d.get('conversion_fit_score', 0.0) or 0.0,
            score_breakdown=d.get('score_breakdown') or {},
            search_sort=d.get('search_sort', '') or '',
            search_rank=d.get('search_rank', 0) or 0,
            search_start=d.get('search_start', 0) or 0,
            search_total=d.get('search_total', 0) or 0,
            sort_appearances=d.get('sort_appearances') or [],
            ai_reviewed=bool(d.get('ai_reviewed', False)),
            ai_infiltration_score=d.get('ai_infiltration_score', 0.0) or 0.0,
            ai_post_type=d.get('ai_post_type', '') or '',
            ai_competitor=bool(d.get('ai_competitor', False)),
            ai_competitor_name=d.get('ai_competitor_name', '') or '',
        )

    @staticmethod
    def _viral_target_from_db_row(row) -> ViralTarget:
        """DB row를 리포팅/체크포인트 복원용 ViralTarget으로 변환."""
        matched_keywords = row["matched_keywords"] or "[]"
        if isinstance(matched_keywords, str):
            try:
                matched_keywords = json.loads(matched_keywords)
            except Exception:
                matched_keywords = []

        row_keys = set(row.keys()) if hasattr(row, "keys") else set()

        def row_value(key: str, default=None):
            return row[key] if key in row_keys else default

        def row_json(key: str, default):
            value = row_value(key, default)
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except Exception:
                    return default
            return value if value is not None else default

        return ViralTarget(
            platform=row["platform"] or "",
            url=row["url"] or "",
            title=row["title"] or "",
            content_preview=row["content_preview"] or "",
            matched_keywords=matched_keywords or [],
            category=row["category"] or "기타",
            is_commentable=bool(row["is_commentable"]),
            generated_comment=row["generated_comment"] or "",
            priority_score=row["priority_score"] or 0.0,
            author=row["author"] or "",
            date_str=row["posted_at"] or "",
            comment_status=row["comment_status"] or "pending",
            discovered_at=row_value("discovered_at", "") or "",
            first_seen_at=row_value("first_seen_at", "") or "",
            last_scanned_at=row_value("last_scanned_at", "") or "",
            scan_count=row_value("scan_count", 0) or 0,
            source_scan_run_id=row["source_scan_run_id"] or 0,
            matched_keyword_grade=row["matched_keyword_grade"] or "",
            matched_keyword_kei=row["matched_keyword_kei"] or 0.0,
            matched_keyword_priority=row["matched_keyword_priority"] or 0.0,
            matched_keyword_category=row["matched_keyword_category"] or "",
            like_count=row_value("like_count", 0) or 0,
            comment_count=row_value("comment_count", 0) or 0,
            view_count=row_value("view_count", 0) or 0,
            exposure_score=row_value("exposure_score", 0.0) or 0.0,
            workability_score=row_value("workability_score", 0.0) or 0.0,
            conversion_fit_score=row_value("conversion_fit_score", 0.0) or 0.0,
            score_breakdown=row_json("score_breakdown", {}),
            search_sort=row_value("search_sort", "") or "",
            search_rank=row_value("search_rank", 0) or 0,
            search_start=row_value("search_start", 0) or 0,
            search_total=row_value("search_total", 0) or 0,
            sort_appearances=row_json("sort_appearances", []),
            ai_reviewed=bool(row_value("ai_reviewed", 0)),
            ai_infiltration_score=row_value("ai_infiltration_score", 0.0) or 0.0,
            ai_post_type=row_value("ai_post_type", "") or "",
            ai_competitor=bool(row_value("ai_competitor", 0)),
            ai_competitor_name=row_value("ai_competitor_name", "") or "",
        )

    def _load_existing_targets_by_urls(self, urls: List[str]) -> List[ViralTarget]:
        """체크포인트 재개 시 이미 저장된 AI 분석 결과를 리포트에 다시 합산."""
        compact_urls = [u for u in dict.fromkeys(urls) if u]
        if not compact_urls:
            return []

        url_to_canonical = {
            url: canonicalize_viral_url(url)
            for url in compact_urls
        }
        loaded_by_url: Dict[str, ViralTarget] = {}
        import sqlite3 as _sql

        try:
            conn = _sql.connect(self.db.db_path)
            conn.row_factory = _sql.Row
            cur = conn.cursor()
            for start in range(0, len(compact_urls), 500):
                raw_chunk = compact_urls[start:start + 500]
                canonical_chunk = [
                    u for u in dict.fromkeys(url_to_canonical.get(url) for url in raw_chunk) if u
                ]
                raw_placeholders = ",".join("?" for _ in raw_chunk)
                canonical_placeholders = ",".join("?" for _ in canonical_chunk)
                where_parts = []
                params = []
                if raw_chunk:
                    where_parts.append(f"url IN ({raw_placeholders})")
                    params.extend(raw_chunk)
                if canonical_chunk:
                    where_parts.append(f"canonical_url IN ({canonical_placeholders})")
                    params.extend(canonical_chunk)
                rows = cur.execute(
                    f"""
                    SELECT *
                    FROM viral_targets
                    WHERE ({' OR '.join(where_parts)})
                      AND COALESCE(comment_status, 'pending') != 'needs_ai_retry'
                    """,
                    params,
                ).fetchall()
                for row in rows:
                    target = self._viral_target_from_db_row(row)
                    if row["url"]:
                        loaded_by_url[row["url"]] = target
                    if "canonical_url" in row.keys() and row["canonical_url"]:
                        loaded_by_url[row["canonical_url"]] = target
            conn.close()
        except Exception as e:
            logger.warning(f"AI 체크포인트 DB 결과 복원 실패: {e}")
            return []

        loaded: List[ViralTarget] = []
        seen_loaded_ids: set[str] = set()
        for url in compact_urls:
            for key in (url, url_to_canonical.get(url)):
                if key not in loaded_by_url:
                    continue
                target = loaded_by_url[key]
                if target.id in seen_loaded_ids:
                    break
                loaded.append(target)
                seen_loaded_ids.add(target.id)
                break
        return loaded

    def _load_backlog_rescue_targets(
        self,
        limit: int,
        exclude_urls: Optional[set] = None,
        days: int = 21,
        categories: Optional[Iterable[str]] = None,
    ) -> List[ViralTarget]:
        """최근 raw_backlog/needs_ai_retry 타겟을 AI 재심사 후보로 로드.

        AI top-N 예산에 밀려 저장만 된 공급이 영구 사장되는 갭을 메운다. 점수순
        정렬 후 `split_ai_targets_with_category_floor`로 카테고리 균형을 강제해
        피부/교통사고 물량이 레스큐 예산까지 독식하지 못하게 한다. 재심사 결과는
        AI 적합 → pending 승격, 부적합 → filtered_out_ai 영속화로 끝나므로 같은
        행이 매 런 재레스큐되는 루프는 생기지 않는다.

        ``categories`` 를 주면 해당 진료축으로 한정해 로드한다(시그니처 백로그 레인).
        category-blind 정렬에서는 피부/다이어트 물량에 밀려 굶는 희소 축을, 확장
        ``days`` 윈도우와 함께 별도 공급하는 용도. 카테고리명은 바인딩 파라미터로만
        전달(상수이지만 인젝션 방지).
        """
        if limit <= 0:
            return []
        import sqlite3 as _sql

        cats = [str(c).strip() for c in (categories or ()) if str(c).strip()]
        cat_clause = ""
        params: list = [f"-{int(days)} days"]
        if cats:
            cat_clause = " AND COALESCE(matched_keyword_category, '') IN (%s)" % (
                ",".join("?" * len(cats))
            )
            params.extend(cats)
        params.append(max(int(limit) * 6, 200))

        rows = []
        try:
            conn = _sql.connect(self.db.db_path)
            conn.row_factory = _sql.Row
            rows = conn.execute(
                f"""
                SELECT *
                FROM viral_targets
                WHERE COALESCE(comment_status, 'pending') IN ('raw_backlog', 'needs_ai_retry')
                  AND COALESCE(is_commentable, 1) = 1
                  AND REPLACE(COALESCE(discovered_at, ''), 'T', ' ') >= datetime('now', ?){cat_clause}
                ORDER BY COALESCE(priority_score, 0) DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            conn.close()
        except Exception as e:
            logger.warning(f"백로그 레스큐 후보 로드 실패: {e}")
            return []

        excluded = exclude_urls or set()
        candidates: List[ViralTarget] = []
        seen_keys: set = set()
        for row in rows:
            target = self._viral_target_from_db_row(row)
            if not target.url:
                continue
            key = canonicalize_viral_url(target.url) or target.url
            if key in excluded or key in seen_keys:
                continue
            seen_keys.add(key)
            candidates.append(target)

        # 레스큐 예산(기본 60)은 top-N(300) 기준 floor보다 훨씬 작아, 원본 쿼터를
        # 그대로 쓰면 피부/교통사고 floor가 예산을 다 소진해 희소축(안면비대칭,
        # 통증/디스크)이 한 건도 못 들어온다 — 예산 비례로 floor를 축소한다.
        scale = min(1.0, int(limit) / 300.0)
        scaled_quotas = {
            category: max(2, int(round(quota * scale)))
            for category, quota in AI_CATEGORY_MIN_QUOTAS.items()
        }
        selected, _rest = split_ai_targets_with_category_floor(
            candidates,
            int(limit),
            category_min_quotas=scaled_quotas,
        )
        return selected

    ENRICHABLE_BODY_PLATFORMS = {"kin", "blog", "cafe", "naver_cafe"}

    def _enrich_and_regate_ai_targets(
        self,
        ai_targets: List[ViralTarget],
        *,
        max_fetch: int = 120,
        time_budget_sec: float = 150.0,
        min_existing_chars: int = 300,
        fetcher=None,
        sleep_sec: float = 0.35,
    ) -> Tuple[List[ViralTarget], Dict[str, int]]:
        """AI 분석 직전, 공개 표면(KIN/blog) 타겟의 실제 본문을 취득하고 게이트 재검사.

        검색 API snippet(~150자)만으로는 UNIFIED_ANALYSIS_PREVIEW_CHARS(700자)의
        설계 의도가 무력하다 — KIN 광고성 답변과 blog 광고 본문 신호는 대부분
        snippet 밖에 있다(라이브 검증: pending 큐의 blog 광고글 2건, KIN 업체
        답변 다수가 snippet 이후 구간에서만 식별 가능). enrichment 후 최종
        게이트를 다시 통과시켜 드러난 광고를 AI 예산 소모 전에 제거한다.
        cafe는 공개 카페만 article API로 취득(멤버 전용 401 → 빈 결과 fail-soft);
        로그인 필요한 카페는 scripts/enrich_cafe_bodies.py(Selenium) 수동 경로 유지.
        """
        stats = {
            "fetched": 0, "enriched": 0, "dated": 0,
            "regate_rejected": 0, "stale_rejected": 0,
        }
        if not ai_targets or max_fetch <= 0:
            return ai_targets, stats

        started = time.time()
        for target in ai_targets:
            if stats["fetched"] >= max_fetch or (time.time() - started) > time_budget_sec:
                break
            if (target.platform or "").lower() not in self.ENRICHABLE_BODY_PLATFORMS:
                continue
            if len(target.content_preview or "") >= min_existing_chars:
                continue
            if not target.url:
                continue
            stats["fetched"] += 1
            detail = fetch_naver_post_detail(target.url, target.platform, fetcher=fetcher)
            if fetcher is None and sleep_sec:
                time.sleep(sleep_sec)

            # 게시일/참여 지표는 본문 개선 여부와 무관하게 채운다 — 검색 API가
            # KIN/cafe 게시일을 주지 않아 타이밍 게이트가 장님이었던 지점.
            if detail["posted_date"] and not target.date_str:
                target.date_str = detail["posted_date"]
                target.score_breakdown = {
                    **(target.score_breakdown or {}),
                    "post_date_enriched": detail["posted_date"],
                }
                stats["dated"] += 1
            for key in ("comment_count", "view_count"):
                value = detail.get(key)
                if value is not None:
                    setattr(target, key, max(int(getattr(target, key, 0) or 0), int(value)))

            body = detail["body"]
            if len(body) <= len(target.content_preview or ""):
                continue
            target.content_preview = body
            target.score_breakdown = {
                **(target.score_breakdown or {}),
                "body_enriched": target.platform,
            }
            stats["enriched"] += 1

        # enrichment 으로 실제 참여 지표(comment/view)가 밝혀진 타겟은 worksite 포화/미답변
        # 신호를 실제 수치로 보정한다 — 선택 시점엔 0이라 死코드였다(no-op when counts=0).
        for target in ai_targets:
            if self._resaturate_worksite_after_enrichment(target):
                stats["worksite_resaturated"] = stats.get("worksite_resaturated", 0) + 1

        # 보강된 타겟만 게이트 재검사 — 미보강 타겟은 같은 증거로 이미 통과했다.
        # KIN [기존답변] 분리는 final_reject_reason 본체가 모든 호출 경로에서
        # 일관되게 수행한다 (여기서 별도 분리하지 않는다).
        kept: List[ViralTarget] = []
        for target in ai_targets:
            breakdown = target.score_breakdown or {}
            if not (breakdown.get("body_enriched") or breakdown.get("post_date_enriched")):
                kept.append(target)
                continue
            if breakdown.get("body_enriched"):
                reject_reason = CommentableFilter.apply_final_reject(target)
                if reject_reason:
                    stats["regate_rejected"] += 1
                    try:
                        self.db.insert_viral_target(target.to_dict())
                    except Exception as e:
                        logger.warning(f"enrichment 게이트 제외 상태 저장 실패: {e}")
                    continue
            # 게시일이 새로 밝혀진 타겟은 타이밍 윈도우를 실제 날짜로 재판정.
            # 발견 시점에는 no_post_date 경로로 '발견 직후 신선' 보너스를 받았다.
            if breakdown.get("post_date_enriched") and not self._timing_regate_keep(target):
                stats["stale_rejected"] += 1
                try:
                    self.db.insert_viral_target(target.to_dict())
                except Exception as e:
                    logger.warning(f"enrichment 타이밍 제외 상태 저장 실패: {e}")
                continue
            kept.append(target)
        return kept, stats

    def _refill_ai_targets_after_enrichment(
        self,
        ai_targets: List[ViralTarget],
        rest_targets: List[ViralTarget],
        *,
        target_count: int,
        max_fetch: int = 0,
        fetcher=None,
    ) -> Tuple[List[ViralTarget], List[ViralTarget], Dict[str, int]]:
        """Backfill AI budget after enrichment/regate removes selected candidates."""
        stats = {
            "attempted": 0, "kept": 0, "rejected": 0,
            "fetched": 0, "enriched": 0, "dated": 0,
            "regate_rejected": 0, "stale_rejected": 0,
        }
        if target_count <= 0 or len(ai_targets) >= target_count or not rest_targets:
            return ai_targets, rest_targets, stats

        selected_keys = {
            canonicalize_viral_url(target.url) or target.url or target.id
            for target in ai_targets
        }
        pool = [
            target for target in sorted(rest_targets, key=_ai_target_sort_key, reverse=True)
            if (canonicalize_viral_url(target.url) or target.url or target.id) not in selected_keys
        ]
        attempted_keys: set[str] = set()
        fetch_budget = max(0, int(max_fetch or 0))

        while len(ai_targets) < target_count and pool:
            candidate = pool.pop(0)
            key = canonicalize_viral_url(candidate.url) or candidate.url or candidate.id
            if not key or key in attempted_keys or key in selected_keys:
                continue
            attempted_keys.add(key)
            stats["attempted"] += 1

            batch = [candidate]
            if fetch_budget > 0:
                kept_batch, enrich_stats = self._enrich_and_regate_ai_targets(
                    batch,
                    max_fetch=fetch_budget,
                    fetcher=fetcher,
                    sleep_sec=0.0 if fetcher is not None else 0.35,
                )
                for stat_key in ("fetched", "enriched", "dated", "regate_rejected", "stale_rejected"):
                    value = int(enrich_stats.get(stat_key, 0) or 0)
                    stats[stat_key] += value
                fetch_budget = max(0, fetch_budget - int(enrich_stats.get("fetched", 0) or 0))
            else:
                kept_batch = batch

            if kept_batch:
                kept = kept_batch[0]
                ai_targets.append(kept)
                selected_keys.add(key)
                stats["kept"] += 1
            else:
                stats["rejected"] += 1

        remaining_rest = [
            target for target in rest_targets
            if (canonicalize_viral_url(target.url) or target.url or target.id) not in attempted_keys
        ]
        ai_targets.sort(key=_ai_target_sort_key, reverse=True)
        return ai_targets, remaining_rest, stats

    @staticmethod
    def _resaturate_worksite_after_enrichment(target: ViralTarget) -> bool:
        """enrichment 으로 실제 comment_count/view_count 가 밝혀진 뒤, 선택 시점엔 0으로
        계산돼 死코드였던 worksite '미답변/포화' 신호를 실제 수치로 보정한다.

        선택 게이트에서는 모든 글이 comment_count=0 → unanswered_thread(+16)을 받아
        포화(답변 多)·미답변 스레드가 동일 점수였다(라이브: 골든큐 노후/포화 오염, 0건
        최근발견). worksite_efficiency_score 는 골든큐 1차 정렬키이므로 보정 가치가 크다.
        같은 인자로 (실수치) vs (0) 두 번 호출해 count 기여분 델타만 정확히 떼어
        점수·priority 에 반영한다 — count 분기가 standalone 이라 다른 항은 상쇄돼 인자
        복원 불완전성과 무관하게 정확하다. 포화 스레드는 정렬 하향 + priority 컷(>=80)
        탈락이 가능해진다. 반환값=보정 적용 여부(테스트/감사용).
        """
        breakdown = target.score_breakdown or {}
        if "worksite_efficiency_score" not in breakdown:
            return False
        if breakdown.get("worksite_saturation_regated_after_enrichment"):
            return False  # 재실행(refill 경로) 중복 적용 방지
        real_cc = max(0, int(getattr(target, "comment_count", 0) or 0))
        real_vc = max(0, int(getattr(target, "view_count", 0) or 0))
        if real_cc == 0 and real_vc == 0:
            return False  # 밝혀진 참여 지표 없음 → 선택 시점과 동일, 보정 불필요

        def _csv(key: str) -> List[str]:
            return [s for s in str(breakdown.get(key, "") or "").split(",") if s]

        def _ival(key: str) -> int:
            try:
                return int(float(breakdown.get(key, 0) or 0))
            except (TypeError, ValueError):
                return 0

        args = (
            _ival("clinic_treatment_fit_score"),
            _ival("viral_need_score"),
            _csv("viral_need_signals"),
            _ival("reply_opportunity_score"),
            _csv("reply_opportunity_signals"),
            _ival("timing_window_score"),
            _csv("timing_window_signals"),
            _ival("journey_fit_score"),
            str(breakdown.get("journey_stage", "") or ""),
            _ival("qualification_fit_score"),
            _csv("reply_risk_flags"),
        )
        real_score = CommentableFilter._assess_worksite_efficiency(target, *args)[0]
        orig_cc, orig_vc = getattr(target, "comment_count", 0), getattr(target, "view_count", 0)
        target.comment_count, target.view_count = 0, 0
        try:
            zero_score = CommentableFilter._assess_worksite_efficiency(target, *args)[0]
        finally:
            target.comment_count, target.view_count = orig_cc, orig_vc

        delta = float(real_score) - float(zero_score)
        old_wk = float(breakdown.get("worksite_efficiency_score", 0) or 0)
        old_adj = float(breakdown.get("worksite_efficiency_adjustment", 0) or 0)
        new_wk = old_wk + delta
        # priority 합성과 동일한 공식(filter): clamp((wk-55)*0.35, -20, 20)
        new_adj = max(-20.0, min(20.0, (new_wk - 55.0) * 0.35))
        target.priority_score = max(
            0.0, float(getattr(target, "priority_score", 0) or 0) + (new_adj - old_adj)
        )
        target.score_breakdown = {
            **breakdown,
            "worksite_efficiency_score": new_wk,
            "worksite_efficiency_adjustment": new_adj,
            "worksite_saturation_regated_after_enrichment": True,
        }
        return True

    @staticmethod
    def _timing_regate_keep(target: ViralTarget) -> bool:
        """게시일 enrichment 후 타이밍 윈도우 재판정. 미달이면 타겟을 만료 상태로 바꾼다.

        viral_need/reply_opportunity 신호는 발견 시점 score_breakdown에 콤마 문자열로
        남아 있어 그대로 복원한다 (rescue 경로 등 신호가 없으면 빈 리스트 fail-soft).
        """
        breakdown = target.score_breakdown or {}
        need_signals = [s for s in str(breakdown.get("viral_need_signals", "")).split(",") if s]
        reply_signals = [s for s in str(breakdown.get("reply_opportunity_signals", "")).split(",") if s]
        score, tier, signals = CommentableFilter._assess_timing_window(
            target, need_signals, reply_signals
        )
        target.score_breakdown = {
            **breakdown,
            "timing_window_score": float(score),
            "timing_window_tier": tier,
            "timing_window_signals": ",".join(signals),
            "timing_regated_after_date_enrichment": True,
        }
        if score >= CommentableFilter.MIN_TIMING_WINDOW_SCORE:
            return True
        target.is_commentable = False
        target.comment_status = "filtered_out_stale_window"
        return False

    @staticmethod
    def _noise_key(text: str) -> str:
        normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
        normalized = re.sub(r"[\[\]{}()|:;,.!?~`'\"<>]", "", normalized)
        return normalized

    def _apply_batch_quality_gate(self, targets: List[ViralTarget]) -> List[ViralTarget]:
        if not targets:
            return targets

        title_counts: Dict[str, int] = {}
        preview_counts: Dict[str, int] = {}
        for target in targets:
            title_key = self._noise_key(target.title)
            if len(title_key) >= 12:
                title_counts[title_key] = title_counts.get(title_key, 0) + 1

            preview_key = self._noise_key(target.content_preview)[:180]
            if len(preview_key) >= 80:
                digest = hashlib.md5(preview_key.encode("utf-8")).hexdigest()
                preview_counts[digest] = preview_counts.get(digest, 0) + 1

        kept: List[ViralTarget] = []
        removed = {"title_duplicate": 0, "preview_duplicate": 0}
        for target in targets:
            title_key = self._noise_key(target.title)
            if title_key and title_counts.get(title_key, 0) >= 3:
                removed["title_duplicate"] += 1
                continue

            preview_key = self._noise_key(target.content_preview)[:180]
            if len(preview_key) >= 80:
                digest = hashlib.md5(preview_key.encode("utf-8")).hexdigest()
                if preview_counts.get(digest, 0) >= 3:
                    removed["preview_duplicate"] += 1
                    continue

            kept.append(target)

        removed_total = len(targets) - len(kept)
        if removed_total:
            logger.info(
                "Batch quality gate removed repeated content: "
                f"{removed_total} targets "
                f"(title={removed['title_duplicate']}, preview={removed['preview_duplicate']})"
            )
            print(
                f"   🧹 반복 콘텐츠 게이트: {len(targets)}개 -> {len(kept)}개 "
                f"(제목중복 {removed['title_duplicate']}, 본문중복 {removed['preview_duplicate']})"
            )
        return kept

    @staticmethod
    def _urls_for_batch_indices(
        targets: List[ViralTarget],
        batch_size: int,
        batch_indices: set,
    ) -> List[str]:
        urls: List[str] = []
        for batch_idx in sorted(batch_indices):
            start = (batch_idx - 1) * batch_size
            if start < 0:
                continue
            for target in targets[start:start + batch_size]:
                if target.url:
                    urls.append(target.url)
        return urls

    def _exclude_existing_targets_before_ai(
        self,
        targets: List[ViralTarget],
    ) -> tuple[List[ViralTarget], int]:
        """Remove DB-existing URLs before raw backlog and AI analysis.

        The rediscovered URLs are still touched in DB so scan_count and latest
        Legion lineage remain useful, but they do not consume AI quota.
        """
        if not targets:
            return targets, 0

        unique_targets: List[ViralTarget] = []
        seen_urls: set[str] = set()
        in_batch_duplicates = 0
        for target in targets:
            if not target.url:
                continue
            canonical_key = canonicalize_viral_url(target.url) or target.url
            if canonical_key in seen_urls:
                in_batch_duplicates += 1
                continue
            seen_urls.add(canonical_key)
            unique_targets.append(target)

        if in_batch_duplicates:
            print(f"   ♻️ 실행 내 중복 URL {in_batch_duplicates}개 제외")
        targets = unique_targets
        if not targets:
            return [], in_batch_duplicates

        existing_urls = self.db.get_existing_viral_urls([t.url for t in targets])
        if not existing_urls:
            print(f"   ✅ 중복 없음: {len(targets)}개 모두 신규")
            return targets, in_batch_duplicates

        duplicate_targets = [t for t in targets if t.url in existing_urls]
        fresh_targets = [t for t in targets if t.url not in existing_urls]

        refreshed = 0
        try:
            refreshed = self.db.refresh_existing_viral_targets(
                [t.to_dict() for t in duplicate_targets]
            )
        except Exception as e:
            logger.warning(f"기존 URL 메타데이터 갱신 실패: {e}")

        print(
            f"   ♻️ 기존 URL {len(duplicate_targets)}개 제외: "
            f"scan_count/source_scan_run_id 갱신 {refreshed}개, "
            f"AI 후보 {len(targets)}개 -> {len(fresh_targets)}개"
        )
        return fresh_targets, len(duplicate_targets) + in_batch_duplicates

    def _persist_viral_discovery_audit(
        self,
        run_started_at: str,
        *,
        source_scan_run_id: Optional[int] = None,
        keyword_count: int = 0,
        db_path: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Persist this run's funnel yield by axis, query variant, and query structure.

        Console funnel stats vanish with the terminal; this keeps per-category and
        per-structure discovery quality queryable (viral_scan_audits) so seed review
        and the next exploration pass can see where SERP budget actually converted
        into workable targets.
        """
        import sqlite3

        path = db_path or os.path.join(self.cfg.root_dir, 'db', 'marketing_data.db')
        conn = sqlite3.connect(path)
        try:
            conn.row_factory = sqlite3.Row
            target_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(viral_targets)").fetchall()
            }
            time_filters: List[str] = []
            time_params: List[str] = []
            if "discovered_at" in target_columns:
                time_filters.append("REPLACE(COALESCE(discovered_at, ''), 'T', ' ') >= ?")
                time_params.append(run_started_at)
            if "last_scanned_at" in target_columns:
                time_filters.append("REPLACE(COALESCE(last_scanned_at, ''), 'T', ' ') >= ?")
                time_params.append(run_started_at)
            if not time_filters:
                return None

            timestamp_selects = []
            for column in ("discovered_at", "last_scanned_at"):
                if column in target_columns:
                    timestamp_selects.append(column)
                else:
                    timestamp_selects.append(f"'' AS {column}")
            where_sql = f"({' OR '.join(time_filters)})"
            query_params: List[Any] = list(time_params)
            if source_scan_run_id is not None and "source_scan_run_id" in target_columns:
                where_sql += " AND COALESCE(source_scan_run_id, 0) = ?"
                query_params.append(int(source_scan_run_id or 0))
            rows = conn.execute(
                f"""
                SELECT category, comment_status, matched_keyword, matched_keywords,
                       matched_keyword_category, score_breakdown,
                       {", ".join(timestamp_selects)}
                FROM viral_targets
                WHERE {where_sql}
                """,
                tuple(query_params),
            ).fetchall()

            def _bucket_status(status: str) -> str:
                if status in {'pending', 'generated', 'posted', 'approved', 'ai_approved'}:
                    return 'pending'
                if status == 'raw_backlog':
                    return 'raw_backlog'
                if status == 'filtered_out_ad':
                    return 'ad_filtered'
                if status.startswith('filtered_out'):
                    return 'rejected'
                return 'other'

            empty_entry = {
                'discovered': 0, 'fresh_discovered': 0,
                'pending': 0, 'fresh_pending': 0, 'rediscovered_pending': 0,
                'open_pending': 0, 'ai_filtered': 0,
                'raw_backlog': 0, 'ad_filtered': 0, 'rejected': 0,
                'other': 0, 'rediscovered': 0,
            }
            per_category: Dict[str, Dict[str, int]] = {}
            per_variant: Dict[str, Dict[str, int]] = {}
            per_category_lens: Dict[str, Dict[str, int]] = {}
            per_category_lens_variant: Dict[str, Dict[str, int]] = {}
            per_structure: Dict[str, Dict[str, int]] = {}
            per_seed: Dict[str, Dict[str, int]] = {}
            # 축별×거절사유 퍼널 분해 — '어느 진료축이 어느 사유로 발견을 잃는가'를 상시
            # 측정해 수동 SQL 포렌식을 시스템 역량으로 만든다(예: 흉터가 region_mismatch
            # 31%·off_domain 29% 로 잃음 → 게이트 버그가 아니라 로컬 키워드 검색의 본질,
            # 또는 안면비대칭이 domain_mismatch 로 잃으면 의미 구제 enable 신호).
            per_category_reject_reason: Dict[str, Dict[str, int]] = {}
            for row in rows:
                try:
                    breakdown = json.loads(row['score_breakdown'] or '{}')
                except (TypeError, ValueError):
                    breakdown = {}
                if not isinstance(breakdown, dict):
                    breakdown = {}
                source_keyword = str(breakdown.get('pathfinder_source_keyword') or '').strip()
                if not source_keyword:
                    try:
                        parsed = json.loads(row['matched_keywords'] or '[]')
                    except (TypeError, ValueError):
                        parsed = []
                    if isinstance(parsed, list) and parsed:
                        source_keyword = str(parsed[0] or '').strip()
                if not source_keyword:
                    source_keyword = str(row['matched_keyword'] or '').strip() or '(unknown)'
                raw_category = str(row['matched_keyword_category'] or row['category'] or '기타')
                category = canonical_category_for_keyword(source_keyword, raw_category)
                variant = str(breakdown.get('pathfinder_query_variant') or '(none)')
                lens = str(breakdown.get('pathfinder_execution_lens') or '').strip().lower()
                if not lens:
                    lens = self._inferred_execution_lens_for_keyword(source_keyword, {"category": category})
                lens = lens or "service"
                category_lens_key = f"{category}::{lens}"
                category_lens_variant_key = f"{category_lens_key}::{variant}"
                status_text = str(row['comment_status'] or 'pending')
                status_bucket = _bucket_status(status_text)
                discovered_current = (
                    str(row['discovered_at'] or '').replace('T', ' ') >= run_started_at
                )
                scanned_current = (
                    str(row['last_scanned_at'] or '').replace('T', ' ') >= run_started_at
                )
                rediscovered_current = bool(scanned_current and not discovered_current)
                structure_key = str(
                    keyword_structure_features(source_keyword, category)['structure_key']
                )
                for table, key in (
                    (per_category, category),
                    (per_variant, variant),
                    (per_category_lens, category_lens_key),
                    (per_category_lens_variant, category_lens_variant_key),
                    (per_structure, structure_key),
                    (per_seed, source_keyword),
                ):
                    entry = table.setdefault(key, dict(empty_entry))
                    entry['discovered'] += 1
                    if discovered_current:
                        entry['fresh_discovered'] += 1
                    entry[status_bucket] += 1
                    if status_text == 'pending':
                        entry['open_pending'] += 1
                    if status_text == 'filtered_out_ai':
                        entry['ai_filtered'] += 1
                    if status_bucket == 'pending':
                        if discovered_current:
                            entry['fresh_pending'] += 1
                        elif rediscovered_current:
                            entry['rediscovered_pending'] += 1
                    if rediscovered_current:
                        entry['rediscovered'] += 1

                if status_text.startswith('filtered_out'):
                    reason = str(breakdown.get('final_reject_reason') or '').strip()
                    if not reason:
                        reason = status_text[len('filtered_out'):].lstrip('_') or '(unspecified)'
                    cat_reasons = per_category_reject_reason.setdefault(category, {})
                    cat_reasons[reason] = cat_reasons.get(reason, 0) + 1

            discovered_total = sum(e['discovered'] for e in per_category.values())
            fresh_total = sum(e['fresh_discovered'] for e in per_category.values())
            pending_total = sum(e['pending'] for e in per_category.values())
            fresh_pending_total = sum(e['fresh_pending'] for e in per_category.values())
            open_pending_total = sum(e['open_pending'] for e in per_category.values())
            ai_filtered_total = sum(e['ai_filtered'] for e in per_category.values())
            raw_backlog_total = sum(e['raw_backlog'] for e in per_category.values())
            rejected_total = sum(e['rejected'] for e in per_category.values())
            ad_total = sum(e['ad_filtered'] for e in per_category.values())
            rediscovered_total = sum(e.get('rediscovered', 0) for e in per_category.values())
            rediscovered_pending_total = sum(e.get('rediscovered_pending', 0) for e in per_category.values())
            post_ai_total = pending_total + ai_filtered_total
            # 제로수율 시드: 이번 런에 실제 신규 SERP 영역을 탐색하고(fresh_discovered)
            # 작업 가능 타겟을 0건 산출한(pending 버킷=posted 포함, 0) 시드만.
            # 전체 discovered 가 아니라 신규 발견으로 게이트해, 옛 URL만 재발견한
            # rediscovery 잡음(런의 ~88%)과 재발견-posted 로 이미 가치를 실현한 성숙
            # 시드를 제로수율로 오분류하지 않는다. 이 목록은 자문/가시성 신호다
            # (구조/카테고리 수요 게이트가 실제 예산 차단을 담당).
            zero_yield_seeds = sorted(
                (
                    {
                        'seed': seed,
                        'discovered': entry['discovered'],
                        'fresh_discovered': entry['fresh_discovered'],
                        'rediscovered': entry['rediscovered'],
                        'ad_filtered': entry['ad_filtered'],
                    }
                    for seed, entry in per_seed.items()
                    if entry['fresh_discovered'] >= ZERO_YIELD_MIN_FRESH_DISCOVERED
                    and entry['pending'] == 0
                ),
                key=lambda item: -item['fresh_discovered'],
            )[:20]
            focus_categories = [
                GYULIM_KEYWORD_PROFILE.normalize_category(category)
                for category in getattr(GYULIM_KEYWORD_PROFILE, "focus_categories", ())
            ]
            focus_categories = list(dict.fromkeys(category for category in focus_categories if category))
            focus_axis_rows: Dict[str, Dict[str, Any]] = {}
            for category in focus_categories:
                entry = dict(per_category.get(category) or empty_entry)
                discovered = int(entry.get('discovered') or 0)
                pending = int(entry.get('pending') or 0)
                open_pending = int(entry.get('open_pending') or 0)
                ai_filtered = int(entry.get('ai_filtered') or 0)
                focus_axis_rows[category] = {
                    **entry,
                    'actionable_rate': (pending / discovered) if discovered else 0.0,
                    'open_pending_rate': (open_pending / discovered) if discovered else 0.0,
                    'ai_filtered_rate': (ai_filtered / discovered) if discovered else 0.0,
                }
            covered_focus = [
                category for category, entry in focus_axis_rows.items()
                if int(entry.get('discovered') or 0) > 0
            ]
            actionable_focus = [
                category for category, entry in focus_axis_rows.items()
                if int(entry.get('pending') or 0) > 0
            ]
            open_pending_focus = [
                category for category, entry in focus_axis_rows.items()
                if int(entry.get('open_pending') or 0) > 0
            ]
            focus_axis_coverage = {
                'total_focus_categories': len(focus_categories),
                'covered_focus_categories': len(covered_focus),
                'actionable_focus_categories': len(actionable_focus),
                'open_pending_focus_categories': len(open_pending_focus),
                'discovery_coverage_rate': (len(covered_focus) / len(focus_categories)) if focus_categories else 0.0,
                'actionable_coverage_rate': (len(actionable_focus) / len(focus_categories)) if focus_categories else 0.0,
                'open_pending_coverage_rate': (len(open_pending_focus) / len(focus_categories)) if focus_categories else 0.0,
                'missing_discovery_categories': [
                    category for category in focus_categories
                    if category not in covered_focus
                ],
                'missing_actionable_categories': [
                    category for category in focus_categories
                    if category not in actionable_focus
                ],
                'missing_open_pending_categories': [
                    category for category in focus_categories
                    if category not in open_pending_focus
                ],
                'priority_focus_categories': [
                    category for category in AI_CATEGORY_FLOOR_PRIORITY
                    if category in focus_categories
                ],
                'by_category': focus_axis_rows,
            }

            # 디스커버리 정직성: 지금까지 stdout 으로만 흘러가 사라지던 "조용한 경계"
            # (퍼널 거절 사유·변형/플랫폼/구조 수율 차단·키워드 한도 절단)을 영속화해
            # 다음 탐색 패스가 "무엇을 발견조차 못 했는지"를 질의할 수 있게 한다.
            filter_obj = getattr(self, "filter", None)
            funnel_rejections = {
                reason: int(count)
                for reason, count in (getattr(filter_obj, "cumulative_reject_stats", {}) or {}).items()
                if int(count or 0) > 0
            }
            filter_input_count = int(getattr(filter_obj, "filter_input_count", 0) or 0)
            filter_survivor_count = int(getattr(filter_obj, "filter_survivor_count", 0) or 0)
            funnel_rejected_total = sum(funnel_rejections.values())
            coverage_bounds = {
                'funnel_rejections': funnel_rejections,
                'funnel_rejected_total': funnel_rejected_total,
                'filter_input_count': filter_input_count,
                'filter_survivor_count': filter_survivor_count,
                'filter_survival_rate': (filter_survivor_count / filter_input_count) if filter_input_count else 0.0,
                'variant_yield_drops': {k: int(v) for k, v in (getattr(self, "_variant_drop_counts", {}) or {}).items()},
                'platform_yield_drops': {k: int(v) for k, v in (getattr(self, "_platform_drop_counts", {}) or {}).items()},
                'structure_blocked': {
                    k: int(v)
                    for k, v in (getattr(getattr(self, "seed_builder", None), "_structure_blocked_buckets", {}) or {}).items()
                },
                'keyword_limit_dropped': int(getattr(self, "_keyword_limit_dropped", 0) or 0),
            }

            audit: Dict[str, Any] = {
                'summary': {
                    'discovered': discovered_total,
                    'fresh_discovered': fresh_total,
                    'pending': pending_total,
                    'actionable': pending_total,
                    'fresh_pending': fresh_pending_total,
                    'open_pending': open_pending_total,
                    'pending_rate': (pending_total / discovered_total) if discovered_total else 0.0,
                    'actionable_rate': (pending_total / discovered_total) if discovered_total else 0.0,
                    'fresh_pending_rate': (fresh_pending_total / fresh_total) if fresh_total else 0.0,
                    'fresh_actionable_rate': (fresh_pending_total / fresh_total) if fresh_total else 0.0,
                    'open_pending_rate': (open_pending_total / discovered_total) if discovered_total else 0.0,
                    'fresh_discovery_rate': (fresh_total / discovered_total) if discovered_total else 0.0,
                    'ai_filtered': ai_filtered_total,
                    'ai_filtered_rate': (ai_filtered_total / discovered_total) if discovered_total else 0.0,
                    'post_ai_survival_rate': (pending_total / post_ai_total) if post_ai_total else 0.0,
                    'raw_backlog': raw_backlog_total,
                    'rejected': rejected_total,
                    'ad_filtered': ad_total,
                    'ad_rate': (ad_total / discovered_total) if discovered_total else 0.0,
                    'rediscovered': rediscovered_total,
                    'rediscovered_pending': rediscovered_pending_total,
                    'rediscovered_rate': (rediscovered_total / discovered_total) if discovered_total else 0.0,
                    'keyword_count': int(keyword_count or 0),
                },
                'per_category': per_category,
                'per_query_variant': per_variant,
                'per_category_lens': per_category_lens,
                'per_category_lens_query_variant': per_category_lens_variant,
                'per_structure': per_structure,
                'per_category_reject_reason': per_category_reject_reason,
                'zero_yield_seeds': zero_yield_seeds,
                'focus_axis_coverage': focus_axis_coverage,
                'category_demand': {
                    'adjustments': getattr(getattr(self, "seed_builder", None), "_category_demand_adjustments", {}) or {},
                    'boosts': getattr(getattr(self, "seed_builder", None), "_category_demand_boosts", {}) or {},
                },
                'coverage_bounds': coverage_bounds,
            }

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS viral_scan_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_started_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                    source_scan_run_id INTEGER,
                    keyword_count INTEGER DEFAULT 0,
                    discovered_count INTEGER DEFAULT 0,
                    pending_count INTEGER DEFAULT 0,
                    pending_rate REAL DEFAULT 0,
                    ad_filtered_count INTEGER DEFAULT 0,
                    audit_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            cursor = conn.execute(
                """
                INSERT INTO viral_scan_audits (
                    run_started_at, source_scan_run_id, keyword_count,
                    discovered_count, pending_count, pending_rate,
                    ad_filtered_count, audit_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_started_at,
                    source_scan_run_id,
                    int(keyword_count or 0),
                    discovered_total,
                    pending_total,
                    audit['summary']['pending_rate'],
                    ad_total,
                    json.dumps(audit, ensure_ascii=False),
                ),
            )
            conn.commit()
            audit['audit_id'] = cursor.lastrowid
            return audit
        finally:
            conn.close()

    def hunt(self, keywords: List[str] = None, limit_keywords: int = None,
             max_per_platform: int = 100, progress_callback=None,
             fresh: bool = False, checkpoint_every: int = 20,
             top_n_for_ai: int = 300, ai_parallel: int = 5,
             use_latest_legion: bool = True,
             source_scan_run_id: Optional[int] = None,
             boost_categories: Optional[Iterable[str]] = None,
             boost_lenses: Optional[Iterable[str]] = None,
             rescue_backlog: int = 60,
             rescue_signature: int = 40,
             enrich_bodies: int = 120,
             expire_pending: bool = True) -> List[ViralTarget]:
        """
        바이럴 타겟 발굴

        Args:
            keywords: 검색할 키워드 (None이면 config에서 로드)
            limit_keywords: 키워드 제한 수
            max_per_platform: 플랫폼당 최대 결과 수
            progress_callback: 진행 상황 콜백 함수 (stage, current, total, message)
            fresh: True면 체크포인트 무시하고 처음부터 시작
            checkpoint_every: N개 키워드마다 체크포인트 저장

        Returns:
            발견된 ViralTarget 리스트
        """
        run_started_at = time.strftime('%Y-%m-%d %H:%M:%S')

        # pending 큐 TTL 정리 — 직원이 손대지 않은 채 댓글 적시성 윈도우가 지난
        # 행을 만료시킨다. 큐가 죽은 재고로 차면 골든큐/우선순위가 모두 오염된다.
        if expire_pending:
            try:
                expiry = expire_stale_pending_targets(self.db.db_path)
                if expiry["expired"]:
                    platform_summary = ", ".join(
                        f"{p} {n}" for p, n in sorted(expiry["by_platform"].items())
                    )
                    print(
                        f"🧽 pending TTL 정리: {expiry['expired']}건 만료 "
                        f"(체류초과 {expiry['expired_dwell']}, 게시물노후 {expiry['expired_post_age']}) / "
                        f"검사 {expiry['checked']}건 ({platform_summary})"
                    )
            except Exception as e:
                logger.warning(f"pending TTL 정리 실패 (계속 진행): {e}")

        # 변형/플랫폼 수율 캐시·차단 집계는 런 단위로 재계산한다 (직전 런 결과 반영).
        self._variant_yield_cache = None
        self._variant_drop_counts = {}
        self._platform_yield_cache = None
        self._platform_drop_counts = {}

        if keywords is None:
            keywords = self._load_keywords(
                use_latest_legion=use_latest_legion,
                source_scan_run_id=source_scan_run_id,
            )
        else:
            self._load_keyword_context(keywords)

        self._load_keyword_context(keywords)
        keywords = self._order_keywords_for_handoff_coverage(
            keywords,
            boost_categories=boost_categories,
            boost_lenses=boost_lenses,
        )

        keyword_total_before_limit = len(keywords)
        if limit_keywords:
            keywords = keywords[:limit_keywords]
        self._keyword_limit_dropped = max(0, keyword_total_before_limit - len(keywords))

        self._load_keyword_context(keywords)

        # Checkpoint scope includes scan lineage, boost lanes, ordered queries, and platform limits.
        kw_hash = self._checkpoint_hash_for_run(
            keywords,
            max_per_platform=max_per_platform,
            source_scan_run_id=source_scan_run_id,
            boost_categories=boost_categories,
            boost_lenses=boost_lenses,
        )
        # 해시 계산이 플랜을 한 번 더 생성하므로 차단 집계는 검색 패스 기준으로 리셋
        self._variant_drop_counts = {}
        self._platform_drop_counts = {}
        # 퍼널 거절 누적도 런 단위로 리셋 (같은 헌터 객체 재사용 시 직전 런 누수 방지).
        if getattr(self, "filter", None) is not None:
            self.filter.cumulative_reject_stats = {}
            self.filter.filter_input_count = 0
            self.filter.filter_survivor_count = 0

        # 체크포인트 복원
        all_targets: List[ViralTarget] = []
        seen_urls: set = set()
        processed_set: set = set()
        targets_by_url: Dict[str, ViralTarget] = {}

        if not fresh:
            cp = self._load_checkpoint(kw_hash)
            if cp:
                processed_set = set(cp.get('processed_keywords') or [])
                seen_urls = {
                    canonicalize_viral_url(u) or u
                    for u in (cp.get('seen_urls') or [])
                }
                all_targets = [
                    self._viral_target_from_dict(d)
                    for d in (cp.get('all_targets') or [])
                ]
                targets_by_url = {
                    canonicalize_viral_url(target.url) or target.url: target
                    for target in all_targets
                    if target.url
                }
                print(f"\n♻️  체크포인트 복원: 처리 완료 {len(processed_set)}/{len(keywords)}, "
                      f"수집 {len(all_targets)}개 (저장 시각 {cp.get('saved_at')})")

        print(f"\n{'='*60}")
        print(f"🎯 Viral Hunter 스캔 시작")
        print(f"   키워드: {len(keywords)}개 (남은 {len(keywords) - len(processed_set)}개)")
        print(f"   플랫폼: 카페, 블로그, 지식인")
        print(f"   체크포인트: 매 {checkpoint_every}개마다 저장")
        print(f"{'='*60}\n")

        if progress_callback:
            progress_callback("초기화", len(processed_set), len(keywords),
                              f"키워드 {len(keywords)}개 로드 완료")

        checkpoint_counter = 0

        for i, kw in enumerate(keywords, 1):
            if kw in processed_set:
                continue  # 이미 처리됨

            print(f"\n[{i}/{len(keywords)}] '{kw}' 검색 중...")

            if progress_callback:
                progress_callback("검색중", i, len(keywords), f"'{kw}' 검색 | 수집: {len(all_targets)}개")

            try:
                results = []
                for search_plan in self._search_queries_for_keyword(kw, max_per_platform):
                    query = search_plan["query"]
                    limits = search_plan["platform_limits"]
                    logger.info(
                        "[search-plan] %s query=%s variant=%s readiness=%.1f risk=%.1f surface=%s type=%s limits=%s",
                        kw,
                        query,
                        search_plan.get("variant") or "base",
                        search_plan["readiness"],
                        search_plan["medical_risk"],
                        search_plan["preferred_surface"] or "-",
                        search_plan["recommended_content_type"] or "-",
                        limits,
                    )
                    query_results = self.searcher.search_all(
                        query,
                        max_per_platform=max_per_platform,
                        include_blog=bool(search_plan["include_blog"]),
                        platform_limits=limits,
                    )
                    for target in query_results:
                        self._attach_search_query_lineage(
                            target,
                            source_keyword=kw,
                            search_query=query,
                            query_variant=search_plan.get("variant") or "base",
                        )
                    results.extend(query_results)
            except Exception as e:
                logger.error(f"'{kw}' 검색 중 예외: {e} — 다음 키워드로 진행")
                results = []

            # 중복 제거
            for target in results:
                canonical_key = canonicalize_viral_url(target.url) or target.url
                existing_target = targets_by_url.get(canonical_key)
                if existing_target:
                    self._merge_duplicate_search_target(existing_target, target)
                    self._apply_keyword_context(existing_target)
                    continue
                if canonical_key not in seen_urls:
                    seen_urls.add(canonical_key)
                    self._apply_keyword_context(target)
                    all_targets.append(target)
                    targets_by_url[canonical_key] = target

            processed_set.add(kw)
            checkpoint_counter += 1

            # 진행 상황
            if i % 5 == 0:
                print(f"   📊 진행: {i}/{len(keywords)} | 수집: {len(all_targets)}개")

            # 체크포인트 저장
            if checkpoint_counter >= checkpoint_every:
                self._save_checkpoint(
                    kw_hash, list(processed_set), all_targets, seen_urls
                )
                checkpoint_counter = 0
                print(f"   💾 체크포인트 저장: {len(processed_set)}/{len(keywords)}, 수집 {len(all_targets)}개")

        # 검색 단계 끝 — 최종 체크포인트 (AI 분석 전 안전장치)
        self._save_checkpoint(
            kw_hash, list(processed_set), all_targets, seen_urls
        )

        # 재발견된 기존 pending 광고글도 상태가 갱신되도록 강한 최종 게이트를 먼저 적용한다.
        if all_targets:
            gate_keep: List[ViralTarget] = []
            gate_removed = 0
            gate_saved = 0
            for target in all_targets:
                reject_reason = CommentableFilter.apply_final_reject(target)
                if reject_reason:
                    gate_removed += 1
                    try:
                        if self.db.insert_viral_target(target.to_dict()):
                            gate_saved += 1
                    except Exception as e:
                        logger.warning(f"사전 최종 게이트 제외 상태 저장 실패: {e}")
                    continue
                gate_keep.append(target)
            if gate_removed:
                print(f"   🧹 사전 광고/노이즈 게이트: {gate_removed}개 제외 (상태 저장 {gate_saved}개)")
            all_targets = gate_keep

        # 필터링
        print(f"\n🔍 필터링 중...")
        if progress_callback:
            progress_callback("필터링중", len(keywords), len(keywords), f"{len(all_targets)}개 타겟 필터링 중...")
        filtered = self.filter.filter(all_targets)
        filtered = self._apply_batch_quality_gate(filtered)

        # 기존 URL은 scan_count/source_scan_run_id만 갱신하고 AI 판별 전 제외한다.
        if filtered:
            print(f"\n🔄 중복 체크 중...")
            try:
                filtered, _existing_before_ai = self._exclude_existing_targets_before_ai(filtered)
            except Exception as e:
                logger.warning(f"중복 체크 실패 (계속 진행): {e}")

        # [D2] Adaptive penalty 적용 — 반복 skip된 도메인/작성자 감점
        if filtered:
            try:
                import sqlite3 as _sql
                from urllib.parse import urlparse as _urlparse
                conn = _sql.connect(os.path.join(self.cfg.root_dir, 'db', 'marketing_data.db'))
                c = conn.cursor()
                c.execute(
                    "SELECT key_type, key_value, skip_count FROM viral_adaptive_penalties WHERE skip_count >= 3"
                )
                penalties = {(r[0], r[1]): r[2] for r in c.fetchall()}
                conn.close()
                if penalties:
                    penalized = 0
                    for t in filtered:
                        domain = _urlparse(t.url or '').netloc.replace('www.', '')
                        dpen = penalties.get(('domain', domain), 0)
                        apen = penalties.get(('author', t.author or ''), 0)
                        total_pen = min(30, dpen * 3) + min(20, apen * 3)
                        if total_pen > 0:
                            t.priority_score = max(0, (t.priority_score or 0) - total_pen)
                            penalized += 1
                    if penalized:
                        filtered.sort(key=lambda x: x.priority_score, reverse=True)
                        print(f"   ⚙️ Adaptive penalty 적용: {penalized}개 타겟 점수 조정")
            except Exception as e:
                logger.debug(f"adaptive penalty skip: {e}")

        # 직원 실작업 결과 prior — 같은 카테고리/레인이라도 직원 승인율이 낮은 시드의
        # 타겟은 AI 예산·pending 큐 순서에서 소폭 뒤로 보낸다 (카테고리 floor가 있어
        # 소수 축이 굶지는 않는다).
        if filtered:
            staff_adjusted = 0
            for t in filtered:
                breakdown = t.score_breakdown or {}
                staff_adj = float(breakdown.get('pathfinder_staff_outcome_adjustment') or 0.0)
                if not staff_adj:
                    continue
                delta = max(-8.0, min(8.0, staff_adj * 0.5))
                t.priority_score = max(0.0, (t.priority_score or 0.0) + delta)
                staff_adjusted += 1
            if staff_adjusted:
                filtered.sort(key=lambda x: x.priority_score, reverse=True)
                print(f"   👤 직원 결과 prior 적용: {staff_adjusted}개 타겟 점수 조정")

        # 상위 N개만 AI 분석 대상, 나머지는 raw 저장.
        # 단, 전역 점수순만 쓰면 피부/교통사고 물량이 많은 날 비대칭/교정 같은
        # 핵심 소수 카테고리가 전부 raw_backlog로 밀린다.
        ai_targets, rest_targets = split_ai_targets_with_category_floor(
            filtered,
            top_n_for_ai,
        )

        # 백로그 레스큐 — AI 예산에 밀려 raw_backlog/needs_ai_retry로 사장된 최근
        # 타겟을 매 런 일정량 재심사한다. 직접 pending 승격은 금지(광고/적합성 AI
        # 게이트를 그대로 통과시켜야 하므로) — AI 분석 큐에 추가 투입만 한다.
        rescued_count = 0
        if rescue_backlog and top_n_for_ai > 0:
            try:
                run_urls = {
                    canonicalize_viral_url(t.url) or t.url
                    for t in filtered
                    if t.url
                }
                rescue_quota = min(int(rescue_backlog), int(top_n_for_ai))
                rescue_candidates = self._load_backlog_rescue_targets(rescue_quota, run_urls)
                rescue_gate_rejected = 0
                rescue_kept: List[ViralTarget] = []
                for t in rescue_candidates:
                    prior_status = t.comment_status or "raw_backlog"
                    reject_reason = CommentableFilter.apply_final_reject(t)
                    if reject_reason:
                        # 게이트가 진화했으므로 과거 backlog도 최신 게이트로 재탈락 영속화
                        rescue_gate_rejected += 1
                        try:
                            self.db.insert_viral_target(t.to_dict())
                        except Exception as e:
                            logger.warning(f"레스큐 게이트 제외 상태 저장 실패: {e}")
                        continue
                    t.score_breakdown = {
                        **(t.score_breakdown or {}),
                        "rescued_from": prior_status,
                    }
                    # AI 적합 판정 시 upsert CASE가 raw_backlog → pending 승격을 처리한다.
                    t.comment_status = "pending"
                    rescue_kept.append(t)
                if rescue_kept:
                    rescued_count = len(rescue_kept)
                    ai_targets = ai_targets + rescue_kept
                    print(
                        f"   ♻️ 백로그 레스큐: {rescued_count}개 AI 재심사 투입 "
                        f"(최신 게이트 재탈락 {rescue_gate_rejected}개)"
                    )
                elif rescue_gate_rejected:
                    print(f"   ♻️ 백로그 레스큐: 최신 게이트 재탈락 {rescue_gate_rejected}개, 투입 0개")
            except Exception as e:
                logger.warning(f"백로그 레스큐 실패 (계속 진행): {e}")

        # 시그니처 백로그 레인 — 로컬 환자글이 구조적으로 희소한 흉터/안면비대칭은 일반
        # 레스큐(category-blind·21일)에서 피부/다이어트 물량에 밀려 굶는다. 확장 윈도우
        # (180일)+카테고리 우선으로 raw_backlog(이미 commentable 통과·예산 기아)를 별도
        # 공급한다. 일반 레스큐와 동일한 최종 게이트를 통과시켜 자동 승격은 없다.
        sig_rescued_count = 0
        if rescue_signature and top_n_for_ai > 0:
            try:
                exclude = {
                    canonicalize_viral_url(t.url) or t.url
                    for t in ai_targets
                    if t.url
                }
                sig_quota = min(int(rescue_signature), int(top_n_for_ai))
                sig_candidates = self._load_backlog_rescue_targets(
                    sig_quota,
                    exclude,
                    days=SIGNATURE_BACKLOG_RESCUE_DAYS,
                    categories=SIGNATURE_BACKLOG_AXES,
                )
                sig_gate_rejected = 0
                sig_kept: List[ViralTarget] = []
                for t in sig_candidates:
                    prior_status = t.comment_status or "raw_backlog"
                    reject_reason = CommentableFilter.apply_final_reject(t)
                    if reject_reason:
                        sig_gate_rejected += 1
                        try:
                            self.db.insert_viral_target(t.to_dict())
                        except Exception as e:
                            logger.warning(f"시그니처 레스큐 게이트 제외 상태 저장 실패: {e}")
                        continue
                    t.score_breakdown = {
                        **(t.score_breakdown or {}),
                        "rescued_from": prior_status,
                        "signature_backlog_lane": True,
                    }
                    t.comment_status = "pending"
                    sig_kept.append(t)
                if sig_kept:
                    sig_rescued_count = len(sig_kept)
                    ai_targets = ai_targets + sig_kept
                    print(
                        f"   🎯 시그니처 백로그 레인: {sig_rescued_count}개 AI 재심사 투입 "
                        f"(흉터/안면비대칭, 최신 게이트 재탈락 {sig_gate_rejected}개)"
                    )
                elif sig_gate_rejected:
                    print(
                        f"   🎯 시그니처 백로그 레인: 최신 게이트 재탈락 {sig_gate_rejected}개, 투입 0개"
                    )
            except Exception as e:
                logger.warning(f"시그니처 백로그 레인 실패 (계속 진행): {e}")

        # 본문 enrichment — AI가 snippet(~150자)이 아닌 실제 본문/답변을 보고
        # 판정하도록 KIN/blog 공개 표면을 보강하고, 드러난 광고는 즉시 재탈락.
        if ai_targets and enrich_bodies:
            try:
                before_enrich = len(ai_targets)
                ai_targets, enrich_stats = self._enrich_and_regate_ai_targets(
                    ai_targets,
                    max_fetch=int(enrich_bodies),
                )
                if enrich_stats["fetched"]:
                    print(
                        f"   📄 본문 enrichment: fetch {enrich_stats['fetched']}건 → "
                        f"보강 {enrich_stats['enriched']}건, 게시일 복원 {enrich_stats['dated']}건, "
                        f"게이트 재탈락 {enrich_stats['regate_rejected']}건, "
                        f"타이밍 만료 {enrich_stats['stale_rejected']}건 "
                        f"(AI 후보 {before_enrich} → {len(ai_targets)})"
                    )
                if len(ai_targets) < before_enrich and rest_targets:
                    refill_fetch_budget = max(
                        0,
                        int(enrich_bodies) - int(enrich_stats.get("fetched", 0) or 0),
                    )
                    ai_targets, rest_targets, refill_stats = self._refill_ai_targets_after_enrichment(
                        ai_targets,
                        rest_targets,
                        target_count=before_enrich,
                        max_fetch=refill_fetch_budget,
                    )
                    if refill_stats["attempted"]:
                        print(
                            f"   🔁 AI 후보 보충: 후보 {refill_stats['attempted']}개 검토 → "
                            f"{refill_stats['kept']}개 보충, 재탈락 {refill_stats['rejected']}개 "
                            f"(fetch {refill_stats['fetched']}건, 보강 {refill_stats['enriched']}건)"
                        )
            except Exception as e:
                logger.warning(f"본문 enrichment 실패 (계속 진행): {e}")

        if ai_targets:
            ai_category_counts: Dict[str, int] = {}
            ai_category_lens_counts: Dict[str, int] = {}
            for target in ai_targets:
                category = _ai_quota_category(target)
                lens = _ai_target_execution_lens(target)
                ai_category_counts[category] = ai_category_counts.get(category, 0) + 1
                category_lens = f"{category}::{lens}"
                ai_category_lens_counts[category_lens] = ai_category_lens_counts.get(category_lens, 0) + 1
            quota_summary = ", ".join(
                f"{category} {count}"
                for category, count in sorted(ai_category_counts.items())
            )
            lens_summary = ", ".join(
                f"{lane} {count}"
                for lane, count in sorted(ai_category_lens_counts.items())
            )
            print(f"   🎛️ AI 분석 카테고리 배분: {quota_summary}")
            if lens_summary:
                print(f"   🎚️ AI 분석 렌즈 배분: {lens_summary}")

        # 나머지(raw)는 먼저 DB에 저장하여 즉시 보존
        raw_saved = 0
        if rest_targets:
            final_gate_removed = 0
            final_gate_saved = 0
            raw_keep: List[ViralTarget] = []
            for t in rest_targets:
                reject_reason = CommentableFilter.apply_final_reject(t)
                if reject_reason:
                    final_gate_removed += 1
                    try:
                        if self.db.insert_viral_target(t.to_dict()):
                            final_gate_saved += 1
                    except Exception as e:
                        logger.warning(f"Raw 최종 게이트 제외 상태 저장 실패: {e}")
                    continue
                raw_keep.append(t)
            rest_targets = raw_keep

            print(f"\n💾 Raw 백로그 저장 (AI 제외 {len(rest_targets)}개, pending 큐 제외)...")
            if final_gate_removed:
                print(f"   🧹 최종 게이트 제외: {final_gate_removed}개 (상태 저장 {final_gate_saved}개)")
            for t in rest_targets:
                t.comment_status = "raw_backlog"
                if self.db.insert_viral_target(t.to_dict()):
                    raw_saved += 1
            print(f"   ✅ Raw {raw_saved}개 저장 완료")

        # AI 통합 분석 (병렬 + 증분 DB 저장)
        analyzed_targets: List[ViralTarget] = []
        if ai_targets:
            print(f"\n🔬 AI 통합 분석 중 (상위 {len(ai_targets)}개, 병렬 {ai_parallel})...")
            if progress_callback:
                progress_callback("AI분석중", len(keywords), len(keywords),
                                  f"{len(ai_targets)}개 타겟 AI 분석 중...")

            # 체크포인트에서 이미 분석한 배치 인덱스 로드 (ai_processed_batches)
            cp_path = self._checkpoint_path()
            already_done_batches: set = set()
            ai_batch_size = 25
            try:
                ai_batch_size = int(
                    self.generator._load_prompts()
                    .get('unified_analysis', {})
                    .get('batch_size', ai_batch_size)
                )
            except Exception:
                ai_batch_size = 25
            if os.path.exists(cp_path):
                try:
                    with open(cp_path, 'r', encoding='utf-8') as f:
                        cp = json.load(f)
                    already_done_batches = set(cp.get('ai_processed_batches') or [])
                except Exception:
                    pass

            resumed_analyzed_targets: List[ViralTarget] = []
            if already_done_batches:
                resumed_urls = self._urls_for_batch_indices(
                    ai_targets,
                    ai_batch_size,
                    already_done_batches,
                )
                resumed_analyzed_targets = self._load_existing_targets_by_urls(resumed_urls)
                print(
                    f"   ♻️ AI 체크포인트 복원: 배치 {len(already_done_batches)}개, "
                    f"DB 결과 {len(resumed_analyzed_targets)}개 합산"
                )

            def save_progress(done_batch_indices: set):
                """현재까지 분석된 배치 인덱스를 체크포인트에 저장"""
                try:
                    cp_data = {}
                    if os.path.exists(cp_path):
                        with open(cp_path, 'r', encoding='utf-8') as f:
                            cp_data = json.load(f)
                    cp_data['ai_processed_batches'] = sorted(done_batch_indices)
                    cp_data['ai_saved_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
                    atomic_write_json(cp_path, cp_data, indent=None)
                except Exception as e:
                    logger.warning(f"AI 체크포인트 저장 실패: {e}")

            newly_analyzed_targets = self.generator.unified_analysis_parallel(
                ai_targets,
                batch_size=ai_batch_size,
                max_workers=ai_parallel,
                db=self.db,
                skip_batch_indices=already_done_batches,
                on_batch_done=save_progress,
            )
            analyzed_targets = resumed_analyzed_targets + newly_analyzed_targets

        # 총 저장 수: raw + AI로 분석되어 이미 저장된 것
        saved = raw_saved + len(analyzed_targets)
        filtered = analyzed_targets + rest_targets  # 리포팅용 (정렬 순서 유지 안 됨)

        # HOT LEAD 즉시 알림 (Telegram) — Tier 구분
        # Tier 1 (점수 120+ 또는 경쟁사 탐지): 즉시 상위 10건 푸시
        # Tier 2 (100~119): daily_brief.py가 오전 09:00 요약
        # Tier 3 (그 외): 대시보드에서만 확인
        if analyzed_targets:
            tier1 = [
                t for t in analyzed_targets
                if (t.priority_score or 0) >= 120 or getattr(t, 'category', '') == '경쟁사_역공략'
            ]
            if tier1:
                try:
                    from alert_bot import TelegramBot
                    bot = TelegramBot()

                    top = sorted(tier1, key=lambda x: x.priority_score or 0, reverse=True)[:10]
                    message = (
                        f"🔥 **Tier 1 HOT LEAD {len(tier1)}건 발견** (점수 120+ 또는 경쟁사 탐지)\n"
                        f"상위 {len(top)}건만 표시, 나머지는 대시보드에서 확인:\n\n"
                    )
                    for i, lead in enumerate(top, 1):
                        platform_icon = {"cafe": "☕", "blog": "📝", "kin": "❓"}.get(lead.platform, "📌")
                        badge = "⚔️" if getattr(lead, 'category', '') == '경쟁사_역공략' else ""
                        reason = "score>=120" if (lead.priority_score or 0) >= 120 else "competitor"
                        message += f"{i}. {platform_icon}{badge} [{lead.platform.upper()}] 점수 {lead.priority_score:.0f} | {reason}\n"
                        message += f"   {lead.title[:60]}\n"
                        message += f"   {lead.url}\n\n"

                    total_rest = len(analyzed_targets) - len(tier1)
                    if total_rest > 0:
                        message += f"ℹ️ Tier 2/3 {total_rest}건은 오전 Daily Brief로 요약 전송됩니다."

                    bot.send_message(message)
                    print(f"   📱 Tier 1 {len(tier1)}건 Telegram 알림 발송 (상위 10건)")
                except Exception as e:
                    logger.warning(f"Telegram 알림 실패: {e}")
            else:
                print(f"   ℹ️ Tier 1 HOT LEAD 없음 — 즉시 알림 스킵 (Daily Brief에서 요약)")

        failed_ai_batches = set(getattr(self.generator, "last_failed_ai_batches", set()) or set())
        if failed_ai_batches:
            print(
                f"   ⚠️ AI 실패 배치 {len(failed_ai_batches)}개가 남아 "
                f"체크포인트를 보존합니다. 다음 실행에서 재시도됩니다."
            )
        else:
            # 체크포인트 삭제 (성공 완료)
            self._clear_checkpoint()

        # CSV 자동 저장
        csv_path = None
        if filtered:
            import csv
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = os.path.join(self.cfg.root_dir, 'reports', f'viral_targets_{timestamp}.csv')
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)

            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'rank', 'platform', 'title', 'priority_score', 'exposure_score',
                    'workability_score', 'conversion_fit_score', 'viral_need_score',
                    'viral_need_tier', 'viral_need_signals', 'reply_opportunity_score',
                    'reply_opportunity_tier', 'reply_opportunity_signals', 'timing_window_score',
                    'timing_window_tier', 'timing_window_signals', 'journey_fit_score',
                    'journey_stage', 'journey_signals', 'qualification_fit_score',
                    'qualification_tier', 'qualification_signals', 'manual_review',
                    'reply_risk_flags', 'search_sort', 'search_rank', 'keyword', 'url'
                ])
                for i, t in enumerate(filtered, 1):
                    breakdown = t.score_breakdown or {}
                    writer.writerow([
                        i,
                        t.platform,
                        t.title,
                        t.priority_score,
                        t.exposure_score,
                        t.workability_score,
                        t.conversion_fit_score,
                        breakdown.get('viral_need_score', 0),
                        breakdown.get('viral_need_tier', ''),
                        breakdown.get('viral_need_signals', ''),
                        breakdown.get('reply_opportunity_score', 0),
                        breakdown.get('reply_opportunity_tier', ''),
                        breakdown.get('reply_opportunity_signals', ''),
                        breakdown.get('timing_window_score', 0),
                        breakdown.get('timing_window_tier', ''),
                        breakdown.get('timing_window_signals', ''),
                        breakdown.get('journey_fit_score', 0),
                        breakdown.get('journey_stage', ''),
                        breakdown.get('journey_signals', ''),
                        breakdown.get('qualification_fit_score', 0),
                        breakdown.get('qualification_tier', ''),
                        breakdown.get('qualification_signals', ''),
                        breakdown.get('manual_review', 0),
                        breakdown.get('reply_risk_flags', ''),
                        t.search_sort,
                        t.search_rank,
                        ', '.join(t.matched_keywords[:3]) if t.matched_keywords else '',
                        t.url
                    ])

        # 디스커버리 감사: 이번 런의 카테고리/쿼리구조별 수율을 영속화
        audit_summary = None
        try:
            audit_summary = self._persist_viral_discovery_audit(
                run_started_at,
                source_scan_run_id=source_scan_run_id,
                keyword_count=len(keywords),
            )
        except Exception as e:
            logger.warning(f"디스커버리 감사 저장 실패: {e}")

        # API 통계
        api_stats = self.searcher.get_stats()

        print(f"\n{'='*60}")
        print(f"✅ 스캔 완료!")
        print(f"   총 발견: {len(all_targets)}개")
        print(f"   필터링 후: {len(filtered)}개")
        print(f"   DB 저장: {saved}개")
        if rescued_count:
            print(f"   ♻️ 백로그 레스큐 재심사: {rescued_count}개")
        dropped_variants = getattr(self, "_variant_drop_counts", {}) or {}
        if dropped_variants:
            drop_summary = ", ".join(
                f"{name}x{count}" for name, count in sorted(dropped_variants.items())
            )
            print(f"   ✂️ 제로수율 변형 차단: {drop_summary}")
        dropped_platforms = getattr(self, "_platform_drop_counts", {}) or {}
        if dropped_platforms:
            factors = self._load_platform_yield_factors()
            plat_summary = ", ".join(
                f"{p} -{n}(가중 {factors.get(p, 1.0):.2f})"
                for p, n in sorted(dropped_platforms.items(), key=lambda kv: -kv[1])
            )
            print(f"   ⚖️ 플랫폼 수율 예산 절감: {plat_summary}")
        blocked_structures = getattr(getattr(self, "seed_builder", None), "_structure_blocked_buckets", {}) or {}
        if blocked_structures:
            struct_summary = ", ".join(
                f"{b}x{n}" for b, n in sorted(blocked_structures.items(), key=lambda kv: -kv[1])[:8]
            )
            print(f"   🚫 제로수율 구조 시드 차단: {struct_summary}")
        demand_adjustments = getattr(getattr(self, "seed_builder", None), "_category_demand_adjustments", {}) or {}
        if demand_adjustments:
            demand_summary = ", ".join(
                f"{cat} {info['original']}→{info['adjusted']}({info['accept_rate'] * 100:.1f}%)"
                for cat, info in sorted(demand_adjustments.items(), key=lambda kv: kv[1]["original"] - kv[1]["adjusted"], reverse=True)[:8]
            )
            print(f"   📉 저수요 진료축 예산 절감: {demand_summary}")
        demand_boosts = getattr(getattr(self, "seed_builder", None), "_category_demand_boosts", {}) or {}
        if demand_boosts:
            boost_summary = ", ".join(f"{cat} +{n}" for cat, n in sorted(demand_boosts.items(), key=lambda kv: -kv[1]))
            print(f"   📈 시그니처 축 예산 재투입: {boost_summary}")
        if audit_summary:
            audit_totals = audit_summary['summary']
            print(
                f"   🧭 디스커버리 감사 #{audit_summary.get('audit_id')}: "
                f"발견 {audit_totals['discovered']}개(신규 {audit_totals.get('fresh_discovered', 0)}개) "
                f"→ actionable {audit_totals['pending']}개(실대기 {audit_totals.get('open_pending', 0)}개, "
                f"신규 {audit_totals.get('fresh_pending', 0)}개) "
                f"({audit_totals['pending_rate']:.1%}, 신규 {audit_totals.get('fresh_pending_rate', 0.0):.1%}), "
                f"AI탈락 {audit_totals.get('ai_filtered', 0)}개, 광고필터 {audit_totals['ad_rate']:.0%}, "
                f"제로수율 시드 {len(audit_summary['zero_yield_seeds'])}개"
            )
            focus_coverage = audit_summary.get('focus_axis_coverage') or {}
            if focus_coverage:
                total_focus = int(focus_coverage.get('total_focus_categories') or 0)
                print(
                    f"   🧩 핵심축 커버리지: 발견 "
                    f"{focus_coverage.get('covered_focus_categories', 0)}/{total_focus}, "
                    f"actionable {focus_coverage.get('actionable_focus_categories', 0)}/{total_focus}, "
                    f"실대기 {focus_coverage.get('open_pending_focus_categories', 0)}/{total_focus}"
                )
                priority_missing = [
                    category for category in (focus_coverage.get('missing_actionable_categories') or [])
                    if category in set(focus_coverage.get('priority_focus_categories') or [])
                ]
                if priority_missing:
                    print(f"   ⚠️ actionable 누락 핵심축: {', '.join(priority_missing[:8])}")
        if csv_path:
            print(f"   📁 CSV: {csv_path}")
        print(f"\n📊 API 통계:")
        print(f"   요청: {api_stats['requests']}건 | 캐시 히트: {api_stats['cache_hits']}건")
        print(f"   에러: {api_stats['errors']}건 ({api_stats['error_rate']})")
        print(f"{'='*60}\n")

        if progress_callback:
            hot_count = len([t for t in filtered if "🔥" in t.content_preview or "🔥HOT" in t.content_preview])
            progress_callback("완료", len(keywords), len(keywords),
                            f"✅ 완료! 총 {saved}개 저장 (🔥HOT {hot_count}개)")

        return filtered

    def generate_comments(self, limit: int = 10, status: str = 'pending') -> List[ViralTarget]:
        """
        pending 상태의 타겟에 대해 AI 댓글 생성

        Args:
            limit: 생성할 최대 수
            status: 필터링할 상태

        Returns:
            댓글이 생성된 타겟 리스트
        """
        print(f"\n{'='*60}")
        print(f"🤖 AI 댓글 생성 시작")
        print(f"   대상 상태: {status}")
        print(f"   최대 생성: {limit}개")
        print(f"{'='*60}\n")

        # DB에서 pending 타겟 조회
        targets_data = self.db.get_viral_targets(status=status, limit=limit)

        if not targets_data:
            print("⚠️ 생성할 타겟이 없습니다.")
            return []

        # ViralTarget 객체로 변환
        targets = []
        for data in targets_data:
            target = ViralTarget(
                platform=data.get('platform', 'unknown'),
                url=data.get('url', ''),
                title=data.get('title', ''),
                content_preview=data.get('content_preview', ''),
                matched_keywords=json.loads(data.get('matched_keywords', '[]')),
                category=data.get('category', '기타'),
                priority_score=data.get('priority_score', 0)
            )
            targets.append(target)

        # 댓글 생성
        generated = self.generator.batch_generate(targets, limit)

        # DB 업데이트
        updated = 0
        for target in generated:
            if target.generated_comment:
                self.db.update_viral_target(target.id, {
                    'generated_comment': target.generated_comment,
                    'comment_status': 'generated'
                })
                updated += 1

        print(f"\n{'='*60}")
        print(f"✅ 댓글 생성 완료!")
        print(f"   생성됨: {updated}개")
        print(f"{'='*60}\n")

        return generated

    def get_stats(self) -> dict:
        """현재 통계 조회"""
        return self.db.get_viral_stats()

    def list_targets(self, status: str = None, platform: str = None,
                     category: str = None, date_filter: str = None,
                     platforms: list = None, comment_status: str = None,
                     min_scan_count: int = None,
                     search: str = None, sort: str = None,
                     scan_batch: str = None, limit: int = 50,
                     offset: int = 0) -> List[dict]:
        """타겟 목록 조회 (필터링 및 정렬 지원)"""
        return self.db.get_viral_targets(
            status=status, platform=platform, category=category,
            date_filter=date_filter, platforms=platforms,
            comment_status=comment_status,
            min_scan_count=min_scan_count, search=search, sort=sort,
            scan_batch=scan_batch, limit=limit, offset=offset
        )


# ============================================
# CLI 인터페이스
# ============================================
def main():
    parser = argparse.ArgumentParser(description="Viral Hunter - 바이럴 마케팅 타겟 발굴")
    parser.add_argument('--scan', action='store_true', help='타겟 스캔 실행')
    parser.add_argument('--generate', action='store_true', help='AI 댓글 생성')
    parser.add_argument('--stats', action='store_true', help='통계 출력')
    parser.add_argument('--list', action='store_true', help='타겟 목록 출력')
    parser.add_argument('--limit-keywords', type=int, default=None, help='스캔할 키워드 수 제한')
    parser.add_argument('--limit', type=int, default=10, help='댓글 생성 수 제한')
    parser.add_argument('--keyword', type=str, help='특정 키워드로 검색')
    parser.add_argument('--test-search', action='store_true', help='검색 테스트')
    parser.add_argument('--test-comment', action='store_true', help='댓글 생성 테스트')
    parser.add_argument('--no-db', action='store_true', help='DB 저장 없이 결과만 출력 (WSL 호환)')
    parser.add_argument('--fresh', action='store_true', help='체크포인트 무시하고 처음부터 스캔')
    parser.add_argument('--legacy-keywords', action='store_true', help='최신 Legion curated seed 대신 기존 누적 키워드 로더 사용')
    parser.add_argument('--source-scan-id', type=int, default=None, help='특정 Pathfinder/Legion scan_run_id 기반 seed로 실행')
    parser.add_argument('--checkpoint-every', type=int, default=20, help='N개 키워드마다 체크포인트 저장 (기본 20)')
    parser.add_argument('--top-n-for-ai', type=int, default=300, help='AI 분석 대상 상위 N개 (나머지는 raw_backlog 저장, 기본 300)')
    parser.add_argument('--ai-parallel', type=int, default=5, help='AI 병렬 호출 수 (기본 5)')
    parser.add_argument('--rescue-backlog', type=int, default=60,
                        help='최근 raw_backlog/needs_ai_retry 타겟을 추가로 AI 재심사할 최대 수 (0=비활성, 기본 60)')
    parser.add_argument('--rescue-signature', type=int, default=40,
                        help='시그니처 축(흉터/안면비대칭) raw_backlog를 확장 윈도우(180일)+카테고리 우선으로 재심사할 최대 수 (0=비활성, 기본 40)')
    parser.add_argument('--enrich-bodies', type=int, default=120,
                        help='AI 분석 전 KIN/blog 본문을 HTTP로 보강할 최대 fetch 수 (0=비활성, 기본 120)')
    parser.add_argument('--skip-pending-expiry', action='store_true',
                        help='스캔 시작 시 pending TTL 만료 정리를 건너뜀 (기본: 실행)')
    parser.add_argument('--boost-category', action='append', default=[], help='먼저 실행할 Pathfinder 진료축 lane')
    parser.add_argument('--boost-lens', action='append', default=[], help='먼저 실행할 Pathfinder 실행렌즈 lane')

    args = parser.parse_args()

    # 테스트 모드는 DB 없이 실행
    if args.test_search:
        keyword = args.keyword or "청주 다이어트"
        print(f"\n🔍 검색 테스트: '{keyword}'")
        searcher = NaverUnifiedSearch()
        results = searcher.search_all(keyword, max_per_platform=5)
        print(f"\n총 {len(results)}개 결과:\n")
        for r in results[:15]:
            print(f"  [{r.platform}] {r.title[:50]}...")
            print(f"       URL: {r.url[:70]}...")
        return

    if args.test_comment:
        # 댓글 생성 테스트 (DB 없이)
        generator = AICommentGenerator()
        test_target = ViralTarget(
            platform="kin",
            url="https://kin.naver.com/test",
            title="청주 다이어트 한의원 추천해주세요",
            content_preview="다이어트를 시작하려고 하는데 청주에 좋은 한의원 있을까요?",
            matched_keywords=["청주 다이어트", "한의원 추천"]
        )
        print(f"\n🤖 댓글 생성 테스트")
        print(f"   제목: {test_target.title}")
        comment = generator.generate(test_target)
        print(f"\n   생성된 댓글:\n   {comment}")
        return

    # --no-db 모드: DB 저장 없이 스캔만 실행
    if args.no_db and args.scan:
        cfg = ConfigManager()
        searcher = NaverUnifiedSearch()
        filter_obj = CommentableFilter()
        generator = AICommentGenerator()

        # 키워드 로드
        seeds = ViralSeedBuilder().build(scan_run_id=args.source_scan_id)
        keywords = [seed.keyword for seed in seeds] or ["청주 한의원", "청주 다이어트"]
        if args.limit_keywords:
            keywords = keywords[:args.limit_keywords]

        print(f"\n{'='*60}")
        print(f"🎯 Viral Hunter 스캔 (DB 저장 안함)")
        print(f"   키워드: {len(keywords)}개")
        print(f"   플랫폼: 카페, 블로그, 지식인")
        print(f"{'='*60}\n")

        all_targets = []
        seen_urls = set()

        for i, kw in enumerate(keywords, 1):
            print(f"[{i}/{len(keywords)}] '{kw}' 검색 중...")
            results = searcher.search_all(kw, max_per_platform=15)

            for target in results:
                canonical_key = canonicalize_viral_url(target.url) or target.url
                if canonical_key not in seen_urls:
                    seen_urls.add(canonical_key)
                    all_targets.append(target)

            if i % 5 == 0:
                print(f"   📊 진행: {i}/{len(keywords)} | 수집: {len(all_targets)}개")

        # 필터링
        print(f"\n🔍 필터링 중...")
        filtered = filter_obj.filter(all_targets)

        # AI 통합 분석 (경쟁사 탐지 + 댓글 응대 적합도 평가를 하나로)
        if filtered:
            print(f"\n🔬 AI 통합 분석 중 (경쟁사 탐지 + 댓글 응대 적합도)...")
            before_count = len(filtered)
            filtered = generator.unified_analysis(filtered, batch_size=25)
            print(f"   통합 분석 완료: {before_count}개 → {len(filtered)}개 (응대적합)")

        # 결과 출력
        print(f"\n{'='*60}")
        print(f"✅ 스캔 완료!")
        print(f"   총 발견: {len(all_targets)}개")
        print(f"   응대적합: {len(filtered)}개")
        print(f"{'='*60}\n")

        # CSV 자동 저장
        if filtered:
            import csv
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = os.path.join(cfg.root_dir, 'reports', f'viral_targets_{timestamp}.csv')
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)

            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'rank', 'platform', 'title', 'url', 'priority_score', 'exposure_score',
                    'workability_score', 'conversion_fit_score', 'viral_need_score',
                    'viral_need_tier', 'viral_need_signals', 'reply_opportunity_score',
                    'reply_opportunity_tier', 'reply_opportunity_signals', 'timing_window_score',
                    'timing_window_tier', 'timing_window_signals', 'journey_fit_score',
                    'journey_stage', 'journey_signals', 'qualification_fit_score',
                    'qualification_tier', 'qualification_signals', 'manual_review',
                    'reply_risk_flags', 'search_sort', 'search_rank', 'keywords',
                    'is_competitor', 'counter_score'
                ])
                for i, t in enumerate(filtered, 1):
                    breakdown = t.score_breakdown or {}
                    writer.writerow([
                        i,
                        t.platform,
                        t.title,
                        t.url,
                        t.priority_score,
                        t.exposure_score,
                        t.workability_score,
                        t.conversion_fit_score,
                        breakdown.get('viral_need_score', 0),
                        breakdown.get('viral_need_tier', ''),
                        breakdown.get('viral_need_signals', ''),
                        breakdown.get('reply_opportunity_score', 0),
                        breakdown.get('reply_opportunity_tier', ''),
                        breakdown.get('reply_opportunity_signals', ''),
                        breakdown.get('timing_window_score', 0),
                        breakdown.get('timing_window_tier', ''),
                        breakdown.get('timing_window_signals', ''),
                        breakdown.get('journey_fit_score', 0),
                        breakdown.get('journey_stage', ''),
                        breakdown.get('journey_signals', ''),
                        breakdown.get('qualification_fit_score', 0),
                        breakdown.get('qualification_tier', ''),
                        breakdown.get('qualification_signals', ''),
                        breakdown.get('manual_review', 0),
                        breakdown.get('reply_risk_flags', ''),
                        t.search_sort,
                        t.search_rank,
                        ', '.join(t.matched_keywords) if t.matched_keywords else '',
                        getattr(t, 'is_competitor', False),
                        getattr(t, 'counter_score', 0)
                    ])
            print(f"📁 CSV 저장: {csv_path}")

        # 상위 결과 출력
        print(f"\n📋 상위 타겟 (우선순위순 상위 20개):")
        print("-" * 60)
        for i, t in enumerate(filtered[:20], 1):
            print(f"{i:2}. [{t.platform:5}] {t.title[:45]}...")
            print(f"     점수: {t.priority_score:.0f} | 키워드: {', '.join(t.matched_keywords[:2])}")
            print(f"     URL: {t.url[:65]}...")
            print()

        # AI 댓글 생성 (선택적)
        if args.generate and filtered:
            print(f"\n🤖 AI 댓글 생성 (상위 {min(args.limit, len(filtered))}개):")
            print("-" * 60)
            for t in filtered[:args.limit]:
                comment = generator.generate(t)
                print(f"\n[{t.platform}] {t.title[:40]}...")
                print(f"💬 {comment}")

        return

    # DB 필요한 명령어들은 여기서 hunter 초기화
    hunter = ViralHunter()

    if args.scan:
        # 스캔 실행
        keywords = [args.keyword] if args.keyword else None
        hunter.hunt(keywords=keywords, limit_keywords=args.limit_keywords,
                    fresh=args.fresh, checkpoint_every=args.checkpoint_every,
                    top_n_for_ai=args.top_n_for_ai, ai_parallel=args.ai_parallel,
                    use_latest_legion=not args.legacy_keywords,
                    source_scan_run_id=args.source_scan_id,
                    boost_categories=args.boost_category,
                    boost_lenses=args.boost_lens,
                    rescue_backlog=args.rescue_backlog,
                    rescue_signature=args.rescue_signature,
                    enrich_bodies=args.enrich_bodies,
                    expire_pending=not args.skip_pending_expiry)
        return

    if args.generate:
        # 댓글 생성
        hunter.generate_comments(limit=args.limit)
        return

    if args.stats:
        # 통계 출력
        stats = hunter.get_stats()
        print(f"\n📊 Viral Hunter 통계")
        print(f"   총 타겟: {stats.get('total', 0)}개")
        print(f"   오늘 발견: {stats.get('today', 0)}개")
        print(f"\n   플랫폼별:")
        for platform, count in stats.get('by_platform', {}).items():
            print(f"      {platform}: {count}개")
        print(f"\n   상태별:")
        for status, count in stats.get('by_status', {}).items():
            print(f"      {status}: {count}개")
        return

    if args.list:
        # 목록 출력
        targets = hunter.list_targets(limit=args.limit)
        print(f"\n📋 타겟 목록 (상위 {len(targets)}개)")
        for t in targets:
            status_icon = "⏳" if t['comment_status'] == 'pending' else "✅"
            print(f"  {status_icon} [{t['platform']}] {t['title'][:40]}...")
            print(f"       점수: {t['priority_score']:.0f} | 상태: {t['comment_status']}")
        return

    # 기본: 도움말 출력
    parser.print_help()


if __name__ == "__main__":
    main()

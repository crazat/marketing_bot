"""Quality audit for the Pathfinder -> Viral Hunter handoff.

The audit is intentionally read-only. It summarizes whether Pathfinder seeds
are turning into usable Viral Hunter targets by treatment axis, keyword grade,
and execution lens.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from core_services.gyulim_keyword_profile import ACTIVE_KEYWORD_PROFILE
from core_services.viral_seed_builder import canonical_category_for_keyword
from core_services.viral_url_canonicalizer import canonicalize_viral_url


ACTIONABLE_STATUSES = {"pending", "generated", "posted", "approved", "ai_approved"}
SURVIVED_STATUSES = ACTIONABLE_STATUSES | {"raw_backlog"}
FILTERED_PREFIXES = ("filtered_out",)
CURRENT_REJECT_STATUS_BY_REASON = {
    "advertorial": "filtered_out_ad",
    "medical_promo": "filtered_out_ad",
    "stale_window": "filtered_out_stale_window",
    "journey_mismatch": "filtered_out_journey_mismatch",
    "unqualified_lead": "filtered_out_unqualified_lead",
    "clinic_mismatch": "filtered_out_clinic_mismatch",
    "low_intent": "filtered_out_low_intent",
    "low_opportunity": "filtered_out_low_opportunity",
    "low_worksite_efficiency": "filtered_out_low_worksite_efficiency",
}
PRIORITY_FOCUS_CATEGORIES = (
    "흉터/여드름흉터",
    "안면비대칭",
    "피부/여드름",
    "다이어트",
    "체형교정",
    "리프팅/탄력",
    "교통사고",
)
PATIENT_JOURNEY_LENSES = (
    "review",
    "community",
    "cost",
    "consultation",
    "availability",
    "safety",
)
WORK_QUEUE_CATEGORY_TARGET = 5
WORK_QUEUE_CATEGORY_LENS_TARGET = 2
FRESH_WORK_QUEUE_DAYS = 14
OPPORTUNITY_DIVERSITY_MIN_PLATFORMS = 2
OPPORTUNITY_DIVERSITY_MIN_SOURCE_SEEDS = 2
OPPORTUNITY_DIVERSITY_MIN_VARIANT_FAMILIES = 2
TREATMENT_SIGNAL_DIVERSITY_CATEGORY_MIN_TERMS = 4
TREATMENT_SIGNAL_DIVERSITY_CATEGORY_LENS_MIN_TERMS = 2
TREATMENT_SUBINTENT_CATEGORY_TARGET = WORK_QUEUE_CATEGORY_TARGET
TREATMENT_SUBINTENT_CATEGORY_LENS_TARGET = WORK_QUEUE_CATEGORY_LENS_TARGET
TREATMENT_SUBINTENT_CATEGORY_MIN_BUCKETS = 3
TREATMENT_SUBINTENT_CATEGORY_LENS_MIN_BUCKETS = 2
EXECUTION_PRIORITY_CATEGORY_TOP_WINDOW = 8
EXECUTION_PRIORITY_CATEGORY_LENS_TOP_WINDOW = 3
SEED_CANDIDATE_ALIGNMENT_MIN_OVERLAP = 2
SEED_CANDIDATE_ALIGNMENT_MIN_RATIO = 0.34
REPLY_WORKABILITY_SCORE_READY = 55.0
REPLY_WORKABILITY_RISK_PENALTY_BLOCK = -40.0
REPLY_WORKABILITY_READY_TIERS = {"assist_now", "good"}
REANALYSIS_RESCUE_MIN_PRIORITY = 115.0
REANALYSIS_RESCUE_MIN_AXIS_FIT = 80.0
REANALYSIS_RESCUE_MIN_LENS_FIT = 70.0
REANALYSIS_RESCUE_MIN_REPLY_SCORE = 75.0
DISCARDED_EXECUTION_RESCUE_MIN_PRIORITY = 115.0
DISCARDED_EXECUTION_RESCUE_MIN_REPLY_SCORE = 55.0
DISCARDED_EXECUTION_AUTO_REQUEUE_STATUSES = {
    "filtered_out",
    "filtered_out_ad",
    "filtered_out_ai",
    "filtered_out_clinic_mismatch",
    "filtered_out_journey_mismatch",
    "filtered_out_low_intent",
    "filtered_out_low_opportunity",
    "filtered_out_unqualified_lead",
}
DISCARDED_EXECUTION_MANUAL_REVIEW_STATUSES = {"deleted", "skipped"}
SOURCE_LINEAGE_MIN_SOURCE_SEED_COVERAGE = 0.90
SOURCE_LINEAGE_MIN_PRIORITY_FOCUS_SOURCE_SEED_COVERAGE = 0.90
SOURCE_LINEAGE_MIN_ACTIONABLE_STRICT_SOURCE_SEED_COVERAGE = 0.90
SOURCE_LINEAGE_MIN_QUERY_VARIANT_COVERAGE = 0.80
LOCAL_AREA_DIVERSITY_CATEGORY_MIN_AREAS = 3
LOCAL_AREA_DIVERSITY_CATEGORY_LENS_MIN_AREAS = 2
CLINIC_MODALITY_CATEGORY_TARGET = WORK_QUEUE_CATEGORY_TARGET
CLINIC_MODALITY_CATEGORY_LENS_TARGET = WORK_QUEUE_CATEGORY_LENS_TARGET
DECISION_WINDOW_CATEGORY_TARGET = WORK_QUEUE_CATEGORY_TARGET
DECISION_WINDOW_CATEGORY_LENS_TARGET = WORK_QUEUE_CATEGORY_LENS_TARGET
COMPLIANCE_SEVERE_RISK_FLAGS = {
    "urgent_medical",
    "medication_advice_request",
    "acute_side_effect",
}
COMPLIANCE_REVIEW_RISK_FLAGS = {
    "sensitive_medical",
    "testimonial_sensitive",
    "generic_category",
}
CONTENT_REPLY_RISK_PATTERNS: Dict[str, tuple[str, ...]] = {
    "urgent_medical": (
        "응급",
        "응급실",
        "119",
        "심한통증",
        "출혈",
        "마비",
        "호흡곤란",
        "emergency",
        "urgent",
        "ervisit",
    ),
    "sensitive_medical": (
        "임신",
        "수유",
        "청소년",
        "소아",
        "당뇨",
        "고혈압",
        "스테로이드",
        "pregnant",
        "breastfeeding",
        "steroid",
    ),
    "medication_advice_request": (
        "약먹어도",
        "복용",
        "처방",
        "약물",
        "medicine",
        "medication",
        "prescription",
        "dosage",
    ),
    "acute_side_effect": (
        "부작용",
        "감염",
        "염증",
        "발열",
        "알레르기",
        "sideeffect",
        "side-effect",
        "infection",
        "allergy",
    ),
    "testimonial_sensitive": (
        "전후사진",
        "효과보장",
        "치료후기",
        "beforeafter",
        "before/after",
        "guaranteedresult",
    ),
}
CONTENT_REPLY_RISK_PENALTIES = {
    "urgent_medical": -60.0,
    "sensitive_medical": -22.0,
    "medication_advice_request": -45.0,
    "acute_side_effect": -55.0,
    "testimonial_sensitive": -10.0,
}
CLINIC_MODALITY_POSITIVE_TERMS: tuple[str, ...] = (
    "한의원",
    "한방",
    "한약",
    "침",
    "침치료",
    "약침",
    "매선",
    "매선침",
    "새살침",
    "추나",
    "추나요법",
    "뜸",
    "부항",
    "다이어트한약",
    "한방다이어트",
    "감량한약",
    "한방리프팅",
)
CLINIC_MODALITY_OFFSCOPE_TERMS: tuple[str, ...] = (
    "피부과",
    "성형외과",
    "레이저",
    "프락셀",
    "레이저토닝",
    "토닝",
    "필러",
    "보톡스",
    "스킨부스터",
    "쥬베룩",
    "리쥬란",
    "인모드",
    "슈링크",
    "울쎄라",
    "지방흡입",
    "양악",
    "윤곽수술",
    "코수술",
    "쌍수",
    "위고비",
    "마운자로",
    "삭센다",
    "오젬픽",
    "다이어트주사",
    "비만주사",
    "식욕억제제",
    "피부과약",
    "항생제",
    "미노씬",
    "독시사이클린",
    "스테로이드",
    "양약",
)
CLINIC_MODALITY_BRIDGE_TERMS: tuple[str, ...] = (
    "말고",
    "대신",
    "비교",
    "차이",
    "vs",
    "브이에스",
    "보다",
    "한의원으로",
    "한방으로",
    "한약으로",
    "침으로",
)
CLINIC_MODALITY_STRONG_BRIDGE_TERMS: tuple[str, ...] = (
    "말고",
    "대신",
    "한의원으로",
    "한방으로",
    "한약으로",
    "침으로",
)
DECISION_WINDOW_ACTIVE_TERMS: tuple[str, ...] = (
    "?",
    "궁금",
    "추천",
    "어디",
    "어떤",
    "어떻게",
    "고민",
    "찾고",
    "찾아요",
    "알아보고",
    "알려",
    "비용",
    "가격",
    "얼마",
    "상담",
    "문의",
    "예약",
    "가능",
    "오늘",
    "주말",
    "야간",
    "근처",
    "가까운",
    "비교",
    "차이",
    "선택",
    "괜찮",
    "할까요",
    "해야",
    "되나요",
    "받아도",
)
DECISION_WINDOW_COMPLETED_TERMS: tuple[str, ...] = (
    "다녀왔",
    "받았",
    "받아봤",
    "해봤",
    "했습니다",
    "했어요",
    "완료",
    "끝났",
    "예약했",
    "예약완료",
    "이미",
    "지난달",
    "작년에",
    "예전에",
    "후기입니다",
    "치료후기",
    "시술후기",
    "수술후기",
    "내돈내산",
    "전후사진",
    "전후",
    "효과봤",
    "효과 보고",
    "리뷰 남",
)
TREATMENT_SUBINTENT_BUCKETS: Dict[str, Dict[str, tuple[str, ...]]] = {
    "흉터/여드름흉터": {
        "acne_scar": ("여드름흉터", "여드름자국", "패인흉터", "흉터치료"),
        "regeneration_hanbang": ("새살침", "흉터새살침", "흉터 새살침", "피부재생"),
        "pore_texture": ("모공흉터", "모공", "피부결"),
        "pigmentation": ("색소침착", "붉은자국", "갈색자국", "착색"),
        "surgery_wound": ("수술흉터", "상처흉터", "수두흉터", "켈로이드"),
    },
    "안면비대칭": {
        "facial_asymmetry": ("안면비대칭", "얼굴비대칭", "얼굴좌우차이", "좌우비대칭"),
        "jaw_tmj": ("턱비대칭", "턱관절", "턱", "교합"),
        "cheekbone_head": ("광대비대칭", "광대좌우차이", "두상비대칭", "머리비대칭"),
        "non_surgical_correction": ("비수술", "안면교정", "비대칭교정", "웨딩 안면비대칭"),
    },
    "피부/여드름": {
        "acne_trouble": ("여드름", "성인여드름", "피부트러블", "트러블", "피지"),
        "skin_condition": ("피부질환", "피부관리", "건선"),
        "dermatitis": ("아토피", "지루성피부염", "습진", "두드러기"),
        "redness_rosacea": ("홍조", "안면홍조", "열감"),
        "wart_pigment": ("편평사마귀", "색소", "기미", "잡티"),
    },
    "다이어트": {
        "diet_program": ("다이어트", "한방다이어트", "다이어트한약", "다이어트 한의원"),
        "weight_loss": ("비만", "체중", "감량", "살빼", "체지방"),
        "appetite_metabolism": ("식욕억제", "식욕", "대사", "요요"),
        "body_part": ("뱃살", "허벅지살", "팔뚝살", "복부"),
        "life_event": ("산후다이어트", "웨딩다이어트", "웨딩 다이어트"),
    },
    "체형교정": {
        "posture_correction": ("체형교정", "자세교정", "추나"),
        "pelvis_spine": ("골반교정", "골반틀어짐", "척추교정", "척추측만"),
        "neck_shoulder": ("거북목", "라운드숄더", "목", "어깨"),
        "leg_posture": ("휜다리", "오다리", "휜다리교정"),
        "posture_pain": ("통증", "허리", "허리통증"),
    },
    "리프팅/탄력": {
        "skin_aging": ("리프팅", "처짐", "노화", "얼굴라인"),
        "thread_lifting": ("매선", "매선리프팅", "침리프팅", "한방리프팅", "동안침", "매선침"),
        "elasticity_wrinkle": ("피부탄력", "탄력", "주름", "팔자주름"),
        "jawline_doublechin": ("이중턱", "턱선", "얼굴라인"),
    },
    "교통사고": {
        "accident_context": (
            "교통사고",
            "자동차사고",
            "추돌사고",
            "교통사고한의원",
            "교통사고 한의원",
            "자동차사고 한의원",
        ),
        "insurance_admin": ("자동차보험", "자보", "보험", "합의"),
        "neck_back_pain": ("목통증", "허리통증", "사고후통증", "통증", "두통"),
        "hospitalization": ("입원", "교통사고입원", "자동차사고입원"),
        "aftereffect": ("후유증", "교통사고후유증"),
    },
}
REPLY_WORKABILITY_GOOD_SIGNALS = {
    "clear_question_shape",
    "help_request_language",
    "decision_or_service_task",
    "situational_problem",
    "local_actionable",
    "service_match",
    "personal_context",
    "public_reply_surface",
    "unanswered_or_low_response",
    "low_response_count",
    "natural_reply_opening",
    "reply_welcome",
    "unanswered_thread",
    "low_response_thread",
    "visible_gap",
    "fresh_response_window",
    "decision_stage",
    "consideration_stage",
    "qualified_lead_context",
    "actionable_need",
}
ENGAGEMENT_HOOK_TERMS: tuple[str, ...] = (
    "?",
    "궁금",
    "추천",
    "어디",
    "어떤",
    "어떻게",
    "될까요",
    "인가요",
    "나요",
    "가능",
    "괜찮",
    "고민",
    "찾",
    "알려",
    "비용",
    "가격",
    "얼마",
    "상담",
    "문의",
    "예약",
    "주차",
    "후기",
    "경험",
    "부작용",
    "회복",
    "통증",
)
ENGAGEMENT_HOOK_LENS_TERMS: Dict[str, tuple[str, ...]] = {
    "review": ("후기", "추천", "경험", "가보", "어디", "괜찮"),
    "community": ("추천", "궁금", "어디", "가보", "괜찮", "고민"),
    "cost": ("비용", "가격", "얼마", "실비", "보험", "치료비", "부담"),
    "consultation": ("상담", "문의", "처방", "진단", "궁금", "가능"),
    "availability": ("예약", "주차", "근처", "가까운", "오늘", "주말", "야간", "시간"),
    "safety": ("부작용", "회복", "통증", "기간", "주의", "안전", "괜찮"),
}
TREATMENT_SIGNATURE_GENERIC_TERMS: tuple[str, ...] = (
    "청주",
    "한의원",
    "한방",
    "한약",
    "병원",
    "의원",
    "클리닉",
    "치료",
    "관리",
    "추천",
    "후기",
    "상담",
    "문의",
    "비용",
    "가격",
    "예약",
    "가능",
    "피부",
    "보험",
    "교정",
)
LENS_SURFACE_TERMS: Dict[str, tuple[str, ...]] = {
    "review": (
        "추천", "후기", "잘하는", "괜찮", "어디", "경험", "가본", "가보신", "해보신",
        "아시는", "리뷰", "review", "recommend",
    ),
    "community": (
        "추천", "후기", "어디", "경험", "가본", "가보신", "해보신", "아시는",
        "분들", "궁금", "부탁", "괜찮", "review", "recommend",
    ),
    "cost": (
        "비용", "가격", "얼마", "실비", "보험", "자보", "치료비", "부담",
        "cost", "price", "insurance",
    ),
    "consultation": (
        "상담", "문의", "처방", "진단", "상담받", "치료받", "검사받",
        "궁금", "알고싶", "consult", "consultation", "inquiry",
    ),
    "availability": (
        "예약", "예약가능", "야간", "주말", "진료시간", "당일진료", "오늘",
        "당일", "위치", "길찾기", "주차", "도보", "대중교통", "근처",
        "가까운", "booking", "appointment", "near", "hours", "parking",
    ),
    "safety": (
        "부작용", "주의", "치료기간", "기간", "통증", "회복", "재발", "안전",
        "효과", "걱정", "sideeffect", "side-effect", "recovery", "safety",
    ),
}
LENS_COMMUNITY_BRIDGE_TERMS = (
    "추천", "후기", "어디", "경험", "가본", "가보신", "해보신",
    "아시는", "궁금", "부탁", "괜찮", "잘하는",
)


PATIENT_SURFACE_PATIENT_TERMS: tuple[str, ...] = (
    "?",
    "추천",
    "후기",
    "경험",
    "궁금",
    "고민",
    "어디",
    "어떤",
    "어떻게",
    "괜찮",
    "알려",
    "문의",
    "상담",
    "예약",
    "비용",
    "가격",
    "얼마",
    "받아보",
    "해보",
    "다녀",
    "가보",
    "부탁",
    "ㅠ",
    "ㅜ",
    "나요",
    "인가요",
    "까요",
    "세요",
)
PATIENT_SURFACE_PROVIDER_TERMS: tuple[str, ...] = (
    "의료진소개",
    "의료진",
    "진료시간",
    "진료안내",
    "오시는길",
    "병원소개",
    "한의원소개",
    "대표원장",
    "본원",
    "공식",
    "홈페이지",
    "온라인상담",
    "예약문의",
    "문의전화",
    "상담센터",
    "둘러보기",
    "시술안내",
    "치료사례",
    "전후사진",
    "가격표",
    "패키지",
    "이벤트",
    "프로모션",
    "체험단",
    "협찬",
    "광고",
    "파워링크",
    "의료심의필",
    "365일진료",
    "평일야간진료",
    "자동차보험진료",
    "맞춤처방",
)

VIRAL_ACTION_ROUTE_DEFINITIONS: tuple[Dict[str, Any], ...] = (
    {
        "route": "recommendation_request",
        "lenses": ("review", "community"),
        "terms": (
            "추천",
            "추천요",
            "추천주세요",
            "추천해주세요",
            "추천요청",
            "어디",
            "어떤",
            "잘하는",
            "잘하는곳",
            "괜찮은곳",
            "병원추천",
            "한의원추천",
            "가볼만",
            "다녀보신",
            "아시는분",
            "아시는 분",
            "찾고있",
            "찾아보고",
        ),
    },
    {
        "route": "experience_request",
        "lenses": ("review", "community"),
        "terms": (
            "후기",
            "경험",
            "해본",
            "해보신",
            "받아본",
            "받아보신",
            "다녀",
            "가본",
            "전후",
            "효과",
            "만족",
            "어땠",
        ),
    },
    {
        "route": "cost_question",
        "lenses": ("cost",),
        "terms": (
            "비용",
            "가격",
            "가격대",
            "금액",
            "얼마",
            "치료비",
            "시술비",
            "총비용",
            "실비",
            "보험",
            "자보",
            "부담",
            "부담되",
            "견적",
            "가격표",
            "비싸",
            "저렴",
        ),
    },
    {
        "route": "consultation_question",
        "lenses": ("consultation",),
        "terms": (
            "상담",
            "문의",
            "진단",
            "처방",
            "검사",
            "치료가능",
            "치료 가능",
            "치료방법",
            "치료 방법",
            "관리방법",
            "관리 방법",
            "가능할",
            "가능한곳",
            "가능한 곳",
            "도움될까요",
            "받아보",
            "알아보",
            "예약상담",
        ),
    },
    {
        "route": "access_booking_question",
        "lenses": ("availability",),
        "terms": (
            "예약",
            "주차",
            "근처",
            "가까운",
            "오늘",
            "주말",
            "야간",
            "야간진료",
            "시간",
            "진료시간",
            "당일",
            "당일진료",
            "당일예약",
            "입원실",
            "가능한곳",
            "가능한 곳",
            "위치",
        ),
    },
    {
        "route": "safety_recovery_question",
        "lenses": ("safety",),
        "terms": (
            "부작용",
            "회복",
            "통증",
            "붓기",
            "멍",
            "안전",
            "주의",
            "기간",
            "효과",
            "재발",
            "악화",
            "괜찮을",
        ),
    },
    {
        "route": "comparison_decision",
        "lenses": ("review", "community", "cost", "consultation"),
        "terms": (
            "비교",
            "차이",
            "고민",
            "선택",
            "어느쪽",
            "어느 곳",
            "vs",
            "나을까요",
            "낫나요",
        ),
    },
)

VIRAL_ACTION_ROUTE_BRIDGE_BY_LENS: Dict[str, tuple[str, ...]] = {
    "cost": (
        "recommendation_request",
        "experience_request",
        "consultation_question",
        "access_booking_question",
        "comparison_decision",
    ),
    "consultation": (
        "recommendation_request",
        "experience_request",
        "cost_question",
        "access_booking_question",
        "safety_recovery_question",
        "comparison_decision",
    ),
    "availability": (
        "recommendation_request",
        "experience_request",
        "consultation_question",
        "comparison_decision",
    ),
    "safety": (
        "experience_request",
        "consultation_question",
        "comparison_decision",
    ),
}


def _loss_reason_for_status(status: str) -> str:
    text = str(status or "").strip() or "unknown"
    if text.startswith("filtered_out_"):
        return text.removeprefix("filtered_out_") or "filtered"
    if text == "filtered_out":
        return "filtered"
    return text


@dataclass
class LaneStats:
    total: int = 0
    actionable: int = 0
    survived: int = 0
    filtered: int = 0
    strict_fit: int = 0
    actionable_strict: int = 0
    fresh_actionable_strict: int = 0
    axis_observed: int = 0
    lens_observed: int = 0
    content_category_observed: int = 0
    content_category_mismatch: int = 0
    lens_surface_checked: int = 0
    lens_surface_matched: int = 0
    lens_surface_mismatch: int = 0
    clinic_observed: int = 0
    worksite_observed: int = 0
    priority_sum: float = 0.0
    axis_fit_sum: float = 0.0
    lens_fit_sum: float = 0.0
    clinic_fit_sum: float = 0.0
    worksite_sum: float = 0.0
    status_counts: Counter = field(default_factory=Counter)
    loss_counts: Counter = field(default_factory=Counter)
    grade_counts: Counter = field(default_factory=Counter)
    lens_counts: Counter = field(default_factory=Counter)
    variant_counts: Counter = field(default_factory=Counter)
    actionable_strict_fingerprints: Counter = field(default_factory=Counter)
    fresh_actionable_strict_fingerprints: Counter = field(default_factory=Counter)

    def add(
        self,
        *,
        status: str,
        grade: str,
        lens: str,
        query_variant: str,
        priority: float,
        axis_fit: Optional[float],
        lens_fit: Optional[float],
        clinic_fit: Optional[float],
        worksite_efficiency: Optional[float],
        strict_fit: bool,
        target_fingerprint: str = "",
        fresh_activity: bool = False,
        content_detected_category: str = "",
        content_category_mismatch: bool = False,
        lens_surface_checked: bool = False,
        lens_surface_matched: bool = False,
    ) -> None:
        self.total += 1
        self.priority_sum += priority
        self.status_counts[status] += 1
        self.grade_counts[grade] += 1
        self.lens_counts[lens] += 1
        self.variant_counts[query_variant] += 1
        if status in ACTIONABLE_STATUSES:
            self.actionable += 1
        if status in SURVIVED_STATUSES:
            self.survived += 1
        else:
            self.loss_counts[_loss_reason_for_status(status)] += 1
        if status.startswith(FILTERED_PREFIXES) or status == "manual_review":
            self.filtered += 1
        if strict_fit:
            self.strict_fit += 1
            if status in ACTIONABLE_STATUSES:
                self.actionable_strict += 1
                if target_fingerprint:
                    self.actionable_strict_fingerprints[target_fingerprint] += 1
                if fresh_activity:
                    self.fresh_actionable_strict += 1
                    if target_fingerprint:
                        self.fresh_actionable_strict_fingerprints[target_fingerprint] += 1
        if content_detected_category:
            self.content_category_observed += 1
        if content_category_mismatch:
            self.content_category_mismatch += 1
        if lens_surface_checked:
            self.lens_surface_checked += 1
            if lens_surface_matched:
                self.lens_surface_matched += 1
            else:
                self.lens_surface_mismatch += 1
        if axis_fit is not None:
            self.axis_observed += 1
            self.axis_fit_sum += axis_fit
        if lens_fit is not None:
            self.lens_observed += 1
            self.lens_fit_sum += lens_fit
        if clinic_fit is not None:
            self.clinic_observed += 1
            self.clinic_fit_sum += clinic_fit
        if worksite_efficiency is not None:
            self.worksite_observed += 1
            self.worksite_sum += worksite_efficiency

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    @staticmethod
    def _avg(total: float, count: int) -> float:
        return round(total / count, 2) if count else 0.0

    def to_dict(self) -> Dict[str, Any]:
        unique_actionable_strict = len(self.actionable_strict_fingerprints)
        unique_fresh_actionable_strict = len(self.fresh_actionable_strict_fingerprints)
        return {
            "total": self.total,
            "actionable": self.actionable,
            "survived": self.survived,
            "filtered": self.filtered,
            "lost": sum(self.loss_counts.values()),
            "strict_fit": self.strict_fit,
            "actionable_strict": self.actionable_strict,
            "fresh_actionable_strict": self.fresh_actionable_strict,
            "unique_actionable_strict": unique_actionable_strict,
            "unique_fresh_actionable_strict": unique_fresh_actionable_strict,
            "actionable_strict_duplicate_count": max(0, self.actionable_strict - unique_actionable_strict),
            "fresh_actionable_strict_duplicate_count": max(
                0,
                self.fresh_actionable_strict - unique_fresh_actionable_strict,
            ),
            "actionable_rate": self._rate(self.actionable, self.total),
            "survival_rate": self._rate(self.survived, self.total),
            "loss_rate": self._rate(sum(self.loss_counts.values()), self.total),
            "strict_fit_rate": self._rate(self.strict_fit, self.total),
            "actionable_strict_rate": self._rate(self.actionable_strict, self.total),
            "unique_actionable_strict_rate": self._rate(unique_actionable_strict, self.total),
            "actionable_strict_uniqueness_rate": self._rate(unique_actionable_strict, self.actionable_strict),
            "actionable_strict_share_of_strict": self._rate(self.actionable_strict, self.strict_fit),
            "fresh_actionable_strict_rate": self._rate(self.fresh_actionable_strict, self.total),
            "unique_fresh_actionable_strict_rate": self._rate(unique_fresh_actionable_strict, self.total),
            "fresh_actionable_strict_uniqueness_rate": self._rate(
                unique_fresh_actionable_strict,
                self.fresh_actionable_strict,
            ),
            "fresh_actionable_strict_share_of_strict": self._rate(self.fresh_actionable_strict, self.strict_fit),
            "fresh_actionable_strict_share_of_actionable_strict": self._rate(
                self.fresh_actionable_strict,
                self.actionable_strict,
            ),
            "avg_priority": self._avg(self.priority_sum, self.total),
            "avg_axis_fit": self._avg(self.axis_fit_sum, self.axis_observed),
            "avg_lens_fit": self._avg(self.lens_fit_sum, self.lens_observed),
            "avg_clinic_fit": self._avg(self.clinic_fit_sum, self.clinic_observed),
            "avg_worksite_efficiency": self._avg(self.worksite_sum, self.worksite_observed),
            "clinic_fit_observed": self.clinic_observed,
            "worksite_efficiency_observed": self.worksite_observed,
            "clinic_fit_coverage_rate": self._rate(self.clinic_observed, self.total),
            "worksite_efficiency_coverage_rate": self._rate(self.worksite_observed, self.total),
            "axis_observed": self.axis_observed,
            "lens_observed": self.lens_observed,
            "axis_coverage_rate": self._rate(self.axis_observed, self.total),
            "lens_coverage_rate": self._rate(self.lens_observed, self.total),
            "content_category_observed": self.content_category_observed,
            "content_category_mismatch": self.content_category_mismatch,
            "content_category_coverage_rate": self._rate(self.content_category_observed, self.total),
            "content_category_mismatch_rate": self._rate(
                self.content_category_mismatch,
                self.content_category_observed,
            ),
            "lens_surface_checked": self.lens_surface_checked,
            "lens_surface_matched": self.lens_surface_matched,
            "lens_surface_mismatch": self.lens_surface_mismatch,
            "lens_surface_match_rate": self._rate(self.lens_surface_matched, self.lens_surface_checked),
            "lens_surface_mismatch_rate": self._rate(self.lens_surface_mismatch, self.lens_surface_checked),
            "status_counts": dict(self.status_counts),
            "loss_reason_counts": dict(self.loss_counts),
            "dominant_loss_reason": self.loss_counts.most_common(1)[0][0] if self.loss_counts else "",
            "grade_counts": dict(self.grade_counts),
            "lens_counts": dict(self.lens_counts),
            "query_variant_counts": dict(self.variant_counts),
        }


def _default_db_path() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "db", "marketing_data.db")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _select_expr(columns: set[str], name: str, fallback: str, alias: Optional[str] = None) -> str:
    output = alias or name
    if name in columns:
        return name if output == name else f"{name} AS {output}"
    return f"{fallback} AS {output}"


def _parse_json(value: object, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default
    return default


def _number(value: object, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _split_signal_values(value: object) -> List[str]:
    items: List[str] = []

    def add(raw: object) -> None:
        if isinstance(raw, (list, tuple, set)):
            for nested in raw:
                add(nested)
            return
        text = str(raw or "").strip()
        if not text:
            return
        for separator in ("|", ";", "\n", "\t"):
            text = text.replace(separator, ",")
        for part in text.split(","):
            clean = part.strip()
            if clean and clean not in items:
                items.append(clean)

    add(value)
    return items


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "1.0", "true", "yes", "y", "manual_review"}


def _grade(value: object) -> str:
    text = str(value or "").strip().upper()
    return text if text in {"S", "A", "B", "C", "D"} else "unknown"


def _status(value: object) -> str:
    return str(value or "pending").strip() or "pending"


def _current_reject_reason(score_breakdown: Dict[str, Any]) -> str:
    if not isinstance(score_breakdown, dict):
        return ""
    for key in ("final_reject_reason", "pathfinder_fit_reject_reason"):
        reason = str(score_breakdown.get(key) or "").strip()
        if reason:
            return reason
    return ""


def _status_from_current_reject_reason(reason: str) -> str:
    clean = str(reason or "").strip()
    if not clean:
        return ""
    return CURRENT_REJECT_STATUS_BY_REASON.get(clean, "filtered_out")


def _effective_current_status(status: object, score_breakdown: Dict[str, Any]) -> str:
    """Use current-run reject evidence over preserved historical work states."""
    normalized = _status(status)
    if normalized not in SURVIVED_STATUSES:
        return normalized
    reject_status = _status_from_current_reject_reason(_current_reject_reason(score_breakdown))
    return reject_status or normalized


def _row_value(row: sqlite3.Row, name: str, default: object = "") -> object:
    try:
        return row[name]
    except (IndexError, KeyError, TypeError):
        return default


def _matched_keyword_candidates(row: sqlite3.Row) -> List[str]:
    candidates: List[str] = []

    def add(value: object) -> None:
        text = str(value or "").strip()
        if text and text not in candidates:
            candidates.append(text)

    add(_row_value(row, "matched_keyword"))
    parsed = _parse_json(_row_value(row, "matched_keywords"), [])
    if isinstance(parsed, list):
        for item in parsed:
            add(item)
    elif isinstance(parsed, str):
        add(parsed)
    return candidates


def _category(row: sqlite3.Row) -> str:
    raw = _row_value(row, "matched_keyword_category") or _row_value(row, "category") or "기타"
    normalized = ACTIVE_KEYWORD_PROFILE.normalize_category(str(raw))
    for keyword in _matched_keyword_candidates(row):
        candidate = canonical_category_for_keyword(keyword, normalized)
        if ACTIVE_KEYWORD_PROFILE.profile_for(candidate):
            return candidate
    return normalized


def _detected_seed_category(seed: str) -> str:
    detected = ACTIVE_KEYWORD_PROFILE.normalize_category(
        ACTIVE_KEYWORD_PROFILE.detect_category(seed or "", default="")
    )
    return detected if ACTIVE_KEYWORD_PROFILE.profile_for(detected) else ""


def _content_text(row: sqlite3.Row) -> str:
    return " ".join(
        str(_row_value(row, column) or "").strip()
        for column in ("title", "content_preview")
        if str(_row_value(row, column) or "").strip()
    )


def _compact_text(text: str) -> str:
    return "".join(str(text or "").lower().split())


def _target_fingerprint(row: sqlite3.Row) -> str:
    """Stable work-opportunity key used to avoid counting duplicates as depth."""
    title_key = _compact_text(str(_row_value(row, "title") or ""))
    preview_key = _compact_text(str(_row_value(row, "content_preview") or ""))[:160]
    if title_key:
        return f"text:{title_key[:180]}:{preview_key}"

    canonical = str(_row_value(row, "canonical_url") or "").strip()
    if not canonical:
        canonical = canonicalize_viral_url(str(_row_value(row, "url") or "")) or str(_row_value(row, "url") or "").strip()
    if canonical:
        return f"url:{_compact_text(canonical)}"

    row_id = str(_row_value(row, "id") or "").strip()
    return f"id:{row_id}" if row_id else ""


def _detected_content_category(row: sqlite3.Row) -> str:
    detected = ACTIVE_KEYWORD_PROFILE.normalize_category(
        ACTIVE_KEYWORD_PROFILE.detect_category(_content_text(row), default="")
    )
    return detected if ACTIVE_KEYWORD_PROFILE.profile_for(detected) else ""


def _lens_surface_evidence(row: sqlite3.Row, lens: str, query_variant: str) -> Dict[str, Any]:
    expected_lens = str(lens or "").strip().lower()
    terms = LENS_SURFACE_TERMS.get(expected_lens)
    if not terms:
        return {
            "checked": False,
            "matched": False,
            "terms": [],
            "bridge_terms": [],
        }

    compact = _compact_text(_content_text(row))
    matched_terms = [
        term for term in terms
        if _compact_text(term) and _compact_text(term) in compact
    ]
    bridge_terms = [
        term for term in LENS_COMMUNITY_BRIDGE_TERMS
        if _compact_text(term) and _compact_text(term) in compact
    ]
    variant = str(query_variant or "").strip()
    bridge_variant = (
        variant.startswith(f"{expected_lens}_community:")
        or (
            expected_lens in {"cost", "consultation", "availability", "safety"}
            and (
                variant == "community_base"
                or variant.startswith("axis_")
                or variant in {"patient_voice_kin", "patient_voice_question_kin"}
            )
        )
    )
    bridge_matched = bool(bridge_variant and bridge_terms)

    return {
        "checked": bool(compact),
        "matched": bool(matched_terms or bridge_matched),
        "terms": matched_terms[:6],
        "bridge_terms": bridge_terms[:6] if bridge_matched else [],
        "bridge_variant": bridge_variant,
    }


def _engagement_hook_evidence(row: sqlite3.Row, lens: str) -> Dict[str, Any]:
    """Detect whether a target exposes a reply-worthy patient intent hook."""
    compact = _compact_text(_content_text(row))
    if not compact:
        return {
            "checked": False,
            "matched": False,
            "terms": [],
        }

    expected_lens = str(lens or "").strip().lower()
    candidate_terms = list(ENGAGEMENT_HOOK_TERMS)
    candidate_terms.extend(ENGAGEMENT_HOOK_LENS_TERMS.get(expected_lens, ()))
    matched_terms: List[str] = []
    for term in candidate_terms:
        compact_term = _compact_text(term)
        if compact_term and compact_term in compact and term not in matched_terms:
            matched_terms.append(term)

    return {
        "checked": True,
        "matched": bool(matched_terms),
        "terms": matched_terms[:8],
    }


def _patient_surface_evidence(row: sqlite3.Row) -> Dict[str, Any]:
    """Detect whether the target looks like a patient/workable post, not provider promo."""
    compact = _compact_text(_content_text(row))
    if not compact:
        return {
            "checked": False,
            "matched": False,
            "terms": [],
            "provider_noise": False,
            "provider_terms": [],
        }

    candidate_patient_terms = list(PATIENT_SURFACE_PATIENT_TERMS)
    candidate_patient_terms.extend(ENGAGEMENT_HOOK_TERMS)
    for lens_terms in ENGAGEMENT_HOOK_LENS_TERMS.values():
        candidate_patient_terms.extend(lens_terms)
    candidate_patient_terms.extend(LENS_COMMUNITY_BRIDGE_TERMS)

    patient_terms: List[str] = []
    for term in candidate_patient_terms:
        compact_term = _compact_text(term)
        if compact_term and compact_term in compact and term not in patient_terms:
            patient_terms.append(term)

    provider_terms: List[str] = []
    for term in PATIENT_SURFACE_PROVIDER_TERMS:
        compact_term = _compact_text(term)
        if compact_term and compact_term in compact and term not in provider_terms:
            provider_terms.append(term)

    provider_noise = bool(provider_terms)
    return {
        "checked": True,
        "matched": bool(patient_terms) and not provider_noise,
        "terms": patient_terms[:8],
        "provider_noise": provider_noise,
        "provider_terms": provider_terms[:8],
    }


def _expected_viral_action_routes(lens: str) -> List[str]:
    expected_lens = str(lens or "").strip().lower()
    routes: List[str] = []
    for definition in VIRAL_ACTION_ROUTE_DEFINITIONS:
        if expected_lens in tuple(definition.get("lenses") or ()):
            route = str(definition.get("route") or "").strip()
            if route and route not in routes:
                routes.append(route)
    return routes


def _viral_action_route_score_breakdown(row: sqlite3.Row) -> Dict[str, Any]:
    parsed = _parse_json(_row_value(row, "score_breakdown"), {})
    return parsed if isinstance(parsed, dict) else {}


def _viral_action_route_bridge_variant(score_breakdown: Dict[str, Any], lens: str) -> bool:
    variant = str(score_breakdown.get("pathfinder_query_variant") or "").strip().lower()
    expected_lens = str(lens or "").strip().lower()
    if not variant:
        return False
    return bool(
        variant == "community_base"
        or variant.startswith(f"{expected_lens}_community:")
        or variant.startswith("community")
        or variant.startswith("patient_voice")
        or variant.startswith("axis_")
    )


def _viral_action_route_source_lens_matched(
    row: sqlite3.Row,
    lens: str,
    score_breakdown: Dict[str, Any],
) -> bool:
    expected_lens = str(lens or "").strip().lower()
    terms = LENS_SURFACE_TERMS.get(expected_lens)
    if not terms:
        return False

    source_parts: List[str] = []

    def add(value: object) -> None:
        if isinstance(value, (list, tuple, set)):
            for nested in value:
                add(nested)
            return
        text = str(value or "").strip()
        if text:
            source_parts.append(text)

    add(score_breakdown.get("pathfinder_source_keyword"))
    add(score_breakdown.get("pathfinder_source_keywords"))
    add(_row_value(row, "matched_keyword"))
    add(_matched_keyword_candidates(row))
    compact_source = _compact_text(" ".join(source_parts))
    if not compact_source:
        return False
    return any(
        _compact_text(term) and _compact_text(term) in compact_source
        for term in terms
    )


def _viral_action_route_bridge_allowed(
    row: sqlite3.Row,
    lens: str,
    matched_route: Dict[str, Any],
    score_breakdown: Dict[str, Any],
) -> bool:
    expected_lens = str(lens or "").strip().lower()
    route = str(matched_route.get("route") or "").strip()
    if route not in VIRAL_ACTION_ROUTE_BRIDGE_BY_LENS.get(expected_lens, ()):
        return False
    return bool(
        _viral_action_route_bridge_variant(score_breakdown, expected_lens)
        or _viral_action_route_source_lens_matched(row, expected_lens, score_breakdown)
    )


def _viral_action_route_evidence(row: sqlite3.Row, lens: str) -> Dict[str, Any]:
    """Classify the concrete viral entry route exposed by a patient post."""
    compact = _compact_text(_content_text(row))
    expected_lens = str(lens or "").strip().lower()
    expected_routes = _expected_viral_action_routes(expected_lens)
    score_breakdown = _viral_action_route_score_breakdown(row)
    if not compact or not expected_routes:
        return {
            "checked": bool(compact),
            "matched": False,
            "route": "",
            "terms": [],
            "routes": [],
            "observed_routes": [],
            "route_bridge": False,
            "route_mismatch": False,
            "expected_routes": expected_routes,
        }

    matched_routes: List[Dict[str, Any]] = []
    for definition in VIRAL_ACTION_ROUTE_DEFINITIONS:
        route = str(definition.get("route") or "").strip()
        route_lenses = tuple(definition.get("lenses") or ())
        route_terms: List[str] = []
        for term in tuple(definition.get("terms") or ()):
            compact_term = _compact_text(term)
            if compact_term and compact_term in compact and term not in route_terms:
                route_terms.append(term)
        if route and route_terms:
            matched_routes.append({
                "route": route,
                "lenses": route_lenses,
                "terms": route_terms[:6],
            })

    accepted_routes = [
        route for route in matched_routes
        if expected_lens in tuple(route.get("lenses") or ())
    ]
    bridge_routes = [
        route for route in matched_routes
        if route not in accepted_routes
        and _viral_action_route_bridge_allowed(row, expected_lens, route, score_breakdown)
    ]
    if not accepted_routes:
        accepted_routes = bridge_routes
    primary = accepted_routes[0] if accepted_routes else {}
    observed_route_names = []
    for route in matched_routes:
        name = str(route.get("route") or "")
        if name and name not in observed_route_names:
            observed_route_names.append(name)

    return {
        "checked": True,
        "matched": bool(accepted_routes),
        "route": str(primary.get("route") or ""),
        "terms": list(primary.get("terms") or []),
        "routes": [str(route.get("route") or "") for route in accepted_routes if route.get("route")][:4],
        "observed_routes": observed_route_names[:6],
        "route_bridge": bool(bridge_routes and accepted_routes == bridge_routes),
        "route_mismatch": bool(matched_routes and not accepted_routes),
        "expected_routes": expected_routes,
    }


def _content_reply_risk_flags(text: str) -> Dict[str, Any]:
    compact = _compact_text(text)
    if not compact:
        return {"flags": [], "penalty": 0.0, "matched_terms": {}}

    matched_terms: Dict[str, List[str]] = {}
    for flag, terms in CONTENT_REPLY_RISK_PATTERNS.items():
        matches: List[str] = []
        for term in terms:
            compact_term = _compact_text(term)
            if compact_term and compact_term in compact and term not in matches:
                matches.append(term)
        if matches:
            matched_terms[flag] = matches[:6]

    flags: List[str] = []
    if matched_terms.get("urgent_medical"):
        flags.append("urgent_medical")
    if matched_terms.get("sensitive_medical"):
        flags.append("sensitive_medical")
    if matched_terms.get("medication_advice_request") and (
        matched_terms.get("sensitive_medical")
        or matched_terms.get("acute_side_effect")
    ):
        flags.append("medication_advice_request")
    if matched_terms.get("acute_side_effect") and (
        matched_terms.get("sensitive_medical")
        or matched_terms.get("medication_advice_request")
    ):
        flags.append("acute_side_effect")
    if matched_terms.get("testimonial_sensitive"):
        flags.append("testimonial_sensitive")

    penalty = 0.0
    for flag in flags:
        penalty += float(CONTENT_REPLY_RISK_PENALTIES.get(flag) or 0.0)
    return {
        "flags": flags,
        "penalty": penalty,
        "matched_terms": matched_terms,
    }


def _reply_workability_evidence(
    row: sqlite3.Row,
    score_breakdown: Dict[str, Any],
    *,
    status: str,
) -> Dict[str, Any]:
    """Audit whether this target is safe and useful for public reply work."""
    score = _number(score_breakdown.get("reply_opportunity_score"), None)
    tier = str(score_breakdown.get("reply_opportunity_tier") or "").strip().lower()
    signals = _split_signal_values(score_breakdown.get("reply_opportunity_signals"))
    risk_flags = _split_signal_values(score_breakdown.get("reply_risk_flags"))
    risk_penalty = _number(score_breakdown.get("reply_risk_penalty"), 0.0) or 0.0
    manual_review = _truthy(score_breakdown.get("manual_review")) or status == "manual_review"
    content_risk = _content_reply_risk_flags(_content_text(row))
    content_risk_flags = list(content_risk.get("flags") or [])
    for flag in content_risk_flags:
        if flag not in risk_flags:
            risk_flags.append(flag)
    content_risk_penalty = float(content_risk.get("penalty") or 0.0)
    if content_risk_penalty < risk_penalty:
        risk_penalty = content_risk_penalty

    comment_count = int(_number(_row_value(row, "comment_count"), 0.0) or 0)
    view_count = int(_number(_row_value(row, "view_count"), 0.0) or 0)
    like_count = int(_number(_row_value(row, "like_count"), 0.0) or 0)

    signal_set = set(signals)
    score_ready = score is not None and score >= REPLY_WORKABILITY_SCORE_READY
    tier_ready = tier in REPLY_WORKABILITY_READY_TIERS
    signal_ready = bool(signal_set & REPLY_WORKABILITY_GOOD_SIGNALS)
    opportunity_ready = bool(score_ready or tier_ready or signal_ready)
    risk_blocked = bool(
        risk_flags
        or risk_penalty <= REPLY_WORKABILITY_RISK_PENALTY_BLOCK
        or manual_review
    )
    metric_missing = score is None and not tier and not signals

    return {
        "checked": not metric_missing or bool(risk_flags) or manual_review,
        "matched": bool(opportunity_ready and not risk_blocked),
        "score": score,
        "tier": tier,
        "signals": signals[:12],
        "risk_flags": risk_flags[:12],
        "content_risk_flags": content_risk_flags[:12],
        "content_risk_terms": content_risk.get("matched_terms") or {},
        "risk_penalty": risk_penalty,
        "manual_review": manual_review,
        "metric_missing": metric_missing,
        "opportunity_ready": opportunity_ready,
        "score_ready": bool(score_ready),
        "tier_ready": bool(tier_ready),
        "signal_ready": bool(signal_ready),
        "risk_blocked": bool(risk_blocked),
        "comment_count": comment_count,
        "view_count": view_count,
        "like_count": like_count,
    }


def _category_signature_terms(category: str) -> List[str]:
    normalized = ACTIVE_KEYWORD_PROFILE.normalize_category(category or "")
    profile = ACTIVE_KEYWORD_PROFILE.profile_for(normalized)
    if not profile:
        return []

    generic = {_compact_text(term) for term in TREATMENT_SIGNATURE_GENERIC_TERMS}
    terms: List[str] = []
    for term in (
        tuple(getattr(profile, "core_tokens", ()) or ())
        + tuple(getattr(profile, "category_terms", ()) or ())
        + tuple(getattr(profile, "seed_terms", ()) or ())
        + tuple(getattr(profile, "direct_service_anchors", ()) or ())
    ):
        clean = str(term or "").strip()
        compact = _compact_text(clean)
        if not compact or compact in generic or len(compact) < 2:
            continue
        if clean not in terms:
            terms.append(clean)
    terms.sort(key=lambda value: len(_compact_text(value)), reverse=True)
    return terms


def _treatment_signature_evidence(row: sqlite3.Row, category: str) -> Dict[str, Any]:
    """Detect whether the target itself carries a concrete Gyulim treatment signal."""
    terms = _category_signature_terms(category)
    compact = _compact_text(_content_text(row))
    if not terms:
        return {
            "checked": False,
            "matched": False,
            "terms": [],
            "expected_terms": [],
        }
    if not compact:
        return {
            "checked": False,
            "matched": False,
            "terms": [],
            "expected_terms": terms[:10],
        }

    matched_terms = [
        term for term in terms
        if _compact_text(term) and _compact_text(term) in compact
    ]
    return {
        "checked": True,
        "matched": bool(matched_terms),
        "terms": matched_terms[:8],
        "expected_terms": terms[:10],
    }


def _category_subintent_buckets(category: str) -> Dict[str, tuple[str, ...]]:
    normalized = ACTIVE_KEYWORD_PROFILE.normalize_category(category or "")
    return TREATMENT_SUBINTENT_BUCKETS.get(normalized, {})


def _treatment_subintent_evidence(row: sqlite3.Row, category: str) -> Dict[str, Any]:
    """Detect which patient sub-problem bucket this target represents."""
    buckets = _category_subintent_buckets(category)
    compact = _compact_text(_content_text(row))
    expected_buckets = list(buckets)
    if not buckets:
        return {
            "checked": False,
            "matched": False,
            "buckets": [],
            "terms": [],
            "bucket_terms": {},
            "expected_buckets": [],
        }
    if not compact:
        return {
            "checked": False,
            "matched": False,
            "buckets": [],
            "terms": [],
            "bucket_terms": {},
            "expected_buckets": expected_buckets,
        }

    matched_buckets: List[str] = []
    matched_terms: List[str] = []
    bucket_terms: Dict[str, List[str]] = {}
    for bucket, terms in buckets.items():
        term_matches: List[str] = []
        for term in terms:
            clean = str(term or "").strip()
            compact_term = _compact_text(clean)
            if compact_term and compact_term in compact and clean not in term_matches:
                term_matches.append(clean)
                if clean not in matched_terms:
                    matched_terms.append(clean)
        if term_matches:
            matched_buckets.append(bucket)
            bucket_terms[bucket] = term_matches[:8]

    return {
        "checked": True,
        "matched": bool(matched_buckets),
        "buckets": matched_buckets[:8],
        "terms": matched_terms[:16],
        "bucket_terms": bucket_terms,
        "expected_buckets": expected_buckets,
    }


def _matched_terms_from_text(text: str, terms: Iterable[object], *, limit: int = 12) -> List[str]:
    compact = _compact_text(text)
    if not compact:
        return []
    matched: List[str] = []
    for term in terms:
        clean = str(term or "").strip()
        compact_term = _compact_text(clean)
        if compact_term and compact_term in compact and clean not in matched:
            matched.append(clean)
            if len(matched) >= limit:
                break
    return matched


def _clinic_modality_positive_terms(category: str) -> List[str]:
    terms: List[str] = []
    anchor_markers = (
        tuple(getattr(ACTIVE_KEYWORD_PROFILE, "hanbang_indicators", ()) or ())
        + CLINIC_MODALITY_POSITIVE_TERMS
        + ("한방병원", "한의사", "경혈", "비수술")
    )
    for term in anchor_markers:
        clean = str(term or "").strip()
        if clean and clean not in terms:
            terms.append(clean)
    normalized = ACTIVE_KEYWORD_PROFILE.normalize_category(category or "")
    profile = ACTIVE_KEYWORD_PROFILE.profile_for(normalized)
    if profile:
        for term in tuple(getattr(profile, "direct_service_anchors", ()) or ()):
            clean = str(term or "").strip()
            compact_clean = _compact_text(clean)
            if (
                clean
                and clean not in terms
                and any(_compact_text(marker) in compact_clean for marker in anchor_markers)
            ):
                terms.append(clean)
    terms.sort(key=lambda value: len(_compact_text(value)), reverse=True)
    return terms


def _clinic_modality_evidence(row: sqlite3.Row, category: str) -> Dict[str, Any]:
    """Detect whether the post is compatible with Gyulim's Korean-medicine modality."""
    text = _content_text(row)
    if not text.strip():
        return {
            "checked": False,
            "matched": False,
            "compatible": False,
            "positive_terms": [],
            "offscope_terms": [],
            "bridge_terms": [],
            "reasons": ["empty_text"],
        }

    positive_terms = _matched_terms_from_text(
        text,
        _clinic_modality_positive_terms(category),
    )
    offscope_terms = _matched_terms_from_text(
        text,
        CLINIC_MODALITY_OFFSCOPE_TERMS,
    )
    bridge_terms = _matched_terms_from_text(
        text,
        CLINIC_MODALITY_BRIDGE_TERMS,
        limit=8,
    )
    strong_bridge_terms = [
        term for term in bridge_terms
        if term in CLINIC_MODALITY_STRONG_BRIDGE_TERMS
    ]
    offscope_only = bool(offscope_terms and not positive_terms and not strong_bridge_terms)
    reasons: List[str] = []
    if offscope_only:
        reasons.append("offscope_modality_noise")
    if offscope_terms and not positive_terms:
        reasons.append("missing_hanbang_modality_anchor")
    if offscope_only and bridge_terms and not strong_bridge_terms:
        reasons.append("weak_comparison_bridge_without_hanbang_anchor")

    compatible = not offscope_only
    return {
        "checked": True,
        "matched": compatible,
        "compatible": compatible,
        "positive_terms": positive_terms[:12],
        "offscope_terms": offscope_terms[:12],
        "bridge_terms": bridge_terms[:8],
        "reasons": reasons,
    }


def _decision_window_evidence(
    row: sqlite3.Row,
    score_breakdown: Dict[str, Any],
) -> Dict[str, Any]:
    """Detect whether the post is still in an actionable decision window."""
    text = _content_text(row)
    if not text.strip():
        return {
            "checked": False,
            "matched": False,
            "active_terms": [],
            "completed_terms": [],
            "active_signals": [],
            "reasons": ["empty_text"],
        }

    active_terms = _matched_terms_from_text(text, DECISION_WINDOW_ACTIVE_TERMS)
    completed_terms = _matched_terms_from_text(text, DECISION_WINDOW_COMPLETED_TERMS)
    reply_signals = _split_signal_values(score_breakdown.get("reply_opportunity_signals"))
    active_signal_names = [
        signal for signal in reply_signals
        if signal in {
            "decision_stage",
            "consideration_stage",
            "qualified_lead_context",
            "actionable_need",
            "decision_or_service_task",
            "help_request_language",
            "clear_question_shape",
        }
    ]
    active = bool(active_terms or active_signal_names)
    completed_only = bool(completed_terms and not active)
    committed_booking_noise = bool(
        completed_terms
        and any("예약" in term for term in completed_terms)
        and not any(term in active_terms for term in ("괜찮", "할까요", "되나요", "?"))
    )

    reasons: List[str] = []
    if not active:
        reasons.append("no_active_decision_window")
    if completed_only:
        reasons.append("completed_or_review_only_surface")
    if committed_booking_noise:
        reasons.append("already_committed_booking_noise")

    matched = bool(active and not completed_only and not committed_booking_noise)
    return {
        "checked": True,
        "matched": matched,
        "active_terms": active_terms[:12],
        "completed_terms": completed_terms[:12],
        "active_signals": active_signal_names[:8],
        "reasons": reasons,
    }


def _local_anchor_terms() -> List[str]:
    terms: List[str] = []
    for term in (
        (getattr(ACTIVE_KEYWORD_PROFILE, "primary_region", "") or "",)
        + tuple(getattr(ACTIVE_KEYWORD_PROFILE, "cheongju_regions", ()) or ())
        + tuple(getattr(ACTIVE_KEYWORD_PROFILE, "neighborhoods", ()) or ())
        + tuple(getattr(ACTIVE_KEYWORD_PROFILE, "nearby_regions", ()) or ())
    ):
        clean = str(term or "").strip()
        compact = _compact_text(clean)
        if not compact or len(compact) < 2:
            continue
        if clean not in terms:
            terms.append(clean)
    terms.sort(key=lambda value: len(_compact_text(value)), reverse=True)
    return terms


def _dedupe_local_area_terms(terms: Iterable[object]) -> List[str]:
    selected: List[str] = []
    selected_compacts: List[str] = []
    candidates: List[str] = []
    for term in terms:
        clean = str(term or "").strip()
        compact = _compact_text(clean)
        if not compact or len(compact) < 2:
            continue
        if clean not in candidates:
            candidates.append(clean)
    candidates.sort(key=lambda value: len(_compact_text(value)), reverse=True)
    for term in candidates:
        compact = _compact_text(term)
        if any(compact == existing or compact in existing or existing in compact for existing in selected_compacts):
            continue
        selected.append(term)
        selected_compacts.append(compact)
    return selected


def _local_area_terms_from_text(text: str) -> List[str]:
    compact = _compact_text(text)
    if not compact:
        return []
    return _dedupe_local_area_terms(
        term for term in _local_anchor_terms()
        if _compact_text(term) and _compact_text(term) in compact
    )


def _local_intent_evidence(row: sqlite3.Row) -> Dict[str, Any]:
    """Detect whether the target itself keeps a Cheongju-area work anchor."""
    terms = _local_anchor_terms()
    compact = _compact_text(_content_text(row))
    if not terms:
        return {
            "checked": False,
            "matched": False,
            "terms": [],
            "expected_terms": [],
        }
    if not compact:
        return {
            "checked": False,
            "matched": False,
            "terms": [],
            "expected_terms": terms[:12],
        }

    matched_terms = [
        term for term in terms
        if _compact_text(term) and _compact_text(term) in compact
    ]
    return {
        "checked": True,
        "matched": bool(matched_terms),
        "terms": matched_terms[:8],
        "expected_terms": terms[:12],
    }


def _local_area_evidence(row: sqlite3.Row, *, source_seeds: List[str]) -> Dict[str, Any]:
    target_terms = _local_area_terms_from_text(_content_text(row))
    source_terms = _local_area_terms_from_text(" ".join(str(seed or "") for seed in source_seeds))
    terms = _dedupe_local_area_terms(list(target_terms) + list(source_terms))
    return {
        "checked": bool(_content_text(row).strip() or source_seeds),
        "matched": bool(terms),
        "terms": terms[:10],
        "target_terms": target_terms[:10],
        "source_terms": source_terms[:10],
        "expected_terms": _local_anchor_terms()[:12],
    }


def _seed_candidate_stop_terms() -> set[str]:
    generic_terms = set(TREATMENT_SIGNATURE_GENERIC_TERMS)
    generic_terms.update({
        "한의원",
        "한방",
        "병원",
        "의원",
        "치료",
        "관리",
        "추천",
        "후기",
        "상담",
        "문의",
        "비용",
        "가격",
        "예약",
        "가능",
        "어디",
        "잘하는",
        "괜찮",
        "궁금",
        "주차",
        "근처",
    })
    generic_terms.update(_local_anchor_terms())
    return {_compact_text(term) for term in generic_terms if _compact_text(term)}


def _keyword_token_terms(text: str) -> List[str]:
    terms: List[str] = []
    token_chars: List[str] = []
    for char in str(text or ""):
        token_chars.append(char if char.isalnum() else " ")
    for token in "".join(token_chars).split():
        clean = token.strip()
        compact = _compact_text(clean)
        if len(compact) < 2:
            continue
        if clean not in terms:
            terms.append(clean)
    return terms


def _source_seed_specific_terms(source_seeds: List[str]) -> List[str]:
    stop_terms = _seed_candidate_stop_terms()
    terms: List[str] = []
    for seed in source_seeds:
        if str(seed or "").strip() == "(unknown)":
            continue
        for token in _keyword_token_terms(str(seed or "")):
            compact = _compact_text(token)
            if compact in stop_terms:
                continue
            if token not in terms:
                terms.append(token)
    terms.sort(key=lambda value: len(_compact_text(value)), reverse=True)
    return terms


def _seed_candidate_semantic_terms(
    source_seeds: List[str],
    *,
    category: str,
    lens: str,
) -> List[str]:
    source_compact = _compact_text(" ".join(str(seed or "") for seed in source_seeds))
    terms: List[str] = []

    def add(term: object) -> None:
        clean = str(term or "").strip()
        compact = _compact_text(clean)
        if len(compact) < 2:
            return
        if compact not in source_compact:
            return
        if clean not in terms:
            terms.append(clean)

    for term in _category_signature_terms(category):
        add(term)
    for term in LENS_SURFACE_TERMS.get(str(lens or "").strip().lower(), ()):
        add(term)
    for definition in VIRAL_ACTION_ROUTE_DEFINITIONS:
        if str(lens or "").strip().lower() not in set(definition.get("lenses") or ()):
            continue
        for term in definition.get("terms") or ():
            add(term)
    terms.sort(key=lambda value: len(_compact_text(value)), reverse=True)
    return terms


def _seed_candidate_alignment_evidence(
    row: sqlite3.Row,
    *,
    source_seeds: List[str],
    category: str,
    lens: str,
) -> Dict[str, Any]:
    source_text = " ".join(str(seed or "") for seed in source_seeds if str(seed or "").strip())
    source_compact = _compact_text(source_text)
    content_compact = _compact_text(_content_text(row))
    specific_terms = _source_seed_specific_terms(source_seeds)
    semantic_terms = _seed_candidate_semantic_terms(source_seeds, category=category, lens=lens)
    local_terms = [
        term for term in _local_anchor_terms()
        if _compact_text(term) and _compact_text(term) in source_compact
    ]
    expected_terms: List[str] = []
    for term in specific_terms + semantic_terms + local_terms:
        if term not in expected_terms:
            expected_terms.append(term)

    matched_specific = [
        term for term in specific_terms
        if _compact_text(term) and _compact_text(term) in content_compact
    ]
    matched_semantic = [
        term for term in semantic_terms
        if _compact_text(term) and _compact_text(term) in content_compact
    ]
    matched_local = [
        term for term in local_terms
        if _compact_text(term) and _compact_text(term) in content_compact
    ]
    matched_terms: List[str] = []
    for term in matched_specific + matched_semantic + matched_local:
        if term not in matched_terms:
            matched_terms.append(term)

    missing_terms = [term for term in expected_terms if term not in matched_terms]
    overlap_rate = LaneStats._rate(len(matched_terms), len(expected_terms))
    local_ok = not local_terms or bool(matched_local)
    specific_ok = bool(matched_specific) or (len(specific_terms) <= 1 and bool(matched_semantic))
    overlap_ok = (
        len(matched_terms) >= SEED_CANDIDATE_ALIGNMENT_MIN_OVERLAP
        or overlap_rate >= SEED_CANDIDATE_ALIGNMENT_MIN_RATIO
    )

    reasons: List[str] = []
    if not source_compact:
        reasons.append("missing_source_seed")
    if not content_compact:
        reasons.append("missing_candidate_text")
    if not expected_terms:
        reasons.append("no_source_alignment_terms")
    if expected_terms and not specific_ok:
        reasons.append("missing_source_specific_term")
    if local_terms and not matched_local:
        reasons.append("missing_source_local_term")
    if expected_terms and not overlap_ok:
        reasons.append("shallow_source_candidate_overlap")

    matched = bool(source_compact and content_compact and expected_terms and specific_ok and local_ok and overlap_ok)
    return {
        "checked": bool(source_compact and content_compact),
        "matched": matched,
        "source_terms": expected_terms[:12],
        "specific_terms": specific_terms[:8],
        "semantic_terms": semantic_terms[:8],
        "local_terms": local_terms[:6],
        "matched_terms": matched_terms[:12],
        "missing_terms": missing_terms[:12],
        "overlap_rate": overlap_rate,
        "reasons": reasons,
    }


def _category_drift_detected(assigned_category: str, detected_category: str) -> bool:
    assigned = ACTIVE_KEYWORD_PROFILE.normalize_category(assigned_category or "")
    detected = ACTIVE_KEYWORD_PROFILE.normalize_category(detected_category or "")
    if not assigned or not detected or assigned == detected:
        return False

    compatible_families = (
        {"흉터/여드름흉터", "피부/여드름"},
    )
    if any({assigned, detected}.issubset(family) for family in compatible_families):
        return False
    return True


def _lens(score_breakdown: Dict[str, Any]) -> str:
    text = str(score_breakdown.get("pathfinder_execution_lens") or "").strip().lower()
    return text or "unknown"


def _platform(row: sqlite3.Row) -> str:
    text = str(_row_value(row, "platform") or "").strip().lower()
    return text or "unknown"


def _variant(score_breakdown: Dict[str, Any]) -> str:
    text = str(score_breakdown.get("pathfinder_query_variant") or "").strip()
    return text or "base"


def _pathfinder_source_seeds(score_breakdown: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []

    def add(value: object) -> None:
        text = str(value or "").strip()
        if text and text not in candidates:
            candidates.append(text)

    add(score_breakdown.get("pathfinder_source_keyword"))
    raw_sources = score_breakdown.get("pathfinder_source_keywords")
    if isinstance(raw_sources, list):
        for item in raw_sources:
            add(item)
    elif raw_sources:
        add(raw_sources)
    return candidates


def _source_seeds(score_breakdown: Dict[str, Any], row: sqlite3.Row) -> List[str]:
    candidates: List[str] = list(_pathfinder_source_seeds(score_breakdown))
    if candidates:
        return candidates

    def add(value: object) -> None:
        text = str(value or "").strip()
        if text and text not in candidates:
            candidates.append(text)

    for keyword in _matched_keyword_candidates(row):
        add(keyword)
    return candidates or ["(unknown)"]


def _source_seed(score_breakdown: Dict[str, Any], row: sqlite3.Row) -> str:
    return _source_seeds(score_breakdown, row)[0]


def _variant_family(query_variant: str) -> str:
    variant = str(query_variant or "").strip()
    if variant in {"", "base", "(none)"}:
        return "base"
    if variant == "community_base":
        return "community_base"
    if variant in {"patient_voice_kin", "patient_voice_question_kin"}:
        return "patient_voice"
    if variant.startswith("colloquial:"):
        return "colloquial"
    if variant.startswith("axis_") and ":specific_" in variant:
        return "axis_specific"
    if variant.startswith("axis_"):
        return "axis_companion"
    if "_community:" in variant:
        return "lens_community"
    if ":" in variant:
        return "lens_companion"
    return "other"


def _score_from_breakdown(score_breakdown: Dict[str, Any], key: str) -> Optional[float]:
    return _number(score_breakdown.get(key), None)


def _score_from_breakdown_any(score_breakdown: Dict[str, Any], keys: Iterable[str]) -> Optional[float]:
    for key in keys:
        value = _score_from_breakdown(score_breakdown, key)
        if value is not None:
            return value
    return None


def _parse_timestamp(value: object) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _row_activity_at(row: sqlite3.Row) -> Optional[datetime]:
    timestamps = [
        parsed for parsed in (
            _parse_timestamp(_row_value(row, "last_scanned_at")),
            _parse_timestamp(_row_value(row, "discovered_at")),
        )
        if parsed is not None
    ]
    return max(timestamps) if timestamps else None


def _fresh_activity(
    row: sqlite3.Row,
    *,
    fresh_days: int,
    reference_time: Optional[datetime] = None,
) -> bool:
    activity_at = _row_activity_at(row)
    if activity_at is None:
        return False
    window_days = max(1, int(fresh_days or FRESH_WORK_QUEUE_DAYS))
    now = reference_time or datetime.now()
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc).replace(tzinfo=None)
    return activity_at >= now - timedelta(days=window_days)


def _row_sample(
    row: sqlite3.Row,
    *,
    category: str,
    grade: str,
    status: str,
    current_reject_reason: str,
    lens: str,
    query_variant: str,
    source_seed: str,
    source_seeds: List[str],
    pathfinder_source_seeds: List[str],
    source_seed_lineage_present: bool,
    source_seed_lineage_fallback: bool,
    query_variant_lineage_present: bool,
    priority: float,
    axis_fit: Optional[float],
    lens_fit: Optional[float],
    clinic_fit: Optional[float],
    worksite_efficiency: Optional[float],
    metric_strict_fit: bool,
    strict_fit: bool,
    target_fingerprint: str,
    content_detected_category: str,
    content_category_mismatch: bool,
    lens_surface_checked: bool,
    lens_surface_matched: bool,
    lens_surface_terms: List[str],
    lens_surface_bridge_terms: List[str],
    engagement_hook_checked: bool,
    engagement_hook_matched: bool,
    engagement_hook_terms: List[str],
    patient_surface_checked: bool,
    patient_surface_matched: bool,
    patient_surface_terms: List[str],
    patient_surface_provider_noise: bool,
    patient_surface_provider_terms: List[str],
    viral_action_route_checked: bool,
    viral_action_route_matched: bool,
    viral_action_route: str,
    viral_action_route_terms: List[str],
    viral_action_route_routes: List[str],
    viral_action_route_observed_routes: List[str],
    viral_action_route_mismatch: bool,
    viral_action_route_expected_routes: List[str],
    reply_workability_checked: bool,
    reply_workability_matched: bool,
    reply_opportunity_score: Optional[float],
    reply_opportunity_tier: str,
    reply_opportunity_signals: List[str],
    reply_risk_flags: List[str],
    content_risk_flags: List[str],
    content_risk_terms: Dict[str, List[str]],
    reply_risk_penalty: float,
    reply_manual_review: bool,
    reply_metric_missing: bool,
    reply_risk_blocked: bool,
    reply_comment_count: int,
    reply_view_count: int,
    reply_like_count: int,
    treatment_signature_checked: bool,
    treatment_signature_matched: bool,
    treatment_signature_terms: List[str],
    treatment_signature_expected_terms: List[str],
    treatment_subintent_checked: bool,
    treatment_subintent_matched: bool,
    treatment_subintent_buckets: List[str],
    treatment_subintent_terms: List[str],
    treatment_subintent_bucket_terms: Dict[str, List[str]],
    treatment_subintent_expected_buckets: List[str],
    clinic_modality_checked: bool,
    clinic_modality_matched: bool,
    clinic_modality_positive_terms: List[str],
    clinic_modality_offscope_terms: List[str],
    clinic_modality_bridge_terms: List[str],
    clinic_modality_reasons: List[str],
    decision_window_checked: bool,
    decision_window_matched: bool,
    decision_window_active_terms: List[str],
    decision_window_completed_terms: List[str],
    decision_window_active_signals: List[str],
    decision_window_reasons: List[str],
    local_intent_checked: bool,
    local_intent_matched: bool,
    local_intent_terms: List[str],
    local_intent_expected_terms: List[str],
    local_area_terms: List[str],
    local_area_target_terms: List[str],
    local_area_source_terms: List[str],
    seed_candidate_alignment_checked: bool,
    seed_candidate_alignment_matched: bool,
    seed_candidate_alignment_terms: List[str],
    seed_candidate_alignment_matched_terms: List[str],
    seed_candidate_alignment_missing_terms: List[str],
    seed_candidate_alignment_local_terms: List[str],
    seed_candidate_alignment_reasons: List[str],
    seed_candidate_alignment_overlap_rate: float,
    fresh_activity: bool,
) -> Dict[str, Any]:
    variant_family = _variant_family(query_variant)
    activity_at = _row_activity_at(row)
    return {
        "id": row["id"] or "",
        "url": row["url"] or "",
        "canonical_url": _row_value(row, "canonical_url") or "",
        "target_fingerprint": target_fingerprint,
        "title": row["title"] or "",
        "content_preview": _row_value(row, "content_preview") or "",
        "discovered_at": _row_value(row, "discovered_at") or "",
        "last_scanned_at": _row_value(row, "last_scanned_at") or "",
        "activity_at": activity_at.isoformat(sep=" ") if activity_at else "",
        "fresh_activity": bool(fresh_activity),
        "platform": _platform(row),
        "category": category,
        "grade": grade,
        "status": status,
        "current_reject_reason": current_reject_reason,
        "lens": lens,
        "query_variant": query_variant,
        "query_variant_family": variant_family,
        "source_seed": source_seed,
        "source_seeds": source_seeds,
        "pathfinder_source_seeds": pathfinder_source_seeds,
        "source_seed_lineage_present": bool(source_seed_lineage_present),
        "source_seed_lineage_fallback": bool(source_seed_lineage_fallback),
        "query_variant_lineage_present": bool(query_variant_lineage_present),
        "content_detected_category": content_detected_category,
        "content_category_mismatch": content_category_mismatch,
        "lens_surface_checked": lens_surface_checked,
        "lens_surface_matched": lens_surface_matched,
        "lens_surface_terms": lens_surface_terms,
        "lens_surface_bridge_terms": lens_surface_bridge_terms,
        "engagement_hook_checked": engagement_hook_checked,
        "engagement_hook_matched": engagement_hook_matched,
        "engagement_hook_terms": engagement_hook_terms,
        "patient_surface_checked": patient_surface_checked,
        "patient_surface_matched": patient_surface_matched,
        "patient_surface_terms": patient_surface_terms,
        "patient_surface_provider_noise": patient_surface_provider_noise,
        "patient_surface_provider_terms": patient_surface_provider_terms,
        "viral_action_route_checked": viral_action_route_checked,
        "viral_action_route_matched": viral_action_route_matched,
        "viral_action_route": viral_action_route,
        "viral_action_route_terms": viral_action_route_terms,
        "viral_action_route_routes": viral_action_route_routes,
        "viral_action_route_observed_routes": viral_action_route_observed_routes,
        "viral_action_route_mismatch": viral_action_route_mismatch,
        "viral_action_route_expected_routes": viral_action_route_expected_routes,
        "reply_workability_checked": reply_workability_checked,
        "reply_workability_matched": reply_workability_matched,
        "reply_opportunity_score": reply_opportunity_score,
        "reply_opportunity_tier": reply_opportunity_tier,
        "reply_opportunity_signals": reply_opportunity_signals,
        "reply_risk_flags": reply_risk_flags,
        "content_risk_flags": content_risk_flags,
        "content_risk_terms": content_risk_terms,
        "reply_risk_penalty": round(float(reply_risk_penalty or 0.0), 2),
        "reply_manual_review": reply_manual_review,
        "reply_metric_missing": reply_metric_missing,
        "reply_risk_blocked": reply_risk_blocked,
        "comment_count": reply_comment_count,
        "view_count": reply_view_count,
        "like_count": reply_like_count,
        "treatment_signature_checked": treatment_signature_checked,
        "treatment_signature_matched": treatment_signature_matched,
        "treatment_signature_terms": treatment_signature_terms,
        "treatment_signature_expected_terms": treatment_signature_expected_terms,
        "treatment_subintent_checked": treatment_subintent_checked,
        "treatment_subintent_matched": treatment_subintent_matched,
        "treatment_subintent_buckets": treatment_subintent_buckets,
        "treatment_subintent_terms": treatment_subintent_terms,
        "treatment_subintent_bucket_terms": treatment_subintent_bucket_terms,
        "treatment_subintent_expected_buckets": treatment_subintent_expected_buckets,
        "clinic_modality_checked": clinic_modality_checked,
        "clinic_modality_matched": clinic_modality_matched,
        "clinic_modality_positive_terms": clinic_modality_positive_terms,
        "clinic_modality_offscope_terms": clinic_modality_offscope_terms,
        "clinic_modality_bridge_terms": clinic_modality_bridge_terms,
        "clinic_modality_reasons": clinic_modality_reasons,
        "decision_window_checked": decision_window_checked,
        "decision_window_matched": decision_window_matched,
        "decision_window_active_terms": decision_window_active_terms,
        "decision_window_completed_terms": decision_window_completed_terms,
        "decision_window_active_signals": decision_window_active_signals,
        "decision_window_reasons": decision_window_reasons,
        "local_intent_checked": local_intent_checked,
        "local_intent_matched": local_intent_matched,
        "local_intent_terms": local_intent_terms,
        "local_intent_expected_terms": local_intent_expected_terms,
        "local_area_terms": local_area_terms,
        "local_area_target_terms": local_area_target_terms,
        "local_area_source_terms": local_area_source_terms,
        "seed_candidate_alignment_checked": seed_candidate_alignment_checked,
        "seed_candidate_alignment_matched": seed_candidate_alignment_matched,
        "seed_candidate_alignment_terms": seed_candidate_alignment_terms,
        "seed_candidate_alignment_matched_terms": seed_candidate_alignment_matched_terms,
        "seed_candidate_alignment_missing_terms": seed_candidate_alignment_missing_terms,
        "seed_candidate_alignment_local_terms": seed_candidate_alignment_local_terms,
        "seed_candidate_alignment_reasons": seed_candidate_alignment_reasons,
        "seed_candidate_alignment_overlap_rate": round(float(seed_candidate_alignment_overlap_rate or 0.0), 4),
        "priority": round(priority, 2),
        "axis_fit": axis_fit,
        "lens_fit": lens_fit,
        "clinic_fit": clinic_fit,
        "worksite_efficiency": worksite_efficiency,
        "metric_strict_fit": metric_strict_fit,
        "strict_fit": strict_fit,
        "matched_keyword": row["matched_keyword"] or "",
    }


def _reanalysis_rescue_quality(records: List[Dict[str, Any]], *, limit: int = 12) -> Dict[str, Any]:
    """Find high-fit filtered targets that should be re-entered into AI review.

    This is a state integrity check, not a quality whitelist. It only surfaces
    recent activity where Viral Hunter has no explicit current reject reason and
    Pathfinder/reply metrics are already strong enough for the retry lane.
    """

    candidates: List[Dict[str, Any]] = []
    by_category: Counter = Counter()
    by_lens: Counter = Counter()
    by_category_lens: Counter = Counter()
    priority_focus = set(_priority_focus_categories())

    for record in records:
        if str(record.get("status") or "") != "filtered_out":
            continue
        if str(record.get("current_reject_reason") or "").strip():
            continue
        if not bool(record.get("fresh_activity")):
            continue
        priority = float(record.get("priority") or 0.0)
        axis_fit = float(record.get("axis_fit") or 0.0)
        lens_fit = float(record.get("lens_fit") or 0.0)
        reply_score = float(record.get("reply_opportunity_score") or 0.0)
        if priority < REANALYSIS_RESCUE_MIN_PRIORITY:
            continue
        if axis_fit < REANALYSIS_RESCUE_MIN_AXIS_FIT:
            continue
        if lens_fit < REANALYSIS_RESCUE_MIN_LENS_FIT:
            continue
        if reply_score < REANALYSIS_RESCUE_MIN_REPLY_SCORE:
            continue
        if record.get("reply_risk_flags"):
            continue
        if bool(record.get("reply_manual_review")):
            continue
        if float(record.get("reply_risk_penalty") or 0.0) <= -40.0:
            continue

        category = str(record.get("category") or "기타")
        lens = str(record.get("lens") or "unknown")
        lane = f"{category}::{lens}"
        by_category[category] += 1
        by_lens[lens] += 1
        by_category_lens[lane] += 1
        candidates.append({
            "id": record.get("id") or "",
            "url": record.get("url") or "",
            "title": record.get("title") or "",
            "platform": record.get("platform") or "",
            "category": category,
            "lens": lens,
            "priority": round(priority, 2),
            "axis_fit": round(axis_fit, 2),
            "lens_fit": round(lens_fit, 2),
            "reply_opportunity_score": round(reply_score, 2),
            "activity_at": record.get("activity_at") or "",
            "source_seed": record.get("source_seed") or "",
        })

    candidates.sort(
        key=lambda item: (
            -float(item.get("priority") or 0.0),
            -float(item.get("axis_fit") or 0.0),
            -float(item.get("lens_fit") or 0.0),
            str(item.get("category") or ""),
            str(item.get("title") or ""),
        )
    )
    candidate_count = len(candidates)
    priority_focus_candidate_count = sum(
        count for category, count in by_category.items() if category in priority_focus
    )

    return {
        "overall": {
            "candidate_count": candidate_count,
            "priority_focus_candidate_count": priority_focus_candidate_count,
            "thresholds": {
                "min_priority": REANALYSIS_RESCUE_MIN_PRIORITY,
                "min_axis_fit": REANALYSIS_RESCUE_MIN_AXIS_FIT,
                "min_lens_fit": REANALYSIS_RESCUE_MIN_LENS_FIT,
                "min_reply_opportunity": REANALYSIS_RESCUE_MIN_REPLY_SCORE,
            },
        },
        "by_category": dict(by_category.most_common()),
        "by_lens": dict(by_lens.most_common()),
        "by_category_lens": dict(by_category_lens.most_common()),
        "samples": candidates[: max(0, int(limit or 0))],
    }


def _discarded_execution_rescue_quality(records: List[Dict[str, Any]], *, limit: int = 12) -> Dict[str, Any]:
    """Find non-actionable rows that look execution-ready except for discard status."""
    candidates: List[Dict[str, Any]] = []
    by_category: Counter = Counter()
    by_lens: Counter = Counter()
    by_category_lens: Counter = Counter()
    by_status: Counter = Counter()
    by_reject_reason: Counter = Counter()
    by_rescue_mode: Counter = Counter()
    priority_focus = set(_priority_focus_categories())
    stale_window_safety_excluded_count = 0

    def missing_reasons(record: Dict[str, Any]) -> List[str]:
        reasons: List[str] = []
        status = str(record.get("status") or "")
        current_reject_reason = str(record.get("current_reject_reason") or "").strip()
        if status in ACTIONABLE_STATUSES:
            reasons.append("already_actionable")
        if current_reject_reason:
            reasons.append("current_reject_reason")
        if status == "filtered_out_ai":
            reasons.append("ai_rejected")
        if not bool(record.get("metric_strict_fit")):
            reasons.append("metric_fit_below_strict")
        if not bool(record.get("fresh_activity")):
            reasons.append("not_fresh")
        if float(record.get("priority") or 0.0) < DISCARDED_EXECUTION_RESCUE_MIN_PRIORITY:
            reasons.append("low_priority")
        if float(record.get("reply_opportunity_score") or 0.0) < DISCARDED_EXECUTION_RESCUE_MIN_REPLY_SCORE:
            reasons.append("low_reply_opportunity")
        for key, reason in (
            ("source_seed_lineage_present", "missing_pathfinder_source_keyword"),
            ("query_variant_lineage_present", "missing_pathfinder_query_variant"),
            ("engagement_hook_matched", "missing_engagement_hook"),
            ("treatment_signature_matched", "missing_treatment_signature"),
            ("treatment_subintent_matched", "missing_treatment_subintent"),
            ("clinic_modality_matched", "clinic_modality_mismatch"),
            ("decision_window_matched", "closed_decision_window"),
            ("local_intent_matched", "missing_local_intent"),
            ("seed_candidate_alignment_matched", "seed_candidate_misaligned"),
            ("patient_surface_matched", "missing_patient_surface"),
            ("viral_action_route_matched", "missing_viral_action_route"),
            ("reply_workability_matched", "missing_reply_workability"),
        ):
            if not bool(record.get(key)):
                reasons.append(reason)
        if bool(record.get("patient_surface_provider_noise")):
            reasons.append("provider_surface_noise")
        if bool(record.get("viral_action_route_mismatch")):
            reasons.append("viral_action_route_mismatch")
        if bool(record.get("reply_risk_blocked")) or record.get("reply_risk_flags"):
            reasons.append("reply_risk_flags")
        if bool(record.get("reply_manual_review")):
            reasons.append("manual_review_required")
        if float(record.get("reply_risk_penalty") or 0.0) <= REPLY_WORKABILITY_RISK_PENALTY_BLOCK:
            reasons.append("reply_risk_penalty_block")
        return reasons

    for record in records:
        # Timing-gate expiry is terminal.  Do not let the audit manufacture an
        # auto-requeue instruction for a post that Viral Hunter must keep stale.
        if str(record.get("status") or "") == "filtered_out_stale_window":
            stale_window_safety_excluded_count += 1
            continue
        reasons = missing_reasons(record)
        if reasons:
            continue
        category = str(record.get("category") or "기타")
        lens = str(record.get("lens") or "unknown")
        lane = f"{category}::{lens}"
        status = str(record.get("status") or "")
        reject_reason = str(record.get("current_reject_reason") or "").strip()
        rescue_mode = (
            "auto_requeue"
            if status in DISCARDED_EXECUTION_AUTO_REQUEUE_STATUSES
            else "manual_review"
        )
        by_category[category] += 1
        by_lens[lens] += 1
        by_category_lens[lane] += 1
        by_status[status] += 1
        by_reject_reason[reject_reason or "(none)"] += 1
        by_rescue_mode[rescue_mode] += 1
        candidates.append({
            "id": record.get("id") or "",
            "url": record.get("url") or "",
            "title": record.get("title") or "",
            "platform": record.get("platform") or "",
            "category": category,
            "lens": lens,
            "status": status,
            "rescue_mode": rescue_mode,
            "current_reject_reason": reject_reason,
            "loss_reason": _loss_reason_for_status(status),
            "priority": round(float(record.get("priority") or 0.0), 2),
            "axis_fit": record.get("axis_fit"),
            "lens_fit": record.get("lens_fit"),
            "clinic_fit": record.get("clinic_fit"),
            "worksite_efficiency": record.get("worksite_efficiency"),
            "reply_opportunity_score": record.get("reply_opportunity_score"),
            "activity_at": record.get("activity_at") or "",
            "source_seed": record.get("source_seed") or "",
            "query_variant": record.get("query_variant") or "",
            "treatment_signature_terms": record.get("treatment_signature_terms") or [],
            "treatment_subintent_buckets": record.get("treatment_subintent_buckets") or [],
            "viral_action_route_routes": record.get("viral_action_route_routes") or [],
            "reply_opportunity_signals": record.get("reply_opportunity_signals") or [],
        })

    candidates.sort(
        key=lambda item: (
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -float(item.get("priority") or 0.0),
            str(item.get("status") or ""),
            str(item.get("title") or ""),
        )
    )
    candidate_count = len(candidates)
    priority_focus_candidate_count = sum(
        count for category, count in by_category.items() if category in priority_focus
    )
    auto_requeue_candidates = [
        item for item in candidates
        if str(item.get("rescue_mode") or "") == "auto_requeue"
    ]
    manual_review_candidates = [
        item for item in candidates
        if str(item.get("rescue_mode") or "") == "manual_review"
    ]
    auto_requeue_candidate_count = len(auto_requeue_candidates)
    manual_review_candidate_count = len(manual_review_candidates)
    auto_requeue_priority_focus_candidate_count = sum(
        1 for item in auto_requeue_candidates
        if str(item.get("category") or "") in priority_focus
    )
    manual_review_priority_focus_candidate_count = sum(
        1 for item in manual_review_candidates
        if str(item.get("category") or "") in priority_focus
    )
    return {
        "overall": {
            "candidate_count": candidate_count,
            "priority_focus_candidate_count": priority_focus_candidate_count,
            "auto_requeue_candidate_count": auto_requeue_candidate_count,
            "auto_requeue_priority_focus_candidate_count": (
                auto_requeue_priority_focus_candidate_count
            ),
            "manual_review_candidate_count": manual_review_candidate_count,
            "manual_review_priority_focus_candidate_count": (
                manual_review_priority_focus_candidate_count
            ),
            "stale_window_safety_excluded_count": stale_window_safety_excluded_count,
            "thresholds": {
                "min_priority": DISCARDED_EXECUTION_RESCUE_MIN_PRIORITY,
                "min_reply_opportunity": DISCARDED_EXECUTION_RESCUE_MIN_REPLY_SCORE,
            },
            "auto_requeue_statuses": sorted(DISCARDED_EXECUTION_AUTO_REQUEUE_STATUSES),
            "manual_review_statuses": sorted(DISCARDED_EXECUTION_MANUAL_REVIEW_STATUSES),
            "safety_excluded_statuses": ["filtered_out_stale_window"],
        },
        "by_category": dict(by_category.most_common()),
        "by_lens": dict(by_lens.most_common()),
        "by_category_lens": dict(by_category_lens.most_common()),
        "by_status": dict(by_status.most_common()),
        "by_reject_reason": dict(by_reject_reason.most_common()),
        "by_rescue_mode": dict(by_rescue_mode.most_common()),
        "auto_requeue_samples": auto_requeue_candidates[: max(0, int(limit or 0))],
        "manual_review_samples": manual_review_candidates[: max(0, int(limit or 0))],
        "samples": candidates[: max(0, int(limit or 0))],
    }


def _source_lineage_sample(record: Dict[str, Any]) -> Dict[str, Any]:
    reasons: List[str] = []
    if not bool(record.get("source_seed_lineage_present")):
        if bool(record.get("source_seed_lineage_fallback")):
            reasons.append("fallback_matched_keyword_used")
        else:
            reasons.append("missing_pathfinder_source_keyword")
    if not bool(record.get("query_variant_lineage_present")):
        reasons.append("missing_pathfinder_query_variant")
    return {
        "id": record.get("id") or "",
        "url": record.get("url") or "",
        "title": record.get("title") or "",
        "platform": record.get("platform") or "",
        "category": record.get("category") or "",
        "lens": record.get("lens") or "",
        "status": record.get("status") or "",
        "priority": record.get("priority") or 0.0,
        "source_seed": record.get("source_seed") or "",
        "pathfinder_source_seeds": record.get("pathfinder_source_seeds") or [],
        "query_variant": record.get("query_variant") or "",
        "matched_keyword": record.get("matched_keyword") or "",
        "reasons": reasons,
    }


def _source_lineage_metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(records)
    source_seed_present = sum(1 for record in records if bool(record.get("source_seed_lineage_present")))
    query_variant_present = sum(1 for record in records if bool(record.get("query_variant_lineage_present")))
    fallback_count = sum(1 for record in records if bool(record.get("source_seed_lineage_fallback")))
    unknown_count = sum(1 for record in records if str(record.get("source_seed") or "").strip() == "(unknown)")
    actionable_strict = [
        record for record in records
        if record.get("status") in ACTIONABLE_STATUSES and bool(record.get("strict_fit"))
    ]
    actionable_strict_total = len(actionable_strict)
    actionable_strict_source_seed_present = sum(
        1 for record in actionable_strict
        if bool(record.get("source_seed_lineage_present"))
    )
    return {
        "total": total,
        "source_seed_present": source_seed_present,
        "source_seed_missing": max(0, total - source_seed_present),
        "source_seed_fallback_count": fallback_count,
        "unknown_source_seed_count": unknown_count,
        "source_seed_coverage_rate": LaneStats._rate(source_seed_present, total),
        "query_variant_present": query_variant_present,
        "query_variant_missing": max(0, total - query_variant_present),
        "query_variant_coverage_rate": LaneStats._rate(query_variant_present, total),
        "actionable_strict_total": actionable_strict_total,
        "actionable_strict_source_seed_present": actionable_strict_source_seed_present,
        "actionable_strict_source_seed_missing": max(
            0,
            actionable_strict_total - actionable_strict_source_seed_present,
        ),
        "actionable_strict_source_seed_coverage_rate": LaneStats._rate(
            actionable_strict_source_seed_present,
            actionable_strict_total,
        ),
    }


def _source_lineage_quality(records: List[Dict[str, Any]], *, limit: int = 12) -> Dict[str, Any]:
    """Audit explicit Pathfinder source-keyword lineage through Viral Hunter targets.

    `_source_seeds` intentionally falls back to matched keywords for legacy rows.
    This audit keeps the fallback useful for diagnostics while preventing fallback
    values from being treated as auditable Pathfinder lineage.
    """
    priority_focus = set(_priority_focus_categories())
    records = list(records)
    priority_records = [
        record for record in records
        if str(record.get("category") or "") in priority_focus
    ]
    actionable_strict = [
        record for record in records
        if record.get("status") in ACTIONABLE_STATUSES and bool(record.get("strict_fit"))
    ]
    priority_actionable_strict = [
        record for record in actionable_strict
        if str(record.get("category") or "") in priority_focus
    ]

    overall = _source_lineage_metrics(records)
    priority_overall = _source_lineage_metrics(priority_records)
    actionable_overall = _source_lineage_metrics(actionable_strict)
    priority_actionable_overall = _source_lineage_metrics(priority_actionable_strict)
    targets = {
        "source_seed_coverage_rate": SOURCE_LINEAGE_MIN_SOURCE_SEED_COVERAGE,
        "priority_focus_source_seed_coverage_rate": (
            SOURCE_LINEAGE_MIN_PRIORITY_FOCUS_SOURCE_SEED_COVERAGE
        ),
        "actionable_strict_source_seed_coverage_rate": (
            SOURCE_LINEAGE_MIN_ACTIONABLE_STRICT_SOURCE_SEED_COVERAGE
        ),
        "query_variant_coverage_rate": SOURCE_LINEAGE_MIN_QUERY_VARIANT_COVERAGE,
    }

    def meets(metrics: Dict[str, Any], key: str, target: float) -> bool:
        return int(metrics.get("total") or 0) == 0 or float(metrics.get(key) or 0.0) >= target

    source_ready = (
        meets(overall, "source_seed_coverage_rate", targets["source_seed_coverage_rate"])
        and meets(
            priority_overall,
            "source_seed_coverage_rate",
            targets["priority_focus_source_seed_coverage_rate"],
        )
        and meets(
            actionable_overall,
            "source_seed_coverage_rate",
            targets["actionable_strict_source_seed_coverage_rate"],
        )
        and meets(
            priority_actionable_overall,
            "source_seed_coverage_rate",
            targets["actionable_strict_source_seed_coverage_rate"],
        )
    )
    query_variant_ready = meets(
        overall,
        "query_variant_coverage_rate",
        targets["query_variant_coverage_rate"],
    )

    by_category: Dict[str, Dict[str, Any]] = {}
    by_category_lens: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []

    category_records: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    category_lens_records: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        category = str(record.get("category") or "")
        lens = str(record.get("lens") or "unknown")
        category_records[category].append(record)
        category_lens_records[f"{category}::{lens}"].append(record)

    for category, items in category_records.items():
        metrics = _source_lineage_metrics(items)
        by_category[category] = metrics
        if (
            category in priority_focus
            and int(metrics.get("total") or 0)
            and float(metrics.get("source_seed_coverage_rate") or 0.0)
            < targets["priority_focus_source_seed_coverage_rate"]
        ):
            category_gaps.append({
                "type": "category",
                "lane": category,
                "category": category,
                **metrics,
                "target": targets["priority_focus_source_seed_coverage_rate"],
                "reasons": ["source_lineage_coverage_low"],
            })

    for lane, items in category_lens_records.items():
        category, _, lens = lane.partition("::")
        metrics = _source_lineage_metrics(items)
        by_category_lens[lane] = {
            "category": category,
            "lens": lens,
            **metrics,
        }
        if (
            category in priority_focus
            and int(metrics.get("total") or 0)
            and float(metrics.get("source_seed_coverage_rate") or 0.0)
            < targets["priority_focus_source_seed_coverage_rate"]
        ):
            category_lens_gaps.append({
                "type": "category_lens",
                "lane": lane,
                "category": category,
                "lens": lens,
                **metrics,
                "target": targets["priority_focus_source_seed_coverage_rate"],
                "reasons": ["source_lineage_coverage_low"],
            })

    gap_sort_key = lambda item: (
        _category_priority_sort_key(item.get("category")),
        _lens_priority_sort_key(item.get("lens")),
        float(item.get("source_seed_coverage_rate") or 0.0),
        -int(item.get("source_seed_missing") or 0),
    )
    category_gaps.sort(key=gap_sort_key)
    category_lens_gaps.sort(key=gap_sort_key)
    missing_records = [
        record for record in records
        if not bool(record.get("source_seed_lineage_present"))
        or not bool(record.get("query_variant_lineage_present"))
    ]
    missing_records.sort(
        key=lambda record: (
            _category_priority_sort_key(record.get("category")),
            -float(record.get("priority") or 0.0),
            str(record.get("title") or ""),
        )
    )

    return {
        "targets": targets,
        "overall": {
            **overall,
            "priority_focus_total": priority_overall["total"],
            "priority_focus_source_seed_present": priority_overall["source_seed_present"],
            "priority_focus_source_seed_missing": priority_overall["source_seed_missing"],
            "priority_focus_source_seed_coverage_rate": priority_overall[
                "source_seed_coverage_rate"
            ],
            "priority_focus_actionable_strict_total": priority_actionable_overall["total"],
            "priority_focus_actionable_strict_source_seed_present": (
                priority_actionable_overall["source_seed_present"]
            ),
            "priority_focus_actionable_strict_source_seed_missing": (
                priority_actionable_overall["source_seed_missing"]
            ),
            "priority_focus_actionable_strict_source_seed_coverage_rate": (
                priority_actionable_overall["source_seed_coverage_rate"]
            ),
            "ready": bool(source_ready and query_variant_ready),
        },
        "by_category": by_category,
        "by_category_lens": by_category_lens,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": (category_gaps + category_lens_gaps)[:10],
        "missing_samples": [
            _source_lineage_sample(record)
            for record in missing_records[: max(0, int(limit or 0))]
        ],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "missing_samples": len(missing_records),
        },
    }


def _record_matches_lane(record: Dict[str, Any], lane_type: str, lane: str) -> bool:
    if lane_type == "category":
        return record["category"] == lane
    if lane_type == "platform":
        return record["platform"] == lane
    if lane_type == "platform_category":
        platform, _, category = lane.partition("::")
        return record["platform"] == platform and record["category"] == category
    if lane_type == "grade":
        return record["grade"] == lane
    if lane_type == "lens":
        return record["lens"] == lane
    if lane_type == "category_lens":
        category, _, lens = lane.partition("::")
        return record["category"] == category and record["lens"] == lens
    if lane_type == "query_variant":
        return record["query_variant"] == lane
    return False


def _sample_for_lane(
    records: List[Dict[str, Any]],
    lane_type: str,
    lane: str,
    limit: int,
    *,
    diagnostic: bool = False,
    record_filter: Optional[Callable[[Dict[str, Any]], bool]] = None,
) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    matched = [
        record for record in records
        if _record_matches_lane(record, lane_type, lane)
        and (record_filter(record) if record_filter else True)
    ]
    if diagnostic:
        def diagnostic_key(record: Dict[str, Any]) -> tuple:
            status = str(record.get("status") or "")
            strict = bool(record.get("strict_fit"))
            survived = status in SURVIVED_STATUSES
            if not strict and not survived:
                bucket = 0
            elif not strict:
                bucket = 1
            elif not survived:
                bucket = 2
            else:
                bucket = 3
            return (bucket, -float(record.get("priority") or 0.0))

        matched.sort(key=diagnostic_key)
    else:
        matched.sort(
            key=lambda record: (
                bool(record.get("strict_fit")),
                float(record.get("priority") or 0.0),
            ),
            reverse=True,
        )
    return matched[:limit]


def _review_samples(
    records: List[Dict[str, Any]],
    weak_lanes: List[Dict[str, Any]],
    *,
    patient_journey_coverage: Optional[Dict[str, Any]] = None,
    work_queue_readiness: Optional[Dict[str, Any]] = None,
    opportunity_diversity: Optional[Dict[str, Any]] = None,
    engagement_hook_quality: Optional[Dict[str, Any]] = None,
    treatment_signature_quality: Optional[Dict[str, Any]] = None,
    treatment_signal_diversity_quality: Optional[Dict[str, Any]] = None,
    treatment_subintent_diversity_quality: Optional[Dict[str, Any]] = None,
    clinic_modality_quality: Optional[Dict[str, Any]] = None,
    decision_window_quality: Optional[Dict[str, Any]] = None,
    seed_candidate_alignment_quality: Optional[Dict[str, Any]] = None,
    local_intent_quality: Optional[Dict[str, Any]] = None,
    local_area_diversity_quality: Optional[Dict[str, Any]] = None,
    patient_surface_quality: Optional[Dict[str, Any]] = None,
    viral_action_route_quality: Optional[Dict[str, Any]] = None,
    reply_workability_quality: Optional[Dict[str, Any]] = None,
    execution_readiness_quality: Optional[Dict[str, Any]] = None,
    execution_priority_alignment_quality: Optional[Dict[str, Any]] = None,
    platform_surface_quality: Optional[Dict[str, Any]] = None,
    sample_per_lane: int,
) -> Dict[str, Any]:
    strict = [record for record in records if record.get("strict_fit")]
    actionable = [record for record in records if record.get("status") in ACTIONABLE_STATUSES]
    filtered = [
        record for record in records
        if str(record.get("status") or "").startswith(FILTERED_PREFIXES)
        or record.get("status") == "manual_review"
    ]
    sort_key = lambda record: float(record.get("priority") or 0.0)
    strict.sort(key=sort_key, reverse=True)
    actionable.sort(key=sort_key, reverse=True)
    filtered.sort(key=sort_key, reverse=True)

    weak_samples = []
    for lane in weak_lanes[:10]:
        samples = _sample_for_lane(
            records,
            str(lane.get("type") or ""),
            str(lane.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
        )
        if samples:
            weak_samples.append({
                "type": lane.get("type"),
                "lane": lane.get("lane"),
                "reasons": lane.get("reasons") or [],
                "samples": samples,
            })

    focus_weak_samples = []
    for lane in _priority_focus_weak_lanes(weak_lanes, limit=10):
        samples = _sample_for_lane(
            records,
            str(lane.get("type") or ""),
            str(lane.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
        )
        if samples:
            focus_weak_samples.append({
                "type": lane.get("type"),
                "lane": lane.get("lane"),
                "focus_category": lane.get("focus_category"),
                "reasons": lane.get("reasons") or [],
                "samples": samples,
            })

    content_mismatch_samples = []
    for lane in _weak_lanes_for_reason(weak_lanes, "content_category_mismatch", limit=10):
        samples = _sample_for_lane(
            records,
            str(lane.get("type") or ""),
            str(lane.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: bool(record.get("content_category_mismatch")),
        )
        if samples:
            content_mismatch_samples.append({
                "type": lane.get("type"),
                "lane": lane.get("lane"),
                "focus_category": _focus_category_for_weak_lane(lane),
                "mismatch_rate": lane.get("content_category_mismatch_rate", 0.0),
                "reasons": lane.get("reasons") or [],
                "samples": samples,
            })

    lens_surface_mismatch_samples = []
    for lane in _weak_lanes_for_reason(weak_lanes, "lens_surface_mismatch", limit=10):
        samples = _sample_for_lane(
            records,
            str(lane.get("type") or ""),
            str(lane.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("lens_surface_checked"))
                and not bool(record.get("lens_surface_matched"))
            ),
        )
        if samples:
            lens_surface_mismatch_samples.append({
                "type": lane.get("type"),
                "lane": lane.get("lane"),
                "focus_category": _focus_category_for_weak_lane(lane),
                "mismatch_rate": lane.get("lens_surface_mismatch_rate", 0.0),
                "reasons": lane.get("reasons") or [],
                "samples": samples,
            })

    platform_surface_samples = []
    platform_surface_quality = platform_surface_quality or {}
    platform_hotspots = (
        platform_surface_quality.get("priority_focus_hotspots")
        or platform_surface_quality.get("hotspots")
        or []
    )
    for hotspot in platform_hotspots[:10]:
        samples = _sample_for_lane(
            records,
            str(hotspot.get("type") or ""),
            str(hotspot.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
        )
        if samples:
            platform_surface_samples.append({
                "type": hotspot.get("type"),
                "lane": hotspot.get("lane"),
                "platform": hotspot.get("platform"),
                "category": hotspot.get("category"),
                "focus_category": hotspot.get("focus_category", ""),
                "reasons": hotspot.get("reasons") or [],
                "loss_rate": hotspot.get("loss_rate", 0.0),
                "survival_rate": hotspot.get("survival_rate", 0.0),
                "strict_fit_rate": hotspot.get("strict_fit_rate", 0.0),
                "samples": samples,
            })

    patient_journey_gap_samples = []
    patient_journey_coverage = patient_journey_coverage or {}
    journey_gaps = (
        patient_journey_coverage.get("priority_focus_gaps")
        or patient_journey_coverage.get("gaps")
        or []
    )
    for gap in journey_gaps[:10]:
        if not int(gap.get("total") or 0):
            continue
        samples = _sample_for_lane(
            records,
            "category_lens",
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
        )
        if samples:
            patient_journey_gap_samples.append({
                "type": "category_lens",
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens"),
                "reasons": gap.get("reasons") or [],
                "survival_rate": gap.get("survival_rate", 0.0),
                "strict_fit_rate": gap.get("strict_fit_rate", 0.0),
                "samples": samples,
            })

    work_queue_gap_samples = []
    work_queue_readiness = work_queue_readiness or {}
    work_queue_gaps = (
        work_queue_readiness.get("priority_gaps")
        or work_queue_readiness.get("category_lens_gaps")
        or work_queue_readiness.get("category_gaps")
        or []
    )
    for gap in work_queue_gaps[:10]:
        if not int(gap.get("total") or 0):
            continue
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
        )
        if samples:
            work_queue_gap_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "actionable_strict": gap.get("actionable_strict", 0),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    fresh_work_queue_gap_samples = []
    fresh_work_queue_gaps = (
        work_queue_readiness.get("fresh_priority_gaps")
        or work_queue_readiness.get("fresh_category_lens_gaps")
        or work_queue_readiness.get("fresh_category_gaps")
        or []
    )
    for gap in fresh_work_queue_gaps[:10]:
        if not int(gap.get("total") or 0):
            continue
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
        )
        if samples:
            fresh_work_queue_gap_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "fresh_actionable_strict": gap.get("fresh_actionable_strict", 0),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    unique_work_queue_gap_samples = []
    unique_work_queue_gaps = (
        work_queue_readiness.get("unique_priority_gaps")
        or work_queue_readiness.get("unique_category_lens_gaps")
        or work_queue_readiness.get("unique_category_gaps")
        or []
    )
    for gap in unique_work_queue_gaps[:10]:
        if not int(gap.get("total") or 0):
            continue
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
        )
        if samples:
            unique_work_queue_gap_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "actionable_strict": gap.get("actionable_strict", 0),
                "unique_actionable_strict": gap.get("unique_actionable_strict", 0),
                "duplicate_count": gap.get("actionable_strict_duplicate_count", 0),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    fresh_unique_work_queue_gap_samples = []
    fresh_unique_work_queue_gaps = (
        work_queue_readiness.get("fresh_unique_priority_gaps")
        or work_queue_readiness.get("fresh_unique_category_lens_gaps")
        or work_queue_readiness.get("fresh_unique_category_gaps")
        or []
    )
    for gap in fresh_unique_work_queue_gaps[:10]:
        if not int(gap.get("total") or 0):
            continue
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
        )
        if samples:
            fresh_unique_work_queue_gap_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "fresh_actionable_strict": gap.get("fresh_actionable_strict", 0),
                "unique_fresh_actionable_strict": gap.get("unique_fresh_actionable_strict", 0),
                "duplicate_count": gap.get("fresh_actionable_strict_duplicate_count", 0),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    opportunity_diversity_samples = []
    opportunity_diversity = opportunity_diversity or {}
    diversity_gaps = (
        opportunity_diversity.get("priority_gaps")
        or opportunity_diversity.get("category_lens_gaps")
        or opportunity_diversity.get("category_gaps")
        or []
    )
    for gap in diversity_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            opportunity_diversity_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_actionable_strict": gap.get("unique_actionable_strict", 0),
                "platform_count": gap.get("platform_count", 0),
                "source_seed_count": gap.get("source_seed_count", 0),
                "variant_family_count": gap.get("variant_family_count", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    fresh_opportunity_diversity_samples = []
    fresh_diversity_gaps = (
        opportunity_diversity.get("fresh_priority_gaps")
        or opportunity_diversity.get("fresh_category_lens_gaps")
        or opportunity_diversity.get("fresh_category_gaps")
        or []
    )
    for gap in fresh_diversity_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and bool(record.get("fresh_activity"))
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            fresh_opportunity_diversity_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_actionable_strict": gap.get("unique_actionable_strict", 0),
                "platform_count": gap.get("platform_count", 0),
                "source_seed_count": gap.get("source_seed_count", 0),
                "variant_family_count": gap.get("variant_family_count", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    engagement_hook_samples = []
    engagement_hook_quality = engagement_hook_quality or {}
    engagement_hook_gaps = (
        engagement_hook_quality.get("priority_gaps")
        or engagement_hook_quality.get("category_lens_gaps")
        or engagement_hook_quality.get("category_gaps")
        or []
    )
    for gap in engagement_hook_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and not bool(record.get("engagement_hook_matched"))
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            engagement_hook_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_actionable_strict": gap.get("unique_actionable_strict", 0),
                "hooked_actionable_strict": gap.get("hooked_actionable_strict", 0),
                "engagement_hook_missing": gap.get("engagement_hook_missing", 0),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    fresh_engagement_hook_samples = []
    fresh_engagement_hook_gaps = (
        engagement_hook_quality.get("fresh_priority_gaps")
        or engagement_hook_quality.get("fresh_category_lens_gaps")
        or engagement_hook_quality.get("fresh_category_gaps")
        or []
    )
    for gap in fresh_engagement_hook_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and bool(record.get("fresh_activity"))
                and not bool(record.get("engagement_hook_matched"))
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                    and bool(record.get("fresh_activity"))
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            fresh_engagement_hook_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_fresh_actionable_strict": gap.get("unique_fresh_actionable_strict", 0),
                "fresh_hooked_actionable_strict": gap.get("fresh_hooked_actionable_strict", 0),
                "engagement_hook_missing": gap.get("engagement_hook_missing", 0),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    treatment_signature_samples = []
    treatment_signature_quality = treatment_signature_quality or {}
    treatment_signature_gaps = (
        treatment_signature_quality.get("priority_gaps")
        or treatment_signature_quality.get("category_lens_gaps")
        or treatment_signature_quality.get("category_gaps")
        or []
    )
    for gap in treatment_signature_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and not bool(record.get("treatment_signature_matched"))
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            treatment_signature_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_actionable_strict": gap.get("unique_actionable_strict", 0),
                "signature_actionable_strict": gap.get("signature_actionable_strict", 0),
                "treatment_signature_missing": gap.get("treatment_signature_missing", 0),
                "expected_treatment_signature_terms": gap.get("expected_treatment_signature_terms", []),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    fresh_treatment_signature_samples = []
    fresh_treatment_signature_gaps = (
        treatment_signature_quality.get("fresh_priority_gaps")
        or treatment_signature_quality.get("fresh_category_lens_gaps")
        or treatment_signature_quality.get("fresh_category_gaps")
        or []
    )
    for gap in fresh_treatment_signature_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and bool(record.get("fresh_activity"))
                and not bool(record.get("treatment_signature_matched"))
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                    and bool(record.get("fresh_activity"))
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            fresh_treatment_signature_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_fresh_actionable_strict": gap.get("unique_fresh_actionable_strict", 0),
                "fresh_signature_actionable_strict": gap.get("fresh_signature_actionable_strict", 0),
                "treatment_signature_missing": gap.get("treatment_signature_missing", 0),
                "expected_treatment_signature_terms": gap.get("expected_treatment_signature_terms", []),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    treatment_signal_diversity_samples = []
    treatment_signal_diversity_quality = treatment_signal_diversity_quality or {}
    treatment_signal_diversity_gaps = (
        treatment_signal_diversity_quality.get("priority_gaps")
        or treatment_signal_diversity_quality.get("category_lens_gaps")
        or treatment_signal_diversity_quality.get("category_gaps")
        or []
    )
    for gap in treatment_signal_diversity_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and bool(record.get("treatment_signature_matched"))
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            treatment_signal_diversity_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_actionable_strict": gap.get("unique_actionable_strict", 0),
                "treatment_signal_actionable_strict": gap.get("treatment_signal_actionable_strict", 0),
                "distinct_treatment_signal_terms": gap.get("distinct_treatment_signal_terms", 0),
                "min_distinct_treatment_signal_terms": gap.get("min_distinct_treatment_signal_terms", 0),
                "treatment_signal_diversity_gap": gap.get("treatment_signal_diversity_gap", 0),
                "treatment_signal_terms": gap.get("treatment_signal_terms", []),
                "expected_treatment_signal_terms": gap.get("expected_treatment_signal_terms", []),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    fresh_treatment_signal_diversity_samples = []
    fresh_treatment_signal_diversity_gaps = (
        treatment_signal_diversity_quality.get("fresh_priority_gaps")
        or treatment_signal_diversity_quality.get("fresh_category_lens_gaps")
        or treatment_signal_diversity_quality.get("fresh_category_gaps")
        or []
    )
    for gap in fresh_treatment_signal_diversity_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and bool(record.get("fresh_activity"))
                and bool(record.get("treatment_signature_matched"))
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                    and bool(record.get("fresh_activity"))
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            fresh_treatment_signal_diversity_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_fresh_actionable_strict": gap.get("unique_fresh_actionable_strict", 0),
                "fresh_treatment_signal_actionable_strict": gap.get(
                    "fresh_treatment_signal_actionable_strict",
                    0,
                ),
                "distinct_treatment_signal_terms": gap.get("distinct_treatment_signal_terms", 0),
                "min_distinct_treatment_signal_terms": gap.get("min_distinct_treatment_signal_terms", 0),
                "treatment_signal_diversity_gap": gap.get("treatment_signal_diversity_gap", 0),
                "treatment_signal_terms": gap.get("treatment_signal_terms", []),
                "expected_treatment_signal_terms": gap.get("expected_treatment_signal_terms", []),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    treatment_subintent_diversity_samples = []
    treatment_subintent_diversity_quality = treatment_subintent_diversity_quality or {}
    treatment_subintent_diversity_gaps = (
        treatment_subintent_diversity_quality.get("priority_gaps")
        or treatment_subintent_diversity_quality.get("category_lens_gaps")
        or treatment_subintent_diversity_quality.get("category_gaps")
        or []
    )
    for gap in treatment_subintent_diversity_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and bool(record.get("treatment_subintent_matched"))
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            treatment_subintent_diversity_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_actionable_strict": gap.get("unique_actionable_strict", 0),
                "treatment_subintent_actionable_strict": gap.get(
                    "treatment_subintent_actionable_strict",
                    0,
                ),
                "distinct_treatment_subintent_buckets": gap.get(
                    "distinct_treatment_subintent_buckets",
                    0,
                ),
                "min_distinct_treatment_subintent_buckets": gap.get(
                    "min_distinct_treatment_subintent_buckets",
                    0,
                ),
                "treatment_subintent_diversity_gap": gap.get("treatment_subintent_diversity_gap", 0),
                "treatment_subintent_buckets": gap.get("treatment_subintent_buckets", []),
                "treatment_subintent_terms": gap.get("treatment_subintent_terms", []),
                "treatment_subintent_bucket_terms": gap.get("treatment_subintent_bucket_terms", {}),
                "expected_treatment_subintent_buckets": gap.get(
                    "expected_treatment_subintent_buckets",
                    [],
                ),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    fresh_treatment_subintent_diversity_samples = []
    fresh_treatment_subintent_diversity_gaps = (
        treatment_subintent_diversity_quality.get("fresh_priority_gaps")
        or treatment_subintent_diversity_quality.get("fresh_category_lens_gaps")
        or treatment_subintent_diversity_quality.get("fresh_category_gaps")
        or []
    )
    for gap in fresh_treatment_subintent_diversity_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and bool(record.get("fresh_activity"))
                and bool(record.get("treatment_subintent_matched"))
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                    and bool(record.get("fresh_activity"))
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            fresh_treatment_subintent_diversity_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_fresh_actionable_strict": gap.get("unique_fresh_actionable_strict", 0),
                "fresh_treatment_subintent_actionable_strict": gap.get(
                    "fresh_treatment_subintent_actionable_strict",
                    0,
                ),
                "distinct_treatment_subintent_buckets": gap.get(
                    "distinct_treatment_subintent_buckets",
                    0,
                ),
                "min_distinct_treatment_subintent_buckets": gap.get(
                    "min_distinct_treatment_subintent_buckets",
                    0,
                ),
                "treatment_subintent_diversity_gap": gap.get("treatment_subintent_diversity_gap", 0),
                "treatment_subintent_buckets": gap.get("treatment_subintent_buckets", []),
                "treatment_subintent_terms": gap.get("treatment_subintent_terms", []),
                "treatment_subintent_bucket_terms": gap.get("treatment_subintent_bucket_terms", {}),
                "expected_treatment_subintent_buckets": gap.get(
                    "expected_treatment_subintent_buckets",
                    [],
                ),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    local_intent_samples = []
    local_intent_quality = local_intent_quality or {}
    local_intent_gaps = (
        local_intent_quality.get("priority_gaps")
        or local_intent_quality.get("category_lens_gaps")
        or local_intent_quality.get("category_gaps")
        or []
    )
    for gap in local_intent_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and not bool(record.get("local_intent_matched"))
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            local_intent_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_actionable_strict": gap.get("unique_actionable_strict", 0),
                "local_actionable_strict": gap.get("local_actionable_strict", 0),
                "local_intent_missing": gap.get("local_intent_missing", 0),
                "expected_local_intent_terms": gap.get("expected_local_intent_terms", []),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    fresh_local_intent_samples = []
    fresh_local_intent_gaps = (
        local_intent_quality.get("fresh_priority_gaps")
        or local_intent_quality.get("fresh_category_lens_gaps")
        or local_intent_quality.get("fresh_category_gaps")
        or []
    )
    for gap in fresh_local_intent_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and bool(record.get("fresh_activity"))
                and not bool(record.get("local_intent_matched"))
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                    and bool(record.get("fresh_activity"))
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            fresh_local_intent_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_fresh_actionable_strict": gap.get("unique_fresh_actionable_strict", 0),
                "fresh_local_actionable_strict": gap.get("fresh_local_actionable_strict", 0),
                "local_intent_missing": gap.get("local_intent_missing", 0),
                "expected_local_intent_terms": gap.get("expected_local_intent_terms", []),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    patient_surface_samples = []
    patient_surface_quality = patient_surface_quality or {}
    patient_surface_gaps = (
        patient_surface_quality.get("priority_gaps")
        or patient_surface_quality.get("category_lens_gaps")
        or patient_surface_quality.get("category_gaps")
        or []
    )
    for gap in patient_surface_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and (
                    not bool(record.get("patient_surface_matched"))
                    or bool(record.get("patient_surface_provider_noise"))
                )
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            patient_surface_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_actionable_strict": gap.get("unique_actionable_strict", 0),
                "patient_surface_actionable_strict": gap.get("patient_surface_actionable_strict", 0),
                "patient_surface_missing": gap.get("patient_surface_missing", 0),
                "provider_surface_noise": gap.get("provider_surface_noise", 0),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    fresh_patient_surface_samples = []
    fresh_patient_surface_gaps = (
        patient_surface_quality.get("fresh_priority_gaps")
        or patient_surface_quality.get("fresh_category_lens_gaps")
        or patient_surface_quality.get("fresh_category_gaps")
        or []
    )
    for gap in fresh_patient_surface_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and bool(record.get("fresh_activity"))
                and (
                    not bool(record.get("patient_surface_matched"))
                    or bool(record.get("patient_surface_provider_noise"))
                )
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                    and bool(record.get("fresh_activity"))
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            fresh_patient_surface_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_fresh_actionable_strict": gap.get("unique_fresh_actionable_strict", 0),
                "fresh_patient_surface_actionable_strict": gap.get(
                    "fresh_patient_surface_actionable_strict",
                    0,
                ),
                "patient_surface_missing": gap.get("patient_surface_missing", 0),
                "provider_surface_noise": gap.get("provider_surface_noise", 0),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    viral_action_route_samples = []
    viral_action_route_quality = viral_action_route_quality or {}
    viral_action_route_gaps = (
        viral_action_route_quality.get("priority_gaps")
        or viral_action_route_quality.get("category_lens_gaps")
        or viral_action_route_quality.get("category_gaps")
        or []
    )
    for gap in viral_action_route_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and (
                    not bool(record.get("viral_action_route_matched"))
                    or bool(record.get("viral_action_route_mismatch"))
                )
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            viral_action_route_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_actionable_strict": gap.get("unique_actionable_strict", 0),
                "routed_actionable_strict": gap.get("routed_actionable_strict", 0),
                "viral_action_route_missing": gap.get("viral_action_route_missing", 0),
                "viral_action_route_mismatch": gap.get("viral_action_route_mismatch", 0),
                "expected_viral_action_routes": gap.get("expected_viral_action_routes", []),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    fresh_viral_action_route_samples = []
    fresh_viral_action_route_gaps = (
        viral_action_route_quality.get("fresh_priority_gaps")
        or viral_action_route_quality.get("fresh_category_lens_gaps")
        or viral_action_route_quality.get("fresh_category_gaps")
        or []
    )
    for gap in fresh_viral_action_route_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and bool(record.get("fresh_activity"))
                and (
                    not bool(record.get("viral_action_route_matched"))
                    or bool(record.get("viral_action_route_mismatch"))
                )
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                    and bool(record.get("fresh_activity"))
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            fresh_viral_action_route_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_fresh_actionable_strict": gap.get("unique_fresh_actionable_strict", 0),
                "fresh_routed_actionable_strict": gap.get("fresh_routed_actionable_strict", 0),
                "viral_action_route_missing": gap.get("viral_action_route_missing", 0),
                "viral_action_route_mismatch": gap.get("viral_action_route_mismatch", 0),
                "expected_viral_action_routes": gap.get("expected_viral_action_routes", []),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    reply_workability_samples = []
    reply_workability_quality = reply_workability_quality or {}
    reply_workability_gaps = (
        reply_workability_quality.get("priority_gaps")
        or reply_workability_quality.get("category_lens_gaps")
        or reply_workability_quality.get("category_gaps")
        or []
    )
    for gap in reply_workability_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and (
                    not bool(record.get("reply_workability_matched"))
                    or bool(record.get("reply_risk_blocked"))
                    or bool(record.get("reply_metric_missing"))
                )
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            reply_workability_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_actionable_strict": gap.get("unique_actionable_strict", 0),
                "reply_workable_actionable_strict": gap.get("reply_workable_actionable_strict", 0),
                "reply_workability_missing": gap.get("reply_workability_missing", 0),
                "reply_risk_flagged": gap.get("reply_risk_flagged", 0),
                "reply_metric_missing": gap.get("reply_metric_missing", 0),
                "avg_reply_opportunity_score": gap.get("avg_reply_opportunity_score"),
                "reply_opportunity_tiers": gap.get("reply_opportunity_tiers", []),
                "reply_opportunity_signals": gap.get("reply_opportunity_signals", []),
                "reply_risk_flags": gap.get("reply_risk_flags", []),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    fresh_reply_workability_samples = []
    fresh_reply_workability_gaps = (
        reply_workability_quality.get("fresh_priority_gaps")
        or reply_workability_quality.get("fresh_category_lens_gaps")
        or reply_workability_quality.get("fresh_category_gaps")
        or []
    )
    for gap in fresh_reply_workability_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and bool(record.get("fresh_activity"))
                and (
                    not bool(record.get("reply_workability_matched"))
                    or bool(record.get("reply_risk_blocked"))
                    or bool(record.get("reply_metric_missing"))
                )
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                    and bool(record.get("fresh_activity"))
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            fresh_reply_workability_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_fresh_actionable_strict": gap.get("unique_fresh_actionable_strict", 0),
                "fresh_reply_workable_actionable_strict": gap.get(
                    "fresh_reply_workable_actionable_strict",
                    0,
                ),
                "reply_workability_missing": gap.get("reply_workability_missing", 0),
                "reply_risk_flagged": gap.get("reply_risk_flagged", 0),
                "reply_metric_missing": gap.get("reply_metric_missing", 0),
                "avg_reply_opportunity_score": gap.get("avg_reply_opportunity_score"),
                "reply_opportunity_tiers": gap.get("reply_opportunity_tiers", []),
                "reply_opportunity_signals": gap.get("reply_opportunity_signals", []),
                "reply_risk_flags": gap.get("reply_risk_flags", []),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    execution_readiness_samples = []
    execution_readiness_quality = execution_readiness_quality or {}
    execution_readiness_gaps = (
        execution_readiness_quality.get("priority_gaps")
        or execution_readiness_quality.get("category_lens_gaps")
        or execution_readiness_quality.get("category_gaps")
        or []
    )
    for gap in execution_readiness_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and not _execution_ready_record(record)
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            execution_readiness_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_actionable_strict": gap.get("unique_actionable_strict", 0),
                "execution_ready_actionable_strict": gap.get("execution_ready_actionable_strict", 0),
                "execution_readiness_missing": gap.get("execution_readiness_missing", 0),
                "execution_readiness_component_counts": gap.get(
                    "execution_readiness_component_counts",
                    {},
                ),
                "execution_readiness_missing_components": gap.get(
                    "execution_readiness_missing_components",
                    {},
                ),
                "fragmented_execution_signals": gap.get("fragmented_execution_signals", False),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    fresh_execution_readiness_samples = []
    fresh_execution_readiness_gaps = (
        execution_readiness_quality.get("fresh_priority_gaps")
        or execution_readiness_quality.get("fresh_category_lens_gaps")
        or execution_readiness_quality.get("fresh_category_gaps")
        or []
    )
    for gap in fresh_execution_readiness_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and bool(record.get("fresh_activity"))
                and not _execution_ready_record(record)
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                    and bool(record.get("fresh_activity"))
                ),
            )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
            )
        if samples:
            fresh_execution_readiness_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_fresh_actionable_strict": gap.get("unique_fresh_actionable_strict", 0),
                "fresh_execution_ready_actionable_strict": gap.get(
                    "fresh_execution_ready_actionable_strict",
                    0,
                ),
                "execution_readiness_missing": gap.get("execution_readiness_missing", 0),
                "execution_readiness_component_counts": gap.get(
                    "execution_readiness_component_counts",
                    {},
                ),
                "execution_readiness_missing_components": gap.get(
                    "execution_readiness_missing_components",
                    {},
                ),
                "fragmented_execution_signals": gap.get("fragmented_execution_signals", False),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    execution_priority_alignment_samples = []
    execution_priority_alignment_quality = execution_priority_alignment_quality or {}
    execution_priority_alignment_gaps = (
        execution_priority_alignment_quality.get("priority_gaps")
        or execution_priority_alignment_quality.get("category_lens_gaps")
        or execution_priority_alignment_quality.get("category_gaps")
        or []
    )
    for gap in execution_priority_alignment_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and not _execution_ready_record(record)
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                ),
            )
        if samples:
            execution_priority_alignment_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "priority_top_window": gap.get("priority_top_window", 0),
                "unique_actionable_strict": gap.get("unique_actionable_strict", 0),
                "execution_ready_actionable_strict": gap.get("execution_ready_actionable_strict", 0),
                "top_execution_ready_actionable_strict": gap.get(
                    "top_execution_ready_actionable_strict",
                    0,
                ),
                "top_non_execution_ready_actionable_strict": gap.get(
                    "top_non_execution_ready_actionable_strict",
                    0,
                ),
                "highest_execution_ready_rank": gap.get("highest_execution_ready_rank"),
                "target_execution_ready_ranks": gap.get("target_execution_ready_ranks", []),
                "execution_priority_gap": gap.get("execution_priority_gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    fresh_execution_priority_alignment_samples = []
    fresh_execution_priority_alignment_gaps = (
        execution_priority_alignment_quality.get("fresh_priority_gaps")
        or execution_priority_alignment_quality.get("fresh_category_lens_gaps")
        or execution_priority_alignment_quality.get("fresh_category_gaps")
        or []
    )
    for gap in fresh_execution_priority_alignment_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and bool(record.get("fresh_activity"))
                and not _execution_ready_record(record)
            ),
        )
        if not samples:
            samples = _sample_for_lane(
                records,
                str(gap.get("type") or ""),
                str(gap.get("lane") or ""),
                sample_per_lane,
                diagnostic=True,
                record_filter=lambda record: (
                    bool(record.get("strict_fit"))
                    and record.get("status") in ACTIONABLE_STATUSES
                    and bool(record.get("fresh_activity"))
                ),
            )
        if samples:
            fresh_execution_priority_alignment_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "priority_top_window": gap.get("priority_top_window", 0),
                "unique_fresh_actionable_strict": gap.get("unique_fresh_actionable_strict", 0),
                "fresh_execution_ready_actionable_strict": gap.get(
                    "fresh_execution_ready_actionable_strict",
                    0,
                ),
                "fresh_top_execution_ready_actionable_strict": gap.get(
                    "fresh_top_execution_ready_actionable_strict",
                    0,
                ),
                "top_non_execution_ready_actionable_strict": gap.get(
                    "top_non_execution_ready_actionable_strict",
                    0,
                ),
                "highest_execution_ready_rank": gap.get("highest_execution_ready_rank"),
                "target_execution_ready_ranks": gap.get("target_execution_ready_ranks", []),
                "execution_priority_gap": gap.get("execution_priority_gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    seed_candidate_alignment_samples = []
    seed_candidate_alignment_quality = seed_candidate_alignment_quality or {}
    seed_candidate_alignment_gaps = (
        seed_candidate_alignment_quality.get("priority_gaps")
        or seed_candidate_alignment_quality.get("category_lens_gaps")
        or seed_candidate_alignment_quality.get("category_gaps")
        or []
    )
    for gap in seed_candidate_alignment_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and not bool(record.get("seed_candidate_alignment_matched"))
            ),
        )
        if samples:
            seed_candidate_alignment_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_actionable_strict": gap.get("unique_actionable_strict", 0),
                "seed_aligned_actionable_strict": gap.get("seed_aligned_actionable_strict", 0),
                "seed_candidate_alignment_missing": gap.get("seed_candidate_alignment_missing", 0),
                "avg_seed_candidate_overlap_rate": gap.get("avg_seed_candidate_overlap_rate", 0.0),
                "seed_candidate_matched_terms": gap.get("seed_candidate_matched_terms", []),
                "seed_candidate_missing_terms": gap.get("seed_candidate_missing_terms", []),
                "seed_candidate_missing_reasons": gap.get("seed_candidate_missing_reasons", {}),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    fresh_seed_candidate_alignment_samples = []
    fresh_seed_candidate_alignment_gaps = (
        seed_candidate_alignment_quality.get("fresh_priority_gaps")
        or seed_candidate_alignment_quality.get("fresh_category_lens_gaps")
        or seed_candidate_alignment_quality.get("fresh_category_gaps")
        or []
    )
    for gap in fresh_seed_candidate_alignment_gaps[:10]:
        samples = _sample_for_lane(
            records,
            str(gap.get("type") or ""),
            str(gap.get("lane") or ""),
            sample_per_lane,
            diagnostic=True,
            record_filter=lambda record: (
                bool(record.get("strict_fit"))
                and record.get("status") in ACTIONABLE_STATUSES
                and bool(record.get("fresh_activity"))
                and not bool(record.get("seed_candidate_alignment_matched"))
            ),
        )
        if samples:
            fresh_seed_candidate_alignment_samples.append({
                "type": gap.get("type"),
                "lane": gap.get("lane"),
                "category": gap.get("category"),
                "lens": gap.get("lens", ""),
                "target": gap.get("target", 0),
                "unique_fresh_actionable_strict": gap.get("unique_fresh_actionable_strict", 0),
                "fresh_seed_aligned_actionable_strict": gap.get(
                    "fresh_seed_aligned_actionable_strict",
                    0,
                ),
                "fresh_seed_candidate_alignment_missing": gap.get(
                    "seed_candidate_alignment_missing",
                    0,
                ),
                "avg_seed_candidate_overlap_rate": gap.get("avg_seed_candidate_overlap_rate", 0.0),
                "seed_candidate_matched_terms": gap.get("seed_candidate_matched_terms", []),
                "seed_candidate_missing_terms": gap.get("seed_candidate_missing_terms", []),
                "seed_candidate_missing_reasons": gap.get("seed_candidate_missing_reasons", {}),
                "gap": gap.get("gap", 0),
                "reasons": gap.get("reasons") or [],
                "samples": samples,
            })

    return {
        "top_strict_fit": strict[:sample_per_lane],
        "top_actionable": actionable[:sample_per_lane],
        "top_filtered": filtered[:sample_per_lane],
        "priority_focus_weak_lane_samples": focus_weak_samples,
        "content_mismatch_samples": content_mismatch_samples,
        "lens_surface_mismatch_samples": lens_surface_mismatch_samples,
        "platform_surface_samples": platform_surface_samples,
        "patient_journey_gap_samples": patient_journey_gap_samples,
        "work_queue_gap_samples": work_queue_gap_samples,
        "fresh_work_queue_gap_samples": fresh_work_queue_gap_samples,
        "unique_work_queue_gap_samples": unique_work_queue_gap_samples,
        "fresh_unique_work_queue_gap_samples": fresh_unique_work_queue_gap_samples,
        "opportunity_diversity_gap_samples": opportunity_diversity_samples,
        "fresh_opportunity_diversity_gap_samples": fresh_opportunity_diversity_samples,
        "engagement_hook_gap_samples": engagement_hook_samples,
        "fresh_engagement_hook_gap_samples": fresh_engagement_hook_samples,
        "treatment_signature_gap_samples": treatment_signature_samples,
        "fresh_treatment_signature_gap_samples": fresh_treatment_signature_samples,
        "treatment_signal_diversity_gap_samples": treatment_signal_diversity_samples,
        "fresh_treatment_signal_diversity_gap_samples": fresh_treatment_signal_diversity_samples,
        "treatment_subintent_diversity_gap_samples": treatment_subintent_diversity_samples,
        "fresh_treatment_subintent_diversity_gap_samples": fresh_treatment_subintent_diversity_samples,
        "seed_candidate_alignment_gap_samples": seed_candidate_alignment_samples,
        "fresh_seed_candidate_alignment_gap_samples": fresh_seed_candidate_alignment_samples,
        "local_intent_gap_samples": local_intent_samples,
        "fresh_local_intent_gap_samples": fresh_local_intent_samples,
        "patient_surface_gap_samples": patient_surface_samples,
        "fresh_patient_surface_gap_samples": fresh_patient_surface_samples,
        "viral_action_route_gap_samples": viral_action_route_samples,
        "fresh_viral_action_route_gap_samples": fresh_viral_action_route_samples,
        "reply_workability_gap_samples": reply_workability_samples,
        "fresh_reply_workability_gap_samples": fresh_reply_workability_samples,
        "execution_readiness_gap_samples": execution_readiness_samples,
        "fresh_execution_readiness_gap_samples": fresh_execution_readiness_samples,
        "execution_priority_alignment_gap_samples": execution_priority_alignment_samples,
        "fresh_execution_priority_alignment_gap_samples": fresh_execution_priority_alignment_samples,
        "weak_lane_samples": weak_samples,
    }


def latest_viral_source_scan_id(db_path: Optional[str] = None) -> Optional[int]:
    path = db_path or _default_db_path()
    if not os.path.exists(path):
        return None
    with sqlite3.connect(path) as conn:
        if not _table_exists(conn, "viral_targets"):
            return None
        columns = _columns(conn, "viral_targets")
        if "source_scan_run_id" not in columns:
            return None
        row = conn.execute(
            """
            SELECT MAX(source_scan_run_id)
            FROM viral_targets
            WHERE COALESCE(source_scan_run_id, 0) > 0
            """
        ).fetchone()
        scan_id = row[0] if row else None
        return int(scan_id) if scan_id else None


def _fetch_rows(
    conn: sqlite3.Connection,
    *,
    source_scan_run_id: Optional[int],
    days: Optional[int],
    since: Optional[str],
    limit: Optional[int],
) -> List[sqlite3.Row]:
    columns = _columns(conn, "viral_targets")
    if not columns:
        return []

    select_cols = [
        _select_expr(columns, "id", "''"),
        _select_expr(columns, "url", "''"),
        _select_expr(columns, "canonical_url", "''"),
        _select_expr(columns, "title", "''"),
        _select_expr(columns, "content_preview", "''"),
        _select_expr(columns, "platform", "''"),
        _select_expr(columns, "category", "'기타'"),
        _select_expr(columns, "matched_keyword", "''"),
        _select_expr(columns, "matched_keywords", "'[]'"),
        _select_expr(columns, "matched_keyword_grade", "''"),
        _select_expr(columns, "matched_keyword_category", "''"),
        _select_expr(columns, "comment_status", "'pending'"),
        _select_expr(columns, "priority_score", "0"),
        _select_expr(columns, "score_breakdown", "'{}'"),
        _select_expr(columns, "source_scan_run_id", "0"),
        _select_expr(columns, "discovered_at", "''"),
        _select_expr(columns, "last_scanned_at", "''"),
        _select_expr(columns, "posted_at", "''"),
        _select_expr(columns, "author", "''"),
        _select_expr(columns, "comment_count", "0"),
        _select_expr(columns, "view_count", "0"),
        _select_expr(columns, "like_count", "0"),
    ]
    where: List[str] = []
    params: List[Any] = []
    if source_scan_run_id is not None and "source_scan_run_id" in columns:
        where.append("COALESCE(source_scan_run_id, 0) = ?")
        params.append(int(source_scan_run_id))
    time_columns = [
        column for column in ("discovered_at", "last_scanned_at")
        if column in columns
    ]
    if since and time_columns:
        where.append(
            "("
            + " OR ".join(f"REPLACE(COALESCE({column}, ''), 'T', ' ') >= ?" for column in time_columns)
            + ")"
        )
        params.extend(str(since).replace("T", " ") for _ in time_columns)
    elif days is not None and time_columns:
        where.append(
            "("
            + " OR ".join(f"REPLACE(COALESCE({column}, ''), 'T', ' ') >= datetime('now', ?)" for column in time_columns)
            + ")"
        )
        params.extend(f"-{int(days)} day" for _ in time_columns)
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    limit_sql = ""
    if limit is not None and int(limit) > 0:
        limit_sql = f" LIMIT {int(limit)}"

    conn.row_factory = sqlite3.Row
    return conn.execute(
        f"""
        SELECT {", ".join(select_cols)}
        FROM viral_targets
        {where_sql}
        ORDER BY COALESCE(priority_score, 0) DESC, discovered_at DESC
        {limit_sql}
        """,
        params,
    ).fetchall()


def _is_strict_fit(
    *,
    status: str,
    lens: str,
    axis_fit: Optional[float],
    lens_fit: Optional[float],
    clinic_fit: Optional[float],
    worksite_efficiency: Optional[float],
    min_axis_fit: float,
    min_lens_fit: float,
    min_clinic_fit: float,
    min_worksite_efficiency: float,
) -> bool:
    if status not in SURVIVED_STATUSES:
        return False
    axis_ok = (axis_fit if axis_fit is not None else clinic_fit or 0.0) >= min_axis_fit
    clinic_ok = (clinic_fit or 0.0) >= min_clinic_fit
    worksite_ok = (worksite_efficiency or 0.0) >= min_worksite_efficiency
    if lens in {"", "unknown", "service"}:
        lens_ok = True
    else:
        lens_ok = (lens_fit if lens_fit is not None else 0.0) >= min_lens_fit
    return bool(axis_ok and lens_ok and clinic_ok and worksite_ok)


def _weak_lane_reasons(metrics: Dict[str, Any], *, min_lane_total: int) -> List[str]:
    if int(metrics.get("total") or 0) < min_lane_total:
        return []
    reasons: List[str] = []
    if float(metrics.get("axis_coverage_rate") or 0.0) < 0.50:
        reasons.append("missing_axis_fit_metrics")
    if float(metrics.get("lens_coverage_rate") or 0.0) < 0.50 and set(metrics.get("lens_counts") or {}) - {"unknown", "service"}:
        reasons.append("missing_lens_fit_metrics")
    if float(metrics.get("survival_rate") or 0.0) < 0.35:
        reasons.append("low_survival_rate")
    if float(metrics.get("strict_fit_rate") or 0.0) < 0.25:
        reasons.append("low_strict_fit_rate")
    if metrics.get("axis_observed") and float(metrics.get("avg_axis_fit") or 0.0) < 55.0:
        reasons.append("low_axis_fit")
    if metrics.get("lens_observed") and float(metrics.get("avg_lens_fit") or 0.0) < 55.0:
        reasons.append("low_lens_fit")
    if (
        int(metrics.get("content_category_observed") or 0) >= max(3, min_lane_total)
        and float(metrics.get("content_category_mismatch_rate") or 0.0) > 0.10
    ):
        reasons.append("content_category_mismatch")
    if (
        int(metrics.get("lens_surface_checked") or 0) >= max(3, min_lane_total)
        and float(metrics.get("lens_surface_mismatch_rate") or 0.0) > 0.35
    ):
        reasons.append("lens_surface_mismatch")
    worksite_observed = int(metrics.get("worksite_efficiency_observed") or 0)
    if (
        worksite_observed >= max(3, min_lane_total)
        and float(metrics.get("avg_worksite_efficiency") or 0.0) < 55.0
    ):
        reasons.append("low_worksite_efficiency")
    return reasons


def _action_for_reason(reason: str) -> str:
    actions = {
        "missing_axis_fit_metrics": "rerun Viral Hunter with current scoring or rescore stored targets to populate pathfinder_axis_fit_*",
        "missing_lens_fit_metrics": "rerun Viral Hunter with current scoring or rescore stored targets to populate pathfinder_lens_fit_*",
        "low_survival_rate": "inspect filtered statuses and tune search surfaces before increasing volume",
        "low_strict_fit_rate": "tighten seed-to-post fit gates for this lane before scaling outreach",
        "low_axis_fit": "tighten treatment-axis query anchors and negative terms for this lane",
        "low_lens_fit": "adjust lens-specific query variants and post-fit terms for this lane",
        "content_category_mismatch": "inspect discovered post titles/bodies and add negative or recategorization rules for this lane",
        "lens_surface_mismatch": "tighten execution-lens query variants or lower priority for posts without the intended patient surface",
        "low_worksite_efficiency": "prefer higher-workability surfaces, recency, unanswered threads, and cafe/kin depth for this lane",
    }
    return actions.get(reason, "review this lane manually before scaling")


def _lane_seed_coverage(
    seed_counts: Dict[str, int],
    lane_summary: Dict[str, Dict[str, Any]],
    *,
    min_targets_per_seed: float,
    min_strict_fit_per_seed: float,
) -> Dict[str, Dict[str, Any]]:
    coverage: Dict[str, Dict[str, Any]] = {}
    for lane, raw_seed_count in sorted((seed_counts or {}).items()):
        seed_count = int(raw_seed_count or 0)
        if seed_count <= 0:
            continue
        metrics = lane_summary.get(lane) or {}
        target_count = int(metrics.get("total") or 0)
        survived = int(metrics.get("survived") or 0)
        strict_fit = int(metrics.get("strict_fit") or 0)
        target_per_seed = round(target_count / seed_count, 4)
        survived_per_seed = round(survived / seed_count, 4)
        strict_fit_per_seed = round(strict_fit / seed_count, 4)
        gap_reasons: List[str] = []
        if target_count == 0:
            gap_reasons.append("no_targets")
        elif target_per_seed < min_targets_per_seed:
            gap_reasons.append("low_target_per_seed")
        if strict_fit_per_seed < min_strict_fit_per_seed:
            gap_reasons.append("low_strict_fit_per_seed")
        if metrics and float(metrics.get("survival_rate") or 0.0) < 0.35:
            gap_reasons.append("low_survival_rate")
        coverage[lane] = {
            "seed_count": seed_count,
            "target_count": target_count,
            "survived": survived,
            "strict_fit": strict_fit,
            "target_per_seed": target_per_seed,
            "survived_per_seed": survived_per_seed,
            "strict_fit_per_seed": strict_fit_per_seed,
            "survival_rate": float(metrics.get("survival_rate") or 0.0),
            "strict_fit_rate": float(metrics.get("strict_fit_rate") or 0.0),
            "gap_reasons": list(dict.fromkeys(gap_reasons)),
        }
    return coverage


def _seed_target_coverage(
    baseline: Dict[str, Any],
    *,
    category_summary: Dict[str, Dict[str, Any]],
    lens_summary: Dict[str, Dict[str, Any]],
    category_lens_summary: Optional[Dict[str, Dict[str, Any]]] = None,
    min_targets_per_seed: float,
    min_strict_fit_per_seed: float,
) -> Dict[str, Any]:
    if not baseline:
        return {}
    by_category = _lane_seed_coverage(
        baseline.get("seed_category_counts") or {},
        category_summary,
        min_targets_per_seed=min_targets_per_seed,
        min_strict_fit_per_seed=min_strict_fit_per_seed,
    )
    by_lens = _lane_seed_coverage(
        baseline.get("seed_lens_counts") or {},
        lens_summary,
        min_targets_per_seed=min_targets_per_seed,
        min_strict_fit_per_seed=min_strict_fit_per_seed,
    )
    by_category_lens = _lane_seed_coverage(
        baseline.get("seed_category_lens_counts") or {},
        category_lens_summary or {},
        min_targets_per_seed=min_targets_per_seed,
        min_strict_fit_per_seed=min_strict_fit_per_seed,
    )
    return {
        "by_category": by_category,
        "by_lens": by_lens,
        "by_category_lens": by_category_lens,
        "undercovered_categories": [
            lane for lane, metrics in by_category.items()
            if metrics.get("gap_reasons")
        ],
        "undercovered_lenses": [
            lane for lane, metrics in by_lens.items()
            if metrics.get("gap_reasons")
        ],
        "undercovered_category_lenses": [
            lane for lane, metrics in by_category_lens.items()
            if metrics.get("gap_reasons")
        ],
    }


def _priority_focus_categories() -> List[str]:
    categories: List[str] = []
    profile_categories = set(getattr(ACTIVE_KEYWORD_PROFILE, "focus_categories", ()) or ())
    for raw_category in PRIORITY_FOCUS_CATEGORIES:
        category = ACTIVE_KEYWORD_PROFILE.normalize_category(raw_category)
        if profile_categories and category not in profile_categories:
            continue
        if ACTIVE_KEYWORD_PROFILE.profile_for(category):
            categories.append(category)
    return list(dict.fromkeys(categories))


def _category_priority_sort_key(category: object) -> tuple:
    normalized = ACTIVE_KEYWORD_PROFILE.normalize_category(str(category or ""))
    priority = _priority_focus_categories()
    priority_index = {name: idx for idx, name in enumerate(priority)}
    if normalized in priority_index:
        return (0, priority_index[normalized], 0.0, normalized)
    profile = ACTIVE_KEYWORD_PROFILE.profile_for(normalized)
    try:
        strategic_weight = float(getattr(profile, "strategic_weight", 1.0) or 1.0) if profile else 1.0
    except (TypeError, ValueError):
        strategic_weight = 1.0
    return (1, len(priority), -strategic_weight, normalized)


def _lens_priority_sort_key(lens: object) -> tuple:
    order = {
        "review": 0,
        "community": 1,
        "cost": 2,
        "consultation": 3,
        "availability": 4,
        "safety": 5,
        "service": 6,
        "unknown": 7,
    }
    text = str(lens or "unknown").strip().lower() or "unknown"
    return (order.get(text, 8), text)


def _platform_priority_sort_key(platform: object) -> tuple:
    order = {
        "kin": 0,
        "naver_kin": 0,
        "cafe": 1,
        "naver_cafe": 1,
        "blog": 2,
        "naver_blog": 2,
        "community": 3,
        "web": 4,
        "unknown": 9,
    }
    text = str(platform or "unknown").strip().lower() or "unknown"
    return (order.get(text, 8), text)


def _category_lens_priority_sort_key(category_lens: object) -> tuple:
    category, _, lens = str(category_lens or "").partition("::")
    return _category_priority_sort_key(category) + _lens_priority_sort_key(lens)


def _focus_category_for_weak_lane(lane: Dict[str, Any]) -> str:
    lane_type = str((lane or {}).get("type") or "")
    raw_lane = str((lane or {}).get("lane") or "")
    if lane_type == "category":
        category = raw_lane
    elif lane_type == "category_lens":
        category, _, _ = raw_lane.partition("::")
    elif lane_type == "platform_category":
        _, _, category = raw_lane.partition("::")
    else:
        return ""
    normalized = ACTIVE_KEYWORD_PROFILE.normalize_category(category)
    return normalized if normalized in set(_priority_focus_categories()) else ""


def _weak_lane_base_sort_key(lane: Dict[str, Any]) -> tuple:
    lane_type = str((lane or {}).get("type") or "")
    raw_lane = str((lane or {}).get("lane") or "")
    if lane_type == "category":
        return (0,) + _category_priority_sort_key(raw_lane)
    if lane_type == "category_lens":
        return (1,) + _category_lens_priority_sort_key(raw_lane)
    if lane_type == "platform_category":
        platform, _, category = raw_lane.partition("::")
        return (2,) + _category_priority_sort_key(category) + _platform_priority_sort_key(platform)
    if lane_type == "lens":
        return (3,) + _lens_priority_sort_key(raw_lane)
    if lane_type == "platform":
        return (4,) + _platform_priority_sort_key(raw_lane)
    if lane_type == "query_variant":
        return (5, raw_lane)
    if lane_type == "variant_family":
        return (6, raw_lane)
    return (9, raw_lane)


def _weak_lanes_for_reason(
    weak_lanes: List[Dict[str, Any]],
    reason: str,
    *,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    metric_key = {
        "content_category_mismatch": "content_category_mismatch_rate",
        "lens_surface_mismatch": "lens_surface_mismatch_rate",
    }.get(reason, "strict_fit_rate")
    lanes = [
        lane for lane in weak_lanes
        if reason in set(lane.get("reasons") or [])
    ]
    lanes.sort(
        key=lambda lane: (
            _weak_lane_base_sort_key(lane),
            -float(lane.get(metric_key) or 0.0),
            -int(lane.get("total") or 0),
        )
    )
    return lanes[: max(0, int(limit or 0))]


def _loss_hotspots(
    *,
    category_summary: Dict[str, Dict[str, Any]],
    lens_summary: Dict[str, Dict[str, Any]],
    category_lens_summary: Dict[str, Dict[str, Any]],
    query_variant_summary: Dict[str, Dict[str, Any]],
    limit: int = 20,
) -> List[Dict[str, Any]]:
    hotspots: List[Dict[str, Any]] = []
    for lane_type, summary in (
        ("category", category_summary),
        ("category_lens", category_lens_summary),
        ("lens", lens_summary),
        ("query_variant", query_variant_summary),
    ):
        for lane, metrics in summary.items():
            lost = int(metrics.get("lost") or 0)
            if lost <= 0:
                continue
            item = {
                "type": lane_type,
                "lane": lane,
                "total": int(metrics.get("total") or 0),
                "lost": lost,
                "loss_rate": float(metrics.get("loss_rate") or 0.0),
                "survival_rate": float(metrics.get("survival_rate") or 0.0),
                "strict_fit_rate": float(metrics.get("strict_fit_rate") or 0.0),
                "dominant_loss_reason": metrics.get("dominant_loss_reason") or "",
                "loss_reason_counts": metrics.get("loss_reason_counts", {}),
            }
            focus_category = _focus_category_for_weak_lane(item)
            if focus_category:
                item["focus_category"] = focus_category
            hotspots.append(item)

    hotspots.sort(
        key=lambda item: (
            _weak_lane_base_sort_key(item),
            -float(item.get("loss_rate") or 0.0),
            -int(item.get("lost") or 0),
        )
    )
    return hotspots[: max(0, int(limit or 0))]


def _loss_analysis(
    *,
    overall: Dict[str, Any],
    category_summary: Dict[str, Dict[str, Any]],
    lens_summary: Dict[str, Dict[str, Any]],
    category_lens_summary: Dict[str, Dict[str, Any]],
    query_variant_summary: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    hotspots = _loss_hotspots(
        category_summary=category_summary,
        lens_summary=lens_summary,
        category_lens_summary=category_lens_summary,
        query_variant_summary=query_variant_summary,
        limit=25,
    )
    focus_categories = set(_priority_focus_categories())
    priority_focus_hotspots = [
        hotspot for hotspot in hotspots
        if hotspot.get("focus_category") in focus_categories
    ][:10]
    return {
        "overall": {
            "lost": int(overall.get("lost") or 0),
            "loss_rate": float(overall.get("loss_rate") or 0.0),
            "dominant_loss_reason": overall.get("dominant_loss_reason") or "",
            "loss_reason_counts": overall.get("loss_reason_counts", {}),
        },
        "hotspots": hotspots,
        "priority_focus_hotspots": priority_focus_hotspots,
    }


def _patient_journey_coverage(
    *,
    category_lens_summary: Dict[str, Dict[str, Any]],
    min_lane_total: int,
) -> Dict[str, Any]:
    """Measure whether focus treatment axes have usable posts for each patient journey lens."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    target_pairs = len(focus_categories) * len(lenses)
    discovered_pairs = 0
    survived_pairs = 0
    strict_pairs = 0
    actionable_strict_pairs = 0
    fresh_actionable_strict_pairs = 0
    by_category: Dict[str, Dict[str, Any]] = {}
    gaps: List[Dict[str, Any]] = []

    for category in focus_categories:
        discovered_lenses: List[str] = []
        survived_lenses: List[str] = []
        strict_lenses: List[str] = []
        actionable_strict_lenses: List[str] = []
        fresh_actionable_strict_lenses: List[str] = []
        category_gaps: List[Dict[str, Any]] = []
        for lens in lenses:
            lane = f"{category}::{lens}"
            metrics = category_lens_summary.get(lane) or {}
            total = int(metrics.get("total") or 0)
            survived = int(metrics.get("survived") or 0)
            strict_fit = int(metrics.get("strict_fit") or 0)
            actionable_strict = int(metrics.get("actionable_strict") or 0)
            fresh_actionable_strict = int(metrics.get("fresh_actionable_strict") or 0)
            loss_rate = float(metrics.get("loss_rate") or 0.0)
            strict_fit_rate = float(metrics.get("strict_fit_rate") or 0.0)
            actionable_strict_rate = float(metrics.get("actionable_strict_rate") or 0.0)
            fresh_actionable_strict_rate = float(metrics.get("fresh_actionable_strict_rate") or 0.0)
            lens_surface_checked = int(metrics.get("lens_surface_checked") or 0)
            lens_surface_mismatch_rate = float(metrics.get("lens_surface_mismatch_rate") or 0.0)

            if total:
                discovered_pairs += 1
                discovered_lenses.append(lens)
            if survived:
                survived_pairs += 1
                survived_lenses.append(lens)
            if strict_fit:
                strict_pairs += 1
                strict_lenses.append(lens)
            if actionable_strict:
                actionable_strict_pairs += 1
                actionable_strict_lenses.append(lens)
            if fresh_actionable_strict:
                fresh_actionable_strict_pairs += 1
                fresh_actionable_strict_lenses.append(lens)

            reasons: List[str] = []
            if not total:
                reasons.append("no_targets")
            else:
                if not survived:
                    reasons.append("no_survivors")
                if not strict_fit:
                    reasons.append("no_strict_fit")
                elif strict_fit_rate < 0.12:
                    reasons.append("weak_strict_fit_rate")
                if strict_fit and not actionable_strict:
                    reasons.append("no_actionable_strict")
                elif actionable_strict and actionable_strict_rate < 0.08:
                    reasons.append("weak_actionable_strict_rate")
                if actionable_strict and not fresh_actionable_strict:
                    reasons.append("no_fresh_actionable_strict")
                elif fresh_actionable_strict and fresh_actionable_strict_rate < 0.08:
                    reasons.append("weak_fresh_actionable_strict_rate")
                if loss_rate >= 0.70 and int(metrics.get("lost") or 0):
                    reasons.append("high_loss")
                if (
                    lens_surface_checked >= max(3, int(min_lane_total or 1))
                    and lens_surface_mismatch_rate > 0.35
                ):
                    reasons.append("lens_surface_mismatch")

            if reasons:
                gap = {
                    "lane": lane,
                    "category": category,
                    "lens": lens,
                    "total": total,
                    "survived": survived,
                    "strict_fit": strict_fit,
                    "actionable_strict": actionable_strict,
                    "fresh_actionable_strict": fresh_actionable_strict,
                    "survival_rate": float(metrics.get("survival_rate") or 0.0),
                    "strict_fit_rate": strict_fit_rate,
                    "actionable_strict_rate": actionable_strict_rate,
                    "fresh_actionable_strict_rate": fresh_actionable_strict_rate,
                    "actionable_strict_share_of_strict": float(
                        metrics.get("actionable_strict_share_of_strict") or 0.0
                    ),
                    "fresh_actionable_strict_share_of_actionable_strict": float(
                        metrics.get("fresh_actionable_strict_share_of_actionable_strict") or 0.0
                    ),
                    "loss_rate": loss_rate,
                    "dominant_loss_reason": metrics.get("dominant_loss_reason") or "",
                    "reasons": reasons,
                }
                category_gaps.append(gap)
                gaps.append(gap)

        by_category[category] = {
            "target_lenses": lenses,
            "discovered_lenses": discovered_lenses,
            "survived_lenses": survived_lenses,
            "strict_lenses": strict_lenses,
            "actionable_strict_lenses": actionable_strict_lenses,
            "fresh_actionable_strict_lenses": fresh_actionable_strict_lenses,
            "missing_discovered_lenses": [lens for lens in lenses if lens not in discovered_lenses],
            "missing_strict_lenses": [lens for lens in lenses if lens not in strict_lenses],
            "missing_actionable_strict_lenses": [
                lens for lens in lenses if lens not in actionable_strict_lenses
            ],
            "missing_fresh_actionable_strict_lenses": [
                lens for lens in lenses if lens not in fresh_actionable_strict_lenses
            ],
            "discovered_lens_coverage_rate": LaneStats._rate(len(discovered_lenses), len(lenses)),
            "survived_lens_coverage_rate": LaneStats._rate(len(survived_lenses), len(lenses)),
            "strict_lens_coverage_rate": LaneStats._rate(len(strict_lenses), len(lenses)),
            "actionable_strict_lens_coverage_rate": LaneStats._rate(
                len(actionable_strict_lenses),
                len(lenses),
            ),
            "fresh_actionable_strict_lens_coverage_rate": LaneStats._rate(
                len(fresh_actionable_strict_lenses),
                len(lenses),
            ),
            "gaps": category_gaps,
        }

    reason_order = {
        "no_targets": 0,
        "no_survivors": 1,
        "no_strict_fit": 2,
        "no_actionable_strict": 3,
        "no_fresh_actionable_strict": 4,
        "weak_strict_fit_rate": 5,
        "weak_actionable_strict_rate": 6,
        "weak_fresh_actionable_strict_rate": 7,
        "high_loss": 8,
        "lens_surface_mismatch": 9,
    }

    def gap_key(item: Dict[str, Any]) -> tuple:
        reasons = item.get("reasons") or []
        first_reason = min((reason_order.get(reason, 9) for reason in reasons), default=9)
        return (
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            first_reason,
            float(item.get("strict_fit_rate") or 0.0),
            float(item.get("survival_rate") or 0.0),
            -int(item.get("total") or 0),
        )

    gaps.sort(key=gap_key)
    return {
        "lenses": lenses,
        "by_category": by_category,
        "gaps": gaps,
        "priority_focus_gaps": gaps[:10],
        "overall": {
            "target_pairs": target_pairs,
            "discovered_pairs": discovered_pairs,
            "survived_pairs": survived_pairs,
            "strict_pairs": strict_pairs,
            "actionable_strict_pairs": actionable_strict_pairs,
            "fresh_actionable_strict_pairs": fresh_actionable_strict_pairs,
            "discovered_coverage_rate": LaneStats._rate(discovered_pairs, target_pairs),
            "survived_coverage_rate": LaneStats._rate(survived_pairs, target_pairs),
            "strict_coverage_rate": LaneStats._rate(strict_pairs, target_pairs),
            "actionable_strict_coverage_rate": LaneStats._rate(actionable_strict_pairs, target_pairs),
            "fresh_actionable_strict_coverage_rate": LaneStats._rate(fresh_actionable_strict_pairs, target_pairs),
        },
        "counts": {
            "gaps": len(gaps),
            "priority_focus_gaps": len(gaps[:10]),
        },
    }


def _work_queue_readiness(
    *,
    category_summary: Dict[str, Dict[str, Any]],
    category_lens_summary: Dict[str, Dict[str, Any]],
    category_target: int = WORK_QUEUE_CATEGORY_TARGET,
    category_lens_target: int = WORK_QUEUE_CATEGORY_LENS_TARGET,
) -> Dict[str, Any]:
    """Check whether there is enough actionable strict-fit inventory to operate repeatedly."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0
    unique_category_ready = 0
    unique_category_lens_ready = 0
    fresh_unique_category_ready = 0
    fresh_unique_category_lens_ready = 0
    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    unique_category_gaps: List[Dict[str, Any]] = []
    unique_category_lens_gaps: List[Dict[str, Any]] = []
    fresh_unique_category_gaps: List[Dict[str, Any]] = []
    fresh_unique_category_lens_gaps: List[Dict[str, Any]] = []

    for category in focus_categories:
        metrics = category_summary.get(category) or {}
        actionable_strict = int(metrics.get("actionable_strict") or 0)
        fresh_actionable_strict = int(metrics.get("fresh_actionable_strict") or 0)
        unique_actionable_strict = int(metrics.get("unique_actionable_strict") or 0)
        unique_fresh_actionable_strict = int(metrics.get("unique_fresh_actionable_strict") or 0)
        category_gap = max(0, category_target - actionable_strict)
        fresh_category_gap = max(0, category_target - fresh_actionable_strict)
        unique_category_gap = max(0, category_target - unique_actionable_strict)
        fresh_unique_category_gap = max(0, category_target - unique_fresh_actionable_strict)
        category_is_ready = category_gap == 0
        fresh_category_is_ready = fresh_category_gap == 0
        unique_category_is_ready = unique_category_gap == 0
        fresh_unique_category_is_ready = fresh_unique_category_gap == 0
        if category_is_ready:
            category_ready += 1
        if fresh_category_is_ready:
            fresh_category_ready += 1
        if unique_category_is_ready:
            unique_category_ready += 1
        if fresh_unique_category_is_ready:
            fresh_unique_category_ready += 1
        category_item = {
            "type": "category",
            "lane": category,
            "category": category,
            "target": category_target,
            "actionable_strict": actionable_strict,
            "fresh_actionable_strict": fresh_actionable_strict,
            "unique_actionable_strict": unique_actionable_strict,
            "unique_fresh_actionable_strict": unique_fresh_actionable_strict,
            "actionable_strict_duplicate_count": int(metrics.get("actionable_strict_duplicate_count") or 0),
            "fresh_actionable_strict_duplicate_count": int(
                metrics.get("fresh_actionable_strict_duplicate_count") or 0
            ),
            "gap": category_gap,
            "fresh_gap": fresh_category_gap,
            "unique_gap": unique_category_gap,
            "fresh_unique_gap": fresh_unique_category_gap,
            "ready": category_is_ready,
            "fresh_ready": fresh_category_is_ready,
            "unique_ready": unique_category_is_ready,
            "fresh_unique_ready": fresh_unique_category_is_ready,
            "total": int(metrics.get("total") or 0),
            "strict_fit": int(metrics.get("strict_fit") or 0),
            "actionable_strict_rate": float(metrics.get("actionable_strict_rate") or 0.0),
            "fresh_actionable_strict_rate": float(metrics.get("fresh_actionable_strict_rate") or 0.0),
            "actionable_strict_uniqueness_rate": float(metrics.get("actionable_strict_uniqueness_rate") or 0.0),
            "fresh_actionable_strict_uniqueness_rate": float(
                metrics.get("fresh_actionable_strict_uniqueness_rate") or 0.0
            ),
            "strict_fit_rate": float(metrics.get("strict_fit_rate") or 0.0),
            "survival_rate": float(metrics.get("survival_rate") or 0.0),
        }
        if not category_is_ready:
            category_item["reasons"] = ["thin_category_queue"]
            if actionable_strict == 0:
                category_item["reasons"].insert(0, "no_category_actionable_strict")
            category_gaps.append(category_item)
        if not fresh_category_is_ready:
            fresh_item = {
                **category_item,
                "gap": fresh_category_gap,
                "ready": fresh_category_is_ready,
                "reasons": ["thin_fresh_category_queue"],
            }
            if fresh_actionable_strict == 0:
                fresh_item["reasons"].insert(0, "no_category_fresh_actionable_strict")
            if actionable_strict > fresh_actionable_strict:
                fresh_item["reasons"].append("stale_category_inventory")
            fresh_category_gaps.append(fresh_item)
        if not unique_category_is_ready:
            unique_item = {
                **category_item,
                "gap": unique_category_gap,
                "ready": unique_category_is_ready,
                "reasons": ["thin_unique_category_queue"],
            }
            if unique_actionable_strict == 0:
                unique_item["reasons"].insert(0, "no_unique_category_actionable_strict")
            if actionable_strict > unique_actionable_strict:
                unique_item["reasons"].append("duplicate_category_inventory")
            unique_category_gaps.append(unique_item)
        if not fresh_unique_category_is_ready:
            fresh_unique_item = {
                **category_item,
                "gap": fresh_unique_category_gap,
                "ready": fresh_unique_category_is_ready,
                "reasons": ["thin_fresh_unique_category_queue"],
            }
            if unique_fresh_actionable_strict == 0:
                fresh_unique_item["reasons"].insert(0, "no_fresh_unique_category_actionable_strict")
            if fresh_actionable_strict > unique_fresh_actionable_strict:
                fresh_unique_item["reasons"].append("duplicate_fresh_category_inventory")
            if unique_actionable_strict > unique_fresh_actionable_strict:
                fresh_unique_item["reasons"].append("stale_unique_category_inventory")
            fresh_unique_category_gaps.append(fresh_unique_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lane = f"{category}::{lens}"
            lane_metrics = category_lens_summary.get(lane) or {}
            lane_actionable_strict = int(lane_metrics.get("actionable_strict") or 0)
            lane_fresh_actionable_strict = int(lane_metrics.get("fresh_actionable_strict") or 0)
            lane_unique_actionable_strict = int(lane_metrics.get("unique_actionable_strict") or 0)
            lane_unique_fresh_actionable_strict = int(lane_metrics.get("unique_fresh_actionable_strict") or 0)
            lane_gap = max(0, category_lens_target - lane_actionable_strict)
            lane_fresh_gap = max(0, category_lens_target - lane_fresh_actionable_strict)
            lane_unique_gap = max(0, category_lens_target - lane_unique_actionable_strict)
            lane_fresh_unique_gap = max(0, category_lens_target - lane_unique_fresh_actionable_strict)
            lane_ready = lane_gap == 0
            lane_fresh_ready = lane_fresh_gap == 0
            lane_unique_ready = lane_unique_gap == 0
            lane_fresh_unique_ready = lane_fresh_unique_gap == 0
            if lane_ready:
                category_lens_ready += 1
            if lane_fresh_ready:
                fresh_category_lens_ready += 1
            if lane_unique_ready:
                unique_category_lens_ready += 1
            if lane_fresh_unique_ready:
                fresh_unique_category_lens_ready += 1
            reasons: List[str] = []
            if int(lane_metrics.get("total") or 0) == 0:
                reasons.append("no_targets")
            if lane_actionable_strict == 0:
                reasons.append("no_lens_actionable_strict")
            elif lane_gap:
                reasons.append("thin_lens_queue")
            if float(lane_metrics.get("loss_rate") or 0.0) >= 0.70 and int(lane_metrics.get("lost") or 0):
                reasons.append("high_loss")
            lens_item = {
                "type": "category_lens",
                "lane": lane,
                "category": category,
                "lens": lens,
                "target": category_lens_target,
                "actionable_strict": lane_actionable_strict,
                "fresh_actionable_strict": lane_fresh_actionable_strict,
                "unique_actionable_strict": lane_unique_actionable_strict,
                "unique_fresh_actionable_strict": lane_unique_fresh_actionable_strict,
                "actionable_strict_duplicate_count": int(
                    lane_metrics.get("actionable_strict_duplicate_count") or 0
                ),
                "fresh_actionable_strict_duplicate_count": int(
                    lane_metrics.get("fresh_actionable_strict_duplicate_count") or 0
                ),
                "gap": lane_gap,
                "fresh_gap": lane_fresh_gap,
                "unique_gap": lane_unique_gap,
                "fresh_unique_gap": lane_fresh_unique_gap,
                "ready": lane_ready,
                "fresh_ready": lane_fresh_ready,
                "unique_ready": lane_unique_ready,
                "fresh_unique_ready": lane_fresh_unique_ready,
                "total": int(lane_metrics.get("total") or 0),
                "strict_fit": int(lane_metrics.get("strict_fit") or 0),
                "actionable_strict_rate": float(lane_metrics.get("actionable_strict_rate") or 0.0),
                "fresh_actionable_strict_rate": float(lane_metrics.get("fresh_actionable_strict_rate") or 0.0),
                "actionable_strict_uniqueness_rate": float(
                    lane_metrics.get("actionable_strict_uniqueness_rate") or 0.0
                ),
                "fresh_actionable_strict_uniqueness_rate": float(
                    lane_metrics.get("fresh_actionable_strict_uniqueness_rate") or 0.0
                ),
                "strict_fit_rate": float(lane_metrics.get("strict_fit_rate") or 0.0),
                "survival_rate": float(lane_metrics.get("survival_rate") or 0.0),
                "dominant_loss_reason": lane_metrics.get("dominant_loss_reason") or "",
                "reasons": reasons,
            }
            lens_items[lens] = lens_item
            if not lane_ready:
                category_lens_gaps.append(lens_item)
            if not lane_fresh_ready:
                fresh_lens_item = {
                    **lens_item,
                    "gap": lane_fresh_gap,
                    "ready": lane_fresh_ready,
                    "reasons": ["thin_fresh_lens_queue"],
                }
                if int(lane_metrics.get("total") or 0) == 0:
                    fresh_lens_item["reasons"].insert(0, "no_targets")
                if lane_fresh_actionable_strict == 0:
                    fresh_lens_item["reasons"].insert(0, "no_lens_fresh_actionable_strict")
                if lane_actionable_strict > lane_fresh_actionable_strict:
                    fresh_lens_item["reasons"].append("stale_lens_inventory")
                if float(lane_metrics.get("loss_rate") or 0.0) >= 0.70 and int(lane_metrics.get("lost") or 0):
                    fresh_lens_item["reasons"].append("high_loss")
                fresh_category_lens_gaps.append(fresh_lens_item)
            if not lane_unique_ready:
                unique_lens_item = {
                    **lens_item,
                    "gap": lane_unique_gap,
                    "ready": lane_unique_ready,
                    "reasons": ["thin_unique_lens_queue"],
                }
                if int(lane_metrics.get("total") or 0) == 0:
                    unique_lens_item["reasons"].insert(0, "no_targets")
                if lane_unique_actionable_strict == 0:
                    unique_lens_item["reasons"].insert(0, "no_unique_lens_actionable_strict")
                if lane_actionable_strict > lane_unique_actionable_strict:
                    unique_lens_item["reasons"].append("duplicate_lens_inventory")
                if float(lane_metrics.get("loss_rate") or 0.0) >= 0.70 and int(lane_metrics.get("lost") or 0):
                    unique_lens_item["reasons"].append("high_loss")
                unique_category_lens_gaps.append(unique_lens_item)
            if not lane_fresh_unique_ready:
                fresh_unique_lens_item = {
                    **lens_item,
                    "gap": lane_fresh_unique_gap,
                    "ready": lane_fresh_unique_ready,
                    "reasons": ["thin_fresh_unique_lens_queue"],
                }
                if int(lane_metrics.get("total") or 0) == 0:
                    fresh_unique_lens_item["reasons"].insert(0, "no_targets")
                if lane_unique_fresh_actionable_strict == 0:
                    fresh_unique_lens_item["reasons"].insert(0, "no_fresh_unique_lens_actionable_strict")
                if lane_fresh_actionable_strict > lane_unique_fresh_actionable_strict:
                    fresh_unique_lens_item["reasons"].append("duplicate_fresh_lens_inventory")
                if lane_unique_actionable_strict > lane_unique_fresh_actionable_strict:
                    fresh_unique_lens_item["reasons"].append("stale_unique_lens_inventory")
                if float(lane_metrics.get("loss_rate") or 0.0) >= 0.70 and int(lane_metrics.get("lost") or 0):
                    fresh_unique_lens_item["reasons"].append("high_loss")
                fresh_unique_category_lens_gaps.append(fresh_unique_lens_item)

        by_category[category] = {
            **category_item,
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "unique_ready_lens_count": sum(1 for item in lens_items.values() if item.get("unique_ready")),
            "fresh_unique_ready_lens_count": sum(
                1 for item in lens_items.values() if item.get("fresh_unique_ready")
            ),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
            "unique_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("unique_ready")),
                len(lens_items),
            ),
            "fresh_unique_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_unique_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        return (
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -int(item.get("gap") or 0),
            int(item.get("fresh_actionable_strict") or item.get("actionable_strict") or 0),
            -int(item.get("total") or 0),
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    unique_category_gaps.sort(key=gap_key)
    unique_category_lens_gaps.sort(key=gap_key)
    unique_priority_gaps = unique_category_gaps + unique_category_lens_gaps
    unique_priority_gaps.sort(key=gap_key)
    fresh_unique_category_gaps.sort(key=gap_key)
    fresh_unique_category_lens_gaps.sort(key=gap_key)
    fresh_unique_priority_gaps = fresh_unique_category_gaps + fresh_unique_category_lens_gaps
    fresh_unique_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_actionable_strict": category_target,
            "category_lens_actionable_strict": category_lens_target,
            "category_unique_actionable_strict": category_target,
            "category_lens_unique_actionable_strict": category_lens_target,
        },
        "overall": {
            "target_categories": target_categories,
            "ready_categories": category_ready,
            "category_ready_rate": LaneStats._rate(category_ready, target_categories),
            "fresh_ready_categories": fresh_category_ready,
            "fresh_category_ready_rate": LaneStats._rate(fresh_category_ready, target_categories),
            "unique_ready_categories": unique_category_ready,
            "unique_category_ready_rate": LaneStats._rate(unique_category_ready, target_categories),
            "fresh_unique_ready_categories": fresh_unique_category_ready,
            "fresh_unique_category_ready_rate": LaneStats._rate(
                fresh_unique_category_ready,
                target_categories,
            ),
            "target_category_lenses": target_category_lenses,
            "ready_category_lenses": category_lens_ready,
            "category_lens_ready_rate": LaneStats._rate(category_lens_ready, target_category_lenses),
            "fresh_ready_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
            "unique_ready_category_lenses": unique_category_lens_ready,
            "unique_category_lens_ready_rate": LaneStats._rate(
                unique_category_lens_ready,
                target_category_lenses,
            ),
            "fresh_unique_ready_category_lenses": fresh_unique_category_lens_ready,
            "fresh_unique_category_lens_ready_rate": LaneStats._rate(
                fresh_unique_category_lens_ready,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "unique_category_gaps": unique_category_gaps,
        "unique_category_lens_gaps": unique_category_lens_gaps,
        "unique_priority_gaps": unique_priority_gaps[:10],
        "fresh_unique_category_gaps": fresh_unique_category_gaps,
        "fresh_unique_category_lens_gaps": fresh_unique_category_lens_gaps,
        "fresh_unique_priority_gaps": fresh_unique_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
            "unique_category_gaps": len(unique_category_gaps),
            "unique_category_lens_gaps": len(unique_category_lens_gaps),
            "fresh_unique_category_gaps": len(fresh_unique_category_gaps),
            "fresh_unique_category_lens_gaps": len(fresh_unique_category_lens_gaps),
        },
    }


def _unique_actionable_records(
    records: List[Dict[str, Any]],
    *,
    category: str,
    lens: Optional[str] = None,
    fresh_only: bool = False,
) -> List[Dict[str, Any]]:
    representatives: Dict[str, Dict[str, Any]] = {}
    for record in sorted(records, key=lambda item: float(item.get("priority") or 0.0), reverse=True):
        if record.get("category") != category:
            continue
        if lens is not None and record.get("lens") != lens:
            continue
        if record.get("status") not in ACTIONABLE_STATUSES:
            continue
        if not bool(record.get("strict_fit")):
            continue
        if fresh_only and not bool(record.get("fresh_activity")):
            continue
        fingerprint = str(
            record.get("target_fingerprint")
            or record.get("canonical_url")
            or record.get("url")
            or record.get("id")
            or ""
        ).strip()
        if not fingerprint:
            continue
        representatives.setdefault(fingerprint, record)
    return list(representatives.values())


def _diversity_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    min_platforms: int,
    min_source_seeds: int,
    min_variant_families: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    platforms = sorted({str(record.get("platform") or "unknown") for record in records})
    source_seeds = sorted({
        str(record.get("source_seed") or "")
        for record in records
        if str(record.get("source_seed") or "").strip()
    })
    variant_families = sorted({
        str(record.get("query_variant_family") or "other")
        for record in records
        if str(record.get("query_variant_family") or "").strip()
    })
    unique_count = len(records)
    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif unique_count < target:
        reasons.append("thin_fresh_unique_inventory" if fresh else "thin_unique_inventory")
    if unique_count:
        if len(platforms) < min_platforms:
            reasons.append("single_platform_dependency")
        if len(source_seeds) < min_source_seeds:
            reasons.append("single_source_seed_dependency")
        if len(variant_families) < min_variant_families:
            reasons.append("single_query_family_dependency")
    ready = not reasons
    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "platform_count": len(platforms),
        "source_seed_count": len(source_seeds),
        "variant_family_count": len(variant_families),
        "platforms": platforms[:8],
        "source_seeds": source_seeds[:8],
        "variant_families": variant_families[:8],
        "min_platforms": min_platforms,
        "min_source_seeds": min_source_seeds,
        "min_variant_families": min_variant_families,
        "ready": ready,
        "gap": max(0, target - unique_count),
        "reasons": reasons,
    }


def _opportunity_diversity(
    records: List[Dict[str, Any]],
    *,
    category_target: int = WORK_QUEUE_CATEGORY_TARGET,
    category_lens_target: int = WORK_QUEUE_CATEGORY_LENS_TARGET,
    min_platforms: int = OPPORTUNITY_DIVERSITY_MIN_PLATFORMS,
    min_source_seeds: int = OPPORTUNITY_DIVERSITY_MIN_SOURCE_SEEDS,
    min_variant_families: int = OPPORTUNITY_DIVERSITY_MIN_VARIANT_FAMILIES,
) -> Dict[str, Any]:
    """Audit whether work-ready opportunities are independent across surfaces and seeds."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))
    min_platforms = max(1, int(min_platforms or 1))
    min_source_seeds = max(1, int(min_source_seeds or 1))
    min_variant_families = max(1, int(min_variant_families or 1))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        category_item = _diversity_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
            min_platforms=min_platforms,
            min_source_seeds=min_source_seeds,
            min_variant_families=min_variant_families,
        )
        fresh_category_item = _diversity_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            min_platforms=min_platforms,
            min_source_seeds=min_source_seeds,
            min_variant_families=min_variant_families,
            fresh=True,
        )
        if category_item["ready"]:
            category_ready += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_ready += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _diversity_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
                min_platforms=min_platforms,
                min_source_seeds=min_source_seeds,
                min_variant_families=min_variant_families,
            )
            fresh_lens_item = _diversity_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                min_platforms=min_platforms,
                min_source_seeds=min_source_seeds,
                min_variant_families=min_variant_families,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "fresh_unique_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_platform_count": fresh_lens_item["platform_count"],
                "fresh_source_seed_count": fresh_lens_item["source_seed_count"],
                "fresh_variant_family_count": fresh_lens_item["variant_family_count"],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_ready += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_ready += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "fresh_unique_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_platform_count": fresh_category_item["platform_count"],
            "fresh_source_seed_count": fresh_category_item["source_seed_count"],
            "fresh_variant_family_count": fresh_category_item["variant_family_count"],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        return (
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -int(item.get("gap") or 0),
            int(item.get("platform_count") or 0),
            int(item.get("source_seed_count") or 0),
            int(item.get("variant_family_count") or 0),
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_unique_actionable_strict": category_target,
            "category_lens_unique_actionable_strict": category_lens_target,
            "min_platforms": min_platforms,
            "min_source_seeds": min_source_seeds,
            "min_variant_families": min_variant_families,
        },
        "overall": {
            "target_categories": target_categories,
            "diverse_categories": category_ready,
            "category_diversity_ready_rate": LaneStats._rate(category_ready, target_categories),
            "fresh_diverse_categories": fresh_category_ready,
            "fresh_category_diversity_ready_rate": LaneStats._rate(fresh_category_ready, target_categories),
            "target_category_lenses": target_category_lenses,
            "diverse_category_lenses": category_lens_ready,
            "category_lens_diversity_ready_rate": LaneStats._rate(category_lens_ready, target_category_lenses),
            "fresh_diverse_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_diversity_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


def _engagement_hook_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    unique_count = len(records)
    checked_count = sum(1 for record in records if bool(record.get("engagement_hook_checked")))
    hooked_records = [record for record in records if bool(record.get("engagement_hook_matched"))]
    hooked_count = len(hooked_records)
    missing_count = max(0, unique_count - hooked_count)
    hook_terms = Counter(
        term
        for record in hooked_records
        for term in (record.get("engagement_hook_terms") or [])
        if str(term or "").strip()
    )

    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif hooked_count == 0:
        reasons.append("no_fresh_hooked_actionable_strict" if fresh else "no_hooked_actionable_strict")
    elif hooked_count < target:
        reasons.append("thin_fresh_hooked_inventory" if fresh else "thin_hooked_inventory")
    if unique_count and hooked_count < target and missing_count:
        reasons.append("missing_engagement_hook")

    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "hooked_actionable_strict": hooked_count,
        "fresh_hooked_actionable_strict": hooked_count if fresh else 0,
        "engagement_hook_checked": checked_count,
        "engagement_hook_missing": missing_count,
        "engagement_hook_terms": [term for term, _ in hook_terms.most_common(8)],
        "ready": hooked_count >= target and not reasons,
        "gap": max(0, target - hooked_count),
        "reasons": reasons,
    }


def _engagement_hook_quality(
    records: List[Dict[str, Any]],
    *,
    category_target: int = WORK_QUEUE_CATEGORY_TARGET,
    category_lens_target: int = WORK_QUEUE_CATEGORY_LENS_TARGET,
) -> Dict[str, Any]:
    """Audit whether work-ready targets include a reply-worthy patient hook."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        category_item = _engagement_hook_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
        )
        fresh_category_item = _engagement_hook_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            fresh=True,
        )
        if category_item["ready"]:
            category_ready += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_ready += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _engagement_hook_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
            )
            fresh_lens_item = _engagement_hook_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "unique_fresh_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_hooked_actionable_strict": fresh_lens_item["hooked_actionable_strict"],
                "fresh_engagement_hook_missing": fresh_lens_item["engagement_hook_missing"],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_ready += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_ready += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "unique_fresh_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_hooked_actionable_strict": fresh_category_item["hooked_actionable_strict"],
            "fresh_engagement_hook_missing": fresh_category_item["engagement_hook_missing"],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        return (
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -int(item.get("gap") or 0),
            int(item.get("hooked_actionable_strict") or 0),
            -int(item.get("engagement_hook_missing") or 0),
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_hooked_actionable_strict": category_target,
            "category_lens_hooked_actionable_strict": category_lens_target,
        },
        "overall": {
            "target_categories": target_categories,
            "hook_ready_categories": category_ready,
            "category_hook_ready_rate": LaneStats._rate(category_ready, target_categories),
            "fresh_hook_ready_categories": fresh_category_ready,
            "fresh_category_hook_ready_rate": LaneStats._rate(fresh_category_ready, target_categories),
            "target_category_lenses": target_category_lenses,
            "hook_ready_category_lenses": category_lens_ready,
            "category_lens_hook_ready_rate": LaneStats._rate(category_lens_ready, target_category_lenses),
            "fresh_hook_ready_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_hook_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


def _treatment_signature_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    unique_count = len(records)
    checked_count = sum(1 for record in records if bool(record.get("treatment_signature_checked")))
    signature_records = [record for record in records if bool(record.get("treatment_signature_matched"))]
    signature_count = len(signature_records)
    missing_count = max(0, unique_count - signature_count)
    signature_terms = Counter(
        term
        for record in signature_records
        for term in (record.get("treatment_signature_terms") or [])
        if str(term or "").strip()
    )
    expected_terms = _category_signature_terms(category)

    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif signature_count == 0:
        reasons.append("no_fresh_treatment_signature" if fresh else "no_treatment_signature")
    elif signature_count < target:
        reasons.append("thin_fresh_signature_inventory" if fresh else "thin_signature_inventory")
    if unique_count and signature_count < target and missing_count:
        reasons.append("missing_treatment_signature")

    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "signature_actionable_strict": signature_count,
        "fresh_signature_actionable_strict": signature_count if fresh else 0,
        "treatment_signature_checked": checked_count,
        "treatment_signature_missing": missing_count,
        "treatment_signature_terms": [term for term, _ in signature_terms.most_common(8)],
        "expected_treatment_signature_terms": expected_terms[:10],
        "ready": signature_count >= target and not reasons,
        "gap": max(0, target - signature_count),
        "reasons": reasons,
    }


def _treatment_signature_quality(
    records: List[Dict[str, Any]],
    *,
    category_target: int = WORK_QUEUE_CATEGORY_TARGET,
    category_lens_target: int = WORK_QUEUE_CATEGORY_LENS_TARGET,
) -> Dict[str, Any]:
    """Audit whether work-ready targets preserve the concrete treatment axis."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        category_item = _treatment_signature_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
        )
        fresh_category_item = _treatment_signature_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            fresh=True,
        )
        if category_item["ready"]:
            category_ready += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_ready += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _treatment_signature_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
            )
            fresh_lens_item = _treatment_signature_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "unique_fresh_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_signature_actionable_strict": fresh_lens_item["signature_actionable_strict"],
                "fresh_treatment_signature_missing": fresh_lens_item["treatment_signature_missing"],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_ready += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_ready += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "unique_fresh_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_signature_actionable_strict": fresh_category_item["signature_actionable_strict"],
            "fresh_treatment_signature_missing": fresh_category_item["treatment_signature_missing"],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        return (
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -int(item.get("gap") or 0),
            int(item.get("signature_actionable_strict") or 0),
            -int(item.get("treatment_signature_missing") or 0),
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_signature_actionable_strict": category_target,
            "category_lens_signature_actionable_strict": category_lens_target,
        },
        "overall": {
            "target_categories": target_categories,
            "signature_ready_categories": category_ready,
            "category_signature_ready_rate": LaneStats._rate(category_ready, target_categories),
            "fresh_signature_ready_categories": fresh_category_ready,
            "fresh_category_signature_ready_rate": LaneStats._rate(fresh_category_ready, target_categories),
            "target_category_lenses": target_category_lenses,
            "signature_ready_category_lenses": category_lens_ready,
            "category_lens_signature_ready_rate": LaneStats._rate(category_lens_ready, target_category_lenses),
            "fresh_signature_ready_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_signature_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


def _treatment_signal_diversity_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    min_distinct_terms: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    unique_count = len(records)
    signature_records = [record for record in records if bool(record.get("treatment_signature_matched"))]
    signature_count = len(signature_records)
    missing_count = max(0, unique_count - signature_count)
    signal_terms = Counter(
        term
        for record in signature_records
        for term in (record.get("treatment_signature_terms") or [])
        if str(term or "").strip()
    )
    distinct_count = len(signal_terms)
    diversity_gap = max(0, min_distinct_terms - distinct_count)

    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif signature_count == 0:
        reasons.append("no_fresh_treatment_signal" if fresh else "no_treatment_signal")
    elif signature_count < target:
        reasons.append("thin_fresh_treatment_signal_inventory" if fresh else "thin_treatment_signal_inventory")
    if unique_count and signature_count < target and missing_count:
        reasons.append("missing_treatment_signal")
    if unique_count and distinct_count < min_distinct_terms:
        reasons.append("narrow_fresh_treatment_signal_diversity" if fresh else "narrow_treatment_signal_diversity")

    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    ready = signature_count >= target and distinct_count >= min_distinct_terms and not reasons
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "treatment_signal_actionable_strict": signature_count,
        "fresh_treatment_signal_actionable_strict": signature_count if fresh else 0,
        "treatment_signal_missing": missing_count,
        "distinct_treatment_signal_terms": distinct_count,
        "min_distinct_treatment_signal_terms": min_distinct_terms,
        "treatment_signal_diversity_gap": diversity_gap,
        "treatment_signal_terms": [term for term, _ in signal_terms.most_common(12)],
        "expected_treatment_signal_terms": _category_signature_terms(category)[:12],
        "ready": ready,
        "gap": max(0, target - signature_count, diversity_gap),
        "reasons": reasons,
    }


def _treatment_signal_diversity_quality(
    records: List[Dict[str, Any]],
    *,
    category_target: int = WORK_QUEUE_CATEGORY_TARGET,
    category_lens_target: int = WORK_QUEUE_CATEGORY_LENS_TARGET,
    category_min_terms: int = TREATMENT_SIGNAL_DIVERSITY_CATEGORY_MIN_TERMS,
    category_lens_min_terms: int = TREATMENT_SIGNAL_DIVERSITY_CATEGORY_LENS_MIN_TERMS,
) -> Dict[str, Any]:
    """Audit whether Pathfinder breadth survives as diverse treatment-level signals."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))
    category_min_terms = max(1, int(category_min_terms or 1))
    category_lens_min_terms = max(1, int(category_lens_min_terms or 1))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        category_item = _treatment_signal_diversity_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
            min_distinct_terms=category_min_terms,
        )
        fresh_category_item = _treatment_signal_diversity_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            min_distinct_terms=category_min_terms,
            fresh=True,
        )
        if category_item["ready"]:
            category_ready += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_ready += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _treatment_signal_diversity_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
                min_distinct_terms=category_lens_min_terms,
            )
            fresh_lens_item = _treatment_signal_diversity_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                min_distinct_terms=category_lens_min_terms,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "unique_fresh_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_treatment_signal_actionable_strict": fresh_lens_item[
                    "treatment_signal_actionable_strict"
                ],
                "fresh_distinct_treatment_signal_terms": fresh_lens_item[
                    "distinct_treatment_signal_terms"
                ],
                "fresh_treatment_signal_diversity_gap": fresh_lens_item[
                    "treatment_signal_diversity_gap"
                ],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_ready += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_ready += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "unique_fresh_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_treatment_signal_actionable_strict": fresh_category_item[
                "treatment_signal_actionable_strict"
            ],
            "fresh_distinct_treatment_signal_terms": fresh_category_item["distinct_treatment_signal_terms"],
            "fresh_treatment_signal_diversity_gap": fresh_category_item["treatment_signal_diversity_gap"],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        unique_count = int(item.get("unique_actionable_strict") or 0)
        diversity_gap = int(item.get("treatment_signal_diversity_gap") or 0)
        treatment_specific_gap = unique_count > 0 and diversity_gap > 0
        no_inventory = unique_count == 0
        return (
            0 if treatment_specific_gap else (2 if no_inventory else 1),
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -diversity_gap,
            -int(item.get("gap") or 0),
            int(item.get("distinct_treatment_signal_terms") or 0),
            int(item.get("treatment_signal_actionable_strict") or 0),
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_treatment_signal_actionable_strict": category_target,
            "category_lens_treatment_signal_actionable_strict": category_lens_target,
            "category_min_distinct_treatment_signal_terms": category_min_terms,
            "category_lens_min_distinct_treatment_signal_terms": category_lens_min_terms,
        },
        "overall": {
            "target_categories": target_categories,
            "treatment_signal_diverse_categories": category_ready,
            "category_treatment_signal_diverse_ready_rate": LaneStats._rate(
                category_ready,
                target_categories,
            ),
            "fresh_treatment_signal_diverse_categories": fresh_category_ready,
            "fresh_category_treatment_signal_diverse_ready_rate": LaneStats._rate(
                fresh_category_ready,
                target_categories,
            ),
            "target_category_lenses": target_category_lenses,
            "treatment_signal_diverse_category_lenses": category_lens_ready,
            "category_lens_treatment_signal_diverse_ready_rate": LaneStats._rate(
                category_lens_ready,
                target_category_lenses,
            ),
            "fresh_treatment_signal_diverse_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_treatment_signal_diverse_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


def _treatment_subintent_diversity_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    min_distinct_buckets: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    unique_count = len(records)
    subintent_records = [record for record in records if bool(record.get("treatment_subintent_matched"))]
    subintent_count = len(subintent_records)
    missing_count = max(0, unique_count - subintent_count)
    bucket_counter = Counter(
        bucket
        for record in subintent_records
        for bucket in (record.get("treatment_subintent_buckets") or [])
        if str(bucket or "").strip()
    )
    term_counter = Counter(
        term
        for record in subintent_records
        for term in (record.get("treatment_subintent_terms") or [])
        if str(term or "").strip()
    )
    merged_bucket_terms: Dict[str, List[str]] = {}
    for record in subintent_records:
        for bucket, terms in (record.get("treatment_subintent_bucket_terms") or {}).items():
            bucket_name = str(bucket or "").strip()
            if not bucket_name:
                continue
            merged_bucket_terms.setdefault(bucket_name, [])
            for term in list(terms or []):
                clean = str(term or "").strip()
                if clean and clean not in merged_bucket_terms[bucket_name]:
                    merged_bucket_terms[bucket_name].append(clean)

    distinct_buckets = len(bucket_counter)
    diversity_gap = max(0, min_distinct_buckets - distinct_buckets)

    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif subintent_count == 0:
        reasons.append("no_fresh_treatment_subintent" if fresh else "no_treatment_subintent")
    elif subintent_count < target:
        reasons.append("thin_fresh_treatment_subintent_inventory" if fresh else "thin_treatment_subintent_inventory")
    if unique_count and subintent_count < target and missing_count:
        reasons.append("missing_treatment_subintent")
    if unique_count and distinct_buckets < min_distinct_buckets:
        reasons.append(
            "narrow_fresh_treatment_subintent_diversity"
            if fresh
            else "narrow_treatment_subintent_diversity"
        )

    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    ready = subintent_count >= target and distinct_buckets >= min_distinct_buckets and not reasons
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "treatment_subintent_actionable_strict": subintent_count,
        "fresh_treatment_subintent_actionable_strict": subintent_count if fresh else 0,
        "treatment_subintent_missing": missing_count,
        "distinct_treatment_subintent_buckets": distinct_buckets,
        "min_distinct_treatment_subintent_buckets": min_distinct_buckets,
        "treatment_subintent_diversity_gap": diversity_gap,
        "treatment_subintent_buckets": [bucket for bucket, _ in bucket_counter.most_common(12)],
        "treatment_subintent_terms": [term for term, _ in term_counter.most_common(16)],
        "treatment_subintent_bucket_terms": {
            bucket: terms[:8]
            for bucket, terms in sorted(merged_bucket_terms.items())
        },
        "expected_treatment_subintent_buckets": list(_category_subintent_buckets(category)),
        "ready": ready,
        "gap": max(0, target - subintent_count, diversity_gap),
        "reasons": reasons,
    }


def _treatment_subintent_diversity_quality(
    records: List[Dict[str, Any]],
    *,
    category_target: int = TREATMENT_SUBINTENT_CATEGORY_TARGET,
    category_lens_target: int = TREATMENT_SUBINTENT_CATEGORY_LENS_TARGET,
    category_min_buckets: int = TREATMENT_SUBINTENT_CATEGORY_MIN_BUCKETS,
    category_lens_min_buckets: int = TREATMENT_SUBINTENT_CATEGORY_LENS_MIN_BUCKETS,
) -> Dict[str, Any]:
    """Audit whether keyword breadth survives as distinct patient sub-problems."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))
    category_min_buckets = max(1, int(category_min_buckets or 1))
    category_lens_min_buckets = max(1, int(category_lens_min_buckets or 1))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        category_item = _treatment_subintent_diversity_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
            min_distinct_buckets=category_min_buckets,
        )
        fresh_category_item = _treatment_subintent_diversity_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            min_distinct_buckets=category_min_buckets,
            fresh=True,
        )
        if category_item["ready"]:
            category_ready += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_ready += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _treatment_subintent_diversity_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
                min_distinct_buckets=category_lens_min_buckets,
            )
            fresh_lens_item = _treatment_subintent_diversity_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                min_distinct_buckets=category_lens_min_buckets,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "unique_fresh_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_treatment_subintent_actionable_strict": fresh_lens_item[
                    "treatment_subintent_actionable_strict"
                ],
                "fresh_distinct_treatment_subintent_buckets": fresh_lens_item[
                    "distinct_treatment_subintent_buckets"
                ],
                "fresh_treatment_subintent_diversity_gap": fresh_lens_item[
                    "treatment_subintent_diversity_gap"
                ],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_ready += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_ready += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "unique_fresh_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_treatment_subintent_actionable_strict": fresh_category_item[
                "treatment_subintent_actionable_strict"
            ],
            "fresh_distinct_treatment_subintent_buckets": fresh_category_item[
                "distinct_treatment_subintent_buckets"
            ],
            "fresh_treatment_subintent_diversity_gap": fresh_category_item[
                "treatment_subintent_diversity_gap"
            ],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        unique_count = int(item.get("unique_actionable_strict") or 0)
        diversity_gap = int(item.get("treatment_subintent_diversity_gap") or 0)
        subintent_specific_gap = unique_count > 0 and diversity_gap > 0
        no_inventory = unique_count == 0
        return (
            0 if subintent_specific_gap else (2 if no_inventory else 1),
            _category_priority_sort_key(item.get("category")),
            0 if str(item.get("type") or "") == "category" else 1,
            _lens_priority_sort_key(item.get("lens")),
            -diversity_gap,
            -int(item.get("gap") or 0),
            int(item.get("distinct_treatment_subintent_buckets") or 0),
            int(item.get("treatment_subintent_actionable_strict") or 0),
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_treatment_subintent_actionable_strict": category_target,
            "category_lens_treatment_subintent_actionable_strict": category_lens_target,
            "category_min_distinct_treatment_subintent_buckets": category_min_buckets,
            "category_lens_min_distinct_treatment_subintent_buckets": category_lens_min_buckets,
        },
        "overall": {
            "target_categories": target_categories,
            "treatment_subintent_diverse_categories": category_ready,
            "category_treatment_subintent_diverse_ready_rate": LaneStats._rate(
                category_ready,
                target_categories,
            ),
            "fresh_treatment_subintent_diverse_categories": fresh_category_ready,
            "fresh_category_treatment_subintent_diverse_ready_rate": LaneStats._rate(
                fresh_category_ready,
                target_categories,
            ),
            "target_category_lenses": target_category_lenses,
            "treatment_subintent_diverse_category_lenses": category_lens_ready,
            "category_lens_treatment_subintent_diverse_ready_rate": LaneStats._rate(
                category_lens_ready,
                target_category_lenses,
            ),
            "fresh_treatment_subintent_diverse_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_treatment_subintent_diverse_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


def _clinic_modality_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    unique_count = len(records)
    compatible_records = [
        record for record in records
        if bool(record.get("clinic_modality_matched"))
    ]
    compatible_count = len(compatible_records)
    offscope_records = [
        record for record in records
        if record.get("clinic_modality_offscope_terms")
        and not bool(record.get("clinic_modality_matched"))
    ]
    offscope_count = len(offscope_records)
    positive_terms = Counter(
        term
        for record in records
        for term in (record.get("clinic_modality_positive_terms") or [])
        if str(term or "").strip()
    )
    offscope_terms = Counter(
        term
        for record in offscope_records
        for term in (record.get("clinic_modality_offscope_terms") or [])
        if str(term or "").strip()
    )
    bridge_terms = Counter(
        term
        for record in records
        for term in (record.get("clinic_modality_bridge_terms") or [])
        if str(term or "").strip()
    )

    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif compatible_count == 0:
        reasons.append("no_fresh_clinic_modality_fit" if fresh else "no_clinic_modality_fit")
    elif compatible_count < target:
        reasons.append("thin_fresh_clinic_modality_inventory" if fresh else "thin_clinic_modality_inventory")
    if unique_count and compatible_count < target and offscope_count:
        reasons.append("offscope_modality_noise")

    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "clinic_modality_fit_actionable_strict": compatible_count,
        "fresh_clinic_modality_fit_actionable_strict": compatible_count if fresh else 0,
        "clinic_modality_missing": max(0, unique_count - compatible_count),
        "offscope_modality_noise": offscope_count,
        "clinic_modality_positive_terms": [term for term, _ in positive_terms.most_common(10)],
        "clinic_modality_offscope_terms": [term for term, _ in offscope_terms.most_common(10)],
        "clinic_modality_bridge_terms": [term for term, _ in bridge_terms.most_common(8)],
        "ready": compatible_count >= target and not reasons,
        "gap": max(0, target - compatible_count),
        "reasons": reasons,
    }


def _clinic_modality_quality(
    records: List[Dict[str, Any]],
    *,
    category_target: int = CLINIC_MODALITY_CATEGORY_TARGET,
    category_lens_target: int = CLINIC_MODALITY_CATEGORY_LENS_TARGET,
) -> Dict[str, Any]:
    """Audit whether strict-fit targets are compatible with Gyulim's treatment modality."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        category_item = _clinic_modality_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
        )
        fresh_category_item = _clinic_modality_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            fresh=True,
        )
        if category_item["ready"]:
            category_ready += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_ready += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _clinic_modality_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
            )
            fresh_lens_item = _clinic_modality_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "unique_fresh_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_clinic_modality_fit_actionable_strict": fresh_lens_item[
                    "clinic_modality_fit_actionable_strict"
                ],
                "fresh_clinic_modality_missing": fresh_lens_item["clinic_modality_missing"],
                "fresh_offscope_modality_noise": fresh_lens_item["offscope_modality_noise"],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_ready += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_ready += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "unique_fresh_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_clinic_modality_fit_actionable_strict": fresh_category_item[
                "clinic_modality_fit_actionable_strict"
            ],
            "fresh_clinic_modality_missing": fresh_category_item["clinic_modality_missing"],
            "fresh_offscope_modality_noise": fresh_category_item["offscope_modality_noise"],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        unique_count = int(item.get("unique_actionable_strict") or 0)
        offscope_count = int(item.get("offscope_modality_noise") or 0)
        no_inventory = unique_count == 0
        return (
            0 if offscope_count else (2 if no_inventory else 1),
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -offscope_count,
            -int(item.get("gap") or 0),
            int(item.get("clinic_modality_fit_actionable_strict") or 0),
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_clinic_modality_fit_actionable_strict": category_target,
            "category_lens_clinic_modality_fit_actionable_strict": category_lens_target,
        },
        "overall": {
            "target_categories": target_categories,
            "clinic_modality_fit_categories": category_ready,
            "category_clinic_modality_fit_ready_rate": LaneStats._rate(
                category_ready,
                target_categories,
            ),
            "fresh_clinic_modality_fit_categories": fresh_category_ready,
            "fresh_category_clinic_modality_fit_ready_rate": LaneStats._rate(
                fresh_category_ready,
                target_categories,
            ),
            "target_category_lenses": target_category_lenses,
            "clinic_modality_fit_category_lenses": category_lens_ready,
            "category_lens_clinic_modality_fit_ready_rate": LaneStats._rate(
                category_lens_ready,
                target_category_lenses,
            ),
            "fresh_clinic_modality_fit_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_clinic_modality_fit_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


def _decision_window_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    unique_count = len(records)
    active_records = [
        record for record in records
        if bool(record.get("decision_window_matched"))
    ]
    active_count = len(active_records)
    completed_noise_records = [
        record for record in records
        if record.get("decision_window_completed_terms")
        and not bool(record.get("decision_window_matched"))
    ]
    completed_noise_count = len(completed_noise_records)
    active_terms = Counter(
        term
        for record in active_records
        for term in (record.get("decision_window_active_terms") or [])
        if str(term or "").strip()
    )
    completed_terms = Counter(
        term
        for record in completed_noise_records
        for term in (record.get("decision_window_completed_terms") or [])
        if str(term or "").strip()
    )
    active_signals = Counter(
        signal
        for record in active_records
        for signal in (record.get("decision_window_active_signals") or [])
        if str(signal or "").strip()
    )
    reason_counts = Counter(
        reason
        for record in records
        if not bool(record.get("decision_window_matched"))
        for reason in (record.get("decision_window_reasons") or [])
        if str(reason or "").strip()
    )

    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif active_count == 0:
        reasons.append("no_fresh_active_decision_window" if fresh else "no_active_decision_window")
    elif active_count < target:
        reasons.append("thin_fresh_decision_window_inventory" if fresh else "thin_decision_window_inventory")
    if unique_count and active_count < target and completed_noise_count:
        reasons.append("completed_decision_window_noise")
    for reason, _ in reason_counts.most_common(4):
        if reason not in reasons:
            reasons.append(reason)

    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "active_decision_actionable_strict": active_count,
        "fresh_active_decision_actionable_strict": active_count if fresh else 0,
        "decision_window_missing": max(0, unique_count - active_count),
        "completed_decision_window_noise": completed_noise_count,
        "decision_window_active_terms": [term for term, _ in active_terms.most_common(10)],
        "decision_window_completed_terms": [term for term, _ in completed_terms.most_common(10)],
        "decision_window_active_signals": [signal for signal, _ in active_signals.most_common(8)],
        "ready": active_count >= target and not reasons,
        "gap": max(0, target - active_count),
        "reasons": reasons,
    }


def _decision_window_quality(
    records: List[Dict[str, Any]],
    *,
    category_target: int = DECISION_WINDOW_CATEGORY_TARGET,
    category_lens_target: int = DECISION_WINDOW_CATEGORY_LENS_TARGET,
) -> Dict[str, Any]:
    """Audit whether strict-fit targets are still actionable decision-stage posts."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        category_item = _decision_window_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
        )
        fresh_category_item = _decision_window_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            fresh=True,
        )
        if category_item["ready"]:
            category_ready += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_ready += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _decision_window_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
            )
            fresh_lens_item = _decision_window_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "unique_fresh_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_active_decision_actionable_strict": fresh_lens_item[
                    "active_decision_actionable_strict"
                ],
                "fresh_decision_window_missing": fresh_lens_item["decision_window_missing"],
                "fresh_completed_decision_window_noise": fresh_lens_item[
                    "completed_decision_window_noise"
                ],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_ready += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_ready += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "unique_fresh_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_active_decision_actionable_strict": fresh_category_item[
                "active_decision_actionable_strict"
            ],
            "fresh_decision_window_missing": fresh_category_item["decision_window_missing"],
            "fresh_completed_decision_window_noise": fresh_category_item[
                "completed_decision_window_noise"
            ],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        unique_count = int(item.get("unique_actionable_strict") or 0)
        completed_noise = int(item.get("completed_decision_window_noise") or 0)
        no_inventory = unique_count == 0
        return (
            0 if completed_noise else (2 if no_inventory else 1),
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -completed_noise,
            -int(item.get("gap") or 0),
            int(item.get("active_decision_actionable_strict") or 0),
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_active_decision_actionable_strict": category_target,
            "category_lens_active_decision_actionable_strict": category_lens_target,
        },
        "overall": {
            "target_categories": target_categories,
            "active_decision_categories": category_ready,
            "category_active_decision_ready_rate": LaneStats._rate(
                category_ready,
                target_categories,
            ),
            "fresh_active_decision_categories": fresh_category_ready,
            "fresh_category_active_decision_ready_rate": LaneStats._rate(
                fresh_category_ready,
                target_categories,
            ),
            "target_category_lenses": target_category_lenses,
            "active_decision_category_lenses": category_lens_ready,
            "category_lens_active_decision_ready_rate": LaneStats._rate(
                category_lens_ready,
                target_category_lenses,
            ),
            "fresh_active_decision_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_active_decision_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


def _seed_candidate_alignment_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    unique_count = len(records)
    checked_count = sum(1 for record in records if bool(record.get("seed_candidate_alignment_checked")))
    aligned_records = [record for record in records if bool(record.get("seed_candidate_alignment_matched"))]
    aligned_count = len(aligned_records)
    missing_count = max(0, unique_count - aligned_count)
    matched_terms = Counter(
        term
        for record in aligned_records
        for term in (record.get("seed_candidate_alignment_matched_terms") or [])
        if str(term or "").strip()
    )
    missing_terms = Counter(
        term
        for record in records
        if not bool(record.get("seed_candidate_alignment_matched"))
        for term in (record.get("seed_candidate_alignment_missing_terms") or [])
        if str(term or "").strip()
    )
    missing_reasons = Counter(
        reason
        for record in records
        if not bool(record.get("seed_candidate_alignment_matched"))
        for reason in (record.get("seed_candidate_alignment_reasons") or [])
        if str(reason or "").strip()
    )
    overlap_rates = [
        float(record.get("seed_candidate_alignment_overlap_rate") or 0.0)
        for record in records
        if bool(record.get("seed_candidate_alignment_checked"))
    ]
    avg_overlap_rate = round(sum(overlap_rates) / len(overlap_rates), 4) if overlap_rates else 0.0

    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif aligned_count == 0:
        reasons.append("no_fresh_seed_candidate_alignment" if fresh else "no_seed_candidate_alignment")
    elif aligned_count < target:
        reasons.append("thin_fresh_seed_candidate_alignment" if fresh else "thin_seed_candidate_alignment")
    if unique_count and aligned_count < target and missing_count:
        reasons.append("source_candidate_drift")
    if aligned_count < target and missing_reasons.get("missing_source_specific_term"):
        reasons.append("source_specific_term_lost")
    if aligned_count < target and missing_reasons.get("missing_source_local_term"):
        reasons.append("source_local_term_lost")
    if aligned_count < target and missing_reasons.get("shallow_source_candidate_overlap"):
        reasons.append("shallow_source_candidate_overlap")

    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "seed_aligned_actionable_strict": aligned_count,
        "fresh_seed_aligned_actionable_strict": aligned_count if fresh else 0,
        "seed_candidate_alignment_checked": checked_count,
        "seed_candidate_alignment_missing": missing_count,
        "avg_seed_candidate_overlap_rate": avg_overlap_rate,
        "seed_candidate_matched_terms": [term for term, _ in matched_terms.most_common(8)],
        "seed_candidate_missing_terms": [term for term, _ in missing_terms.most_common(8)],
        "seed_candidate_missing_reasons": {
            reason: count for reason, count in missing_reasons.most_common(8)
        },
        "ready": aligned_count >= target and not reasons,
        "gap": max(0, target - aligned_count),
        "reasons": reasons,
    }


def _seed_candidate_alignment_quality(
    records: List[Dict[str, Any]],
    *,
    category_target: int = WORK_QUEUE_CATEGORY_TARGET,
    category_lens_target: int = WORK_QUEUE_CATEGORY_LENS_TARGET,
) -> Dict[str, Any]:
    """Audit whether Pathfinder source-keyword intent survives in the chosen targets."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        category_item = _seed_candidate_alignment_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
        )
        fresh_category_item = _seed_candidate_alignment_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            fresh=True,
        )
        if category_item["ready"]:
            category_ready += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_ready += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _seed_candidate_alignment_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
            )
            fresh_lens_item = _seed_candidate_alignment_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "unique_fresh_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_seed_aligned_actionable_strict": fresh_lens_item[
                    "seed_aligned_actionable_strict"
                ],
                "fresh_seed_candidate_alignment_missing": fresh_lens_item[
                    "seed_candidate_alignment_missing"
                ],
                "fresh_seed_candidate_missing_reasons": fresh_lens_item[
                    "seed_candidate_missing_reasons"
                ],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_ready += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_ready += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "unique_fresh_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_seed_aligned_actionable_strict": fresh_category_item[
                "seed_aligned_actionable_strict"
            ],
            "fresh_seed_candidate_alignment_missing": fresh_category_item[
                "seed_candidate_alignment_missing"
            ],
            "fresh_seed_candidate_missing_reasons": fresh_category_item[
                "seed_candidate_missing_reasons"
            ],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        unique_count = int(item.get("unique_actionable_strict") or 0)
        missing_count = int(item.get("seed_candidate_alignment_missing") or 0)
        has_source_drift = bool(unique_count and missing_count)
        return (
            0 if has_source_drift else (2 if unique_count == 0 else 1),
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -int(item.get("gap") or 0),
            int(item.get("seed_aligned_actionable_strict") or 0),
            -missing_count,
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_seed_aligned_actionable_strict": category_target,
            "category_lens_seed_aligned_actionable_strict": category_lens_target,
        },
        "overall": {
            "target_categories": target_categories,
            "seed_aligned_categories": category_ready,
            "category_seed_alignment_ready_rate": LaneStats._rate(category_ready, target_categories),
            "fresh_seed_aligned_categories": fresh_category_ready,
            "fresh_category_seed_alignment_ready_rate": LaneStats._rate(
                fresh_category_ready,
                target_categories,
            ),
            "target_category_lenses": target_category_lenses,
            "seed_aligned_category_lenses": category_lens_ready,
            "category_lens_seed_alignment_ready_rate": LaneStats._rate(
                category_lens_ready,
                target_category_lenses,
            ),
            "fresh_seed_aligned_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_seed_alignment_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


def _local_intent_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    unique_count = len(records)
    checked_count = sum(1 for record in records if bool(record.get("local_intent_checked")))
    local_records = [record for record in records if bool(record.get("local_intent_matched"))]
    local_count = len(local_records)
    missing_count = max(0, unique_count - local_count)
    local_terms = Counter(
        term
        for record in local_records
        for term in (record.get("local_intent_terms") or [])
        if str(term or "").strip()
    )
    expected_terms = _local_anchor_terms()

    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif local_count == 0:
        reasons.append("no_fresh_local_intent" if fresh else "no_local_intent")
    elif local_count < target:
        reasons.append("thin_fresh_local_inventory" if fresh else "thin_local_inventory")
    if unique_count and local_count < target and missing_count:
        reasons.append("missing_local_intent")

    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "local_actionable_strict": local_count,
        "fresh_local_actionable_strict": local_count if fresh else 0,
        "local_intent_checked": checked_count,
        "local_intent_missing": missing_count,
        "local_intent_terms": [term for term, _ in local_terms.most_common(8)],
        "expected_local_intent_terms": expected_terms[:12],
        "ready": local_count >= target and not reasons,
        "gap": max(0, target - local_count),
        "reasons": reasons,
    }


def _local_intent_quality(
    records: List[Dict[str, Any]],
    *,
    category_target: int = WORK_QUEUE_CATEGORY_TARGET,
    category_lens_target: int = WORK_QUEUE_CATEGORY_LENS_TARGET,
) -> Dict[str, Any]:
    """Audit whether work-ready targets preserve Cheongju-area local intent."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        category_item = _local_intent_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
        )
        fresh_category_item = _local_intent_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            fresh=True,
        )
        if category_item["ready"]:
            category_ready += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_ready += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _local_intent_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
            )
            fresh_lens_item = _local_intent_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "unique_fresh_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_local_actionable_strict": fresh_lens_item["local_actionable_strict"],
                "fresh_local_intent_missing": fresh_lens_item["local_intent_missing"],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_ready += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_ready += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "unique_fresh_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_local_actionable_strict": fresh_category_item["local_actionable_strict"],
            "fresh_local_intent_missing": fresh_category_item["local_intent_missing"],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        unique_count = int(item.get("unique_actionable_strict") or 0)
        missing_count = int(item.get("local_intent_missing") or 0)
        local_specific_gap = unique_count > 0 and missing_count > 0
        no_inventory = unique_count == 0
        return (
            0 if local_specific_gap else (2 if no_inventory else 1),
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -int(item.get("gap") or 0),
            int(item.get("local_actionable_strict") or 0),
            -missing_count,
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_local_actionable_strict": category_target,
            "category_lens_local_actionable_strict": category_lens_target,
        },
        "overall": {
            "target_categories": target_categories,
            "local_ready_categories": category_ready,
            "category_local_ready_rate": LaneStats._rate(category_ready, target_categories),
            "fresh_local_ready_categories": fresh_category_ready,
            "fresh_category_local_ready_rate": LaneStats._rate(fresh_category_ready, target_categories),
            "target_category_lenses": target_category_lenses,
            "local_ready_category_lenses": category_lens_ready,
            "category_lens_local_ready_rate": LaneStats._rate(category_lens_ready, target_category_lenses),
            "fresh_local_ready_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_local_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


def _local_area_diversity_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    min_areas: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    unique_count = len(records)
    local_records = [
        record for record in records
        if record.get("local_area_terms")
    ]
    local_count = len(local_records)
    area_terms = Counter(
        term
        for record in local_records
        for term in (record.get("local_area_terms") or [])
        if str(term or "").strip()
    )
    target_area_terms = Counter(
        term
        for record in local_records
        for term in (record.get("local_area_target_terms") or [])
        if str(term or "").strip()
    )
    source_area_terms = Counter(
        term
        for record in local_records
        for term in (record.get("local_area_source_terms") or [])
        if str(term or "").strip()
    )
    area_count = len(area_terms)
    missing_count = max(0, unique_count - local_count)

    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif local_count == 0:
        reasons.append("no_fresh_local_area_terms" if fresh else "no_local_area_terms")
    elif local_count < target:
        reasons.append("thin_fresh_local_area_inventory" if fresh else "thin_local_area_inventory")
    if unique_count and local_count < target and missing_count:
        reasons.append("missing_local_area_terms")
    if unique_count and area_count < min_areas:
        reasons.append(
            "single_local_area_dependency"
            if area_count <= 1
            else "thin_local_area_diversity"
        )

    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "min_local_areas": min_areas,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "local_area_actionable_strict": local_count,
        "fresh_local_area_actionable_strict": local_count if fresh else 0,
        "local_area_missing": missing_count,
        "local_area_count": area_count,
        "local_area_terms": [term for term, _ in area_terms.most_common(10)],
        "target_local_area_terms": [term for term, _ in target_area_terms.most_common(8)],
        "source_local_area_terms": [term for term, _ in source_area_terms.most_common(8)],
        "ready": local_count >= target and area_count >= min_areas and not reasons,
        "gap": max(0, min_areas - area_count),
        "reasons": reasons,
    }


def _local_area_diversity_quality(
    records: List[Dict[str, Any]],
    *,
    category_target: int = WORK_QUEUE_CATEGORY_TARGET,
    category_lens_target: int = WORK_QUEUE_CATEGORY_LENS_TARGET,
    category_min_areas: int = LOCAL_AREA_DIVERSITY_CATEGORY_MIN_AREAS,
    category_lens_min_areas: int = LOCAL_AREA_DIVERSITY_CATEGORY_LENS_MIN_AREAS,
) -> Dict[str, Any]:
    """Audit whether work-ready local inventory spans independent Cheongju areas."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))
    category_min_areas = max(1, int(category_min_areas or 1))
    category_lens_min_areas = max(1, int(category_lens_min_areas or 1))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        category_item = _local_area_diversity_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
            min_areas=category_min_areas,
        )
        fresh_category_item = _local_area_diversity_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            min_areas=category_min_areas,
            fresh=True,
        )
        if category_item["ready"]:
            category_ready += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_ready += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _local_area_diversity_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
                min_areas=category_lens_min_areas,
            )
            fresh_lens_item = _local_area_diversity_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                min_areas=category_lens_min_areas,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "unique_fresh_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_local_area_actionable_strict": fresh_lens_item["local_area_actionable_strict"],
                "fresh_local_area_count": fresh_lens_item["local_area_count"],
                "fresh_local_area_missing": fresh_lens_item["local_area_missing"],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_ready += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_ready += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "unique_fresh_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_local_area_actionable_strict": fresh_category_item["local_area_actionable_strict"],
            "fresh_local_area_count": fresh_category_item["local_area_count"],
            "fresh_local_area_missing": fresh_category_item["local_area_missing"],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        unique_count = int(item.get("unique_actionable_strict") or 0)
        area_count = int(item.get("local_area_count") or 0)
        has_area_gap = bool(unique_count and area_count < int(item.get("min_local_areas") or 1))
        return (
            0 if has_area_gap else (2 if unique_count == 0 else 1),
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            area_count,
            -int(item.get("unique_actionable_strict") or 0),
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_local_area_actionable_strict": category_target,
            "category_lens_local_area_actionable_strict": category_lens_target,
            "category_min_local_areas": category_min_areas,
            "category_lens_min_local_areas": category_lens_min_areas,
        },
        "overall": {
            "target_categories": target_categories,
            "local_area_diverse_categories": category_ready,
            "category_local_area_diversity_ready_rate": LaneStats._rate(
                category_ready,
                target_categories,
            ),
            "fresh_local_area_diverse_categories": fresh_category_ready,
            "fresh_category_local_area_diversity_ready_rate": LaneStats._rate(
                fresh_category_ready,
                target_categories,
            ),
            "target_category_lenses": target_category_lenses,
            "local_area_diverse_category_lenses": category_lens_ready,
            "category_lens_local_area_diversity_ready_rate": LaneStats._rate(
                category_lens_ready,
                target_category_lenses,
            ),
            "fresh_local_area_diverse_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_local_area_diversity_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


def _patient_surface_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    unique_count = len(records)
    checked_count = sum(1 for record in records if bool(record.get("patient_surface_checked")))
    patient_records = [record for record in records if bool(record.get("patient_surface_matched"))]
    provider_noise_records = [
        record for record in records
        if bool(record.get("patient_surface_provider_noise"))
    ]
    patient_count = len(patient_records)
    provider_noise_count = len(provider_noise_records)
    missing_count = max(0, unique_count - patient_count)
    patient_terms = Counter(
        term
        for record in patient_records
        for term in (record.get("patient_surface_terms") or [])
        if str(term or "").strip()
    )
    provider_terms = Counter(
        term
        for record in provider_noise_records
        for term in (record.get("patient_surface_provider_terms") or [])
        if str(term or "").strip()
    )

    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif patient_count == 0:
        reasons.append("no_fresh_patient_surface" if fresh else "no_patient_surface")
    elif patient_count < target:
        reasons.append("thin_fresh_patient_surface_inventory" if fresh else "thin_patient_surface_inventory")
    if unique_count and patient_count < target and missing_count:
        reasons.append("missing_patient_surface")
    if unique_count and patient_count < target and provider_noise_count:
        reasons.append("provider_surface_noise")

    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "patient_surface_actionable_strict": patient_count,
        "fresh_patient_surface_actionable_strict": patient_count if fresh else 0,
        "patient_surface_checked": checked_count,
        "patient_surface_missing": missing_count,
        "provider_surface_noise": provider_noise_count,
        "patient_surface_terms": [term for term, _ in patient_terms.most_common(8)],
        "patient_surface_provider_terms": [term for term, _ in provider_terms.most_common(8)],
        "ready": patient_count >= target and not reasons,
        "gap": max(0, target - patient_count),
        "reasons": reasons,
    }


def _patient_surface_quality(
    records: List[Dict[str, Any]],
    *,
    category_target: int = WORK_QUEUE_CATEGORY_TARGET,
    category_lens_target: int = WORK_QUEUE_CATEGORY_LENS_TARGET,
) -> Dict[str, Any]:
    """Audit whether work-ready targets are authentic patient/workable surfaces."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        category_item = _patient_surface_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
        )
        fresh_category_item = _patient_surface_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            fresh=True,
        )
        if category_item["ready"]:
            category_ready += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_ready += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _patient_surface_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
            )
            fresh_lens_item = _patient_surface_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "unique_fresh_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_patient_surface_actionable_strict": fresh_lens_item["patient_surface_actionable_strict"],
                "fresh_patient_surface_missing": fresh_lens_item["patient_surface_missing"],
                "fresh_provider_surface_noise": fresh_lens_item["provider_surface_noise"],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_ready += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_ready += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "unique_fresh_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_patient_surface_actionable_strict": fresh_category_item["patient_surface_actionable_strict"],
            "fresh_patient_surface_missing": fresh_category_item["patient_surface_missing"],
            "fresh_provider_surface_noise": fresh_category_item["provider_surface_noise"],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        unique_count = int(item.get("unique_actionable_strict") or 0)
        missing_count = int(item.get("patient_surface_missing") or 0)
        provider_noise_count = int(item.get("provider_surface_noise") or 0)
        surface_specific_gap = unique_count > 0 and (missing_count > 0 or provider_noise_count > 0)
        no_inventory = unique_count == 0
        return (
            0 if surface_specific_gap else (2 if no_inventory else 1),
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -int(item.get("gap") or 0),
            int(item.get("patient_surface_actionable_strict") or 0),
            -provider_noise_count,
            -missing_count,
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_patient_surface_actionable_strict": category_target,
            "category_lens_patient_surface_actionable_strict": category_lens_target,
        },
        "overall": {
            "target_categories": target_categories,
            "patient_surface_ready_categories": category_ready,
            "category_patient_surface_ready_rate": LaneStats._rate(category_ready, target_categories),
            "fresh_patient_surface_ready_categories": fresh_category_ready,
            "fresh_category_patient_surface_ready_rate": LaneStats._rate(fresh_category_ready, target_categories),
            "target_category_lenses": target_category_lenses,
            "patient_surface_ready_category_lenses": category_lens_ready,
            "category_lens_patient_surface_ready_rate": LaneStats._rate(
                category_lens_ready,
                target_category_lenses,
            ),
            "fresh_patient_surface_ready_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_patient_surface_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


def _viral_action_route_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    unique_count = len(records)
    checked_count = sum(1 for record in records if bool(record.get("viral_action_route_checked")))
    routed_records = [record for record in records if bool(record.get("viral_action_route_matched"))]
    mismatch_records = [
        record for record in records
        if bool(record.get("viral_action_route_mismatch"))
    ]
    routed_count = len(routed_records)
    mismatch_count = len(mismatch_records)
    missing_count = max(0, unique_count - routed_count)
    routes = Counter(
        route
        for record in routed_records
        for route in (record.get("viral_action_route_routes") or [record.get("viral_action_route")])
        if str(route or "").strip()
    )
    route_terms = Counter(
        term
        for record in routed_records
        for term in (record.get("viral_action_route_terms") or [])
        if str(term or "").strip()
    )
    observed_routes = Counter(
        route
        for record in records
        for route in (record.get("viral_action_route_observed_routes") or [])
        if str(route or "").strip()
    )
    expected_routes = _expected_viral_action_routes(lens)

    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif routed_count == 0:
        reasons.append("no_fresh_viral_action_route" if fresh else "no_viral_action_route")
    elif routed_count < target:
        reasons.append("thin_fresh_viral_action_route_inventory" if fresh else "thin_viral_action_route_inventory")
    if unique_count and routed_count < target and missing_count:
        reasons.append("missing_viral_action_route")
    if unique_count and routed_count < target and mismatch_count:
        reasons.append("viral_action_route_mismatch")

    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "routed_actionable_strict": routed_count,
        "fresh_routed_actionable_strict": routed_count if fresh else 0,
        "viral_action_route_checked": checked_count,
        "viral_action_route_missing": missing_count,
        "viral_action_route_mismatch": mismatch_count,
        "viral_action_routes": [route for route, _ in routes.most_common(8)],
        "viral_action_route_terms": [term for term, _ in route_terms.most_common(8)],
        "observed_viral_action_routes": [route for route, _ in observed_routes.most_common(8)],
        "expected_viral_action_routes": expected_routes[:8],
        "ready": routed_count >= target and not reasons,
        "gap": max(0, target - routed_count),
        "reasons": reasons,
    }


def _viral_action_route_quality(
    records: List[Dict[str, Any]],
    *,
    category_target: int = WORK_QUEUE_CATEGORY_TARGET,
    category_lens_target: int = WORK_QUEUE_CATEGORY_LENS_TARGET,
) -> Dict[str, Any]:
    """Audit whether work-ready targets expose a concrete viral action route."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        category_item = _viral_action_route_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
        )
        fresh_category_item = _viral_action_route_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            fresh=True,
        )
        if category_item["ready"]:
            category_ready += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_ready += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _viral_action_route_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
            )
            fresh_lens_item = _viral_action_route_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "unique_fresh_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_routed_actionable_strict": fresh_lens_item["routed_actionable_strict"],
                "fresh_viral_action_route_missing": fresh_lens_item["viral_action_route_missing"],
                "fresh_viral_action_route_mismatch": fresh_lens_item["viral_action_route_mismatch"],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_ready += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_ready += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "unique_fresh_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_routed_actionable_strict": fresh_category_item["routed_actionable_strict"],
            "fresh_viral_action_route_missing": fresh_category_item["viral_action_route_missing"],
            "fresh_viral_action_route_mismatch": fresh_category_item["viral_action_route_mismatch"],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        unique_count = int(item.get("unique_actionable_strict") or 0)
        missing_count = int(item.get("viral_action_route_missing") or 0)
        mismatch_count = int(item.get("viral_action_route_mismatch") or 0)
        route_specific_gap = unique_count > 0 and (missing_count > 0 or mismatch_count > 0)
        no_inventory = unique_count == 0
        return (
            0 if route_specific_gap else (2 if no_inventory else 1),
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -int(item.get("gap") or 0),
            int(item.get("routed_actionable_strict") or 0),
            -mismatch_count,
            -missing_count,
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_routed_actionable_strict": category_target,
            "category_lens_routed_actionable_strict": category_lens_target,
        },
        "overall": {
            "target_categories": target_categories,
            "route_ready_categories": category_ready,
            "category_route_ready_rate": LaneStats._rate(category_ready, target_categories),
            "fresh_route_ready_categories": fresh_category_ready,
            "fresh_category_route_ready_rate": LaneStats._rate(fresh_category_ready, target_categories),
            "target_category_lenses": target_category_lenses,
            "route_ready_category_lenses": category_lens_ready,
            "category_lens_route_ready_rate": LaneStats._rate(category_lens_ready, target_category_lenses),
            "fresh_route_ready_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_route_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


def _reply_workability_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    unique_count = len(records)
    checked_count = sum(1 for record in records if bool(record.get("reply_workability_checked")))
    workable_records = [record for record in records if bool(record.get("reply_workability_matched"))]
    risk_records = [record for record in records if bool(record.get("reply_risk_blocked"))]
    metric_missing_records = [record for record in records if bool(record.get("reply_metric_missing"))]
    low_opportunity_records = [
        record for record in records
        if not bool(record.get("reply_workability_matched"))
        and not bool(record.get("reply_risk_blocked"))
    ]
    workable_count = len(workable_records)
    risk_count = len(risk_records)
    metric_missing_count = len(metric_missing_records)
    missing_count = max(0, unique_count - workable_count)
    scores = [
        float(record.get("reply_opportunity_score"))
        for record in records
        if record.get("reply_opportunity_score") is not None
    ]
    tiers = Counter(
        str(record.get("reply_opportunity_tier") or "")
        for record in records
        if str(record.get("reply_opportunity_tier") or "").strip()
    )
    signals = Counter(
        signal
        for record in records
        for signal in (record.get("reply_opportunity_signals") or [])
        if str(signal or "").strip()
    )
    risk_flags = Counter(
        flag
        for record in risk_records
        for flag in (record.get("reply_risk_flags") or [])
        if str(flag or "").strip()
    )

    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif workable_count == 0:
        reasons.append("no_fresh_reply_workable_surface" if fresh else "no_reply_workable_surface")
    elif workable_count < target:
        reasons.append("thin_fresh_reply_workable_inventory" if fresh else "thin_reply_workable_inventory")
    if unique_count and workable_count < target and missing_count:
        reasons.append("missing_reply_workability")
    if unique_count and workable_count < target and risk_count:
        reasons.append("reply_risk_flags")
    if unique_count and workable_count < target and metric_missing_count:
        reasons.append("missing_reply_opportunity_metrics")
    if unique_count and workable_count < target and low_opportunity_records:
        reasons.append("low_reply_opportunity_score")

    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    avg_score = round(sum(scores) / len(scores), 2) if scores else None
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "reply_workable_actionable_strict": workable_count,
        "fresh_reply_workable_actionable_strict": workable_count if fresh else 0,
        "reply_workability_checked": checked_count,
        "reply_workability_missing": missing_count,
        "reply_risk_flagged": risk_count,
        "reply_metric_missing": metric_missing_count,
        "avg_reply_opportunity_score": avg_score,
        "reply_opportunity_tiers": [tier for tier, _ in tiers.most_common(8)],
        "reply_opportunity_signals": [signal for signal, _ in signals.most_common(8)],
        "reply_risk_flags": [flag for flag, _ in risk_flags.most_common(8)],
        "ready": workable_count >= target and not reasons,
        "gap": max(0, target - workable_count),
        "reasons": reasons,
    }


def _reply_workability_quality(
    records: List[Dict[str, Any]],
    *,
    category_target: int = WORK_QUEUE_CATEGORY_TARGET,
    category_lens_target: int = WORK_QUEUE_CATEGORY_LENS_TARGET,
) -> Dict[str, Any]:
    """Audit whether work-ready targets are safe and useful for public reply work."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        category_item = _reply_workability_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
        )
        fresh_category_item = _reply_workability_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            fresh=True,
        )
        if category_item["ready"]:
            category_ready += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_ready += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _reply_workability_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
            )
            fresh_lens_item = _reply_workability_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "unique_fresh_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_reply_workable_actionable_strict": fresh_lens_item[
                    "reply_workable_actionable_strict"
                ],
                "fresh_reply_workability_missing": fresh_lens_item["reply_workability_missing"],
                "fresh_reply_risk_flagged": fresh_lens_item["reply_risk_flagged"],
                "fresh_reply_metric_missing": fresh_lens_item["reply_metric_missing"],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_ready += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_ready += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "unique_fresh_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_reply_workable_actionable_strict": fresh_category_item[
                "reply_workable_actionable_strict"
            ],
            "fresh_reply_workability_missing": fresh_category_item["reply_workability_missing"],
            "fresh_reply_risk_flagged": fresh_category_item["reply_risk_flagged"],
            "fresh_reply_metric_missing": fresh_category_item["reply_metric_missing"],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        unique_count = int(item.get("unique_actionable_strict") or 0)
        missing_count = int(item.get("reply_workability_missing") or 0)
        risk_count = int(item.get("reply_risk_flagged") or 0)
        metric_missing = int(item.get("reply_metric_missing") or 0)
        reply_specific_gap = unique_count > 0 and (missing_count > 0 or risk_count > 0 or metric_missing > 0)
        no_inventory = unique_count == 0
        return (
            0 if reply_specific_gap else (2 if no_inventory else 1),
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -int(item.get("gap") or 0),
            int(item.get("reply_workable_actionable_strict") or 0),
            -risk_count,
            -metric_missing,
            -missing_count,
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_reply_workable_actionable_strict": category_target,
            "category_lens_reply_workable_actionable_strict": category_lens_target,
        },
        "overall": {
            "target_categories": target_categories,
            "reply_workable_categories": category_ready,
            "category_reply_workable_ready_rate": LaneStats._rate(category_ready, target_categories),
            "fresh_reply_workable_categories": fresh_category_ready,
            "fresh_category_reply_workable_ready_rate": LaneStats._rate(
                fresh_category_ready,
                target_categories,
            ),
            "target_category_lenses": target_category_lenses,
            "reply_workable_category_lenses": category_lens_ready,
            "category_lens_reply_workable_ready_rate": LaneStats._rate(
                category_lens_ready,
                target_category_lenses,
            ),
            "fresh_reply_workable_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_reply_workable_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


def _compliance_work_mode(record: Dict[str, Any]) -> str:
    """Classify a strict actionable target by how safely it can enter viral work."""
    if record.get("status") not in ACTIONABLE_STATUSES or not bool(record.get("strict_fit")):
        return "not_work_queue"
    risk_flags = {
        str(flag or "").strip()
        for flag in (record.get("reply_risk_flags") or [])
        if str(flag or "").strip()
    }
    risk_penalty = float(record.get("reply_risk_penalty") or 0.0)
    manual_review = bool(record.get("reply_manual_review")) or str(record.get("status") or "") == "manual_review"
    severe = bool(risk_flags & COMPLIANCE_SEVERE_RISK_FLAGS)
    if severe or risk_penalty <= REPLY_WORKABILITY_RISK_PENALTY_BLOCK or str(record.get("status") or "") == "manual_review":
        return "blocked_or_escalate"
    if risk_flags or manual_review or bool(record.get("reply_risk_blocked")):
        return "manual_review_only"
    if bool(record.get("reply_metric_missing")):
        return "reply_metric_missing"
    if not bool(record.get("reply_workability_matched")):
        return "low_reply_opportunity"
    return "auto_work_ready"


def _compliance_work_mode_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    mode_counts = Counter(_compliance_work_mode(record) for record in records)
    unique_count = len(records)
    auto_count = int(mode_counts.get("auto_work_ready") or 0)
    manual_count = int(mode_counts.get("manual_review_only") or 0)
    blocked_count = int(mode_counts.get("blocked_or_escalate") or 0)
    metric_missing_count = int(mode_counts.get("reply_metric_missing") or 0)
    low_opportunity_count = int(mode_counts.get("low_reply_opportunity") or 0)
    risk_flags = Counter(
        flag
        for record in records
        for flag in (record.get("reply_risk_flags") or [])
        if str(flag or "").strip()
    )

    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif auto_count == 0:
        reasons.append("no_fresh_auto_work_ready_target" if fresh else "no_auto_work_ready_target")
    elif auto_count < target:
        reasons.append("thin_fresh_auto_work_ready_inventory" if fresh else "thin_auto_work_ready_inventory")
    if unique_count and auto_count < target and manual_count:
        reasons.append("manual_review_only_inventory")
    if unique_count and auto_count < target and blocked_count:
        reasons.append("blocked_or_escalate_inventory")
    if unique_count and auto_count < target and metric_missing_count:
        reasons.append("missing_reply_opportunity_metrics")
    if unique_count and auto_count < target and low_opportunity_count:
        reasons.append("low_reply_opportunity_score")

    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "auto_work_ready_actionable_strict": auto_count,
        "fresh_auto_work_ready_actionable_strict": auto_count if fresh else 0,
        "manual_review_only_actionable_strict": manual_count,
        "blocked_or_escalate_actionable_strict": blocked_count,
        "reply_metric_missing_actionable_strict": metric_missing_count,
        "low_reply_opportunity_actionable_strict": low_opportunity_count,
        "work_mode_counts": dict(mode_counts),
        "reply_risk_flags": [flag for flag, _ in risk_flags.most_common(8)],
        "ready": auto_count >= target and not reasons,
        "gap": max(0, target - auto_count),
        "reasons": reasons,
    }


def _compliance_work_mode_quality(
    records: List[Dict[str, Any]],
    *,
    category_target: int = WORK_QUEUE_CATEGORY_TARGET,
    category_lens_target: int = WORK_QUEUE_CATEGORY_LENS_TARGET,
) -> Dict[str, Any]:
    """Audit whether strict-fit inventory is actually usable without compliance escalation."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0
    overall_modes: Counter = Counter()
    fresh_overall_modes: Counter = Counter()

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        for record in category_records:
            overall_modes[_compliance_work_mode(record)] += 1
        for record in fresh_category_records:
            fresh_overall_modes[_compliance_work_mode(record)] += 1
        category_item = _compliance_work_mode_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
        )
        fresh_category_item = _compliance_work_mode_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            fresh=True,
        )
        if category_item["ready"]:
            category_ready += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_ready += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _compliance_work_mode_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
            )
            fresh_lens_item = _compliance_work_mode_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "unique_fresh_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_auto_work_ready_actionable_strict": fresh_lens_item[
                    "auto_work_ready_actionable_strict"
                ],
                "fresh_manual_review_only_actionable_strict": fresh_lens_item[
                    "manual_review_only_actionable_strict"
                ],
                "fresh_blocked_or_escalate_actionable_strict": fresh_lens_item[
                    "blocked_or_escalate_actionable_strict"
                ],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_ready += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_ready += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "unique_fresh_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_auto_work_ready_actionable_strict": fresh_category_item[
                "auto_work_ready_actionable_strict"
            ],
            "fresh_manual_review_only_actionable_strict": fresh_category_item[
                "manual_review_only_actionable_strict"
            ],
            "fresh_blocked_or_escalate_actionable_strict": fresh_category_item[
                "blocked_or_escalate_actionable_strict"
            ],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        unique_count = int(item.get("unique_actionable_strict") or 0)
        manual_count = int(item.get("manual_review_only_actionable_strict") or 0)
        blocked_count = int(item.get("blocked_or_escalate_actionable_strict") or 0)
        no_inventory = unique_count == 0
        return (
            0 if unique_count and (manual_count or blocked_count) else (2 if no_inventory else 1),
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -int(item.get("gap") or 0),
            -blocked_count,
            -manual_count,
            int(item.get("auto_work_ready_actionable_strict") or 0),
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_auto_work_ready_actionable_strict": category_target,
            "category_lens_auto_work_ready_actionable_strict": category_lens_target,
        },
        "overall": {
            "target_categories": target_categories,
            "auto_work_ready_categories": category_ready,
            "category_auto_work_ready_rate": LaneStats._rate(category_ready, target_categories),
            "fresh_auto_work_ready_categories": fresh_category_ready,
            "fresh_category_auto_work_ready_rate": LaneStats._rate(fresh_category_ready, target_categories),
            "target_category_lenses": target_category_lenses,
            "auto_work_ready_category_lenses": category_lens_ready,
            "category_lens_auto_work_ready_rate": LaneStats._rate(
                category_lens_ready,
                target_category_lenses,
            ),
            "fresh_auto_work_ready_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_auto_work_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
            "work_mode_counts": dict(overall_modes),
            "fresh_work_mode_counts": dict(fresh_overall_modes),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


EXECUTION_READINESS_COMPONENTS = (
    "engagement_hook",
    "treatment_signature",
    "local_intent",
    "patient_surface",
    "viral_action_route",
    "reply_workability",
)


def _execution_readiness_missing_components(record: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    if not bool(record.get("engagement_hook_matched")):
        missing.append("engagement_hook")
    if not bool(record.get("treatment_signature_matched")):
        missing.append("treatment_signature")
    if not bool(record.get("local_intent_matched")):
        missing.append("local_intent")
    if not bool(record.get("patient_surface_matched")):
        missing.append("patient_surface")
    if bool(record.get("patient_surface_provider_noise")):
        missing.append("provider_surface_noise")
    if not bool(record.get("viral_action_route_matched")):
        missing.append("viral_action_route")
    if bool(record.get("viral_action_route_mismatch")):
        missing.append("viral_action_route_mismatch")
    if not bool(record.get("reply_workability_matched")):
        missing.append("reply_workability")
    if bool(record.get("reply_risk_blocked")):
        missing.append("reply_risk_flags")
    return missing


def _execution_ready_record(record: Dict[str, Any]) -> bool:
    return not _execution_readiness_missing_components(record)


def _execution_readiness_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    unique_count = len(records)
    ready_records = [record for record in records if _execution_ready_record(record)]
    ready_count = len(ready_records)
    missing_counter = Counter(
        component
        for record in records
        if not _execution_ready_record(record)
        for component in _execution_readiness_missing_components(record)
    )
    component_counts = {
        "engagement_hook": sum(1 for record in records if bool(record.get("engagement_hook_matched"))),
        "treatment_signature": sum(1 for record in records if bool(record.get("treatment_signature_matched"))),
        "local_intent": sum(1 for record in records if bool(record.get("local_intent_matched"))),
        "patient_surface": sum(1 for record in records if bool(record.get("patient_surface_matched"))),
        "viral_action_route": sum(1 for record in records if bool(record.get("viral_action_route_matched"))),
        "reply_workability": sum(1 for record in records if bool(record.get("reply_workability_matched"))),
    }
    fragmented = bool(
        unique_count
        and ready_count < target
        and all(component_counts.get(component, 0) >= target for component in EXECUTION_READINESS_COMPONENTS)
    )
    treatment_terms = Counter(
        term
        for record in ready_records
        for term in (record.get("treatment_signature_terms") or [])
        if str(term or "").strip()
    )
    local_terms = Counter(
        term
        for record in ready_records
        for term in (record.get("local_intent_terms") or [])
        if str(term or "").strip()
    )
    routes = Counter(
        route
        for record in ready_records
        for route in (record.get("viral_action_route_routes") or [record.get("viral_action_route")])
        if str(route or "").strip()
    )
    reply_signals = Counter(
        signal
        for record in ready_records
        for signal in (record.get("reply_opportunity_signals") or [])
        if str(signal or "").strip()
    )

    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif ready_count == 0:
        reasons.append("no_fresh_execution_ready_target" if fresh else "no_execution_ready_target")
    elif ready_count < target:
        reasons.append("thin_fresh_execution_ready_inventory" if fresh else "thin_execution_ready_inventory")
    if fragmented:
        reasons.append("fragmented_fresh_execution_signals" if fresh else "fragmented_execution_signals")
    if unique_count and ready_count < target:
        reason_names = {
            "engagement_hook": "missing_engagement_hook",
            "treatment_signature": "missing_treatment_signature",
            "local_intent": "missing_local_intent",
            "patient_surface": "missing_patient_surface",
            "provider_surface_noise": "provider_surface_noise",
            "viral_action_route": "missing_viral_action_route",
            "viral_action_route_mismatch": "viral_action_route_mismatch",
            "reply_workability": "missing_reply_workability",
            "reply_risk_flags": "reply_risk_flags",
        }
        for component in (
            "engagement_hook",
            "treatment_signature",
            "local_intent",
            "patient_surface",
            "provider_surface_noise",
            "viral_action_route",
            "viral_action_route_mismatch",
            "reply_workability",
            "reply_risk_flags",
        ):
            if missing_counter.get(component):
                reasons.append(reason_names[component])

    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "execution_ready_actionable_strict": ready_count,
        "fresh_execution_ready_actionable_strict": ready_count if fresh else 0,
        "execution_readiness_missing": max(0, unique_count - ready_count),
        "execution_readiness_component_counts": component_counts,
        "execution_readiness_missing_components": dict(missing_counter),
        "fragmented_execution_signals": fragmented,
        "treatment_signature_terms": [term for term, _ in treatment_terms.most_common(8)],
        "local_intent_terms": [term for term, _ in local_terms.most_common(8)],
        "viral_action_routes": [route for route, _ in routes.most_common(8)],
        "reply_opportunity_signals": [signal for signal, _ in reply_signals.most_common(8)],
        "ready": ready_count >= target and not reasons,
        "gap": max(0, target - ready_count),
        "reasons": reasons,
    }


def _execution_readiness_quality(
    records: List[Dict[str, Any]],
    *,
    category_target: int = WORK_QUEUE_CATEGORY_TARGET,
    category_lens_target: int = WORK_QUEUE_CATEGORY_LENS_TARGET,
) -> Dict[str, Any]:
    """Audit whether one target carries every signal needed for Viral Hunter work."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_ready = 0
    category_lens_ready = 0
    fresh_category_ready = 0
    fresh_category_lens_ready = 0

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        category_item = _execution_readiness_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
        )
        fresh_category_item = _execution_readiness_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            fresh=True,
        )
        if category_item["ready"]:
            category_ready += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_ready += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _execution_readiness_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
            )
            fresh_lens_item = _execution_readiness_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "unique_fresh_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_execution_ready_actionable_strict": fresh_lens_item[
                    "execution_ready_actionable_strict"
                ],
                "fresh_execution_readiness_missing": fresh_lens_item["execution_readiness_missing"],
                "fresh_execution_readiness_missing_components": fresh_lens_item[
                    "execution_readiness_missing_components"
                ],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_ready += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_ready += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "unique_fresh_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_execution_ready_actionable_strict": fresh_category_item[
                "execution_ready_actionable_strict"
            ],
            "fresh_execution_readiness_missing": fresh_category_item["execution_readiness_missing"],
            "fresh_execution_readiness_missing_components": fresh_category_item[
                "execution_readiness_missing_components"
            ],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        unique_count = int(item.get("unique_actionable_strict") or 0)
        missing_count = int(item.get("execution_readiness_missing") or 0)
        fragmented = bool(item.get("fragmented_execution_signals"))
        no_inventory = unique_count == 0
        return (
            0 if fragmented else (1 if unique_count and missing_count else (3 if no_inventory else 2)),
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -int(item.get("gap") or 0),
            int(item.get("execution_ready_actionable_strict") or 0),
            -missing_count,
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_execution_ready_actionable_strict": category_target,
            "category_lens_execution_ready_actionable_strict": category_lens_target,
        },
        "overall": {
            "target_categories": target_categories,
            "execution_ready_categories": category_ready,
            "category_execution_ready_rate": LaneStats._rate(category_ready, target_categories),
            "fresh_execution_ready_categories": fresh_category_ready,
            "fresh_category_execution_ready_rate": LaneStats._rate(fresh_category_ready, target_categories),
            "target_category_lenses": target_category_lenses,
            "execution_ready_category_lenses": category_lens_ready,
            "category_lens_execution_ready_rate": LaneStats._rate(
                category_lens_ready,
                target_category_lenses,
            ),
            "fresh_execution_ready_category_lenses": fresh_category_lens_ready,
            "fresh_category_lens_execution_ready_rate": LaneStats._rate(
                fresh_category_lens_ready,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


def _execution_priority_alignment_item(
    *,
    lane_type: str,
    category: str,
    lens: str = "",
    records: List[Dict[str, Any]],
    target: int,
    top_window: int,
    fresh: bool = False,
) -> Dict[str, Any]:
    ordered_records = sorted(
        records,
        key=lambda record: float(record.get("priority") or 0.0),
        reverse=True,
    )
    unique_count = len(ordered_records)
    top_window = max(target, int(top_window or target or 1))
    top_records = ordered_records[:top_window]
    ready_records = [record for record in ordered_records if _execution_ready_record(record)]
    top_ready_records = [record for record in top_records if _execution_ready_record(record)]
    ready_count = len(ready_records)
    top_ready_count = len(top_ready_records)
    top_non_ready_count = max(0, len(top_records) - top_ready_count)
    ready_ranks = [
        index + 1
        for index, record in enumerate(ordered_records)
        if _execution_ready_record(record)
    ]
    first_ready_rank = min(ready_ranks) if ready_ranks else None
    target_ready_ranks = ready_ranks[:target]
    target_ready_within_window = bool(
        len(target_ready_ranks) >= target
        and max(target_ready_ranks) <= top_window
    )
    non_ready_above_target_ready = False
    if ready_count >= target and target_ready_ranks:
        cutoff_rank = max(target_ready_ranks)
        non_ready_above_target_ready = any(
            not _execution_ready_record(record)
            for record in ordered_records[:cutoff_rank]
        )

    ready_priorities = [
        float(record.get("priority") or 0.0)
        for record in ready_records
    ]
    non_ready_top_priorities = [
        float(record.get("priority") or 0.0)
        for record in top_records
        if not _execution_ready_record(record)
    ]

    reasons: List[str] = []
    if unique_count == 0:
        reasons.append("no_fresh_unique_actionable_strict" if fresh else "no_unique_actionable_strict")
    elif ready_count == 0:
        reasons.append("no_fresh_execution_ready_inventory" if fresh else "no_execution_ready_inventory")
    elif ready_count < target:
        reasons.append("thin_fresh_execution_ready_inventory" if fresh else "thin_execution_ready_inventory")
    elif top_ready_count < target:
        reasons.append("fresh_execution_ready_buried" if fresh else "execution_ready_buried")
    if ready_count >= target and top_ready_count < target and top_non_ready_count:
        reasons.append("non_ready_priority_inversion")
    if ready_count >= target and not target_ready_within_window:
        reasons.append("top_priority_execution_gap")
    if ready_count >= target and top_ready_count < target and non_ready_above_target_ready:
        reasons.append("non_ready_above_execution_ready")

    lane = f"{category}::{lens}" if lane_type == "category_lens" else category
    return {
        "type": lane_type,
        "lane": lane,
        "category": category,
        "lens": lens,
        "target": target,
        "priority_top_window": top_window,
        "unique_actionable_strict": unique_count,
        "unique_fresh_actionable_strict": unique_count if fresh else 0,
        "execution_ready_actionable_strict": ready_count,
        "fresh_execution_ready_actionable_strict": ready_count if fresh else 0,
        "top_execution_ready_actionable_strict": top_ready_count,
        "fresh_top_execution_ready_actionable_strict": top_ready_count if fresh else 0,
        "top_non_execution_ready_actionable_strict": top_non_ready_count,
        "highest_execution_ready_rank": first_ready_rank,
        "target_execution_ready_ranks": target_ready_ranks,
        "execution_priority_gap": max(0, target - top_ready_count),
        "max_execution_ready_priority": max(ready_priorities) if ready_priorities else None,
        "max_top_non_ready_priority": max(non_ready_top_priorities) if non_ready_top_priorities else None,
        "ready": ready_count >= target and top_ready_count >= target and not reasons,
        "gap": max(0, target - top_ready_count),
        "reasons": reasons,
    }


def _execution_priority_alignment_quality(
    records: List[Dict[str, Any]],
    *,
    category_target: int = WORK_QUEUE_CATEGORY_TARGET,
    category_lens_target: int = WORK_QUEUE_CATEGORY_LENS_TARGET,
    category_top_window: int = EXECUTION_PRIORITY_CATEGORY_TOP_WINDOW,
    category_lens_top_window: int = EXECUTION_PRIORITY_CATEGORY_LENS_TOP_WINDOW,
) -> Dict[str, Any]:
    """Audit whether execution-ready targets are ranked where Viral Hunter will use them."""
    focus_categories = _priority_focus_categories()
    lenses = list(PATIENT_JOURNEY_LENSES)
    category_target = max(1, int(category_target or 1))
    category_lens_target = max(1, int(category_lens_target or 1))
    category_top_window = max(category_target, int(category_top_window or category_target))
    category_lens_top_window = max(category_lens_target, int(category_lens_top_window or category_lens_target))

    by_category: Dict[str, Dict[str, Any]] = {}
    category_gaps: List[Dict[str, Any]] = []
    category_lens_gaps: List[Dict[str, Any]] = []
    fresh_category_gaps: List[Dict[str, Any]] = []
    fresh_category_lens_gaps: List[Dict[str, Any]] = []
    category_aligned = 0
    category_lens_aligned = 0
    fresh_category_aligned = 0
    fresh_category_lens_aligned = 0

    for category in focus_categories:
        category_records = _unique_actionable_records(records, category=category)
        fresh_category_records = _unique_actionable_records(records, category=category, fresh_only=True)
        category_item = _execution_priority_alignment_item(
            lane_type="category",
            category=category,
            records=category_records,
            target=category_target,
            top_window=category_top_window,
        )
        fresh_category_item = _execution_priority_alignment_item(
            lane_type="category",
            category=category,
            records=fresh_category_records,
            target=category_target,
            top_window=category_top_window,
            fresh=True,
        )
        if category_item["ready"]:
            category_aligned += 1
        else:
            category_gaps.append(category_item)
        if fresh_category_item["ready"]:
            fresh_category_aligned += 1
        else:
            fresh_category_gaps.append(fresh_category_item)

        lens_items: Dict[str, Dict[str, Any]] = {}
        for lens in lenses:
            lens_records = _unique_actionable_records(records, category=category, lens=lens)
            fresh_lens_records = _unique_actionable_records(
                records,
                category=category,
                lens=lens,
                fresh_only=True,
            )
            lens_item = _execution_priority_alignment_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=lens_records,
                target=category_lens_target,
                top_window=category_lens_top_window,
            )
            fresh_lens_item = _execution_priority_alignment_item(
                lane_type="category_lens",
                category=category,
                lens=lens,
                records=fresh_lens_records,
                target=category_lens_target,
                top_window=category_lens_top_window,
                fresh=True,
            )
            lens_items[lens] = {
                **lens_item,
                "fresh_ready": fresh_lens_item["ready"],
                "unique_fresh_actionable_strict": fresh_lens_item["unique_actionable_strict"],
                "fresh_execution_ready_actionable_strict": fresh_lens_item[
                    "execution_ready_actionable_strict"
                ],
                "fresh_top_execution_ready_actionable_strict": fresh_lens_item[
                    "top_execution_ready_actionable_strict"
                ],
                "fresh_execution_priority_gap": fresh_lens_item["execution_priority_gap"],
                "fresh_reasons": fresh_lens_item["reasons"],
            }
            if lens_item["ready"]:
                category_lens_aligned += 1
            else:
                category_lens_gaps.append(lens_item)
            if fresh_lens_item["ready"]:
                fresh_category_lens_aligned += 1
            else:
                fresh_category_lens_gaps.append(fresh_lens_item)

        by_category[category] = {
            **category_item,
            "fresh_ready": fresh_category_item["ready"],
            "unique_fresh_actionable_strict": fresh_category_item["unique_actionable_strict"],
            "fresh_execution_ready_actionable_strict": fresh_category_item[
                "execution_ready_actionable_strict"
            ],
            "fresh_top_execution_ready_actionable_strict": fresh_category_item[
                "top_execution_ready_actionable_strict"
            ],
            "fresh_execution_priority_gap": fresh_category_item["execution_priority_gap"],
            "fresh_reasons": fresh_category_item["reasons"],
            "lenses": lens_items,
            "ready_lens_count": sum(1 for item in lens_items.values() if item.get("ready")),
            "fresh_ready_lens_count": sum(1 for item in lens_items.values() if item.get("fresh_ready")),
            "lens_count": len(lens_items),
            "lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("ready")),
                len(lens_items),
            ),
            "fresh_lens_ready_rate": LaneStats._rate(
                sum(1 for item in lens_items.values() if item.get("fresh_ready")),
                len(lens_items),
            ),
        }

    def gap_key(item: Dict[str, Any]) -> tuple:
        unique_count = int(item.get("unique_actionable_strict") or 0)
        ready_count = int(item.get("execution_ready_actionable_strict") or 0)
        priority_gap = int(item.get("execution_priority_gap") or 0)
        buried = "execution_ready_buried" in set(item.get("reasons") or []) or "fresh_execution_ready_buried" in set(
            item.get("reasons") or []
        )
        no_inventory = unique_count == 0
        return (
            0 if buried else (1 if ready_count else (3 if no_inventory else 2)),
            _category_priority_sort_key(item.get("category")),
            _lens_priority_sort_key(item.get("lens")),
            -priority_gap,
            int(item.get("top_execution_ready_actionable_strict") or 0),
            int(item.get("highest_execution_ready_rank") or 9999),
        )

    category_gaps.sort(key=gap_key)
    category_lens_gaps.sort(key=gap_key)
    priority_gaps = category_gaps + category_lens_gaps
    priority_gaps.sort(key=gap_key)
    fresh_category_gaps.sort(key=gap_key)
    fresh_category_lens_gaps.sort(key=gap_key)
    fresh_priority_gaps = fresh_category_gaps + fresh_category_lens_gaps
    fresh_priority_gaps.sort(key=gap_key)
    target_categories = len(focus_categories)
    target_category_lenses = len(focus_categories) * len(lenses)
    return {
        "targets": {
            "category_execution_ready_top_ranked": category_target,
            "category_lens_execution_ready_top_ranked": category_lens_target,
            "category_top_window": category_top_window,
            "category_lens_top_window": category_lens_top_window,
        },
        "overall": {
            "target_categories": target_categories,
            "priority_aligned_categories": category_aligned,
            "category_priority_alignment_rate": LaneStats._rate(category_aligned, target_categories),
            "fresh_priority_aligned_categories": fresh_category_aligned,
            "fresh_category_priority_alignment_rate": LaneStats._rate(fresh_category_aligned, target_categories),
            "target_category_lenses": target_category_lenses,
            "priority_aligned_category_lenses": category_lens_aligned,
            "category_lens_priority_alignment_rate": LaneStats._rate(
                category_lens_aligned,
                target_category_lenses,
            ),
            "fresh_priority_aligned_category_lenses": fresh_category_lens_aligned,
            "fresh_category_lens_priority_alignment_rate": LaneStats._rate(
                fresh_category_lens_aligned,
                target_category_lenses,
            ),
        },
        "by_category": by_category,
        "category_gaps": category_gaps,
        "category_lens_gaps": category_lens_gaps,
        "priority_gaps": priority_gaps[:10],
        "fresh_category_gaps": fresh_category_gaps,
        "fresh_category_lens_gaps": fresh_category_lens_gaps,
        "fresh_priority_gaps": fresh_priority_gaps[:10],
        "counts": {
            "category_gaps": len(category_gaps),
            "category_lens_gaps": len(category_lens_gaps),
            "fresh_category_gaps": len(fresh_category_gaps),
            "fresh_category_lens_gaps": len(fresh_category_lens_gaps),
        },
    }


def _platform_surface_reasons(
    metrics: Dict[str, Any],
    *,
    min_lane_total: int,
) -> List[str]:
    if int(metrics.get("total") or 0) < max(1, int(min_lane_total or 1)):
        return []
    reasons: List[str] = []
    if float(metrics.get("survival_rate") or 0.0) < 0.20:
        reasons.append("low_platform_survival")
    if float(metrics.get("strict_fit_rate") or 0.0) < 0.12:
        reasons.append("low_platform_strict_fit")
    if int(metrics.get("lost") or 0) and float(metrics.get("loss_rate") or 0.0) >= 0.70:
        reasons.append("high_platform_loss")
    if (
        int(metrics.get("content_category_observed") or 0) >= max(3, int(min_lane_total or 1))
        and float(metrics.get("content_category_mismatch_rate") or 0.0) > 0.10
    ):
        reasons.append("high_platform_content_mismatch")
    if (
        int(metrics.get("lens_surface_checked") or 0) >= max(3, int(min_lane_total or 1))
        and float(metrics.get("lens_surface_mismatch_rate") or 0.0) > 0.35
    ):
        reasons.append("high_platform_lens_mismatch")
    return reasons


def _platform_surface_quality(
    *,
    platform_summary: Dict[str, Dict[str, Any]],
    platform_category_summary: Dict[str, Dict[str, Any]],
    min_lane_total: int,
    limit: int = 25,
) -> Dict[str, Any]:
    """Find platform surfaces that fail to yield usable posts for focus axes."""
    hotspots: List[Dict[str, Any]] = []
    focus_categories = set(_priority_focus_categories())

    for platform, metrics in platform_summary.items():
        reasons = _platform_surface_reasons(metrics, min_lane_total=min_lane_total)
        if not reasons:
            continue
        hotspots.append({
            "type": "platform",
            "lane": platform,
            "platform": platform,
            "category": "",
            "total": int(metrics.get("total") or 0),
            "lost": int(metrics.get("lost") or 0),
            "survived": int(metrics.get("survived") or 0),
            "strict_fit": int(metrics.get("strict_fit") or 0),
            "loss_rate": float(metrics.get("loss_rate") or 0.0),
            "survival_rate": float(metrics.get("survival_rate") or 0.0),
            "strict_fit_rate": float(metrics.get("strict_fit_rate") or 0.0),
            "content_category_mismatch_rate": float(metrics.get("content_category_mismatch_rate") or 0.0),
            "lens_surface_mismatch_rate": float(metrics.get("lens_surface_mismatch_rate") or 0.0),
            "dominant_loss_reason": metrics.get("dominant_loss_reason") or "",
            "loss_reason_counts": metrics.get("loss_reason_counts", {}),
            "reasons": reasons,
        })

    for lane, metrics in platform_category_summary.items():
        platform, _, category = str(lane or "").partition("::")
        reasons = _platform_surface_reasons(metrics, min_lane_total=min_lane_total)
        if not reasons:
            continue
        normalized_category = ACTIVE_KEYWORD_PROFILE.normalize_category(category)
        hotspot = {
            "type": "platform_category",
            "lane": lane,
            "platform": platform,
            "category": category,
            "total": int(metrics.get("total") or 0),
            "lost": int(metrics.get("lost") or 0),
            "survived": int(metrics.get("survived") or 0),
            "strict_fit": int(metrics.get("strict_fit") or 0),
            "loss_rate": float(metrics.get("loss_rate") or 0.0),
            "survival_rate": float(metrics.get("survival_rate") or 0.0),
            "strict_fit_rate": float(metrics.get("strict_fit_rate") or 0.0),
            "content_category_mismatch_rate": float(metrics.get("content_category_mismatch_rate") or 0.0),
            "lens_surface_mismatch_rate": float(metrics.get("lens_surface_mismatch_rate") or 0.0),
            "dominant_loss_reason": metrics.get("dominant_loss_reason") or "",
            "loss_reason_counts": metrics.get("loss_reason_counts", {}),
            "reasons": reasons,
        }
        if normalized_category in focus_categories:
            hotspot["focus_category"] = normalized_category
        hotspots.append(hotspot)

    def hotspot_key(item: Dict[str, Any]) -> tuple:
        has_focus = bool(item.get("focus_category"))
        category = item.get("category") or ""
        platform = item.get("platform") or ""
        return (
            0 if has_focus else 1,
            _category_priority_sort_key(category),
            _platform_priority_sort_key(platform),
            float(item.get("strict_fit_rate") or 0.0),
            float(item.get("survival_rate") or 0.0),
            -float(item.get("loss_rate") or 0.0),
            -int(item.get("total") or 0),
        )

    hotspots.sort(key=hotspot_key)
    priority_focus_hotspots = [
        item for item in hotspots
        if item.get("focus_category") in focus_categories
    ][:10]

    return {
        "hotspots": hotspots[: max(0, int(limit or 0))],
        "priority_focus_hotspots": priority_focus_hotspots,
        "counts": {
            "hotspots": len(hotspots),
            "priority_focus_hotspots": len(priority_focus_hotspots),
        },
    }


def _priority_focus_weak_lanes(
    weak_lanes: List[Dict[str, Any]],
    *,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Return weak lanes that affect Gyulim's signature treatment axes first."""
    lane_type_order = {
        "category": 0,
        "category_lens": 1,
        "query_variant": 2,
    }
    focus_lanes: List[Dict[str, Any]] = []
    for lane in weak_lanes:
        focus_category = _focus_category_for_weak_lane(lane)
        if not focus_category:
            continue
        enriched = dict(lane)
        enriched["focus_category"] = focus_category
        focus_lanes.append(enriched)

    focus_lanes.sort(
        key=lambda lane: (
            _category_priority_sort_key(lane.get("focus_category")),
            lane_type_order.get(str(lane.get("type") or ""), 9),
            _lens_priority_sort_key(str(lane.get("lane") or "").partition("::")[2]),
            float(lane.get("strict_fit_rate") or 0.0),
            float(lane.get("survival_rate") or 0.0),
            -int(lane.get("total") or 0),
        )
    )
    return focus_lanes[: max(0, int(limit or 0))]


def _weak_source_seeds(
    source_seed_summary: Dict[str, Dict[str, Any]],
    *,
    min_lane_total: int,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    weak: List[Dict[str, Any]] = []
    for seed, metrics in source_seed_summary.items():
        reasons = _weak_lane_reasons(metrics, min_lane_total=min_lane_total)
        if not reasons:
            continue
        weak.append({
            "seed": seed,
            "category": metrics.get("category") or "",
            "total": metrics.get("total", 0),
            "credit_total": metrics.get("credit_total", metrics.get("total", 0)),
            "primary_total": metrics.get("primary_total", 0),
            "assist_total": metrics.get("assist_total", 0),
            "survival_rate": metrics.get("survival_rate", 0.0),
            "strict_fit_rate": metrics.get("strict_fit_rate", 0.0),
            "avg_axis_fit": metrics.get("avg_axis_fit", 0.0),
            "avg_lens_fit": metrics.get("avg_lens_fit", 0.0),
            "query_variant_counts": metrics.get("query_variant_counts", {}),
            "status_counts": metrics.get("status_counts", {}),
            "reasons": reasons,
        })
    weak.sort(
        key=lambda item: (
            _category_priority_sort_key(item.get("category")),
            0 if int(item.get("primary_total") or 0) > 0 else 1,
            float(item.get("strict_fit_rate") or 0.0),
            float(item.get("survival_rate") or 0.0),
            -int(item.get("primary_total") or 0),
            -int(item.get("credit_total") or item.get("total") or 0),
            str(item.get("seed") or ""),
        )
    )
    return weak[: max(0, int(limit or 0))]


def _source_seed_feedback(
    source_seed_summary: Dict[str, Dict[str, Any]],
    *,
    limit: int = 10,
) -> Dict[str, Any]:
    """Classify source seeds into actionable Pathfinder feedback buckets."""
    recategorize_candidates: List[Dict[str, Any]] = []
    scale_candidates: List[Dict[str, Any]] = []
    repair_candidates: List[Dict[str, Any]] = []
    retire_candidates: List[Dict[str, Any]] = []
    assist_only_candidates: List[Dict[str, Any]] = []

    for seed, metrics in source_seed_summary.items():
        category = str(metrics.get("category") or "")
        credit_total = int(metrics.get("credit_total") or metrics.get("total") or 0)
        primary_total = int(metrics.get("primary_total") or 0)
        assist_total = int(metrics.get("assist_total") or 0)
        strict_fit = int(metrics.get("strict_fit") or 0)
        actionable = int(metrics.get("actionable") or 0)
        survived = int(metrics.get("survived") or 0)
        survival_rate = float(metrics.get("survival_rate") or 0.0)
        strict_fit_rate = float(metrics.get("strict_fit_rate") or 0.0)
        detected_category = str(metrics.get("detected_category") or "")
        category_drift_count = int(metrics.get("category_drift_count") or 0)
        category_drift_rate = float(metrics.get("category_drift_rate") or 0.0)
        dominant_category_drift = bool(metrics.get("dominant_category_drift"))
        base = {
            "seed": seed,
            "category": category,
            "detected_category": detected_category,
            "category_counts": metrics.get("category_counts", {}),
            "detected_category_counts": metrics.get("detected_category_counts", {}),
            "credit_total": credit_total,
            "primary_total": primary_total,
            "assist_total": assist_total,
            "actionable": actionable,
            "survived": survived,
            "strict_fit": strict_fit,
            "survival_rate": survival_rate,
            "strict_fit_rate": strict_fit_rate,
            "category_drift_count": category_drift_count,
            "category_drift_rate": category_drift_rate,
            "category_drift": bool(category_drift_count),
            "dominant_category_drift": dominant_category_drift,
            "query_variant_counts": metrics.get("query_variant_counts", {}),
        }

        assist_only = primary_total == 0 and assist_total > 0

        if dominant_category_drift and not assist_only:
            recategorize_candidates.append({
                **base,
                "action": "recategorize_or_quarantine",
                "why": "source seed text maps to a different treatment axis than its handoff category",
            })
        if primary_total > 0 and (strict_fit > 0 or actionable > 0):
            scale_candidates.append({
                **base,
                "action": "scale_or_keep",
                "why": "primary seed produced actionable or strict-fit targets",
            })
        if primary_total >= 8 and (strict_fit_rate < 0.02 or survival_rate < 0.08):
            repair_candidates.append({
                **base,
                "action": "repair_query_shape",
                "why": "primary seed generated volume but weak survival/strict-fit yield",
            })
        if primary_total >= 20 and survived == 0 and strict_fit == 0:
            retire_candidates.append({
                **base,
                "action": "retire_or_pause",
                "why": "primary seed has enough evidence with zero survived/strict-fit targets",
            })
        if assist_only:
            assist_only_candidates.append({
                **base,
                "action": "merge_or_keep_as_companion",
                "why": "seed contributes only as merged duplicate lineage, not as primary discovery",
            })

    def category_key(item: Dict[str, Any]) -> tuple:
        return _category_priority_sort_key(item.get("category"))

    recategorize_candidates.sort(
        key=lambda item: (
            _category_priority_sort_key(item.get("category")),
            0 if int(item.get("primary_total") or 0) > 0 else 1,
            -float(item.get("category_drift_rate") or 0.0),
            -int(item.get("category_drift_count") or 0),
            -int(item.get("primary_total") or 0),
            str(item.get("seed") or ""),
        )
    )
    scale_candidates.sort(
        key=lambda item: (
            category_key(item),
            -int(item.get("strict_fit") or 0),
            -int(item.get("actionable") or 0),
            -float(item.get("strict_fit_rate") or 0.0),
            -int(item.get("primary_total") or 0),
        )
    )
    repair_candidates.sort(
        key=lambda item: (
            category_key(item),
            float(item.get("strict_fit_rate") or 0.0),
            float(item.get("survival_rate") or 0.0),
            -int(item.get("primary_total") or 0),
        )
    )
    retire_candidates.sort(
        key=lambda item: (
            category_key(item),
            -int(item.get("primary_total") or 0),
            str(item.get("seed") or ""),
        )
    )
    assist_only_candidates.sort(
        key=lambda item: (
            category_key(item),
            -int(item.get("assist_total") or 0),
            str(item.get("seed") or ""),
        )
    )

    return {
        "recategorize_candidates": recategorize_candidates[:limit],
        "scale_candidates": scale_candidates[:limit],
        "repair_candidates": repair_candidates[:limit],
        "retire_candidates": retire_candidates[:limit],
        "assist_only_candidates": assist_only_candidates[:limit],
        "counts": {
            "recategorize_candidates": len(recategorize_candidates),
            "scale_candidates": len(scale_candidates),
            "repair_candidates": len(repair_candidates),
            "retire_candidates": len(retire_candidates),
            "assist_only_candidates": len(assist_only_candidates),
        },
    }


def _variant_quality_feedback(
    query_variant_summary: Dict[str, Dict[str, Any]],
    variant_family_summary: Dict[str, Dict[str, Any]],
    *,
    category_lens_query_variant_summary: Optional[Dict[str, Dict[str, Any]]] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Classify query variants into actionable discovery-quality feedback buckets."""
    scale_variants: List[Dict[str, Any]] = []
    repair_variants: List[Dict[str, Any]] = []
    retire_variants: List[Dict[str, Any]] = []
    scale_category_lens_variants: List[Dict[str, Any]] = []
    repair_category_lens_variants: List[Dict[str, Any]] = []
    retire_category_lens_variants: List[Dict[str, Any]] = []
    scale_families: List[Dict[str, Any]] = []
    repair_families: List[Dict[str, Any]] = []
    retire_families: List[Dict[str, Any]] = []

    protected_variants = {"", "base", "(none)", "community_base"}
    protected_families = {"base", "community_base"}

    def base_entry(kind: str, name: str, metrics: Dict[str, Any]) -> Dict[str, Any]:
        total = int(metrics.get("total") or 0)
        lost = int(metrics.get("lost") or 0)
        entry = {
            "type": kind,
            "total": total,
            "survived": int(metrics.get("survived") or 0),
            "actionable": int(metrics.get("actionable") or 0),
            "strict_fit": int(metrics.get("strict_fit") or 0),
            "actionable_strict": int(metrics.get("actionable_strict") or 0),
            "fresh_actionable_strict": int(metrics.get("fresh_actionable_strict") or 0),
            "survival_rate": float(metrics.get("survival_rate") or 0.0),
            "strict_fit_rate": float(metrics.get("strict_fit_rate") or 0.0),
            "actionable_strict_rate": float(metrics.get("actionable_strict_rate") or 0.0),
            "fresh_actionable_strict_rate": float(metrics.get("fresh_actionable_strict_rate") or 0.0),
            "loss_rate": float(metrics.get("loss_rate") or LaneStats._rate(lost, total)),
            "dominant_loss_reason": str(metrics.get("dominant_loss_reason") or ""),
            "status_counts": metrics.get("status_counts", {}),
            "loss_reason_counts": metrics.get("loss_reason_counts", {}),
            "lens_counts": metrics.get("lens_counts", {}),
            "grade_counts": metrics.get("grade_counts", {}),
        }
        if kind == "query_variant":
            entry["variant"] = name
            entry["variant_family"] = _variant_family(name)
        elif kind == "category_lens_query_variant":
            category, _, rest = name.partition("::")
            lens, _, variant = rest.partition("::")
            entry["category"] = category
            entry["lens"] = lens or "service"
            entry["category_lens"] = f"{category}::{lens or 'service'}"
            entry["variant"] = variant
            entry["variant_family"] = _variant_family(variant)
        else:
            entry["family"] = name
        return entry

    def with_action(entry: Dict[str, Any], action: str, why: str) -> Dict[str, Any]:
        return {
            **entry,
            "action": action,
            "why": why,
        }

    def scale_supported(entry: Dict[str, Any], *, small_total: int) -> bool:
        total = int(entry["total"])
        strict_fit = int(entry["strict_fit"])
        actionable_strict = int(entry["actionable_strict"])
        strict_fit_rate = float(entry["strict_fit_rate"])
        actionable_strict_rate = float(entry["actionable_strict_rate"])
        if strict_fit <= 0 and actionable_strict <= 0:
            return False
        if total < small_total:
            return True
        if total < 80:
            return (
                (actionable_strict >= 2 and actionable_strict_rate >= 0.02)
                or (strict_fit >= 3 and strict_fit_rate >= 0.05)
            )
        return (
            actionable_strict >= 3
            and actionable_strict_rate >= 0.015
            and strict_fit_rate >= 0.02
        )

    for variant, metrics in query_variant_summary.items():
        entry = base_entry("query_variant", variant, metrics)
        total = int(entry["total"])
        survived = int(entry["survived"])
        strict_fit = int(entry["strict_fit"])
        survival_rate = float(entry["survival_rate"])
        strict_fit_rate = float(entry["strict_fit_rate"])
        protected = variant in protected_variants

        if total >= 3 and scale_supported(entry, small_total=30):
            scale_variants.append(with_action(
                entry,
                "scale_or_keep",
                "query variant produced enough strict-fit/actionable-strict yield",
            ))
        if total >= 8 and (strict_fit_rate < 0.02 or survival_rate < 0.08):
            repair_variants.append(with_action(
                entry,
                "repair_query_shape",
                "query variant generated volume but weak survival/strict-fit yield",
            ))
        if not protected and total >= 20 and survived == 0 and strict_fit == 0:
            retire_variants.append(with_action(
                entry,
                "retire_or_pause",
                "query variant has enough evidence with zero survived/strict-fit targets",
            ))

    for lane_variant, metrics in (category_lens_query_variant_summary or {}).items():
        entry = base_entry("category_lens_query_variant", lane_variant, metrics)
        total = int(entry["total"])
        survived = int(entry["survived"])
        strict_fit = int(entry["strict_fit"])
        survival_rate = float(entry["survival_rate"])
        strict_fit_rate = float(entry["strict_fit_rate"])
        variant = str(entry.get("variant") or "")
        protected = variant in protected_variants

        if total >= 3 and scale_supported(entry, small_total=30):
            scale_category_lens_variants.append(with_action(
                entry,
                "scale_or_keep",
                "category/lens query variant produced enough strict-fit/actionable-strict yield",
            ))
        if total >= 8 and (strict_fit_rate < 0.02 or survival_rate < 0.08):
            repair_category_lens_variants.append(with_action(
                entry,
                "repair_query_shape",
                "category/lens query variant generated volume but weak survival/strict-fit yield",
            ))
        if not protected and total >= 20 and survived == 0 and strict_fit == 0:
            retire_category_lens_variants.append(with_action(
                entry,
                "retire_or_pause",
                "category/lens query variant has enough evidence with zero survived/strict-fit targets",
            ))

    for family, metrics in variant_family_summary.items():
        entry = base_entry("variant_family", family, metrics)
        total = int(entry["total"])
        survived = int(entry["survived"])
        strict_fit = int(entry["strict_fit"])
        survival_rate = float(entry["survival_rate"])
        strict_fit_rate = float(entry["strict_fit_rate"])
        protected = family in protected_families

        if total >= 5 and scale_supported(entry, small_total=40):
            scale_families.append(with_action(
                entry,
                "scale_or_keep",
                "variant family produced enough strict-fit/actionable-strict yield",
            ))
        if total >= 15 and (strict_fit_rate < 0.02 or survival_rate < 0.08):
            repair_families.append(with_action(
                entry,
                "repair_family_query_shape",
                "variant family generated volume but weak survival/strict-fit yield",
            ))
        if not protected and total >= 60 and survived == 0 and strict_fit == 0:
            retire_families.append(with_action(
                entry,
                "retire_family_or_pause",
                "variant family has enough evidence with zero survived/strict-fit targets",
            ))

    scale_variants.sort(
        key=lambda item: (
            -int(item.get("strict_fit") or 0),
            -int(item.get("actionable_strict") or 0),
            -float(item.get("strict_fit_rate") or 0.0),
            -int(item.get("total") or 0),
            str(item.get("variant") or ""),
        )
    )
    repair_variants.sort(
        key=lambda item: (
            float(item.get("strict_fit_rate") or 0.0),
            float(item.get("survival_rate") or 0.0),
            -int(item.get("total") or 0),
            str(item.get("variant") or ""),
        )
    )
    retire_variants.sort(
        key=lambda item: (
            -int(item.get("total") or 0),
            str(item.get("variant") or ""),
        )
    )
    scale_category_lens_variants.sort(
        key=lambda item: (
            -int(item.get("strict_fit") or 0),
            -int(item.get("actionable_strict") or 0),
            -float(item.get("strict_fit_rate") or 0.0),
            -int(item.get("total") or 0),
            str(item.get("category_lens") or ""),
            str(item.get("variant") or ""),
        )
    )
    repair_category_lens_variants.sort(
        key=lambda item: (
            float(item.get("strict_fit_rate") or 0.0),
            float(item.get("survival_rate") or 0.0),
            -int(item.get("total") or 0),
            str(item.get("category_lens") or ""),
            str(item.get("variant") or ""),
        )
    )
    retire_category_lens_variants.sort(
        key=lambda item: (
            -int(item.get("total") or 0),
            str(item.get("category_lens") or ""),
            str(item.get("variant") or ""),
        )
    )
    scale_families.sort(
        key=lambda item: (
            -int(item.get("strict_fit") or 0),
            -int(item.get("actionable_strict") or 0),
            -float(item.get("strict_fit_rate") or 0.0),
            -int(item.get("total") or 0),
            str(item.get("family") or ""),
        )
    )
    repair_families.sort(
        key=lambda item: (
            float(item.get("strict_fit_rate") or 0.0),
            float(item.get("survival_rate") or 0.0),
            -int(item.get("total") or 0),
            str(item.get("family") or ""),
        )
    )
    retire_families.sort(
        key=lambda item: (
            -int(item.get("total") or 0),
            str(item.get("family") or ""),
        )
    )

    return {
        "scale_variants": scale_variants[:limit],
        "repair_variants": repair_variants[:limit],
        "retire_variants": retire_variants[:limit],
        "scale_category_lens_variants": scale_category_lens_variants[:limit],
        "repair_category_lens_variants": repair_category_lens_variants[:limit],
        "retire_category_lens_variants": retire_category_lens_variants[:limit],
        "scale_families": scale_families[:limit],
        "repair_families": repair_families[:limit],
        "retire_families": retire_families[:limit],
        "counts": {
            "scale_variants": len(scale_variants),
            "repair_variants": len(repair_variants),
            "retire_variants": len(retire_variants),
            "scale_category_lens_variants": len(scale_category_lens_variants),
            "repair_category_lens_variants": len(repair_category_lens_variants),
            "retire_category_lens_variants": len(retire_category_lens_variants),
            "scale_families": len(scale_families),
            "repair_families": len(repair_families),
            "retire_families": len(retire_families),
        },
    }


def _metrics_rate(metrics: Dict[str, Any], key: str) -> float:
    try:
        return float((metrics or {}).get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _completion(value: float, target: float) -> float:
    if target <= 0:
        return 1.0
    return max(0.0, min(1.0, float(value or 0.0) / target))


def _gate(name: str, passed: bool, *, actual: Any, target: Any, required: bool = True) -> Dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "actual": actual,
        "target": target,
        "required": bool(required),
    }


def _handoff_quality_bar(
    *,
    overall: Dict[str, Any],
    category_summary: Dict[str, Dict[str, Any]],
    variant_family_summary: Dict[str, Dict[str, Any]],
    weak_lanes: List[Dict[str, Any]],
    source_seed_feedback: Optional[Dict[str, Any]] = None,
    patient_journey_coverage: Optional[Dict[str, Any]] = None,
    work_queue_readiness: Optional[Dict[str, Any]] = None,
    opportunity_diversity: Optional[Dict[str, Any]] = None,
    engagement_hook_quality: Optional[Dict[str, Any]] = None,
    treatment_signature_quality: Optional[Dict[str, Any]] = None,
    treatment_signal_diversity_quality: Optional[Dict[str, Any]] = None,
    treatment_subintent_diversity_quality: Optional[Dict[str, Any]] = None,
    clinic_modality_quality: Optional[Dict[str, Any]] = None,
    decision_window_quality: Optional[Dict[str, Any]] = None,
    seed_candidate_alignment_quality: Optional[Dict[str, Any]] = None,
    local_intent_quality: Optional[Dict[str, Any]] = None,
    local_area_diversity_quality: Optional[Dict[str, Any]] = None,
    patient_surface_quality: Optional[Dict[str, Any]] = None,
    viral_action_route_quality: Optional[Dict[str, Any]] = None,
    reply_workability_quality: Optional[Dict[str, Any]] = None,
    compliance_work_mode_quality: Optional[Dict[str, Any]] = None,
    execution_readiness_quality: Optional[Dict[str, Any]] = None,
    execution_priority_alignment_quality: Optional[Dict[str, Any]] = None,
    platform_surface_quality: Optional[Dict[str, Any]] = None,
    source_lineage_quality: Optional[Dict[str, Any]] = None,
    reanalysis_rescue_quality: Optional[Dict[str, Any]] = None,
    discarded_execution_rescue_quality: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """World-class readiness gate for the Pathfinder -> Viral Hunter handoff.

    The normal lane tables are diagnostic; this aggregates the few properties that
    decide whether the system is safe to scale: current scoring coverage, usable
    target yield, priority treatment-axis coverage, and patient-surface health.
    """
    focus_categories = _priority_focus_categories()
    focus_discovered = [
        category for category in focus_categories
        if int((category_summary.get(category) or {}).get("total") or 0) > 0
    ]
    focus_survived = [
        category for category in focus_categories
        if int((category_summary.get(category) or {}).get("survived") or 0) > 0
    ]
    focus_strict = [
        category for category in focus_categories
        if int((category_summary.get(category) or {}).get("strict_fit") or 0) > 0
    ]
    focus_total = len(focus_categories)
    focus_discovery_rate = round(len(focus_discovered) / focus_total, 4) if focus_total else 0.0
    focus_survival_rate = round(len(focus_survived) / focus_total, 4) if focus_total else 0.0
    focus_strict_rate = round(len(focus_strict) / focus_total, 4) if focus_total else 0.0

    axis_metric_coverage = _metrics_rate(overall, "axis_coverage_rate")
    lens_metric_coverage = _metrics_rate(overall, "lens_coverage_rate")
    clinic_fit_metric_coverage = _metrics_rate(overall, "clinic_fit_coverage_rate")
    worksite_efficiency_metric_coverage = _metrics_rate(overall, "worksite_efficiency_coverage_rate")
    metric_coverage = min(
        axis_metric_coverage,
        lens_metric_coverage,
        clinic_fit_metric_coverage,
        worksite_efficiency_metric_coverage,
    )
    survival_rate = _metrics_rate(overall, "survival_rate")
    strict_fit_rate = _metrics_rate(overall, "strict_fit_rate")
    actionable_rate = _metrics_rate(overall, "actionable_rate")
    source_seed_feedback = source_seed_feedback or {}
    source_seed_counts = source_seed_feedback.get("counts") or {}
    source_seed_category_drift = int(source_seed_counts.get("recategorize_candidates") or 0)
    row_total = int(overall.get("total") or 0)
    source_lineage_quality = source_lineage_quality or {}
    source_lineage_overall = source_lineage_quality.get("overall") or {}
    source_lineage_targets = source_lineage_quality.get("targets") or {}
    source_lineage_seed_rate = _metrics_rate(source_lineage_overall, "source_seed_coverage_rate")
    source_lineage_priority_seed_rate = _metrics_rate(
        source_lineage_overall,
        "priority_focus_source_seed_coverage_rate",
    )
    source_lineage_actionable_seed_rate = _metrics_rate(
        source_lineage_overall,
        "actionable_strict_source_seed_coverage_rate",
    )
    source_lineage_priority_actionable_seed_rate = _metrics_rate(
        source_lineage_overall,
        "priority_focus_actionable_strict_source_seed_coverage_rate",
    )
    source_lineage_query_variant_rate = _metrics_rate(
        source_lineage_overall,
        "query_variant_coverage_rate",
    )
    source_lineage_priority_total = int(source_lineage_overall.get("priority_focus_total") or 0)
    source_lineage_actionable_total = int(source_lineage_overall.get("actionable_strict_total") or 0)
    source_lineage_priority_actionable_total = int(
        source_lineage_overall.get("priority_focus_actionable_strict_total") or 0
    )
    source_lineage_seed_target = float(
        source_lineage_targets.get("source_seed_coverage_rate")
        or SOURCE_LINEAGE_MIN_SOURCE_SEED_COVERAGE
    )
    source_lineage_priority_seed_target = float(
        source_lineage_targets.get("priority_focus_source_seed_coverage_rate")
        or SOURCE_LINEAGE_MIN_PRIORITY_FOCUS_SOURCE_SEED_COVERAGE
    )
    source_lineage_actionable_seed_target = float(
        source_lineage_targets.get("actionable_strict_source_seed_coverage_rate")
        or SOURCE_LINEAGE_MIN_ACTIONABLE_STRICT_SOURCE_SEED_COVERAGE
    )
    source_lineage_query_variant_target = float(
        source_lineage_targets.get("query_variant_coverage_rate")
        or SOURCE_LINEAGE_MIN_QUERY_VARIANT_COVERAGE
    )
    source_lineage_seed_rates = [source_lineage_seed_rate]
    if source_lineage_priority_total:
        source_lineage_seed_rates.append(source_lineage_priority_seed_rate)
    if source_lineage_actionable_total:
        source_lineage_seed_rates.append(source_lineage_actionable_seed_rate)
    if source_lineage_priority_actionable_total:
        source_lineage_seed_rates.append(source_lineage_priority_actionable_seed_rate)
    source_lineage_min_seed_rate = min(source_lineage_seed_rates)
    content_category_observed = int(overall.get("content_category_observed") or 0)
    content_category_mismatch_rate = _metrics_rate(overall, "content_category_mismatch_rate")
    lens_surface_checked = int(overall.get("lens_surface_checked") or 0)
    lens_surface_mismatch_rate = _metrics_rate(overall, "lens_surface_mismatch_rate")
    patient_journey_coverage = patient_journey_coverage or {}
    patient_journey_overall = patient_journey_coverage.get("overall") or {}
    patient_journey_target_pairs = int(patient_journey_overall.get("target_pairs") or 0)
    patient_journey_strict_coverage = _metrics_rate(patient_journey_overall, "strict_coverage_rate")
    patient_journey_actionable_strict_coverage = _metrics_rate(
        patient_journey_overall,
        "actionable_strict_coverage_rate",
    )
    work_queue_readiness = work_queue_readiness or {}
    work_queue_overall = work_queue_readiness.get("overall") or {}
    work_queue_category_ready_rate = _metrics_rate(work_queue_overall, "category_ready_rate")
    work_queue_category_lens_ready_rate = _metrics_rate(work_queue_overall, "category_lens_ready_rate")
    fresh_work_queue_category_ready_rate = _metrics_rate(work_queue_overall, "fresh_category_ready_rate")
    fresh_work_queue_category_lens_ready_rate = _metrics_rate(work_queue_overall, "fresh_category_lens_ready_rate")
    unique_work_queue_category_ready_rate = _metrics_rate(work_queue_overall, "unique_category_ready_rate")
    unique_work_queue_category_lens_ready_rate = _metrics_rate(work_queue_overall, "unique_category_lens_ready_rate")
    fresh_unique_work_queue_category_ready_rate = _metrics_rate(
        work_queue_overall,
        "fresh_unique_category_ready_rate",
    )
    fresh_unique_work_queue_category_lens_ready_rate = _metrics_rate(
        work_queue_overall,
        "fresh_unique_category_lens_ready_rate",
    )
    work_queue_target_categories = int(work_queue_overall.get("target_categories") or 0)
    work_queue_target_category_lenses = int(work_queue_overall.get("target_category_lenses") or 0)
    opportunity_diversity = opportunity_diversity or {}
    opportunity_diversity_overall = opportunity_diversity.get("overall") or {}
    diversity_category_ready_rate = _metrics_rate(
        opportunity_diversity_overall,
        "category_diversity_ready_rate",
    )
    diversity_category_lens_ready_rate = _metrics_rate(
        opportunity_diversity_overall,
        "category_lens_diversity_ready_rate",
    )
    fresh_diversity_category_ready_rate = _metrics_rate(
        opportunity_diversity_overall,
        "fresh_category_diversity_ready_rate",
    )
    fresh_diversity_category_lens_ready_rate = _metrics_rate(
        opportunity_diversity_overall,
        "fresh_category_lens_diversity_ready_rate",
    )
    diversity_target_categories = int(opportunity_diversity_overall.get("target_categories") or 0)
    diversity_target_category_lenses = int(opportunity_diversity_overall.get("target_category_lenses") or 0)
    engagement_hook_quality = engagement_hook_quality or {}
    engagement_hook_overall = engagement_hook_quality.get("overall") or {}
    hook_category_ready_rate = _metrics_rate(
        engagement_hook_overall,
        "category_hook_ready_rate",
    )
    hook_category_lens_ready_rate = _metrics_rate(
        engagement_hook_overall,
        "category_lens_hook_ready_rate",
    )
    fresh_hook_category_ready_rate = _metrics_rate(
        engagement_hook_overall,
        "fresh_category_hook_ready_rate",
    )
    fresh_hook_category_lens_ready_rate = _metrics_rate(
        engagement_hook_overall,
        "fresh_category_lens_hook_ready_rate",
    )
    hook_target_categories = int(engagement_hook_overall.get("target_categories") or 0)
    hook_target_category_lenses = int(engagement_hook_overall.get("target_category_lenses") or 0)
    treatment_signature_quality = treatment_signature_quality or {}
    signature_overall = treatment_signature_quality.get("overall") or {}
    signature_category_ready_rate = _metrics_rate(
        signature_overall,
        "category_signature_ready_rate",
    )
    signature_category_lens_ready_rate = _metrics_rate(
        signature_overall,
        "category_lens_signature_ready_rate",
    )
    fresh_signature_category_ready_rate = _metrics_rate(
        signature_overall,
        "fresh_category_signature_ready_rate",
    )
    fresh_signature_category_lens_ready_rate = _metrics_rate(
        signature_overall,
        "fresh_category_lens_signature_ready_rate",
    )
    signature_target_categories = int(signature_overall.get("target_categories") or 0)
    signature_target_category_lenses = int(signature_overall.get("target_category_lenses") or 0)
    treatment_signal_diversity_quality = treatment_signal_diversity_quality or {}
    treatment_signal_diversity_overall = treatment_signal_diversity_quality.get("overall") or {}
    treatment_signal_diversity_category_ready_rate = _metrics_rate(
        treatment_signal_diversity_overall,
        "category_treatment_signal_diverse_ready_rate",
    )
    treatment_signal_diversity_category_lens_ready_rate = _metrics_rate(
        treatment_signal_diversity_overall,
        "category_lens_treatment_signal_diverse_ready_rate",
    )
    fresh_treatment_signal_diversity_category_ready_rate = _metrics_rate(
        treatment_signal_diversity_overall,
        "fresh_category_treatment_signal_diverse_ready_rate",
    )
    fresh_treatment_signal_diversity_category_lens_ready_rate = _metrics_rate(
        treatment_signal_diversity_overall,
        "fresh_category_lens_treatment_signal_diverse_ready_rate",
    )
    treatment_signal_diversity_target_categories = int(
        treatment_signal_diversity_overall.get("target_categories") or 0
    )
    treatment_signal_diversity_target_category_lenses = int(
        treatment_signal_diversity_overall.get("target_category_lenses") or 0
    )
    treatment_subintent_diversity_quality = treatment_subintent_diversity_quality or {}
    treatment_subintent_diversity_overall = treatment_subintent_diversity_quality.get("overall") or {}
    treatment_subintent_diversity_category_ready_rate = _metrics_rate(
        treatment_subintent_diversity_overall,
        "category_treatment_subintent_diverse_ready_rate",
    )
    treatment_subintent_diversity_category_lens_ready_rate = _metrics_rate(
        treatment_subintent_diversity_overall,
        "category_lens_treatment_subintent_diverse_ready_rate",
    )
    fresh_treatment_subintent_diversity_category_ready_rate = _metrics_rate(
        treatment_subintent_diversity_overall,
        "fresh_category_treatment_subintent_diverse_ready_rate",
    )
    fresh_treatment_subintent_diversity_category_lens_ready_rate = _metrics_rate(
        treatment_subintent_diversity_overall,
        "fresh_category_lens_treatment_subintent_diverse_ready_rate",
    )
    treatment_subintent_diversity_target_categories = int(
        treatment_subintent_diversity_overall.get("target_categories") or 0
    )
    treatment_subintent_diversity_target_category_lenses = int(
        treatment_subintent_diversity_overall.get("target_category_lenses") or 0
    )
    clinic_modality_quality = clinic_modality_quality or {}
    clinic_modality_overall = clinic_modality_quality.get("overall") or {}
    clinic_modality_category_ready_rate = _metrics_rate(
        clinic_modality_overall,
        "category_clinic_modality_fit_ready_rate",
    )
    clinic_modality_category_lens_ready_rate = _metrics_rate(
        clinic_modality_overall,
        "category_lens_clinic_modality_fit_ready_rate",
    )
    fresh_clinic_modality_category_ready_rate = _metrics_rate(
        clinic_modality_overall,
        "fresh_category_clinic_modality_fit_ready_rate",
    )
    fresh_clinic_modality_category_lens_ready_rate = _metrics_rate(
        clinic_modality_overall,
        "fresh_category_lens_clinic_modality_fit_ready_rate",
    )
    clinic_modality_target_categories = int(clinic_modality_overall.get("target_categories") or 0)
    clinic_modality_target_category_lenses = int(
        clinic_modality_overall.get("target_category_lenses") or 0
    )
    decision_window_quality = decision_window_quality or {}
    decision_window_overall = decision_window_quality.get("overall") or {}
    decision_window_category_ready_rate = _metrics_rate(
        decision_window_overall,
        "category_active_decision_ready_rate",
    )
    decision_window_category_lens_ready_rate = _metrics_rate(
        decision_window_overall,
        "category_lens_active_decision_ready_rate",
    )
    fresh_decision_window_category_ready_rate = _metrics_rate(
        decision_window_overall,
        "fresh_category_active_decision_ready_rate",
    )
    fresh_decision_window_category_lens_ready_rate = _metrics_rate(
        decision_window_overall,
        "fresh_category_lens_active_decision_ready_rate",
    )
    decision_window_target_categories = int(decision_window_overall.get("target_categories") or 0)
    decision_window_target_category_lenses = int(
        decision_window_overall.get("target_category_lenses") or 0
    )
    seed_candidate_alignment_quality = seed_candidate_alignment_quality or {}
    seed_candidate_alignment_overall = seed_candidate_alignment_quality.get("overall") or {}
    seed_candidate_alignment_category_ready_rate = _metrics_rate(
        seed_candidate_alignment_overall,
        "category_seed_alignment_ready_rate",
    )
    seed_candidate_alignment_category_lens_ready_rate = _metrics_rate(
        seed_candidate_alignment_overall,
        "category_lens_seed_alignment_ready_rate",
    )
    fresh_seed_candidate_alignment_category_ready_rate = _metrics_rate(
        seed_candidate_alignment_overall,
        "fresh_category_seed_alignment_ready_rate",
    )
    fresh_seed_candidate_alignment_category_lens_ready_rate = _metrics_rate(
        seed_candidate_alignment_overall,
        "fresh_category_lens_seed_alignment_ready_rate",
    )
    seed_candidate_alignment_target_categories = int(
        seed_candidate_alignment_overall.get("target_categories") or 0
    )
    seed_candidate_alignment_target_category_lenses = int(
        seed_candidate_alignment_overall.get("target_category_lenses") or 0
    )
    local_intent_quality = local_intent_quality or {}
    local_intent_overall = local_intent_quality.get("overall") or {}
    local_category_ready_rate = _metrics_rate(
        local_intent_overall,
        "category_local_ready_rate",
    )
    local_category_lens_ready_rate = _metrics_rate(
        local_intent_overall,
        "category_lens_local_ready_rate",
    )
    fresh_local_category_ready_rate = _metrics_rate(
        local_intent_overall,
        "fresh_category_local_ready_rate",
    )
    fresh_local_category_lens_ready_rate = _metrics_rate(
        local_intent_overall,
        "fresh_category_lens_local_ready_rate",
    )
    local_target_categories = int(local_intent_overall.get("target_categories") or 0)
    local_target_category_lenses = int(local_intent_overall.get("target_category_lenses") or 0)
    local_area_diversity_quality = local_area_diversity_quality or {}
    local_area_diversity_overall = local_area_diversity_quality.get("overall") or {}
    local_area_category_ready_rate = _metrics_rate(
        local_area_diversity_overall,
        "category_local_area_diversity_ready_rate",
    )
    local_area_category_lens_ready_rate = _metrics_rate(
        local_area_diversity_overall,
        "category_lens_local_area_diversity_ready_rate",
    )
    fresh_local_area_category_ready_rate = _metrics_rate(
        local_area_diversity_overall,
        "fresh_category_local_area_diversity_ready_rate",
    )
    fresh_local_area_category_lens_ready_rate = _metrics_rate(
        local_area_diversity_overall,
        "fresh_category_lens_local_area_diversity_ready_rate",
    )
    local_area_target_categories = int(local_area_diversity_overall.get("target_categories") or 0)
    local_area_target_category_lenses = int(
        local_area_diversity_overall.get("target_category_lenses") or 0
    )
    patient_surface_quality = patient_surface_quality or {}
    patient_surface_overall_quality = patient_surface_quality.get("overall") or {}
    authentic_surface_category_ready_rate = _metrics_rate(
        patient_surface_overall_quality,
        "category_patient_surface_ready_rate",
    )
    authentic_surface_category_lens_ready_rate = _metrics_rate(
        patient_surface_overall_quality,
        "category_lens_patient_surface_ready_rate",
    )
    fresh_authentic_surface_category_ready_rate = _metrics_rate(
        patient_surface_overall_quality,
        "fresh_category_patient_surface_ready_rate",
    )
    fresh_authentic_surface_category_lens_ready_rate = _metrics_rate(
        patient_surface_overall_quality,
        "fresh_category_lens_patient_surface_ready_rate",
    )
    authentic_surface_target_categories = int(patient_surface_overall_quality.get("target_categories") or 0)
    authentic_surface_target_category_lenses = int(
        patient_surface_overall_quality.get("target_category_lenses") or 0
    )
    viral_action_route_quality = viral_action_route_quality or {}
    viral_action_route_overall = viral_action_route_quality.get("overall") or {}
    route_category_ready_rate = _metrics_rate(
        viral_action_route_overall,
        "category_route_ready_rate",
    )
    route_category_lens_ready_rate = _metrics_rate(
        viral_action_route_overall,
        "category_lens_route_ready_rate",
    )
    fresh_route_category_ready_rate = _metrics_rate(
        viral_action_route_overall,
        "fresh_category_route_ready_rate",
    )
    fresh_route_category_lens_ready_rate = _metrics_rate(
        viral_action_route_overall,
        "fresh_category_lens_route_ready_rate",
    )
    route_target_categories = int(viral_action_route_overall.get("target_categories") or 0)
    route_target_category_lenses = int(viral_action_route_overall.get("target_category_lenses") or 0)
    reply_workability_quality = reply_workability_quality or {}
    reply_workability_overall = reply_workability_quality.get("overall") or {}
    reply_workability_category_ready_rate = _metrics_rate(
        reply_workability_overall,
        "category_reply_workable_ready_rate",
    )
    reply_workability_category_lens_ready_rate = _metrics_rate(
        reply_workability_overall,
        "category_lens_reply_workable_ready_rate",
    )
    fresh_reply_workability_category_ready_rate = _metrics_rate(
        reply_workability_overall,
        "fresh_category_reply_workable_ready_rate",
    )
    fresh_reply_workability_category_lens_ready_rate = _metrics_rate(
        reply_workability_overall,
        "fresh_category_lens_reply_workable_ready_rate",
    )
    reply_workability_target_categories = int(reply_workability_overall.get("target_categories") or 0)
    reply_workability_target_category_lenses = int(
        reply_workability_overall.get("target_category_lenses") or 0
    )
    compliance_work_mode_quality = compliance_work_mode_quality or {}
    compliance_work_mode_overall = compliance_work_mode_quality.get("overall") or {}
    compliance_category_ready_rate = _metrics_rate(
        compliance_work_mode_overall,
        "category_auto_work_ready_rate",
    )
    compliance_category_lens_ready_rate = _metrics_rate(
        compliance_work_mode_overall,
        "category_lens_auto_work_ready_rate",
    )
    fresh_compliance_category_ready_rate = _metrics_rate(
        compliance_work_mode_overall,
        "fresh_category_auto_work_ready_rate",
    )
    fresh_compliance_category_lens_ready_rate = _metrics_rate(
        compliance_work_mode_overall,
        "fresh_category_lens_auto_work_ready_rate",
    )
    compliance_target_categories = int(compliance_work_mode_overall.get("target_categories") or 0)
    compliance_target_category_lenses = int(
        compliance_work_mode_overall.get("target_category_lenses") or 0
    )
    execution_readiness_quality = execution_readiness_quality or {}
    execution_readiness_overall = execution_readiness_quality.get("overall") or {}
    execution_readiness_category_ready_rate = _metrics_rate(
        execution_readiness_overall,
        "category_execution_ready_rate",
    )
    execution_readiness_category_lens_ready_rate = _metrics_rate(
        execution_readiness_overall,
        "category_lens_execution_ready_rate",
    )
    fresh_execution_readiness_category_ready_rate = _metrics_rate(
        execution_readiness_overall,
        "fresh_category_execution_ready_rate",
    )
    fresh_execution_readiness_category_lens_ready_rate = _metrics_rate(
        execution_readiness_overall,
        "fresh_category_lens_execution_ready_rate",
    )
    execution_readiness_target_categories = int(execution_readiness_overall.get("target_categories") or 0)
    execution_readiness_target_category_lenses = int(
        execution_readiness_overall.get("target_category_lenses") or 0
    )
    execution_priority_alignment_quality = execution_priority_alignment_quality or {}
    execution_priority_alignment_overall = execution_priority_alignment_quality.get("overall") or {}
    execution_priority_category_alignment_rate = _metrics_rate(
        execution_priority_alignment_overall,
        "category_priority_alignment_rate",
    )
    execution_priority_category_lens_alignment_rate = _metrics_rate(
        execution_priority_alignment_overall,
        "category_lens_priority_alignment_rate",
    )
    fresh_execution_priority_category_alignment_rate = _metrics_rate(
        execution_priority_alignment_overall,
        "fresh_category_priority_alignment_rate",
    )
    fresh_execution_priority_category_lens_alignment_rate = _metrics_rate(
        execution_priority_alignment_overall,
        "fresh_category_lens_priority_alignment_rate",
    )
    execution_priority_target_categories = int(
        execution_priority_alignment_overall.get("target_categories") or 0
    )
    execution_priority_target_category_lenses = int(
        execution_priority_alignment_overall.get("target_category_lenses") or 0
    )
    platform_surface_quality = platform_surface_quality or {}
    platform_surface_counts = platform_surface_quality.get("counts") or {}
    platform_surface_focus_hotspots = int(platform_surface_counts.get("priority_focus_hotspots") or 0)
    reanalysis_rescue_quality = reanalysis_rescue_quality or {}
    reanalysis_rescue_overall = reanalysis_rescue_quality.get("overall") or {}
    reanalysis_rescue_candidates = int(reanalysis_rescue_overall.get("candidate_count") or 0)
    reanalysis_rescue_priority_focus_candidates = int(
        reanalysis_rescue_overall.get("priority_focus_candidate_count") or 0
    )
    discarded_execution_rescue_quality = discarded_execution_rescue_quality or {}
    discarded_execution_rescue_overall = discarded_execution_rescue_quality.get("overall") or {}
    discarded_execution_rescue_candidates = int(
        discarded_execution_rescue_overall.get("candidate_count") or 0
    )
    discarded_execution_rescue_priority_focus_candidates = int(
        discarded_execution_rescue_overall.get("priority_focus_candidate_count") or 0
    )
    discarded_execution_auto_requeue_candidates = int(
        discarded_execution_rescue_overall.get("auto_requeue_candidate_count") or 0
    )
    discarded_execution_manual_review_candidates = int(
        discarded_execution_rescue_overall.get("manual_review_candidate_count") or 0
    )

    patient_voice = variant_family_summary.get("patient_voice") or {}
    axis_specific = variant_family_summary.get("axis_specific") or {}
    axis_companion = variant_family_summary.get("axis_companion") or {}
    patient_surface_total = (
        int(patient_voice.get("total") or 0)
        + int(axis_specific.get("total") or 0)
        + int(axis_companion.get("total") or 0)
    )
    patient_surface_strict = (
        int(patient_voice.get("strict_fit") or 0)
        + int(axis_specific.get("strict_fit") or 0)
        + int(axis_companion.get("strict_fit") or 0)
    )
    patient_surface_survived = (
        int(patient_voice.get("survived") or 0)
        + int(axis_specific.get("survived") or 0)
        + int(axis_companion.get("survived") or 0)
    )
    patient_surface_strict_rate = (
        round(patient_surface_strict / patient_surface_total, 4)
        if patient_surface_total else 0.0
    )
    patient_surface_survival_rate = (
        round(patient_surface_survived / patient_surface_total, 4)
        if patient_surface_total else 0.0
    )

    required_gates = [
        _gate("metric_coverage", metric_coverage >= 0.80, actual=round(metric_coverage, 4), target=0.80),
        _gate("overall_survival", survival_rate >= 0.35, actual=round(survival_rate, 4), target=0.35),
        _gate("overall_strict_fit", strict_fit_rate >= 0.25, actual=round(strict_fit_rate, 4), target=0.25),
        _gate("focus_discovery_coverage", focus_discovery_rate >= 0.90, actual=focus_discovery_rate, target=0.90),
        _gate("focus_strict_coverage", focus_strict_rate >= 0.70, actual=focus_strict_rate, target=0.70),
    ]
    advisory_gates = [
        _gate(
            "patient_surface_survival",
            patient_surface_total == 0 or patient_surface_survival_rate >= 0.20,
            actual=patient_surface_survival_rate,
            target=0.20,
            required=False,
        ),
        _gate(
            "patient_surface_strict_fit",
            patient_surface_total == 0 or patient_surface_strict_rate >= 0.12,
            actual=patient_surface_strict_rate,
            target=0.12,
            required=False,
        ),
        _gate(
            "source_seed_category_drift",
            source_seed_category_drift == 0,
            actual=source_seed_category_drift,
            target=0,
            required=False,
        ),
        _gate(
            "source_lineage_coverage",
            row_total == 0
            or (
                source_lineage_seed_rate >= source_lineage_seed_target
                and (
                    source_lineage_priority_total == 0
                    or source_lineage_priority_seed_rate >= source_lineage_priority_seed_target
                )
                and (
                    source_lineage_actionable_total == 0
                    or source_lineage_actionable_seed_rate >= source_lineage_actionable_seed_target
                )
                and (
                    source_lineage_priority_actionable_total == 0
                    or source_lineage_priority_actionable_seed_rate
                    >= source_lineage_actionable_seed_target
                )
            ),
            actual=round(source_lineage_min_seed_rate, 4),
            target=round(
                min(
                    source_lineage_seed_target,
                    source_lineage_priority_seed_target,
                    source_lineage_actionable_seed_target,
                ),
                4,
            ),
            required=False,
        ),
        _gate(
            "query_variant_lineage_coverage",
            row_total == 0 or source_lineage_query_variant_rate >= source_lineage_query_variant_target,
            actual=round(source_lineage_query_variant_rate, 4),
            target=round(source_lineage_query_variant_target, 4),
            required=False,
        ),
        _gate(
            "content_category_mismatch",
            content_category_observed == 0 or content_category_mismatch_rate <= 0.05,
            actual=round(content_category_mismatch_rate, 4),
            target=0.05,
            required=False,
        ),
        _gate(
            "lens_surface_mismatch",
            lens_surface_checked == 0 or lens_surface_mismatch_rate <= 0.20,
            actual=round(lens_surface_mismatch_rate, 4),
            target=0.20,
            required=False,
        ),
        _gate(
            "patient_journey_strict_coverage",
            patient_journey_target_pairs == 0 or patient_journey_strict_coverage >= 0.45,
            actual=round(patient_journey_strict_coverage, 4),
            target=0.45,
            required=False,
        ),
        _gate(
            "patient_journey_actionable_strict_coverage",
            patient_journey_target_pairs == 0 or patient_journey_actionable_strict_coverage >= 0.35,
            actual=round(patient_journey_actionable_strict_coverage, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "work_queue_category_depth",
            work_queue_target_categories == 0 or work_queue_category_ready_rate >= 0.70,
            actual=round(work_queue_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "work_queue_lens_depth",
            work_queue_target_category_lenses == 0 or work_queue_category_lens_ready_rate >= 0.35,
            actual=round(work_queue_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_work_queue_category_depth",
            work_queue_target_categories == 0 or fresh_work_queue_category_ready_rate >= 0.70,
            actual=round(fresh_work_queue_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_work_queue_lens_depth",
            work_queue_target_category_lenses == 0 or fresh_work_queue_category_lens_ready_rate >= 0.30,
            actual=round(fresh_work_queue_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "unique_work_queue_category_depth",
            work_queue_target_categories == 0 or unique_work_queue_category_ready_rate >= 0.70,
            actual=round(unique_work_queue_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "unique_work_queue_lens_depth",
            work_queue_target_category_lenses == 0 or unique_work_queue_category_lens_ready_rate >= 0.35,
            actual=round(unique_work_queue_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_unique_work_queue_category_depth",
            work_queue_target_categories == 0 or fresh_unique_work_queue_category_ready_rate >= 0.70,
            actual=round(fresh_unique_work_queue_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_unique_work_queue_lens_depth",
            work_queue_target_category_lenses == 0 or fresh_unique_work_queue_category_lens_ready_rate >= 0.30,
            actual=round(fresh_unique_work_queue_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "opportunity_diversity_category_coverage",
            diversity_target_categories == 0 or diversity_category_ready_rate >= 0.70,
            actual=round(diversity_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "opportunity_diversity_lens_coverage",
            diversity_target_category_lenses == 0 or diversity_category_lens_ready_rate >= 0.35,
            actual=round(diversity_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_opportunity_diversity_category_coverage",
            diversity_target_categories == 0 or fresh_diversity_category_ready_rate >= 0.70,
            actual=round(fresh_diversity_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_opportunity_diversity_lens_coverage",
            diversity_target_category_lenses == 0 or fresh_diversity_category_lens_ready_rate >= 0.30,
            actual=round(fresh_diversity_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "engagement_hook_category_coverage",
            hook_target_categories == 0 or hook_category_ready_rate >= 0.70,
            actual=round(hook_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "engagement_hook_lens_coverage",
            hook_target_category_lenses == 0 or hook_category_lens_ready_rate >= 0.35,
            actual=round(hook_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_engagement_hook_category_coverage",
            hook_target_categories == 0 or fresh_hook_category_ready_rate >= 0.70,
            actual=round(fresh_hook_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_engagement_hook_lens_coverage",
            hook_target_category_lenses == 0 or fresh_hook_category_lens_ready_rate >= 0.30,
            actual=round(fresh_hook_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "treatment_signature_category_coverage",
            signature_target_categories == 0 or signature_category_ready_rate >= 0.70,
            actual=round(signature_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "treatment_signature_lens_coverage",
            signature_target_category_lenses == 0 or signature_category_lens_ready_rate >= 0.35,
            actual=round(signature_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_treatment_signature_category_coverage",
            signature_target_categories == 0 or fresh_signature_category_ready_rate >= 0.70,
            actual=round(fresh_signature_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_treatment_signature_lens_coverage",
            signature_target_category_lenses == 0 or fresh_signature_category_lens_ready_rate >= 0.30,
            actual=round(fresh_signature_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "treatment_signal_diversity_category_coverage",
            (
                treatment_signal_diversity_target_categories == 0
                or treatment_signal_diversity_category_ready_rate >= 0.70
            ),
            actual=round(treatment_signal_diversity_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "treatment_signal_diversity_lens_coverage",
            (
                treatment_signal_diversity_target_category_lenses == 0
                or treatment_signal_diversity_category_lens_ready_rate >= 0.35
            ),
            actual=round(treatment_signal_diversity_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_treatment_signal_diversity_category_coverage",
            (
                treatment_signal_diversity_target_categories == 0
                or fresh_treatment_signal_diversity_category_ready_rate >= 0.70
            ),
            actual=round(fresh_treatment_signal_diversity_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_treatment_signal_diversity_lens_coverage",
            (
                treatment_signal_diversity_target_category_lenses == 0
                or fresh_treatment_signal_diversity_category_lens_ready_rate >= 0.30
            ),
            actual=round(fresh_treatment_signal_diversity_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "treatment_subintent_diversity_category_coverage",
            (
                treatment_subintent_diversity_target_categories == 0
                or treatment_subintent_diversity_category_ready_rate >= 0.70
            ),
            actual=round(treatment_subintent_diversity_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "treatment_subintent_diversity_lens_coverage",
            (
                treatment_subintent_diversity_target_category_lenses == 0
                or treatment_subintent_diversity_category_lens_ready_rate >= 0.35
            ),
            actual=round(treatment_subintent_diversity_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_treatment_subintent_diversity_category_coverage",
            (
                treatment_subintent_diversity_target_categories == 0
                or fresh_treatment_subintent_diversity_category_ready_rate >= 0.70
            ),
            actual=round(fresh_treatment_subintent_diversity_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_treatment_subintent_diversity_lens_coverage",
            (
                treatment_subintent_diversity_target_category_lenses == 0
                or fresh_treatment_subintent_diversity_category_lens_ready_rate >= 0.30
            ),
            actual=round(fresh_treatment_subintent_diversity_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "clinic_modality_category_coverage",
            (
                clinic_modality_target_categories == 0
                or clinic_modality_category_ready_rate >= 0.70
            ),
            actual=round(clinic_modality_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "clinic_modality_lens_coverage",
            (
                clinic_modality_target_category_lenses == 0
                or clinic_modality_category_lens_ready_rate >= 0.35
            ),
            actual=round(clinic_modality_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_clinic_modality_category_coverage",
            (
                clinic_modality_target_categories == 0
                or fresh_clinic_modality_category_ready_rate >= 0.70
            ),
            actual=round(fresh_clinic_modality_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_clinic_modality_lens_coverage",
            (
                clinic_modality_target_category_lenses == 0
                or fresh_clinic_modality_category_lens_ready_rate >= 0.30
            ),
            actual=round(fresh_clinic_modality_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "decision_window_category_coverage",
            (
                decision_window_target_categories == 0
                or decision_window_category_ready_rate >= 0.70
            ),
            actual=round(decision_window_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "decision_window_lens_coverage",
            (
                decision_window_target_category_lenses == 0
                or decision_window_category_lens_ready_rate >= 0.35
            ),
            actual=round(decision_window_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_decision_window_category_coverage",
            (
                decision_window_target_categories == 0
                or fresh_decision_window_category_ready_rate >= 0.70
            ),
            actual=round(fresh_decision_window_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_decision_window_lens_coverage",
            (
                decision_window_target_category_lenses == 0
                or fresh_decision_window_category_lens_ready_rate >= 0.30
            ),
            actual=round(fresh_decision_window_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "seed_candidate_alignment_category_coverage",
            (
                seed_candidate_alignment_target_categories == 0
                or seed_candidate_alignment_category_ready_rate >= 0.70
            ),
            actual=round(seed_candidate_alignment_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "seed_candidate_alignment_lens_coverage",
            (
                seed_candidate_alignment_target_category_lenses == 0
                or seed_candidate_alignment_category_lens_ready_rate >= 0.35
            ),
            actual=round(seed_candidate_alignment_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_seed_candidate_alignment_category_coverage",
            (
                seed_candidate_alignment_target_categories == 0
                or fresh_seed_candidate_alignment_category_ready_rate >= 0.70
            ),
            actual=round(fresh_seed_candidate_alignment_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_seed_candidate_alignment_lens_coverage",
            (
                seed_candidate_alignment_target_category_lenses == 0
                or fresh_seed_candidate_alignment_category_lens_ready_rate >= 0.30
            ),
            actual=round(fresh_seed_candidate_alignment_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "local_intent_category_coverage",
            local_target_categories == 0 or local_category_ready_rate >= 0.70,
            actual=round(local_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "local_intent_lens_coverage",
            local_target_category_lenses == 0 or local_category_lens_ready_rate >= 0.35,
            actual=round(local_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_local_intent_category_coverage",
            local_target_categories == 0 or fresh_local_category_ready_rate >= 0.70,
            actual=round(fresh_local_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_local_intent_lens_coverage",
            local_target_category_lenses == 0 or fresh_local_category_lens_ready_rate >= 0.30,
            actual=round(fresh_local_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "local_area_diversity_category_coverage",
            local_area_target_categories == 0 or local_area_category_ready_rate >= 0.70,
            actual=round(local_area_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "local_area_diversity_lens_coverage",
            local_area_target_category_lenses == 0 or local_area_category_lens_ready_rate >= 0.35,
            actual=round(local_area_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_local_area_diversity_category_coverage",
            local_area_target_categories == 0 or fresh_local_area_category_ready_rate >= 0.70,
            actual=round(fresh_local_area_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_local_area_diversity_lens_coverage",
            local_area_target_category_lenses == 0 or fresh_local_area_category_lens_ready_rate >= 0.30,
            actual=round(fresh_local_area_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "patient_surface_authenticity_category_coverage",
            authentic_surface_target_categories == 0 or authentic_surface_category_ready_rate >= 0.70,
            actual=round(authentic_surface_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "patient_surface_authenticity_lens_coverage",
            authentic_surface_target_category_lenses == 0 or authentic_surface_category_lens_ready_rate >= 0.35,
            actual=round(authentic_surface_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_patient_surface_authenticity_category_coverage",
            authentic_surface_target_categories == 0 or fresh_authentic_surface_category_ready_rate >= 0.70,
            actual=round(fresh_authentic_surface_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_patient_surface_authenticity_lens_coverage",
            (
                authentic_surface_target_category_lenses == 0
                or fresh_authentic_surface_category_lens_ready_rate >= 0.30
            ),
            actual=round(fresh_authentic_surface_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "viral_action_route_category_coverage",
            route_target_categories == 0 or route_category_ready_rate >= 0.70,
            actual=round(route_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "viral_action_route_lens_coverage",
            route_target_category_lenses == 0 or route_category_lens_ready_rate >= 0.35,
            actual=round(route_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_viral_action_route_category_coverage",
            route_target_categories == 0 or fresh_route_category_ready_rate >= 0.70,
            actual=round(fresh_route_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_viral_action_route_lens_coverage",
            route_target_category_lenses == 0 or fresh_route_category_lens_ready_rate >= 0.30,
            actual=round(fresh_route_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "reply_workability_category_coverage",
            reply_workability_target_categories == 0 or reply_workability_category_ready_rate >= 0.70,
            actual=round(reply_workability_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "reply_workability_lens_coverage",
            (
                reply_workability_target_category_lenses == 0
                or reply_workability_category_lens_ready_rate >= 0.35
            ),
            actual=round(reply_workability_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_reply_workability_category_coverage",
            (
                reply_workability_target_categories == 0
                or fresh_reply_workability_category_ready_rate >= 0.70
            ),
            actual=round(fresh_reply_workability_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_reply_workability_lens_coverage",
            (
                reply_workability_target_category_lenses == 0
                or fresh_reply_workability_category_lens_ready_rate >= 0.30
            ),
            actual=round(fresh_reply_workability_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "compliance_work_mode_category_coverage",
            compliance_target_categories == 0 or compliance_category_ready_rate >= 0.70,
            actual=round(compliance_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "compliance_work_mode_lens_coverage",
            compliance_target_category_lenses == 0 or compliance_category_lens_ready_rate >= 0.35,
            actual=round(compliance_category_lens_ready_rate, 4),
            target=0.35,
            required=False,
        ),
        _gate(
            "fresh_compliance_work_mode_category_coverage",
            compliance_target_categories == 0 or fresh_compliance_category_ready_rate >= 0.70,
            actual=round(fresh_compliance_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_compliance_work_mode_lens_coverage",
            compliance_target_category_lenses == 0 or fresh_compliance_category_lens_ready_rate >= 0.30,
            actual=round(fresh_compliance_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "execution_readiness_category_coverage",
            execution_readiness_target_categories == 0 or execution_readiness_category_ready_rate >= 0.70,
            actual=round(execution_readiness_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "execution_readiness_lens_coverage",
            (
                execution_readiness_target_category_lenses == 0
                or execution_readiness_category_lens_ready_rate >= 0.30
            ),
            actual=round(execution_readiness_category_lens_ready_rate, 4),
            target=0.30,
            required=False,
        ),
        _gate(
            "fresh_execution_readiness_category_coverage",
            (
                execution_readiness_target_categories == 0
                or fresh_execution_readiness_category_ready_rate >= 0.70
            ),
            actual=round(fresh_execution_readiness_category_ready_rate, 4),
            target=0.70,
            required=False,
        ),
        _gate(
            "fresh_execution_readiness_lens_coverage",
            (
                execution_readiness_target_category_lenses == 0
                or fresh_execution_readiness_category_lens_ready_rate >= 0.25
            ),
            actual=round(fresh_execution_readiness_category_lens_ready_rate, 4),
            target=0.25,
            required=False,
        ),
        _gate(
            "execution_priority_alignment_category_coverage",
            execution_priority_target_categories == 0 or execution_priority_category_alignment_rate >= 0.65,
            actual=round(execution_priority_category_alignment_rate, 4),
            target=0.65,
            required=False,
        ),
        _gate(
            "execution_priority_alignment_lens_coverage",
            (
                execution_priority_target_category_lenses == 0
                or execution_priority_category_lens_alignment_rate >= 0.25
            ),
            actual=round(execution_priority_category_lens_alignment_rate, 4),
            target=0.25,
            required=False,
        ),
        _gate(
            "fresh_execution_priority_alignment_category_coverage",
            (
                execution_priority_target_categories == 0
                or fresh_execution_priority_category_alignment_rate >= 0.65
            ),
            actual=round(fresh_execution_priority_category_alignment_rate, 4),
            target=0.65,
            required=False,
        ),
        _gate(
            "fresh_execution_priority_alignment_lens_coverage",
            (
                execution_priority_target_category_lenses == 0
                or fresh_execution_priority_category_lens_alignment_rate >= 0.20
            ),
            actual=round(fresh_execution_priority_category_lens_alignment_rate, 4),
            target=0.20,
            required=False,
        ),
        _gate(
            "platform_surface_hotspots",
            platform_surface_focus_hotspots == 0,
            actual=platform_surface_focus_hotspots,
            target=0,
            required=False,
        ),
        _gate(
            "reanalysis_rescue_backlog",
            reanalysis_rescue_candidates == 0,
            actual=reanalysis_rescue_candidates,
            target=0,
            required=False,
        ),
        _gate(
            "discarded_execution_rescue_backlog",
            discarded_execution_rescue_candidates == 0,
            actual=discarded_execution_rescue_candidates,
            target=0,
            required=False,
        ),
    ]

    score = 0.0
    score += 20.0 * _completion(metric_coverage, 0.80)
    score += 18.0 * _completion(survival_rate, 0.35)
    score += 18.0 * _completion(strict_fit_rate, 0.25)
    score += 14.0 * _completion(actionable_rate, 0.20)
    score += 12.0 * _completion(focus_discovery_rate, 0.90)
    score += 12.0 * _completion(focus_strict_rate, 0.70)
    if patient_surface_total:
        patient_surface_score = (
            0.45 * _completion(patient_surface_survival_rate, 0.20)
            + 0.55 * _completion(patient_surface_strict_rate, 0.12)
        )
    else:
        patient_surface_score = 0.60
    score += 6.0 * patient_surface_score
    score = round(max(0.0, min(100.0, score)), 2)

    required_passed = all(gate["passed"] for gate in required_gates)
    advisory_passed = all(gate["passed"] for gate in advisory_gates)
    if score >= 85.0 and required_passed and advisory_passed:
        tier = "world_class"
    elif score >= 70.0 and required_passed:
        tier = "production_ready"
    elif score >= 50.0:
        tier = "needs_improvement"
    else:
        tier = "critical"

    failed_required = [gate["name"] for gate in required_gates if not gate["passed"]]
    failed_advisory = [gate["name"] for gate in advisory_gates if not gate["passed"]]
    high_volume_weak = [
        lane for lane in weak_lanes
        if int(lane.get("total") or 0) >= 50
        and str(lane.get("type") or "") in {"category", "category_lens", "query_variant"}
    ][:10]
    priority_focus_weak = _priority_focus_weak_lanes(weak_lanes, limit=10)

    return {
        "score": score,
        "tier": tier,
        "required_gates_passed": required_passed,
        "advisory_gates_passed": advisory_passed,
        "failed_required_gates": failed_required,
        "failed_advisory_gates": failed_advisory,
        "gates": required_gates + advisory_gates,
        "metric_coverage": {
            "minimum_rate": round(metric_coverage, 4),
            "axis_fit_coverage_rate": round(axis_metric_coverage, 4),
            "lens_fit_coverage_rate": round(lens_metric_coverage, 4),
            "clinic_fit_coverage_rate": round(clinic_fit_metric_coverage, 4),
            "worksite_efficiency_coverage_rate": round(worksite_efficiency_metric_coverage, 4),
            "target": 0.80,
        },
        "focus_categories": {
            "categories": focus_categories,
            "discovered": focus_discovered,
            "survived": focus_survived,
            "strict_fit": focus_strict,
            "missing_discovery": [category for category in focus_categories if category not in focus_discovered],
            "missing_strict_fit": [category for category in focus_categories if category not in focus_strict],
            "discovery_coverage_rate": focus_discovery_rate,
            "survival_coverage_rate": focus_survival_rate,
            "strict_fit_coverage_rate": focus_strict_rate,
        },
        "patient_surface": {
            "total": patient_surface_total,
            "survived": patient_surface_survived,
            "strict_fit": patient_surface_strict,
            "survival_rate": patient_surface_survival_rate,
            "strict_fit_rate": patient_surface_strict_rate,
            "families": {
                "patient_voice": patient_voice,
                "axis_specific": axis_specific,
                "axis_companion": axis_companion,
            },
        },
        "source_seed_integrity": {
            "category_drift_count": source_seed_category_drift,
            "total": int(source_lineage_overall.get("total") or 0),
            "priority_focus_total": source_lineage_priority_total,
            "actionable_strict_total": source_lineage_actionable_total,
            "priority_focus_actionable_strict_total": source_lineage_priority_actionable_total,
            "source_seed_present": int(source_lineage_overall.get("source_seed_present") or 0),
            "priority_focus_source_seed_present": int(
                source_lineage_overall.get("priority_focus_source_seed_present") or 0
            ),
            "actionable_strict_source_seed_present": int(
                source_lineage_overall.get("actionable_strict_source_seed_present") or 0
            ),
            "priority_focus_actionable_strict_source_seed_present": int(
                source_lineage_overall.get("priority_focus_actionable_strict_source_seed_present")
                or 0
            ),
            "source_seed_coverage_rate": round(source_lineage_seed_rate, 4),
            "priority_focus_source_seed_coverage_rate": round(
                source_lineage_priority_seed_rate,
                4,
            ),
            "actionable_strict_source_seed_coverage_rate": round(
                source_lineage_actionable_seed_rate,
                4,
            ),
            "priority_focus_actionable_strict_source_seed_coverage_rate": round(
                source_lineage_priority_actionable_seed_rate,
                4,
            ),
            "query_variant_coverage_rate": round(source_lineage_query_variant_rate, 4),
            "source_seed_missing": int(source_lineage_overall.get("source_seed_missing") or 0),
            "source_seed_fallback_count": int(
                source_lineage_overall.get("source_seed_fallback_count") or 0
            ),
            "query_variant_missing": int(source_lineage_overall.get("query_variant_missing") or 0),
            "target_source_seed_coverage_rate": round(source_lineage_seed_target, 4),
            "target_query_variant_coverage_rate": round(source_lineage_query_variant_target, 4),
        },
        "content_coherence": {
            "observed": content_category_observed,
            "mismatch": int(overall.get("content_category_mismatch") or 0),
            "mismatch_rate": round(content_category_mismatch_rate, 4),
        },
        "lens_surface": {
            "checked": lens_surface_checked,
            "matched": int(overall.get("lens_surface_matched") or 0),
            "mismatch": int(overall.get("lens_surface_mismatch") or 0),
            "mismatch_rate": round(lens_surface_mismatch_rate, 4),
        },
        "patient_journey": {
            "target_pairs": patient_journey_target_pairs,
            "strict_pairs": int(patient_journey_overall.get("strict_pairs") or 0),
            "actionable_strict_pairs": int(patient_journey_overall.get("actionable_strict_pairs") or 0),
            "strict_coverage_rate": round(patient_journey_strict_coverage, 4),
            "actionable_strict_coverage_rate": round(patient_journey_actionable_strict_coverage, 4),
            "gaps": int((patient_journey_coverage.get("counts") or {}).get("gaps") or 0),
            "priority_focus_gaps": patient_journey_coverage.get("priority_focus_gaps") or [],
        },
        "work_queue": {
            "target_categories": work_queue_target_categories,
            "ready_categories": int(work_queue_overall.get("ready_categories") or 0),
            "category_ready_rate": round(work_queue_category_ready_rate, 4),
            "fresh_ready_categories": int(work_queue_overall.get("fresh_ready_categories") or 0),
            "fresh_category_ready_rate": round(fresh_work_queue_category_ready_rate, 4),
            "target_category_lenses": work_queue_target_category_lenses,
            "ready_category_lenses": int(work_queue_overall.get("ready_category_lenses") or 0),
            "category_lens_ready_rate": round(work_queue_category_lens_ready_rate, 4),
            "fresh_ready_category_lenses": int(work_queue_overall.get("fresh_ready_category_lenses") or 0),
            "fresh_category_lens_ready_rate": round(fresh_work_queue_category_lens_ready_rate, 4),
            "unique_ready_categories": int(work_queue_overall.get("unique_ready_categories") or 0),
            "unique_category_ready_rate": round(unique_work_queue_category_ready_rate, 4),
            "unique_ready_category_lenses": int(work_queue_overall.get("unique_ready_category_lenses") or 0),
            "unique_category_lens_ready_rate": round(unique_work_queue_category_lens_ready_rate, 4),
            "fresh_unique_ready_categories": int(work_queue_overall.get("fresh_unique_ready_categories") or 0),
            "fresh_unique_category_ready_rate": round(fresh_unique_work_queue_category_ready_rate, 4),
            "fresh_unique_ready_category_lenses": int(
                work_queue_overall.get("fresh_unique_ready_category_lenses") or 0
            ),
            "fresh_unique_category_lens_ready_rate": round(
                fresh_unique_work_queue_category_lens_ready_rate,
                4,
            ),
            "priority_gaps": work_queue_readiness.get("priority_gaps") or [],
            "fresh_priority_gaps": work_queue_readiness.get("fresh_priority_gaps") or [],
            "unique_priority_gaps": work_queue_readiness.get("unique_priority_gaps") or [],
            "fresh_unique_priority_gaps": work_queue_readiness.get("fresh_unique_priority_gaps") or [],
        },
        "platform_surface": {
            "hotspots": int(platform_surface_counts.get("hotspots") or 0),
            "priority_focus_hotspots": platform_surface_focus_hotspots,
        },
        "reanalysis_rescue_backlog": {
            "candidate_count": reanalysis_rescue_candidates,
            "priority_focus_candidate_count": reanalysis_rescue_priority_focus_candidates,
            "by_category": reanalysis_rescue_quality.get("by_category") or {},
            "by_lens": reanalysis_rescue_quality.get("by_lens") or {},
            "by_category_lens": reanalysis_rescue_quality.get("by_category_lens") or {},
        },
        "discarded_execution_rescue_backlog": {
            "candidate_count": discarded_execution_rescue_candidates,
            "priority_focus_candidate_count": discarded_execution_rescue_priority_focus_candidates,
            "auto_requeue_candidate_count": discarded_execution_auto_requeue_candidates,
            "manual_review_candidate_count": discarded_execution_manual_review_candidates,
            "by_category": discarded_execution_rescue_quality.get("by_category") or {},
            "by_lens": discarded_execution_rescue_quality.get("by_lens") or {},
            "by_category_lens": discarded_execution_rescue_quality.get("by_category_lens") or {},
            "by_status": discarded_execution_rescue_quality.get("by_status") or {},
            "by_reject_reason": discarded_execution_rescue_quality.get("by_reject_reason") or {},
            "by_rescue_mode": discarded_execution_rescue_quality.get("by_rescue_mode") or {},
        },
        "opportunity_diversity": {
            "target_categories": diversity_target_categories,
            "diverse_categories": int(opportunity_diversity_overall.get("diverse_categories") or 0),
            "category_diversity_ready_rate": round(diversity_category_ready_rate, 4),
            "fresh_diverse_categories": int(opportunity_diversity_overall.get("fresh_diverse_categories") or 0),
            "fresh_category_diversity_ready_rate": round(fresh_diversity_category_ready_rate, 4),
            "target_category_lenses": diversity_target_category_lenses,
            "diverse_category_lenses": int(opportunity_diversity_overall.get("diverse_category_lenses") or 0),
            "category_lens_diversity_ready_rate": round(diversity_category_lens_ready_rate, 4),
            "fresh_diverse_category_lenses": int(
                opportunity_diversity_overall.get("fresh_diverse_category_lenses") or 0
            ),
            "fresh_category_lens_diversity_ready_rate": round(fresh_diversity_category_lens_ready_rate, 4),
            "priority_gaps": opportunity_diversity.get("priority_gaps") or [],
            "fresh_priority_gaps": opportunity_diversity.get("fresh_priority_gaps") or [],
        },
        "engagement_hook": {
            "target_categories": hook_target_categories,
            "hook_ready_categories": int(engagement_hook_overall.get("hook_ready_categories") or 0),
            "category_hook_ready_rate": round(hook_category_ready_rate, 4),
            "fresh_hook_ready_categories": int(engagement_hook_overall.get("fresh_hook_ready_categories") or 0),
            "fresh_category_hook_ready_rate": round(fresh_hook_category_ready_rate, 4),
            "target_category_lenses": hook_target_category_lenses,
            "hook_ready_category_lenses": int(
                engagement_hook_overall.get("hook_ready_category_lenses") or 0
            ),
            "category_lens_hook_ready_rate": round(hook_category_lens_ready_rate, 4),
            "fresh_hook_ready_category_lenses": int(
                engagement_hook_overall.get("fresh_hook_ready_category_lenses") or 0
            ),
            "fresh_category_lens_hook_ready_rate": round(fresh_hook_category_lens_ready_rate, 4),
            "priority_gaps": engagement_hook_quality.get("priority_gaps") or [],
            "fresh_priority_gaps": engagement_hook_quality.get("fresh_priority_gaps") or [],
        },
        "treatment_signature": {
            "target_categories": signature_target_categories,
            "signature_ready_categories": int(signature_overall.get("signature_ready_categories") or 0),
            "category_signature_ready_rate": round(signature_category_ready_rate, 4),
            "fresh_signature_ready_categories": int(
                signature_overall.get("fresh_signature_ready_categories") or 0
            ),
            "fresh_category_signature_ready_rate": round(fresh_signature_category_ready_rate, 4),
            "target_category_lenses": signature_target_category_lenses,
            "signature_ready_category_lenses": int(
                signature_overall.get("signature_ready_category_lenses") or 0
            ),
            "category_lens_signature_ready_rate": round(signature_category_lens_ready_rate, 4),
            "fresh_signature_ready_category_lenses": int(
                signature_overall.get("fresh_signature_ready_category_lenses") or 0
            ),
            "fresh_category_lens_signature_ready_rate": round(fresh_signature_category_lens_ready_rate, 4),
            "priority_gaps": treatment_signature_quality.get("priority_gaps") or [],
            "fresh_priority_gaps": treatment_signature_quality.get("fresh_priority_gaps") or [],
        },
        "treatment_signal_diversity": {
            "target_categories": treatment_signal_diversity_target_categories,
            "treatment_signal_diverse_categories": int(
                treatment_signal_diversity_overall.get("treatment_signal_diverse_categories") or 0
            ),
            "category_treatment_signal_diverse_ready_rate": round(
                treatment_signal_diversity_category_ready_rate,
                4,
            ),
            "fresh_treatment_signal_diverse_categories": int(
                treatment_signal_diversity_overall.get("fresh_treatment_signal_diverse_categories") or 0
            ),
            "fresh_category_treatment_signal_diverse_ready_rate": round(
                fresh_treatment_signal_diversity_category_ready_rate,
                4,
            ),
            "target_category_lenses": treatment_signal_diversity_target_category_lenses,
            "treatment_signal_diverse_category_lenses": int(
                treatment_signal_diversity_overall.get("treatment_signal_diverse_category_lenses") or 0
            ),
            "category_lens_treatment_signal_diverse_ready_rate": round(
                treatment_signal_diversity_category_lens_ready_rate,
                4,
            ),
            "fresh_treatment_signal_diverse_category_lenses": int(
                treatment_signal_diversity_overall.get("fresh_treatment_signal_diverse_category_lenses") or 0
            ),
            "fresh_category_lens_treatment_signal_diverse_ready_rate": round(
                fresh_treatment_signal_diversity_category_lens_ready_rate,
                4,
            ),
            "priority_gaps": treatment_signal_diversity_quality.get("priority_gaps") or [],
            "fresh_priority_gaps": treatment_signal_diversity_quality.get("fresh_priority_gaps") or [],
        },
        "treatment_subintent_diversity": {
            "target_categories": treatment_subintent_diversity_target_categories,
            "treatment_subintent_diverse_categories": int(
                treatment_subintent_diversity_overall.get("treatment_subintent_diverse_categories") or 0
            ),
            "category_treatment_subintent_diverse_ready_rate": round(
                treatment_subintent_diversity_category_ready_rate,
                4,
            ),
            "fresh_treatment_subintent_diverse_categories": int(
                treatment_subintent_diversity_overall.get("fresh_treatment_subintent_diverse_categories") or 0
            ),
            "fresh_category_treatment_subintent_diverse_ready_rate": round(
                fresh_treatment_subintent_diversity_category_ready_rate,
                4,
            ),
            "target_category_lenses": treatment_subintent_diversity_target_category_lenses,
            "treatment_subintent_diverse_category_lenses": int(
                treatment_subintent_diversity_overall.get("treatment_subintent_diverse_category_lenses") or 0
            ),
            "category_lens_treatment_subintent_diverse_ready_rate": round(
                treatment_subintent_diversity_category_lens_ready_rate,
                4,
            ),
            "fresh_treatment_subintent_diverse_category_lenses": int(
                treatment_subintent_diversity_overall.get(
                    "fresh_treatment_subintent_diverse_category_lenses"
                )
                or 0
            ),
            "fresh_category_lens_treatment_subintent_diverse_ready_rate": round(
                fresh_treatment_subintent_diversity_category_lens_ready_rate,
                4,
            ),
            "priority_gaps": treatment_subintent_diversity_quality.get("priority_gaps") or [],
            "fresh_priority_gaps": treatment_subintent_diversity_quality.get("fresh_priority_gaps") or [],
        },
        "clinic_modality_fit": {
            "target_categories": clinic_modality_target_categories,
            "clinic_modality_fit_categories": int(
                clinic_modality_overall.get("clinic_modality_fit_categories") or 0
            ),
            "category_clinic_modality_fit_ready_rate": round(
                clinic_modality_category_ready_rate,
                4,
            ),
            "fresh_clinic_modality_fit_categories": int(
                clinic_modality_overall.get("fresh_clinic_modality_fit_categories") or 0
            ),
            "fresh_category_clinic_modality_fit_ready_rate": round(
                fresh_clinic_modality_category_ready_rate,
                4,
            ),
            "target_category_lenses": clinic_modality_target_category_lenses,
            "clinic_modality_fit_category_lenses": int(
                clinic_modality_overall.get("clinic_modality_fit_category_lenses") or 0
            ),
            "category_lens_clinic_modality_fit_ready_rate": round(
                clinic_modality_category_lens_ready_rate,
                4,
            ),
            "fresh_clinic_modality_fit_category_lenses": int(
                clinic_modality_overall.get("fresh_clinic_modality_fit_category_lenses") or 0
            ),
            "fresh_category_lens_clinic_modality_fit_ready_rate": round(
                fresh_clinic_modality_category_lens_ready_rate,
                4,
            ),
            "priority_gaps": clinic_modality_quality.get("priority_gaps") or [],
            "fresh_priority_gaps": clinic_modality_quality.get("fresh_priority_gaps") or [],
        },
        "decision_window": {
            "target_categories": decision_window_target_categories,
            "active_decision_categories": int(
                decision_window_overall.get("active_decision_categories") or 0
            ),
            "category_active_decision_ready_rate": round(
                decision_window_category_ready_rate,
                4,
            ),
            "fresh_active_decision_categories": int(
                decision_window_overall.get("fresh_active_decision_categories") or 0
            ),
            "fresh_category_active_decision_ready_rate": round(
                fresh_decision_window_category_ready_rate,
                4,
            ),
            "target_category_lenses": decision_window_target_category_lenses,
            "active_decision_category_lenses": int(
                decision_window_overall.get("active_decision_category_lenses") or 0
            ),
            "category_lens_active_decision_ready_rate": round(
                decision_window_category_lens_ready_rate,
                4,
            ),
            "fresh_active_decision_category_lenses": int(
                decision_window_overall.get("fresh_active_decision_category_lenses") or 0
            ),
            "fresh_category_lens_active_decision_ready_rate": round(
                fresh_decision_window_category_lens_ready_rate,
                4,
            ),
            "priority_gaps": decision_window_quality.get("priority_gaps") or [],
            "fresh_priority_gaps": decision_window_quality.get("fresh_priority_gaps") or [],
        },
        "seed_candidate_alignment": {
            "target_categories": seed_candidate_alignment_target_categories,
            "seed_aligned_categories": int(
                seed_candidate_alignment_overall.get("seed_aligned_categories") or 0
            ),
            "category_seed_alignment_ready_rate": round(
                seed_candidate_alignment_category_ready_rate,
                4,
            ),
            "fresh_seed_aligned_categories": int(
                seed_candidate_alignment_overall.get("fresh_seed_aligned_categories") or 0
            ),
            "fresh_category_seed_alignment_ready_rate": round(
                fresh_seed_candidate_alignment_category_ready_rate,
                4,
            ),
            "target_category_lenses": seed_candidate_alignment_target_category_lenses,
            "seed_aligned_category_lenses": int(
                seed_candidate_alignment_overall.get("seed_aligned_category_lenses") or 0
            ),
            "category_lens_seed_alignment_ready_rate": round(
                seed_candidate_alignment_category_lens_ready_rate,
                4,
            ),
            "fresh_seed_aligned_category_lenses": int(
                seed_candidate_alignment_overall.get("fresh_seed_aligned_category_lenses") or 0
            ),
            "fresh_category_lens_seed_alignment_ready_rate": round(
                fresh_seed_candidate_alignment_category_lens_ready_rate,
                4,
            ),
            "priority_gaps": seed_candidate_alignment_quality.get("priority_gaps") or [],
            "fresh_priority_gaps": seed_candidate_alignment_quality.get("fresh_priority_gaps") or [],
        },
        "local_intent": {
            "target_categories": local_target_categories,
            "local_ready_categories": int(local_intent_overall.get("local_ready_categories") or 0),
            "category_local_ready_rate": round(local_category_ready_rate, 4),
            "fresh_local_ready_categories": int(
                local_intent_overall.get("fresh_local_ready_categories") or 0
            ),
            "fresh_category_local_ready_rate": round(fresh_local_category_ready_rate, 4),
            "target_category_lenses": local_target_category_lenses,
            "local_ready_category_lenses": int(
                local_intent_overall.get("local_ready_category_lenses") or 0
            ),
            "category_lens_local_ready_rate": round(local_category_lens_ready_rate, 4),
            "fresh_local_ready_category_lenses": int(
                local_intent_overall.get("fresh_local_ready_category_lenses") or 0
            ),
            "fresh_category_lens_local_ready_rate": round(fresh_local_category_lens_ready_rate, 4),
            "priority_gaps": local_intent_quality.get("priority_gaps") or [],
            "fresh_priority_gaps": local_intent_quality.get("fresh_priority_gaps") or [],
        },
        "local_area_diversity": {
            "target_categories": local_area_target_categories,
            "local_area_diverse_categories": int(
                local_area_diversity_overall.get("local_area_diverse_categories") or 0
            ),
            "category_local_area_diversity_ready_rate": round(local_area_category_ready_rate, 4),
            "fresh_local_area_diverse_categories": int(
                local_area_diversity_overall.get("fresh_local_area_diverse_categories") or 0
            ),
            "fresh_category_local_area_diversity_ready_rate": round(
                fresh_local_area_category_ready_rate,
                4,
            ),
            "target_category_lenses": local_area_target_category_lenses,
            "local_area_diverse_category_lenses": int(
                local_area_diversity_overall.get("local_area_diverse_category_lenses") or 0
            ),
            "category_lens_local_area_diversity_ready_rate": round(
                local_area_category_lens_ready_rate,
                4,
            ),
            "fresh_local_area_diverse_category_lenses": int(
                local_area_diversity_overall.get("fresh_local_area_diverse_category_lenses") or 0
            ),
            "fresh_category_lens_local_area_diversity_ready_rate": round(
                fresh_local_area_category_lens_ready_rate,
                4,
            ),
            "priority_gaps": local_area_diversity_quality.get("priority_gaps") or [],
            "fresh_priority_gaps": local_area_diversity_quality.get("fresh_priority_gaps") or [],
        },
        "patient_surface_authenticity": {
            "target_categories": authentic_surface_target_categories,
            "patient_surface_ready_categories": int(
                patient_surface_overall_quality.get("patient_surface_ready_categories") or 0
            ),
            "category_patient_surface_ready_rate": round(authentic_surface_category_ready_rate, 4),
            "fresh_patient_surface_ready_categories": int(
                patient_surface_overall_quality.get("fresh_patient_surface_ready_categories") or 0
            ),
            "fresh_category_patient_surface_ready_rate": round(fresh_authentic_surface_category_ready_rate, 4),
            "target_category_lenses": authentic_surface_target_category_lenses,
            "patient_surface_ready_category_lenses": int(
                patient_surface_overall_quality.get("patient_surface_ready_category_lenses") or 0
            ),
            "category_lens_patient_surface_ready_rate": round(authentic_surface_category_lens_ready_rate, 4),
            "fresh_patient_surface_ready_category_lenses": int(
                patient_surface_overall_quality.get("fresh_patient_surface_ready_category_lenses") or 0
            ),
            "fresh_category_lens_patient_surface_ready_rate": round(
                fresh_authentic_surface_category_lens_ready_rate,
                4,
            ),
            "priority_gaps": patient_surface_quality.get("priority_gaps") or [],
            "fresh_priority_gaps": patient_surface_quality.get("fresh_priority_gaps") or [],
        },
        "viral_action_route": {
            "target_categories": route_target_categories,
            "route_ready_categories": int(viral_action_route_overall.get("route_ready_categories") or 0),
            "category_route_ready_rate": round(route_category_ready_rate, 4),
            "fresh_route_ready_categories": int(
                viral_action_route_overall.get("fresh_route_ready_categories") or 0
            ),
            "fresh_category_route_ready_rate": round(fresh_route_category_ready_rate, 4),
            "target_category_lenses": route_target_category_lenses,
            "route_ready_category_lenses": int(
                viral_action_route_overall.get("route_ready_category_lenses") or 0
            ),
            "category_lens_route_ready_rate": round(route_category_lens_ready_rate, 4),
            "fresh_route_ready_category_lenses": int(
                viral_action_route_overall.get("fresh_route_ready_category_lenses") or 0
            ),
            "fresh_category_lens_route_ready_rate": round(fresh_route_category_lens_ready_rate, 4),
            "priority_gaps": viral_action_route_quality.get("priority_gaps") or [],
            "fresh_priority_gaps": viral_action_route_quality.get("fresh_priority_gaps") or [],
        },
        "reply_workability": {
            "target_categories": reply_workability_target_categories,
            "reply_workable_categories": int(
                reply_workability_overall.get("reply_workable_categories") or 0
            ),
            "category_reply_workable_ready_rate": round(reply_workability_category_ready_rate, 4),
            "fresh_reply_workable_categories": int(
                reply_workability_overall.get("fresh_reply_workable_categories") or 0
            ),
            "fresh_category_reply_workable_ready_rate": round(
                fresh_reply_workability_category_ready_rate,
                4,
            ),
            "target_category_lenses": reply_workability_target_category_lenses,
            "reply_workable_category_lenses": int(
                reply_workability_overall.get("reply_workable_category_lenses") or 0
            ),
            "category_lens_reply_workable_ready_rate": round(
                reply_workability_category_lens_ready_rate,
                4,
            ),
            "fresh_reply_workable_category_lenses": int(
                reply_workability_overall.get("fresh_reply_workable_category_lenses") or 0
            ),
            "fresh_category_lens_reply_workable_ready_rate": round(
                fresh_reply_workability_category_lens_ready_rate,
                4,
            ),
            "priority_gaps": reply_workability_quality.get("priority_gaps") or [],
            "fresh_priority_gaps": reply_workability_quality.get("fresh_priority_gaps") or [],
        },
        "compliance_work_mode": {
            "target_categories": compliance_target_categories,
            "auto_work_ready_categories": int(
                compliance_work_mode_overall.get("auto_work_ready_categories") or 0
            ),
            "category_auto_work_ready_rate": round(compliance_category_ready_rate, 4),
            "fresh_auto_work_ready_categories": int(
                compliance_work_mode_overall.get("fresh_auto_work_ready_categories") or 0
            ),
            "fresh_category_auto_work_ready_rate": round(fresh_compliance_category_ready_rate, 4),
            "target_category_lenses": compliance_target_category_lenses,
            "auto_work_ready_category_lenses": int(
                compliance_work_mode_overall.get("auto_work_ready_category_lenses") or 0
            ),
            "category_lens_auto_work_ready_rate": round(compliance_category_lens_ready_rate, 4),
            "fresh_auto_work_ready_category_lenses": int(
                compliance_work_mode_overall.get("fresh_auto_work_ready_category_lenses") or 0
            ),
            "fresh_category_lens_auto_work_ready_rate": round(
                fresh_compliance_category_lens_ready_rate,
                4,
            ),
            "work_mode_counts": compliance_work_mode_overall.get("work_mode_counts") or {},
            "fresh_work_mode_counts": compliance_work_mode_overall.get("fresh_work_mode_counts") or {},
            "priority_gaps": compliance_work_mode_quality.get("priority_gaps") or [],
            "fresh_priority_gaps": compliance_work_mode_quality.get("fresh_priority_gaps") or [],
        },
        "execution_readiness": {
            "target_categories": execution_readiness_target_categories,
            "execution_ready_categories": int(
                execution_readiness_overall.get("execution_ready_categories") or 0
            ),
            "category_execution_ready_rate": round(execution_readiness_category_ready_rate, 4),
            "fresh_execution_ready_categories": int(
                execution_readiness_overall.get("fresh_execution_ready_categories") or 0
            ),
            "fresh_category_execution_ready_rate": round(
                fresh_execution_readiness_category_ready_rate,
                4,
            ),
            "target_category_lenses": execution_readiness_target_category_lenses,
            "execution_ready_category_lenses": int(
                execution_readiness_overall.get("execution_ready_category_lenses") or 0
            ),
            "category_lens_execution_ready_rate": round(
                execution_readiness_category_lens_ready_rate,
                4,
            ),
            "fresh_execution_ready_category_lenses": int(
                execution_readiness_overall.get("fresh_execution_ready_category_lenses") or 0
            ),
            "fresh_category_lens_execution_ready_rate": round(
                fresh_execution_readiness_category_lens_ready_rate,
                4,
            ),
            "priority_gaps": execution_readiness_quality.get("priority_gaps") or [],
            "fresh_priority_gaps": execution_readiness_quality.get("fresh_priority_gaps") or [],
        },
        "execution_priority_alignment": {
            "target_categories": execution_priority_target_categories,
            "priority_aligned_categories": int(
                execution_priority_alignment_overall.get("priority_aligned_categories") or 0
            ),
            "category_priority_alignment_rate": round(execution_priority_category_alignment_rate, 4),
            "fresh_priority_aligned_categories": int(
                execution_priority_alignment_overall.get("fresh_priority_aligned_categories") or 0
            ),
            "fresh_category_priority_alignment_rate": round(
                fresh_execution_priority_category_alignment_rate,
                4,
            ),
            "target_category_lenses": execution_priority_target_category_lenses,
            "priority_aligned_category_lenses": int(
                execution_priority_alignment_overall.get("priority_aligned_category_lenses") or 0
            ),
            "category_lens_priority_alignment_rate": round(
                execution_priority_category_lens_alignment_rate,
                4,
            ),
            "fresh_priority_aligned_category_lenses": int(
                execution_priority_alignment_overall.get("fresh_priority_aligned_category_lenses") or 0
            ),
            "fresh_category_lens_priority_alignment_rate": round(
                fresh_execution_priority_category_lens_alignment_rate,
                4,
            ),
            "priority_gaps": execution_priority_alignment_quality.get("priority_gaps") or [],
            "fresh_priority_gaps": execution_priority_alignment_quality.get("fresh_priority_gaps") or [],
        },
        "high_volume_weak_lanes": high_volume_weak,
        "priority_focus_weak_lanes": priority_focus_weak,
    }


def _next_run_playbook(
    *,
    source_scan_run_id: Optional[int],
    row_count: int,
    overall: Dict[str, Any],
    seed_target_coverage: Dict[str, Any],
    weak_lanes: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
    sample_per_lane: int,
    source_seed_feedback: Optional[Dict[str, Any]] = None,
    variant_quality_feedback: Optional[Dict[str, Any]] = None,
    loss_analysis: Optional[Dict[str, Any]] = None,
    patient_journey_coverage: Optional[Dict[str, Any]] = None,
    work_queue_readiness: Optional[Dict[str, Any]] = None,
    opportunity_diversity: Optional[Dict[str, Any]] = None,
    engagement_hook_quality: Optional[Dict[str, Any]] = None,
    treatment_signature_quality: Optional[Dict[str, Any]] = None,
    treatment_signal_diversity_quality: Optional[Dict[str, Any]] = None,
    treatment_subintent_diversity_quality: Optional[Dict[str, Any]] = None,
    clinic_modality_quality: Optional[Dict[str, Any]] = None,
    decision_window_quality: Optional[Dict[str, Any]] = None,
    seed_candidate_alignment_quality: Optional[Dict[str, Any]] = None,
    local_intent_quality: Optional[Dict[str, Any]] = None,
    local_area_diversity_quality: Optional[Dict[str, Any]] = None,
    patient_surface_quality: Optional[Dict[str, Any]] = None,
    viral_action_route_quality: Optional[Dict[str, Any]] = None,
    reply_workability_quality: Optional[Dict[str, Any]] = None,
    compliance_work_mode_quality: Optional[Dict[str, Any]] = None,
    execution_readiness_quality: Optional[Dict[str, Any]] = None,
    execution_priority_alignment_quality: Optional[Dict[str, Any]] = None,
    platform_surface_quality: Optional[Dict[str, Any]] = None,
    source_lineage_quality: Optional[Dict[str, Any]] = None,
    reanalysis_rescue_quality: Optional[Dict[str, Any]] = None,
    discarded_execution_rescue_quality: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    source_seed_feedback = source_seed_feedback or {}
    variant_quality_feedback = variant_quality_feedback or {}
    loss_analysis = loss_analysis or {}
    patient_journey_coverage = patient_journey_coverage or {}
    work_queue_readiness = work_queue_readiness or {}
    opportunity_diversity = opportunity_diversity or {}
    engagement_hook_quality = engagement_hook_quality or {}
    treatment_signature_quality = treatment_signature_quality or {}
    treatment_signal_diversity_quality = treatment_signal_diversity_quality or {}
    treatment_subintent_diversity_quality = treatment_subintent_diversity_quality or {}
    clinic_modality_quality = clinic_modality_quality or {}
    decision_window_quality = decision_window_quality or {}
    seed_candidate_alignment_quality = seed_candidate_alignment_quality or {}
    local_intent_quality = local_intent_quality or {}
    local_area_diversity_quality = local_area_diversity_quality or {}
    patient_surface_quality = patient_surface_quality or {}
    viral_action_route_quality = viral_action_route_quality or {}
    reply_workability_quality = reply_workability_quality or {}
    compliance_work_mode_quality = compliance_work_mode_quality or {}
    execution_readiness_quality = execution_readiness_quality or {}
    execution_priority_alignment_quality = execution_priority_alignment_quality or {}
    platform_surface_quality = platform_surface_quality or {}
    source_lineage_quality = source_lineage_quality or {}
    reanalysis_rescue_quality = reanalysis_rescue_quality or {}
    discarded_execution_rescue_quality = discarded_execution_rescue_quality or {}
    metric_backfill_gaps: List[Dict[str, Any]] = []
    if row_count:
        for code, metric_key, label in (
            ("axis_fit_metric_coverage_low", "axis_coverage_rate", "axis_fit"),
            ("lens_fit_metric_coverage_low", "lens_coverage_rate", "lens_fit"),
            ("clinic_fit_metric_coverage_low", "clinic_fit_coverage_rate", "clinic_fit"),
            (
                "worksite_efficiency_metric_coverage_low",
                "worksite_efficiency_coverage_rate",
                "worksite_efficiency",
            ),
        ):
            coverage_rate = float(overall.get(metric_key) or 0.0)
            if coverage_rate < 0.80:
                metric_backfill_gaps.append({
                    "code": code,
                    "metric": label,
                    "coverage_rate": round(coverage_rate, 4),
                    "target": 0.80,
                })
    metric_backfill_required = bool(metric_backfill_gaps)
    boost_categories = [
        {
            "category": lane,
            **metrics,
        }
        for lane, metrics in (seed_target_coverage.get("by_category") or {}).items()
        if metrics.get("gap_reasons")
    ]
    boost_lenses = [
        {
            "lens": lane,
            **metrics,
        }
        for lane, metrics in (seed_target_coverage.get("by_lens") or {}).items()
        if metrics.get("gap_reasons")
    ]
    boost_category_lenses = [
        {
            "category_lens": lane,
            **metrics,
        }
        for lane, metrics in (seed_target_coverage.get("by_category_lens") or {}).items()
        if metrics.get("gap_reasons")
    ]
    boost_categories.sort(
        key=lambda item: (
            _category_priority_sort_key(item.get("category")),
            item["target_per_seed"],
            item["strict_fit_per_seed"],
            -item["seed_count"],
        )
    )
    boost_lenses.sort(key=lambda item: (item["target_per_seed"], item["strict_fit_per_seed"], -item["seed_count"]))
    boost_category_lenses.sort(
        key=lambda item: (
            _category_lens_priority_sort_key(item.get("category_lens")),
            item["target_per_seed"],
            item["strict_fit_per_seed"],
            -item["seed_count"],
        )
    )
    coverage_gap_required = bool(boost_categories or boost_lenses or boost_category_lenses)
    content_mismatch_lanes = _weak_lanes_for_reason(
        weak_lanes,
        "content_category_mismatch",
        limit=10,
    )
    lens_surface_mismatch_lanes = _weak_lanes_for_reason(
        weak_lanes,
        "lens_surface_mismatch",
        limit=10,
    )
    content_coherence_required = bool(
        content_mismatch_lanes
        or (
            int(overall.get("content_category_observed") or 0) > 0
            and float(overall.get("content_category_mismatch_rate") or 0.0) > 0.05
        )
    )
    lens_surface_required = bool(
        lens_surface_mismatch_lanes
        or (
            int(overall.get("lens_surface_checked") or 0) > 0
            and float(overall.get("lens_surface_mismatch_rate") or 0.0) > 0.20
        )
    )

    review_before_scaling = [
        lane for lane in weak_lanes
        if any(
            reason in set(lane.get("reasons") or [])
            for reason in (
                "low_axis_fit",
                "low_lens_fit",
                "low_strict_fit_rate",
                "content_category_mismatch",
                "lens_surface_mismatch",
                "low_worksite_efficiency",
            )
        )
    ][:10]
    source_seed_actions = {
        "recategorize_or_quarantine": (source_seed_feedback.get("recategorize_candidates") or [])[:10],
        "repair_query_shape": (source_seed_feedback.get("repair_candidates") or [])[:10],
        "retire_or_pause": (source_seed_feedback.get("retire_candidates") or [])[:10],
        "scale_or_keep": (source_seed_feedback.get("scale_candidates") or [])[:10],
        "assist_only_companions": (source_seed_feedback.get("assist_only_candidates") or [])[:10],
    }
    source_seed_feedback_required = bool(
        source_seed_actions["recategorize_or_quarantine"]
        or source_seed_actions["repair_query_shape"]
        or source_seed_actions["retire_or_pause"]
    )
    source_lineage_overall = source_lineage_quality.get("overall") or {}
    source_lineage_targets = source_lineage_quality.get("targets") or {}
    source_lineage_seed_target = float(
        source_lineage_targets.get("source_seed_coverage_rate")
        or SOURCE_LINEAGE_MIN_SOURCE_SEED_COVERAGE
    )
    source_lineage_priority_seed_target = float(
        source_lineage_targets.get("priority_focus_source_seed_coverage_rate")
        or SOURCE_LINEAGE_MIN_PRIORITY_FOCUS_SOURCE_SEED_COVERAGE
    )
    source_lineage_actionable_seed_target = float(
        source_lineage_targets.get("actionable_strict_source_seed_coverage_rate")
        or SOURCE_LINEAGE_MIN_ACTIONABLE_STRICT_SOURCE_SEED_COVERAGE
    )
    source_lineage_query_variant_target = float(
        source_lineage_targets.get("query_variant_coverage_rate")
        or SOURCE_LINEAGE_MIN_QUERY_VARIANT_COVERAGE
    )
    source_lineage_priority_total = int(source_lineage_overall.get("priority_focus_total") or 0)
    source_lineage_actionable_total = int(source_lineage_overall.get("actionable_strict_total") or 0)
    source_lineage_priority_actionable_total = int(
        source_lineage_overall.get("priority_focus_actionable_strict_total") or 0
    )
    source_lineage_repair_required = bool(
        row_count
        and source_lineage_overall
        and (
            float(source_lineage_overall.get("source_seed_coverage_rate") or 0.0)
            < source_lineage_seed_target
            or (
                source_lineage_priority_total
                and float(
                    source_lineage_overall.get("priority_focus_source_seed_coverage_rate")
                    or 0.0
                )
                < source_lineage_priority_seed_target
            )
            or (
                source_lineage_actionable_total
                and float(
                    source_lineage_overall.get("actionable_strict_source_seed_coverage_rate")
                    or 0.0
                )
                < source_lineage_actionable_seed_target
            )
            or (
                source_lineage_priority_actionable_total
                and float(
                    source_lineage_overall.get(
                        "priority_focus_actionable_strict_source_seed_coverage_rate"
                    )
                    or 0.0
                )
                < source_lineage_actionable_seed_target
            )
            or float(source_lineage_overall.get("query_variant_coverage_rate") or 0.0)
            < source_lineage_query_variant_target
        )
    )
    source_lineage_gaps = (
        source_lineage_quality.get("priority_gaps")
        or source_lineage_quality.get("category_lens_gaps")
        or source_lineage_quality.get("category_gaps")
        or []
    )[:10]
    source_lineage_missing_samples = list(source_lineage_quality.get("missing_samples") or [])[:10]
    variant_actions = {
        "repair_query_shape": (variant_quality_feedback.get("repair_variants") or [])[:10],
        "retire_or_pause": (variant_quality_feedback.get("retire_variants") or [])[:10],
        "scale_or_keep": (variant_quality_feedback.get("scale_variants") or [])[:10],
        "repair_category_lens_query_shape": (
            variant_quality_feedback.get("repair_category_lens_variants") or []
        )[:10],
        "retire_category_lens_or_pause": (
            variant_quality_feedback.get("retire_category_lens_variants") or []
        )[:10],
        "scale_category_lens_or_keep": (
            variant_quality_feedback.get("scale_category_lens_variants") or []
        )[:10],
        "repair_family_query_shape": (variant_quality_feedback.get("repair_families") or [])[:10],
        "retire_family_or_pause": (variant_quality_feedback.get("retire_families") or [])[:10],
        "scale_family_or_keep": (variant_quality_feedback.get("scale_families") or [])[:10],
    }
    variant_quality_feedback_required = bool(
        variant_actions["repair_query_shape"]
        or variant_actions["retire_or_pause"]
        or variant_actions["repair_category_lens_query_shape"]
        or variant_actions["retire_category_lens_or_pause"]
        or variant_actions["repair_family_query_shape"]
        or variant_actions["retire_family_or_pause"]
    )
    loss_hotspots = (loss_analysis.get("priority_focus_hotspots") or loss_analysis.get("hotspots") or [])[:10]
    filter_loss_required = bool(loss_hotspots)
    patient_journey_gaps = (
        patient_journey_coverage.get("priority_focus_gaps")
        or patient_journey_coverage.get("gaps")
        or []
    )[:10]
    patient_journey_required = bool(patient_journey_gaps)
    work_queue_gaps = (
        work_queue_readiness.get("priority_gaps")
        or work_queue_readiness.get("category_lens_gaps")
        or work_queue_readiness.get("category_gaps")
        or []
    )[:10]
    work_queue_required = bool(work_queue_gaps)
    fresh_work_queue_gaps = (
        work_queue_readiness.get("fresh_priority_gaps")
        or work_queue_readiness.get("fresh_category_lens_gaps")
        or work_queue_readiness.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_work_queue_required = bool(fresh_work_queue_gaps)
    unique_work_queue_gaps = (
        work_queue_readiness.get("unique_priority_gaps")
        or work_queue_readiness.get("unique_category_lens_gaps")
        or work_queue_readiness.get("unique_category_gaps")
        or []
    )[:10]
    unique_work_queue_required = bool(unique_work_queue_gaps)
    fresh_unique_work_queue_gaps = (
        work_queue_readiness.get("fresh_unique_priority_gaps")
        or work_queue_readiness.get("fresh_unique_category_lens_gaps")
        or work_queue_readiness.get("fresh_unique_category_gaps")
        or []
    )[:10]
    fresh_unique_work_queue_required = bool(fresh_unique_work_queue_gaps)
    opportunity_diversity_gaps = (
        opportunity_diversity.get("priority_gaps")
        or opportunity_diversity.get("category_lens_gaps")
        or opportunity_diversity.get("category_gaps")
        or []
    )[:10]
    opportunity_diversity_required = bool(opportunity_diversity_gaps)
    fresh_opportunity_diversity_gaps = (
        opportunity_diversity.get("fresh_priority_gaps")
        or opportunity_diversity.get("fresh_category_lens_gaps")
        or opportunity_diversity.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_opportunity_diversity_required = bool(fresh_opportunity_diversity_gaps)
    engagement_hook_gaps = (
        engagement_hook_quality.get("priority_gaps")
        or engagement_hook_quality.get("category_lens_gaps")
        or engagement_hook_quality.get("category_gaps")
        or []
    )[:10]
    engagement_hook_required = bool(engagement_hook_gaps)
    fresh_engagement_hook_gaps = (
        engagement_hook_quality.get("fresh_priority_gaps")
        or engagement_hook_quality.get("fresh_category_lens_gaps")
        or engagement_hook_quality.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_engagement_hook_required = bool(fresh_engagement_hook_gaps)
    treatment_signature_gaps = (
        treatment_signature_quality.get("priority_gaps")
        or treatment_signature_quality.get("category_lens_gaps")
        or treatment_signature_quality.get("category_gaps")
        or []
    )[:10]
    treatment_signature_required = bool(treatment_signature_gaps)
    fresh_treatment_signature_gaps = (
        treatment_signature_quality.get("fresh_priority_gaps")
        or treatment_signature_quality.get("fresh_category_lens_gaps")
        or treatment_signature_quality.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_treatment_signature_required = bool(fresh_treatment_signature_gaps)
    treatment_signal_diversity_gaps = (
        treatment_signal_diversity_quality.get("priority_gaps")
        or treatment_signal_diversity_quality.get("category_lens_gaps")
        or treatment_signal_diversity_quality.get("category_gaps")
        or []
    )[:10]
    treatment_signal_diversity_required = bool(treatment_signal_diversity_gaps)
    fresh_treatment_signal_diversity_gaps = (
        treatment_signal_diversity_quality.get("fresh_priority_gaps")
        or treatment_signal_diversity_quality.get("fresh_category_lens_gaps")
        or treatment_signal_diversity_quality.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_treatment_signal_diversity_required = bool(fresh_treatment_signal_diversity_gaps)
    treatment_subintent_diversity_gaps = (
        treatment_subintent_diversity_quality.get("priority_gaps")
        or treatment_subintent_diversity_quality.get("category_lens_gaps")
        or treatment_subintent_diversity_quality.get("category_gaps")
        or []
    )[:10]
    treatment_subintent_diversity_required = bool(treatment_subintent_diversity_gaps)
    fresh_treatment_subintent_diversity_gaps = (
        treatment_subintent_diversity_quality.get("fresh_priority_gaps")
        or treatment_subintent_diversity_quality.get("fresh_category_lens_gaps")
        or treatment_subintent_diversity_quality.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_treatment_subintent_diversity_required = bool(fresh_treatment_subintent_diversity_gaps)
    clinic_modality_gaps = (
        clinic_modality_quality.get("priority_gaps")
        or clinic_modality_quality.get("category_lens_gaps")
        or clinic_modality_quality.get("category_gaps")
        or []
    )[:10]
    clinic_modality_required = bool(clinic_modality_gaps)
    fresh_clinic_modality_gaps = (
        clinic_modality_quality.get("fresh_priority_gaps")
        or clinic_modality_quality.get("fresh_category_lens_gaps")
        or clinic_modality_quality.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_clinic_modality_required = bool(fresh_clinic_modality_gaps)
    decision_window_gaps = (
        decision_window_quality.get("priority_gaps")
        or decision_window_quality.get("category_lens_gaps")
        or decision_window_quality.get("category_gaps")
        or []
    )[:10]
    decision_window_required = bool(decision_window_gaps)
    fresh_decision_window_gaps = (
        decision_window_quality.get("fresh_priority_gaps")
        or decision_window_quality.get("fresh_category_lens_gaps")
        or decision_window_quality.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_decision_window_required = bool(fresh_decision_window_gaps)
    seed_candidate_alignment_gaps = (
        seed_candidate_alignment_quality.get("priority_gaps")
        or seed_candidate_alignment_quality.get("category_lens_gaps")
        or seed_candidate_alignment_quality.get("category_gaps")
        or []
    )[:10]
    seed_candidate_alignment_required = bool(seed_candidate_alignment_gaps)
    fresh_seed_candidate_alignment_gaps = (
        seed_candidate_alignment_quality.get("fresh_priority_gaps")
        or seed_candidate_alignment_quality.get("fresh_category_lens_gaps")
        or seed_candidate_alignment_quality.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_seed_candidate_alignment_required = bool(fresh_seed_candidate_alignment_gaps)
    local_intent_gaps = (
        local_intent_quality.get("priority_gaps")
        or local_intent_quality.get("category_lens_gaps")
        or local_intent_quality.get("category_gaps")
        or []
    )[:10]
    local_intent_required = bool(local_intent_gaps)
    fresh_local_intent_gaps = (
        local_intent_quality.get("fresh_priority_gaps")
        or local_intent_quality.get("fresh_category_lens_gaps")
        or local_intent_quality.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_local_intent_required = bool(fresh_local_intent_gaps)
    local_area_diversity_gaps = (
        local_area_diversity_quality.get("priority_gaps")
        or local_area_diversity_quality.get("category_lens_gaps")
        or local_area_diversity_quality.get("category_gaps")
        or []
    )[:10]
    local_area_diversity_required = bool(local_area_diversity_gaps)
    fresh_local_area_diversity_gaps = (
        local_area_diversity_quality.get("fresh_priority_gaps")
        or local_area_diversity_quality.get("fresh_category_lens_gaps")
        or local_area_diversity_quality.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_local_area_diversity_required = bool(fresh_local_area_diversity_gaps)
    patient_surface_gaps = (
        patient_surface_quality.get("priority_gaps")
        or patient_surface_quality.get("category_lens_gaps")
        or patient_surface_quality.get("category_gaps")
        or []
    )[:10]
    patient_surface_required = bool(patient_surface_gaps)
    fresh_patient_surface_gaps = (
        patient_surface_quality.get("fresh_priority_gaps")
        or patient_surface_quality.get("fresh_category_lens_gaps")
        or patient_surface_quality.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_patient_surface_required = bool(fresh_patient_surface_gaps)
    viral_action_route_gaps = (
        viral_action_route_quality.get("priority_gaps")
        or viral_action_route_quality.get("category_lens_gaps")
        or viral_action_route_quality.get("category_gaps")
        or []
    )[:10]
    viral_action_route_required = bool(viral_action_route_gaps)
    fresh_viral_action_route_gaps = (
        viral_action_route_quality.get("fresh_priority_gaps")
        or viral_action_route_quality.get("fresh_category_lens_gaps")
        or viral_action_route_quality.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_viral_action_route_required = bool(fresh_viral_action_route_gaps)
    reply_workability_gaps = (
        reply_workability_quality.get("priority_gaps")
        or reply_workability_quality.get("category_lens_gaps")
        or reply_workability_quality.get("category_gaps")
        or []
    )[:10]
    reply_workability_required = bool(reply_workability_gaps)
    fresh_reply_workability_gaps = (
        reply_workability_quality.get("fresh_priority_gaps")
        or reply_workability_quality.get("fresh_category_lens_gaps")
        or reply_workability_quality.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_reply_workability_required = bool(fresh_reply_workability_gaps)
    compliance_work_mode_gaps = (
        compliance_work_mode_quality.get("priority_gaps")
        or compliance_work_mode_quality.get("category_lens_gaps")
        or compliance_work_mode_quality.get("category_gaps")
        or []
    )[:10]
    compliance_work_mode_required = bool(compliance_work_mode_gaps)
    fresh_compliance_work_mode_gaps = (
        compliance_work_mode_quality.get("fresh_priority_gaps")
        or compliance_work_mode_quality.get("fresh_category_lens_gaps")
        or compliance_work_mode_quality.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_compliance_work_mode_required = bool(fresh_compliance_work_mode_gaps)
    execution_readiness_gaps = (
        execution_readiness_quality.get("priority_gaps")
        or execution_readiness_quality.get("category_lens_gaps")
        or execution_readiness_quality.get("category_gaps")
        or []
    )[:10]
    execution_readiness_required = bool(execution_readiness_gaps)
    fresh_execution_readiness_gaps = (
        execution_readiness_quality.get("fresh_priority_gaps")
        or execution_readiness_quality.get("fresh_category_lens_gaps")
        or execution_readiness_quality.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_execution_readiness_required = bool(fresh_execution_readiness_gaps)
    execution_priority_alignment_gaps = (
        execution_priority_alignment_quality.get("priority_gaps")
        or execution_priority_alignment_quality.get("category_lens_gaps")
        or execution_priority_alignment_quality.get("category_gaps")
        or []
    )[:10]
    execution_priority_alignment_required = bool(execution_priority_alignment_gaps)
    fresh_execution_priority_alignment_gaps = (
        execution_priority_alignment_quality.get("fresh_priority_gaps")
        or execution_priority_alignment_quality.get("fresh_category_lens_gaps")
        or execution_priority_alignment_quality.get("fresh_category_gaps")
        or []
    )[:10]
    fresh_execution_priority_alignment_required = bool(fresh_execution_priority_alignment_gaps)
    platform_surface_hotspots = (
        platform_surface_quality.get("priority_focus_hotspots")
        or platform_surface_quality.get("hotspots")
        or []
    )[:10]
    platform_surface_required = bool(platform_surface_hotspots)
    reanalysis_rescue_overall = reanalysis_rescue_quality.get("overall") or {}
    try:
        reanalysis_rescue_candidate_count = int(float(reanalysis_rescue_overall.get("candidate_count") or 0))
    except (TypeError, ValueError):
        reanalysis_rescue_candidate_count = 0
    try:
        reanalysis_rescue_priority_focus_candidate_count = int(
            float(reanalysis_rescue_overall.get("priority_focus_candidate_count") or 0)
        )
    except (TypeError, ValueError):
        reanalysis_rescue_priority_focus_candidate_count = 0
    reanalysis_rescue_samples = list(reanalysis_rescue_quality.get("samples") or [])[:10]
    reanalysis_rescue_required = reanalysis_rescue_candidate_count > 0
    reanalysis_rescue_budget = (
        max(60, min(300, int(reanalysis_rescue_candidate_count * 1.5)))
        if reanalysis_rescue_required
        else 0
    )
    discarded_execution_rescue_overall = discarded_execution_rescue_quality.get("overall") or {}
    try:
        discarded_execution_rescue_candidate_count = int(
            float(discarded_execution_rescue_overall.get("candidate_count") or 0)
        )
    except (TypeError, ValueError):
        discarded_execution_rescue_candidate_count = 0
    try:
        discarded_execution_rescue_priority_focus_candidate_count = int(
            float(discarded_execution_rescue_overall.get("priority_focus_candidate_count") or 0)
        )
    except (TypeError, ValueError):
        discarded_execution_rescue_priority_focus_candidate_count = 0
    try:
        discarded_execution_auto_requeue_candidate_count = int(
            float(discarded_execution_rescue_overall.get("auto_requeue_candidate_count") or 0)
        )
    except (TypeError, ValueError):
        discarded_execution_auto_requeue_candidate_count = 0
    try:
        discarded_execution_manual_review_candidate_count = int(
            float(discarded_execution_rescue_overall.get("manual_review_candidate_count") or 0)
        )
    except (TypeError, ValueError):
        discarded_execution_manual_review_candidate_count = 0
    discarded_execution_rescue_samples = list(discarded_execution_rescue_quality.get("samples") or [])[:10]
    discarded_execution_auto_requeue_samples = list(
        discarded_execution_rescue_quality.get("auto_requeue_samples") or []
    )[:10]
    discarded_execution_manual_review_samples = list(
        discarded_execution_rescue_quality.get("manual_review_samples") or []
    )[:10]
    discarded_execution_rescue_required = discarded_execution_auto_requeue_candidate_count > 0
    discarded_execution_manual_review_required = discarded_execution_manual_review_candidate_count > 0
    discarded_execution_rescue_budget = (
        max(30, min(200, int(discarded_execution_auto_requeue_candidate_count * 1.2)))
        if discarded_execution_rescue_required
        else 0
    )

    def quote_cli(value: object) -> str:
        text = str(value or "").replace('"', '\\"')
        return f'"{text}"'

    boost_category_args: List[str] = []
    boost_lens_args: List[str] = []
    boost_category_lens_args: List[str] = []

    def add_gap_boost_item(item: Any) -> None:
        if not isinstance(item, dict):
            return
        lane = str(item.get("category_lens") or item.get("lane") or "").strip()
        category = str(item.get("category") or "").strip()
        lens = str(item.get("lens") or "").strip().lower()
        if (not category or not lens) and "::" in lane:
            lane_category, _, lane_lens = lane.partition("::")
            category = category or lane_category.strip()
            lens = lens or lane_lens.strip().lower()
        elif not category and not lens and ":" in lane:
            lane_category, _, lane_lens = lane.rpartition(":")
            category = lane_category.strip()
            lens = lane_lens.strip().lower()
        elif lane and "::" not in lane and ":" not in lane and not category:
            category = lane

        if category and lens:
            category_lens = f"{category}::{lens}"
            if category_lens not in boost_category_lens_args:
                boost_category_lens_args.append(category_lens)
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)

    def add_gap_boost_items(items: Iterable[Any]) -> None:
        for item in list(items or [])[:5]:
            add_gap_boost_item(item)

    def add_quality_gap_boost_items(section: Dict[str, Any]) -> None:
        for key, value in (section or {}).items():
            if not isinstance(value, list):
                continue
            if key == "gaps" or key.endswith("_gaps"):
                add_gap_boost_items(value)

    for gap_items in (
        fresh_treatment_signature_gaps,
        treatment_signature_gaps,
        fresh_treatment_signal_diversity_gaps,
        treatment_signal_diversity_gaps,
        fresh_treatment_subintent_diversity_gaps,
        treatment_subintent_diversity_gaps,
        fresh_clinic_modality_gaps,
        clinic_modality_gaps,
        fresh_decision_window_gaps,
        decision_window_gaps,
        fresh_seed_candidate_alignment_gaps,
        seed_candidate_alignment_gaps,
        fresh_engagement_hook_gaps,
        engagement_hook_gaps,
        fresh_opportunity_diversity_gaps,
        opportunity_diversity_gaps,
        fresh_unique_work_queue_gaps,
        unique_work_queue_gaps,
        fresh_work_queue_gaps,
        work_queue_gaps,
        patient_journey_gaps,
        fresh_local_intent_gaps,
        local_intent_gaps,
        fresh_local_area_diversity_gaps,
        local_area_diversity_gaps,
        fresh_patient_surface_gaps,
        patient_surface_gaps,
        fresh_viral_action_route_gaps,
        viral_action_route_gaps,
        fresh_reply_workability_gaps,
        reply_workability_gaps,
        fresh_compliance_work_mode_gaps,
        compliance_work_mode_gaps,
        fresh_execution_readiness_gaps,
        execution_readiness_gaps,
        fresh_execution_priority_alignment_gaps,
        execution_priority_alignment_gaps,
    ):
        add_gap_boost_items(gap_items)
    for quality_section in (
        patient_journey_coverage,
        work_queue_readiness,
        opportunity_diversity,
        engagement_hook_quality,
        treatment_signature_quality,
        treatment_signal_diversity_quality,
        treatment_subintent_diversity_quality,
        clinic_modality_quality,
        decision_window_quality,
        seed_candidate_alignment_quality,
        local_intent_quality,
        local_area_diversity_quality,
        patient_surface_quality,
        viral_action_route_quality,
        reply_workability_quality,
        compliance_work_mode_quality,
        execution_readiness_quality,
        execution_priority_alignment_quality,
    ):
        add_quality_gap_boost_items(quality_section)

    for item in fresh_treatment_signature_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in treatment_signature_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in fresh_treatment_signal_diversity_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in treatment_signal_diversity_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in fresh_treatment_subintent_diversity_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in treatment_subintent_diversity_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in fresh_seed_candidate_alignment_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in seed_candidate_alignment_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in fresh_engagement_hook_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in engagement_hook_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in fresh_opportunity_diversity_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in opportunity_diversity_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in fresh_unique_work_queue_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in unique_work_queue_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in fresh_work_queue_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in work_queue_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in patient_journey_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in fresh_local_intent_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in local_intent_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in fresh_patient_surface_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in patient_surface_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in fresh_viral_action_route_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in viral_action_route_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in fresh_reply_workability_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in reply_workability_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in fresh_compliance_work_mode_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in compliance_work_mode_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in fresh_execution_readiness_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in execution_readiness_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in fresh_execution_priority_alignment_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in execution_priority_alignment_gaps[:5]:
        category = item.get("category")
        lens = item.get("lens")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in boost_categories[:5]:
        category = item.get("category")
        if category and category not in boost_category_args:
            boost_category_args.append(category)
    for item in boost_lenses[:5]:
        lens = item.get("lens")
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in boost_category_lenses[:5]:
        category_lens = str(item.get("category_lens") or "")
        category, _, lens = category_lens.partition("::")
        if category and lens and category_lens not in boost_category_lens_args:
            boost_category_lens_args.append(category_lens)
        if category and category not in boost_category_args:
            boost_category_args.append(category)
        if lens and lens not in boost_lens_args:
            boost_lens_args.append(lens)
    for item in reanalysis_rescue_samples[:5]:
        add_gap_boost_item(item)
    for item in discarded_execution_auto_requeue_samples[:5]:
        add_gap_boost_item(item)

    boost_args = [f"--boost-category {quote_cli(category)}" for category in boost_category_args[:5]]
    boost_args.extend(f"--boost-lens {quote_cli(lens)}" for lens in boost_lens_args[:5])
    boost_args.extend(f"--boost-category-lens {quote_cli(lane)}" for lane in boost_category_lens_args[:5])

    scan_command = "python viral_hunter.py --scan --fresh --top-n-for-ai 300 --ai-parallel 5"
    if source_scan_run_id:
        scan_command += f" --source-scan-id {int(source_scan_run_id)}"
    rescue_budget = max(reanalysis_rescue_budget, discarded_execution_rescue_budget)
    if rescue_budget:
        scan_command += f" --rescue-backlog {rescue_budget}"
    if boost_args:
        scan_command += " " + " ".join(boost_args)
    audit_command = "python scripts/viral_handoff_audit.py"
    if source_scan_run_id:
        audit_command += f" --scan-id {source_scan_run_id}"
    audit_command += " --days 1"
    audit_command += f" --sample-per-lane {max(1, int(sample_per_lane or 1))}"
    audit_out = (
        f"reports/viral_handoff_audit_scan{int(source_scan_run_id)}_days1.json"
        if source_scan_run_id
        else "reports/viral_handoff_audit_days1.json"
    )
    audit_command += f" --out {audit_out}"
    audit_current_template = "python scripts/viral_handoff_audit.py"
    if source_scan_run_id:
        audit_current_template += f" --scan-id {source_scan_run_id}"
    audit_current_template += ' --since "<RUN_STARTED_AT>"'
    audit_current_template += f" --sample-per-lane {max(1, int(sample_per_lane or 1))}"
    audit_current_out = (
        f"reports/viral_handoff_audit_scan{int(source_scan_run_id)}_current_run.json"
        if source_scan_run_id
        else "reports/viral_handoff_audit_current_run.json"
    )
    audit_current_template += f" --out {audit_current_out}"

    return {
        "rerun_required": bool(
            row_count == 0
            or metric_backfill_required
            or coverage_gap_required
            or content_coherence_required
            or lens_surface_required
            or source_seed_feedback_required
            or source_lineage_repair_required
            or variant_quality_feedback_required
            or filter_loss_required
            or patient_journey_required
            or work_queue_required
            or fresh_work_queue_required
            or unique_work_queue_required
            or fresh_unique_work_queue_required
            or opportunity_diversity_required
            or fresh_opportunity_diversity_required
            or engagement_hook_required
            or fresh_engagement_hook_required
            or treatment_signature_required
            or fresh_treatment_signature_required
            or treatment_signal_diversity_required
            or fresh_treatment_signal_diversity_required
            or treatment_subintent_diversity_required
            or fresh_treatment_subintent_diversity_required
            or clinic_modality_required
            or fresh_clinic_modality_required
            or decision_window_required
            or fresh_decision_window_required
            or seed_candidate_alignment_required
            or fresh_seed_candidate_alignment_required
            or local_intent_required
            or fresh_local_intent_required
            or local_area_diversity_required
            or fresh_local_area_diversity_required
            or patient_surface_required
            or fresh_patient_surface_required
            or viral_action_route_required
            or fresh_viral_action_route_required
            or reply_workability_required
            or fresh_reply_workability_required
            or compliance_work_mode_required
            or fresh_compliance_work_mode_required
            or execution_readiness_required
            or fresh_execution_readiness_required
            or execution_priority_alignment_required
            or fresh_execution_priority_alignment_required
            or platform_surface_required
            or reanalysis_rescue_required
            or discarded_execution_rescue_required
        ),
        "metric_backfill_required": metric_backfill_required,
        "metric_backfill_gaps": metric_backfill_gaps,
        "coverage_gap_required": coverage_gap_required,
        "content_coherence_required": content_coherence_required,
        "content_mismatch_lanes": content_mismatch_lanes,
        "lens_surface_required": lens_surface_required,
        "lens_surface_mismatch_lanes": lens_surface_mismatch_lanes,
        "source_seed_feedback_required": source_seed_feedback_required,
        "source_lineage_repair_required": source_lineage_repair_required,
        "source_lineage_gaps": source_lineage_gaps,
        "source_lineage_missing_samples": source_lineage_missing_samples,
        "variant_quality_feedback_required": variant_quality_feedback_required,
        "filter_loss_required": filter_loss_required,
        "filter_loss_hotspots": loss_hotspots,
        "patient_journey_required": patient_journey_required,
        "patient_journey_gaps": patient_journey_gaps,
        "work_queue_required": work_queue_required,
        "work_queue_gaps": work_queue_gaps,
        "fresh_work_queue_required": fresh_work_queue_required,
        "fresh_work_queue_gaps": fresh_work_queue_gaps,
        "unique_work_queue_required": unique_work_queue_required,
        "unique_work_queue_gaps": unique_work_queue_gaps,
        "fresh_unique_work_queue_required": fresh_unique_work_queue_required,
        "fresh_unique_work_queue_gaps": fresh_unique_work_queue_gaps,
        "opportunity_diversity_required": opportunity_diversity_required,
        "opportunity_diversity_gaps": opportunity_diversity_gaps,
        "fresh_opportunity_diversity_required": fresh_opportunity_diversity_required,
        "fresh_opportunity_diversity_gaps": fresh_opportunity_diversity_gaps,
        "engagement_hook_required": engagement_hook_required,
        "engagement_hook_gaps": engagement_hook_gaps,
        "fresh_engagement_hook_required": fresh_engagement_hook_required,
        "fresh_engagement_hook_gaps": fresh_engagement_hook_gaps,
        "treatment_signature_required": treatment_signature_required,
        "treatment_signature_gaps": treatment_signature_gaps,
        "fresh_treatment_signature_required": fresh_treatment_signature_required,
        "fresh_treatment_signature_gaps": fresh_treatment_signature_gaps,
        "treatment_signal_diversity_required": treatment_signal_diversity_required,
        "treatment_signal_diversity_gaps": treatment_signal_diversity_gaps,
        "fresh_treatment_signal_diversity_required": fresh_treatment_signal_diversity_required,
        "fresh_treatment_signal_diversity_gaps": fresh_treatment_signal_diversity_gaps,
        "treatment_subintent_diversity_required": treatment_subintent_diversity_required,
        "treatment_subintent_diversity_gaps": treatment_subintent_diversity_gaps,
        "fresh_treatment_subintent_diversity_required": fresh_treatment_subintent_diversity_required,
        "fresh_treatment_subintent_diversity_gaps": fresh_treatment_subintent_diversity_gaps,
        "clinic_modality_required": clinic_modality_required,
        "clinic_modality_gaps": clinic_modality_gaps,
        "fresh_clinic_modality_required": fresh_clinic_modality_required,
        "fresh_clinic_modality_gaps": fresh_clinic_modality_gaps,
        "decision_window_required": decision_window_required,
        "decision_window_gaps": decision_window_gaps,
        "fresh_decision_window_required": fresh_decision_window_required,
        "fresh_decision_window_gaps": fresh_decision_window_gaps,
        "seed_candidate_alignment_required": seed_candidate_alignment_required,
        "seed_candidate_alignment_gaps": seed_candidate_alignment_gaps,
        "fresh_seed_candidate_alignment_required": fresh_seed_candidate_alignment_required,
        "fresh_seed_candidate_alignment_gaps": fresh_seed_candidate_alignment_gaps,
        "local_intent_required": local_intent_required,
        "local_intent_gaps": local_intent_gaps,
        "fresh_local_intent_required": fresh_local_intent_required,
        "fresh_local_intent_gaps": fresh_local_intent_gaps,
        "local_area_diversity_required": local_area_diversity_required,
        "local_area_diversity_gaps": local_area_diversity_gaps,
        "fresh_local_area_diversity_required": fresh_local_area_diversity_required,
        "fresh_local_area_diversity_gaps": fresh_local_area_diversity_gaps,
        "patient_surface_required": patient_surface_required,
        "patient_surface_gaps": patient_surface_gaps,
        "fresh_patient_surface_required": fresh_patient_surface_required,
        "fresh_patient_surface_gaps": fresh_patient_surface_gaps,
        "viral_action_route_required": viral_action_route_required,
        "viral_action_route_gaps": viral_action_route_gaps,
        "fresh_viral_action_route_required": fresh_viral_action_route_required,
        "fresh_viral_action_route_gaps": fresh_viral_action_route_gaps,
        "reply_workability_required": reply_workability_required,
        "reply_workability_gaps": reply_workability_gaps,
        "fresh_reply_workability_required": fresh_reply_workability_required,
        "fresh_reply_workability_gaps": fresh_reply_workability_gaps,
        "compliance_work_mode_required": compliance_work_mode_required,
        "compliance_work_mode_gaps": compliance_work_mode_gaps,
        "fresh_compliance_work_mode_required": fresh_compliance_work_mode_required,
        "fresh_compliance_work_mode_gaps": fresh_compliance_work_mode_gaps,
        "execution_readiness_required": execution_readiness_required,
        "execution_readiness_gaps": execution_readiness_gaps,
        "fresh_execution_readiness_required": fresh_execution_readiness_required,
        "fresh_execution_readiness_gaps": fresh_execution_readiness_gaps,
        "execution_priority_alignment_required": execution_priority_alignment_required,
        "execution_priority_alignment_gaps": execution_priority_alignment_gaps,
        "fresh_execution_priority_alignment_required": fresh_execution_priority_alignment_required,
        "fresh_execution_priority_alignment_gaps": fresh_execution_priority_alignment_gaps,
        "platform_surface_required": platform_surface_required,
        "platform_surface_hotspots": platform_surface_hotspots,
        "reanalysis_rescue_required": reanalysis_rescue_required,
        "reanalysis_rescue_candidate_count": reanalysis_rescue_candidate_count,
        "reanalysis_rescue_priority_focus_candidate_count": reanalysis_rescue_priority_focus_candidate_count,
        "reanalysis_rescue_budget": reanalysis_rescue_budget,
        "reanalysis_rescue_samples": reanalysis_rescue_samples,
        "reanalysis_rescue_by_category": reanalysis_rescue_quality.get("by_category") or {},
        "reanalysis_rescue_by_lens": reanalysis_rescue_quality.get("by_lens") or {},
        "discarded_execution_rescue_required": discarded_execution_rescue_required,
        "discarded_execution_rescue_candidate_count": discarded_execution_rescue_candidate_count,
        "discarded_execution_rescue_priority_focus_candidate_count": (
            discarded_execution_rescue_priority_focus_candidate_count
        ),
        "discarded_execution_auto_requeue_candidate_count": (
            discarded_execution_auto_requeue_candidate_count
        ),
        "discarded_execution_manual_review_candidate_count": (
            discarded_execution_manual_review_candidate_count
        ),
        "discarded_execution_manual_review_required": discarded_execution_manual_review_required,
        "discarded_execution_rescue_budget": discarded_execution_rescue_budget,
        "discarded_execution_rescue_samples": discarded_execution_rescue_samples,
        "discarded_execution_auto_requeue_samples": discarded_execution_auto_requeue_samples,
        "discarded_execution_manual_review_samples": discarded_execution_manual_review_samples,
        "discarded_execution_rescue_by_category": discarded_execution_rescue_quality.get("by_category") or {},
        "discarded_execution_rescue_by_lens": discarded_execution_rescue_quality.get("by_lens") or {},
        "discarded_execution_rescue_by_status": discarded_execution_rescue_quality.get("by_status") or {},
        "discarded_execution_rescue_by_reject_reason": (
            discarded_execution_rescue_quality.get("by_reject_reason") or {}
        ),
        "discarded_execution_rescue_by_rescue_mode": (
            discarded_execution_rescue_quality.get("by_rescue_mode") or {}
        ),
        "boost_categories": boost_categories[:10],
        "boost_lenses": boost_lenses[:10],
        "boost_category_lenses": boost_category_lenses[:10],
        "source_seed_actions": source_seed_actions,
        "variant_actions": variant_actions,
        "review_before_scaling": review_before_scaling,
        "top_recommendation_codes": [item.get("code") for item in recommendations[:5]],
        "suggested_commands": {
            "live_scan": scan_command,
            "post_run_audit": audit_command,
            "post_run_audit_current_run_template": audit_current_template,
        },
    }


def _recommendations(
    *,
    row_count: int,
    overall: Dict[str, Any],
    weak_lanes: List[Dict[str, Any]],
    baseline: Dict[str, Any],
    seed_target_coverage: Dict[str, Any],
    quality_bar: Optional[Dict[str, Any]] = None,
    source_seed_feedback: Optional[Dict[str, Any]] = None,
    variant_quality_feedback: Optional[Dict[str, Any]] = None,
    loss_analysis: Optional[Dict[str, Any]] = None,
    patient_journey_coverage: Optional[Dict[str, Any]] = None,
    work_queue_readiness: Optional[Dict[str, Any]] = None,
    opportunity_diversity: Optional[Dict[str, Any]] = None,
    engagement_hook_quality: Optional[Dict[str, Any]] = None,
    treatment_signature_quality: Optional[Dict[str, Any]] = None,
    treatment_signal_diversity_quality: Optional[Dict[str, Any]] = None,
    treatment_subintent_diversity_quality: Optional[Dict[str, Any]] = None,
    clinic_modality_quality: Optional[Dict[str, Any]] = None,
    decision_window_quality: Optional[Dict[str, Any]] = None,
    seed_candidate_alignment_quality: Optional[Dict[str, Any]] = None,
    local_intent_quality: Optional[Dict[str, Any]] = None,
    local_area_diversity_quality: Optional[Dict[str, Any]] = None,
    patient_surface_quality: Optional[Dict[str, Any]] = None,
    viral_action_route_quality: Optional[Dict[str, Any]] = None,
    reply_workability_quality: Optional[Dict[str, Any]] = None,
    compliance_work_mode_quality: Optional[Dict[str, Any]] = None,
    execution_readiness_quality: Optional[Dict[str, Any]] = None,
    execution_priority_alignment_quality: Optional[Dict[str, Any]] = None,
    platform_surface_quality: Optional[Dict[str, Any]] = None,
    source_lineage_quality: Optional[Dict[str, Any]] = None,
    reanalysis_rescue_quality: Optional[Dict[str, Any]] = None,
    discarded_execution_rescue_quality: Optional[Dict[str, Any]] = None,
    top_n: int = 30,
) -> List[Dict[str, Any]]:
    recommendations: List[Dict[str, Any]] = []

    def add(priority: int, code: str, message: str, action: str, lanes: Optional[List[str]] = None) -> None:
        recommendations.append({
            "priority": priority,
            "code": code,
            "message": message,
            "action": action,
            "lanes": lanes or [],
        })

    seed_count = int(baseline.get("seed_count") or 0)
    quality_bar = quality_bar or {}
    source_seed_feedback = source_seed_feedback or {}
    variant_quality_feedback = variant_quality_feedback or {}
    loss_analysis = loss_analysis or {}
    patient_journey_coverage = patient_journey_coverage or {}
    work_queue_readiness = work_queue_readiness or {}
    opportunity_diversity = opportunity_diversity or {}
    engagement_hook_quality = engagement_hook_quality or {}
    treatment_signature_quality = treatment_signature_quality or {}
    treatment_signal_diversity_quality = treatment_signal_diversity_quality or {}
    treatment_subintent_diversity_quality = treatment_subintent_diversity_quality or {}
    clinic_modality_quality = clinic_modality_quality or {}
    decision_window_quality = decision_window_quality or {}
    seed_candidate_alignment_quality = seed_candidate_alignment_quality or {}
    local_intent_quality = local_intent_quality or {}
    local_area_diversity_quality = local_area_diversity_quality or {}
    patient_surface_quality = patient_surface_quality or {}
    viral_action_route_quality = viral_action_route_quality or {}
    reply_workability_quality = reply_workability_quality or {}
    compliance_work_mode_quality = compliance_work_mode_quality or {}
    execution_readiness_quality = execution_readiness_quality or {}
    execution_priority_alignment_quality = execution_priority_alignment_quality or {}
    platform_surface_quality = platform_surface_quality or {}
    source_lineage_quality = source_lineage_quality or {}
    reanalysis_rescue_quality = reanalysis_rescue_quality or {}
    discarded_execution_rescue_quality = discarded_execution_rescue_quality or {}
    recategorize_candidates = source_seed_feedback.get("recategorize_candidates") or []
    if row_count and quality_bar and quality_bar.get("tier") != "world_class":
        failed = list(quality_bar.get("failed_required_gates") or [])
        failed.extend(quality_bar.get("failed_advisory_gates") or [])
        add(
            96,
            "handoff_quality_bar_not_world_class",
            f"Pathfinder -> Viral Hunter handoff quality tier is {quality_bar.get('tier')} ({quality_bar.get('score')}/100).",
            "fix the failed quality gates before scaling the next Viral Hunter run",
            [f"gate:{name}" for name in failed[:8]],
        )

    if recategorize_candidates:
        add(
            90,
            "source_seed_category_drift",
            "Some Pathfinder source seeds appear to belong to a different treatment axis than their handoff category.",
            "recategorize or quarantine these source seeds before scaling the next Viral Hunter run",
            [
                f"source_seed:{item.get('category')}->{item.get('detected_category')}:{item.get('seed')}"
                for item in recategorize_candidates[:6]
            ],
        )

    source_lineage_overall = source_lineage_quality.get("overall") or {}
    source_lineage_targets = source_lineage_quality.get("targets") or {}
    if source_lineage_overall:
        source_lineage_seed_target = float(
            source_lineage_targets.get("source_seed_coverage_rate")
            or SOURCE_LINEAGE_MIN_SOURCE_SEED_COVERAGE
        )
        source_lineage_priority_seed_target = float(
            source_lineage_targets.get("priority_focus_source_seed_coverage_rate")
            or SOURCE_LINEAGE_MIN_PRIORITY_FOCUS_SOURCE_SEED_COVERAGE
        )
        source_lineage_actionable_seed_target = float(
            source_lineage_targets.get("actionable_strict_source_seed_coverage_rate")
            or SOURCE_LINEAGE_MIN_ACTIONABLE_STRICT_SOURCE_SEED_COVERAGE
        )
        source_lineage_query_variant_target = float(
            source_lineage_targets.get("query_variant_coverage_rate")
            or SOURCE_LINEAGE_MIN_QUERY_VARIANT_COVERAGE
        )
        source_lineage_priority_total = int(source_lineage_overall.get("priority_focus_total") or 0)
        source_lineage_actionable_total = int(source_lineage_overall.get("actionable_strict_total") or 0)
        source_lineage_priority_actionable_total = int(
            source_lineage_overall.get("priority_focus_actionable_strict_total") or 0
        )
        source_lineage_low = (
            float(source_lineage_overall.get("source_seed_coverage_rate") or 0.0)
            < source_lineage_seed_target
            or (
                source_lineage_priority_total
                and float(
                    source_lineage_overall.get("priority_focus_source_seed_coverage_rate")
                    or 0.0
                )
                < source_lineage_priority_seed_target
            )
            or (
                source_lineage_actionable_total
                and float(
                    source_lineage_overall.get("actionable_strict_source_seed_coverage_rate")
                    or 0.0
                )
                < source_lineage_actionable_seed_target
            )
            or (
                source_lineage_priority_actionable_total
                and float(
                    source_lineage_overall.get(
                        "priority_focus_actionable_strict_source_seed_coverage_rate"
                    )
                    or 0.0
                )
                < source_lineage_actionable_seed_target
            )
            or float(source_lineage_overall.get("query_variant_coverage_rate") or 0.0)
            < source_lineage_query_variant_target
        )
        if row_count and source_lineage_low:
            add(
                58,
                "source_lineage_coverage_low",
                "Some Viral Hunter targets lack explicit Pathfinder source-keyword or query-variant lineage.",
                "backfill pathfinder_source_keyword/pathfinder_source_keywords and preserve query variants before using these posts for viral work",
                [
                    (
                        f"{item.get('category')}::{item.get('lens')}:"
                        f"{','.join(item.get('reasons') or [])}:{item.get('title')}"
                    )
                    for item in (source_lineage_quality.get("missing_samples") or [])[:8]
                ],
            )

    variant_repair_or_retire = (
        list(variant_quality_feedback.get("retire_variants") or [])
        + list(variant_quality_feedback.get("repair_variants") or [])
        + list(variant_quality_feedback.get("retire_category_lens_variants") or [])
        + list(variant_quality_feedback.get("repair_category_lens_variants") or [])
        + list(variant_quality_feedback.get("retire_families") or [])
        + list(variant_quality_feedback.get("repair_families") or [])
    )
    if variant_repair_or_retire:
        add(
            89,
            "query_variant_quality_feedback",
            "Some Pathfinder query variants or variant families generate volume but do not convert into strict-fit Viral Hunter targets.",
            "repair or pause weak query variants before scaling; keep high-yield variants as the next-run expansion template",
            [
                (
                    f"{item.get('type')}:{item.get('category_lens') or '-'}:"
                    f"{item.get('variant') or item.get('family')}:"
                    f"{item.get('action')}:{item.get('strict_fit')}/{item.get('total')}"
                )
                for item in variant_repair_or_retire[:8]
            ],
        )

    priority_focus_loss_hotspots = loss_analysis.get("priority_focus_hotspots") or []
    if priority_focus_loss_hotspots:
        add(
            89,
            "priority_focus_filter_loss_hotspots",
            "Some Gyulim priority treatment axes are losing too many discovered targets to specific filter statuses.",
            "inspect the dominant loss reasons and repair the corresponding filters, freshness windows, or fit gates before scaling",
            [
                f"{item.get('type')}:{item.get('lane')}:{item.get('dominant_loss_reason')}"
                for item in priority_focus_loss_hotspots[:8]
            ],
        )

    reanalysis_rescue_overall = reanalysis_rescue_quality.get("overall") or {}
    reanalysis_rescue_candidates = int(reanalysis_rescue_overall.get("candidate_count") or 0)
    if reanalysis_rescue_candidates:
        add(
            90,
            "reanalysis_rescue_backlog",
            "Some recently resurfaced high-fit targets are still stored as filtered_out without an explicit reject reason.",
            "send these targets through the Viral Hunter reanalysis rescue lane before judging the handoff as production-ready",
            [
                f"{item.get('category')}::{item.get('lens')}:{item.get('title')}"
                for item in (reanalysis_rescue_quality.get("samples") or [])[:8]
            ],
        )

    discarded_execution_rescue_overall = discarded_execution_rescue_quality.get("overall") or {}
    discarded_execution_rescue_candidates = int(
        discarded_execution_rescue_overall.get("candidate_count") or 0
    )
    if discarded_execution_rescue_candidates:
        auto_requeue_count = int(
            discarded_execution_rescue_overall.get("auto_requeue_candidate_count") or 0
        )
        manual_review_count = int(
            discarded_execution_rescue_overall.get("manual_review_candidate_count") or 0
        )
        add(
            96,
            "discarded_execution_rescue_backlog",
            (
                "Some non-actionable Viral Hunter rows look ready for execution except for "
                f"their discard/filter status (auto={auto_requeue_count}, manual={manual_review_count})."
            ),
            (
                "requeue auto_requeue rows through rescue-backlog, and review manual rows "
                "separately before repairing filters or broadening Pathfinder seeds"
            ),
            [
                (
                    f"{item.get('rescue_mode')}:{item.get('status')}:"
                    f"{item.get('current_reject_reason') or '-'}:"
                    f"{item.get('category')}::{item.get('lens')}:{item.get('title')}"
                )
                for item in (discarded_execution_rescue_quality.get("samples") or [])[:8]
            ],
        )

    patient_journey_gaps = patient_journey_coverage.get("priority_focus_gaps") or []
    if patient_journey_gaps:
        add(
            88,
            "patient_journey_coverage_gaps",
            "Some Gyulim priority treatment axes lack strict-fit Viral Hunter targets for key patient journey lenses.",
            "boost the missing category/lens pairs and inspect whether Pathfinder insights preserve patient intent through Viral Hunter search",
            [
                f"{item.get('category')}::{item.get('lens')}:{','.join(item.get('reasons') or [])}"
                for item in patient_journey_gaps[:8]
            ],
        )

    work_queue_gaps = work_queue_readiness.get("priority_gaps") or []
    if work_queue_gaps:
        add(
            88,
            "work_queue_depth_gaps",
            "Some Gyulim priority treatment axes do not have enough actionable strict-fit inventory for repeated viral work.",
            "build more work-ready target depth for these category/lens queues before increasing production volume",
            [
                f"{item.get('lane')}:{item.get('actionable_strict')}/{item.get('target')}:{','.join(item.get('reasons') or [])}"
                for item in work_queue_gaps[:8]
            ],
        )

    fresh_work_queue_gaps = work_queue_readiness.get("fresh_priority_gaps") or []
    if fresh_work_queue_gaps:
        add(
            88,
            "fresh_work_queue_depth_gaps",
            "Some Gyulim priority treatment queues lack enough fresh actionable strict-fit targets.",
            "refresh or rediscover these category/lens queues before assigning them to viral production",
            [
                f"{item.get('lane')}:{item.get('fresh_actionable_strict')}/{item.get('target')}:{','.join(item.get('reasons') or [])}"
                for item in fresh_work_queue_gaps[:8]
            ],
        )

    unique_work_queue_gaps = work_queue_readiness.get("unique_priority_gaps") or []
    if unique_work_queue_gaps:
        add(
            89,
            "unique_work_queue_depth_gaps",
            "Some Gyulim priority queues are inflated by duplicate or near-duplicate actionable strict-fit targets.",
            "deduplicate the work queue and rediscover distinct patient-surface posts for these category/lens lanes",
            [
                f"{item.get('lane')}:{item.get('unique_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in unique_work_queue_gaps[:8]
            ],
        )

    fresh_unique_work_queue_gaps = work_queue_readiness.get("fresh_unique_priority_gaps") or []
    if fresh_unique_work_queue_gaps:
        add(
            89,
            "fresh_unique_work_queue_depth_gaps",
            "Some Gyulim priority queues lack enough fresh distinct actionable strict-fit targets.",
            "refresh these lanes with new URLs/titles instead of reusing duplicate inventory",
            [
                f"{item.get('lane')}:{item.get('unique_fresh_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_unique_work_queue_gaps[:8]
            ],
        )

    opportunity_diversity_gaps = opportunity_diversity.get("priority_gaps") or []
    if opportunity_diversity_gaps:
        add(
            89,
            "opportunity_diversity_gaps",
            "Some Gyulim priority queues depend on too few platforms, Pathfinder source seeds, or query families.",
            "expand these lanes with independent source seeds and discovery surfaces before assigning repeat viral work",
            [
                f"{item.get('lane')}:{item.get('platform_count')}p/"
                f"{item.get('source_seed_count')}s/{item.get('variant_family_count')}v:"
                f"{','.join(item.get('reasons') or [])}"
                for item in opportunity_diversity_gaps[:8]
            ],
        )

    fresh_opportunity_diversity_gaps = opportunity_diversity.get("fresh_priority_gaps") or []
    if fresh_opportunity_diversity_gaps:
        add(
            89,
            "fresh_opportunity_diversity_gaps",
            "Some Gyulim priority queues lack fresh independent opportunities across platforms, source seeds, or query families.",
            "refresh these lanes from additional surfaces and Pathfinder seed clusters, not just the same source pattern",
            [
                f"{item.get('lane')}:{item.get('platform_count')}p/"
                f"{item.get('source_seed_count')}s/{item.get('variant_family_count')}v:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_opportunity_diversity_gaps[:8]
            ],
        )

    engagement_hook_gaps = engagement_hook_quality.get("priority_gaps") or []
    if engagement_hook_gaps:
        add(
            90,
            "engagement_hook_gaps",
            "Some Gyulim priority queues have strict-fit targets but too few posts with a reply-worthy patient intent hook.",
            "rediscover or reprioritize posts that contain recommendation, cost, consultation, booking, or safety-concern signals",
            [
                f"{item.get('lane')}:{item.get('hooked_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in engagement_hook_gaps[:8]
            ],
        )

    fresh_engagement_hook_gaps = engagement_hook_quality.get("fresh_priority_gaps") or []
    if fresh_engagement_hook_gaps:
        add(
            90,
            "fresh_engagement_hook_gaps",
            "Some Gyulim priority queues lack fresh posts with a usable patient intent hook.",
            "refresh these lanes with recent question, recommendation, cost, consultation, booking, and safety-concern posts",
            [
                f"{item.get('lane')}:{item.get('fresh_hooked_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_engagement_hook_gaps[:8]
            ],
        )

    local_intent_gaps = [
        item for item in (local_intent_quality.get("priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("local_intent_missing") or 0) > 0
    ]
    if local_intent_gaps:
        add(
            92,
            "local_intent_gaps",
            "Some Gyulim priority queues have strict-fit targets that do not show a Cheongju-area local anchor.",
            "rediscover or reprioritize posts whose title/body contains Cheongju, district, neighborhood, or nearby-region terms",
            [
                f"{item.get('lane')}:{item.get('local_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in local_intent_gaps[:8]
            ],
        )

    fresh_local_intent_gaps = [
        item for item in (local_intent_quality.get("fresh_priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("local_intent_missing") or 0) > 0
    ]
    if fresh_local_intent_gaps:
        add(
            92,
            "fresh_local_intent_gaps",
            "Some Gyulim priority queues lack fresh work-ready posts with a Cheongju-area local anchor.",
            "refresh these lanes with recent posts that explicitly mention Cheongju, districts, neighborhoods, or nearby regions",
            [
                f"{item.get('lane')}:{item.get('fresh_local_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_local_intent_gaps[:8]
            ],
        )

    local_area_diversity_gaps = [
        item for item in (local_area_diversity_quality.get("priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("local_area_count") or 0) < int(item.get("min_local_areas") or 1)
    ]
    if local_area_diversity_gaps:
        add(
            57,
            "local_area_diversity_gaps",
            "Some Gyulim priority queues depend on too few independent Cheongju-area anchors.",
            "expand Pathfinder seed clusters and Viral Hunter queries across Cheongju districts, neighborhoods, and nearby-region modifiers before assigning repeat viral work",
            [
                f"{item.get('lane')}:{item.get('local_area_count')}/{item.get('min_local_areas')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in local_area_diversity_gaps[:8]
            ],
        )

    fresh_local_area_diversity_gaps = [
        item for item in (local_area_diversity_quality.get("fresh_priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("local_area_count") or 0) < int(item.get("min_local_areas") or 1)
    ]
    if fresh_local_area_diversity_gaps:
        add(
            57,
            "fresh_local_area_diversity_gaps",
            "Some Gyulim priority queues lack fresh work-ready posts from diverse Cheongju-area anchors.",
            "refresh these lanes with distinct recent posts from additional Cheongju districts, neighborhoods, and nearby regions",
            [
                f"{item.get('lane')}:{item.get('local_area_count')}/{item.get('min_local_areas')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_local_area_diversity_gaps[:8]
            ],
        )

    patient_surface_gaps = [
        item for item in (patient_surface_quality.get("priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and (
            int(item.get("patient_surface_missing") or 0) > 0
            or int(item.get("provider_surface_noise") or 0) > 0
        )
    ]
    if patient_surface_gaps:
        add(
            93,
            "patient_surface_authenticity_gaps",
            "Some Gyulim priority queues have strict-fit targets that look like provider promo or non-patient surfaces.",
            "rediscover or reprioritize patient-authored questions, reviews, recommendation asks, and concern posts before assigning viral work",
            [
                f"{item.get('lane')}:{item.get('patient_surface_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in patient_surface_gaps[:8]
            ],
        )

    fresh_patient_surface_gaps = [
        item for item in (patient_surface_quality.get("fresh_priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and (
            int(item.get("patient_surface_missing") or 0) > 0
            or int(item.get("provider_surface_noise") or 0) > 0
        )
    ]
    if fresh_patient_surface_gaps:
        add(
            93,
            "fresh_patient_surface_authenticity_gaps",
            "Some Gyulim priority queues lack fresh work-ready patient-authored surfaces.",
            "refresh these lanes with recent patient questions, reviews, recommendation asks, and concern posts rather than provider promo",
            [
                f"{item.get('lane')}:{item.get('fresh_patient_surface_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_patient_surface_gaps[:8]
            ],
        )

    viral_action_route_gaps = [
        item for item in (viral_action_route_quality.get("priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("routed_actionable_strict") or 0) < int(item.get("target") or 0)
    ]
    if viral_action_route_gaps:
        add(
            94,
            "viral_action_route_gaps",
            "Some Gyulim priority queues have strict-fit patient targets but no clear viral action route.",
            "rediscover or reprioritize posts whose wording exposes a recommendation, experience, cost, consultation, booking, or safety route",
            [
                f"{item.get('lane')}:{item.get('routed_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in viral_action_route_gaps[:8]
            ],
        )

    fresh_viral_action_route_gaps = [
        item for item in (viral_action_route_quality.get("fresh_priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("fresh_routed_actionable_strict") or 0) < int(item.get("target") or 0)
    ]
    if fresh_viral_action_route_gaps:
        add(
            94,
            "fresh_viral_action_route_gaps",
            "Some Gyulim priority queues lack fresh targets with a clear viral action route.",
            "refresh these lanes with recent posts that show the exact entry route for the viral writer",
            [
                f"{item.get('lane')}:{item.get('fresh_routed_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_viral_action_route_gaps[:8]
            ],
        )

    reply_workability_gaps = [
        item for item in (reply_workability_quality.get("priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("reply_workable_actionable_strict") or 0) < int(item.get("target") or 0)
    ]
    if reply_workability_gaps:
        add(
            95,
            "reply_workability_gaps",
            "Some Gyulim priority queues have strict-fit routed targets that are not safe or useful enough for public reply work.",
            "rediscover or reprioritize posts with high reply opportunity, low answer saturation, and no medical guardrail risk flags",
            [
                f"{item.get('lane')}:{item.get('reply_workable_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in reply_workability_gaps[:8]
            ],
        )

    fresh_reply_workability_gaps = [
        item for item in (reply_workability_quality.get("fresh_priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("fresh_reply_workable_actionable_strict") or 0) < int(item.get("target") or 0)
    ]
    if fresh_reply_workability_gaps:
        add(
            95,
            "fresh_reply_workability_gaps",
            "Some Gyulim priority queues lack fresh targets that are ready for safe public reply work.",
            "refresh these lanes with recent unanswered or low-response posts that have strong reply opportunity and no risk flags",
            [
                f"{item.get('lane')}:{item.get('fresh_reply_workable_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_reply_workability_gaps[:8]
            ],
        )

    compliance_work_mode_gaps = [
        item for item in (compliance_work_mode_quality.get("priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("auto_work_ready_actionable_strict") or 0) < int(item.get("target") or 0)
    ]
    if compliance_work_mode_gaps:
        add(
            96,
            "compliance_work_mode_gaps",
            "Some strict-fit Gyulim queues overstate usable inventory because targets require manual review or compliance escalation.",
            "rediscover or reprioritize posts that are auto-work-ready: clear patient need, no medical guardrail flags, and strong reply opportunity",
            [
                f"{item.get('lane')}:{item.get('auto_work_ready_actionable_strict')}/{item.get('target')}:"
                f"manual={item.get('manual_review_only_actionable_strict')}:"
                f"blocked={item.get('blocked_or_escalate_actionable_strict')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in compliance_work_mode_gaps[:8]
            ],
        )

    fresh_compliance_work_mode_gaps = [
        item for item in (compliance_work_mode_quality.get("fresh_priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("fresh_auto_work_ready_actionable_strict") or 0) < int(item.get("target") or 0)
    ]
    if fresh_compliance_work_mode_gaps:
        add(
            96,
            "fresh_compliance_work_mode_gaps",
            "Some fresh strict-fit Gyulim queues lack enough posts that are ready for direct, compliant viral work.",
            "refresh these lanes with recent patient-authored posts that avoid testimonial, urgent-medical, or prescription-advice risk flags",
            [
                f"{item.get('lane')}:{item.get('fresh_auto_work_ready_actionable_strict')}/{item.get('target')}:"
                f"manual={item.get('manual_review_only_actionable_strict')}:"
                f"blocked={item.get('blocked_or_escalate_actionable_strict')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_compliance_work_mode_gaps[:8]
            ],
        )

    execution_readiness_gaps = [
        item for item in (execution_readiness_quality.get("priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("execution_ready_actionable_strict") or 0) < int(item.get("target") or 0)
    ]
    if execution_readiness_gaps:
        add(
            97,
            "execution_readiness_gaps",
            "Some Gyulim priority queues have component-level signals but too few single posts that are ready for Viral Hunter execution.",
            "rediscover or reprioritize posts where local intent, patient surface, treatment signal, viral route, and reply workability all appear together",
            [
                f"{item.get('lane')}:{item.get('execution_ready_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in execution_readiness_gaps[:8]
            ],
        )

    fresh_execution_readiness_gaps = [
        item for item in (execution_readiness_quality.get("fresh_priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("fresh_execution_ready_actionable_strict") or 0) < int(item.get("target") or 0)
    ]
    if fresh_execution_readiness_gaps:
        add(
            97,
            "fresh_execution_readiness_gaps",
            "Some Gyulim priority queues lack fresh single-post targets that are ready for Viral Hunter execution.",
            "refresh these lanes with recent posts that combine local intent, patient surface, treatment signal, viral route, and safe reply opportunity",
            [
                f"{item.get('lane')}:{item.get('fresh_execution_ready_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_execution_readiness_gaps[:8]
            ],
        )

    execution_priority_alignment_gaps = [
        item for item in (execution_priority_alignment_quality.get("priority_gaps") or [])
        if int(item.get("execution_ready_actionable_strict") or 0) >= int(item.get("target") or 0)
        and int(item.get("top_execution_ready_actionable_strict") or 0) < int(item.get("target") or 0)
    ]
    if execution_priority_alignment_gaps:
        add(
            98,
            "execution_priority_alignment_gaps",
            "Some Gyulim priority queues have execution-ready posts, but the priority score buries them below non-ready targets.",
            "raise the ranking weight for combined local, patient, treatment, route, and reply-readiness signals before scaling Viral Hunter",
            [
                f"{item.get('lane')}:top{item.get('priority_top_window')}="
                f"{item.get('top_execution_ready_actionable_strict')}/{item.get('target')}:"
                f"ready={item.get('execution_ready_actionable_strict')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in execution_priority_alignment_gaps[:8]
            ],
        )

    fresh_execution_priority_alignment_gaps = [
        item for item in (execution_priority_alignment_quality.get("fresh_priority_gaps") or [])
        if int(item.get("fresh_execution_ready_actionable_strict") or 0) >= int(item.get("target") or 0)
        and int(item.get("fresh_top_execution_ready_actionable_strict") or 0) < int(item.get("target") or 0)
    ]
    if fresh_execution_priority_alignment_gaps:
        add(
            98,
            "fresh_execution_priority_alignment_gaps",
            "Some Gyulim priority queues have fresh execution-ready posts, but priority ranking does not surface them early enough.",
            "boost recent all-in-one execution-ready signals in the priority formula and demote fragmented or risky posts",
            [
                f"{item.get('lane')}:top{item.get('priority_top_window')}="
                f"{item.get('fresh_top_execution_ready_actionable_strict')}/{item.get('target')}:"
                f"fresh_ready={item.get('fresh_execution_ready_actionable_strict')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_execution_priority_alignment_gaps[:8]
            ],
        )

    treatment_signature_gaps = [
        item for item in (treatment_signature_quality.get("priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("treatment_signature_missing") or 0) > 0
    ]
    if treatment_signature_gaps:
        add(
            91,
            "treatment_signature_gaps",
            "Some Gyulim priority queues have strict-fit targets that do not clearly mention the concrete treatment axis.",
            "rediscover or reprioritize posts whose title/body contains the category's actual treatment terms, not just generic clinic intent",
            [
                f"{item.get('lane')}:{item.get('signature_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in treatment_signature_gaps[:8]
            ],
        )

    fresh_treatment_signature_gaps = [
        item for item in (treatment_signature_quality.get("fresh_priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("treatment_signature_missing") or 0) > 0
    ]
    if fresh_treatment_signature_gaps:
        add(
            91,
            "fresh_treatment_signature_gaps",
            "Some Gyulim priority queues lack fresh work-ready posts that mention the concrete treatment axis.",
            "refresh these lanes with recent posts carrying scar, asymmetry, acne, diet, posture, lifting, or accident-specific terms",
            [
                f"{item.get('lane')}:{item.get('fresh_signature_actionable_strict')}/{item.get('target')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_treatment_signature_gaps[:8]
            ],
        )

    treatment_signal_diversity_gaps = [
        item for item in (treatment_signal_diversity_quality.get("priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("treatment_signal_diversity_gap") or 0) > 0
    ]
    if treatment_signal_diversity_gaps:
        add(
            92,
            "treatment_signal_diversity_gaps",
            "Some Gyulim priority queues have treatment-fit targets but their concrete treatment signals are too narrow.",
            "expand Pathfinder seed clusters and Viral Hunter query variants so scar, asymmetry, acne, diet, posture, lifting, and accident sub-intents survive into the work queue",
            [
                f"{item.get('lane')}:{item.get('distinct_treatment_signal_terms')}/"
                f"{item.get('min_distinct_treatment_signal_terms')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in treatment_signal_diversity_gaps[:8]
            ],
        )

    fresh_treatment_signal_diversity_gaps = [
        item for item in (treatment_signal_diversity_quality.get("fresh_priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("treatment_signal_diversity_gap") or 0) > 0
    ]
    if fresh_treatment_signal_diversity_gaps:
        add(
            92,
            "fresh_treatment_signal_diversity_gaps",
            "Some Gyulim priority queues lack fresh work-ready posts with diverse concrete treatment signals.",
            "refresh these lanes with recent posts that cover multiple sub-problems inside the same treatment axis, not only one repeated keyword",
            [
                f"{item.get('lane')}:{item.get('distinct_treatment_signal_terms')}/"
                f"{item.get('min_distinct_treatment_signal_terms')}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_treatment_signal_diversity_gaps[:8]
            ],
        )

    treatment_subintent_diversity_gaps = [
        item for item in (treatment_subintent_diversity_quality.get("priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("treatment_subintent_diversity_gap") or 0) > 0
    ]
    if treatment_subintent_diversity_gaps:
        add(
            57,
            "treatment_subintent_diversity_gaps",
            "Some Gyulim priority queues have enough treatment keywords, but the patient sub-problems collapse into too few buckets.",
            "expand Pathfinder seed clusters and Viral Hunter queries across scar, asymmetry, skin, diet, posture, lifting, and accident sub-problem buckets before assigning repeat viral work",
            [
                f"{item.get('lane')}:{item.get('distinct_treatment_subintent_buckets')}/"
                f"{item.get('min_distinct_treatment_subintent_buckets')}:"
                f"{','.join(item.get('treatment_subintent_buckets') or [])}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in treatment_subintent_diversity_gaps[:8]
            ],
        )

    fresh_treatment_subintent_diversity_gaps = [
        item for item in (treatment_subintent_diversity_quality.get("fresh_priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("treatment_subintent_diversity_gap") or 0) > 0
    ]
    if fresh_treatment_subintent_diversity_gaps:
        add(
            57,
            "fresh_treatment_subintent_diversity_gaps",
            "Some fresh Gyulim priority queues repeat the same patient sub-problem even though the treatment signal count looks healthy.",
            "refresh these lanes with recent posts from different sub-problem buckets, not just synonyms of one high-volume keyword",
            [
                f"{item.get('lane')}:{item.get('distinct_treatment_subintent_buckets')}/"
                f"{item.get('min_distinct_treatment_subintent_buckets')}:"
                f"{','.join(item.get('treatment_subintent_buckets') or [])}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_treatment_subintent_diversity_gaps[:8]
            ],
        )

    clinic_modality_gaps = [
        item for item in (clinic_modality_quality.get("priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and (
            int(item.get("clinic_modality_fit_actionable_strict") or 0)
            < int(item.get("target") or 0)
            or int(item.get("offscope_modality_noise") or 0) > 0
        )
    ]
    if clinic_modality_gaps:
        add(
            57,
            "clinic_modality_fit_gaps",
            "Some Gyulim priority queues contain strict-fit targets that point to non-Gyulim modalities such as dermatology, cosmetic surgery, or drug-only diet paths.",
            "rediscover or reprioritize posts that either mention Korean-medicine/Gyulim modalities or clearly compare outside options against a Korean-medicine alternative",
            [
                f"{item.get('lane')}:{item.get('clinic_modality_fit_actionable_strict')}/"
                f"{item.get('target')}:offscope={item.get('offscope_modality_noise')}:"
                f"{','.join(item.get('clinic_modality_offscope_terms') or [])}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in clinic_modality_gaps[:8]
            ],
        )

    fresh_clinic_modality_gaps = [
        item for item in (clinic_modality_quality.get("fresh_priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and (
            int(item.get("fresh_clinic_modality_fit_actionable_strict") or 0)
            < int(item.get("target") or 0)
            or int(item.get("offscope_modality_noise") or 0) > 0
        )
    ]
    if fresh_clinic_modality_gaps:
        add(
            57,
            "fresh_clinic_modality_fit_gaps",
            "Some fresh Gyulim priority queues contain work-ready-looking posts centered on non-Gyulim modalities.",
            "refresh these lanes with recent posts that preserve scar, asymmetry, acne, diet, posture, lifting, or accident intent while staying compatible with Korean-medicine treatment routes",
            [
                f"{item.get('lane')}:{item.get('fresh_clinic_modality_fit_actionable_strict')}/"
                f"{item.get('target')}:offscope={item.get('offscope_modality_noise')}:"
                f"{','.join(item.get('clinic_modality_offscope_terms') or [])}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_clinic_modality_gaps[:8]
            ],
        )

    decision_window_gaps = [
        item for item in (decision_window_quality.get("priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and (
            int(item.get("active_decision_actionable_strict") or 0)
            < int(item.get("target") or 0)
            or int(item.get("completed_decision_window_noise") or 0) > 0
        )
    ]
    if decision_window_gaps:
        add(
            57,
            "decision_window_gaps",
            "Some Gyulim priority queues contain strict-fit targets that look completed, booked, or retrospective rather than still in an actionable decision window.",
            "rediscover or reprioritize posts with current recommendation, cost, consultation, booking, comparison, or concern wording before assigning viral work",
            [
                f"{item.get('lane')}:{item.get('active_decision_actionable_strict')}/"
                f"{item.get('target')}:completed={item.get('completed_decision_window_noise')}:"
                f"{','.join(item.get('decision_window_completed_terms') or [])}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in decision_window_gaps[:8]
            ],
        )

    fresh_decision_window_gaps = [
        item for item in (decision_window_quality.get("fresh_priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and (
            int(item.get("fresh_active_decision_actionable_strict") or 0)
            < int(item.get("target") or 0)
            or int(item.get("completed_decision_window_noise") or 0) > 0
        )
    ]
    if fresh_decision_window_gaps:
        add(
            57,
            "fresh_decision_window_gaps",
            "Some fresh Gyulim priority queues are inflated by recent-looking posts that are already completed or booked.",
            "refresh these lanes with unresolved current questions, comparison requests, cost inquiries, consultation asks, and booking-intent posts",
            [
                f"{item.get('lane')}:{item.get('fresh_active_decision_actionable_strict')}/"
                f"{item.get('target')}:completed={item.get('completed_decision_window_noise')}:"
                f"{','.join(item.get('decision_window_completed_terms') or [])}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_decision_window_gaps[:8]
            ],
        )

    seed_candidate_alignment_gaps = [
        item for item in (seed_candidate_alignment_quality.get("priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("seed_candidate_alignment_missing") or 0) > 0
    ]
    if seed_candidate_alignment_gaps:
        add(
            93,
            "seed_candidate_alignment_gaps",
            "Some Gyulim targets are strict-fit posts, but the candidate text does not preserve Pathfinder's source-keyword intent.",
            "tighten source keyword to query-variant handoff and demote candidates that only match generic local or clinic terms",
            [
                f"{item.get('lane')}:{item.get('seed_aligned_actionable_strict')}/{item.get('target')}:"
                f"missing={','.join(item.get('seed_candidate_missing_terms') or [])}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in seed_candidate_alignment_gaps[:8]
            ],
        )

    fresh_seed_candidate_alignment_gaps = [
        item for item in (seed_candidate_alignment_quality.get("fresh_priority_gaps") or [])
        if int(item.get("unique_actionable_strict") or 0) > 0
        and int(item.get("seed_candidate_alignment_missing") or 0) > 0
    ]
    if fresh_seed_candidate_alignment_gaps:
        add(
            93,
            "fresh_seed_candidate_alignment_gaps",
            "Some fresh Gyulim targets are usable on paper, but recent candidates do not carry the Pathfinder source-keyword intent.",
            "refresh these lanes with recent posts whose title/body keeps the exact sub-intent terms from the seed cluster",
            [
                f"{item.get('lane')}:{item.get('fresh_seed_aligned_actionable_strict')}/{item.get('target')}:"
                f"missing={','.join(item.get('seed_candidate_missing_terms') or [])}:"
                f"{','.join(item.get('reasons') or [])}"
                for item in fresh_seed_candidate_alignment_gaps[:8]
            ],
        )

    priority_focus_platform_hotspots = platform_surface_quality.get("priority_focus_hotspots") or []
    if priority_focus_platform_hotspots:
        add(
            88,
            "priority_focus_platform_surface_hotspots",
            "Some Gyulim priority treatment axes are failing on specific Viral Hunter discovery surfaces.",
            "inspect the platform/category hotspots and adjust surface mix, query variants, or platform-specific filters before scaling",
            [
                f"{item.get('platform')}::{item.get('category')}:{','.join(item.get('reasons') or [])}"
                for item in priority_focus_platform_hotspots[:8]
            ],
        )

    if (
        int(overall.get("content_category_observed") or 0) > 0
        and float(overall.get("content_category_mismatch_rate") or 0.0) > 0.05
    ):
        mismatch_lanes = [
            f"{lane.get('type')}:{lane.get('lane')}"
            for lane in _weak_lanes_for_reason(
                weak_lanes,
                "content_category_mismatch",
                limit=8,
            )
        ]
        add(
            89,
            "content_category_mismatch",
            "Some discovered posts appear to discuss a different treatment axis than their handoff category.",
            "inspect content-mismatch samples and tighten post-fit or recategorization rules before scaling",
            mismatch_lanes[:8],
        )

    if (
        int(overall.get("lens_surface_checked") or 0) > 0
        and float(overall.get("lens_surface_mismatch_rate") or 0.0) > 0.20
    ):
        mismatch_lanes = [
            f"{lane.get('type')}:{lane.get('lane')}"
            for lane in _weak_lanes_for_reason(
                weak_lanes,
                "lens_surface_mismatch",
                limit=8,
            )
        ]
        add(
            88,
            "lens_surface_mismatch",
            "Some discovered posts do not show the patient surface intended by Pathfinder's execution lens.",
            "tighten lens-specific query variants and inspect lens-surface mismatch samples before scaling",
            mismatch_lanes[:8],
        )

    if seed_count and row_count == 0:
        add(
            100,
            "no_viral_targets_for_seed_scan",
            f"Pathfinder has {seed_count} seeds but Viral Hunter has no stored targets for this scan.",
            "run Viral Hunter live for this Pathfinder scan, then rerun this audit",
        )

    missing_categories = baseline.get("missing_seed_categories_in_targets") or []
    if missing_categories:
        add(
            92,
            "missing_seed_categories_in_targets",
            "Some Pathfinder treatment axes produced no Viral Hunter targets.",
            "increase or verify search execution for the missing treatment axes",
            [f"category:{category}" for category in missing_categories],
        )

    missing_lenses = baseline.get("missing_seed_lenses_in_targets") or []
    if missing_lenses:
        add(
            88,
            "missing_seed_lenses_in_targets",
            "Some Pathfinder execution lenses produced no Viral Hunter targets.",
            "check lens query variants and checkpoint freshness for the missing lenses",
            [f"lens:{lens}" for lens in missing_lenses],
        )

    missing_category_lenses = baseline.get("missing_seed_category_lenses_in_targets") or []
    if missing_category_lenses:
        add(
            84,
            "missing_seed_category_lenses_in_targets",
            "Some Pathfinder treatment-axis/execution-lens combinations produced no Viral Hunter targets.",
            "boost the affected category and lens together, then inspect whether query variants preserve the seed's specific patient vocabulary",
            [f"category_lens:{lane}" for lane in missing_category_lenses[:8]],
        )

    for lane_type, code, priority in (
        ("by_category", "undercovered_seed_categories", 86),
        ("by_category_lens", "undercovered_seed_category_lenses", 84),
        ("by_lens", "undercovered_seed_lenses", 82),
    ):
        undercovered_pairs = [
            (lane, metrics)
            for lane, metrics in (seed_target_coverage.get(lane_type) or {}).items()
            if metrics.get("gap_reasons")
        ]
        if lane_type == "by_category":
            undercovered_pairs.sort(key=lambda item: _category_priority_sort_key(item[0]))
        elif lane_type == "by_category_lens":
            undercovered_pairs.sort(key=lambda item: _category_lens_priority_sort_key(item[0]))
        elif lane_type == "by_lens":
            undercovered_pairs.sort(key=lambda item: _lens_priority_sort_key(item[0]))
        undercovered = [
            f"{lane_type.removeprefix('by_')}:{lane}"
            for lane, _ in undercovered_pairs
        ]
        if undercovered:
            add(
                priority,
                code,
                "Some Pathfinder seed lanes are producing too few usable Viral Hunter targets.",
                "boost these lanes in the next Viral Hunter run and inspect their weak-lane samples",
                undercovered[:8],
            )

    if row_count and float(overall.get("axis_coverage_rate") or 0.0) < 0.80:
        add(
            84,
            "axis_fit_metric_coverage_low",
            "Most stored targets do not have pathfinder_axis_fit_* metrics.",
            "rerun with the current build or backfill scoring before judging fit quality",
        )
    if row_count and float(overall.get("lens_coverage_rate") or 0.0) < 0.80:
        add(
            78,
            "lens_fit_metric_coverage_low",
            "Most stored targets do not have pathfinder_lens_fit_* metrics.",
            "rerun with the current build or backfill scoring before judging lens quality",
        )
    if row_count and float(overall.get("clinic_fit_coverage_rate") or 0.0) < 0.80:
        add(
            83,
            "clinic_fit_metric_coverage_low",
            "Most stored targets do not have clinic_treatment_fit_score metrics.",
            "backfill Gyulim treatment-fit scoring before judging whether discovered posts match clinic services",
        )
    if row_count and float(overall.get("worksite_efficiency_coverage_rate") or 0.0) < 0.80:
        add(
            81,
            "worksite_efficiency_metric_coverage_low",
            "Most stored targets do not have worksite_efficiency_score metrics.",
            "backfill worksite-efficiency scoring before assigning posts to viral production",
        )
    if row_count and float(overall.get("strict_fit_rate") or 0.0) < 0.30:
        add(
            72,
            "strict_fit_rate_low",
            "Too few targets satisfy axis, lens, clinic-fit, and worksite-fit thresholds.",
            "prioritize weak lanes and inspect sample targets before increasing run volume",
        )

    grouped_reasons: Dict[str, List[str]] = defaultdict(list)
    for lane in weak_lanes:
        lane_name = f"{lane.get('type')}:{lane.get('lane')}"
        for reason in lane.get("reasons") or []:
            grouped_reasons[reason].append(lane_name)

    for reason, lanes in grouped_reasons.items():
        priority = {
            "missing_axis_fit_metrics": 70,
            "missing_lens_fit_metrics": 66,
            "low_survival_rate": 62,
            "low_strict_fit_rate": 60,
            "low_axis_fit": 58,
            "low_lens_fit": 59,
            "content_category_mismatch": 55,
            "lens_surface_mismatch": 55,
            "low_worksite_efficiency": 54,
        }.get(reason, 50)
        add(
            priority,
            reason,
            f"{len(lanes)} lane(s) flagged for {reason}.",
            _action_for_reason(reason),
            lanes[:8],
        )

    recommendations.sort(key=lambda item: int(item.get("priority") or 0), reverse=True)
    return recommendations[:top_n]


def _seed_baseline(db_path: str, source_scan_run_id: Optional[int]) -> Dict[str, Any]:
    if source_scan_run_id is None:
        return {}
    try:
        from core_services.viral_seed_builder import ViralSeedBuilder

        seeds = ViralSeedBuilder(db_path).build(scan_run_id=source_scan_run_id)
    except Exception:
        return {}
    if not seeds:
        return {}
    return {
        "seed_count": len(seeds),
        "seed_category_counts": dict(Counter(seed.category for seed in seeds)),
        "seed_grade_counts": dict(Counter(seed.grade for seed in seeds)),
        "seed_lens_counts": dict(Counter(seed.execution_lens or "service" for seed in seeds)),
        "seed_category_lens_counts": dict(
            Counter(f"{seed.category}::{seed.execution_lens or 'service'}" for seed in seeds)
        ),
    }


def summarize_viral_handoff_quality(
    db_path: Optional[str] = None,
    *,
    source_scan_run_id: Optional[int] = None,
    days: Optional[int] = None,
    since: Optional[str] = None,
    limit: Optional[int] = None,
    min_axis_fit: float = 55.0,
    min_lens_fit: float = 55.0,
    min_clinic_fit: float = 55.0,
    min_worksite_efficiency: float = 55.0,
    min_lane_total: int = 3,
    min_targets_per_seed: float = 1.0,
    min_strict_fit_per_seed: float = 0.25,
    sample_per_lane: int = 3,
    fresh_days: int = FRESH_WORK_QUEUE_DAYS,
    include_seed_baseline: bool = True,
) -> Dict[str, Any]:
    """Return a read-only quality report for stored Viral Hunter targets."""
    path = db_path or _default_db_path()
    if source_scan_run_id is None:
        source_scan_run_id = latest_viral_source_scan_id(path)

    if not os.path.exists(path):
        return {
            "db_path": path,
            "source_scan_run_id": source_scan_run_id,
            "row_count": 0,
            "error": "db_not_found",
        }

    overall = LaneStats()
    by_category: Dict[str, LaneStats] = defaultdict(LaneStats)
    by_platform: Dict[str, LaneStats] = defaultdict(LaneStats)
    by_grade: Dict[str, LaneStats] = defaultdict(LaneStats)
    by_lens: Dict[str, LaneStats] = defaultdict(LaneStats)
    by_category_lens: Dict[str, LaneStats] = defaultdict(LaneStats)
    by_platform_category: Dict[str, LaneStats] = defaultdict(LaneStats)
    by_query_variant: Dict[str, LaneStats] = defaultdict(LaneStats)
    by_variant_family: Dict[str, LaneStats] = defaultdict(LaneStats)
    by_category_lens_query_variant: Dict[str, LaneStats] = defaultdict(LaneStats)
    by_source_seed: Dict[str, LaneStats] = defaultdict(LaneStats)
    source_seed_categories: Dict[str, str] = {}
    source_seed_category_counts: Dict[str, Counter] = defaultdict(Counter)
    source_seed_detected_categories: Dict[str, Counter] = defaultdict(Counter)
    source_seed_category_drift_counts: Counter = Counter()
    source_seed_primary_counts: Counter = Counter()
    source_seed_assist_counts: Counter = Counter()
    records: List[Dict[str, Any]] = []

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = _fetch_rows(
            conn,
            source_scan_run_id=source_scan_run_id,
            days=days,
            since=since,
            limit=limit,
        )

    for row in rows:
        score_breakdown = _parse_json(row["score_breakdown"], {})
        category = _category(row)
        content_detected_category = _detected_content_category(row)
        content_category_mismatch = _category_drift_detected(category, content_detected_category)
        grade = _grade(row["matched_keyword_grade"])
        status = _effective_current_status(row["comment_status"], score_breakdown)
        platform = _platform(row)
        lens = _lens(score_breakdown)
        query_variant = _variant(score_breakdown)
        pathfinder_source_seeds = _pathfinder_source_seeds(score_breakdown)
        source_seed_lineage_present = bool(pathfinder_source_seeds)
        query_variant_lineage_present = bool(
            str(score_breakdown.get("pathfinder_query_variant") or "").strip()
        )
        lens_surface = _lens_surface_evidence(row, lens, query_variant)
        engagement_hook = _engagement_hook_evidence(row, lens)
        patient_surface = _patient_surface_evidence(row)
        viral_action_route = _viral_action_route_evidence(row, lens)
        reply_workability = _reply_workability_evidence(row, score_breakdown, status=status)
        treatment_signature = _treatment_signature_evidence(row, category)
        treatment_subintent = _treatment_subintent_evidence(row, category)
        clinic_modality = _clinic_modality_evidence(row, category)
        decision_window = _decision_window_evidence(row, score_breakdown)
        local_intent = _local_intent_evidence(row)
        is_fresh_activity = _fresh_activity(row, fresh_days=fresh_days)
        target_fingerprint = _target_fingerprint(row)
        variant_family = _variant_family(query_variant)
        source_seeds = _source_seeds(score_breakdown, row)
        source_seed = source_seeds[0]
        source_seed_lineage_fallback = (
            not source_seed_lineage_present
            and bool(source_seeds)
            and str(source_seed or "").strip() != "(unknown)"
        )
        local_area = _local_area_evidence(row, source_seeds=source_seeds)
        seed_candidate_alignment = _seed_candidate_alignment_evidence(
            row,
            source_seeds=source_seeds,
            category=category,
            lens=lens,
        )
        for seed in source_seeds:
            source_seed_category = canonical_category_for_keyword(seed, category)
            if not ACTIVE_KEYWORD_PROFILE.profile_for(source_seed_category):
                source_seed_category = category
            source_seed_category_counts[seed][source_seed_category] += 1
            detected_source_category = _detected_seed_category(seed)
            if detected_source_category:
                source_seed_detected_categories[seed][detected_source_category] += 1
            if _category_drift_detected(source_seed_category, detected_source_category):
                source_seed_category_drift_counts[seed] += 1
            source_seed_categories.setdefault(seed, source_seed_category)
        priority = _number(row["priority_score"], 0.0) or 0.0
        clinic_fit = _score_from_breakdown(score_breakdown, "clinic_treatment_fit_score")
        worksite_efficiency = _score_from_breakdown(score_breakdown, "worksite_efficiency_score")
        axis_fit = _score_from_breakdown_any(
            score_breakdown,
            ("pathfinder_axis_fit_score", "pathfinder_local_service_fit_score"),
        )
        lens_fit = _score_from_breakdown_any(
            score_breakdown,
            ("pathfinder_lens_fit_score", "pathfinder_content_actionability_score"),
        )
        strict_fit = _is_strict_fit(
            status=status,
            lens=lens,
            axis_fit=axis_fit,
            lens_fit=lens_fit,
            clinic_fit=clinic_fit,
            worksite_efficiency=worksite_efficiency,
            min_axis_fit=min_axis_fit,
            min_lens_fit=min_lens_fit,
            min_clinic_fit=min_clinic_fit,
            min_worksite_efficiency=min_worksite_efficiency,
        )
        metric_strict_fit = _is_strict_fit(
            status="pending",
            lens=lens,
            axis_fit=axis_fit,
            lens_fit=lens_fit,
            clinic_fit=clinic_fit,
            worksite_efficiency=worksite_efficiency,
            min_axis_fit=min_axis_fit,
            min_lens_fit=min_lens_fit,
            min_clinic_fit=min_clinic_fit,
            min_worksite_efficiency=min_worksite_efficiency,
        )
        add_kwargs = {
            "status": status,
            "grade": grade,
            "lens": lens,
            "query_variant": query_variant,
            "priority": priority,
            "axis_fit": axis_fit,
            "lens_fit": lens_fit,
            "clinic_fit": clinic_fit,
            "worksite_efficiency": worksite_efficiency,
            "strict_fit": strict_fit,
            "target_fingerprint": target_fingerprint,
            "fresh_activity": is_fresh_activity,
            "content_detected_category": content_detected_category,
            "content_category_mismatch": content_category_mismatch,
            "lens_surface_checked": bool(lens_surface.get("checked")),
            "lens_surface_matched": bool(lens_surface.get("matched")),
        }
        overall.add(**add_kwargs)
        by_category[category].add(**add_kwargs)
        by_platform[platform].add(**add_kwargs)
        by_grade[grade].add(**add_kwargs)
        by_lens[lens].add(**add_kwargs)
        by_category_lens[f"{category}::{lens}"].add(**add_kwargs)
        by_platform_category[f"{platform}::{category}"].add(**add_kwargs)
        by_query_variant[query_variant].add(**add_kwargs)
        by_variant_family[variant_family].add(**add_kwargs)
        by_category_lens_query_variant[f"{category}::{lens}::{query_variant}"].add(**add_kwargs)
        for seed in source_seeds:
            by_source_seed[seed].add(**add_kwargs)
        source_seed_primary_counts[source_seed] += 1
        for seed in source_seeds[1:]:
            source_seed_assist_counts[seed] += 1
        records.append(
            _row_sample(
                row,
                category=category,
                grade=grade,
                status=status,
                current_reject_reason=_current_reject_reason(score_breakdown),
                lens=lens,
                query_variant=query_variant,
                source_seed=source_seed,
                source_seeds=source_seeds,
                pathfinder_source_seeds=pathfinder_source_seeds,
                source_seed_lineage_present=source_seed_lineage_present,
                source_seed_lineage_fallback=source_seed_lineage_fallback,
                query_variant_lineage_present=query_variant_lineage_present,
                priority=priority,
                axis_fit=axis_fit,
                lens_fit=lens_fit,
                clinic_fit=clinic_fit,
                worksite_efficiency=worksite_efficiency,
                metric_strict_fit=metric_strict_fit,
                strict_fit=strict_fit,
                target_fingerprint=target_fingerprint,
                content_detected_category=content_detected_category,
                content_category_mismatch=content_category_mismatch,
                lens_surface_checked=bool(lens_surface.get("checked")),
                lens_surface_matched=bool(lens_surface.get("matched")),
                lens_surface_terms=list(lens_surface.get("terms") or []),
                lens_surface_bridge_terms=list(lens_surface.get("bridge_terms") or []),
                engagement_hook_checked=bool(engagement_hook.get("checked")),
                engagement_hook_matched=bool(engagement_hook.get("matched")),
                engagement_hook_terms=list(engagement_hook.get("terms") or []),
                patient_surface_checked=bool(patient_surface.get("checked")),
                patient_surface_matched=bool(patient_surface.get("matched")),
                patient_surface_terms=list(patient_surface.get("terms") or []),
                patient_surface_provider_noise=bool(patient_surface.get("provider_noise")),
                patient_surface_provider_terms=list(patient_surface.get("provider_terms") or []),
                viral_action_route_checked=bool(viral_action_route.get("checked")),
                viral_action_route_matched=bool(viral_action_route.get("matched")),
                viral_action_route=str(viral_action_route.get("route") or ""),
                viral_action_route_terms=list(viral_action_route.get("terms") or []),
                viral_action_route_routes=list(viral_action_route.get("routes") or []),
                viral_action_route_observed_routes=list(viral_action_route.get("observed_routes") or []),
                viral_action_route_mismatch=bool(viral_action_route.get("route_mismatch")),
                viral_action_route_expected_routes=list(viral_action_route.get("expected_routes") or []),
                reply_workability_checked=bool(reply_workability.get("checked")),
                reply_workability_matched=bool(reply_workability.get("matched")),
                reply_opportunity_score=reply_workability.get("score"),
                reply_opportunity_tier=str(reply_workability.get("tier") or ""),
                reply_opportunity_signals=list(reply_workability.get("signals") or []),
                reply_risk_flags=list(reply_workability.get("risk_flags") or []),
                content_risk_flags=list(reply_workability.get("content_risk_flags") or []),
                content_risk_terms=dict(reply_workability.get("content_risk_terms") or {}),
                reply_risk_penalty=float(reply_workability.get("risk_penalty") or 0.0),
                reply_manual_review=bool(reply_workability.get("manual_review")),
                reply_metric_missing=bool(reply_workability.get("metric_missing")),
                reply_risk_blocked=bool(reply_workability.get("risk_blocked")),
                reply_comment_count=int(reply_workability.get("comment_count") or 0),
                reply_view_count=int(reply_workability.get("view_count") or 0),
                reply_like_count=int(reply_workability.get("like_count") or 0),
                treatment_signature_checked=bool(treatment_signature.get("checked")),
                treatment_signature_matched=bool(treatment_signature.get("matched")),
                treatment_signature_terms=list(treatment_signature.get("terms") or []),
                treatment_signature_expected_terms=list(treatment_signature.get("expected_terms") or []),
                treatment_subintent_checked=bool(treatment_subintent.get("checked")),
                treatment_subintent_matched=bool(treatment_subintent.get("matched")),
                treatment_subintent_buckets=list(treatment_subintent.get("buckets") or []),
                treatment_subintent_terms=list(treatment_subintent.get("terms") or []),
                treatment_subintent_bucket_terms=dict(treatment_subintent.get("bucket_terms") or {}),
                treatment_subintent_expected_buckets=list(treatment_subintent.get("expected_buckets") or []),
                clinic_modality_checked=bool(clinic_modality.get("checked")),
                clinic_modality_matched=bool(clinic_modality.get("matched")),
                clinic_modality_positive_terms=list(clinic_modality.get("positive_terms") or []),
                clinic_modality_offscope_terms=list(clinic_modality.get("offscope_terms") or []),
                clinic_modality_bridge_terms=list(clinic_modality.get("bridge_terms") or []),
                clinic_modality_reasons=list(clinic_modality.get("reasons") or []),
                decision_window_checked=bool(decision_window.get("checked")),
                decision_window_matched=bool(decision_window.get("matched")),
                decision_window_active_terms=list(decision_window.get("active_terms") or []),
                decision_window_completed_terms=list(decision_window.get("completed_terms") or []),
                decision_window_active_signals=list(decision_window.get("active_signals") or []),
                decision_window_reasons=list(decision_window.get("reasons") or []),
                local_intent_checked=bool(local_intent.get("checked")),
                local_intent_matched=bool(local_intent.get("matched")),
                local_intent_terms=list(local_intent.get("terms") or []),
                local_intent_expected_terms=list(local_intent.get("expected_terms") or []),
                local_area_terms=list(local_area.get("terms") or []),
                local_area_target_terms=list(local_area.get("target_terms") or []),
                local_area_source_terms=list(local_area.get("source_terms") or []),
                seed_candidate_alignment_checked=bool(seed_candidate_alignment.get("checked")),
                seed_candidate_alignment_matched=bool(seed_candidate_alignment.get("matched")),
                seed_candidate_alignment_terms=list(seed_candidate_alignment.get("source_terms") or []),
                seed_candidate_alignment_matched_terms=list(seed_candidate_alignment.get("matched_terms") or []),
                seed_candidate_alignment_missing_terms=list(seed_candidate_alignment.get("missing_terms") or []),
                seed_candidate_alignment_local_terms=list(seed_candidate_alignment.get("local_terms") or []),
                seed_candidate_alignment_reasons=list(seed_candidate_alignment.get("reasons") or []),
                seed_candidate_alignment_overlap_rate=float(seed_candidate_alignment.get("overlap_rate") or 0.0),
                fresh_activity=is_fresh_activity,
            )
        )

    category_summary = {key: stats.to_dict() for key, stats in sorted(by_category.items())}
    platform_summary = {key: stats.to_dict() for key, stats in sorted(by_platform.items())}
    grade_summary = {key: stats.to_dict() for key, stats in sorted(by_grade.items())}
    lens_summary = {key: stats.to_dict() for key, stats in sorted(by_lens.items())}
    category_lens_summary = {
        key: stats.to_dict()
        for key, stats in sorted(by_category_lens.items())
    }
    platform_category_summary = {
        key: stats.to_dict()
        for key, stats in sorted(by_platform_category.items())
    }
    query_variant_summary = {
        key: stats.to_dict()
        for key, stats in sorted(by_query_variant.items())
    }
    variant_family_summary = {
        key: stats.to_dict()
        for key, stats in sorted(by_variant_family.items())
    }
    category_lens_query_variant_summary = {
        key: stats.to_dict()
        for key, stats in sorted(by_category_lens_query_variant.items())
    }
    source_seed_summary = {}
    for seed, stats in sorted(by_source_seed.items()):
        metrics = stats.to_dict()
        category_counts = dict(source_seed_category_counts.get(seed, {}))
        dominant_category = (
            source_seed_category_counts.get(seed, Counter()).most_common(1)[0][0]
            if category_counts else source_seed_categories.get(seed, "")
        )
        metrics["category"] = dominant_category
        metrics["category_counts"] = category_counts
        detected_counts = dict(source_seed_detected_categories.get(seed, {}))
        metrics["detected_category_counts"] = detected_counts
        metrics["detected_category"] = (
            source_seed_detected_categories.get(seed, Counter()).most_common(1)[0][0]
            if detected_counts else ""
        )
        category_drift_count = int(source_seed_category_drift_counts.get(seed, 0) or 0)
        metrics["category_drift_count"] = category_drift_count
        metrics["category_drift_rate"] = LaneStats._rate(category_drift_count, metrics["total"])
        metrics["category_drift"] = bool(category_drift_count)
        metrics["dominant_category_drift"] = _category_drift_detected(
            dominant_category,
            str(metrics.get("detected_category") or ""),
        )
        metrics["credit_total"] = metrics["total"]
        metrics["primary_total"] = int(source_seed_primary_counts.get(seed, 0) or 0)
        metrics["assist_total"] = int(source_seed_assist_counts.get(seed, 0) or 0)
        metrics["credit_note"] = "total is source-seed credit count; row_count is not duplicated"
        source_seed_summary[seed] = metrics
    weak_source_seeds = _weak_source_seeds(
        source_seed_summary,
        min_lane_total=min_lane_total,
        limit=20,
    )
    source_seed_feedback = _source_seed_feedback(
        source_seed_summary,
        limit=10,
    )
    variant_quality_feedback = _variant_quality_feedback(
        query_variant_summary,
        variant_family_summary,
        category_lens_query_variant_summary=category_lens_query_variant_summary,
        limit=10,
    )

    weak_lanes = []
    for lane_type, summary in (
        ("category", category_summary),
        ("grade", grade_summary),
        ("lens", lens_summary),
        ("category_lens", category_lens_summary),
        ("query_variant", query_variant_summary),
        ("variant_family", variant_family_summary),
        ("category_lens_query_variant", category_lens_query_variant_summary),
    ):
        for lane, metrics in summary.items():
            reasons = _weak_lane_reasons(metrics, min_lane_total=min_lane_total)
            if reasons:
                weak_lanes.append({
                    "type": lane_type,
                    "lane": lane,
                    "total": metrics["total"],
                    "survival_rate": metrics["survival_rate"],
                    "strict_fit_rate": metrics["strict_fit_rate"],
                    "avg_axis_fit": metrics["avg_axis_fit"],
                    "avg_lens_fit": metrics["avg_lens_fit"],
                    "content_category_mismatch": metrics.get("content_category_mismatch", 0),
                    "content_category_mismatch_rate": metrics.get("content_category_mismatch_rate", 0.0),
                    "lens_surface_mismatch": metrics.get("lens_surface_mismatch", 0),
                    "lens_surface_mismatch_rate": metrics.get("lens_surface_mismatch_rate", 0.0),
                    "reasons": reasons,
                })
    weak_lanes.sort(key=lambda item: (item["strict_fit_rate"], item["survival_rate"], -item["total"]))

    baseline = _seed_baseline(path, source_scan_run_id) if include_seed_baseline else {}
    if baseline:
        discovered_categories = set(category_summary)
        discovered_lenses = set(lens_summary)
        baseline["missing_seed_categories_in_targets"] = sorted(
            set(baseline.get("seed_category_counts", {})) - discovered_categories
        )
        baseline["missing_seed_lenses_in_targets"] = sorted(
            set(baseline.get("seed_lens_counts", {})) - discovered_lenses
        )
        discovered_category_lenses = set(category_lens_summary)
        baseline["missing_seed_category_lenses_in_targets"] = sorted(
            set(baseline.get("seed_category_lens_counts", {})) - discovered_category_lenses
        )

    overall_summary = overall.to_dict()
    loss_analysis = _loss_analysis(
        overall=overall_summary,
        category_summary=category_summary,
        lens_summary=lens_summary,
        category_lens_summary=category_lens_summary,
        query_variant_summary=query_variant_summary,
    )
    patient_journey_coverage = _patient_journey_coverage(
        category_lens_summary=category_lens_summary,
        min_lane_total=min_lane_total,
    )
    work_queue_readiness = _work_queue_readiness(
        category_summary=category_summary,
        category_lens_summary=category_lens_summary,
    )
    opportunity_diversity = _opportunity_diversity(records)
    engagement_hook_quality = _engagement_hook_quality(records)
    treatment_signature_quality = _treatment_signature_quality(records)
    treatment_signal_diversity_quality = _treatment_signal_diversity_quality(records)
    treatment_subintent_diversity_quality = _treatment_subintent_diversity_quality(records)
    clinic_modality_quality = _clinic_modality_quality(records)
    decision_window_quality = _decision_window_quality(records)
    seed_candidate_alignment_quality = _seed_candidate_alignment_quality(records)
    source_lineage_quality = _source_lineage_quality(records)
    local_intent_quality = _local_intent_quality(records)
    local_area_diversity_quality = _local_area_diversity_quality(records)
    patient_surface_quality = _patient_surface_quality(records)
    viral_action_route_quality = _viral_action_route_quality(records)
    reply_workability_quality = _reply_workability_quality(records)
    compliance_work_mode_quality = _compliance_work_mode_quality(records)
    execution_readiness_quality = _execution_readiness_quality(records)
    execution_priority_alignment_quality = _execution_priority_alignment_quality(records)
    reanalysis_rescue_quality = _reanalysis_rescue_quality(
        records,
        limit=max(3, int(sample_per_lane or 0) * 4),
    )
    discarded_execution_rescue_quality = _discarded_execution_rescue_quality(
        records,
        limit=max(3, int(sample_per_lane or 0) * 4),
    )
    platform_surface_quality = _platform_surface_quality(
        platform_summary=platform_summary,
        platform_category_summary=platform_category_summary,
        min_lane_total=min_lane_total,
    )
    seed_target_coverage = _seed_target_coverage(
        baseline,
        category_summary=category_summary,
        lens_summary=lens_summary,
        category_lens_summary=category_lens_summary,
        min_targets_per_seed=min_targets_per_seed,
        min_strict_fit_per_seed=min_strict_fit_per_seed,
    )
    quality_bar = _handoff_quality_bar(
        overall=overall_summary,
        category_summary=category_summary,
        variant_family_summary=variant_family_summary,
        weak_lanes=weak_lanes,
        source_seed_feedback=source_seed_feedback,
        patient_journey_coverage=patient_journey_coverage,
        work_queue_readiness=work_queue_readiness,
        opportunity_diversity=opportunity_diversity,
        engagement_hook_quality=engagement_hook_quality,
        treatment_signature_quality=treatment_signature_quality,
        treatment_signal_diversity_quality=treatment_signal_diversity_quality,
        treatment_subintent_diversity_quality=treatment_subintent_diversity_quality,
        clinic_modality_quality=clinic_modality_quality,
        decision_window_quality=decision_window_quality,
        seed_candidate_alignment_quality=seed_candidate_alignment_quality,
        local_intent_quality=local_intent_quality,
        local_area_diversity_quality=local_area_diversity_quality,
        patient_surface_quality=patient_surface_quality,
        viral_action_route_quality=viral_action_route_quality,
        reply_workability_quality=reply_workability_quality,
        compliance_work_mode_quality=compliance_work_mode_quality,
        execution_readiness_quality=execution_readiness_quality,
        execution_priority_alignment_quality=execution_priority_alignment_quality,
        platform_surface_quality=platform_surface_quality,
        source_lineage_quality=source_lineage_quality,
        reanalysis_rescue_quality=reanalysis_rescue_quality,
        discarded_execution_rescue_quality=discarded_execution_rescue_quality,
    )
    recommendations = _recommendations(
        row_count=len(rows),
        overall=overall_summary,
        weak_lanes=weak_lanes,
        baseline=baseline,
        seed_target_coverage=seed_target_coverage,
        quality_bar=quality_bar,
        source_seed_feedback=source_seed_feedback,
        variant_quality_feedback=variant_quality_feedback,
        loss_analysis=loss_analysis,
        patient_journey_coverage=patient_journey_coverage,
        work_queue_readiness=work_queue_readiness,
        opportunity_diversity=opportunity_diversity,
        engagement_hook_quality=engagement_hook_quality,
        treatment_signature_quality=treatment_signature_quality,
        treatment_signal_diversity_quality=treatment_signal_diversity_quality,
        treatment_subintent_diversity_quality=treatment_subintent_diversity_quality,
        clinic_modality_quality=clinic_modality_quality,
        decision_window_quality=decision_window_quality,
        seed_candidate_alignment_quality=seed_candidate_alignment_quality,
        local_intent_quality=local_intent_quality,
        local_area_diversity_quality=local_area_diversity_quality,
        patient_surface_quality=patient_surface_quality,
        viral_action_route_quality=viral_action_route_quality,
        reply_workability_quality=reply_workability_quality,
        compliance_work_mode_quality=compliance_work_mode_quality,
        execution_readiness_quality=execution_readiness_quality,
        execution_priority_alignment_quality=execution_priority_alignment_quality,
        platform_surface_quality=platform_surface_quality,
        source_lineage_quality=source_lineage_quality,
        reanalysis_rescue_quality=reanalysis_rescue_quality,
        discarded_execution_rescue_quality=discarded_execution_rescue_quality,
    )
    next_run_playbook = _next_run_playbook(
        source_scan_run_id=source_scan_run_id,
        row_count=len(rows),
        overall=overall_summary,
        seed_target_coverage=seed_target_coverage,
        weak_lanes=weak_lanes,
        recommendations=recommendations,
        sample_per_lane=sample_per_lane,
        source_seed_feedback=source_seed_feedback,
        variant_quality_feedback=variant_quality_feedback,
        loss_analysis=loss_analysis,
        patient_journey_coverage=patient_journey_coverage,
        work_queue_readiness=work_queue_readiness,
        opportunity_diversity=opportunity_diversity,
        engagement_hook_quality=engagement_hook_quality,
        treatment_signature_quality=treatment_signature_quality,
        treatment_signal_diversity_quality=treatment_signal_diversity_quality,
        treatment_subintent_diversity_quality=treatment_subintent_diversity_quality,
        clinic_modality_quality=clinic_modality_quality,
        decision_window_quality=decision_window_quality,
        seed_candidate_alignment_quality=seed_candidate_alignment_quality,
        local_intent_quality=local_intent_quality,
        local_area_diversity_quality=local_area_diversity_quality,
        patient_surface_quality=patient_surface_quality,
        viral_action_route_quality=viral_action_route_quality,
        reply_workability_quality=reply_workability_quality,
        compliance_work_mode_quality=compliance_work_mode_quality,
        execution_readiness_quality=execution_readiness_quality,
        execution_priority_alignment_quality=execution_priority_alignment_quality,
        platform_surface_quality=platform_surface_quality,
        source_lineage_quality=source_lineage_quality,
        reanalysis_rescue_quality=reanalysis_rescue_quality,
        discarded_execution_rescue_quality=discarded_execution_rescue_quality,
    )

    return {
        "db_path": path,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_scan_run_id": source_scan_run_id,
        "row_count": len(rows),
        "thresholds": {
            "min_axis_fit": min_axis_fit,
            "min_lens_fit": min_lens_fit,
            "min_clinic_fit": min_clinic_fit,
            "min_worksite_efficiency": min_worksite_efficiency,
            "min_lane_total": min_lane_total,
            "min_targets_per_seed": min_targets_per_seed,
            "min_strict_fit_per_seed": min_strict_fit_per_seed,
            "sample_per_lane": sample_per_lane,
            "fresh_days": fresh_days,
        },
        "filters": {
            "days": days,
            "since": since,
        },
        "overall": overall_summary,
        "by_category": category_summary,
        "by_platform": platform_summary,
        "by_grade": grade_summary,
        "by_lens": lens_summary,
        "by_category_lens": category_lens_summary,
        "by_platform_category": platform_category_summary,
        "by_query_variant": query_variant_summary,
        "by_variant_family": variant_family_summary,
        "by_category_lens_query_variant": category_lens_query_variant_summary,
        "by_source_seed": source_seed_summary,
        "loss_analysis": loss_analysis,
        "patient_journey_coverage": patient_journey_coverage,
        "work_queue_readiness": work_queue_readiness,
        "opportunity_diversity": opportunity_diversity,
        "engagement_hook_quality": engagement_hook_quality,
        "treatment_signature_quality": treatment_signature_quality,
        "treatment_signal_diversity_quality": treatment_signal_diversity_quality,
        "treatment_subintent_diversity_quality": treatment_subintent_diversity_quality,
        "clinic_modality_quality": clinic_modality_quality,
        "decision_window_quality": decision_window_quality,
        "seed_candidate_alignment_quality": seed_candidate_alignment_quality,
        "source_lineage_quality": source_lineage_quality,
        "local_intent_quality": local_intent_quality,
        "local_area_diversity_quality": local_area_diversity_quality,
        "patient_surface_quality": patient_surface_quality,
        "viral_action_route_quality": viral_action_route_quality,
        "reply_workability_quality": reply_workability_quality,
        "compliance_work_mode_quality": compliance_work_mode_quality,
        "execution_readiness_quality": execution_readiness_quality,
        "execution_priority_alignment_quality": execution_priority_alignment_quality,
        "platform_surface_quality": platform_surface_quality,
        "reanalysis_rescue_quality": reanalysis_rescue_quality,
        "discarded_execution_rescue_quality": discarded_execution_rescue_quality,
        "weak_source_seeds": weak_source_seeds,
        "source_seed_feedback": source_seed_feedback,
        "variant_quality_feedback": variant_quality_feedback,
        "quality_bar": quality_bar,
        "seed_target_coverage": seed_target_coverage,
        "weak_lanes": weak_lanes,
        "recommendations": recommendations,
        "next_run_playbook": next_run_playbook,
        "review_samples": _review_samples(
            records,
            weak_lanes,
            patient_journey_coverage=patient_journey_coverage,
            work_queue_readiness=work_queue_readiness,
            opportunity_diversity=opportunity_diversity,
            engagement_hook_quality=engagement_hook_quality,
            treatment_signature_quality=treatment_signature_quality,
            treatment_signal_diversity_quality=treatment_signal_diversity_quality,
            treatment_subintent_diversity_quality=treatment_subintent_diversity_quality,
            seed_candidate_alignment_quality=seed_candidate_alignment_quality,
            local_intent_quality=local_intent_quality,
            patient_surface_quality=patient_surface_quality,
            viral_action_route_quality=viral_action_route_quality,
            reply_workability_quality=reply_workability_quality,
            execution_readiness_quality=execution_readiness_quality,
            execution_priority_alignment_quality=execution_priority_alignment_quality,
            platform_surface_quality=platform_surface_quality,
            sample_per_lane=max(0, int(sample_per_lane or 0)),
        ),
        "seed_baseline": baseline,
    }

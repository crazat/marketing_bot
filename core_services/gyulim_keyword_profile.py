"""Shared keyword taxonomy for Cheongju Gyulim Korean-medicine marketing.

The Pathfinder family had the same business rules copied across several files:
regions, treatment categories, seed terms, service anchors, and low-value
leakage terms.  This module keeps those rules explicit and reusable so keyword
discovery, scoring, and UI filtering do not drift apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower())


def _unique(items: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    result: List[str] = []
    for item in items:
        clean = (item or "").strip()
        if not clean:
            continue
        key = _compact(clean)
        if key in seen:
            continue
        seen.add(key)
        result.append(clean)
    return result


@dataclass(frozen=True)
class TreatmentCategoryProfile:
    category: str
    seed_terms: Tuple[str, ...]
    category_terms: Tuple[str, ...]
    direct_service_anchors: Tuple[str, ...]
    core_tokens: Tuple[str, ...]
    low_business_value_terms: Tuple[str, ...] = ()
    longtail_suffixes: Tuple[str, ...] = (
        "비용",
        "상담",
        "예약",
        "후기",
        "추천",
        "주차",
    )
    longtail_contexts: Tuple[str, ...] = ()
    journey_suffixes: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    strategic_weight: float = 1.0


class GyulimKeywordProfile:
    """Canonical treatment, region, and intent profile for Pathfinder."""

    cheongju_regions: Tuple[str, ...] = (
        "청주",
        "상당",
        "서원",
        "흥덕",
        "청원",
        "상당구",
        "서원구",
        "흥덕구",
        "청원구",
        "오창",
        "오송",
    )
    neighborhoods: Tuple[str, ...] = (
        "복대동",
        "가경동",
        "분평동",
        "봉명동",
        "사창동",
        "산남동",
        "수곡동",
        "모충동",
        "용암동",
        "금천동",
        "율량동",
        "사직동",
        "성화동",
        "내덕동",
        "우암동",
        "오창",
        "오송",
        "복대",
        "가경",
        "분평",
        "봉명",
        "율량",
    )
    nearby_regions: Tuple[str, ...] = ("진천", "증평", "괴산", "음성", "보은")

    hanbang_indicators: Tuple[str, ...] = (
        "한의원",
        "한방",
        "한약",
        "한방병원",
        "침",
        "뜸",
        "부항",
        "추나",
        "한의사",
        "경혈",
        "공진단",
        "경옥고",
        "보약",
        "총명탕",
    )
    high_intent_terms: Tuple[str, ...] = (
        "가격",
        "비용",
        "상담",
        "예약",
        "후기",
        "추천",
        "잘하는곳",
        "잘하는",
        "효과",
        "부작용",
        "주의사항",
        "기간",
        "주차",
        "야간",
        "주말",
        "진료시간",
        "보험",
        "실비",
        "자보",
        "자동차보험",
        "치료비",
        "입원",
        "근처",
        "당일",
    )
    medical_general_tokens: Tuple[str, ...] = (
        "피부과",
        "내과",
        "이비인후과",
        "안과",
        "치과",
        "정형외과",
        "성형외과",
        "신경외과",
        "비뇨기과",
        "산부인과",
        "소아과",
        "응급실",
    )

    category_aliases: Dict[str, str] = {
        "다이어트/비만": "다이어트",
        "비만": "다이어트",
        "안면비대칭_교정": "안면비대칭",
        "안면비대칭교정": "안면비대칭",
        "비대칭_교정": "안면비대칭",
        "여드름_피부": "피부/여드름",
        "여드름/피부": "피부/여드름",
        "피부": "피부/여드름",
        "여드름": "피부/여드름",
        "교통사고_입원": "교통사고",
        "교통사고입원": "교통사고",
        "통증": "통증/디스크",
        "통증_디스크": "통증/디스크",
        "디스크": "통증/디스크",
        "리프팅_탄력": "리프팅/탄력",
        "리프팅": "리프팅/탄력",
        "매선": "리프팅/탄력",
    }

    def __init__(self) -> None:
        self.profiles: Tuple[TreatmentCategoryProfile, ...] = (
            TreatmentCategoryProfile(
                category="다이어트",
                seed_terms=(
                    "다이어트",
                    "다이어트 한의원",
                    "다이어트 한약",
                    "한방다이어트",
                    "비만 한의원",
                    "비만클리닉",
                    "식욕억제",
                    "체지방",
                    "뱃살",
                    "허벅지살",
                    "산후다이어트",
                    "웨딩 다이어트",
                ),
                category_terms=(
                    "다이어트",
                    "비만",
                    "살빼",
                    "체중",
                    "감량",
                    "체지방",
                    "식욕억제",
                    "요요",
                    "뱃살",
                    "허벅지살",
                    "팔뚝살",
                    "산후다이어트",
                    "웨딩다이어트",
                    "한방다이어트",
                    "다이어트한약",
                ),
                direct_service_anchors=(
                    "한의원",
                    "한방",
                    "한약",
                    "다이어트한약",
                    "비만한의원",
                    "비만클리닉",
                    "식욕억제",
                    "체질",
                    "상담",
                ),
                core_tokens=("다이어트", "비만", "체중", "감량", "체지방", "식욕억제"),
                low_business_value_terms=(
                    "다이어트댄스",
                    "다이어트 댄스",
                    "댄스",
                    "줌바",
                    "요가",
                    "필라테스",
                    "헬스",
                    "pt",
                    "피티",
                    "홈트",
                    "운동",
                    "식단",
                    "도시락",
                    "쉐이크",
                    "보조제",
                    "챌린지",
                    "캠프",
                    "학원",
                ),
                longtail_contexts=("직장인", "산후", "출산후", "갱년기", "웨딩", "요요"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "가격"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("부작용", "주의사항", "요요"),
                },
                strategic_weight=1.2,
            ),
            TreatmentCategoryProfile(
                category="피부/여드름",
                seed_terms=(
                    "여드름",
                    "여드름 한의원",
                    "여드름흉터",
                    "여드름흉터 한의원",
                    "새살침",
                    "패인흉터",
                    "모공흉터",
                    "여드름자국",
                    "피부 한의원",
                    "피부질환",
                    "아토피",
                    "지루성피부염",
                    "안면홍조",
                ),
                category_terms=(
                    "여드름",
                    "여드름흉터",
                    "여드름자국",
                    "새살침",
                    "흉터",
                    "패인흉터",
                    "모공흉터",
                    "색소침착",
                    "피부",
                    "피부질환",
                    "피부관리",
                    "아토피",
                    "지루성피부염",
                    "홍조",
                    "습진",
                    "두드러기",
                    "건선",
                ),
                direct_service_anchors=(
                    "한의원",
                    "한방",
                    "새살침",
                    "흉터치료",
                    "패인흉터",
                    "모공흉터",
                    "여드름흉터",
                    "여드름자국",
                    "피부질환",
                ),
                core_tokens=(
                    "여드름",
                    "여드름흉터",
                    "여드름자국",
                    "새살침",
                    "흉터",
                    "패인흉터",
                    "모공흉터",
                    "피부질환",
                    "피부관리",
                    "아토피",
                    "지루성피부염",
                    "홍조",
                ),
                low_business_value_terms=(
                    "화장품",
                    "폼클렌징",
                    "클렌징",
                    "연고",
                    "패치",
                    "압출기",
                    "마스크팩",
                    "올리브영",
                ),
                longtail_contexts=("흉터", "민감피부", "재발", "성인", "마스크", "압출후"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("부작용", "주의사항", "재발"),
                },
                strategic_weight=1.25,
            ),
            TreatmentCategoryProfile(
                category="안면비대칭",
                seed_terms=(
                    "안면비대칭",
                    "안면비대칭 교정",
                    "얼굴비대칭",
                    "턱비대칭",
                    "턱관절",
                    "얼굴교정",
                    "광대비대칭",
                    "눈비대칭",
                    "비수술 안면교정",
                    "웨딩 안면비대칭",
                ),
                category_terms=(
                    "안면비대칭",
                    "얼굴비대칭",
                    "턱비대칭",
                    "비대칭교정",
                    "안면교정",
                    "광대비대칭",
                    "눈비대칭",
                    "입비대칭",
                    "턱관절",
                    "얼굴교정",
                    "얼굴형",
                ),
                direct_service_anchors=("한의원", "교정", "안면교정", "얼굴교정", "턱관절"),
                core_tokens=("안면비대칭", "얼굴비대칭", "턱비대칭", "비대칭교정", "턱관절"),
                low_business_value_terms=("셀프", "마사지", "운동", "유튜브", "홈케어"),
                longtail_contexts=("턱관절", "얼굴형", "사진", "교정 전후", "통증", "비수술"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("주의사항", "통증", "비수술"),
                },
                strategic_weight=1.2,
            ),
            TreatmentCategoryProfile(
                category="체형교정",
                seed_terms=(
                    "체형교정",
                    "골반교정",
                    "자세교정",
                    "척추교정",
                    "거북목",
                    "라운드숄더",
                    "척추측만",
                    "휜다리교정",
                ),
                category_terms=(
                    "체형교정",
                    "골반교정",
                    "자세교정",
                    "척추교정",
                    "척추측만",
                    "거북목",
                    "라운드숄더",
                    "휜다리",
                    "오다리",
                    "골반틀어짐",
                ),
                direct_service_anchors=("한의원", "교정", "골반교정", "자세교정", "척추교정", "추나"),
                core_tokens=("체형교정", "골반교정", "자세교정", "척추교정", "척추측만", "거북목"),
                low_business_value_terms=("셀프", "운동", "유튜브", "홈트", "필라테스", "요가"),
                longtail_contexts=("골반", "라운드숄더", "거북목", "허리통증", "산후", "비수술"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("주의사항", "통증", "비수술"),
                },
                strategic_weight=1.0,
            ),
            TreatmentCategoryProfile(
                category="교통사고",
                seed_terms=(
                    "교통사고",
                    "교통사고 한의원",
                    "교통사고 입원",
                    "교통사고 후유증",
                    "자동차사고 한의원",
                    "자보 한의원",
                    "교통사고 목통증",
                    "교통사고 허리통증",
                    "교통사고 두통",
                ),
                category_terms=(
                    "교통사고",
                    "자동차사고",
                    "후유증",
                    "입원",
                    "교통사고한의원",
                    "자보한의원",
                    "교통사고입원",
                    "자동차보험",
                    "교통사고보험",
                    "추돌사고",
                    "사고후통증",
                ),
                direct_service_anchors=(
                    "한의원",
                    "한방병원",
                    "입원",
                    "후유증",
                    "자보",
                    "자동차보험",
                    "보험",
                    "치료",
                    "치료비",
                ),
                core_tokens=("교통사고", "자동차사고", "후유증", "입원", "자보", "자동차보험"),
                longtail_suffixes=("입원", "자보", "자동차보험", "치료비", "주말", "야간", "상담"),
                longtail_contexts=("입원 가능한", "야간", "주말", "목통증", "허리통증", "합의전"),
                journey_suffixes={
                    "decision": ("입원", "상담", "예약", "치료비"),
                    "access": ("주말", "야간", "주차", "입원 가능"),
                    "coverage": ("자보", "자동차보험 서류", "치료비", "보험"),
                    "safety": ("후유증", "합의전 상담", "주의사항"),
                },
                strategic_weight=1.2,
            ),
            TreatmentCategoryProfile(
                category="통증/디스크",
                seed_terms=(
                    "허리통증",
                    "허리통증 한의원",
                    "목디스크",
                    "허리디스크",
                    "디스크 한의원",
                    "추나요법",
                    "어깨통증",
                    "무릎통증",
                    "오십견",
                    "손목터널증후군",
                    "족저근막염",
                    "좌골신경통",
                    "대상포진 통증",
                ),
                category_terms=(
                    "허리디스크",
                    "목디스크",
                    "허리통증",
                    "목통증",
                    "어깨통증",
                    "무릎통증",
                    "추나",
                    "추나요법",
                    "도수치료",
                    "척추",
                    "디스크한의원",
                    "통증",
                    "디스크",
                    "관절",
                    "오십견",
                    "테니스엘보",
                    "손목터널",
                    "족저근막염",
                    "좌골신경통",
                    "척추관협착증",
                    "대상포진",
                ),
                direct_service_anchors=(
                    "한의원",
                    "한방",
                    "추나",
                    "추나요법",
                    "침",
                    "치료",
                    "통증치료",
                    "디스크한의원",
                ),
                core_tokens=(
                    "허리통증",
                    "목통증",
                    "어깨통증",
                    "무릎통증",
                    "허리디스크",
                    "목디스크",
                    "디스크",
                    "통증",
                    "오십견",
                    "손목터널",
                    "족저근막염",
                    "좌골신경통",
                    "대상포진",
                ),
                low_business_value_terms=("셀프", "운동", "홈트", "유튜브", "필라테스", "요가"),
                longtail_suffixes=("비용", "상담", "예약", "추천", "주차", "야간", "치료기간"),
                longtail_contexts=("직장인", "야간", "주말", "재발", "만성", "비수술"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("주의사항", "통증", "비수술", "치료기간"),
                },
                strategic_weight=1.1,
            ),
            TreatmentCategoryProfile(
                category="리프팅/탄력",
                seed_terms=(
                    "한방리프팅",
                    "매선리프팅",
                    "침리프팅",
                    "매선침",
                    "피부탄력",
                    "팔자주름",
                    "이중턱",
                ),
                category_terms=(
                    "리프팅",
                    "매선",
                    "매선리프팅",
                    "한방리프팅",
                    "침리프팅",
                    "피부탄력",
                    "주름",
                    "동안침",
                    "팔자주름",
                    "이중턱",
                    "탄력",
                ),
                direct_service_anchors=("한의원", "한방", "매선", "매선리프팅", "한방리프팅", "침리프팅"),
                core_tokens=("리프팅", "매선", "한방리프팅", "침리프팅", "피부탄력", "팔자주름", "이중턱"),
                low_business_value_terms=("화장품", "팩", "마사지", "홈케어"),
                longtail_contexts=("팔자주름", "이중턱", "탄력", "웨딩", "자연스러운", "통증 적은"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("부작용", "주의사항", "통증"),
                },
                strategic_weight=0.9,
            ),
        )
        self._profile_by_category: Dict[str, TreatmentCategoryProfile] = {
            profile.category: profile for profile in self.profiles
        }

    @property
    def focus_categories(self) -> Tuple[str, ...]:
        return tuple(profile.category for profile in self.profiles)

    @property
    def business_core_categories(self) -> Tuple[str, ...]:
        return self.focus_categories

    @property
    def hanbang_keywords(self) -> Tuple[str, ...]:
        terms: List[str] = list(self.hanbang_indicators)
        for profile in self.profiles:
            terms.extend(profile.category_terms)
            terms.extend(profile.seed_terms)
        return tuple(_unique(terms))

    def normalize_category(self, category: Optional[str]) -> str:
        if not category:
            return "기타"
        return self.category_aliases.get(category, category)

    def category_patterns(self) -> Dict[str, Tuple[str, ...]]:
        return {profile.category: profile.category_terms for profile in self.profiles}

    def direct_service_anchors(self) -> Dict[str, Tuple[str, ...]]:
        return {profile.category: profile.direct_service_anchors for profile in self.profiles}

    def low_business_value_terms(self) -> Dict[str, Tuple[str, ...]]:
        return {profile.category: profile.low_business_value_terms for profile in self.profiles}

    def profile_for(self, category: Optional[str]) -> Optional[TreatmentCategoryProfile]:
        return self._profile_by_category.get(self.normalize_category(category))

    def detect_category(self, keyword: str, default: str = "기타") -> str:
        kw = _compact(keyword)
        for profile in self.profiles:
            if any(_compact(term) in kw for term in profile.category_terms):
                return profile.category
        if any(_compact(term) in kw for term in self.hanbang_indicators):
            return "한의원일반"
        return default

    def is_target_region(self, keyword: str, include_nearby: bool = False) -> bool:
        regions: Sequence[str]
        if include_nearby:
            regions = self.cheongju_regions + self.neighborhoods + self.nearby_regions
        else:
            regions = self.cheongju_regions + self.neighborhoods
        return any(_compact(region) in _compact(keyword) for region in regions)

    def has_hanbang_or_treatment_signal(self, keyword: str) -> bool:
        kw = _compact(keyword)
        return any(_compact(term) in kw for term in self.hanbang_keywords)

    def has_medical_general_without_hanbang(self, keyword: str) -> bool:
        kw = _compact(keyword)
        has_general = any(_compact(term) in kw for term in self.medical_general_tokens)
        has_hanbang = any(_compact(term) in kw for term in self.hanbang_indicators)
        return has_general and not has_hanbang

    def has_direct_service_anchor(self, keyword: str, category: Optional[str] = None) -> bool:
        profile = self.profile_for(category or self.detect_category(keyword))
        if not profile:
            return False
        kw = _compact(keyword)
        return any(_compact(anchor) in kw for anchor in profile.direct_service_anchors)

    def low_business_value_reason(self, keyword: str, category: Optional[str] = None) -> Optional[str]:
        profile = self.profile_for(category or self.detect_category(keyword))
        if not profile:
            return None
        kw = _compact(keyword)
        matched = next((term for term in profile.low_business_value_terms if _compact(term) in kw), None)
        if not matched:
            return None
        if self.has_direct_service_anchor(keyword, profile.category):
            return None
        return f"low_business_value_{profile.category}:{matched}"

    def is_business_core_keyword(self, keyword: str, category: Optional[str] = None) -> bool:
        category = self.normalize_category(category or self.detect_category(keyword))
        profile = self.profile_for(category)
        if not profile:
            return False
        kw = _compact(keyword)
        if category == "통증/디스크":
            return any(_compact(token) in kw for token in profile.core_tokens)
        if category == "피부/여드름":
            return any(_compact(token) in kw for token in profile.core_tokens)
        return True

    def is_focus_candidate(self, keyword: str, category: Optional[str] = None) -> bool:
        category = self.normalize_category(category or self.detect_category(keyword))
        profile = self.profile_for(category)
        if not profile:
            return False
        if self.low_business_value_reason(keyword, category):
            return False
        if self.has_medical_general_without_hanbang(keyword):
            return False

        kw = _compact(keyword)
        if category == "통증/디스크":
            # Keep pain broad enough for discovery, but block bare technique terms
            # such as "청주 추나" unless an actual pain/problem token is present.
            return any(_compact(token) in kw for token in profile.core_tokens)
        if category == "피부/여드름":
            return any(_compact(token) in kw for token in profile.core_tokens)
        return True

    def business_relevance_score(
        self,
        keyword: str,
        category: Optional[str] = None,
        *,
        include_region_bonus: bool = True,
    ) -> float:
        category = self.normalize_category(category or self.detect_category(keyword))
        profile = self.profile_for(category)
        if not profile:
            return 20.0 if self.has_hanbang_or_treatment_signal(keyword) else 0.0

        kw = _compact(keyword)
        score = 42.0 * profile.strategic_weight
        if self.is_business_core_keyword(keyword, category):
            score += 24.0
        if self.has_direct_service_anchor(keyword, category):
            score += 14.0
        if any(_compact(term) in kw for term in self.high_intent_terms):
            score += 12.0
        if include_region_bonus and self.is_target_region(keyword):
            score += 8.0
        if self.low_business_value_reason(keyword, category):
            score -= 45.0
        if self.has_medical_general_without_hanbang(keyword):
            score -= 60.0
        return max(0.0, min(100.0, score))

    def build_seed_keywords(
        self,
        *,
        categories: Optional[Iterable[str]] = None,
        max_terms_per_category: int = 10,
        max_suffixes_per_category: int = 4,
        max_neighborhoods_per_category: int = 4,
        include_contexts: bool = True,
    ) -> List[str]:
        target_categories = {
            self.normalize_category(category) for category in categories
        } if categories else set(self.focus_categories)

        seeds: List[str] = [
            "청주 한의원",
            "청주 한의원 추천",
            "청주 한의원 잘하는곳",
            "청주 야간 한의원",
            "청주 주말 한의원",
        ]
        neighborhoods = self.neighborhoods[:max_neighborhoods_per_category]

        for profile in self.profiles:
            if profile.category not in target_categories:
                continue
            terms = profile.seed_terms[:max_terms_per_category]
            suffixes = profile.longtail_suffixes[:max_suffixes_per_category]
            contexts = profile.longtail_contexts[:3] if include_contexts else ()

            for term in terms:
                seeds.append(f"청주 {term}")

            for term in terms[:5]:
                for suffix in suffixes:
                    seeds.append(f"청주 {term} {suffix}")

            for region in neighborhoods:
                for term in terms[:2]:
                    seeds.append(f"{region} {term}")

            for context in contexts:
                for term in terms[:2]:
                    seeds.append(f"청주 {context} {term}")

        return _unique(seeds)

    def coverage_audit(self, keywords: Iterable[str], min_per_category: int = 3) -> Dict[str, object]:
        counts: Dict[str, int] = {category: 0 for category in self.focus_categories}
        for keyword in keywords:
            category = self.detect_category(keyword)
            category = self.normalize_category(category)
            if category in counts:
                counts[category] += 1
        missing = [category for category, count in counts.items() if count == 0]
        undercovered = {
            category: count
            for category, count in counts.items()
            if 0 < count < min_per_category
        }
        return {
            "counts": counts,
            "missing": missing,
            "undercovered": undercovered,
            "ok": not missing and not undercovered,
        }


GYULIM_KEYWORD_PROFILE = GyulimKeywordProfile()


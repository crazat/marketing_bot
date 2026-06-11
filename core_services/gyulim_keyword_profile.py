"""Shared keyword taxonomy for Cheongju Gyulim Korean-medicine marketing.

The Pathfinder family had the same business rules copied across several files:
regions, treatment categories, seed terms, service anchors, and low-value
leakage terms.  This module keeps those rules explicit and reusable so keyword
discovery, scoring, and UI filtering do not drift apart.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
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

    profile_key = "gyulim_cheongju"
    display_name = "규림 청주"
    primary_region = "청주"
    service_query_anchor = "한의원"
    profile_match_signal = "gyulim_profile_match"
    area_signal = "cheongju_area"
    neighborhood_signal = "cheongju_neighborhood"
    cosmetic_clinic_terms_on_scope = False
    own_brand_terms: Tuple[str, ...] = ("규림", "규림한의원", "kyurim", "gyulim")

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
        "비대칭/교정": "안면비대칭",
        "여드름_피부": "피부/여드름",
        "여드름/피부": "피부/여드름",
        "피부": "피부/여드름",
        "여드름": "피부/여드름",
        "흉터": "피부/여드름",
        "피부/흉터": "피부/여드름",
        "흉터/여드름흉터": "피부/여드름",
        "여드름흉터": "피부/여드름",
        "패인흉터": "피부/여드름",
        "모공흉터": "피부/여드름",
        "수두흉터": "피부/여드름",
        "수술흉터": "피부/여드름",
        "새살침": "피부/여드름",
        "교통사고_입원": "교통사고",
        "교통사고입원": "교통사고",
        "통증": "통증/디스크",
        "통증_디스크": "통증/디스크",
        "디스크": "통증/디스크",
        "리프팅_탄력": "리프팅/탄력",
        "리프팅": "리프팅/탄력",
        "매선": "리프팅/탄력",
        "두통_어지럼증": "두통/어지럼",
        "두통/어지럼증": "두통/어지럼",
        "어지럼증": "두통/어지럼",
        "소화불량_위장": "소화/위장",
        "소화기": "소화/위장",
        "위장": "소화/위장",
        "비염": "호흡기/알레르기",
        "알레르기_아토피": "호흡기/알레르기",
        "알레르기": "호흡기/알레르기",
        "호흡기": "호흡기/알레르기",
        "탈모": "탈모/두피",
        "두피": "탈모/두피",
        "갱년기_호르몬": "갱년기/여성",
        "갱년기": "갱년기/여성",
        "여성건강": "갱년기/여성",
        "불면증_수면": "수면/피로",
        "수면/스트레스": "수면/피로",
        "자율신경_스트레스": "스트레스/자율신경",
        "스트레스": "스트레스/자율신경",
        "산후조리_여성": "여성/산후",
        "다한증_냉증": "다한증/냉증",
        "수험생_집중력": "수험생/집중력",
        "수험생": "수험생/집중력",
        "면역_보약": "면역/보약",
        "보약": "면역/보약",
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
                    "여드름흉터",
                    "여드름흉터 한의원",
                    "새살침",
                    "패인흉터",
                    "모공흉터",
                    "수두흉터",
                    "수술흉터",
                    "여드름 한의원",
                    "상처흉터",
                    "켈로이드",
                    "흉터치료",
                    "흉터 새살침",
                    "피부재생",
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
                    "수두흉터",
                    "수술흉터",
                    "상처흉터",
                    "켈로이드",
                    "흉터치료",
                    "흉터새살침",
                    "피부재생",
                    "색소침착",
                    "붉은자국",
                    "갈색자국",
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
                    "수두흉터",
                    "수술흉터",
                    "상처흉터",
                    "켈로이드",
                    "흉터새살침",
                    "피부재생",
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
                    "수두흉터",
                    "수술흉터",
                    "상처흉터",
                    "켈로이드",
                    "흉터치료",
                    "흉터새살침",
                    "피부재생",
                    "색소침착",
                    "붉은자국",
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
                longtail_suffixes=("비용", "상담", "치료기간", "예약", "후기", "추천", "부작용", "주의사항", "재발"),
                longtail_contexts=(
                    "흉터",
                    "패인흉터",
                    "모공흉터",
                    "수두흉터",
                    "수술흉터",
                    "상처흉터",
                    "켈로이드",
                    "여드름자국",
                    "민감피부",
                    "재발",
                    "성인",
                    "마스크",
                    "압출후",
                ),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("부작용", "주의사항", "재발", "치료기간"),
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
            TreatmentCategoryProfile(
                category="탈모/두피",
                seed_terms=(
                    "탈모",
                    "탈모 한의원",
                    "탈모 한약",
                    "원형탈모",
                    "정수리탈모",
                    "M자탈모",
                    "여성탈모",
                    "두피관리",
                ),
                category_terms=(
                    "탈모",
                    "원형탈모",
                    "정수리탈모",
                    "m자탈모",
                    "M자탈모",
                    "여성탈모",
                    "산후탈모",
                    "두피",
                    "두피관리",
                    "머리숱",
                    "발모",
                ),
                direct_service_anchors=("한의원", "한방", "한약", "탈모한약", "치료", "상담", "두피관리"),
                core_tokens=("탈모", "원형탈모", "정수리탈모", "M자탈모", "여성탈모", "산후탈모", "두피관리"),
                low_business_value_terms=("샴푸", "토닉", "영양제", "미녹시딜", "가발", "두피문신"),
                longtail_suffixes=("비용", "상담", "예약", "추천", "치료기간", "원인"),
                longtail_contexts=("산후", "여성", "원형", "정수리", "스트레스", "환절기"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("원인", "주의사항", "치료기간", "재발"),
                },
                strategic_weight=0.8,
            ),
            TreatmentCategoryProfile(
                category="두통/어지럼",
                seed_terms=(
                    "두통",
                    "두통 한의원",
                    "편두통",
                    "만성두통",
                    "긴장성두통",
                    "어지럼증",
                    "이명",
                    "이석증",
                ),
                category_terms=(
                    "두통",
                    "편두통",
                    "만성두통",
                    "긴장성두통",
                    "어지럼",
                    "어지럼증",
                    "현기증",
                    "이명",
                    "이석증",
                    "목어깨두통",
                ),
                direct_service_anchors=("한의원", "한방", "한약", "침", "추나", "치료", "상담"),
                core_tokens=("두통", "편두통", "만성두통", "어지럼증", "이명", "이석증"),
                low_business_value_terms=("진통제", "타이레놀", "카페인", "두통약", "영양제"),
                longtail_suffixes=("비용", "상담", "예약", "추천", "치료기간", "원인"),
                longtail_contexts=("직장인", "만성", "목어깨", "스트레스", "재발", "검사후"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("원인", "주의사항", "치료기간", "재발"),
                },
                strategic_weight=0.85,
            ),
            TreatmentCategoryProfile(
                category="소화/위장",
                seed_terms=(
                    "소화불량",
                    "소화불량 한의원",
                    "위염",
                    "역류성식도염",
                    "담적",
                    "과민성대장",
                    "속쓰림",
                    "변비",
                ),
                category_terms=(
                    "소화불량",
                    "소화",
                    "위염",
                    "역류성식도염",
                    "역류",
                    "담적",
                    "위장",
                    "속쓰림",
                    "더부룩",
                    "복부팽만",
                    "과민성대장",
                    "변비",
                    "설사",
                    "복통",
                ),
                direct_service_anchors=("한의원", "한방", "한약", "침", "치료", "상담", "담적"),
                core_tokens=("소화불량", "위염", "역류성식도염", "담적", "과민성대장", "변비"),
                low_business_value_terms=("소화제", "유산균", "영양제", "음식", "식단", "배달"),
                longtail_suffixes=("비용", "상담", "예약", "추천", "치료기간", "원인"),
                longtail_contexts=("만성", "직장인", "스트레스", "식후", "재발", "검사후"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("원인", "주의사항", "치료기간", "재발"),
                },
                strategic_weight=0.8,
            ),
            TreatmentCategoryProfile(
                category="호흡기/알레르기",
                seed_terms=(
                    "비염",
                    "비염 한의원",
                    "알레르기비염",
                    "만성비염",
                    "축농증",
                    "코막힘",
                    "후비루",
                    "환절기 비염",
                ),
                category_terms=(
                    "비염",
                    "알레르기비염",
                    "만성비염",
                    "축농증",
                    "부비동염",
                    "코막힘",
                    "콧물",
                    "재채기",
                    "후비루",
                    "알레르기",
                    "환절기",
                    "기침",
                    "천식",
                ),
                direct_service_anchors=("한의원", "한방", "한약", "치료", "상담", "면역"),
                core_tokens=("비염", "알레르기비염", "만성비염", "축농증", "코막힘", "후비루"),
                low_business_value_terms=("스프레이", "마스크", "공기청정기", "영양제", "비염약"),
                longtail_suffixes=("비용", "상담", "예약", "추천", "치료기간", "원인"),
                longtail_contexts=("환절기", "아이", "성인", "만성", "재발", "면역"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("원인", "주의사항", "치료기간", "재발"),
                },
                strategic_weight=0.85,
            ),
            TreatmentCategoryProfile(
                category="갱년기/여성",
                seed_terms=(
                    "갱년기",
                    "갱년기 한의원",
                    "갱년기 한약",
                    "여성 갱년기",
                    "남성 갱년기",
                    "폐경 증상",
                    "안면홍조",
                    "식은땀",
                ),
                category_terms=(
                    "갱년기",
                    "폐경",
                    "폐경기",
                    "안면홍조",
                    "식은땀",
                    "열감",
                    "여성호르몬",
                    "남성갱년기",
                    "여성건강",
                    "생리통",
                    "생리불순",
                ),
                direct_service_anchors=("한의원", "한방", "한약", "보약", "치료", "상담"),
                core_tokens=("갱년기", "갱년기한약", "안면홍조", "폐경", "생리통", "생리불순"),
                low_business_value_terms=("영양제", "건강식품", "홍삼", "홈케어"),
                longtail_suffixes=("비용", "상담", "예약", "추천", "치료기간", "주의사항"),
                longtail_contexts=("40대", "50대", "열감", "불면", "식은땀", "체중증가"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("주의사항", "치료기간", "한약 상담"),
                },
                strategic_weight=0.85,
            ),
            TreatmentCategoryProfile(
                category="수면/피로",
                seed_terms=(
                    "불면증",
                    "불면증 한의원",
                    "수면장애",
                    "잠 안올때",
                    "만성피로",
                    "피로회복",
                    "기력저하",
                    "무기력증",
                ),
                category_terms=(
                    "불면",
                    "불면증",
                    "수면장애",
                    "수면",
                    "잠안올때",
                    "만성피로",
                    "피로",
                    "피로회복",
                    "기력저하",
                    "무기력",
                    "번아웃",
                ),
                direct_service_anchors=("한의원", "한방", "한약", "보약", "치료", "상담"),
                core_tokens=("불면증", "수면장애", "만성피로", "기력저하", "번아웃"),
                low_business_value_terms=("수면제", "영양제", "커피", "카페인", "수면앱"),
                longtail_suffixes=("비용", "상담", "예약", "추천", "치료기간", "원인"),
                longtail_contexts=("직장인", "스트레스", "갱년기", "야간", "만성", "번아웃"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("원인", "주의사항", "치료기간", "한약 상담"),
                },
                strategic_weight=0.8,
            ),
            TreatmentCategoryProfile(
                category="스트레스/자율신경",
                seed_terms=(
                    "자율신경",
                    "자율신경 한의원",
                    "자율신경실조증",
                    "스트레스 한의원",
                    "화병",
                    "공황장애 한의원",
                    "불안장애",
                    "가슴두근거림",
                ),
                category_terms=(
                    "자율신경",
                    "자율신경실조",
                    "스트레스",
                    "화병",
                    "공황",
                    "공황장애",
                    "불안",
                    "불안장애",
                    "우울",
                    "가슴두근거림",
                    "손떨림",
                    "긴장",
                ),
                direct_service_anchors=("한의원", "한방", "한약", "침", "치료", "상담"),
                core_tokens=("자율신경", "자율신경실조", "스트레스", "화병", "공황장애", "불안장애"),
                low_business_value_terms=("상담센터", "심리상담", "명상", "앱", "영양제"),
                longtail_suffixes=("비용", "상담", "예약", "추천", "치료기간", "원인"),
                longtail_contexts=("직장인", "번아웃", "불면", "두근거림", "만성", "재발"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("원인", "주의사항", "치료기간", "한약 상담"),
                },
                strategic_weight=0.75,
            ),
            TreatmentCategoryProfile(
                category="여성/산후",
                seed_terms=(
                    "산후보약",
                    "산후조리 한의원",
                    "산후풍",
                    "출산후 보약",
                    "유산후 관리",
                    "임신준비 한의원",
                    "난임 한의원",
                    "여성한의원",
                ),
                category_terms=(
                    "산후",
                    "산후보약",
                    "산후조리",
                    "산후풍",
                    "출산후",
                    "유산후",
                    "임신준비",
                    "난임",
                    "여성한의원",
                    "여성질환",
                ),
                direct_service_anchors=("한의원", "한방", "한약", "보약", "치료", "상담", "관리"),
                core_tokens=("산후보약", "산후조리", "산후풍", "출산후", "유산후", "임신준비", "난임"),
                low_business_value_terms=("산후도우미", "산후조리원", "마사지", "요가", "필라테스"),
                longtail_suffixes=("비용", "상담", "예약", "추천", "치료기간", "주의사항"),
                longtail_contexts=("출산후", "모유수유", "유산후", "기력회복", "산후풍", "붓기"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("주의사항", "복용 상담", "치료기간"),
                },
                strategic_weight=0.85,
            ),
            TreatmentCategoryProfile(
                category="다한증/냉증",
                seed_terms=(
                    "다한증",
                    "다한증 한의원",
                    "수족냉증",
                    "냉증 한의원",
                    "손땀",
                    "겨드랑이 땀",
                    "손발 차가움",
                    "식은땀",
                ),
                category_terms=(
                    "다한증",
                    "수족냉증",
                    "냉증",
                    "손땀",
                    "발땀",
                    "겨드랑이땀",
                    "식은땀",
                    "손발차가움",
                    "하체냉증",
                ),
                direct_service_anchors=("한의원", "한방", "한약", "침", "치료", "상담"),
                core_tokens=("다한증", "수족냉증", "냉증", "손땀", "식은땀"),
                low_business_value_terms=("데오드란트", "보톡스", "영양제", "패드", "양말"),
                longtail_suffixes=("비용", "상담", "예약", "추천", "치료기간", "원인"),
                longtail_contexts=("여름", "직장인", "긴장", "손발", "재발", "체질"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("원인", "주의사항", "치료기간", "체질 상담"),
                },
                strategic_weight=0.75,
            ),
            TreatmentCategoryProfile(
                category="수험생/집중력",
                seed_terms=(
                    "수험생 한약",
                    "총명탕",
                    "집중력 한의원",
                    "수능 한약",
                    "학생 보약",
                    "시험 불안",
                    "집중력 저하",
                    "기억력",
                ),
                category_terms=(
                    "수험생",
                    "총명탕",
                    "집중력",
                    "수능한약",
                    "학생보약",
                    "시험불안",
                    "집중력저하",
                    "기억력",
                    "공부",
                ),
                direct_service_anchors=("한의원", "한방", "한약", "보약", "총명탕", "상담"),
                core_tokens=("수험생한약", "총명탕", "집중력", "수능한약", "학생보약", "시험불안"),
                low_business_value_terms=("학원", "과외", "인강", "독서실", "스터디카페"),
                longtail_suffixes=("비용", "상담", "예약", "추천", "복용기간", "주의사항"),
                longtail_contexts=("고3", "중3", "수능", "시험전", "집중력", "체력"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "추천"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("주의사항", "복용기간", "한약 상담"),
                },
                strategic_weight=0.75,
            ),
            TreatmentCategoryProfile(
                category="면역/보약",
                seed_terms=(
                    "보약",
                    "보약 한의원",
                    "공진단",
                    "경옥고",
                    "면역력",
                    "체력보강",
                    "기력회복",
                    "대상포진 후유증",
                ),
                category_terms=(
                    "보약",
                    "공진단",
                    "경옥고",
                    "면역",
                    "면역력",
                    "체력보강",
                    "기력회복",
                    "허약",
                    "환절기감기",
                    "대상포진후유증",
                ),
                direct_service_anchors=("한의원", "한방", "한약", "보약", "공진단", "경옥고", "상담"),
                core_tokens=("보약", "공진단", "경옥고", "면역력", "체력보강", "기력회복"),
                low_business_value_terms=("건강식품", "영양제", "홍삼", "비타민", "쇼핑"),
                longtail_suffixes=("가격", "비용", "상담", "예약", "추천", "복용기간"),
                longtail_contexts=("어르신", "직장인", "수험생", "환절기", "회복", "만성피로"),
                journey_suffixes={
                    "decision": ("가격", "비용", "상담", "예약"),
                    "access": ("주차", "야간", "주말", "진료시간"),
                    "safety": ("복용기간", "주의사항", "체질 상담"),
                },
                strategic_weight=0.75,
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
        if profile.strategic_weight < 1.0:
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
        if profile.strategic_weight < 1.0:
            return self.is_business_core_keyword(keyword, category) or self.has_direct_service_anchor(keyword, category)
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

        primary_region = getattr(self, "primary_region", "청주")
        service_anchor = getattr(self, "service_query_anchor", "한의원")

        seeds: List[str] = [
            f"{primary_region} {service_anchor}",
            f"{primary_region} {service_anchor} 추천",
            f"{primary_region} {service_anchor} 잘하는곳",
            f"{primary_region} 야간 {service_anchor}",
            f"{primary_region} 주말 {service_anchor}",
        ]
        neighborhoods = self.neighborhoods[:max_neighborhoods_per_category]

        for profile in self.profiles:
            if profile.category not in target_categories:
                continue
            terms = profile.seed_terms[:max_terms_per_category]
            suffixes = profile.longtail_suffixes[:max_suffixes_per_category]
            contexts = profile.longtail_contexts[:3] if include_contexts else ()

            for term in terms:
                seeds.append(f"{primary_region} {term}")

            for term in terms[:5]:
                for suffix in suffixes:
                    seeds.append(f"{primary_region} {term} {suffix}")

            for region in neighborhoods:
                for term in terms[:2]:
                    seeds.append(f"{region} {term}")

            for context in contexts:
                for term in terms[:2]:
                    seeds.append(f"{primary_region} {context} {term}")

        return _unique(seeds)

    def build_exploration_seed_keywords(
        self,
        *,
        categories: Optional[Iterable[str]] = None,
        max_terms_per_category: int = 8,
        max_suffixes_per_category: int = 6,
        max_contexts_per_category: int = 5,
        max_neighborhoods_per_category: int = 6,
    ) -> List[str]:
        """Build broad patient-journey seeds beyond autocomplete-friendly terms.

        Autocomplete tends to over-represent short head terms.  These seeds force
        Pathfinder to inspect problem, context, decision, access, and safety
        searches that are sparse but high intent for a local clinic.
        """
        target_categories = {
            self.normalize_category(category) for category in categories
        } if categories else set(self.focus_categories)

        primary_region = getattr(self, "primary_region", "청주")
        service_anchor = getattr(self, "service_query_anchor", "한의원")
        regions = (primary_region,) + self.neighborhoods[:max_neighborhoods_per_category]
        universal_suffixes = (
            "비용",
            "상담",
            "예약",
            "추천",
            "치료기간",
            "부작용",
            "주의사항",
            "야간",
            "주말",
            "주차",
            "잘하는곳",
        )
        question_patterns = (
            "{region} {term} 비용 얼마",
            "{region} {term} " + service_anchor + " 어디",
            "{region} {term} 상담 가능한곳",
            "{region} {term} 야간 진료",
            "{region} {term} 주차 편한 " + service_anchor,
        )

        seeds: List[str] = []
        for profile in self.profiles:
            if profile.category not in target_categories:
                continue

            terms = _unique(profile.seed_terms + profile.core_tokens)[:max_terms_per_category]
            journey_suffixes: List[str] = []
            for suffix_group in profile.journey_suffixes.values():
                journey_suffixes.extend(suffix_group)
            suffixes = _unique(
                list(profile.longtail_suffixes)
                + journey_suffixes
                + list(universal_suffixes)
            )[:max_suffixes_per_category]
            contexts = profile.longtail_contexts[:max_contexts_per_category]

            for term in terms:
                for suffix in suffixes:
                    seeds.append(f"{primary_region} {term} {suffix}")
                for context in contexts:
                    seeds.append(f"{primary_region} {context} {term}")
                    seeds.append(f"{primary_region} {term} {context}")

            for region in regions:
                for term in terms[:4]:
                    seeds.append(f"{region} {term} {service_anchor}")
                    for suffix in suffixes[:6]:
                        seeds.append(f"{region} {term} {service_anchor} {suffix}")
                    for pattern in question_patterns[:3]:
                        seeds.append(pattern.format(region=region, term=term))

            for context in contexts:
                for term in terms[:3]:
                    for suffix in suffixes[:3]:
                        seeds.append(f"{primary_region} {context} {term} {suffix}")

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

class RecoverGangnamKeywordProfile(GyulimKeywordProfile):
    """Keyword taxonomy for RECOVER Gangnam scar, skin, asymmetry, and diet care."""

    profile_key = "recover_gangnam"
    display_name = "리커버 강남"
    primary_region = "강남"
    service_query_anchor = "클리닉"
    profile_match_signal = "recover_profile_match"
    area_signal = "gangnam_area"
    neighborhood_signal = "gangnam_neighborhood"
    cosmetic_clinic_terms_on_scope = True
    own_brand_terms: Tuple[str, ...] = ("리커버", "리커버의원", "recover")

    cheongju_regions: Tuple[str, ...] = (
        "강남",
        "강남구",
        "강남역",
        "신논현",
        "논현",
        "언주",
        "선릉",
        "역삼",
        "삼성",
        "청담",
        "압구정",
        "신사",
        "서초",
        "교대",
        "양재",
    )
    neighborhoods: Tuple[str, ...] = (
        "강남역",
        "신논현",
        "역삼동",
        "논현동",
        "신사동",
        "청담동",
        "삼성동",
        "대치동",
        "도곡동",
        "압구정동",
        "서초동",
        "반포동",
        "잠원동",
        "선릉",
        "언주",
        "학동",
        "논현",
        "역삼",
        "삼성",
        "청담",
        "압구정",
    )
    nearby_regions: Tuple[str, ...] = ("서초", "송파", "잠실", "성수", "용산", "분당", "판교")

    hanbang_indicators: Tuple[str, ...] = (
        "의원",
        "클리닉",
        "병원",
        "피부과",
        "성형외과",
        "피부클리닉",
        "흉터클리닉",
        "비만클리닉",
        "다이어트클리닉",
        "상담",
        "진료",
        "치료",
        "시술",
        "레이저",
        "주사",
        "처방",
        "리커버",
        "recover",
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
        "회복",
        "회복기간",
        "통증",
        "붓기",
        "멍",
        "당일",
        "야간",
        "주말",
        "진료시간",
        "전문의",
        "원장",
        "실비",
        "근처",
    )
    medical_general_tokens: Tuple[str, ...] = (
        "치과",
        "정형외과",
        "한의원",
        "한방병원",
        "내과",
        "이비인후과",
        "안과",
        "비뇨기과",
        "산부인과",
        "소아과",
        "응급실",
    )
    category_aliases: Dict[str, str] = {
        "흉터": "흉터/여드름흉터",
        "여드름흉터": "흉터/여드름흉터",
        "수술흉터": "흉터/여드름흉터",
        "피부": "피부/여드름",
        "여드름": "피부/여드름",
        "여드름_피부": "피부/여드름",
        "여드름/피부": "피부/여드름",
        "피부/흉터": "흉터/여드름흉터",
        "비대칭/교정": "안면비대칭",
        "비대칭_교정": "안면비대칭",
        "안면비대칭_교정": "안면비대칭",
        "안면비대칭교정": "안면비대칭",
        "얼굴비대칭": "안면비대칭",
        "다이어트/비만": "다이어트",
        "비만": "다이어트",
        "체형": "체형교정",
        "체형/바디": "체형교정",
        "리프팅": "리프팅/탄력",
        "탄력": "리프팅/탄력",
        "스킨부스터": "피부/여드름",
    }

    def __init__(self) -> None:
        self.profiles: Tuple[TreatmentCategoryProfile, ...] = (
            TreatmentCategoryProfile(
                category="흉터/여드름흉터",
                seed_terms=(
                    "흉터",
                    "흉터 치료",
                    "여드름흉터",
                    "패인흉터",
                    "모공흉터",
                    "수두흉터",
                    "수술흉터",
                    "켈로이드",
                    "흉터레이저",
                    "흉터재생",
                    "흉터클리닉",
                    "새살침",
                ),
                category_terms=(
                    "흉터",
                    "여드름흉터",
                    "패인흉터",
                    "모공흉터",
                    "수두흉터",
                    "수술흉터",
                    "켈로이드",
                    "색소침착",
                    "흉터자국",
                    "흉터재생",
                    "흉터치료",
                    "흉터레이저",
                    "새살침",
                ),
                direct_service_anchors=(
                    "의원",
                    "클리닉",
                    "병원",
                    "피부과",
                    "상담",
                    "치료",
                    "시술",
                    "레이저",
                    "재생",
                    "흉터클리닉",
                ),
                core_tokens=("흉터", "여드름흉터", "패인흉터", "수술흉터", "켈로이드", "모공흉터"),
                low_business_value_terms=("연고", "패치", "화장품", "홈케어", "셀프", "민간요법", "타투커버"),
                longtail_suffixes=("비용", "상담", "예약", "후기", "추천", "회복기간", "부작용", "주의사항", "통증"),
                longtail_contexts=("패인", "깊은", "오래된", "얼굴", "볼", "코", "수술 후", "붉은 자국"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "가격"),
                    "validation": ("후기", "추천", "잘하는곳", "전문의"),
                    "safety": ("부작용", "주의사항", "회복기간", "통증"),
                },
                strategic_weight=1.35,
            ),
            TreatmentCategoryProfile(
                category="안면비대칭",
                seed_terms=(
                    "안면비대칭",
                    "얼굴비대칭",
                    "턱비대칭",
                    "광대비대칭",
                    "좌우비대칭",
                    "얼굴균형",
                    "턱관절 비대칭",
                    "비대칭 상담",
                ),
                category_terms=(
                    "안면비대칭",
                    "얼굴비대칭",
                    "턱비대칭",
                    "광대비대칭",
                    "좌우비대칭",
                    "얼굴균형",
                    "얼굴라인",
                    "턱관절",
                    "비대칭",
                    "윤곽",
                ),
                direct_service_anchors=("의원", "클리닉", "상담", "진료", "교정", "분석", "검사", "촬영"),
                core_tokens=("안면비대칭", "얼굴비대칭", "턱비대칭", "비대칭", "턱관절", "얼굴균형"),
                low_business_value_terms=("셀프", "마사지", "운동", "유튜브", "홈케어", "보정앱"),
                longtail_suffixes=("비용", "상담", "예약", "후기", "추천", "검사", "원인", "교정기간"),
                longtail_contexts=("턱", "광대", "입꼬리", "사진", "웨딩", "면접", "증명사진"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "검사"),
                    "validation": ("후기", "추천", "잘하는곳"),
                    "safety": ("원인", "교정기간", "주의사항"),
                },
                strategic_weight=1.25,
            ),
            TreatmentCategoryProfile(
                category="피부/여드름",
                seed_terms=(
                    "피부",
                    "여드름",
                    "성인여드름",
                    "피부트러블",
                    "모공",
                    "색소침착",
                    "기미",
                    "홍조",
                    "피부재생",
                    "스킨부스터",
                    "리쥬란",
                    "쥬베룩",
                ),
                category_terms=(
                    "피부",
                    "여드름",
                    "성인여드름",
                    "트러블",
                    "모공",
                    "색소침착",
                    "기미",
                    "잡티",
                    "홍조",
                    "피부결",
                    "피부재생",
                    "스킨부스터",
                    "리쥬란",
                    "쥬베룩",
                    "포텐자",
                ),
                direct_service_anchors=("의원", "클리닉", "피부과", "상담", "치료", "시술", "레이저", "주사", "관리"),
                core_tokens=("피부", "여드름", "트러블", "모공", "색소침착", "홍조", "피부재생"),
                low_business_value_terms=("화장품", "폼클렌징", "클렌징", "홈케어", "팩", "올리브영", "셀프"),
                longtail_suffixes=("비용", "상담", "예약", "후기", "추천", "부작용", "회복기간"),
                longtail_contexts=("성인", "턱", "볼", "마스크", "민감성", "피부결", "웨딩"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "가격"),
                    "validation": ("후기", "추천", "잘하는곳"),
                    "safety": ("부작용", "주의사항", "회복기간"),
                },
                strategic_weight=1.15,
            ),
            TreatmentCategoryProfile(
                category="다이어트",
                seed_terms=(
                    "다이어트",
                    "비만클리닉",
                    "다이어트약",
                    "식욕억제",
                    "체중감량",
                    "지방분해",
                    "비만관리",
                    "삭센다",
                    "위고비",
                    "마운자로",
                ),
                category_terms=(
                    "다이어트",
                    "비만",
                    "체중",
                    "감량",
                    "체지방",
                    "식욕억제",
                    "다이어트약",
                    "비만클리닉",
                    "지방분해",
                    "삭센다",
                    "위고비",
                    "마운자로",
                    "요요",
                ),
                direct_service_anchors=("의원", "클리닉", "상담", "진료", "처방", "주사", "약", "비만클리닉"),
                core_tokens=("다이어트", "비만", "체중", "감량", "체지방", "식욕억제", "다이어트약"),
                low_business_value_terms=("댄스", "줌바", "요가", "필라테스", "헬스", "pt", "홈트", "식단", "도시락"),
                longtail_suffixes=("비용", "상담", "예약", "후기", "추천", "부작용", "처방", "요요"),
                longtail_contexts=("직장인", "웨딩", "산후", "복부", "허벅지", "팔뚝", "단기"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약", "처방"),
                    "validation": ("후기", "추천", "잘하는곳"),
                    "safety": ("부작용", "주의사항", "요요"),
                },
                strategic_weight=1.2,
            ),
            TreatmentCategoryProfile(
                category="리프팅/탄력",
                seed_terms=(
                    "리프팅",
                    "피부탄력",
                    "주름",
                    "탄력관리",
                    "콜라겐",
                    "스킨부스터",
                    "볼처짐",
                    "팔자주름",
                ),
                category_terms=(
                    "리프팅",
                    "탄력",
                    "주름",
                    "처짐",
                    "피부탄력",
                    "콜라겐",
                    "팔자주름",
                    "볼처짐",
                    "목주름",
                    "스킨부스터",
                ),
                direct_service_anchors=("의원", "클리닉", "피부과", "상담", "시술", "레이저", "주사"),
                core_tokens=("리프팅", "탄력", "주름", "처짐", "피부탄력", "팔자주름"),
                low_business_value_terms=("화장품", "팩", "마사지", "홈케어", "괄사", "셀프"),
                longtail_suffixes=("비용", "상담", "예약", "후기", "추천", "부작용", "회복기간"),
                longtail_contexts=("팔자", "볼", "턱선", "목", "눈가", "웨딩", "동안"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약"),
                    "validation": ("후기", "추천", "잘하는곳"),
                    "safety": ("부작용", "주의사항", "회복기간"),
                },
                strategic_weight=1.05,
            ),
            TreatmentCategoryProfile(
                category="체형교정",
                seed_terms=(
                    "체형교정",
                    "바디라인",
                    "골반비대칭",
                    "승모근",
                    "종아리라인",
                    "복부라인",
                    "팔뚝라인",
                ),
                category_terms=(
                    "체형",
                    "체형교정",
                    "바디라인",
                    "골반",
                    "골반비대칭",
                    "승모근",
                    "종아리",
                    "복부",
                    "팔뚝",
                    "라인",
                ),
                direct_service_anchors=("의원", "클리닉", "상담", "진료", "시술", "관리", "분석"),
                core_tokens=("체형", "체형교정", "바디라인", "골반비대칭", "승모근", "종아리"),
                low_business_value_terms=("헬스", "pt", "요가", "필라테스", "홈트", "운동", "마사지", "셀프"),
                longtail_suffixes=("비용", "상담", "예약", "후기", "추천", "기간"),
                longtail_contexts=("웨딩", "직장인", "어깨", "골반", "종아리", "복부", "팔뚝"),
                journey_suffixes={
                    "decision": ("비용", "상담", "예약"),
                    "validation": ("후기", "추천", "잘하는곳"),
                    "safety": ("기간", "주의사항", "통증"),
                },
                strategic_weight=0.95,
            ),
        )
        self._profile_by_category: Dict[str, TreatmentCategoryProfile] = {
            profile.category: profile for profile in self.profiles
        }


GYULIM_KEYWORD_PROFILE = GyulimKeywordProfile()
RECOVER_GANGNAM_KEYWORD_PROFILE = RecoverGangnamKeywordProfile()


def _read_business_profile_key() -> str:
    explicit = os.getenv("MARKETING_BOT_CLINIC_PROFILE") or os.getenv("CLINIC_KEYWORD_PROFILE")
    if explicit:
        return explicit.strip().lower()

    profile_path = Path(__file__).resolve().parent.parent / "config" / "business_profile.json"
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    explicit_config = str(data.get("clinic_profile") or data.get("profile_key") or "").strip().lower()
    if explicit_config:
        return explicit_config

    business = data.get("business") or {}
    marker = " ".join(
        str(business.get(key) or "")
        for key in ("name", "short_name", "english_name", "region", "address")
    ).lower()
    if any(token in marker for token in ("리커버", "recover", "강남", "gangnam")):
        return "recover_gangnam"
    return "gyulim_cheongju"


def get_active_keyword_profile() -> GyulimKeywordProfile:
    key = _read_business_profile_key()
    if key in {"recover", "recover_gangnam", "gangnam", "리커버", "리커버강남"}:
        return RECOVER_GANGNAM_KEYWORD_PROFILE
    return GYULIM_KEYWORD_PROFILE


ACTIVE_KEYWORD_PROFILE = get_active_keyword_profile()
CLINIC_KEYWORD_PROFILE = ACTIVE_KEYWORD_PROFILE

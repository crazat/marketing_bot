"""[Q11] 카테고리 정규화 - keyword_insights(50종) -> viral_targets(11종) 매핑.

keyword_insights에는 동의어가 난립함:
  - "여드름/피부", "여드름_피부", "피부/여드름" 모두 같은 의미
  - "다이어트" vs "다이어트/비만"
  - "통증", "통증_디스크", "통증/디스크" 등

viral_targets와 frontend(types/viral.ts CATEGORIES)는 11종 표준만 사용.
이 함수가 양쪽 시스템의 단일 진입점.

frontend CATEGORIES와 일관성 유지 필수 (frontend/src/types/viral.ts).
"""
from __future__ import annotations

from typing import Optional


# viral_targets / frontend 표준 카테고리 (11종)
STANDARD_CATEGORIES = [
    "다이어트",
    "비대칭/교정",
    "피부",
    "교통사고",
    "통증/디스크",
    "두통/어지럼",
    "소화기",
    "호흡기",
    "기타증상",
    "경쟁사_역공략",
    "기타",
]


# keyword_insights 카테고리 -> 표준 카테고리
# 키는 lower-cased + 공백/구분자 정규화 후 비교
_ALIAS_MAP: dict[str, str] = {
    # 다이어트
    "다이어트": "다이어트",
    "다이어트/비만": "다이어트",
    "다이어트_비만": "다이어트",
    # 비대칭/교정
    "비대칭/교정": "비대칭/교정",
    "안면비대칭": "비대칭/교정",
    "안면비대칭_교정": "비대칭/교정",
    "안면비대칭/교정": "비대칭/교정",
    "체형교정": "비대칭/교정",
    # 피부
    "피부": "피부",
    "피부/여드름": "피부",
    "여드름/피부": "피부",
    "여드름_피부": "피부",
    "리프팅_탄력": "피부",
    "리프팅/성형": "피부",
    "리프팅/탄력": "피부",
    "알레르기_아토피": "피부",
    "알레르기/아토피": "피부",
    # 교통사고
    "교통사고": "교통사고",
    "교통사고_입원": "교통사고",
    "교통사고/입원": "교통사고",
    # 통증/디스크
    "통증": "통증/디스크",
    "통증_디스크": "통증/디스크",
    "통증/디스크": "통증/디스크",
    "추나": "통증/디스크",
    # 두통/어지럼
    "두통_어지럼증": "두통/어지럼",
    "두통/어지럼": "두통/어지럼",
    "두통/어지럼증": "두통/어지럼",
    # 소화기
    "소화불량_위장": "소화기",
    "소화/위장": "소화기",
    "소화_위장": "소화기",
    "소화기": "소화기",
    # 호흡기
    "비염": "호흡기",
    "호흡기": "호흡기",
    "감기": "호흡기",
    # 기타증상
    "탈모": "기타증상",
    "탈모_모발": "기타증상",
    "탈모/모발": "기타증상",
    "다한증_냉증": "기타증상",
    "다한증/냉증": "기타증상",
    "불면증": "기타증상",
    "불면증_수면": "기타증상",
    "불면증/수면": "기타증상",
    "갱년기": "기타증상",
    "갱년기_호르몬": "기타증상",
    "갱년기/호르몬": "기타증상",
    "자율신경_스트레스": "기타증상",
    "스트레스/자율신경": "기타증상",
    "이석증": "기타증상",
    # 기타 (한의원 일반/접근성/임시 분류 미정)
    "한의원일반": "기타",
    "여성건강": "기타",
    "여성건강/산후조리": "기타",
    "면역_보약": "기타",
    "면역/보약": "기타",
    "산후조리": "기타",
    "산후조리_여성": "기타",
    "수험생_집중력": "기타",
    "수험생/집중력": "기타",
    "야간진료": "기타",
    "야간진료_접근성": "기타",
    "야간진료/접근성": "기타",
    "지역명": "기타",
    "기타": "기타",
    # 경쟁사 분석 결과
    "경쟁사_역공략": "경쟁사_역공략",
    "경쟁사/역공략": "경쟁사_역공략",
}


def _canonicalize(raw: str) -> str:
    """공백 제거 + lowercase로 비교용 키 생성."""
    return raw.replace(" ", "").lower()


# 정규화된 키-기반 매핑 (런타임 lookup용)
_NORMALIZED_MAP: dict[str, str] = {
    _canonicalize(k): v for k, v in _ALIAS_MAP.items()
}


def normalize_category(raw: Optional[str]) -> str:
    """임의 카테고리 문자열을 표준 11종 중 하나로 정규화.

    매칭 실패 시 '기타' 반환. 알 수 없는 분류는 silent 폴백 (frontend 깨지지 않게).
    """
    if not raw:
        return "기타"

    key = _canonicalize(str(raw))
    if not key:
        return "기타"

    # 직접 매칭
    if key in _NORMALIZED_MAP:
        return _NORMALIZED_MAP[key]

    # 부분 매칭 (예: "청주_다이어트_여성" 같은 변형) — 표준 11종 중 포함되면 그것 사용
    for std in STANDARD_CATEGORIES:
        if _canonicalize(std) in key:
            return std

    # 키워드 기반 휴리스틱 (마지막 폴백)
    if any(t in key for t in ("다이어트", "비만", "체중")):
        return "다이어트"
    if any(t in key for t in ("비대칭", "교정")):
        return "비대칭/교정"
    if any(t in key for t in ("여드름", "피부", "리프팅", "탄력", "흉터")):
        return "피부"
    if any(t in key for t in ("교통사고", "사고")):
        return "교통사고"
    if any(t in key for t in ("디스크", "허리", "목", "어깨", "통증", "추나", "도수")):
        return "통증/디스크"
    if any(t in key for t in ("두통", "편두통", "어지", "현훈")):
        return "두통/어지럼"
    if any(t in key for t in ("소화", "위장", "역류", "변비")):
        return "소화기"
    if any(t in key for t in ("비염", "감기", "기침", "천식", "호흡")):
        return "호흡기"

    return "기타"


__all__ = ["normalize_category", "STANDARD_CATEGORIES"]

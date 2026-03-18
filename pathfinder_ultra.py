#!/usr/bin/env python3
"""
Pathfinder ULTRA - 고도화된 키워드 발굴 시스템
============================================

주요 개선사항:
1. MF-KEI 2.0: Multi-Factor KEI 점수 (가짜 Golden 99% 제거)
2. 스마트 시드 엔진 (SSE): 4-Source Seed Fusion
3. SERP 딥 분석 엔진 (SDE): 3-Layer 분석
4. 경쟁사 인텔리전스 시스템 (CIS): 자동 발견 및 갭 분석
5. 지역 확장 인텔리전스 (GEI): 4-Ring 동심원 확장

지원 카테고리 (16개):
- 다이어트, 안면비대칭_교정, 여드름_피부, 리프팅_탄력
- 교통사고_입원, 통증_디스크, 갱년기_호르몬, 불면증_수면
- 소화불량_위장, 두통_어지럼증, 알레르기_아토피, 자율신경_스트레스
- 산후조리_여성, 다한증_냉증, 수험생_집중력, 면역_보약
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import json
import time
import sqlite3
import requests
import argparse
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from pathlib import Path


# ============================================================
# 상수 및 설정
# ============================================================

# 16개 전체 카테고리 (절대 누락 금지)
ALL_CATEGORIES = [
    # ===== 메인 5대 카테고리 =====
    "다이어트",
    "안면비대칭_교정",
    "여드름_피부",
    "리프팅_탄력",
    "교통사고_입원",
    # ===== 서브 카테고리 =====
    "통증_디스크",
    "갱년기_호르몬",
    "불면증_수면",
    "소화불량_위장",
    "두통_어지럼증",
    "알레르기_아토피",
    "자율신경_스트레스",
    "산후조리_여성",
    "다한증_냉증",
    "수험생_집중력",
    "면역_보약",
    # ===== 추가 카테고리 (LEGION 호환) =====
    "탈모_모발",
    "야간진료_접근성"
]

# 공급 필터 임계값 (Phase 1)
SUPPLY_FILTER = {
    "MIN_SUPPLY": 10,       # 블로그 10개 미만 = 가짜 Golden
    "MAX_SUPPLY": 30000,    # 블로그 3만개 초과 = Red Ocean
    "SWEET_SPOT_MIN": 50,   # 최적 범위 시작
    "SWEET_SPOT_MAX": 3000  # 최적 범위 끝
}

# 지역 Ring 설정 (Phase 4)
GEOGRAPHIC_RINGS = {
    "ring0": {
        "name": "청주 핵심",
        "regions": ["청주", "상당", "서원", "흥덕", "청원"],
        "neighborhoods": [
            "복대동", "가경동", "분평동", "봉명동", "사창동",
            "산남동", "수곡동", "모충동", "용암동", "금천동",
            "율량동", "사직동", "성화동", "내덕동", "우암동",
            "강서동", "신봉동", "개신동", "죽림동", "비하동"
        ],
        "priority": 1.0,
        "all_categories": True  # 모든 카테고리 공략
    },
    "ring1": {
        "name": "청주 인접",
        "regions": ["오창", "오송", "세종"],
        "neighborhoods": ["오창읍", "오송읍", "조치원"],
        "priority": 0.8,
        "target_categories": [
            "다이어트", "교통사고_입원", "안면비대칭_교정",
            "여드름_피부", "통증_디스크"
        ]
    },
    "ring2": {
        "name": "확장 권역",
        "regions": ["진천", "증평", "괴산", "보은"],
        "neighborhoods": [],
        "priority": 0.6,
        "target_categories": [
            "안면비대칭_교정", "여드름_피부", "면역_보약",
            "다이어트", "탈모_모발", "교통사고_입원", "리프팅_탄력"
        ]
    },
    "ring3": {
        "name": "광역 권역",
        "regions": ["충주", "제천", "음성", "대전"],
        "neighborhoods": [],
        "priority": 0.4,
        "target_categories": [
            "안면비대칭_교정",  # 특수 시술
            "다이어트",         # 광역 수요
            "탈모_모발",        # 광역 수요
            "교통사고_입원"     # 광역 수요
        ]
    }
}


# ============================================================
# 데이터 클래스
# ============================================================

@dataclass
class KeywordResult:
    """키워드 분석 결과"""
    keyword: str
    search_volume: int = 0
    supply: int = 0  # 블로그 수
    difficulty: int = 50
    opportunity: int = 50

    # MF-KEI 2.0 구성요소
    mf_kei_score: float = 0.0
    demand_factor: float = 1.0
    supply_factor: float = 1.0
    competition_factor: float = 1.0
    intent_factor: float = 1.0
    trend_factor: float = 1.0

    # 메타데이터
    grade: str = "C"
    category: str = "기타"
    source: str = "unknown"
    region: str = "청주"
    ring: int = 0

    # 검색 의도
    search_intent: str = "unknown"

    # 트렌드
    trend_slope: float = 0.0
    trend_status: str = "unknown"

    # 경쟁사 관련
    is_gap_keyword: bool = False
    competitor_weakness: str = ""

    # 시즌
    is_seasonal: bool = False
    peak_months: List[int] = field(default_factory=list)

    # 병합 정보
    merged_from: List[str] = field(default_factory=list)


# ============================================================
# Phase 1: 공급 필터 강화
# ============================================================

class SupplyFilter:
    """공급 기반 키워드 필터"""

    @staticmethod
    def classify_supply(supply: int) -> Tuple[str, float]:
        """
        공급량 분류 및 팩터 계산

        Returns:
            (분류명, supply_factor)
        """
        if supply < SUPPLY_FILTER["MIN_SUPPLY"]:
            return "fake_golden", 0.1  # 가짜 Golden 패널티
        elif supply > SUPPLY_FILTER["MAX_SUPPLY"]:
            return "red_ocean", 0.3  # Red Ocean 패널티
        elif supply <= 100:
            return "blue_ocean", 2.0  # Blue Ocean 보너스
        elif supply <= SUPPLY_FILTER["SWEET_SPOT_MAX"]:
            return "sweet_spot", 1.5  # Sweet Spot 보너스
        elif supply <= 10000:
            return "moderate", 1.0  # 보통
        else:
            return "competitive", 0.7  # 경쟁 심함

    @staticmethod
    def should_exclude(supply: int) -> Tuple[bool, str]:
        """
        키워드 제외 여부 판단

        Returns:
            (제외여부, 사유)
        """
        if supply < SUPPLY_FILTER["MIN_SUPPLY"]:
            return True, f"가짜 Golden (공급 {supply} < {SUPPLY_FILTER['MIN_SUPPLY']})"
        if supply > SUPPLY_FILTER["MAX_SUPPLY"]:
            return True, f"Red Ocean (공급 {supply:,} > {SUPPLY_FILTER['MAX_SUPPLY']:,})"
        return False, ""


# ============================================================
# Phase 2: MF-KEI 2.0 (Multi-Factor KEI)
# ============================================================

class MFKEI:
    """Multi-Factor KEI 점수 계산기"""

    # 검색 의도별 가중치
    INTENT_WEIGHTS = {
        "transactional": 1.8,  # 가격, 비용, 예약
        "commercial": 1.5,     # 후기, 추천, 비교
        "informational": 1.0,  # 효과, 방법, 증상
        "navigational": 0.8,   # 위치, 주소, 연락처
        "unknown": 1.0
    }

    # 의도 분류 패턴
    INTENT_PATTERNS = {
        "transactional": ["가격", "비용", "할인", "이벤트", "예약", "상담", "무료", "체험"],
        "commercial": ["추천", "비교", "순위", "후기", "리뷰", "잘하는", "유명한", "좋은", "전문", "1위"],
        "informational": ["방법", "효과", "원인", "증상", "치료", "기간", "부작용", "주의", "차이"],
        "navigational": ["위치", "주소", "전화", "영업시간", "휴무", "주차", "근처", "가까운"]
    }

    @classmethod
    def classify_intent(cls, keyword: str) -> str:
        """검색 의도 분류"""
        kw_lower = keyword.lower()
        scores = {intent: 0 for intent in cls.INTENT_PATTERNS}

        for intent, patterns in cls.INTENT_PATTERNS.items():
            for pattern in patterns:
                if pattern in kw_lower:
                    scores[intent] += 1

        max_score = max(scores.values())
        if max_score > 0:
            for intent, score in scores.items():
                if score == max_score:
                    return intent

        return "commercial"  # 한의원 키워드 기본값

    @classmethod
    def calculate(cls, result: KeywordResult) -> float:
        """
        MF-KEI 점수 계산

        Formula: Base × Demand × Supply × Competition × Intent × Trend
        """
        # 1. Base Score (검색량 기반)
        if result.search_volume >= 500:
            base = 100
        elif result.search_volume >= 100:
            base = 80
        elif result.search_volume >= 50:
            base = 60
        elif result.search_volume >= 20:
            base = 40
        elif result.search_volume >= 10:
            base = 25
        else:
            base = 10

        # 2. Demand Factor (수요 신뢰도)
        # 검색량이 있고 공급도 어느 정도 있으면 신뢰
        if result.search_volume > 0 and result.supply >= 10:
            result.demand_factor = 1.2
        elif result.search_volume > 0:
            result.demand_factor = 1.0
        else:
            result.demand_factor = 0.5

        # 3. Supply Factor (공급 적정성)
        _, result.supply_factor = SupplyFilter.classify_supply(result.supply)

        # 4. Competition Factor (SERP 경쟁도)
        # difficulty 점수 기반 (0-100, 낮을수록 좋음)
        result.competition_factor = (100 - result.difficulty) / 50  # 0-2 범위
        result.competition_factor = max(0.5, min(2.0, result.competition_factor))

        # 5. Intent Factor (구매 의도)
        result.search_intent = cls.classify_intent(result.keyword)
        result.intent_factor = cls.INTENT_WEIGHTS.get(result.search_intent, 1.0)

        # 6. Trend Factor (트렌드)
        if result.trend_slope > 0.5:
            result.trend_factor = 1.5
        elif result.trend_slope > 0:
            result.trend_factor = 1.2
        elif result.trend_slope > -0.3:
            result.trend_factor = 1.0
        else:
            result.trend_factor = 0.7

        # 최종 MF-KEI 계산
        result.mf_kei_score = (
            base
            * result.demand_factor
            * result.supply_factor
            * result.competition_factor
            * result.intent_factor
            * result.trend_factor
        )

        return result.mf_kei_score

    @classmethod
    def assign_grade(cls, result: KeywordResult) -> str:
        """MF-KEI 점수 기반 등급 부여"""
        score = result.mf_kei_score

        if score >= 200:
            result.grade = "S"
        elif score >= 100:
            result.grade = "A"
        elif score >= 50:
            result.grade = "B"
        else:
            result.grade = "C"

        return result.grade


# ============================================================
# Phase 3: 시즌 키워드 DB
# ============================================================

class SeasonalKeywordDB:
    """월별 시즌 키워드 데이터베이스"""

    # 카테고리별 시즌 키워드 (메인 5개 카테고리 강화)
    SEASONAL_KEYWORDS = {
        # ============ 메인 카테고리 (강화) ============
        "다이어트": {
            1: ["새해 다이어트", "신년 다이어트", "겨울 다이어트", "1월 다이어트"],
            2: ["졸업 다이어트", "취업준비 다이어트", "봄맞이 다이어트"],
            3: ["봄 다이어트", "졸업 다이어트", "취업 다이어트", "환절기 다이어트"],
            4: ["봄 다이어트", "웨딩 다이어트", "결혼준비 다이어트"],
            5: ["여름 준비 다이어트", "웨딩 다이어트", "5월 다이어트"],
            6: ["여름 다이어트", "휴가전 다이어트", "반팔 다이어트"],
            7: ["여름 다이어트", "휴가 전 다이어트", "비키니 다이어트", "수영복 다이어트"],
            8: ["여름 다이어트", "가을준비 다이어트"],
            9: ["가을 다이어트", "추석 후 다이어트", "명절 후 다이어트"],
            10: ["가을 다이어트", "환절기 다이어트"],
            11: ["겨울 다이어트", "연말 다이어트", "송년 다이어트"],
            12: ["연말 다이어트", "새해준비 다이어트", "12월 다이어트"]
        },
        "안면비대칭_교정": {
            1: ["새해 교정", "신년 비대칭교정", "1월 교정"],
            2: ["졸업사진 비대칭", "취업 면접 비대칭", "증명사진 비대칭", "졸업시즌 교정"],
            3: ["졸업 안면비대칭", "취업 준비 교정", "면접 준비 교정", "봄 교정"],
            4: ["봄 비대칭교정", "웨딩 안면교정"],
            5: ["웨딩 안면비대칭", "결혼준비 교정", "5월 교정"],
            6: ["여름 비대칭교정", "여름방학 교정"],
            7: ["여름방학 교정", "휴가전 교정"],
            8: ["개학전 교정", "여름 비대칭"],
            9: ["추석 전 교정", "가을 비대칭교정"],
            10: ["가을 교정", "환절기 교정"],
            11: ["수능 후 교정", "겨울방학 교정", "연말 준비 교정"],
            12: ["연말 비대칭교정", "새해 교정", "송년 교정"]
        },
        "여드름_피부": {
            1: ["겨울 건조 여드름", "새해 피부관리", "설 피부", "1월 여드름"],
            2: ["환절기 여드름", "봄철 여드름", "건조 여드름"],
            3: ["봄 피부관리", "환절기 피부", "봄 여드름", "졸업사진 피부"],
            4: ["봄 여드름", "미세먼지 피부"],
            5: ["여름 피부", "자외선 피부", "웨딩 피부관리"],
            6: ["여름 여드름", "땀 여드름"],
            7: ["여름 여드름", "땀 여드름", "마스크 여드름", "휴가전 피부"],
            8: ["여름 여드름", "자외선 피부"],
            9: ["가을 피부", "건조 피부", "환절기 여드름"],
            10: ["가을 피부", "건조 여드름"],
            11: ["겨울 피부", "건조 여드름"],
            12: ["겨울 건조 피부", "연말 피부관리"]
        },
        "교통사고_입원": {
            1: ["빙판길 교통사고", "겨울 교통사고", "설 귀성길 사고", "1월 교통사고"],
            2: ["설 귀성길 교통사고", "겨울 교통사고", "빙판길 사고"],
            3: ["봄 나들이 사고", "졸업여행 교통사고", "환절기 교통사고"],
            4: ["봄 교통사고", "벚꽃놀이 교통사고", "주말 나들이 사고"],
            5: ["황금연휴 교통사고", "봄 나들이 사고", "어버이날 교통사고"],
            6: ["장마철 교통사고", "빗길 교통사고", "6월 교통사고"],
            7: ["휴가철 교통사고", "여름 교통사고", "피서길 사고"],
            8: ["휴가철 교통사고", "여름 교통사고"],
            9: ["추석 귀성길 교통사고", "명절 교통사고", "추석 교통사고"],
            10: ["추석 귀경길 교통사고", "가을 교통사고"],
            11: ["가을 교통사고", "연말 교통사고"],
            12: ["연말 교통사고", "송년회 교통사고", "눈길 교통사고", "빙판 교통사고"]
        },
        "리프팅_탄력": {
            1: ["새해 리프팅", "신년 피부관리", "겨울 리프팅", "설 피부관리"],
            2: ["졸업사진 리프팅", "면접준비 리프팅", "발렌타인 피부"],
            3: ["봄 피부 리프팅", "졸업 리프팅", "취업 리프팅", "환절기 피부탄력"],
            4: ["봄 리프팅", "웨딩 리프팅", "결혼시즌 피부"],
            5: ["웨딩 리프팅", "결혼 리프팅", "가정의달 피부관리"],
            6: ["여름 리프팅", "반팔 리프팅", "여름 피부탄력"],
            7: ["여름휴가 피부", "바캉스 리프팅", "피서전 리프팅"],
            8: ["가을준비 리프팅", "여름후 피부관리", "휴가후 피부"],
            9: ["추석 리프팅", "가을 리프팅", "명절 피부관리"],
            10: ["가을 피부탄력", "환절기 리프팅", "10월 리프팅"],
            11: ["연말 리프팅", "송년 리프팅", "연말모임 피부"],
            12: ["연말 모임 피부", "송년회 피부", "크리스마스 리프팅", "겨울 피부탄력"]
        },
        # ============ 서브 카테고리 ============
        "면역_보약": {
            1: ["새해 보약", "설 보약", "신년 건강"],
            3: ["환절기 보약", "봄 보약"],
            5: ["가정의 달 보약", "부모님 보약", "어버이날 보약"],
            9: ["추석 보약", "환절기 면역"],
            12: ["연말 보약", "송년 건강", "겨울 면역"]
        },
        "수험생_집중력": {
            3: ["새학기 집중력", "개학 한약"],
            6: ["기말고사 한약", "시험기간 집중력"],
            9: ["수능 100일 한약", "모의고사 집중력"],
            11: ["수능 한약", "수능 집중력", "수험생 D-Day"],
            12: ["겨울방학 보약", "수능 후 보양"]
        },
        "알레르기_아토피": {
            3: ["봄 알레르기", "황사 비염", "미세먼지 비염"],
            4: ["꽃가루 알레르기", "봄철 비염"],
            9: ["환절기 비염", "가을 알레르기"],
            10: ["환절기 아토피"]
        },
        "갱년기_호르몬": {
            5: ["가정의 달 갱년기", "어머니 갱년기"],
            9: ["추석 갱년기 선물"],
            12: ["연말 건강검진", "겨울 갱년기"]
        },
        "불면증_수면": {
            3: ["봄 졸음", "춘곤증"],
            6: ["열대야 불면증", "여름 불면"],
            11: ["수능 불면증", "시험 불면"],
            12: ["연말 피로", "송년 스트레스"]
        },
        "자율신경_스트레스": {
            3: ["취업 스트레스", "이직 스트레스"],
            6: ["직장인 번아웃", "상반기 피로"],
            11: ["연말 스트레스", "성과 압박"],
            12: ["송년 우울", "연말 피로"]
        },
        "산후조리_여성": {
            1: ["새해 임신 준비"],
            5: ["어머니날 산후조리"],
            9: ["추석 산후 선물"]
        },
        "통증_디스크": {
            3: ["봄 운동 부상"],
            7: ["여름 스포츠 부상", "휴가 후 통증"],
            12: ["겨울 관절통", "한파 통증"]
        },
        "소화불량_위장": {
            1: ["새해 위장", "설 과식"],
            5: ["회식 소화불량"],
            9: ["추석 과식", "명절 소화불량"],
            12: ["연말 회식", "송년회 위장"]
        },
        "다한증_냉증": {
            6: ["여름 다한증", "땀 많이"],
            7: ["여름 손땀", "열대야 땀"],
            12: ["겨울 수족냉증", "한파 냉증"]
        },
        "두통_어지럼증": {
            3: ["환절기 두통", "봄 편두통"],
            7: ["폭염 두통", "여름 어지럼"],
            9: ["환절기 두통"],
            12: ["연말 두통"]
        },
        # ===== 추가 카테고리 (LEGION 호환) =====
        "탈모_모발": {
            1: ["겨울 탈모", "두피 건조"],
            3: ["환절기 탈모", "봄 탈모"],
            4: ["미세먼지 두피", "봄 탈모관리"],
            5: ["결혼준비 탈모", "취업 탈모"],
            6: ["여름 탈모", "땀 두피"],
            7: ["휴가전 탈모치료"],
            9: ["환절기 탈모", "가을 탈모"],
            10: ["가을 탈모", "두피관리"],
            11: ["겨울준비 탈모", "연말 탈모"],
            12: ["겨울 탈모", "연말 탈모치료"]
        },
        "야간진료_접근성": {
            1: ["새해 야간진료"],
            3: ["새학기 야간진료"],
            6: ["퇴근후 한의원"],
            9: ["추석 야간진료"],
            12: ["연말 야간진료", "송년회 후 한의원"]
        },
    }

    @classmethod
    def get_current_seasonal_keywords(cls, category: str) -> List[str]:
        """현재 월의 시즌 키워드 반환"""
        current_month = datetime.now().month

        if category not in cls.SEASONAL_KEYWORDS:
            return []

        # 현재 월 ± 1개월 키워드 포함
        keywords = []
        for month in [current_month - 1, current_month, current_month + 1]:
            adjusted_month = month if month > 0 else month + 12
            adjusted_month = adjusted_month if adjusted_month <= 12 else adjusted_month - 12

            if adjusted_month in cls.SEASONAL_KEYWORDS[category]:
                keywords.extend(cls.SEASONAL_KEYWORDS[category][adjusted_month])

        return list(set(keywords))

    @classmethod
    def generate_seasonal_seeds(cls, base_region: str = "청주") -> List[Tuple[str, str]]:
        """모든 카테고리의 현재 시즌 시드 생성"""
        seeds = []

        for category in ALL_CATEGORIES:
            seasonal_kws = cls.get_current_seasonal_keywords(category)
            for kw in seasonal_kws:
                seed = f"{base_region} {kw}"
                seeds.append((seed, category))

        return seeds


# ============================================================
# Phase 4: 지역 Ring 확장
# ============================================================

class GeographicExpander:
    """지역 확장 키워드 생성기"""

    @classmethod
    def get_regions_for_category(cls, category: str) -> List[Dict]:
        """카테고리에 해당하는 지역 Ring 목록 반환"""
        applicable_rings = []

        for ring_id, ring_config in GEOGRAPHIC_RINGS.items():
            if ring_config.get("all_categories", False):
                applicable_rings.append({
                    "ring_id": ring_id,
                    **ring_config
                })
            elif category in ring_config.get("target_categories", []):
                applicable_rings.append({
                    "ring_id": ring_id,
                    **ring_config
                })

        return applicable_rings

    @classmethod
    def generate_regional_seeds(cls, category: str, core_terms: List[str]) -> List[Tuple[str, str, int]]:
        """
        카테고리의 지역별 시드 생성

        Returns:
            List of (seed_keyword, category, ring_number)
        """
        seeds = []
        applicable_rings = cls.get_regions_for_category(category)

        for ring in applicable_rings:
            ring_num = int(ring["ring_id"].replace("ring", ""))

            # 지역명 + 핵심 용어
            for region in ring["regions"]:
                for term in core_terms:
                    seeds.append((f"{region} {term}", category, ring_num))

            # 동네명 + 핵심 용어 (Ring 0, 1만)
            if ring_num <= 1:
                for neighborhood in ring.get("neighborhoods", []):
                    for term in core_terms[:2]:  # 핵심 2개만
                        seeds.append((f"{neighborhood} {term}", category, ring_num))

        return seeds


# ============================================================
# Phase 5: 경쟁사 자동 발견 시스템
# ============================================================

class CompetitorDiscovery:
    """경쟁사 자동 발견 및 분석"""

    def __init__(self, delay: float = 0.5):
        self.delay = delay
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9"
        }

    def discover_competitors(self, category: str, region: str = "청주") -> List[Dict]:
        """
        카테고리별 경쟁사 자동 발견

        Args:
            category: 진료 카테고리
            region: 지역명

        Returns:
            List of competitor info dicts
        """
        # 카테고리별 검색 쿼리 매핑
        category_queries = {
            "다이어트": "다이어트 한의원",
            "안면비대칭_교정": "안면비대칭 교정",
            "여드름_피부": "여드름 한의원",
            "리프팅_탄력": "한방 리프팅",
            "교통사고_입원": "교통사고 한의원",
            "통증_디스크": "디스크 한의원",
            "갱년기_호르몬": "갱년기 한의원",
            "불면증_수면": "불면증 한의원",
            "소화불량_위장": "위장 한의원",
            "두통_어지럼증": "두통 한의원",
            "알레르기_아토피": "비염 한의원",
            "자율신경_스트레스": "스트레스 한의원",
            "산후조리_여성": "산후조리 한의원",
            "다한증_냉증": "다한증 한의원",
            "수험생_집중력": "수험생 한약",
            "면역_보약": "보약 한의원"
        }

        query = f"{region} {category_queries.get(category, '한의원')}"

        # 네이버 검색으로 경쟁사 탐색
        competitors = []

        try:
            time.sleep(self.delay)
            url = "https://search.naver.com/search.naver"
            params = {"where": "nexearch", "query": query}

            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # 플레이스 결과에서 한의원 추출
            place_items = soup.select('.place_bluelink') or soup.select('.place_name')

            for item in place_items[:10]:
                name = item.get_text(strip=True)
                if "규림" not in name and ("한의원" in name or "한방" in name):
                    competitors.append({
                        "name": name,
                        "category": category,
                        "discovered_at": datetime.now().isoformat()
                    })
        except Exception as e:
            print(f"   경쟁사 탐색 실패 ({category}): {e}")

        return competitors

    def find_gap_keywords(self, our_keywords: Set[str], competitor_keywords: Set[str]) -> List[str]:
        """경쟁사는 있고 우리는 없는 갭 키워드 찾기"""
        return list(competitor_keywords - our_keywords)


# ============================================================
# 메인 수집기: LEGION ULTRA
# ============================================================

class PathfinderUltra:
    """Pathfinder ULTRA - 통합 키워드 발굴 시스템"""

    def __init__(self, delay: float = 0.3):
        self.delay = delay
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.naver.com/",
            "Accept-Language": "ko-KR,ko;q=0.9"
        }

        # 결과 저장
        self.results: Dict[str, KeywordResult] = {}
        self.analyzed_keywords: Set[str] = set()
        self.filter_stats = defaultdict(int)

        # 카테고리별 핵심 용어 (메인 5개 카테고리 대폭 강화)
        self.category_terms = {
            # ============ 메인 카테고리 (강화) ============
            "다이어트": [
                # 기본 용어
                "다이어트", "비만", "살빼기", "체중감량", "다이어트한약",
                # 한의원 특화
                "다이어트한의원", "비만한의원", "한방다이어트", "한약다이어트",
                # 부위별
                "뱃살", "하체비만", "상체비만", "팔뚝살", "허벅지살",
                # 타겟별
                "산후다이어트", "남자다이어트", "직장인다이어트",
                # 방법
                "식욕억제", "체지방감량", "비만치료", "비만클리닉"
            ],
            "안면비대칭_교정": [
                # 기본 용어
                "안면비대칭", "얼굴비대칭", "턱비대칭", "체형교정", "골반교정",
                # 한의원 특화
                "비대칭교정", "안면교정", "한방교정", "체형교정한의원",
                # 부위별
                "광대비대칭", "눈비대칭", "입비대칭", "턱교정", "코비대칭",
                # 관련 용어
                "안면윤곽", "턱관절", "사각턱", "얼굴교정", "골격교정",
                # 추가
                "얼굴작아지는법", "비대칭얼굴", "안면비대칭교정"
            ],
            "여드름_피부": [
                # 기본 용어
                "여드름", "여드름흉터", "새살침", "피부", "아토피",
                # 한의원 특화
                "여드름한의원", "피부한의원", "한방피부", "여드름침",
                # 유형별
                "성인여드름", "턱여드름", "이마여드름", "볼여드름", "등여드름",
                # 흉터 관련 (중요!)
                "여드름자국", "흉터치료", "패인흉터", "튀어나온흉터", "여드름흉터치료",
                # 치료법
                "여드름치료", "여드름압출", "피부트러블", "모공", "피지"
            ],
            "교통사고_입원": [
                # 기본 용어
                "교통사고", "자동차사고", "교통사고한의원", "입원", "후유증",
                # 한의원 특화
                "교통사고치료", "자보한의원", "교통사고입원", "한방병원교통사고",
                # 보험 관련
                "자동차보험", "교통사고보험", "자보", "합의금",
                # 증상별
                "교통사고목", "교통사고허리", "교통사고두통", "교통사고어깨",
                # 관련 용어
                "교통사고후유증", "사고후치료", "추돌사고", "접촉사고"
            ],
            "리프팅_탄력": [
                # 기본 용어
                "리프팅", "매선", "피부탄력", "주름", "동안침",
                # 한의원 특화
                "한방리프팅", "매선리프팅", "침리프팅", "매선침", "탄력침",
                # 부위별
                "팔자주름", "눈가주름", "이마주름", "목주름", "입가주름",
                # 관련 용어
                "동안", "피부처짐", "탄력관리", "콜라겐", "안티에이징",
                # 시술명
                "브이리프팅", "실리프팅", "한방매선"
            ],
            # ============ 서브 카테고리 ============
            "통증_디스크": ["허리디스크", "목디스크", "허리통증", "추나", "도수치료",
                          "척추", "디스크한의원", "추나요법", "허리통증한의원"],
            "갱년기_호르몬": ["갱년기", "폐경", "여성호르몬", "안면홍조", "갱년기한약",
                            "갱년기한의원", "호르몬치료", "갱년기증상"],
            "불면증_수면": ["불면증", "수면장애", "수면", "만성피로", "피로회복",
                          "불면증한의원", "수면한약", "잠이안와요"],
            "소화불량_위장": ["소화불량", "위염", "역류성식도염", "담적", "위장",
                            "위장한의원", "소화불량한약", "담적병"],
            "두통_어지럼증": ["두통", "편두통", "어지럼증", "이석증", "만성두통",
                            "두통한의원", "어지럼증치료"],
            "알레르기_아토피": ["비염", "알레르기", "아토피", "축농증", "만성비염",
                              "비염한의원", "아토피한의원", "비염치료"],
            "자율신경_스트레스": ["스트레스", "공황장애", "자율신경", "화병", "불안",
                                "스트레스한의원", "공황장애치료"],
            "산후조리_여성": ["산후조리", "산후보약", "생리통", "난임", "여성질환",
                            "산후조리한의원", "생리통한약"],
            "다한증_냉증": ["다한증", "수족냉증", "손땀", "냉증", "땀",
                          "다한증한의원", "냉증치료"],
            "수험생_집중력": ["수험생한약", "집중력", "총명탕", "수능한약", "기억력",
                            "집중력한약", "공부한약"],
            "면역_보약": ["공진단", "경옥고", "보약", "면역력", "보양",
                        "보약한의원", "맞춤보약", "체력보강"],
            # ===== 추가 카테고리 (LEGION 호환) =====
            "탈모_모발": [
                # 기본 용어
                "탈모", "원형탈모", "정수리탈모", "M자탈모", "여성탈모",
                # 한의원 특화
                "탈모한의원", "탈모한약", "탈모치료", "한방탈모",
                # 모발 관련
                "모발이식", "발모", "탈모예방", "두피", "두피관리",
                # 증상별
                "머리숱", "가르마탈모", "앞머리탈모", "탈모초기", "탈모진행"
            ],
            "야간진료_접근성": [
                # 야간진료
                "야간진료", "야간한의원", "늦게까지", "저녁진료", "주말진료",
                # 접근성
                "24시한의원", "일요일진료", "토요일진료", "공휴일진료",
                # 동네별
                "율량동한의원", "복대동한의원", "가경동한의원", "용암동한의원",
                "분평동한의원", "사창동한의원", "산남동한의원", "봉명동한의원"
            ]
        }

        # 구매 의도 서픽스 (강화)
        self.intent_suffixes = [
            # 가격/비용
            "가격", "비용", "치료비", "가격표", "얼마",
            # 후기/추천
            "후기", "추천", "잘하는곳", "유명한곳", "좋은곳",
            # 효과/결과
            "효과", "전후", "결과", "성공", "실패",
            # 정보
            "부작용", "기간", "횟수", "방법", "원인",
            # 한의원 특화
            "한의원", "한방", "한약", "침", "보험적용"
        ]

        # API 연결
        self._init_apis()

    def _init_apis(self):
        """외부 API 초기화"""
        # Naver Ad API
        try:
            from scrapers.naver_ad_manager import NaverAdManager
            self.ad_manager = NaverAdManager()
            self.has_ad_api = not getattr(self.ad_manager, 'disabled', False)
        except Exception:
            self.ad_manager = None
            self.has_ad_api = False

        # Naver DataLab API
        try:
            from scrapers.naver_datalab_manager import NaverDataLabManager
            self.datalab = NaverDataLabManager()
            self.has_datalab = bool(self.datalab.api_keys)
        except Exception:
            self.datalab = None
            self.has_datalab = False

        # KeywordHarvester (블로그 수 조회용)
        try:
            from scrapers.keyword_harvester import KeywordHarvester
            self.harvester = KeywordHarvester()
            self.has_harvester = bool(self.harvester.api_keys)
        except Exception:
            self.harvester = None
            self.has_harvester = False

    def _rate_limit(self):
        """API 호출 제한"""
        time.sleep(self.delay)

    def get_autocomplete(self, keyword: str) -> List[str]:
        """Naver 자동완성 조회"""
        url = "https://ac.search.naver.com/nx/ac"
        params = {
            "q": keyword, "q_enc": "UTF-8", "st": 100, "frm": "nv",
            "r_format": "json", "r_enc": "UTF-8", "r_unicode": 0,
            "t_koreng": 1, "ans": 2, "run": 2, "rev": 4, "con": 1
        }

        try:
            self._rate_limit()
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            data = response.json()

            if "items" in data and data["items"] and len(data["items"]) > 0:
                return [item[0] if isinstance(item, list) else item for item in data["items"][0]]
        except:
            pass

        return []

    def get_blog_count(self, keyword: str) -> int:
        """Naver 블로그 수 조회 (Naver Search API 사용)"""
        # KeywordHarvester가 있으면 사용 (API 기반)
        if self.has_harvester and self.harvester:
            try:
                return self.harvester.get_naver_blog_count(keyword)
            except:
                pass

        # Fallback: 웹 스크래핑 (JS 렌더링 미지원으로 정확도 낮음)
        url = "https://search.naver.com/search.naver"
        params = {"where": "blog", "query": keyword}

        try:
            self._rate_limit()
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # 검색 결과 수 추출
            count_elem = soup.select_one('.title_num') or soup.select_one('.sub_count')
            if count_elem:
                count_text = count_elem.get_text()
                import re
                match = re.search(r'[\d,]+', count_text.replace(',', ''))
                if match:
                    return int(match.group().replace(',', ''))
        except:
            pass

        return 0

    def _detect_category(self, keyword: str) -> str:
        """키워드에서 카테고리 감지"""
        kw_lower = keyword.lower()

        for category, terms in self.category_terms.items():
            if any(term in kw_lower for term in terms):
                return category

        return "기타"

    def _is_valid_keyword(self, keyword: str) -> bool:
        """유효한 키워드인지 확인"""
        # 청주 또는 인근 지역 포함
        all_regions = []
        for ring in GEOGRAPHIC_RINGS.values():
            all_regions.extend(ring["regions"])
            all_regions.extend(ring.get("neighborhoods", []))

        has_region = any(r in keyword for r in all_regions)

        # 한의원 관련 키워드 포함
        hanbang_terms = []
        for terms in self.category_terms.values():
            hanbang_terms.extend(terms)
        hanbang_terms.extend(["한의원", "한방", "한약", "침", "추나"])

        has_hanbang = any(h in keyword for h in hanbang_terms)

        return has_region and has_hanbang

    def _detect_ring(self, keyword: str) -> int:
        """키워드의 지역 Ring 감지"""
        for ring_id, ring in GEOGRAPHIC_RINGS.items():
            ring_num = int(ring_id.replace("ring", ""))
            all_locations = ring["regions"] + ring.get("neighborhoods", [])

            if any(loc in keyword for loc in all_locations):
                return ring_num

        return 0  # 기본값: 청주 핵심

    def analyze_keyword(self, keyword: str, source: str, category: str = None) -> Optional[KeywordResult]:
        """단일 키워드 분석"""
        if keyword in self.analyzed_keywords:
            return None

        self.analyzed_keywords.add(keyword)

        # 유효성 검사
        if not self._is_valid_keyword(keyword):
            self.filter_stats["invalid"] += 1
            return None

        # 블로그 수 조회 (공급)
        supply = self.get_blog_count(keyword)

        # 공급 필터
        should_exclude, reason = SupplyFilter.should_exclude(supply)
        if should_exclude:
            self.filter_stats["supply_filtered"] += 1
            return None

        # KeywordResult 생성
        result = KeywordResult(
            keyword=keyword,
            supply=supply,
            source=source,
            category=category or self._detect_category(keyword),
            region="청주",  # 기본값
            ring=self._detect_ring(keyword)
        )

        return result

    def analyze_batch(self, keywords: List[Tuple[str, str, str]], show_progress: bool = True) -> int:
        """
        배치 키워드 분석

        Args:
            keywords: List of (keyword, source, category)

        Returns:
            신규 추가된 키워드 수
        """
        new_count = 0
        valid_results = []

        # 1단계: 유효성 검사 및 공급 조회
        for i, (kw, source, category) in enumerate(keywords):
            result = self.analyze_keyword(kw, source, category)
            if result:
                valid_results.append(result)

            if show_progress and (i + 1) % 50 == 0:
                print(f"   진행: {i+1}/{len(keywords)}... ({len(valid_results)} 유효)")

        if not valid_results:
            return 0

        # 2단계: 검색량 일괄 조회
        if self.has_ad_api and self.ad_manager:
            try:
                kw_list = [r.keyword for r in valid_results]
                volumes = self.ad_manager.get_keyword_volumes(kw_list) or {}

                for result in valid_results:
                    result.search_volume = volumes.get(result.keyword, 0)
                    if result.search_volume == 0:
                        # 공백 없는 버전으로 재시도
                        result.search_volume = volumes.get(result.keyword.replace(" ", ""), 0)
            except Exception as e:
                print(f"   검색량 조회 실패: {e}")

        # 3단계: MF-KEI 점수 계산 및 등급 부여
        for result in valid_results:
            MFKEI.calculate(result)
            MFKEI.assign_grade(result)

            self.results[result.keyword] = result
            new_count += 1

        return new_count

    def run(self, target_sa: int = 300, max_rounds: int = 8) -> List[KeywordResult]:
        """
        ULTRA MODE 실행

        Args:
            target_sa: 목표 S/A급 키워드 수
            max_rounds: 최대 라운드 수
        """
        print("=" * 70)
        print("🚀 PATHFINDER ULTRA MODE")
        print(f"   지원 카테고리: {len(ALL_CATEGORIES)}개")
        print(f"   목표 S/A급: {target_sa}개")
        print("=" * 70)

        total_sa = 0

        # ==========================================
        # Round 1: 카테고리별 기본 시드 자동완성
        # ==========================================
        print(f"\n[Round 1] 16개 카테고리 기본 시드 확장...")

        round1_keywords = []
        for category in ALL_CATEGORIES:
            terms = self.category_terms.get(category, [])

            for term in terms[:3]:  # 상위 3개 핵심 용어
                seed = f"청주 {term}"
                suggestions = self.get_autocomplete(seed)

                for s in suggestions:
                    round1_keywords.append((s, "round1_seed", category))
                round1_keywords.append((seed, "round1_seed", category))

        new_count = self.analyze_batch(round1_keywords)
        sa_count = sum(1 for r in self.results.values() if r.grade in ['S', 'A'])
        total_sa = sa_count
        print(f"   수집: {len(round1_keywords)}개 → 유효: {new_count}개, S/A급: {total_sa}개")

        if total_sa >= target_sa:
            return self._finalize()

        # ==========================================
        # Round 2: 시즌 키워드 주입
        # ==========================================
        print(f"\n[Round 2] 시즌 키워드 주입 (현재 월: {datetime.now().month}월)...")

        seasonal_seeds = SeasonalKeywordDB.generate_seasonal_seeds()
        round2_keywords = []

        for seed, category in seasonal_seeds:
            suggestions = self.get_autocomplete(seed)
            for s in suggestions:
                round2_keywords.append((s, "round2_seasonal", category))
            round2_keywords.append((seed, "round2_seasonal", category))

        new_count = self.analyze_batch(round2_keywords)
        total_sa = sum(1 for r in self.results.values() if r.grade in ['S', 'A'])
        print(f"   시즌 시드: {len(seasonal_seeds)}개 → 유효: {new_count}개, 누적 S/A급: {total_sa}개")

        if total_sa >= target_sa:
            return self._finalize()

        # ==========================================
        # Round 3: 지역 Ring 확장
        # ==========================================
        print(f"\n[Round 3] 지역 Ring 확장 (4개 Ring)...")

        round3_keywords = []
        for category in ALL_CATEGORIES:
            terms = self.category_terms.get(category, [])[:2]  # 핵심 2개
            regional_seeds = GeographicExpander.generate_regional_seeds(category, terms)

            for seed, cat, ring in regional_seeds:
                suggestions = self.get_autocomplete(seed)
                for s in suggestions:
                    round3_keywords.append((s, f"round3_ring{ring}", cat))
                round3_keywords.append((seed, f"round3_ring{ring}", cat))

        new_count = self.analyze_batch(round3_keywords)
        total_sa = sum(1 for r in self.results.values() if r.grade in ['S', 'A'])
        print(f"   지역 확장: {new_count}개 유효, 누적 S/A급: {total_sa}개")

        if total_sa >= target_sa:
            return self._finalize()

        # ==========================================
        # Round 4: 의도 확장 (가격/후기/추천)
        # ==========================================
        print(f"\n[Round 4] 구매 의도 확장 (가격/후기/추천)...")

        # 기존 S/A/B급 키워드에 의도 suffix 추가
        good_keywords = [kw for kw, r in self.results.items() if r.grade in ['S', 'A', 'B']]
        round4_keywords = []

        for kw in good_keywords[:50]:  # 상위 50개
            category = self.results[kw].category

            for intent in self.intent_suffixes[:5]:
                new_kw = f"{kw} {intent}"
                round4_keywords.append((new_kw, "round4_intent", category))

                suggestions = self.get_autocomplete(new_kw)
                for s in suggestions:
                    round4_keywords.append((s, "round4_intent", category))

        new_count = self.analyze_batch(round4_keywords)
        total_sa = sum(1 for r in self.results.values() if r.grade in ['S', 'A'])
        print(f"   의도 확장: {new_count}개 유효, 누적 S/A급: {total_sa}개")

        if total_sa >= target_sa:
            return self._finalize()

        # ==========================================
        # Round 5: S/A급 재확장
        # ==========================================
        print(f"\n[Round 5] S/A급 키워드 재확장...")

        sa_keywords = [kw for kw, r in self.results.items() if r.grade in ['S', 'A']]
        round5_keywords = []

        for kw in sa_keywords:
            category = self.results[kw].category

            # 자동완성 확장
            suggestions = self.get_autocomplete(kw)
            for s in suggestions:
                round5_keywords.append((s, "round5_sa_expand", category))

        new_count = self.analyze_batch(round5_keywords)
        total_sa = sum(1 for r in self.results.values() if r.grade in ['S', 'A'])
        print(f"   S/A 재확장: {new_count}개 유효, 누적 S/A급: {total_sa}개")

        return self._finalize()

    def _finalize(self) -> List[KeywordResult]:
        """최종 결과 정리"""
        results = list(self.results.values())

        # MF-KEI 점수로 정렬
        results.sort(key=lambda x: x.mf_kei_score, reverse=True)

        # 등급별 통계
        grade_counts = defaultdict(int)
        category_counts = defaultdict(int)
        ring_counts = defaultdict(int)
        intent_counts = defaultdict(int)

        for r in results:
            grade_counts[r.grade] += 1
            category_counts[r.category] += 1
            ring_counts[r.ring] += 1
            intent_counts[r.search_intent] += 1

        # 결과 출력
        print("\n" + "=" * 70)
        print("📊 PATHFINDER ULTRA 결과")
        print("=" * 70)

        print(f"\n총 키워드: {len(results)}개")
        print(f"   🔥 S급: {grade_counts['S']}개")
        print(f"   🟢 A급: {grade_counts['A']}개")
        print(f"   🔵 B급: {grade_counts['B']}개")
        print(f"   ⚪ C급: {grade_counts['C']}개")

        print(f"\n필터링 통계:")
        print(f"   무효 키워드: {self.filter_stats['invalid']}개")
        print(f"   공급 필터: {self.filter_stats['supply_filtered']}개")

        print(f"\n카테고리별 분포:")
        for cat in ALL_CATEGORIES:
            count = category_counts.get(cat, 0)
            if count > 0:
                print(f"   {cat}: {count}개")

        print(f"\n지역 Ring별 분포:")
        for ring_num in range(4):
            print(f"   Ring {ring_num}: {ring_counts.get(ring_num, 0)}개")

        print(f"\n검색 의도별 분포:")
        intent_labels = {
            "transactional": "💰 거래형",
            "commercial": "🔍 상업형",
            "informational": "📚 정보형",
            "navigational": "📍 탐색형",
            "unknown": "❓ 미분류"
        }
        for intent, count in sorted(intent_counts.items(), key=lambda x: -x[1]):
            print(f"   {intent_labels.get(intent, intent)}: {count}개")

        # 상위 S급 키워드
        s_keywords = [r for r in results if r.grade == 'S'][:15]
        if s_keywords:
            print(f"\n🔥 상위 S급 키워드:")
            for r in s_keywords:
                print(f"   - {r.keyword}")
                print(f"     MF-KEI: {r.mf_kei_score:.1f} | 검색량: {r.search_volume} | 공급: {r.supply}")

        return results

    def export_csv(self, results: List[KeywordResult], filename: str = "ultra_results.csv"):
        """CSV 내보내기"""
        import csv

        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'keyword', 'mf_kei_score', 'grade', 'search_volume', 'supply',
                'category', 'region', 'ring', 'search_intent',
                'demand_factor', 'supply_factor', 'competition_factor',
                'intent_factor', 'trend_factor', 'source'
            ])
            writer.writeheader()

            for r in results:
                row = {
                    'keyword': r.keyword,
                    'mf_kei_score': round(r.mf_kei_score, 1),
                    'grade': r.grade,
                    'search_volume': r.search_volume,
                    'supply': r.supply,
                    'category': r.category,
                    'region': r.region,
                    'ring': r.ring,
                    'search_intent': r.search_intent,
                    'demand_factor': round(r.demand_factor, 2),
                    'supply_factor': round(r.supply_factor, 2),
                    'competition_factor': round(r.competition_factor, 2),
                    'intent_factor': round(r.intent_factor, 2),
                    'trend_factor': round(r.trend_factor, 2),
                    'source': r.source
                }
                writer.writerow(row)

        print(f"\n📁 결과 저장: {filename}")

    def save_to_db(self, results: List[KeywordResult], db_path: str = None):
        """DB 저장"""
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "db", "marketing_data.db")

        print(f"\n💾 DB 저장: {db_path}")

        try:
            conn = sqlite3.connect(db_path, timeout=60)
            cursor = conn.cursor()

            # 테이블 확인/생성
            cursor.execute('''CREATE TABLE IF NOT EXISTS keyword_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT UNIQUE,
                volume INTEGER,
                competition TEXT,
                opp_score REAL,
                tag TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                search_volume INTEGER DEFAULT 0,
                region TEXT DEFAULT '청주',
                category TEXT DEFAULT '기타',
                difficulty INTEGER DEFAULT 50,
                opportunity INTEGER DEFAULT 50,
                priority_v3 REAL DEFAULT 0,
                grade TEXT DEFAULT 'C',
                source TEXT DEFAULT 'ultra',
                mf_kei_score REAL DEFAULT 0,
                ring INTEGER DEFAULT 0,
                search_intent TEXT DEFAULT 'unknown'
            )''')

            # ULTRA 전용 컬럼 추가
            for col, ctype in [
                ("mf_kei_score", "REAL DEFAULT 0"),
                ("ring", "INTEGER DEFAULT 0"),
                ("search_intent", "TEXT DEFAULT 'unknown'"),
                ("demand_factor", "REAL DEFAULT 1.0"),
                ("supply_factor", "REAL DEFAULT 1.0"),
                ("competition_factor", "REAL DEFAULT 1.0"),
                ("intent_factor", "REAL DEFAULT 1.0"),
                ("trend_factor", "REAL DEFAULT 1.0")
            ]:
                try:
                    cursor.execute(f"ALTER TABLE keyword_insights ADD COLUMN {col} {ctype}")
                except:
                    pass

            # 저장
            saved = 0
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for r in results:
                try:
                    cursor.execute('''
                        INSERT INTO keyword_insights (
                            keyword, volume, competition, opp_score, tag, created_at,
                            search_volume, region, category, difficulty, opportunity,
                            priority_v3, grade, source, mf_kei_score, ring, search_intent,
                            demand_factor, supply_factor, competition_factor, intent_factor, trend_factor
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(keyword) DO UPDATE SET
                            mf_kei_score=excluded.mf_kei_score,
                            grade=excluded.grade,
                            search_volume=excluded.search_volume,
                            ring=excluded.ring,
                            search_intent=excluded.search_intent,
                            source=excluded.source,
                            created_at=excluded.created_at
                    ''', (
                        r.keyword, r.supply, "Low" if r.supply < 1000 else "High",
                        r.mf_kei_score, r.grade, now,
                        r.search_volume, r.region, r.category,
                        r.difficulty, r.opportunity, r.mf_kei_score, r.grade, r.source,
                        r.mf_kei_score, r.ring, r.search_intent,
                        r.demand_factor, r.supply_factor, r.competition_factor,
                        r.intent_factor, r.trend_factor
                    ))
                    saved += 1
                except Exception as e:
                    pass

            conn.commit()
            conn.close()

            print(f"   ✅ {saved}/{len(results)}개 저장 완료")

        except Exception as e:
            print(f"   ❌ DB 저장 실패: {e}")


# ============================================================
# 메인 실행
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Pathfinder ULTRA")
    parser.add_argument("--target", type=int, default=300, help="목표 S/A급 키워드 수")
    parser.add_argument("--save-db", action="store_true", default=True, help="DB에 저장 (기본값: True)")
    parser.add_argument("--no-db", action="store_true", help="DB 저장 안 함")
    parser.add_argument("--no-csv", action="store_true", help="CSV 저장 안 함")
    args = parser.parse_args()

    ultra = PathfinderUltra()
    results = ultra.run(target_sa=args.target)

    if not args.no_csv:
        ultra.export_csv(results)

    # DB 저장 (기본값: True, --no-db로 비활성화)
    if not args.no_db:
        ultra.save_to_db(results)


if __name__ == "__main__":
    main()

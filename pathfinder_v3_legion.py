#!/usr/bin/env python3
"""
Pathfinder V3 LEGION MODE
- 다중 확장 전략으로 고품질 키워드 대량 수집
- Multi-Source: Naver + Google 자동완성
- MF-KEI 5.0: 트렌드 + 계절성 + 비즈니스 관련도 반영
- 품질 필터: 노이즈/경쟁사 키워드 제거
- Round 1: 기본 시드 자동완성 (Naver + Google)
- Round 2: S/A급 키워드 재확장
- Round 3: 지역 확장
- Round 4: 의도 확장
- Round 5: 경쟁사 역분석
- Round 6: 연관검색어
- Round 7: 문제 해결형 키워드
- Round 8: AI 시맨틱 확장 (Codex CLI)
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import atexit
import requests
import re
import time
import math
import json
import argparse
import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Dict, Set, Tuple, Optional
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
from functools import lru_cache
from utils.json_io import atomic_write_json
from core_services.gyulim_keyword_profile import ACTIVE_KEYWORD_PROFILE as GYULIM_KEYWORD_PROFILE

# 품질 필터 (노이즈 제거)
try:
    from core_services.keyword_filter import KeywordQualityFilter
    HAS_QUALITY_FILTER = True
except ImportError:
    HAS_QUALITY_FILTER = False
    print("⚠️ KeywordQualityFilter 미설치 - 기본 필터만 사용")

# AI 키워드 확장 (Codex CLI)
try:
    from core_services.ai_keyword_expander import AIKeywordExpander
    HAS_AI_EXPANDER = True
except ImportError:
    HAS_AI_EXPANDER = False

# 블로그 제목 마이닝
try:
    from core_services.blog_miner import BlogTitleMiner
    HAS_BLOG_MINER = True
except ImportError:
    HAS_BLOG_MINER = False

# 네이버 검색 API (총 문서수 조회용 - SERP 캡차 우회)
try:
    from naver_api_client import NaverApiClient
    HAS_NAVER_API = True
except ImportError:
    HAS_NAVER_API = False
    print("⚠️ NaverApiClient 미설치 - SERP HTML로 폴백")


# ============================================================
# Scan History 헬퍼 함수 (scan_runs 테이블 연동)
# ============================================================

def _get_db_path() -> str:
    """DB 경로 반환"""
    db_path = os.environ.get('MARKETING_BOT_DB_PATH')
    if db_path and os.path.exists(db_path):
        return db_path

    base_dir = Path(__file__).parent
    default_path = base_dir / "db" / "marketing_data.db"
    if default_path.exists():
        return str(default_path)

    return str(default_path)


def create_scan_run(scan_type: str = "legion", mode: str = "legion", target_count: int = 0) -> int:
    """스캔 실행 레코드 생성 (status='running')"""
    db_path = _get_db_path()
    if not os.path.exists(db_path):
        return 0

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # scan_runs 테이블 확인/생성
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scan_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_type TEXT NOT NULL,
                mode TEXT DEFAULT 'unknown',
                target_count INTEGER DEFAULT 0,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status TEXT DEFAULT 'running',
                total_keywords INTEGER DEFAULT 0,
                new_keywords INTEGER DEFAULT 0,
                updated_keywords INTEGER DEFAULT 0,
                s_grade_count INTEGER DEFAULT 0,
                a_grade_count INTEGER DEFAULT 0,
                b_grade_count INTEGER DEFAULT 0,
                c_grade_count INTEGER DEFAULT 0,
                sources_json TEXT DEFAULT '{}',
                categories_json TEXT DEFAULT '{}',
                error_message TEXT,
                top_keywords_json TEXT DEFAULT '[]',
                execution_time_seconds INTEGER DEFAULT 0,
                notes TEXT
            )
        ''')

        for col, ctype in [
            ("updated_keywords", "INTEGER DEFAULT 0"),
            ("sources_json", "TEXT DEFAULT '{}'"),
            ("categories_json", "TEXT DEFAULT '{}'"),
            ("notes", "TEXT"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE scan_runs ADD COLUMN {col} {ctype}")
            except sqlite3.OperationalError:
                pass

        cursor.execute('''
            INSERT INTO scan_runs (scan_type, mode, target_count, status)
            VALUES (?, ?, ?, 'running')
        ''', (scan_type, mode, target_count))

        run_id = cursor.lastrowid
        conn.commit()
        conn.close()

        print(f"📝 스캔 기록 시작 (ID: {run_id})")
        return run_id
    except Exception as e:
        print(f"⚠️ 스캔 기록 생성 실패: {e}")
        return 0


def update_scan_run(run_id: int, status: str = "completed",
                    total_keywords: int = 0, new_keywords: int = 0,
                    updated_keywords: int = 0,
                    s_count: int = 0, a_count: int = 0, b_count: int = 0, c_count: int = 0,
                    top_keywords: list = None, error_message: str = None,
                    execution_time: int = 0, notes: str = None):
    """스캔 실행 레코드 업데이트"""
    if not run_id:
        return

    db_path = _get_db_path()
    if not os.path.exists(db_path):
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for col, ctype in [
            ("updated_keywords", "INTEGER DEFAULT 0"),
            ("sources_json", "TEXT DEFAULT '{}'"),
            ("categories_json", "TEXT DEFAULT '{}'"),
            ("notes", "TEXT"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE scan_runs ADD COLUMN {col} {ctype}")
            except sqlite3.OperationalError:
                pass

        top_json = json.dumps(top_keywords[:10] if top_keywords else [], ensure_ascii=False)

        cursor.execute('''
            UPDATE scan_runs SET
                status = ?,
                completed_at = CURRENT_TIMESTAMP,
                total_keywords = ?,
                new_keywords = ?,
                updated_keywords = ?,
                s_grade_count = ?,
                a_grade_count = ?,
                b_grade_count = ?,
                c_grade_count = ?,
                top_keywords_json = ?,
                error_message = ?,
                execution_time_seconds = ?,
                notes = ?
            WHERE id = ?
        ''', (status, total_keywords, new_keywords, updated_keywords,
              s_count, a_count, b_count, c_count,
              top_json, error_message, execution_time, notes, run_id))

        conn.commit()
        conn.close()

        print(f"📝 스캔 기록 완료 (ID: {run_id}, 상태: {status})")
    except Exception as e:
        print(f"⚠️ 스캔 기록 업데이트 실패: {e}")

# Async HTTP (optional, fallback to sync if not available)
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    print("⚠️ aiohttp 미설치 - ThreadPool 모드로 동작")


# ============================================================
# TeeWriter: stdout + 파일 동시 출력 (실시간 로그 스트리밍용)
# ============================================================

class TeeWriter:
    """stdout과 파일에 동시 출력하는 Writer 클래스"""

    def __init__(self, log_file_path: str, status_file_path: str, mode: str = 'legion'):
        self.terminal = sys.stdout
        self.log_file_path = log_file_path
        self.status_file_path = status_file_path
        self.mode = mode

        # 로그 디렉토리 생성
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

        # 로그 파일 열기 (덮어쓰기)
        self.log_file = open(log_file_path, 'w', encoding='utf-8', buffering=1)

        # 상태 파일 업데이트: running
        self._update_status('running', f'Pathfinder LEGION MODE 시작됨')

        # 종료 시 cleanup 등록
        atexit.register(self._cleanup)

    def write(self, message):
        self.terminal.write(message)
        self.terminal.flush()
        try:
            self.log_file.write(message)
            self.log_file.flush()
        except Exception:
            pass  # 로그 파일 쓰기 실패는 무시

    def flush(self):
        self.terminal.flush()
        try:
            self.log_file.flush()
        except Exception:
            pass  # 로그 파일 flush 실패는 무시

    def _update_status(self, status: str, message: str = ''):
        """상태 파일 업데이트"""
        import json
        try:
            status_data = {
                'status': status,
                'message': message,
                'updated_at': datetime.now().isoformat(),
                'mode': self.mode
            }
            atomic_write_json(self.status_file_path, status_data)
        except Exception:
            pass  # 상태 파일 업데이트 실패는 무시

    def _cleanup(self):
        """종료 시 정리"""
        try:
            self._update_status('completed', 'Pathfinder LEGION MODE 완료')
            self.log_file.close()
        except Exception:
            pass  # 종료 시 정리 실패는 무시


def setup_live_logging():
    """실시간 로그 스트리밍 설정"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(base_dir, 'logs')

    log_file = os.path.join(log_dir, 'pathfinder_live.log')
    status_file = os.path.join(log_dir, 'pathfinder_status.json')

    tee = TeeWriter(log_file, status_file, mode='legion')
    sys.stdout = tee
    return tee


# ============================================================
# 데이터 클래스
# ============================================================

@dataclass
class KeywordResult:
    """키워드 결과 (KEI 지원)"""
    keyword: str
    search_volume: int
    difficulty: int
    opportunity: int
    grade: str
    category: str
    priority_score: float
    source: str  # round1, round2, region, intent, competitor, related
    trend_slope: float = 0.0  # 트렌드 기울기 (양수=상승, 음수=하락)
    trend_status: str = "unknown"  # rising, falling, stable, unknown
    search_intent: str = "unknown"  # informational, transactional, navigational, commercial
    merged_from: List[str] = None  # 병합된 원본 키워드들
    document_count: int = 0  # 총 검색 결과 문서 수
    kei: float = 0.0  # 실제 KEI = 검색량² / 문서수
    kei_grade: str = "C"  # KEI 기반 등급 (S/A/B/C)
    business_core: bool = False  # 실제 유입 핵심군 여부 (등급과 별도)
    source_signals: List[str] = None
    verification_score: float = 0.0
    novelty_score: float = 0.0
    diversity_rank: int = 0
    quality_flags: List[str] = None
    longtail_score: float = 0.0
    business_value_score: float = 0.0
    high_value_longtail: bool = False
    inbound_impressions: int = 0
    inbound_clicks: int = 0
    inbound_ctr: float = 0.0
    inbound_position: float = 0.0
    inbound_sources: List[str] = None
    mobile_share: float = 0.0
    content_cluster_key: str = ""
    owned_rank: int = 0
    owned_rank_device: str = ""
    rank_gap_signal: float = 0.0
    rank_status: str = "unknown"
    community_mentions: int = 0
    community_conversion_fit: float = 0.0
    community_signal: float = 0.0
    community_platforms: List[str] = None
    conversion_calls: int = 0
    conversion_naver_calls: int = 0
    conversion_duration_seconds: int = 0
    conversion_signal: float = 0.0
    profile_action_signal: float = 0.0
    profile_actions_total: int = 0
    profile_direction_actions: int = 0
    profile_website_actions: int = 0
    profile_booking_actions: int = 0
    profile_message_actions: int = 0
    profile_action_sources: List[str] = None
    profile_action_flags: List[str] = None
    availability_intent_score: float = 0.0
    availability_intent_type: str = "none"
    availability_action_flags: List[str] = None
    payment_coverage_score: float = 0.0
    payment_coverage_type: str = "none"
    payment_action_flags: List[str] = None
    access_convenience_score: float = 0.0
    access_convenience_type: str = "none"
    access_convenience_flags: List[str] = None
    medical_ad_risk_score: float = 0.0
    medical_ad_risk_flags: List[str] = None
    content_feasibility_score: float = 100.0
    local_service_fit_score: float = 0.0
    negative_intent_flags: List[str] = None
    content_actionability_score: float = 0.0
    recommended_content_type: str = ""
    content_action_flags: List[str] = None
    local_surface_score: float = 0.0
    preferred_search_surface: str = ""
    local_surface_flags: List[str] = None
    brand_intent_type: str = "generic"
    brand_signal_score: float = 0.0
    brand_mentions: List[str] = None
    competitor_brand_risk_score: float = 0.0
    brand_action_flags: List[str] = None
    review_surface_score: float = 0.0
    reputation_risk_score: float = 0.0
    review_intent_type: str = "none"
    review_action_flags: List[str] = None

    def __post_init__(self):
        if self.merged_from is None:
            self.merged_from = []
        if self.source_signals is None:
            self.source_signals = []
        if self.quality_flags is None:
            self.quality_flags = []
        if self.inbound_sources is None:
            self.inbound_sources = []
        if self.community_platforms is None:
            self.community_platforms = []
        if self.profile_action_sources is None:
            self.profile_action_sources = []
        if self.profile_action_flags is None:
            self.profile_action_flags = []
        if self.availability_action_flags is None:
            self.availability_action_flags = []
        if self.payment_action_flags is None:
            self.payment_action_flags = []
        if self.access_convenience_flags is None:
            self.access_convenience_flags = []
        if self.medical_ad_risk_flags is None:
            self.medical_ad_risk_flags = []
        if self.negative_intent_flags is None:
            self.negative_intent_flags = []
        if self.content_action_flags is None:
            self.content_action_flags = []
        if self.local_surface_flags is None:
            self.local_surface_flags = []
        if self.brand_mentions is None:
            self.brand_mentions = []
        if self.brand_action_flags is None:
            self.brand_action_flags = []
        if self.review_action_flags is None:
            self.review_action_flags = []


# ============================================================
# 검색 의도 분류기
# ============================================================

class SearchIntentClassifier:
    """검색 의도 자동 분류"""

    # 의도별 패턴 — [R7] Cross-User 행동 모델 대응으로 3종 추가
    # 우선순위: dict 순서. red_flag → validation → comparison가 commercial/informational보다 위.
    # AI(발견) → 네이버(검증) → 솔직 후기 확인 흐름의 검증 단계 키워드 분리.
    INTENT_PATTERNS = {
        'red_flag': [
            # 부정 검색 (경쟁사·자기 한의원 모두 추적 가치)
            '부작용', '위험', '단점', '안좋', '문제', '실패', '후회',
            '사기', '환불', '논란', '의심',
        ],
        'validation': [
            # 신뢰 검증 — Cross-User 핵심 패턴
            '진짜', '솔직', '찐', '정말', '실제로', '리얼',
            '진정', '솔직후기', '진짜효과',
        ],
        'comparison': [
            # 명시적 비교 의도
            'vs', '보다', '차이', '비교',
            '뭐가나', '어디가더', '뭐가더',
        ],
        'transactional': [
            # 구매/예약 의도
            '가격', '비용', '할인', '이벤트', '예약', '상담',
            '무료', '체험', '프로모션', '쿠폰',
            '보험', '실비', '자보', '자동차보험', '치료비', '입원',
            '초진', '진료시간', '야간진료', '주말진료', '일요일진료',
            '당일', '가능', '얼마',
        ],
        'commercial': [
            # 검토/추천 의도 (validation·comparison와 분리됨)
            '추천', '순위', '랭킹', '베스트', '인기',
            '후기', '리뷰', '평가', '잘하는', '유명한', '좋은',
            '전문', '1위', 'top', '맛집',
            '어디', '근처', '내돈내산',
        ],
        'informational': [
            # 정보 탐색 (red_flag/comparison 패턴은 위로 분리됨)
            '방법', '효과', '원인', '증상', '치료', '기간',
            '주의', '종류', '장단점',
            '란', '이란', '뜻', '의미', '알아보기',
        ],
        'navigational': [
            '위치', '주소', '전화', '번호', '오시는길',
            '영업시간', '휴무', '주차', '근처', '가까운',
        ],
    }

    @classmethod
    def classify(cls, keyword: str) -> str:
        """키워드의 검색 의도 분류"""
        keyword_lower = keyword.lower()

        # 각 의도별 매칭 점수 계산
        scores = {intent: 0 for intent in cls.INTENT_PATTERNS}

        for intent, patterns in cls.INTENT_PATTERNS.items():
            for pattern in patterns:
                if pattern in keyword_lower:
                    scores[intent] += 1

        # 가장 높은 점수의 의도 반환
        max_score = max(scores.values())
        if max_score > 0:
            for intent, score in scores.items():
                if score == max_score:
                    return intent

        # 기본값: 상업적 의도 (한의원 키워드 특성)
        return 'commercial'

    @classmethod
    def get_intent_label(cls, intent: str) -> str:
        """의도 레이블 (한글)"""
        labels = {
            'red_flag': '⚠️ 부정 검색 (부작용/단점)',
            'validation': '✅ 신뢰 검증 (진짜/솔직)',
            'comparison': '⚖️ 비교 의도 (vs/차이)',
            'transactional': '💰 거래형 (가격/예약)',
            'commercial': '🔍 상업형 (비교/후기)',
            'informational': '📚 정보형 (효과/방법)',
            'navigational': '📍 탐색형 (위치/연락처)',
            'unknown': '❓ 미분류',
        }
        return labels.get(intent, '❓ 미분류')


# ============================================================
# 시즌 키워드 DB (ULTRA 이식)
# ============================================================

class SeasonalKeywordDB:
    """월별 시즌 키워드 데이터베이스"""

    SEASONAL_KEYWORDS = {
        # 다이어트
        "다이어트": {
            1: ["새해 다이어트", "신년 다이어트", "겨울 다이어트"],
            2: ["졸업 다이어트", "취업준비 다이어트", "봄맞이 다이어트"],
            3: ["봄 다이어트", "환절기 다이어트"],
            4: ["봄 다이어트", "웨딩 다이어트"],
            5: ["여름 준비 다이어트", "웨딩 다이어트"],
            6: ["여름 다이어트", "휴가전 다이어트", "반팔 다이어트"],
            7: ["여름 다이어트", "휴가 전 다이어트", "비키니 다이어트"],
            8: ["여름 다이어트", "가을준비 다이어트"],
            9: ["가을 다이어트", "추석 후 다이어트"],
            10: ["가을 다이어트", "환절기 다이어트"],
            11: ["겨울 다이어트", "연말 다이어트"],
            12: ["연말 다이어트", "새해준비 다이어트"]
        },
        # 안면비대칭
        "안면비대칭": {
            2: ["졸업사진 비대칭", "면접 비대칭", "증명사진 비대칭"],
            3: ["졸업 안면비대칭", "면접 준비 교정"],
            4: ["봄 비대칭교정", "웨딩 안면교정"],
            5: ["웨딩 안면비대칭", "결혼준비 교정"],
            7: ["여름방학 교정", "휴가전 교정"],
            9: ["추석 전 교정", "가을 비대칭교정"],
            11: ["수능 후 교정", "겨울방학 교정"],
            12: ["연말 비대칭교정", "새해 교정"]
        },
        # 여드름/피부
        "여드름": {
            1: ["겨울 건조 여드름", "새해 피부관리"],
            2: ["환절기 여드름", "봄철 여드름"],
            3: ["봄 피부관리", "환절기 피부"],
            5: ["여름 피부", "자외선 피부"],
            6: ["여름 여드름", "땀 여드름"],
            7: ["땀 여드름", "마스크 여드름"],
            9: ["가을 피부", "환절기 여드름"],
            12: ["겨울 건조 피부", "연말 피부관리"]
        },
        # 교통사고
        "교통사고": {
            1: ["빙판길 교통사고", "겨울 교통사고", "설 귀성길 사고"],
            2: ["설 귀성길 교통사고", "빙판길 사고"],
            6: ["장마철 교통사고", "빗길 교통사고"],
            7: ["휴가철 교통사고", "피서길 사고"],
            9: ["추석 귀성길 교통사고", "명절 교통사고"],
            12: ["연말 교통사고", "송년회 교통사고", "눈길 교통사고"]
        },
        # 리프팅
        "리프팅": {
            2: ["졸업사진 리프팅", "면접준비 리프팅"],
            4: ["봄 리프팅", "웨딩 리프팅"],
            5: ["웨딩 리프팅", "결혼 리프팅"],
            7: ["여름휴가 피부", "바캉스 리프팅"],
            9: ["추석 리프팅", "가을 리프팅"],
            12: ["연말 모임 피부", "송년회 피부"]
        },
        # 탈모
        "탈모": {
            1: ["겨울 탈모", "두피 건조"],
            3: ["환절기 탈모", "봄 탈모"],
            5: ["결혼준비 탈모", "취업 탈모"],
            6: ["여름 탈모", "땀 두피"],
            9: ["환절기 탈모", "가을 탈모"],
            12: ["겨울 탈모", "연말 탈모치료"]
        },
        # 면역/보약
        "보약": {
            1: ["새해 보약", "설 보약"],
            3: ["환절기 보약", "봄 보약"],
            5: ["어버이날 보약", "부모님 보약"],
            9: ["추석 보약", "환절기 면역"],
            12: ["연말 보약", "겨울 면역"]
        },
        # 수험생
        "수험생": {
            3: ["새학기 집중력", "개학 한약"],
            6: ["기말고사 한약", "시험기간 집중력"],
            9: ["수능 100일 한약"],
            11: ["수능 한약", "수능 집중력"],
            12: ["겨울방학 보약", "수능 후 보양"]
        },
        # 알레르기
        "알레르기": {
            3: ["봄 알레르기", "황사 비염", "미세먼지 비염"],
            4: ["꽃가루 알레르기", "봄철 비염"],
            9: ["환절기 비염", "가을 알레르기"]
        }
    }

    @classmethod
    def get_current_seasonal_keywords(cls) -> List[Tuple[str, str]]:
        """현재 월의 시즌 키워드 반환 (keyword, category)"""
        current_month = datetime.now().month
        keywords = []

        for category, months in cls.SEASONAL_KEYWORDS.items():
            # 현재 월 ± 1개월 키워드 포함
            for month in [current_month - 1, current_month, current_month + 1]:
                adjusted_month = month if month > 0 else month + 12
                adjusted_month = adjusted_month if adjusted_month <= 12 else adjusted_month - 12

                if adjusted_month in months:
                    for kw in months[adjusted_month]:
                        keywords.append((f"{GYULIM_KEYWORD_PROFILE.primary_region} {kw}", category))

        return keywords


# ============================================================
# 중복 키워드 병합기
# ============================================================

class KeywordMerger:
    """중복/유사 키워드 병합"""

    @staticmethod
    def normalize(keyword: str) -> str:
        """키워드 정규화 (공백 제거, 소문자)"""
        return keyword.replace(" ", "").lower()

    @staticmethod
    def are_similar(kw1: str, kw2: str) -> bool:
        """두 키워드가 유사한지 판단"""
        # 정규화 후 동일
        if KeywordMerger.normalize(kw1) == KeywordMerger.normalize(kw2):
            return True

        # 공백만 다른 경우
        if kw1.replace(" ", "") == kw2.replace(" ", ""):
            return True

        # 순서만 다른 경우 (2단어)
        words1 = set(kw1.split())
        words2 = set(kw2.split())
        if len(words1) == len(words2) == 2 and words1 == words2:
            return True

        return False

    @classmethod
    def find_duplicates(cls, keywords: List[str]) -> Dict[str, List[str]]:
        """중복 키워드 그룹 찾기"""
        groups = defaultdict(list)
        processed = set()

        for kw in keywords:
            if kw in processed:
                continue

            normalized = cls.normalize(kw)
            groups[normalized].append(kw)
            processed.add(kw)

            # 다른 키워드와 비교
            for other in keywords:
                if other != kw and other not in processed:
                    if cls.are_similar(kw, other):
                        groups[normalized].append(other)
                        processed.add(other)

        # 2개 이상인 그룹만 반환
        return {k: v for k, v in groups.items() if len(v) > 1}

    @classmethod
    def merge_results(cls, results: Dict[str, 'KeywordResult']) -> Dict[str, 'KeywordResult']:
        """중복 키워드 병합 (높은 검색량 유지)"""
        keywords = list(results.keys())
        duplicates = cls.find_duplicates(keywords)

        if not duplicates:
            return results

        merged_results = {}
        merged_keywords = set()

        for normalized, group in duplicates.items():
            # 그룹 내 최고 검색량 키워드 선택
            best = max(group, key=lambda k: results[k].search_volume)
            best_result = results[best]

            # 병합 정보 추가
            others = [k for k in group if k != best]
            best_result.merged_from = others
            best_result.business_core = any(results[k].business_core for k in group)
            best_result.source_signals = sorted({
                signal
                for k in group
                for signal in (results[k].source_signals or [results[k].source])
            })
            best_result.quality_flags = sorted({
                flag
                for k in group
                for flag in (results[k].quality_flags or [])
            })
            best_result.verification_score = max(results[k].verification_score for k in group)
            best_result.longtail_score = max(results[k].longtail_score for k in group)
            best_result.business_value_score = max(results[k].business_value_score for k in group)
            best_result.high_value_longtail = any(results[k].high_value_longtail for k in group)
            best_result.inbound_impressions = sum(results[k].inbound_impressions for k in group)
            best_result.inbound_clicks = sum(results[k].inbound_clicks for k in group)
            best_result.inbound_ctr = (
                best_result.inbound_clicks / best_result.inbound_impressions
                if best_result.inbound_impressions > 0 else 0.0
            )
            inbound_positions = [results[k].inbound_position for k in group if results[k].inbound_position > 0]
            best_result.inbound_position = min(inbound_positions) if inbound_positions else 0.0
            best_result.inbound_sources = sorted({
                source
                for k in group
                for source in (results[k].inbound_sources or [])
            })
            best_result.mobile_share = max(results[k].mobile_share for k in group)
            best_result.content_cluster_key = best_result.content_cluster_key or next(
                (results[k].content_cluster_key for k in group if results[k].content_cluster_key),
                "",
            )
            rank_candidates = [results[k] for k in group if results[k].rank_gap_signal > 0 or results[k].owned_rank > 0]
            if rank_candidates:
                rank_best = max(rank_candidates, key=lambda r: r.rank_gap_signal)
                best_result.owned_rank = rank_best.owned_rank
                best_result.owned_rank_device = rank_best.owned_rank_device
                best_result.rank_gap_signal = rank_best.rank_gap_signal
                best_result.rank_status = rank_best.rank_status
            community_candidates = [results[k] for k in group if results[k].community_signal > 0 or results[k].community_mentions > 0]
            if community_candidates:
                community_best = max(community_candidates, key=lambda r: r.community_signal)
                best_result.community_mentions = sum(results[k].community_mentions for k in group)
                best_result.community_conversion_fit = max(results[k].community_conversion_fit for k in group)
                best_result.community_signal = community_best.community_signal
                best_result.community_platforms = sorted({
                    platform
                    for k in group
                    for platform in (results[k].community_platforms or [])
                })
            conversion_candidates = [results[k] for k in group if results[k].conversion_signal > 0 or results[k].conversion_calls > 0]
            if conversion_candidates:
                conversion_best = max(conversion_candidates, key=lambda r: r.conversion_signal)
                best_result.conversion_calls = sum(results[k].conversion_calls for k in group)
                best_result.conversion_naver_calls = sum(results[k].conversion_naver_calls for k in group)
                best_result.conversion_duration_seconds = sum(results[k].conversion_duration_seconds for k in group)
                best_result.conversion_signal = conversion_best.conversion_signal
            profile_action_candidates = [results[k] for k in group if results[k].profile_action_signal > 0 or results[k].profile_actions_total > 0]
            if profile_action_candidates:
                profile_action_best = max(profile_action_candidates, key=lambda r: r.profile_action_signal)
                best_result.profile_action_signal = profile_action_best.profile_action_signal
                best_result.profile_actions_total = sum(results[k].profile_actions_total for k in group)
                best_result.profile_direction_actions = sum(results[k].profile_direction_actions for k in group)
                best_result.profile_website_actions = sum(results[k].profile_website_actions for k in group)
                best_result.profile_booking_actions = sum(results[k].profile_booking_actions for k in group)
                best_result.profile_message_actions = sum(results[k].profile_message_actions for k in group)
                best_result.profile_action_sources = sorted({
                    source
                    for k in group
                    for source in (results[k].profile_action_sources or [])
                })
                best_result.profile_action_flags = sorted({
                    flag
                    for k in group
                    for flag in (results[k].profile_action_flags or [])
                })
            availability_candidates = [results[k] for k in group if results[k].availability_intent_score > 0]
            if availability_candidates:
                availability_best = max(availability_candidates, key=lambda r: r.availability_intent_score)
                best_result.availability_intent_score = availability_best.availability_intent_score
                best_result.availability_intent_type = availability_best.availability_intent_type
                best_result.availability_action_flags = sorted({
                    flag
                    for k in group
                    for flag in (results[k].availability_action_flags or [])
                })
            payment_candidates = [results[k] for k in group if results[k].payment_coverage_score > 0]
            if payment_candidates:
                payment_best = max(payment_candidates, key=lambda r: r.payment_coverage_score)
                best_result.payment_coverage_score = payment_best.payment_coverage_score
                best_result.payment_coverage_type = payment_best.payment_coverage_type
                best_result.payment_action_flags = sorted({
                    flag
                    for k in group
                    for flag in (results[k].payment_action_flags or [])
                })
            access_candidates = [results[k] for k in group if results[k].access_convenience_score > 0]
            if access_candidates:
                access_best = max(access_candidates, key=lambda r: r.access_convenience_score)
                best_result.access_convenience_score = access_best.access_convenience_score
                best_result.access_convenience_type = access_best.access_convenience_type
                best_result.access_convenience_flags = sorted({
                    flag
                    for k in group
                    for flag in (results[k].access_convenience_flags or [])
                })
            risk_candidates = [results[k] for k in group if results[k].medical_ad_risk_score > 0]
            if risk_candidates:
                risk_worst = max(risk_candidates, key=lambda r: r.medical_ad_risk_score)
                best_result.medical_ad_risk_score = risk_worst.medical_ad_risk_score
                best_result.medical_ad_risk_flags = sorted({
                    flag
                    for k in group
                    for flag in (results[k].medical_ad_risk_flags or [])
                })
                best_result.content_feasibility_score = min(results[k].content_feasibility_score for k in group)
            best_result.local_service_fit_score = max(results[k].local_service_fit_score for k in group)
            best_result.negative_intent_flags = sorted({
                flag
                for k in group
                for flag in (results[k].negative_intent_flags or [])
            })
            action_candidates = [results[k] for k in group if results[k].content_actionability_score > 0]
            if action_candidates:
                action_best = max(action_candidates, key=lambda r: r.content_actionability_score)
                best_result.content_actionability_score = action_best.content_actionability_score
                best_result.recommended_content_type = action_best.recommended_content_type
                best_result.content_action_flags = sorted({
                    flag
                    for k in group
                    for flag in (results[k].content_action_flags or [])
                })
            surface_candidates = [results[k] for k in group if results[k].local_surface_score > 0]
            if surface_candidates:
                surface_best = max(surface_candidates, key=lambda r: r.local_surface_score)
                best_result.local_surface_score = surface_best.local_surface_score
                best_result.preferred_search_surface = surface_best.preferred_search_surface
                best_result.local_surface_flags = sorted({
                    flag
                    for k in group
                    for flag in (results[k].local_surface_flags or [])
                })
            brand_candidates = [
                results[k] for k in group
                if results[k].brand_signal_score > 0 or results[k].competitor_brand_risk_score > 0
            ]
            if brand_candidates:
                brand_best = max(
                    brand_candidates,
                    key=lambda r: (r.competitor_brand_risk_score, r.brand_signal_score),
                )
                best_result.brand_intent_type = brand_best.brand_intent_type
                best_result.brand_signal_score = max(results[k].brand_signal_score for k in group)
                best_result.competitor_brand_risk_score = max(
                    results[k].competitor_brand_risk_score for k in group
                )
                best_result.brand_mentions = sorted({
                    mention
                    for k in group
                    for mention in (results[k].brand_mentions or [])
                })
                best_result.brand_action_flags = sorted({
                    flag
                    for k in group
                    for flag in (results[k].brand_action_flags or [])
                })
            review_candidates = [
                results[k] for k in group
                if results[k].review_surface_score > 0 or results[k].reputation_risk_score > 0
            ]
            if review_candidates:
                review_best = max(
                    review_candidates,
                    key=lambda r: (r.reputation_risk_score, r.review_surface_score),
                )
                best_result.review_surface_score = max(results[k].review_surface_score for k in group)
                best_result.reputation_risk_score = max(results[k].reputation_risk_score for k in group)
                best_result.review_intent_type = review_best.review_intent_type
                best_result.review_action_flags = sorted({
                    flag
                    for k in group
                    for flag in (results[k].review_action_flags or [])
                })

            # 검색량 합산 (옵션)
            total_volume = sum(results[k].search_volume for k in group)
            best_result.search_volume = total_volume

            # KEI 재계산 (검색량 합산 후)
            if best_result.document_count > 0 and total_volume > 0:
                best_result.kei = calculate_real_kei(total_volume, best_result.document_count)
                # KEI 등급 재부여
                if best_result.kei >= 500:
                    best_result.kei_grade = 'S'
                elif best_result.kei >= 200:
                    best_result.kei_grade = 'A'
                elif best_result.kei >= 50:
                    best_result.kei_grade = 'B'
                else:
                    best_result.kei_grade = 'C'

            merged_results[best] = best_result
            merged_keywords.update(group)

        # 병합되지 않은 키워드 추가
        for kw, result in results.items():
            if kw not in merged_keywords:
                merged_results[kw] = result

        return merged_results

    @classmethod
    def get_merge_stats(cls, original_count: int, merged_count: int) -> str:
        """병합 통계 문자열"""
        removed = original_count - merged_count
        if removed > 0:
            return f"🔗 중복 병합: {original_count}개 → {merged_count}개 ({removed}개 통합)"
        return ""


# ============================================================
# Google 자동완성 (다중 소스 키워드 수집)
# ============================================================

class GoogleAutocomplete:
    """Google 자동완성 API - 키워드 다양성 확보용"""

    def __init__(self, delay: float = 0.3):
        self.delay = delay
        self.base_url = "https://suggestqueries.google.com/complete/search"
        self._last_call = 0
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def get_suggestions(self, keyword: str, max_retries: int = 2) -> List[str]:
        """Google 자동완성 제안 가져오기"""
        params = {
            "client": "firefox",  # JSON 응답
            "q": keyword,
            "hl": "ko"
        }

        for attempt in range(max_retries):
            try:
                self._rate_limit()
                response = requests.get(
                    self.base_url,
                    params=params,
                    headers=self.headers,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    # 응답 형식: [검색어, [제안목록], ...]
                    if len(data) > 1 and isinstance(data[1], list):
                        return data[1][:10]
                return []

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    time.sleep(2)
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1)

        return []


# ============================================================
# 키워드 수집기
# ============================================================

class LegionCollector:
    """LEGION MODE 키워드 수집기 (Multi-Source)"""

    # 활성 클리닉과 무관한 키워드 블랙리스트.
    # 프로필에 따라 일부 의료과/시술명은 치료축 안에 포함될 수 있다.
    BLACKLIST_KEYWORDS = [
        # 다른 진료과 (한의원 진료 영역 외)
        '치과', '정형외과', '산부인과', '안과', '외과',
        '성형외과', '신경외과', '비뇨기과',
        # 비의료
        '카페', '맛집', '식당', '음식점', '술집', '호프',
        '학원', '학교', '유치원', '어린이집',
    ]

    def __init__(self, delay: float = 0.3, use_google: bool = True):
        self.delay = delay
        self._last_call = 0
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.naver.com/",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }

        # Google 자동완성 (다중 소스)
        self.use_google = use_google
        if use_google:
            self.google = GoogleAutocomplete(delay=0.5)
        else:
            self.google = None

        # 지역/동네 기준은 활성 클리닉 프로필을 따른다.
        self.cheongju_regions = list(GYULIM_KEYWORD_PROFILE.cheongju_regions)
        self.nearby_regions = list(GYULIM_KEYWORD_PROFILE.nearby_regions)
        self.neighborhoods = list(GYULIM_KEYWORD_PROFILE.neighborhoods)

        # 활성 클리닉 진료축 관련 키워드. 공용 프로필 + 보조 진료군을 합친다.
        self.hanbang_keywords = list(GYULIM_KEYWORD_PROFILE.hanbang_keywords) + [
            "갱년기", "생리", "산후", "불임",
            "불면", "두통", "어지럼",
            "편두통", "만성두통", "어지럼증",
            "다한증", "냉증", "수족냉증", "땀",
            "자율신경", "스트레스", "화병", "불안", "우울",
            "탈모", "비염", "축농증", "알레르기", "보약",
        ]
        self.hanbang_keywords = list(dict.fromkeys(self.hanbang_keywords))

        # 의도 키워드 (Round 4용) - B: 의도 기반 롱테일 강화
        self.intent_suffixes = [
            # 기본 의도
            "가격", "비용", "후기", "추천", "잘하는곳",
            "효과", "부작용", "전후", "치료비", "보험",
            # 시간 관련
            "야간진료", "야간", "24시", "주말진료", "일요일진료",
            # 보험/비용 상세 (높은 전환 의도)
            "자보", "실비", "건강보험", "의료비", "할인",
            # 구체적 니즈
            "예약", "상담", "초진", "진료시간", "주차",
            # 결과/신뢰. 성공사례/전후사진류는 의료광고 리스크가 커서 자동 확장 제외.
            "실제후기", "솔직후기"
        ]

        # C: 문제 해결형 키워드 (증상 + 고민)
        self.problem_keywords = [
            # 통증/근골격
            "만성두통", "편두통", "목통증", "어깨통증", "허리통증",
            "거북목", "일자목", "손목터널증후군", "허리디스크", "목디스크",
            "오십견", "테니스엘보", "족저근막염", "무릎통증",
            # 체형 문제
            "골반틀어짐", "척추측만", "체형불균형", "다리길이차이",
            "휜다리", "오다리", "X자다리", "골반교정",
            # 피부/미용
            "안면홍조", "주사피부", "여드름흉터", "패인흉터", "모공흉터",
            # 정신/스트레스
            "불면증", "만성피로", "번아웃", "자율신경실조", "공황장애"
        ]
        for profile in GYULIM_KEYWORD_PROFILE.profiles:
            self.problem_keywords.extend(profile.core_tokens)
        self.problem_keywords = list(dict.fromkeys(self.problem_keywords))

        # 카테고리 패턴 (S/A급 0% 카테고리 추가)
        self.category_patterns = {
            # ===== 메인 카테고리 (DB와 일치) =====
            "다이어트": [
                "다이어트", "비만", "살빼", "체중", "다이어트한약", "비만한의원", "한방다이어트",
                "뱃살", "하체비만", "상체비만", "팔뚝살", "허벅지살",
                "산후다이어트", "남자다이어트", "식욕억제", "체지방", "비만클리닉"
            ],
            "안면비대칭": [
                "안면비대칭", "얼굴비대칭", "턱비대칭", "비대칭교정", "안면교정",
                "광대비대칭", "눈비대칭", "입비대칭",
                "안면윤곽", "턱관절", "사각턱", "얼굴교정", "골격교정", "얼굴작아지는법"
            ],
            "체형교정": ["체형교정", "골반교정", "자세교정", "척추측만"],
            "피부/여드름": [
                "여드름", "여드름흉터", "새살침", "흉터",
                "여드름한의원", "성인여드름", "턱여드름", "등여드름",
                "여드름자국", "흉터치료", "패인흉터", "모공흉터", "여드름압출"
            ],
            "교통사고": [
                "교통사고", "자동차사고", "후유증", "입원", "교통사고한의원",
                "자보한의원", "교통사고입원", "자동차보험", "교통사고보험",
                "교통사고목", "교통사고허리", "교통사고두통", "추돌사고"
            ],
            "리프팅/탄력": [
                "리프팅", "매선", "피부탄력", "주름", "동안침",
                "한방리프팅", "매선리프팅", "침리프팅", "매선침", "탄력침",
                "팔자주름", "눈가주름", "이마주름", "목주름",
                "피부처짐", "탄력관리", "콜라겐", "안티에이징", "브이리프팅"
            ],
            # ===== 서브 카테고리 (DB와 일치) =====
            "통증/디스크": [
                "허리디스크", "목디스크", "허리통증", "추나", "도수치료",
                "척추", "디스크한의원", "추나요법", "통증", "어깨", "무릎", "대상포진"
            ],
            "탈모": [
                "탈모", "원형탈모", "정수리탈모", "M자탈모", "여성탈모",
                "탈모한의원", "탈모한약", "두피", "두피관리", "머리숱", "발모"
            ],
            "비염": ["비염", "코막힘", "축농증", "만성비염", "비염한의원"],
            "알레르기/아토피": ["알레르기", "아토피", "알레르기검사", "아토피한의원"],
            "면역/보약": [
                "공진단", "경옥고", "보약", "면역", "보양",
                "보약한의원", "맞춤보약", "체력보강"
            ],
            "갱년기": ["갱년기", "폐경", "여성호르몬", "안면홍조", "갱년기한약"],
            "불면증/수면": ["불면증", "수면장애", "수면", "만성피로", "피로회복", "수면클리닉"],
            "소화/위장": ["소화불량", "위염", "역류성식도염", "담적", "위장"],
            "두통/어지럼": ["두통", "편두통", "어지럼증", "이석증", "만성두통", "이명"],
            "스트레스/자율신경": ["스트레스", "공황장애", "자율신경", "화병", "불안"],
            "여성건강/산후조리": ["산후조리", "산후보약", "생리통", "난임", "여성질환", "산후도우미", "산후조리원"],
            "다한증/냉증": ["다한증", "수족냉증", "손땀", "냉증", "땀"],
            "수험생/집중력": ["수험생한약", "집중력", "총명탕", "수능한약", "기억력", "수험생"],
            "야간진료": ["야간진료", "야간한의원", "늦게까지", "저녁진료", "주말진료"],
            "한의원일반": ["한의원", "한방병원"],
        }
        for cat, terms in GYULIM_KEYWORD_PROFILE.category_patterns().items():
            existing = self.category_patterns.get(cat, [])
            self.category_patterns[cat] = list(dict.fromkeys(list(terms) + list(existing)))

        self.business_core_categories = set(GYULIM_KEYWORD_PROFILE.business_core_categories)
        skin_profile = GYULIM_KEYWORD_PROFILE.profile_for("피부/여드름")
        self.business_core_skin_tokens = tuple(skin_profile.core_tokens if skin_profile else ())
        self.direct_service_anchors = {
            "다이어트": (
                "한의원", "한방", "한약", "다이어트한약", "비만한의원",
                "비만클리닉", "식욕억제", "체질", "상담",
            ),
            "교통사고": (
                "한의원", "한방병원", "입원", "후유증", "자보",
                "자동차보험", "보험", "치료", "치료비",
            ),
            "피부/여드름": (
                "한의원", "한방", "새살침", "흉터치료", "패인흉터",
                "모공흉터", "여드름흉터", "여드름자국",
            ),
            "안면비대칭": ("한의원", "교정", "안면교정", "얼굴교정", "턱관절"),
            "체형교정": ("한의원", "교정", "골반교정", "자세교정", "척추교정", "추나"),
            "리프팅/탄력": ("한의원", "한방", "매선", "매선리프팅", "한방리프팅", "침리프팅"),
        }
        for cat, anchors in GYULIM_KEYWORD_PROFILE.direct_service_anchors().items():
            existing = self.direct_service_anchors.get(cat, ())
            self.direct_service_anchors[cat] = tuple(dict.fromkeys(tuple(anchors) + tuple(existing)))
        self.low_business_value_terms = {
            "다이어트": (
                "다이어트댄스", "다이어트 댄스", "댄스", "줌바", "요가",
                "필라테스", "헬스", "pt", "피티", "홈트", "운동", "식단",
                "도시락", "쉐이크", "보조제", "챌린지", "캠프", "학원",
            ),
            "피부/여드름": (
                "화장품", "폼클렌징", "클렌징", "연고", "패치", "압출기",
                "마스크팩", "올리브영",
            ),
            "안면비대칭": ("셀프", "마사지", "운동", "유튜브", "홈케어"),
            "체형교정": ("셀프", "운동", "유튜브", "홈트", "필라테스", "요가"),
            "리프팅/탄력": ("화장품", "팩", "마사지", "홈케어"),
        }
        for cat, terms in GYULIM_KEYWORD_PROFILE.low_business_value_terms().items():
            existing = self.low_business_value_terms.get(cat, ())
            self.low_business_value_terms[cat] = tuple(dict.fromkeys(tuple(terms) + tuple(existing)))

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    # ===== 도메인/지역 적합도 헬퍼 (관련도 강등용) =====

    # 기존 호출부 호환용 기본값. 실제 판정은 활성 프로필의 토큰을 우선 사용한다.
    MEDICAL_GENERAL_TOKENS = tuple(GYULIM_KEYWORD_PROFILE.medical_general_tokens)
    HANBANG_INDICATORS = tuple(GYULIM_KEYWORD_PROFILE.hanbang_indicators)

    def _is_medical_general(self, keyword: str) -> bool:
        """활성 프로필의 진료축 밖 의료 일반과 키워드인지 판정한다."""
        text = keyword or ""
        medical_general_tokens = tuple(getattr(GYULIM_KEYWORD_PROFILE, "medical_general_tokens", self.MEDICAL_GENERAL_TOKENS))
        service_indicators = tuple(getattr(GYULIM_KEYWORD_PROFILE, "hanbang_indicators", self.HANBANG_INDICATORS))
        if not any(t in text for t in medical_general_tokens):
            return False
        # 프로필별 서비스 indicator가 동반되면 비교/전환 콘텐츠로 활용 가능하다.
        return not any(h in text for h in service_indicators)

    def _is_in_target_region(self, keyword: str) -> bool:
        """본 사업영역 매칭. 인접 권역은 기본적으로 False."""
        return GYULIM_KEYWORD_PROFILE.is_target_region(keyword)

    def apply_relevance_demotion(self, keyword: str, grade: str) -> Tuple[str, Optional[str]]:
        """
        도메인/지역 관련도 기반 등급 강등.
        Returns: (new_grade, reason or None)
        - 의료 일반과: S/A/B -> C (사업 무관)
        - 비타깃 지역: 2단계 강등 (S->B, A->C)
        """
        # P1: 의료 일반과 누수 차단
        if self._is_medical_general(keyword):
            if grade in ('S', 'A', 'B'):
                return 'C', 'medical_general'
        # P2: 비타깃 지역 2단계 강등
        if not self._is_in_target_region(keyword):
            order = ['S', 'A', 'B', 'C']
            if grade in order:
                idx = order.index(grade)
                new_idx = min(idx + 2, len(order) - 1)
                if new_idx > idx:
                    return order[new_idx], 'non_target_region'
        return grade, None

    def _detect_category(self, keyword: str) -> str:
        kw = keyword.lower()
        profile_category = GYULIM_KEYWORD_PROFILE.detect_category(keyword, default="")
        if profile_category in GYULIM_KEYWORD_PROFILE.focus_categories:
            return profile_category
        # 한방 indicator는 카테고리 매칭 우선 — "기타" fallback 누수 방지
        for cat, patterns in self.category_patterns.items():
            if any(p in kw for p in patterns):
                return cat
        # 한의원/한약 들어있는데 다른 카테고리에 매칭 안 됐으면 한의원일반
        if any(h in kw for h in ('한의원', '한약', '한방', '한방병원')):
            return '한의원일반'
        return "기타"

    def _is_core_skin_keyword(self, keyword: str) -> bool:
        """실제 유입 핵심인 여드름/흉터/새살침 계열만 피부 핵심군으로 본다."""
        return any(token in keyword for token in self.business_core_skin_tokens)

    def _has_direct_service_anchor(self, keyword: str, category: Optional[str] = None) -> bool:
        """검색어가 한의원 서비스로 직접 이어지는 표현을 포함하는지 확인."""
        if category is None:
            category = self._detect_category(keyword)
        anchors = self.direct_service_anchors.get(category, ())
        return any(anchor in keyword for anchor in anchors)

    def low_business_value_reason(self, keyword: str, category: Optional[str] = None) -> Optional[str]:
        """진료/상담 의도보다 활동·상품·자가관리 의도가 강한 누수 키워드 판정."""
        if category is None:
            category = self._detect_category(keyword)
        profile_reason = GYULIM_KEYWORD_PROFILE.low_business_value_reason(keyword, category)
        if profile_reason:
            return profile_reason
        kw_lower = (keyword or "").lower()
        terms = self.low_business_value_terms.get(category, ())
        matched = next((term for term in terms if term.lower() in kw_lower), None)
        if not matched:
            return None

        # 직접 진료 앵커가 있으면 완전 제외하지 않고 점수 단계에서만 보수적으로 다룬다.
        if self._has_direct_service_anchor(keyword, category):
            return None
        return f"low_business_value_{category}:{matched}"

    def is_business_core_keyword(self, keyword: str, category: Optional[str] = None) -> bool:
        """등급과 별개로 사업상 실제 유입 핵심군인지 판정."""
        if category is None:
            category = self._detect_category(keyword)
        category = GYULIM_KEYWORD_PROFILE.normalize_category(category)

        if category in GYULIM_KEYWORD_PROFILE.focus_categories:
            return GYULIM_KEYWORD_PROFILE.is_business_core_keyword(keyword, category)
        return False

    def is_focus_candidate(self, keyword: str, category: Optional[str] = None) -> bool:
        """활성 프로필의 기본 Legion 타깃 진료축 중심."""
        if category is None:
            category = self._detect_category(keyword)
        category = GYULIM_KEYWORD_PROFILE.normalize_category(category)

        if self.low_business_value_reason(keyword, category):
            return False
        if category in GYULIM_KEYWORD_PROFILE.focus_categories:
            return GYULIM_KEYWORD_PROFILE.is_focus_candidate(keyword, category)

        return False

    def _is_valid_keyword(self, keyword: str) -> bool:
        """유효한 키워드인지 확인"""
        # 활성 프로필의 타깃 또는 인근 지역 포함
        has_region = GYULIM_KEYWORD_PROFILE.is_target_region(keyword, include_nearby=True)
        # 활성 프로필의 진료/시술 관련 키워드 포함
        has_hanbang = GYULIM_KEYWORD_PROFILE.has_hanbang_or_treatment_signal(keyword) or any(
            h in keyword for h in self.hanbang_keywords
        )
        return has_region and has_hanbang

    def _is_blacklisted_keyword(self, keyword: str) -> bool:
        text = keyword or ""
        cosmetic_scope = getattr(GYULIM_KEYWORD_PROFILE, "cosmetic_clinic_terms_on_scope", False)
        scar_skin_context = any(
            token in text
            for token in ("흉터", "여드름", "패인흉터", "모공흉터", "수술흉터", "켈로이드", "피부")
        )
        for blocked in self.BLACKLIST_KEYWORDS:
            if blocked not in text:
                continue
            if cosmetic_scope and blocked in {"성형외과", "외과"} and scar_skin_context:
                continue
            return True
        return False

    def _filter_blacklist(self, keywords: List[str]) -> List[str]:
        """블랙리스트 키워드 필터링"""
        if not keywords:
            return keywords
        return [kw for kw in keywords if not self._is_blacklisted_keyword(kw)]

    def get_autocomplete(self, keyword: str, max_retries: int = 3) -> List[str]:
        """Naver 자동완성 가져오기 (재시도 로직 포함)"""
        url = "https://ac.search.naver.com/nx/ac"
        params = {
            "q": keyword, "q_enc": "UTF-8", "st": 100, "frm": "nv",
            "r_format": "json", "r_enc": "UTF-8", "r_unicode": 0,
            "t_koreng": 1, "ans": 2, "run": 2, "rev": 4, "con": 1
        }

        for attempt in range(max_retries):
            try:
                self._rate_limit()
                response = requests.get(url, params=params, headers=self.headers, timeout=15)

                # 429/503 에러 처리
                if response.status_code == 429:
                    wait_time = 60 + (attempt * 30)
                    print(f"   ⚠️ 429 에러 - {wait_time}초 대기...")
                    time.sleep(wait_time)
                    continue
                if response.status_code == 503:
                    wait_time = 30 + (attempt * 15)
                    print(f"   ⚠️ 503 에러 - {wait_time}초 대기...")
                    time.sleep(wait_time)
                    continue

                data = response.json()
                if "items" in data and data["items"] and len(data["items"]) > 0:
                    raw_results = [item[0] if isinstance(item, list) else item for item in data["items"][0]]
                    return self._filter_blacklist(raw_results)
                return []

            except requests.exceptions.Timeout:
                wait_time = 5 * (attempt + 1)
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
            except Exception as e:
                wait_time = 2 ** (attempt + 1)
                if attempt < max_retries - 1:
                    time.sleep(wait_time)

        return []

    def get_autocomplete_multi(self, keyword: str) -> Set[str]:
        """다중 소스 자동완성 (Naver + Google)"""
        results = set()

        # 1. Naver 자동완성
        naver_results = self.get_autocomplete(keyword)
        if naver_results:
            results.update(naver_results)

        # 2. Google 자동완성 (활성화된 경우)
        if self.use_google and self.google:
            google_results = self.google.get_suggestions(keyword)
            if google_results:
                # Google 결과 중 유효한 것만 추가 (블랙리스트 필터 적용)
                filtered_google = self._filter_blacklist(google_results)
                for kw in filtered_google:
                    if self._is_valid_keyword(kw):
                        results.add(kw)

        return results

    def get_related_keywords(self, keyword: str, max_retries: int = 3) -> List[str]:
        """Naver 검색 결과의 연관검색어 가져오기 (재시도 로직 포함)"""
        url = "https://search.naver.com/search.naver"
        params = {"where": "nexearch", "query": keyword}

        for attempt in range(max_retries):
            try:
                self._rate_limit()
                response = requests.get(url, params=params, headers=self.headers, timeout=15)

                # 429/503 에러 처리
                if response.status_code == 429:
                    wait_time = 60 + (attempt * 30)
                    print(f"   ⚠️ 429 에러 - {wait_time}초 대기...")
                    time.sleep(wait_time)
                    continue
                if response.status_code == 503:
                    wait_time = 30 + (attempt * 15)
                    print(f"   ⚠️ 503 에러 - {wait_time}초 대기...")
                    time.sleep(wait_time)
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')
                related = []

                # 방법 1: lst_related_srch 클래스
                related_list = soup.find('ul', class_='lst_related_srch')
                if related_list:
                    for li in related_list.find_all('li'):
                        text = li.get_text(strip=True)
                        if text and len(text) > 2 and text not in ['더보기', '열기', '닫기']:
                            related.append(text)

                # 방법 2: related_srch 영역
                if not related:
                    related_box = soup.find('div', class_='related_srch')
                    if related_box:
                        for a in related_box.find_all('a'):
                            text = a.get_text(strip=True)
                            if text and len(text) > 2 and text not in ['더보기', '열기', '닫기', '도움말']:
                                related.append(text)

                # 방법 3: 우측 연관검색어
                if not related:
                    right_related = soup.find(id='nx_right_related_keywords')
                    if right_related:
                        for a in right_related.find_all('a'):
                            text = a.get_text(strip=True)
                            if text and len(text) > 2 and text not in ['더보기', '열기', '닫기', '도움말', '검색어제안 기능 닫기']:
                                related.append(text)

                return self._filter_blacklist(related[:10])

            except requests.exceptions.Timeout:
                wait_time = 5 * (attempt + 1)
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"   ⚠️ 연관검색어 조회 실패 ({keyword}): {e}")
                wait_time = 2 ** (attempt + 1)
                if attempt < max_retries - 1:
                    time.sleep(wait_time)

        return []


# ============================================================
# SERP 분석기 (성능 최적화: 캐싱 + 병렬 + 샘플링)
# ============================================================

class SERPCache:
    """SERP 분석 결과 캐시 (SQLite 기반) - document_count 지원"""

    def __init__(self, db_path: str = "db/serp_cache.db", max_age_days: int = 7):
        self.db_path = db_path
        self.max_age_days = max_age_days
        self._init_db()
        self._memory_cache = {}  # 메모리 캐시 (세션 내)

    def _init_db(self):
        """캐시 테이블 생성 (document_count 포함)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS serp_cache (
                    keyword TEXT PRIMARY KEY,
                    difficulty INTEGER,
                    opportunity INTEGER,
                    grade TEXT,
                    document_count INTEGER DEFAULT 0,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cached_at ON serp_cache(cached_at)')

            # 기존 테이블에 document_count 컬럼 추가 (마이그레이션)
            try:
                cursor.execute("ALTER TABLE serp_cache ADD COLUMN document_count INTEGER DEFAULT 0")
            except Exception:
                pass  # 이미 존재하는 경우 무시

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"⚠️ SERP 캐시 DB 초기화 실패: {e}")

    def get(self, keyword: str) -> Optional[Tuple[int, int, str, int]]:
        """캐시에서 조회 → (difficulty, opportunity, grade, document_count)"""
        # 메모리 캐시 먼저
        if keyword in self._memory_cache:
            return self._memory_cache[keyword]

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cutoff = datetime.now() - timedelta(days=self.max_age_days)
            cursor.execute('''
                SELECT difficulty, opportunity, grade, document_count FROM serp_cache
                WHERE keyword = ? AND cached_at > ?
            ''', (keyword, cutoff))
            row = cursor.fetchone()
            conn.close()

            if row:
                document_count = row[3] or 0
                # document_count가 0이면 캐시 무효 (재분석 필요)
                if document_count == 0:
                    return None  # 캐시 미스로 처리하여 실제 문서 수 파싱
                result = (row[0], row[1], row[2], document_count)
                self._memory_cache[keyword] = result
                return result
        except Exception as e:
            logger.debug(f"캐시 조회 실패 [{keyword}]: {e}")
        return None

    def set(self, keyword: str, difficulty: int, opportunity: int, grade: str, document_count: int = 0):
        """캐시에 저장 (document_count 포함)"""
        self._memory_cache[keyword] = (difficulty, opportunity, grade, document_count)
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO serp_cache (keyword, difficulty, opportunity, grade, document_count, cached_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (keyword, difficulty, opportunity, grade, document_count))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"캐시 저장 실패 [{keyword}]: {e}")

    def get_stats(self) -> Dict:
        """캐시 통계"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM serp_cache')
            total = cursor.fetchone()[0]
            cutoff = datetime.now() - timedelta(days=self.max_age_days)
            cursor.execute('SELECT COUNT(*) FROM serp_cache WHERE cached_at > ?', (cutoff,))
            valid = cursor.fetchone()[0]
            conn.close()
            return {'total': total, 'valid': valid, 'memory': len(self._memory_cache)}
        except Exception as e:
            logger.debug(f"캐시 통계 조회 실패: {e}")
            return {'total': 0, 'valid': 0, 'memory': len(self._memory_cache)}


class SERPAnalyzer:
    """SERP 분석기 (캐싱 + 병렬 + 샘플링) - KEI 지원"""

    def __init__(self, delay: float = 0.5, max_workers: int = 5):
        self.delay = delay
        self.max_workers = max_workers
        self._last_call = 0
        self._lock = asyncio.Lock() if HAS_AIOHTTP else None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        self.cache = SERPCache()
        self._analyzed_count = 0
        self._cache_hit_count = 0
        # 네이버 검색 API (SERP 캡차 우회용 docs count 조회)
        self.naver_api = NaverApiClient() if HAS_NAVER_API else None

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def _fetch_document_count(self, keyword: str) -> int:
        """
        네이버 검색 API의 total 필드로 진짜 docs count 조회.
        SERP HTML 셀렉터가 캡차/구조변경에 취약하므로 API가 1차 소스.
        실패 시 0 반환 → 호출부에서 등급 부여 보류.
        """
        if not self.naver_api or not keyword:
            return 0
        try:
            result = self.naver_api.search_blog(keyword, count=1)
            if isinstance(result, dict):
                total = result.get('total', 0)
                if isinstance(total, int) and total > 0:
                    return total
        except Exception as e:
            logger.debug(f"네이버 API docs 조회 실패 [{keyword}]: {e}")
        return 0

    def _parse_document_count(self, soup: BeautifulSoup) -> int:
        """
        SERP HTML에서 총 문서 수 파싱 (보조 폴백).
        주: 네이버 search.naver.com이 단순 requests에 403을 반환하므로
        대부분 실패. _fetch_document_count(API) 우선 사용 권장.
        실패 시 0 반환 (이전: 10000 폴백 → KEI 부풀림 야기, 제거됨).
        """
        document_count = 0

        result_count_selectors = [
            'span.title_num', 'div.title_area span',
            'span.sub_num', 'em.title_num',
        ]
        for selector in result_count_selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                match = re.search(r'[\d,]+', text)
                if match:
                    try:
                        document_count = int(match.group().replace(',', ''))
                        if document_count > 0:
                            return document_count
                    except (ValueError, AttributeError):
                        pass

        full_text = soup.get_text()
        patterns = [
            r'검색결과\s*약?\s*([\d,]+)\s*건',
            r'([\d,]+)\s*개의?\s*검색\s*결과',
            r'총\s*([\d,]+)\s*건',
        ]
        for pattern in patterns:
            match = re.search(pattern, full_text)
            if match:
                try:
                    document_count = int(match.group(1).replace(',', ''))
                    if document_count > 0:
                        return document_count
                except (ValueError, AttributeError, IndexError):
                    pass

        return 0  # 폴백 10000 제거: 미상이면 0, 등급 보류

    def _parse_serp(self, html: str, keyword: str = "") -> Tuple[int, int, str, int]:
        """SERP HTML 파싱 → (난이도, 기회, 등급, 문서수)

        문서수는 네이버 검색 API(total) 우선 사용, HTML 파싱은 폴백.
        """
        soup = BeautifulSoup(html, 'html.parser')
        post_pattern = re.compile(r'blog\.naver\.com/(\w+)/(\d+)')
        blogs = []
        seen = set()

        # 문서 수: API 우선, HTML 폴백 (둘 다 실패 시 0)
        document_count = self._fetch_document_count(keyword) if keyword else 0
        if document_count == 0:
            document_count = self._parse_document_count(soup)

        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            match = post_pattern.search(href)
            if not match or href in seen:
                continue

            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            seen.add(href)

            # 날짜 찾기
            days = 90
            parent = link.parent
            for _ in range(10):
                if parent is None:
                    break
                text = parent.get_text()
                if m := re.search(r'(\d+)일 전', text):
                    days = int(m.group(1))
                    break
                if m := re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', text):
                    try:
                        d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                        days = (datetime.now() - d).days
                    except (ValueError, TypeError):
                        pass  # 날짜 파싱 실패 시 무시
                    break
                parent = parent.parent

            is_official = any(k in (match.group(1) + title).lower()
                              for k in ["한의원", "병원", "의원", "클리닉"])

            blogs.append({'days': days, 'official': is_official})
            if len(blogs) >= 10:
                break

        # 난이도 계산
        difficulty = 0
        for b in blogs[:5]:
            if b['official']:
                difficulty += 15
            if b['days'] <= 30:
                difficulty += 10
            elif b['days'] <= 90:
                difficulty += 5

        # 기회 계산
        opportunity = 0
        for i, b in enumerate(blogs[:5]):
            w = 5 - i
            if b['days'] > 180:
                opportunity += 10 * w
            elif b['days'] > 90:
                opportunity += 5 * w
            if not b['official']:
                opportunity += 8 * w
        opportunity = min(opportunity, 100)

        # 등급
        if difficulty <= 30 and opportunity >= 60:
            grade = "S"
        elif difficulty <= 50 and opportunity >= 40:
            grade = "A"
        elif difficulty <= 70:
            grade = "B"
        else:
            grade = "C"

        return difficulty, opportunity, grade, document_count

    def analyze(self, keyword: str) -> Tuple[int, int, str, int]:
        """SERP 분석 (캐시 우선) → (difficulty, opportunity, grade, document_count)"""
        # 캐시 확인
        cached = self.cache.get(keyword)
        if cached:
            self._cache_hit_count += 1
            return cached

        self._rate_limit()
        self._analyzed_count += 1

        url = "https://search.naver.com/search.naver"
        params = {"where": "blog", "query": keyword}

        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            result = self._parse_serp(response.text, keyword)
            self.cache.set(keyword, *result)
            return result
        except Exception as e:
            logger.debug(f"SERP 분석 실패 [{keyword}]: {e}")
            # SERP 실패해도 docs는 API에서 보충
            docs = self._fetch_document_count(keyword)
            return 50, 50, "B", docs

    def analyze_batch(self, keywords: List[str], show_progress: bool = True) -> Dict[str, Tuple[int, int, str, int]]:
        """배치 SERP 분석 (병렬 처리) → {keyword: (difficulty, opportunity, grade, document_count)}"""
        results = {}
        to_analyze = []

        # 캐시 확인
        for kw in keywords:
            cached = self.cache.get(kw)
            if cached:
                results[kw] = cached
                self._cache_hit_count += 1
            else:
                to_analyze.append(kw)

        if show_progress and results:
            print(f"   💾 SERP 캐시 HIT: {len(results)}/{len(keywords)}개")

        if not to_analyze:
            return results

        # 병렬 분석
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self._analyze_single, kw): kw for kw in to_analyze}

            done_count = 0
            for future in as_completed(futures):
                kw = futures[future]
                try:
                    result = future.result()
                    results[kw] = result
                    self.cache.set(kw, *result)
                except Exception as e:
                    # 분석 실패해도 docs는 API로 보충 (KEI 신뢰성 확보)
                    docs = self._fetch_document_count(kw)
                    results[kw] = (50, 50, "B", docs)

                done_count += 1
                if show_progress and done_count % 20 == 0:
                    print(f"   📊 SERP 분석: {done_count}/{len(to_analyze)}...")

        self._analyzed_count += len(to_analyze)
        return results

    def _analyze_single(self, keyword: str) -> Tuple[int, int, str, int]:
        """단일 키워드 분석 (스레드용) → (difficulty, opportunity, grade, document_count)"""
        time.sleep(self.delay)  # rate limit
        url = "https://search.naver.com/search.naver"
        params = {"where": "blog", "query": keyword}

        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            return self._parse_serp(response.text, keyword)
        except Exception as e:
            logger.debug(f"단일 SERP 분석 실패 [{keyword}]: {e}")
            docs = self._fetch_document_count(keyword)
            return 50, 50, "B", docs

    def get_stats(self) -> Dict:
        """분석 통계"""
        cache_stats = self.cache.get_stats()
        return {
            'analyzed': self._analyzed_count,
            'cache_hits': self._cache_hit_count,
            'cache_total': cache_stats['total'],
            'cache_valid': cache_stats['valid']
        }


def cluster_keywords_for_sampling(keywords: List[str]) -> Dict[str, List[str]]:
    """키워드 클러스터링 (샘플링용) - 유사 키워드 그룹화"""
    clusters = defaultdict(list)

    for kw in keywords:
        # 핵심어 추출 (지역 제거)
        clean = kw
        active_regions = (
            list(getattr(GYULIM_KEYWORD_PROFILE, "cheongju_regions", ()))
            + list(getattr(GYULIM_KEYWORD_PROFILE, "neighborhoods", ()))
            + list(getattr(GYULIM_KEYWORD_PROFILE, "nearby_regions", ()))
        )
        for region in active_regions:
            clean = clean.replace(region, "").strip()

        # 의도 suffix 제거
        core = clean.split()[0] if clean.split() else kw
        for suffix in ["가격", "비용", "후기", "추천", "효과", "전후", "방법", "기간"]:
            if core.endswith(suffix):
                core = core[:-len(suffix)]
                break

        if core:
            clusters[core].append(kw)

    return dict(clusters)


def analyze_with_sampling(serp: SERPAnalyzer, keywords: List[str],
                          sample_ratio: float = 0.3) -> Dict[str, Tuple[int, int, str, int]]:
    """샘플링 기반 SERP 분석 - 대표 키워드만 분석 후 점수 전파 (document_count 포함)"""
    results = {}

    # 1. 클러스터링
    clusters = cluster_keywords_for_sampling(keywords)

    # 2. 대표 키워드 선정 (각 클러스터에서 가장 짧은 것)
    representatives = []
    cluster_map = {}  # representative -> cluster members

    for core, members in clusters.items():
        if len(members) == 1:
            representatives.append(members[0])
            cluster_map[members[0]] = members
        else:
            # 가장 짧은 키워드를 대표로
            rep = min(members, key=len)
            representatives.append(rep)
            cluster_map[rep] = members

    print(f"   🎯 샘플링: {len(keywords)}개 → {len(representatives)}개 대표 분석 ({len(representatives)/len(keywords)*100:.1f}%)")

    # 3. 대표 키워드만 SERP 분석
    rep_results = serp.analyze_batch(representatives, show_progress=True)

    # 4. 점수 전파
    import random
    for rep, members in cluster_map.items():
        if rep in rep_results:
            base_diff, base_opp, base_grade, base_doc_count = rep_results[rep]

            for member in members:
                if member == rep:
                    results[member] = (base_diff, base_opp, base_grade, base_doc_count)
                else:
                    # 약간의 변동 추가 (±5)
                    var_diff = max(0, min(100, base_diff + random.randint(-5, 5)))
                    var_opp = max(0, min(100, base_opp + random.randint(-5, 5)))
                    # document_count도 ±10% 변동
                    var_doc = max(1000, int(base_doc_count * (1 + random.uniform(-0.1, 0.1))))

                    # 등급 재계산
                    if var_diff <= 30 and var_opp >= 60:
                        grade = "S"
                    elif var_diff <= 50 and var_opp >= 40:
                        grade = "A"
                    elif var_diff <= 70:
                        grade = "B"
                    else:
                        grade = "C"

                    results[member] = (var_diff, var_opp, grade, var_doc)

    return results


# ============================================================
# KEI 계산 함수
# ============================================================

def calculate_real_kei(search_volume: int, document_count: int) -> float:
    """
    실제 KEI(Keyword Effectiveness Index) 계산

    공식: KEI = 검색량² / 총문서수

    Args:
        search_volume: 월간 검색량
        document_count: 총 검색 결과 문서 수

    Returns:
        KEI 값 (소수점 2자리)
    """
    if document_count <= 0 or search_volume <= 0:
        return 0.0
    # Very small SERP counts can be parser/API artifacts. Use a light floor so
    # one-document outliers do not dominate S/A selection.
    effective_document_count = max(document_count, 20)
    return round((search_volume ** 2) / effective_document_count, 2)


def assign_kei_grade(kei: float) -> str:
    """
    KEI 기반 등급 부여

    등급 기준:
    - S급: KEI >= 500 (골든 키워드 - 즉시 공략)
    - A급: KEI >= 200 (우수 키워드 - 적극 공략)
    - B급: KEI >= 50  (보통 키워드 - 보조 활용)
    - C급: KEI < 50   (저효율 - 장기 관찰)

    Args:
        kei: KEI 값

    Returns:
        등급 문자열 (S/A/B/C)
    """
    if kei >= 500:
        return 'S'
    elif kei >= 200:
        return 'A'
    elif kei >= 50:
        return 'B'
    else:
        return 'C'


# ============================================================
# LEGION MODE 실행기
# ============================================================

class PathfinderLegion:
    """Pathfinder V3 LEGION MODE"""

    HIGH_INTENT_TERMS = (
        "가격", "비용", "예약", "상담", "추천", "후기", "잘하는곳", "잘하는",
        "보험", "실비", "자보", "자동차보험", "치료비", "입원", "초진",
        "진료시간", "야간진료", "주말진료", "일요일진료", "당일", "근처",
        "솔직", "진짜", "비교", "차이", "부작용", "전후", "효과", "기간",
    )
    STRONG_DECISION_TERMS = (
        "가격", "비용", "예약", "상담", "보험", "실비", "자보", "자동차보험",
        "치료비", "입원", "초진", "진료시간", "야간진료", "주말진료",
        "일요일진료", "당일",
    )
    HIGH_VALUE_INTENTS = {"transactional", "comparison", "validation", "red_flag"}
    LONGTAIL_REGION_TERMS = (
        "복대동", "가경동", "분평동", "봉명동", "사창동", "산남동", "수곡동",
        "모충동", "용암동", "금천동", "율량동", "사직동", "성화동", "내덕동",
        "우암동", "오창", "오송", "율량", "복대", "가경", "분평", "봉명",
        "강남", "강남역", "신논현", "논현", "논현동", "역삼", "역삼동",
        "선릉", "삼성", "삼성동", "청담", "청담동", "압구정", "신사동",
    )
    LONGTAIL_SCOUT_REGIONS = (
        "청주", "복대동", "가경동", "분평동", "봉명동", "율량동", "용암동", "오송", "오창",
    )
    CATEGORY_CANONICAL_SERVICES = {
        "다이어트": ("다이어트 한의원", "다이어트 한약", "비만 한의원", "다이어트약 처방", "비만클리닉", "식욕억제 상담"),
        "교통사고": ("교통사고 한의원", "교통사고 입원", "교통사고 후유증"),
        "흉터/여드름흉터": (
            "여드름흉터 한의원",
            "패인흉터 새살침",
            "수두흉터 한의원",
            "흉터 클리닉",
            "여드름흉터 치료",
            "패인흉터 상담",
            "새살침 상담",
            "수술흉터 치료",
            "켈로이드 상담",
        ),
        "피부/여드름": ("여드름 치료", "성인여드름 한의원", "피부질환 한의원", "아토피 한의원", "안면홍조 상담", "지루성피부염 한의원"),
        "안면비대칭": ("안면비대칭 교정", "얼굴비대칭 교정", "턱관절 한의원", "안면비대칭 상담", "얼굴비대칭 클리닉"),
        "체형교정": ("체형교정 한의원", "골반교정 한의원", "자세교정 한의원", "바디라인 클리닉", "체형교정 상담"),
        "통증/디스크": ("허리통증 한의원", "디스크 한의원", "추나요법"),
        "리프팅/탄력": ("한방리프팅", "매선리프팅", "침리프팅", "리프팅 클리닉", "피부탄력 상담", "스킨부스터 리프팅"),
        "탈모/두피": ("탈모 한의원", "탈모 한약", "두피관리 한의원"),
        "두통/어지럼": ("두통 한의원", "편두통 한의원", "어지럼증 한의원"),
        "소화/위장": ("소화불량 한의원", "담적 한의원", "역류성식도염 한의원"),
        "호흡기/알레르기": ("비염 한의원", "알레르기비염 한의원", "축농증 한의원"),
        "갱년기/여성": ("갱년기 한의원", "갱년기 한약", "안면홍조 한의원"),
        "수면/피로": ("불면증 한의원", "수면장애 한의원", "만성피로 한의원"),
        "스트레스/자율신경": ("자율신경 한의원", "화병 한의원", "공황장애 한의원"),
        "여성/산후": ("산후보약", "산후조리 한의원", "산후풍 한의원"),
        "다한증/냉증": ("다한증 한의원", "수족냉증 한의원", "냉증 한의원"),
        "수험생/집중력": ("수험생 한약", "총명탕", "집중력 한의원"),
        "면역/보약": ("보약 한의원", "공진단", "경옥고"),
    }
    STRATEGIC_SA_DENSITY_CATEGORIES = ("흉터/여드름흉터", "피부/여드름", "다이어트", "안면비대칭")
    STRATEGIC_SA_DENSITY_SUFFIXES = {
        "흉터/여드름흉터": ("비용", "상담", "예약", "후기", "추천", "치료기간"),
        "피부/여드름": ("비용", "상담", "예약", "후기", "추천", "치료기간"),
        "다이어트": ("상담", "예약", "비용", "후기", "추천", "가격"),
        "안면비대칭": ("상담", "예약", "비용", "후기", "추천", "교정"),
    }
    HIGH_VALUE_LONGTAIL_SUFFIXES = {
        "다이어트": ("비용", "상담", "예약", "추천", "주차", "야간"),
        "교통사고": ("입원", "자보", "자동차보험", "치료비", "주말", "야간"),
        "흉터/여드름흉터": ("비용", "상담", "치료기간", "예약", "추천", "후기", "회복기간", "부작용", "주의사항", "통증"),
        "피부/여드름": ("비용", "상담", "치료기간", "추천", "예약", "부작용", "주의사항"),
        "안면비대칭": ("비용", "상담", "예약", "추천", "주차", "주의사항"),
        "체형교정": ("비용", "상담", "예약", "추천", "주차", "주의사항"),
        "통증/디스크": ("비용", "상담", "예약", "추천", "주차", "야간", "치료기간"),
        "리프팅/탄력": ("비용", "상담", "예약", "추천", "주차", "주의사항"),
        "탈모/두피": ("비용", "상담", "예약", "추천", "치료기간", "원인"),
        "두통/어지럼": ("비용", "상담", "예약", "추천", "치료기간", "원인"),
        "소화/위장": ("비용", "상담", "예약", "추천", "치료기간", "원인"),
        "호흡기/알레르기": ("비용", "상담", "예약", "추천", "치료기간", "원인"),
        "갱년기/여성": ("비용", "상담", "예약", "추천", "치료기간", "주의사항"),
        "수면/피로": ("비용", "상담", "예약", "추천", "치료기간", "원인"),
        "스트레스/자율신경": ("비용", "상담", "예약", "추천", "치료기간", "원인"),
        "여성/산후": ("비용", "상담", "예약", "추천", "복용상담", "주의사항"),
        "다한증/냉증": ("비용", "상담", "예약", "추천", "치료기간", "원인"),
        "수험생/집중력": ("비용", "상담", "예약", "추천", "복용기간", "주의사항"),
        "면역/보약": ("가격", "비용", "상담", "예약", "복용기간", "체질상담"),
    }
    HIGH_VALUE_LONGTAIL_CONTEXTS = {
        "다이어트": ("직장인", "산후", "출산후", "갱년기", "웨딩", "요요", "식욕억제"),
        "교통사고": ("입원 가능한", "야간", "주말", "목통증", "허리통증", "합의전"),
        "흉터/여드름흉터": ("패인흉터", "모공흉터", "수술흉터", "수두흉터", "켈로이드", "오래된", "얼굴", "볼", "코"),
        "피부/여드름": ("성인여드름", "화농성여드름", "좁쌀여드름", "피부질환", "민감피부", "재발", "성인", "압출후"),
        "안면비대칭": ("턱관절", "얼굴형", "사진", "교정 전후", "통증", "비수술"),
        "체형교정": ("골반", "라운드숄더", "거북목", "허리통증", "산후", "비수술"),
        "통증/디스크": ("직장인", "야간", "주말", "재발", "만성", "비수술"),
        "리프팅/탄력": ("팔자주름", "이중턱", "탄력", "웨딩", "자연스러운", "통증 적은"),
        "탈모/두피": ("산후", "여성", "원형", "정수리", "스트레스", "환절기"),
        "두통/어지럼": ("직장인", "만성", "목어깨", "스트레스", "재발", "검사후"),
        "소화/위장": ("만성", "직장인", "스트레스", "식후", "재발", "검사후"),
        "호흡기/알레르기": ("환절기", "아이", "성인", "만성", "재발", "면역"),
        "갱년기/여성": ("40대", "50대", "열감", "불면", "식은땀", "체중증가"),
        "수면/피로": ("직장인", "스트레스", "갱년기", "야간", "만성", "번아웃"),
        "스트레스/자율신경": ("직장인", "번아웃", "불면", "두근거림", "만성", "재발"),
        "여성/산후": ("출산후", "모유수유", "유산후", "기력회복", "산후풍", "붓기"),
        "다한증/냉증": ("여름", "직장인", "긴장", "손발", "재발", "체질"),
        "수험생/집중력": ("고3", "중3", "수능", "시험전", "집중력", "체력"),
        "면역/보약": ("어르신", "직장인", "수험생", "환절기", "회복", "만성피로"),
    }
    HIGH_VALUE_LONGTAIL_QUESTION_PATTERNS = (
        "{region} {service} 비용 얼마",
        "{region} {service} 후기 괜찮은곳",
        "{region} {service} 부작용 있나요",
        "{region} {service} 주차 되나요",
        "{region} {service} 야간 예약",
        "{region} {service} 상담 어디",
    )
    SEARCH_JOURNEY_STAGES = ("decision", "access", "coverage", "safety")
    CATEGORY_SEARCH_JOURNEY_SUFFIXES = {
        "다이어트": {
            "decision": ("비용", "상담", "예약", "가격"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("처방 상담", "한약 비용"),
            "safety": ("부작용", "주의사항", "요요"),
        },
        "교통사고": {
            "decision": ("입원", "상담", "예약", "치료비"),
            "access": ("주말", "야간", "주차", "입원 가능"),
            "coverage": ("자보", "자동차보험 서류", "치료비", "보험"),
            "safety": ("후유증", "합의전 상담", "주의사항"),
        },
        "피부/여드름": {
            "decision": ("비용", "상담", "예약", "추천", "후기"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("치료비", "상담", "새살침 상담", "치료기간"),
            "safety": ("부작용", "주의사항", "재발", "치료기간", "통증"),
        },
        "흉터/여드름흉터": {
            "decision": ("비용", "상담", "예약", "추천", "후기"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("흉터 상담", "치료기간", "회복기간"),
            "safety": ("부작용", "주의사항", "통증", "켈로이드"),
        },
        "안면비대칭": {
            "decision": ("비용", "상담", "예약", "추천"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("치료비", "상담"),
            "safety": ("주의사항", "통증", "비수술"),
        },
        "체형교정": {
            "decision": ("비용", "상담", "예약", "추천"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("치료비", "상담"),
            "safety": ("주의사항", "통증", "비수술"),
        },
        "통증/디스크": {
            "decision": ("비용", "상담", "예약", "추천"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("치료비", "상담"),
            "safety": ("주의사항", "통증", "비수술", "치료기간"),
        },
        "리프팅/탄력": {
            "decision": ("비용", "상담", "예약", "추천"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("상담", "치료비"),
            "safety": ("부작용", "주의사항", "통증"),
        },
        "탈모/두피": {
            "decision": ("비용", "상담", "예약", "추천"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("한약 비용", "상담"),
            "safety": ("원인", "주의사항", "치료기간", "재발"),
        },
        "두통/어지럼": {
            "decision": ("비용", "상담", "예약", "추천"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("치료비", "상담"),
            "safety": ("원인", "주의사항", "치료기간", "재발"),
        },
        "소화/위장": {
            "decision": ("비용", "상담", "예약", "추천"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("치료비", "상담"),
            "safety": ("원인", "주의사항", "치료기간", "재발"),
        },
        "호흡기/알레르기": {
            "decision": ("비용", "상담", "예약", "추천"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("치료비", "상담"),
            "safety": ("원인", "주의사항", "치료기간", "재발"),
        },
        "갱년기/여성": {
            "decision": ("비용", "상담", "예약", "추천"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("한약 비용", "상담"),
            "safety": ("주의사항", "치료기간", "복용 상담"),
        },
        "수면/피로": {
            "decision": ("비용", "상담", "예약", "추천"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("한약 비용", "상담"),
            "safety": ("원인", "주의사항", "치료기간", "복용 상담"),
        },
        "스트레스/자율신경": {
            "decision": ("비용", "상담", "예약", "추천"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("한약 비용", "상담"),
            "safety": ("원인", "주의사항", "치료기간", "복용 상담"),
        },
        "여성/산후": {
            "decision": ("비용", "상담", "예약", "추천"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("한약 비용", "상담"),
            "safety": ("주의사항", "복용 상담", "치료기간"),
        },
        "다한증/냉증": {
            "decision": ("비용", "상담", "예약", "추천"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("치료비", "상담"),
            "safety": ("원인", "주의사항", "치료기간", "체질 상담"),
        },
        "수험생/집중력": {
            "decision": ("비용", "상담", "예약", "추천"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("한약 비용", "상담"),
            "safety": ("주의사항", "복용기간", "한약 상담"),
        },
        "면역/보약": {
            "decision": ("가격", "비용", "상담", "예약"),
            "access": ("주차", "야간", "주말", "진료시간"),
            "coverage": ("보약 비용", "상담"),
            "safety": ("복용기간", "주의사항", "체질 상담"),
        },
    }
    MEDICAL_AD_HIGH_RISK_TERMS = (
        "100%", "완치", "보장", "확실", "무조건", "반드시", "부작용없", "부작용 없음",
        "안전보장", "즉시효과", "단기간완성", "1회완성", "유일", "최고", "1위",
    )
    MEDICAL_AD_TESTIMONIAL_RISK_TERMS = (
        "성공사례", "치료경험담", "환자후기", "실제후기", "솔직후기", "내돈내산",
        "전후사진", "비포애프터", "before after", "beforeafter",
    )
    MEDICAL_AD_CLAIM_RISK_TERMS = (
        "전후", "효과", "효능", "개선효과", "치료효과", "근본치료", "완성", "해결",
    )
    MEDICAL_AD_COMPARISON_RISK_TERMS = (
        "비교", "vs", "보다", "타병원", "타한의원", "더 잘", "더잘", "제일",
    )
    MEDICAL_AD_SAFE_INFO_TERMS = (
        "부작용", "주의", "금기", "상담", "진료", "확인", "가능", "되나요", "있나요",
    )
    NEGATIVE_INTENT_TERMS = {
        "employment_intent": (
            "채용", "구인", "구직", "알바", "취업", "연봉", "면접", "직원모집", "간호조무사",
        ),
        "education_course_intent": (
            "학원", "강의", "교육", "자격증", "수업", "배우기", "세미나", "강사",
        ),
        "retail_product_intent": (
            "쇼핑몰", "쿠팡", "스마트스토어", "도매", "중고", "판매처", "구매처", "직구",
        ),
        "self_care_intent": (
            "셀프", "홈케어", "집에서", "혼자", "직접", "diy", "자가관리", "민간요법",
        ),
        "directory_admin_intent": (
            "전화번호부", "사업자등록", "허가", "보건소", "민원", "서류양식",
        ),
    }
    HARD_NEGATIVE_INTENT_FLAGS = {
        "non_target_region",
        "medical_general",
        "employment_intent",
        "education_course_intent",
        "retail_product_intent",
        "self_care_intent",
        "directory_admin_intent",
    }
    CONTENT_ACTION_TERMS = (
        "비용", "가격", "상담", "예약", "입원", "보험", "실비", "자보", "치료비",
        "부작용", "주의", "기간", "방법", "가능", "어디", "얼마", "있나요", "되나요",
    )
    CONTENT_PROOF_SENSITIVE_TERMS = (
        "1위", "최고", "제일", "유일", "잘하는", "잘하는곳", "추천", "후기",
        "실제후기", "솔직후기", "내돈내산", "전후", "전후사진", "비교", "vs",
    )
    LOCAL_SURFACE_TERMS = (
        "근처", "가까운", "주변", "위치", "주소", "지도", "길찾기", "전화", "전화번호",
        "영업시간", "진료시간", "주차", "예약", "상담", "입원", "야간", "주말", "일요일",
    )
    PLACE_ACTION_TERMS = (
        "전화", "전화번호", "예약", "상담", "길찾기", "위치", "주소", "주차",
        "영업시간", "진료시간", "입원", "야간", "주말", "일요일",
    )
    AVAILABILITY_IMMEDIATE_TERMS = (
        "오늘", "지금", "당일", "바로", "급하게", "즉시", "이번주", "이번 주",
    )
    AVAILABILITY_SCHEDULE_TERMS = (
        "야간", "저녁", "주말", "토요일", "일요일", "공휴일", "휴일",
        "평일", "퇴근후", "퇴근 후", "점심시간",
    )
    AVAILABILITY_HOURS_TERMS = (
        "영업시간", "진료시간", "운영시간", "오픈", "문여는", "문 여는",
        "닫는시간", "마감", "휴무", "휴진",
    )
    AVAILABILITY_BOOKING_TERMS = (
        "예약", "상담", "예약가능", "예약 가능", "당일예약", "당일 예약",
        "네이버예약", "네이버 예약", "접수",
    )
    AVAILABILITY_CAPACITY_TERMS = (
        "입원가능", "입원 가능", "주차가능", "주차 가능", "초진가능", "초진 가능",
        "진료 가능", "가능한곳", "가능한 곳",
    )
    PAYMENT_COST_TERMS = (
        "비용", "가격", "진료비", "치료비", "입원비", "상담비", "검사비",
        "한약값", "한약 비용", "얼마", "금액", "비싸", "저렴",
    )
    PAYMENT_INSURANCE_TERMS = (
        "보험", "건강보험", "실비", "실손", "실손보험", "자동차보험", "자보",
        "산재", "보험적용", "보험 적용", "적용되나요", "급여", "비급여",
        "본인부담", "본인 부담",
    )
    PAYMENT_CLAIM_TERMS = (
        "청구", "보험청구", "보험 청구", "서류", "영수증", "진단서", "소견서",
        "확인서", "제출", "환급", "보상",
    )
    AUTO_INSURANCE_TERMS = ("교통사고", "자동차사고", "자동차 사고", "자보", "자동차보험", "후유증")
    ACCESS_PARKING_TERMS = (
        "주차", "주차장", "주차가능", "주차 가능", "무료주차", "무료 주차",
        "주차비", "주차권", "발렛", "건물주차", "건물 주차",
    )
    ACCESSIBILITY_NEED_TERMS = (
        "휠체어", "장애인", "무장애", "계단없는", "계단 없는", "엘리베이터",
        "엘베", "유모차", "노약자", "보행", "거동불편",
    )
    TRANSIT_PROXIMITY_TERMS = (
        "역근처", "역 근처", "터미널", "버스", "버스정류장", "정류장",
        "대중교통", "지하철", "택시", "도보", "걸어서",
    )
    ROUTE_LOCATION_TERMS = (
        "길찾기", "위치", "주소", "가는길", "가는 길", "근처", "가까운",
        "주변", "몇층", "몇 층", "찾아가는",
    )
    OWN_BRAND_FALLBACK_TERMS = tuple(getattr(GYULIM_KEYWORD_PROFILE, "own_brand_terms", ("규림한의원", "규림", "kyurim")))
    BRAND_COMPARISON_TERMS = ("비교", "vs", "보다", "차이", "어디", "추천", "후기")
    BRAND_DEFENSE_TERMS = ("후기", "가격", "비용", "예약", "전화", "위치", "영업시간", "진료시간")
    REVIEW_INTENT_TERMS = (
        "후기", "리뷰", "평점", "별점", "방문자 리뷰", "영수증 리뷰", "만족도",
        "추천", "잘하는", "잘하는곳", "괜찮은곳", "어디가 좋아",
    )
    REPUTATION_RISK_TERMS = (
        "불친절", "비싸", "비싼", "바가지", "실망", "후회", "환불", "불만",
        "민원", "부작용", "효과없", "효과 없음", "사기", "과잉진료", "대기시간",
    )
    REVIEW_DEFENSE_TERMS = ("후기", "리뷰", "평점", "별점", "방문자", "영수증", "만족도")
    TREND_ANALYSIS_LIMIT = 150

    def __init__(self):
        self.collector = LegionCollector(delay=0.2, use_google=True)  # Multi-Source 수집
        self.serp = SERPAnalyzer(delay=0.3, max_workers=10)  # 병렬 처리 강화

        # 품질 필터 초기화
        if HAS_QUALITY_FILTER:
            self.quality_filter = KeywordQualityFilter()
            print("✅ 품질 필터 활성화")
        else:
            self.quality_filter = None

        # AI 키워드 확장기 초기화
        if HAS_AI_EXPANDER:
            self.ai_expander = AIKeywordExpander()
            self.has_ai_expander = self.ai_expander.is_available()
        else:
            self.ai_expander = None
            self.has_ai_expander = False

        # 블로그 마이너 초기화
        if HAS_BLOG_MINER:
            self.blog_miner = BlogTitleMiner(delay=1.0)
            print("✅ 블로그 마이닝 활성화")
        else:
            self.blog_miner = None

        # SERP 캐시 상태 출력
        cache_stats = self.serp.cache.get_stats()
        if cache_stats['valid'] > 0:
            print(f"💾 SERP 캐시: {cache_stats['valid']}개 유효 (총 {cache_stats['total']}개)")

        # Naver Ad API for search volume
        try:
            from scrapers.naver_ad_manager import NaverAdManager
            self.ad_manager = NaverAdManager()
            self.has_ad_api = not getattr(self.ad_manager, 'disabled', False)
            if self.has_ad_api:
                print("✅ Naver Ad API 연동 완료")
            else:
                print("⚠️ Naver Ad API 비활성화 (검색량 추정치 사용)")
        except Exception as e:
            print(f"⚠️ Naver Ad API 로드 실패: {e}")
            self.ad_manager = None
            self.has_ad_api = False

        # Naver DataLab API for trend analysis
        try:
            from scrapers.naver_datalab_manager import NaverDataLabManager
            self.datalab = NaverDataLabManager()
            self.has_datalab = bool(self.datalab.api_keys)
            if self.has_datalab:
                print("✅ Naver DataLab API 연동 완료 (트렌드 분석)")
            else:
                print("⚠️ Naver DataLab API 비활성화")
        except Exception as e:
            print(f"⚠️ Naver DataLab API 로드 실패: {e}")
            self.datalab = None
            self.has_datalab = False

        # 레거시 핵심 시드. 활성 프로필의 진료권에 맞는 경우에만 보조로 유지한다.
        legacy_base_seeds = [
            # 안면비대칭/체형교정
            "청주 안면비대칭", "청주 안면비대칭 교정", "청주 얼굴비대칭",
            "청주 체형교정", "청주 골반교정", "청주 자세교정",

            # 교통사고
            "청주 교통사고", "청주 교통사고 한의원", "청주 교통사고 입원",

            # 피부/여드름
            "청주 여드름", "청주 여드름 한의원", "청주 여드름흉터",
            "청주 새살침",

            # 다이어트
            "청주 다이어트", "청주 다이어트 한의원", "청주 다이어트 한약",

            # 교통사고/입원실 세부
            "청주 자동차사고", "청주 자동차사고 한의원", "청주 교통사고 입원치료",
            "청주 자보 한의원", "청주 교통사고 후유증",

            # 피부/흉터 세부
            "청주 여드름흉터 한의원", "청주 패인흉터", "청주 여드름자국",
            "청주 모공흉터", "청주 흉터치료",

            # 미용/웨딩 세부
            "청주 웨딩 다이어트", "청주 결혼준비 다이어트", "청주 웨딩 안면비대칭",
            "청주 한방리프팅", "청주 매선리프팅",
        ]
        profile_base_seeds = GYULIM_KEYWORD_PROFILE.build_seed_keywords(
            max_terms_per_category=10,
            max_suffixes_per_category=3,
            max_neighborhoods_per_category=5,
            include_contexts=True,
        )
        profile_base_seeds.extend(
            GYULIM_KEYWORD_PROFILE.build_exploration_seed_keywords(
                max_terms_per_category=7,
                max_suffixes_per_category=5,
                max_contexts_per_category=4,
                max_neighborhoods_per_category=5,
            )
        )
        legacy_base_seeds = [
            seed for seed in legacy_base_seeds
            if GYULIM_KEYWORD_PROFILE.is_target_region(seed, include_nearby=True)
        ]
        self.base_seeds = list(dict.fromkeys(profile_base_seeds + legacy_base_seeds))
        seed_coverage = GYULIM_KEYWORD_PROFILE.coverage_audit(self.base_seeds, min_per_category=8)
        if not seed_coverage["ok"]:
            repair_categories = list(seed_coverage["missing"]) + list(seed_coverage["undercovered"].keys())
            self.base_seeds.extend(
                GYULIM_KEYWORD_PROFILE.build_seed_keywords(
                    categories=repair_categories,
                    max_terms_per_category=8,
                    max_suffixes_per_category=2,
                    max_neighborhoods_per_category=3,
                )
            )
            self.base_seeds = list(dict.fromkeys(self.base_seeds))
            seed_coverage = GYULIM_KEYWORD_PROFILE.coverage_audit(self.base_seeds, min_per_category=8)
        print(f"🎯 {GYULIM_KEYWORD_PROFILE.display_name} 진료축 시드 커버리지: {seed_coverage['counts']}")

        # ========== 시즌 키워드 추가 (ULTRA 이식) ==========
        seasonal_seeds = SeasonalKeywordDB.get_current_seasonal_keywords()
        if seasonal_seeds:
            focused_seasonal = [
                kw for kw, category in seasonal_seeds
                if GYULIM_KEYWORD_PROFILE.normalize_category(category) in GYULIM_KEYWORD_PROFILE.focus_categories
                   or self.collector.is_focus_candidate(kw)
            ]
            print(f"📅 시즌 키워드 추가: {len(focused_seasonal)}/{len(seasonal_seeds)}개 (현재: {datetime.now().month}월)")
            self.base_seeds.extend(focused_seasonal)

        # 이전 Legion/Viral Hunter 이력을 반영해 반복 시드보다 미탐색 조합을 더 많이 시도한다.
        self.diversity_profile = self._load_diversity_profile()
        exploration_seeds = self._build_history_aware_exploration_seeds()
        if exploration_seeds:
            print(f"🧭 히스토리 기반 탐색 시드 추가: {len(exploration_seeds)}개")
            self.base_seeds.extend(exploration_seeds)

        # discovery_audit가 지목한 blind-spot 표면을 다음 런이 실제로 탐사한다
        # (이전까지 next_exploration_queue는 write-only였다).
        audit_gap_seeds = self._load_discovery_audit_gap_seeds()
        if audit_gap_seeds:
            print(f"🕳️ 디스커버리 감사 blind-spot 시드 추가: {len(audit_gap_seeds)}개")
            self.base_seeds.extend(audit_gap_seeds)
            self.base_seeds = list(dict.fromkeys(self.base_seeds))

        # 수집된 키워드
        self.collected: Dict[str, KeywordResult] = {}
        self.analyzed_keywords: Set[str] = set()
        self.candidate_stats = {
            "input_by_source": Counter(),
            "valid_by_source": Counter(),
            "accepted_by_source": Counter(),
            "sa_by_source": Counter(),
            "rejected_by_source": defaultdict(Counter),
        }
        self.keyword_source_signals: Dict[str, Set[str]] = defaultdict(set)
        self.keyword_canonical_by_norm: Dict[str, str] = {}
        self.volume_hints: Dict[str, int] = {}
        self.keyword_ad_metrics: Dict[str, Dict[str, object]] = {}
        self.inbound_query_metrics: Dict[str, Dict[str, object]] = self._load_inbound_query_metrics()
        self.owned_rank_metrics: Dict[str, Dict[str, object]] = self._load_owned_rank_metrics()
        self.community_keyword_metrics: Dict[str, Dict[str, object]] = self._load_community_keyword_metrics()
        self.conversion_keyword_metrics: Dict[str, Dict[str, object]] = self._load_conversion_keyword_metrics()
        self.profile_action_metrics: Dict[str, Dict[str, object]] = self._load_profile_action_metrics()
        self.diversity_metrics: Dict[str, object] = {}
        inbound_seeds = self._build_inbound_query_seeds()
        if inbound_seeds:
            print(f"📥 실제 유입 쿼리 시드 추가: {len(inbound_seeds)}개")
            self.base_seeds.extend(inbound_seeds)
        rank_gap_seeds = self._build_owned_rank_gap_seeds()
        if rank_gap_seeds:
            print(f"📍 자체 순위 갭 시드 추가: {len(rank_gap_seeds)}개")
            self.base_seeds.extend(rank_gap_seeds)
        community_seeds = self._build_community_signal_seeds()
        if community_seeds:
            print(f"💬 커뮤니티 수요 시드 추가: {len(community_seeds)}개")
            self.base_seeds.extend(community_seeds)
        conversion_seeds = self._build_conversion_signal_seeds()
        if conversion_seeds:
            print(f"☎️ 실제 전화 전환 시드 추가: {len(conversion_seeds)}개")
            self.base_seeds.extend(conversion_seeds)
        profile_action_seeds = self._build_profile_action_seeds()
        if profile_action_seeds:
            print(f"🧭 프로필 액션 전환 시드 추가: {len(profile_action_seeds)}개")
            self.base_seeds.extend(profile_action_seeds)

    @staticmethod
    def _normalize_keyword_for_history(keyword: str) -> str:
        return re.sub(r"\s+", "", (keyword or "").strip().lower())

    @staticmethod
    def _empty_diversity_profile() -> Dict[str, object]:
        return {
            "keyword_norms": set(),
            "category_counts": Counter(),
            "intent_counts": Counter(),
            "viral_keyword_stats": {},
        }

    def _ensure_quality_tracking(self) -> None:
        if not hasattr(self, "candidate_stats"):
            self.candidate_stats = {
                "input_by_source": Counter(),
                "valid_by_source": Counter(),
                "accepted_by_source": Counter(),
                "sa_by_source": Counter(),
                "rejected_by_source": defaultdict(Counter),
            }
        if not hasattr(self, "keyword_source_signals"):
            self.keyword_source_signals = defaultdict(set)
        if not hasattr(self, "keyword_canonical_by_norm"):
            self.keyword_canonical_by_norm = {}
        if not hasattr(self, "volume_hints"):
            self.volume_hints = {}
        if not hasattr(self, "keyword_ad_metrics"):
            self.keyword_ad_metrics = {}
        if not hasattr(self, "inbound_query_metrics"):
            self.inbound_query_metrics = {}
        if not hasattr(self, "owned_rank_metrics"):
            self.owned_rank_metrics = {}
        if not hasattr(self, "community_keyword_metrics"):
            self.community_keyword_metrics = {}
        if not hasattr(self, "conversion_keyword_metrics"):
            self.conversion_keyword_metrics = {}
        if not hasattr(self, "profile_action_metrics"):
            self.profile_action_metrics = {}
        if not hasattr(self, "diversity_metrics"):
            self.diversity_metrics = {}
        if not hasattr(self, "own_brand_terms") or not hasattr(self, "competitor_brand_terms"):
            self._load_brand_intent_terms()

    def _collector_or_default(self) -> LegionCollector:
        if not hasattr(self, "collector") or self.collector is None:
            self.collector = LegionCollector(delay=0.0, use_google=False)
        return self.collector

    @staticmethod
    def _canonical_profile_category(keyword: str, category: Optional[str] = None) -> str:
        normalized = GYULIM_KEYWORD_PROFILE.normalize_category(category or "기타")
        detected = GYULIM_KEYWORD_PROFILE.normalize_category(
            GYULIM_KEYWORD_PROFILE.detect_category(keyword or "", default=normalized)
        )
        if detected in {"", "기타"}:
            return normalized
        stale_or_generic = normalized in {"", "기타", "한의원일반"}
        legacy_skin_scar = normalized == "피부/여드름" and detected == "흉터/여드름흉터"
        if stale_or_generic or legacy_skin_scar:
            return detected
        return normalized

    @staticmethod
    def _normalize_brand_term(term: str) -> str:
        return re.sub(r"\s+", "", (term or "").strip().lower())

    def _load_brand_intent_terms(self) -> None:
        own_terms: Set[str] = set(self.OWN_BRAND_FALLBACK_TERMS)
        own_terms.update(str(term) for term in getattr(GYULIM_KEYWORD_PROFILE, "own_brand_terms", ()) if term)
        competitor_terms: Set[str] = set()

        business_profile_path = Path("config/business_profile.json")
        if business_profile_path.exists():
            try:
                with open(business_profile_path, "r", encoding="utf-8") as f:
                    profile = json.load(f)
                business = profile.get("business") or profile
                for key in ("name", "short_name", "english_name"):
                    value = str(business.get(key) or "").strip()
                    if value:
                        own_terms.add(value)
                branding = profile.get("branding") or {}
                for value in branding.values():
                    for token in re.findall(r"[0-9A-Za-z가-힣]+", str(value or "")):
                        normalized_token = token.lower()
                        if any(str(brand).lower() in normalized_token for brand in own_terms):
                            own_terms.add(token)
            except Exception:
                pass

        competitors_path = Path("config/competitors.json")
        if competitors_path.exists():
            try:
                with open(competitors_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                competitors = list(config.get("competitors", []))
                for category_config in (config.get("category_competitors") or {}).values():
                    competitors.extend(category_config.get("main_competitors", []) or [])
                for comp in competitors:
                    if isinstance(comp, dict):
                        name = str(comp.get("name") or "").strip()
                    else:
                        name = str(comp or "").strip()
                    if name:
                        competitor_terms.add(name)
            except Exception:
                pass

        sentinel_path = Path("config/sentinel_targets.json")
        if sentinel_path.exists():
            try:
                with open(sentinel_path, "r", encoding="utf-8") as f:
                    sentinel = json.load(f)
                for term in sentinel.get("brand_keywords", []) or []:
                    if term:
                        own_terms.add(str(term))
                for term in sentinel.get("competitors", []) or []:
                    if term:
                        competitor_terms.add(str(term))
            except Exception:
                pass

        own_norms = {
            term for term in (self._normalize_brand_term(t) for t in own_terms)
            if len(term) >= 2
        }
        competitor_norms = {
            term for term in (self._normalize_brand_term(t) for t in competitor_terms)
            if len(term) >= 3 and term not in own_norms
        }
        self.own_brand_terms = own_norms
        self.competitor_brand_terms = competitor_norms

    def _load_inbound_query_metrics(self, lookback_days: int = 120) -> Dict[str, Dict[str, object]]:
        """Load first-party GSC/Naver Advisor queries when the shared inbound table exists."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, "db", "marketing_data.db")
        if not os.path.exists(db_path):
            return {}

        cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        try:
            with closing(sqlite3.connect(db_path, timeout=10)) as conn:
                cursor = conn.cursor()
                exists = cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inbound_search_queries'"
                ).fetchone()
                if not exists:
                    return {}
                rows = cursor.execute(
                    """
                    SELECT query,
                           GROUP_CONCAT(DISTINCT source),
                           SUM(COALESCE(impressions, 0)),
                           SUM(COALESCE(clicks, 0)),
                           AVG(COALESCE(position, 0)),
                           MAX(measured_date)
                      FROM inbound_search_queries
                     WHERE measured_date >= ?
                       AND query IS NOT NULL
                       AND TRIM(query) <> ''
                     GROUP BY query
                    """,
                    (cutoff,),
                ).fetchall()
        except Exception:
            return {}

        metrics: Dict[str, Dict[str, object]] = {}
        for query, sources, impressions, clicks, position, latest_date in rows:
            norm = self._normalize_keyword_for_history(query)
            if not norm:
                continue
            impressions = int(impressions or 0)
            clicks = int(clicks or 0)
            metrics[norm] = {
                "query": query,
                "sources": [s for s in (sources or "").split(",") if s],
                "impressions": impressions,
                "clicks": clicks,
                "ctr": (clicks / impressions) if impressions > 0 else 0.0,
                "position": float(position or 0.0),
                "latest_date": latest_date,
            }
        return metrics

    def _build_inbound_query_seeds(self, limit: int = 80) -> List[str]:
        collector = self._collector_or_default()
        scored: List[Tuple[float, str]] = []
        for data in getattr(self, "inbound_query_metrics", {}).values():
            keyword = str(data.get("query") or "").strip()
            if not keyword or not collector._is_valid_keyword(keyword):
                continue
            category = collector._detect_category(keyword)
            if not collector.is_focus_candidate(keyword, category):
                continue
            if collector.low_business_value_reason(keyword, category):
                continue
            impressions = int(data.get("impressions", 0) or 0)
            clicks = int(data.get("clicks", 0) or 0)
            position = float(data.get("position", 0.0) or 0.0)
            score = clicks * 25.0 + impressions * 0.25
            if 0 < position <= 20:
                score += 20.0 - position
            if self._is_longtail_keyword(keyword):
                score += 12.0
            scored.append((score, keyword))

        scored.sort(key=lambda item: item[0], reverse=True)
        seen: Set[str] = set()
        seeds: List[str] = []
        for _, keyword in scored:
            norm = self._normalize_keyword_for_history(keyword)
            if norm in seen:
                continue
            seen.add(norm)
            seeds.append(keyword)
            if len(seeds) >= limit:
                break
        return seeds

    def _load_owned_rank_metrics(self, lookback_days: int = 45, target_name: str = "규림한의원") -> Dict[str, Dict[str, object]]:
        """Load latest owned mobile/desktop rankings for rank-gap prioritization."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, "db", "marketing_data.db")
        if not os.path.exists(db_path):
            return {}

        cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        try:
            with closing(sqlite3.connect(db_path, timeout=10)) as conn:
                cursor = conn.cursor()
                exists = cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='rank_history'"
                ).fetchone()
                if not exists:
                    return {}
                columns = {row[1] for row in cursor.execute("PRAGMA table_info(rank_history)").fetchall()}
                date_col = "date" if "date" in columns else None
                checked_col = "checked_at" if "checked_at" in columns else None
                if date_col:
                    date_filter = "date >= ?"
                    order_expr = "date DESC"
                elif checked_col:
                    date_filter = "DATE(checked_at) >= ?"
                    order_expr = "checked_at DESC"
                else:
                    date_filter = "1=1"
                    order_expr = "id DESC"

                rows = cursor.execute(
                    f"""
                    SELECT keyword,
                           COALESCE(rank, 0),
                           COALESCE(status, ''),
                           COALESCE(target_name, ''),
                           COALESCE(device_type, 'mobile'),
                           COALESCE(total_results, 0)
                      FROM rank_history
                     WHERE target_name LIKE ?
                       AND {date_filter}
                     ORDER BY keyword ASC, device_type ASC, {order_expr}, id DESC
                    """,
                    (f"%{target_name}%", cutoff) if date_filter != "1=1" else (f"%{target_name}%",),
                ).fetchall()
        except Exception:
            return {}

        latest_by_device: Dict[Tuple[str, str], Dict[str, object]] = {}
        for keyword, rank, status, target, device, total_results in rows:
            norm = self._normalize_keyword_for_history(keyword)
            device = (device or "mobile").lower()
            key = (norm, device)
            if not norm or key in latest_by_device:
                continue
            latest_by_device[key] = {
                "keyword": keyword,
                "rank": int(rank or 0),
                "status": status or "",
                "target_name": target or "",
                "device": device,
                "total_results": int(total_results or 0),
            }

        metrics: Dict[str, Dict[str, object]] = {}
        for (norm, device), data in latest_by_device.items():
            current = metrics.setdefault(norm, {"keyword": data["keyword"], "devices": {}})
            current["devices"][device] = data

        for norm, data in metrics.items():
            devices = data.get("devices", {}) or {}
            preferred = devices.get("mobile") or devices.get("desktop") or next(iter(devices.values()), {})
            best_found = [
                item for item in devices.values()
                if str(item.get("status", "")).lower() == "found" and int(item.get("rank", 0) or 0) > 0
            ]
            if best_found:
                preferred = min(
                    best_found,
                    key=lambda item: (
                        0 if str(item.get("device", "")).lower() == "mobile" else 1,
                        int(item.get("rank", 999) or 999),
                    ),
                )
            data["rank"] = int(preferred.get("rank", 0) or 0)
            data["status"] = str(preferred.get("status", "") or "")
            data["device"] = str(preferred.get("device", "") or "")
            data["rank_gap_signal"] = self._calculate_rank_gap_signal(data)
            data["rank_status"] = self._rank_status_label(data)

        return metrics

    def _build_owned_rank_gap_seeds(self, limit: int = 80) -> List[str]:
        collector = self._collector_or_default()
        scored: List[Tuple[float, str]] = []
        for data in getattr(self, "owned_rank_metrics", {}).values():
            keyword = str(data.get("keyword") or "").strip()
            if not keyword or not collector._is_valid_keyword(keyword):
                continue
            category = collector._detect_category(keyword)
            if not collector.is_focus_candidate(keyword, category):
                continue
            if collector.low_business_value_reason(keyword, category):
                continue
            rank_gap_signal = float(data.get("rank_gap_signal", 0.0) or 0.0)
            rank = int(data.get("rank", 0) or 0)
            if rank_gap_signal < 55 or rank <= 0:
                continue
            scored.append((rank_gap_signal + (8.0 if self._is_longtail_keyword(keyword) else 0.0), keyword))

        scored.sort(key=lambda item: item[0], reverse=True)
        seen: Set[str] = set()
        seeds: List[str] = []
        for _, keyword in scored:
            norm = self._normalize_keyword_for_history(keyword)
            if norm in seen:
                continue
            seen.add(norm)
            seeds.append(keyword)
            if len(seeds) >= limit:
                break
        return seeds

    def _load_community_keyword_metrics(self, lookback_days: int = 120) -> Dict[str, Dict[str, object]]:
        """Load Viral Hunter community evidence keyed by matched keyword."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, "db", "marketing_data.db")
        if not os.path.exists(db_path):
            return {}

        cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        try:
            with closing(sqlite3.connect(db_path, timeout=10)) as conn:
                cursor = conn.cursor()
                exists = cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='viral_targets'"
                ).fetchone()
                if not exists:
                    return {}
                columns = {row[1] for row in cursor.execute("PRAGMA table_info(viral_targets)").fetchall()}
                date_col = next(
                    (col for col in ("last_scanned_at", "updated_at", "discovered_at", "first_seen_at") if col in columns),
                    None,
                )
                where_clause = f"WHERE DATE({date_col}) >= ?" if date_col else ""
                params: Tuple[object, ...] = (cutoff,) if date_col else ()
                rows = cursor.execute(
                    f"""
                    SELECT COALESCE(platform, ''),
                           COALESCE(matched_keywords, '[]'),
                           COALESCE(matched_keyword, ''),
                           COALESCE(priority_score, 0),
                           COALESCE(conversion_fit_score, 0),
                           COALESCE(ai_infiltration_score, 0),
                           COALESCE(is_commentable, 0)
                      FROM viral_targets
                      {where_clause}
                    """,
                    params,
                ).fetchall()
        except Exception:
            return {}

        metrics: Dict[str, Dict[str, object]] = {}
        for platform, matched_keywords_raw, matched_keyword, priority, conversion_fit, infiltration, is_commentable in rows:
            keywords: List[str] = []
            if matched_keyword:
                keywords.append(str(matched_keyword))
            if matched_keywords_raw:
                try:
                    parsed = json.loads(matched_keywords_raw) if isinstance(matched_keywords_raw, str) else matched_keywords_raw
                    if isinstance(parsed, list):
                        keywords.extend(str(item) for item in parsed if item)
                except Exception:
                    pass
            for keyword in dict.fromkeys(keywords):
                norm = self._normalize_keyword_for_history(keyword)
                if not norm:
                    continue
                data = metrics.setdefault(
                    norm,
                    {
                        "keyword": keyword,
                        "mentions": 0,
                        "platforms": set(),
                        "commentable": 0,
                        "max_priority": 0.0,
                        "max_conversion_fit": 0.0,
                        "max_infiltration": 0.0,
                    },
                )
                data["mentions"] = int(data.get("mentions", 0) or 0) + 1
                if platform:
                    data["platforms"].add(str(platform))
                if int(is_commentable or 0):
                    data["commentable"] = int(data.get("commentable", 0) or 0) + 1
                data["max_priority"] = max(float(data.get("max_priority", 0.0) or 0.0), float(priority or 0.0))
                data["max_conversion_fit"] = max(float(data.get("max_conversion_fit", 0.0) or 0.0), float(conversion_fit or 0.0))
                data["max_infiltration"] = max(float(data.get("max_infiltration", 0.0) or 0.0), float(infiltration or 0.0))

        for data in metrics.values():
            data["platforms"] = sorted(data.get("platforms", set()))
            data["community_signal"] = self._calculate_community_value_signal(data)

        return metrics

    def _build_community_signal_seeds(self, limit: int = 80) -> List[str]:
        collector = self._collector_or_default()
        scored: List[Tuple[float, str]] = []
        for data in getattr(self, "community_keyword_metrics", {}).values():
            keyword = str(data.get("keyword") or "").strip()
            if not keyword or not collector._is_valid_keyword(keyword):
                continue
            category = collector._detect_category(keyword)
            if not collector.is_focus_candidate(keyword, category):
                continue
            if collector.low_business_value_reason(keyword, category):
                continue
            signal = float(data.get("community_signal", 0.0) or 0.0)
            if signal < 40.0:
                continue
            scored.append((signal + (10.0 if self._is_longtail_keyword(keyword) else 0.0), keyword))

        scored.sort(key=lambda item: item[0], reverse=True)
        seen: Set[str] = set()
        seeds: List[str] = []
        for _, keyword in scored:
            norm = self._normalize_keyword_for_history(keyword)
            if norm in seen:
                continue
            seen.add(norm)
            seeds.append(keyword)
            if len(seeds) >= limit:
                break
        return seeds

    def _load_conversion_keyword_metrics(self, lookback_days: int = 180) -> Dict[str, Dict[str, object]]:
        """Load keyword-level call tracking evidence from SmartPlace call imports."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, "db", "marketing_data.db")
        if not os.path.exists(db_path):
            return {}

        cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        try:
            with closing(sqlite3.connect(db_path, timeout=10)) as conn:
                cursor = conn.cursor()
                exists = cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='call_tracking'"
                ).fetchone()
                if not exists:
                    return {}
                rows = cursor.execute(
                    """
                    SELECT keyword,
                           COALESCE(SUM(total_calls), 0),
                           COALESCE(SUM(naver_search_calls), 0),
                           COALESCE(SUM(duration_seconds), 0),
                           COUNT(*)
                      FROM call_tracking
                     WHERE stat_date >= ?
                       AND keyword IS NOT NULL
                       AND TRIM(keyword) <> ''
                     GROUP BY keyword
                    """,
                    (cutoff,),
                ).fetchall()
        except Exception:
            return {}

        metrics: Dict[str, Dict[str, object]] = {}
        for keyword, total_calls, naver_calls, duration_seconds, rows_count in rows:
            norm = self._normalize_keyword_for_history(keyword)
            if not norm:
                continue
            data = {
                "keyword": keyword,
                "total_calls": int(total_calls or 0),
                "naver_search_calls": int(naver_calls or 0),
                "duration_seconds": int(duration_seconds or 0),
                "rows": int(rows_count or 0),
            }
            data["conversion_signal"] = self._calculate_conversion_value_signal(data)
            metrics[norm] = data
        return metrics

    def _build_conversion_signal_seeds(self, limit: int = 80) -> List[str]:
        collector = self._collector_or_default()
        scored: List[Tuple[float, str]] = []
        for data in getattr(self, "conversion_keyword_metrics", {}).values():
            keyword = str(data.get("keyword") or "").strip()
            if not keyword or not collector._is_valid_keyword(keyword):
                continue
            category = collector._detect_category(keyword)
            if not collector.is_focus_candidate(keyword, category):
                continue
            if collector.low_business_value_reason(keyword, category):
                continue
            signal = float(data.get("conversion_signal", 0.0) or 0.0)
            if signal < 35.0:
                continue
            scored.append((signal + (8.0 if self._is_longtail_keyword(keyword) else 0.0), keyword))

        scored.sort(key=lambda item: item[0], reverse=True)
        seen: Set[str] = set()
        seeds: List[str] = []
        for _, keyword in scored:
            norm = self._normalize_keyword_for_history(keyword)
            if norm in seen:
                continue
            seen.add(norm)
            seeds.append(keyword)
            if len(seeds) >= limit:
                break
        return seeds

    @staticmethod
    def _first_existing_column(columns: Set[str], candidates: Tuple[str, ...]) -> Optional[str]:
        for candidate in candidates:
            if candidate in columns:
                return candidate
        return None

    @staticmethod
    def _sum_columns_expr(columns: Set[str], candidates: Tuple[str, ...]) -> str:
        parts = [f"COALESCE({col}, 0)" for col in candidates if col in columns]
        return " + ".join(parts) if parts else "0"

    def _load_profile_action_metrics(self, lookback_days: int = 180) -> Dict[str, Dict[str, object]]:
        """Load keyword-level Google Business Profile / SmartPlace action evidence when imported."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, "db", "marketing_data.db")
        if not os.path.exists(db_path):
            return {}

        candidate_tables = (
            "profile_action_metrics",
            "business_profile_action_metrics",
            "smartplace_keyword_actions",
            "gbp_keyword_actions",
        )
        cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        metrics: Dict[str, Dict[str, object]] = {}

        try:
            with closing(sqlite3.connect(db_path, timeout=10)) as conn:
                cursor = conn.cursor()
                existing_tables = {
                    row[0]
                    for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                for table in candidate_tables:
                    if table not in existing_tables:
                        continue
                    columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}
                    keyword_col = self._first_existing_column(columns, ("keyword", "query", "search_query", "search_term"))
                    if not keyword_col:
                        continue
                    date_col = self._first_existing_column(columns, ("stat_date", "measured_date", "date", "month", "created_at"))
                    calls_expr = self._sum_columns_expr(columns, ("calls", "phone_clicks", "call_clicks", "total_calls"))
                    directions_expr = self._sum_columns_expr(columns, ("directions", "direction_clicks", "direction_requests"))
                    website_expr = self._sum_columns_expr(columns, ("website_clicks", "website_actions", "site_clicks"))
                    bookings_expr = self._sum_columns_expr(columns, ("bookings", "booking_clicks", "booking_actions", "reservations", "reservation_clicks"))
                    messages_expr = self._sum_columns_expr(columns, ("messages", "message_clicks", "talktalk_clicks", "chat_clicks"))
                    source_expr = "GROUP_CONCAT(DISTINCT source)" if "source" in columns else f"'{table}'"

                    where_clause = f"WHERE DATE({date_col}) >= ?" if date_col else "WHERE 1=1"
                    params: Tuple[object, ...] = (cutoff,) if date_col else ()
                    rows = cursor.execute(
                        f"""
                        SELECT {keyword_col},
                               SUM({calls_expr}),
                               SUM({directions_expr}),
                               SUM({website_expr}),
                               SUM({bookings_expr}),
                               SUM({messages_expr}),
                               {source_expr}
                          FROM {table}
                         {where_clause}
                           AND {keyword_col} IS NOT NULL
                           AND TRIM({keyword_col}) <> ''
                         GROUP BY {keyword_col}
                        """,
                        params,
                    ).fetchall()

                    for keyword, calls, directions, website, bookings, messages, sources in rows:
                        norm = self._normalize_keyword_for_history(keyword)
                        if not norm:
                            continue
                        current = metrics.setdefault(
                            norm,
                            {
                                "keyword": keyword,
                                "calls": 0,
                                "directions": 0,
                                "website_clicks": 0,
                                "bookings": 0,
                                "messages": 0,
                                "sources": set(),
                            },
                        )
                        current["calls"] = int(current.get("calls", 0) or 0) + int(calls or 0)
                        current["directions"] = int(current.get("directions", 0) or 0) + int(directions or 0)
                        current["website_clicks"] = int(current.get("website_clicks", 0) or 0) + int(website or 0)
                        current["bookings"] = int(current.get("bookings", 0) or 0) + int(bookings or 0)
                        current["messages"] = int(current.get("messages", 0) or 0) + int(messages or 0)
                        for source in str(sources or table).split(","):
                            if source:
                                current["sources"].add(source)
        except Exception:
            return {}

        for data in metrics.values():
            data["sources"] = sorted(data.get("sources", set()))
            data["profile_action_signal"] = self._calculate_profile_action_value_signal(data)
            data["total_actions"] = (
                int(data.get("calls", 0) or 0)
                + int(data.get("directions", 0) or 0)
                + int(data.get("website_clicks", 0) or 0)
                + int(data.get("bookings", 0) or 0)
                + int(data.get("messages", 0) or 0)
            )

        return metrics

    def _build_profile_action_seeds(self, limit: int = 80) -> List[str]:
        collector = self._collector_or_default()
        scored: List[Tuple[float, str]] = []
        for data in getattr(self, "profile_action_metrics", {}).values():
            keyword = str(data.get("keyword") or "").strip()
            if not keyword or not collector._is_valid_keyword(keyword):
                continue
            category = collector._detect_category(keyword)
            if not collector.is_focus_candidate(keyword, category):
                continue
            if collector.low_business_value_reason(keyword, category):
                continue
            signal = float(data.get("profile_action_signal", 0.0) or 0.0)
            if signal < 35.0:
                continue
            scored.append((signal + (8.0 if self._is_longtail_keyword(keyword) else 0.0), keyword))

        scored.sort(key=lambda item: item[0], reverse=True)
        seen: Set[str] = set()
        seeds: List[str] = []
        for _, keyword in scored:
            norm = self._normalize_keyword_for_history(keyword)
            if norm in seen:
                continue
            seen.add(norm)
            seeds.append(keyword)
            if len(seeds) >= limit:
                break
        return seeds

    @staticmethod
    def _keyword_terms(keyword: str) -> List[str]:
        return re.findall(r"[0-9A-Za-z가-힣]+", (keyword or "").lower())

    @staticmethod
    def _compact_keyword(keyword: str) -> str:
        return re.sub(r"\s+", "", (keyword or "").strip().lower())

    def _extract_target_region(self, keyword: str) -> str:
        collector = self._collector_or_default()
        for region in list(collector.neighborhoods) + list(collector.cheongju_regions):
            if region and region in (keyword or ""):
                return region
        return GYULIM_KEYWORD_PROFILE.primary_region

    def _is_longtail_keyword(self, keyword: str) -> bool:
        terms = self._keyword_terms(keyword)
        compact = self._compact_keyword(keyword)
        return (
            len(terms) >= 3
            or len(compact) >= 10
            or any(term in keyword for term in self.HIGH_INTENT_TERMS)
            or any(region in keyword for region in self.LONGTAIL_REGION_TERMS)
        )

    def _calculate_service_fit_profile(
        self,
        keyword: str,
        category: Optional[str] = None,
        search_intent: Optional[str] = None,
    ) -> Dict[str, object]:
        """Score whether a keyword is truly local, service-relevant, and conversion-fit."""
        collector = self._collector_or_default()
        keyword = keyword or ""
        kw_lower = keyword.lower()
        compact = self._compact_keyword(keyword)
        category = self._canonical_profile_category(keyword, category or collector._detect_category(keyword))
        search_intent = search_intent or SearchIntentClassifier.classify(keyword)
        flags: List[str] = []
        score = 0.0

        if collector._is_in_target_region(keyword):
            score += 30.0
        else:
            score -= 35.0
            flags.append("non_target_region")

        if collector._is_medical_general(keyword):
            score -= 55.0
            flags.append("medical_general")

        business_core = collector.is_business_core_keyword(keyword, category)
        focus_candidate = collector.is_focus_candidate(keyword, category)
        if business_core:
            score += 30.0
        elif focus_candidate:
            score += 22.0
        else:
            score -= 18.0
            flags.append("non_focus_category")

        if collector._has_direct_service_anchor(keyword, category):
            score += 22.0
        elif business_core:
            score += 8.0
        else:
            score -= 12.0
            flags.append("weak_service_anchor")

        if search_intent in self.HIGH_VALUE_INTENTS:
            score += 8.0
        if any(term in keyword for term in self.HIGH_INTENT_TERMS):
            score += 5.0

        low_reason = collector.low_business_value_reason(keyword, category)
        if low_reason:
            score -= 40.0
            flags.append("low_business_value")

        for flag, terms in self.NEGATIVE_INTENT_TERMS.items():
            if any(term.lower().replace(" ", "") in compact or term.lower() in kw_lower for term in terms):
                score -= 42.0
                flags.append(flag)

        score = round(max(0.0, min(100.0, score)), 2)
        hard_negative = any(flag in self.HARD_NEGATIVE_INTENT_FLAGS for flag in flags)
        return {
            "score": score,
            "flags": sorted(set(flags)),
            "hard_negative": hard_negative,
            "low_business_value_reason": low_reason,
        }

    def _calculate_local_surface_profile(
        self,
        keyword: str,
        category: Optional[str] = None,
        search_intent: Optional[str] = None,
        mobile_share: float = 0.0,
        rank_gap_signal: float = 0.0,
        conversion_signal: float = 0.0,
        service_fit_score: Optional[float] = None,
    ) -> Dict[str, object]:
        """Score whether a keyword is best handled through local/map/profile surfaces."""
        collector = self._collector_or_default()
        keyword = keyword or ""
        category = self._canonical_profile_category(keyword, category or collector._detect_category(keyword))
        search_intent = search_intent or SearchIntentClassifier.classify(keyword)
        if service_fit_score is None:
            service_fit_score = float(self._calculate_service_fit_profile(keyword, category, search_intent)["score"])

        flags: List[str] = []
        score = 0.0
        has_target_region = collector._is_in_target_region(keyword)
        has_neighborhood = any(region in keyword for region in self.LONGTAIL_REGION_TERMS)
        has_local_surface_term = any(term in keyword for term in self.LOCAL_SURFACE_TERMS)
        has_place_action_term = any(term in keyword for term in self.PLACE_ACTION_TERMS)

        if has_target_region:
            score += 24.0
            flags.append("target_region")
        if has_neighborhood:
            score += 14.0
            flags.append("neighborhood_modifier")
        if has_local_surface_term:
            score += 18.0
            flags.append("local_surface_intent")
        if has_place_action_term:
            score += 18.0
            flags.append("place_action_intent")
        if search_intent in {"navigational", "transactional"}:
            score += 8.0
        if mobile_share >= 0.75:
            score += 12.0
            flags.append("mobile_heavy")
        elif mobile_share >= 0.65:
            score += 8.0
            flags.append("mobile_local")
        if rank_gap_signal >= 55.0:
            score += min(14.0, rank_gap_signal / 8.0)
            flags.append("owned_rank_gap_surface")
        if conversion_signal >= 35.0:
            score += min(16.0, conversion_signal / 5.0)
            flags.append("call_conversion_surface")
        if float(service_fit_score or 0.0) >= 80.0:
            score += 6.0
        elif float(service_fit_score or 0.0) < 60.0:
            score -= 18.0
            flags.append("weak_service_fit")

        score = round(max(0.0, min(100.0, score)), 2)
        if score >= 70.0 and has_place_action_term:
            preferred_surface = "profile_action"
        elif score >= 58.0:
            preferred_surface = "local_pack"
        elif score >= 40.0:
            preferred_surface = "hybrid_local_content"
        else:
            preferred_surface = "web_content"

        return {
            "score": score,
            "preferred_search_surface": preferred_surface,
            "flags": sorted(set(flags)),
        }

    def _calculate_availability_intent_profile(
        self,
        keyword: str,
        category: Optional[str] = None,
        search_intent: Optional[str] = None,
        local_surface_score: float = 0.0,
        profile_action_signal: float = 0.0,
        service_fit_score: Optional[float] = None,
    ) -> Dict[str, object]:
        """Score time-sensitive availability queries such as same-day, hours, weekend, and booking intent."""
        collector = self._collector_or_default()
        keyword = keyword or ""
        category = self._canonical_profile_category(keyword, category or collector._detect_category(keyword))
        search_intent = search_intent or SearchIntentClassifier.classify(keyword)
        if service_fit_score is None:
            service_fit_score = float(self._calculate_service_fit_profile(keyword, category, search_intent)["score"])

        compact = self._compact_keyword(keyword)
        flags: List[str] = []

        def matched(terms: Tuple[str, ...]) -> List[str]:
            return [term for term in terms if term.lower().replace(" ", "") in compact]

        immediate_terms = matched(self.AVAILABILITY_IMMEDIATE_TERMS)
        schedule_terms = matched(self.AVAILABILITY_SCHEDULE_TERMS)
        hours_terms = matched(self.AVAILABILITY_HOURS_TERMS)
        booking_terms = matched(self.AVAILABILITY_BOOKING_TERMS)
        capacity_terms = matched(self.AVAILABILITY_CAPACITY_TERMS)

        if not any((immediate_terms, schedule_terms, hours_terms, booking_terms, capacity_terms)):
            return {
                "availability_intent_score": 0.0,
                "availability_intent_type": "none",
                "flags": [],
            }

        score = 0.0
        if immediate_terms:
            score += 28.0
            flags.append("same_day_or_now")
        if schedule_terms:
            score += 22.0
            flags.append("schedule_sensitive")
        if hours_terms:
            score += 30.0
            flags.append("hours_check")
        if booking_terms:
            score += 20.0
            flags.append("booking_or_consult")
        if capacity_terms:
            score += 18.0
            flags.append("capacity_check")
        if schedule_terms and capacity_terms:
            score += 14.0
            flags.append("schedule_capacity_match")
        if hours_terms and collector._is_in_target_region(keyword):
            score += 10.0
            flags.append("local_hours_check")
        if hours_terms and local_surface_score >= 55.0:
            score += 8.0
        if collector._is_in_target_region(keyword):
            score += 8.0
            flags.append("target_region_availability")
        if any(region in keyword for region in self.LONGTAIL_REGION_TERMS):
            score += 5.0
            flags.append("neighborhood_availability")
        if search_intent in {"transactional", "navigational"}:
            score += 6.0
        if local_surface_score >= 70.0:
            score += 8.0
            flags.append("local_surface_availability")
        elif local_surface_score >= 55.0:
            score += 5.0
        if profile_action_signal >= 60.0:
            score += 8.0
            flags.append("profile_action_backed")
        elif profile_action_signal >= 35.0:
            score += 5.0
        if float(service_fit_score or 0.0) >= 80.0:
            score += 5.0
        elif float(service_fit_score or 0.0) < 60.0:
            score -= 15.0
            flags.append("weak_service_fit")

        if immediate_terms and booking_terms:
            intent_type = "same_day_booking"
        elif schedule_terms and booking_terms:
            intent_type = "after_hours_or_weekend_booking"
        elif capacity_terms:
            intent_type = "capacity_availability"
        elif hours_terms:
            intent_type = "hours_check"
        elif booking_terms:
            intent_type = "booking_availability"
        elif schedule_terms:
            intent_type = "schedule_availability"
        else:
            intent_type = "availability_discovery"

        score = round(max(0.0, min(100.0, score)), 2)
        if score >= 70.0:
            flags.append("availability_high_intent")
        elif score >= 55.0:
            flags.append("availability_review")

        return {
            "availability_intent_score": score,
            "availability_intent_type": intent_type,
            "flags": sorted(set(flags)),
        }

    def _calculate_payment_coverage_profile(
        self,
        keyword: str,
        category: Optional[str] = None,
        search_intent: Optional[str] = None,
        service_fit_score: Optional[float] = None,
        medical_ad_risk_score: float = 0.0,
        local_surface_score: float = 0.0,
        profile_action_signal: float = 0.0,
    ) -> Dict[str, object]:
        """Score cost, insurance, reimbursement, and payment-coverage decision intent."""
        collector = self._collector_or_default()
        keyword = keyword or ""
        category = self._canonical_profile_category(keyword, category or collector._detect_category(keyword))
        search_intent = search_intent or SearchIntentClassifier.classify(keyword)
        if service_fit_score is None:
            service_fit_score = float(self._calculate_service_fit_profile(keyword, category, search_intent)["score"])

        compact = self._compact_keyword(keyword)
        flags: List[str] = []

        def matched(terms: Tuple[str, ...]) -> List[str]:
            return [term for term in terms if term.lower().replace(" ", "") in compact]

        cost_terms = matched(self.PAYMENT_COST_TERMS)
        insurance_terms = matched(self.PAYMENT_INSURANCE_TERMS)
        claim_terms = matched(self.PAYMENT_CLAIM_TERMS)
        auto_terms = matched(self.AUTO_INSURANCE_TERMS)
        chuna_insurance = "추나" in keyword and bool(insurance_terms)

        if not any((cost_terms, insurance_terms, claim_terms)):
            return {
                "payment_coverage_score": 0.0,
                "payment_coverage_type": "none",
                "flags": [],
            }

        score = 0.0
        if cost_terms:
            score += 28.0
            flags.append("cost_transparency")
        if insurance_terms:
            score += 30.0
            flags.append("insurance_coverage")
        if claim_terms:
            score += 18.0
            flags.append("claim_document_intent")
        if insurance_terms and claim_terms:
            score += 14.0
            flags.append("insurance_claim_context")
        if auto_terms and insurance_terms:
            score += 16.0
            flags.append("auto_insurance_context")
        if chuna_insurance:
            score += 12.0
            flags.append("chuna_insurance_context")
        if any(term in compact for term in ("비급여", "급여", "본인부담", "본인부담률")):
            score += 10.0
            flags.append("coverage_scope_check")
        if collector._is_in_target_region(keyword):
            score += 8.0
            flags.append("target_region_payment")
        if any(region in keyword for region in self.LONGTAIL_REGION_TERMS):
            score += 5.0
            flags.append("neighborhood_payment")
        if collector._has_direct_service_anchor(keyword, category):
            score += 8.0
            flags.append("service_payment_anchor")
        elif collector.is_business_core_keyword(keyword, category):
            score += 5.0
        if search_intent in {"transactional", "commercial", "comparison"}:
            score += 6.0
        if local_surface_score >= 70.0:
            score += 5.0
        if profile_action_signal >= 60.0:
            score += 6.0
            flags.append("profile_action_backed")
        elif profile_action_signal >= 35.0:
            score += 3.0
        if float(service_fit_score or 0.0) < 60.0:
            score -= 18.0
            flags.append("weak_service_fit")
        if medical_ad_risk_score >= 70.0:
            score -= 12.0
            flags.append("medical_ad_high_risk_payment")

        if auto_terms and insurance_terms:
            payment_type = "auto_insurance"
        elif cost_terms and insurance_terms:
            payment_type = "cost_and_insurance"
        elif claim_terms:
            payment_type = "claim_documents"
        elif insurance_terms:
            payment_type = "insurance_coverage"
        elif any(term in compact for term in ("비급여", "급여", "본인부담", "본인부담률")):
            payment_type = "coverage_scope"
        else:
            payment_type = "cost_transparency"

        score = round(max(0.0, min(100.0, score)), 2)
        if score >= 70.0:
            flags.append("payment_high_intent")
        elif score >= 55.0:
            flags.append("payment_review")

        return {
            "payment_coverage_score": score,
            "payment_coverage_type": payment_type,
            "flags": sorted(set(flags)),
        }

    def _calculate_access_convenience_profile(
        self,
        keyword: str,
        category: Optional[str] = None,
        search_intent: Optional[str] = None,
        service_fit_score: Optional[float] = None,
        local_surface_score: float = 0.0,
        profile_action_signal: float = 0.0,
        availability_intent_score: float = 0.0,
    ) -> Dict[str, object]:
        """Score visit-readiness terms such as parking, wheelchair access, transit, and route finding."""
        collector = self._collector_or_default()
        keyword = keyword or ""
        category = self._canonical_profile_category(keyword, category or collector._detect_category(keyword))
        search_intent = search_intent or SearchIntentClassifier.classify(keyword)
        if service_fit_score is None:
            service_fit_score = float(self._calculate_service_fit_profile(keyword, category, search_intent)["score"])

        compact = self._compact_keyword(keyword)
        flags: List[str] = []

        def matched(terms: Tuple[str, ...]) -> List[str]:
            return [term for term in terms if term.lower().replace(" ", "") in compact]

        parking_terms = matched(self.ACCESS_PARKING_TERMS)
        accessibility_terms = matched(self.ACCESSIBILITY_NEED_TERMS)
        transit_terms = matched(self.TRANSIT_PROXIMITY_TERMS)
        route_terms = matched(self.ROUTE_LOCATION_TERMS)

        if not any((parking_terms, accessibility_terms, transit_terms, route_terms)):
            return {
                "access_convenience_score": 0.0,
                "access_convenience_type": "none",
                "flags": [],
            }

        score = 0.0
        if parking_terms:
            score += 30.0
            flags.append("parking_intent")
        if accessibility_terms:
            score += 32.0
            flags.append("accessibility_need")
        if transit_terms:
            score += 20.0
            flags.append("transit_proximity")
        if route_terms:
            score += 18.0
            flags.append("route_or_location_check")
        if parking_terms and route_terms:
            score += 8.0
            flags.append("parking_route_match")
        if accessibility_terms and route_terms:
            score += 8.0
            flags.append("accessible_route_match")
        if collector._is_in_target_region(keyword):
            score += 8.0
            flags.append("target_region_access")
        if any(region in keyword for region in self.LONGTAIL_REGION_TERMS):
            score += 5.0
            flags.append("neighborhood_access")
        if collector._has_direct_service_anchor(keyword, category):
            score += 7.0
            flags.append("service_access_anchor")
        elif collector.is_business_core_keyword(keyword, category):
            score += 4.0
        if search_intent in {"transactional", "navigational"}:
            score += 5.0
        if local_surface_score >= 70.0:
            score += 8.0
            flags.append("local_surface_backed")
        elif local_surface_score >= 55.0:
            score += 5.0
        if profile_action_signal >= 60.0:
            score += 6.0
            flags.append("profile_action_backed")
        elif profile_action_signal >= 35.0:
            score += 3.0
        if availability_intent_score >= 70.0:
            score += 5.0
            flags.append("availability_backed")
        if float(service_fit_score or 0.0) < 60.0:
            score -= 16.0
            flags.append("weak_service_fit")

        if accessibility_terms:
            access_type = "accessibility_need"
        elif parking_terms:
            access_type = "parking_access"
        elif transit_terms:
            access_type = "transit_proximity"
        elif route_terms:
            access_type = "route_finding"
        else:
            access_type = "visit_logistics"

        score = round(max(0.0, min(100.0, score)), 2)
        if score >= 70.0:
            flags.append("access_high_intent")
        elif score >= 55.0:
            flags.append("access_review")

        return {
            "access_convenience_score": score,
            "access_convenience_type": access_type,
            "flags": sorted(set(flags)),
        }

    def _calculate_brand_intent_profile(
        self,
        keyword: str,
        search_intent: Optional[str] = None,
    ) -> Dict[str, object]:
        """Separate own-brand defense and competitor-brand queries from generic acquisition terms."""
        self._ensure_quality_tracking()
        keyword = keyword or ""
        compact = self._normalize_brand_term(keyword)
        search_intent = search_intent or SearchIntentClassifier.classify(keyword)
        flags: List[str] = []

        def matches(terms: Set[str]) -> List[str]:
            found: List[str] = []
            for term in sorted(terms, key=len, reverse=True):
                if term and term in compact:
                    found.append(term)
            return found

        own_matches = matches(set(getattr(self, "own_brand_terms", set()) or set()))
        competitor_matches = matches(set(getattr(self, "competitor_brand_terms", set()) or set()))
        comparison_intent = any(term.lower() in keyword.lower() for term in self.BRAND_COMPARISON_TERMS)
        defense_intent = any(term.lower() in keyword.lower() for term in self.BRAND_DEFENSE_TERMS)

        brand_type = "generic"
        signal_score = 0.0
        competitor_risk = 0.0

        if own_matches and competitor_matches:
            brand_type = "own_vs_competitor"
            signal_score = 74.0
            competitor_risk = 62.0
            flags.extend(["own_brand_defense", "competitor_brand_review", "brand_comparison"])
        elif competitor_matches:
            if comparison_intent or search_intent in {"comparison", "commercial", "validation"}:
                brand_type = "competitor_comparison"
                signal_score = 58.0
                competitor_risk = 72.0
                flags.extend(["competitor_brand_review", "brand_comparison"])
            else:
                brand_type = "competitor_brand"
                signal_score = 44.0
                competitor_risk = 56.0
                flags.append("competitor_brand_review")
        elif own_matches:
            brand_type = "own_brand_defense"
            signal_score = 92.0 if defense_intent else 80.0
            flags.append("own_brand_defense")

        if competitor_risk >= 70.0:
            flags.append("competitor_brand_high_risk")
        elif competitor_risk >= 50.0:
            flags.append("competitor_brand_policy_review")

        return {
            "brand_intent_type": brand_type,
            "brand_signal_score": signal_score,
            "brand_mentions": sorted(set(own_matches + competitor_matches)),
            "competitor_brand_risk_score": competitor_risk,
            "flags": sorted(set(flags)),
        }

    def _calculate_review_reputation_profile(
        self,
        keyword: str,
        search_intent: Optional[str] = None,
        brand_intent_type: str = "generic",
        community_signal: float = 0.0,
        local_surface_score: float = 0.0,
        medical_ad_risk_score: float = 0.0,
    ) -> Dict[str, object]:
        """Score review-surface value separately from reputation-response risk."""
        collector = self._collector_or_default()
        keyword = keyword or ""
        keyword_lower = keyword.lower()
        search_intent = search_intent or SearchIntentClassifier.classify(keyword)
        brand_intent_type = brand_intent_type or "generic"
        flags: List[str] = []

        matched_review_terms = [
            term for term in self.REVIEW_INTENT_TERMS
            if term.lower() in keyword_lower
        ]
        matched_direct_review_terms = [
            term for term in self.REVIEW_DEFENSE_TERMS
            if term.lower() in keyword_lower
        ]
        matched_risk_terms = [
            term for term in self.REPUTATION_RISK_TERMS
            if term.lower() in keyword_lower
        ]
        has_review_intent = bool(matched_review_terms)
        has_direct_review_surface = bool(matched_direct_review_terms)
        hard_risk_terms = [term for term in matched_risk_terms if term not in {"부작용"}]
        has_reputation_risk = bool(matched_risk_terms) and (has_review_intent or bool(hard_risk_terms))

        if not has_review_intent and not has_reputation_risk:
            return {
                "review_surface_score": 0.0,
                "reputation_risk_score": 0.0,
                "review_intent_type": "none",
                "flags": [],
            }

        category = collector._detect_category(keyword)
        review_score = 0.0
        reputation_risk = 0.0
        review_type = "generic_review_discovery" if has_review_intent else "reputation_issue"

        if has_direct_review_surface:
            review_score += 42.0
            flags.append("review_intent")
        elif has_review_intent:
            review_score += 24.0
            review_type = "recommendation_discovery"
            flags.append("recommendation_discovery")
        if any(term in keyword for term in ("추천", "잘하는", "잘하는곳", "괜찮은곳", "어디가 좋아")):
            review_score += 12.0
            flags.append("recommendation_intent")
        if has_direct_review_surface:
            review_score += 6.0
            flags.append("rating_or_review_surface")
        if collector._is_in_target_region(keyword):
            review_score += 10.0
            flags.append("target_region_review")
        if any(region in keyword for region in self.LONGTAIL_REGION_TERMS):
            review_score += 8.0
            flags.append("neighborhood_review")
        if collector._has_direct_service_anchor(keyword, category):
            review_score += 8.0
            flags.append("service_review_anchor")
        if search_intent in {"validation", "commercial"}:
            review_score += 6.0

        if brand_intent_type == "own_brand_defense":
            review_score += 24.0
            review_type = "own_review_defense"
            flags.append("review_defense")
        elif brand_intent_type in {"competitor_brand", "competitor_comparison", "own_vs_competitor"}:
            review_score += 18.0
            reputation_risk += 28.0
            review_type = "competitor_review_monitor"
            flags.append("competitor_review_monitor")

        if has_reputation_risk:
            reputation_risk += 42.0 + min(28.0, max(0, len(matched_risk_terms) - 1) * 12.0)
            review_score += 10.0
            if review_type == "generic_review_discovery":
                review_type = "reputation_issue"
            flags.append("reputation_risk_query")

        if community_signal >= 40.0:
            review_score += min(16.0, float(community_signal) / 6.0)
            flags.append("community_review_signal")
        if local_surface_score >= 70.0:
            review_score += 8.0
            flags.append("local_review_surface")
        elif local_surface_score >= 55.0:
            review_score += 5.0
        if medical_ad_risk_score >= 40.0 and has_review_intent:
            reputation_risk += 16.0
            flags.append("medical_review_claim_sensitive")

        review_score = round(max(0.0, min(100.0, review_score)), 2)
        reputation_risk = round(max(0.0, min(100.0, reputation_risk)), 2)

        if review_score >= 70.0:
            flags.append("review_surface_high_value")
        elif review_score >= 55.0:
            flags.append("review_surface_review")
        if reputation_risk >= 70.0:
            flags.append("reputation_high_risk")
        elif reputation_risk >= 40.0:
            flags.append("reputation_review_required")

        return {
            "review_surface_score": review_score,
            "reputation_risk_score": reputation_risk,
            "review_intent_type": review_type,
            "flags": sorted(set(flags)),
        }

    def _recommend_content_type(
        self,
        keyword: str,
        category: Optional[str] = None,
        search_intent: Optional[str] = None,
    ) -> str:
        keyword = keyword or ""
        search_intent = search_intent or SearchIntentClassifier.classify(keyword)
        if search_intent == "red_flag" or any(term in keyword for term in ("부작용", "주의", "금기")):
            return "faq_safety"
        if any(term in keyword for term in ("입원", "야간", "주말", "일요일", "위치", "주소", "주차")):
            return "access_landing"
        if any(term in keyword for term in ("비용", "가격", "얼마", "치료비", "보험", "실비", "자보")):
            return "service_landing"
        if search_intent == "transactional":
            return "service_landing"
        if search_intent in {"validation", "commercial"} or any(term in keyword for term in ("후기", "추천", "잘하는")):
            return "proof_safe_guide"
        if search_intent == "comparison":
            return "comparison_guide"
        if search_intent == "informational":
            return "educational_article"
        return "topic_hub"

    def _calculate_content_actionability_profile(
        self,
        keyword: str,
        category: Optional[str] = None,
        search_intent: Optional[str] = None,
        medical_ad_risk_score: Optional[float] = None,
        service_fit_score: Optional[float] = None,
    ) -> Dict[str, object]:
        """Score whether a keyword can become a distinct, helpful page without thin/unsafe content."""
        collector = self._collector_or_default()
        keyword = keyword or ""
        category = self._canonical_profile_category(keyword, category or collector._detect_category(keyword))
        search_intent = search_intent or SearchIntentClassifier.classify(keyword)
        if medical_ad_risk_score is None:
            medical_ad_risk_score = float(self._calculate_medical_ad_risk_profile(keyword, search_intent)["score"])
        if service_fit_score is None:
            service_fit_score = float(self._calculate_service_fit_profile(keyword, category, search_intent)["score"])

        recommended_type = self._recommend_content_type(keyword, category, search_intent)
        flags: List[str] = []
        score = float(service_fit_score) * 0.55

        business_core = collector.is_business_core_keyword(keyword, category)
        has_direct_anchor = collector._has_direct_service_anchor(keyword, category)
        if has_direct_anchor:
            score += 20.0
        elif business_core:
            score += 10.0
        else:
            score -= 12.0
            flags.append("needs_service_anchor")

        if business_core:
            score += 10.0
        if search_intent in self.HIGH_VALUE_INTENTS:
            score += 8.0
        if any(term in keyword for term in self.CONTENT_ACTION_TERMS):
            score += 10.0
        if collector._is_in_target_region(keyword):
            score += 4.0

        if recommended_type in {"service_landing", "access_landing"} and has_direct_anchor:
            score += 5.0
        if recommended_type == "faq_safety":
            score += 8.0
            flags.append("safe_faq_candidate")

        proof_terms = [term for term in self.CONTENT_PROOF_SENSITIVE_TERMS if term.lower() in keyword.lower()]
        if proof_terms:
            score -= 24.0
            flags.append("proof_sensitive_claim")

        if medical_ad_risk_score >= 70.0:
            score -= 42.0
            flags.append("medical_ad_high_risk_content")
        elif medical_ad_risk_score >= 40.0:
            score -= 15.0
            flags.append("medical_ad_review_content")

        score = round(max(0.0, min(100.0, score)), 2)
        if score < 45.0:
            flags.append("content_low_actionability")
        elif score < 60.0:
            flags.append("content_review_required")

        return {
            "score": score,
            "recommended_content_type": recommended_type,
            "flags": sorted(set(flags)),
        }

    def _calculate_keyword_value_profile(
        self,
        keyword: str,
        category: Optional[str] = None,
        search_intent: Optional[str] = None,
        search_volume: int = 0,
        difficulty: int = 50,
        opportunity: int = 50,
        document_count: int = 0,
        source_signal_count: int = 1,
        has_real_volume: Optional[bool] = None,
        business_core: Optional[bool] = None,
        medical_ad_risk_score: Optional[float] = None,
        content_actionability_score: Optional[float] = None,
        local_surface_score: Optional[float] = None,
        brand_intent_type: Optional[str] = None,
        competitor_brand_risk_score: Optional[float] = None,
        review_surface_score: Optional[float] = None,
        reputation_risk_score: Optional[float] = None,
        review_intent_type: Optional[str] = None,
        profile_action_signal: Optional[float] = None,
        availability_intent_score: Optional[float] = None,
        availability_intent_type: Optional[str] = None,
        payment_coverage_score: Optional[float] = None,
        payment_coverage_type: Optional[str] = None,
        access_convenience_score: Optional[float] = None,
        access_convenience_type: Optional[str] = None,
    ) -> Dict[str, object]:
        """검색량이 작은 롱테일도 사업 전환 가치가 있으면 보존하기 위한 별도 프로필."""
        collector = self._collector_or_default()
        keyword = keyword or ""
        category = self._canonical_profile_category(keyword, category or collector._detect_category(keyword))
        search_intent = search_intent or SearchIntentClassifier.classify(keyword)
        if has_real_volume is None:
            has_real_volume = search_volume > 0
        if business_core is None:
            business_core = collector.is_business_core_keyword(keyword, category)

        terms = self._keyword_terms(keyword)
        compact = self._compact_keyword(keyword)
        matched_intents = [term for term in self.HIGH_INTENT_TERMS if term in keyword]
        strong_decision_terms = [term for term in self.STRONG_DECISION_TERMS if term in keyword]
        has_region = collector._is_in_target_region(keyword)
        has_neighborhood = any(region in keyword for region in self.LONGTAIL_REGION_TERMS)
        has_direct_anchor = collector._has_direct_service_anchor(keyword, category)
        category_terms = collector.category_patterns.get(category, ())
        category_term_count = sum(1 for term in category_terms if term in keyword)
        low_reason = collector.low_business_value_reason(keyword, category)
        service_fit_profile = self._calculate_service_fit_profile(keyword, category, search_intent)
        service_fit_score = float(service_fit_profile["score"])
        negative_intent_flags = list(service_fit_profile["flags"])
        if content_actionability_score is None:
            content_profile = self._calculate_content_actionability_profile(
                keyword,
                category,
                search_intent,
                medical_ad_risk_score=medical_ad_risk_score,
                service_fit_score=service_fit_score,
            )
            content_actionability_score = float(content_profile["score"])
        if local_surface_score is None:
            local_surface_profile = self._calculate_local_surface_profile(
                keyword,
                category,
                search_intent,
                service_fit_score=service_fit_score,
            )
            local_surface_score = float(local_surface_profile["score"])
        if brand_intent_type is None or competitor_brand_risk_score is None:
            brand_profile = self._calculate_brand_intent_profile(keyword, search_intent)
            brand_intent_type = str(brand_profile["brand_intent_type"])
            competitor_brand_risk_score = float(brand_profile["competitor_brand_risk_score"])
        if review_surface_score is None or reputation_risk_score is None or review_intent_type is None:
            review_profile = self._calculate_review_reputation_profile(
                keyword,
                search_intent,
                brand_intent_type=brand_intent_type,
                local_surface_score=float(local_surface_score or 0.0),
                medical_ad_risk_score=float(medical_ad_risk_score or 0.0),
            )
            review_surface_score = float(review_profile["review_surface_score"])
            reputation_risk_score = float(review_profile["reputation_risk_score"])
            review_intent_type = str(review_profile["review_intent_type"])
        if profile_action_signal is None:
            profile_action_signal = 0.0
        if availability_intent_score is None or availability_intent_type is None:
            availability_profile = self._calculate_availability_intent_profile(
                keyword,
                category,
                search_intent,
                local_surface_score=float(local_surface_score or 0.0),
                profile_action_signal=float(profile_action_signal or 0.0),
                service_fit_score=service_fit_score,
            )
            availability_intent_score = float(availability_profile["availability_intent_score"])
            availability_intent_type = str(availability_profile["availability_intent_type"])
        if payment_coverage_score is None or payment_coverage_type is None:
            payment_profile = self._calculate_payment_coverage_profile(
                keyword,
                category,
                search_intent,
                service_fit_score=service_fit_score,
                medical_ad_risk_score=float(medical_ad_risk_score or 0.0),
                local_surface_score=float(local_surface_score or 0.0),
                profile_action_signal=float(profile_action_signal or 0.0),
            )
            payment_coverage_score = float(payment_profile["payment_coverage_score"])
            payment_coverage_type = str(payment_profile["payment_coverage_type"])
        if access_convenience_score is None or access_convenience_type is None:
            access_profile = self._calculate_access_convenience_profile(
                keyword,
                category,
                search_intent,
                service_fit_score=service_fit_score,
                local_surface_score=float(local_surface_score or 0.0),
                profile_action_signal=float(profile_action_signal or 0.0),
                availability_intent_score=float(availability_intent_score or 0.0),
            )
            access_convenience_score = float(access_profile["access_convenience_score"])
            access_convenience_type = str(access_profile["access_convenience_type"])

        is_longtail = self._is_longtail_keyword(keyword)
        intent_is_valuable = search_intent in self.HIGH_VALUE_INTENTS or bool(matched_intents)

        business_value_score = 0.0
        if has_region:
            business_value_score += 20.0
        if has_neighborhood:
            business_value_score += 7.0
        if business_core:
            business_value_score += 25.0
        elif collector.is_focus_candidate(keyword, category):
            business_value_score += 15.0
        if has_direct_anchor:
            business_value_score += 18.0
        elif category_term_count:
            business_value_score += 10.0
        if intent_is_valuable:
            business_value_score += 17.0
        if document_count > 0:
            business_value_score += 5.0
        if low_reason:
            business_value_score -= 45.0
        if collector._is_medical_general(keyword):
            business_value_score -= 60.0
        if service_fit_score >= 80.0:
            business_value_score += 8.0
        elif service_fit_score < 60.0:
            business_value_score -= min(35.0, (60.0 - service_fit_score) * 0.7)
        if content_actionability_score >= 80.0:
            business_value_score += 6.0
        elif content_actionability_score < 55.0:
            business_value_score -= min(28.0, (55.0 - content_actionability_score) * 0.65)
        if local_surface_score >= 70.0:
            business_value_score += 8.0
        elif local_surface_score >= 55.0:
            business_value_score += 4.0
        if brand_intent_type == "own_brand_defense":
            business_value_score += 8.0
        elif brand_intent_type in {"competitor_brand", "competitor_comparison", "own_vs_competitor"}:
            business_value_score -= 20.0
            if competitor_brand_risk_score >= 70.0:
                business_value_score -= 18.0
        if review_surface_score >= 70.0:
            business_value_score += 8.0
        elif review_surface_score >= 55.0:
            business_value_score += 4.0
        if reputation_risk_score >= 70.0:
            business_value_score -= 18.0
        elif reputation_risk_score >= 40.0:
            business_value_score -= 8.0
        if profile_action_signal >= 60.0:
            business_value_score += 10.0
        elif profile_action_signal >= 35.0:
            business_value_score += 5.0
        if availability_intent_score >= 70.0:
            business_value_score += 9.0
        elif availability_intent_score >= 55.0:
            business_value_score += 5.0
        if payment_coverage_score >= 70.0:
            business_value_score += 10.0
        elif payment_coverage_score >= 55.0:
            business_value_score += 5.0
        if access_convenience_score >= 70.0:
            business_value_score += 8.0
        elif access_convenience_score >= 55.0:
            business_value_score += 4.0
        business_value_score = round(max(0.0, min(100.0, business_value_score)), 2)

        longtail_score = 0.0
        if is_longtail:
            longtail_score += 18.0
        if len(terms) >= 3:
            longtail_score += 8.0
        if len(terms) >= 4:
            longtail_score += 5.0
        if len(compact) >= 10:
            longtail_score += 5.0
        if len(compact) >= 14:
            longtail_score += 4.0
        if has_neighborhood:
            longtail_score += 12.0
        elif has_region:
            longtail_score += 7.0
        if category_term_count:
            longtail_score += min(14.0, 8.0 + category_term_count * 1.5)
        if has_direct_anchor:
            longtail_score += 12.0
        if matched_intents:
            longtail_score += min(22.0, 10.0 + len(matched_intents) * 4.0)
        if search_intent in self.HIGH_VALUE_INTENTS:
            longtail_score += 8.0
        if business_core:
            longtail_score += 8.0
        if has_real_volume:
            if 10 <= search_volume <= 300:
                longtail_score += 8.0
            elif search_volume < 10:
                longtail_score += 3.0
            elif search_volume <= 1000:
                longtail_score += 4.0
        if difficulty <= 35:
            longtail_score += 7.0
        elif difficulty <= 55:
            longtail_score += 4.0
        if opportunity >= 75:
            longtail_score += 7.0
        elif opportunity >= 60:
            longtail_score += 4.0
        if source_signal_count >= 2:
            longtail_score += 6.0
        if low_reason:
            longtail_score -= 35.0
        if service_fit_score >= 80.0:
            longtail_score += 5.0
        elif service_fit_score < 55.0:
            longtail_score -= min(25.0, (55.0 - service_fit_score) * 0.5)
        if content_actionability_score >= 80.0:
            longtail_score += 4.0
        elif content_actionability_score < 55.0:
            longtail_score -= min(20.0, (55.0 - content_actionability_score) * 0.45)
        if local_surface_score >= 70.0:
            longtail_score += 6.0
        elif local_surface_score >= 55.0:
            longtail_score += 3.0
        if brand_intent_type in {"competitor_brand", "competitor_comparison", "own_vs_competitor"}:
            longtail_score -= 18.0
        if review_surface_score >= 70.0:
            longtail_score += 5.0
        elif review_surface_score >= 55.0:
            longtail_score += 3.0
        if reputation_risk_score >= 70.0:
            longtail_score -= 12.0
        if profile_action_signal >= 60.0:
            longtail_score += 6.0
        elif profile_action_signal >= 35.0:
            longtail_score += 3.0
        if availability_intent_score >= 70.0:
            longtail_score += 6.0
        elif availability_intent_score >= 55.0:
            longtail_score += 3.0
        if payment_coverage_score >= 70.0:
            longtail_score += 6.0
        elif payment_coverage_score >= 55.0:
            longtail_score += 3.0
        if access_convenience_score >= 70.0:
            longtail_score += 5.0
        elif access_convenience_score >= 55.0:
            longtail_score += 3.0
        longtail_score = round(max(0.0, min(100.0, longtail_score)), 2)

        high_value_longtail = (
            is_longtail
            and intent_is_valuable
            and has_region
            and (business_core or has_direct_anchor)
            and not low_reason
            and service_fit_score >= 65.0
            and not service_fit_profile["hard_negative"]
            and (
                content_actionability_score >= 58.0
                or local_surface_score >= 70.0
                or review_surface_score >= 70.0
                or profile_action_signal >= 60.0
                or availability_intent_score >= 70.0
                or payment_coverage_score >= 70.0
                or access_convenience_score >= 70.0
            )
            and brand_intent_type in {"generic"}
            and reputation_risk_score < 70.0
            and longtail_score >= 68.0
            and business_value_score >= 65.0
            and (has_real_volume or source_signal_count >= 2)
        )

        return {
            "category": category,
            "is_longtail": is_longtail,
            "high_value_longtail": high_value_longtail,
            "longtail_score": longtail_score,
            "business_value_score": business_value_score,
            "matched_intents": matched_intents,
            "strong_decision_terms": strong_decision_terms,
            "has_direct_anchor": has_direct_anchor,
            "low_business_value_reason": low_reason,
            "service_fit_score": service_fit_score,
            "negative_intent_flags": negative_intent_flags,
            "hard_negative_intent": bool(service_fit_profile["hard_negative"]),
            "content_actionability_score": float(content_actionability_score),
            "local_surface_score": float(local_surface_score),
            "brand_intent_type": brand_intent_type,
            "competitor_brand_risk_score": float(competitor_brand_risk_score or 0.0),
            "review_surface_score": float(review_surface_score or 0.0),
            "reputation_risk_score": float(reputation_risk_score or 0.0),
            "review_intent_type": review_intent_type or "none",
            "profile_action_signal": float(profile_action_signal or 0.0),
            "availability_intent_score": float(availability_intent_score or 0.0),
            "availability_intent_type": availability_intent_type or "none",
            "payment_coverage_score": float(payment_coverage_score or 0.0),
            "payment_coverage_type": payment_coverage_type or "none",
            "access_convenience_score": float(access_convenience_score or 0.0),
            "access_convenience_type": access_convenience_type or "none",
            "source_signal_count": source_signal_count,
            "has_real_volume": has_real_volume,
        }

    def _promote_grade_for_high_value_longtail(
        self,
        grade: str,
        value_profile: Dict[str, object],
        has_real_volume: bool,
        search_volume: int,
        difficulty: int,
        opportunity: int,
        verification_score: float,
        quality_flags: Optional[List[str]] = None,
    ) -> Tuple[str, List[str]]:
        flags = list(quality_flags or [])
        low_reason = value_profile.get("low_business_value_reason")
        if low_reason and low_reason not in flags:
            flags.append(str(low_reason))
        for negative_flag in value_profile.get("negative_intent_flags") or []:
            quality_flag = f"negative_intent:{negative_flag}"
            if quality_flag not in flags:
                flags.append(quality_flag)
        brand_intent_type = str(value_profile.get("brand_intent_type") or "generic")
        if brand_intent_type != "generic":
            quality_flag = f"brand_intent:{brand_intent_type}"
            if quality_flag not in flags:
                flags.append(quality_flag)
        review_surface_score = float(value_profile.get("review_surface_score", 0.0) or 0.0)
        reputation_risk_score = float(value_profile.get("reputation_risk_score", 0.0) or 0.0)
        profile_action_signal = float(value_profile.get("profile_action_signal", 0.0) or 0.0)
        availability_intent_score = float(value_profile.get("availability_intent_score", 0.0) or 0.0)
        payment_coverage_score = float(value_profile.get("payment_coverage_score", 0.0) or 0.0)
        access_convenience_score = float(value_profile.get("access_convenience_score", 0.0) or 0.0)
        if reputation_risk_score >= 70.0 and "reputation_high_risk_review" not in flags:
            flags.append("reputation_high_risk_review")

        if not value_profile.get("high_value_longtail"):
            return grade, flags
        if reputation_risk_score >= 70.0:
            return grade, flags
        if brand_intent_type != "generic":
            return grade, flags
        if bool(value_profile.get("hard_negative_intent")):
            return grade, flags
        if float(value_profile.get("service_fit_score", 0.0) or 0.0) < 65.0:
            return grade, flags
        if (
            float(value_profile.get("content_actionability_score", 0.0) or 0.0) < 58.0
            and float(value_profile.get("local_surface_score", 0.0) or 0.0) < 70.0
            and review_surface_score < 70.0
            and profile_action_signal < 60.0
            and availability_intent_score < 70.0
            and payment_coverage_score < 70.0
            and access_convenience_score < 70.0
        ):
            return grade, flags
        if (
            not value_profile.get("strong_decision_terms")
            and review_surface_score < 70.0
            and availability_intent_score < 70.0
            and payment_coverage_score < 70.0
            and access_convenience_score < 70.0
        ):
            return grade, flags
        if float(value_profile.get("longtail_score", 0.0) or 0.0) < 78.0:
            return grade, flags
        if float(value_profile.get("business_value_score", 0.0) or 0.0) < 75.0:
            return grade, flags

        if not has_real_volume:
            source_signal_count = int(value_profile.get("source_signal_count", 0) or 0)
            if (
                source_signal_count >= 2
                and verification_score >= 55
                and difficulty <= 35
                and opportunity >= 80
            ):
                if "estimated_high_value_longtail" not in flags:
                    flags.append("estimated_high_value_longtail")
                return ("B" if grade == "C" else grade), flags
            return grade, flags

        if search_volume < 10:
            return grade, flags
        if search_volume < 20 and verification_score < 75:
            return grade, flags
        if verification_score < 65 or difficulty > 35 or opportunity < 75:
            return grade, flags

        if grade == "B":
            return "A", flags
        if grade == "C" and verification_score >= 65 and difficulty <= 30 and opportunity >= 80:
            return "B", flags
        return grade, flags

    def _promote_grade_for_execution_fit(
        self,
        grade: str,
        value_profile: Dict[str, object],
        *,
        has_real_volume: bool,
        search_volume: int,
        verification_score: float,
        source_signal_count: int,
        category: str,
        community_signal: float,
        conversion_signal: float,
        profile_action_signal: float,
        local_service_fit_score: float,
        content_actionability_score: float,
        local_surface_score: float,
        review_surface_score: float,
        availability_intent_score: float,
        payment_coverage_score: float,
        access_convenience_score: float,
        medical_ad_risk_score: float,
        reputation_risk_score: float,
        brand_intent_type: str,
        quality_flags: Optional[List[str]] = None,
    ) -> Tuple[str, List[str]]:
        """Promote local medical longtails that are execution-ready, not just KEI-rich.

        Regional clinic keywords often have low KEI because document counts are
        broad while true demand appears in community, booking, cost, and local
        surface signals. This promotion keeps the existing risk guards, but lets
        a small set of well-verified execution keywords reach S/A.
        """
        flags = list(quality_flags or [])
        order = {"S": 0, "A": 1, "B": 2, "C": 3}
        current_rank = order.get(grade, 3)

        if current_rank >= order["C"]:
            return grade, flags
        if not has_real_volume or search_volume < 20:
            return grade, flags
        if not bool(value_profile.get("high_value_longtail")):
            return grade, flags
        if str(brand_intent_type or "generic") != "generic":
            return grade, flags
        if medical_ad_risk_score >= 40.0 or reputation_risk_score >= 40.0:
            return grade, flags
        if bool(value_profile.get("hard_negative_intent")):
            return grade, flags
        red_flag_execution = any(
            flag == "content_action:safe_faq_candidate"
            or flag.startswith("negative_intent:")
            for flag in flags
        )

        business_value_score = float(value_profile.get("business_value_score", 0.0) or 0.0)
        longtail_score = float(value_profile.get("longtail_score", 0.0) or 0.0)
        market_signal = max(
            float(community_signal or 0.0),
            float(conversion_signal or 0.0) * 1.15,
            float(profile_action_signal or 0.0),
            float(review_surface_score or 0.0),
            float(availability_intent_score or 0.0),
            float(payment_coverage_score or 0.0),
            float(access_convenience_score or 0.0),
        )
        execution_score = (
            min(100.0, max(0.0, local_service_fit_score)) * 0.20
            + min(100.0, max(0.0, content_actionability_score)) * 0.18
            + min(100.0, max(0.0, business_value_score)) * 0.14
            + min(100.0, max(0.0, longtail_score)) * 0.10
            + min(100.0, max(0.0, verification_score)) * 0.12
            + min(100.0, max(0.0, local_surface_score)) * 0.10
            + min(100.0, max(0.0, market_signal)) * 0.16
        )

        category_key = GYULIM_KEYWORD_PROFILE.normalize_category(
            str(value_profile.get("category") or category or "")
        )
        skin_service_axis_signal = (
            category_key == "피부/여드름"
            and local_surface_score >= 70.0
            and availability_intent_score >= 45.0
            and local_service_fit_score >= 90.0
            and content_actionability_score >= 90.0
            and business_value_score >= 95.0
            and longtail_score >= 90.0
        )
        strategic_focus_service_floor = {
            "흉터/여드름흉터": 90.0,
            "피부/여드름": 90.0,
            "다이어트": 90.0,
            "안면비대칭": 80.0,
        }.get(category_key)
        strategic_focus_axis_signal = bool(
            strategic_focus_service_floor is not None
            and local_service_fit_score >= strategic_focus_service_floor
            and content_actionability_score >= 84.0
            and business_value_score >= 95.0
            and longtail_score >= 90.0
            and (
                local_surface_score >= 70.0
                or review_surface_score >= 65.0
                or availability_intent_score >= 45.0
                or payment_coverage_score >= 50.0
                or community_signal >= 60.0
            )
        )
        s_signal = (
            community_signal >= 65.0
            or conversion_signal >= 45.0
            or profile_action_signal >= 60.0
            or (review_surface_score >= 70.0 and community_signal >= 40.0)
            or (
                category_key == "교통사고"
                and payment_coverage_score >= 70.0
                and community_signal >= 35.0
            )
        )
        s_ready = (
            execution_score >= 90.0
            and verification_score >= 82.0
            and local_service_fit_score >= 90.0
            and content_actionability_score >= 85.0
            and local_surface_score >= 70.0
            and business_value_score >= 90.0
            and longtail_score >= 85.0
            and s_signal
            and not red_flag_execution
        )
        if s_ready and current_rank > order["S"]:
            if "execution_fit_s_grade" not in flags:
                flags.append("execution_fit_s_grade")
            return "S", flags

        a_signal = (
            market_signal >= 55.0
            or source_signal_count >= 2
            or skin_service_axis_signal
            or strategic_focus_axis_signal
        )
        a_ready = (
            execution_score >= 82.0
            and verification_score >= 75.0
            and local_service_fit_score >= 85.0
            and content_actionability_score >= 80.0
            and local_surface_score >= 65.0
            and business_value_score >= 85.0
            and longtail_score >= 75.0
            and a_signal
        )
        strategic_focus_a_ready = (
            strategic_focus_axis_signal
            and execution_score >= 78.0
            and verification_score >= 65.0
            and local_service_fit_score >= strategic_focus_service_floor
            and content_actionability_score >= 84.0
            and business_value_score >= 95.0
            and longtail_score >= 90.0
        )
        if (a_ready or strategic_focus_a_ready) and current_rank > order["A"]:
            if "execution_fit_a_grade" not in flags:
                flags.append("execution_fit_a_grade")
            if strategic_focus_a_ready and "strategic_focus_axis_a_grade" not in flags:
                flags.append("strategic_focus_axis_a_grade")
            return "A", flags

        return grade, flags

    def _build_high_value_longtail_variants(
        self,
        seed_keywords: List[str],
        max_keywords: int = 360,
    ) -> Set[str]:
        """자동완성으로 잘 안 잡히는 지역+서비스+전환 의도 롱테일을 직접 생성."""
        collector = self._collector_or_default()
        variants: Set[str] = set()
        seen: Set[str] = set()

        def add_variant(*parts: str) -> bool:
            keyword = " ".join(part.strip() for part in parts if part and part.strip())
            cleaned = " ".join(dict.fromkeys(keyword.split()))
            norm = self._normalize_keyword_for_history(cleaned)
            if not norm or norm in seen:
                return False
            seen.add(norm)
            if not collector._is_valid_keyword(cleaned):
                return False
            category_for_cleaned = collector._detect_category(cleaned)
            if not collector.is_focus_candidate(cleaned, category_for_cleaned):
                return False
            variants.add(cleaned)
            return len(variants) >= max_keywords

        category_order: List[str] = []
        region_order: List[str] = []
        for seed in seed_keywords:
            category = self._canonical_profile_category(seed, collector._detect_category(seed))
            if category in self.CATEGORY_CANONICAL_SERVICES and category not in category_order:
                category_order.append(category)
            region = self._extract_target_region(seed)
            if region and region not in region_order:
                region_order.append(region)

        for category in self.CATEGORY_CANONICAL_SERVICES:
            if category not in category_order:
                category_order.append(category)

        active_scout_regions = list(dict.fromkeys(
            [GYULIM_KEYWORD_PROFILE.primary_region]
            + list(collector.neighborhoods[:8])
            + list(collector.cheongju_regions[:6])
            + [
                region for region in self.LONGTAIL_SCOUT_REGIONS
                if GYULIM_KEYWORD_PROFILE.is_target_region(region, include_nearby=True)
            ]
        ))
        for region in active_scout_regions:
            if region not in region_order:
                region_order.append(region)

        first_pass_limit = min(max_keywords, max(90, int(max_keywords * 0.30)))
        strategic_limit = min(max_keywords, max(45, int(max_keywords * 0.24)))
        journey_limit = min(max_keywords, max(first_pass_limit, int(max_keywords * 0.62)))
        question_limit = min(max_keywords, max(journey_limit, int(max_keywords * 0.82)))

        # Strategic density pass: secure high-intent scar, skin, diet, and asymmetry
        # variants before broad medical categories consume the early quota.
        # Build them round-robin so scar/skin terms do not consume the whole
        # strategic slice before diet and asymmetry get coverage.
        strategic_combos_by_category: Dict[str, List[Tuple[str, str, str]]] = {}
        for category in self.STRATEGIC_SA_DENSITY_CATEGORIES:
            services = self.CATEGORY_CANONICAL_SERVICES.get(category, ())
            suffixes = self.STRATEGIC_SA_DENSITY_SUFFIXES.get(category, ())
            if not services or not suffixes:
                continue
            strategic_combos_by_category[category] = [
                (region_item, service, suffix)
                for region_item in region_order[:5]
                for service in services[:4]
                for suffix in suffixes[:5]
            ]

        strategic_indices = {category: 0 for category in strategic_combos_by_category}
        while len(variants) < strategic_limit and strategic_combos_by_category:
            progressed = False
            for category in self.STRATEGIC_SA_DENSITY_CATEGORIES:
                combos = strategic_combos_by_category.get(category)
                if not combos:
                    continue
                index = strategic_indices.get(category, 0)
                while index < len(combos):
                    strategic_indices[category] = index + 1
                    before_count = len(variants)
                    if add_variant(*combos[index]):
                        return variants
                    index += 1
                    if len(variants) > before_count:
                        progressed = True
                        break
                if strategic_indices.get(category, 0) >= len(combos):
                    strategic_combos_by_category.pop(category, None)
                if len(variants) >= strategic_limit:
                    break
            if not progressed:
                break

        # First pass: cover every focus category across priority regions before adding richer context variants.
        for region_item in region_order[:3]:
            if len(variants) >= first_pass_limit:
                break
            for category in category_order:
                if len(variants) >= first_pass_limit:
                    break
                services = self.CATEGORY_CANONICAL_SERVICES.get(category, ())
                suffixes = self.HIGH_VALUE_LONGTAIL_SUFFIXES.get(category, ())
                if not services or not suffixes:
                    continue
                for service in services[:3]:
                    if len(variants) >= first_pass_limit:
                        break
                    for suffix in suffixes[:4]:
                        if add_variant(region_item, service, suffix):
                            return variants
                        if len(variants) >= first_pass_limit:
                            break

        # Search journey pass: expand practical customer needs without multiplying every possible suffix.
        for region_item in region_order[:4]:
            if len(variants) >= journey_limit:
                break
            for category in category_order:
                if len(variants) >= journey_limit:
                    break
                services = self.CATEGORY_CANONICAL_SERVICES.get(category, ())
                journey_suffixes = self.CATEGORY_SEARCH_JOURNEY_SUFFIXES.get(category, {})
                if not services or not journey_suffixes:
                    continue
                for stage in self.SEARCH_JOURNEY_STAGES:
                    if len(variants) >= journey_limit:
                        break
                    suffixes = journey_suffixes.get(stage, ())
                    if not suffixes:
                        continue
                    for service in services[:2]:
                        if len(variants) >= journey_limit:
                            break
                        for suffix in suffixes[:4]:
                            if add_variant(region_item, service, suffix):
                                return variants
                            if len(variants) >= journey_limit:
                                break

        # Second pass: question-form longtails capture high-intent searches that are often too sparse for autocomplete.
        for region_item in region_order:
            if len(variants) >= question_limit:
                break
            for category in category_order:
                if len(variants) >= question_limit:
                    break
                services = self.CATEGORY_CANONICAL_SERVICES.get(category, ())
                if not services:
                    continue
                for service in services[:3]:
                    if len(variants) >= question_limit:
                        break
                    for pattern in self.HIGH_VALUE_LONGTAIL_QUESTION_PATTERNS:
                        if add_variant(pattern.format(region=region_item, service=service)):
                            return variants
                        if len(variants) >= question_limit:
                            break
                    if len(variants) >= question_limit:
                        break
                if len(variants) >= question_limit:
                    break
            if len(variants) >= question_limit:
                break

        # Third pass: add situational modifiers that autocomplete often misses.
        for region_item in region_order:
            for category in category_order:
                services = self.CATEGORY_CANONICAL_SERVICES.get(category, ())
                suffixes = self.HIGH_VALUE_LONGTAIL_SUFFIXES.get(category, ())
                contexts = self.HIGH_VALUE_LONGTAIL_CONTEXTS.get(category, ())
                if not services or not suffixes or not contexts:
                    continue
                for service in services[:3]:
                    for context in contexts[:5]:
                        for suffix in suffixes[:4]:
                            if add_variant(region_item, context, service, suffix):
                                return variants
                            if add_variant(region_item, service, context, suffix):
                                return variants

        return variants

    def _record_rejection(self, source: str, reason: str, count: int = 1) -> None:
        self._ensure_quality_tracking()
        self.candidate_stats["rejected_by_source"][source][reason] += count

    def _record_source_signal(self, keyword: str, source: str) -> None:
        self._ensure_quality_tracking()
        norm = self._normalize_keyword_for_history(keyword)
        if not norm:
            return
        self.keyword_source_signals[norm].add(source)

        canonical = self.keyword_canonical_by_norm.get(norm)
        if canonical and hasattr(self, "collected") and canonical in self.collected:
            self._sync_result_quality_fields(self.collected[canonical])

    def _merge_ad_keyword_metrics(self, metrics: Optional[Dict[str, Dict[str, object]]]) -> None:
        self._ensure_quality_tracking()
        for keyword, data in (metrics or {}).items():
            norm = self._normalize_keyword_for_history(keyword)
            if norm and isinstance(data, dict):
                self.keyword_ad_metrics[norm] = dict(data)

    def _get_ad_keyword_metrics(self, keyword: str) -> Dict[str, object]:
        self._ensure_quality_tracking()
        norm = self._normalize_keyword_for_history(keyword)
        if norm in self.keyword_ad_metrics:
            return self.keyword_ad_metrics[norm]
        compact_norm = self._normalize_keyword_for_history((keyword or "").replace(" ", ""))
        return self.keyword_ad_metrics.get(compact_norm, {})

    def _get_inbound_query_metrics(self, keyword: str) -> Dict[str, object]:
        self._ensure_quality_tracking()
        norm = self._normalize_keyword_for_history(keyword)
        if norm in self.inbound_query_metrics:
            return self.inbound_query_metrics[norm]
        compact_norm = self._normalize_keyword_for_history((keyword or "").replace(" ", ""))
        return self.inbound_query_metrics.get(compact_norm, {})

    def _get_owned_rank_metrics(self, keyword: str) -> Dict[str, object]:
        self._ensure_quality_tracking()
        norm = self._normalize_keyword_for_history(keyword)
        if norm in self.owned_rank_metrics:
            return self.owned_rank_metrics[norm]
        compact_norm = self._normalize_keyword_for_history((keyword or "").replace(" ", ""))
        return self.owned_rank_metrics.get(compact_norm, {})

    def _get_community_keyword_metrics(self, keyword: str) -> Dict[str, object]:
        self._ensure_quality_tracking()
        norm = self._normalize_keyword_for_history(keyword)
        if norm in self.community_keyword_metrics:
            return self.community_keyword_metrics[norm]
        compact_norm = self._normalize_keyword_for_history((keyword or "").replace(" ", ""))
        return self.community_keyword_metrics.get(compact_norm, {})

    def _get_conversion_keyword_metrics(self, keyword: str) -> Dict[str, object]:
        self._ensure_quality_tracking()
        norm = self._normalize_keyword_for_history(keyword)
        if norm in self.conversion_keyword_metrics:
            return self.conversion_keyword_metrics[norm]
        compact_norm = self._normalize_keyword_for_history((keyword or "").replace(" ", ""))
        return self.conversion_keyword_metrics.get(compact_norm, {})

    def _get_profile_action_metrics(self, keyword: str) -> Dict[str, object]:
        self._ensure_quality_tracking()
        norm = self._normalize_keyword_for_history(keyword)
        if norm in self.profile_action_metrics:
            return self.profile_action_metrics[norm]
        compact_norm = self._normalize_keyword_for_history((keyword or "").replace(" ", ""))
        return self.profile_action_metrics.get(compact_norm, {})

    @staticmethod
    def _calculate_ad_value_signal(metrics: Optional[Dict[str, object]]) -> float:
        if not metrics:
            return 0.0

        def as_float(key: str) -> float:
            try:
                return float(metrics.get(key, 0.0) or 0.0)
            except (TypeError, ValueError):
                return 0.0

        clicks = as_float("monthly_pc_clicks") + as_float("monthly_mobile_clicks")
        ctr = max(as_float("monthly_pc_ctr"), as_float("monthly_mobile_ctr"))
        ad_depth = as_float("avg_ad_depth")
        competition = str(metrics.get("competition", "") or "").lower()

        if clicks >= 100:
            click_score = 30.0
        elif clicks >= 30:
            click_score = 22.0
        elif clicks >= 10:
            click_score = 14.0
        elif clicks > 0:
            click_score = 7.0
        else:
            click_score = 0.0

        if ctr >= 3.0:
            ctr_score = 25.0
        elif ctr >= 1.0:
            ctr_score = 18.0
        elif ctr >= 0.3:
            ctr_score = 10.0
        elif ctr > 0:
            ctr_score = 4.0
        else:
            ctr_score = 0.0

        if "높" in competition or "high" in competition:
            competition_score = 20.0
        elif "중" in competition or "medium" in competition:
            competition_score = 12.0
        elif "낮" in competition or "low" in competition:
            competition_score = 4.0
        else:
            competition_score = 0.0

        depth_score = min(25.0, max(0.0, ad_depth) * 2.5)
        return round(min(100.0, click_score + ctr_score + competition_score + depth_score), 2)

    @staticmethod
    def _calculate_mobile_share(metrics: Optional[Dict[str, object]]) -> float:
        if not metrics:
            return 0.0
        try:
            pc = float(metrics.get("monthly_pc_count", 0.0) or 0.0)
            mobile = float(metrics.get("monthly_mobile_count", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0
        total = pc + mobile
        return round(mobile / total, 4) if total > 0 else 0.0

    @staticmethod
    def _calculate_inbound_value_signal(metrics: Optional[Dict[str, object]]) -> float:
        if not metrics:
            return 0.0
        impressions = int(metrics.get("impressions", 0) or 0)
        clicks = int(metrics.get("clicks", 0) or 0)
        ctr = float(metrics.get("ctr", 0.0) or 0.0)
        position = float(metrics.get("position", 0.0) or 0.0)

        impression_score = min(28.0, math.log1p(max(0, impressions)) * 5.0)
        click_score = min(35.0, clicks * 8.0)
        ctr_score = min(22.0, ctr * 180.0)
        position_score = 0.0
        if 0 < position <= 3:
            position_score = 15.0
        elif position <= 10:
            position_score = 10.0
        elif position <= 20:
            position_score = 6.0
        elif position <= 50:
            position_score = 3.0
        return round(min(100.0, impression_score + click_score + ctr_score + position_score), 2)

    @staticmethod
    def _rank_status_label(metrics: Optional[Dict[str, object]]) -> str:
        if not metrics:
            return "unknown"
        status = str(metrics.get("status", "") or "").lower()
        rank = int(metrics.get("rank", 0) or 0)
        if status == "found" and rank > 0:
            if rank <= 3:
                return "owned_top3"
            if rank <= 10:
                return "striking_top10"
            if rank <= 20:
                return "striking_page2"
            if rank <= 40:
                return "visible_gap"
            return "deep_gap"
        if status in {"not_in_results", "no_results"}:
            return status
        return "unknown"

    @classmethod
    def _calculate_rank_gap_signal(cls, metrics: Optional[Dict[str, object]]) -> float:
        if not metrics:
            return 0.0
        status = str(metrics.get("status", "") or "").lower()
        rank = int(metrics.get("rank", 0) or 0)
        device = str(metrics.get("device", "") or "").lower()
        if status != "found" or rank <= 0:
            return 18.0 if status == "not_in_results" else 0.0
        if rank <= 3:
            score = 12.0
        elif rank <= 10:
            score = 78.0
        elif rank <= 20:
            score = 88.0
        elif rank <= 40:
            score = 62.0
        else:
            score = 35.0
        if device == "mobile" and score >= 50.0:
            score += 6.0
        return round(min(100.0, score), 2)

    @staticmethod
    def _calculate_community_value_signal(metrics: Optional[Dict[str, object]]) -> float:
        if not metrics:
            return 0.0
        mentions = int(metrics.get("mentions", 0) or 0)
        platforms = metrics.get("platforms", []) or []
        platform_count = len(platforms)
        commentable = int(metrics.get("commentable", 0) or 0)
        max_priority = float(metrics.get("max_priority", 0.0) or 0.0)
        max_conversion_fit = float(metrics.get("max_conversion_fit", 0.0) or 0.0)
        max_infiltration = float(metrics.get("max_infiltration", 0.0) or 0.0)

        mention_score = min(24.0, math.log1p(max(0, mentions)) * 8.0)
        platform_score = min(16.0, platform_count * 6.0)
        commentable_score = min(10.0, commentable * 3.0)
        conversion_score = min(28.0, max_conversion_fit * 0.28)
        infiltration_score = min(14.0, max_infiltration * 0.14)
        priority_score = min(8.0, max_priority * 0.05)
        return round(
            min(100.0, mention_score + platform_score + commentable_score + conversion_score + infiltration_score + priority_score),
            2,
        )

    @staticmethod
    def _calculate_conversion_value_signal(metrics: Optional[Dict[str, object]]) -> float:
        if not metrics:
            return 0.0
        total_calls = int(metrics.get("total_calls", 0) or 0)
        naver_calls = int(metrics.get("naver_search_calls", 0) or 0)
        duration_seconds = int(metrics.get("duration_seconds", 0) or 0)
        rows = int(metrics.get("rows", 0) or 0)

        call_score = min(42.0, math.log1p(max(0, total_calls)) * 18.0)
        naver_score = min(24.0, math.log1p(max(0, naver_calls)) * 12.0)
        duration_score = min(18.0, math.log1p(max(0, duration_seconds) / 60.0) * 8.0)
        repeat_score = min(16.0, rows * 4.0)
        return round(min(100.0, call_score + naver_score + duration_score + repeat_score), 2)

    @staticmethod
    def _calculate_profile_action_value_signal(metrics: Optional[Dict[str, object]]) -> float:
        if not metrics:
            return 0.0
        calls = int(metrics.get("calls", 0) or metrics.get("phone_clicks", 0) or 0)
        directions = int(metrics.get("directions", 0) or metrics.get("direction_requests", 0) or 0)
        website = int(metrics.get("website_clicks", 0) or metrics.get("website_actions", 0) or 0)
        bookings = int(metrics.get("bookings", 0) or metrics.get("reservations", 0) or 0)
        messages = int(metrics.get("messages", 0) or metrics.get("message_clicks", 0) or 0)
        total_actions = calls + directions + website + bookings + messages

        action_score = min(32.0, math.log1p(max(0, total_actions)) * 12.0)
        direction_score = min(22.0, math.log1p(max(0, directions)) * 10.0)
        booking_score = min(24.0, math.log1p(max(0, bookings)) * 14.0)
        call_score = min(14.0, math.log1p(max(0, calls)) * 6.0)
        website_score = min(8.0, math.log1p(max(0, website)) * 4.0)
        message_score = min(8.0, math.log1p(max(0, messages)) * 5.0)
        return round(
            min(100.0, action_score + direction_score + booking_score + call_score + website_score + message_score),
            2,
        )

    def _calculate_medical_ad_risk_profile(self, keyword: str, search_intent: Optional[str] = None) -> Dict[str, object]:
        keyword = keyword or ""
        compact = re.sub(r"\s+", "", keyword.lower())
        search_intent = search_intent or SearchIntentClassifier.classify(keyword)
        flags: List[str] = []
        score = 0.0

        def matched_terms(terms: Tuple[str, ...]) -> List[str]:
            return [term for term in terms if term.lower().replace(" ", "") in compact]

        high_risk_terms = matched_terms(self.MEDICAL_AD_HIGH_RISK_TERMS)
        testimonial_terms = matched_terms(self.MEDICAL_AD_TESTIMONIAL_RISK_TERMS)
        claim_terms = matched_terms(self.MEDICAL_AD_CLAIM_RISK_TERMS)
        comparison_terms = matched_terms(self.MEDICAL_AD_COMPARISON_RISK_TERMS)
        safe_info_terms = matched_terms(self.MEDICAL_AD_SAFE_INFO_TERMS)

        if high_risk_terms:
            score += 42.0 + min(28.0, max(0, len(high_risk_terms) - 1) * 14.0)
            flags.append("high_risk_claim")
        if testimonial_terms:
            score += 28.0
            flags.append("testimonial_or_before_after")
        if claim_terms:
            score += 16.0
            flags.append("treatment_effect_claim")
        if comparison_terms:
            score += 14.0
            flags.append("comparative_claim")

        is_safe_info = bool(safe_info_terms)
        if is_safe_info:
            flags.append("safe_info_possible")
            if not any(flag in flags for flag in ("high_risk_claim", "testimonial_or_before_after")):
                score = max(0.0, score - 12.0)

        if search_intent in {"red_flag", "informational"} and not any(
            flag in flags for flag in ("high_risk_claim", "testimonial_or_before_after")
        ):
            score = max(0.0, score - 8.0)

        score = round(min(100.0, max(0.0, score)), 2)
        if score >= 70.0:
            risk_level = "high"
        elif score >= 40.0:
            risk_level = "review"
        elif score > 0:
            risk_level = "low"
        else:
            risk_level = "safe"

        feasibility = round(max(0.0, min(100.0, 100.0 - score + (8.0 if is_safe_info else 0.0))), 2)
        return {
            "score": score,
            "flags": flags,
            "risk_level": risk_level,
            "content_feasibility_score": feasibility,
        }

    def _content_cluster_key(self, keyword: str, category: Optional[str] = None, search_intent: Optional[str] = None) -> str:
        keyword = keyword or ""
        collector = self._collector_or_default()
        category = self._canonical_profile_category(keyword, category or collector._detect_category(keyword))
        search_intent = search_intent or SearchIntentClassifier.classify(keyword)
        region = self._extract_target_region(keyword)

        aspect_map = (
            ("price", ("가격", "비용", "얼마", "치료비", "보험", "실비", "자보", "자동차보험")),
            ("review", ("후기", "추천", "잘하는", "괜찮은곳", "유명")),
            ("consult", ("상담", "예약", "문의", "초진", "어디")),
            ("effect", ("효과", "전후", "기간", "차이")),
            ("risk", ("부작용", "통증", "재발", "주의")),
            ("access", ("야간", "주말", "일요일", "근처", "입원")),
        )
        aspect = "general"
        for key, terms in aspect_map:
            if any(term in keyword for term in terms):
                aspect = key
                break

        return "|".join([
            region or GYULIM_KEYWORD_PROFILE.primary_region,
            category or "unknown",
            search_intent or "unknown",
            aspect,
        ])

    @staticmethod
    def _normalize_quality_flags(flags: Optional[List[str]], search_volume: int, document_count: int) -> List[str]:
        cleaned: List[str] = []
        for flag in flags or []:
            if flag == "missing_document_count" and document_count > 0:
                continue
            if flag == "low_document_count" and document_count >= 10:
                continue
            if flag not in cleaned:
                cleaned.append(flag)
        return cleaned

    def _sync_result_quality_fields(self, result: KeywordResult) -> None:
        self._ensure_quality_tracking()
        result.quality_flags = self._normalize_quality_flags(
            result.quality_flags,
            result.search_volume,
            result.document_count,
        )
        norm = self._normalize_keyword_for_history(result.keyword)
        signals = sorted(self.keyword_source_signals.get(norm, {result.source}))
        if result.source not in signals:
            signals.append(result.source)
            signals = sorted(set(signals))
        ad_metrics = self._get_ad_keyword_metrics(result.keyword)
        inbound_metrics = self._get_inbound_query_metrics(result.keyword)
        inbound_value_signal = self._calculate_inbound_value_signal(inbound_metrics)
        rank_metrics = self._get_owned_rank_metrics(result.keyword)
        rank_gap_signal = float(rank_metrics.get("rank_gap_signal", 0.0) or 0.0)
        community_metrics = self._get_community_keyword_metrics(result.keyword)
        community_signal = float(community_metrics.get("community_signal", 0.0) or 0.0)
        conversion_metrics = self._get_conversion_keyword_metrics(result.keyword)
        conversion_signal = float(conversion_metrics.get("conversion_signal", 0.0) or 0.0)
        profile_action_metrics = self._get_profile_action_metrics(result.keyword)
        profile_action_signal = float(profile_action_metrics.get("profile_action_signal", 0.0) or 0.0)
        mobile_share = self._calculate_mobile_share(ad_metrics)
        if inbound_metrics and "inbound_query" not in signals:
            signals = sorted(set(signals + ["inbound_query"]))
        if rank_gap_signal >= 55.0 and "owned_rank_gap" not in signals:
            signals = sorted(set(signals + ["owned_rank_gap"]))
        if community_signal >= 40.0 and "community_demand" not in signals:
            signals = sorted(set(signals + ["community_demand"]))
        if conversion_signal >= 35.0 and "actual_call_conversion" not in signals:
            signals = sorted(set(signals + ["actual_call_conversion"]))
        if profile_action_signal >= 35.0 and "profile_action_conversion" not in signals:
            signals = sorted(set(signals + ["profile_action_conversion"]))
        result.source_signals = signals
        result.mobile_share = mobile_share
        result.owned_rank = int(rank_metrics.get("rank", result.owned_rank) or 0)
        result.owned_rank_device = str(rank_metrics.get("device", result.owned_rank_device) or "")
        result.rank_gap_signal = rank_gap_signal
        result.rank_status = str(rank_metrics.get("rank_status", result.rank_status) or "unknown")
        result.community_mentions = int(community_metrics.get("mentions", result.community_mentions) or 0)
        result.community_conversion_fit = float(community_metrics.get("max_conversion_fit", result.community_conversion_fit) or 0.0)
        result.community_signal = community_signal
        result.community_platforms = list(community_metrics.get("platforms", result.community_platforms) or [])
        result.conversion_calls = int(conversion_metrics.get("total_calls", result.conversion_calls) or 0)
        result.conversion_naver_calls = int(conversion_metrics.get("naver_search_calls", result.conversion_naver_calls) or 0)
        result.conversion_duration_seconds = int(conversion_metrics.get("duration_seconds", result.conversion_duration_seconds) or 0)
        result.conversion_signal = conversion_signal
        result.profile_action_signal = profile_action_signal
        result.profile_actions_total = int(profile_action_metrics.get("total_actions", result.profile_actions_total) or 0)
        result.profile_direction_actions = int(profile_action_metrics.get("directions", result.profile_direction_actions) or 0)
        result.profile_website_actions = int(profile_action_metrics.get("website_clicks", result.profile_website_actions) or 0)
        result.profile_booking_actions = int(profile_action_metrics.get("bookings", result.profile_booking_actions) or 0)
        result.profile_message_actions = int(profile_action_metrics.get("messages", result.profile_message_actions) or 0)
        result.profile_action_sources = list(profile_action_metrics.get("sources", result.profile_action_sources) or [])
        result.profile_action_flags = []
        result.inbound_impressions = int(inbound_metrics.get("impressions", result.inbound_impressions) or 0)
        result.inbound_clicks = int(inbound_metrics.get("clicks", result.inbound_clicks) or 0)
        result.inbound_ctr = float(inbound_metrics.get("ctr", result.inbound_ctr) or 0.0)
        result.inbound_position = float(inbound_metrics.get("position", result.inbound_position) or 0.0)
        result.inbound_sources = list(inbound_metrics.get("sources", result.inbound_sources) or [])
        result.content_cluster_key = self._content_cluster_key(result.keyword, result.category, result.search_intent)
        medical_risk = self._calculate_medical_ad_risk_profile(result.keyword, result.search_intent)
        result.medical_ad_risk_score = float(medical_risk["score"])
        result.medical_ad_risk_flags = list(medical_risk["flags"])
        result.content_feasibility_score = float(medical_risk["content_feasibility_score"])
        service_fit = self._calculate_service_fit_profile(result.keyword, result.category, result.search_intent)
        result.local_service_fit_score = float(service_fit["score"])
        result.negative_intent_flags = list(service_fit["flags"])
        content_action = self._calculate_content_actionability_profile(
            result.keyword,
            result.category,
            result.search_intent,
            medical_ad_risk_score=result.medical_ad_risk_score,
            service_fit_score=result.local_service_fit_score,
        )
        result.content_actionability_score = float(content_action["score"])
        result.recommended_content_type = str(content_action["recommended_content_type"])
        result.content_action_flags = list(content_action["flags"])
        local_surface = self._calculate_local_surface_profile(
            result.keyword,
            result.category,
            result.search_intent,
            mobile_share=mobile_share,
            rank_gap_signal=rank_gap_signal,
            conversion_signal=max(conversion_signal, profile_action_signal),
            service_fit_score=result.local_service_fit_score,
        )
        result.local_surface_score = float(local_surface["score"])
        result.preferred_search_surface = str(local_surface["preferred_search_surface"])
        result.local_surface_flags = list(local_surface["flags"])
        availability_profile = self._calculate_availability_intent_profile(
            result.keyword,
            result.category,
            result.search_intent,
            local_surface_score=result.local_surface_score,
            profile_action_signal=result.profile_action_signal,
            service_fit_score=result.local_service_fit_score,
        )
        result.availability_intent_score = float(availability_profile["availability_intent_score"])
        result.availability_intent_type = str(availability_profile["availability_intent_type"])
        result.availability_action_flags = list(availability_profile["flags"])
        payment_profile = self._calculate_payment_coverage_profile(
            result.keyword,
            result.category,
            result.search_intent,
            service_fit_score=result.local_service_fit_score,
            medical_ad_risk_score=result.medical_ad_risk_score,
            local_surface_score=result.local_surface_score,
            profile_action_signal=result.profile_action_signal,
        )
        result.payment_coverage_score = float(payment_profile["payment_coverage_score"])
        result.payment_coverage_type = str(payment_profile["payment_coverage_type"])
        result.payment_action_flags = list(payment_profile["flags"])
        access_profile = self._calculate_access_convenience_profile(
            result.keyword,
            result.category,
            result.search_intent,
            service_fit_score=result.local_service_fit_score,
            local_surface_score=result.local_surface_score,
            profile_action_signal=result.profile_action_signal,
            availability_intent_score=result.availability_intent_score,
        )
        result.access_convenience_score = float(access_profile["access_convenience_score"])
        result.access_convenience_type = str(access_profile["access_convenience_type"])
        result.access_convenience_flags = list(access_profile["flags"])
        brand_profile = self._calculate_brand_intent_profile(result.keyword, result.search_intent)
        result.brand_intent_type = str(brand_profile["brand_intent_type"])
        result.brand_signal_score = float(brand_profile["brand_signal_score"])
        result.brand_mentions = list(brand_profile["brand_mentions"])
        result.competitor_brand_risk_score = float(brand_profile["competitor_brand_risk_score"])
        result.brand_action_flags = list(brand_profile["flags"])
        review_profile = self._calculate_review_reputation_profile(
            result.keyword,
            result.search_intent,
            brand_intent_type=result.brand_intent_type,
            community_signal=community_signal,
            local_surface_score=result.local_surface_score,
            medical_ad_risk_score=result.medical_ad_risk_score,
        )
        result.review_surface_score = float(review_profile["review_surface_score"])
        result.reputation_risk_score = float(review_profile["reputation_risk_score"])
        result.review_intent_type = str(review_profile["review_intent_type"])
        result.review_action_flags = list(review_profile["flags"])
        if result.local_service_fit_score < 35.0:
            result.grade = self._cap_grade(result.grade, "C")
            result.high_value_longtail = False
            if "service_fit_block" not in result.quality_flags:
                result.quality_flags.append("service_fit_block")
        elif result.local_service_fit_score < 60.0 and "service_fit_review" not in result.quality_flags:
            result.grade = self._cap_grade(result.grade, "B")
            result.quality_flags.append("service_fit_review")
        for negative_flag in result.negative_intent_flags:
            quality_flag = f"negative_intent:{negative_flag}"
            if quality_flag not in result.quality_flags:
                result.quality_flags.append(quality_flag)
        if result.content_actionability_score < 45.0:
            result.grade = self._cap_grade(result.grade, "C")
            result.high_value_longtail = False
            if "content_low_actionability" not in result.quality_flags:
                result.quality_flags.append("content_low_actionability")
        elif result.content_actionability_score < 60.0 and "content_action_review" not in result.quality_flags:
            result.grade = self._cap_grade(result.grade, "B")
            result.quality_flags.append("content_action_review")
        for action_flag in result.content_action_flags:
            quality_flag = f"content_action:{action_flag}"
            if quality_flag not in result.quality_flags:
                result.quality_flags.append(quality_flag)
        if result.local_surface_score >= 70.0 and "local_surface_high_value" not in result.quality_flags:
            result.quality_flags.append("local_surface_high_value")
        if result.profile_action_signal >= 60.0:
            result.profile_action_flags.append("profile_action_high_value")
            if "profile_action_high_value" not in result.quality_flags:
                result.quality_flags.append("profile_action_high_value")
        elif result.profile_action_signal >= 35.0:
            result.profile_action_flags.append("profile_action_signal")
            if "profile_action_signal" not in result.quality_flags:
                result.quality_flags.append("profile_action_signal")
        for availability_flag in result.availability_action_flags:
            quality_flag = f"availability_action:{availability_flag}"
            if quality_flag not in result.quality_flags:
                result.quality_flags.append(quality_flag)
        if result.availability_intent_score >= 70.0 and "availability_high_intent" not in result.quality_flags:
            result.quality_flags.append("availability_high_intent")
        elif result.availability_intent_score >= 55.0 and "availability_review" not in result.quality_flags:
            result.quality_flags.append("availability_review")
        for payment_flag in result.payment_action_flags:
            quality_flag = f"payment_action:{payment_flag}"
            if quality_flag not in result.quality_flags:
                result.quality_flags.append(quality_flag)
        if result.payment_coverage_score >= 70.0 and "payment_high_intent" not in result.quality_flags:
            result.quality_flags.append("payment_high_intent")
        elif result.payment_coverage_score >= 55.0 and "payment_review" not in result.quality_flags:
            result.quality_flags.append("payment_review")
        for access_flag in result.access_convenience_flags:
            quality_flag = f"access_action:{access_flag}"
            if quality_flag not in result.quality_flags:
                result.quality_flags.append(quality_flag)
        if result.access_convenience_score >= 70.0 and "access_high_intent" not in result.quality_flags:
            result.quality_flags.append("access_high_intent")
        elif result.access_convenience_score >= 55.0 and "access_review" not in result.quality_flags:
            result.quality_flags.append("access_review")
        for review_flag in result.review_action_flags:
            quality_flag = f"review_action:{review_flag}"
            if quality_flag not in result.quality_flags:
                result.quality_flags.append(quality_flag)
        if result.review_surface_score >= 70.0 and "review_surface_high_value" not in result.quality_flags:
            result.quality_flags.append("review_surface_high_value")
        if result.reputation_risk_score >= 70.0:
            result.grade = self._cap_grade(result.grade, "B")
            result.high_value_longtail = False
            if "reputation_high_risk_review" not in result.quality_flags:
                result.quality_flags.append("reputation_high_risk_review")
        elif result.reputation_risk_score >= 40.0 and "reputation_review_required" not in result.quality_flags:
            result.grade = self._cap_grade(result.grade, "B")
            result.quality_flags.append("reputation_review_required")
        for brand_flag in result.brand_action_flags:
            quality_flag = f"brand_action:{brand_flag}"
            if quality_flag not in result.quality_flags:
                result.quality_flags.append(quality_flag)
        if result.brand_intent_type in {"competitor_brand", "competitor_comparison", "own_vs_competitor"}:
            result.grade = self._cap_grade(result.grade, "B")
            result.high_value_longtail = False
            if "competitor_brand_review_required" not in result.quality_flags:
                result.quality_flags.append("competitor_brand_review_required")
        elif result.brand_intent_type == "own_brand_defense" and "own_brand_defense" not in result.quality_flags:
            result.quality_flags.append("own_brand_defense")
        if result.medical_ad_risk_score >= 70.0:
            result.grade = self._cap_grade(result.grade, "B")
            if "medical_ad_high_risk" not in result.quality_flags:
                result.quality_flags.append("medical_ad_high_risk")
        elif result.medical_ad_risk_score >= 40.0 and "medical_ad_review_required" not in result.quality_flags:
            result.quality_flags.append("medical_ad_review_required")
        has_real_volume = result.search_volume > 0 and "missing_real_volume" not in (result.quality_flags or [])
        result.verification_score = self._calculate_verification_score(
            result.keyword,
            result.search_volume,
            result.document_count,
            len(signals),
            has_real_volume,
            result.business_core,
        )
        ad_value_signal = self._calculate_ad_value_signal(ad_metrics)
        if ad_value_signal >= 65:
            result.verification_score = min(100.0, result.verification_score + min(8.0, ad_value_signal / 12.0))
        if inbound_value_signal >= 30:
            result.verification_score = min(100.0, result.verification_score + min(14.0, inbound_value_signal / 7.0))
        if rank_gap_signal >= 55.0:
            result.verification_score = min(100.0, result.verification_score + min(10.0, rank_gap_signal / 10.0))
        if community_signal >= 40.0:
            result.verification_score = min(100.0, result.verification_score + min(12.0, community_signal / 8.0))
        if conversion_signal >= 35.0:
            result.verification_score = min(100.0, result.verification_score + min(18.0, conversion_signal / 5.5))
        if profile_action_signal >= 35.0:
            result.verification_score = min(100.0, result.verification_score + min(16.0, profile_action_signal / 5.0))
        if result.availability_intent_score >= 55.0:
            result.verification_score = min(100.0, result.verification_score + min(8.0, result.availability_intent_score / 12.0))
        if result.payment_coverage_score >= 55.0:
            result.verification_score = min(100.0, result.verification_score + min(9.0, result.payment_coverage_score / 11.0))
        if result.access_convenience_score >= 55.0:
            result.verification_score = min(100.0, result.verification_score + min(8.0, result.access_convenience_score / 12.0))
        value_profile = self._calculate_keyword_value_profile(
            result.keyword,
            category=result.category,
            search_intent=result.search_intent,
            search_volume=result.search_volume,
            difficulty=result.difficulty,
            opportunity=result.opportunity,
            document_count=result.document_count,
            source_signal_count=len(signals),
            has_real_volume=has_real_volume,
            business_core=result.business_core,
            medical_ad_risk_score=result.medical_ad_risk_score,
            content_actionability_score=result.content_actionability_score,
            local_surface_score=result.local_surface_score,
            brand_intent_type=result.brand_intent_type,
            competitor_brand_risk_score=result.competitor_brand_risk_score,
            review_surface_score=result.review_surface_score,
            reputation_risk_score=result.reputation_risk_score,
            review_intent_type=result.review_intent_type,
            profile_action_signal=result.profile_action_signal,
            availability_intent_score=result.availability_intent_score,
            availability_intent_type=result.availability_intent_type,
            payment_coverage_score=result.payment_coverage_score,
            payment_coverage_type=result.payment_coverage_type,
            access_convenience_score=result.access_convenience_score,
            access_convenience_type=result.access_convenience_type,
        )
        if (
            ad_value_signal >= 55 or inbound_value_signal >= 30 or mobile_share >= 0.65
            or rank_gap_signal >= 55.0 or community_signal >= 40.0 or conversion_signal >= 35.0
            or profile_action_signal >= 35.0 or result.availability_intent_score >= 55.0
            or result.payment_coverage_score >= 55.0
            or result.access_convenience_score >= 55.0
        ):
            value_profile = dict(value_profile)
            ad_bonus = min(12.0, (ad_value_signal - 50.0) / 4.0) if ad_value_signal >= 55 else 0.0
            inbound_bonus = min(14.0, inbound_value_signal / 7.0) if inbound_value_signal >= 30 else 0.0
            mobile_bonus = 5.0 if mobile_share >= 0.65 and self._collector_or_default()._is_in_target_region(result.keyword) else 0.0
            rank_bonus = min(10.0, rank_gap_signal / 12.0) if rank_gap_signal >= 55.0 else 0.0
            community_bonus = min(14.0, community_signal / 7.0) if community_signal >= 40.0 else 0.0
            conversion_bonus = min(20.0, conversion_signal / 4.5) if conversion_signal >= 35.0 else 0.0
            profile_action_bonus = min(18.0, profile_action_signal / 4.5) if profile_action_signal >= 35.0 else 0.0
            availability_bonus = min(12.0, result.availability_intent_score / 8.0) if result.availability_intent_score >= 55.0 else 0.0
            payment_bonus = min(14.0, result.payment_coverage_score / 7.0) if result.payment_coverage_score >= 55.0 else 0.0
            access_bonus = min(12.0, result.access_convenience_score / 8.0) if result.access_convenience_score >= 55.0 else 0.0
            value_profile["business_value_score"] = min(
                100.0,
                float(value_profile["business_value_score"]) + ad_bonus + inbound_bonus + mobile_bonus + rank_bonus + community_bonus + conversion_bonus + profile_action_bonus + availability_bonus + payment_bonus + access_bonus,
            )
            if (
                float(value_profile["longtail_score"]) >= 60.0
                and float(value_profile["business_value_score"]) >= 75.0
                and (
                    ad_value_signal >= 55 or inbound_value_signal >= 30 or mobile_share >= 0.75
                    or rank_gap_signal >= 70.0 or community_signal >= 60.0 or conversion_signal >= 45.0
                    or profile_action_signal >= 60.0 or result.availability_intent_score >= 70.0
                    or result.payment_coverage_score >= 70.0
                    or result.access_convenience_score >= 70.0
                )
            ):
                value_profile["high_value_longtail"] = True
        result.longtail_score = float(value_profile["longtail_score"])
        result.business_value_score = float(value_profile["business_value_score"])
        result.high_value_longtail = bool(value_profile["high_value_longtail"])
        if result.local_service_fit_score < 65.0 or bool(service_fit["hard_negative"]):
            result.high_value_longtail = False
        if result.content_actionability_score < 58.0:
            if (
                result.local_surface_score < 70.0
                and result.review_surface_score < 70.0
                and result.profile_action_signal < 60.0
                and result.availability_intent_score < 70.0
                and result.payment_coverage_score < 70.0
                and result.access_convenience_score < 70.0
            ):
                result.high_value_longtail = False
        if result.medical_ad_risk_score >= 70.0:
            result.high_value_longtail = False
        if result.reputation_risk_score >= 70.0:
            result.high_value_longtail = False
        if result.brand_intent_type != "generic":
            result.high_value_longtail = False
        value_profile = dict(value_profile)
        value_profile["high_value_longtail"] = result.high_value_longtail
        result.grade, result.quality_flags = self._promote_grade_for_execution_fit(
            result.grade,
            value_profile,
            has_real_volume=has_real_volume,
            search_volume=result.search_volume,
            verification_score=result.verification_score,
            source_signal_count=len(signals),
            category=result.category,
            community_signal=result.community_signal,
            conversion_signal=result.conversion_signal,
            profile_action_signal=result.profile_action_signal,
            local_service_fit_score=result.local_service_fit_score,
            content_actionability_score=result.content_actionability_score,
            local_surface_score=result.local_surface_score,
            review_surface_score=result.review_surface_score,
            availability_intent_score=result.availability_intent_score,
            payment_coverage_score=result.payment_coverage_score,
            access_convenience_score=result.access_convenience_score,
            medical_ad_risk_score=result.medical_ad_risk_score,
            reputation_risk_score=result.reputation_risk_score,
            brand_intent_type=result.brand_intent_type,
            quality_flags=result.quality_flags,
        )

    @staticmethod
    def _calculate_verification_score(
        keyword: str,
        search_volume: int,
        document_count: int,
        source_signal_count: int,
        has_real_volume: bool,
        business_core: bool,
    ) -> float:
        score = 0.0
        if has_real_volume:
            score += 28.0
            if search_volume >= 1000:
                score += 14.0
            elif search_volume >= 100:
                score += 9.0
            elif search_volume >= 20:
                score += 5.0

        if document_count >= 1000:
            score += 20.0
        elif document_count >= 100:
            score += 15.0
        elif document_count >= 10:
            score += 10.0
        elif document_count > 0:
            score += 4.0

        score += min(26.0, max(0, source_signal_count) * 8.0)

        if business_core:
            score += 10.0
        if len((keyword or "").split()) >= 4:
            score += 4.0

        return round(min(score, 100.0), 2)

    @staticmethod
    def _cap_grade(grade: str, cap: str) -> str:
        order = {"S": 0, "A": 1, "B": 2, "C": 3}
        reverse = {0: "S", 1: "A", 2: "B", 3: "C"}
        if grade not in order or cap not in order:
            return grade
        return reverse[max(order[grade], order[cap])]

    def _apply_quality_grade_guard(
        self,
        grade: str,
        kei_grade: str,
        search_volume: int,
        document_count: int,
        verification_score: float,
        source_signal_count: int,
        has_real_volume: bool,
    ) -> Tuple[str, str, List[str]]:
        flags: List[str] = []
        adjusted_grade = grade
        adjusted_kei_grade = kei_grade

        if not has_real_volume:
            flags.append("missing_real_volume")
            adjusted_grade = "C"
            adjusted_kei_grade = "C"

        if document_count <= 0:
            flags.append("missing_document_count")
            adjusted_grade = self._cap_grade(adjusted_grade, "B")
            adjusted_kei_grade = self._cap_grade(adjusted_kei_grade, "B")
        elif document_count < 10:
            flags.append("low_document_count")
            if search_volume < 100 or source_signal_count < 2:
                adjusted_grade = self._cap_grade(adjusted_grade, "B")
                adjusted_kei_grade = self._cap_grade(adjusted_kei_grade, "B")

        if verification_score < 45 and adjusted_grade in ("S", "A"):
            flags.append("low_verification_score")
            adjusted_grade = "B"
        elif verification_score < 60 and adjusted_grade == "S":
            flags.append("s_grade_needs_more_verification")
            adjusted_grade = "A"

        return adjusted_grade, adjusted_kei_grade, flags

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table_name: str) -> Set[str]:
        try:
            rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        except sqlite3.Error:
            return set()
        return {row[1] for row in rows}

    def _load_diversity_profile(self, lookback_scan_runs: int = 5) -> Dict[str, object]:
        profile = self._empty_diversity_profile()
        db_path = _get_db_path()
        if not os.path.exists(db_path):
            return profile

        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                keyword_cols = self._table_columns(conn, "keyword_insights")
                if keyword_cols:
                    last_scan_expr = None
                    if {"last_scan_run_id", "scan_run_id"}.issubset(keyword_cols):
                        last_scan_expr = "COALESCE(last_scan_run_id, scan_run_id, 0)"
                    elif "last_scan_run_id" in keyword_cols:
                        last_scan_expr = "COALESCE(last_scan_run_id, 0)"
                    elif "scan_run_id" in keyword_cols:
                        last_scan_expr = "COALESCE(scan_run_id, 0)"

                    category_expr = "category" if "category" in keyword_cols else "''"
                    intent_expr = "search_intent" if "search_intent" in keyword_cols else "''"
                    where_clause = ""
                    params: Tuple[int, ...] = ()
                    if last_scan_expr:
                        max_scan = conn.execute(f"SELECT MAX({last_scan_expr}) FROM keyword_insights").fetchone()[0] or 0
                        min_scan = max(0, int(max_scan) - lookback_scan_runs + 1)
                        where_clause = f"WHERE {last_scan_expr} >= ?"
                        params = (min_scan,)

                    rows = conn.execute(
                        f"""
                        SELECT keyword, {category_expr} AS category, {intent_expr} AS search_intent
                        FROM keyword_insights
                        {where_clause}
                        ORDER BY id DESC
                        LIMIT 2000
                        """,
                        params,
                    ).fetchall()

                    for row in rows:
                        keyword = row["keyword"] or ""
                        norm = self._normalize_keyword_for_history(keyword)
                        if norm:
                            profile["keyword_norms"].add(norm)
                        category = row["category"] or ""
                        intent = row["search_intent"] or "unknown"
                        if category:
                            profile["category_counts"][category] += 1
                        if intent:
                            profile["intent_counts"][intent] += 1

                viral_cols = self._table_columns(conn, "viral_targets")
                if "matched_keyword" in viral_cols:
                    scan_count_expr = "COALESCE(scan_count, 1)" if "scan_count" in viral_cols else "1"
                    if {"matched_keyword_category", "category"}.issubset(viral_cols):
                        category_expr = "COALESCE(matched_keyword_category, category, '')"
                    elif "matched_keyword_category" in viral_cols:
                        category_expr = "matched_keyword_category"
                    elif "category" in viral_cols:
                        category_expr = "category"
                    else:
                        category_expr = "''"
                    rows = conn.execute(
                        f"""
                        SELECT matched_keyword,
                               {category_expr} AS category,
                               COUNT(*) AS total_count,
                               SUM(CASE WHEN {scan_count_expr} > 1 THEN 1 ELSE 0 END) AS revisited_count
                        FROM viral_targets
                        WHERE matched_keyword IS NOT NULL
                          AND matched_keyword != ''
                        GROUP BY matched_keyword, category
                        """
                    ).fetchall()
                    for row in rows:
                        keyword = row["matched_keyword"] or ""
                        total = int(row["total_count"] or 0)
                        revisited = int(row["revisited_count"] or 0)
                        norm = self._normalize_keyword_for_history(keyword)
                        if not norm:
                            continue
                        profile["viral_keyword_stats"][norm] = {
                            "total_count": total,
                            "revisit_rate": (revisited / total) if total else 0.0,
                        }
                        category = row["category"] or ""
                        if category:
                            profile["category_counts"][category] += total
        except sqlite3.Error as e:
            print(f"⚠️ 다양성 히스토리 로드 실패: {e}")

        return profile

    def _load_discovery_audit_gap_seeds(self, max_seeds: int = 24) -> List[str]:
        """Pathfinder discovery_audit의 next_exploration_queue를 다음 런 시드로 소비.

        감사가 blind-spot(서비스 앵커/여정 단계/동네 커버리지 결손)을 지목해도
        아무도 듣지 않던 write-only 루프를 닫는다. 브로커/DB가 얇거나 실패하면
        조용히 빈 리스트 — 기존 시드 구성에는 영향이 없다.
        """
        try:
            from core_services.pathfinder_insight_broker import PathfinderInsightBroker
            broker = PathfinderInsightBroker(_get_db_path())
            cards = broker.keyword_cards(limit=80)
            if not cards:
                return []
            treatment = broker._treatment_intelligence(cards, selected_cards=cards)
            audit = broker._discovery_audit(
                cards,
                selected_cards=cards,
                treatment_intelligence=treatment,
            )
            queue = [
                str(seed).strip()
                for seed in (audit.get("next_exploration_queue") or [])
                if str(seed or "").strip()
            ]
        except Exception as e:
            print(f"⚠️ 디스커버리 감사 시드 로드 실패 (무시): {e}")
            return []

        seen = set(getattr(self, "base_seeds", []) or [])
        collector = getattr(self, "collector", None)
        selected: List[str] = []
        for seed in queue:
            if seed in seen:
                continue
            if not GYULIM_KEYWORD_PROFILE.is_target_region(seed, include_nearby=True):
                continue
            # 감사 큐에는 '동네+한방+거래접미사' 같은 무앵커 조합도 섞인다 —
            # 라이브 수율 증거(0.3%)가 있는 낭비 패턴이라 서비스 앵커를 강제한다.
            if collector is not None:
                try:
                    if not collector._is_valid_keyword(seed) or not collector.is_focus_candidate(seed):
                        continue
                except Exception:
                    pass
            selected.append(seed)
            seen.add(seed)
            if len(selected) >= max_seeds:
                break
        return selected

    def _build_history_aware_exploration_seeds(self, max_seeds: int = 48) -> List[str]:
        profile = getattr(self, "diversity_profile", self._empty_diversity_profile())
        keyword_norms: Set[str] = profile.get("keyword_norms", set())
        category_counts: Counter = profile.get("category_counts", Counter())
        intent_counts: Counter = profile.get("intent_counts", Counter())

        category_terms = {
            profile.category: list(
                dict.fromkeys(
                    list(self.CATEGORY_CANONICAL_SERVICES.get(profile.category, ()))
                    + list(profile.seed_terms[:4])
                    + list(profile.core_tokens[:3])
                )
            )
            for profile in GYULIM_KEYWORD_PROFILE.profiles
        }
        intent_suffixes = [
            ("transactional", "상담"),
            ("transactional", "예약"),
            ("transactional", "가격"),
            ("commercial", "추천"),
            ("commercial", "후기"),
            ("informational", "효과"),
            ("red_flag", "부작용"),
            ("validation", "진짜"),
            ("comparison", "비교"),
        ]
        intent_suffixes.sort(key=lambda item: intent_counts.get(item[0], 0))
        diverse_suffixes = []
        used_intents = set()
        for item in intent_suffixes:
            if item[0] in used_intents:
                continue
            diverse_suffixes.append(item)
            used_intents.add(item[0])
        for item in intent_suffixes:
            if item not in diverse_suffixes:
                diverse_suffixes.append(item)
        intent_suffixes = diverse_suffixes

        region_pool = [GYULIM_KEYWORD_PROFILE.primary_region]
        for region in self.collector.neighborhoods[:8]:
            if region not in region_pool:
                region_pool.append(region)

        category_order = sorted(category_terms, key=lambda category: category_counts.get(category, 0))
        seeds: List[str] = []
        seen: Set[str] = set()

        def add_seed(seed: str) -> None:
            norm = self._normalize_keyword_for_history(seed)
            if not norm or norm in seen or norm in keyword_norms:
                return
            category = self.collector._detect_category(seed)
            if self.collector.low_business_value_reason(seed, category):
                return
            if not self.collector._is_valid_keyword(seed) and not self.collector.is_focus_candidate(seed):
                return
            seen.add(norm)
            seeds.append(seed)

        for category in category_order:
            terms = category_terms[category]
            for idx, term in enumerate(terms):
                region = region_pool[(len(seeds) + idx) % len(region_pool)]
                add_seed(f"{region} {term}")
                for _, suffix in intent_suffixes[:3]:
                    add_seed(f"{region} {term} {suffix}")
                    if len(seeds) >= max_seeds:
                        return seeds

        return seeds[:max_seeds]

    def _apply_history_novelty_adjustment(
        self,
        keyword: str,
        priority: float,
        category: str,
        search_intent: str,
    ) -> float:
        profile = getattr(self, "diversity_profile", self._empty_diversity_profile())
        norm = self._normalize_keyword_for_history(keyword)
        keyword_norms: Set[str] = profile.get("keyword_norms", set())
        category_counts: Counter = profile.get("category_counts", Counter())
        intent_counts: Counter = profile.get("intent_counts", Counter())
        viral_stats: Dict[str, dict] = profile.get("viral_keyword_stats", {})

        penalty = 0.0
        if norm in keyword_norms:
            penalty += 8.0

        stats = viral_stats.get(norm)
        if stats:
            penalty += min(35.0, float(stats.get("total_count", 0)) * 1.2)
            penalty += min(30.0, float(stats.get("revisit_rate", 0.0)) * 30.0)

        category_total = sum(category_counts.values())
        if category_total and category:
            category_share = category_counts.get(category, 0) / category_total
            if category_share > 0.35:
                penalty += min(8.0, (category_share - 0.35) * 20.0)

        intent_total = sum(intent_counts.values())
        if intent_total and search_intent:
            intent_share = intent_counts.get(search_intent, 0) / intent_total
            if intent_share > 0.45:
                penalty += min(6.0, (intent_share - 0.45) * 18.0)

        novelty_bonus = 6.0 if norm and norm not in keyword_norms and norm not in viral_stats else 0.0
        return max(0.0, float(priority or 0.0) - penalty + novelty_bonus)

    def _select_expansion_keywords(
        self,
        grades: Set[str],
        limit: Optional[int] = None,
        max_per_category: int = 12,
    ) -> List[str]:
        candidates = [r for r in self.collected.values() if r.grade in grades]
        candidates.sort(
            key=lambda r: (
                1 if getattr(r, "high_value_longtail", False) else 0,
                float(getattr(r, "business_value_score", 0.0) or 0.0),
                float(getattr(r, "longtail_score", 0.0) or 0.0),
                float(r.priority_score or 0.0),
            ),
            reverse=True,
        )

        selected: List[KeywordResult] = []
        deferred: List[KeywordResult] = []
        category_counts: Counter = Counter()

        for result in candidates:
            category = result.category or "기타"
            if category_counts[category] < max_per_category:
                selected.append(result)
                category_counts[category] += 1
            else:
                deferred.append(result)
            if limit and len(selected) >= limit:
                return [r.keyword for r in selected[:limit]]

        if limit and len(selected) < limit:
            selected.extend(deferred[: limit - len(selected)])
        elif not limit:
            selected.extend(deferred)

        return [r.keyword for r in selected[:limit] if r.keyword] if limit else [r.keyword for r in selected if r.keyword]

    def _collect_ad_related_keywords(
        self,
        seed_keywords: List[str],
        source: str = "round1_ad_related",
        max_seeds: int = 50,
        max_keywords: int = 300,
        min_volume: int = 10,
    ) -> List[str]:
        """Use Naver SearchAd related-keyword payload as a validated source."""
        self._ensure_quality_tracking()
        if not self.has_ad_api or not self.ad_manager or not seed_keywords:
            return []

        unique_seeds: List[str] = []
        seen_seed_norms: Set[str] = set()
        for keyword in seed_keywords:
            norm = self._normalize_keyword_for_history(keyword)
            if not norm or norm in seen_seed_norms:
                continue
            seen_seed_norms.add(norm)
            unique_seeds.append(keyword)
            if len(unique_seeds) >= max_seeds:
                break

        try:
            related_volume_map = self.ad_manager.get_keyword_volumes(unique_seeds) or {}
            if hasattr(self.ad_manager, "get_last_keyword_metrics"):
                self._merge_ad_keyword_metrics(self.ad_manager.get_last_keyword_metrics())
        except Exception as e:
            print(f"   ⚠️ 검색광고 연관어 조회 실패: {e}")
            return []

        if not related_volume_map:
            return []

        self.volume_hints.update(related_volume_map)
        seed_norms = {self._normalize_keyword_for_history(seed) for seed in unique_seeds}
        candidates = sorted(
            related_volume_map.items(),
            key=lambda item: int(item[1] or 0),
            reverse=True,
        )

        related_keywords: List[str] = []
        seen_related: Set[str] = set()
        for keyword, volume in candidates:
            norm = self._normalize_keyword_for_history(keyword)
            if not norm or norm in seed_norms or norm in seen_related:
                continue
            if int(volume or 0) < min_volume:
                self._record_rejection(source, "ad_related_low_volume")
                continue
            self._record_source_signal(keyword, source)
            if not self.collector._is_valid_keyword(keyword):
                self._record_rejection(source, "ad_related_invalid_scope")
                continue
            if not self.collector.is_focus_candidate(keyword):
                self._record_rejection(source, "ad_related_non_focus")
                continue
            seen_related.add(norm)
            related_keywords.append(keyword)
            if len(related_keywords) >= max_keywords:
                break

        return related_keywords

    def _calculate_seasonality_score(self, keyword: str) -> float:
        """현재 시즌에 맞는 키워드인지 점수화 (0-100)"""
        current_month = datetime.now().month
        keyword_lower = keyword.lower()

        # 계절별 키워드 매핑
        season_keywords = {
            # 봄 (3-5월)
            'spring': ['환절기', '봄', '황사', '미세먼지', '꽃가루'],
            # 여름 (6-8월)
            'summer': ['여름', '휴가', '다이어트', '비키니', '땀', '열사병'],
            # 가을 (9-11월)
            'fall': ['가을', '환절기', '추석', '수능'],
            # 겨울 (12-2월)
            'winter': ['겨울', '설', '새해', '신년', '연말', '빙판'],
        }

        # 현재 시즌 결정
        if current_month in [3, 4, 5]:
            current_season = 'spring'
        elif current_month in [6, 7, 8]:
            current_season = 'summer'
        elif current_month in [9, 10, 11]:
            current_season = 'fall'
        else:
            current_season = 'winter'

        # 현재 시즌 키워드 매칭 시 높은 점수
        if any(sk in keyword_lower for sk in season_keywords[current_season]):
            return 90.0

        # 다음 시즌 키워드도 약간의 점수
        next_seasons = {
            'spring': 'summer', 'summer': 'fall',
            'fall': 'winter', 'winter': 'spring'
        }
        next_season = next_seasons[current_season]
        if any(sk in keyword_lower for sk in season_keywords[next_season]):
            return 60.0

        # 시즌과 무관한 키워드
        return 50.0

    def _calculate_business_relevance(self, keyword: str) -> float:
        """비즈니스 관련도 점수 (0-100)"""
        collector = self._collector_or_default()
        keyword_lower = keyword.lower()
        score = 0.0
        category = collector._detect_category(keyword)
        profile_score = GYULIM_KEYWORD_PROFILE.business_relevance_score(keyword, category)

        # Tier 1: 활성 프로필의 핵심 서비스 키워드 (+40)
        tier1 = list(getattr(GYULIM_KEYWORD_PROFILE, "hanbang_indicators", ()))
        if any(t in keyword_lower for t in tier1):
            score += 40

        # Tier 2: 주요 시술/진료 (+30)
        tier2 = list(getattr(GYULIM_KEYWORD_PROFILE, "hanbang_keywords", ()))
        if any(t in keyword_lower for t in tier2):
            score += 30

        # Tier 3: 타깃 지역 (+20)
        tier3 = (
            list(getattr(GYULIM_KEYWORD_PROFILE, "cheongju_regions", ()))
            + list(getattr(GYULIM_KEYWORD_PROFILE, "neighborhoods", ()))
            + list(getattr(GYULIM_KEYWORD_PROFILE, "nearby_regions", ()))
        )
        if any(t in keyword_lower for t in tier3):
            score += 20

        # Tier 4: 전환 의도 (+15)
        tier4 = [
            '가격', '비용', '후기', '추천', '예약', '잘하는', '상담',
            '보험', '실비', '자보', '자동차보험', '입원', '치료비',
        ]
        if any(t in keyword_lower for t in tier4):
            score += 15

        if collector._has_direct_service_anchor(keyword, category):
            score += 10
        if collector.low_business_value_reason(keyword, category):
            score -= 40
        service_fit_score = float(
            self._calculate_service_fit_profile(keyword, category).get("score", 0.0) or 0.0
        )
        score = (score * 0.75) + (service_fit_score * 0.25)
        score = max(score, profile_score)
        if service_fit_score < 45.0:
            score = min(score, service_fit_score)

        return max(0.0, min(score, 100.0))

    def _calculate_priority(self, difficulty: int, opportunity: int, keyword: str,
                             search_volume: int = 0, kei: float = 0.0,
                             trend_slope: float = 0.0,
                             category: Optional[str] = None,
                             search_intent: Optional[str] = None,
                             has_real_volume: Optional[bool] = None,
                             business_core: Optional[bool] = None,
                             source_signal_count: int = 1,
                             longtail_score: Optional[float] = None,
                             business_value_score: Optional[float] = None,
                             local_surface_score: Optional[float] = None,
                             review_surface_score: Optional[float] = None,
                             profile_action_signal: Optional[float] = None,
                             availability_intent_score: Optional[float] = None,
                             payment_coverage_score: Optional[float] = None,
                             access_convenience_score: Optional[float] = None) -> float:
        """
        MF-KEI 5.0 점수 계산 (트렌드 + 계절성 + 비즈니스 관련도 반영)

        공식: KEI + 기회 + 난이도 + 트렌드 + 계절성 + 관련도 + 고가치 롱테일

        Args:
            difficulty: SERP 난이도 (0-100)
            opportunity: 진입 기회 (0-100)
            keyword: 키워드
            search_volume: 월간 검색량
            kei: 실제 KEI 값 (검색량² / 문서수)
            trend_slope: 트렌드 기울기 (양수=상승, 음수=하락)

        Returns:
            우선순위 점수 (0-200)
        """
        import math

        # 1. KEI 점수 (로그 스케일 정규화)
        if kei > 0:
            kei_score = min(100, (math.log10(kei + 1) / math.log10(1000)) * 100)
        else:
            kei_score = 0

        # 2. 기회 점수
        opportunity_score = opportunity

        # 3. 난이도 점수 (낮을수록 좋음)
        difficulty_score = 100 - difficulty

        # 4. 트렌드 점수 (기울기 기반)
        # slope: -1.0 ~ +1.0 범위를 0 ~ 100으로 변환
        trend_score = 50 + (trend_slope * 50)  # -1.0→0, 0→50, +1.0→100
        trend_score = max(0, min(100, trend_score))

        # 5. 계절성 + 비즈니스 관련도 + 롱테일 가치 점수
        seasonality_score = self._calculate_seasonality_score(keyword)
        relevance_score = self._calculate_business_relevance(keyword)
        if longtail_score is None or business_value_score is None:
            value_profile = self._calculate_keyword_value_profile(
                keyword,
                category=category,
                search_intent=search_intent,
                search_volume=search_volume,
                difficulty=difficulty,
                opportunity=opportunity,
                source_signal_count=source_signal_count,
                has_real_volume=has_real_volume,
                business_core=business_core,
                local_surface_score=local_surface_score,
                review_surface_score=review_surface_score,
                profile_action_signal=profile_action_signal,
                availability_intent_score=availability_intent_score,
                payment_coverage_score=payment_coverage_score,
                access_convenience_score=access_convenience_score,
            )
            longtail_score = float(value_profile["longtail_score"])
            business_value_score = float(value_profile["business_value_score"])
            local_surface_score = float(value_profile.get("local_surface_score", local_surface_score or 0.0))
            review_surface_score = float(value_profile.get("review_surface_score", review_surface_score or 0.0))
            profile_action_signal = float(value_profile.get("profile_action_signal", profile_action_signal or 0.0))
            availability_intent_score = float(value_profile.get("availability_intent_score", availability_intent_score or 0.0))
            payment_coverage_score = float(value_profile.get("payment_coverage_score", payment_coverage_score or 0.0))
            access_convenience_score = float(value_profile.get("access_convenience_score", access_convenience_score or 0.0))
        if local_surface_score is None:
            local_surface_score = 0.0
        if review_surface_score is None:
            review_surface_score = 0.0
        if profile_action_signal is None:
            profile_action_signal = 0.0
        if availability_intent_score is None:
            availability_intent_score = 0.0
        if payment_coverage_score is None:
            payment_coverage_score = 0.0
        if access_convenience_score is None:
            access_convenience_score = 0.0

        # 6. MF-KEI 5.5 가중 평균
        base_score = (
            kei_score * 0.22 +
            opportunity_score * 0.22 +
            difficulty_score * 0.18 +
            trend_score * 0.10 +
            seasonality_score * 0.08 +
            relevance_score * 0.08 +
            float(business_value_score or 0.0) * 0.05 +
            float(longtail_score or 0.0) * 0.05 +
            float(local_surface_score or 0.0) * 0.02 +
            float(review_surface_score or 0.0) * 0.02 +
            float(profile_action_signal or 0.0) * 0.02 +
            float(availability_intent_score or 0.0) * 0.02 +
            float(payment_coverage_score or 0.0) * 0.02 +
            float(access_convenience_score or 0.0) * 0.02
        )

        # 7. 검색 의도 가중치. 저검색량 롱테일도 전환 의도가 명확하면 반영한다.
        intent_weight = 1.0
        if any(w in keyword for w in ["가격", "비용", "예약", "상담", "보험", "실비", "자보", "입원"]):
            intent_weight = 1.28
        elif any(w in keyword for w in ["후기", "추천", "잘하는", "솔직", "진짜", "비교"]):
            intent_weight = 1.16
        if float(longtail_score or 0.0) >= 68 and float(business_value_score or 0.0) >= 65:
            intent_weight += 0.08
        if float(local_surface_score or 0.0) >= 70:
            intent_weight += 0.05
        if float(review_surface_score or 0.0) >= 70:
            intent_weight += 0.04
        if float(profile_action_signal or 0.0) >= 60:
            intent_weight += 0.05
        if float(availability_intent_score or 0.0) >= 70:
            intent_weight += 0.05
        if float(payment_coverage_score or 0.0) >= 70:
            intent_weight += 0.05
        if float(access_convenience_score or 0.0) >= 70:
            intent_weight += 0.04
        if has_real_volume is False and search_volume <= 30:
            intent_weight = min(intent_weight, 1.08)

        # 최종 점수 (최대 300)
        return base_score * intent_weight

    def _analyze_and_add(self, keywords: List[str], source: str) -> int:
        """키워드 분석 후 추가, 새로 추가된 S/A급 개수 반환"""
        new_sa = 0
        filtered_count = 0
        self._ensure_quality_tracking()
        self.candidate_stats["input_by_source"][source] += len(keywords)

        # 1단계: 기본 유효성 필터링 + 띄어쓰기 변형 추가
        valid_keywords = []
        for kw in keywords:
            self._record_source_signal(kw, source)
            if kw in self.analyzed_keywords:
                self._record_rejection(source, "duplicate_signal")
                continue
            if not self.collector._is_valid_keyword(kw):
                self._record_rejection(source, "invalid_scope")
                continue
            valid_keywords.append(kw)
            self.analyzed_keywords.add(kw)

            # 띄어쓰기 변형 추가 (예: "가경동 한의원" → "가경동한의원")
            kw_no_space = kw.replace(" ", "")
            if kw_no_space != kw and kw_no_space not in self.analyzed_keywords:
                self._record_source_signal(kw_no_space, source)
                if self.collector._is_valid_keyword(kw_no_space):
                    valid_keywords.append(kw_no_space)
                    self.analyzed_keywords.add(kw_no_space)
                else:
                    self._record_rejection(source, "invalid_no_space_variant")

        if not valid_keywords:
            return 0

        # 2단계: 품질 필터 적용 (노이즈, 블랙리스트 제거)
        if self.quality_filter:
            passed, rejected = self.quality_filter.filter_batch(valid_keywords)
            filtered_count = len(rejected)
            if filtered_count > 0:
                print(f"   🧹 품질 필터: {filtered_count}개 제거")
            for _, reason in rejected:
                self._record_rejection(source, f"quality_{reason}")
            valid_keywords = passed

        # 진료/상담으로 이어지기 어려운 활동·상품성 롱테일은 SERP 분석 전에 제외한다.
        business_value_keywords = []
        low_value_count = 0
        for kw in valid_keywords:
            category = self.collector._detect_category(kw)
            low_value_reason = self.collector.low_business_value_reason(kw, category)
            if low_value_reason:
                low_value_count += 1
                self._record_rejection(source, low_value_reason)
                continue
            business_value_keywords.append(kw)

        if low_value_count:
            print(f"   🧭 사업가치 필터: 저전환 롱테일 {low_value_count}개 제외")
        valid_keywords = business_value_keywords

        # 기본 Legion은 미용/흉터/비대칭/다이어트/교통사고 입원실에 집중한다.
        focus_keywords = []
        non_focus_count = 0
        for kw in valid_keywords:
            category = self.collector._detect_category(kw)
            if self.collector.is_focus_candidate(kw, category):
                focus_keywords.append(kw)
            else:
                non_focus_count += 1
                self._record_rejection(source, "non_focus")

        if non_focus_count:
            print(f"   🎯 포커스 필터: 비핵심 진료군 {non_focus_count}개 제외")
        valid_keywords = focus_keywords

        if not valid_keywords:
            return 0
        self.candidate_stats["valid_by_source"][source] += len(valid_keywords)

        # 검색량 일괄 조회 (Naver Ad API)
        volume_map = {}
        if self.has_ad_api and self.ad_manager:
            try:
                result = self.ad_manager.get_keyword_volumes(valid_keywords)
                # None 방어 처리
                volume_map = result if result is not None else {}
                if hasattr(self.ad_manager, "get_last_keyword_metrics"):
                    self._merge_ad_keyword_metrics(self.ad_manager.get_last_keyword_metrics())
                if volume_map:
                    print(f"   📊 검색량 조회: {len(volume_map)}개")
            except Exception as e:
                print(f"   ⚠️ 검색량 조회 실패: {e}")
                volume_map = {}  # 예외 발생 시 빈 딕셔너리로 초기화

        # SERP 분석 (샘플링 + 배치 처리)
        if self.volume_hints:
            volume_map = {**self.volume_hints, **volume_map}
        use_sampling = len(valid_keywords) > 50  # 50개 이상이면 샘플링
        if use_sampling:
            serp_results = analyze_with_sampling(self.serp, valid_keywords)
        else:
            serp_results = self.serp.analyze_batch(valid_keywords, show_progress=True)

        # 키워드별 결과 저장
        for kw in valid_keywords:
            if kw in serp_results:
                serp_data = serp_results[kw]
                # 4-튜플 지원 (document_count 포함)
                if len(serp_data) == 4:
                    difficulty, opportunity, grade, document_count = serp_data
                else:
                    difficulty, opportunity, grade = serp_data
                    document_count = 0
            else:
                difficulty, opportunity, grade, document_count = 50, 50, "B", 0
            # docs가 0이면 네이버 API에서 보충 (KEI 신뢰성 회복)
            if document_count == 0:
                document_count = self.serp._fetch_document_count(kw)

            category = self.collector._detect_category(kw)

            # 검색량: API 결과 가져오기
            search_volume = volume_map.get(kw, 0)
            has_real_volume = search_volume > 0

            if search_volume == 0:
                # 공백 제거 버전으로 재시도
                search_volume = volume_map.get(kw.replace(" ", ""), 0)
                has_real_volume = search_volume > 0

            # ===== KEI 계산 =====
            if has_real_volume and document_count > 0:
                kei = calculate_real_kei(search_volume, document_count)
                kei_grade = assign_kei_grade(kei)
            else:
                kei = 0.0
                kei_grade = 'C'

            # 등급 재평가: SERP 등급과 KEI 등급 중 더 좋은 것 사용
            # ⚠️ 실제 검색량이 있는 경우만 S/A급 가능
            # ⚠️ 최소 검색량 조건 완화: S급=20, A급=10 (니치 키워드 포함)
            MIN_VOLUME_S = 20  # 개선: 50→20 (니치 키워드 포함)
            MIN_VOLUME_A = 10  # 개선: 30→10 (롱테일 키워드 포함)

            if has_real_volume:
                # KEI 기반 등급 우선 (단, 최소 검색량 조건 충족 시)
                if kei >= 500 and search_volume >= MIN_VOLUME_S:
                    grade = 'S'
                elif kei >= 200 and search_volume >= MIN_VOLUME_A:
                    grade = 'A'
                elif kei >= 50:
                    # SERP 기반 등급도 고려
                    if search_volume >= 100 and (opportunity >= 90 or difficulty < 15):
                        grade = 'S'
                    elif search_volume >= MIN_VOLUME_A and (opportunity >= 80 or difficulty < 20):
                        grade = 'A'
                    else:
                        grade = 'B'
                else:
                    # KEI가 낮으면 B급 이하
                    grade = 'B' if difficulty <= 70 else 'C'
            else:
                # [Q7] 검색량 데이터 없음 → SERP grade 무시하고 C급 강제
                # 이전: 'B'로 강등했지만 신뢰도 없는 데이터를 B급에 두는 건 부적절
                grade = 'C'
                search_volume = 30  # 점수 계산용 추정치

            # 도메인·지역 관련도 강등 (의료일반·비타깃 지역 누수 차단)
            grade, demote_reason = self.collector.apply_relevance_demotion(kw, grade)
            if demote_reason and kei_grade in ('S', 'A', 'B'):
                # KEI 기반 등급도 동일하게 강등 (보고서 일관성)
                if demote_reason == 'medical_general':
                    kei_grade = 'C'
                elif demote_reason in {'non_cheongju', 'non_target_region'}:
                    _order = ['S', 'A', 'B', 'C']
                    _idx = _order.index(kei_grade)
                    kei_grade = _order[min(_idx + 2, len(_order) - 1)]

            business_core = self.collector.is_business_core_keyword(kw, category)
            norm = self._normalize_keyword_for_history(kw)
            source_signals = sorted(self.keyword_source_signals.get(norm, {source}))
            if source not in source_signals:
                source_signals = sorted(set(source_signals + [source]))
            ad_metrics = self._get_ad_keyword_metrics(kw)
            inbound_metrics = self._get_inbound_query_metrics(kw)
            rank_metrics = self._get_owned_rank_metrics(kw)
            community_metrics = self._get_community_keyword_metrics(kw)
            conversion_metrics = self._get_conversion_keyword_metrics(kw)
            profile_action_metrics = self._get_profile_action_metrics(kw)
            ad_value_signal = self._calculate_ad_value_signal(ad_metrics)
            inbound_value_signal = self._calculate_inbound_value_signal(inbound_metrics)
            rank_gap_signal = float(rank_metrics.get("rank_gap_signal", 0.0) or 0.0)
            community_signal = float(community_metrics.get("community_signal", 0.0) or 0.0)
            conversion_signal = float(conversion_metrics.get("conversion_signal", 0.0) or 0.0)
            profile_action_signal = float(profile_action_metrics.get("profile_action_signal", 0.0) or 0.0)
            mobile_share = self._calculate_mobile_share(ad_metrics)
            inbound_sources = list(inbound_metrics.get("sources", []) or [])
            profile_action_sources = list(profile_action_metrics.get("sources", []) or [])
            if inbound_metrics and "inbound_query" not in source_signals:
                source_signals = sorted(set(source_signals + ["inbound_query"]))
            if rank_gap_signal >= 55.0 and "owned_rank_gap" not in source_signals:
                source_signals = sorted(set(source_signals + ["owned_rank_gap"]))
            if community_signal >= 40.0 and "community_demand" not in source_signals:
                source_signals = sorted(set(source_signals + ["community_demand"]))
            if conversion_signal >= 35.0 and "actual_call_conversion" not in source_signals:
                source_signals = sorted(set(source_signals + ["actual_call_conversion"]))
            if profile_action_signal >= 35.0 and "profile_action_conversion" not in source_signals:
                source_signals = sorted(set(source_signals + ["profile_action_conversion"]))
            verification_score = self._calculate_verification_score(
                kw,
                search_volume,
                document_count,
                len(source_signals),
                has_real_volume,
                business_core,
            )
            if ad_value_signal >= 65:
                verification_score = min(100.0, verification_score + min(8.0, ad_value_signal / 12.0))
            if inbound_value_signal >= 30:
                verification_score = min(100.0, verification_score + min(14.0, inbound_value_signal / 7.0))
            if rank_gap_signal >= 55.0:
                verification_score = min(100.0, verification_score + min(10.0, rank_gap_signal / 10.0))
            if community_signal >= 40.0:
                verification_score = min(100.0, verification_score + min(12.0, community_signal / 8.0))
            if conversion_signal >= 35.0:
                verification_score = min(100.0, verification_score + min(18.0, conversion_signal / 5.5))
            if profile_action_signal >= 35.0:
                verification_score = min(100.0, verification_score + min(16.0, profile_action_signal / 5.0))
            grade, kei_grade, quality_flags = self._apply_quality_grade_guard(
                grade,
                kei_grade,
                search_volume,
                document_count,
                verification_score,
                len(source_signals),
                has_real_volume,
            )
            if ad_value_signal >= 65 and "ad_value_signal" not in quality_flags:
                quality_flags.append("ad_value_signal")
            if inbound_value_signal >= 30 and "first_party_inbound_query" not in quality_flags:
                quality_flags.append("first_party_inbound_query")
            if mobile_share >= 0.65 and "mobile_local_signal" not in quality_flags:
                quality_flags.append("mobile_local_signal")
            rank_status = str(rank_metrics.get("rank_status", "unknown") or "unknown")
            if rank_gap_signal >= 55.0 and "owned_rank_gap" not in quality_flags:
                quality_flags.append("owned_rank_gap")
            elif rank_status == "owned_top3" and "owned_top_rank" not in quality_flags:
                quality_flags.append("owned_top_rank")
            if community_signal >= 40.0 and "community_demand_signal" not in quality_flags:
                quality_flags.append("community_demand_signal")
            if conversion_signal >= 35.0 and "actual_call_conversion" not in quality_flags:
                quality_flags.append("actual_call_conversion")
            profile_action_flags: List[str] = []
            if profile_action_signal >= 60.0:
                profile_action_flags.append("profile_action_high_value")
                if "profile_action_high_value" not in quality_flags:
                    quality_flags.append("profile_action_high_value")
            elif profile_action_signal >= 35.0:
                profile_action_flags.append("profile_action_signal")
                if "profile_action_signal" not in quality_flags:
                    quality_flags.append("profile_action_signal")

            # 검색 의도 분류
            search_intent = SearchIntentClassifier.classify(kw)
            medical_risk = self._calculate_medical_ad_risk_profile(kw, search_intent)
            medical_ad_risk_score = float(medical_risk["score"])
            medical_ad_risk_flags = list(medical_risk["flags"])
            content_feasibility_score = float(medical_risk["content_feasibility_score"])
            service_fit = self._calculate_service_fit_profile(kw, category, search_intent)
            local_service_fit_score = float(service_fit["score"])
            negative_intent_flags = list(service_fit["flags"])
            content_action = self._calculate_content_actionability_profile(
                kw,
                category,
                search_intent,
                medical_ad_risk_score=medical_ad_risk_score,
                service_fit_score=local_service_fit_score,
            )
            content_actionability_score = float(content_action["score"])
            recommended_content_type = str(content_action["recommended_content_type"])
            content_action_flags = list(content_action["flags"])
            local_surface = self._calculate_local_surface_profile(
                kw,
                category,
                search_intent,
                mobile_share=mobile_share,
                rank_gap_signal=rank_gap_signal,
                conversion_signal=max(conversion_signal, profile_action_signal),
                service_fit_score=local_service_fit_score,
            )
            local_surface_score = float(local_surface["score"])
            preferred_search_surface = str(local_surface["preferred_search_surface"])
            local_surface_flags = list(local_surface["flags"])
            availability_profile = self._calculate_availability_intent_profile(
                kw,
                category,
                search_intent,
                local_surface_score=local_surface_score,
                profile_action_signal=profile_action_signal,
                service_fit_score=local_service_fit_score,
            )
            availability_intent_score = float(availability_profile["availability_intent_score"])
            availability_intent_type = str(availability_profile["availability_intent_type"])
            availability_action_flags = list(availability_profile["flags"])
            if availability_intent_score >= 55.0:
                verification_score = min(100.0, verification_score + min(8.0, availability_intent_score / 12.0))
            payment_profile = self._calculate_payment_coverage_profile(
                kw,
                category,
                search_intent,
                service_fit_score=local_service_fit_score,
                medical_ad_risk_score=medical_ad_risk_score,
                local_surface_score=local_surface_score,
                profile_action_signal=profile_action_signal,
            )
            payment_coverage_score = float(payment_profile["payment_coverage_score"])
            payment_coverage_type = str(payment_profile["payment_coverage_type"])
            payment_action_flags = list(payment_profile["flags"])
            if payment_coverage_score >= 55.0:
                verification_score = min(100.0, verification_score + min(9.0, payment_coverage_score / 11.0))
            access_profile = self._calculate_access_convenience_profile(
                kw,
                category,
                search_intent,
                service_fit_score=local_service_fit_score,
                local_surface_score=local_surface_score,
                profile_action_signal=profile_action_signal,
                availability_intent_score=availability_intent_score,
            )
            access_convenience_score = float(access_profile["access_convenience_score"])
            access_convenience_type = str(access_profile["access_convenience_type"])
            access_convenience_flags = list(access_profile["flags"])
            if access_convenience_score >= 55.0:
                verification_score = min(100.0, verification_score + min(8.0, access_convenience_score / 12.0))
            brand_profile = self._calculate_brand_intent_profile(kw, search_intent)
            brand_intent_type = str(brand_profile["brand_intent_type"])
            brand_signal_score = float(brand_profile["brand_signal_score"])
            brand_mentions = list(brand_profile["brand_mentions"])
            competitor_brand_risk_score = float(brand_profile["competitor_brand_risk_score"])
            brand_action_flags = list(brand_profile["flags"])
            review_profile = self._calculate_review_reputation_profile(
                kw,
                search_intent,
                brand_intent_type=brand_intent_type,
                community_signal=community_signal,
                local_surface_score=local_surface_score,
                medical_ad_risk_score=medical_ad_risk_score,
            )
            review_surface_score = float(review_profile["review_surface_score"])
            reputation_risk_score = float(review_profile["reputation_risk_score"])
            review_intent_type = str(review_profile["review_intent_type"])
            review_action_flags = list(review_profile["flags"])
            if local_service_fit_score < 35.0:
                grade = self._cap_grade(grade, "C")
                kei_grade = self._cap_grade(kei_grade, "C")
                if "service_fit_block" not in quality_flags:
                    quality_flags.append("service_fit_block")
            elif local_service_fit_score < 60.0:
                grade = self._cap_grade(grade, "B")
                kei_grade = self._cap_grade(kei_grade, "B")
                if "service_fit_review" not in quality_flags:
                    quality_flags.append("service_fit_review")
            for negative_flag in negative_intent_flags:
                quality_flag = f"negative_intent:{negative_flag}"
                if quality_flag not in quality_flags:
                    quality_flags.append(quality_flag)
            if content_actionability_score < 45.0:
                grade = self._cap_grade(grade, "C")
                kei_grade = self._cap_grade(kei_grade, "C")
                if "content_low_actionability" not in quality_flags:
                    quality_flags.append("content_low_actionability")
            elif content_actionability_score < 60.0:
                grade = self._cap_grade(grade, "B")
                kei_grade = self._cap_grade(kei_grade, "B")
                if "content_action_review" not in quality_flags:
                    quality_flags.append("content_action_review")
            for action_flag in content_action_flags:
                quality_flag = f"content_action:{action_flag}"
                if quality_flag not in quality_flags:
                    quality_flags.append(quality_flag)
            if local_surface_score >= 70.0 and "local_surface_high_value" not in quality_flags:
                quality_flags.append("local_surface_high_value")
            for availability_flag in availability_action_flags:
                quality_flag = f"availability_action:{availability_flag}"
                if quality_flag not in quality_flags:
                    quality_flags.append(quality_flag)
            if availability_intent_score >= 70.0 and "availability_high_intent" not in quality_flags:
                quality_flags.append("availability_high_intent")
            elif availability_intent_score >= 55.0 and "availability_review" not in quality_flags:
                quality_flags.append("availability_review")
            for payment_flag in payment_action_flags:
                quality_flag = f"payment_action:{payment_flag}"
                if quality_flag not in quality_flags:
                    quality_flags.append(quality_flag)
            if payment_coverage_score >= 70.0 and "payment_high_intent" not in quality_flags:
                quality_flags.append("payment_high_intent")
            elif payment_coverage_score >= 55.0 and "payment_review" not in quality_flags:
                quality_flags.append("payment_review")
            for access_flag in access_convenience_flags:
                quality_flag = f"access_action:{access_flag}"
                if quality_flag not in quality_flags:
                    quality_flags.append(quality_flag)
            if access_convenience_score >= 70.0 and "access_high_intent" not in quality_flags:
                quality_flags.append("access_high_intent")
            elif access_convenience_score >= 55.0 and "access_review" not in quality_flags:
                quality_flags.append("access_review")
            for review_flag in review_action_flags:
                quality_flag = f"review_action:{review_flag}"
                if quality_flag not in quality_flags:
                    quality_flags.append(quality_flag)
            if review_surface_score >= 70.0 and "review_surface_high_value" not in quality_flags:
                quality_flags.append("review_surface_high_value")
            if reputation_risk_score >= 70.0:
                grade = self._cap_grade(grade, "B")
                kei_grade = self._cap_grade(kei_grade, "B")
                if "reputation_high_risk_review" not in quality_flags:
                    quality_flags.append("reputation_high_risk_review")
            elif reputation_risk_score >= 40.0:
                grade = self._cap_grade(grade, "B")
                kei_grade = self._cap_grade(kei_grade, "B")
                if "reputation_review_required" not in quality_flags:
                    quality_flags.append("reputation_review_required")
            for brand_flag in brand_action_flags:
                quality_flag = f"brand_action:{brand_flag}"
                if quality_flag not in quality_flags:
                    quality_flags.append(quality_flag)
            if brand_intent_type in {"competitor_brand", "competitor_comparison", "own_vs_competitor"}:
                grade = self._cap_grade(grade, "B")
                kei_grade = self._cap_grade(kei_grade, "B")
                if "competitor_brand_review_required" not in quality_flags:
                    quality_flags.append("competitor_brand_review_required")
            elif brand_intent_type == "own_brand_defense" and "own_brand_defense" not in quality_flags:
                quality_flags.append("own_brand_defense")
            if medical_ad_risk_score >= 70.0:
                grade = self._cap_grade(grade, "B")
                kei_grade = self._cap_grade(kei_grade, "B")
                if "medical_ad_high_risk" not in quality_flags:
                    quality_flags.append("medical_ad_high_risk")
            elif medical_ad_risk_score >= 40.0 and "medical_ad_review_required" not in quality_flags:
                quality_flags.append("medical_ad_review_required")
            value_profile = self._calculate_keyword_value_profile(
                kw,
                category=category,
                search_intent=search_intent,
                search_volume=search_volume,
                difficulty=difficulty,
                opportunity=opportunity,
                document_count=document_count,
                source_signal_count=len(source_signals),
                has_real_volume=has_real_volume,
                business_core=business_core,
                medical_ad_risk_score=medical_ad_risk_score,
                content_actionability_score=content_actionability_score,
                local_surface_score=local_surface_score,
                brand_intent_type=brand_intent_type,
                competitor_brand_risk_score=competitor_brand_risk_score,
                review_surface_score=review_surface_score,
                reputation_risk_score=reputation_risk_score,
                review_intent_type=review_intent_type,
                profile_action_signal=profile_action_signal,
                availability_intent_score=availability_intent_score,
                availability_intent_type=availability_intent_type,
                payment_coverage_score=payment_coverage_score,
                payment_coverage_type=payment_coverage_type,
                access_convenience_score=access_convenience_score,
                access_convenience_type=access_convenience_type,
            )
            if ad_value_signal >= 55:
                value_profile = dict(value_profile)
                value_profile["business_value_score"] = min(
                    100.0,
                    float(value_profile["business_value_score"]) + min(12.0, (ad_value_signal - 50.0) / 4.0),
                )
                if (
                    float(value_profile["longtail_score"]) >= 60.0
                    and float(value_profile["business_value_score"]) >= 75.0
                ):
                    value_profile["high_value_longtail"] = True
            if (
                inbound_value_signal >= 30 or mobile_share >= 0.65 or rank_gap_signal >= 55.0
                or community_signal >= 40.0 or conversion_signal >= 35.0 or profile_action_signal >= 35.0
                or availability_intent_score >= 55.0
                or payment_coverage_score >= 55.0
                or access_convenience_score >= 55.0
            ):
                value_profile = dict(value_profile)
                inbound_bonus = min(14.0, inbound_value_signal / 7.0) if inbound_value_signal >= 30 else 0.0
                mobile_bonus = 5.0 if mobile_share >= 0.65 and self.collector._is_in_target_region(kw) else 0.0
                rank_bonus = min(10.0, rank_gap_signal / 12.0) if rank_gap_signal >= 55.0 else 0.0
                community_bonus = min(14.0, community_signal / 7.0) if community_signal >= 40.0 else 0.0
                conversion_bonus = min(20.0, conversion_signal / 4.5) if conversion_signal >= 35.0 else 0.0
                profile_action_bonus = min(18.0, profile_action_signal / 4.5) if profile_action_signal >= 35.0 else 0.0
                availability_bonus = min(12.0, availability_intent_score / 8.0) if availability_intent_score >= 55.0 else 0.0
                payment_bonus = min(14.0, payment_coverage_score / 7.0) if payment_coverage_score >= 55.0 else 0.0
                access_bonus = min(12.0, access_convenience_score / 8.0) if access_convenience_score >= 55.0 else 0.0
                value_profile["business_value_score"] = min(
                    100.0,
                    float(value_profile["business_value_score"]) + inbound_bonus + mobile_bonus + rank_bonus + community_bonus + conversion_bonus + profile_action_bonus + availability_bonus + payment_bonus + access_bonus,
                )
                if (
                    float(value_profile["longtail_score"]) >= 60.0
                    and float(value_profile["business_value_score"]) >= 75.0
                    and (
                        inbound_value_signal >= 30 or mobile_share >= 0.75 or rank_gap_signal >= 70.0
                        or community_signal >= 60.0 or conversion_signal >= 45.0 or profile_action_signal >= 60.0
                        or availability_intent_score >= 70.0
                        or payment_coverage_score >= 70.0
                        or access_convenience_score >= 70.0
                    )
                ):
                    value_profile["high_value_longtail"] = True
            if medical_ad_risk_score >= 70.0:
                value_profile = dict(value_profile)
                value_profile["high_value_longtail"] = False
            if local_service_fit_score < 65.0 or bool(service_fit["hard_negative"]):
                value_profile = dict(value_profile)
                value_profile["high_value_longtail"] = False
            if content_actionability_score < 58.0:
                if (
                    local_surface_score < 70.0
                    and review_surface_score < 70.0
                    and profile_action_signal < 60.0
                    and availability_intent_score < 70.0
                    and payment_coverage_score < 70.0
                    and access_convenience_score < 70.0
                ):
                    value_profile = dict(value_profile)
                    value_profile["high_value_longtail"] = False
            if reputation_risk_score >= 70.0:
                value_profile = dict(value_profile)
                value_profile["high_value_longtail"] = False
            if brand_intent_type != "generic":
                value_profile = dict(value_profile)
                value_profile["high_value_longtail"] = False
            grade, quality_flags = self._promote_grade_for_high_value_longtail(
                grade,
                value_profile,
                has_real_volume,
                search_volume,
                difficulty,
                opportunity,
                verification_score,
                quality_flags,
            )
            grade, quality_flags = self._promote_grade_for_execution_fit(
                grade,
                value_profile,
                has_real_volume=has_real_volume,
                search_volume=search_volume,
                verification_score=verification_score,
                source_signal_count=len(source_signals),
                category=category,
                community_signal=community_signal,
                conversion_signal=conversion_signal,
                profile_action_signal=profile_action_signal,
                local_service_fit_score=local_service_fit_score,
                content_actionability_score=content_actionability_score,
                local_surface_score=local_surface_score,
                review_surface_score=review_surface_score,
                availability_intent_score=availability_intent_score,
                payment_coverage_score=payment_coverage_score,
                access_convenience_score=access_convenience_score,
                medical_ad_risk_score=medical_ad_risk_score,
                reputation_risk_score=reputation_risk_score,
                brand_intent_type=brand_intent_type,
                quality_flags=quality_flags,
            )

            # 우선순위 점수 계산 (KEI 포함) + 히스토리 기반 신규성 보정
            priority = self._calculate_priority(
                difficulty,
                opportunity,
                kw,
                search_volume,
                kei,
                category=category,
                search_intent=search_intent,
                has_real_volume=has_real_volume,
                business_core=business_core,
                source_signal_count=len(source_signals),
                longtail_score=float(value_profile["longtail_score"]),
                business_value_score=float(value_profile["business_value_score"]),
                local_surface_score=local_surface_score,
                review_surface_score=review_surface_score,
                profile_action_signal=profile_action_signal,
                availability_intent_score=availability_intent_score,
                payment_coverage_score=payment_coverage_score,
                access_convenience_score=access_convenience_score,
            )
            if inbound_value_signal >= 30:
                priority *= 1.0 + min(0.18, inbound_value_signal / 600.0)
            if mobile_share >= 0.65 and self.collector._is_in_target_region(kw):
                priority *= 1.04
            if rank_gap_signal >= 55.0:
                priority *= 1.0 + min(0.16, rank_gap_signal / 700.0)
            elif rank_status == "owned_top3":
                priority *= 0.92
            if community_signal >= 40.0:
                priority *= 1.0 + min(0.16, community_signal / 650.0)
            if conversion_signal >= 35.0:
                priority *= 1.0 + min(0.22, conversion_signal / 500.0)
            if profile_action_signal >= 60.0:
                priority *= 1.0 + min(0.18, profile_action_signal / 520.0)
            elif profile_action_signal >= 35.0:
                priority *= 1.05
            if availability_intent_score >= 70.0:
                priority *= 1.0 + min(0.14, availability_intent_score / 700.0)
            elif availability_intent_score >= 55.0:
                priority *= 1.04
            if payment_coverage_score >= 70.0:
                priority *= 1.0 + min(0.15, payment_coverage_score / 680.0)
            elif payment_coverage_score >= 55.0:
                priority *= 1.04
            if access_convenience_score >= 70.0:
                priority *= 1.0 + min(0.13, access_convenience_score / 720.0)
            elif access_convenience_score >= 55.0:
                priority *= 1.04
            if medical_ad_risk_score >= 70.0:
                priority *= 0.72
            elif medical_ad_risk_score >= 40.0:
                priority *= 0.86
            elif medical_ad_risk_score > 0:
                priority *= 0.95
            if local_service_fit_score < 35.0:
                priority *= 0.45
            elif local_service_fit_score < 60.0:
                priority *= 0.75
            elif local_service_fit_score >= 85.0:
                priority *= 1.04
            if content_actionability_score < 45.0:
                priority *= 0.58
            elif content_actionability_score < 60.0:
                priority *= 0.82
            elif content_actionability_score >= 82.0:
                priority *= 1.05
            if local_surface_score >= 70.0:
                priority *= 1.0 + min(0.14, local_surface_score / 700.0)
            elif local_surface_score >= 55.0:
                priority *= 1.04
            if review_surface_score >= 70.0:
                priority *= 1.0 + min(0.12, review_surface_score / 800.0)
            elif review_surface_score >= 55.0:
                priority *= 1.03
            if reputation_risk_score >= 70.0:
                priority *= 0.74
            elif reputation_risk_score >= 40.0:
                priority *= 0.88
            if brand_intent_type == "own_brand_defense":
                priority *= 0.96
            elif competitor_brand_risk_score >= 70.0:
                priority *= 0.68
            elif competitor_brand_risk_score >= 50.0:
                priority *= 0.82
            priority = self._apply_history_novelty_adjustment(kw, priority, category, search_intent)
            priority *= 0.75 + (min(verification_score, 100.0) / 400.0)
            content_cluster_key = self._content_cluster_key(kw, category, search_intent)

            result = KeywordResult(
                keyword=kw,
                search_volume=search_volume,
                difficulty=difficulty,
                opportunity=opportunity,
                grade=grade,
                category=category,
                priority_score=priority,
                source=source,
                search_intent=search_intent,
                document_count=document_count,
                kei=kei,
                kei_grade=kei_grade,
                business_core=business_core,
                source_signals=source_signals,
                verification_score=verification_score,
                quality_flags=quality_flags,
                longtail_score=float(value_profile["longtail_score"]),
                business_value_score=float(value_profile["business_value_score"]),
                high_value_longtail=bool(value_profile["high_value_longtail"]),
                inbound_impressions=int(inbound_metrics.get("impressions", 0) or 0),
                inbound_clicks=int(inbound_metrics.get("clicks", 0) or 0),
                inbound_ctr=float(inbound_metrics.get("ctr", 0.0) or 0.0),
                inbound_position=float(inbound_metrics.get("position", 0.0) or 0.0),
                inbound_sources=inbound_sources,
                mobile_share=mobile_share,
                content_cluster_key=content_cluster_key,
                owned_rank=int(rank_metrics.get("rank", 0) or 0),
                owned_rank_device=str(rank_metrics.get("device", "") or ""),
                rank_gap_signal=rank_gap_signal,
                rank_status=rank_status,
                community_mentions=int(community_metrics.get("mentions", 0) or 0),
                community_conversion_fit=float(community_metrics.get("max_conversion_fit", 0.0) or 0.0),
                community_signal=community_signal,
                community_platforms=list(community_metrics.get("platforms", []) or []),
                conversion_calls=int(conversion_metrics.get("total_calls", 0) or 0),
                conversion_naver_calls=int(conversion_metrics.get("naver_search_calls", 0) or 0),
                conversion_duration_seconds=int(conversion_metrics.get("duration_seconds", 0) or 0),
                conversion_signal=conversion_signal,
                profile_action_signal=profile_action_signal,
                profile_actions_total=int(profile_action_metrics.get("total_actions", 0) or 0),
                profile_direction_actions=int(profile_action_metrics.get("directions", 0) or 0),
                profile_website_actions=int(profile_action_metrics.get("website_clicks", 0) or 0),
                profile_booking_actions=int(profile_action_metrics.get("bookings", 0) or 0),
                profile_message_actions=int(profile_action_metrics.get("messages", 0) or 0),
                profile_action_sources=profile_action_sources,
                profile_action_flags=profile_action_flags,
                availability_intent_score=availability_intent_score,
                availability_intent_type=availability_intent_type,
                availability_action_flags=availability_action_flags,
                payment_coverage_score=payment_coverage_score,
                payment_coverage_type=payment_coverage_type,
                payment_action_flags=payment_action_flags,
                access_convenience_score=access_convenience_score,
                access_convenience_type=access_convenience_type,
                access_convenience_flags=access_convenience_flags,
                medical_ad_risk_score=medical_ad_risk_score,
                medical_ad_risk_flags=medical_ad_risk_flags,
                content_feasibility_score=content_feasibility_score,
                local_service_fit_score=local_service_fit_score,
                negative_intent_flags=negative_intent_flags,
                content_actionability_score=content_actionability_score,
                recommended_content_type=recommended_content_type,
                content_action_flags=content_action_flags,
                local_surface_score=local_surface_score,
                preferred_search_surface=preferred_search_surface,
                local_surface_flags=local_surface_flags,
                brand_intent_type=brand_intent_type,
                brand_signal_score=brand_signal_score,
                brand_mentions=brand_mentions,
                competitor_brand_risk_score=competitor_brand_risk_score,
                brand_action_flags=brand_action_flags,
                review_surface_score=review_surface_score,
                reputation_risk_score=reputation_risk_score,
                review_intent_type=review_intent_type,
                review_action_flags=review_action_flags,
            )

            self.collected[kw] = result
            self.keyword_canonical_by_norm[norm] = kw
            self.candidate_stats["accepted_by_source"][source] += 1

            if grade in ['S', 'A']:
                new_sa += 1
                self.candidate_stats["sa_by_source"][source] += 1

        return new_sa

    def run(
        self,
        target_sa: int = 500,
        max_rounds: int = 10,
        round1_seed_limit: Optional[int] = None,
        skip_ad_related: bool = False,
    ) -> List[KeywordResult]:
        """
        LEGION MODE 실행

        Args:
            target_sa: 목표 S/A급 키워드 수
            max_rounds: 최대 라운드 수

        Returns:
            KeywordResult 리스트
        """
        print("=" * 70)
        print("🚀 PATHFINDER V3 LEGION MODE")
        print(f"   목표: S/A급 {target_sa}개")
        print("=" * 70)

        total_sa = 0
        round_num = 0

        # ==========================================
        # Round 1: 기본 시드 자동완성 (Multi-Source: Naver + Google)
        # ==========================================
        round_num += 1
        google_status = "ON" if self.collector.use_google else "OFF"
        print(f"\n[Round {round_num}] 기본 시드 자동완성 (Google: {google_status})...")

        round1_keywords = set()
        naver_count = 0
        google_count = 0

        round1_seeds = self.base_seeds
        if round1_seed_limit is not None:
            limit = max(0, round1_seed_limit)
            if len(round1_seeds) > limit:
                step = len(round1_seeds) / limit
                round1_seeds = [round1_seeds[int(i * step)] for i in range(limit)]
            print(f"   Smoke/limited mode: Round 1 seeds {len(round1_seeds)}/{len(self.base_seeds)}")

        for seed in round1_seeds:
            # 다중 소스 수집 (Naver + Google)
            suggestions = self.collector.get_autocomplete_multi(seed)
            if suggestions:
                # Google에서 추가된 키워드 수 추적
                naver_only = set(self.collector.get_autocomplete(seed) or [])
                google_added = suggestions - naver_only
                naver_count += len(naver_only)
                google_count += len(google_added)
                round1_keywords.update(suggestions)
            round1_keywords.add(seed)

        if google_count > 0:
            print(f"   📊 소스별: Naver {naver_count}개, Google +{google_count}개")

        new_sa = self._analyze_and_add(list(round1_keywords), "round1_seed")
        total_sa += new_sa
        print(f"   수집: {len(round1_keywords)}개, 신규 S/A급: {new_sa}개, 누적: {total_sa}개")

        if not skip_ad_related:
            ad_related_keywords = self._collect_ad_related_keywords(
                list(round1_keywords) + self.base_seeds,
                source="round1_ad_related",
                max_seeds=50,
                max_keywords=300,
                min_volume=10,
            )
            if ad_related_keywords:
                new_sa = self._analyze_and_add(ad_related_keywords, "round1_ad_related")
                total_sa += new_sa
                print(f"   검색광고 연관어: {len(ad_related_keywords)}개, 신규 S/A급: {new_sa}개, 누적: {total_sa}개")

        if total_sa < target_sa and max_rounds > 1:
            early_longtail_keywords = self._build_high_value_longtail_variants(
                list(round1_keywords) + list(round1_seeds),
                max_keywords=180,
            )
            if early_longtail_keywords:
                new_sa = self._analyze_and_add(list(early_longtail_keywords), "round1_longtail_scout")
                total_sa += new_sa
                print(
                    f"   고가치 롱테일 스카우트: {len(early_longtail_keywords)}개, "
                    f"신규 S/A급: {new_sa}개, 누적: {total_sa}개"
                )

        if total_sa >= target_sa:
            return self._finalize()
        if round_num >= max_rounds:
            return self._finalize()

        # ==========================================
        # Round 2: S/A급 키워드 재확장 (의도 suffix 추가)
        # ==========================================
        round_num += 1
        print(f"\n[Round {round_num}] S/A급 키워드 재확장 (의도 기반)...")

        sa_keywords = self._select_expansion_keywords({'S', 'A'}, limit=50, max_per_category=10)
        round2_keywords = set()

        # 의도 suffix - 고객 행동/확인 니즈 중심으로 확장하고 홍보성 claim 반복은 제외.
        round2_suffixes = ["비용", "예약", "상담", "주차", "기간", "주의사항"]

        for kw in sa_keywords:
            # 1) 기본 자동완성
            suggestions = self.collector.get_autocomplete(kw)
            if suggestions is not None:
                round2_keywords.update(suggestions)

            # 2) 의도 suffix 추가 자동완성 (롱테일 발굴)
            for suffix in round2_suffixes:
                expanded_kw = f"{kw} {suffix}"
                suggestions2 = self.collector.get_autocomplete(expanded_kw)
                if suggestions2 is not None:
                    round2_keywords.update(suggestions2)
                round2_keywords.add(expanded_kw)

        new_sa = self._analyze_and_add(list(round2_keywords), "round2_expand")
        total_sa += new_sa
        print(f"   수집: {len(round2_keywords)}개, 신규 S/A급: {new_sa}개, 누적: {total_sa}개")

        if total_sa >= target_sa:
            return self._finalize()
        if round_num >= max_rounds:
            return self._finalize()

        # ==========================================
        # Round 3: 지역 확장 (동네별)
        # ==========================================
        round_num += 1
        print(f"\n[Round {round_num}] 지역 확장 (동네별)...")

        core_terms = [
            "다이어트", "교통사고", "교통사고 입원",
            "안면비대칭", "여드름", "여드름흉터",
            "새살침", "체형교정",
        ]
        round3_keywords = set()

        for dong in self.collector.neighborhoods[:10]:
            for term in core_terms:
                seed = f"{dong} {term}"
                suggestions = self.collector.get_autocomplete(seed)
                if suggestions is not None:  # None 방어
                    round3_keywords.update(suggestions)
                round3_keywords.add(seed)

        new_sa = self._analyze_and_add(list(round3_keywords), "round3_region")
        total_sa += new_sa
        print(f"   수집: {len(round3_keywords)}개, 신규 S/A급: {new_sa}개, 누적: {total_sa}개")

        if total_sa >= target_sa:
            return self._finalize()
        if round_num >= max_rounds:
            return self._finalize()

        # ==========================================
        # Round 4: 의도 확장 (B: 의도 기반 롱테일 강화)
        # ==========================================
        round_num += 1
        print(f"\n[Round {round_num}] 의도 확장 (전환 의도 키워드)...")

        # 기존 S/A/B급 키워드에 의도 suffix 추가 - 전체 사용
        good_keywords = self._select_expansion_keywords({'S', 'A', 'B'}, limit=70, max_per_category=12)
        round4_keywords = set()

        generic_high_intent = ["가격", "비용", "예약", "후기", "추천"]
        accident_high_intent = ["자보", "자동차보험", "보험", "치료비"]
        high_intent_pool = set(generic_high_intent + accident_high_intent)
        other_intent = [i for i in self.collector.intent_suffixes if i not in high_intent_pool]

        for kw in good_keywords:
            result = self.collected.get(kw)
            category = result.category if result else self.collector._detect_category(kw)
            high_intents = list(generic_high_intent)
            if category == "교통사고":
                high_intents.extend(accident_high_intent)

            for intent in high_intents:
                new_kw = f"{kw} {intent}"
                round4_keywords.add(new_kw)
                suggestions = self.collector.get_autocomplete(new_kw)
                if suggestions is not None:
                    round4_keywords.update(suggestions)

            # 기타 의도는 S/A급에만
            if self.collected.get(kw) and self.collected[kw].grade in ['S', 'A']:
                for intent in other_intent[:5]:
                    new_kw = f"{kw} {intent}"
                    round4_keywords.add(new_kw)

        new_sa = self._analyze_and_add(list(round4_keywords), "round4_intent")
        total_sa += new_sa
        print(f"   수집: {len(round4_keywords)}개, 신규 S/A급: {new_sa}개, 누적: {total_sa}개")

        round4_longtail_keywords = self._build_high_value_longtail_variants(good_keywords)
        if round4_longtail_keywords:
            new_sa = self._analyze_and_add(list(round4_longtail_keywords), "round4_longtail")
            total_sa += new_sa
            print(
                f"   고가치 롱테일 템플릿: {len(round4_longtail_keywords)}개, "
                f"신규 S/A급: {new_sa}개, 누적: {total_sa}개"
            )

        if total_sa >= target_sa:
            return self._finalize()
        if round_num >= max_rounds:
            return self._finalize()

        # ==========================================
        # Round 5: 경쟁사 역분석 (A: 경쟁 갭 발굴)
        # ==========================================
        round_num += 1
        print(f"\n[Round {round_num}] 경쟁사 역분석 + 갭 키워드 발굴...")

        competitors_path = Path("config/competitors.json")
        round5_keywords = set()
        competitor_keywords = set()  # 경쟁사가 타겟팅하는 키워드

        if competitors_path.exists():
            with open(competitors_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            competitors = list(config.get("competitors", []))
            if not competitors:
                for category_config in config.get("category_competitors", {}).values():
                    competitors.extend(category_config.get("main_competitors", []))

            deduped_competitors = []
            seen_competitors = set()
            for comp in competitors:
                key = (comp.get("name", ""), comp.get("blog_url", ""))
                if key in seen_competitors:
                    continue
                seen_competitors.add(key)
                deduped_competitors.append(comp)
            competitors = deduped_competitors
            print(f"   경쟁사 {len(competitors)}개 분석 중...")

            for comp in competitors:
                comp_name = comp.get("name", "")
                blog_url = comp.get("blog_url", "")

                # 1. 경쟁사 이름으로 검색 (어떤 키워드로 노출되는지)
                if comp_name and "example" not in comp_name.lower():
                    suggestions = self.collector.get_autocomplete(comp_name)
                    if suggestions is not None:
                        round5_keywords.update(suggestions)
                        competitor_keywords.update(suggestions)

                # 2. 블로그 ID로 검색
                if blog_url and "example" not in blog_url:
                    match = re.search(r'blog\.naver\.com/(\w+)', blog_url)
                    if match:
                        blog_id = match.group(1)
                        suggestions = self.collector.get_autocomplete(f"{blog_id}")
                        if suggestions is not None:
                            round5_keywords.update(suggestions)

                # 3. 경쟁사 + 키워드 조합 (그들의 강점 파악)
                region = self.collector.cheongju_regions[0] if self.collector.cheongju_regions else GYULIM_KEYWORD_PROFILE.primary_region
                for cat in ["다이어트", "흉터", "피부", GYULIM_KEYWORD_PROFILE.service_query_anchor]:
                    seed = f"{region} {cat} {comp_name.split()[0] if comp_name else ''}"
                    suggestions = self.collector.get_autocomplete(seed.strip())
                    if suggestions is not None:
                        competitor_keywords.update(suggestions)

            # 경쟁 갭 표시: 우리 키워드 중 경쟁사가 타겟팅 안 하는 것
            gap_count = 0
            for kw, result in self.collected.items():
                is_gap = not any(ck in kw or kw in ck for ck in competitor_keywords)
                if is_gap and result.grade in ['S', 'A']:
                    result.is_gap_keyword = True
                    gap_count += 1

            print(f"   경쟁 갭 키워드 발견: {gap_count}개 (경쟁사 미타겟)")

        if round5_keywords:
            new_sa = self._analyze_and_add(list(round5_keywords), "round5_competitor")
            total_sa += new_sa
            print(f"   수집: {len(round5_keywords)}개, 신규 S/A급: {new_sa}개, 누적: {total_sa}개")
        else:
            print("   경쟁사 설정 없음, 기본 갭 분석만 수행")

        if total_sa >= target_sa:
            return self._finalize()
        if round_num >= max_rounds:
            return self._finalize()

        # ==========================================
        # Round 6: 연관검색어 (확대 적용)
        # ==========================================
        round_num += 1
        print(f"\n[Round {round_num}] 연관검색어 수집 (S/A급 전체 + B급 상위)...")

        # S/A급 전체 + B급 상위 30개로 확대
        sa_keywords = self._select_expansion_keywords({'S', 'A'}, limit=None, max_per_category=20)
        b_keywords = self._select_expansion_keywords({'B'}, limit=30, max_per_category=8)
        target_keywords = sa_keywords + b_keywords

        round6_keywords = set()
        related_count = 0

        for kw in target_keywords:
            related = self.collector.get_related_keywords(kw)
            if related is not None:
                related_count += len(related)
                for r in related:
                    if self.collector._is_valid_keyword(r):
                        round6_keywords.add(r)

        print(f"   연관검색어 조회: {len(target_keywords)}개 키워드 → {related_count}개 연관검색어")

        if round6_keywords:
            new_sa = self._analyze_and_add(list(round6_keywords), "round6_related")
            total_sa += new_sa
            print(f"   수집: {len(round6_keywords)}개, 신규 S/A급: {new_sa}개, 누적: {total_sa}개")
        else:
            print("   유효한 연관검색어 없음 (중복 또는 검증 탈락)")

        if total_sa >= target_sa:
            return self._finalize()
        if round_num >= max_rounds:
            return self._finalize()

        # ==========================================
        # Round 6.5: 블로그 제목 마이닝
        # ==========================================
        if self.blog_miner:
            round_num += 1
            print(f"\n[Round {round_num}] 블로그 제목 마이닝...")

            # S/A급 키워드로 블로그 검색하여 추가 키워드 발굴
            sa_keywords = self._select_expansion_keywords({'S', 'A'}, limit=15, max_per_category=5)

            blog_keywords = set()
            for kw in sa_keywords:
                try:
                    mined = self.blog_miner.mine_from_search(kw, top_n=10)
                    for mk in mined:
                        if self.collector._is_valid_keyword(mk):
                            blog_keywords.add(mk)
                except Exception as e:
                    pass

            if blog_keywords:
                print(f"   📰 블로그에서 {len(blog_keywords)}개 키워드 추출")
                new_sa = self._analyze_and_add(list(blog_keywords), "blog_mining")
                total_sa += new_sa
                print(f"   수집: {len(blog_keywords)}개, 신규 S/A급: {new_sa}개, 누적: {total_sa}개")

            if total_sa >= target_sa:
                return self._finalize()
            if round_num >= max_rounds:
                return self._finalize()

        # ==========================================
        # Round 7: 문제 해결형 키워드 (C: 증상 + 고민)
        # ==========================================
        round_num += 1
        print(f"\n[Round {round_num}] 문제 해결형 키워드 (증상/고민 기반)...")

        round7_keywords = set()
        region = GYULIM_KEYWORD_PROFILE.primary_region

        # 문제 키워드 + 지역 조합
        for problem in self.collector.problem_keywords:
            # 지역 + 문제
            seed1 = f"{region} {problem}"
            round7_keywords.add(seed1)
            suggestions = self.collector.get_autocomplete(seed1)
            if suggestions is not None:
                round7_keywords.update(suggestions)

            # 문제 + 서비스/치료
            for suffix in [GYULIM_KEYWORD_PROFILE.service_query_anchor, "치료", "병원", "상담"]:
                seed2 = f"{region} {problem} {suffix}"
                round7_keywords.add(seed2)
                suggestions = self.collector.get_autocomplete(seed2)
                if suggestions is not None:
                    round7_keywords.update(suggestions)

        new_sa = self._analyze_and_add(list(round7_keywords), "round7_problem")
        total_sa += new_sa
        print(f"   수집: {len(round7_keywords)}개, 신규 S/A급: {new_sa}개, 누적: {total_sa}개")

        if total_sa >= target_sa:
            return self._finalize()
        if round_num >= max_rounds:
            return self._finalize()

        # ==========================================
        # Round 8: AI 시맨틱 확장 (Codex CLI)
        # ==========================================
        if self.has_ai_expander and self.ai_expander:
            round_num += 1
            print(f"\n[Round {round_num}] AI 시맨틱 확장 (Codex CLI)...")

            round8_keywords = set()

            # 카테고리별 S/A급 키워드로 AI 확장
            category_seeds = {}
            for kw, result in self.collected.items():
                if result.grade in ['S', 'A']:
                    cat = result.category
                    if cat not in category_seeds:
                        category_seeds[cat] = []
                    if len(category_seeds[cat]) < 5:  # 카테고리당 5개 시드
                        category_seeds[cat].append(kw)

            # 카테고리별 AI 확장 (개선: max_results 15→50)
            for category, seeds in list(category_seeds.items())[:5]:  # 상위 5개 카테고리만
                try:
                    expanded = self.ai_expander.expand_semantic(seeds, category, max_results=50)
                    if expanded:
                        for kw in expanded:
                            if self.collector._is_valid_keyword(kw):
                                round8_keywords.add(kw)
                        print(f"   🤖 {category}: +{len(expanded)}개")
                except Exception as e:
                    print(f"   ⚠️ {category} AI 확장 실패: {e}")

            if round8_keywords:
                new_sa = self._analyze_and_add(list(round8_keywords), "round8_ai")
                total_sa += new_sa
                print(f"   수집: {len(round8_keywords)}개, 신규 S/A급: {new_sa}개, 누적: {total_sa}개")

            if total_sa >= target_sa:
                return self._finalize()

        # ==========================================
        # 추가 라운드 (목표 미달 시)
        # ==========================================
        while total_sa < target_sa and round_num < max_rounds:
            round_num += 1
            print(f"\n[Round {round_num}] 추가 확장...")

            # B급 키워드 재확장
            b_keywords = self._select_expansion_keywords({'B'}, limit=20, max_per_category=6)
            extra_keywords = set()

            for kw in b_keywords:
                suggestions = self.collector.get_autocomplete(kw)
                if suggestions is not None:  # None 방어
                    extra_keywords.update(suggestions)

            if not extra_keywords:
                print("   더 이상 확장할 키워드 없음")
                break

            new_sa = self._analyze_and_add(list(extra_keywords), f"round{round_num}_extra")
            total_sa += new_sa
            print(f"   수집: {len(extra_keywords)}개, 신규 S/A급: {new_sa}개, 누적: {total_sa}개")

            # 수확률 체크
            if new_sa == 0:
                print("   수확률 0%, 종료")
                break

        return self._finalize()

    @staticmethod
    def _tokenize_keyword(keyword: str) -> Set[str]:
        tokens = set(re.findall(r"[0-9A-Za-z가-힣]+", (keyword or "").lower()))
        compact = re.sub(r"\s+", "", (keyword or "").lower())
        if len(compact) >= 4:
            tokens.update(compact[i:i + 2] for i in range(max(0, len(compact) - 1)))
        return {token for token in tokens if token}

    @classmethod
    def _keyword_similarity(cls, left: KeywordResult, right: KeywordResult) -> float:
        left_tokens = cls._tokenize_keyword(left.keyword)
        right_tokens = cls._tokenize_keyword(right.keyword)
        if not left_tokens or not right_tokens:
            token_similarity = 0.0
        else:
            token_similarity = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))

        aspect_bonus = 0.0
        if left.category and left.category == right.category:
            aspect_bonus += 0.12
        if left.search_intent and left.search_intent == right.search_intent:
            aspect_bonus += 0.08
        if left.source and left.source == right.source:
            aspect_bonus += 0.05
        return min(1.0, token_similarity + aspect_bonus)

    @staticmethod
    def _entropy_norm(counter: Counter) -> float:
        total = sum(counter.values())
        if total <= 0 or len(counter) <= 1:
            return 0.0
        entropy = 0.0
        for count in counter.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log(p)
        return entropy / math.log(len(counter))

    @staticmethod
    def _hhi(counter: Counter) -> float:
        total = sum(counter.values())
        if total <= 0:
            return 0.0
        return sum((count / total) ** 2 for count in counter.values())

    def _calculate_diversity_metrics(self, results: List[KeywordResult]) -> Dict[str, object]:
        self._ensure_quality_tracking()
        total = len(results)
        grade_counts = Counter(r.grade for r in results)
        category_counts = Counter(r.category or "unknown" for r in results)
        source_counts = Counter(r.source or "unknown" for r in results)
        intent_counts = Counter(r.search_intent or "unknown" for r in results)
        cluster_counts = Counter(r.content_cluster_key or "unknown" for r in results)
        longtail_count = sum(1 for r in results if self._is_longtail_keyword(r.keyword or ""))
        high_value_longtail_count = sum(1 for r in results if getattr(r, "high_value_longtail", False))
        inbound_query_count = sum(1 for r in results if int(getattr(r, "inbound_impressions", 0) or 0) > 0)
        inbound_click_count = sum(1 for r in results if int(getattr(r, "inbound_clicks", 0) or 0) > 0)
        mobile_local_signal_count = sum(1 for r in results if float(getattr(r, "mobile_share", 0.0) or 0.0) >= 0.65)
        owned_rank_gap_count = sum(1 for r in results if float(getattr(r, "rank_gap_signal", 0.0) or 0.0) >= 55.0)
        owned_top_rank_count = sum(1 for r in results if getattr(r, "rank_status", "") == "owned_top3")
        community_signal_count = sum(1 for r in results if float(getattr(r, "community_signal", 0.0) or 0.0) >= 40.0)
        community_multi_platform_count = sum(1 for r in results if len(getattr(r, "community_platforms", []) or []) >= 2)
        conversion_signal_count = sum(1 for r in results if float(getattr(r, "conversion_signal", 0.0) or 0.0) >= 35.0)
        conversion_call_total = sum(int(getattr(r, "conversion_calls", 0) or 0) for r in results)
        profile_action_signal_count = sum(
            1 for r in results if float(getattr(r, "profile_action_signal", 0.0) or 0.0) >= 35.0
        )
        profile_action_high_count = sum(
            1 for r in results if float(getattr(r, "profile_action_signal", 0.0) or 0.0) >= 60.0
        )
        profile_action_total = sum(int(getattr(r, "profile_actions_total", 0) or 0) for r in results)
        profile_direction_total = sum(int(getattr(r, "profile_direction_actions", 0) or 0) for r in results)
        profile_booking_total = sum(int(getattr(r, "profile_booking_actions", 0) or 0) for r in results)
        profile_action_scores = [float(getattr(r, "profile_action_signal", 0.0) or 0.0) for r in results]
        availability_scores = [float(getattr(r, "availability_intent_score", 0.0) or 0.0) for r in results]
        availability_high_count = sum(
            1 for r in results if float(getattr(r, "availability_intent_score", 0.0) or 0.0) >= 70.0
        )
        availability_review_count = sum(
            1 for r in results if 55.0 <= float(getattr(r, "availability_intent_score", 0.0) or 0.0) < 70.0
        )
        availability_intent_counts = Counter(getattr(r, "availability_intent_type", "") or "none" for r in results)
        payment_scores = [float(getattr(r, "payment_coverage_score", 0.0) or 0.0) for r in results]
        payment_high_count = sum(
            1 for r in results if float(getattr(r, "payment_coverage_score", 0.0) or 0.0) >= 70.0
        )
        payment_review_count = sum(
            1 for r in results if 55.0 <= float(getattr(r, "payment_coverage_score", 0.0) or 0.0) < 70.0
        )
        payment_type_counts = Counter(getattr(r, "payment_coverage_type", "") or "none" for r in results)
        access_scores = [float(getattr(r, "access_convenience_score", 0.0) or 0.0) for r in results]
        access_high_count = sum(
            1 for r in results if float(getattr(r, "access_convenience_score", 0.0) or 0.0) >= 70.0
        )
        access_review_count = sum(
            1 for r in results if 55.0 <= float(getattr(r, "access_convenience_score", 0.0) or 0.0) < 70.0
        )
        access_type_counts = Counter(getattr(r, "access_convenience_type", "") or "none" for r in results)
        medical_ad_high_risk_count = sum(1 for r in results if float(getattr(r, "medical_ad_risk_score", 0.0) or 0.0) >= 70.0)
        medical_ad_review_count = sum(1 for r in results if 40.0 <= float(getattr(r, "medical_ad_risk_score", 0.0) or 0.0) < 70.0)
        feasibility_scores = [float(getattr(r, "content_feasibility_score", 100.0) or 0.0) for r in results]
        service_fit_scores = [float(getattr(r, "local_service_fit_score", 0.0) or 0.0) for r in results]
        service_fit_block_count = sum(
            1 for r in results if float(getattr(r, "local_service_fit_score", 0.0) or 0.0) < 35.0
        )
        service_fit_review_count = sum(
            1 for r in results if 35.0 <= float(getattr(r, "local_service_fit_score", 0.0) or 0.0) < 60.0
        )
        negative_intent_count = sum(1 for r in results if getattr(r, "negative_intent_flags", []) or [])
        content_action_scores = [float(getattr(r, "content_actionability_score", 0.0) or 0.0) for r in results]
        content_action_block_count = sum(
            1 for r in results if float(getattr(r, "content_actionability_score", 0.0) or 0.0) < 45.0
        )
        content_action_review_count = sum(
            1 for r in results if 45.0 <= float(getattr(r, "content_actionability_score", 0.0) or 0.0) < 60.0
        )
        recommended_content_counts = Counter(getattr(r, "recommended_content_type", "") or "unknown" for r in results)
        local_surface_scores = [float(getattr(r, "local_surface_score", 0.0) or 0.0) for r in results]
        local_surface_high_count = sum(
            1 for r in results if float(getattr(r, "local_surface_score", 0.0) or 0.0) >= 70.0
        )
        local_surface_review_count = sum(
            1 for r in results if 55.0 <= float(getattr(r, "local_surface_score", 0.0) or 0.0) < 70.0
        )
        preferred_surface_counts = Counter(getattr(r, "preferred_search_surface", "") or "unknown" for r in results)
        brand_intent_counts = Counter(getattr(r, "brand_intent_type", "") or "generic" for r in results)
        own_brand_count = sum(1 for r in results if getattr(r, "brand_intent_type", "") == "own_brand_defense")
        competitor_brand_count = sum(
            1 for r in results
            if getattr(r, "brand_intent_type", "") in {"competitor_brand", "competitor_comparison", "own_vs_competitor"}
        )
        competitor_brand_high_risk_count = sum(
            1 for r in results if float(getattr(r, "competitor_brand_risk_score", 0.0) or 0.0) >= 70.0
        )
        review_surface_scores = [float(getattr(r, "review_surface_score", 0.0) or 0.0) for r in results]
        reputation_risk_scores = [float(getattr(r, "reputation_risk_score", 0.0) or 0.0) for r in results]
        review_surface_high_count = sum(
            1 for r in results if float(getattr(r, "review_surface_score", 0.0) or 0.0) >= 70.0
        )
        reputation_review_count = sum(
            1 for r in results if 40.0 <= float(getattr(r, "reputation_risk_score", 0.0) or 0.0) < 70.0
        )
        reputation_high_risk_count = sum(
            1 for r in results if float(getattr(r, "reputation_risk_score", 0.0) or 0.0) >= 70.0
        )
        review_intent_counts = Counter(getattr(r, "review_intent_type", "") or "none" for r in results)
        low_volume_high_value_longtail_count = sum(
            1
            for r in results
            if getattr(r, "high_value_longtail", False) and 0 < (r.search_volume or 0) <= 50
        )
        longtail_4plus_count = sum(
            1
            for r in results
            if len(self._keyword_terms(getattr(r, "keyword", "") or "")) >= 4
        )
        estimated_high_value_longtail_count = sum(
            1
            for r in results
            if getattr(r, "high_value_longtail", False)
            and "estimated_high_value_longtail" in (r.quality_flags or [])
        )
        high_value_longtail_sa_count = sum(
            1
            for r in results
            if getattr(r, "high_value_longtail", False) and r.grade in ("S", "A")
        )
        business_value_scores = [float(getattr(r, "business_value_score", 0.0) or 0.0) for r in results]
        verified_count = sum(1 for r in results if r.verification_score >= 55)
        multi_source_count = sum(1 for r in results if len(r.source_signals or []) >= 2)
        risk_flag_count = sum(1 for r in results if r.quality_flags)

        def top_share(counter: Counter) -> float:
            return (max(counter.values()) / total) if total and counter else 0.0

        rejected = {
            source: dict(reason_counts)
            for source, reason_counts in self.candidate_stats["rejected_by_source"].items()
        }

        return {
            "total_keywords": total,
            "grade_counts": dict(grade_counts),
            "sa_count": grade_counts.get("S", 0) + grade_counts.get("A", 0),
            "sa_rate": round((grade_counts.get("S", 0) + grade_counts.get("A", 0)) / max(1, total), 4),
            "category_count": len(category_counts),
            "source_count": len(source_counts),
            "intent_count": len(intent_counts),
            "content_cluster_count": len(cluster_counts),
            "category_entropy_norm": round(self._entropy_norm(category_counts), 4),
            "source_entropy_norm": round(self._entropy_norm(source_counts), 4),
            "intent_entropy_norm": round(self._entropy_norm(intent_counts), 4),
            "content_cluster_entropy_norm": round(self._entropy_norm(cluster_counts), 4),
            "category_hhi": round(self._hhi(category_counts), 4),
            "source_hhi": round(self._hhi(source_counts), 4),
            "content_cluster_hhi": round(self._hhi(cluster_counts), 4),
            "top_category_share": round(top_share(category_counts), 4),
            "top_source_share": round(top_share(source_counts), 4),
            "top_content_cluster_share": round(top_share(cluster_counts), 4),
            "longtail_rate": round(longtail_count / max(1, total), 4),
            "longtail_4plus_count": longtail_4plus_count,
            "longtail_4plus_rate": round(longtail_4plus_count / max(1, total), 4),
            "high_value_longtail_count": high_value_longtail_count,
            "high_value_longtail_rate": round(high_value_longtail_count / max(1, total), 4),
            "high_value_longtail_sa_count": high_value_longtail_sa_count,
            "high_value_longtail_sa_rate": round(high_value_longtail_sa_count / max(1, high_value_longtail_count), 4),
            "low_volume_high_value_longtail_count": low_volume_high_value_longtail_count,
            "estimated_high_value_longtail_count": estimated_high_value_longtail_count,
            "inbound_query_count": inbound_query_count,
            "inbound_query_rate": round(inbound_query_count / max(1, total), 4),
            "inbound_click_count": inbound_click_count,
            "mobile_local_signal_count": mobile_local_signal_count,
            "mobile_local_signal_rate": round(mobile_local_signal_count / max(1, total), 4),
            "owned_rank_gap_count": owned_rank_gap_count,
            "owned_rank_gap_rate": round(owned_rank_gap_count / max(1, total), 4),
            "owned_top_rank_count": owned_top_rank_count,
            "community_signal_count": community_signal_count,
            "community_signal_rate": round(community_signal_count / max(1, total), 4),
            "community_multi_platform_count": community_multi_platform_count,
            "conversion_signal_count": conversion_signal_count,
            "conversion_signal_rate": round(conversion_signal_count / max(1, total), 4),
            "conversion_call_total": conversion_call_total,
            "profile_action_signal_count": profile_action_signal_count,
            "profile_action_signal_rate": round(profile_action_signal_count / max(1, total), 4),
            "profile_action_high_count": profile_action_high_count,
            "profile_action_total": profile_action_total,
            "profile_direction_total": profile_direction_total,
            "profile_booking_total": profile_booking_total,
            "avg_profile_action_signal": round(sum(profile_action_scores) / max(1, len(profile_action_scores)), 2),
            "availability_high_count": availability_high_count,
            "availability_review_count": availability_review_count,
            "avg_availability_intent_score": round(sum(availability_scores) / max(1, len(availability_scores)), 2),
            "payment_high_count": payment_high_count,
            "payment_review_count": payment_review_count,
            "avg_payment_coverage_score": round(sum(payment_scores) / max(1, len(payment_scores)), 2),
            "access_high_count": access_high_count,
            "access_review_count": access_review_count,
            "avg_access_convenience_score": round(sum(access_scores) / max(1, len(access_scores)), 2),
            "medical_ad_high_risk_count": medical_ad_high_risk_count,
            "medical_ad_review_count": medical_ad_review_count,
            "avg_content_feasibility_score": round(sum(feasibility_scores) / max(1, len(feasibility_scores)), 2),
            "service_fit_block_count": service_fit_block_count,
            "service_fit_review_count": service_fit_review_count,
            "negative_intent_count": negative_intent_count,
            "avg_local_service_fit_score": round(sum(service_fit_scores) / max(1, len(service_fit_scores)), 2),
            "content_action_block_count": content_action_block_count,
            "content_action_review_count": content_action_review_count,
            "avg_content_actionability_score": round(sum(content_action_scores) / max(1, len(content_action_scores)), 2),
            "local_surface_high_count": local_surface_high_count,
            "local_surface_review_count": local_surface_review_count,
            "avg_local_surface_score": round(sum(local_surface_scores) / max(1, len(local_surface_scores)), 2),
            "own_brand_count": own_brand_count,
            "competitor_brand_count": competitor_brand_count,
            "competitor_brand_high_risk_count": competitor_brand_high_risk_count,
            "review_surface_high_count": review_surface_high_count,
            "reputation_review_count": reputation_review_count,
            "reputation_high_risk_count": reputation_high_risk_count,
            "avg_review_surface_score": round(sum(review_surface_scores) / max(1, len(review_surface_scores)), 2),
            "avg_reputation_risk_score": round(sum(reputation_risk_scores) / max(1, len(reputation_risk_scores)), 2),
            "avg_business_value_score": round(sum(business_value_scores) / max(1, total), 2),
            "verified_rate": round(verified_count / max(1, total), 4),
            "multi_source_verified_rate": round(multi_source_count / max(1, total), 4),
            "quality_flag_rate": round(risk_flag_count / max(1, total), 4),
            "category_counts": dict(category_counts),
            "source_counts": dict(source_counts),
            "intent_counts": dict(intent_counts),
            "content_cluster_counts": dict(cluster_counts),
            "recommended_content_counts": dict(recommended_content_counts),
            "preferred_surface_counts": dict(preferred_surface_counts),
            "brand_intent_counts": dict(brand_intent_counts),
            "review_intent_counts": dict(review_intent_counts),
            "availability_intent_counts": dict(availability_intent_counts),
            "payment_type_counts": dict(payment_type_counts),
            "access_type_counts": dict(access_type_counts),
            "input_by_source": dict(self.candidate_stats["input_by_source"]),
            "valid_by_source": dict(self.candidate_stats["valid_by_source"]),
            "accepted_by_source": dict(self.candidate_stats["accepted_by_source"]),
            "sa_by_source": dict(self.candidate_stats["sa_by_source"]),
            "rejected_by_source": rejected,
        }

    def _rerank_for_diversity(self, results: List[KeywordResult], lambda_quality: float = 0.68) -> List[KeywordResult]:
        if len(results) <= 2:
            for idx, result in enumerate(results, 1):
                result.diversity_rank = idx
                result.novelty_score = 100.0
            return results

        grade_bonus = {"S": 35.0, "A": 22.0, "B": 7.0, "C": 0.0}
        quality_values = [
            max(0.0, float(r.priority_score or 0.0))
            + grade_bonus.get(r.grade, 0.0)
            + min(12.0, float(getattr(r, "longtail_score", 0.0) or 0.0) * (0.12 if getattr(r, "high_value_longtail", False) else 0.04))
            + min(10.0, float(getattr(r, "business_value_score", 0.0) or 0.0) * 0.10)
            + min(8.0, float(getattr(r, "local_surface_score", 0.0) or 0.0) * 0.08)
            + min(6.0, float(getattr(r, "review_surface_score", 0.0) or 0.0) * 0.06)
            + min(7.0, float(getattr(r, "profile_action_signal", 0.0) or 0.0) * 0.07)
            + min(6.0, float(getattr(r, "availability_intent_score", 0.0) or 0.0) * 0.06)
            + min(7.0, float(getattr(r, "payment_coverage_score", 0.0) or 0.0) * 0.07)
            + min(6.0, float(getattr(r, "access_convenience_score", 0.0) or 0.0) * 0.06)
            for r in results
        ]
        max_quality = max(quality_values) or 1.0
        quality_map = {id(r): q / max_quality * 100.0 for r, q in zip(results, quality_values)}

        remaining = list(results)
        selected: List[KeywordResult] = []
        category_counts: Counter = Counter()
        source_counts: Counter = Counter()
        intent_counts: Counter = Counter()
        cluster_counts: Counter = Counter()
        token_map = {id(result): self._tokenize_keyword(result.keyword) for result in remaining}
        max_similarity_by_id = {id(result): 0.0 for result in remaining}

        def similarity(left: KeywordResult, right: KeywordResult) -> float:
            left_tokens = token_map.get(id(left), set())
            right_tokens = token_map.get(id(right), set())
            if not left_tokens or not right_tokens:
                token_similarity = 0.0
            else:
                token_similarity = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))

            aspect_bonus = 0.0
            if left.category and left.category == right.category:
                aspect_bonus += 0.12
            if left.search_intent and left.search_intent == right.search_intent:
                aspect_bonus += 0.08
            if left.source and left.source == right.source:
                aspect_bonus += 0.05
            if left.content_cluster_key and left.content_cluster_key == right.content_cluster_key:
                aspect_bonus += 0.25
            return min(1.0, token_similarity + aspect_bonus)

        while remaining:
            best = None
            best_score = -1.0
            selected_count = max(1, len(selected))

            for candidate in remaining:
                max_similarity = max_similarity_by_id.get(id(candidate), 0.0)
                novelty = max(0.0, 100.0 * (1.0 - max_similarity))
                category_share = category_counts[candidate.category or "unknown"] / selected_count
                source_share = source_counts[candidate.source or "unknown"] / selected_count
                intent_share = intent_counts[candidate.search_intent or "unknown"] / selected_count
                cluster_share = cluster_counts[candidate.content_cluster_key or "unknown"] / selected_count
                balance_penalty = min(35.0, category_share * 28.0)
                balance_penalty += min(25.0, source_share * 20.0)
                balance_penalty += min(15.0, intent_share * 12.0)
                balance_penalty += min(25.0, cluster_share * 24.0)
                balance = max(0.0, 100.0 - balance_penalty)
                score = (
                    quality_map[id(candidate)] * lambda_quality
                    + novelty * (1.0 - lambda_quality) * 0.75
                    + balance * (1.0 - lambda_quality) * 0.25
                )
                if score > best_score:
                    best = candidate
                    best_score = score
                    candidate.novelty_score = round(novelty, 2)

            selected.append(best)
            remaining.remove(best)
            category_counts[best.category or "unknown"] += 1
            source_counts[best.source or "unknown"] += 1
            intent_counts[best.search_intent or "unknown"] += 1
            cluster_counts[best.content_cluster_key or "unknown"] += 1

            for candidate in remaining:
                candidate_id = id(candidate)
                max_similarity_by_id[candidate_id] = max(
                    max_similarity_by_id.get(candidate_id, 0.0),
                    similarity(candidate, best),
                )

        for idx, result in enumerate(selected, 1):
            result.diversity_rank = idx
        return selected

    def _finalize(self) -> List[KeywordResult]:
        """최종 결과 정리"""
        original_count = len(self.collected)

        # A1: 중복 단어 자동 제거 (가격 가격 → 가격)
        print("\n[후처리] 중복 단어 정제 중...")
        cleaned_collected = {}
        cleaned_count = 0
        for kw, result in self.collected.items():
            # 연속 중복 단어 제거
            words = kw.split()
            cleaned_words = []
            prev = None
            for word in words:
                if word != prev:
                    cleaned_words.append(word)
                prev = word
            cleaned_kw = ' '.join(cleaned_words)

            if cleaned_kw != kw:
                cleaned_count += 1
                result.keyword = cleaned_kw

            # 정제된 키워드로 저장 (중복 시 검색량 높은 것 유지)
            if cleaned_kw not in cleaned_collected or result.search_volume > cleaned_collected[cleaned_kw].search_volume:
                cleaned_collected[cleaned_kw] = result

        self.collected = cleaned_collected
        if cleaned_count > 0:
            print(f"   🧹 중복 단어 정제: {cleaned_count}개")

        # 중복 키워드 병합
        print("\n[후처리] 중복 키워드 병합 중...")
        self.collected = KeywordMerger.merge_results(self.collected)
        merged_count = len(self.collected)

        merge_msg = KeywordMerger.get_merge_stats(original_count, merged_count)
        if merge_msg:
            print(f"   {merge_msg}")
        else:
            print("   중복 키워드 없음")

        results = list(self.collected.values())
        results.sort(key=lambda x: x.priority_score, reverse=True)

        # S/A급 키워드와 고가치 롱테일 트렌드 분석
        if self.has_datalab and self.datalab:
            trend_targets = [
                r for r in results
                if r.grade in ['S', 'A'] or getattr(r, "high_value_longtail", False)
            ]
            trend_targets.sort(
                key=lambda r: (
                    r.grade in ['S', 'A'],
                    float(getattr(r, "business_value_score", 0.0) or 0.0),
                    float(getattr(r, "priority_score", 0.0) or 0.0),
                ),
                reverse=True,
            )
            sa_keywords = trend_targets[: self.TREND_ANALYSIS_LIMIT]
            if sa_keywords:
                print(f"\n[트렌드 분석] S/A급 + 고가치 롱테일 {len(sa_keywords)}개 키워드 분석 중...")
                analyzed = 0
                for r in sa_keywords:
                    try:
                        slope = self.datalab.get_trend_slope(r.keyword)
                        if slope is not None:
                            r.trend_slope = slope
                            if slope > 0.3:
                                r.trend_status = "rising"
                            elif slope < -0.3:
                                r.trend_status = "falling"
                            else:
                                r.trend_status = "stable"
                            analyzed += 1
                    except Exception as e:
                        pass  # 개별 키워드 실패는 무시

                    if analyzed % 10 == 0 and analyzed > 0:
                        print(f"   진행: {analyzed}/{len(sa_keywords)}...")

                print(f"   ✅ 트렌드 분석 완료: {analyzed}개")

                # MF-KEI 5.0: 트렌드 반영하여 priority 재계산
                recalculated = 0
                for r in sa_keywords:
                    if r.trend_slope != 0.0:
                        recalculated_priority = self._calculate_priority(
                            r.difficulty, r.opportunity, r.keyword,
                            r.search_volume, r.kei, r.trend_slope,
                            category=r.category,
                            search_intent=r.search_intent,
                            has_real_volume="missing_real_volume" not in (r.quality_flags or []),
                            business_core=r.business_core,
                            source_signal_count=len(r.source_signals or []),
                            longtail_score=r.longtail_score,
                            business_value_score=r.business_value_score,
                            local_surface_score=r.local_surface_score,
                        )
                        recalculated_priority = self._apply_history_novelty_adjustment(
                            r.keyword, recalculated_priority, r.category, r.search_intent
                        )
                        recalculated_priority *= 0.75 + (min(r.verification_score, 100.0) / 400.0)
                        r.priority_score = recalculated_priority
                        recalculated += 1

                if recalculated > 0:
                    print(f"   🔄 MF-KEI 5.0 재계산: {recalculated}개")
                    # 재정렬
                    results = list(self.collected.values())
                    results.sort(key=lambda x: x.priority_score, reverse=True)

                # 트렌드 통계
                rising = sum(1 for r in sa_keywords if r.trend_status == "rising")
                falling = sum(1 for r in sa_keywords if r.trend_status == "falling")
                stable = sum(1 for r in sa_keywords if r.trend_status == "stable")
                print(f"   📈 상승: {rising}개 | 📉 하락: {falling}개 | ➡️ 안정: {stable}개")

        for result in results:
            self._sync_result_quality_fields(result)
            has_real_volume = result.search_volume > 0 and "missing_real_volume" not in (result.quality_flags or [])
            value_profile = self._calculate_keyword_value_profile(
                result.keyword,
                category=result.category,
                search_intent=result.search_intent,
                search_volume=result.search_volume,
                difficulty=result.difficulty,
                opportunity=result.opportunity,
                document_count=result.document_count,
                source_signal_count=len(result.source_signals or []),
                has_real_volume=has_real_volume,
                business_core=result.business_core,
                medical_ad_risk_score=result.medical_ad_risk_score,
                content_actionability_score=result.content_actionability_score,
                local_surface_score=result.local_surface_score,
                brand_intent_type=result.brand_intent_type,
                competitor_brand_risk_score=result.competitor_brand_risk_score,
            )
            result.grade, result.quality_flags = self._promote_grade_for_high_value_longtail(
                result.grade,
                value_profile,
                has_real_volume,
                result.search_volume,
                result.difficulty,
                result.opportunity,
                result.verification_score,
                result.quality_flags,
            )
        results = self._rerank_for_diversity(results)
        self.diversity_metrics = self._calculate_diversity_metrics(results)

        # 통계
        s_count = sum(1 for r in results if r.grade == 'S')
        a_count = sum(1 for r in results if r.grade == 'A')
        b_count = sum(1 for r in results if r.grade == 'B')
        c_count = sum(1 for r in results if r.grade == 'C')

        print("\n" + "=" * 70)
        print("📊 LEGION MODE 결과")
        print("=" * 70)

        print(f"\n총 키워드: {len(results)}개")
        print(f"   🔥 S급: {s_count}개")
        print(f"   🟢 A급: {a_count}개")
        print(f"   🔵 B급: {b_count}개")
        print(f"   ⚪ C급: {c_count}개")
        print(f"\n   S/A급 비율: {(s_count + a_count) / max(1, len(results)) * 100:.1f}%")

        # 소스별 분포
        print("\n소스별 분포:")
        source_counts: Dict[str, int] = {}
        for r in results:
            source_counts[r.source] = source_counts.get(r.source, 0) + 1
        for src, cnt in sorted(source_counts.items(), key=lambda x: -x[1]):
            print(f"   {src}: {cnt}개")

        # 카테고리별 분포
        print("\n카테고리별 분포:")
        cat_counts: Dict[str, int] = {}
        for r in results:
            cat_counts[r.category] = cat_counts.get(r.category, 0) + 1
        for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
            print(f"   {cat}: {cnt}개")

        # 검색 의도별 분포
        print("\n검색 의도별 분포:")
        intent_counts: Dict[str, int] = {}
        for r in results:
            intent_counts[r.search_intent] = intent_counts.get(r.search_intent, 0) + 1
        for intent, cnt in sorted(intent_counts.items(), key=lambda x: -x[1]):
            label = SearchIntentClassifier.get_intent_label(intent)
            print(f"   {label}: {cnt}개")

        # 상위 S급 키워드 (KEI 포함)
        print("\n🔥 상위 S급 키워드 (KEI 기준):")
        s_keywords = sorted([x for x in results if x.grade == 'S'], key=lambda x: x.kei, reverse=True)
        for r in s_keywords[:15]:
            print(f"   - {r.keyword} [KEI:{r.kei:.1f} 난이도:{r.difficulty} 기회:{r.opportunity}]")

        # KEI 500+ 키워드 수 표시
        kei_500_count = sum(1 for r in results if r.kei >= 500)
        kei_200_count = sum(1 for r in results if r.kei >= 200)
        print(f"\n📈 KEI 분포:")
        print(f"   KEI 500+: {kei_500_count}개 ({kei_500_count/max(1,len(results))*100:.1f}%)")
        print(f"   KEI 200+: {kei_200_count}개 ({kei_200_count/max(1,len(results))*100:.1f}%)")

        metrics = getattr(self, "diversity_metrics", {})
        if metrics:
            print("\n🧭 다양성/검증 지표:")
            print(f"   카테고리 엔트로피: {metrics.get('category_entropy_norm', 0):.3f}")
            print(f"   소스 엔트로피: {metrics.get('source_entropy_norm', 0):.3f}")
            print(f"   의도 엔트로피: {metrics.get('intent_entropy_norm', 0):.3f}")
            print(f"   단일 소스 최대 비중: {metrics.get('top_source_share', 0) * 100:.1f}%")
            print(f"   콘텐츠 클러스터 수: {metrics.get('content_cluster_count', 0)}개")
            print(f"   단일 클러스터 최대 비중: {metrics.get('top_content_cluster_share', 0) * 100:.1f}%")
            print(f"   롱테일 비율: {metrics.get('longtail_rate', 0) * 100:.1f}%")
            print(f"   고가치 롱테일 비율: {metrics.get('high_value_longtail_rate', 0) * 100:.1f}%")
            print(f"   고가치 롱테일 S/A 비율: {metrics.get('high_value_longtail_sa_rate', 0) * 100:.1f}%")
            print(f"   추정 고가치 롱테일: {metrics.get('estimated_high_value_longtail_count', 0)}개")
            print(f"   실제 유입 쿼리 반영: {metrics.get('inbound_query_count', 0)}개")
            print(f"   모바일 로컬 신호: {metrics.get('mobile_local_signal_count', 0)}개")
            print(f"   자체 순위 갭 후보: {metrics.get('owned_rank_gap_count', 0)}개")
            print(f"   자체 Top3 유지 후보: {metrics.get('owned_top_rank_count', 0)}개")
            print(f"   커뮤니티 수요 신호: {metrics.get('community_signal_count', 0)}개")
            print(f"   실제 전화 전환 신호: {metrics.get('conversion_signal_count', 0)}개")
            print(f"   프로필 액션 전환 신호: {metrics.get('profile_action_signal_count', 0)}개")
            print(f"   프로필 액션 고가치: {metrics.get('profile_action_high_count', 0)}개")
            print(f"   프로필 총 액션: {metrics.get('profile_action_total', 0)}회")
            print(f"   시간/예약 가용성 고의도: {metrics.get('availability_high_count', 0)}개")
            print(f"   시간/예약 가용성 검토: {metrics.get('availability_review_count', 0)}개")
            print(f"   비용/보험 고의도: {metrics.get('payment_high_count', 0)}개")
            print(f"   비용/보험 검토: {metrics.get('payment_review_count', 0)}개")
            print(f"   방문 편의/접근성 고의도: {metrics.get('access_high_count', 0)}개")
            print(f"   방문 편의/접근성 검토: {metrics.get('access_review_count', 0)}개")
            print(f"   의료광고 고위험: {metrics.get('medical_ad_high_risk_count', 0)}개")
            print(f"   의료광고 검토필요: {metrics.get('medical_ad_review_count', 0)}개")
            print(f"   서비스 적합도 차단: {metrics.get('service_fit_block_count', 0)}개")
            print(f"   서비스 적합도 검토: {metrics.get('service_fit_review_count', 0)}개")
            print(f"   제외 의도 플래그: {metrics.get('negative_intent_count', 0)}개")
            print(f"   평균 서비스 적합도: {metrics.get('avg_local_service_fit_score', 0):.1f}")
            print(f"   콘텐츠 실행 차단: {metrics.get('content_action_block_count', 0)}개")
            print(f"   콘텐츠 실행 검토: {metrics.get('content_action_review_count', 0)}개")
            print(f"   평균 콘텐츠 실행가능성: {metrics.get('avg_content_actionability_score', 0):.1f}")
            print(f"   로컬/플레이스 표면 고가치: {metrics.get('local_surface_high_count', 0)}개")
            print(f"   로컬/플레이스 표면 검토: {metrics.get('local_surface_review_count', 0)}개")
            print(f"   평균 로컬 표면 점수: {metrics.get('avg_local_surface_score', 0):.1f}")
            print(f"   자사 브랜드 방어: {metrics.get('own_brand_count', 0)}개")
            print(f"   경쟁사 브랜드 검토: {metrics.get('competitor_brand_count', 0)}개")
            print(f"   경쟁사 브랜드 고위험: {metrics.get('competitor_brand_high_risk_count', 0)}개")
            print(f"   리뷰/평판 표면 고가치: {metrics.get('review_surface_high_count', 0)}개")
            print(f"   평판 검토 필요: {metrics.get('reputation_review_count', 0)}개")
            print(f"   평판 고위험: {metrics.get('reputation_high_risk_count', 0)}개")
            print(f"   평균 리뷰 표면 점수: {metrics.get('avg_review_surface_score', 0):.1f}")
            print(f"   평균 사업가치 점수: {metrics.get('avg_business_value_score', 0):.1f}")
            print(f"   다중 소스 검증 비율: {metrics.get('multi_source_verified_rate', 0) * 100:.1f}%")
            print(f"   품질 플래그 비율: {metrics.get('quality_flag_rate', 0) * 100:.1f}%")

        return results

    def export_csv(self, results: List[KeywordResult], filename: str = "legion_v3_results.csv"):
        """CSV 내보내기 (KEI 포함)"""
        import csv

        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'keyword', 'search_volume', 'difficulty', 'opportunity',
                'grade', 'category', 'priority_score', 'source',
                'trend_slope', 'trend_status', 'search_intent',
                'document_count', 'kei', 'kei_grade', 'business_core',
                'source_signals', 'verification_score', 'novelty_score',
                'diversity_rank', 'quality_flags',
                'longtail_score', 'business_value_score', 'high_value_longtail',
                'inbound_impressions', 'inbound_clicks', 'inbound_ctr', 'inbound_position',
                'inbound_sources', 'mobile_share', 'content_cluster_key',
                'owned_rank', 'owned_rank_device', 'rank_gap_signal', 'rank_status',
                'community_mentions', 'community_conversion_fit', 'community_signal',
                'community_platforms', 'conversion_calls', 'conversion_naver_calls',
                'conversion_duration_seconds', 'conversion_signal',
                'profile_action_signal', 'profile_actions_total', 'profile_direction_actions',
                'profile_website_actions', 'profile_booking_actions', 'profile_message_actions',
                'profile_action_sources', 'profile_action_flags',
                'availability_intent_score', 'availability_intent_type', 'availability_action_flags',
                'payment_coverage_score', 'payment_coverage_type', 'payment_action_flags',
                'access_convenience_score', 'access_convenience_type', 'access_convenience_flags',
                'medical_ad_risk_score', 'medical_ad_risk_flags', 'content_feasibility_score',
                'local_service_fit_score', 'negative_intent_flags',
                'content_actionability_score', 'recommended_content_type', 'content_action_flags',
                'local_surface_score', 'preferred_search_surface', 'local_surface_flags',
                'brand_intent_type', 'brand_signal_score', 'brand_mentions',
                'competitor_brand_risk_score', 'brand_action_flags',
                'review_surface_score', 'reputation_risk_score',
                'review_intent_type', 'review_action_flags'
            ])
            writer.writeheader()
            for r in results:
                row = asdict(r)
                row.pop('merged_from', None)  # merged_from은 CSV에서 제외
                row['source_signals'] = json.dumps(row.get('source_signals') or [], ensure_ascii=False)
                row['quality_flags'] = json.dumps(row.get('quality_flags') or [], ensure_ascii=False)
                row['inbound_sources'] = json.dumps(row.get('inbound_sources') or [], ensure_ascii=False)
                row['community_platforms'] = json.dumps(row.get('community_platforms') or [], ensure_ascii=False)
                row['profile_action_sources'] = json.dumps(row.get('profile_action_sources') or [], ensure_ascii=False)
                row['profile_action_flags'] = json.dumps(row.get('profile_action_flags') or [], ensure_ascii=False)
                row['availability_action_flags'] = json.dumps(row.get('availability_action_flags') or [], ensure_ascii=False)
                row['payment_action_flags'] = json.dumps(row.get('payment_action_flags') or [], ensure_ascii=False)
                row['access_convenience_flags'] = json.dumps(row.get('access_convenience_flags') or [], ensure_ascii=False)
                row['medical_ad_risk_flags'] = json.dumps(row.get('medical_ad_risk_flags') or [], ensure_ascii=False)
                row['negative_intent_flags'] = json.dumps(row.get('negative_intent_flags') or [], ensure_ascii=False)
                row['content_action_flags'] = json.dumps(row.get('content_action_flags') or [], ensure_ascii=False)
                row['local_surface_flags'] = json.dumps(row.get('local_surface_flags') or [], ensure_ascii=False)
                row['brand_mentions'] = json.dumps(row.get('brand_mentions') or [], ensure_ascii=False)
                row['brand_action_flags'] = json.dumps(row.get('brand_action_flags') or [], ensure_ascii=False)
                row['review_action_flags'] = json.dumps(row.get('review_action_flags') or [], ensure_ascii=False)
                writer.writerow(row)

        print(f"\n📁 결과 저장: {filename}")

    def export_metrics(self, filename: str = "legion_v3_metrics.json"):
        """Export source yield, diversity, and verification metrics."""
        metrics = getattr(self, "diversity_metrics", {}) or {}
        if not metrics:
            return
        atomic_write_json(filename, metrics)
        print(f"💾 지표 저장: {filename}")

    def save_to_db(self, results: List[KeywordResult], db_path: str = None, scan_run_id: int = 0) -> dict:
        """DB 저장 (WSL + Dropbox 환경: 로컬 임시 파일 사용)"""
        import sqlite3
        import os
        import shutil
        import tempfile
        import time

        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "db", "marketing_data.db")

        print(f"\n💾 DB 저장: {db_path}")

        # WSL + Dropbox 환경: 로컬 임시 파일로 작업 후 복사
        is_wsl_dropbox = '/mnt/' in db_path and ('Dropbox' in db_path or 'OneDrive' in db_path)

        if is_wsl_dropbox and os.path.exists(db_path):
            # 1. WSL 로컬 임시 디렉토리에 DB 복사
            temp_dir = tempfile.mkdtemp(prefix='legion_db_')
            temp_db = os.path.join(temp_dir, 'marketing_data.db')

            print(f"   📋 WSL 환경 감지: 로컬 임시 파일 사용")
            print(f"   임시 경로: {temp_db}")

            shutil.copy2(db_path, temp_db)
            work_db_path = temp_db
        else:
            work_db_path = db_path
            temp_dir = None
            temp_db = None

        # DB 연결 (재시도 로직 추가)
        max_retries = 5
        retry_delay = 2
        conn = None

        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(work_db_path, timeout=120)
                cursor = conn.cursor()

                # SQLite 최적화 (WAL 모드로 다중 접근 허용)
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=60000")
                break
            except sqlite3.OperationalError as e:
                if attempt < max_retries - 1:
                    print(f"   ⚠️  DB 잠금 감지 (시도 {attempt+1}/{max_retries}), {retry_delay}초 후 재시도...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 지수 백오프
                else:
                    print(f"\n❌ DB 연결 실패: {e}")
                    print(f"   Dashboard나 다른 프로세스를 종료하고 다시 시도하세요.")
                    raise

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
            region TEXT DEFAULT '기타',
            category TEXT DEFAULT '기타',
            difficulty INTEGER DEFAULT 50,
            opportunity INTEGER DEFAULT 50,
            priority_v3 REAL DEFAULT 0,
            grade TEXT DEFAULT 'C',
            is_gap_keyword INTEGER DEFAULT 0,
            source TEXT DEFAULT 'legion'
        )''')

        # V3 + KEI 컬럼 추가
        for col, ctype in [("difficulty", "INTEGER DEFAULT 50"), ("opportunity", "INTEGER DEFAULT 50"),
                           ("priority_v3", "REAL DEFAULT 0"), ("grade", "TEXT DEFAULT 'C'"),
                           ("source", "TEXT DEFAULT 'legion'"),
                           ("trend_slope", "REAL DEFAULT 0"), ("trend_status", "TEXT DEFAULT 'unknown'"),
                           ("search_intent", "TEXT DEFAULT 'unknown'"),
                           # KEI 관련 컬럼 추가
                           ("document_count", "INTEGER DEFAULT 0"),
                           ("kei", "REAL DEFAULT 0.0"),
                           ("kei_grade", "TEXT DEFAULT 'C'"),
                           # 스캔 히스토리 연동
                           ("scan_run_id", "INTEGER DEFAULT 0"),
                           ("last_scan_run_id", "INTEGER DEFAULT 0"),
                           ("business_core", "INTEGER DEFAULT 0"),
                           ("source_signals_json", "TEXT DEFAULT '[]'"),
                           ("verification_score", "REAL DEFAULT 0"),
                           ("novelty_score", "REAL DEFAULT 0"),
                           ("diversity_rank", "INTEGER DEFAULT 0"),
                           ("quality_flags_json", "TEXT DEFAULT '[]'"),
                           ("longtail_score", "REAL DEFAULT 0"),
                           ("business_value_score", "REAL DEFAULT 0"),
                           ("high_value_longtail", "INTEGER DEFAULT 0"),
                           ("inbound_impressions", "INTEGER DEFAULT 0"),
                           ("inbound_clicks", "INTEGER DEFAULT 0"),
                           ("inbound_ctr", "REAL DEFAULT 0"),
                           ("inbound_position", "REAL DEFAULT 0"),
                           ("inbound_sources_json", "TEXT DEFAULT '[]'"),
                           ("mobile_share", "REAL DEFAULT 0"),
                           ("content_cluster_key", "TEXT DEFAULT ''"),
                           ("owned_rank", "INTEGER DEFAULT 0"),
                           ("owned_rank_device", "TEXT DEFAULT ''"),
                           ("rank_gap_signal", "REAL DEFAULT 0"),
                           ("rank_status", "TEXT DEFAULT 'unknown'"),
                           ("community_mentions", "INTEGER DEFAULT 0"),
                           ("community_conversion_fit", "REAL DEFAULT 0"),
                           ("community_signal", "REAL DEFAULT 0"),
                           ("community_platforms_json", "TEXT DEFAULT '[]'"),
                           ("conversion_calls", "INTEGER DEFAULT 0"),
                           ("conversion_naver_calls", "INTEGER DEFAULT 0"),
                           ("conversion_duration_seconds", "INTEGER DEFAULT 0"),
                           ("conversion_signal", "REAL DEFAULT 0"),
                           ("profile_action_signal", "REAL DEFAULT 0"),
                           ("profile_actions_total", "INTEGER DEFAULT 0"),
                           ("profile_direction_actions", "INTEGER DEFAULT 0"),
                           ("profile_website_actions", "INTEGER DEFAULT 0"),
                           ("profile_booking_actions", "INTEGER DEFAULT 0"),
                           ("profile_message_actions", "INTEGER DEFAULT 0"),
                           ("profile_action_sources_json", "TEXT DEFAULT '[]'"),
                           ("profile_action_flags_json", "TEXT DEFAULT '[]'"),
                           ("availability_intent_score", "REAL DEFAULT 0"),
                           ("availability_intent_type", "TEXT DEFAULT 'none'"),
                           ("availability_action_flags_json", "TEXT DEFAULT '[]'"),
                           ("payment_coverage_score", "REAL DEFAULT 0"),
                           ("payment_coverage_type", "TEXT DEFAULT 'none'"),
                           ("payment_action_flags_json", "TEXT DEFAULT '[]'"),
                           ("access_convenience_score", "REAL DEFAULT 0"),
                           ("access_convenience_type", "TEXT DEFAULT 'none'"),
                           ("access_convenience_flags_json", "TEXT DEFAULT '[]'"),
                           ("medical_ad_risk_score", "REAL DEFAULT 0"),
                           ("medical_ad_risk_flags_json", "TEXT DEFAULT '[]'"),
                           ("content_feasibility_score", "REAL DEFAULT 100"),
                           ("local_service_fit_score", "REAL DEFAULT 0"),
                           ("negative_intent_flags_json", "TEXT DEFAULT '[]'"),
                           ("content_actionability_score", "REAL DEFAULT 0"),
                           ("recommended_content_type", "TEXT DEFAULT ''"),
                           ("content_action_flags_json", "TEXT DEFAULT '[]'"),
                           ("local_surface_score", "REAL DEFAULT 0"),
                           ("preferred_search_surface", "TEXT DEFAULT ''"),
                           ("local_surface_flags_json", "TEXT DEFAULT '[]'"),
                           ("brand_intent_type", "TEXT DEFAULT 'generic'"),
                           ("brand_signal_score", "REAL DEFAULT 0"),
                           ("brand_mentions_json", "TEXT DEFAULT '[]'"),
                           ("competitor_brand_risk_score", "REAL DEFAULT 0"),
                           ("brand_action_flags_json", "TEXT DEFAULT '[]'"),
                           ("review_surface_score", "REAL DEFAULT 0"),
                           ("reputation_risk_score", "REAL DEFAULT 0"),
                           ("review_intent_type", "TEXT DEFAULT 'none'"),
                           ("review_action_flags_json", "TEXT DEFAULT '[]'")]:
            try:
                cursor.execute(f"ALTER TABLE keyword_insights ADD COLUMN {col} {ctype}")
            except Exception:
                pass  # 컬럼이 이미 존재하는 경우 무시

        # 저장 (배치 처리로 Dropbox 충돌 최소화)
        saved = 0
        inserted = 0
        updated = 0
        errors = 0
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        batch_size = 50  # 50개씩 배치 커밋

        for i, r in enumerate(results):
            try:
                region = GYULIM_KEYWORD_PROFILE.primary_region
                region_candidates = (
                    list(getattr(GYULIM_KEYWORD_PROFILE, "neighborhoods", ()))
                    + list(getattr(GYULIM_KEYWORD_PROFILE, "cheongju_regions", ()))
                    + list(getattr(GYULIM_KEYWORD_PROFILE, "nearby_regions", ()))
                )
                for reg in region_candidates:
                    if reg in r.keyword:
                        region = reg
                        break

                tag = "일반"
                if any(w in r.keyword for w in ["가격", "비용"]):
                    tag = "구매의도"
                elif any(w in r.keyword for w in ["후기", "추천"]):
                    tag = "신뢰의도"

                cursor.execute("SELECT 1 FROM keyword_insights WHERE keyword = ?", (r.keyword,))
                existed = cursor.fetchone() is not None

                cursor.execute('''
                    INSERT INTO keyword_insights (
                        keyword, volume, competition, opp_score, tag, created_at,
                        search_volume, region, category,
                        difficulty, opportunity, priority_v3, grade, source,
                        trend_slope, trend_status, search_intent,
                        document_count, kei, kei_grade,
                        scan_run_id, last_scan_run_id, business_core,
                        source_signals_json, verification_score, novelty_score,
                        diversity_rank, quality_flags_json,
                        longtail_score, business_value_score, high_value_longtail,
                        inbound_impressions, inbound_clicks, inbound_ctr,
                        inbound_position, inbound_sources_json,
                        mobile_share, content_cluster_key,
                        owned_rank, owned_rank_device, rank_gap_signal, rank_status,
                        community_mentions, community_conversion_fit,
                        community_signal, community_platforms_json,
                        conversion_calls, conversion_naver_calls,
                        conversion_duration_seconds, conversion_signal,
                        profile_action_signal, profile_actions_total,
                        profile_direction_actions, profile_website_actions,
                        profile_booking_actions, profile_message_actions,
                        profile_action_sources_json, profile_action_flags_json,
                        availability_intent_score, availability_intent_type,
                        availability_action_flags_json,
                        payment_coverage_score, payment_coverage_type,
                        payment_action_flags_json,
                        access_convenience_score, access_convenience_type,
                        access_convenience_flags_json,
                        medical_ad_risk_score, medical_ad_risk_flags_json,
                        content_feasibility_score, local_service_fit_score,
                        negative_intent_flags_json, content_actionability_score,
                        recommended_content_type, content_action_flags_json,
                        local_surface_score, preferred_search_surface,
                        local_surface_flags_json, brand_intent_type,
                        brand_signal_score, brand_mentions_json,
                        competitor_brand_risk_score, brand_action_flags_json,
                        review_surface_score, reputation_risk_score,
                        review_intent_type, review_action_flags_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(keyword) DO UPDATE SET
                        difficulty=excluded.difficulty,
                        opportunity=excluded.opportunity,
                        priority_v3=excluded.priority_v3,
                        grade=excluded.grade,
                        source=excluded.source,
                        trend_slope=excluded.trend_slope,
                        trend_status=excluded.trend_status,
                        search_intent=excluded.search_intent,
                        document_count=excluded.document_count,
                        kei=excluded.kei,
                        kei_grade=excluded.kei_grade,
                        created_at=excluded.created_at,
                        last_scan_run_id=excluded.last_scan_run_id,
                        business_core=excluded.business_core,
                        category=excluded.category,
                        search_volume=excluded.search_volume,
                        region=excluded.region,
                        source_signals_json=excluded.source_signals_json,
                        verification_score=excluded.verification_score,
                        novelty_score=excluded.novelty_score,
                        diversity_rank=excluded.diversity_rank,
                        quality_flags_json=excluded.quality_flags_json,
                        longtail_score=excluded.longtail_score,
                        business_value_score=excluded.business_value_score,
                        high_value_longtail=excluded.high_value_longtail,
                        inbound_impressions=excluded.inbound_impressions,
                        inbound_clicks=excluded.inbound_clicks,
                        inbound_ctr=excluded.inbound_ctr,
                        inbound_position=excluded.inbound_position,
                        inbound_sources_json=excluded.inbound_sources_json,
                        mobile_share=excluded.mobile_share,
                        content_cluster_key=excluded.content_cluster_key,
                        owned_rank=excluded.owned_rank,
                        owned_rank_device=excluded.owned_rank_device,
                        rank_gap_signal=excluded.rank_gap_signal,
                        rank_status=excluded.rank_status,
                        community_mentions=excluded.community_mentions,
                        community_conversion_fit=excluded.community_conversion_fit,
                        community_signal=excluded.community_signal,
                        community_platforms_json=excluded.community_platforms_json,
                        conversion_calls=excluded.conversion_calls,
                        conversion_naver_calls=excluded.conversion_naver_calls,
                        conversion_duration_seconds=excluded.conversion_duration_seconds,
                        conversion_signal=excluded.conversion_signal,
                        profile_action_signal=excluded.profile_action_signal,
                        profile_actions_total=excluded.profile_actions_total,
                        profile_direction_actions=excluded.profile_direction_actions,
                        profile_website_actions=excluded.profile_website_actions,
                        profile_booking_actions=excluded.profile_booking_actions,
                        profile_message_actions=excluded.profile_message_actions,
                        profile_action_sources_json=excluded.profile_action_sources_json,
                        profile_action_flags_json=excluded.profile_action_flags_json,
                        availability_intent_score=excluded.availability_intent_score,
                        availability_intent_type=excluded.availability_intent_type,
                        availability_action_flags_json=excluded.availability_action_flags_json,
                        payment_coverage_score=excluded.payment_coverage_score,
                        payment_coverage_type=excluded.payment_coverage_type,
                        payment_action_flags_json=excluded.payment_action_flags_json,
                        access_convenience_score=excluded.access_convenience_score,
                        access_convenience_type=excluded.access_convenience_type,
                        access_convenience_flags_json=excluded.access_convenience_flags_json,
                        medical_ad_risk_score=excluded.medical_ad_risk_score,
                        medical_ad_risk_flags_json=excluded.medical_ad_risk_flags_json,
                        content_feasibility_score=excluded.content_feasibility_score,
                        local_service_fit_score=excluded.local_service_fit_score,
                        negative_intent_flags_json=excluded.negative_intent_flags_json,
                        content_actionability_score=excluded.content_actionability_score,
                        recommended_content_type=excluded.recommended_content_type,
                        content_action_flags_json=excluded.content_action_flags_json,
                        local_surface_score=excluded.local_surface_score,
                        preferred_search_surface=excluded.preferred_search_surface,
                        local_surface_flags_json=excluded.local_surface_flags_json,
                        brand_intent_type=excluded.brand_intent_type,
                        brand_signal_score=excluded.brand_signal_score,
                        brand_mentions_json=excluded.brand_mentions_json,
                        competitor_brand_risk_score=excluded.competitor_brand_risk_score,
                        brand_action_flags_json=excluded.brand_action_flags_json,
                        review_surface_score=excluded.review_surface_score,
                        reputation_risk_score=excluded.reputation_risk_score,
                        review_intent_type=excluded.review_intent_type,
                        review_action_flags_json=excluded.review_action_flags_json
                ''', (
                    r.keyword, 0, "Low" if r.difficulty < 50 else "High",
                    r.priority_score, tag, now,
                    r.search_volume, region, r.category,
                    r.difficulty, r.opportunity, r.priority_score, r.grade, r.source,
                    r.trend_slope, r.trend_status, r.search_intent,
                    r.document_count, r.kei, r.kei_grade,
                    scan_run_id, scan_run_id, 1 if r.business_core else 0,
                    json.dumps(r.source_signals or [], ensure_ascii=False),
                    r.verification_score, r.novelty_score, r.diversity_rank,
                    json.dumps(r.quality_flags or [], ensure_ascii=False),
                    r.longtail_score, r.business_value_score, 1 if r.high_value_longtail else 0,
                    r.inbound_impressions, r.inbound_clicks, r.inbound_ctr,
                    r.inbound_position, json.dumps(r.inbound_sources or [], ensure_ascii=False),
                    r.mobile_share, r.content_cluster_key,
                    r.owned_rank, r.owned_rank_device, r.rank_gap_signal, r.rank_status,
                    r.community_mentions, r.community_conversion_fit, r.community_signal,
                    json.dumps(r.community_platforms or [], ensure_ascii=False),
                    r.conversion_calls, r.conversion_naver_calls,
                    r.conversion_duration_seconds, r.conversion_signal,
                    r.profile_action_signal,
                    r.profile_actions_total,
                    r.profile_direction_actions,
                    r.profile_website_actions,
                    r.profile_booking_actions,
                    r.profile_message_actions,
                    json.dumps(r.profile_action_sources or [], ensure_ascii=False),
                    json.dumps(r.profile_action_flags or [], ensure_ascii=False),
                    r.availability_intent_score,
                    r.availability_intent_type,
                    json.dumps(r.availability_action_flags or [], ensure_ascii=False),
                    r.payment_coverage_score,
                    r.payment_coverage_type,
                    json.dumps(r.payment_action_flags or [], ensure_ascii=False),
                    r.access_convenience_score,
                    r.access_convenience_type,
                    json.dumps(r.access_convenience_flags or [], ensure_ascii=False),
                    r.medical_ad_risk_score,
                    json.dumps(r.medical_ad_risk_flags or [], ensure_ascii=False),
                    r.content_feasibility_score,
                    r.local_service_fit_score,
                    json.dumps(r.negative_intent_flags or [], ensure_ascii=False),
                    r.content_actionability_score,
                    r.recommended_content_type,
                    json.dumps(r.content_action_flags or [], ensure_ascii=False),
                    r.local_surface_score,
                    r.preferred_search_surface,
                    json.dumps(r.local_surface_flags or [], ensure_ascii=False),
                    r.brand_intent_type,
                    r.brand_signal_score,
                    json.dumps(r.brand_mentions or [], ensure_ascii=False),
                    r.competitor_brand_risk_score,
                    json.dumps(r.brand_action_flags or [], ensure_ascii=False),
                    r.review_surface_score,
                    r.reputation_risk_score,
                    r.review_intent_type,
                    json.dumps(r.review_action_flags or [], ensure_ascii=False)
                ))
                saved += 1
                if existed:
                    updated += 1
                else:
                    inserted += 1

                # 배치 커밋 (Dropbox 동기화 충돌 방지)
                if (i + 1) % batch_size == 0:
                    conn.commit()
                    time.sleep(0.1)  # Dropbox 동기화 시간 확보
                    print(f"   진행: {saved}/{len(results)}개 저장...")

            except Exception as e:
                errors += 1
                if errors <= 3:  # 처음 3개만 에러 출력
                    print(f"   오류 ({r.keyword}): {e}")

        # 최종 커밋
        conn.commit()
        conn.close()

        # WSL 환경: 임시 파일을 원본 경로로 복사
        if is_wsl_dropbox and temp_dir:
            import shutil
            print(f"   📤 원본 DB로 복사 중...")
            time.sleep(0.5)  # Dropbox 동기화 대기

            try:
                # 원본 백업
                backup_path = db_path + '.backup'
                if os.path.exists(db_path):
                    shutil.copy2(db_path, backup_path)

                # 임시 파일을 원본으로 복사
                shutil.copy2(temp_db, db_path)
                print(f"   ✅ DB 복사 완료")

                # 임시 디렉토리 정리
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                print(f"   ⚠️ 복사 실패: {e}")
                print(f"   임시 파일 위치: {temp_db}")
                print(f"   수동으로 복사하세요: cp {temp_db} {db_path}")

        print(
            f"   ✅ {saved}/{len(results)}개 처리 완료"
            f" (신규: {inserted}개, 업데이트: {updated}개)"
            + (f" (에러: {errors}개)" if errors else "")
        )
        return {
            "processed": saved,
            "inserted": inserted,
            "updated": updated,
            "errors": errors,
        }


def main():
    parser = argparse.ArgumentParser(description="Pathfinder V3 LEGION MODE")
    parser.add_argument("--target", type=int, default=300, help="목표 S/A급 키워드 수 (기본: 300)")
    parser.add_argument("--no-db", action="store_true", help="DB 저장 안 함")
    parser.add_argument("--no-csv", action="store_true", help="CSV 저장 안 함")
    parser.add_argument("--save-db", action="store_true", help="DB에 저장 (--no-db의 반대)")
    parser.add_argument("--max-rounds", type=int, default=10, help="Maximum Legion rounds to run.")
    parser.add_argument("--round1-seed-limit", type=int, default=None, help="Limit initial seed count for Round 1.")
    parser.add_argument("--no-google", action="store_true", help="Disable Google autocomplete source.")
    parser.add_argument("--skip-ad-related", action="store_true", help="Skip Round 1 Naver ad related keyword expansion.")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Fast validation mode: no Google, 1 round, 3 seeds, no DB/CSV writes.",
    )
    args = parser.parse_args()

    if args.smoke:
        args.no_db = True
        args.no_csv = True
        args.max_rounds = 1
        args.round1_seed_limit = 3 if args.round1_seed_limit is None else min(args.round1_seed_limit, 3)
        args.no_google = True
        args.skip_ad_related = True

    # 실시간 로그 스트리밍 설정
    tee = setup_live_logging()

    # 스캔 시작 시간 기록
    start_time = time.time()

    # 스캔 기록 생성 (DB 저장 모드일 때만)
    scan_run_id = 0
    if not args.no_db:
        scan_run_id = create_scan_run(
            scan_type="legion",
            mode="legion",
            target_count=args.target
        )

    legion = PathfinderLegion()
    if args.no_google:
        legion.collector.use_google = False

    try:
        results = legion.run(
            target_sa=args.target,
            max_rounds=args.max_rounds,
            round1_seed_limit=args.round1_seed_limit,
            skip_ad_related=args.skip_ad_related,
        )

        print("\n" + "=" * 70)
        print(f"✅ LEGION MODE 완료! 총 {len(results)}개 키워드")
        print("=" * 70)

        # 성능 통계 출력
        serp_stats = legion.serp.get_stats()
        print(f"\n📊 성능 통계:")
        print(f"   SERP 분석: {serp_stats['analyzed']}건")
        print(f"   캐시 히트: {serp_stats['cache_hits']}건")
        if serp_stats['analyzed'] + serp_stats['cache_hits'] > 0:
            hit_rate = serp_stats['cache_hits'] / (serp_stats['analyzed'] + serp_stats['cache_hits']) * 100
            print(f"   캐시 적중률: {hit_rate:.1f}%")

        if not args.no_csv:
            legion.export_csv(results)
            legion.export_metrics()

        # DB 저장 (기본값: True, --no-db로 비활성화)
        if not args.no_db:
            save_stats = legion.save_to_db(results, scan_run_id=scan_run_id)

            # 스캔 완료 통계 계산
            s_count = sum(1 for r in results if r.grade == 'S')
            a_count = sum(1 for r in results if r.grade == 'A')
            b_count = sum(1 for r in results if r.grade == 'B')
            c_count = sum(1 for r in results if r.grade == 'C')

            # 상위 키워드 추출
            top_keywords = [
                {
                    "keyword": r.keyword,
                    "grade": r.grade,
                    "kei": r.kei,
                    "verification_score": r.verification_score,
                    "diversity_rank": r.diversity_rank,
                }
                for r in results[:10]
            ]

            execution_time = int(time.time() - start_time)

            # 스캔 기록 업데이트
            update_scan_run(
                run_id=scan_run_id,
                status="completed",
                total_keywords=len(results),
                new_keywords=save_stats.get("inserted", 0),
                updated_keywords=save_stats.get("updated", 0),
                s_count=s_count,
                a_count=a_count,
                b_count=b_count,
                c_count=c_count,
                top_keywords=top_keywords,
                execution_time=execution_time,
                notes=json.dumps(getattr(legion, "diversity_metrics", {}) or {}, ensure_ascii=False)[:4000]
            )

    except Exception as e:
        # 스캔 실패 시 에러 기록
        if scan_run_id:
            execution_time = int(time.time() - start_time)
            update_scan_run(
                run_id=scan_run_id,
                status="failed",
                error_message=str(e),
                execution_time=execution_time
            )
        raise


if __name__ == "__main__":
    main()

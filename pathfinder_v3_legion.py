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
- Round 8: AI 시맨틱 확장 (Gemini)
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import atexit
import requests
import re
import time
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
from pathlib import Path
from functools import lru_cache

# 품질 필터 (노이즈 제거)
try:
    from core_services.keyword_filter import KeywordQualityFilter
    HAS_QUALITY_FILTER = True
except ImportError:
    HAS_QUALITY_FILTER = False
    print("⚠️ KeywordQualityFilter 미설치 - 기본 필터만 사용")

# AI 키워드 확장 (Gemini)
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
            with open(self.status_file_path, 'w', encoding='utf-8') as f:
                json.dump(status_data, f, ensure_ascii=False, indent=2)
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

    def __post_init__(self):
        if self.merged_from is None:
            self.merged_from = []


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
        ],
        'commercial': [
            # 검토/추천 의도 (validation·comparison와 분리됨)
            '추천', '순위', '랭킹', '베스트', '인기',
            '후기', '리뷰', '평가', '잘하는', '유명한', '좋은',
            '전문', '1위', 'top', '맛집',
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
                        keywords.append((f"청주 {kw}", category))

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

            # 검색량 합산 (옵션)
            total_volume = sum(results[k].search_volume for k in group)
            best_result.search_volume = total_volume

            # KEI 재계산 (검색량 합산 후)
            if best_result.document_count > 0 and total_volume > 0:
                best_result.kei = round((total_volume ** 2) / best_result.document_count, 2)
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

    # 한의원과 무관한 키워드 블랙리스트
    # (피부과/내과는 한의원과 경쟁 관계이므로 유지)
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

        # 청주 지역
        self.cheongju_regions = [
            "청주", "상당", "서원", "흥덕", "청원",
            "복대", "가경", "율량", "오창", "오송",
            "분평", "봉명", "산남", "용암", "금천"
        ]

        # 확장 지역 (인근 도시) - 보고서 분석 반영
        self.nearby_regions = ["충주", "제천", "진천", "증평", "괴산", "음성", "세종"]

        # 동네 (세부 지역)
        self.neighborhoods = [
            "복대동", "가경동", "분평동", "봉명동", "사창동",
            "산남동", "수곡동", "모충동", "용암동", "금천동",
            "율량동", "사직동", "성화동", "내덕동", "우암동"
        ]

        # 한의원 관련 키워드 (S/A급 0% 카테고리 키워드 추가)
        self.hanbang_keywords = [
            "한의원", "한방", "한약", "침", "추나", "부항", "뜸",
            "안면비대칭", "얼굴비대칭", "턱비대칭", "비대칭",
            "체형교정", "골반교정", "척추교정", "자세교정",
            "교통사고", "자동차사고", "후유증", "입원",
            "여드름", "여드름흉터", "새살침", "흉터", "피부", "아토피",
            "다이어트", "비만", "살빼", "체중",
            "통증", "디스크", "허리", "어깨", "무릎",
            "갱년기", "생리", "산후", "불임",
            "불면", "두통", "어지럼",
            # 추가 (2026-01-31): S/A급 0% 카테고리
            "편두통", "만성두통", "어지럼증",
            "다한증", "냉증", "수족냉증", "땀",
            "자율신경", "스트레스", "화병", "불안", "우울"
        ]

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
                "여드름", "여드름흉터", "새살침", "피부", "흉터",
                "여드름한의원", "피부한의원", "성인여드름", "턱여드름", "등여드름",
                "여드름자국", "흉터치료", "패인흉터", "여드름압출", "피부트러블", "모공",
                "기미", "주근깨", "잡티", "사마귀"
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

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    # ===== 도메인/지역 적합도 헬퍼 (관련도 강등용) =====

    # 한의원 외 의료 일반과 (한의원 콘텐츠 후보 부적합)
    MEDICAL_GENERAL_TOKENS = (
        '피부과', '내과', '이비인후과', '안과', '치과',
        '정형외과', '성형외과', '신경외과', '비뇨기과', '산부인과',
        '소아과', '가정의학과', '외과', '응급실',
    )

    # 한방 indicator (이게 있으면 한의원 컨텍스트로 인정)
    HANBANG_INDICATORS = (
        '한의원', '한방', '한약', '한약재', '침', '추나',
        '뜸', '부항', '경혈', '한의사', '한방병원',
    )

    def _is_medical_general(self, keyword: str) -> bool:
        """한의원 외 의료 일반과 키워드 (한방 indicator 부재 시 True)"""
        if not any(t in keyword for t in self.MEDICAL_GENERAL_TOKENS):
            return False
        # 한방 indicator 동반 시 한의원 비교 콘텐츠로 활용 가능 → 강등 면제
        return not any(h in keyword for h in self.HANBANG_INDICATORS)

    def _is_in_target_region(self, keyword: str) -> bool:
        """본 사업영역(청주 행정구역) 매칭. 인접 시(충주/제천/세종 등)는 False."""
        return any(r in keyword for r in self.cheongju_regions) or \
               any(n in keyword for n in self.neighborhoods)

    def apply_relevance_demotion(self, keyword: str, grade: str) -> Tuple[str, Optional[str]]:
        """
        도메인/지역 관련도 기반 등급 강등.
        Returns: (new_grade, reason or None)
        - 의료 일반과: S/A/B → C (사업 무관)
        - 비-청주 지역: 2단계 강등 (S→B, A→C — 사업영역 외 격하)
        """
        # P1: 의료 일반과 누수 차단
        if self._is_medical_general(keyword):
            if grade in ('S', 'A', 'B'):
                return 'C', 'medical_general'
        # P2: 비-청주 지역 2단계 강등 (S→B, A→C, B→C)
        if not self._is_in_target_region(keyword):
            order = ['S', 'A', 'B', 'C']
            if grade in order:
                idx = order.index(grade)
                new_idx = min(idx + 2, len(order) - 1)
                if new_idx > idx:
                    return order[new_idx], 'non_cheongju'
        return grade, None

    def _detect_category(self, keyword: str) -> str:
        kw = keyword.lower()
        # 한방 indicator는 카테고리 매칭 우선 — "기타" fallback 누수 방지
        for cat, patterns in self.category_patterns.items():
            if any(p in kw for p in patterns):
                return cat
        # 한의원/한약 들어있는데 다른 카테고리에 매칭 안 됐으면 한의원일반
        if any(h in kw for h in ('한의원', '한약', '한방', '한방병원')):
            return '한의원일반'
        return "기타"

    def is_focus_candidate(self, keyword: str, category: Optional[str] = None) -> bool:
        """규림 기본 Legion 타깃: 미용 한의원 + 교통사고 입원실 중심."""
        if category is None:
            category = self._detect_category(keyword)

        focus_categories = {
            "다이어트", "안면비대칭", "체형교정",
            "피부/여드름", "리프팅/탄력", "교통사고",
        }
        if category in focus_categories:
            return True

        accident_context = ("교통사고", "자동차사고", "사고", "입원", "자보", "자동차보험")
        if category == "통증/디스크" and any(token in keyword for token in accident_context):
            return True

        return False

    def _is_valid_keyword(self, keyword: str) -> bool:
        """유효한 키워드인지 확인"""
        # 청주 또는 인근 지역 포함
        has_region = any(r in keyword for r in self.cheongju_regions + self.nearby_regions + self.neighborhoods)
        # 한방 관련 키워드 포함
        has_hanbang = any(h in keyword for h in self.hanbang_keywords)
        return has_region and has_hanbang

    def _filter_blacklist(self, keywords: List[str]) -> List[str]:
        """블랙리스트 키워드 필터링"""
        if not keywords:
            return keywords
        return [kw for kw in keywords
                if not any(bl in kw for bl in self.BLACKLIST_KEYWORDS)]

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
        for region in ["청주", "충주", "제천", "진천", "증평"]:
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
    return round((search_volume ** 2) / document_count, 2)


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

        # 규림한의원 핵심 시드
        self.base_seeds = [
            # 안면비대칭/체형교정
            "청주 안면비대칭", "청주 안면비대칭 교정", "청주 얼굴비대칭",
            "청주 체형교정", "청주 골반교정", "청주 자세교정",

            # 교통사고
            "청주 교통사고", "청주 교통사고 한의원", "청주 교통사고 입원",

            # 피부/여드름
            "청주 여드름", "청주 여드름 한의원", "청주 여드름흉터",
            "청주 새살침", "청주 피부 한의원", "청주 아토피",

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

        # ========== 시즌 키워드 추가 (ULTRA 이식) ==========
        seasonal_seeds = SeasonalKeywordDB.get_current_seasonal_keywords()
        if seasonal_seeds:
            focused_seasonal = [
                kw for kw, category in seasonal_seeds
                if category in {"다이어트", "안면비대칭", "여드름", "피부", "교통사고", "리프팅"}
                   or self.collector.is_focus_candidate(kw)
            ]
            print(f"📅 시즌 키워드 추가: {len(focused_seasonal)}/{len(seasonal_seeds)}개 (현재: {datetime.now().month}월)")
            self.base_seeds.extend(focused_seasonal)

        # 수집된 키워드
        self.collected: Dict[str, KeywordResult] = {}
        self.analyzed_keywords: Set[str] = set()

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
        keyword_lower = keyword.lower()
        score = 0.0

        # Tier 1: 핵심 한방 키워드 (+40)
        tier1 = ['한의원', '한방', '한약', '침', '추나', '부항', '뜸']
        if any(t in keyword_lower for t in tier1):
            score += 40

        # Tier 2: 주요 시술/진료 (+30)
        tier2 = ['다이어트', '교통사고', '입원', '자동차사고', '안면비대칭', '비대칭', '여드름', '여드름흉터', '흉터', '새살침']
        if any(t in keyword_lower for t in tier2):
            score += 30

        # Tier 3: 지역 (+20)
        tier3 = ['청주', '충북', '세종', '오창', '오송', '율량']
        if any(t in keyword_lower for t in tier3):
            score += 20

        # Tier 4: 전환 의도 (+10)
        tier4 = ['가격', '비용', '후기', '추천', '예약', '잘하는']
        if any(t in keyword_lower for t in tier4):
            score += 10

        return min(score, 100.0)

    def _calculate_priority(self, difficulty: int, opportunity: int, keyword: str,
                             search_volume: int = 0, kei: float = 0.0,
                             trend_slope: float = 0.0) -> float:
        """
        MF-KEI 5.0 점수 계산 (트렌드 + 계절성 + 비즈니스 관련도 반영)

        공식: KEI 30% + 기회 25% + 난이도 20% + 트렌드 15% + 계절성/관련도 10%

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

        # 5. 계절성 + 비즈니스 관련도 점수
        seasonality_score = self._calculate_seasonality_score(keyword)
        relevance_score = self._calculate_business_relevance(keyword)
        combined_score = (seasonality_score * 0.5) + (relevance_score * 0.5)

        # 6. MF-KEI 5.0 가중 평균
        base_score = (
            kei_score * 0.30 +
            opportunity_score * 0.25 +
            difficulty_score * 0.20 +
            trend_score * 0.15 +
            combined_score * 0.10
        )

        # 7. 검색 의도 가중치 (검색량 50 이상만 적용)
        intent_weight = 1.0
        if search_volume >= 50:
            if any(w in keyword for w in ["가격", "비용", "예약"]):
                intent_weight = 1.5
            elif any(w in keyword for w in ["후기", "추천"]):
                intent_weight = 1.3

        # 최종 점수 (최대 300)
        return base_score * intent_weight

    def _analyze_and_add(self, keywords: List[str], source: str) -> int:
        """키워드 분석 후 추가, 새로 추가된 S/A급 개수 반환"""
        new_sa = 0
        filtered_count = 0

        # 1단계: 기본 유효성 필터링 + 띄어쓰기 변형 추가
        valid_keywords = []
        for kw in keywords:
            if kw in self.analyzed_keywords:
                continue
            if not self.collector._is_valid_keyword(kw):
                continue
            valid_keywords.append(kw)
            self.analyzed_keywords.add(kw)

            # 띄어쓰기 변형 추가 (예: "가경동 한의원" → "가경동한의원")
            kw_no_space = kw.replace(" ", "")
            if kw_no_space != kw and kw_no_space not in self.analyzed_keywords:
                if self.collector._is_valid_keyword(kw_no_space):
                    valid_keywords.append(kw_no_space)
                    self.analyzed_keywords.add(kw_no_space)

        if not valid_keywords:
            return 0

        # 2단계: 품질 필터 적용 (노이즈, 블랙리스트 제거)
        if self.quality_filter:
            passed, rejected = self.quality_filter.filter_batch(valid_keywords)
            filtered_count = len(rejected)
            if filtered_count > 0:
                print(f"   🧹 품질 필터: {filtered_count}개 제거")
            valid_keywords = passed

        # 기본 Legion은 미용/흉터/비대칭/다이어트/교통사고 입원실에 집중한다.
        focus_keywords = []
        non_focus_count = 0
        for kw in valid_keywords:
            if self.collector.is_focus_candidate(kw):
                focus_keywords.append(kw)
            else:
                non_focus_count += 1

        if non_focus_count:
            print(f"   🎯 포커스 필터: 비핵심 진료군 {non_focus_count}개 제외")
        valid_keywords = focus_keywords

        if not valid_keywords:
            return 0

        # 검색량 일괄 조회 (Naver Ad API)
        volume_map = {}
        if self.has_ad_api and self.ad_manager:
            try:
                result = self.ad_manager.get_keyword_volumes(valid_keywords)
                # None 방어 처리
                volume_map = result if result is not None else {}
                if volume_map:
                    print(f"   📊 검색량 조회: {len(volume_map)}개")
            except Exception as e:
                print(f"   ⚠️ 검색량 조회 실패: {e}")
                volume_map = {}  # 예외 발생 시 빈 딕셔너리로 초기화

        # SERP 분석 (샘플링 + 배치 처리)
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

            # 도메인·지역 관련도 강등 (의료일반·비-청주 누수 차단)
            grade, demote_reason = self.collector.apply_relevance_demotion(kw, grade)
            if demote_reason and kei_grade in ('S', 'A', 'B'):
                # KEI 기반 등급도 동일하게 강등 (보고서 일관성)
                if demote_reason == 'medical_general':
                    kei_grade = 'C'
                elif demote_reason == 'non_cheongju':
                    _order = ['S', 'A', 'B', 'C']
                    _idx = _order.index(kei_grade)
                    kei_grade = _order[min(_idx + 2, len(_order) - 1)]

            # 우선순위 점수 계산 (KEI 포함)
            priority = self._calculate_priority(difficulty, opportunity, kw, search_volume, kei)

            # 검색 의도 분류
            search_intent = SearchIntentClassifier.classify(kw)

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
                kei_grade=kei_grade
            )

            self.collected[kw] = result

            if grade in ['S', 'A']:
                new_sa += 1

        return new_sa

    def run(self, target_sa: int = 500, max_rounds: int = 10) -> List[KeywordResult]:
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

        for seed in self.base_seeds:
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

        if total_sa >= target_sa:
            return self._finalize()

        # ==========================================
        # Round 2: S/A급 키워드 재확장 (의도 suffix 추가)
        # ==========================================
        round_num += 1
        print(f"\n[Round {round_num}] S/A급 키워드 재확장 (의도 기반)...")

        sa_keywords = [kw for kw, r in self.collected.items() if r.grade in ['S', 'A']]
        round2_keywords = set()

        # 의도 suffix - Round 4와 다른 세트로 차별화
        round2_suffixes = ["비용", "효과", "전후", "방법", "기간"]

        for kw in sa_keywords[:50]:  # 상위 50개로 확대
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

        # ==========================================
        # Round 3: 지역 확장 (동네별)
        # ==========================================
        round_num += 1
        print(f"\n[Round {round_num}] 지역 확장 (동네별)...")

        core_terms = ["다이어트", "교통사고", "교통사고 입원", "안면비대칭", "여드름흉터", "새살침"]
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

        # ==========================================
        # Round 4: 의도 확장 (B: 의도 기반 롱테일 강화)
        # ==========================================
        round_num += 1
        print(f"\n[Round {round_num}] 의도 확장 (전환 의도 키워드)...")

        # 기존 S/A/B급 키워드에 의도 suffix 추가 - 전체 사용
        good_keywords = [kw for kw, r in self.collected.items() if r.grade in ['S', 'A', 'B']]
        round4_keywords = set()

        generic_high_intent = ["가격", "비용", "예약", "후기", "추천"]
        accident_high_intent = ["자보", "자동차보험", "보험", "치료비"]
        high_intent_pool = set(generic_high_intent + accident_high_intent)
        other_intent = [i for i in self.collector.intent_suffixes if i not in high_intent_pool]

        for kw in good_keywords[:70]:  # 50 → 70개로 확대
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

        if total_sa >= target_sa:
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

            competitors = config.get("competitors", [])
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
                region = self.collector.regions[0] if self.collector.regions else "청주"
                for cat in ["다이어트", "교통사고", "한의원"]:
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

        # ==========================================
        # Round 6: 연관검색어 (확대 적용)
        # ==========================================
        round_num += 1
        print(f"\n[Round {round_num}] 연관검색어 수집 (S/A급 전체 + B급 상위)...")

        # S/A급 전체 + B급 상위 30개로 확대
        sa_keywords = [kw for kw, r in self.collected.items() if r.grade in ['S', 'A']]
        b_keywords = [kw for kw, r in self.collected.items() if r.grade == 'B'][:30]
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

        # ==========================================
        # Round 6.5: 블로그 제목 마이닝
        # ==========================================
        if self.blog_miner:
            round_num += 1
            print(f"\n[Round {round_num}] 블로그 제목 마이닝...")

            # S/A급 키워드로 블로그 검색하여 추가 키워드 발굴
            sa_keywords = [kw for kw, r in self.collected.items() if r.grade in ['S', 'A']][:15]

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

        # ==========================================
        # Round 7: 문제 해결형 키워드 (C: 증상 + 고민)
        # ==========================================
        round_num += 1
        print(f"\n[Round {round_num}] 문제 해결형 키워드 (증상/고민 기반)...")

        round7_keywords = set()
        region = "청주"  # 기본 지역

        # 문제 키워드 + 지역 조합
        for problem in self.collector.problem_keywords:
            # 지역 + 문제
            seed1 = f"{region} {problem}"
            round7_keywords.add(seed1)
            suggestions = self.collector.get_autocomplete(seed1)
            if suggestions is not None:
                round7_keywords.update(suggestions)

            # 문제 + 한의원/치료
            for suffix in ["한의원", "치료", "병원"]:
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

        # ==========================================
        # Round 8: AI 시맨틱 확장 (Gemini)
        # ==========================================
        if self.has_ai_expander and self.ai_expander:
            round_num += 1
            print(f"\n[Round {round_num}] AI 시맨틱 확장 (Gemini)...")

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
            b_keywords = [kw for kw, r in self.collected.items() if r.grade == 'B']
            extra_keywords = set()

            for kw in b_keywords[:20]:
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

        # S/A급 키워드 트렌드 분석
        if self.has_datalab and self.datalab:
            sa_keywords = [r for r in results if r.grade in ['S', 'A']]
            if sa_keywords:
                print(f"\n[트렌드 분석] S/A급 {len(sa_keywords)}개 키워드 분석 중...")
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
                        r.priority_score = self._calculate_priority(
                            r.difficulty, r.opportunity, r.keyword,
                            r.search_volume, r.kei, r.trend_slope
                        )
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

        return results

    def export_csv(self, results: List[KeywordResult], filename: str = "legion_v3_results.csv"):
        """CSV 내보내기 (KEI 포함)"""
        import csv

        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'keyword', 'search_volume', 'difficulty', 'opportunity',
                'grade', 'category', 'priority_score', 'source',
                'trend_slope', 'trend_status', 'search_intent',
                'document_count', 'kei', 'kei_grade'  # KEI 필드 추가
            ])
            writer.writeheader()
            for r in results:
                row = asdict(r)
                row.pop('merged_from', None)  # merged_from은 CSV에서 제외
                writer.writerow(row)

        print(f"\n📁 결과 저장: {filename}")

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
                           ("last_scan_run_id", "INTEGER DEFAULT 0")]:
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
                region = "청주"
                for reg in ["오창", "가경", "복대", "율량", "세종", "대전"]:
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
                        scan_run_id, last_scan_run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        category=excluded.category,
                        search_volume=excluded.search_volume,
                        region=excluded.region
                ''', (
                    r.keyword, 0, "Low" if r.difficulty < 50 else "High",
                    r.priority_score, tag, now,
                    r.search_volume, region, r.category,
                    r.difficulty, r.opportunity, r.priority_score, r.grade, r.source,
                    r.trend_slope, r.trend_status, r.search_intent,
                    r.document_count, r.kei, r.kei_grade,
                    scan_run_id, scan_run_id
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
    args = parser.parse_args()

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

    try:
        results = legion.run(target_sa=args.target)

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
                {"keyword": r.keyword, "grade": r.grade, "kei": r.kei}
                for r in sorted(results, key=lambda x: x.priority_score, reverse=True)[:10]
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
                notes="keyword_insights.scan_run_id=first_seen, last_scan_run_id=last_seen"
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

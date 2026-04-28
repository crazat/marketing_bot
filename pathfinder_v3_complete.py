#!/usr/bin/env python3
"""
Pathfinder V3 완전판 (MF-KEI 5.0)
- Phase 1: Naver + Google 자동완성 기반 키워드 수집
- Phase 2: SERP 분석 (난이도/기회 점수)
- Phase 3: 경쟁사 역분석 (갭 키워드)
- Phase 4: 통합 우선순위 계산 (MF-KEI 5.0)
- Phase 5: 트렌드 분석
- Phase 6: 블로그 마이닝 + AI 시맨틱 확장
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import atexit

# [고도화 A-1] Sentry 에러 모니터링
try:
    from scrapers.sentry_init import init_sentry
    init_sentry("pathfinder_v3")
except Exception:
    pass
import requests
import re
import time
import json
import math
from bs4 import BeautifulSoup
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Set, Tuple, Optional
from collections import Counter
from pathlib import Path

# 서비스 모듈 import
try:
    from core.event_bus import publish_event, EventType
    HAS_EVENT_BUS = True
except ImportError:
    HAS_EVENT_BUS = False

try:
    from services.keyword_filter import KeywordQualityFilter
    HAS_FILTER = True
except ImportError:
    HAS_FILTER = False
    print("⚠️ KeywordQualityFilter 로드 실패 - 필터링 비활성화")

try:
    from services.blog_miner import BlogTitleMiner
    HAS_BLOG_MINER = True
except ImportError:
    HAS_BLOG_MINER = False
    print("⚠️ BlogTitleMiner 로드 실패 - 블로그 마이닝 비활성화")

try:
    from services.ai_keyword_expander import AIKeywordExpander
    HAS_AI_EXPANDER = True
except ImportError:
    HAS_AI_EXPANDER = False
    print("⚠️ AIKeywordExpander 로드 실패 - AI 확장 비활성화")


# ============================================================
# TeeWriter: stdout + 파일 동시 출력 (실시간 로그 스트리밍용)
# ============================================================

class TeeWriter:
    """stdout과 파일에 동시 출력하는 Writer 클래스"""

    def __init__(self, log_file_path: str, status_file_path: str):
        self.terminal = sys.stdout
        self.log_file_path = log_file_path
        self.status_file_path = status_file_path

        # 로그 디렉토리 생성
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

        # 로그 파일 열기 (덮어쓰기)
        self.log_file = open(log_file_path, 'w', encoding='utf-8', buffering=1)

        # 상태 파일 업데이트: running
        self._update_status('running', 'Pathfinder V3 시작됨')

        # 종료 시 cleanup 등록
        atexit.register(self._cleanup)

    def write(self, message):
        self.terminal.write(message)
        self.terminal.flush()
        try:
            self.log_file.write(message)
            self.log_file.flush()
        except (IOError, OSError):
            pass  # 로그 파일 쓰기 실패는 무시

    def flush(self):
        self.terminal.flush()
        try:
            self.log_file.flush()
        except (IOError, OSError):
            pass  # 로그 파일 플러시 실패는 무시

    def _update_status(self, status: str, message: str = ''):
        """상태 파일 업데이트"""
        import json
        try:
            status_data = {
                'status': status,
                'message': message,
                'updated_at': datetime.now().isoformat(),
                'mode': 'total_war'
            }
            with open(self.status_file_path, 'w', encoding='utf-8') as f:
                json.dump(status_data, f, ensure_ascii=False, indent=2)
        except (IOError, OSError, TypeError):
            pass  # 상태 파일 업데이트 실패는 무시

    def _cleanup(self):
        """종료 시 정리"""
        try:
            self._update_status('completed', 'Pathfinder V3 완료')
            self.log_file.close()
        except (IOError, OSError, AttributeError):
            pass  # 정리 중 오류는 무시


def setup_live_logging():
    """실시간 로그 스트리밍 설정"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(base_dir, 'logs')

    log_file = os.path.join(log_dir, 'pathfinder_live.log')
    status_file = os.path.join(log_dir, 'pathfinder_status.json')

    tee = TeeWriter(log_file, status_file)
    sys.stdout = tee
    return tee


# ============================================================
# 데이터 클래스
# ============================================================

@dataclass
class KeywordResult:
    """최종 키워드 결과"""
    keyword: str
    search_volume: int
    blog_count: int
    difficulty: int
    opportunity: int
    grade: str
    category: str
    priority_score: float
    is_gap_keyword: bool = False
    source: str = ""  # "autocomplete", "related", "competitor", "paa"
    trend_slope: float = 0.0
    trend_status: str = "unknown"
    # [R7] 검색 의도 분류 (Cross-User 행동 모델 대응)
    search_intent: str = "commercial"  # red_flag, validation, comparison, transactional, commercial, informational, navigational


def _classify_intent(keyword: str) -> str:
    """[R7] 검증/비교/부정 의도 키워드 분류. Cross-User 행동 대응.

    legion 파일의 SearchIntentClassifier와 동일 로직 (의존성 회피 위해 인라인).
    """
    kw = (keyword or '').lower()
    patterns = [
        ('red_flag',     ['부작용', '위험', '단점', '안좋', '문제', '실패', '후회', '사기', '환불', '논란', '의심']),
        ('validation',   ['진짜', '솔직', '찐', '정말', '실제로', '리얼', '진정']),
        ('comparison',   ['vs', '보다', '차이', '비교', '뭐가나', '어디가더', '뭐가더']),
        ('transactional',['가격', '비용', '할인', '이벤트', '예약', '상담', '무료', '체험', '프로모션', '쿠폰']),
        ('commercial',   ['추천', '순위', '랭킹', '베스트', '인기', '후기', '리뷰', '평가', '잘하는', '유명한', '좋은', '전문', '1위']),
        ('informational',['방법', '효과', '원인', '증상', '치료', '기간', '주의', '종류', '장단점', '뜻', '의미']),
        ('navigational', ['위치', '주소', '전화', '오시는길', '영업시간', '근처', '가까운']),
    ]
    for intent, words in patterns:  # dict 순서 = 우선순위
        if any(w in kw for w in words):
            return intent
    return 'commercial'


# ============================================================
# Google 자동완성 (멀티소스 수집)
# ============================================================

class GoogleAutocomplete:
    """Google 자동완성 API"""

    def __init__(self, delay: float = 0.3):
        self.delay = delay
        self._last_call = 0
        self.base_url = "https://suggestqueries.google.com/complete/search"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def get_suggestions(self, keyword: str, max_retries: int = 2) -> List[str]:
        """Google 자동완성 제안 가져오기"""
        self._rate_limit()

        params = {
            "client": "firefox",
            "q": keyword,
            "hl": "ko"
        }

        for attempt in range(max_retries):
            try:
                response = requests.get(
                    self.base_url,
                    params=params,
                    headers=self.headers,
                    timeout=5
                )

                if response.status_code == 200:
                    data = response.json()
                    if len(data) >= 2 and isinstance(data[1], list):
                        return [s for s in data[1] if isinstance(s, str)]
                return []
            except Exception:
                if attempt < max_retries - 1:
                    time.sleep(0.5)
                continue

        return []


# ============================================================
# 시즌 키워드 DB (ULTRA 이식)
# ============================================================

class SeasonalKeywordDB:
    """월별 시즌 키워드 데이터베이스"""

    SEASONAL_KEYWORDS = {
        "다이어트": {
            1: ["새해 다이어트", "신년 다이어트"],
            2: ["졸업 다이어트", "취업준비 다이어트"],
            3: ["봄 다이어트"],
            5: ["여름 준비 다이어트", "웨딩 다이어트"],
            6: ["여름 다이어트", "휴가전 다이어트"],
            7: ["비키니 다이어트"],
            9: ["추석 후 다이어트"],
            12: ["연말 다이어트"]
        },
        "안면비대칭": {
            2: ["졸업사진 비대칭", "면접 비대칭"],
            3: ["졸업 안면비대칭"],
            5: ["웨딩 안면비대칭"],
            11: ["수능 후 교정"]
        },
        "여드름": {
            1: ["겨울 건조 여드름"],
            2: ["환절기 여드름"],
            6: ["여름 여드름", "땀 여드름"],
            9: ["환절기 여드름"]
        },
        "교통사고": {
            1: ["빙판길 교통사고", "설 귀성길 사고"],
            7: ["휴가철 교통사고"],
            9: ["추석 귀성길 교통사고"],
            12: ["연말 교통사고", "눈길 교통사고"]
        },
        "탈모": {
            3: ["환절기 탈모"],
            5: ["취업 탈모"],
            9: ["가을 탈모"]
        }
    }

    @classmethod
    def get_current_seasonal_keywords(cls) -> List[str]:
        """현재 월의 시즌 키워드 반환"""
        current_month = datetime.now().month
        keywords = []

        for category, months in cls.SEASONAL_KEYWORDS.items():
            # 현재 월 ± 1개월 포함
            for month in [current_month - 1, current_month, current_month + 1]:
                adjusted_month = month if month > 0 else month + 12
                adjusted_month = adjusted_month if adjusted_month <= 12 else adjusted_month - 12

                if adjusted_month in months:
                    for kw in months[adjusted_month]:
                        keywords.append(f"청주 {kw}")

        return keywords


# ============================================================
# Phase 1: 키워드 수집 (Naver 자동완성)
# ============================================================

class KeywordCollector:
    """Phase 1: Naver 자동완성 기반 키워드 수집"""

    def __init__(self, delay: float = 0.3):
        self.delay = delay
        self.base_url = "https://ac.search.naver.com/nx/ac"
        self._last_call = 0

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.naver.com/"
        }

        # 청주 지역명
        self.cheongju_regions = [
            "청주", "상당", "서원", "흥덕", "청원",
            "복대", "가경", "율량", "오창", "오송",
            "분평", "봉명", "산남", "용암", "금천"
        ]

        # 한의원 관련 키워드 (규림한의원 진료 분야 포함)
        self.hanbang_keywords = [
            # 기본 한의원
            "한의원", "한방", "한약", "침", "추나", "부항", "뜸",

            # 안면비대칭/체형교정 (핵심 특화)
            "안면비대칭", "얼굴비대칭", "턱비대칭", "광대비대칭", "비대칭",
            "체형교정", "골반교정", "척추교정", "자세교정", "휜다리",

            # 교통사고/입원
            "교통사고", "자동차사고", "후유증", "입원",

            # 피부/여드름 (특화)
            "여드름", "여드름흉터", "여드름자국", "새살침", "흉터",
            "피부", "아토피", "습진", "두드러기", "건선", "피부질환",

            # 다이어트
            "다이어트", "비만", "살빼", "체중", "뱃살", "허벅지", "체중감량",

            # 통증
            "통증", "디스크", "허리", "목", "어깨", "무릎", "관절", "오십견",

            # 탈모
            "탈모", "두피", "원형탈모",

            # 비염
            "비염", "알레르기", "축농증", "코막힘",

            # 여성건강
            "갱년기", "폐경", "생리", "산후", "불임", "여성질환", "산후조리",

            # 기타
            "불면", "수면", "스트레스", "우울",
            "소화", "위장", "역류", "변비", "소화불량",
            "두통", "어지럼", "이명"
        ]

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def get_suggestions(self, keyword: str) -> List[str]:
        """자동완성 제안 가져오기"""
        self._rate_limit()

        params = {
            "q": keyword,
            "q_enc": "UTF-8",
            "st": 100,
            "frm": "nv",
            "r_format": "json",
            "r_enc": "UTF-8",
            "r_unicode": 0,
            "t_koreng": 1,
            "ans": 2,
            "run": 2,
            "rev": 4,
            "con": 1
        }

        try:
            response = requests.get(self.base_url, params=params, headers=self.headers, timeout=10)
            data = response.json()

            if "items" in data and data["items"] and len(data["items"]) > 0:
                return [item[0] if isinstance(item, list) else item
                        for item in data["items"][0]]
            return []
        except (requests.RequestException, json.JSONDecodeError, KeyError, IndexError, TypeError):
            return []  # 네트워크 오류 또는 파싱 오류

    def is_hanbang_related(self, keyword: str) -> bool:
        """한의원 관련 키워드인지 확인"""
        kw = keyword.lower()
        return any(h in kw for h in self.hanbang_keywords)

    def is_cheongju_related(self, keyword: str) -> bool:
        """청주 지역 키워드인지 확인"""
        return any(r in keyword for r in self.cheongju_regions)

    def collect(self, seeds: List[str], max_keywords: int = 500) -> Set[str]:
        """
        시드에서 키워드 수집

        Args:
            seeds: 시드 키워드 리스트
            max_keywords: 최대 수집 키워드 수

        Returns:
            수집된 키워드 세트
        """
        all_keywords = set()

        # 1차: 시드 확장
        for seed in seeds:
            suggestions = self.get_suggestions(seed)
            for s in suggestions:
                if self.is_cheongju_related(s) and self.is_hanbang_related(s):
                    all_keywords.add(s)

                if len(all_keywords) >= max_keywords:
                    break

            if len(all_keywords) >= max_keywords:
                break

        # 2차: 수집된 키워드 재확장 (개선: 50→300개로 확대)
        first_round = list(all_keywords)[:300]  # 상위 300개 재확장
        for kw in first_round:
            suggestions = self.get_suggestions(kw)
            for s in suggestions:
                if self.is_cheongju_related(s) and self.is_hanbang_related(s):
                    all_keywords.add(s)

                if len(all_keywords) >= max_keywords:
                    break

            if len(all_keywords) >= max_keywords:
                break

        return all_keywords


# ============================================================
# Phase 2: SERP 분석
# ============================================================

class SERPAnalyzer:
    """Phase 2: SERP 분석기"""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self._last_call = 0

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def _parse_date(self, date_str: str) -> int:
        """날짜에서 경과일 계산"""
        now = datetime.now()

        match = re.search(r"(\d+)일 전", date_str)
        if match:
            return int(match.group(1))

        if "시간 전" in date_str or "분 전" in date_str:
            return 0

        match = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", date_str)
        if match:
            try:
                pub_date = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                days = (now - pub_date).days
                return max(0, days) if days >= 0 else 30
            except (ValueError, TypeError):
                pass  # 날짜 파싱 실패

        return 90

    def analyze(self, keyword: str) -> Tuple[int, int, str]:
        """
        키워드의 SERP 분석

        Returns:
            (난이도, 기회점수, 등급)
        """
        self._rate_limit()

        url = "https://search.naver.com/search.naver"
        params = {"where": "blog", "query": keyword}

        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # 블로그 포스트 파싱
            post_pattern = re.compile(r'blog\.naver\.com/(\w+)/(\d+)')
            blogs = []
            seen_urls = set()

            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                match = post_pattern.search(href)

                if not match or href in seen_urls:
                    continue

                title = link.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                seen_urls.add(href)

                # 날짜 찾기
                days_since = 90
                parent = link.parent
                for _ in range(10):
                    if parent is None:
                        break
                    text = parent.get_text()

                    date_match = re.search(r'(\d{4}\.\d{1,2}\.\d{1,2})', text)
                    if date_match:
                        days_since = self._parse_date(date_match.group(1))
                        break

                    days_match = re.search(r'(\d+)일 전', text)
                    if days_match:
                        days_since = int(days_match.group(1))
                        break

                    parent = parent.parent

                # 공식 블로그 체크
                combined = (match.group(1) + " " + title).lower()
                is_official = any(kw in combined for kw in ["한의원", "병원", "의원", "클리닉"])

                blogs.append({
                    'days': days_since,
                    'official': is_official
                })

                if len(blogs) >= 10:
                    break

            # 난이도 계산
            difficulty = 0
            for blog in blogs[:5]:
                if blog['official']:
                    difficulty += 15
                if blog['days'] <= 30:
                    difficulty += 10
                elif blog['days'] <= 90:
                    difficulty += 5

            # 기회 점수 계산
            opportunity = 0
            for i, blog in enumerate(blogs[:5]):
                weight = (5 - i)
                if blog['days'] > 180:
                    opportunity += 10 * weight
                elif blog['days'] > 90:
                    opportunity += 5 * weight
                if not blog['official']:
                    opportunity += 8 * weight

            opportunity = min(opportunity, 100)

            # 등급 결정
            if difficulty <= 30 and opportunity >= 60:
                grade = "S"
            elif difficulty <= 50 and opportunity >= 40:
                grade = "A"
            elif difficulty <= 70:
                grade = "B"
            else:
                grade = "C"

            return difficulty, opportunity, grade

        except Exception as e:
            return 50, 50, "B"

    def analyze_batch(self, keywords: List[str], max_workers: int = 5, show_progress: bool = True) -> Dict[str, Tuple[int, int, str]]:
        """
        [성능 최적화] 병렬 SERP 분석

        Args:
            keywords: 분석할 키워드 목록
            max_workers: 동시 작업자 수 (기본 5)
            show_progress: 진행률 표시 여부

        Returns:
            {keyword: (difficulty, opportunity, grade)} 딕셔너리
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = {}
        total = len(keywords)

        def analyze_single(kw: str) -> Tuple[str, Tuple[int, int, str]]:
            """단일 키워드 분석 (rate limit 없이)"""
            try:
                url = "https://search.naver.com/search.naver"
                params = {"where": "blog", "query": kw}
                response = requests.get(url, params=params, headers=self.headers, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')

                # 간소화된 파싱 로직
                post_pattern = re.compile(r'blog\.naver\.com/(\w+)/(\d+)')
                blog_count = len(set(post_pattern.findall(str(soup))))

                # 난이도/기회 계산 (간소화)
                difficulty = min(100, max(0, blog_count * 5))
                opportunity = max(0, 100 - difficulty)

                if difficulty <= 20 and opportunity >= 70:
                    grade = "S"
                elif difficulty <= 50 and opportunity >= 40:
                    grade = "A"
                elif difficulty <= 70:
                    grade = "B"
                else:
                    grade = "C"

                return kw, (difficulty, opportunity, grade)
            except Exception:
                return kw, (50, 50, "B")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(analyze_single, kw): kw for kw in keywords}
            done_count = 0

            for future in as_completed(futures):
                kw, result = future.result()
                results[kw] = result
                done_count += 1

                if show_progress and done_count % 10 == 0:
                    print(f"   SERP 분석: {done_count}/{total}...")

        return results


# ============================================================
# Phase 3: 경쟁사 분석
# ============================================================

class CompetitorAnalyzer:
    """Phase 3: 경쟁사 역분석기"""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self._last_call = 0

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }

        self.region_keywords = [
            "청주", "상당", "서원", "흥덕", "청원",
            "복대", "가경", "율량", "오창", "오송"
        ]

        self.medical_keywords = [
            "한의원", "한방", "한약", "다이어트", "비만",
            "여드름", "피부", "교통사고", "통증", "탈모", "비염"
        ]

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def _extract_keywords(self, title: str) -> List[str]:
        """제목에서 키워드 추출"""
        keywords = []

        regions = [r for r in self.region_keywords if r in title]
        medicals = [m for m in self.medical_keywords if m in title]

        for region in regions:
            for medical in medicals:
                keywords.append(f"{region} {medical}")

        return keywords

    def get_competitor_keywords(self, blog_url: str, max_posts: int = 30) -> Dict[str, int]:
        """경쟁사 블로그에서 키워드 추출"""
        match = re.search(r'blog\.naver\.com/(\w+)', blog_url)
        if not match:
            return {}

        blog_id = match.group(1)
        keyword_counter: Counter = Counter()

        self._rate_limit()

        url = f"https://blog.naver.com/PostList.naver"
        params = {"blogId": blog_id, "currentPage": 1, "countPerPage": 30}

        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            post_pattern = re.compile(rf'{blog_id}/\d+')

            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                if post_pattern.search(href):
                    title = link.get_text(strip=True)
                    if title and len(title) >= 5:
                        keywords = self._extract_keywords(title)
                        keyword_counter.update(keywords)

        except (requests.RequestException, AttributeError, TypeError) as e:
            pass  # 네트워크 오류 또는 파싱 오류 무시

        return dict(keyword_counter.most_common(20))

    def find_gap_keywords(self, competitor_keywords: Dict[str, int], our_keywords: Set[str]) -> List[str]:
        """갭 키워드 찾기"""
        gap = []
        for kw in competitor_keywords:
            if kw.lower() not in {k.lower() for k in our_keywords}:
                gap.append(kw)
        return gap


# ============================================================
# Pathfinder V3 통합
# ============================================================

class PathfinderV3:
    """Pathfinder V3 통합 클래스 (MF-KEI 5.0)"""

    def __init__(self):
        self.collector = KeywordCollector(delay=0.3)
        self.google_autocomplete = GoogleAutocomplete(delay=0.3)
        self.serp_analyzer = SERPAnalyzer(delay=1.0)
        self.competitor_analyzer = CompetitorAnalyzer(delay=1.0)

        # 품질 필터
        if HAS_FILTER:
            self.quality_filter = KeywordQualityFilter()
            print("✅ 품질 필터 로드 완료")
        else:
            self.quality_filter = None

        # 블로그 마이너
        if HAS_BLOG_MINER:
            self.blog_miner = BlogTitleMiner(delay=1.0)
            print("✅ 블로그 마이너 로드 완료")
        else:
            self.blog_miner = None

        # AI 확장기
        if HAS_AI_EXPANDER:
            self.ai_expander = AIKeywordExpander()
            if self.ai_expander.is_available():
                print("✅ AI 키워드 확장기 로드 완료")
            else:
                self.ai_expander = None
        else:
            self.ai_expander = None

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

        # 카테고리 패턴 (우선순위 순서대로 체크됨 - 규림한의원 진료 분야)
        self.category_patterns = {
            # 핵심 특화 분야
            "안면비대칭": ["안면비대칭", "얼굴비대칭", "턱비대칭", "광대비대칭", "비대칭교정", "안비"],
            "체형교정": ["체형교정", "골반교정", "척추교정", "자세교정", "휜다리", "체형"],
            "교통사고": ["교통사고", "자동차사고", "후유증", "사고치료", "입원치료", "사고입원"],
            "피부/여드름": ["여드름", "여드름흉터", "여드름자국", "새살침", "피부", "아토피", "습진", "두드러기", "건선", "피부질환"],

            # 주요 진료 분야
            "다이어트": ["다이어트", "비만", "살빼", "체중", "뱃살", "허벅지살", "체중감량"],
            "통증": ["통증", "디스크", "허리", "어깨", "무릎", "목디스크", "허리디스크", "관절", "오십견"],
            "탈모": ["탈모", "두피", "원형탈모", "머리카락", "탈모치료"],
            "비염": ["비염", "알레르기", "축농증", "코막힘", "비강"],
            "여성건강": ["갱년기", "폐경", "산후", "생리", "불임", "여성질환", "산후조리"],

            # 기타 분야
            "수면/스트레스": ["불면", "수면", "스트레스", "우울", "불안", "자율신경"],
            "소화기": ["소화", "위장", "역류", "변비", "설사", "위염", "소화불량"],
            "두통/어지럼": ["두통", "어지럼", "이명", "편두통"],
            "한의원일반": ["한의원", "한방", "한약", "침", "추나", "부항", "뜸"],
        }

    def _detect_category(self, keyword: str) -> str:
        kw = keyword.lower()
        for cat, patterns in self.category_patterns.items():
            if any(p in kw for p in patterns):
                return cat
        if any(h in kw for h in ('한의원', '한약', '한방', '한방병원')):
            return '한의원일반'
        return "기타"

    def _calculate_seasonality_score(self, keyword: str) -> float:
        """
        현재 월 기준 시즌성 점수 계산 (0.0 ~ 1.0)

        Returns:
            시즌성 점수 (0.0: 비시즌, 1.0: 정시즌)
        """
        current_month = datetime.now().month

        # 시즌 패턴 정의: {키워드 패턴: [피크 월들]}
        seasonal_patterns = {
            "다이어트": [1, 3, 5, 6],  # 새해, 봄, 여름 준비
            "비만": [1, 3, 5, 6],
            "여드름": [5, 6, 7, 8],  # 여름
            "탈모": [9, 10, 11],  # 가을
            "비염": [3, 4, 9, 10],  # 환절기
            "갱년기": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],  # 연중
            "교통사고": [1, 7, 8, 9, 12],  # 겨울, 휴가철, 명절
            "안면비대칭": [2, 3, 5, 11],  # 졸업, 취업, 결혼, 수능후
            "체형교정": [1, 3, 5],  # 새해, 봄, 여름 준비
        }

        kw_lower = keyword.lower()

        for pattern, peak_months in seasonal_patterns.items():
            if pattern in kw_lower:
                if current_month in peak_months:
                    return 1.0  # 정시즌
                # 인접 월이면 부분 점수
                for pm in peak_months:
                    if abs(current_month - pm) == 1 or abs(current_month - pm) == 11:
                        return 0.5
                return 0.2  # 비시즌

        return 0.5  # 시즌성 없음 (중립)

    def _calculate_business_relevance(self, keyword: str) -> float:
        """
        비즈니스 관련성 점수 계산 (0.0 ~ 1.0)
        규림한의원 핵심 서비스 기준

        Returns:
            관련성 점수 (0.0: 무관, 1.0: 핵심)
        """
        kw_lower = keyword.lower()

        # Tier 1: 핵심 특화 (1.0)
        tier1 = ["안면비대칭", "얼굴비대칭", "체형교정", "골반교정", "새살침", "여드름흉터"]
        if any(t in kw_lower for t in tier1):
            return 1.0

        # Tier 2: 주력 서비스 (0.8)
        tier2 = ["교통사고", "입원", "다이어트", "한약", "여드름", "피부"]
        if any(t in kw_lower for t in tier2):
            return 0.8

        # Tier 3: 일반 진료 (0.6)
        tier3 = ["통증", "디스크", "탈모", "비염", "갱년기"]
        if any(t in kw_lower for t in tier3):
            return 0.6

        # Tier 4: 한의원 일반 (0.4)
        tier4 = ["한의원", "한방", "침", "추나", "부항"]
        if any(t in kw_lower for t in tier4):
            return 0.4

        return 0.2  # 기타

    def _calculate_priority(self, volume: int, difficulty: int, opportunity: int,
                            keyword: str, is_gap: bool = False,
                            kei: float = 0.0, trend_slope: float = 0.0) -> float:
        """
        MF-KEI 5.0 우선순위 점수 계산

        공식: KEI(30%) + 기회(25%) + 난이도(20%) + 트렌드(15%) + 계절성/관련성(10%)

        Args:
            volume: 월간 검색량
            difficulty: SERP 난이도 (0-100)
            opportunity: 진입 기회 (0-100)
            keyword: 키워드
            is_gap: 갭 키워드 여부
            kei: KEI 점수 (0-100)
            trend_slope: 트렌드 기울기 (-1.0 ~ 1.0)

        Returns:
            우선순위 점수 (0-100)
        """
        # 1. KEI 점수 (검색량/경쟁도 비율) - 30%
        if kei > 0:
            kei_score = min(100, kei)
        elif volume > 0:
            # KEI가 없으면 검색량 기반 추정
            kei_score = min(100, (math.log10(max(1, volume)) / 4) * 100)
        else:
            kei_score = 0

        # 2. 기회 점수 - 25%
        opportunity_score = min(100, opportunity)

        # 3. 난이도 점수 (역전) - 20%
        difficulty_score = max(0, 100 - difficulty)

        # 4. 트렌드 점수 - 15%
        # trend_slope: -1.0(급락) ~ 0(안정) ~ 1.0(급상승)
        trend_score = 50 + (trend_slope * 50)  # 0~100 범위로 변환
        trend_score = max(0, min(100, trend_score))

        # 5. 계절성 + 비즈니스 관련성 - 10%
        seasonality = self._calculate_seasonality_score(keyword)
        business_relevance = self._calculate_business_relevance(keyword)
        combined_score = (seasonality * 0.4 + business_relevance * 0.6) * 100

        # MF-KEI 5.0 가중 평균
        base_score = (
            kei_score * 0.30 +
            opportunity_score * 0.25 +
            difficulty_score * 0.20 +
            trend_score * 0.15 +
            combined_score * 0.10
        )

        # 의도 가중치 (검색량 50 이상만 적용)
        intent_weight = 1.0
        if volume >= 50:
            if any(w in keyword for w in ["가격", "비용"]):
                intent_weight = 1.3
            elif any(w in keyword for w in ["후기", "추천"]):
                intent_weight = 1.2
            elif any(w in keyword for w in ["잘하는", "좋은"]):
                intent_weight = 1.15

        # 갭 키워드 보너스
        gap_bonus = 1.2 if is_gap else 1.0

        # 최종 점수 (최대 ~150 정도)
        return base_score * intent_weight * gap_bonus

    def run(self, max_keywords: int = 2000, competitors_config: str = "config/competitors.json") -> List[KeywordResult]:
        """
        V3 전체 실행 (MF-KEI 5.0)

        Args:
            max_keywords: 최대 분석 키워드 수
            competitors_config: 경쟁사 설정 파일 경로

        Returns:
            KeywordResult 리스트 (우선순위 순)
        """
        print("=" * 70)
        print("Pathfinder V3 Complete (MF-KEI 5.0)")
        print("=" * 70)

        # =====================================
        # Phase 1: 멀티소스 키워드 수집 (Naver + Google)
        # =====================================
        print("\n[Phase 1] 멀티소스 키워드 수집...")

        # 규림한의원 실제 진료 분야 기반 시드
        seeds = [
            # 기본 한의원
            "청주 한의원", "청주 한의원 추천", "청주 한의원 잘하는곳",
            "오창 한의원", "가경동 한의원", "복대동 한의원",

            # ===== 안면비대칭/체형교정 =====
            "청주 안면비대칭", "청주 안면비대칭 교정", "청주 얼굴비대칭",
            "청주 턱비대칭", "청주 광대비대칭", "청주 안면비대칭 한의원",
            "청주 체형교정", "청주 골반교정", "청주 척추교정",
            "청주 자세교정", "청주 휜다리교정", "청주 체형교정 한의원",

            # ===== 교통사고/입원 =====
            "청주 교통사고", "청주 교통사고 한의원", "청주 교통사고 입원",
            "청주 자동차사고", "청주 교통사고 치료", "청주 교통사고 후유증",
            "청주 교통사고 입원치료", "청주 한의원 입원",

            # ===== 피부/여드름/흉터 =====
            "청주 여드름", "청주 여드름 한의원", "청주 여드름 치료",
            "청주 여드름흉터", "청주 여드름자국", "청주 새살침",
            "청주 피부 한의원", "청주 피부질환", "청주 아토피",
            "청주 습진", "청주 두드러기", "청주 건선",

            # ===== 다이어트/비만 =====
            "청주 다이어트", "청주 다이어트 한의원", "청주 다이어트 한약",
            "청주 비만 클리닉", "청주 살빼는 한의원", "청주 체중감량",
            "청주 뱃살", "청주 허벅지살", "청주 한약 다이어트",

            # ===== 통증/디스크 =====
            "청주 통증", "청주 허리 한의원", "청주 디스크 한의원",
            "청주 어깨통증", "청주 무릎통증", "청주 목디스크",
            "청주 허리디스크", "청주 오십견", "청주 관절통증",

            # ===== 탈모 =====
            "청주 탈모", "청주 탈모 한의원", "청주 탈모 치료",
            "청주 원형탈모", "청주 두피관리",

            # ===== 비염/알레르기 =====
            "청주 비염", "청주 비염 한의원", "청주 알레르기",
            "청주 축농증", "청주 코막힘",

            # ===== 여성/갱년기 =====
            "청주 갱년기", "청주 갱년기 한의원", "청주 생리통",
            "청주 산후조리", "청주 불임", "청주 여성질환",

            # ===== 기타 =====
            "청주 불면증", "청주 소화불량", "청주 두통",
            "청주 어지럼증", "청주 이명", "청주 자율신경",

            # ===== 인근 지역 확장 (보고서 분석 반영) =====
            # 충주
            "충주 한의원", "충주 교통사고", "충주 다이어트",
            "충주 여드름", "충주 탈모", "충주 피부관리",
            "충주 야간진료", "충주 추나요법", "충주 리프팅",

            # 제천
            "제천 한의원", "제천 다이어트", "제천 피부관리",
            "제천 탈모", "제천 턱관절", "제천 한방병원",

            # 진천
            "진천 한의원", "진천 다이어트", "진천 피부관리",
            "진천 한방병원",

            # 증평
            "증평 한의원", "증평 여드름흉터", "증평 피부관리",
            "증평 한방병원",

            # ===== 야간진료 (보고서 분석 반영) =====
            "청주 야간진료", "청주 한의원 야간", "청주 야간 한의원",
            "율량동 야간진료", "가경동 야간진료", "오창 야간진료",
        ]

        # ========== 시즌 키워드 추가 (ULTRA 이식) ==========
        seasonal_seeds = SeasonalKeywordDB.get_current_seasonal_keywords()
        if seasonal_seeds:
            print(f"📅 시즌 키워드 추가: {len(seasonal_seeds)}개 (현재: {datetime.now().month}월)")
            seeds.extend(seasonal_seeds)

        # 1-1. Naver 자동완성
        print("   [1-1] Naver 자동완성...")
        naver_keywords = self.collector.collect(seeds, max_keywords=max_keywords * 2)
        print(f"      Naver: {len(naver_keywords)}개")

        # 1-2. Google 자동완성
        print("   [1-2] Google 자동완성...")
        google_keywords = set()
        for seed in seeds[:30]:  # 상위 30개 시드만
            suggestions = self.google_autocomplete.get_suggestions(seed)
            for s in suggestions:
                if self.collector.is_cheongju_related(s) and self.collector.is_hanbang_related(s):
                    google_keywords.add(s)
        print(f"      Google: {len(google_keywords)}개")

        # 합집합
        collected_keywords = naver_keywords | google_keywords
        print(f"   📊 멀티소스 수집 완료: {len(collected_keywords)}개 (중복 제거)")

        # =====================================
        # Phase 1.5: 블로그 마이닝
        # =====================================
        if self.blog_miner:
            print("\n[Phase 1.5] 블로그 마이닝...")
            mining_queries = [
                "청주 다이어트 한의원",
                "청주 교통사고 한의원",
                "청주 안면비대칭",
                "청주 여드름 한의원",
                "청주 탈모 한의원"
            ]
            mined_keywords = self.blog_miner.mine_batch(mining_queries, top_n=10)
            before_count = len(collected_keywords)
            collected_keywords.update(mined_keywords)
            print(f"   블로그 마이닝: +{len(collected_keywords) - before_count}개 신규")

        # =====================================
        # Phase 2: 경쟁사 분석
        # =====================================
        print("\n[Phase 2] 경쟁사 분석...")

        gap_keywords: Set[str] = set()
        competitors_path = Path(competitors_config)

        if competitors_path.exists():
            with open(competitors_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            for comp in config.get("competitors", []):
                blog_url = comp.get("blog_url", "")
                if blog_url and "example" not in blog_url:
                    comp_keywords = self.competitor_analyzer.get_competitor_keywords(blog_url)
                    gaps = self.competitor_analyzer.find_gap_keywords(comp_keywords, collected_keywords)
                    gap_keywords.update(gaps)
                    print(f"   {comp.get('name', 'Unknown')}: {len(gaps)}개 갭 키워드 발견")

        # 갭 키워드 추가
        all_keywords = collected_keywords | gap_keywords
        print(f"   갭 키워드 포함 총: {len(all_keywords)}개")

        # =====================================
        # Phase 2.5: AI 시맨틱 확장
        # =====================================
        if self.ai_expander and self.ai_expander.is_available():
            print("\n[Phase 2.5] AI 시맨틱 확장...")
            # 카테고리별 시드 추출
            category_seeds = {
                "다이어트": [kw for kw in list(all_keywords)[:100] if "다이어트" in kw][:5],
                "안면비대칭": [kw for kw in list(all_keywords)[:100] if "비대칭" in kw][:5],
                "교통사고": [kw for kw in list(all_keywords)[:100] if "교통사고" in kw][:5],
            }

            ai_expanded = self.ai_expander.batch_expand(category_seeds, max_per_category=10)
            ai_count = 0
            for cat, keywords_list in ai_expanded.items():
                for kw in keywords_list:
                    if self.collector.is_cheongju_related(kw) or "청주" in kw:
                        all_keywords.add(kw)
                        ai_count += 1

            print(f"   🤖 AI 확장: +{ai_count}개 신규")

        # =====================================
        # Phase 2.6: 품질 필터링
        # =====================================
        if self.quality_filter:
            print("\n[Phase 2.6] 품질 필터링...")
            before_filter = len(all_keywords)
            passed, rejected = self.quality_filter.filter_batch(list(all_keywords))
            all_keywords = set(passed)
            print(f"   필터링: {before_filter} → {len(all_keywords)}개 (제외: {len(rejected)}개)")

            # 제외 사유 통계
            stats = self.quality_filter.get_stats(passed, rejected)
            if stats['rejection_reasons']:
                for reason, count in stats['rejection_reasons'].items():
                    print(f"      - {reason}: {count}개")

        # 띄어쓰기 변형 추가 (예: "가경동 한의원" → "가경동한의원")
        expanded_keywords = set(all_keywords)
        for kw in list(all_keywords):
            kw_no_space = kw.replace(" ", "")
            if kw_no_space != kw and len(kw_no_space) > 2:
                expanded_keywords.add(kw_no_space)

        print(f"   띄어쓰기 변형 포함: {len(expanded_keywords)}개")

        # 키워드 수 제한
        keywords = list(expanded_keywords)[:max_keywords]
        print(f"   분석 대상: {len(keywords)}개")

        # =====================================
        # Phase 3: 검색량 조회 (Naver Ad API)
        # =====================================
        print(f"\n[Phase 3] 검색량 조회...")

        volume_map = {}
        if self.has_ad_api and self.ad_manager:
            try:
                result = self.ad_manager.get_keyword_volumes(keywords)
                # None 방어 처리
                volume_map = result if result is not None else {}
                if volume_map:
                    print(f"   📊 검색량 조회 완료: {len(volume_map)}개")
            except Exception as e:
                print(f"   ⚠️ 검색량 조회 실패: {e}")
                volume_map = {}  # 예외 발생 시 빈 딕셔너리로 초기화

        # =====================================
        # Phase 4: SERP 분석 (병렬 처리)
        # =====================================
        print(f"\n[Phase 4] SERP 분석 (병렬 처리, {len(keywords)}개)...")

        # [성능 최적화] 병렬 SERP 분석 (기존 순차 처리 대비 3-5배 속도 향상)
        serp_results = self.serp_analyzer.analyze_batch(keywords, max_workers=5, show_progress=True)

        results = []
        for kw in keywords:
            # SERP 결과 가져오기
            difficulty, opportunity, grade = serp_results.get(kw, (50, 50, "B"))
            category = self._detect_category(kw)
            is_gap = kw in gap_keywords

            # 검색량: API 결과 가져오기
            volume = volume_map.get(kw, 0)
            has_real_volume = volume > 0

            if volume == 0:
                # 공백 제거 버전으로 재시도
                volume = volume_map.get(kw.replace(" ", ""), 0)
                has_real_volume = volume > 0

            # 등급 재평가 — [Q7] 강화된 게이트
            # 이전 버그: SERP 분석에서 받은 grade='S'가 has_real_volume=True + volume 50-99 구간에서
            # 그대로 통과했음 (volume<50 분기에만 'B' 강등). 검색량 신뢰도 없는 S 989건의 원인.
            if has_real_volume:
                if volume >= 100 and (opportunity >= 90 or difficulty < 15):
                    grade = 'S'
                elif volume >= 50 and (opportunity >= 80 or difficulty < 20):
                    grade = 'A'
                elif volume >= 50:
                    grade = 'B'   # 50+ 검색량이지만 SERP 조건 미달
                else:
                    grade = 'C'   # 50 미만 검색량 → 신뢰도 부족, C급 강제
            else:
                # 검색량 데이터 자체 없음 → SERP grade 무시하고 C급 강제
                grade = 'C'
                volume = 30  # 점수 계산용 추정치 (등급은 이미 C 확정)

            # KEI 계산 (검색량 / 경쟁도)
            kei = 0.0
            if volume > 0 and difficulty > 0:
                kei = (volume / max(1, difficulty)) * 10

            # [Q7] 안전장치: KEI=0 (SERP 분석 실패 등) → C급 강제
            if kei == 0 and grade in ('S', 'A', 'B'):
                grade = 'C'

            priority = self._calculate_priority(
                volume, difficulty, opportunity, kw,
                is_gap=is_gap, kei=kei, trend_slope=0.0
            )

            results.append(KeywordResult(
                keyword=kw,
                search_volume=volume,
                blog_count=0,
                difficulty=difficulty,
                opportunity=opportunity,
                grade=grade,
                category=category,
                priority_score=priority,
                is_gap_keyword=is_gap,
                source="gap" if is_gap else "autocomplete",
                search_intent=_classify_intent(kw),  # [R7]
            ))

        # =====================================
        # Phase 5: 우선순위 정렬 및 결과
        # =====================================
        print("\n[Phase 5] 우선순위 정렬 및 결과...")

        results.sort(key=lambda x: x.priority_score, reverse=True)

        # 결과 출력
        print("\n" + "=" * 70)
        print("결과 요약")
        print("=" * 70)

        s_grade = [r for r in results if r.grade == "S"]
        a_grade = [r for r in results if r.grade == "A"]
        b_grade = [r for r in results if r.grade == "B"]
        c_grade = [r for r in results if r.grade == "C"]
        gap_count = sum(1 for r in results if r.is_gap_keyword)

        print(f"\nS급 (즉시 공략): {len(s_grade)}개")
        for r in s_grade[:10]:
            gap_mark = " [GAP]" if r.is_gap_keyword else ""
            print(f"  - {r.keyword} [난이도:{r.difficulty} 기회:{r.opportunity}] 우선순위:{r.priority_score:.0f}{gap_mark}")

        print(f"\nA급 (적극 공략): {len(a_grade)}개")
        for r in a_grade[:10]:
            gap_mark = " [GAP]" if r.is_gap_keyword else ""
            print(f"  - {r.keyword} [난이도:{r.difficulty} 기회:{r.opportunity}]{gap_mark}")

        print(f"\nB급 (보조 공략): {len(b_grade)}개")
        print(f"C급 (장기 전략): {len(c_grade)}개")
        print(f"\n갭 키워드 (경쟁사 역분석): {gap_count}개")

        # 카테고리별 분포
        print("\n카테고리별 분포:")
        cat_count: Dict[str, int] = {}
        for r in results:
            cat_count[r.category] = cat_count.get(r.category, 0) + 1

        for cat, cnt in sorted(cat_count.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {cnt}개")

        # =====================================
        # Phase 6: S/A급 키워드 트렌드 분석 및 우선순위 재계산
        # =====================================
        if self.has_datalab and self.datalab:
            sa_keywords = [r for r in results if r.grade in ['S', 'A']]
            if sa_keywords:
                print(f"\n[Phase 6] 트렌드 분석 (S/A급 {len(sa_keywords)}개)...")
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

                            # 트렌드 반영하여 우선순위 재계산
                            kei = (r.search_volume / max(1, r.difficulty)) * 10 if r.search_volume > 0 else 0
                            r.priority_score = self._calculate_priority(
                                r.search_volume, r.difficulty, r.opportunity, r.keyword,
                                is_gap=r.is_gap_keyword, kei=kei, trend_slope=slope
                            )
                    except Exception as e:
                        pass

                    if analyzed % 10 == 0 and analyzed > 0:
                        print(f"   진행: {analyzed}/{len(sa_keywords)}...")

                # 트렌드 반영 후 재정렬
                results.sort(key=lambda x: x.priority_score, reverse=True)

                print(f"   ✅ 트렌드 분석 완료: {analyzed}개")

                # 트렌드 통계
                rising = sum(1 for r in sa_keywords if r.trend_status == "rising")
                falling = sum(1 for r in sa_keywords if r.trend_status == "falling")
                stable = sum(1 for r in sa_keywords if r.trend_status == "stable")
                print(f"   📈 상승: {rising}개 | 📉 하락: {falling}개 | ➡️ 안정: {stable}개")

        return results

    def export_csv(self, results: List[KeywordResult], filename: str = "pathfinder_v3_results.csv"):
        """결과를 CSV로 내보내기"""
        import csv

        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'keyword', 'grade', 'priority_score', 'search_volume', 'difficulty', 'opportunity',
                'category', 'is_gap_keyword', 'source', 'trend_slope', 'trend_status'
            ])
            writer.writeheader()

            for r in results:
                writer.writerow({
                    'keyword': r.keyword,
                    'grade': r.grade,
                    'priority_score': round(r.priority_score, 1),
                    'search_volume': r.search_volume,
                    'difficulty': r.difficulty,
                    'opportunity': r.opportunity,
                    'category': r.category,
                    'is_gap_keyword': r.is_gap_keyword,
                    'source': r.source,
                    'trend_slope': round(r.trend_slope, 3),
                    'trend_status': r.trend_status
                })

        print(f"\n결과 저장: {filename}")

    def save_to_db(self, results: List[KeywordResult], db_path: str = None):
        """
        결과를 DB에 저장 (Phase 4 핵심)

        Args:
            results: KeywordResult 리스트
            db_path: DB 경로 (없으면 기본 경로)
        """
        import sqlite3
        import os

        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "db", "marketing_data.db")

        print(f"\n[DB 저장] {db_path}")

        # DB 연결 (재시도 로직 추가)
        max_retries = 5
        retry_delay = 2
        conn = None

        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(db_path, timeout=120)
                cursor = conn.cursor()

                # SQLite 최적화 (WAL 모드로 다중 접근 허용)
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=60000")
                break
            except sqlite3.OperationalError as e:
                if attempt < max_retries - 1:
                    print(f"   ⚠️  DB 잠금 감지 (시도 {attempt+1}/{max_retries}), {retry_delay}초 후 재시도...")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 지수 백오프
                else:
                    print(f"\n❌ DB 연결 실패: {e}")
                    print(f"   Dashboard나 다른 프로세스를 종료하고 다시 시도하세요.")
                    raise

        # V3 스키마 확인 및 생성
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
            trend_slope REAL DEFAULT 0.0,
            trend_status TEXT DEFAULT 'unknown',
            trend_checked_at TIMESTAMP,
            difficulty INTEGER DEFAULT 50,
            opportunity INTEGER DEFAULT 50,
            priority_v3 REAL DEFAULT 0,
            grade TEXT DEFAULT 'C',
            is_gap_keyword INTEGER DEFAULT 0,
            serp_analyzed_at TIMESTAMP,
            source TEXT DEFAULT 'legacy'
        )''')

        # V3 컬럼 추가 (없으면)
        v3_columns = [
            ("difficulty", "INTEGER DEFAULT 50"),
            ("opportunity", "INTEGER DEFAULT 50"),
            ("priority_v3", "REAL DEFAULT 0"),
            ("grade", "TEXT DEFAULT 'C'"),
            ("is_gap_keyword", "INTEGER DEFAULT 0"),
            ("serp_analyzed_at", "TIMESTAMP"),
            ("source", "TEXT DEFAULT 'legacy'"),
            ("trend_slope", "REAL DEFAULT 0"),
            ("trend_status", "TEXT DEFAULT 'unknown'")
        ]

        cursor.execute("PRAGMA table_info(keyword_insights)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        for col_name, col_type in v3_columns:
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE keyword_insights ADD COLUMN {col_name} {col_type}")
                except sqlite3.OperationalError:
                    pass  # 컬럼이 이미 존재하는 경우 무시

        # SERP 분석 테이블
        cursor.execute('''CREATE TABLE IF NOT EXISTS serp_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE,
            top_10_json TEXT,
            difficulty INTEGER DEFAULT 50,
            opportunity INTEGER DEFAULT 50,
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # 갭 키워드 테이블
        cursor.execute('''CREATE TABLE IF NOT EXISTS gap_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE,
            found_in_competitors TEXT,
            frequency INTEGER DEFAULT 0,
            priority REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # 결과 저장
        saved = 0
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for r in results:
            try:
                # 지역 추출
                region = "청주"
                for reg in ["오창", "가경", "복대", "율량", "분평", "봉명", "산남"]:
                    if reg in r.keyword:
                        region = reg
                        break

                # 의도 태그
                tag = "일반"
                if any(w in r.keyword for w in ["가격", "비용"]):
                    tag = "구매의도"
                elif any(w in r.keyword for w in ["후기", "추천"]):
                    tag = "신뢰의도"
                elif any(w in r.keyword for w in ["잘하는", "좋은"]):
                    tag = "품질탐색"

                cursor.execute('''
                    INSERT INTO keyword_insights (
                        keyword, document_count, competition, opp_score, tag, created_at,
                        search_volume, region, category,
                        difficulty, opportunity, priority_v3, grade,
                        is_gap_keyword, serp_analyzed_at, source,
                        trend_slope, trend_status, search_intent
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(keyword) DO UPDATE SET
                        document_count=excluded.document_count,
                        opp_score=excluded.opp_score,
                        tag=excluded.tag,
                        created_at=excluded.created_at,
                        search_volume=excluded.search_volume,
                        region=excluded.region,
                        category=excluded.category,
                        difficulty=excluded.difficulty,
                        opportunity=excluded.opportunity,
                        priority_v3=excluded.priority_v3,
                        grade=excluded.grade,
                        is_gap_keyword=excluded.is_gap_keyword,
                        serp_analyzed_at=excluded.serp_analyzed_at,
                        source=excluded.source,
                        trend_slope=excluded.trend_slope,
                        trend_status=excluded.trend_status,
                        search_intent=excluded.search_intent
                ''', (
                    r.keyword,
                    r.blog_count,
                    "Low" if r.difficulty < 50 else "High",
                    r.priority_score,
                    tag,
                    now,
                    r.search_volume,
                    region,
                    r.category,
                    r.difficulty,
                    r.opportunity,
                    r.priority_score,
                    r.grade,
                    1 if r.is_gap_keyword else 0,
                    now,
                    r.source,
                    r.trend_slope,
                    r.trend_status,
                    r.search_intent,  # [R7]
                ))
                saved += 1
            except Exception as e:
                print(f"   저장 오류 ({r.keyword}): {e}")

        conn.commit()
        conn.close()

        print(f"   {saved}/{len(results)}개 키워드 DB 저장 완료")

        # [Phase 2.1] 이벤트 발행 - 새 키워드 발견
        if HAS_EVENT_BUS and saved > 0:
            try:
                # A등급 이상 키워드만 이벤트 발행
                high_grade_keywords = [r for r in results if r.grade in ['S', 'A']]
                if high_grade_keywords:
                    publish_event(
                        EventType.KEYWORD_DISCOVERED,
                        {
                            'total_saved': saved,
                            'high_grade_count': len(high_grade_keywords),
                            'keywords': [
                                {'keyword': k.keyword, 'grade': k.grade, 'priority': k.priority_score}
                                for k in high_grade_keywords[:10]  # 상위 10개만
                            ]
                        },
                        source='pathfinder'
                    )
                    print(f"   📡 이벤트 발행: {len(high_grade_keywords)}개 고등급 키워드")
            except Exception as e:
                print(f"   ⚠️ 이벤트 발행 실패: {e}")

        # 저장 결과 요약
        print(f"\n   등급별 저장:")
        grade_counts = {}
        for r in results:
            grade_counts[r.grade] = grade_counts.get(r.grade, 0) + 1
        for g in ["S", "A", "B", "C"]:
            print(f"      {g}급: {grade_counts.get(g, 0)}개")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Pathfinder V3 - 키워드 발굴 시스템")
    parser.add_argument("--max", type=int, default=50, help="최대 키워드 수 (기본: 50)")
    parser.add_argument("--no-db", action="store_true", help="DB 저장 안 함")
    parser.add_argument("--no-csv", action="store_true", help="CSV 저장 안 함")
    parser.add_argument("--save-db", action="store_true", help="DB에 저장 (--no-db의 반대)")
    args = parser.parse_args()

    # 실시간 로그 스트리밍 설정
    tee = setup_live_logging()

    pf = PathfinderV3()
    results = pf.run(max_keywords=args.max)

    print("\n" + "=" * 70)
    print(f"총 {len(results)}개 키워드 분석 완료!")
    print("=" * 70)

    # CSV 내보내기
    if not args.no_csv:
        pf.export_csv(results)

    # DB 저장 (기본값: True, --no-db로 비활성화)
    if not args.no_db:
        pf.save_to_db(results)


if __name__ == "__main__":
    main()

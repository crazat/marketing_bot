#!/usr/bin/env python3
"""
Pathfinder V3 통합 실행기
- Phase 1: Naver 자동완성 기반 키워드 수집
- Phase 2: SERP 분석 (난이도/기회 점수)
- 통합 우선순위 계산
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import requests
import re
import time
from bs4 import BeautifulSoup
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional


# ============================================================
# Phase 1: 키워드 수집 (Naver 자동완성 + Ad API)
# ============================================================

class NaverAutocomplete:
    """Naver 자동완성 수집기"""

    def __init__(self, delay: float = 0.3):
        self.delay = delay
        self.base_url = "https://ac.search.naver.com/nx/ac"
        self._last_call = 0

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def get_suggestions(self, keyword: str) -> List[str]:
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

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.naver.com/"
        }

        try:
            response = requests.get(self.base_url, params=params, headers=headers, timeout=10)
            data = response.json()

            if "items" in data and data["items"] and len(data["items"]) > 0:
                return [item[0] if isinstance(item, list) else item
                        for item in data["items"][0]]
            return []
        except Exception:
            return []


# ============================================================
# Phase 2: SERP 분석
# ============================================================

@dataclass
class SERPResult:
    """SERP 분석 결과"""
    keyword: str
    search_volume: int
    blog_count: int
    difficulty: int
    opportunity: int
    grade: str
    category: str
    priority_score: float


class SERPAnalyzer:
    """SERP 분석기"""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self._last_call = 0

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
            except Exception:
                pass

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
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }

        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
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
            print(f"SERP 분석 오류 ({keyword}): {e}")
            return 50, 50, "B"


# ============================================================
# 통합 실행기
# ============================================================

class PathfinderV3:
    """Pathfinder V3 통합 클래스"""

    def __init__(self):
        self.autocomplete = NaverAutocomplete(delay=0.3)
        self.serp_analyzer = SERPAnalyzer(delay=1.0)

        # 청주 지역명
        self.cheongju_regions = [
            "청주", "상당", "서원", "흥덕", "청원",
            "복대", "가경", "율량", "오창", "오송",
            "분평", "봉명", "산남", "용암", "금천"
        ]

        # 카테고리 패턴
        self.category_patterns = {
            "다이어트": ["다이어트", "비만", "살빼", "체중"],
            "피부": ["여드름", "피부", "모공", "아토피"],
            "교통사고": ["교통사고", "자동차사고", "후유증"],
            "통증": ["통증", "디스크", "허리", "어깨", "무릎"],
            "탈모": ["탈모", "두피"],
            "여성": ["갱년기", "폐경", "산후", "생리"],
            "비염": ["비염", "알레르기", "축농증"],
            "한의원": ["한의원", "한방", "한약", "침", "추나"],
        }

    def _detect_category(self, keyword: str) -> str:
        """카테고리 감지"""
        kw = keyword.lower()
        for cat, patterns in self.category_patterns.items():
            if any(p in kw for p in patterns):
                return cat
        return "기타"

    def _calculate_priority(self, volume: int, difficulty: int, opportunity: int, keyword: str) -> float:
        """
        V3 우선순위 점수 계산

        Priority = 검색량 × (1/난이도) × 기회보너스 × 의도가중치
        """
        # 기본 점수
        base = volume if volume > 0 else 10

        # 난이도 보정 (낮을수록 좋음)
        difficulty_factor = (100 - difficulty) / 100

        # 기회 보너스
        opportunity_factor = 1 + (opportunity / 100)

        # 의도 가중치
        intent_weight = 1.0
        if any(w in keyword for w in ["가격", "비용"]):
            intent_weight = 1.5
        elif any(w in keyword for w in ["후기", "추천"]):
            intent_weight = 1.3
        elif any(w in keyword for w in ["잘하는", "좋은"]):
            intent_weight = 1.2

        return base * difficulty_factor * opportunity_factor * intent_weight

    def run(self, max_keywords: int = 100) -> List[SERPResult]:
        """
        V3 실행

        Args:
            max_keywords: 최대 분석 키워드 수

        Returns:
            SERPResult 리스트 (우선순위 순)
        """
        print("=" * 70)
        print("Pathfinder V3 통합 실행")
        print("=" * 70)

        # Phase 1: 시드 생성 및 자동완성 수집
        print("\n[Phase 1] 키워드 수집...")

        seeds = []
        terms = ["한의원", "다이어트", "교통사고", "탈모", "비염", "통증"]

        for term in terms:
            seeds.append(f"청주 {term}")
            seeds.append(f"청주 {term} 추천")
            seeds.append(f"청주 {term} 가격")

        for dong in ["오창", "가경동", "복대동"]:
            seeds.append(f"{dong} 한의원")

        print(f"시드: {len(seeds)}개")

        # 자동완성 확장
        all_keywords = set(seeds)
        for seed in seeds:
            suggestions = self.autocomplete.get_suggestions(seed)
            for s in suggestions:
                if any(r in s for r in self.cheongju_regions):
                    all_keywords.add(s)

        print(f"자동완성 확장: {len(all_keywords)}개")

        # 키워드 수 제한
        keywords = list(all_keywords)[:max_keywords]
        print(f"분석 대상: {len(keywords)}개")

        # Phase 2: SERP 분석
        print(f"\n[Phase 2] SERP 분석 (약 {len(keywords)}초 소요)...")

        results = []
        for i, kw in enumerate(keywords, 1):
            if i % 10 == 0:
                print(f"   진행: {i}/{len(keywords)}...")

            difficulty, opportunity, grade = self.serp_analyzer.analyze(kw)
            category = self._detect_category(kw)

            # 가상 검색량 (실제로는 Ad API 필요)
            volume = 100 if grade in ["S", "A"] else 50 if grade == "B" else 30

            priority = self._calculate_priority(volume, difficulty, opportunity, kw)

            results.append(SERPResult(
                keyword=kw,
                search_volume=volume,
                blog_count=0,  # 별도 조회 필요
                difficulty=difficulty,
                opportunity=opportunity,
                grade=grade,
                category=category,
                priority_score=priority
            ))

        # 우선순위 정렬
        results.sort(key=lambda x: x.priority_score, reverse=True)

        # 결과 출력
        print("\n" + "=" * 70)
        print("결과 요약")
        print("=" * 70)

        s_grade = [r for r in results if r.grade == "S"]
        a_grade = [r for r in results if r.grade == "A"]
        b_grade = [r for r in results if r.grade == "B"]
        c_grade = [r for r in results if r.grade == "C"]

        print(f"\nS급 (즉시 공략): {len(s_grade)}개")
        for r in s_grade[:10]:
            print(f"  - {r.keyword} [난이도:{r.difficulty} 기회:{r.opportunity}] 우선순위:{r.priority_score:.0f}")

        print(f"\nA급 (적극 공략): {len(a_grade)}개")
        for r in a_grade[:10]:
            print(f"  - {r.keyword} [난이도:{r.difficulty} 기회:{r.opportunity}]")

        print(f"\nB급 (보조 공략): {len(b_grade)}개")
        print(f"C급 (장기 전략): {len(c_grade)}개")

        # 카테고리별 분포
        print("\n카테고리별 분포:")
        cat_count = {}
        for r in results:
            cat_count[r.category] = cat_count.get(r.category, 0) + 1

        for cat, cnt in sorted(cat_count.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {cnt}개")

        return results


def main():
    pf = PathfinderV3()
    results = pf.run(max_keywords=50)

    print("\n" + "=" * 70)
    print(f"총 {len(results)}개 키워드 분석 완료!")
    print("=" * 70)


if __name__ == "__main__":
    main()

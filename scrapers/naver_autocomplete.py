#!/usr/bin/env python3
"""
Naver Autocomplete Scraper
- 실제 사용자가 검색하는 키워드 수집
- Phase 1: Pathfinder V3의 핵심 키워드 소스
"""
import requests
import time
import logging
from typing import List, Set, Optional
from collections import deque

logger = logging.getLogger(__name__)


class NaverAutocompleteScraper:
    """
    네이버 자동완성 API를 활용한 실제 검색 키워드 수집기

    특징:
    - 실제 사용자가 검색하는 키워드만 반환
    - BFS 방식으로 깊이 있는 키워드 확장
    - Rate limiting 내장 (0.3초 간격)
    """

    def __init__(self, delay: float = 0.3):
        """
        Args:
            delay: API 호출 간 대기 시간 (초)
        """
        self.delay = delay
        self.base_url = "https://ac.search.naver.com/nx/ac"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.naver.com/"
        }
        self._last_call = 0

    def _rate_limit(self):
        """API 호출 간격 제어"""
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def get_suggestions(self, keyword: str) -> List[str]:
        """
        단일 키워드에 대한 자동완성 제안 가져오기

        Args:
            keyword: 검색할 키워드

        Returns:
            자동완성 제안 키워드 리스트 (최대 10개)
        """
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
            response = requests.get(
                self.base_url,
                params=params,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()

            data = response.json()

            # items[0]에 자동완성 리스트가 있음
            if "items" in data and data["items"] and len(data["items"]) > 0:
                items = data["items"][0]
                suggestions = []
                for item in items:
                    if isinstance(item, list) and len(item) > 0:
                        suggestions.append(item[0])
                    elif isinstance(item, str):
                        suggestions.append(item)
                return suggestions

            return []

        except requests.exceptions.RequestException as e:
            logger.warning(f"자동완성 API 호출 실패 ({keyword}): {e}")
            return []
        except (KeyError, IndexError, ValueError) as e:
            logger.warning(f"자동완성 응답 파싱 실패 ({keyword}): {e}")
            return []

    def expand_keywords_bfs(
        self,
        seed_keywords: List[str],
        max_depth: int = 2,
        max_total: int = 500,
        region_filter: Optional[List[str]] = None
    ) -> List[str]:
        """
        BFS 방식으로 키워드 확장

        시드 키워드에서 시작하여 자동완성을 통해 관련 키워드를 확장

        Args:
            seed_keywords: 시작 키워드 리스트
            max_depth: 최대 확장 깊이 (1=시드의 자동완성만, 2=자동완성의 자동완성까지)
            max_total: 최대 수집 키워드 수
            region_filter: 포함해야 할 지역명 리스트 (None이면 필터 안 함)

        Returns:
            확장된 키워드 리스트 (중복 제거됨)
        """
        collected: Set[str] = set()
        queue = deque()

        # 시드 키워드를 큐에 추가 (depth=0)
        for seed in seed_keywords:
            queue.append((seed, 0))
            collected.add(seed)

        while queue and len(collected) < max_total:
            current_keyword, depth = queue.popleft()

            if depth >= max_depth:
                continue

            # 자동완성 가져오기
            suggestions = self.get_suggestions(current_keyword)

            for suggestion in suggestions:
                if suggestion in collected:
                    continue

                # 지역 필터 적용
                if region_filter:
                    has_region = any(region in suggestion for region in region_filter)
                    if not has_region:
                        continue

                collected.add(suggestion)

                # 다음 깊이로 큐에 추가
                if depth + 1 < max_depth:
                    queue.append((suggestion, depth + 1))

                if len(collected) >= max_total:
                    break

            # 진행 상황 로깅 (100개마다)
            if len(collected) % 100 == 0:
                logger.info(f"자동완성 키워드 수집 진행: {len(collected):,}개")

        return list(collected)

    def expand_with_modifiers(
        self,
        base_keywords: List[str],
        modifiers: Optional[List[str]] = None,
        max_total: int = 1000
    ) -> List[str]:
        """
        기본 키워드에 수식어를 붙여서 확장

        Args:
            base_keywords: 기본 키워드 리스트 (예: ["청주 다이어트", "청주 한의원"])
            modifiers: 추가할 수식어 (None이면 기본 수식어 사용)
            max_total: 최대 수집 키워드 수

        Returns:
            확장된 키워드 리스트
        """
        if modifiers is None:
            modifiers = [
                "가격", "비용", "후기", "추천", "잘하는곳",
                "효과", "부작용", "기간", "상담", "예약",
                "진료", "치료", "약", "병원", "의원"
            ]

        collected: Set[str] = set()

        for base in base_keywords:
            collected.add(base)

            # 기본 키워드의 자동완성
            suggestions = self.get_suggestions(base)
            for s in suggestions:
                collected.add(s)

            # 수식어 조합
            for mod in modifiers:
                combined = f"{base} {mod}"
                suggestions = self.get_suggestions(combined)

                for s in suggestions:
                    collected.add(s)
                    if len(collected) >= max_total:
                        break

                if len(collected) >= max_total:
                    break

            if len(collected) >= max_total:
                break

        return list(collected)


def main():
    """테스트 실행"""
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 60)
    print("Naver Autocomplete Scraper 테스트")
    print("=" * 60)

    scraper = NaverAutocompleteScraper(delay=0.3)

    # 테스트 1: 단일 키워드 자동완성
    print("\n[테스트 1] 단일 키워드 자동완성")
    print("-" * 40)
    test_keywords = ["청주 다이어트", "청주 한의원", "청주 교통사고"]

    for kw in test_keywords:
        suggestions = scraper.get_suggestions(kw)
        print(f"\n'{kw}'의 자동완성 ({len(suggestions)}개):")
        for i, s in enumerate(suggestions, 1):
            print(f"  {i}. {s}")

    # 테스트 2: BFS 확장
    print("\n\n[테스트 2] BFS 키워드 확장")
    print("-" * 40)

    seeds = ["청주 다이어트", "청주 한의원"]
    cheongju_regions = ["청주", "오창", "오송", "복대", "가경", "율량"]

    expanded = scraper.expand_keywords_bfs(
        seed_keywords=seeds,
        max_depth=2,
        max_total=50,
        region_filter=cheongju_regions
    )

    print(f"\n시드 {len(seeds)}개 → 확장 {len(expanded)}개")
    print("\n확장된 키워드:")
    for i, kw in enumerate(expanded, 1):
        print(f"  {i}. {kw}")

    # 테스트 3: 수식어 확장
    print("\n\n[테스트 3] 수식어 기반 확장")
    print("-" * 40)

    base = ["청주 다이어트"]
    expanded_mod = scraper.expand_with_modifiers(
        base_keywords=base,
        modifiers=["가격", "후기", "추천"],
        max_total=30
    )

    print(f"\n기본 키워드: {base}")
    print(f"확장된 키워드 ({len(expanded_mod)}개):")
    for i, kw in enumerate(expanded_mod, 1):
        print(f"  {i}. {kw}")


if __name__ == "__main__":
    main()

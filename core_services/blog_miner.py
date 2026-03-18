#!/usr/bin/env python3
"""
블로그 제목 마이닝
- 상위 노출 블로그에서 키워드 패턴 추출
- 경쟁사가 타겟팅하는 키워드 파악
"""

import re
import time
import requests
from bs4 import BeautifulSoup
from typing import List, Set, Dict, Tuple
from collections import Counter


class BlogTitleMiner:
    """블로그 검색 결과에서 키워드 추출"""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self._last_call = 0
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }

        # 키워드 추출 패턴
        self.extraction_patterns = [
            # 지역 + 시술 + 한의원
            r'(청주\s*\S+\s*한의원)',
            r'(청주\s*\S+\s*한약)',
            # 지역 + 키워드 + 추천/후기
            r'(청주\s*\S+\s*추천)',
            r'(청주\s*\S+\s*후기)',
            r'(청주\s*\S+\s*가격)',
            r'(청주\s*\S+\s*비용)',
            r'(청주\s*\S+\s*효과)',
            # N글자 패턴
            r'(청주\s*[\w가-힣]{2,6}\s*[\w가-힣]{2,6})',
        ]

        # 제외할 패턴
        self.exclude_patterns = [
            r'^\d+',  # 숫자로 시작
            r'카페',  # 카페 관련
            r'맛집',  # 맛집 (비관련)
            r'부동산',  # 부동산 (비관련)
        ]

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def _is_valid_keyword(self, keyword: str) -> bool:
        """추출된 키워드 유효성 검사"""
        # 너무 짧거나 긴 키워드 제외 (개선: 30→60자로 확대하여 롱테일 키워드 수집)
        if len(keyword) < 4 or len(keyword) > 60:
            return False

        # 제외 패턴 체크
        for pattern in self.exclude_patterns:
            if re.search(pattern, keyword):
                return False

        # 한방 관련 키워드 포함 확인
        hanbang_keywords = [
            '한의원', '한약', '한방', '침', '추나',
            '다이어트', '교통사고', '비대칭', '여드름', '탈모',
            '비염', '디스크', '통증', '보약', '갱년기'
        ]

        return any(hk in keyword for hk in hanbang_keywords)

    def mine_from_search(self, query: str, top_n: int = 20) -> Set[str]:
        """
        네이버 블로그 검색 결과에서 키워드 추출

        Args:
            query: 검색어
            top_n: 분석할 상위 결과 수

        Returns:
            추출된 키워드 세트
        """
        self._rate_limit()

        url = "https://search.naver.com/search.naver"
        params = {"where": "blog", "query": query}

        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')

            # 블로그 제목 추출
            titles = []
            for title_elem in soup.select('.title_link, .api_txt_lines.total_tit'):
                text = title_elem.get_text(strip=True)
                if text and len(text) > 5:
                    titles.append(text)

            if not titles:
                return set()

            # 키워드 추출
            keywords = set()
            for title in titles[:top_n]:
                for pattern in self.extraction_patterns:
                    matches = re.findall(pattern, title)
                    for match in matches:
                        # 공백 정리
                        cleaned = re.sub(r'\s+', ' ', match.strip())
                        if self._is_valid_keyword(cleaned):
                            keywords.add(cleaned)

            return keywords

        except Exception as e:
            print(f"   ⚠️ 블로그 마이닝 실패 ({query}): {e}")
            return set()

    def mine_batch(self, queries: List[str], top_n: int = 10) -> Set[str]:
        """
        여러 검색어로 배치 마이닝

        Args:
            queries: 검색어 목록
            top_n: 검색어당 분석할 상위 결과 수

        Returns:
            추출된 키워드 세트 (합집합)
        """
        all_keywords = set()

        for query in queries:
            keywords = self.mine_from_search(query, top_n)
            all_keywords.update(keywords)

        return all_keywords

    def extract_common_patterns(self, titles: List[str]) -> Dict[str, int]:
        """
        제목들에서 공통 패턴 추출

        Args:
            titles: 블로그 제목 목록

        Returns:
            {패턴: 빈도수} 딕셔너리
        """
        # 2-gram, 3-gram 추출
        ngrams = Counter()

        for title in titles:
            words = title.split()
            # 2-gram
            for i in range(len(words) - 1):
                ngram = ' '.join(words[i:i+2])
                if len(ngram) >= 4:
                    ngrams[ngram] += 1
            # 3-gram
            for i in range(len(words) - 2):
                ngram = ' '.join(words[i:i+3])
                if len(ngram) >= 6:
                    ngrams[ngram] += 1

        # 빈도 2 이상만 반환
        return {k: v for k, v in ngrams.most_common(50) if v >= 2}


# 테스트 코드
if __name__ == '__main__':
    miner = BlogTitleMiner()

    # 테스트 검색어
    test_queries = [
        "청주 다이어트 한의원",
        "청주 교통사고 한의원",
        "청주 안면비대칭"
    ]

    print("=== 블로그 제목 마이닝 테스트 ===")
    for query in test_queries:
        print(f"\n검색어: {query}")
        keywords = miner.mine_from_search(query, top_n=10)
        print(f"추출 키워드 ({len(keywords)}개): {keywords}")

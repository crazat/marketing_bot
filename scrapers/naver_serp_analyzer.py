#!/usr/bin/env python3
"""
Naver SERP Analyzer
- 네이버 검색 결과 1페이지 분석
- 상위 블로그 품질 분석
- 키워드 난이도/기회 점수 계산

Phase 2: Pathfinder V3
"""
import requests
import time
import re
import json
import logging
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class BlogAnalysis:
    """개별 블로그 포스트 분석 결과"""
    rank: int                    # SERP 순위 (1-10)
    url: str                     # 블로그 URL
    title: str                   # 제목
    snippet: str                 # 미리보기 텍스트
    blog_name: str               # 블로그 이름

    # 콘텐츠 품질 지표 (상세 분석 시)
    word_count: int = 0          # 글자 수
    image_count: int = 0         # 이미지 수

    # 블로그 권위 지표
    blog_type: str = "personal"  # "official" | "influencer" | "personal"
    is_official: bool = False    # 공식 블로그 여부

    # 시간 지표
    publish_date: str = ""       # 발행일 (문자열)
    days_since_publish: int = 365  # 발행 후 경과일

    # 품질 점수 (0-100)
    quality_score: int = 50


@dataclass
class SERPAnalysis:
    """SERP 분석 결과"""
    keyword: str
    total_results: int           # 총 검색 결과 수
    blog_results: List[BlogAnalysis]  # 상위 블로그 목록

    # 계산된 점수
    difficulty: int              # 난이도 (0-100, 높을수록 어려움)
    opportunity: int             # 기회 점수 (0-100, 높을수록 좋음)
    grade: str                   # 등급 (S/A/B/C)

    analyzed_at: str             # 분석 시간


class NaverSERPAnalyzer:
    """
    네이버 검색 결과 분석기

    기능:
    - 검색 결과 1페이지 크롤링
    - 상위 블로그 품질 분석
    - 난이도/기회 점수 계산
    """

    def __init__(self, delay: float = 1.0):
        """
        Args:
            delay: 요청 간 대기 시간 (초)
        """
        self.delay = delay
        self.session = requests.Session()

        # User-Agent 로테이션
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        self.ua_index = 0
        self._last_call = 0

    def _get_headers(self) -> dict:
        """헤더 생성 (User-Agent 로테이션)"""
        ua = self.user_agents[self.ua_index % len(self.user_agents)]
        self.ua_index += 1

        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://www.naver.com/",
        }

    def _rate_limit(self):
        """API 호출 간격 제어"""
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def _parse_date(self, date_str: str) -> Tuple[str, int]:
        """
        날짜 문자열 파싱

        Args:
            date_str: "2024.01.15.", "3일 전", "1시간 전" 등

        Returns:
            (날짜 문자열, 경과일)
        """
        now = datetime.now()

        # "X일 전" 패턴
        if "일 전" in date_str:
            match = re.search(r"(\d+)일 전", date_str)
            if match:
                days = int(match.group(1))
                return date_str, days

        # "X시간 전" 패턴
        if "시간 전" in date_str:
            return date_str, 0

        # "X분 전" 패턴
        if "분 전" in date_str:
            return date_str, 0

        # "어제" 패턴
        if "어제" in date_str:
            return date_str, 1

        # "YYYY.MM.DD." 패턴
        match = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", date_str)
        if match:
            try:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))
                pub_date = datetime(year, month, day)
                days = (now - pub_date).days

                # 미래 날짜인 경우 (데이터 오류) 기본값 사용
                if days < 0:
                    return date_str, 30  # 최근 글로 간주

                return date_str, days
            except Exception:
                pass

        # 파싱 실패 시 기본값 (중간 정도)
        return date_str, 90

    def _detect_blog_type(self, blog_name: str, url: str) -> Tuple[str, bool]:
        """
        블로그 타입 감지

        Returns:
            (blog_type, is_official)
        """
        # 공식 블로그 패턴
        official_patterns = [
            "한의원", "병원", "의원", "클리닉", "센터",
            "공식", "official", "대표", "원장"
        ]

        # 인플루언서 패턴
        influencer_patterns = [
            "인플루언서", "파워블로거", "에디터", "리뷰어"
        ]

        blog_name_lower = blog_name.lower()

        # 공식 블로그 체크
        if any(pat in blog_name_lower for pat in official_patterns):
            return "official", True

        # 인플루언서 체크
        if any(pat in blog_name_lower for pat in influencer_patterns):
            return "influencer", False

        # 기본값: 개인 블로그
        return "personal", False

    def analyze_serp(self, keyword: str, detailed: bool = False) -> Optional[SERPAnalysis]:
        """
        키워드의 SERP 분석

        Args:
            keyword: 분석할 키워드
            detailed: True면 각 블로그 상세 분석 (느림)

        Returns:
            SERPAnalysis 또는 None (실패 시)
        """
        self._rate_limit()

        url = "https://search.naver.com/search.naver"
        params = {
            "where": "blog",  # 블로그 탭
            "query": keyword,
            "sm": "tab_opt",
            "nso": "so:r,p:all"  # 정렬: 관련도
        }

        try:
            response = self.session.get(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=10
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # 블로그 검색 결과 파싱
            blog_results = self._parse_blog_results(soup, keyword)

            if not blog_results:
                logger.warning(f"No blog results found for: {keyword}")
                return None

            # 총 검색 결과 수 파싱
            total_results = self._parse_total_results(soup)

            # 상세 분석 (옵션)
            if detailed:
                blog_results = self._analyze_blogs_detailed(blog_results)

            # 난이도/기회 점수 계산
            difficulty = self._calculate_difficulty(blog_results)
            opportunity = self._calculate_opportunity(blog_results)
            grade = self._assign_grade(difficulty, opportunity)

            return SERPAnalysis(
                keyword=keyword,
                total_results=total_results,
                blog_results=blog_results,
                difficulty=difficulty,
                opportunity=opportunity,
                grade=grade,
                analyzed_at=datetime.now().isoformat()
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"SERP request failed for '{keyword}': {e}")
            return None
        except Exception as e:
            logger.error(f"SERP parsing failed for '{keyword}': {e}")
            return None

    def _parse_blog_results(self, soup: BeautifulSoup, keyword: str) -> List[BlogAnalysis]:
        """블로그 검색 결과 파싱 (2024-2026 네이버 HTML 구조)"""
        results = []

        # 방법 1: blog.naver.com/username/postid 패턴의 링크 찾기
        post_pattern = re.compile(r'blog\.naver\.com/(\w+)/(\d+)')

        seen_urls = set()
        all_links = soup.find_all('a', href=True)

        for link in all_links:
            href = link.get('href', '')

            # 블로그 포스트 링크인지 확인
            match = post_pattern.search(href)
            if not match:
                continue

            # 중복 URL 제거
            if href in seen_urls:
                continue

            # 제목 추출 (링크 텍스트)
            title = link.get_text(strip=True)

            # 제목이 너무 짧거나 없으면 건너뛰기
            if not title or len(title) < 5:
                continue

            seen_urls.add(href)

            # 블로그 이름 추출 (username에서)
            username = match.group(1)

            # 부모 요소에서 추가 정보 찾기
            blog_name = username
            pub_date = ""
            days_since = 180  # 기본값

            # 상위 컨테이너에서 날짜/블로그명 찾기
            parent = link.parent
            for _ in range(10):  # 최대 10단계 상위까지
                if parent is None:
                    break

                # 날짜 패턴 찾기
                text = parent.get_text()
                date_match = re.search(r'(\d{4}\.\d{1,2}\.\d{1,2})', text)
                if date_match and not pub_date:
                    pub_date = date_match.group(1)
                    pub_date, days_since = self._parse_date(pub_date)

                # 다른 날짜 패턴 (X일 전)
                days_match = re.search(r'(\d+)일 전', text)
                if days_match and days_since == 180:
                    days_since = int(days_match.group(1))
                    pub_date = f"{days_since}일 전"

                parent = parent.parent

            # 블로그 타입 감지
            blog_type, is_official = self._detect_blog_type(blog_name, href)

            results.append(BlogAnalysis(
                rank=len(results) + 1,
                url=href,
                title=title,
                snippet="",
                blog_name=blog_name,
                blog_type=blog_type,
                is_official=is_official,
                publish_date=pub_date,
                days_since_publish=days_since
            ))

            # 최대 10개
            if len(results) >= 10:
                break

        # 결과가 없으면 대체 방법 시도
        if not results:
            logger.debug("Primary parsing failed, trying fallback method")
            results = self._parse_blog_results_fallback(soup)

        return results

    def _parse_blog_results_fallback(self, soup: BeautifulSoup) -> List[BlogAnalysis]:
        """대체 파싱 방법 (기존 선택자)"""
        results = []

        # 여러 선택자 시도
        selectors = [
            '.api_txt_lines.total_tit',
            '.title_link',
            'a[href*="blog.naver.com"]'
        ]

        for selector in selectors:
            items = soup.select(selector)
            if items:
                for i, item in enumerate(items[:10], 1):
                    title = item.get_text(strip=True)
                    url = item.get('href', '')

                    if title and len(title) > 5 and 'blog.naver.com' in url:
                        results.append(BlogAnalysis(
                            rank=i,
                            url=url,
                            title=title,
                            snippet="",
                            blog_name="블로그"
                        ))

                if results:
                    break

        return results

    def _parse_total_results(self, soup: BeautifulSoup) -> int:
        """총 검색 결과 수 파싱"""
        try:
            # "블로그 1-10 / 12,345건" 패턴
            count_elem = soup.select_one('.title_num') or soup.select_one('.result_info')
            if count_elem:
                text = count_elem.get_text()
                match = re.search(r'([\d,]+)건', text)
                if match:
                    return int(match.group(1).replace(',', ''))
        except Exception:
            pass

        return 0

    def _analyze_blogs_detailed(self, blogs: List[BlogAnalysis]) -> List[BlogAnalysis]:
        """
        각 블로그 상세 분석 (글자 수, 이미지 수 등)
        주의: 느림 (각 블로그 페이지 방문)
        """
        for blog in blogs[:5]:  # 상위 5개만 상세 분석
            try:
                self._rate_limit()

                response = self.session.get(
                    blog.url,
                    headers=self._get_headers(),
                    timeout=10
                )

                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')

                # 본문 찾기
                content = soup.select_one('.se-main-container') or \
                          soup.select_one('#postViewArea') or \
                          soup.select_one('.post-view')

                if content:
                    # 글자 수
                    text = content.get_text(strip=True)
                    blog.word_count = len(text)

                    # 이미지 수
                    images = content.select('img')
                    blog.image_count = len(images)

                # 품질 점수 계산
                blog.quality_score = self._calculate_blog_quality(blog)

            except Exception as e:
                logger.debug(f"Failed to analyze blog detail: {e}")
                continue

        return blogs

    def _calculate_blog_quality(self, blog: BlogAnalysis) -> int:
        """개별 블로그 품질 점수 계산 (0-100)"""
        score = 0

        # 글자 수 점수 (최대 25)
        if blog.word_count >= 3000:
            score += 25
        elif blog.word_count >= 2000:
            score += 20
        elif blog.word_count >= 1000:
            score += 15
        elif blog.word_count >= 500:
            score += 10
        else:
            score += 5

        # 이미지 수 점수 (최대 20)
        if blog.image_count >= 10:
            score += 20
        elif blog.image_count >= 5:
            score += 15
        elif blog.image_count >= 3:
            score += 10
        else:
            score += 5

        # 블로그 타입 점수 (최대 30)
        if blog.blog_type == "official":
            score += 30
        elif blog.blog_type == "influencer":
            score += 20
        else:
            score += 10

        # 발행일 점수 (최대 25)
        if blog.days_since_publish <= 30:
            score += 25
        elif blog.days_since_publish <= 90:
            score += 20
        elif blog.days_since_publish <= 180:
            score += 15
        elif blog.days_since_publish <= 365:
            score += 10
        else:
            score += 5

        return min(score, 100)

    def _calculate_difficulty(self, blogs: List[BlogAnalysis]) -> int:
        """
        키워드 난이도 계산 (0-100)

        높을수록 어려움:
        - 공식 블로그가 많으면 어려움
        - 최신 글이 많으면 어려움
        - 고품질 글이 많으면 어려움
        """
        if not blogs:
            return 50

        scores = []

        for blog in blogs[:5]:  # 상위 5개만
            score = 0

            # 블로그 타입 점수
            if blog.is_official:
                score += 35
            elif blog.blog_type == "influencer":
                score += 25
            else:
                score += 10

            # 발행일 점수 (최신일수록 어려움)
            if blog.days_since_publish <= 30:
                score += 30
            elif blog.days_since_publish <= 90:
                score += 20
            elif blog.days_since_publish <= 180:
                score += 10
            else:
                score += 5

            # 글자 수 점수 (상세 분석 시)
            if blog.word_count >= 2000:
                score += 20
            elif blog.word_count >= 1000:
                score += 10

            # 이미지 수 점수 (상세 분석 시)
            if blog.image_count >= 5:
                score += 15
            elif blog.image_count >= 3:
                score += 10

            scores.append(score)

        # 상위 5개 평균 (빈 슬롯은 기본값)
        while len(scores) < 5:
            scores.append(30)

        return min(int(sum(scores) / len(scores)), 100)

    def _calculate_opportunity(self, blogs: List[BlogAnalysis]) -> int:
        """
        기회 점수 계산 (0-100)

        높을수록 좋음:
        - 오래된 글이 상위에 있으면 기회
        - 개인 블로그가 상위에 있으면 기회
        - 짧은 글이 상위에 있으면 기회
        """
        if not blogs:
            return 50

        opportunity = 0

        for i, blog in enumerate(blogs[:5]):
            position_weight = (5 - i)  # 1위: 4, 2위: 3, ... 5위: 0

            # 오래된 글 (6개월+)
            if blog.days_since_publish > 180:
                opportunity += 8 * position_weight

            # 개인 블로그
            if blog.blog_type == "personal" and not blog.is_official:
                opportunity += 10 * position_weight

            # 짧은 글 (상세 분석 시)
            if 0 < blog.word_count < 1000:
                opportunity += 6 * position_weight

            # 이미지 적음 (상세 분석 시)
            if 0 < blog.image_count < 3:
                opportunity += 4 * position_weight

        return min(opportunity, 100)

    def _assign_grade(self, difficulty: int, opportunity: int) -> str:
        """
        등급 부여

        - S급: 난이도 30 이하 + 기회 70 이상
        - A급: 난이도 40 이하 + 기회 50 이상
        - B급: 난이도 60 이하
        - C급: 그 외
        """
        if difficulty <= 30 and opportunity >= 70:
            return "S"
        elif difficulty <= 40 and opportunity >= 50:
            return "A"
        elif difficulty <= 60:
            return "B"
        else:
            return "C"

    def analyze_keywords_batch(
        self,
        keywords: List[str],
        detailed: bool = False,
        max_keywords: int = 50
    ) -> List[SERPAnalysis]:
        """
        여러 키워드 일괄 분석

        Args:
            keywords: 분석할 키워드 리스트
            detailed: 상세 분석 여부
            max_keywords: 최대 분석 키워드 수

        Returns:
            SERPAnalysis 리스트
        """
        results = []

        for i, kw in enumerate(keywords[:max_keywords], 1):
            logger.info(f"[{i}/{min(len(keywords), max_keywords)}] Analyzing: {kw}")

            analysis = self.analyze_serp(kw, detailed=detailed)
            if analysis:
                results.append(analysis)

            # 진행 상황 (10개마다)
            if i % 10 == 0:
                s_count = sum(1 for r in results if r.grade == "S")
                a_count = sum(1 for r in results if r.grade == "A")
                logger.info(f"   Progress: {i}/{max_keywords} | S: {s_count}, A: {a_count}")

        return results


def main():
    """테스트 실행"""
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 70)
    print("Naver SERP Analyzer 테스트")
    print("=" * 70)

    analyzer = NaverSERPAnalyzer(delay=1.5)

    # 테스트 키워드
    test_keywords = [
        "청주 다이어트 한의원",
        "청주 교통사고 한의원",
        "청주 탈모 치료",
        "청주 한의원 추천",
        "오창 한의원"
    ]

    print(f"\n테스트 키워드: {len(test_keywords)}개")

    for kw in test_keywords:
        print(f"\n{'='*60}")
        print(f"키워드: {kw}")
        print("-" * 60)

        result = analyzer.analyze_serp(kw, detailed=False)

        if result:
            print(f"난이도: {result.difficulty}/100")
            print(f"기회 점수: {result.opportunity}/100")
            print(f"등급: {result.grade}급")
            print(f"총 검색 결과: {result.total_results:,}건")

            print(f"\n상위 5개 블로그:")
            for blog in result.blog_results[:5]:
                official = " [공식]" if blog.is_official else ""
                print(f"  {blog.rank}. {blog.title[:40]}...{official}")
                print(f"     블로그: {blog.blog_name} | {blog.publish_date}")
        else:
            print("분석 실패")

    print(f"\n{'='*70}")
    print("테스트 완료!")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Phase 3: 경쟁사 역분석기
- 경쟁사 블로그 포스트 수집
- 키워드 역추적
- 갭 키워드 분석
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import requests
import re
import time
import json
from bs4 import BeautifulSoup
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Set, Optional, Tuple
from collections import Counter
from pathlib import Path


@dataclass
class BlogPost:
    """블로그 포스트 정보"""
    title: str
    url: str
    publish_date: str
    days_since: int
    extracted_keywords: List[str]


@dataclass
class CompetitorProfile:
    """경쟁사 프로필"""
    name: str
    blog_url: str
    blog_id: str
    total_posts: int
    posts: List[BlogPost]
    top_keywords: Dict[str, int]  # keyword -> frequency
    posting_frequency: float  # posts per month
    analyzed_at: str


@dataclass
class GapKeyword:
    """갭 키워드 (경쟁사 O, 우리 X)"""
    keyword: str
    found_in: List[str]  # competitor names
    frequency: int
    priority: float


class CompetitorAnalyzer:
    """경쟁사 블로그 분석기"""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self._last_call = 0
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }

        # 청주 지역 키워드
        self.region_keywords = [
            "청주", "상당", "서원", "흥덕", "청원",
            "복대", "가경", "율량", "오창", "오송",
            "분평", "봉명", "산남", "용암", "금천"
        ]

        # 한의원 관련 키워드 (키워드 추출 시 필터링용)
        self.medical_keywords = [
            "한의원", "한방", "한약", "침", "추나", "부항",
            "다이어트", "비만", "살빼", "체중", "뱃살",
            "여드름", "피부", "아토피", "습진",
            "교통사고", "자동차사고", "후유증",
            "통증", "디스크", "허리", "목", "어깨", "무릎",
            "탈모", "두피", "원형탈모",
            "비염", "알레르기", "축농증",
            "갱년기", "폐경", "생리", "산후",
            "불면", "수면", "스트레스",
            "소화", "위장", "역류",
            "두통", "어지럼", "이명"
        ]

        # 의도 키워드
        self.intent_keywords = ["가격", "비용", "후기", "추천", "잘하는", "좋은", "유명한", "효과"]

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def _parse_date(self, date_str: str) -> Tuple[str, int]:
        """날짜 문자열 파싱 -> (날짜문자열, 경과일)"""
        now = datetime.now()

        # "X일 전" 패턴
        match = re.search(r"(\d+)일 전", date_str)
        if match:
            days = int(match.group(1))
            return date_str, days

        # "X시간 전", "X분 전"
        if "시간 전" in date_str or "분 전" in date_str:
            return date_str, 0

        # "YYYY.MM.DD" 패턴
        match = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", date_str)
        if match:
            try:
                pub_date = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                days = (now - pub_date).days
                return date_str, max(0, days)
            except Exception:
                pass

        return date_str, 180  # 기본값

    def _extract_keywords_from_title(self, title: str) -> List[str]:
        """제목에서 키워드 추출"""
        keywords = []

        # 지역 키워드 확인
        for region in self.region_keywords:
            if region in title:
                keywords.append(region)

        # 의료 키워드 확인
        for medical in self.medical_keywords:
            if medical in title:
                keywords.append(medical)

        # 의도 키워드 확인
        for intent in self.intent_keywords:
            if intent in title:
                keywords.append(intent)

        # 조합 키워드 생성 (지역 + 의료)
        regions_found = [r for r in self.region_keywords if r in title]
        medicals_found = [m for m in self.medical_keywords if m in title]

        for region in regions_found:
            for medical in medicals_found:
                keywords.append(f"{region} {medical}")

        return list(set(keywords))

    def get_blog_posts(self, blog_id: str, max_posts: int = 50) -> List[BlogPost]:
        """
        네이버 블로그에서 포스트 목록 수집

        Args:
            blog_id: 블로그 ID (blog.naver.com/{blog_id})
            max_posts: 최대 수집 포스트 수

        Returns:
            BlogPost 리스트
        """
        posts = []
        page = 1

        while len(posts) < max_posts:
            self._rate_limit()

            # 블로그 글 목록 페이지
            url = f"https://blog.naver.com/PostList.naver"
            params = {
                "blogId": blog_id,
                "currentPage": page,
                "categoryNo": 0,
                "parentCategoryNo": 0,
                "countPerPage": 30
            }

            try:
                response = requests.get(url, params=params, headers=self.headers, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')

                # 포스트 링크 찾기
                post_pattern = re.compile(rf'{blog_id}/(\d+)')
                found_any = False

                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    match = post_pattern.search(href)

                    if not match:
                        continue

                    title = link.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue

                    post_no = match.group(1)
                    post_url = f"https://blog.naver.com/{blog_id}/{post_no}"

                    # 이미 수집한 URL인지 확인
                    if any(p.url == post_url for p in posts):
                        continue

                    # 날짜 찾기
                    date_str = ""
                    days_since = 180

                    parent = link.parent
                    for _ in range(5):
                        if parent is None:
                            break
                        text = parent.get_text()
                        date_match = re.search(r'(\d{4}\.\d{1,2}\.\d{1,2})', text)
                        if date_match:
                            date_str, days_since = self._parse_date(date_match.group(1))
                            break
                        parent = parent.parent

                    # 키워드 추출
                    keywords = self._extract_keywords_from_title(title)

                    posts.append(BlogPost(
                        title=title,
                        url=post_url,
                        publish_date=date_str,
                        days_since=days_since,
                        extracted_keywords=keywords
                    ))

                    found_any = True

                    if len(posts) >= max_posts:
                        break

                # 더 이상 포스트가 없으면 종료
                if not found_any:
                    break

                page += 1

                # 안전장치: 10페이지 이상 시도하지 않음
                if page > 10:
                    break

            except Exception as e:
                print(f"블로그 포스트 수집 오류 ({blog_id}): {e}")
                break

        return posts

    def analyze_competitor(self, name: str, blog_url: str) -> Optional[CompetitorProfile]:
        """
        경쟁사 블로그 전체 분석

        Args:
            name: 경쟁사 이름
            blog_url: 블로그 URL (https://blog.naver.com/xxx)

        Returns:
            CompetitorProfile 또는 None
        """
        # blog_id 추출
        match = re.search(r'blog\.naver\.com/(\w+)', blog_url)
        if not match:
            print(f"잘못된 블로그 URL: {blog_url}")
            return None

        blog_id = match.group(1)
        print(f"\n[{name}] 블로그 분석 시작: {blog_id}")

        # 포스트 수집
        posts = self.get_blog_posts(blog_id, max_posts=50)
        print(f"   수집된 포스트: {len(posts)}개")

        if not posts:
            return None

        # 키워드 빈도 계산
        keyword_counter = Counter()
        for post in posts:
            keyword_counter.update(post.extracted_keywords)

        # 상위 30개 키워드
        top_keywords = dict(keyword_counter.most_common(30))

        # 포스팅 빈도 계산 (월평균)
        if posts:
            oldest_days = max(p.days_since for p in posts if p.days_since < 365)
            months = max(oldest_days / 30, 1)
            posting_frequency = len(posts) / months
        else:
            posting_frequency = 0

        return CompetitorProfile(
            name=name,
            blog_url=blog_url,
            blog_id=blog_id,
            total_posts=len(posts),
            posts=posts,
            top_keywords=top_keywords,
            posting_frequency=round(posting_frequency, 1),
            analyzed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    def find_gap_keywords(self,
                          competitor_profiles: List[CompetitorProfile],
                          our_keywords: Set[str]) -> List[GapKeyword]:
        """
        갭 키워드 찾기 (경쟁사는 공략하지만 우리는 없는 키워드)

        Args:
            competitor_profiles: 분석된 경쟁사 프로필 리스트
            our_keywords: 우리가 보유한 키워드 세트

        Returns:
            GapKeyword 리스트 (우선순위 순)
        """
        # 경쟁사 키워드 통합
        competitor_keywords: Dict[str, Dict] = {}  # keyword -> {competitors, frequency}

        for profile in competitor_profiles:
            for keyword, freq in profile.top_keywords.items():
                if keyword not in competitor_keywords:
                    competitor_keywords[keyword] = {
                        "competitors": [],
                        "frequency": 0
                    }
                competitor_keywords[keyword]["competitors"].append(profile.name)
                competitor_keywords[keyword]["frequency"] += freq

        # 갭 키워드 식별
        gap_keywords = []
        for keyword, data in competitor_keywords.items():
            # 우리가 보유하지 않은 키워드만
            if keyword.lower() not in {k.lower() for k in our_keywords}:
                # 최소 길이 체크 (2단어 이상 조합 키워드 우선)
                word_count = len(keyword.split())

                # 우선순위 계산
                priority = (
                    data["frequency"] * 10 +  # 빈도
                    len(data["competitors"]) * 20 +  # 여러 경쟁사가 공략
                    (word_count >= 2) * 30  # 조합 키워드 보너스
                )

                gap_keywords.append(GapKeyword(
                    keyword=keyword,
                    found_in=data["competitors"],
                    frequency=data["frequency"],
                    priority=priority
                ))

        # 우선순위 정렬
        gap_keywords.sort(key=lambda x: x.priority, reverse=True)

        return gap_keywords

    def search_competitor_ranking(self, keyword: str, competitor_blog_ids: List[str]) -> Dict[str, int]:
        """
        특정 키워드에서 경쟁사 블로그 순위 확인

        Args:
            keyword: 검색 키워드
            competitor_blog_ids: 경쟁사 블로그 ID 리스트

        Returns:
            {blog_id: 순위} (순위 없으면 0)
        """
        self._rate_limit()

        url = "https://search.naver.com/search.naver"
        params = {"where": "blog", "query": keyword}

        rankings = {bid: 0 for bid in competitor_blog_ids}

        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # 블로그 링크 순위 확인
            post_pattern = re.compile(r'blog\.naver\.com/(\w+)/\d+')
            rank = 0

            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                match = post_pattern.search(href)

                if match:
                    rank += 1
                    blog_id = match.group(1)

                    if blog_id in rankings and rankings[blog_id] == 0:
                        rankings[blog_id] = rank

                    if rank >= 10:
                        break

        except Exception as e:
            print(f"순위 검색 오류 ({keyword}): {e}")

        return rankings


def load_competitors(config_path: str = "config/competitors.json") -> List[Dict]:
    """경쟁사 설정 파일 로드"""
    path = Path(config_path)

    if not path.exists():
        # 기본 설정 생성
        default_config = {
            "competitors": [
                {
                    "name": "예시한의원",
                    "blog_url": "https://blog.naver.com/example_clinic",
                    "naver_place_id": ""
                }
            ]
        }

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)

        print(f"기본 설정 파일 생성: {config_path}")
        print("경쟁사 블로그 URL을 추가해주세요.")
        return []

    with open(path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    return config.get("competitors", [])


def main():
    """테스트 실행"""
    print("=" * 70)
    print("Phase 3: 경쟁사 역분석기 테스트")
    print("=" * 70)

    analyzer = CompetitorAnalyzer(delay=1.0)

    # 경쟁사 설정 로드
    competitors = load_competitors()

    if not competitors:
        print("\n경쟁사가 설정되지 않았습니다.")
        print("config/competitors.json 파일에 경쟁사 블로그 URL을 추가해주세요.")

        # 테스트용 가상 데이터로 진행
        print("\n[테스트 모드] 가상 데이터로 갭 분석 데모...")

        # 가상 경쟁사 키워드
        competitor_keywords = {
            "청주 다이어트": 5,
            "청주 다이어트 한의원": 3,
            "청주 교통사고 한의원": 4,
            "청주 여드름 치료": 2,
            "복대동 한의원": 3,
            "청주 비염 한의원": 2,
            "청주 갱년기 한의원": 1,
            "청주 탈모 치료": 2
        }

        # 우리 키워드 (Phase 1에서 수집한 것)
        our_keywords = {
            "청주 다이어트",
            "청주 한의원",
            "청주 교통사고"
        }

        print(f"\n경쟁사 키워드: {len(competitor_keywords)}개")
        print(f"우리 키워드: {len(our_keywords)}개")

        # 갭 분석
        gap = [k for k in competitor_keywords if k not in our_keywords]
        print(f"\n📊 갭 키워드 (경쟁사 O, 우리 X): {len(gap)}개")
        for kw in gap:
            print(f"   - {kw} (경쟁사 빈도: {competitor_keywords[kw]})")

        return

    # 실제 경쟁사 분석
    print(f"\n분석할 경쟁사: {len(competitors)}개")

    profiles = []
    for comp in competitors:
        name = comp.get("name", "Unknown")
        blog_url = comp.get("blog_url", "")

        if not blog_url or "example" in blog_url:
            continue

        profile = analyzer.analyze_competitor(name, blog_url)
        if profile:
            profiles.append(profile)

            print(f"\n   상위 키워드:")
            for kw, freq in list(profile.top_keywords.items())[:10]:
                print(f"      - {kw}: {freq}회")

    if profiles:
        # 갭 키워드 분석 (우리 키워드는 빈 세트로 테스트)
        our_keywords: Set[str] = set()  # 실제로는 DB에서 로드
        gap_keywords = analyzer.find_gap_keywords(profiles, our_keywords)

        print("\n" + "=" * 70)
        print("갭 키워드 분석 결과")
        print("=" * 70)

        print(f"\n총 갭 키워드: {len(gap_keywords)}개")
        print("\n상위 20개 갭 키워드:")
        for i, gap in enumerate(gap_keywords[:20], 1):
            competitors_str = ", ".join(gap.found_in)
            print(f"   {i:2}. {gap.keyword} (빈도: {gap.frequency}, 발견: {competitors_str})")

    print("\n" + "=" * 70)
    print("분석 완료!")


if __name__ == "__main__":
    main()

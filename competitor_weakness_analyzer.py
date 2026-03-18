"""
Competitor Weakness Analyzer

경쟁사 리뷰/콘텐츠에서 약점을 추출하고 기회 키워드를 생성합니다.
Sentinel 시스템의 확장 모듈입니다.

Features:
- 네이버 플레이스 리뷰 수집
- Gemini AI로 약점 분석
- 기회 키워드 자동 생성
- 콘텐츠 제안 생성
"""

import os
import sys
import json
import time
import random
import logging
import requests
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from bs4 import BeautifulSoup

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import ConfigManager
from db.database import DatabaseManager

# Logging setup
logger = logging.getLogger("WeaknessAnalyzer")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

# User agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


@dataclass
class WeaknessData:
    """약점 분석 결과"""
    competitor_name: str
    source: str  # review, blog, cafe
    weakness_type: str  # 서비스, 가격, 시설, 대기시간, 효과, 기타
    original_text: str
    weakness_keywords: List[str] = field(default_factory=list)
    opportunity_keywords: List[str] = field(default_factory=list)
    content_suggestion: str = ""
    sentiment_score: float = 0.0  # -1 (매우 부정) ~ 1 (매우 긍정)
    source_url: str = ""


class CompetitorWeaknessAnalyzer:
    """경쟁사 약점 분석기"""

    WEAKNESS_TYPES = {
        '서비스': ['불친절', '응대', '설명', '상담', '태도', '무성의'],
        '가격': ['비싸', '가격', '비용', '돈', '결제', '추가금'],
        '시설': ['시설', '청결', '위생', '좁', '오래된', '주차'],
        '대기시간': ['대기', '기다', '오래', '늦', '예약'],
        '효과': ['효과', '결과', '변화', '재발', '안됨', '별로'],
    }

    def __init__(self):
        self.config = ConfigManager()
        self.db = DatabaseManager()
        self.competitors = self._load_competitors()
        self._init_gemini()

    def _load_competitors(self) -> List[Dict]:
        """targets.json에서 경쟁사 정보 로드"""
        competitors = []
        try:
            targets_path = os.path.join(self.config.root_dir, 'config', 'targets.json')
            with open(targets_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for target in data.get('targets', []):
                if target.get('priority') in ['High', 'Critical', 'Medium']:
                    place_url = target.get('monitor_urls', {}).get('naver_place', '')
                    if place_url:
                        competitors.append({
                            'name': target.get('name', ''),
                            'place_url': place_url,
                            'category': target.get('category', ''),
                            'keywords': target.get('keywords', [])
                        })

            logger.info(f"Loaded {len(competitors)} competitors for weakness analysis")
            return competitors

        except Exception as e:
            logger.error(f"Failed to load competitors: {e}")
            return []

    def _init_gemini(self):
        """Gemini API 초기화"""
        try:
            from google import genai

            api_key = self.config.get_api_key()
            if api_key:
                self.client = genai.Client(
                    api_key=api_key,
                    http_options={'timeout': 30000}
                )
                self.model_name = self.config.get_model_name("flash")
                logger.info(f"Gemini initialized: {self.model_name}")
            else:
                self.client = None
                logger.warning("Gemini API key not found")
        except Exception as e:
            self.client = None
            logger.error(f"Gemini init failed: {e}")

    def _get_headers(self) -> dict:
        """랜덤 User-Agent 헤더 생성"""
        return {"User-Agent": random.choice(USER_AGENTS)}

    def _extract_place_id(self, url: str) -> Optional[str]:
        """네이버 플레이스 URL에서 ID 추출"""
        import re
        patterns = [
            r'/hospital/(\d+)',
            r'/place/(\d+)',
            r'/restaurant/(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def scrape_naver_place_reviews(self, place_url: str, limit: int = 20) -> List[Dict]:
        """
        네이버 플레이스 리뷰 스크래핑

        Returns:
            list: [{'text': str, 'rating': int, 'date': str}]
        """
        reviews = []
        place_id = self._extract_place_id(place_url)

        if not place_id:
            logger.warning(f"Could not extract place ID from: {place_url}")
            return reviews

        try:
            # 네이버 플레이스 리뷰 API 호출
            review_url = f"https://m.place.naver.com/hospital/{place_id}/review/visitor"

            response = requests.get(review_url, headers=self._get_headers(), timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # 리뷰 컨테이너 찾기 (여러 선택자 시도)
            review_selectors = [
                '.pui__vn15t2',  # 새 UI
                '.review_contents',
                '.txt_comment',
                '[class*="review"]'
            ]

            review_items = []
            for selector in review_selectors:
                review_items = soup.select(selector)
                if review_items:
                    break

            for item in review_items[:limit]:
                text = item.get_text(strip=True)
                if len(text) > 10:  # 최소 글자수 필터
                    reviews.append({
                        'text': text[:500],  # 최대 500자
                        'rating': 0,  # 별점은 별도 파싱 필요
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'url': review_url
                    })

            logger.info(f"Scraped {len(reviews)} reviews from {place_id}")

        except Exception as e:
            logger.error(f"Review scraping failed: {e}")

        return reviews

    def scrape_naver_blog_reviews(self, competitor_name: str, limit: int = 10) -> List[Dict]:
        """
        네이버 블로그에서 경쟁사 관련 부정 리뷰 검색

        Returns:
            list: [{'text': str, 'title': str, 'url': str}]
        """
        reviews = []

        try:
            # 부정적 키워드와 함께 검색
            negative_queries = [
                f"{competitor_name} 후기 별로",
                f"{competitor_name} 실망",
                f"{competitor_name} 비추",
            ]

            for query in negative_queries[:1]:  # API 부하 방지
                search_url = f"https://search.naver.com/search.naver?where=view&query={query}"

                response = requests.get(search_url, headers=self._get_headers(), timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')

                items = soup.select('.view_wrap, .total_wrap')[:limit]

                for item in items:
                    title_el = item.select_one('.title_link, .api_txt_lines')
                    desc_el = item.select_one('.dsc_link, .api_txt_lines.dsc_txt')

                    if title_el:
                        title = title_el.get_text(strip=True)
                        link = title_el.get('href', '')
                        desc = desc_el.get_text(strip=True) if desc_el else ''

                        reviews.append({
                            'text': f"{title} {desc}",
                            'title': title,
                            'url': link
                        })

                time.sleep(random.uniform(1, 2))

        except Exception as e:
            logger.error(f"Blog review scraping failed: {e}")

        return reviews

    def analyze_weakness_with_ai(self, text: str, competitor_name: str) -> Optional[WeaknessData]:
        """
        Gemini AI로 텍스트에서 약점 분석

        Returns:
            WeaknessData or None
        """
        if not self.client:
            return self._analyze_weakness_rule_based(text, competitor_name)

        prompt = f"""
        당신은 마케팅 전문가입니다. 다음 리뷰/게시글에서 경쟁사의 약점을 분석하세요.

        [경쟁사]: {competitor_name}
        [텍스트]: {text[:800]}

        분석 후 JSON으로 반환하세요:
        {{
            "is_negative": true/false,
            "weakness_type": "서비스|가격|시설|대기시간|효과|기타",
            "weakness_keywords": ["불친절", "비싸다" 등 약점 키워드 3개 이하],
            "opportunity_keywords": ["청주 친절한 한의원", "청주 가성비 한의원" 등 우리가 공략할 수 있는 키워드 3개],
            "content_suggestion": "이 약점을 공략하는 블로그 콘텐츠 제목 1개",
            "sentiment_score": -1.0 ~ 1.0 (부정~긍정)
        }}

        부정적 내용이 아니면 is_negative: false로 반환하세요.
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )

            result = json.loads(response.text)

            if not result.get('is_negative', False):
                return None

            return WeaknessData(
                competitor_name=competitor_name,
                source='review',
                weakness_type=result.get('weakness_type', '기타'),
                original_text=text[:500],
                weakness_keywords=result.get('weakness_keywords', []),
                opportunity_keywords=result.get('opportunity_keywords', []),
                content_suggestion=result.get('content_suggestion', ''),
                sentiment_score=result.get('sentiment_score', 0)
            )

        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return self._analyze_weakness_rule_based(text, competitor_name)

    def _analyze_weakness_rule_based(self, text: str, competitor_name: str) -> Optional[WeaknessData]:
        """규칙 기반 약점 분석 (AI 폴백)"""
        text_lower = text.lower()

        # 부정적 키워드 체크
        negative_keywords = ['별로', '실망', '비추', '안좋', '불친절', '비싸', '오래걸']
        is_negative = any(kw in text_lower for kw in negative_keywords)

        if not is_negative:
            return None

        # 약점 유형 분류
        weakness_type = '기타'
        for wtype, keywords in self.WEAKNESS_TYPES.items():
            if any(kw in text_lower for kw in keywords):
                weakness_type = wtype
                break

        # 기회 키워드 생성
        opportunity_map = {
            '서비스': ['청주 친절한 한의원', '청주 상담 잘해주는 한의원'],
            '가격': ['청주 가성비 한의원', '청주 합리적 한의원'],
            '대기시간': ['청주 예약제 한의원', '청주 대기없는 한의원'],
            '효과': ['청주 효과좋은 한의원', '청주 결과 보장 한의원'],
            '시설': ['청주 깨끗한 한의원', '청주 최신시설 한의원'],
        }

        return WeaknessData(
            competitor_name=competitor_name,
            source='review',
            weakness_type=weakness_type,
            original_text=text[:500],
            weakness_keywords=[kw for kw in negative_keywords if kw in text_lower][:3],
            opportunity_keywords=opportunity_map.get(weakness_type, ['청주 한의원 추천']),
            content_suggestion=f"'{competitor_name}' 보다 나은 선택, 규림한의원",
            sentiment_score=-0.5
        )

    def run(self, review_limit: int = 20):
        """
        전체 경쟁사 약점 분석 실행

        Args:
            review_limit: 경쟁사당 수집할 리뷰 수
        """
        print(f"\n{'='*60}")
        print(f"🔍 경쟁사 약점 분석 시작")
        print(f"{'='*60}")
        print(f"   경쟁사 수: {len(self.competitors)}")
        print(f"   리뷰 제한: {review_limit}/경쟁사")
        print(f"   AI 모드: {'Gemini' if self.client else 'Rule-based'}")
        print(f"{'='*60}\n")

        total_weaknesses = 0
        total_opportunities = 0

        for comp in self.competitors:
            name = comp['name']
            place_url = comp.get('place_url', '')

            print(f"\n📊 분석 중: {name}")
            print(f"   {'─'*40}")

            weaknesses_found = []

            # 1. 네이버 플레이스 리뷰 수집
            if place_url:
                reviews = self.scrape_naver_place_reviews(place_url, limit=review_limit)
                print(f"   📝 플레이스 리뷰: {len(reviews)}개 수집")

                for review in reviews:
                    weakness = self.analyze_weakness_with_ai(review['text'], name)
                    if weakness:
                        weakness.source_url = review.get('url', '')
                        weaknesses_found.append(weakness)

            # 2. 블로그 리뷰 수집
            blog_reviews = self.scrape_naver_blog_reviews(name, limit=5)
            print(f"   📰 블로그 리뷰: {len(blog_reviews)}개 수집")

            for review in blog_reviews:
                weakness = self.analyze_weakness_with_ai(review['text'], name)
                if weakness:
                    weakness.source = 'blog'
                    weakness.source_url = review.get('url', '')
                    weaknesses_found.append(weakness)

            # 3. DB 저장
            for w in weaknesses_found:
                self.db.insert_competitor_weakness({
                    'competitor_name': w.competitor_name,
                    'source': w.source,
                    'weakness_type': w.weakness_type,
                    'original_text': w.original_text,
                    'weakness_keywords': w.weakness_keywords,
                    'opportunity_keywords': w.opportunity_keywords,
                    'sentiment_score': w.sentiment_score,
                    'source_url': w.source_url,
                    'content_suggestion': w.content_suggestion
                })

            total_weaknesses += len(weaknesses_found)
            total_opportunities += sum(len(w.opportunity_keywords) for w in weaknesses_found)

            # 결과 요약
            if weaknesses_found:
                print(f"   ⚠️ 약점 발견: {len(weaknesses_found)}개")
                for w in weaknesses_found[:3]:
                    print(f"      [{w.weakness_type}] {w.weakness_keywords[:2]}")
            else:
                print(f"   ✅ 약점 미발견")

            time.sleep(random.uniform(2, 4))

        # 최종 리포트
        self._print_summary_report()

        print(f"\n{'='*60}")
        print(f"✅ 분석 완료")
        print(f"   총 약점: {total_weaknesses}개")
        print(f"   기회 키워드: {total_opportunities}개")
        print(f"{'='*60}\n")

        return total_weaknesses

    def _print_summary_report(self):
        """분석 요약 리포트 출력"""
        summary = self.db.get_weakness_summary()

        print(f"\n{'='*60}")
        print(f"📊 경쟁사 약점 요약 리포트")
        print(f"{'='*60}")

        # 경쟁사별 약점
        print(f"\n🏢 경쟁사별 약점 현황")
        for name, data in summary.get('by_competitor', {}).items():
            print(f"   {name}: {data['count']}건")
            for wtype, cnt in data.get('weaknesses', {}).items():
                print(f"      - {wtype}: {cnt}건")

        # 약점 유형별 통계
        print(f"\n📈 약점 유형별 통계")
        for wtype, cnt in sorted(summary.get('by_type', {}).items(), key=lambda x: x[1], reverse=True):
            bar = '█' * min(cnt, 20)
            print(f"   {wtype}: {bar} {cnt}건")

        # 기회 키워드
        print(f"\n🎯 기회 키워드 TOP 10")
        for i, opp in enumerate(summary.get('top_opportunity_keywords', [])[:10], 1):
            print(f"   {i}. [{opp['type']}] {opp['keyword']}")
            print(f"      → 경쟁사: {opp['competitor']}")

    def get_content_suggestions(self, limit: int = 10) -> List[Dict]:
        """
        기회 키워드 기반 콘텐츠 제안

        Returns:
            list: [{'keyword', 'title_suggestion', 'competitor', 'weakness'}]
        """
        opportunities = self.db.get_opportunity_keywords(status='pending', limit=limit)

        suggestions = []
        for opp in opportunities:
            suggestions.append({
                'keyword': opp['keyword'],
                'title': opp.get('suggestion', f"'{opp['keyword']}' 최고의 선택"),
                'competitor': opp['competitor'],
                'weakness_type': opp['weakness_type'],
                'priority': opp['priority']
            })

        return suggestions


def main():
    import argparse

    parser = argparse.ArgumentParser(description="경쟁사 약점 분석기")
    parser.add_argument('--limit', type=int, default=20,
                        help='경쟁사당 수집할 리뷰 수')
    parser.add_argument('--report', action='store_true',
                        help='기존 데이터로 리포트만 출력')
    parser.add_argument('--suggestions', action='store_true',
                        help='콘텐츠 제안 출력')

    args = parser.parse_args()

    analyzer = CompetitorWeaknessAnalyzer()

    if args.report:
        analyzer._print_summary_report()
    elif args.suggestions:
        suggestions = analyzer.get_content_suggestions(limit=10)
        print(f"\n🎯 콘텐츠 제안 TOP 10")
        print(f"{'='*60}")
        for i, s in enumerate(suggestions, 1):
            print(f"\n{i}. 키워드: {s['keyword']}")
            print(f"   제목: {s['title']}")
            print(f"   약점 공략: {s['competitor']} - {s['weakness_type']}")
    else:
        analyzer.run(review_limit=args.limit)


if __name__ == "__main__":
    main()

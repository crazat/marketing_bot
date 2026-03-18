#!/usr/bin/env python3
"""
경쟁사 블로그 콘텐츠 갭 분석
- 경쟁사가 다루는 주제 vs 안 다루는 주제 파악
- 블루오션 키워드 발굴
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import requests
import re
import time
import random
import json
from bs4 import BeautifulSoup
from collections import Counter, defaultdict
from typing import List, Dict, Set
from datetime import datetime
from pathlib import Path


class BlogGapAnalyzer:
    """경쟁사 블로그 콘텐츠 갭 분석"""

    def __init__(self, region: str = "청주"):
        self.region = region
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # Naver API 키 로드
        self.api_keys = self._load_api_keys()
        self.current_key_index = 0

        # 분석할 주제 카테고리
        self.topic_categories = {
            "다이어트": ["다이어트", "살빼기", "체중감량", "한약다이어트", "비만", "뱃살", "하체비만"],
            "교통사고": ["교통사고", "자동차사고", "추돌", "자보", "교통사고치료", "입원"],
            "피부/여드름": ["여드름", "피부", "흉터", "새살침", "아토피", "지루성"],
            "탈모": ["탈모", "두피", "원형탈모", "탈모치료", "모발"],
            "통증/체형": ["허리", "목", "어깨", "디스크", "체형", "골반", "척추", "거북목"],
            "산후/여성": ["산후", "출산", "산후조리", "난임", "생리", "갱년기", "골반교정"],
            "안면/미용": ["안면비대칭", "턱", "얼굴", "주름", "리프팅"],
            "내과/면역": ["면역", "보약", "감기", "소화", "위장", "알레르기"],
            "정신/수면": ["불면", "스트레스", "우울", "불안", "자율신경"],
            "기타치료": ["침", "뜸", "부항", "추나", "한방"],
        }

    def _load_api_keys(self) -> List[Dict]:
        """네이버 검색 API 키 로드"""
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except Exception:
            pass

        keys = []
        for i in range(1, 6):
            client_id = os.environ.get(f'NAVER_SEARCH_CLIENT_ID_{i}')
            client_secret = os.environ.get(f'NAVER_SEARCH_SECRET_{i}')

            if client_id and client_secret:
                keys.append({
                    'client_id': client_id,
                    'client_secret': client_secret
                })

        return keys

    def _get_next_key(self) -> Dict:
        """다음 API 키 가져오기"""
        if not self.api_keys:
            return None
        key = self.api_keys[self.current_key_index]
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        return key

    def load_competitors(self) -> List[Dict]:
        """경쟁사 정보 로드"""
        possible_paths = [
            Path("config/competitors.json"),
            Path("../config/competitors.json"),
            Path("/mnt/c/Projects/marketing_bot/config/competitors.json"),
        ]

        competitors = []

        for competitors_path in possible_paths:
            if competitors_path.exists():
                try:
                    with open(competitors_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    category_competitors = data.get("category_competitors", {})
                    for category, info in category_competitors.items():
                        main_comps = info.get("main_competitors", [])
                        for comp in main_comps:
                            if comp.get("name") and comp not in competitors:
                                comp["category"] = category
                                competitors.append(comp)

                    if competitors:
                        print(f"   📁 경쟁사 설정 로드: {competitors_path}")
                        return competitors
                except Exception as e:
                    print(f"   ⚠️ 경쟁사 파일 로드 오류: {e}")
                    continue

        print("   ⚠️ 경쟁사 설정 파일 없음 - 기본값 사용")
        return [
            {"name": "자연과한의원 청주점", "blog_url": "", "category": "다이어트"},
            {"name": "하늘체한의원 청주점", "blog_url": "", "category": "여드름"},
        ]

    def search_blog_api(self, query: str, display: int = 30) -> List[Dict]:
        """네이버 블로그 API 검색 (우선 사용)"""
        posts = []
        key = self._get_next_key()

        if not key:
            return posts

        try:
            url = "https://openapi.naver.com/v1/search/blog.json"
            headers = {
                "X-Naver-Client-Id": key['client_id'],
                "X-Naver-Client-Secret": key['client_secret']
            }
            params = {
                'query': query,
                'display': display,
                'sort': 'sim'
            }

            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for item in data.get('items', []):
                    title = re.sub(r'<[^>]+>', '', item.get('title', ''))
                    description = re.sub(r'<[^>]+>', '', item.get('description', ''))

                    posts.append({
                        'title': title,
                        'content': description[:300],
                        'link': item.get('link', ''),
                        'blogger': item.get('bloggername', ''),
                        'query': query
                    })

            time.sleep(0.2)

        except Exception as e:
            print(f"   [블로그 API] {query} 오류: {e}")

        return posts

    def search_blog_posts(self, query: str, count: int = 30) -> List[Dict]:
        """네이버 블로그 검색 (API 우선)"""
        posts = self.search_blog_api(query, display=count)

        if posts:
            return posts

        # API 실패시 웹 스크래핑
        try:
            url = "https://search.naver.com/search.naver"
            params = {
                'where': 'blog',
                'query': query,
                'sm': 'tab_opt',
                'nso': 'so:r,p:1m'
            }

            response = self.session.get(url, params=params, timeout=10)
            if response.status_code != 200:
                return posts

            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.select('li.bx')

            for item in items[:count]:
                title_elem = item.select_one('a.title_link')
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                link = title_elem.get('href', '')
                blogger_elem = item.select_one('a.name')
                blogger = blogger_elem.get_text(strip=True) if blogger_elem else ''
                content_elem = item.select_one('div.dsc_txt')
                content = content_elem.get_text(strip=True) if content_elem else ''

                posts.append({
                    'title': title,
                    'content': content[:300],
                    'link': link,
                    'blogger': blogger,
                    'query': query
                })

            time.sleep(random.uniform(0.5, 1.0))

        except Exception as e:
            print(f"   검색 오류 ({query}): {e}")

        return posts

    def analyze_competitor_topics(self, competitor_name: str) -> Dict[str, int]:
        """특정 경쟁사가 다루는 주제 분석"""
        topic_counts = defaultdict(int)

        query = f"{competitor_name} 블로그"
        posts = self.search_blog_posts(query, count=50)

        for post in posts:
            text = f"{post['title']} {post['content']}".lower()

            for category, keywords in self.topic_categories.items():
                for kw in keywords:
                    if kw in text:
                        topic_counts[category] += 1
                        break

        return dict(topic_counts)

    def analyze_market_topics(self) -> Dict[str, int]:
        """전체 시장에서 다뤄지는 주제 분석"""
        topic_counts = defaultdict(int)

        queries = [
            f"{self.region} 한의원",
            f"{self.region} 한방병원",
            f"{self.region} 한의원 추천",
        ]

        for query in queries:
            posts = self.search_blog_posts(query, count=30)

            for post in posts:
                text = f"{post['title']} {post['content']}".lower()

                for category, keywords in self.topic_categories.items():
                    for kw in keywords:
                        if kw in text:
                            topic_counts[category] += 1
                            break

        return dict(topic_counts)

    def find_content_gaps(self, competitor_topics: Dict[str, Dict], market_topics: Dict) -> List[Dict]:
        """콘텐츠 갭 발견"""
        gaps = []

        all_competitor_topics = defaultdict(int)
        for comp_name, topics in competitor_topics.items():
            for topic, count in topics.items():
                all_competitor_topics[topic] += count

        for topic, market_count in market_topics.items():
            competitor_count = all_competitor_topics.get(topic, 0)

            if market_count > 5 and competitor_count < 3:
                gap_score = market_count - competitor_count
                gaps.append({
                    'topic': topic,
                    'market_mentions': market_count,
                    'competitor_mentions': competitor_count,
                    'gap_score': gap_score,
                    'keywords': self.topic_categories.get(topic, [])
                })

        gaps.sort(key=lambda x: x['gap_score'], reverse=True)

        return gaps

    def generate_gap_keywords(self, gaps: List[Dict]) -> List[str]:
        """갭에서 키워드 생성"""
        keywords = set()

        for gap in gaps:
            topic_keywords = gap.get('keywords', [])

            for kw in topic_keywords:
                keywords.add(f"{self.region} {kw}")
                keywords.add(f"{self.region} {kw} 한의원")
                keywords.add(f"{self.region} {kw} 치료")

                for intent in ["추천", "가격", "후기", "효과"]:
                    keywords.add(f"{self.region} {kw} {intent}")

        return list(keywords)

    def run(self) -> Dict:
        """전체 분석 실행"""
        print("=" * 60)
        print("🔍 경쟁사 블로그 콘텐츠 갭 분석")
        print("=" * 60)
        print()

        print(f"🔑 API 키: {len(self.api_keys)}개 로드됨")

        competitors = self.load_competitors()
        print(f"📋 분석 대상 경쟁사: {len(competitors)}개")

        competitor_topics = {}
        for comp in competitors:
            name = comp.get('name', '')
            if not name or 'example' in name.lower():
                continue

            print(f"\n   분석 중: {name}")
            topics = self.analyze_competitor_topics(name)
            competitor_topics[name] = topics

            if topics:
                top_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:5]
                print(f"      주력 주제: {', '.join([t[0] for t in top_topics])}")

        print(f"\n📊 시장 전체 주제 분석...")
        market_topics = self.analyze_market_topics()

        print("\n시장 주요 주제:")
        for topic, count in sorted(market_topics.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"   {topic}: {count}회")

        print("\n🎯 콘텐츠 갭 분석...")
        gaps = self.find_content_gaps(competitor_topics, market_topics)

        print("\n💎 발견된 블루오션 (경쟁사 미타겟):")
        for gap in gaps[:10]:
            print(f"   {gap['topic']}: 시장 {gap['market_mentions']}회 vs 경쟁사 {gap['competitor_mentions']}회")

        gap_keywords = self.generate_gap_keywords(gaps)

        print(f"\n🔑 갭 키워드 생성: {len(gap_keywords)}개")

        return {
            'competitor_topics': competitor_topics,
            'market_topics': market_topics,
            'gaps': gaps,
            'gap_keywords': gap_keywords,
            'timestamp': datetime.now().isoformat()
        }


def main():
    analyzer = BlogGapAnalyzer(region="청주")
    results = analyzer.run()

    output_path = "keyword_discovery/blog_gap_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print()
    print(f"💾 결과 저장: {output_path}")

    return results


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
네이버 지식인/카페 실제 질문 크롤링
- 실제 고객이 묻는 질문에서 키워드 추출
- 검색량 API에 안 잡히는 롱테일 발굴
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import requests
import re
import time
import random
from bs4 import BeautifulSoup
from collections import Counter
from typing import List, Dict, Set
from datetime import datetime


class KinCrawler:
    """네이버 지식인/카페 질문 크롤러"""

    def __init__(self, region: str = "청주"):
        self.region = region
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # Naver API 키 로드
        self.api_keys = self._load_api_keys()
        self.current_key_index = 0

        # 수집할 시드 키워드
        self.seed_keywords = [
            f"{region} 한의원",
            f"{region} 다이어트",
            f"{region} 교통사고",
            f"{region} 여드름",
            f"{region} 탈모",
            f"{region} 허리",
            f"{region} 목디스크",
            f"{region} 산후조리",
            f"{region} 한약",
            f"{region} 침",
        ]

        # 질문 패턴 (실제 고객 니즈)
        self.question_patterns = [
            r'어디.*(좋|추천|괜찮)',
            r'(가격|비용|얼마)',
            r'(효과|후기|경험)',
            r'(보험|자보|실비)',
            r'어떻게',
            r'(가야|가도|가면)',
            r'(되나요|될까요|할까요)',
            r'(좋을까요|나을까요)',
            r'(아시는분|해보신분|다녀보신)',
        ]

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

    def search_kin_api(self, query: str, display: int = 30) -> List[Dict]:
        """네이버 지식인 API 검색 (우선 사용)"""
        results = []
        key = self._get_next_key()

        if not key:
            return results

        try:
            url = "https://openapi.naver.com/v1/search/kin.json"
            headers = {
                "X-Naver-Client-Id": key['client_id'],
                "X-Naver-Client-Secret": key['client_secret']
            }
            params = {
                'query': query,
                'display': display,
                'sort': 'sim'  # 정확도순
            }

            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for item in data.get('items', []):
                    # HTML 태그 제거
                    title = re.sub(r'<[^>]+>', '', item.get('title', ''))
                    description = re.sub(r'<[^>]+>', '', item.get('description', ''))

                    results.append({
                        'title': title,
                        'content': description[:200],
                        'link': item.get('link', ''),
                        'source': 'kin_api',
                        'query': query
                    })

            time.sleep(0.2)  # API 속도 제한

        except Exception as e:
            print(f"   [지식인 API] {query} 오류: {e}")

        return results

    def search_kin(self, query: str, pages: int = 3) -> List[Dict]:
        """네이버 지식인 검색 (API 우선, fallback으로 웹 스크래핑)"""
        # API 먼저 시도
        results = self.search_kin_api(query, display=30)

        if results:
            return results

        # API 실패시 웹 스크래핑
        print(f"   [지식인] API 실패, 웹 스크래핑 시도...")

        for page in range(1, pages + 1):
            try:
                url = f"https://kin.naver.com/search/list.naver"
                params = {
                    'query': query,
                    'page': page,
                    'sort': 0
                }

                response = self.session.get(url, params=params, timeout=10)
                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')
                items = soup.select('ul.basic1 > li')

                for item in items:
                    title_elem = item.select_one('dt > a')
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    link = title_elem.get('href', '')
                    content_elem = item.select_one('dd')
                    content = content_elem.get_text(strip=True) if content_elem else ''

                    results.append({
                        'title': title,
                        'content': content[:200],
                        'link': link,
                        'source': 'kin',
                        'query': query
                    })

                time.sleep(random.uniform(0.5, 1.5))

            except Exception as e:
                print(f"   [지식인] {query} 페이지 {page} 오류: {e}")
                continue

        return results

    def search_cafe(self, query: str, pages: int = 2) -> List[Dict]:
        """네이버 카페 검색"""
        results = []

        for page in range(1, pages + 1):
            try:
                url = "https://search.naver.com/search.naver"
                params = {
                    'where': 'article',
                    'query': query,
                    'start': (page - 1) * 10 + 1
                }

                response = self.session.get(url, params=params, timeout=10)
                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')
                items = soup.select('li.bx')

                for item in items:
                    title_elem = item.select_one('a.title_link')
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    link = title_elem.get('href', '')
                    content_elem = item.select_one('div.dsc_txt')
                    content = content_elem.get_text(strip=True) if content_elem else ''

                    results.append({
                        'title': title,
                        'content': content[:200],
                        'link': link,
                        'source': 'cafe',
                        'query': query
                    })

                time.sleep(random.uniform(0.5, 1.5))

            except Exception as e:
                print(f"   [카페] {query} 페이지 {page} 오류: {e}")
                continue

        return results

    def extract_keywords_from_questions(self, questions: List[Dict]) -> List[Dict]:
        """질문에서 키워드/니즈 추출"""
        keyword_freq = Counter()
        question_keywords = []

        meaningful_patterns = [
            r'(허리|목|어깨|무릎|골반|척추|디스크|통증|두통|편두통)',
            r'(다이어트|살|체중|비만|뱃살)',
            r'(여드름|피부|흉터|탈모|두피)',
            r'(교통사고|자동차사고|추돌|접촉사고)',
            r'(산후|출산|임신|불임|난임|생리)',
            r'(불면|수면|피로|스트레스)',
            r'(가격|비용|얼마|저렴|싼)',
            r'(추천|좋은|잘하는|유명한)',
            r'(후기|경험|효과|결과)',
            r'(보험|자보|실비|의료비)',
            r'(예약|상담|진료|치료)',
            r'(어디|어떻게|언제|얼마나)',
        ]

        for q in questions:
            text = f"{q['title']} {q['content']}"
            extracted = []

            for pattern in meaningful_patterns:
                matches = re.findall(pattern, text)
                extracted.extend(matches)

            is_real_question = any(re.search(p, text) for p in self.question_patterns)

            if extracted:
                keyword_freq.update(extracted)
                question_keywords.append({
                    'title': q['title'],
                    'keywords': list(set(extracted)),
                    'is_question': is_real_question,
                    'source': q['source']
                })

        return question_keywords, keyword_freq

    def generate_longtail_keywords(self, keyword_freq: Counter) -> List[str]:
        """빈도 높은 키워드로 롱테일 생성"""
        longtails = set()
        top_keywords = [kw for kw, _ in keyword_freq.most_common(20)]

        intent_suffixes = ["추천", "가격", "비용", "후기", "효과", "병원", "한의원", "치료"]

        for kw in top_keywords:
            for suffix in intent_suffixes:
                longtails.add(f"{self.region} {kw} {suffix}")

            longtails.add(f"{self.region} {kw} 어디가 좋아요")
            longtails.add(f"{self.region} {kw} 추천해주세요")
            longtails.add(f"{self.region} {kw} 잘하는곳")

        return list(longtails)

    def run(self) -> Dict:
        """전체 크롤링 실행"""
        print("=" * 60)
        print("🔍 네이버 지식인/카페 실제 질문 크롤링")
        print("=" * 60)
        print()

        all_questions = []

        print(f"🔑 API 키: {len(self.api_keys)}개 로드됨")

        for seed in self.seed_keywords:
            print(f"   검색 중: {seed}")

            kin_results = self.search_kin(seed, pages=2)
            all_questions.extend(kin_results)
            print(f"      지식인: {len(kin_results)}개")

            cafe_results = self.search_cafe(seed, pages=2)
            all_questions.extend(cafe_results)
            print(f"      카페: {len(cafe_results)}개")

        print()
        print(f"📊 총 수집: {len(all_questions)}개 질문/글")

        question_keywords, keyword_freq = self.extract_keywords_from_questions(all_questions)

        print()
        print("📈 자주 언급되는 키워드:")
        for kw, count in keyword_freq.most_common(15):
            print(f"   {kw}: {count}회")

        longtails = self.generate_longtail_keywords(keyword_freq)

        print()
        print(f"🎯 생성된 롱테일 키워드: {len(longtails)}개")

        real_questions = [q for q in question_keywords if q.get('is_question')]

        print()
        print("💬 실제 질문 샘플 (Top 10):")
        for q in real_questions[:10]:
            print(f"   - {q['title'][:50]}...")

        return {
            'questions': all_questions,
            'keyword_freq': dict(keyword_freq),
            'longtail_keywords': longtails,
            'real_questions': real_questions,
            'timestamp': datetime.now().isoformat()
        }


def main():
    crawler = KinCrawler(region="청주")
    results = crawler.run()

    import json
    output_path = "keyword_discovery/kin_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print()
    print(f"💾 결과 저장: {output_path}")

    return results


if __name__ == "__main__":
    main()

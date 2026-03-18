#!/usr/bin/env python3
"""
질문형 롱테일 키워드 발굴
- PAA(People Also Ask) 스타일 질문 키워드
- 블로그 제목으로 바로 사용 가능한 키워드
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import requests
import re
import time
import random
import json
from bs4 import BeautifulSoup
from typing import List, Dict, Set
from datetime import datetime
from collections import defaultdict


class QuestionFinder:
    """질문형 롱테일 키워드 발굴"""

    def __init__(self, region: str = "청주"):
        self.region = region
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # 질문 시드 템플릿
        self.question_templates = [
            "{region} {topic} 어디가 좋아요",
            "{region} {topic} 추천해주세요",
            "{region} {topic} 어디서",
            "{region} {topic} 어떻게",
            "{region} {topic} 얼마나",
            "{region} {topic} 언제",
            "{region} {topic} 왜",
            "{topic} {region}에서 하면",
            "{region} {topic} 가능한가요",
            "{region} {topic} 되나요",
        ]

        # 주제 카테고리
        self.topics = {
            "치료": [
                "다이어트", "교통사고 치료", "여드름 치료", "탈모 치료",
                "허리 치료", "목디스크", "안면비대칭 교정", "산후조리"
            ],
            "시술": [
                "침", "뜸", "부항", "추나", "한약", "새살침", "약침"
            ],
            "상담": [
                "한의원 상담", "진료 예약", "비용 상담", "보험 적용"
            ],
            "효과": [
                "다이어트 한약 효과", "침 효과", "추나 효과", "한약 부작용"
            ],
        }

        # 의문사 패턴
        self.question_words = [
            "어디", "어떻게", "얼마", "언제", "왜", "뭐가", "누가",
            "좋아요", "될까요", "할까요", "가요", "되나요", "하나요"
        ]

    def get_autocomplete_questions(self, query: str) -> List[str]:
        """네이버 자동완성에서 질문형 키워드 추출"""
        questions = []

        try:
            # 네이버 자동완성 API
            url = "https://ac.search.naver.com/nx/ac"
            params = {
                'q': query,
                'con': 1,
                'frm': 'nv',
                'ans': 2,
                'r_format': 'json',
                'r_enc': 'UTF-8',
                'r_unicode': 0,
                't_koreng': 1,
            }

            response = self.session.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [[]])[0]

                for item in items:
                    if isinstance(item, list) and len(item) > 0:
                        suggestion = item[0]
                        # 질문형 패턴 확인
                        if any(qw in suggestion for qw in self.question_words):
                            questions.append(suggestion)

            time.sleep(random.uniform(0.2, 0.5))

        except Exception as e:
            pass

        return questions

    def generate_question_keywords(self) -> List[Dict]:
        """질문형 키워드 생성"""
        all_questions = []
        seen = set()

        for category, topics in self.topics.items():
            for topic in topics:
                # 템플릿 기반 생성
                for template in self.question_templates:
                    question = template.format(region=self.region, topic=topic)

                    if question not in seen:
                        seen.add(question)
                        all_questions.append({
                            'keyword': question,
                            'category': category,
                            'topic': topic,
                            'source': 'template'
                        })

                # 자동완성에서 추가 수집
                seed_queries = [
                    f"{self.region} {topic}",
                    f"{self.region} {topic} 어디",
                    f"{self.region} {topic} 어떻게",
                ]

                for seed in seed_queries:
                    ac_questions = self.get_autocomplete_questions(seed)
                    for q in ac_questions:
                        if q not in seen:
                            seen.add(q)
                            all_questions.append({
                                'keyword': q,
                                'category': category,
                                'topic': topic,
                                'source': 'autocomplete'
                            })

        return all_questions

    def search_paa_style(self, query: str) -> List[str]:
        """네이버 검색에서 PAA 스타일 질문 추출"""
        questions = []

        try:
            url = "https://search.naver.com/search.naver"
            params = {'where': 'nexearch', 'query': query}

            response = self.session.get(url, params=params, timeout=10)
            if response.status_code != 200:
                return questions

            soup = BeautifulSoup(response.text, 'html.parser')

            # "사람들이 많이 본 질문" 또는 유사 섹션
            # 연관 검색어에서 질문형 추출
            related_keywords = soup.select('span.keyword, a.keyword')

            for elem in related_keywords:
                text = elem.get_text(strip=True)
                if any(qw in text for qw in self.question_words):
                    questions.append(text)

            # 지식인 스니펫에서 질문 추출
            kin_titles = soup.select('a.title_link')
            for title in kin_titles[:5]:
                text = title.get_text(strip=True)
                if any(qw in text for qw in self.question_words):
                    questions.append(text)

            time.sleep(random.uniform(0.5, 1.0))

        except Exception as e:
            pass

        return questions

    def categorize_by_intent(self, questions: List[Dict]) -> Dict[str, List]:
        """의도별 분류"""
        categorized = defaultdict(list)

        intent_patterns = {
            "위치/탐색": ["어디", "어디서", "위치", "찾"],
            "방법": ["어떻게", "방법", "하려면", "해야"],
            "비용": ["얼마", "가격", "비용", "저렴"],
            "시간": ["언제", "기간", "오래"],
            "추천": ["추천", "좋은", "잘하는", "유명"],
            "효과": ["효과", "좋아요", "될까", "나을까"],
            "가능여부": ["되나요", "가능", "할수있"],
        }

        for q in questions:
            keyword = q['keyword']
            matched = False

            for intent, patterns in intent_patterns.items():
                if any(p in keyword for p in patterns):
                    categorized[intent].append(q)
                    matched = True
                    break

            if not matched:
                categorized["기타"].append(q)

        return dict(categorized)

    def score_questions(self, questions: List[Dict]) -> List[Dict]:
        """질문 키워드 점수 계산"""
        scored = []

        for q in questions:
            keyword = q['keyword']
            score = 50  # 기본 점수

            # 자동완성 출처 보너스
            if q.get('source') == 'autocomplete':
                score += 20

            # 의도 명확성 보너스
            if any(w in keyword for w in ["추천", "좋아요", "잘하는"]):
                score += 15  # 전환 의도 높음

            if any(w in keyword for w in ["가격", "비용", "얼마"]):
                score += 10  # 구매 의도

            # 지역 포함 보너스
            if self.region in keyword:
                score += 10

            # 길이 패널티/보너스
            word_count = len(keyword.split())
            if 3 <= word_count <= 6:
                score += 5  # 적정 길이
            elif word_count > 8:
                score -= 10  # 너무 긴 키워드

            q['score'] = score
            scored.append(q)

        # 점수순 정렬
        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored

    def generate_blog_titles(self, questions: List[Dict]) -> List[str]:
        """블로그 제목 생성"""
        titles = []

        title_templates = [
            "{keyword}? 한의사가 알려드립니다",
            "{keyword} - 전문가 답변",
            "[{region}] {topic} 완벽 가이드",
            "{keyword} 총정리",
            "많이 묻는 질문: {keyword}",
        ]

        for q in questions[:20]:
            keyword = q['keyword']
            topic = q.get('topic', '')

            # 질문형은 그대로 제목으로 사용 가능
            if keyword.endswith("요") or keyword.endswith("까요"):
                titles.append(f"{keyword}? 답변드립니다")
            else:
                titles.append(f"{keyword} 알아보기")

        return titles

    def run(self) -> Dict:
        """전체 실행"""
        print("=" * 60)
        print("❓ 질문형 롱테일 키워드 발굴")
        print("=" * 60)
        print()

        # 질문 키워드 생성
        print("🔍 질문형 키워드 수집 중...")
        questions = self.generate_question_keywords()
        print(f"   템플릿 + 자동완성: {len(questions)}개")

        # PAA 스타일 추가 수집
        print("🔍 PAA 스타일 질문 수집 중...")
        paa_queries = [
            f"{self.region} 한의원",
            f"{self.region} 다이어트",
            f"{self.region} 교통사고",
        ]

        for query in paa_queries:
            paa_questions = self.search_paa_style(query)
            for pq in paa_questions:
                questions.append({
                    'keyword': pq,
                    'category': '기타',
                    'topic': query,
                    'source': 'paa'
                })

        # 중복 제거
        seen = set()
        unique_questions = []
        for q in questions:
            if q['keyword'] not in seen:
                seen.add(q['keyword'])
                unique_questions.append(q)

        print(f"   총 수집 (중복 제거): {len(unique_questions)}개")

        # 점수 계산
        scored_questions = self.score_questions(unique_questions)

        # 의도별 분류
        categorized = self.categorize_by_intent(scored_questions)

        print("\n📊 의도별 분류:")
        for intent, items in categorized.items():
            print(f"   {intent}: {len(items)}개")

        # 상위 키워드
        print("\n🎯 상위 질문형 키워드 (Top 20):")
        for q in scored_questions[:20]:
            print(f"   [{q['score']}] {q['keyword']}")

        # 블로그 제목 생성
        blog_titles = self.generate_blog_titles(scored_questions)

        print("\n📝 블로그 제목 제안:")
        for title in blog_titles[:10]:
            print(f"   - {title}")

        return {
            'questions': scored_questions,
            'categorized': categorized,
            'blog_titles': blog_titles,
            'total_count': len(scored_questions),
            'timestamp': datetime.now().isoformat()
        }


def main():
    finder = QuestionFinder(region="청주")
    results = finder.run()

    # 결과 저장
    output_path = "keyword_discovery/question_keywords_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print()
    print(f"💾 결과 저장: {output_path}")

    return results


if __name__ == "__main__":
    main()

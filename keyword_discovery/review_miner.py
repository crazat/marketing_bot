#!/usr/bin/env python3
"""
네이버 플레이스 리뷰 텍스트 마이닝
- 실제 환자들이 사용하는 언어/키워드 추출
- 고객 니즈 및 고민 파악
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import sqlite3
import re
import json
from collections import Counter, defaultdict
from typing import List, Dict, Tuple
from datetime import datetime
from pathlib import Path


class ReviewMiner:
    """리뷰 텍스트 마이닝"""

    def __init__(self, db_path: str = "db/marketing_data.db"):
        self.db_path = db_path

        # 증상/니즈 키워드 패턴
        self.symptom_patterns = {
            "통증": [r"(허리|목|어깨|무릎|골반|두통|편두통|요통).*(아프|통증|뻣뻣|결림|저림)"],
            "다이어트": [r"(살|체중|다이어트|비만|뱃살|하체|허벅지)"],
            "피부": [r"(여드름|피부|흉터|뾰루지|트러블|아토피|가려움)"],
            "탈모": [r"(탈모|두피|머리카락|모발|빠지)"],
            "교통사고": [r"(교통사고|사고|추돌|접촉|자보|보험)"],
            "산후": [r"(출산|산후|육아|임신|골반|산후조리)"],
            "스트레스": [r"(스트레스|불면|피로|우울|불안|긴장)"],
            "소화": [r"(소화|위장|더부룩|속쓰림|역류|변비)"],
        }

        # 만족/불만 패턴
        self.sentiment_patterns = {
            "positive": [
                r"(좋|만족|추천|친절|효과|나았|편해|감사|최고|굿)",
                r"(덕분에|덕에|잘|확실히|진짜|정말)",
            ],
            "negative": [
                r"(별로|아쉽|비싸|불친절|효과없|안좋|실망)",
                r"(오래|기다림|불편)",
            ]
        }

        # 고객 언어 → 키워드 매핑
        self.customer_language = {
            "허리 아파서": "허리통증",
            "목이 뻣뻣": "거북목",
            "살 빼려고": "다이어트",
            "살 빼러": "다이어트",
            "여드름 때문에": "여드름치료",
            "피부가 안좋아서": "피부관리",
            "머리가 빠져서": "탈모치료",
            "사고 나서": "교통사고치료",
            "출산 후": "산후관리",
            "잠을 못 자서": "불면증",
            "스트레스 받아서": "스트레스",
            "소화가 안돼서": "소화불량",
        }

    def load_reviews_from_db(self) -> List[Dict]:
        """DB에서 리뷰 로드"""
        reviews = []

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # competitor_reviews 테이블에서 리뷰 로드
            cursor.execute("""
                SELECT competitor_name, review_text, rating, review_date
                FROM competitor_reviews
                WHERE review_text IS NOT NULL AND review_text != ''
                ORDER BY review_date DESC
                LIMIT 1000
            """)

            for row in cursor.fetchall():
                reviews.append({
                    'source': row[0],
                    'text': row[1],
                    'rating': row[2],
                    'date': row[3]
                })

            conn.close()

        except Exception as e:
            print(f"   DB 로드 오류: {e}")

        return reviews

    def load_reviews_from_json(self) -> List[Dict]:
        """JSON 백업에서 리뷰 로드 (DB 실패 시)"""
        reviews = []
        json_path = Path("data/reviews_backup.json")

        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                reviews = data.get('reviews', [])

        return reviews

    def extract_symptoms(self, text: str) -> List[str]:
        """리뷰에서 증상/니즈 추출"""
        found_symptoms = []

        for symptom, patterns in self.symptom_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text):
                    found_symptoms.append(symptom)
                    break

        return found_symptoms

    def extract_customer_keywords(self, text: str) -> List[str]:
        """고객 언어에서 키워드 추출"""
        keywords = []

        for phrase, keyword in self.customer_language.items():
            if phrase in text:
                keywords.append(keyword)

        return keywords

    def analyze_sentiment(self, text: str) -> str:
        """감성 분석"""
        pos_count = sum(
            1 for patterns in self.sentiment_patterns['positive']
            for _ in re.finditer(patterns, text)
        )
        neg_count = sum(
            1 for patterns in self.sentiment_patterns['negative']
            for _ in re.finditer(patterns, text)
        )

        if pos_count > neg_count:
            return "positive"
        elif neg_count > pos_count:
            return "negative"
        return "neutral"

    def extract_treatment_mentions(self, text: str) -> List[str]:
        """치료 방법 언급 추출"""
        treatments = []
        treatment_patterns = [
            (r"(침|침치료|침놓|침맞)", "침치료"),
            (r"(뜸|쑥뜸)", "뜸치료"),
            (r"(부항|컵)", "부항"),
            (r"(추나|추나요법|교정)", "추나"),
            (r"(한약|탕약|약)", "한약"),
            (r"(약침|봉침)", "약침"),
        ]

        for pattern, treatment in treatment_patterns:
            if re.search(pattern, text):
                treatments.append(treatment)

        return treatments

    def generate_insight_keywords(self, symptom_freq: Counter, treatment_freq: Counter) -> List[str]:
        """인사이트 기반 키워드 생성"""
        keywords = set()
        region = "청주"

        # 증상 기반
        for symptom, count in symptom_freq.most_common(10):
            keywords.add(f"{region} {symptom}")
            keywords.add(f"{region} {symptom} 한의원")
            keywords.add(f"{region} {symptom} 치료")
            keywords.add(f"{region} {symptom} 효과")

        # 치료법 기반
        for treatment, count in treatment_freq.most_common(5):
            keywords.add(f"{region} {treatment}")
            keywords.add(f"{region} {treatment} 잘하는곳")
            keywords.add(f"{region} {treatment} 추천")

        # 증상 + 치료 조합
        top_symptoms = [s for s, _ in symptom_freq.most_common(5)]
        top_treatments = [t for t, _ in treatment_freq.most_common(3)]

        for symptom in top_symptoms:
            for treatment in top_treatments:
                keywords.add(f"{region} {symptom} {treatment}")

        return list(keywords)

    def run(self) -> Dict:
        """전체 분석 실행"""
        print("=" * 60)
        print("📝 리뷰 텍스트 마이닝")
        print("=" * 60)
        print()

        # 리뷰 로드
        reviews = self.load_reviews_from_db()

        if not reviews:
            print("   DB에서 리뷰를 찾을 수 없습니다. JSON 백업 시도...")
            reviews = self.load_reviews_from_json()

        if not reviews:
            print("   리뷰 데이터가 없습니다.")
            # 샘플 리뷰 생성 (데모용)
            reviews = self._generate_sample_reviews()

        print(f"📊 분석 대상: {len(reviews)}개 리뷰")

        # 분석 결과
        symptom_freq = Counter()
        treatment_freq = Counter()
        customer_keyword_freq = Counter()
        sentiment_counts = Counter()
        insights = []

        for review in reviews:
            text = review.get('text', '')
            if not text:
                continue

            # 증상 추출
            symptoms = self.extract_symptoms(text)
            symptom_freq.update(symptoms)

            # 치료법 언급
            treatments = self.extract_treatment_mentions(text)
            treatment_freq.update(treatments)

            # 고객 언어 키워드
            customer_kws = self.extract_customer_keywords(text)
            customer_keyword_freq.update(customer_kws)

            # 감성
            sentiment = self.analyze_sentiment(text)
            sentiment_counts[sentiment] += 1

            # 인사이트 저장
            if symptoms or treatments:
                insights.append({
                    'text': text[:100],
                    'symptoms': symptoms,
                    'treatments': treatments,
                    'sentiment': sentiment
                })

        # 결과 출력
        print("\n📈 증상/니즈 빈도:")
        for symptom, count in symptom_freq.most_common(10):
            print(f"   {symptom}: {count}회")

        print("\n💊 치료법 언급:")
        for treatment, count in treatment_freq.most_common(5):
            print(f"   {treatment}: {count}회")

        print("\n😊 감성 분포:")
        total = sum(sentiment_counts.values())
        for sentiment, count in sentiment_counts.items():
            pct = count / total * 100 if total > 0 else 0
            emoji = "😊" if sentiment == "positive" else "😐" if sentiment == "neutral" else "😞"
            print(f"   {emoji} {sentiment}: {count}개 ({pct:.1f}%)")

        # 키워드 생성
        insight_keywords = self.generate_insight_keywords(symptom_freq, treatment_freq)
        print(f"\n🔑 인사이트 키워드 생성: {len(insight_keywords)}개")

        print("\n💬 리뷰 인사이트 샘플:")
        for insight in insights[:5]:
            print(f"   \"{insight['text']}...\"")
            print(f"      → 증상: {insight['symptoms']}, 치료: {insight['treatments']}")

        return {
            'review_count': len(reviews),
            'symptom_freq': dict(symptom_freq),
            'treatment_freq': dict(treatment_freq),
            'sentiment_counts': dict(sentiment_counts),
            'insight_keywords': insight_keywords,
            'insights': insights[:50],
            'timestamp': datetime.now().isoformat()
        }

    def _generate_sample_reviews(self) -> List[Dict]:
        """샘플 리뷰 (데모용)"""
        return [
            {'text': '허리가 너무 아파서 방문했는데 침치료 받고 많이 나아졌어요', 'rating': 5},
            {'text': '다이어트 한약 먹고 살이 많이 빠졌습니다 추천해요', 'rating': 5},
            {'text': '교통사고 후 목이 뻣뻣했는데 추나 받고 편해졌어요', 'rating': 4},
            {'text': '여드름 때문에 고민이었는데 피부 치료 효과 좋아요', 'rating': 5},
            {'text': '출산 후 골반 틀어진 것 같아서 왔는데 교정 잘해주셨어요', 'rating': 5},
            {'text': '스트레스 받아서 불면증이 심했는데 한약 먹고 잠을 잘 자요', 'rating': 4},
            {'text': '탈모 때문에 걱정이었는데 두피 치료 받고 있어요', 'rating': 4},
            {'text': '소화가 안돼서 힘들었는데 침 맞고 속이 편해졌어요', 'rating': 5},
            {'text': '목디스크로 고생했는데 추나요법 효과 좋습니다', 'rating': 5},
            {'text': '안면비대칭 교정 받고 있는데 만족스러워요', 'rating': 4},
        ]


def main():
    miner = ReviewMiner()
    results = miner.run()

    # 결과 저장
    output_path = "keyword_discovery/review_mining_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print()
    print(f"💾 결과 저장: {output_path}")

    return results


if __name__ == "__main__":
    main()

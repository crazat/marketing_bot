#!/usr/bin/env python3
"""
Review NLP Analyzer - 경쟁사 리뷰 AI 심층 분석기
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Gemini AI를 활용하여 competitor_reviews 테이블의 리뷰 텍스트를
심층 분석합니다.

- 경쟁사별 강점/약점 도출
- 빈출 시술/불만 분석
- 감성 비율 (긍정/중립/부정)
- 핵심 키워드 및 차별화 기회 발굴

Usage:
    python scrapers/review_nlp_analyzer.py
"""

import sys
import os
import time
import json
import logging
import traceback
import sqlite3
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'marketing_bot_web', 'backend'))

# Windows console encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

from db.database import DatabaseManager
from utils import ConfigManager
from services.ai_client import ai_generate, ai_generate_json

logger = logging.getLogger(__name__)


class ReviewNLPAnalyzer:
    """AI를 활용한 경쟁사 리뷰 심층 분석기"""

    BATCH_SIZE = 20  # 토큰 제한을 고려한 배치 크기
    RATE_LIMIT_DELAY = 2.0  # API 호출 간격 (초)

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self.ai_available = True
        self._ensure_table()

    def _ensure_table(self):
        """review_nlp_analysis 테이블이 없으면 생성합니다."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS review_nlp_analysis (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        competitor_name TEXT NOT NULL,
                        analysis_date TEXT NOT NULL,
                        total_reviews_analyzed INTEGER DEFAULT 0,
                        strengths TEXT DEFAULT '[]',
                        weaknesses TEXT DEFAULT '[]',
                        frequent_treatments TEXT DEFAULT '[]',
                        frequent_complaints TEXT DEFAULT '[]',
                        sentiment_positive REAL DEFAULT 0,
                        sentiment_neutral REAL DEFAULT 0,
                        sentiment_negative REAL DEFAULT 0,
                        key_keywords TEXT DEFAULT '[]',
                        differentiation_opportunities TEXT DEFAULT '[]',
                        raw_ai_response TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(competitor_name, analysis_date)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_review_nlp_competitor_date
                    ON review_nlp_analysis (competitor_name, analysis_date)
                """)
                conn.commit()
            logger.info("review_nlp_analysis 테이블 준비 완료")
        except Exception as e:
            logger.error(f"테이블 생성 실패: {e}")
            logger.debug(traceback.format_exc())

    def _load_reviews(self) -> Dict[str, List[Dict]]:
        """DB에서 경쟁사별 리뷰를 로드합니다."""
        reviews_by_competitor = defaultdict(list)

        try:
            with self.db.get_new_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT competitor_name, content, sentiment
                    FROM competitor_reviews
                    WHERE content IS NOT NULL AND content != ''
                    ORDER BY competitor_name, scraped_at DESC
                """)

                for row in cursor.fetchall():
                    reviews_by_competitor[row['competitor_name']].append({
                        'content': row['content'],
                        'sentiment': row['sentiment'] or 'neutral'
                    })

        except Exception as e:
            logger.error(f"리뷰 로드 실패: {e}")
            logger.debug(traceback.format_exc())

        return dict(reviews_by_competitor)

    def _build_prompt(self, competitor_name: str, reviews: List[Dict], batch_num: int, total_batches: int) -> str:
        """Gemini 분석 프롬프트를 생성합니다."""
        count = len(reviews)
        reviews_text = ""
        for i, review in enumerate(reviews, 1):
            sentiment_tag = f" [기존감성: {review['sentiment']}]" if review['sentiment'] != 'neutral' else ""
            reviews_text += f"\n[리뷰 {i}]{sentiment_tag}\n{review['content'][:500]}\n"

        batch_info = f" (배치 {batch_num}/{total_batches})" if total_batches > 1 else ""

        prompt = f"""다음은 {competitor_name}에 대한 고객 리뷰 {count}건입니다{batch_info}. 분석해주세요:

{reviews_text}

JSON 형식으로 응답:
{{
  "strengths": ["강점1", "강점2"],
  "weaknesses": ["약점1", "약점2"],
  "frequent_treatments": ["시술1", "시술2"],
  "frequent_complaints": ["불만1", "불만2"],
  "sentiment_ratio": {{"positive": 70, "neutral": 20, "negative": 10}},
  "key_keywords": ["키워드1", "키워드2"],
  "differentiation_opportunities": ["우리가 강조할 수 있는 차별점1", "차별점2"]
}}

반드시 유효한 JSON만 출력하세요. 다른 설명은 포함하지 마세요."""

        return prompt

    def _parse_json_response(self, text: str) -> Optional[Dict]:
        """Gemini 응답에서 JSON을 추출하고 파싱합니다."""
        if not text:
            return None

        # 마크다운 코드 블록 제거
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # JSON 블록 추출 시도
            json_match = re.search(r'\{[\s\S]*\}', cleaned)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

        logger.warning(f"JSON 파싱 실패: {text[:200]}...")
        return None

    def _merge_batch_results(self, batch_results: List[Dict]) -> Dict:
        """여러 배치의 분석 결과를 병합합니다."""
        merged = {
            'strengths': [],
            'weaknesses': [],
            'frequent_treatments': [],
            'frequent_complaints': [],
            'sentiment_ratio': {'positive': 0, 'neutral': 0, 'negative': 0},
            'key_keywords': [],
            'differentiation_opportunities': []
        }

        if not batch_results:
            return merged

        for result in batch_results:
            merged['strengths'].extend(result.get('strengths', []))
            merged['weaknesses'].extend(result.get('weaknesses', []))
            merged['frequent_treatments'].extend(result.get('frequent_treatments', []))
            merged['frequent_complaints'].extend(result.get('frequent_complaints', []))
            merged['key_keywords'].extend(result.get('key_keywords', []))
            merged['differentiation_opportunities'].extend(result.get('differentiation_opportunities', []))

            sr = result.get('sentiment_ratio', {})
            merged['sentiment_ratio']['positive'] += sr.get('positive', 0)
            merged['sentiment_ratio']['neutral'] += sr.get('neutral', 0)
            merged['sentiment_ratio']['negative'] += sr.get('negative', 0)

        # 중복 제거
        for key in ['strengths', 'weaknesses', 'frequent_treatments',
                     'frequent_complaints', 'key_keywords', 'differentiation_opportunities']:
            merged[key] = list(dict.fromkeys(merged[key]))

        # 감성 비율 평균화
        n = len(batch_results)
        if n > 0:
            merged['sentiment_ratio']['positive'] = round(merged['sentiment_ratio']['positive'] / n, 1)
            merged['sentiment_ratio']['neutral'] = round(merged['sentiment_ratio']['neutral'] / n, 1)
            merged['sentiment_ratio']['negative'] = round(merged['sentiment_ratio']['negative'] / n, 1)

        return merged

    def analyze_competitor(self, competitor_name: str, reviews: List[Dict]) -> Optional[Dict]:
        """단일 경쟁사의 리뷰를 분석합니다."""
        total_reviews = len(reviews)
        batches = [reviews[i:i + self.BATCH_SIZE] for i in range(0, total_reviews, self.BATCH_SIZE)]
        total_batches = len(batches)

        print(f"  [{competitor_name}] 리뷰 {total_reviews}건 분석 중 ({total_batches}개 배치)...", end=" ")

        batch_results = []
        raw_responses = []

        for batch_num, batch in enumerate(batches, 1):
            prompt = self._build_prompt(competitor_name, batch, batch_num, total_batches)

            try:
                parsed = ai_generate_json(prompt, temperature=0.3)
                if parsed:
                    raw_responses.append(json.dumps(parsed, ensure_ascii=False))
                    batch_results.append(parsed)
                else:
                    logger.warning(f"  [{competitor_name}] 배치 {batch_num} JSON 파싱 실패")

            except Exception as e:
                logger.error(f"  [{competitor_name}] 배치 {batch_num} AI 호출 실패: {e}")
                logger.debug(traceback.format_exc())

            # Rate limit
            if batch_num < total_batches:
                time.sleep(self.RATE_LIMIT_DELAY)

        if not batch_results:
            print("-> 분석 실패")
            return None

        # 배치 결과 병합
        merged = self._merge_batch_results(batch_results)

        sr = merged['sentiment_ratio']
        print(f"-> 긍정 {sr['positive']:.0f}% / 중립 {sr['neutral']:.0f}% / 부정 {sr['negative']:.0f}%")

        return {
            'competitor_name': competitor_name,
            'total_reviews_analyzed': total_reviews,
            'analysis': merged,
            'raw_responses': raw_responses
        }

    def _save_result(self, result: Dict):
        """분석 결과를 DB에 저장합니다."""
        analysis_date = datetime.now().strftime("%Y-%m-%d")
        analysis = result['analysis']

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO review_nlp_analysis
                    (competitor_name, analysis_date, total_reviews_analyzed,
                     strengths, weaknesses, frequent_treatments, frequent_complaints,
                     sentiment_positive, sentiment_neutral, sentiment_negative,
                     key_keywords, differentiation_opportunities, raw_ai_response)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(competitor_name, analysis_date) DO UPDATE SET
                        total_reviews_analyzed = excluded.total_reviews_analyzed,
                        strengths = excluded.strengths,
                        weaknesses = excluded.weaknesses,
                        frequent_treatments = excluded.frequent_treatments,
                        frequent_complaints = excluded.frequent_complaints,
                        sentiment_positive = excluded.sentiment_positive,
                        sentiment_neutral = excluded.sentiment_neutral,
                        sentiment_negative = excluded.sentiment_negative,
                        key_keywords = excluded.key_keywords,
                        differentiation_opportunities = excluded.differentiation_opportunities,
                        raw_ai_response = excluded.raw_ai_response
                """, (
                    result['competitor_name'],
                    analysis_date,
                    result['total_reviews_analyzed'],
                    json.dumps(analysis.get('strengths', []), ensure_ascii=False),
                    json.dumps(analysis.get('weaknesses', []), ensure_ascii=False),
                    json.dumps(analysis.get('frequent_treatments', []), ensure_ascii=False),
                    json.dumps(analysis.get('frequent_complaints', []), ensure_ascii=False),
                    analysis.get('sentiment_ratio', {}).get('positive', 0),
                    analysis.get('sentiment_ratio', {}).get('neutral', 0),
                    analysis.get('sentiment_ratio', {}).get('negative', 0),
                    json.dumps(analysis.get('key_keywords', []), ensure_ascii=False),
                    json.dumps(analysis.get('differentiation_opportunities', []), ensure_ascii=False),
                    json.dumps(result.get('raw_responses', []), ensure_ascii=False)
                ))
                conn.commit()
                logger.info(f"  [{result['competitor_name']}] DB 저장 완료")

        except Exception as e:
            logger.error(f"DB 저장 오류 [{result['competitor_name']}]: {e}")
            logger.debug(traceback.format_exc())

    def run(self):
        """전체 경쟁사에 대해 리뷰 NLP 분석을 수행합니다."""

        # 리뷰 로드
        reviews_by_competitor = self._load_reviews()

        if not reviews_by_competitor:
            print("분석할 리뷰가 없습니다.")
            return

        total_reviews = sum(len(v) for v in reviews_by_competitor.values())
        total_competitors = len(reviews_by_competitor)

        print(f"\n{'='*60}")
        print(f" Review NLP Analyzer")
        print(f" 경쟁사: {total_competitors}개 / 리뷰: {total_reviews}건")
        print(f" 시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        results = []
        success_count = 0
        error_count = 0

        for idx, (competitor_name, reviews) in enumerate(sorted(reviews_by_competitor.items()), 1):
            print(f"\n  [{idx}/{total_competitors}] ", end="")

            try:
                result = self.analyze_competitor(competitor_name, reviews)
                if result:
                    self._save_result(result)
                    results.append(result)
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                error_count += 1
                print(f"  [{competitor_name}] 오류: {e}")
                logger.error(f"[{competitor_name}] 분석 오류: {e}")
                logger.debug(traceback.format_exc())

            # Rate limit between competitors
            if idx < total_competitors:
                time.sleep(self.RATE_LIMIT_DELAY)

        # 결과 요약
        print(f"\n{'='*60}")
        print(f" 분석 완료! 성공: {success_count}/{total_competitors}")
        if error_count:
            print(f" 실패: {error_count}건")
        print(f"{'='*60}")

        # 상세 결과 출력
        if results:
            print(f"\n{'='*60}")
            print(f" 경쟁사별 분석 요약")
            print(f"{'='*60}")

            for r in results:
                analysis = r['analysis']
                sr = analysis.get('sentiment_ratio', {})
                print(f"\n  [{r['competitor_name']}] ({r['total_reviews_analyzed']}건 분석)")
                print(f"  감성 비율: 긍정 {sr.get('positive', 0):.0f}% / 중립 {sr.get('neutral', 0):.0f}% / 부정 {sr.get('negative', 0):.0f}%")

                strengths = analysis.get('strengths', [])[:3]
                if strengths:
                    print(f"  강점: {', '.join(strengths)}")

                weaknesses = analysis.get('weaknesses', [])[:3]
                if weaknesses:
                    print(f"  약점: {', '.join(weaknesses)}")

                opportunities = analysis.get('differentiation_opportunities', [])[:3]
                if opportunities:
                    print(f"  차별화 기회: {', '.join(opportunities)}")

        return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        analyzer = ReviewNLPAnalyzer()
        analyzer.run()
    except KeyboardInterrupt:
        print("\n사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.error(f"치명적 오류: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

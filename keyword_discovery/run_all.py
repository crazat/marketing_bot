#!/usr/bin/env python3
"""
키워드 발굴 시스템 통합 실행
- 5가지 접근법 순차 실행
- 결과 통합 및 우선순위 정렬
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
import os
from datetime import datetime
from pathlib import Path
from collections import Counter
from typing import Dict

# 모듈 import
from kin_crawler import KinCrawler
from blog_gap_analyzer import BlogGapAnalyzer
from review_miner import ReviewMiner
from trend_detector import TrendDetector
from question_finder import QuestionFinder

# 검색량 API
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
try:
    from scrapers.naver_ad_manager import NaverAdManager
    SEARCH_VOLUME_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ NaverAdManager import 실패: {e}")
    SEARCH_VOLUME_AVAILABLE = False


class KeywordDiscoverySystem:
    """키워드 발굴 통합 시스템"""

    def __init__(self, region: str = "청주"):
        self.region = region
        self.results = {}
        self.all_keywords = set()
        self.scored_keywords = []

    def run_all(self) -> Dict:
        """전체 실행"""
        print()
        print("=" * 70)
        print("🚀 키워드 발굴 시스템 v2.0")
        print("   5가지 접근법으로 진짜 가치 있는 키워드 발굴")
        print("=" * 70)
        print()

        # 1. 지식인/카페 크롤링
        print("\n" + "─" * 70)
        print("📌 [1/5] 네이버 지식인/카페 실제 질문 크롤링")
        print("─" * 70)
        try:
            kin_crawler = KinCrawler(region=self.region)
            self.results['kin'] = kin_crawler.run()
            self.all_keywords.update(self.results['kin'].get('longtail_keywords', []))
        except Exception as e:
            print(f"   ❌ 오류: {e}")
            self.results['kin'] = {'error': str(e)}

        # 2. 경쟁사 블로그 갭 분석
        print("\n" + "─" * 70)
        print("📌 [2/5] 경쟁사 블로그 콘텐츠 갭 분석")
        print("─" * 70)
        try:
            blog_analyzer = BlogGapAnalyzer(region=self.region)
            self.results['blog_gap'] = blog_analyzer.run()
            self.all_keywords.update(self.results['blog_gap'].get('gap_keywords', []))
        except Exception as e:
            print(f"   ❌ 오류: {e}")
            self.results['blog_gap'] = {'error': str(e)}

        # 3. 리뷰 텍스트 마이닝
        print("\n" + "─" * 70)
        print("📌 [3/5] 리뷰 텍스트 마이닝")
        print("─" * 70)
        try:
            review_miner = ReviewMiner()
            self.results['review'] = review_miner.run()
            self.all_keywords.update(self.results['review'].get('insight_keywords', []))
        except Exception as e:
            print(f"   ❌ 오류: {e}")
            self.results['review'] = {'error': str(e)}

        # 4. 트렌드 이상 감지
        print("\n" + "─" * 70)
        print("📌 [4/5] 검색 트렌드 이상 감지")
        print("─" * 70)
        try:
            trend_detector = TrendDetector(region=self.region)
            self.results['trend'] = trend_detector.run()
            self.all_keywords.update(self.results['trend'].get('opportunity_keywords', []))
        except Exception as e:
            print(f"   ❌ 오류: {e}")
            self.results['trend'] = {'error': str(e)}

        # 5. 질문형 롱테일
        print("\n" + "─" * 70)
        print("📌 [5/5] 질문형 롱테일 키워드")
        print("─" * 70)
        try:
            question_finder = QuestionFinder(region=self.region)
            self.results['question'] = question_finder.run()
            # 질문형 키워드 추가
            for q in self.results['question'].get('questions', []):
                self.all_keywords.add(q.get('keyword', ''))
        except Exception as e:
            print(f"   ❌ 오류: {e}")
            self.results['question'] = {'error': str(e)}

        # 결과 통합
        self._merge_and_score()

        return self.results

    def _merge_and_score(self):
        """결과 통합 및 점수화"""
        print("\n" + "=" * 70)
        print("📊 결과 통합 및 분석")
        print("=" * 70)

        # 키워드 출처 추적
        keyword_sources = {}

        # 지식인 키워드
        for kw in self.results.get('kin', {}).get('longtail_keywords', []):
            if kw not in keyword_sources:
                keyword_sources[kw] = []
            keyword_sources[kw].append('지식인')

        # 블로그 갭 키워드
        for kw in self.results.get('blog_gap', {}).get('gap_keywords', []):
            if kw not in keyword_sources:
                keyword_sources[kw] = []
            keyword_sources[kw].append('블로그갭')

        # 리뷰 인사이트 키워드
        for kw in self.results.get('review', {}).get('insight_keywords', []):
            if kw not in keyword_sources:
                keyword_sources[kw] = []
            keyword_sources[kw].append('리뷰')

        # 트렌드 기회 키워드
        for kw in self.results.get('trend', {}).get('opportunity_keywords', []):
            if kw not in keyword_sources:
                keyword_sources[kw] = []
            keyword_sources[kw].append('트렌드')

        # 질문형 키워드
        for q in self.results.get('question', {}).get('questions', []):
            kw = q.get('keyword', '')
            if kw:
                if kw not in keyword_sources:
                    keyword_sources[kw] = []
                keyword_sources[kw].append('질문형')

        # 점수 계산
        for kw, sources in keyword_sources.items():
            score = 0

            # 출처 다양성 보너스 (여러 접근법에서 발견된 키워드)
            score += len(sources) * 20

            # 출처별 가중치
            source_weights = {
                '지식인': 15,  # 실제 고객 질문
                '블로그갭': 20,  # 경쟁 갭
                '리뷰': 10,  # 고객 언어
                '트렌드': 25,  # 급증 기회
                '질문형': 15,  # 전환 의도
            }

            for src in sources:
                score += source_weights.get(src, 5)

            self.scored_keywords.append({
                'keyword': kw,
                'score': score,
                'sources': sources,
                'source_count': len(sources)
            })

        # 점수순 정렬
        self.scored_keywords.sort(key=lambda x: x['score'], reverse=True)

        # 검색량 검증 (상위 100개)
        self._validate_search_volume()

        # 결과 저장
        self.results['merged'] = {
            'total_keywords': len(keyword_sources),
            'scored_keywords': self.scored_keywords[:100],  # 상위 100개
            'multi_source_keywords': [
                k for k in self.scored_keywords if k['source_count'] >= 2
            ]
        }

        # 출력
        print(f"\n📈 총 발굴 키워드: {len(keyword_sources)}개")
        print(f"   다중 출처 키워드: {len(self.results['merged']['multi_source_keywords'])}개")

        print("\n🏆 최종 추천 키워드 (Top 30):")
        print("-" * 70)
        for i, kw in enumerate(self.scored_keywords[:30], 1):
            sources_str = ', '.join(kw['sources'])
            vol = kw.get('search_volume', 0)
            vol_str = f" | 검색량:{vol}" if vol > 0 else ""
            print(f"   {i:2}. [{kw['score']:3}] {kw['keyword']}{vol_str}")
            print(f"       └─ 출처: {sources_str}")

    def _validate_search_volume(self):
        """검색량 API로 키워드 검증 및 점수 반영"""
        if not SEARCH_VOLUME_AVAILABLE:
            print("\n⚠️ 검색량 API 사용 불가 - 검색량 검증 건너뜀")
            return

        print("\n📊 검색량 검증 중...")

        try:
            ad_manager = NaverAdManager()
            if ad_manager.disabled:
                print("   ⚠️ Naver Ad API 비활성화 상태")
                return

            # 상위 100개 키워드만 검증
            top_keywords = [kw['keyword'] for kw in self.scored_keywords[:100]]

            # 검색량 조회
            volumes = ad_manager.get_keyword_volumes(top_keywords)

            if not volumes:
                print("   ⚠️ 검색량 데이터 없음")
                return

            print(f"   ✅ {len(volumes)}개 키워드 검색량 조회 완료")

            # 점수에 검색량 반영
            for kw_data in self.scored_keywords:
                keyword = kw_data['keyword']
                # 정확한 매칭 또는 공백 제거 매칭
                vol = volumes.get(keyword, 0)
                if vol == 0:
                    # 공백 제거 버전 시도
                    vol = volumes.get(keyword.replace(" ", ""), 0)

                kw_data['search_volume'] = vol

                # 검색량 기반 점수 조정
                if vol >= 1000:
                    kw_data['score'] += 30  # 고검색량 보너스
                elif vol >= 500:
                    kw_data['score'] += 20
                elif vol >= 100:
                    kw_data['score'] += 10
                elif vol >= 50:
                    kw_data['score'] += 5
                elif vol == 0:
                    kw_data['score'] -= 10  # 검색량 없음 패널티

            # 점수 재정렬
            self.scored_keywords.sort(key=lambda x: x['score'], reverse=True)

            # 검색량 상위 키워드 출력
            print("\n📈 검색량 높은 키워드 (Top 10):")
            volume_sorted = sorted(
                [k for k in self.scored_keywords if k.get('search_volume', 0) > 0],
                key=lambda x: x['search_volume'],
                reverse=True
            )[:10]
            for kw in volume_sorted:
                print(f"   {kw['keyword']}: {kw['search_volume']:,}회/월")

        except Exception as e:
            print(f"   ❌ 검색량 검증 오류: {e}")

    def save_results(self, output_dir: str = "keyword_discovery"):
        """결과 저장"""
        Path(output_dir).mkdir(exist_ok=True)

        # 전체 결과
        output_path = f"{output_dir}/discovery_results.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)

        # CSV 형식 (상위 키워드) - 검색량 포함
        csv_path = f"{output_dir}/top_keywords.csv"
        with open(csv_path, 'w', encoding='utf-8-sig') as f:
            f.write("순위,키워드,점수,검색량,출처,출처수\n")
            for i, kw in enumerate(self.scored_keywords[:100], 1):
                sources = '|'.join(kw['sources'])
                vol = kw.get('search_volume', 0)
                f.write(f"{i},{kw['keyword']},{kw['score']},{vol},{sources},{kw['source_count']}\n")

        print(f"\n💾 결과 저장 완료:")
        print(f"   - {output_path}")
        print(f"   - {csv_path}")


def main():
    print("\n" + "=" * 70)
    print("   🔬 새로운 키워드 발굴 시스템")
    print("   뻔한 키워드가 아닌, 진짜 가치 있는 키워드 발굴")
    print("=" * 70)

    system = KeywordDiscoverySystem(region="청주")
    results = system.run_all()
    system.save_results()

    print("\n" + "=" * 70)
    print("✅ 키워드 발굴 완료!")
    print("=" * 70)

    return results


if __name__ == "__main__":
    main()

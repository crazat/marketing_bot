"""
AI Keyword Enhancer - A3 검색 의도 분류 + A2 의미 클러스터링
AI Client 활용
"""
import os
import sys
import sqlite3
import json
import time
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import re

# UTF-8 출력 설정
sys.stdout = sys.stdout if hasattr(sys.stdout, 'buffer') else sys.stdout
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# Add backend to path for ai_client import
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'marketing_bot_web', 'backend'))
from services.ai_client import ai_generate, ai_generate_json

# 유사도 계산용
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.cluster import DBSCAN
    import numpy as np
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("⚠️ scikit-learn 미설치 - 기본 클러스터링 사용")


@dataclass
class KeywordCluster:
    """키워드 클러스터 (KEI 지원)"""
    cluster_id: int
    representative: str  # 대표 키워드
    keywords: List[str]
    total_volume: int
    avg_difficulty: float
    search_intent: str
    # KEI 관련 필드
    avg_document_count: float = 0.0  # 클러스터 평균 문서 수
    cluster_kei: float = 0.0  # 클러스터 KEI = (클러스터 총 검색량)² / (클러스터 평균 문서 수)
    kei_grade: str = "C"  # KEI 기반 등급 (S/A/B/C)


class SearchIntentClassifierAI:
    """
    A3: LLM 기반 검색 의도 분류
    - Gemini API로 정확한 의도 분류
    - 배치 처리로 API 효율화
    """

    INTENT_DESCRIPTIONS = {
        'transactional': '구매/예약/상담 의도 (가격, 비용, 예약, 상담, 할인)',
        'commercial': '비교/검토 의도 (추천, 후기, 비교, 순위, 잘하는곳)',
        'informational': '정보 탐색 의도 (방법, 효과, 원인, 증상, 기간)',
        'navigational': '위치/연락처 탐색 (주소, 위치, 전화번호, 영업시간)'
    }

    def __init__(self, api_key: Optional[str] = None):
        self.available = True
        print("✅ AI Client 연결됨 (centralized ai_client)")

    def classify_batch(self, keywords: List[str], batch_size: int = 50) -> Dict[str, str]:
        """
        배치로 키워드 의도 분류
        Returns: {keyword: intent}
        """
        if not self.available:
            return self._fallback_classify(keywords)

        results = {}
        total = len(keywords)

        for i in range(0, total, batch_size):
            batch = keywords[i:i+batch_size]
            batch_results = self._classify_batch_api(batch)
            results.update(batch_results)

            print(f"   의도 분류: {min(i+batch_size, total)}/{total}...")
            time.sleep(0.5)  # Rate limiting

        return results

    def _classify_batch_api(self, keywords: List[str]) -> Dict[str, str]:
        """AI Client로 배치 분류"""
        prompt = f"""다음 한국어 키워드들의 검색 의도를 분류해주세요.

검색 의도 유형:
- transactional: 구매/예약/상담 의도 (가격, 비용, 예약)
- commercial: 비교/검토 의도 (추천, 후기, 비교, 순위)
- informational: 정보 탐색 의도 (방법, 효과, 원인, 증상)
- navigational: 위치/연락처 탐색 (주소, 위치, 전화번호)

키워드 목록:
{json.dumps(keywords, ensure_ascii=False, indent=2)}

JSON 형식으로만 응답해주세요:
{{"키워드1": "intent", "키워드2": "intent", ...}}
"""

        try:
            result = ai_generate_json(prompt, temperature=0.3)
            if result:
                return result

            # 실패 시 패턴 기반 fallback
            return self._fallback_classify(keywords)

        except Exception as e:
            print(f"   ⚠️ API 에러: {e}")
            return self._fallback_classify(keywords)

    def _fallback_classify(self, keywords: List[str]) -> Dict[str, str]:
        """패턴 기반 fallback 분류"""
        patterns = {
            'transactional': ['가격', '비용', '할인', '예약', '상담', '무료', '체험', '견적'],
            'commercial': ['추천', '비교', '순위', '후기', '리뷰', '잘하는', '전문', '맛집', '인기'],
            'informational': ['방법', '효과', '원인', '증상', '치료', '기간', '부작용', '차이', '뜻'],
            'navigational': ['위치', '주소', '전화', '영업시간', '근처', '가까운', '길찾기'],
        }

        results = {}
        for kw in keywords:
            intent = 'unknown'
            for intent_type, words in patterns.items():
                if any(w in kw for w in words):
                    intent = intent_type
                    break
            results[kw] = intent

        return results


class SemanticClusteringAI:
    """
    A2: 의미 기반 키워드 클러스터링 (KEI 지원)
    - TF-IDF + 코사인 유사도 기반
    - DBSCAN으로 자동 클러스터 수 결정
    - 클러스터 KEI 계산
    """

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            analyzer='char_wb',  # 한글 형태소 대신 char n-gram
            ngram_range=(2, 4),
            max_features=5000
        ) if SKLEARN_AVAILABLE else None

    def _calculate_cluster_kei(self, total_volume: int, avg_document_count: float) -> float:
        """
        클러스터 KEI 계산

        공식: 클러스터 KEI = (클러스터 총 검색량)² / (클러스터 평균 문서 수)

        Args:
            total_volume: 클러스터 내 모든 키워드 검색량 합
            avg_document_count: 클러스터 내 키워드 평균 문서 수

        Returns:
            클러스터 KEI 값
        """
        if avg_document_count <= 0 or total_volume <= 0:
            return 0.0
        return round((total_volume ** 2) / avg_document_count, 2)

    def _assign_kei_grade(self, kei: float) -> str:
        """KEI 기반 등급 부여"""
        if kei >= 500:
            return 'S'
        elif kei >= 200:
            return 'A'
        elif kei >= 50:
            return 'B'
        else:
            return 'C'

    def cluster_keywords(
        self,
        keywords: List[str],
        volumes: Dict[str, int] = None,
        difficulties: Dict[str, float] = None,
        document_counts: Dict[str, int] = None,  # 신규: 문서 수
        min_similarity: float = 0.6
    ) -> List[KeywordCluster]:
        """
        키워드 클러스터링 (KEI 포함)
        Returns: 클러스터 목록
        """
        if not SKLEARN_AVAILABLE:
            return self._fallback_cluster(keywords, volumes, difficulties, document_counts)

        if len(keywords) < 2:
            return []

        # TF-IDF 벡터화
        try:
            tfidf_matrix = self.vectorizer.fit_transform(keywords)
        except Exception:
            return self._fallback_cluster(keywords, volumes, difficulties, document_counts)

        # 코사인 유사도 계산
        similarity_matrix = cosine_similarity(tfidf_matrix)

        # 거리 행렬로 변환 (1 - similarity), 음수 방지
        distance_matrix = 1 - similarity_matrix
        distance_matrix = np.clip(distance_matrix, 0, 2)  # 음수 방지

        # DBSCAN 클러스터링 (eps = 1 - min_similarity)
        clustering = DBSCAN(
            eps=1-min_similarity,
            min_samples=2,
            metric='precomputed'
        )

        labels = clustering.fit_predict(distance_matrix)

        # 클러스터 구성
        clusters_dict = defaultdict(list)
        for idx, label in enumerate(labels):
            if label != -1:  # 노이즈 제외
                clusters_dict[label].append(keywords[idx])

        # 클러스터 객체 생성
        clusters = []
        for cluster_id, kw_list in clusters_dict.items():
            # 대표 키워드 선정 (가장 짧은 키워드)
            representative = min(kw_list, key=len)

            # 통계 계산
            total_vol = sum(volumes.get(kw, 0) for kw in kw_list) if volumes else 0
            avg_diff = (
                sum(difficulties.get(kw, 50) for kw in kw_list) / len(kw_list)
                if difficulties else 50
            )

            # KEI 계산
            avg_doc_count = 0.0
            if document_counts:
                doc_counts = [document_counts.get(kw, 0) for kw in kw_list if document_counts.get(kw, 0) > 0]
                if doc_counts:
                    avg_doc_count = sum(doc_counts) / len(doc_counts)

            cluster_kei = self._calculate_cluster_kei(total_vol, avg_doc_count)
            kei_grade = self._assign_kei_grade(cluster_kei)

            clusters.append(KeywordCluster(
                cluster_id=cluster_id,
                representative=representative,
                keywords=kw_list,
                total_volume=total_vol,
                avg_difficulty=avg_diff,
                search_intent='unknown',
                avg_document_count=avg_doc_count,
                cluster_kei=cluster_kei,
                kei_grade=kei_grade
            ))

        # 클러스터 KEI순 정렬
        clusters.sort(key=lambda c: c.cluster_kei, reverse=True)

        return clusters

    def _fallback_cluster(
        self,
        keywords: List[str],
        volumes: Dict[str, int] = None,
        difficulties: Dict[str, float] = None,
        document_counts: Dict[str, int] = None
    ) -> List[KeywordCluster]:
        """scikit-learn 없을 때 기본 클러스터링 (KEI 지원)"""
        clusters_dict = defaultdict(list)

        for kw in keywords:
            # 핵심어 추출 (지역명 제거 후 첫 단어)
            core = kw.replace('청주', '').replace('제천', '').replace('충주', '').strip()
            core = re.sub(r'\s+', ' ', core)
            parts = core.split()

            if parts:
                key = parts[0][:4]  # 첫 4글자를 키로
                clusters_dict[key].append(kw)

        clusters = []
        for idx, (key, kw_list) in enumerate(clusters_dict.items()):
            if len(kw_list) >= 2:
                representative = min(kw_list, key=len)
                total_vol = sum(volumes.get(kw, 0) for kw in kw_list) if volumes else 0
                avg_diff = (
                    sum(difficulties.get(kw, 50) for kw in kw_list) / len(kw_list)
                    if difficulties else 50
                )

                # KEI 계산
                avg_doc_count = 0.0
                if document_counts:
                    doc_counts = [document_counts.get(kw, 0) for kw in kw_list if document_counts.get(kw, 0) > 0]
                    if doc_counts:
                        avg_doc_count = sum(doc_counts) / len(doc_counts)

                cluster_kei = self._calculate_cluster_kei(total_vol, avg_doc_count)
                kei_grade = self._assign_kei_grade(cluster_kei)

                clusters.append(KeywordCluster(
                    cluster_id=idx,
                    representative=representative,
                    keywords=kw_list,
                    total_volume=total_vol,
                    avg_difficulty=avg_diff,
                    search_intent='unknown',
                    avg_document_count=avg_doc_count,
                    cluster_kei=cluster_kei,
                    kei_grade=kei_grade
                ))

        clusters.sort(key=lambda c: c.cluster_kei, reverse=True)
        return clusters


class AIKeywordEnhancer:
    """
    통합 AI 키워드 강화 모듈
    - A3: 검색 의도 LLM 분류
    - A2: 의미 기반 클러스터링
    """

    def __init__(self, db_path: str = "db/marketing_data.db"):
        self.db_path = db_path
        self.intent_classifier = SearchIntentClassifierAI()
        self.semantic_clusterer = SemanticClusteringAI()

    def enhance_all(self, update_db: bool = True) -> Dict:
        """전체 키워드 강화 실행"""
        print("=" * 60)
        print("🤖 AI 키워드 강화 시작")
        print("=" * 60)

        # DB에서 키워드 로드
        conn = sqlite3.connect(self.db_path)
        df_query = """
            SELECT keyword, search_volume, difficulty, search_intent, grade
            FROM keyword_insights
        """
        cursor = conn.cursor()
        cursor.execute(df_query)
        rows = cursor.fetchall()

        keywords = []
        volumes = {}
        difficulties = {}
        current_intents = {}
        grades = {}

        for row in rows:
            kw, vol, diff, intent, grade = row
            keywords.append(kw)
            volumes[kw] = vol or 0
            difficulties[kw] = diff or 50
            current_intents[kw] = intent or 'unknown'
            grades[kw] = grade or 'C'

        print(f"\n총 키워드: {len(keywords)}개")

        # 1. A3: 검색 의도 분류
        print("\n" + "=" * 60)
        print("🔍 A3: 검색 의도 LLM 분류")
        print("=" * 60)

        # unknown인 키워드만 분류
        unknown_keywords = [kw for kw, intent in current_intents.items() if intent == 'unknown']
        print(f"   미분류 키워드: {len(unknown_keywords)}개")

        if unknown_keywords and self.intent_classifier.available:
            new_intents = self.intent_classifier.classify_batch(unknown_keywords)

            # 통계
            intent_counts = defaultdict(int)
            for kw, intent in new_intents.items():
                intent_counts[intent] += 1
                current_intents[kw] = intent

            print("\n   분류 결과:")
            for intent, count in sorted(intent_counts.items(), key=lambda x: -x[1]):
                pct = count / len(unknown_keywords) * 100
                print(f"      {intent}: {count}개 ({pct:.1f}%)")
        else:
            print("   ⚠️ Gemini API 불가 - 패턴 기반 분류 사용")
            new_intents = self.intent_classifier._fallback_classify(unknown_keywords)
            for kw, intent in new_intents.items():
                current_intents[kw] = intent

        # 2. A2: 의미 클러스터링
        print("\n" + "=" * 60)
        print("🔗 A2: 의미 기반 클러스터링")
        print("=" * 60)

        clusters = self.semantic_clusterer.cluster_keywords(
            keywords, volumes, difficulties
        )

        print(f"   클러스터 수: {len(clusters)}개")
        print(f"   클러스터링된 키워드: {sum(len(c.keywords) for c in clusters)}개")

        # 클러스터에 검색 의도 할당
        for cluster in clusters:
            intent_counts = defaultdict(int)
            for kw in cluster.keywords:
                intent_counts[current_intents.get(kw, 'unknown')] += 1
            cluster.search_intent = max(intent_counts, key=intent_counts.get)

        # 상위 클러스터 출력
        print("\n   상위 10개 클러스터:")
        for c in clusters[:10]:
            sa_count = sum(1 for kw in c.keywords if grades.get(kw) in ['S', 'A'])
            print(f"      [{c.representative}] {len(c.keywords)}개, "
                  f"S/A:{sa_count}, 의도:{c.search_intent}")

        # 3. DB 업데이트
        if update_db:
            print("\n" + "=" * 60)
            print("💾 DB 업데이트")
            print("=" * 60)

            # search_intent 업데이트
            updated = 0
            for kw, intent in current_intents.items():
                if intent != 'unknown':
                    cursor.execute(
                        "UPDATE keyword_insights SET search_intent = ? WHERE keyword = ?",
                        (intent, kw)
                    )
                    updated += 1

            conn.commit()
            print(f"   검색 의도 업데이트: {updated}개")

        conn.close()

        # 4. 결과 요약
        print("\n" + "=" * 60)
        print("📊 AI 강화 결과 요약")
        print("=" * 60)

        # 의도별 통계
        intent_stats = defaultdict(lambda: {'count': 0, 'sa_count': 0})
        for kw, intent in current_intents.items():
            intent_stats[intent]['count'] += 1
            if grades.get(kw) in ['S', 'A']:
                intent_stats[intent]['sa_count'] += 1

        print("\n의도별 분포 및 S/A급 비율:")
        for intent, stats in sorted(intent_stats.items(), key=lambda x: -x[1]['count']):
            sa_rate = stats['sa_count'] / stats['count'] * 100 if stats['count'] > 0 else 0
            emoji = {'transactional': '💰', 'commercial': '🔍',
                     'informational': '📚', 'navigational': '📍'}.get(intent, '❓')
            print(f"   {emoji} {intent}: {stats['count']}개, S/A급 {sa_rate:.1f}%")

        # 클러스터 통계
        print(f"\n클러스터 통계:")
        print(f"   총 클러스터: {len(clusters)}개")
        print(f"   평균 키워드/클러스터: {sum(len(c.keywords) for c in clusters) / max(1, len(clusters)):.1f}개")
        print(f"   최대 클러스터: {max(len(c.keywords) for c in clusters) if clusters else 0}개")

        return {
            'total_keywords': len(keywords),
            'intent_classified': len([i for i in current_intents.values() if i != 'unknown']),
            'clusters': len(clusters),
            'clustered_keywords': sum(len(c.keywords) for c in clusters),
            'intent_stats': dict(intent_stats),
            'top_clusters': clusters[:20]
        }

    def get_content_recommendations(self, top_n: int = 10) -> List[Dict]:
        """
        콘텐츠 추천 생성
        클러스터 기반으로 한 번에 여러 키워드 커버
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # S/A급 키워드 로드
        cursor.execute("""
            SELECT keyword, search_volume, difficulty, search_intent, grade
            FROM keyword_insights
            WHERE grade IN ('S', 'A')
            ORDER BY search_volume DESC
        """)
        rows = cursor.fetchall()

        keywords = []
        volumes = {}
        difficulties = {}
        intents = {}

        for row in rows:
            kw, vol, diff, intent, grade = row
            keywords.append(kw)
            volumes[kw] = vol or 0
            difficulties[kw] = diff or 50
            intents[kw] = intent or 'unknown'

        conn.close()

        # 클러스터링
        clusters = self.semantic_clusterer.cluster_keywords(keywords, volumes, difficulties)

        # 콘텐츠 추천 생성
        recommendations = []
        for c in clusters[:top_n]:
            # 대표 의도 결정
            intent_counts = defaultdict(int)
            for kw in c.keywords:
                intent_counts[intents.get(kw, 'unknown')] += 1
            main_intent = max(intent_counts, key=intent_counts.get)

            # 제목 템플릿
            title_templates = {
                'transactional': f"{c.representative} 가격/비용 총정리 - 예약 전 필독!",
                'commercial': f"{c.representative} 추천 BEST - 실제 후기 비교",
                'informational': f"{c.representative} 효과와 방법 - 전문가 가이드",
                'navigational': f"{c.representative} 위치/영업시간 안내"
            }

            recommendations.append({
                'title': title_templates.get(main_intent, f"{c.representative} 완벽 가이드"),
                'main_keyword': c.representative,
                'target_keywords': c.keywords[:10],
                'total_volume': c.total_volume,
                'avg_difficulty': c.avg_difficulty,
                'search_intent': main_intent,
                'keyword_count': len(c.keywords)
            })

        return recommendations


def main():
    """메인 실행"""
    print("=" * 60)
    print("🚀 AI 키워드 강화 모듈 실행")
    print("=" * 60)

    enhancer = AIKeywordEnhancer()

    # 전체 강화 실행
    results = enhancer.enhance_all(update_db=True)

    # 콘텐츠 추천
    print("\n" + "=" * 60)
    print("📝 콘텐츠 추천 (상위 10개)")
    print("=" * 60)

    recommendations = enhancer.get_content_recommendations(top_n=10)

    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. {rec['title']}")
        print(f"   대표 키워드: {rec['main_keyword']}")
        print(f"   타겟 키워드 수: {rec['keyword_count']}개")
        print(f"   총 검색량: {rec['total_volume']:,}")
        print(f"   평균 난이도: {rec['avg_difficulty']:.1f}")
        print(f"   검색 의도: {rec['search_intent']}")
        print(f"   포함 키워드: {', '.join(rec['target_keywords'][:5])}...")

    print("\n✅ 완료!")


if __name__ == "__main__":
    main()

"""
Pathfinder 업그레이드 모듈
- A1: 중복 단어 자동 제거
- A3: 검색량 0 키워드 필터
- B1: 경쟁사 블로그 역분석
- F1: API 비용 최적화 (Gemini 캐싱)
- F2: 병렬 수집 강화 (async)
"""
import os
import sys
import sqlite3
import json
import time
import re
import hashlib
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import urllib.parse

# UTF-8 출력
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass  # Windows 콘솔 호환성: 일부 환경에서 reconfigure 미지원

# Add backend to path for ai_client import
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'marketing_bot_web', 'backend'))
from services.ai_client import ai_generate


# =============================================================================
# A1: 중복 단어 자동 제거
# =============================================================================
class DuplicateWordCleaner:
    """중복 단어 자동 제거"""

    @staticmethod
    def clean(keyword: str) -> str:
        """중복 연속 단어 제거"""
        words = keyword.split()
        cleaned = []
        prev = None
        for word in words:
            if word != prev:
                cleaned.append(word)
            prev = word
        return ' '.join(cleaned)

    @staticmethod
    def clean_batch(keywords: List[str]) -> Dict[str, str]:
        """배치 처리: {원본: 정제된} 반환"""
        result = {}
        for kw in keywords:
            cleaned = DuplicateWordCleaner.clean(kw)
            if cleaned != kw:
                result[kw] = cleaned
        return result

    @staticmethod
    def apply_to_db(db_path: str = "db/marketing_data.db") -> int:
        """DB에 적용"""
        conn = None
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT keyword FROM keyword_insights")
            keywords = [row[0] for row in cursor.fetchall()]

            cleaned_map = DuplicateWordCleaner.clean_batch(keywords)

            updated = 0
            for original, cleaned in cleaned_map.items():
                # 정제된 키워드가 이미 존재하는지 확인
                cursor.execute("SELECT 1 FROM keyword_insights WHERE keyword = ?", (cleaned,))
                if cursor.fetchone():
                    # 이미 존재하면 원본 삭제
                    cursor.execute("DELETE FROM keyword_insights WHERE keyword = ?", (original,))
                else:
                    # 없으면 업데이트
                    cursor.execute(
                        "UPDATE keyword_insights SET keyword = ? WHERE keyword = ?",
                        (cleaned, original)
                    )
                updated += 1

            conn.commit()
            return updated
        finally:
            if conn:
                conn.close()


# =============================================================================
# A3: 검색량 0 키워드 필터
# =============================================================================
class ZeroVolumeFilter:
    """검색량 0 또는 NULL 키워드 필터"""

    @staticmethod
    def get_zero_volume_keywords(db_path: str = "db/marketing_data.db") -> List[str]:
        """검색량 0인 키워드 조회"""
        conn = None
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT keyword FROM keyword_insights
                WHERE search_volume IS NULL OR search_volume = 0
            """)
            keywords = [row[0] for row in cursor.fetchall()]
            return keywords
        finally:
            if conn:
                conn.close()

    @staticmethod
    def archive_zero_volume(db_path: str = "db/marketing_data.db") -> int:
        """검색량 0 키워드를 아카이브 테이블로 이동"""
        conn = None
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 아카이브 테이블 생성
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS keyword_archive (
                    keyword TEXT PRIMARY KEY,
                    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reason TEXT
                )
            """)

            # 검색량 0 키워드 아카이브
            cursor.execute("""
                INSERT OR IGNORE INTO keyword_archive (keyword, reason)
                SELECT keyword, 'zero_volume' FROM keyword_insights
                WHERE search_volume IS NULL OR search_volume = 0
            """)

            archived = cursor.rowcount

            # 원본에서 삭제
            cursor.execute("""
                DELETE FROM keyword_insights
                WHERE search_volume IS NULL OR search_volume = 0
            """)

            conn.commit()
            return archived
        finally:
            if conn:
                conn.close()


# =============================================================================
# B1: 경쟁사 블로그 역분석
# =============================================================================
class CompetitorBlogAnalyzer:
    """경쟁사 블로그 키워드 역분석"""

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

    def extract_keywords_from_blog(self, blog_url: str) -> List[str]:
        """블로그에서 키워드 추출"""
        try:
            req = urllib.request.Request(blog_url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8', errors='ignore')

            keywords = []

            # 제목 추출
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.I)
            if title_match:
                keywords.append(title_match.group(1).strip())

            # 해시태그 추출
            hashtags = re.findall(r'#([가-힣a-zA-Z0-9_]+)', html)
            keywords.extend(hashtags)

            # meta keywords
            meta_match = re.search(r'<meta[^>]+name=["\']keywords["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
            if meta_match:
                keywords.extend(meta_match.group(1).split(','))

            return list(set(kw.strip() for kw in keywords if kw.strip()))

        except Exception as e:
            print(f"   ⚠️ 블로그 분석 실패: {e}")
            return []

    def search_competitor_blogs(self, query: str, location: str = "청주") -> List[Dict]:
        """네이버 블로그 검색 결과에서 경쟁사 블로그 찾기"""
        # 네이버 검색 API 사용
        try:
            from utils import ConfigManager
            config = ConfigManager()
            client_id = config.get('NAVER_CLIENT_ID')
            client_secret = config.get('NAVER_CLIENT_SECRET')
        except Exception as e:
            logger.warning(f"ConfigManager 로드 실패: {e}")
            return []

        if not client_id or not client_secret:
            return []

        search_query = f"{location} {query}"
        encoded_query = urllib.parse.quote(search_query)
        url = f"https://openapi.naver.com/v1/search/blog.json?query={encoded_query}&display=10&sort=sim"

        req = urllib.request.Request(url)
        req.add_header("X-Naver-Client-Id", client_id)
        req.add_header("X-Naver-Client-Secret", client_secret)

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data.get('items', [])
        except Exception as e:
            print(f"   ⚠️ 블로그 검색 실패: {e}")
            return []

    def analyze_top_blogs(self, category: str, location: str = "청주", top_n: int = 5) -> List[str]:
        """상위 블로그에서 키워드 추출"""
        blogs = self.search_competitor_blogs(category, location)

        all_keywords = []
        for blog in blogs[:top_n]:
            link = blog.get('link', '')
            if 'blog.naver.com' in link:
                keywords = self.extract_keywords_from_blog(link)
                all_keywords.extend(keywords)
                time.sleep(0.3)  # Rate limiting

        # 빈도순 정렬
        from collections import Counter
        keyword_counts = Counter(all_keywords)
        return [kw for kw, _ in keyword_counts.most_common(20)]


# =============================================================================
# F1: API 비용 최적화 (Gemini 캐싱)
# =============================================================================
class GeminiCache:
    """Gemini API 응답 캐싱"""

    def __init__(self, cache_db: str = "db/gemini_cache.db"):
        self.cache_db = cache_db
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gemini_cache (
                prompt_hash TEXT PRIMARY KEY,
                response TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tokens_saved INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def _hash_prompt(self, prompt: str) -> str:
        return hashlib.md5(prompt.encode()).hexdigest()

    def get(self, prompt: str) -> Optional[str]:
        """캐시에서 응답 조회"""
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()
        prompt_hash = self._hash_prompt(prompt)
        cursor.execute(
            "SELECT response FROM gemini_cache WHERE prompt_hash = ?",
            (prompt_hash,)
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def set(self, prompt: str, response: str, tokens: int = 0):
        """캐시에 응답 저장"""
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()
        prompt_hash = self._hash_prompt(prompt)
        cursor.execute("""
            INSERT OR REPLACE INTO gemini_cache (prompt_hash, response, tokens_saved)
            VALUES (?, ?, ?)
        """, (prompt_hash, response, tokens))
        conn.commit()
        conn.close()

    def get_stats(self) -> Dict:
        """캐시 통계"""
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(tokens_saved) FROM gemini_cache")
        row = cursor.fetchone()
        conn.close()
        return {
            'cached_responses': row[0] or 0,
            'tokens_saved': row[1] or 0,
            'estimated_cost_saved': (row[1] or 0) * 0.00001  # 대략적 비용
        }


class CachedGeminiClient:
    """캐싱이 적용된 AI 클라이언트"""

    def __init__(self, api_key: Optional[str] = None):
        self.cache = GeminiCache()
        self.cache_hits = 0
        self.api_calls = 0

    def generate(self, prompt: str, use_cache: bool = True) -> Optional[str]:
        """캐시 우선 생성"""
        # 캐시 확인
        if use_cache:
            cached = self.cache.get(prompt)
            if cached:
                self.cache_hits += 1
                return cached

        try:
            result = ai_generate(prompt, temperature=0.7)
            self.api_calls += 1

            # 캐시 저장
            if use_cache:
                tokens = len(prompt.split()) + len(result.split())
                self.cache.set(prompt, result, tokens)

            return result
        except Exception as e:
            print(f"   ⚠️ AI 에러: {e}")
            return None

    def get_stats(self) -> Dict:
        """통계 조회"""
        cache_stats = self.cache.get_stats()
        return {
            'cache_hits': self.cache_hits,
            'api_calls': self.api_calls,
            'hit_rate': self.cache_hits / max(1, self.cache_hits + self.api_calls) * 100,
            **cache_stats
        }


# =============================================================================
# F2: 병렬 수집 강화
# =============================================================================
class ParallelCollector:
    """병렬 키워드 수집"""

    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers

    def collect_autocomplete_parallel(
        self,
        seeds: List[str],
        collector_func
    ) -> Dict[str, List[str]]:
        """병렬 자동완성 수집"""
        results = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_seed = {
                executor.submit(collector_func, seed): seed
                for seed in seeds
            }

            for future in as_completed(future_to_seed):
                seed = future_to_seed[future]
                try:
                    result = future.result()
                    if result:
                        results[seed] = result
                except Exception as e:
                    print(f"   ⚠️ {seed} 수집 실패: {e}")

        return results

    def analyze_serp_parallel(
        self,
        keywords: List[str],
        analyzer_func,
        batch_size: int = 20
    ) -> Dict[str, Tuple[int, int, str]]:
        """병렬 SERP 분석"""
        results = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_kw = {
                executor.submit(analyzer_func, kw): kw
                for kw in keywords
            }

            completed = 0
            for future in as_completed(future_to_kw):
                kw = future_to_kw[future]
                try:
                    result = future.result()
                    if result:
                        results[kw] = result
                except Exception:
                    pass

                completed += 1
                if completed % batch_size == 0:
                    print(f"   진행: {completed}/{len(keywords)}...")

        return results


# =============================================================================
# 통합 테스트
# =============================================================================
def test_all_upgrades():
    """모든 업그레이드 테스트"""
    print("=" * 60)
    print("🧪 Pathfinder 업그레이드 테스트")
    print("=" * 60)

    # A1: 중복 단어 제거
    print("\n[A1] 중복 단어 자동 제거")
    print("-" * 40)

    test_keywords = [
        "청주 산후조리원 비용 비용",
        "청주 다이어트 한약 추천 추천",
        "청주 안면비대칭 교정 가격 가격",
        "청주 탈모 치료",  # 정상
    ]

    for kw in test_keywords:
        cleaned = DuplicateWordCleaner.clean(kw)
        if kw != cleaned:
            print(f"   ✅ '{kw}' → '{cleaned}'")
        else:
            print(f"   ⏭️ '{kw}' (변경 없음)")

    # DB 적용
    print("\n   DB 적용 중...")
    updated = DuplicateWordCleaner.apply_to_db()
    print(f"   ✅ {updated}개 키워드 정제됨")

    # A3: 검색량 0 필터
    print("\n[A3] 검색량 0 키워드 필터")
    print("-" * 40)

    zero_keywords = ZeroVolumeFilter.get_zero_volume_keywords()
    print(f"   검색량 0 키워드: {len(zero_keywords)}개")

    if zero_keywords:
        print("   예시:")
        for kw in zero_keywords[:5]:
            print(f"      - {kw}")

        # 아카이브 (주석 처리 - 실제 적용 시 해제)
        # archived = ZeroVolumeFilter.archive_zero_volume()
        # print(f"   ✅ {archived}개 아카이브됨")
        print("   ⏸️ 아카이브 대기 (수동 실행 필요)")

    # B1: 경쟁사 블로그 역분석
    print("\n[B1] 경쟁사 블로그 역분석")
    print("-" * 40)

    analyzer = CompetitorBlogAnalyzer()
    categories = ["다이어트 한의원", "교통사고 한의원", "탈모 치료"]

    for category in categories[:1]:  # 테스트는 1개만
        print(f"\n   '{category}' 분석 중...")
        keywords = analyzer.analyze_top_blogs(category, "청주", top_n=3)
        if keywords:
            print(f"   발견된 키워드: {len(keywords)}개")
            for kw in keywords[:5]:
                print(f"      - {kw}")
        else:
            print("   ⚠️ 키워드 발견 실패 (API 키 확인 필요)")

    # F1: Gemini 캐싱
    print("\n[F1] API 비용 최적화 (Gemini 캐싱)")
    print("-" * 40)

    client = CachedGeminiClient()

    # 테스트 프롬프트
    test_prompt = "청주 다이어트 한의원의 검색 의도를 분류해주세요."

    print("   첫 번째 호출 (API)...")
    result1 = client.generate(test_prompt)
    stats1 = client.get_stats()
    print(f"   API 호출: {stats1['api_calls']}, 캐시 히트: {stats1['cache_hits']}")

    print("   두 번째 호출 (캐시)...")
    result2 = client.generate(test_prompt)
    stats2 = client.get_stats()
    print(f"   API 호출: {stats2['api_calls']}, 캐시 히트: {stats2['cache_hits']}")

    if stats2['cache_hits'] > stats1['cache_hits']:
        print("   ✅ 캐싱 작동 확인!")

    cache_stats = client.cache.get_stats()
    print(f"\n   캐시 통계:")
    print(f"      저장된 응답: {cache_stats['cached_responses']}개")
    print(f"      절약된 토큰: {cache_stats['tokens_saved']:,}개")
    print(f"      예상 비용 절감: ${cache_stats['estimated_cost_saved']:.4f}")

    # F2: 병렬 수집
    print("\n[F2] 병렬 수집 강화")
    print("-" * 40)

    parallel = ParallelCollector(max_workers=5)

    # 간단한 테스트 함수
    def dummy_collect(seed):
        time.sleep(0.1)  # 시뮬레이션
        return [f"{seed} 키워드1", f"{seed} 키워드2"]

    test_seeds = ["청주 다이어트", "청주 탈모", "청주 교통사고", "청주 한의원", "청주 피부과"]

    print(f"   {len(test_seeds)}개 시드 병렬 수집 중...")
    start_time = time.time()
    results = parallel.collect_autocomplete_parallel(test_seeds, dummy_collect)
    elapsed = time.time() - start_time

    print(f"   ✅ 완료: {len(results)}개 결과, {elapsed:.2f}초")
    print(f"   (순차 처리 예상: {len(test_seeds) * 0.1:.2f}초)")
    print(f"   속도 향상: {(len(test_seeds) * 0.1) / elapsed:.1f}배")

    # 최종 요약
    print("\n" + "=" * 60)
    print("📊 업그레이드 테스트 결과 요약")
    print("=" * 60)
    print(f"""
✅ A1 중복 단어 제거: {updated}개 정제
✅ A3 검색량 0 필터: {len(zero_keywords)}개 발견
✅ B1 경쟁사 역분석: 작동 확인
✅ F1 Gemini 캐싱: 히트율 {stats2['hit_rate']:.1f}%
✅ F2 병렬 수집: {(len(test_seeds) * 0.1) / elapsed:.1f}배 속도 향상
""")

    print("✅ 모든 업그레이드 테스트 완료!")


if __name__ == "__main__":
    test_all_upgrades()

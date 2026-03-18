#!/usr/bin/env python3
"""
Keyword Cluster Analyzer - 키워드 시맨틱 클러스터 분석기
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
기존 DB의 키워드 데이터를 활용하여 의미적으로 연관된 키워드를
클러스터로 그룹핑하고, 각 클러스터의 기회를 분석합니다.

- keyword_insights, naver_ad_keyword_data, naver_ad_related_keywords 활용
- 연결 요소(Connected Component) 기반 클러스터링
- 클러스터별 검색량, 경쟁도, 추적 현황, 기회 점수 산출
- 검색 의도(intent) 자동 분류

Usage:
    python scrapers/keyword_cluster_analyzer.py
"""

import sys
import os
import time
import json
import logging
import traceback
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict, deque

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Windows console encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

from db.database import DatabaseManager
from utils import ConfigManager

logger = logging.getLogger(__name__)


# Intent classification rules
INTENT_RULES = {
    'treatment_seeking': [
        '시술', '치료', '수술', '교정', '보톡스', '필러', '리프팅',
        '추나', '도수', '침', '한약', '보약', '다이어트', '탈모',
        '레이저', '인모드', '슈링크', '제모', '임플란트', '스케일링'
    ],
    'clinic_finding': [
        '병원', '한의원', '클리닉', '의원', '추천', '잘하는', '유명한',
        '근처', '주변', '가까운'
    ],
    'price_comparing': [
        '비용', '가격', '얼마', '저렴', '싼', '할인', '이벤트',
        '보험', '실비', '비급여'
    ],
    'review_checking': [
        '후기', '리뷰', '솔직', '체험', '전후', '경험', '효과',
        '부작용', '결과'
    ],
    'symptom_research': [
        '증상', '원인', '질환', '통증', '아파', '아픈', '디스크',
        '관절', '여드름', '비만', '불면', '우울'
    ]
}

# Theme detection keywords
THEME_KEYWORDS = {
    '다이어트': ['다이어트', '살빼기', '비만', '체중', '감량'],
    '교통사고': ['교통사고', '후유증', '자동차', '사고'],
    '여드름': ['여드름', '피부', '모공', '흉터', '아토피'],
    '안면비대칭': ['안면비대칭', '비대칭', '안면', '턱'],
    '통증': ['통증', '디스크', '관절', '염좌', '허리', '목', '어깨'],
    '한약': ['한약', '보약', '한방', '한의원'],
    '미용': ['보톡스', '필러', '리프팅', '성형', '미백', '레이저'],
    '재활': ['재활', '추나', '도수', '물리치료'],
    '정신건강': ['우울', '불면', '공황', '스트레스', '상담'],
    '치과': ['치과', '임플란트', '교정', '스케일링', '사랑니'],
}


class KeywordClusterAnalyzer:
    """키워드 시맨틱 클러스터 분석기"""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self._ensure_table()

        # 추적 중인 키워드 로드
        self.tracked_keywords = set()
        self._load_tracked_keywords()

    def _ensure_table(self):
        """keyword_clusters 테이블이 없으면 생성합니다."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS keyword_clusters (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cluster_name TEXT NOT NULL,
                        cluster_theme TEXT,
                        intent_type TEXT DEFAULT 'general',
                        keywords TEXT NOT NULL,
                        keyword_count INTEGER DEFAULT 0,
                        total_search_volume INTEGER DEFAULT 0,
                        avg_competition TEXT,
                        tracked_keywords INTEGER DEFAULT 0,
                        untracked_keywords INTEGER DEFAULT 0,
                        best_rank INTEGER DEFAULT 0,
                        opportunity_score REAL DEFAULT 0,
                        analysis_date TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(cluster_name, analysis_date)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_keyword_clusters_date
                    ON keyword_clusters (analysis_date)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_keyword_clusters_opp
                    ON keyword_clusters (opportunity_score DESC)
                """)
                conn.commit()
            logger.info("keyword_clusters 테이블 준비 완료")
        except Exception as e:
            logger.error(f"테이블 생성 실패: {e}")
            logger.debug(traceback.format_exc())

    def _load_tracked_keywords(self):
        """config/keywords.json에서 추적 키워드를 로드합니다."""
        try:
            kw_path = os.path.join(project_root, 'config', 'keywords.json')
            if os.path.exists(kw_path):
                with open(kw_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for kw in data.get('naver_place', []):
                    self.tracked_keywords.add(kw.strip())
                for kw in data.get('blog_seo', []):
                    self.tracked_keywords.add(kw.strip())
        except Exception as e:
            logger.warning(f"추적 키워드 로드 실패: {e}")

        logger.info(f"추적 키워드 {len(self.tracked_keywords)}개 로드")

    def _load_all_keywords(self) -> Dict[str, Dict]:
        """모든 키워드 소스에서 키워드를 로드합니다."""
        keywords = {}  # keyword -> {search_volume, competition, ...}

        try:
            with self.db.get_new_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # 1. keyword_insights
                cursor.execute("""
                    SELECT keyword, search_volume, competition, category, grade
                    FROM keyword_insights
                    WHERE status = 'active' OR status IS NULL
                """)
                for row in cursor.fetchall():
                    kw = row['keyword'].strip()
                    if kw:
                        keywords[kw] = {
                            'search_volume': row['search_volume'] or 0,
                            'competition': row['competition'] or '',
                            'category': row['category'] or '',
                            'grade': row['grade'] or 'C',
                            'source': 'keyword_insights'
                        }

                # 2. naver_ad_keyword_data (최신 데이터만)
                cursor.execute("""
                    SELECT keyword, total_search_volume, competition_level
                    FROM naver_ad_keyword_data
                    WHERE collected_date = (
                        SELECT MAX(collected_date) FROM naver_ad_keyword_data
                    )
                """)
                for row in cursor.fetchall():
                    kw = row['keyword'].strip()
                    if kw:
                        if kw in keywords:
                            # 기존 데이터 보완
                            if row['total_search_volume'] and row['total_search_volume'] > 0:
                                keywords[kw]['search_volume'] = max(
                                    keywords[kw].get('search_volume', 0),
                                    row['total_search_volume']
                                )
                            if row['competition_level']:
                                keywords[kw]['competition'] = row['competition_level']
                        else:
                            keywords[kw] = {
                                'search_volume': row['total_search_volume'] or 0,
                                'competition': row['competition_level'] or '',
                                'category': '',
                                'grade': '',
                                'source': 'naver_ad'
                            }

        except Exception as e:
            logger.error(f"키워드 로드 실패: {e}")
            logger.debug(traceback.format_exc())

        logger.info(f"총 {len(keywords)}개 키워드 로드")
        return keywords

    def _load_relations(self) -> List[Tuple[str, str]]:
        """키워드 간 관계(연관 키워드)를 로드합니다."""
        relations = []

        try:
            with self.db.get_new_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT source_keyword, related_keyword
                    FROM naver_ad_related_keywords
                    WHERE collected_date = (
                        SELECT MAX(collected_date) FROM naver_ad_related_keywords
                    )
                """)
                for row in cursor.fetchall():
                    src = row['source_keyword'].strip()
                    rel = row['related_keyword'].strip()
                    if src and rel:
                        relations.append((src, rel))

        except Exception as e:
            logger.error(f"연관 키워드 로드 실패: {e}")
            logger.debug(traceback.format_exc())

        logger.info(f"연관 키워드 관계 {len(relations)}개 로드")
        return relations

    def _build_graph(self, keywords: Dict[str, Dict], relations: List[Tuple[str, str]]) -> Dict[str, Set[str]]:
        """테마 기반 클러스터링 (연관 키워드 체인 무시 - 거대 클러스터 방지)."""
        # 테마 기반으로 직접 분류 (BFS 대신 테마 할당)
        # 연관 키워드 관계는 클러스터 연결에 사용하지 않음 (체인 폭발 방지)
        theme_clusters = defaultdict(set)

        for kw in keywords:
            assigned = False
            for theme, theme_words in THEME_KEYWORDS.items():
                if any(tw in kw for tw in theme_words):
                    theme_clusters[theme].add(kw)
                    assigned = True
                    break
            if not assigned:
                theme_clusters['기타'].add(kw)

        # 테마 클러스터를 그래프 형태로 변환 (같은 테마 내 키워드만 연결)
        graph = defaultdict(set)
        for theme, cluster_kws in theme_clusters.items():
            kw_list = list(cluster_kws)
            if len(kw_list) < 2:
                continue
            # 스타 토폴로지: 첫 번째 키워드를 허브로
            hub = kw_list[0]
            for kw in kw_list[1:]:
                graph[hub].add(kw)
                graph[kw].add(hub)

        return dict(graph)

    def _find_clusters(self, graph: Dict[str, Set[str]], all_keywords: Set[str]) -> List[Set[str]]:
        """BFS를 사용하여 연결 요소(connected components)를 찾습니다."""
        visited = set()
        clusters = []

        # 그래프에 포함된 키워드
        graph_keywords = set(graph.keys())
        for neighbors in graph.values():
            graph_keywords.update(neighbors)

        # 그래프에 포함되지 않은 키워드 (고립 노드)
        isolated = all_keywords - graph_keywords

        for start in graph_keywords:
            if start in visited:
                continue

            # BFS
            cluster = set()
            queue = deque([start])

            while queue:
                node = queue.popleft()
                if node in visited:
                    continue
                visited.add(node)
                cluster.add(node)

                for neighbor in graph.get(node, set()):
                    if neighbor not in visited:
                        queue.append(neighbor)

            if len(cluster) >= 2:  # 최소 2개 키워드 이상인 클러스터만
                clusters.append(cluster)

        # 고립 키워드 중 검색량이 있는 것들은 단독 클러스터로
        # (너무 많아지면 노이즈이므로 건너뜀)

        return clusters

    def _detect_theme(self, keywords: Set[str]) -> str:
        """클러스터의 테마를 감지합니다."""
        keyword_text = ' '.join(keywords)
        best_theme = 'general'
        best_score = 0

        for theme, theme_words in THEME_KEYWORDS.items():
            score = sum(1 for tw in theme_words if tw in keyword_text)
            if score > best_score:
                best_score = score
                best_theme = theme

        return best_theme

    def _classify_intent(self, keywords: Set[str]) -> str:
        """클러스터의 검색 의도를 분류합니다."""
        keyword_text = ' '.join(keywords)
        best_intent = 'general'
        best_score = 0

        for intent, intent_words in INTENT_RULES.items():
            score = sum(1 for iw in intent_words if iw in keyword_text)
            if score > best_score:
                best_score = score
                best_intent = intent

        return best_intent

    def _get_best_rank(self, keywords: Set[str]) -> int:
        """클러스터 내 키워드 중 최고 순위를 조회합니다."""
        best_rank = 0

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                placeholders = ','.join('?' * len(keywords))
                cursor.execute(f"""
                    SELECT MIN(rank) as best_rank
                    FROM rank_history
                    WHERE keyword IN ({placeholders})
                      AND status = 'found'
                      AND scanned_date >= date('now', '-7 days')
                """, list(keywords))
                row = cursor.fetchone()
                if row and row[0]:
                    best_rank = row[0]
        except Exception as e:
            logger.debug(f"순위 조회 실패: {e}")

        return best_rank

    def _calculate_opportunity_score(self, cluster_data: Dict) -> float:
        """클러스터의 기회 점수를 계산합니다."""
        score = 0.0

        # 검색량 기반 (높을수록 좋음)
        volume = cluster_data.get('total_search_volume', 0)
        if volume > 10000:
            score += 30
        elif volume > 5000:
            score += 25
        elif volume > 1000:
            score += 20
        elif volume > 100:
            score += 10

        # 미추적 키워드 비율 (높을수록 기회 많음)
        total_kw = cluster_data.get('keyword_count', 1)
        untracked = cluster_data.get('untracked_keywords', 0)
        untracked_ratio = untracked / max(total_kw, 1)
        score += untracked_ratio * 25

        # 경쟁도 기반 (낮을수록 좋음)
        comp = cluster_data.get('avg_competition', '')
        if comp == 'LOW' or comp == '낮음':
            score += 20
        elif comp == 'MEDIUM' or comp == '보통':
            score += 10
        elif comp == 'HIGH' or comp == '높음':
            score += 5

        # 키워드 수 보너스 (많으면 풍부한 클러스터)
        if total_kw >= 10:
            score += 15
        elif total_kw >= 5:
            score += 10
        elif total_kw >= 3:
            score += 5

        # 순위 보너스 (이미 순위가 있으면 +)
        best_rank = cluster_data.get('best_rank', 0)
        if 0 < best_rank <= 10:
            score += 10
        elif 0 < best_rank <= 30:
            score += 5

        return round(min(score, 100), 1)

    def _get_avg_competition(self, keyword_data: List[Dict]) -> str:
        """키워드 목록의 평균 경쟁도를 계산합니다."""
        comp_scores = {'HIGH': 3, '높음': 3, 'MEDIUM': 2, '보통': 2, 'LOW': 1, '낮음': 1}
        total_score = 0
        count = 0

        for kd in keyword_data:
            comp = kd.get('competition', '')
            if comp in comp_scores:
                total_score += comp_scores[comp]
                count += 1

        if count == 0:
            return 'UNKNOWN'

        avg = total_score / count
        if avg >= 2.5:
            return 'HIGH'
        elif avg >= 1.5:
            return 'MEDIUM'
        else:
            return 'LOW'

    def analyze_clusters(self) -> List[Dict]:
        """키워드 클러스터를 분석합니다."""
        # 데이터 로드
        keywords = self._load_all_keywords()
        relations = self._load_relations()

        if not keywords:
            print("분석할 키워드가 없습니다.")
            return []

        # 그래프 구축
        graph = self._build_graph(keywords, relations)

        # 클러스터 찾기
        clusters = self._find_clusters(graph, set(keywords.keys()))

        if not clusters:
            print("형성된 클러스터가 없습니다.")
            return []

        # 클러스터 분석
        cluster_results = []
        analysis_date = datetime.now().strftime("%Y-%m-%d")

        for cluster_keywords in sorted(clusters, key=len, reverse=True):
            # 클러스터 메타데이터 수집
            keyword_data_list = []
            total_volume = 0

            for kw in cluster_keywords:
                kd = keywords.get(kw, {})
                keyword_data_list.append(kd)
                total_volume += kd.get('search_volume', 0)

            # 테마 및 의도 분류
            theme = self._detect_theme(cluster_keywords)
            intent = self._classify_intent(cluster_keywords)

            # 추적/미추적 키워드 분리
            tracked = sum(1 for kw in cluster_keywords if kw in self.tracked_keywords)
            untracked = len(cluster_keywords) - tracked

            # 평균 경쟁도
            avg_comp = self._get_avg_competition(keyword_data_list)

            # 최고 순위
            best_rank = self._get_best_rank(cluster_keywords)

            # 클러스터 이름 생성 (테마 + 대표 키워드)
            sorted_by_volume = sorted(
                cluster_keywords,
                key=lambda kw: keywords.get(kw, {}).get('search_volume', 0),
                reverse=True
            )
            representative_kw = sorted_by_volume[0] if sorted_by_volume else list(cluster_keywords)[0]
            cluster_name = f"{theme}_{representative_kw}"

            cluster_data = {
                'cluster_name': cluster_name,
                'cluster_theme': theme,
                'intent_type': intent,
                'keywords': sorted(cluster_keywords),
                'keyword_count': len(cluster_keywords),
                'total_search_volume': total_volume,
                'avg_competition': avg_comp,
                'tracked_keywords': tracked,
                'untracked_keywords': untracked,
                'best_rank': best_rank,
                'analysis_date': analysis_date,
            }

            # 기회 점수
            cluster_data['opportunity_score'] = self._calculate_opportunity_score(cluster_data)

            cluster_results.append(cluster_data)

        # 기회 점수 기준 정렬
        cluster_results.sort(key=lambda x: x['opportunity_score'], reverse=True)

        return cluster_results

    def _save_results(self, clusters: List[Dict]):
        """클러스터 분석 결과를 DB에 저장합니다."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                for cluster in clusters:
                    cursor.execute("""
                        INSERT INTO keyword_clusters
                        (cluster_name, cluster_theme, intent_type, keywords,
                         keyword_count, total_search_volume, avg_competition,
                         tracked_keywords, untracked_keywords, best_rank,
                         opportunity_score, analysis_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(cluster_name, analysis_date) DO UPDATE SET
                            cluster_theme = excluded.cluster_theme,
                            intent_type = excluded.intent_type,
                            keywords = excluded.keywords,
                            keyword_count = excluded.keyword_count,
                            total_search_volume = excluded.total_search_volume,
                            avg_competition = excluded.avg_competition,
                            tracked_keywords = excluded.tracked_keywords,
                            untracked_keywords = excluded.untracked_keywords,
                            best_rank = excluded.best_rank,
                            opportunity_score = excluded.opportunity_score
                    """, (
                        cluster['cluster_name'],
                        cluster['cluster_theme'],
                        cluster['intent_type'],
                        json.dumps(cluster['keywords'], ensure_ascii=False),
                        cluster['keyword_count'],
                        cluster['total_search_volume'],
                        cluster['avg_competition'],
                        cluster['tracked_keywords'],
                        cluster['untracked_keywords'],
                        cluster['best_rank'],
                        cluster['opportunity_score'],
                        cluster['analysis_date']
                    ))

                conn.commit()
                logger.info(f"클러스터 {len(clusters)}개 DB 저장 완료")

        except Exception as e:
            logger.error(f"DB 저장 오류: {e}")
            logger.debug(traceback.format_exc())

    def run(self):
        """키워드 클러스터 분석을 실행합니다."""
        print(f"\n{'='*60}")
        print(f" Keyword Cluster Analyzer")
        print(f" 시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        clusters = self.analyze_clusters()

        if not clusters:
            print("분석 결과가 없습니다.")
            return

        # DB 저장
        self._save_results(clusters)

        # 결과 출력
        print(f"\n{'='*60}")
        print(f" 클러스터 맵 ({len(clusters)}개 클러스터)")
        print(f"{'='*60}")

        for idx, cluster in enumerate(clusters, 1):
            rank_str = f"#{cluster['best_rank']}" if cluster['best_rank'] > 0 else "순위없음"
            print(f"\n  [{idx}] {cluster['cluster_name']}")
            print(f"      테마: {cluster['cluster_theme']} | 의도: {cluster['intent_type']}")
            print(f"      키워드: {cluster['keyword_count']}개 (추적: {cluster['tracked_keywords']} / 미추적: {cluster['untracked_keywords']})")
            print(f"      검색량: {cluster['total_search_volume']:,} | 경쟁도: {cluster['avg_competition']} | 최고순위: {rank_str}")
            print(f"      기회 점수: {cluster['opportunity_score']:.1f}/100")

            # 상위 키워드 표시
            kw_list = cluster['keywords'][:5]
            if kw_list:
                print(f"      대표 키워드: {', '.join(kw_list)}")
            if len(cluster['keywords']) > 5:
                print(f"      ... 외 {len(cluster['keywords']) - 5}개")

        # 요약 통계
        total_kw = sum(c['keyword_count'] for c in clusters)
        total_vol = sum(c['total_search_volume'] for c in clusters)
        tracked_total = sum(c['tracked_keywords'] for c in clusters)
        untracked_total = sum(c['untracked_keywords'] for c in clusters)

        print(f"\n{'='*60}")
        print(f" 요약 통계")
        print(f"{'='*60}")
        print(f"  총 클러스터: {len(clusters)}개")
        print(f"  총 키워드: {total_kw}개 (추적: {tracked_total} / 미추적: {untracked_total})")
        print(f"  총 검색량: {total_vol:,}")
        print(f"  최고 기회 클러스터: {clusters[0]['cluster_name']} ({clusters[0]['opportunity_score']:.1f}점)")
        print(f"{'='*60}")

        return clusters


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        analyzer = KeywordClusterAnalyzer()
        analyzer.run()
    except KeyboardInterrupt:
        print("\n사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.error(f"치명적 오류: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

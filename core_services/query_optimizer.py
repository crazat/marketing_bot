"""
Query Optimizer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 5.0] 성능 최적화 - N+1 쿼리 해결

JOIN 기반 최적화된 쿼리 헬퍼:
- 리드 + 키워드 인사이트 조인
- 바이럴 타겟 + 키워드 조인
- 배치 조회 지원
"""

import sqlite3
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# DB 경로
DB_PATH = Path(__file__).parent.parent / 'db' / 'marketing_data.db'


class QueryOptimizer:
    """
    N+1 쿼리 해결을 위한 최적화된 쿼리 헬퍼

    주요 기능:
    - JOIN 기반 단일 쿼리로 관련 데이터 조회
    - 배치 조회로 다중 ID 효율적 처리
    - 캐싱 가능한 구조
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)

    def _get_connection(self) -> sqlite3.Connection:
        """DB 연결 획득"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def get_leads_with_keywords(
        self,
        status: str = None,
        platform: str = None,
        limit: int = 50,
        offset: int = 0,
        order_by: str = 'scraped_at',
        order_dir: str = 'DESC'
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        리드 + 키워드 인사이트 조인 조회 (N+1 해결)

        기존 패턴 (N+1):
            leads = SELECT * FROM mentions
            for lead in leads:
                keyword_info = SELECT * FROM keyword_insights WHERE keyword = lead.keyword

        최적화 패턴 (JOIN):
            SELECT m.*, k.grade, k.search_volume, k.category
            FROM mentions m
            LEFT JOIN keyword_insights k ON m.keyword = k.keyword

        Args:
            status: 리드 상태 필터
            platform: 플랫폼/소스 필터
            limit: 조회 개수
            offset: 시작 위치
            order_by: 정렬 컬럼
            order_dir: 정렬 방향

        Returns:
            (리드 목록, 전체 개수)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 동적 WHERE 조건 구성
            where_clauses = []
            params = []

            if status:
                where_clauses.append("m.status = ?")
                params.append(status)

            if platform:
                where_clauses.append("(m.source = ? OR m.source LIKE ?)")
                params.extend([platform, f"%{platform}%"])

            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)

            # 전체 개수 조회
            count_sql = f"SELECT COUNT(*) FROM mentions m {where_sql}"
            cursor.execute(count_sql, params)
            total = cursor.fetchone()[0]

            # JOIN 조회 (N+1 해결)
            query = f"""
                SELECT
                    m.id,
                    m.target_name,
                    m.keyword,
                    m.source,
                    m.title,
                    m.content,
                    m.url,
                    m.date_posted,
                    m.scraped_at,
                    m.status,
                    m.memo,
                    m.score,
                    m.score_breakdown,
                    -- 키워드 인사이트 조인
                    k.grade as keyword_grade,
                    k.search_volume as keyword_volume,
                    k.category as keyword_category,
                    k.difficulty as keyword_difficulty,
                    k.opportunity as keyword_opportunity
                FROM mentions m
                LEFT JOIN keyword_insights k ON m.keyword = k.keyword
                {where_sql}
                ORDER BY m.{order_by} {order_dir}
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            cursor.execute(query, params)

            leads = []
            for row in cursor.fetchall():
                lead = dict(row)
                # 키워드 정보 중첩 객체로 구성
                lead['keyword_info'] = {
                    'grade': lead.pop('keyword_grade', None),
                    'volume': lead.pop('keyword_volume', 0),
                    'category': lead.pop('keyword_category', None),
                    'difficulty': lead.pop('keyword_difficulty', 50),
                    'opportunity': lead.pop('keyword_opportunity', 50)
                }
                leads.append(lead)

            conn.close()
            return leads, total

        except Exception as e:
            logger.error(f"리드 조인 조회 실패: {e}")
            conn.close()
            raise

    def get_viral_targets_with_keywords(
        self,
        platform: str = None,
        comment_status: str = None,
        min_score: float = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        바이럴 타겟 + 키워드 인사이트 조인 조회

        Args:
            platform: 플랫폼 필터
            comment_status: 댓글 상태 필터
            min_score: 최소 우선순위 점수
            limit: 조회 개수
            offset: 시작 위치

        Returns:
            (바이럴 타겟 목록, 전체 개수)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            where_clauses = []
            params = []

            if platform:
                where_clauses.append("v.platform = ?")
                params.append(platform)

            if comment_status:
                where_clauses.append("v.comment_status = ?")
                params.append(comment_status)

            if min_score is not None:
                where_clauses.append("v.priority_score >= ?")
                params.append(min_score)

            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)

            # 전체 개수
            count_sql = f"SELECT COUNT(*) FROM viral_targets v {where_sql}"
            cursor.execute(count_sql, params)
            total = cursor.fetchone()[0]

            # JOIN 조회
            # matched_keywords에서 첫 번째 키워드로 조인
            query = f"""
                SELECT
                    v.*,
                    k.grade as keyword_grade,
                    k.search_volume as keyword_volume,
                    k.category as keyword_category
                FROM viral_targets v
                LEFT JOIN keyword_insights k ON k.keyword = v.matched_keyword
                {where_sql}
                ORDER BY v.priority_score DESC
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            cursor.execute(query, params)

            targets = []
            for row in cursor.fetchall():
                target = dict(row)
                target['keyword_info'] = {
                    'grade': target.pop('keyword_grade', None),
                    'volume': target.pop('keyword_volume', 0),
                    'category': target.pop('keyword_category', None)
                }
                targets.append(target)

            conn.close()
            return targets, total

        except Exception as e:
            logger.error(f"바이럴 타겟 조인 조회 실패: {e}")
            conn.close()
            raise

    def batch_get_keyword_info(
        self,
        keywords: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        배치로 키워드 정보 조회 (N+1 해결)

        기존 패턴 (N+1):
            for keyword in keywords:
                info = SELECT * FROM keyword_insights WHERE keyword = ?

        최적화 패턴 (IN 절):
            SELECT * FROM keyword_insights WHERE keyword IN (?, ?, ?)

        Args:
            keywords: 키워드 목록

        Returns:
            {키워드: 정보 딕셔너리} 형태의 매핑
        """
        if not keywords:
            return {}

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # IN 절로 배치 조회
            placeholders = ",".join(["?"] * len(keywords))
            query = f"""
                SELECT keyword, grade, search_volume, category,
                       difficulty, opportunity, trend_status
                FROM keyword_insights
                WHERE keyword IN ({placeholders})
            """
            cursor.execute(query, keywords)

            result = {}
            for row in cursor.fetchall():
                result[row['keyword']] = {
                    'grade': row['grade'],
                    'volume': row['search_volume'],
                    'category': row['category'],
                    'difficulty': row['difficulty'],
                    'opportunity': row['opportunity'],
                    'trend': row['trend_status']
                }

            conn.close()
            return result

        except Exception as e:
            logger.error(f"배치 키워드 조회 실패: {e}")
            conn.close()
            return {}

    def get_rank_history_with_keywords(
        self,
        days: int = 7,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        순위 히스토리 + 키워드 정보 조인 조회

        Args:
            days: 최근 N일
            limit: 최대 조회 개수

        Returns:
            순위 히스토리 목록 (키워드 정보 포함)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = """
                SELECT
                    r.id,
                    r.keyword,
                    r.rank,
                    r.target_name,
                    r.checked_at,
                    r.status,
                    r.date,
                    k.grade as keyword_grade,
                    k.search_volume as keyword_volume,
                    k.category as keyword_category
                FROM rank_history r
                LEFT JOIN keyword_insights k ON r.keyword = k.keyword
                WHERE r.checked_at >= datetime('now', ?)
                ORDER BY r.checked_at DESC
                LIMIT ?
            """
            cursor.execute(query, (f'-{days} days', limit))

            results = []
            for row in cursor.fetchall():
                item = dict(row)
                item['keyword_info'] = {
                    'grade': item.pop('keyword_grade', None),
                    'volume': item.pop('keyword_volume', 0),
                    'category': item.pop('keyword_category', None)
                }
                results.append(item)

            conn.close()
            return results

        except Exception as e:
            logger.error(f"순위 히스토리 조인 조회 실패: {e}")
            conn.close()
            return []


# 싱글톤 인스턴스
_optimizer_instance: Optional[QueryOptimizer] = None


def get_query_optimizer(db_path: str = None) -> QueryOptimizer:
    """QueryOptimizer 싱글톤 인스턴스 반환"""
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = QueryOptimizer(db_path)
    return _optimizer_instance

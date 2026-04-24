"""
Database Migration Manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 1-4] 마이그레이션 버전 관리 시스템
- 스키마 버전 추적
- 마이그레이션 히스토리 관리
- 롤백 지원 (향후 확장)
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Callable, List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / 'db' / 'marketing_data.db'


class Migration:
    """개별 마이그레이션 정의"""

    def __init__(
        self,
        version: str,
        description: str,
        up_sql: List[str] = None,
        up_func: Callable = None,
        down_sql: List[str] = None
    ):
        """
        Args:
            version: 마이그레이션 버전 (예: "001", "002")
            description: 마이그레이션 설명
            up_sql: 적용할 SQL 목록
            up_func: 복잡한 마이그레이션을 위한 콜백 함수
            down_sql: 롤백 SQL 목록 (선택적)
        """
        self.version = version
        self.description = description
        self.up_sql = up_sql or []
        self.up_func = up_func
        self.down_sql = down_sql or []

    def apply(self, cursor: sqlite3.Cursor) -> bool:
        """마이그레이션 적용"""
        try:
            # SQL 문 실행
            for sql in self.up_sql:
                cursor.execute(sql)

            # 콜백 함수 실행
            if self.up_func:
                self.up_func(cursor)

            return True
        except Exception as e:
            logger.error(f"마이그레이션 {self.version} 적용 실패: {e}")
            raise

    def rollback(self, cursor: sqlite3.Cursor) -> bool:
        """마이그레이션 롤백"""
        try:
            for sql in self.down_sql:
                cursor.execute(sql)
            return True
        except Exception as e:
            logger.error(f"마이그레이션 {self.version} 롤백 실패: {e}")
            raise


class MigrationManager:
    """마이그레이션 관리자"""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.migrations: List[Migration] = []
        self._register_migrations()

    def _register_migrations(self):
        """모든 마이그레이션 등록"""
        # 마이그레이션 버전 001: schema_versions 테이블 생성
        self.migrations.append(Migration(
            version="001",
            description="schema_versions 테이블 생성",
            up_sql=[
                """
                CREATE TABLE IF NOT EXISTS schema_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL UNIQUE,
                    description TEXT,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    checksum TEXT
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_schema_versions_version ON schema_versions(version)"
            ]
        ))

        # 마이그레이션 버전 002: comment_templates Phase 5.0 컬럼 추가
        self.migrations.append(Migration(
            version="002",
            description="comment_templates: situation_type, engagement_signal 컬럼 추가",
            up_func=self._migrate_002_comment_templates
        ))

        # 마이그레이션 버전 003: notifications reference_keyword 컬럼 추가
        self.migrations.append(Migration(
            version="003",
            description="notifications: reference_keyword 컬럼 추가",
            up_func=self._migrate_003_notifications
        ))

        # 마이그레이션 버전 004: viral_targets Phase G 컬럼 추가
        self.migrations.append(Migration(
            version="004",
            description="viral_targets: 전환 어트리뷰션 관련 컬럼 추가",
            up_func=self._migrate_004_viral_targets
        ))

        # 마이그레이션 버전 005: automation_rules 테이블 검증 컬럼
        self.migrations.append(Migration(
            version="005",
            description="automation_rules: last_triggered 컬럼 추가",
            up_func=self._migrate_005_automation_rules
        ))

        # 마이그레이션 버전 006: 데이터베이스 인덱스 최적화
        self.migrations.append(Migration(
            version="006",
            description="[Phase 3-5] 주요 테이블 인덱스 최적화",
            up_func=self._migrate_006_index_optimization
        ))

        # 마이그레이션 버전 007: competitor_reviews 별점 컬럼 추가
        self.migrations.append(Migration(
            version="007",
            description="[고도화 A-2] competitor_reviews: star_rating, reviewer_name 컬럼 추가",
            up_func=self._migrate_007_star_rating
        ))

        # 마이그레이션 버전 013: 환자 전환 추적 테이블
        self.migrations.append(Migration(
            version="013",
            description="[고도화 V3-3] patient_attribution 테이블 생성",
            up_sql=[
                """
                CREATE TABLE IF NOT EXISTS patient_attribution (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    source_channel TEXT NOT NULL,
                    patient_type TEXT DEFAULT 'new',
                    treatment_type TEXT,
                    revenue INTEGER DEFAULT 0,
                    coupon_code TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_attribution_channel ON patient_attribution(source_channel)",
                "CREATE INDEX IF NOT EXISTS idx_attribution_date ON patient_attribution(date)",
                """
                CREATE TABLE IF NOT EXISTS marketing_spend (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    month TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    spend INTEGER DEFAULT 0,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(month, channel)
                )
                """,
            ]
        ))

        # 마이그레이션 버전 011: 바이럴 속도 감지 테이블
        self.migrations.append(Migration(
            version="011",
            description="[고도화 C-3] viral_velocity 테이블 생성",
            up_sql=[
                """
                CREATE TABLE IF NOT EXISTS viral_velocity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL,
                    platform TEXT DEFAULT 'all',
                    time_window TEXT NOT NULL,
                    mention_count INTEGER DEFAULT 0,
                    moving_average REAL DEFAULT 0,
                    std_deviation REAL DEFAULT 0,
                    z_score REAL DEFAULT 0,
                    spike_detected BOOLEAN DEFAULT 0,
                    spike_magnitude REAL DEFAULT 0,
                    sample_urls TEXT DEFAULT '[]',
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_viral_velocity_keyword ON viral_velocity(keyword)",
                "CREATE INDEX IF NOT EXISTS idx_viral_velocity_spike ON viral_velocity(spike_detected, detected_at)",
            ]
        ))

        # 마이그레이션 버전 012: 의료광고 규정 체크 테이블
        self.migrations.append(Migration(
            version="012",
            description="[고도화 C-5] content_compliance_checks 테이블 생성",
            up_sql=[
                """
                CREATE TABLE IF NOT EXISTS content_compliance_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_type TEXT NOT NULL,
                    content_title TEXT,
                    content_url TEXT,
                    content_text TEXT,
                    ai_check_result TEXT DEFAULT 'pending',
                    compliance_issues TEXT DEFAULT '[]',
                    severity TEXT DEFAULT 'info',
                    recommendations TEXT,
                    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_compliance_result ON content_compliance_checks(ai_check_result)",
                "CREATE INDEX IF NOT EXISTS idx_compliance_severity ON content_compliance_checks(severity)",
            ]
        ))

        # 마이그레이션 버전 010: AI 검색 가시성 테이블
        self.migrations.append(Migration(
            version="010",
            description="[고도화 B-2] ai_search_visibility 테이블 생성",
            up_sql=[
                """
                CREATE TABLE IF NOT EXISTS ai_search_visibility (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL,
                    search_engine TEXT DEFAULT 'naver',
                    ai_briefing_detected BOOLEAN DEFAULT 0,
                    ai_briefing_position TEXT,
                    briefing_content_summary TEXT,
                    source_urls TEXT DEFAULT '[]',
                    competitor_mentioned TEXT DEFAULT '[]',
                    our_mention BOOLEAN DEFAULT 0,
                    our_mention_context TEXT,
                    total_results_count INTEGER DEFAULT 0,
                    smartblock_types TEXT DEFAULT '[]',
                    scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_ai_search_keyword ON ai_search_visibility(keyword)",
                "CREATE INDEX IF NOT EXISTS idx_ai_search_scanned ON ai_search_visibility(scanned_at)",
                "CREATE INDEX IF NOT EXISTS idx_ai_search_our_mention ON ai_search_visibility(our_mention)",
            ]
        ))

        # 마이그레이션 버전 009: 리뷰 자동 응답 테이블
        self.migrations.append(Migration(
            version="009",
            description="[고도화 B-4] review_responses 테이블 생성",
            up_sql=[
                """
                CREATE TABLE IF NOT EXISTS review_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_id INTEGER,
                    competitor_name TEXT,
                    review_content TEXT,
                    star_rating REAL,
                    sentiment TEXT DEFAULT 'neutral',
                    topics TEXT DEFAULT '[]',
                    draft_response TEXT,
                    final_response TEXT,
                    status TEXT DEFAULT 'draft',
                    telegram_sent BOOLEAN DEFAULT 0,
                    response_time_minutes INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    approved_at TIMESTAMP,
                    posted_at TIMESTAMP
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_review_responses_status ON review_responses(status)",
                "CREATE INDEX IF NOT EXISTS idx_review_responses_created ON review_responses(created_at)",
            ]
        ))

        # 마이그레이션 버전 008: 행동 데이터 점수 테이블
        self.migrations.append(Migration(
            version="008",
            description="[고도화 B-3] place_behavior_scores 테이블 생성",
            up_sql=[
                """
                CREATE TABLE IF NOT EXISTS place_behavior_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL UNIQUE,
                    phone_clicks INTEGER DEFAULT 0,
                    direction_clicks INTEGER DEFAULT 0,
                    booking_clicks INTEGER DEFAULT 0,
                    save_clicks INTEGER DEFAULT 0,
                    share_clicks INTEGER DEFAULT 0,
                    review_clicks INTEGER DEFAULT 0,
                    website_clicks INTEGER DEFAULT 0,
                    total_views INTEGER DEFAULT 0,
                    place_views INTEGER DEFAULT 0,
                    search_views INTEGER DEFAULT 0,
                    popularity_score REAL DEFAULT 0,
                    freshness_score REAL DEFAULT 0,
                    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_behavior_scores_date ON place_behavior_scores(date)",
            ]
        ))

    def _column_exists(self, cursor: sqlite3.Cursor, table: str, column: str) -> bool:
        """컬럼 존재 여부 확인"""
        cursor.execute(f"PRAGMA table_info({table})")
        columns = {row[1] for row in cursor.fetchall()}
        return column in columns

    def _table_exists(self, cursor: sqlite3.Cursor, table: str) -> bool:
        """테이블 존재 여부 확인"""
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        )
        return cursor.fetchone() is not None

    def _migrate_002_comment_templates(self, cursor: sqlite3.Cursor):
        """comment_templates Phase 5.0 컬럼"""
        if not self._table_exists(cursor, 'comment_templates'):
            return

        if not self._column_exists(cursor, 'comment_templates', 'situation_type'):
            cursor.execute("ALTER TABLE comment_templates ADD COLUMN situation_type TEXT DEFAULT 'general'")
            logger.info("  - comment_templates: situation_type 컬럼 추가됨")

        if not self._column_exists(cursor, 'comment_templates', 'engagement_signal'):
            cursor.execute("ALTER TABLE comment_templates ADD COLUMN engagement_signal TEXT DEFAULT 'any'")
            logger.info("  - comment_templates: engagement_signal 컬럼 추가됨")

    def _migrate_003_notifications(self, cursor: sqlite3.Cursor):
        """notifications reference_keyword 컬럼"""
        if not self._table_exists(cursor, 'notifications'):
            return

        if not self._column_exists(cursor, 'notifications', 'reference_keyword'):
            cursor.execute("ALTER TABLE notifications ADD COLUMN reference_keyword TEXT")
            logger.info("  - notifications: reference_keyword 컬럼 추가됨")

    def _migrate_004_viral_targets(self, cursor: sqlite3.Cursor):
        """viral_targets 전환 어트리뷰션 컬럼"""
        if not self._table_exists(cursor, 'viral_targets'):
            return

        columns_to_add = [
            ("conversion_chain", "TEXT"),
            ("attribution_first", "TEXT"),
            ("attribution_last", "TEXT"),
            ("conversion_score", "REAL DEFAULT 0"),
            ("days_to_convert", "INTEGER"),
            ("touchpoints_count", "INTEGER DEFAULT 0")
        ]

        for col_name, col_type in columns_to_add:
            if not self._column_exists(cursor, 'viral_targets', col_name):
                cursor.execute(f"ALTER TABLE viral_targets ADD COLUMN {col_name} {col_type}")
                logger.info(f"  - viral_targets: {col_name} 컬럼 추가됨")

    def _migrate_005_automation_rules(self, cursor: sqlite3.Cursor):
        """automation_rules last_triggered 컬럼"""
        if not self._table_exists(cursor, 'automation_rules'):
            return

        if not self._column_exists(cursor, 'automation_rules', 'last_triggered'):
            cursor.execute("ALTER TABLE automation_rules ADD COLUMN last_triggered TIMESTAMP")
            logger.info("  - automation_rules: last_triggered 컬럼 추가됨")

    def _migrate_006_index_optimization(self, cursor: sqlite3.Cursor):
        """[Phase 3-5] 주요 테이블 인덱스 최적화"""

        # 인덱스 존재 여부 확인 헬퍼
        def index_exists(idx_name: str) -> bool:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                (idx_name,)
            )
            return cursor.fetchone() is not None

        indexes_to_create = [
            # keyword_insights 테이블 인덱스
            ("idx_keyword_insights_keyword", "keyword_insights", "keyword"),
            ("idx_keyword_insights_grade", "keyword_insights", "grade"),
            ("idx_keyword_insights_category", "keyword_insights", "category"),
            ("idx_keyword_insights_status", "keyword_insights", "status"),
            ("idx_keyword_insights_created", "keyword_insights", "created_at"),

            # rank_history 테이블 인덱스
            ("idx_rank_history_keyword", "rank_history", "keyword"),
            ("idx_rank_history_scanned_at", "rank_history", "scanned_at"),
            ("idx_rank_history_status", "rank_history", "status"),
            ("idx_rank_history_device", "rank_history", "device_type"),

            # viral_targets 테이블 인덱스
            ("idx_viral_targets_platform", "viral_targets", "platform"),
            ("idx_viral_targets_status", "viral_targets", "status"),
            ("idx_viral_targets_priority", "viral_targets", "priority_score"),
            ("idx_viral_targets_created", "viral_targets", "created_at"),
            ("idx_viral_targets_matched_kw", "viral_targets", "matched_keyword"),

            # competitor_reviews 테이블 인덱스
            ("idx_competitor_reviews_name", "competitor_reviews", "competitor_name"),
            ("idx_competitor_reviews_date", "competitor_reviews", "review_date"),

            # scan_runs 테이블 인덱스
            ("idx_scan_runs_mode", "scan_runs", "mode"),
            ("idx_scan_runs_status", "scan_runs", "status"),
            ("idx_scan_runs_started", "scan_runs", "started_at"),
        ]

        created_count = 0
        for idx_name, table_name, column_name in indexes_to_create:
            if not self._table_exists(cursor, table_name):
                continue

            if not index_exists(idx_name):
                try:
                    cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name}({column_name})")
                    logger.info(f"  - 인덱스 생성: {idx_name}")
                    created_count += 1
                except sqlite3.OperationalError as e:
                    # 컬럼이 없는 경우 무시
                    logger.debug(f"  - 인덱스 생성 스킵 ({idx_name}): {e}")

        # 복합 인덱스
        compound_indexes = [
            ("idx_rank_history_keyword_date", "rank_history", "keyword, scanned_at"),
            ("idx_viral_targets_platform_status", "viral_targets", "platform, status"),
            ("idx_keyword_insights_grade_category", "keyword_insights", "grade, category"),
        ]

        for idx_name, table_name, columns in compound_indexes:
            if not self._table_exists(cursor, table_name):
                continue

            if not index_exists(idx_name):
                try:
                    cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name}({columns})")
                    logger.info(f"  - 복합 인덱스 생성: {idx_name}")
                    created_count += 1
                except sqlite3.OperationalError as e:
                    logger.debug(f"  - 복합 인덱스 생성 스킵 ({idx_name}): {e}")

        logger.info(f"  총 {created_count}개 인덱스 생성됨")

    def _migrate_007_star_rating(self, cursor: sqlite3.Cursor):
        """[고도화 A-2] competitor_reviews에 별점 및 리뷰어명 컬럼 추가"""
        if not self._table_exists(cursor, 'competitor_reviews'):
            return

        columns_to_add = [
            ("star_rating", "REAL DEFAULT NULL"),
            ("reviewer_name", "TEXT"),
        ]

        for col_name, col_type in columns_to_add:
            if not self._column_exists(cursor, 'competitor_reviews', col_name):
                cursor.execute(f"ALTER TABLE competitor_reviews ADD COLUMN {col_name} {col_type}")
                logger.info(f"  - competitor_reviews: {col_name} 컬럼 추가됨")

        # star_rating 인덱스 추가
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_competitor_reviews_star_rating'"
        )
        if not cursor.fetchone():
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_competitor_reviews_star_rating "
                "ON competitor_reviews(star_rating)"
            )
            logger.info("  - 인덱스 생성: idx_competitor_reviews_star_rating")

    def get_applied_versions(self, cursor: sqlite3.Cursor) -> set:
        """적용된 마이그레이션 버전 목록 조회"""
        try:
            cursor.execute("SELECT version FROM schema_versions")
            return {row[0] for row in cursor.fetchall()}
        except sqlite3.OperationalError:
            # schema_versions 테이블이 없는 경우
            return set()

    def run_migrations(self) -> Dict[str, Any]:
        """모든 마이그레이션 실행"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        result = {
            "applied": [],
            "skipped": [],
            "errors": []
        }

        try:
            # 적용된 버전 확인
            applied_versions = self.get_applied_versions(cursor)

            for migration in self.migrations:
                if migration.version in applied_versions:
                    result["skipped"].append({
                        "version": migration.version,
                        "description": migration.description
                    })
                    continue

                try:
                    logger.info(f"📦 마이그레이션 {migration.version} 적용 중: {migration.description}")
                    migration.apply(cursor)

                    # 버전 기록 (schema_versions 테이블이 생성된 후에만)
                    if migration.version != "001":
                        cursor.execute(
                            "INSERT INTO schema_versions (version, description) VALUES (?, ?)",
                            (migration.version, migration.description)
                        )
                    else:
                        # 001 마이그레이션 자체를 기록
                        cursor.execute(
                            "INSERT INTO schema_versions (version, description) VALUES (?, ?)",
                            (migration.version, migration.description)
                        )

                    result["applied"].append({
                        "version": migration.version,
                        "description": migration.description
                    })
                    logger.info(f"✅ 마이그레이션 {migration.version} 완료")

                except Exception as e:
                    result["errors"].append({
                        "version": migration.version,
                        "description": migration.description,
                        "error": str(e)
                    })
                    logger.error(f"❌ 마이그레이션 {migration.version} 실패: {e}")
                    conn.rollback()
                    raise

            conn.commit()

        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()

        return result

    def get_status(self) -> Dict[str, Any]:
        """마이그레이션 상태 조회"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            applied_versions = self.get_applied_versions(cursor)

            # 상세 정보 조회
            applied_details = []
            try:
                cursor.execute(
                    "SELECT version, description, applied_at FROM schema_versions ORDER BY version"
                )
                applied_details = [dict(row) for row in cursor.fetchall()]
            except sqlite3.OperationalError:
                pass

            pending = []
            for migration in self.migrations:
                if migration.version not in applied_versions:
                    pending.append({
                        "version": migration.version,
                        "description": migration.description
                    })

            return {
                "current_version": max(applied_versions) if applied_versions else None,
                "total_migrations": len(self.migrations),
                "applied_count": len(applied_versions),
                "pending_count": len(pending),
                "applied": applied_details,
                "pending": pending
            }
        finally:
            conn.close()


def run_all_migrations() -> Dict[str, Any]:
    """모든 마이그레이션 실행 (외부 호출용)"""
    manager = MigrationManager()
    return manager.run_migrations()


def get_migration_status() -> Dict[str, Any]:
    """마이그레이션 상태 조회 (외부 호출용)"""
    manager = MigrationManager()
    return manager.get_status()

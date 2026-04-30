import sqlite3
import os
import logging
import hashlib
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta

logger = logging.getLogger("DatabaseManager")


class DatabaseManager:
    """
    [성능 최적화] 싱글톤 패턴 + 스레드 안전 커넥션 관리
    - 단일 인스턴스로 DB 연결 재사용
    - get_connection() 컨텍스트 매니저로 안전한 연결 관리
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path=None):
        """싱글톤 인스턴스 생성"""
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path=None):
        # 이미 초기화되었으면 스킵 (싱글톤)
        if self._initialized:
            return

        if db_path is None:
            # 환경 변수로 DB 경로 오버라이드 가능
            db_override = os.environ.get('MARKETING_BOT_DB_PATH')
            if db_override:
                self.db_path = db_override
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                self.db_path = os.path.join(base_dir, "marketing_data.db")
                # 항상 Windows DB 사용 (WSL 환경 감지 제거됨)
        else:
            self.db_path = db_path

        self._conn_lock = threading.Lock()
        self._init_db()
        self._initialized = True
        # [S3] Repository 레이어 lazy 캐시 (신규 코드에서 사용 권장)
        self._viral_target_repo = None
        self._lead_repo = None
        self._competitor_repo = None
        self._keyword_repo = None
        logger.info(f"DatabaseManager 싱글톤 초기화 완료: {self.db_path}")

    @property
    def viral_targets(self):
        """[S3] ViralTargetRepository 게터 (lazy).

        새 코드에서 `db.viral_targets.list(...)` 형태로 사용 권장.
        """
        if self._viral_target_repo is None:
            from repositories import ViralTargetRepository
            self._viral_target_repo = ViralTargetRepository(self.db_path)
        return self._viral_target_repo

    @property
    def leads(self):
        """[S3] LeadRepository 게터 (lazy)."""
        if self._lead_repo is None:
            from repositories import LeadRepository
            self._lead_repo = LeadRepository(self.db_path)
        return self._lead_repo

    @property
    def competitors(self):
        """[S3] CompetitorRepository 게터 (lazy)."""
        if self._competitor_repo is None:
            from repositories import CompetitorRepository
            self._competitor_repo = CompetitorRepository(self.db_path)
        return self._competitor_repo

    @property
    def keywords(self):
        """[S3] KeywordRepository 게터 (lazy)."""
        if self._keyword_repo is None:
            from repositories import KeywordRepository
            self._keyword_repo = KeywordRepository(self.db_path)
        return self._keyword_repo

    @contextmanager
    def get_connection(self):
        """
        스레드 안전한 DB 연결 컨텍스트 매니저
        Usage:
            db = DatabaseManager()
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(...)
        """
        # 기존 연결 재사용 (check_same_thread=False로 이미 스레드 안전)
        try:
            yield self.conn
        except Exception as e:
            logger.error(f"DB 작업 오류: {e}")
            raise

    @contextmanager
    def get_new_connection(self):
        """
        [성능 최적화] 새 연결 생성/반환 컨텍스트 매니저
        - 예외 시에도 반드시 conn.close() 호출 → 연결 누수 방지
        - 개별 요청 처리에 적합 (싱글톤 연결과 분리)
        - [Phase 1] WAL 모드 및 busy_timeout 설정으로 동시성 문제 해결
        Usage:
            db = DatabaseManager()
            with db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(...)
        """
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        # [Phase 1] WAL 모드 및 동시성 설정 적용
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")  # 5초 대기
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        # [Robustness] Increase timeout to 30s to handle concurrent writes (File Lock)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        self.cursor = self.conn.cursor()

        # [성능 최적화] WAL 모드 설정 - 동시 읽기/쓰기 성능 향상
        # [W8] 마이그레이션 버전 추적 테이블 — _ensure_wal_mode보다 먼저 준비
        self._ensure_schema_migrations_early()
        self._ensure_wal_mode()

    def _ensure_schema_migrations_early(self):
        """[W8/X3] schema_migrations 테이블 — _ensure_wal_mode 전에 먼저 준비.

        이렇게 하면 _ensure_wal_mode 안에서 baseline 마이그레이션 체크 가능.
        """
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            )
            """
        )
        self.conn.commit()
        self._baseline_migration_applied = self.migration_applied("baseline_v2026_04")

    # 하위 호환: 기존 호출자가 있을 수 있음
    _ensure_schema_migrations = _ensure_schema_migrations_early

    def migration_applied(self, version: str) -> bool:
        """특정 마이그레이션이 이미 적용됐는지 확인."""
        try:
            self.cursor.execute(
                "SELECT 1 FROM schema_migrations WHERE version = ?",
                (version,),
            )
            return self.cursor.fetchone() is not None
        except Exception:
            return False

    def mark_migration(self, version: str, notes: str = "") -> None:
        """마이그레이션 버전 기록."""
        try:
            self.cursor.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, notes) VALUES(?, ?)",
                (version, notes),
            )
            self.conn.commit()
        except Exception as e:
            logger.warning(f"mark_migration failed: {e}")

    def run_guarded_alters(self, version: str, alters: list, notes: str = "") -> bool:
        """[X3] 버전 체크된 ALTER 일괄 실행.

        이미 적용된 version이면 즉시 반환. 그렇지 않으면 각 ALTER 시도하고
        (컬럼 이미 존재 에러는 조용히 무시) 마이그레이션 완료 기록.

        Args:
            version: 마이그레이션 버전 ID (예: "2026.04_add_viral_metrics")
            alters: SQL 문자열 리스트
            notes: 기록용 메모

        Returns:
            새로 실행됐으면 True, 이미 적용됐으면 False
        """
        if self.migration_applied(version):
            return False
        for sql in alters:
            try:
                self.cursor.execute(sql)
            except sqlite3.OperationalError as e:
                # duplicate column 등 이미 있는 경우 무시
                if "duplicate column" not in str(e).lower() and "already exists" not in str(e).lower():
                    logger.warning(f"[migration {version}] {sql[:60]}... → {e}")
        self.conn.commit()
        self.mark_migration(version, notes or f"{len(alters)} ALTERs")
        return True

    def _ensure_wal_mode(self):
        """
        [성능 최적화] SQLite WAL 모드 설정
        - WAL(Write-Ahead Logging): 읽기와 쓰기가 동시에 가능
        - synchronous=NORMAL: 안정성과 성능의 균형
        """
        try:
            self.cursor.execute("PRAGMA journal_mode=WAL")
            self.cursor.execute("PRAGMA synchronous=NORMAL")
            self.cursor.execute("PRAGMA cache_size=-64000")  # 64MB 캐시
            self.cursor.execute("PRAGMA temp_store=MEMORY")
            result = self.cursor.fetchone()
            logger.info(f"SQLite WAL 모드 활성화: {result}")
        except Exception as e:
            logger.warning(f"WAL 모드 설정 실패 (계속 진행): {e}")

        # Table: Mentions (Leads/Reviews)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS mentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_name TEXT,
                keyword TEXT,
                source TEXT,
                title TEXT,
                content TEXT,
                url TEXT UNIQUE,
                date_posted TEXT,
                scraped_at TIMESTAMP,
                status TEXT DEFAULT 'New',
                memo TEXT DEFAULT ''
            )
        ''')

        # Table: Daily Stats (Aggregated Trends)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                target_name TEXT,
                mention_count INTEGER
            )
        ''')

        # Create Rank History Table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS rank_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT,
                rank INTEGER,
                target_name TEXT,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'found',
                total_results INTEGER DEFAULT 0,
                note TEXT DEFAULT '',
                device_type TEXT DEFAULT 'mobile'
            )
        ''')

        # Migration: Add device_type column if not exists
        try:
            self.cursor.execute("SELECT device_type FROM rank_history LIMIT 1")
        except sqlite3.OperationalError:
            self.cursor.execute("ALTER TABLE rank_history ADD COLUMN device_type TEXT DEFAULT 'mobile'")
            self.conn.commit()
            logger.info("Added device_type column to rank_history table")
        
        # Table: Competitor Reviews (for Tactician)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS competitor_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                competitor_name TEXT,
                source TEXT,
                content TEXT,
                sentiment TEXT DEFAULT 'neutral',
                keywords TEXT DEFAULT '[]',
                review_date TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table: Chat Sessions (for History Manager)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table: Chat Messages (for History Manager)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                role TEXT,
                content TEXT,
                meta_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
            )
        ''')
        
        # Table: Insights (for Insight Manager)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                title TEXT,
                content TEXT,
                status TEXT DEFAULT 'active',
                meta_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table: System Logs (for centralized logging)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT,
                module TEXT,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table: Competitors (for competitor tracking)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS competitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                naver_place_id TEXT,
                keywords TEXT DEFAULT '[]',
                last_scraped_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Table: Influencers (for Ambassador V2)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS influencers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                platform TEXT NOT NULL,
                handle TEXT NOT NULL,
                profile_url TEXT,
                followers INTEGER DEFAULT 0,
                avg_engagement REAL DEFAULT 0,
                total_posts INTEGER DEFAULT 0,
                relevance_score INTEGER DEFAULT 0,
                sponsored_experience BOOLEAN DEFAULT FALSE,
                content_categories TEXT DEFAULT '[]',
                contact_email TEXT,
                contact_phone TEXT,
                contact_dm TEXT,
                status TEXT DEFAULT 'discovered',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_contacted_at TIMESTAMP,
                UNIQUE(platform, handle)
            )
        ''')

        # [3단계] Table: Scan History (증분 스캔용)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS scan_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                last_post_date TEXT,
                last_scan_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_collected INTEGER DEFAULT 0,
                UNIQUE(source, source_id)
            )
        ''')

        # Table: Influencer Collaborations
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS influencer_collaborations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                influencer_id INTEGER NOT NULL,
                campaign_name TEXT,
                collaboration_type TEXT,
                start_date TEXT,
                end_date TEXT,
                cost INTEGER DEFAULT 0,
                deliverables TEXT,
                result_url TEXT,
                impressions INTEGER DEFAULT 0,
                clicks INTEGER DEFAULT 0,
                conversions INTEGER DEFAULT 0,
                satisfaction_score INTEGER,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (influencer_id) REFERENCES influencers(id)
            )
        ''')

        # Table: Sentinel Threats (for Reputation Monitoring History)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS sentinel_threats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id TEXT,
                threat_type TEXT,
                keyword TEXT,
                title TEXT,
                url TEXT,
                danger_score INTEGER,
                reason TEXT,
                competitor_name TEXT,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Table: Briefing Runs (for Briefing execution history)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS briefing_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status TEXT DEFAULT 'running',
                tasks_total INTEGER DEFAULT 0,
                tasks_completed INTEGER DEFAULT 0,
                tasks_failed INTEGER DEFAULT 0,
                error_log TEXT,
                execution_time_ms INTEGER DEFAULT 0
            )
        ''')

        # Table: Briefing Task Results (individual task execution records)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS briefing_task_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                task_name TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                duration_ms INTEGER DEFAULT 0,
                error_message TEXT,
                FOREIGN KEY (run_id) REFERENCES briefing_runs(id)
            )
        ''')

        # Table: Viral Targets (for Viral Hunter - 바이럴 마케팅 타겟)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS viral_targets (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                url TEXT UNIQUE,
                title TEXT,
                content_preview TEXT,
                matched_keywords TEXT DEFAULT '[]',
                category TEXT,
                is_commentable BOOLEAN DEFAULT 1,
                comment_status TEXT DEFAULT 'pending',
                generated_comment TEXT,
                priority_score REAL DEFAULT 0,
                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_scanned_at TIMESTAMP,
                scan_count INTEGER DEFAULT 1,
                source_scan_run_id INTEGER DEFAULT 0,
                matched_keyword_grade TEXT,
                matched_keyword_kei REAL DEFAULT 0,
                matched_keyword_priority REAL DEFAULT 0,
                matched_keyword_category TEXT
            )
        ''')

        # 기존 테이블에 컬럼 추가 (마이그레이션)
        try:
            self.cursor.execute("ALTER TABLE viral_targets ADD COLUMN last_scanned_at TIMESTAMP")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        try:
            self.cursor.execute("ALTER TABLE viral_targets ADD COLUMN scan_count INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        # [Phase 1.2] 중복 제거를 위한 content_hash 컬럼 추가
        try:
            self.cursor.execute("ALTER TABLE viral_targets ADD COLUMN content_hash TEXT")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        try:
            self.cursor.execute("ALTER TABLE competitor_reviews ADD COLUMN content_hash TEXT")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        # content_hash 인덱스 생성 (중복 검사 속도 향상)
        try:
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_viral_content_hash ON viral_targets(content_hash)")
        except sqlite3.OperationalError:
            pass  # 인덱스가 이미 있거나 생성 실패

        try:
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_review_content_hash ON competitor_reviews(content_hash)")
        except sqlite3.OperationalError:
            pass  # 인덱스가 이미 있거나 생성 실패

        # image_count 컬럼 추가 (마이그레이션)
        try:
            self.cursor.execute("ALTER TABLE competitor_reviews ADD COLUMN image_count INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        # [Phase 7.0] viral_targets engagement 필드 추가 (Instagram 등)
        try:
            self.cursor.execute("ALTER TABLE viral_targets ADD COLUMN like_count INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        try:
            self.cursor.execute("ALTER TABLE viral_targets ADD COLUMN comment_count INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        try:
            self.cursor.execute("ALTER TABLE viral_targets ADD COLUMN view_count INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        try:
            self.cursor.execute("ALTER TABLE viral_targets ADD COLUMN author TEXT")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        try:
            self.cursor.execute("ALTER TABLE viral_targets ADD COLUMN posted_at TIMESTAMP")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        # Pathfinder Legion -> Viral Hunter 연결 정보 스냅샷
        for col, ctype in [
            ("source_scan_run_id", "INTEGER DEFAULT 0"),
            ("matched_keyword_grade", "TEXT"),
            ("matched_keyword_kei", "REAL DEFAULT 0"),
            ("matched_keyword_priority", "REAL DEFAULT 0"),
            ("matched_keyword_category", "TEXT"),
        ]:
            try:
                self.cursor.execute(f"ALTER TABLE viral_targets ADD COLUMN {col} {ctype}")
            except sqlite3.OperationalError:
                pass

        # [Phase 1.3] 리드 스코어링을 위한 score 컬럼 추가
        try:
            self.cursor.execute("ALTER TABLE mentions ADD COLUMN score INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        try:
            self.cursor.execute("ALTER TABLE mentions ADD COLUMN score_breakdown TEXT DEFAULT '{}'")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        try:
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_score ON mentions(score DESC)")
        except sqlite3.OperationalError:
            pass  # 인덱스가 이미 있거나 생성 실패

        # [Phase 2.1] Table: Events Log (이벤트 버스 로깅)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS events_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                payload TEXT,
                source TEXT DEFAULT 'system',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        try:
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events_log(event_type)")
        except sqlite3.OperationalError:
            pass  # 인덱스가 이미 있거나 생성 실패

        try:
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_created ON events_log(created_at)")
        except sqlite3.OperationalError:
            pass  # 인덱스가 이미 있거나 생성 실패

        # [Phase 2.3] Table: Schedule History (적응형 스케줄링)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module TEXT NOT NULL,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'success',
                duration_seconds INTEGER DEFAULT 0,
                result_summary TEXT,
                error_message TEXT
            )
        ''')

        try:
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_module ON schedule_history(module)")
        except sqlite3.OperationalError:
            pass  # 인덱스가 이미 있거나 생성 실패

        try:
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_status ON schedule_history(status)")
        except sqlite3.OperationalError:
            pass  # 인덱스가 이미 있거나 생성 실패

        # Table: Keyword Insights (for Pathfinder V3 - 키워드 발굴)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS keyword_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT UNIQUE,
                volume INTEGER,
                competition TEXT,
                opp_score REAL,
                tag TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                search_volume INTEGER DEFAULT 0,
                region TEXT DEFAULT '기타',
                category TEXT DEFAULT '기타',
                difficulty INTEGER DEFAULT 50,
                opportunity INTEGER DEFAULT 50,
                priority_v3 REAL DEFAULT 0,
                grade TEXT DEFAULT 'C',
                is_gap_keyword INTEGER DEFAULT 0,
                source TEXT DEFAULT 'legacy',
                trend_slope REAL DEFAULT 0,
                trend_status TEXT DEFAULT 'unknown',
                search_intent TEXT DEFAULT 'unknown',
                document_count INTEGER DEFAULT 0,
                kei REAL DEFAULT 0.0,
                kei_grade TEXT DEFAULT 'C'
            )
        ''')

        # Table: Competitor Weaknesses (경쟁사 약점 분석)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS competitor_weaknesses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                competitor_name TEXT,
                weakness_type TEXT,
                description TEXT,
                severity TEXT DEFAULT 'Medium',
                source_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Table: Opportunity Keywords (약점 기반 기회 키워드)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS opportunity_keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT UNIQUE,
                weakness_type TEXT,
                opportunity_description TEXT,
                priority_score REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Add CRM columns if not exist (Migration)
        try:
            self.cursor.execute("ALTER TABLE mentions ADD COLUMN status TEXT DEFAULT 'New'")
            self.cursor.execute("ALTER TABLE mentions ADD COLUMN memo TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass # Columns likely exist
            
        # Add Image URL column (Phase 19)
        try:
            self.cursor.execute("ALTER TABLE mentions ADD COLUMN image_url TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

        try:
            self.cursor.execute("ALTER TABLE rank_history ADD COLUMN date TEXT")
        except sqlite3.OperationalError:
            pass

        # Migration: Add status, total_results, note columns to rank_history
        try:
            self.cursor.execute("ALTER TABLE rank_history ADD COLUMN status TEXT DEFAULT 'found'")
        except sqlite3.OperationalError:
            pass
        try:
            self.cursor.execute("ALTER TABLE rank_history ADD COLUMN total_results INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            self.cursor.execute("ALTER TABLE rank_history ADD COLUMN note TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
            
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_status_source ON mentions(status, source)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_rank_history_date ON rank_history(date)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_insights_status ON insights(status)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_sentinel_threats_scan_id ON sentinel_threats(scan_id)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_sentinel_threats_detected_at ON sentinel_threats(detected_at)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_briefing_runs_started_at ON briefing_runs(started_at)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_briefing_task_results_run_id ON briefing_task_results(run_id)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_viral_targets_platform ON viral_targets(platform)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_viral_targets_status ON viral_targets(comment_status)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_viral_targets_priority ON viral_targets(priority_score DESC)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_keyword_insights_grade ON keyword_insights(grade)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_keyword_insights_category ON keyword_insights(category)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_keyword_insights_created_at ON keyword_insights(created_at)")

        # 추가 인덱스 (2026-02-05)
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_rank_history_keyword ON rank_history(keyword)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_rank_history_keyword_date ON rank_history(keyword, date)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_platform ON mentions(source)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_competitor_weaknesses_competitor ON competitor_weaknesses(competitor_name)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_competitor_weaknesses_type ON competitor_weaknesses(weakness_type)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_opportunity_keywords_status ON opportunity_keywords(status)")

        # [Phase 3.1] Table: Competitor Knowledge (경쟁사 지식 프로파일)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS competitor_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                competitor_name TEXT NOT NULL,
                knowledge_type TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL DEFAULT 0.8,
                source_analysis_id INTEGER,
                source TEXT DEFAULT 'auto',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_competitor_knowledge_name ON competitor_knowledge(competitor_name)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_competitor_knowledge_type ON competitor_knowledge(knowledge_type)")

        # [Phase 3.2] Table: Agent Actions Log (AI 에이전트 액션 로그)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_actions_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger_event TEXT NOT NULL,
                analysis TEXT,
                recommended_actions TEXT,
                executed_actions TEXT,
                approval_status TEXT DEFAULT 'pending',
                approved_by TEXT,
                execution_result TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                executed_at TIMESTAMP
            )
        ''')

        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_actions_trigger ON agent_actions_log(trigger_event)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_actions_status ON agent_actions_log(approval_status)")

        # [Phase 5.0] Table: Q&A Repository (질문-응답 템플릿)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS qa_repository (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_pattern TEXT NOT NULL,
                question_category TEXT DEFAULT 'general',
                standard_answer TEXT NOT NULL,
                variations TEXT DEFAULT '[]',
                use_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_qa_category ON qa_repository(question_category)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_qa_use_count ON qa_repository(use_count DESC)")

        # [Phase 5.0] Table: Scan Runs (스캔 실행 히스토리)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS scan_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_type TEXT NOT NULL,
                mode TEXT DEFAULT 'unknown',
                target_count INTEGER DEFAULT 0,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status TEXT DEFAULT 'running',
                total_keywords INTEGER DEFAULT 0,
                new_keywords INTEGER DEFAULT 0,
                updated_keywords INTEGER DEFAULT 0,
                s_grade_count INTEGER DEFAULT 0,
                a_grade_count INTEGER DEFAULT 0,
                b_grade_count INTEGER DEFAULT 0,
                c_grade_count INTEGER DEFAULT 0,
                sources_json TEXT DEFAULT '{}',
                categories_json TEXT DEFAULT '{}',
                top_keywords_json TEXT DEFAULT '[]',
                error_message TEXT,
                execution_time_seconds INTEGER DEFAULT 0,
                notes TEXT
            )
        ''')

        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_runs_started ON scan_runs(started_at DESC)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_runs_type ON scan_runs(scan_type)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_runs_status ON scan_runs(status)")

        # keyword_insights에 scan_run_id 컬럼 추가 (마이그레이션)
        try:
            self.cursor.execute("ALTER TABLE keyword_insights ADD COLUMN scan_run_id INTEGER")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        try:
            self.cursor.execute("ALTER TABLE keyword_insights ADD COLUMN last_scan_run_id INTEGER")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_keywords_scan_run ON keyword_insights(scan_run_id)")

        # [Phase 5.0] 성능 최적화 - 추가 인덱스
        # 자주 사용되는 필터 조건에 대한 인덱스
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_status ON mentions(status)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_keyword ON mentions(keyword)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_scraped_at ON mentions(scraped_at DESC)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_rank_history_checked_at ON rank_history(checked_at DESC)")
        # idx_viral_targets_score는 idx_viral_targets_priority와 중복이므로 신규 설치에서는 생성하지 않음
        # (기존 DB의 중복 인덱스는 앱 시작 시 _cleanup_duplicate_indexes에서 제거)
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_viral_targets_scraped_at ON viral_targets(discovered_at DESC)")
        # [Phase 11] home-stats 및 카테고리 필터 가속용 복합 인덱스
        # (idx_viral_targets_category 단독 인덱스는 기존 스키마에 존재)
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_viral_status_category ON viral_targets(comment_status, category)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_viral_discovered_status ON viral_targets(discovered_at DESC, comment_status)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_keyword_insights_kei ON keyword_insights(kei DESC)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_keyword_insights_priority ON keyword_insights(priority_v3 DESC)")

        # 복합 인덱스 (자주 함께 사용되는 필터 조합)
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_status_source ON mentions(status, source)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_viral_status_platform ON viral_targets(comment_status, platform)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_keywords_grade_category ON keyword_insights(grade, category)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_viral_source_scan ON viral_targets(source_scan_run_id)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_viral_matched_keyword ON viral_targets(matched_keyword)")
        # [성능 최적화] rank_history 복합 인덱스 - keyword+status 필터링 최적화
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_rank_history_keyword_status ON rank_history(keyword, status)")

        # [Phase 5.0 성능 최적화] 추가 인덱스
        # rank_history 상태별 필터링 최적화
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_rank_history_status ON rank_history(status)")
        # rank_history 키워드별 시간순 쿼리 최적화
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_rank_history_keyword_checked ON rank_history(keyword, checked_at DESC)")
        # competitor_reviews 경쟁사별 시간순 쿼리 최적화
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_competitor_reviews_name_scraped ON competitor_reviews(competitor_name, scraped_at DESC)")
        # mentions 생성일 기준 정렬 최적화
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_date_posted ON mentions(date_posted DESC)")

        # [M4] 전수 감사에서 지목된 누락 인덱스
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_created_at ON mentions(created_at DESC)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_keyword_created ON mentions(keyword, created_at DESC)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_comp_reviews_competitor ON competitor_reviews(competitor_name)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_comp_reviews_date ON competitor_reviews(scraped_at DESC)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_keyword_insights_keyword ON keyword_insights(keyword)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_runs_status_started ON scan_runs(status, started_at DESC)")

        # [Phase 11] 중복 인덱스 정리 (idx_viral_targets_score == idx_viral_targets_priority)
        try:
            self.cursor.execute("DROP INDEX IF EXISTS idx_viral_targets_score")
        except sqlite3.OperationalError:
            pass

        # [Phase 5.0] comment_templates 테이블 확장 - situation_type, engagement_signal 추가
        try:
            self.cursor.execute("ALTER TABLE comment_templates ADD COLUMN situation_type TEXT DEFAULT 'general'")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        try:
            self.cursor.execute("ALTER TABLE comment_templates ADD COLUMN engagement_signal TEXT DEFAULT 'any'")
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 있으면 무시

        # [Phase 5.0] comment_templates 테이블 생성 (없으면 생성)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS comment_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                situation_type TEXT DEFAULT 'general',
                engagement_signal TEXT DEFAULT 'any',
                use_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # [Phase 6.1] Table: Contact History (컨택 히스토리)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS contact_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL,
                contact_type TEXT NOT NULL DEFAULT 'comment',
                content TEXT,
                platform TEXT,
                template_id INTEGER,
                status TEXT DEFAULT 'sent',
                response TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                responded_at TIMESTAMP,
                notes TEXT,
                FOREIGN KEY (lead_id) REFERENCES mentions(id) ON DELETE CASCADE
            )
        ''')

        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_contact_history_lead ON contact_history(lead_id)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_contact_history_created ON contact_history(created_at DESC)")

        # 초기 템플릿 추가 (없으면 삽입)
        self._seed_comment_templates()

        # [X3] baseline 마이그레이션 기록 (최초 init 시 1회)
        if not self._baseline_migration_applied:
            self.mark_migration(
                "baseline_v2026_04",
                "24개 ALTER TABLE 누적분 — viral_targets/mentions/rank_history/comment_templates 확장"
            )

        self.conn.commit()

    # ============================================
    # [Phase 5.0] 초기 댓글 템플릿 Seed
    # ============================================
    def _seed_comment_templates(self):
        """
        초기 댓글 템플릿 30개+ 추가 (없을 때만)
        카테고리: 다이어트, 피부, 통증, 교통사고, 비대칭, 두통, 일반
        상황: general, question, review, recommendation, comparison
        """
        # 이미 템플릿이 있으면 스킵
        self.cursor.execute("SELECT COUNT(*) FROM comment_templates")
        count = self.cursor.fetchone()[0]
        if count >= 30:
            return

        templates = [
            # === 다이어트 카테고리 ===
            ("다이어트 공감", "저도 다이어트 고민 많았는데, 한의원에서 체질 진단 받으니까 확실히 달랐어요. 체질별로 살 찌는 이유가 다르다더라고요~", "다이어트", "question", "seeking_info"),
            ("산후 다이어트", "산후 다이어트는 특히 몸조리랑 같이 해야 해서 한의원 추천해요. 저도 청주에서 했었는데 효과 좋았어요!", "다이어트", "recommendation", "ready_to_act"),
            ("한약 다이어트 후기", "한약 다이어트 효과 궁금하시죠? 저는 3개월 하니까 체질 자체가 바뀐 느낌이에요. 요요도 없고요~", "다이어트", "question", "seeking_info"),
            ("다이어트 약 부작용", "양약 부작용 걱정되시면 한약도 고려해보세요. 자연 성분이라 속도 편하고 지방분해 효과도 있더라고요", "다이어트", "general", "any"),
            ("살빼기 힘드신 분", "운동해도 안 빠지면 체질 문제일 수 있어요. 저도 그래서 한의원 가서 상담받았는데 도움 많이 됐어요~", "다이어트", "question", "passive"),

            # === 피부 카테고리 ===
            ("여드름 고민", "여드름은 외부 관리만으론 한계가 있어요. 한의원에서 체질 개선 같이 하면 재발도 덜하더라고요~", "피부", "question", "seeking_info"),
            ("피부 트러블", "피부 트러블 오래 가시면 한번 한의원 상담 받아보세요. 근본 원인을 찾아야 낫더라고요", "피부", "general", "any"),
            ("리프팅 효과", "침으로 하는 리프팅도 효과 좋아요! 시술보다 자연스럽고 부작용 없어서 저는 정기적으로 받아요", "피부", "recommendation", "ready_to_act"),
            ("흉터 치료", "흉터도 한의원에서 치료 가능해요. 오래된 흉터도 침+약 병행하면 많이 좋아지더라고요", "피부", "question", "seeking_info"),
            ("피부 건조", "피부가 건조하고 푸석하면 속부터 채워야 해요. 한방 치료로 진액 보충하면 확실히 달라져요~", "피부", "general", "passive"),

            # === 통증/디스크 카테고리 ===
            ("허리 통증", "허리 디스크는 초기에 잡아야 해요. 저도 추나 치료 받고 많이 나아졌어요~", "통증", "question", "seeking_info"),
            ("목디스크 경험", "목디스크 증상이시면 빨리 치료받으세요. 저는 한의원에서 침+추나 받고 이제 거의 정상이에요", "통증", "recommendation", "ready_to_act"),
            ("어깨 통증", "오십견이나 어깨 통증은 한의원 치료가 잘 맞아요. 침+물리치료 병행하면 빨리 나아요", "통증", "general", "any"),
            ("무릎 관절", "무릎 관절 안 좋으시면 봉침 추천해요. 염증 가라앉히는 데 효과 좋더라고요~", "통증", "question", "seeking_info"),
            ("만성 통증", "만성 통증은 양방에서 해결 안 되면 한의원 도움받아보세요. 근본 치료가 필요해요", "통증", "general", "passive"),

            # === 교통사고 카테고리 ===
            ("교통사고 치료", "교통사고 나셨으면 빨리 한의원 가세요! 자보 처리되고, 후유증 예방하려면 초기 치료가 중요해요", "교통사고", "question", "ready_to_act"),
            ("사고 후유증", "사고 후유증 방치하면 나중에 더 아파요. 저도 한의원에서 치료받고 후유증 없이 회복했어요~", "교통사고", "recommendation", "seeking_info"),
            ("자보 한의원", "교통사고는 자보로 한의원 치료비 다 나와요. 걱정 마시고 일단 치료부터 받으세요!", "교통사고", "general", "any"),
            ("교통사고 입원", "교통사고면 입원 치료도 고려하세요. 집중 치료하면 회복 훨씬 빨라요", "교통사고", "question", "seeking_info"),

            # === 비대칭/교정 카테고리 ===
            ("안면비대칭", "안면비대칭은 한의원에서 교정 가능해요! 저도 턱 교정 받았는데 사진 찍으면 확실히 달라요~", "비대칭", "question", "seeking_info"),
            ("체형교정", "자세 안 좋으면 체형 틀어지는데, 추나로 교정하면 자세도 좋아지고 통증도 없어져요", "비대칭", "recommendation", "ready_to_act"),
            ("골반교정", "골반 틀어지면 다리 길이도 달라지고 여러 문제 생겨요. 추나 치료 추천합니다!", "비대칭", "general", "any"),
            ("얼굴비대칭", "얼굴비대칭 고민이시면 한의원 상담 추천해요. 턱관절+안면교정 같이 하면 효과 좋아요", "비대칭", "question", "seeking_info"),

            # === 두통/어지럼 카테고리 ===
            ("만성 두통", "만성 두통은 원인이 다양해요. 한의원에서 정확히 진단받고 치료하면 확실히 나아져요~", "두통", "question", "seeking_info"),
            ("편두통 치료", "편두통 약만 먹으면 일시적이에요. 한방 치료로 근본 원인 잡으면 재발이 줄어들어요", "두통", "recommendation", "ready_to_act"),
            ("어지럼증", "어지럼증이 자주 있으면 한의원 진료 받아보세요. 이석증이나 기타 원인을 찾을 수 있어요", "두통", "general", "any"),
            ("머리 무거움", "머리가 무겁고 맑지 않으면 혈액순환 문제일 수 있어요. 한방 치료로 개선할 수 있답니다~", "두통", "question", "passive"),

            # === 일반 카테고리 ===
            ("한의원 추천", "어디 한의원 가야 할지 고민이시면 후기 많은 곳 추천해요. 직접 가서 상담받아보시면 좋아요~", "일반", "question", "seeking_info"),
            ("첫 방문 팁", "한의원 처음 가시면 현재 증상 자세히 말씀하세요. 체질 진단도 같이 받으면 좋아요!", "일반", "general", "any"),
            ("비용 문의", "한의원 비용은 보험 적용되는 것도 있어서 생각보다 부담 안 돼요. 일단 상담부터 받아보세요~", "일반", "question", "seeking_info"),
            ("치료 기간", "한방 치료는 근본 치료라 시간은 좀 걸려도 재발이 적어요. 꾸준히 하면 효과 확실해요!", "일반", "general", "passive"),
            ("예약 문의", "요즘 한의원 예약 쉬워요. 전화나 카톡으로 문의하시면 친절하게 안내해줘요~", "일반", "recommendation", "ready_to_act"),

            # === 지역 특화 ===
            ("청주 추천", "청주에서 찾으시면 후기 좋은 한의원 몇 군데 있어요. 검색해보시고 방문해보세요~", "일반", "recommendation", "seeking_info"),
            ("청주 한의원", "청주 한의원 다녀봤는데 친절하고 실력 좋더라고요. 고민되시면 한번 상담받아보세요!", "일반", "general", "any"),
        ]

        for name, content, category, situation_type, engagement_signal in templates:
            try:
                self.cursor.execute("""
                    INSERT OR IGNORE INTO comment_templates
                    (name, content, category, situation_type, engagement_signal)
                    VALUES (?, ?, ?, ?, ?)
                """, (name, content, category, situation_type, engagement_signal))
            except Exception as e:
                print(f"[DB] 템플릿 추가 실패: {e}")

    # ============================================
    # [Phase 1.2] 중복 제거 헬퍼 메서드
    # ============================================
    @staticmethod
    def calculate_content_hash(url: str, title: str, content: str = "") -> str:
        """
        URL, 제목, 내용을 기반으로 고유 해시를 생성합니다.
        중복 콘텐츠 감지에 사용됩니다.
        """
        # 정규화: 공백 제거, 소문자 변환
        normalized = f"{url.strip().lower()}|{title.strip().lower()}|{content[:200].strip().lower()}"
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()

    def check_duplicate(self, table: str, content_hash: str) -> bool:
        """
        해당 content_hash가 이미 테이블에 존재하는지 확인합니다.

        Returns:
            True if duplicate exists, False otherwise
        """
        try:
            self.cursor.execute(
                f"SELECT 1 FROM {table} WHERE content_hash = ? LIMIT 1",
                (content_hash,)
            )
            return self.cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"check_duplicate error: {e}")
            return False

    def insert_competitor_review(self, competitor_name: str, source: str, content: str,
                                  sentiment: str = 'neutral', keywords: str = '[]',
                                  review_date: str = None, image_count: int = 0,
                                  star_rating: float = None, reviewer_name: str = None) -> bool:
        """
        경쟁사 리뷰를 중복 방지하여 저장합니다.

        Args:
            competitor_name: 경쟁사 이름
            source: 데이터 출처 (예: 'naver_place_real')
            content: 리뷰 내용
            sentiment: 감성 분석 결과 ('positive', 'negative', 'neutral')
            keywords: 키워드 JSON 문자열
            review_date: 리뷰 작성일
            image_count: 첨부 이미지 수
            star_rating: 별점 (1.0~5.0, None이면 미수집)
            reviewer_name: 리뷰어 이름

        Returns:
            True if inserted (new), False if duplicate or error
        """
        try:
            # 해시 계산
            content_hash = self.calculate_content_hash(
                url=f"{competitor_name}_{source}",
                title=content[:50],
                content=content
            )

            # 중복 체크
            if self.check_duplicate('competitor_reviews', content_hash):
                logger.debug(f"Duplicate review skipped: {content[:30]}...")
                return False

            # 삽입
            if review_date is None:
                review_date = datetime.now().strftime('%Y-%m-%d')

            self.cursor.execute('''
                INSERT INTO competitor_reviews
                (competitor_name, source, content, sentiment, keywords, review_date,
                 content_hash, image_count, star_rating, reviewer_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (competitor_name, source, content, sentiment, keywords, review_date,
                  content_hash, image_count, star_rating, reviewer_name))

            self.conn.commit()
            return True

        except Exception as e:
            logger.error(f"insert_competitor_review error: {e}")
            return False

    def get_duplicate_stats(self) -> dict:
        """
        중복 데이터 통계를 반환합니다.
        """
        stats = {
            'viral_targets': {'total': 0, 'with_hash': 0, 'duplicates': 0},
            'competitor_reviews': {'total': 0, 'with_hash': 0, 'duplicates': 0}
        }

        try:
            # viral_targets 통계
            self.cursor.execute("SELECT COUNT(*) FROM viral_targets")
            stats['viral_targets']['total'] = self.cursor.fetchone()[0]

            self.cursor.execute("SELECT COUNT(*) FROM viral_targets WHERE content_hash IS NOT NULL")
            stats['viral_targets']['with_hash'] = self.cursor.fetchone()[0]

            self.cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT content_hash FROM viral_targets
                    WHERE content_hash IS NOT NULL
                    GROUP BY content_hash HAVING COUNT(*) > 1
                )
            """)
            stats['viral_targets']['duplicates'] = self.cursor.fetchone()[0]

            # competitor_reviews 통계
            self.cursor.execute("SELECT COUNT(*) FROM competitor_reviews")
            stats['competitor_reviews']['total'] = self.cursor.fetchone()[0]

            self.cursor.execute("SELECT COUNT(*) FROM competitor_reviews WHERE content_hash IS NOT NULL")
            stats['competitor_reviews']['with_hash'] = self.cursor.fetchone()[0]

            self.cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT content_hash FROM competitor_reviews
                    WHERE content_hash IS NOT NULL
                    GROUP BY content_hash HAVING COUNT(*) > 1
                )
            """)
            stats['competitor_reviews']['duplicates'] = self.cursor.fetchone()[0]

        except Exception as e:
            logger.error(f"get_duplicate_stats error: {e}")

        return stats

    def log_system_event(self, source: str, message: str, level: str = "INFO"):
        """Logs a system event to the database. Maps 'source' arg to 'module' column."""
        try:
            # Clean message if too long
            if len(message) > 500:
                message = message[:497] + "..."
                
            self.cursor.execute('''
                INSERT INTO system_logs (module, message, level)
                VALUES (?, ?, ?)
            ''', (source, message, level))
            self.conn.commit()
        except Exception as e:
            # Fallback to logger if DB fails
            logger.error(f"Failed to log to DB: {e}")

    def insert_mention(self, data):
        """Insert a new mention. Ignores if URL+content already exists."""
        try:
            # Check duplicates by URL + content (같은 영상의 다른 댓글은 허용)
            self.cursor.execute(
                "SELECT id FROM mentions WHERE url = ? AND content = ?",
                (data['url'], data.get('content', ''))
            )
            if self.cursor.fetchone():
                return False
                
            self.cursor.execute('''
                INSERT INTO mentions (target_name, keyword, source, title, content, url, date_posted, scraped_at, status, memo, image_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'New', ?, ?)
            ''', (
                data.get('target_name'),
                data.get('keyword'),
                data.get('source'),
                data.get('title'),
                data.get('content'),
                data.get('url'),
                data.get('date_posted'),
                datetime.now().isoformat(),
                data.get('memo', ''),  # LeadClassifier 분류 정보 저장
                data.get('image_url', '')
            ))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"❌ DB Error: {e}", exc_info=True)
            return False

    def update_status(self, mention_id, status, memo=None):
        if memo is not None:
            self.cursor.execute("UPDATE mentions SET status = ?, memo = ? WHERE id = ?", (status, memo, mention_id))
        else:
            self.cursor.execute("UPDATE mentions SET status = ? WHERE id = ?", (status, mention_id))
        self.conn.commit()

    # ============================================
    # [4단계] 리드 상태 관리 메서드
    # ============================================
    LEAD_STATUS = ['New', 'Reviewed', 'Responded', 'Converted', 'Closed']

    def get_leads_by_status(self, status: str, source: str = None, limit: int = 50) -> list:
        """상태별 리드 조회."""
        try:
            if source:
                self.cursor.execute('''
                    SELECT id, target_name, keyword, source, title, url, date_posted, status, memo, scraped_at
                    FROM mentions
                    WHERE status = ? AND source = ?
                    ORDER BY scraped_at DESC
                    LIMIT ?
                ''', (status, source, limit))
            else:
                self.cursor.execute('''
                    SELECT id, target_name, keyword, source, title, url, date_posted, status, memo, scraped_at
                    FROM mentions
                    WHERE status = ?
                    ORDER BY scraped_at DESC
                    LIMIT ?
                ''', (status, limit))

            rows = self.cursor.fetchall()
            leads = []
            for row in rows:
                leads.append({
                    'id': row[0],
                    'target_name': row[1],
                    'keyword': row[2],
                    'source': row[3],
                    'title': row[4],
                    'url': row[5],
                    'date_posted': row[6],
                    'status': row[7],
                    'memo': row[8],
                    'scraped_at': row[9]
                })
            return leads
        except Exception as e:
            logger.error(f"get_leads_by_status error: {e}")
            return []

    def get_lead_stats(self) -> dict:
        """리드 통계 조회."""
        try:
            stats = {}
            # 상태별 카운트
            self.cursor.execute('''
                SELECT status, COUNT(*) as cnt
                FROM mentions
                GROUP BY status
            ''')
            for row in self.cursor.fetchall():
                stats[row[0] or 'Unknown'] = row[1]

            # 소스별 카운트
            self.cursor.execute('''
                SELECT source, COUNT(*) as cnt
                FROM mentions
                GROUP BY source
            ''')
            stats['by_source'] = {row[0]: row[1] for row in self.cursor.fetchall()}

            # 오늘 수집
            today = datetime.now().strftime('%Y-%m-%d')
            self.cursor.execute('''
                SELECT COUNT(*) FROM mentions
                WHERE date(scraped_at) = ?
            ''', (today,))
            stats['today_collected'] = self.cursor.fetchone()[0]

            # 총 리드 수
            self.cursor.execute('SELECT COUNT(*) FROM mentions')
            stats['total'] = self.cursor.fetchone()[0]

            return stats
        except Exception as e:
            logger.error(f"get_lead_stats error: {e}")
            return {}

    def bulk_update_status(self, mention_ids: list, status: str, memo: str = None) -> int:
        """다수 리드 상태 일괄 업데이트."""
        try:
            updated = 0
            for mid in mention_ids:
                if memo is not None:
                    self.cursor.execute(
                        "UPDATE mentions SET status = ?, memo = ? WHERE id = ?",
                        (status, memo, mid)
                    )
                else:
                    self.cursor.execute(
                        "UPDATE mentions SET status = ? WHERE id = ?",
                        (status, mid)
                    )
                updated += self.cursor.rowcount
            self.conn.commit()
            return updated
        except Exception as e:
            logger.error(f"bulk_update_status error: {e}")
            return 0

    def insert_rank(self, keyword, rank, target_name="Naver", status="found", total_results=0, note="", device_type="mobile"):
        """
        Insert rank history with detailed status.

        Args:
            keyword: Search keyword
            rank: Actual rank (1-based), 0 if not found
            target_name: Platform name (e.g., "Naver Place")
            status: One of:
                - 'found': Target found at given rank
                - 'not_in_results': Results exist but target not in top N
                - 'no_results': No search results for this keyword
                - 'error': Scraping error occurred
            total_results: Number of results found (for context)
            note: Additional notes (e.g., error message)
            device_type: 'mobile' or 'desktop'
        """
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            self.cursor.execute('''
                INSERT INTO rank_history (date, keyword, rank, target_name, status, total_results, note, device_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (today, keyword, rank, target_name, status, total_results, note, device_type))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"❌ DB Rank Error: {e}", exc_info=True)
            return False

    # ============================================
    # [순위 트렌드 분석] 고급 분석 메서드
    # ============================================
    def get_rank_trends_detailed(self, days: int = 30) -> list:
        """
        일별 순위 변화 상세 조회.

        Returns:
            list: [{'date', 'keyword', 'rank', 'prev_rank', 'change', 'status'}]
        """
        try:
            self.cursor.execute('''
                WITH ranked_data AS (
                    SELECT
                        date,
                        keyword,
                        rank,
                        status,
                        LAG(rank) OVER (PARTITION BY keyword ORDER BY date) as prev_rank
                    FROM rank_history
                    WHERE date >= date('now', ?)
                    AND status = 'found'
                )
                SELECT
                    date,
                    keyword,
                    rank,
                    COALESCE(prev_rank, rank) as prev_rank,
                    COALESCE(prev_rank - rank, 0) as change,
                    status
                FROM ranked_data
                ORDER BY date DESC, keyword
            ''', (f'-{days} days',))

            rows = self.cursor.fetchall()
            return [{
                'date': r[0],
                'keyword': r[1],
                'rank': r[2],
                'prev_rank': r[3],
                'change': r[4],  # 양수 = 상승, 음수 = 하락
                'status': r[5]
            } for r in rows]
        except Exception as e:
            logger.error(f"get_rank_trends_detailed error: {e}")
            return []

    def get_rank_change_summary(self) -> dict:
        """
        순위 상승/하락 키워드 요약 (어제 vs 오늘).

        Returns:
            dict: {
                'rising': [{'keyword', 'change', 'today_rank', 'yesterday_rank'}],
                'falling': [{'keyword', 'change', 'today_rank', 'yesterday_rank'}],
                'stable': [{'keyword', 'rank'}],
                'avg_rank': float,
                'avg_change': float,
                'has_yesterday_data': bool  # 어제 데이터 존재 여부
            }
        """
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

            # 메인 타겟 이름 가져오기 (규림한의원)
            target_name = "규림한의원"
            try:
                from utils import ConfigManager
                cfg = ConfigManager()
                targets_data = cfg.load_targets()
                for t in targets_data.get('targets', []):
                    if t.get('is_main') or "규림" in t['name']:
                        target_name = t['name']
                        break
            except (ImportError, KeyError, TypeError, FileNotFoundError):
                pass  # 설정 로드 실패 시 기본값 사용

            # 어제 데이터 존재 여부 확인
            self.cursor.execute('''
                SELECT COUNT(*) FROM rank_history
                WHERE date = ? AND status = 'found' AND target_name = ?
            ''', (yesterday, target_name))
            yesterday_count = self.cursor.fetchone()[0]

            # 어제 데이터가 없으면 비교 불가
            if yesterday_count == 0:
                # 오늘 데이터만 반환 (stable로 분류)
                self.cursor.execute('''
                    SELECT keyword, rank
                    FROM rank_history
                    WHERE date = ? AND status = 'found' AND target_name = ?
                ''', (today, target_name))
                today_rows = self.cursor.fetchall()

                stable = [{'keyword': kw, 'rank': rank} for kw, rank in today_rows]
                avg_rank = round(sum(r for _, r in today_rows) / len(today_rows), 1) if today_rows else 0

                return {
                    'rising': [],
                    'falling': [],
                    'stable': stable,
                    'rising_count': 0,
                    'falling_count': 0,
                    'avg_rank': avg_rank,
                    'avg_change': 0,
                    'has_yesterday_data': False
                }

            # 오늘과 어제 순위 비교 (INNER JOIN - 양쪽 모두 있는 키워드만)
            self.cursor.execute('''
                WITH today_ranks AS (
                    SELECT keyword, rank
                    FROM rank_history
                    WHERE date = ? AND status = 'found' AND target_name = ?
                ),
                yesterday_ranks AS (
                    SELECT keyword, rank
                    FROM rank_history
                    WHERE date = ? AND status = 'found' AND target_name = ?
                )
                SELECT
                    t.keyword,
                    t.rank as today_rank,
                    y.rank as yesterday_rank,
                    (y.rank - t.rank) as change
                FROM today_ranks t
                INNER JOIN yesterday_ranks y ON t.keyword = y.keyword
            ''', (today, target_name, yesterday, target_name))

            rows = self.cursor.fetchall()

            rising = []
            falling = []
            stable = []
            total_rank = 0
            total_change = 0
            count = 0

            for r in rows:
                keyword, today_rank, yesterday_rank, change = r
                total_rank += today_rank
                total_change += change
                count += 1

                item = {
                    'keyword': keyword,
                    'today_rank': today_rank,
                    'yesterday_rank': yesterday_rank,
                    'change': change
                }

                if change > 0:
                    rising.append(item)
                elif change < 0:
                    falling.append(item)
                else:
                    stable.append({'keyword': keyword, 'rank': today_rank})

            # 변동폭 순으로 정렬
            rising.sort(key=lambda x: x['change'], reverse=True)
            falling.sort(key=lambda x: x['change'])

            return {
                'rising': rising,
                'falling': falling,
                'stable': stable,
                'rising_count': len(rising),
                'falling_count': len(falling),
                'avg_rank': round(total_rank / count, 1) if count > 0 else 0,
                'avg_change': round(total_change / count, 2) if count > 0 else 0,
                'has_yesterday_data': True
            }
        except Exception as e:
            logger.error(f"get_rank_change_summary error: {e}")
            return {
                'rising': [], 'falling': [], 'stable': [],
                'rising_count': 0, 'falling_count': 0,
                'avg_rank': 0, 'avg_change': 0,
                'has_yesterday_data': False
            }

    def get_rank_statistics(self, keyword: str = None) -> dict:
        """
        순위 통계 (평균, 최고, 최저, 트렌드) - 30일 기준.

        Args:
            keyword: 특정 키워드 (None이면 전체)

        Returns:
            dict: {
                'overall': {'avg', 'best', 'worst', 'trend'},
                'by_keyword': {keyword: {'avg', 'best', 'worst', 'trend', 'data_points'}}
            }
        """
        try:
            if keyword:
                # 특정 키워드 통계
                self.cursor.execute('''
                    SELECT
                        AVG(rank) as avg_rank,
                        MIN(rank) as best_rank,
                        MAX(rank) as worst_rank,
                        COUNT(*) as data_points
                    FROM rank_history
                    WHERE keyword = ?
                    AND date >= date('now', '-30 days')
                    AND status = 'found'
                ''', (keyword,))
                row = self.cursor.fetchone()

                # 트렌드 계산 (최근 7일 vs 이전 7일) - 데이터 포인트 충분할 때만
                self.cursor.execute('''
                    SELECT COUNT(DISTINCT date) FROM rank_history
                    WHERE keyword = ?
                    AND date >= date('now', '-7 days')
                    AND status = 'found'
                ''', (keyword,))
                recent_days = self.cursor.fetchone()[0] or 0

                self.cursor.execute('''
                    SELECT COUNT(DISTINCT date) FROM rank_history
                    WHERE keyword = ?
                    AND date >= date('now', '-14 days')
                    AND date < date('now', '-7 days')
                    AND status = 'found'
                ''', (keyword,))
                prev_days = self.cursor.fetchone()[0] or 0

                trend = 0
                trend_label = '-'

                # 양쪽 모두 최소 2일 이상 데이터가 있어야 의미 있는 트렌드
                if recent_days >= 2 and prev_days >= 2:
                    self.cursor.execute('''
                        SELECT AVG(rank) FROM rank_history
                        WHERE keyword = ?
                        AND date >= date('now', '-7 days')
                        AND status = 'found'
                    ''', (keyword,))
                    recent_avg = self.cursor.fetchone()[0] or 0

                    self.cursor.execute('''
                        SELECT AVG(rank) FROM rank_history
                        WHERE keyword = ?
                        AND date >= date('now', '-14 days')
                        AND date < date('now', '-7 days')
                        AND status = 'found'
                    ''', (keyword,))
                    prev_avg = self.cursor.fetchone()[0] or 0

                    if recent_avg and prev_avg:
                        trend = round(prev_avg - recent_avg, 1)
                        trend_label = '상승세' if trend > 0 else ('하락세' if trend < 0 else '유지')

                return {
                    'keyword': keyword,
                    'avg': round(row[0], 1) if row[0] else 0,
                    'best': row[1] or 0,
                    'worst': row[2] or 0,
                    'data_points': row[3] or 0,
                    'trend': trend,  # 양수 = 개선, 음수 = 악화
                    'trend_label': trend_label,
                    'has_trend_data': (recent_days >= 2 and prev_days >= 2)
                }
            else:
                # 전체 통계
                self.cursor.execute('''
                    SELECT
                        keyword,
                        AVG(rank) as avg_rank,
                        MIN(rank) as best_rank,
                        MAX(rank) as worst_rank,
                        COUNT(*) as data_points
                    FROM rank_history
                    WHERE date >= date('now', '-30 days')
                    AND status = 'found'
                    GROUP BY keyword
                ''')
                rows = self.cursor.fetchall()

                by_keyword = {}
                total_avg = 0
                best_overall = 999
                worst_overall = 0

                for r in rows:
                    kw, avg, best, worst, points = r
                    by_keyword[kw] = {
                        'avg': round(avg, 1) if avg else 0,
                        'best': best or 0,
                        'worst': worst or 0,
                        'data_points': points or 0
                    }
                    total_avg += avg if avg else 0
                    if best and best < best_overall:
                        best_overall = best
                    if worst and worst > worst_overall:
                        worst_overall = worst

                # 전체 트렌드 계산 (데이터 포인트 충분할 때만)
                # 최근 7일 데이터 포인트 확인
                self.cursor.execute('''
                    SELECT COUNT(DISTINCT date) FROM rank_history
                    WHERE date >= date('now', '-7 days')
                    AND status = 'found'
                ''')
                recent_days = self.cursor.fetchone()[0] or 0

                # 이전 7일 데이터 포인트 확인
                self.cursor.execute('''
                    SELECT COUNT(DISTINCT date) FROM rank_history
                    WHERE date >= date('now', '-14 days')
                    AND date < date('now', '-7 days')
                    AND status = 'found'
                ''')
                prev_days = self.cursor.fetchone()[0] or 0

                overall_trend = 0
                trend_label = '-'

                # 양쪽 모두 최소 2일 이상 데이터가 있어야 의미 있는 트렌드
                if recent_days >= 2 and prev_days >= 2:
                    self.cursor.execute('''
                        SELECT AVG(rank) FROM rank_history
                        WHERE date >= date('now', '-7 days')
                        AND status = 'found'
                    ''')
                    recent_avg = self.cursor.fetchone()[0] or 0

                    self.cursor.execute('''
                        SELECT AVG(rank) FROM rank_history
                        WHERE date >= date('now', '-14 days')
                        AND date < date('now', '-7 days')
                        AND status = 'found'
                    ''')
                    prev_avg = self.cursor.fetchone()[0] or 0

                    if recent_avg and prev_avg:
                        overall_trend = round(prev_avg - recent_avg, 1)
                        trend_label = '상승세' if overall_trend > 0 else ('하락세' if overall_trend < 0 else '유지')

                return {
                    'overall': {
                        'avg': round(total_avg / len(rows), 1) if rows else 0,
                        'best': best_overall if best_overall < 999 else 0,
                        'worst': worst_overall,
                        'trend': overall_trend,
                        'trend_label': trend_label,
                        'keyword_count': len(rows),
                        'has_trend_data': (recent_days >= 2 and prev_days >= 2)
                    },
                    'by_keyword': by_keyword
                }
        except Exception as e:
            logger.error(f"get_rank_statistics error: {e}")
            return {'overall': {'avg': 0, 'best': 0, 'worst': 0, 'trend': 0}, 'by_keyword': {}}

    # ============================================
    # [Pathfinder ULTRA] 전용 분석 메서드
    # ============================================
    def get_ultra_keywords_summary(self) -> dict:
        """
        ULTRA 모드로 분석된 키워드 요약 통계.

        Returns:
            dict: {
                'total': int,
                'by_grade': {'S': int, 'A': int, 'B': int, 'C': int, 'D': int},
                'by_category': {category: count},
                'by_ring': {ring: count},
                'by_intent': {intent: count},
                'avg_mf_kei': float,
                'top_keywords': [{'keyword', 'kei', 'grade', 'category'}]
            }
        """
        try:
            result = {
                'total': 0,
                'by_grade': {'S': 0, 'A': 0, 'B': 0, 'C': 0, 'D': 0},
                'by_category': {},
                'by_ring': {0: 0, 1: 0, 2: 0, 3: 0},
                'by_intent': {},
                'avg_mf_kei': 0.0,
                'top_keywords': []
            }

            # 전체 ULTRA 키워드 수
            self.cursor.execute('''
                SELECT COUNT(*) FROM keyword_insights
                WHERE source = 'ultra' OR kei > 0
            ''')
            result['total'] = self.cursor.fetchone()[0] or 0

            if result['total'] == 0:
                return result

            # 등급별 분포
            self.cursor.execute('''
                SELECT grade, COUNT(*) FROM keyword_insights
                WHERE source = 'ultra' OR kei > 0
                GROUP BY grade
            ''')
            for row in self.cursor.fetchall():
                grade, count = row
                if grade in result['by_grade']:
                    result['by_grade'][grade] = count

            # 카테고리별 분포
            self.cursor.execute('''
                SELECT category, COUNT(*) FROM keyword_insights
                WHERE source = 'ultra' OR kei > 0
                GROUP BY category
            ''')
            for row in self.cursor.fetchall():
                category, count = row
                result['by_category'][category or '기타'] = count

            # Ring별 분포
            self.cursor.execute('''
                SELECT ring, COUNT(*) FROM keyword_insights
                WHERE source = 'ultra' OR kei > 0
                GROUP BY ring
            ''')
            for row in self.cursor.fetchall():
                ring, count = row
                if ring in result['by_ring']:
                    result['by_ring'][ring] = count

            # 검색 의도별 분포
            self.cursor.execute('''
                SELECT search_intent, COUNT(*) FROM keyword_insights
                WHERE source = 'ultra' OR kei > 0
                GROUP BY search_intent
            ''')
            for row in self.cursor.fetchall():
                intent, count = row
                result['by_intent'][intent or 'unknown'] = count

            # 평균 KEI
            self.cursor.execute('''
                SELECT AVG(kei) FROM keyword_insights
                WHERE (source = 'ultra' OR kei > 0) AND kei > 0
            ''')
            result['avg_mf_kei'] = round(self.cursor.fetchone()[0] or 0, 2)

            # Top 20 키워드 (KEI 점수 순)
            self.cursor.execute('''
                SELECT keyword, kei, grade, category, ring, search_intent, search_volume
                FROM keyword_insights
                WHERE source = 'ultra' OR kei > 0
                ORDER BY kei DESC
                LIMIT 20
            ''')
            for row in self.cursor.fetchall():
                result['top_keywords'].append({
                    'keyword': row[0],
                    'kei': round(row[1] or 0, 2),
                    'grade': row[2],
                    'category': row[3],
                    'ring': row[4],
                    'search_intent': row[5],
                    'search_volume': row[6] or 0
                })

            return result
        except Exception as e:
            logger.error(f"get_ultra_keywords_summary error: {e}")
            return {
                'total': 0, 'by_grade': {}, 'by_category': {},
                'by_ring': {}, 'by_intent': {}, 'avg_mf_kei': 0, 'top_keywords': []
            }

    def get_ultra_keywords_by_category(self, category: str, grade: str = None, limit: int = 50) -> list:
        """
        카테고리별 ULTRA 키워드 조회.

        Args:
            category: 카테고리명 (예: '다이어트', '교통사고_입원')
            grade: 등급 필터 (S, A, B, C, D)
            limit: 최대 반환 개수

        Returns:
            list: [{'keyword', 'kei', 'grade', 'search_volume', ...}]
        """
        try:
            query = '''
                SELECT keyword, kei, grade, search_volume, ring, search_intent, volume
                FROM keyword_insights
                WHERE category = ?
                AND (source = 'ultra' OR kei > 0)
            '''
            params = [category]

            if grade:
                query += " AND grade = ?"
                params.append(grade)

            query += " ORDER BY kei DESC LIMIT ?"
            params.append(limit)

            self.cursor.execute(query, params)

            return [{
                'keyword': r[0],
                'kei': round(r[1] or 0, 2),
                'grade': r[2],
                'search_volume': r[3] or 0,
                'ring': r[4] or 0,
                'search_intent': r[5],
                'supply': r[6] or 0
            } for r in self.cursor.fetchall()]
        except Exception as e:
            logger.error(f"get_ultra_keywords_by_category error: {e}")
            return []

    # ============================================
    # [경쟁사 비교 분석] 고급 분석 메서드
    # ============================================
    def get_competitor_rank_comparison(self, days: int = 30, our_name: str = "규림한의원") -> dict:
        """
        우리 vs 경쟁사 순위 비교 (순위 갭 차트용).

        Returns:
            dict: {
                'keywords': [키워드 목록],
                'our_ranks': {keyword: [날짜별 순위]},
                'competitor_ranks': {competitor: {keyword: [날짜별 순위]}},
                'gap_summary': {keyword: {'avg_gap': float, 'trend': str}}
            }
        """
        try:
            # 우리 순위 데이터
            self.cursor.execute('''
                SELECT date, keyword, rank
                FROM rank_history
                WHERE target_name LIKE ?
                AND date >= date('now', ?)
                AND status = 'found'
                ORDER BY date, keyword
            ''', (f'%{our_name}%', f'-{days} days'))
            our_data = self.cursor.fetchall()

            # 경쟁사 순위 데이터
            self.cursor.execute('''
                SELECT DISTINCT target_name
                FROM rank_history
                WHERE target_name NOT LIKE ?
                AND date >= date('now', ?)
                AND status = 'found'
            ''', (f'%{our_name}%', f'-{days} days'))
            competitors = [r[0] for r in self.cursor.fetchall()]

            # 키워드 목록
            keywords = list(set([r[1] for r in our_data]))

            # 우리 순위 정리
            our_ranks = {}
            for date, keyword, rank in our_data:
                if keyword not in our_ranks:
                    our_ranks[keyword] = []
                our_ranks[keyword].append({'date': date, 'rank': rank})

            # 경쟁사 순위 정리
            competitor_ranks = {}
            for comp in competitors:
                self.cursor.execute('''
                    SELECT date, keyword, rank
                    FROM rank_history
                    WHERE target_name = ?
                    AND date >= date('now', ?)
                    AND status = 'found'
                    ORDER BY date, keyword
                ''', (comp, f'-{days} days'))
                comp_data = self.cursor.fetchall()

                competitor_ranks[comp] = {}
                for date, keyword, rank in comp_data:
                    if keyword not in competitor_ranks[comp]:
                        competitor_ranks[comp][keyword] = []
                    competitor_ranks[comp][keyword].append({'date': date, 'rank': rank})

            # 갭 요약 계산
            gap_summary = {}
            for keyword in keywords:
                our_avg = sum([r['rank'] for r in our_ranks.get(keyword, [])]) / len(our_ranks.get(keyword, [{'rank': 0}])) if our_ranks.get(keyword) else 0
                comp_avgs = []
                for comp in competitors:
                    comp_kw_data = competitor_ranks.get(comp, {}).get(keyword, [])
                    if comp_kw_data:
                        comp_avgs.append(sum([r['rank'] for r in comp_kw_data]) / len(comp_kw_data))

                avg_comp = sum(comp_avgs) / len(comp_avgs) if comp_avgs else 0
                gap = avg_comp - our_avg  # 양수면 우리가 더 좋음

                gap_summary[keyword] = {
                    'our_avg': round(our_avg, 1),
                    'comp_avg': round(avg_comp, 1),
                    'gap': round(gap, 1),
                    'status': '우세' if gap > 0 else ('열세' if gap < 0 else '동등')
                }

            return {
                'keywords': keywords,
                'our_ranks': our_ranks,
                'competitor_ranks': competitor_ranks,
                'competitors': competitors,
                'gap_summary': gap_summary
            }
        except Exception as e:
            logger.error(f"get_competitor_rank_comparison error: {e}")
            return {'keywords': [], 'our_ranks': {}, 'competitor_ranks': {}, 'competitors': [], 'gap_summary': {}}

    def get_keyword_dominance(self, days: int = 7) -> dict:
        """
        키워드별 TOP5 점유 현황 (히트맵용).

        Returns:
            dict: {
                'keywords': [키워드 목록],
                'dominance': {keyword: [{'name': str, 'rank': int, 'is_ours': bool}]}
            }
        """
        try:
            # 최근 N일간 각 키워드별 최신 순위 가져오기
            self.cursor.execute('''
                SELECT keyword, target_name, MIN(rank) as best_rank
                FROM rank_history
                WHERE date >= date('now', ?)
                AND status = 'found'
                AND rank > 0
                GROUP BY keyword, target_name
                ORDER BY keyword, best_rank
            ''', (f'-{days} days',))
            data = self.cursor.fetchall()

            # 키워드별로 그룹화
            keyword_data = {}
            for keyword, target_name, rank in data:
                if keyword not in keyword_data:
                    keyword_data[keyword] = []
                keyword_data[keyword].append({
                    'name': target_name,
                    'rank': rank,
                    'is_ours': '규림' in target_name
                })

            # TOP5만 유지
            dominance = {}
            for keyword, entries in keyword_data.items():
                entries.sort(key=lambda x: x['rank'])
                dominance[keyword] = entries[:5]

            return {
                'keywords': list(keyword_data.keys()),
                'dominance': dominance
            }
        except Exception as e:
            logger.error(f"get_keyword_dominance error: {e}")
            return {'keywords': [], 'dominance': {}}

    def get_competition_intensity(self) -> dict:
        """
        키워드별 경쟁 강도 지수.

        Returns:
            dict: {
                keyword: {
                    'total_competitors': int,
                    'avg_rank_spread': float,
                    'intensity_score': float (0-100),
                    'intensity_label': str
                }
            }
        """
        try:
            # 최근 7일간 데이터
            self.cursor.execute('''
                SELECT keyword, COUNT(DISTINCT target_name) as competitors,
                       MIN(rank) as best, MAX(rank) as worst, AVG(rank) as avg_rank
                FROM rank_history
                WHERE date >= date('now', '-7 days')
                AND status = 'found'
                AND rank > 0
                GROUP BY keyword
            ''')
            data = self.cursor.fetchall()

            result = {}
            for keyword, competitors, best, worst, avg_rank in data:
                spread = worst - best if worst and best else 0
                # 경쟁 강도 계산: 경쟁자 수 * 30 + 순위 밀집도 * 70
                density = max(0, 100 - spread * 10)  # 순위가 밀집되어 있을수록 높음
                intensity = min(100, competitors * 15 + density * 0.5)

                result[keyword] = {
                    'total_competitors': competitors,
                    'best_rank': best,
                    'worst_rank': worst,
                    'avg_rank': round(avg_rank, 1) if avg_rank else 0,
                    'rank_spread': spread,
                    'intensity_score': round(intensity, 1),
                    'intensity_label': '치열' if intensity >= 70 else ('보통' if intensity >= 40 else '여유')
                }

            return result
        except Exception as e:
            logger.error(f"get_competition_intensity error: {e}")
            return {}

    # ============================================
    # [시각화] 고급 시각화용 데이터 메서드
    # ============================================
    def get_rank_calendar_data(self, days: int = 30) -> dict:
        """
        히트맵 달력용 일별 순위 데이터.

        Returns:
            dict: {
                'dates': [날짜 목록],
                'keywords': [키워드 목록],
                'data': [[키워드별 일별 순위 2D 배열]],
                'changes': [[일별 변화량 2D 배열]]
            }
        """
        try:
            self.cursor.execute('''
                SELECT date, keyword, MIN(rank) as rank
                FROM rank_history
                WHERE date >= date('now', ?)
                AND status = 'found'
                GROUP BY date, keyword
                ORDER BY date, keyword
            ''', (f'-{days} days',))
            rows = self.cursor.fetchall()

            if not rows:
                return {'dates': [], 'keywords': [], 'data': [], 'changes': []}

            # 데이터 정리
            date_set = sorted(set(r[0] for r in rows))
            keyword_set = sorted(set(r[1] for r in rows))

            # 2D 배열 생성 (키워드 x 날짜)
            data = []
            changes = []
            for keyword in keyword_set:
                row_data = []
                row_changes = []
                prev_rank = None
                for date in date_set:
                    rank = next((r[2] for r in rows if r[0] == date and r[1] == keyword), None)
                    row_data.append(rank if rank else 0)
                    if prev_rank and rank:
                        row_changes.append(prev_rank - rank)  # 양수 = 상승
                    else:
                        row_changes.append(0)
                    prev_rank = rank
                data.append(row_data)
                changes.append(row_changes)

            return {
                'dates': date_set,
                'keywords': keyword_set,
                'data': data,
                'changes': changes
            }
        except Exception as e:
            logger.error(f"get_rank_calendar_data error: {e}")
            return {'dates': [], 'keywords': [], 'data': [], 'changes': []}

    def get_radar_chart_data(self, our_name: str = "규림한의원") -> dict:
        """
        경쟁 레이더 차트용 데이터.

        Returns:
            dict: {
                'keywords': [키워드 목록],
                'our_scores': [우리 점수 (100 - 순위*10)],
                'competitors': {name: [점수 목록]}
            }
        """
        try:
            # 최근 7일 평균 순위 기준
            self.cursor.execute('''
                SELECT keyword, target_name, AVG(rank) as avg_rank
                FROM rank_history
                WHERE date >= date('now', '-7 days')
                AND status = 'found'
                GROUP BY keyword, target_name
            ''')
            rows = self.cursor.fetchall()

            if not rows:
                return {'keywords': [], 'our_scores': [], 'competitors': {}}

            # 키워드 목록
            keywords = sorted(set(r[0] for r in rows))

            # 점수 계산 (100 - 순위*10, 최소 0)
            def rank_to_score(rank):
                return max(0, 100 - (rank * 10)) if rank else 0

            # 우리 점수
            our_scores = []
            for kw in keywords:
                our_rank = next((r[2] for r in rows if r[0] == kw and our_name in r[1]), None)
                our_scores.append(rank_to_score(our_rank) if our_rank else 0)

            # 경쟁사 점수
            competitors = {}
            comp_names = set(r[1] for r in rows if our_name not in r[1])
            for comp in comp_names:
                scores = []
                for kw in keywords:
                    rank = next((r[2] for r in rows if r[0] == kw and r[1] == comp), None)
                    scores.append(rank_to_score(rank) if rank else 0)
                if any(s > 0 for s in scores):  # 최소 1개 키워드 데이터 있는 경쟁사만
                    competitors[comp] = scores

            return {
                'keywords': keywords,
                'our_scores': our_scores,
                'competitors': competitors
            }
        except Exception as e:
            logger.error(f"get_radar_chart_data error: {e}")
            return {'keywords': [], 'our_scores': [], 'competitors': {}}

    def get_realtime_stats(self) -> dict:
        """
        실시간 대시보드용 핵심 통계.

        Returns:
            dict: {
                'total_leads': int,
                'today_leads': int,
                'avg_rank': float,
                'best_keyword': str,
                'worst_keyword': str,
                'active_threats': int,
                'last_update': str
            }
        """
        try:
            stats = {}

            # 총 리드 수
            self.cursor.execute('SELECT COUNT(*) FROM mentions')
            stats['total_leads'] = self.cursor.fetchone()[0]

            # 오늘 리드
            self.cursor.execute('''
                SELECT COUNT(*) FROM mentions
                WHERE date(scraped_at) = date('now')
            ''')
            stats['today_leads'] = self.cursor.fetchone()[0]

            # 평균 순위 (오늘)
            self.cursor.execute('''
                SELECT AVG(rank), MIN(rank), MAX(rank)
                FROM rank_history
                WHERE date = date('now')
                AND status = 'found'
            ''')
            row = self.cursor.fetchone()
            stats['avg_rank'] = round(row[0], 1) if row[0] else 0
            stats['best_rank'] = row[1] or 0
            stats['worst_rank'] = row[2] or 0

            # 최고/최악 키워드
            self.cursor.execute('''
                SELECT keyword, rank FROM rank_history
                WHERE date = date('now') AND status = 'found'
                ORDER BY rank ASC LIMIT 1
            ''')
            best = self.cursor.fetchone()
            stats['best_keyword'] = f"{best[0]} ({best[1]}위)" if best else "-"

            self.cursor.execute('''
                SELECT keyword, rank FROM rank_history
                WHERE date = date('now') AND status = 'found'
                ORDER BY rank DESC LIMIT 1
            ''')
            worst = self.cursor.fetchone()
            stats['worst_keyword'] = f"{worst[0]} ({worst[1]}위)" if worst else "-"

            # 활성 위협
            self.cursor.execute('''
                SELECT COUNT(*) FROM sentinel_threats
                WHERE date(detected_at) = date('now')
            ''')
            stats['active_threats'] = self.cursor.fetchone()[0]

            # 마지막 업데이트
            stats['last_update'] = datetime.now().strftime("%H:%M:%S")

            return stats
        except Exception as e:
            logger.error(f"get_realtime_stats error: {e}")
            return {
                'total_leads': 0, 'today_leads': 0, 'avg_rank': 0,
                'best_keyword': '-', 'worst_keyword': '-',
                'active_threats': 0, 'last_update': '-'
            }

    # ============================================
    # [Instagram 경쟁사 분석] 메서드
    # ============================================
    def insert_instagram_competitor(self, data: dict) -> bool:
        """
        Instagram 경쟁사 포스트를 DB에 저장.

        Args:
            data: {
                'competitor_name': str,
                'username': str,
                'post_id': str,
                'post_url': str,
                'caption': str,
                'hashtags': list,
                'like_count': int,
                'comment_count': int,
                'media_type': str,
                'posted_at': str
            }
        """
        try:
            # 테이블 존재 확인 및 생성
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS instagram_competitors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    competitor_name TEXT,
                    username TEXT,
                    post_id TEXT UNIQUE,
                    post_url TEXT,
                    caption TEXT,
                    hashtags TEXT,
                    like_count INTEGER DEFAULT 0,
                    comment_count INTEGER DEFAULT 0,
                    engagement_rate REAL DEFAULT 0,
                    media_type TEXT,
                    posted_at TEXT,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            hashtags_str = ','.join(data.get('hashtags', []))

            self.cursor.execute('''
                INSERT OR REPLACE INTO instagram_competitors
                (competitor_name, username, post_id, post_url, caption, hashtags,
                 like_count, comment_count, media_type, posted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get('competitor_name', ''),
                data.get('username', ''),
                data.get('post_id', ''),
                data.get('post_url', ''),
                data.get('caption', ''),
                hashtags_str,
                data.get('like_count', 0),
                data.get('comment_count', 0),
                data.get('media_type', 'IMAGE'),
                data.get('posted_at', '')
            ))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"insert_instagram_competitor error: {e}")
            return False

    def get_instagram_competitor_stats(self, days: int = 30) -> dict:
        """
        Instagram 경쟁사 통계 조회.

        Returns:
            dict: {
                'competitors': [{
                    'name': str,
                    'username': str,
                    'post_count': int,
                    'avg_likes': float,
                    'avg_comments': float,
                    'top_hashtags': list,
                    'posting_frequency': float (posts/week)
                }],
                'total_posts': int,
                'our_comparison': dict
            }
        """
        try:
            # 테이블 존재 확인
            self.cursor.execute('''
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='instagram_competitors'
            ''')
            if not self.cursor.fetchone():
                return {'competitors': [], 'total_posts': 0}

            # 경쟁사별 통계
            self.cursor.execute('''
                SELECT
                    competitor_name,
                    username,
                    COUNT(*) as post_count,
                    AVG(like_count) as avg_likes,
                    AVG(comment_count) as avg_comments,
                    MIN(posted_at) as first_post,
                    MAX(posted_at) as last_post
                FROM instagram_competitors
                WHERE scraped_at >= date('now', ?)
                GROUP BY competitor_name, username
                ORDER BY avg_likes DESC
            ''', (f'-{days} days',))
            rows = self.cursor.fetchall()

            competitors = []
            for r in rows:
                name, username, count, avg_likes, avg_comments, first, last = r

                # 해시태그 분석
                self.cursor.execute('''
                    SELECT hashtags FROM instagram_competitors
                    WHERE competitor_name = ? AND scraped_at >= date('now', ?)
                ''', (name, f'-{days} days'))
                all_hashtags = []
                for row in self.cursor.fetchall():
                    if row[0]:
                        all_hashtags.extend(row[0].split(','))

                # 빈도 계산 (상위 10개)
                from collections import Counter
                hashtag_counts = Counter([h.strip() for h in all_hashtags if h.strip()])
                top_hashtags = [{'tag': h, 'count': c} for h, c in hashtag_counts.most_common(10)]

                # 포스팅 빈도 계산
                weeks = days / 7
                freq = round(count / weeks, 1) if weeks > 0 else 0

                competitors.append({
                    'name': name,
                    'username': username,
                    'post_count': count,
                    'avg_likes': round(avg_likes, 1) if avg_likes else 0,
                    'avg_comments': round(avg_comments, 1) if avg_comments else 0,
                    'top_hashtags': top_hashtags,
                    'posting_frequency': freq
                })

            # 총 포스트 수
            self.cursor.execute('''
                SELECT COUNT(*) FROM instagram_competitors
                WHERE scraped_at >= date('now', ?)
            ''', (f'-{days} days',))
            total = self.cursor.fetchone()[0]

            return {
                'competitors': competitors,
                'total_posts': total
            }
        except Exception as e:
            logger.error(f"get_instagram_competitor_stats error: {e}")
            return {'competitors': [], 'total_posts': 0}

    def get_instagram_hashtag_analysis(self, days: int = 30) -> dict:
        """
        경쟁사가 사용하는 해시태그 분석.

        Returns:
            dict: {
                'popular_hashtags': [{'tag', 'count', 'avg_engagement'}],
                'unique_hashtags': [우리가 안 쓰는 해시태그],
                'overlap_hashtags': [공통 해시태그]
            }
        """
        try:
            self.cursor.execute('''
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='instagram_competitors'
            ''')
            if not self.cursor.fetchone():
                return {'popular_hashtags': [], 'unique_hashtags': [], 'overlap_hashtags': []}

            # 모든 해시태그 수집
            self.cursor.execute('''
                SELECT hashtags, like_count, comment_count
                FROM instagram_competitors
                WHERE scraped_at >= date('now', ?)
            ''', (f'-{days} days',))
            rows = self.cursor.fetchall()

            hashtag_data = {}  # {tag: {'count': n, 'total_engagement': n}}
            for hashtags_str, likes, comments in rows:
                if not hashtags_str:
                    continue
                engagement = (likes or 0) + (comments or 0)
                for tag in hashtags_str.split(','):
                    tag = tag.strip()
                    if not tag:
                        continue
                    if tag not in hashtag_data:
                        hashtag_data[tag] = {'count': 0, 'total_engagement': 0}
                    hashtag_data[tag]['count'] += 1
                    hashtag_data[tag]['total_engagement'] += engagement

            # 인기 해시태그 (사용 빈도순)
            popular = []
            for tag, data in sorted(hashtag_data.items(), key=lambda x: x[1]['count'], reverse=True)[:20]:
                avg_eng = data['total_engagement'] / data['count'] if data['count'] > 0 else 0
                popular.append({
                    'tag': tag,
                    'count': data['count'],
                    'avg_engagement': round(avg_eng, 1)
                })

            return {
                'popular_hashtags': popular,
                'total_unique_tags': len(hashtag_data),
                'hashtag_data': hashtag_data
            }
        except Exception as e:
            logger.error(f"get_instagram_hashtag_analysis error: {e}")
            return {'popular_hashtags': [], 'total_unique_tags': 0}

    def get_instagram_content_analysis(self, days: int = 30) -> dict:
        """
        경쟁사 콘텐츠 분석 (인기 포스트, 콘텐츠 유형 등).

        Returns:
            dict: {
                'top_posts': [상위 참여율 포스트],
                'content_types': {'IMAGE': n, 'VIDEO': n, 'CAROUSEL': n},
                'posting_patterns': {'monday': n, 'tuesday': n, ...}
            }
        """
        try:
            self.cursor.execute('''
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='instagram_competitors'
            ''')
            if not self.cursor.fetchone():
                return {'top_posts': [], 'content_types': {}, 'posting_patterns': {}}

            # 인기 포스트 (참여율 기준)
            self.cursor.execute('''
                SELECT competitor_name, username, post_url, caption,
                       like_count, comment_count, media_type, posted_at
                FROM instagram_competitors
                WHERE scraped_at >= date('now', ?)
                ORDER BY (like_count + comment_count) DESC
                LIMIT 10
            ''', (f'-{days} days',))

            top_posts = []
            for r in self.cursor.fetchall():
                top_posts.append({
                    'competitor': r[0],
                    'username': r[1],
                    'url': r[2],
                    'caption': (r[3] or '')[:100] + '...' if r[3] and len(r[3]) > 100 else r[3],
                    'likes': r[4],
                    'comments': r[5],
                    'type': r[6],
                    'posted_at': r[7]
                })

            # 콘텐츠 유형 분포
            self.cursor.execute('''
                SELECT media_type, COUNT(*) as cnt
                FROM instagram_competitors
                WHERE scraped_at >= date('now', ?)
                GROUP BY media_type
            ''', (f'-{days} days',))
            content_types = {r[0]: r[1] for r in self.cursor.fetchall()}

            return {
                'top_posts': top_posts,
                'content_types': content_types
            }
        except Exception as e:
            logger.error(f"get_instagram_content_analysis error: {e}")
            return {'top_posts': [], 'content_types': {}}

    # ============================================
    # [3단계] 증분 스캔 관련 메서드
    # ============================================
    def get_last_scan(self, source: str, source_id: str) -> dict:
        """마지막 스캔 정보 조회."""
        try:
            self.cursor.execute('''
                SELECT last_post_date, last_scan_at, total_collected
                FROM scan_history
                WHERE source = ? AND source_id = ?
            ''', (source, source_id))
            row = self.cursor.fetchone()
            if row:
                return {
                    'last_post_date': row[0],
                    'last_scan_at': row[1],
                    'total_collected': row[2]
                }
            return None
        except Exception as e:
            logger.error(f"get_last_scan error: {e}")
            return None

    def update_scan_history(self, source: str, source_id: str, last_post_date: str, count: int):
        """스캔 히스토리 업데이트 (UPSERT)."""
        try:
            self.cursor.execute('''
                INSERT INTO scan_history (source, source_id, last_post_date, last_scan_at, total_collected)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source, source_id) DO UPDATE SET
                    last_post_date = excluded.last_post_date,
                    last_scan_at = excluded.last_scan_at,
                    total_collected = total_collected + excluded.total_collected
            ''', (source, source_id, last_post_date, datetime.now().isoformat(), count))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"update_scan_history error: {e}")
            return False

    # ============================================
    # [Sentinel] 위협 히스토리 관련 메서드
    # ============================================
    def insert_sentinel_threat(self, threat_data: dict) -> bool:
        """Sentinel 위협을 DB에 저장합니다."""
        try:
            self.cursor.execute('''
                INSERT INTO sentinel_threats
                (scan_id, threat_type, keyword, title, url, danger_score, reason, competitor_name, detected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                threat_data.get('scan_id'),
                threat_data.get('type'),
                threat_data.get('keyword'),
                threat_data.get('title'),
                threat_data.get('url'),
                threat_data.get('score'),
                threat_data.get('reason'),
                threat_data.get('competitor_name'),
                datetime.now().isoformat()
            ))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"insert_sentinel_threat error: {e}")
            return False

    def get_sentinel_history(self, days: int = 7, threat_type: str = None) -> list:
        """최근 N일간의 Sentinel 위협 히스토리를 조회합니다."""
        try:
            if threat_type:
                self.cursor.execute('''
                    SELECT id, scan_id, threat_type, keyword, title, url, danger_score, reason, competitor_name, detected_at
                    FROM sentinel_threats
                    WHERE detected_at >= datetime('now', ?)
                    AND threat_type = ?
                    ORDER BY detected_at DESC
                ''', (f'-{days} days', threat_type))
            else:
                self.cursor.execute('''
                    SELECT id, scan_id, threat_type, keyword, title, url, danger_score, reason, competitor_name, detected_at
                    FROM sentinel_threats
                    WHERE detected_at >= datetime('now', ?)
                    ORDER BY detected_at DESC
                ''', (f'-{days} days',))

            rows = self.cursor.fetchall()
            threats = []
            for row in rows:
                threats.append({
                    'id': row[0],
                    'scan_id': row[1],
                    'type': row[2],
                    'keyword': row[3],
                    'title': row[4],
                    'url': row[5],
                    'score': row[6],
                    'reason': row[7],
                    'competitor_name': row[8],
                    'detected_at': row[9]
                })
            return threats
        except Exception as e:
            logger.error(f"get_sentinel_history error: {e}")
            return []

    # ============================================
    # [경쟁사 약점 분석] 메서드
    # ============================================
    def insert_competitor_weakness(self, data: dict) -> bool:
        """
        경쟁사 약점 데이터를 DB에 저장.

        Args:
            data: {
                'competitor_name': str,
                'source': str (review/blog/cafe),
                'weakness_type': str (서비스/가격/시설/대기시간/효과),
                'original_text': str,
                'weakness_keywords': list,
                'opportunity_keywords': list,
                'sentiment_score': float (-1 to 1),
                'source_url': str
            }
        """
        try:
            # 테이블 존재 확인 및 생성
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS competitor_weaknesses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    competitor_name TEXT,
                    source TEXT,
                    weakness_type TEXT,
                    original_text TEXT,
                    weakness_keywords TEXT,
                    opportunity_keywords TEXT,
                    sentiment_score REAL DEFAULT 0,
                    source_url TEXT,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'new'
                )
            ''')

            # 기회 키워드 테이블
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS opportunity_keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT UNIQUE,
                    source_weakness_id INTEGER,
                    competitor_name TEXT,
                    weakness_type TEXT,
                    priority_score REAL DEFAULT 50,
                    content_suggestion TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    used_at TIMESTAMP,
                    status TEXT DEFAULT 'pending'
                )
            ''')

            weakness_kw_str = ','.join(data.get('weakness_keywords', []))
            opportunity_kw_str = ','.join(data.get('opportunity_keywords', []))

            self.cursor.execute('''
                INSERT INTO competitor_weaknesses
                (competitor_name, source, weakness_type, original_text,
                 weakness_keywords, opportunity_keywords, sentiment_score, source_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get('competitor_name', ''),
                data.get('source', ''),
                data.get('weakness_type', ''),
                data.get('original_text', ''),
                weakness_kw_str,
                opportunity_kw_str,
                data.get('sentiment_score', 0),
                data.get('source_url', '')
            ))

            weakness_id = self.cursor.lastrowid

            # 기회 키워드도 저장
            for kw in data.get('opportunity_keywords', []):
                try:
                    self.cursor.execute('''
                        INSERT OR IGNORE INTO opportunity_keywords
                        (keyword, source_weakness_id, competitor_name, weakness_type, content_suggestion)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        kw,
                        weakness_id,
                        data.get('competitor_name', ''),
                        data.get('weakness_type', ''),
                        data.get('content_suggestion', '')
                    ))
                except sqlite3.IntegrityError:
                    pass  # 중복 키워드는 무시

            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"insert_competitor_weakness error: {e}")
            return False

    def get_competitor_weaknesses(self, days: int = 30, competitor: str = None) -> list:
        """
        경쟁사 약점 데이터 조회.

        Returns:
            list: [{'competitor_name', 'weakness_type', 'count', 'keywords', ...}]
        """
        try:
            self.cursor.execute('''
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='competitor_weaknesses'
            ''')
            if not self.cursor.fetchone():
                return []

            if competitor:
                self.cursor.execute('''
                    SELECT competitor_name, weakness_type, original_text,
                           weakness_keywords, opportunity_keywords, sentiment_score,
                           source_url, analyzed_at
                    FROM competitor_weaknesses
                    WHERE analyzed_at >= date('now', ?)
                    AND competitor_name LIKE ?
                    ORDER BY analyzed_at DESC
                ''', (f'-{days} days', f'%{competitor}%'))
            else:
                self.cursor.execute('''
                    SELECT competitor_name, weakness_type, original_text,
                           weakness_keywords, opportunity_keywords, sentiment_score,
                           source_url, analyzed_at
                    FROM competitor_weaknesses
                    WHERE analyzed_at >= date('now', ?)
                    ORDER BY analyzed_at DESC
                ''', (f'-{days} days',))

            rows = self.cursor.fetchall()
            return [{
                'competitor_name': r[0],
                'weakness_type': r[1],
                'original_text': r[2],
                'weakness_keywords': r[3].split(',') if r[3] else [],
                'opportunity_keywords': r[4].split(',') if r[4] else [],
                'sentiment_score': r[5],
                'source_url': r[6],
                'analyzed_at': r[7]
            } for r in rows]
        except Exception as e:
            logger.error(f"get_competitor_weaknesses error: {e}")
            return []

    def get_weakness_summary(self) -> dict:
        """
        경쟁사 약점 요약 통계.

        Returns:
            dict: {
                'by_competitor': {name: {'count': n, 'top_weakness': str}},
                'by_type': {type: count},
                'total_opportunities': int,
                'top_opportunity_keywords': list
            }
        """
        try:
            self.cursor.execute('''
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='competitor_weaknesses'
            ''')
            if not self.cursor.fetchone():
                return {'by_competitor': {}, 'by_type': {}, 'total_opportunities': 0}

            # 경쟁사별 통계
            self.cursor.execute('''
                SELECT competitor_name, weakness_type, COUNT(*) as cnt
                FROM competitor_weaknesses
                WHERE analyzed_at >= date('now', '-30 days')
                GROUP BY competitor_name, weakness_type
                ORDER BY cnt DESC
            ''')
            rows = self.cursor.fetchall()

            by_competitor = {}
            by_type = {}
            for name, wtype, cnt in rows:
                if name not in by_competitor:
                    by_competitor[name] = {'count': 0, 'weaknesses': {}}
                by_competitor[name]['count'] += cnt
                by_competitor[name]['weaknesses'][wtype] = cnt

                by_type[wtype] = by_type.get(wtype, 0) + cnt

            # 기회 키워드 통계
            self.cursor.execute('''
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='opportunity_keywords'
            ''')
            if self.cursor.fetchone():
                self.cursor.execute('''
                    SELECT keyword, priority_score, competitor_name, weakness_type
                    FROM opportunity_keywords
                    WHERE status = 'pending'
                    ORDER BY priority_score DESC
                    LIMIT 20
                ''')
                opportunity_rows = self.cursor.fetchall()
                top_opportunities = [{
                    'keyword': r[0],
                    'priority': r[1],
                    'competitor': r[2],
                    'type': r[3]
                } for r in opportunity_rows]

                self.cursor.execute('SELECT COUNT(*) FROM opportunity_keywords WHERE status = ?', ('pending',))
                total_opp = self.cursor.fetchone()[0]
            else:
                top_opportunities = []
                total_opp = 0

            return {
                'by_competitor': by_competitor,
                'by_type': by_type,
                'total_opportunities': total_opp,
                'top_opportunity_keywords': top_opportunities
            }
        except Exception as e:
            logger.error(f"get_weakness_summary error: {e}")
            return {'by_competitor': {}, 'by_type': {}, 'total_opportunities': 0}

    def get_opportunity_keywords(self, status: str = 'pending', limit: int = 50) -> list:
        """
        기회 키워드 조회.

        Args:
            status: 'pending', 'used', 'all'
            limit: 최대 결과 수

        Returns:
            list: [{'keyword', 'priority', 'competitor', 'suggestion', ...}]
        """
        try:
            self.cursor.execute('''
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='opportunity_keywords'
            ''')
            if not self.cursor.fetchone():
                return []

            if status == 'all':
                self.cursor.execute('''
                    SELECT keyword, priority_score, competitor_name, weakness_type,
                           content_suggestion, created_at, status
                    FROM opportunity_keywords
                    ORDER BY priority_score DESC
                    LIMIT ?
                ''', (limit,))
            else:
                self.cursor.execute('''
                    SELECT keyword, priority_score, competitor_name, weakness_type,
                           content_suggestion, created_at, status
                    FROM opportunity_keywords
                    WHERE status = ?
                    ORDER BY priority_score DESC
                    LIMIT ?
                ''', (status, limit))

            rows = self.cursor.fetchall()
            return [{
                'keyword': r[0],
                'priority': r[1],
                'competitor': r[2],
                'weakness_type': r[3],
                'suggestion': r[4],
                'created_at': r[5],
                'status': r[6]
            } for r in rows]
        except Exception as e:
            logger.error(f"get_opportunity_keywords error: {e}")
            return []

    def mark_opportunity_used(self, keyword: str) -> bool:
        """기회 키워드를 '사용됨'으로 표시."""
        try:
            self.cursor.execute('''
                UPDATE opportunity_keywords
                SET status = 'used', used_at = ?
                WHERE keyword = ?
            ''', (datetime.now().isoformat(), keyword))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"mark_opportunity_used error: {e}")
            return False

    def get_stats_by_date(self, start_date=None):
        """Get aggregated stats for charting."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = '''
            SELECT date(scraped_at) as date, target_name, COUNT(*) as count
            FROM mentions
            GROUP BY date(scraped_at), target_name
            ORDER BY date DESC
        '''
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        return rows

    # ============================================
    # Briefing Run Management Methods
    # ============================================
    def create_briefing_run(self, tasks_total: int) -> int:
        """새 Briefing 실행 레코드를 생성하고 ID를 반환합니다."""
        try:
            self.cursor.execute('''
                INSERT INTO briefing_runs (started_at, status, tasks_total)
                VALUES (?, 'running', ?)
            ''', (datetime.now().isoformat(), tasks_total))
            self.conn.commit()
            return self.cursor.lastrowid
        except Exception as e:
            logger.error(f"create_briefing_run error: {e}")
            return -1

    def update_briefing_run(self, run_id: int, status: str, tasks_completed: int = 0,
                           tasks_failed: int = 0, error_log: str = None,
                           execution_time_ms: int = 0) -> bool:
        """Briefing 실행 레코드를 업데이트합니다."""
        try:
            self.cursor.execute('''
                UPDATE briefing_runs
                SET status = ?, completed_at = ?, tasks_completed = ?,
                    tasks_failed = ?, error_log = ?, execution_time_ms = ?
                WHERE id = ?
            ''', (status, datetime.now().isoformat(), tasks_completed,
                  tasks_failed, error_log, execution_time_ms, run_id))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"update_briefing_run error: {e}")
            return False

    def create_task_result(self, run_id: int, task_name: str) -> int:
        """새 태스크 결과 레코드를 생성합니다."""
        try:
            self.cursor.execute('''
                INSERT INTO briefing_task_results (run_id, task_name, status, started_at)
                VALUES (?, ?, 'running', ?)
            ''', (run_id, task_name, datetime.now().isoformat()))
            self.conn.commit()
            return self.cursor.lastrowid
        except Exception as e:
            logger.error(f"create_task_result error: {e}")
            return -1

    def update_task_result(self, task_id: int, status: str, duration_ms: int = 0,
                          error_message: str = None) -> bool:
        """태스크 결과 레코드를 업데이트합니다."""
        try:
            self.cursor.execute('''
                UPDATE briefing_task_results
                SET status = ?, completed_at = ?, duration_ms = ?, error_message = ?
                WHERE id = ?
            ''', (status, datetime.now().isoformat(), duration_ms, error_message, task_id))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"update_task_result error: {e}")
            return False

    def get_briefing_runs(self, limit: int = 10) -> list:
        """최근 Briefing 실행 기록을 조회합니다."""
        try:
            self.cursor.execute('''
                SELECT id, started_at, completed_at, status, tasks_total,
                       tasks_completed, tasks_failed, error_log, execution_time_ms
                FROM briefing_runs
                ORDER BY started_at DESC
                LIMIT ?
            ''', (limit,))
            rows = self.cursor.fetchall()
            return [{
                'id': r[0], 'started_at': r[1], 'completed_at': r[2],
                'status': r[3], 'tasks_total': r[4], 'tasks_completed': r[5],
                'tasks_failed': r[6], 'error_log': r[7], 'execution_time_ms': r[8]
            } for r in rows]
        except Exception as e:
            logger.error(f"get_briefing_runs error: {e}")
            return []

    def get_task_results(self, run_id: int) -> list:
        """특정 Briefing 실행의 태스크 결과를 조회합니다."""
        try:
            self.cursor.execute('''
                SELECT id, task_name, status, started_at, completed_at,
                       duration_ms, error_message
                FROM briefing_task_results
                WHERE run_id = ?
                ORDER BY started_at
            ''', (run_id,))
            rows = self.cursor.fetchall()
            return [{
                'id': r[0], 'task_name': r[1], 'status': r[2],
                'started_at': r[3], 'completed_at': r[4],
                'duration_ms': r[5], 'error_message': r[6]
            } for r in rows]
        except Exception as e:
            logger.error(f"get_task_results error: {e}")
            return []

    def get_briefing_stats(self, days: int = 7) -> dict:
        """Briefing 실행 통계를 조회합니다."""
        try:
            stats = {}

            # 최근 N일간 실행 수
            self.cursor.execute('''
                SELECT COUNT(*) FROM briefing_runs
                WHERE started_at >= datetime('now', ?)
            ''', (f'-{days} days',))
            stats['total_runs'] = self.cursor.fetchone()[0]

            # 성공/실패 수
            self.cursor.execute('''
                SELECT status, COUNT(*) FROM briefing_runs
                WHERE started_at >= datetime('now', ?)
                GROUP BY status
            ''', (f'-{days} days',))
            for row in self.cursor.fetchall():
                stats[f'status_{row[0]}'] = row[1]

            # 평균 실행 시간
            self.cursor.execute('''
                SELECT AVG(execution_time_ms) FROM briefing_runs
                WHERE status = 'completed' AND started_at >= datetime('now', ?)
            ''', (f'-{days} days',))
            avg = self.cursor.fetchone()[0]
            stats['avg_execution_time_ms'] = int(avg) if avg else 0

            # 일별 추이
            self.cursor.execute('''
                SELECT date(started_at) as day, COUNT(*),
                       SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)
                FROM briefing_runs
                WHERE started_at >= datetime('now', ?)
                GROUP BY date(started_at)
                ORDER BY day
            ''', (f'-{days} days',))
            stats['daily'] = [{'date': r[0], 'total': r[1], 'success': r[2], 'failed': r[3]}
                             for r in self.cursor.fetchall()]

            return stats
        except Exception as e:
            logger.error(f"get_briefing_stats error: {e}")
            return {}

    def get_latest_running_briefing(self) -> dict:
        """현재 실행 중인 Briefing을 조회합니다."""
        try:
            self.cursor.execute('''
                SELECT id, started_at, tasks_total, tasks_completed, tasks_failed
                FROM briefing_runs
                WHERE status = 'running'
                ORDER BY started_at DESC
                LIMIT 1
            ''')
            row = self.cursor.fetchone()
            if row:
                return {
                    'id': row[0], 'started_at': row[1], 'tasks_total': row[2],
                    'tasks_completed': row[3], 'tasks_failed': row[4]
                }
            return None
        except Exception as e:
            logger.error(f"get_latest_running_briefing error: {e}")
            return None

    # ============================================
    # Viral Hunter 관련 메서드
    # ============================================
    def insert_viral_target(self, target_data: dict) -> bool:
        """
        Viral Target을 DB에 저장합니다.

        - 신규: discovered_at, last_scanned_at, scan_count=1 설정
        - 중복: discovered_at 유지, last_scanned_at 업데이트, scan_count +1
        - [Phase 1.2] content_hash 기반 중복 감지 추가
        """
        try:
            import json
            keywords_json = json.dumps(target_data.get('matched_keywords', []), ensure_ascii=False)
            now = datetime.now().isoformat()

            # [Phase 1.2] content_hash 계산
            content_hash = self.calculate_content_hash(
                url=target_data.get('url', ''),
                title=target_data.get('title', ''),
                content=target_data.get('content_preview', '')
            )

            # 작성자/게시일 (date_str → posted_at, 빈 값이면 NULL)
            author = target_data.get('author') or None
            posted_at = target_data.get('date_str') or target_data.get('posted_at') or None
            # 첫 매칭 키워드를 단일 컬럼에도 저장 (UI/필터 편의용)
            kws_list = target_data.get('matched_keywords') or []
            matched_keyword_single = (kws_list[0] if kws_list else None) or target_data.get('matched_keyword')

            self.cursor.execute('''
                INSERT INTO viral_targets
                (id, platform, url, title, content_preview, matched_keywords, matched_keyword,
                 category, is_commentable, comment_status, generated_comment,
                 priority_score, discovered_at, last_scanned_at, scan_count, content_hash,
                 author, posted_at, source_scan_run_id, matched_keyword_grade,
                 matched_keyword_kei, matched_keyword_priority, matched_keyword_category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title = excluded.title,
                    matched_keywords = excluded.matched_keywords,
                    matched_keyword = COALESCE(excluded.matched_keyword, viral_targets.matched_keyword),
                    priority_score = excluded.priority_score,
                    last_scanned_at = excluded.last_scanned_at,
                    scan_count = viral_targets.scan_count + 1,
                    content_hash = excluded.content_hash,
                    author = COALESCE(excluded.author, viral_targets.author),
                    posted_at = COALESCE(excluded.posted_at, viral_targets.posted_at),
                    source_scan_run_id = COALESCE(NULLIF(excluded.source_scan_run_id, 0), viral_targets.source_scan_run_id),
                    matched_keyword_grade = COALESCE(excluded.matched_keyword_grade, viral_targets.matched_keyword_grade),
                    matched_keyword_kei = COALESCE(excluded.matched_keyword_kei, viral_targets.matched_keyword_kei),
                    matched_keyword_priority = COALESCE(excluded.matched_keyword_priority, viral_targets.matched_keyword_priority),
                    matched_keyword_category = COALESCE(excluded.matched_keyword_category, viral_targets.matched_keyword_category)
            ''', (
                target_data.get('id'),
                target_data.get('platform'),
                target_data.get('url'),
                target_data.get('title'),
                target_data.get('content_preview', ''),
                keywords_json,
                matched_keyword_single,
                target_data.get('category', '기타'),
                target_data.get('is_commentable', True),
                target_data.get('comment_status', 'pending'),
                target_data.get('generated_comment', ''),
                target_data.get('priority_score', 0),
                now,  # discovered_at (신규만)
                now,  # last_scanned_at (매번 업데이트)
                1,    # scan_count (신규는 1, 중복은 +1)
                content_hash,
                author,
                posted_at,
                target_data.get('source_scan_run_id', 0),
                target_data.get('matched_keyword_grade') or None,
                target_data.get('matched_keyword_kei', 0),
                target_data.get('matched_keyword_priority', 0),
                target_data.get('matched_keyword_category') or None,
            ))
            # [Phase 11 D1] matched_keywords 정규화 저장 (viral_target_keywords)
            try:
                target_id = target_data.get('id')
                kws = target_data.get('matched_keywords') or []
                if target_id and isinstance(kws, list) and kws:
                    self.cursor.executemany(
                        'INSERT OR IGNORE INTO viral_target_keywords(viral_target_id, keyword) VALUES (?, ?)',
                        [(target_id, str(k).strip()) for k in kws if k and str(k).strip()]
                    )
            except Exception as e:
                logger.debug(f"viral_target_keywords sync skipped: {e}")

            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"insert_viral_target error: {e}")
            return False

    def get_viral_targets(self, status: str = None, platform: str = None,
                          category: str = None, date_filter: str = None,
                          platforms: list = None, comment_status: str = None,
                          min_scan_count: int = None,
                          search: str = None, sort: str = None,
                          scan_batch: str = None, limit: int = 100,
                          offset: int = 0) -> list:
        """Viral Target 목록을 조회합니다.

        Args:
            status: 상태 필터 (pending, generated, posted, skipped) - 기본값
            platform: 플랫폼 필터 (cafe, blog, kin) - 단일
            category: 카테고리 필터 (기타, 경쟁사_역공략)
            date_filter: 날짜 필터 (오늘, 최근 7일, 최근 30일)
            platforms: 다중 플랫폼 필터 ['cafe', 'blog', 'instagram']
            comment_status: 댓글 상태 필터 (status 오버라이드)
            min_scan_count: 최소 재발견 횟수
            search: 검색 키워드 (title, content_preview)
            sort: 정렬 기준 (priority, date, scan_count)
            scan_batch: 스캔 배치 필터 (YYYY-MM-DD HH 형식)
            limit: 최대 결과 수
        """
        try:
            query = 'SELECT * FROM viral_targets WHERE 1=1'
            params = []

            # comment_status가 있으면 우선, 없으면 status 사용
            effective_status = comment_status if comment_status else status
            if effective_status:
                query += ' AND comment_status = ?'
                params.append(effective_status)

            # 다중 플랫폼 필터 (우선순위)
            if platforms and len(platforms) > 0:
                placeholders = ','.join(['?'] * len(platforms))
                query += f' AND platform IN ({placeholders})'
                params.extend(platforms)
            elif platform:
                query += ' AND platform = ?'
                params.append(platform)

            if category:
                query += ' AND category = ?'
                params.append(category)

            # 스캔 배치 필터 (YYYY-MM-DD HH 형식)
            if scan_batch:
                query += " AND strftime('%Y-%m-%d %H', discovered_at) = ?"
                params.append(scan_batch)
            elif date_filter:
                if date_filter == "오늘":
                    query += " AND DATE(discovered_at) = DATE('now', 'localtime')"
                elif date_filter == "최근 7일":
                    query += " AND discovered_at >= datetime('now', '-7 days')"
                elif date_filter == "최근 30일":
                    query += " AND discovered_at >= datetime('now', '-30 days')"

            # 재발견 필터
            if min_scan_count is not None and min_scan_count > 0:
                query += ' AND scan_count >= ?'
                params.append(min_scan_count)

            # 검색 키워드
            if search:
                query += ' AND (title LIKE ? OR content_preview LIKE ?)'
                search_pattern = f'%{search}%'
                params.append(search_pattern)
                params.append(search_pattern)

            # 정렬
            if sort == 'date':
                query += ' ORDER BY discovered_at DESC'
            elif sort == 'scan_count':
                query += ' ORDER BY scan_count DESC, discovered_at DESC'
            else:  # 기본: priority
                query += ' ORDER BY priority_score DESC, discovered_at DESC'

            query += ' LIMIT ? OFFSET ?'
            params.append(limit)
            params.append(offset)

            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            columns = [desc[0] for desc in self.cursor.description]

            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"get_viral_targets error: {e}")
            return []

    def get_viral_target(self, target_id: int) -> dict:
        """단일 Viral Target을 조회합니다.

        Args:
            target_id: 타겟 ID

        Returns:
            타겟 데이터 (딕셔너리) 또는 None
        """
        try:
            self.cursor.execute('SELECT * FROM viral_targets WHERE id = ?', (target_id,))
            row = self.cursor.fetchone()

            if row:
                columns = [desc[0] for desc in self.cursor.description]
                return dict(zip(columns, row))
            return None

        except Exception as e:
            logger.error(f"get_viral_target error: {e}")
            return None

    def update_viral_target(self, target_id: str, updates: dict) -> bool:
        """Viral Target 업데이트."""
        try:
            set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [target_id]

            self.cursor.execute(
                f'UPDATE viral_targets SET {set_clause} WHERE id = ?',
                values
            )
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            logger.error(f"update_viral_target error: {e}")
            return False

    def get_viral_stats(self) -> dict:
        """Viral Hunter 통계를 조회합니다."""
        try:
            stats = {}

            # 플랫폼별 카운트
            self.cursor.execute('''
                SELECT platform, COUNT(*) FROM viral_targets GROUP BY platform
            ''')
            stats['by_platform'] = {r[0]: r[1] for r in self.cursor.fetchall()}

            # 상태별 카운트
            self.cursor.execute('''
                SELECT comment_status, COUNT(*) FROM viral_targets GROUP BY comment_status
            ''')
            stats['by_status'] = {r[0]: r[1] for r in self.cursor.fetchall()}

            # 총 개수
            self.cursor.execute('SELECT COUNT(*) FROM viral_targets')
            stats['total'] = self.cursor.fetchone()[0]

            # 오늘 발견
            today = datetime.now().strftime('%Y-%m-%d')
            self.cursor.execute('''
                SELECT COUNT(*) FROM viral_targets
                WHERE date(discovered_at) = ?
            ''', (today,))
            stats['today'] = self.cursor.fetchone()[0]

            return stats
        except Exception as e:
            logger.error(f"get_viral_stats error: {e}")
            return {}

    def delete_viral_target(self, target_id: str) -> bool:
        """Viral Target 삭제."""
        try:
            self.cursor.execute('DELETE FROM viral_targets WHERE id = ?', (target_id,))
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            logger.error(f"delete_viral_target error: {e}")
            return False

    # ============================================
    # [키워드 제안] 신규 키워드 추천 시스템
    # ============================================
    def get_tracked_keywords(self) -> list:
        """
        현재 rank_history에서 추적 중인 고유 키워드 목록 조회.

        Returns:
            list: [{'keyword': str, 'last_tracked': str, 'avg_rank': float, 'track_count': int}]
        """
        try:
            self.cursor.execute('''
                SELECT
                    keyword,
                    MAX(date) as last_tracked,
                    ROUND(AVG(CASE WHEN status = 'found' THEN rank ELSE NULL END), 1) as avg_rank,
                    COUNT(*) as track_count
                FROM rank_history
                GROUP BY keyword
                ORDER BY last_tracked DESC
            ''')
            rows = self.cursor.fetchall()
            return [{
                'keyword': r[0],
                'last_tracked': r[1],
                'avg_rank': r[2] if r[2] else 0,
                'track_count': r[3]
            } for r in rows]
        except Exception as e:
            logger.error(f"get_tracked_keywords error: {e}")
            return []

    def get_keyword_suggestions(self, config_path: str = None) -> list:
        """
        신규 키워드 제안 생성.

        소스:
        1. opportunity_keywords 테이블 (경쟁사 약점 분석에서 추출)
        2. targets.json의 community_scan_keywords (아직 추적하지 않는 것)
        3. targets.json의 경쟁사 keywords (우리가 추적하지 않는 것)

        Returns:
            list: [{
                'keyword': str,
                'source': str ('opportunity'|'config'|'competitor'),
                'source_detail': str,
                'priority': int (1-10),
                'reason': str
            }]
        """
        try:
            # 현재 추적 중인 키워드 목록
            tracked = set(kw['keyword'] for kw in self.get_tracked_keywords())

            suggestions = []

            # 1. opportunity_keywords에서 pending 상태인 것
            self.cursor.execute('''
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='opportunity_keywords'
            ''')
            if self.cursor.fetchone():
                self.cursor.execute('''
                    SELECT keyword, competitor_name, weakness_type, priority_score
                    FROM opportunity_keywords
                    WHERE status = 'pending'
                    ORDER BY priority_score DESC
                    LIMIT 20
                ''')
                for r in self.cursor.fetchall():
                    if r[0] and r[0] not in tracked:
                        suggestions.append({
                            'keyword': r[0],
                            'source': 'opportunity',
                            'source_detail': f"경쟁사({r[1]}) 약점: {r[2]}",
                            'priority': min(int(r[3]) if r[3] else 5, 10),
                            'reason': f"경쟁사 {r[1]}의 {r[2]} 약점에서 발굴된 기회 키워드"
                        })

            # 2. targets.json에서 키워드 로드
            import json
            if config_path is None:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                config_path = os.path.join(base_dir, 'config', 'targets.json')

            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                # community_scan_keywords 중 아직 추적하지 않는 것
                scan_keywords = config.get('community_scan_keywords', [])
                for kw in scan_keywords:
                    if kw and kw not in tracked:
                        suggestions.append({
                            'keyword': kw,
                            'source': 'config',
                            'source_detail': 'community_scan_keywords',
                            'priority': 7,
                            'reason': '설정된 커뮤니티 스캔 키워드 (아직 순위 추적 미시작)'
                        })

                # 경쟁사 키워드 중 아직 추적하지 않는 것
                targets = config.get('targets', [])
                for target in targets:
                    competitor_name = target.get('name', '')
                    competitor_keywords = target.get('keywords', [])
                    for kw in competitor_keywords:
                        if kw and kw not in tracked:
                            # 경쟁사 우선순위에 따라 점수 조정
                            priority_map = {'Critical': 9, 'High': 8, 'Medium': 6, 'Low': 4}
                            priority = priority_map.get(target.get('priority', 'Medium'), 6)
                            suggestions.append({
                                'keyword': kw,
                                'source': 'competitor',
                                'source_detail': competitor_name,
                                'priority': priority,
                                'reason': f"경쟁사 '{competitor_name}'의 주요 키워드"
                            })

            # 중복 제거 및 우선순위 정렬
            seen = set()
            unique_suggestions = []
            for s in sorted(suggestions, key=lambda x: x['priority'], reverse=True):
                if s['keyword'] not in seen:
                    seen.add(s['keyword'])
                    unique_suggestions.append(s)

            return unique_suggestions

        except Exception as e:
            logger.error(f"get_keyword_suggestions error: {e}")
            return []

    def add_keyword_to_tracking(self, keyword: str, initial_rank: int = 0) -> bool:
        """
        신규 키워드를 rank_history에 추가하고 keywords.json에도 등록하여 추적 시작.

        Args:
            keyword: 추가할 키워드
            initial_rank: 초기 순위 (0 = 아직 확인 안됨)

        Returns:
            bool: 성공 여부
        """
        import json as json_module
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            # 1. rank_history에 초기 레코드 삽입 (모바일 & 데스크톱 둘 다)
            for device in ['mobile', 'desktop']:
                self.cursor.execute('''
                    INSERT INTO rank_history (date, keyword, rank, target_name, status, note, device_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (today, keyword, initial_rank, '규림한의원', 'pending', '신규 추가됨 - 다음 스캔에서 확인 예정', device))
            self.conn.commit()

            # 2. keywords.json에도 추가 (Place Sniper가 사용하는 파일)
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            keywords_path = os.path.join(base_dir, 'config', 'keywords.json')

            if os.path.exists(keywords_path):
                with open(keywords_path, 'r', encoding='utf-8') as f:
                    kw_data = json_module.load(f)

                naver_place_keywords = kw_data.get('naver_place', [])
                if keyword not in naver_place_keywords:
                    naver_place_keywords.append(keyword)
                    kw_data['naver_place'] = naver_place_keywords

                    with open(keywords_path, 'w', encoding='utf-8') as f:
                        json_module.dump(kw_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"[KeywordSuggestion] keywords.json에 추가됨: {keyword}")

            logger.info(f"[KeywordSuggestion] 키워드 추적 시작: {keyword}")
            return True
        except Exception as e:
            logger.error(f"add_keyword_to_tracking error: {e}")
            return False

    def get_keyword_performance(self, days: int = 30) -> list:
        """
        키워드별 성과 분석 (제안용 참고 데이터).

        Returns:
            list: [{
                'keyword': str,
                'avg_rank': float,
                'best_rank': int,
                'worst_rank': int,
                'track_days': int,
                'trend': str ('improving'|'declining'|'stable')
            }]
        """
        try:
            self.cursor.execute('''
                WITH keyword_stats AS (
                    SELECT
                        keyword,
                        ROUND(AVG(rank), 1) as avg_rank,
                        MIN(rank) as best_rank,
                        MAX(rank) as worst_rank,
                        COUNT(DISTINCT date) as track_days
                    FROM rank_history
                    WHERE date >= date('now', ?)
                    AND status = 'found'
                    GROUP BY keyword
                ),
                recent_trend AS (
                    SELECT
                        keyword,
                        AVG(CASE WHEN date >= date('now', '-7 days') THEN rank END) as recent_avg,
                        AVG(CASE WHEN date < date('now', '-7 days') THEN rank END) as older_avg
                    FROM rank_history
                    WHERE date >= date('now', ?)
                    AND status = 'found'
                    GROUP BY keyword
                )
                SELECT
                    s.keyword,
                    s.avg_rank,
                    s.best_rank,
                    s.worst_rank,
                    s.track_days,
                    CASE
                        WHEN r.recent_avg < r.older_avg - 1 THEN 'improving'
                        WHEN r.recent_avg > r.older_avg + 1 THEN 'declining'
                        ELSE 'stable'
                    END as trend
                FROM keyword_stats s
                LEFT JOIN recent_trend r ON s.keyword = r.keyword
                ORDER BY s.avg_rank ASC
            ''', (f'-{days} days', f'-{days} days'))

            rows = self.cursor.fetchall()
            return [{
                'keyword': r[0],
                'avg_rank': r[1],
                'best_rank': r[2],
                'worst_rank': r[3],
                'track_days': r[4],
                'trend': r[5] if r[5] else 'stable'
            } for r in rows]
        except Exception as e:
            logger.error(f"get_keyword_performance error: {e}")
            return []

if __name__ == "__main__":
    db = DatabaseManager()
    print("✅ Database initialized successfully.")

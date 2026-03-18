"""
Database Initialization Service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 6.1] 앱 시작 시 DB 테이블 및 스키마 초기화
- 매 요청마다 테이블 존재 확인하는 비효율 제거
- 앱 시작 시 한 번만 실행

[Phase 1-4] 마이그레이션 버전 관리 시스템 통합
- schema_versions 테이블로 적용된 마이그레이션 추적
- MigrationManager를 통한 버전 관리
"""

import sqlite3
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# 프로젝트 루트 (backend -> marketing_bot_web -> marketing_bot)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / 'db' / 'marketing_data.db'


def ensure_all_tables():
    """
    모든 필요한 테이블과 스키마가 존재하는지 확인하고 생성
    앱 시작 시 한 번만 호출됨

    [Phase 1-4] 마이그레이션 시스템 통합
    1. 테이블 생성 (CREATE TABLE IF NOT EXISTS)
    2. 마이그레이션 실행 (ALTER TABLE 등 스키마 변경)
    """
    logger.info("📦 DB 스키마 초기화 시작...")

    # 마이그레이션 시스템 실행
    try:
        from services.migration_manager import run_all_migrations
        migration_result = run_all_migrations()
        if migration_result["applied"]:
            logger.info(f"📋 마이그레이션 {len(migration_result['applied'])}개 적용됨")
        if migration_result["errors"]:
            logger.warning(f"⚠️ 마이그레이션 오류: {migration_result['errors']}")
    except ImportError:
        logger.warning("마이그레이션 관리자를 로드할 수 없습니다. 기본 스키마 초기화만 진행합니다.")
    except Exception as e:
        logger.warning(f"마이그레이션 실행 중 오류 (계속 진행): {e}")

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        # 1. Q&A Repository 테이블
        _ensure_qa_repository_table(cursor)

        # 2. Comment Templates 테이블 및 컬럼
        _ensure_comment_templates_table(cursor)

        # 3. Notifications 테이블 (순위 하락 알림용)
        _ensure_notifications_table(cursor)

        # 4. Contact History 테이블 (리드 컨택 히스토리)
        _ensure_contact_history_table(cursor)

        # 5. Competitor Rankings 테이블 (경쟁사 순위 추적)
        _ensure_competitor_rankings_table(cursor)

        # 6. Auto Approval Rules 테이블 (AI Agent 자동 승인 규칙)
        _ensure_auto_approval_rules_table(cursor)

        # 7. [Phase G] 전환 어트리뷰션 체인 테이블 및 컬럼
        _ensure_conversion_attribution_table(cursor)

        # 8. [Phase H] 리드 응답 시간 추적 컬럼
        _ensure_lead_response_tracking(cursor)

        # 9. [Phase K] 키워드 라이프사이클 테이블
        _ensure_keyword_lifecycle_table(cursor)

        # 10. [Phase B] AI Intelligence 테이블
        _ensure_intelligence_tables(cursor)

        # 11. [Phase C] Automation 테이블 및 컬럼
        _ensure_automation_tables(cursor)

        # 12. [Phase D] Feedback 테이블
        _ensure_feedback_tables(cursor)

        # 13. Competitor Weaknesses 테이블 컬럼
        _ensure_competitor_weaknesses_table(cursor)

        # ============================================
        # [Marketing Enhancement] 마케팅 강화 테이블들
        # ============================================

        # 14. 골든타임 분석 테이블 및 컬럼
        _ensure_golden_time_tables(cursor)

        # 15. 리드 품질 스코어링 테이블
        _ensure_lead_quality_tables(cursor)

        # 16. 콘텐츠 성과 분석 테이블
        _ensure_content_performance_tables(cursor)

        # 17. 캠페인 관리 테이블
        _ensure_campaign_tables(cursor)

        # 18. A/B 테스트 테이블
        _ensure_ab_testing_tables(cursor)

        # 19. 경쟁사 바이럴 레이더 테이블
        _ensure_competitor_radar_tables(cursor)

        # 20. 스마트 알림 및 자동화 테이블
        _ensure_smart_automation_tables(cursor)

        # 21. 통합 ROI 테이블
        _ensure_roi_tables(cursor)

        # 22. [Phase 7.0] 통합 리드 프로필 테이블
        _ensure_unified_contacts_table(cursor)

        # ============================================
        # [Marketing Enhancement 2.0] 실시간 알림 시스템
        # ============================================

        # 23. 알림 설정 테이블 (카카오톡/텔레그램)
        _ensure_notification_settings_table(cursor)

        # 24. 알림 발송 이력 테이블
        _ensure_notification_history_table(cursor)

        # ============================================
        # [멀티채널 확장] 인스타그램/틱톡 강화
        # ============================================

        # 25. 인스타그램 릴스 분석 테이블
        _ensure_instagram_reels_analysis_table(cursor)

        # 26. 인스타그램 해시태그 트렌드 테이블
        _ensure_instagram_hashtag_trends_table(cursor)

        # 27. 틱톡 비디오 테이블
        _ensure_tiktok_videos_table(cursor)

        # 28. 틱톡 트렌드 테이블
        _ensure_tiktok_trends_table(cursor)

        # 29. [성능 최적화] 핵심 인덱스 추가
        _ensure_performance_indexes(cursor)

        # 30. [Phase 4-2] Hot Lead 재알림 테이블
        _ensure_lead_reminder_tables(cursor)

        # 31. [Phase 4] viral_target_keywords 정규화 테이블
        _ensure_viral_target_keywords_table(cursor)

        # ============================================
        # [Phase 9: Intelligence Enhancement] 정보 수집 고도화
        # ============================================

        # 32. 스마트플레이스 통계 데이터
        _ensure_smartplace_stats_table(cursor)

        # 33. 리뷰 인텔리전스 (메타데이터 확장)
        _ensure_review_intelligence_table(cursor)

        # 34. 블로그 VIEW탭 순위 추적
        _ensure_blog_rank_history_table(cursor)

        # 35. HIRA 의료기관 공공 데이터
        _ensure_hira_clinics_table(cursor)

        # 36. 의료 리뷰 플랫폼 모니터링
        _ensure_medical_platform_reviews_table(cursor)

        # 37. 경쟁사 웹사이트 변경 감지
        _ensure_competitor_changes_table(cursor)

        # 38. 카카오맵 순위 추적
        _ensure_kakao_rank_history_table(cursor)

        # 39. 전화/전환 추적
        _ensure_call_tracking_table(cursor)

        # 40. 소상공인 상권 데이터
        _ensure_commercial_district_table(cursor)

        # 41. 지오그리드 순위 추적
        _ensure_geo_grid_rankings_table(cursor)

        # 42. 네이버 광고 키워드 상세 데이터
        _ensure_naver_ad_keyword_data_table(cursor)

        # 43. 커뮤니티 멘션 확장
        _ensure_community_mentions_table(cursor)

        # 44. [Phase 9] 인텔리전스 인덱스
        _ensure_intelligence_indexes(cursor)

        conn.commit()
        logger.info("✅ DB 스키마 초기화 완료")

    except Exception as e:
        logger.error(f"❌ DB 스키마 초기화 실패: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_qa_repository_table(cursor):
    """Q&A Repository 테이블 생성"""
    cursor.execute("""
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
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_qa_category
        ON qa_repository(question_category)
    """)
    logger.debug("  - qa_repository 테이블 확인됨")


def _ensure_comment_templates_table(cursor):
    """Comment Templates 테이블 및 Phase 5.0 컬럼 확인"""
    # 테이블 생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comment_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            situation_type TEXT DEFAULT 'general',
            engagement_signal TEXT DEFAULT 'any',
            use_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 기존 테이블에 Phase 5.0 컬럼이 없으면 추가
    cursor.execute("PRAGMA table_info(comment_templates)")
    columns = {row[1] for row in cursor.fetchall()}

    if 'situation_type' not in columns:
        cursor.execute("ALTER TABLE comment_templates ADD COLUMN situation_type TEXT DEFAULT 'general'")
        logger.info("  - comment_templates: situation_type 컬럼 추가됨")

    if 'engagement_signal' not in columns:
        cursor.execute("ALTER TABLE comment_templates ADD COLUMN engagement_signal TEXT DEFAULT 'any'")
        logger.info("  - comment_templates: engagement_signal 컬럼 추가됨")

    logger.debug("  - comment_templates 테이블 확인됨")


def _ensure_notifications_table(cursor):
    """Notifications 테이블 및 인덱스 확인"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT,
            priority TEXT DEFAULT 'medium',
            is_read INTEGER DEFAULT 0,
            metadata TEXT DEFAULT '{}',
            reference_keyword TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 기존 테이블에 reference_keyword 컬럼이 없으면 추가
    cursor.execute("PRAGMA table_info(notifications)")
    columns = {row[1] for row in cursor.fetchall()}

    if 'reference_keyword' not in columns:
        cursor.execute("ALTER TABLE notifications ADD COLUMN reference_keyword TEXT")
        logger.info("  - notifications: reference_keyword 컬럼 추가됨")

    # 인덱스 생성 (LIKE 대신 직접 컬럼 검색용)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_type_keyword
        ON notifications(type, reference_keyword)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_created
        ON notifications(created_at)
    """)

    logger.debug("  - notifications 테이블 확인됨")


def _ensure_contact_history_table(cursor):
    """Contact History 테이블 확인"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contact_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            contact_type TEXT DEFAULT 'comment',
            content TEXT NOT NULL,
            platform TEXT,
            response TEXT,
            status TEXT DEFAULT 'sent',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lead_id) REFERENCES viral_targets(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_contact_history_lead
        ON contact_history(lead_id)
    """)
    logger.debug("  - contact_history 테이블 확인됨")


def _ensure_competitor_rankings_table(cursor):
    """
    [Phase 6.2] Competitor Rankings 테이블 생성
    경쟁사의 키워드별 순위를 추적하여 우리 업체와 비교 분석
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS competitor_rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_name TEXT NOT NULL,
            keyword TEXT NOT NULL,
            rank INTEGER DEFAULT 0,
            scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            scanned_date TEXT DEFAULT (DATE('now')),
            note TEXT,
            UNIQUE(competitor_name, keyword, scanned_date)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_competitor_rankings_competitor
        ON competitor_rankings(competitor_name)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_competitor_rankings_keyword
        ON competitor_rankings(keyword)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_competitor_rankings_date
        ON competitor_rankings(scanned_at DESC)
    """)
    logger.debug("  - competitor_rankings 테이블 확인됨")


def _ensure_auto_approval_rules_table(cursor):
    """
    [Phase 6.2] Auto Approval Rules 테이블 생성
    AI Agent 자동 승인 규칙
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auto_approval_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            condition_type TEXT NOT NULL,
            condition_value TEXT NOT NULL,
            action TEXT DEFAULT 'approve',
            priority INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_auto_approval_rules_active
        ON auto_approval_rules(is_active)
    """)
    logger.debug("  - auto_approval_rules 테이블 확인됨")


def _ensure_conversion_attribution_table(cursor):
    """
    [Phase G-1] 전환 어트리뷰션 체인 테이블 및 컬럼
    키워드 → 바이럴 → 리드 → 전환의 전체 경로 추적
    """
    # lead_conversions 테이블 생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lead_conversions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            converted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            revenue REAL DEFAULT 0,
            conversion_type TEXT DEFAULT 'direct',
            source_viral_id INTEGER,
            attribution_chain TEXT DEFAULT '{}',
            days_to_conversion INTEGER,
            response_time_hours REAL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lead_id) REFERENCES mentions(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_lead_conversions_lead
        ON lead_conversions(lead_id)
    """)
    logger.debug("  - lead_conversions 테이블 확인됨")

    # lead_conversions 테이블에 어트리뷰션 관련 컬럼 추가 (기존 테이블 호환성)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lead_conversions'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(lead_conversions)")
        columns = {row[1] for row in cursor.fetchall()}

        # converted_at 컬럼 추가 (기존 conversion_date 호환)
        if 'converted_at' not in columns:
            cursor.execute("ALTER TABLE lead_conversions ADD COLUMN converted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            logger.info("  - lead_conversions: converted_at 컬럼 추가됨")
            # 기존 conversion_date 데이터 복사
            if 'conversion_date' in columns:
                cursor.execute("UPDATE lead_conversions SET converted_at = conversion_date WHERE converted_at IS NULL")

        if 'source_viral_id' not in columns:
            cursor.execute("ALTER TABLE lead_conversions ADD COLUMN source_viral_id INTEGER")
            logger.info("  - lead_conversions: source_viral_id 컬럼 추가됨")

        if 'attribution_chain' not in columns:
            cursor.execute("ALTER TABLE lead_conversions ADD COLUMN attribution_chain TEXT DEFAULT '{}'")
            logger.info("  - lead_conversions: attribution_chain 컬럼 추가됨")

        if 'days_to_conversion' not in columns:
            cursor.execute("ALTER TABLE lead_conversions ADD COLUMN days_to_conversion INTEGER")
            logger.info("  - lead_conversions: days_to_conversion 컬럼 추가됨")

        if 'response_time_hours' not in columns:
            cursor.execute("ALTER TABLE lead_conversions ADD COLUMN response_time_hours REAL")
            logger.info("  - lead_conversions: response_time_hours 컬럼 추가됨")

        # converted_at 인덱스 생성 (컬럼 추가 후)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_lead_conversions_date
            ON lead_conversions(converted_at DESC)
        """)

    # ROI 분석용 집계 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyword_roi_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            total_leads INTEGER DEFAULT 0,
            total_conversions INTEGER DEFAULT 0,
            total_revenue REAL DEFAULT 0,
            viral_count INTEGER DEFAULT 0,
            avg_days_to_conversion REAL,
            conversion_rate REAL,
            roi_score REAL,
            calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(keyword, period_start, period_end)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_keyword_roi_keyword
        ON keyword_roi_stats(keyword)
    """)
    logger.debug("  - keyword_roi_stats 테이블 확인됨")


def _ensure_lead_response_tracking(cursor):
    """
    [Phase H-3] 리드 응답 시간 추적 컬럼
    골든타임 분석을 위한 응답 시간 기록
    """
    # mentions 테이블에 응답 시간 컬럼 추가
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(mentions)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'first_response_at' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN first_response_at TEXT")
            logger.info("  - mentions: first_response_at 컬럼 추가됨")

        if 'response_time_hours' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN response_time_hours REAL")
            logger.info("  - mentions: response_time_hours 컬럼 추가됨")

    # viral_targets 테이블에도 동일하게 추가
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='viral_targets'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(viral_targets)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'first_response_at' not in columns:
            cursor.execute("ALTER TABLE viral_targets ADD COLUMN first_response_at TEXT")
            logger.info("  - viral_targets: first_response_at 컬럼 추가됨")

        if 'response_time_hours' not in columns:
            cursor.execute("ALTER TABLE viral_targets ADD COLUMN response_time_hours REAL")
            logger.info("  - viral_targets: response_time_hours 컬럼 추가됨")

        # [FIX] content 컬럼 추가 (viral.py에서 사용)
        if 'content' not in columns:
            cursor.execute("ALTER TABLE viral_targets ADD COLUMN content TEXT")
            logger.info("  - viral_targets: content 컬럼 추가됨")

        # [FIX] first_seen_at 컬럼 추가 (viral.py에서 사용)
        if 'first_seen_at' not in columns:
            cursor.execute("ALTER TABLE viral_targets ADD COLUMN first_seen_at TIMESTAMP")
            logger.info("  - viral_targets: first_seen_at 컬럼 추가됨")

    logger.debug("  - 리드 응답 시간 추적 컬럼 확인됨")


def _ensure_keyword_lifecycle_table(cursor):
    """
    [Phase K-1] 키워드 라이프사이클 테이블
    키워드 상태: discovered → tracking → active → maintaining → archived
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyword_lifecycle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL UNIQUE,
            status TEXT DEFAULT 'discovered',
            grade TEXT,
            discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tracking_started_at TEXT,
            active_started_at TEXT,
            maintaining_started_at TEXT,
            archived_at TEXT,
            total_leads INTEGER DEFAULT 0,
            total_conversions INTEGER DEFAULT 0,
            total_revenue REAL DEFAULT 0,
            current_rank INTEGER,
            best_rank INTEGER,
            weeks_in_top10 INTEGER DEFAULT 0,
            last_viral_at TEXT,
            last_lead_at TEXT,
            last_conversion_at TEXT,
            auto_transition_enabled INTEGER DEFAULT 1,
            notes TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_keyword_lifecycle_status
        ON keyword_lifecycle(status)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_keyword_lifecycle_keyword
        ON keyword_lifecycle(keyword)
    """)

    # 키워드 상태 변경 히스토리
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyword_lifecycle_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL,
            reason TEXT,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_keyword_lifecycle_history_keyword
        ON keyword_lifecycle_history(keyword)
    """)

    logger.debug("  - keyword_lifecycle 테이블 확인됨")


def _ensure_intelligence_tables(cursor):
    """
    [Phase B] AI Intelligence 테이블
    - 전환 패턴, 댓글 효과, 순위 예측, 타이밍 분석
    """
    # B-1: 전환 패턴 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversion_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT NOT NULL,
            pattern_key TEXT NOT NULL,
            conversion_rate REAL DEFAULT 0,
            sample_count INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(pattern_type, pattern_key)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversion_patterns_type
        ON conversion_patterns(pattern_type)
    """)

    # B-2: 댓글 효과 분석 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comment_effectiveness (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_type TEXT NOT NULL,
            category TEXT NOT NULL,
            total_count INTEGER DEFAULT 0,
            conversion_count INTEGER DEFAULT 0,
            conversion_rate REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(analysis_type, category)
        )
    """)

    # B-3: 순위 예측 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rank_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            current_rank INTEGER,
            predicted_rank INTEGER,
            trend TEXT,
            confidence TEXT,
            days_ahead INTEGER DEFAULT 7,
            predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actual_rank INTEGER,
            accuracy_checked INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_rank_predictions_keyword
        ON rank_predictions(keyword)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_rank_predictions_date
        ON rank_predictions(predicted_at DESC)
    """)

    # B-4: 타이밍 분석 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS timing_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_type TEXT NOT NULL,
            category TEXT NOT NULL,
            sub_category TEXT,
            total_count INTEGER DEFAULT 0,
            conversion_count INTEGER DEFAULT 0,
            conversion_rate REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(analysis_type, category, sub_category)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_timing_analytics_type
        ON timing_analytics(analysis_type)
    """)

    logger.debug("  - AI Intelligence 테이블 확인됨")


def _ensure_automation_tables(cursor):
    """
    [Phase C] Automation 테이블 및 컬럼
    - mentions 테이블에 auto_classified 컬럼 추가
    - daily_briefings 테이블 생성
    """
    # mentions 테이블에 auto_classified 컬럼 추가
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(mentions)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'auto_classified' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN auto_classified INTEGER DEFAULT 0")
            logger.info("  - mentions: auto_classified 컬럼 추가됨")

        if 'score' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN score INTEGER")
            logger.info("  - mentions: score 컬럼 추가됨")

        if 'grade' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN grade TEXT")
            logger.info("  - mentions: grade 컬럼 추가됨")

        if 'trust_score' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN trust_score INTEGER")
            logger.info("  - mentions: trust_score 컬럼 추가됨")

    # daily_briefings 테이블 생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_briefings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            period TEXT DEFAULT 'daily',
            content TEXT NOT NULL,
            highlights TEXT,
            actions_count INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_daily_briefings_date
        ON daily_briefings(generated_at DESC)
    """)

    logger.debug("  - Automation 테이블 확인됨")


def _ensure_feedback_tables(cursor):
    """
    [Phase D] Feedback 테이블
    - 피드백 분석, 정확도 리포트, 성과 리포트
    """
    # feedback_analysis 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_type TEXT NOT NULL,
            analysis_date TEXT DEFAULT (DATE('now')),
            content TEXT NOT NULL,
            adjustments_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # accuracy_reports 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accuracy_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_type TEXT NOT NULL,
            report_date TEXT DEFAULT (DATE('now')),
            overall_accuracy REAL,
            verified_count INTEGER,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # performance_reports 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS performance_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_type TEXT NOT NULL,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            period_days INTEGER,
            content TEXT NOT NULL,
            highlights TEXT,
            recommendations TEXT
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_performance_reports_type
        ON performance_reports(report_type, generated_at DESC)
    """)

    logger.debug("  - Feedback 테이블 확인됨")


def _ensure_competitor_weaknesses_table(cursor):
    """
    Competitor Weaknesses 테이블 컬럼 확인
    - opportunity_keywords, evidence 컬럼 추가
    """
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitor_weaknesses'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(competitor_weaknesses)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'opportunity_keywords' not in columns:
            cursor.execute("ALTER TABLE competitor_weaknesses ADD COLUMN opportunity_keywords TEXT")
            logger.info("  - competitor_weaknesses: opportunity_keywords 컬럼 추가됨")

        if 'evidence' not in columns:
            cursor.execute("ALTER TABLE competitor_weaknesses ADD COLUMN evidence TEXT")
            logger.info("  - competitor_weaknesses: evidence 컬럼 추가됨")

    logger.debug("  - competitor_weaknesses 테이블 확인됨")


# ============================================
# [Marketing Enhancement] 마케팅 강화 테이블 함수들
# ============================================

def _ensure_golden_time_tables(cursor):
    """
    [ME-1] 골든타임 분석 테이블 및 컬럼
    - 댓글 게시 시간별 반응률 추적
    - 최적 게시 시간 분석
    """
    # posted_comments 테이블 생성 (이미 있으면 컬럼만 추가)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posted_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id TEXT NOT NULL,
            content TEXT NOT NULL,
            platform TEXT,
            url TEXT,
            template_id INTEGER,
            template_name TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            posted_hour INTEGER,
            posted_day_of_week INTEGER,
            likes INTEGER DEFAULT 0,
            replies INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            led_to_contact INTEGER DEFAULT 0,
            led_to_conversion INTEGER DEFAULT 0,
            engagement_checked_at TEXT,
            engagement_24h TEXT,
            engagement_48h TEXT,
            engagement_72h TEXT,
            FOREIGN KEY (target_id) REFERENCES viral_targets(id)
        )
    """)

    # 기존 테이블에 골든타임 컬럼 추가
    cursor.execute("PRAGMA table_info(posted_comments)")
    columns = {row[1] for row in cursor.fetchall()}

    new_columns = [
        ('posted_hour', 'INTEGER'),
        ('posted_day_of_week', 'INTEGER'),
        ('engagement_24h', 'TEXT'),
        ('engagement_48h', 'TEXT'),
        ('engagement_72h', 'TEXT'),
        ('engagement_checked_at', 'TEXT'),
    ]

    for col_name, col_type in new_columns:
        if col_name not in columns:
            cursor.execute(f"ALTER TABLE posted_comments ADD COLUMN {col_name} {col_type}")
            logger.info(f"  - posted_comments: {col_name} 컬럼 추가됨")

    # 골든타임 집계 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS golden_time_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            category TEXT DEFAULT 'all',
            hour INTEGER NOT NULL,
            day_of_week INTEGER,
            total_comments INTEGER DEFAULT 0,
            total_likes INTEGER DEFAULT 0,
            total_replies INTEGER DEFAULT 0,
            total_clicks INTEGER DEFAULT 0,
            total_conversions INTEGER DEFAULT 0,
            avg_engagement_rate REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(platform, category, hour, day_of_week)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_golden_time_platform
        ON golden_time_stats(platform, category)
    """)

    # 예약 게시 큐
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id TEXT NOT NULL,
            content TEXT NOT NULL,
            platform TEXT,
            scheduled_at TIMESTAMP NOT NULL,
            optimal_hour INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            posted_at TIMESTAMP,
            error_message TEXT,
            FOREIGN KEY (target_id) REFERENCES viral_targets(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_scheduled_posts_status
        ON scheduled_posts(status, scheduled_at)
    """)

    logger.debug("  - 골든타임 분석 테이블 확인됨")


def _ensure_lead_quality_tables(cursor):
    """
    [ME-2] 리드 품질 스코어링 테이블
    - 타겟→리드→전환 품질 추적
    - 플랫폼/카테고리별 전환율 분석
    """
    # mentions (리드) 테이블에 source_target_id 컬럼 추가
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(mentions)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'source_target_id' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN source_target_id TEXT")
            logger.info("  - mentions: source_target_id 컬럼 추가됨")

        if 'source_platform' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN source_platform TEXT")
            logger.info("  - mentions: source_platform 컬럼 추가됨")

        if 'source_category' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN source_category TEXT")
            logger.info("  - mentions: source_category 컬럼 추가됨")

        if 'conversion_value' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN conversion_value REAL DEFAULT 0")
            logger.info("  - mentions: conversion_value 컬럼 추가됨")

        # viral.py _create_lead_from_viral 함수에서 사용하는 컬럼들 추가
        if 'platform' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN platform TEXT")
            logger.info("  - mentions: platform 컬럼 추가됨")

        if 'summary' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN summary TEXT")
            logger.info("  - mentions: summary 컬럼 추가됨")

        if 'author' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN author TEXT")
            logger.info("  - mentions: author 컬럼 추가됨")

        if 'category' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN category TEXT")
            logger.info("  - mentions: category 컬럼 추가됨")

        if 'source_module' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN source_module TEXT")
            logger.info("  - mentions: source_module 컬럼 추가됨")

        if 'created_at' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN created_at TIMESTAMP")
            logger.info("  - mentions: created_at 컬럼 추가됨")

    # 리드 품질 통계 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lead_quality_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dimension_type TEXT NOT NULL,
            dimension_value TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            total_targets INTEGER DEFAULT 0,
            total_comments INTEGER DEFAULT 0,
            total_leads INTEGER DEFAULT 0,
            total_conversions INTEGER DEFAULT 0,
            total_revenue REAL DEFAULT 0,
            avg_conversion_value REAL DEFAULT 0,
            conversion_rate REAL DEFAULT 0,
            lead_to_conversion_rate REAL DEFAULT 0,
            quality_score REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(dimension_type, dimension_value, period_start, period_end)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_lead_quality_dimension
        ON lead_quality_stats(dimension_type, dimension_value)
    """)

    logger.debug("  - 리드 품질 스코어링 테이블 확인됨")


def _ensure_content_performance_tables(cursor):
    """
    [ME-3] 콘텐츠 성과 분석 테이블
    - 게시물 유형별 전환율 분석
    - 콘텐츠 패턴 학습
    """
    # viral_targets에 콘텐츠 유형 컬럼 추가
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='viral_targets'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(viral_targets)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'content_type' not in columns:
            cursor.execute("ALTER TABLE viral_targets ADD COLUMN content_type TEXT DEFAULT 'unknown'")
            logger.info("  - viral_targets: content_type 컬럼 추가됨")

        if 'content_intent' not in columns:
            cursor.execute("ALTER TABLE viral_targets ADD COLUMN content_intent TEXT")
            logger.info("  - viral_targets: content_intent 컬럼 추가됨")

    # 콘텐츠 성과 통계 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS content_performance_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_type TEXT NOT NULL,
            platform TEXT NOT NULL,
            category TEXT DEFAULT 'all',
            total_targets INTEGER DEFAULT 0,
            total_comments INTEGER DEFAULT 0,
            total_engagements INTEGER DEFAULT 0,
            total_leads INTEGER DEFAULT 0,
            total_conversions INTEGER DEFAULT 0,
            engagement_rate REAL DEFAULT 0,
            lead_rate REAL DEFAULT 0,
            conversion_rate REAL DEFAULT 0,
            avg_priority_score REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(content_type, platform, category)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_content_performance_type
        ON content_performance_stats(content_type, platform)
    """)

    logger.debug("  - 콘텐츠 성과 분석 테이블 확인됨")


def _ensure_campaign_tables(cursor):
    """
    [ME-4] 캠페인 관리 테이블
    - 다중 마케팅 캠페인 동시 운영
    - 캠페인별 목표 및 KPI 추적
    """
    # 캠페인 메인 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'draft',
            start_date TEXT,
            end_date TEXT,
            target_categories TEXT DEFAULT '[]',
            target_platforms TEXT DEFAULT '[]',
            daily_target INTEGER DEFAULT 10,
            total_target INTEGER DEFAULT 100,
            budget REAL DEFAULT 0,
            template_ids TEXT DEFAULT '[]',
            priority INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaigns_status
        ON campaigns(status, start_date)
    """)

    # 캠페인-타겟 연결 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaign_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            target_id TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP,
            result TEXT,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
            FOREIGN KEY (target_id) REFERENCES viral_targets(id),
            UNIQUE(campaign_id, target_id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaign_targets_campaign
        ON campaign_targets(campaign_id, status)
    """)

    # 캠페인 KPI 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaign_kpis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            recorded_date TEXT DEFAULT (DATE('now')),
            targets_processed INTEGER DEFAULT 0,
            comments_posted INTEGER DEFAULT 0,
            engagements INTEGER DEFAULT 0,
            leads_generated INTEGER DEFAULT 0,
            conversions INTEGER DEFAULT 0,
            revenue REAL DEFAULT 0,
            cost REAL DEFAULT 0,
            roi REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
            UNIQUE(campaign_id, recorded_date)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaign_kpis_campaign
        ON campaign_kpis(campaign_id, recorded_date)
    """)

    logger.debug("  - 캠페인 관리 테이블 확인됨")


def _ensure_ab_testing_tables(cursor):
    """
    [ME-5] A/B 테스트 테이블
    - 댓글 스타일별 효과 측정
    - 통계적 유의성 검증
    """
    # 실험 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ab_experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'draft',
            experiment_type TEXT DEFAULT 'comment_style',
            target_category TEXT,
            target_platform TEXT,
            sample_size_target INTEGER DEFAULT 100,
            confidence_level REAL DEFAULT 0.95,
            start_date TIMESTAMP,
            end_date TIMESTAMP,
            winner_variant_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ab_experiments_status
        ON ab_experiments(status)
    """)

    # 변형 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ab_variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            content_template TEXT,
            weight REAL DEFAULT 1.0,
            is_control INTEGER DEFAULT 0,
            impressions INTEGER DEFAULT 0,
            engagements INTEGER DEFAULT 0,
            conversions INTEGER DEFAULT 0,
            engagement_rate REAL DEFAULT 0,
            conversion_rate REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (experiment_id) REFERENCES ab_experiments(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ab_variants_experiment
        ON ab_variants(experiment_id)
    """)

    # 할당 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ab_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL,
            variant_id INTEGER NOT NULL,
            target_id TEXT NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            engaged INTEGER DEFAULT 0,
            converted INTEGER DEFAULT 0,
            engagement_value REAL DEFAULT 0,
            conversion_value REAL DEFAULT 0,
            FOREIGN KEY (experiment_id) REFERENCES ab_experiments(id),
            FOREIGN KEY (variant_id) REFERENCES ab_variants(id),
            UNIQUE(experiment_id, target_id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ab_assignments_experiment
        ON ab_assignments(experiment_id, variant_id)
    """)

    logger.debug("  - A/B 테스트 테이블 확인됨")


def _ensure_competitor_radar_tables(cursor):
    """
    [ME-6] 경쟁사 바이럴 레이더 테이블
    - 경쟁사 온라인 활동 모니터링
    - 역공략 기회 탐지
    """
    # 경쟁사 바이럴 언급 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS competitor_viral_mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_name TEXT NOT NULL,
            platform TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            title TEXT,
            content_preview TEXT,
            mention_type TEXT DEFAULT 'neutral',
            sentiment TEXT DEFAULT 'neutral',
            weakness_detected INTEGER DEFAULT 0,
            weakness_type TEXT,
            counter_attack_score REAL DEFAULT 0,
            discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed INTEGER DEFAULT 0,
            processed_at TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_competitor_viral_competitor
        ON competitor_viral_mentions(competitor_name, platform)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_competitor_viral_weakness
        ON competitor_viral_mentions(weakness_detected, counter_attack_score DESC)
    """)

    # 역공략 기회 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS counter_attack_opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_mention_id INTEGER,
            competitor_name TEXT NOT NULL,
            opportunity_type TEXT NOT NULL,
            opportunity_score REAL DEFAULT 0,
            our_strength TEXT,
            suggested_response TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actioned_at TIMESTAMP,
            result TEXT,
            FOREIGN KEY (source_mention_id) REFERENCES competitor_viral_mentions(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_counter_attack_status
        ON counter_attack_opportunities(status, opportunity_score DESC)
    """)

    # 경쟁사 활동 통계
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS competitor_activity_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_name TEXT NOT NULL,
            period_date TEXT NOT NULL,
            total_mentions INTEGER DEFAULT 0,
            positive_mentions INTEGER DEFAULT 0,
            negative_mentions INTEGER DEFAULT 0,
            neutral_mentions INTEGER DEFAULT 0,
            weakness_count INTEGER DEFAULT 0,
            our_counter_attacks INTEGER DEFAULT 0,
            market_share_estimate REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(competitor_name, period_date)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_competitor_activity_date
        ON competitor_activity_stats(period_date DESC)
    """)

    logger.debug("  - 경쟁사 바이럴 레이더 테이블 확인됨")


def _ensure_smart_automation_tables(cursor):
    """
    [ME-7] 스마트 알림 및 자동화 테이블
    - 조건 기반 알림 규칙
    - 자동화 액션 정의
    """
    # 알림 규칙 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alert_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            rule_type TEXT NOT NULL,
            condition_json TEXT NOT NULL,
            action_type TEXT DEFAULT 'notification',
            action_params TEXT DEFAULT '{}',
            priority TEXT DEFAULT 'medium',
            is_active INTEGER DEFAULT 1,
            cooldown_minutes INTEGER DEFAULT 60,
            last_triggered_at TIMESTAMP,
            trigger_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_alert_rules_active
        ON alert_rules(is_active, rule_type)
    """)

    # 알림 로그 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alert_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER,
            alert_type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT,
            priority TEXT DEFAULT 'medium',
            channel TEXT DEFAULT 'web',
            status TEXT DEFAULT 'pending',
            sent_at TIMESTAMP,
            read_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (rule_id) REFERENCES alert_rules(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_alert_logs_status
        ON alert_logs(status, created_at DESC)
    """)

    # 자동화 액션 로그
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS automation_action_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER,
            action_type TEXT NOT NULL,
            target_type TEXT,
            target_id TEXT,
            action_params TEXT,
            status TEXT DEFAULT 'pending',
            result TEXT,
            error_message TEXT,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (rule_id) REFERENCES alert_rules(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_automation_logs_rule
        ON automation_action_logs(rule_id, executed_at DESC)
    """)

    logger.debug("  - 스마트 알림 및 자동화 테이블 확인됨")


def _ensure_roi_tables(cursor):
    """
    [ME-8] 통합 ROI 테이블
    - 채널별 ROI 계산
    - 퍼널 분석
    """
    # 일일 ROI 스냅샷
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_roi_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL UNIQUE,
            total_targets INTEGER DEFAULT 0,
            total_comments INTEGER DEFAULT 0,
            total_engagements INTEGER DEFAULT 0,
            total_leads INTEGER DEFAULT 0,
            total_conversions INTEGER DEFAULT 0,
            total_revenue REAL DEFAULT 0,
            estimated_cost REAL DEFAULT 0,
            roi_percentage REAL DEFAULT 0,
            funnel_json TEXT DEFAULT '{}',
            by_platform_json TEXT DEFAULT '{}',
            by_category_json TEXT DEFAULT '{}',
            by_campaign_json TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_daily_roi_date
        ON daily_roi_snapshot(snapshot_date DESC)
    """)

    # 채널별 ROI 통계
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channel_roi_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_type TEXT NOT NULL,
            channel_value TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            targets INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            engagements INTEGER DEFAULT 0,
            leads INTEGER DEFAULT 0,
            conversions INTEGER DEFAULT 0,
            revenue REAL DEFAULT 0,
            cost REAL DEFAULT 0,
            roi_percentage REAL DEFAULT 0,
            efficiency_score REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(channel_type, channel_value, period_start, period_end)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_roi_type
        ON channel_roi_stats(channel_type, channel_value)
    """)

    # AI ROI 권장사항
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roi_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recommendation_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            expected_impact TEXT,
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actioned_at TIMESTAMP,
            result TEXT
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_roi_recommendations_status
        ON roi_recommendations(status, priority)
    """)

    logger.debug("  - 통합 ROI 테이블 확인됨")


def _ensure_unified_contacts_table(cursor):
    """
    [Phase 7.0] 통합 리드 프로필 테이블 생성

    여러 플랫폼에서 동일한 사용자를 그룹핑하여 통합 관리
    """
    # 통합 연락처 그룹 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS unified_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name TEXT NOT NULL,
            primary_platform TEXT,
            primary_identifier TEXT,
            email TEXT,
            phone TEXT,
            notes TEXT,
            tags TEXT DEFAULT '[]',
            total_interactions INTEGER DEFAULT 0,
            last_interaction_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_unified_contacts_name
        ON unified_contacts(display_name)
    """)

    # 기존 mentions 테이블에 unified_contact_id 컬럼 추가
    cursor.execute("PRAGMA table_info(mentions)")
    columns = {row[1] for row in cursor.fetchall()}

    if 'unified_contact_id' not in columns:
        cursor.execute("ALTER TABLE mentions ADD COLUMN unified_contact_id INTEGER")
        logger.info("  - mentions: unified_contact_id 컬럼 추가됨")

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_mentions_unified_contact
        ON mentions(unified_contact_id)
    """)

    logger.debug("  - 통합 리드 프로필 테이블 확인됨")


# ============================================
# [Marketing Enhancement 2.0] 실시간 알림 시스템
# ============================================

def _ensure_notification_settings_table(cursor):
    """
    [ME 2.0-1] 알림 설정 테이블
    - 텔레그램/카카오톡 알림 활성화/비활성화
    - 알림 임계값 설정 (순위 하락, 리드 점수 등)
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_enabled INTEGER DEFAULT 0,
            telegram_bot_token TEXT,
            telegram_chat_id TEXT,
            kakao_enabled INTEGER DEFAULT 0,
            kakao_rest_api_key TEXT,
            kakao_access_token TEXT,
            rank_drop_threshold INTEGER DEFAULT 5,
            new_lead_min_score INTEGER DEFAULT 70,
            competitor_activity_alert INTEGER DEFAULT 1,
            system_error_alert INTEGER DEFAULT 1,
            alert_quiet_start TEXT DEFAULT '22:00',
            alert_quiet_end TEXT DEFAULT '08:00',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 기본 설정이 없으면 추가
    cursor.execute("SELECT COUNT(*) FROM notification_settings")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO notification_settings (telegram_enabled, kakao_enabled)
            VALUES (0, 0)
        """)
        logger.info("  - notification_settings: 기본 설정 추가됨")

    logger.debug("  - notification_settings 테이블 확인됨")


def _ensure_notification_history_table(cursor):
    """
    [ME 2.0-2] 알림 발송 이력 테이블
    - 발송된 알림 추적
    - 성공/실패 상태 기록
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notification_type TEXT NOT NULL,
            channel TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT,
            metadata TEXT DEFAULT '{}',
            status TEXT DEFAULT 'sent',
            error_message TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_notification_history_type
        ON notification_history(notification_type, sent_at DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_notification_history_channel
        ON notification_history(channel, status)
    """)

    logger.debug("  - notification_history 테이블 확인됨")


# ============================================
# [멀티채널 확장] 인스타그램/틱톡 강화
# ============================================

def _ensure_instagram_reels_analysis_table(cursor):
    """
    [MC-1] 인스타그램 릴스 분석 테이블
    - 릴스 콘텐츠 분석 데이터 저장
    - 조회수, 참여율 등 성과 지표
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS instagram_reels_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_username TEXT NOT NULL,
            reel_id TEXT NOT NULL UNIQUE,
            reel_url TEXT,
            caption TEXT,
            hashtags TEXT DEFAULT '[]',
            view_count INTEGER DEFAULT 0,
            like_count INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0,
            share_count INTEGER DEFAULT 0,
            save_count INTEGER DEFAULT 0,
            engagement_rate REAL DEFAULT 0,
            duration_seconds INTEGER,
            audio_name TEXT,
            audio_is_original INTEGER DEFAULT 0,
            thumbnail_url TEXT,
            posted_at TIMESTAMP,
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_instagram_reels_account
        ON instagram_reels_analysis(account_username, posted_at DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_instagram_reels_engagement
        ON instagram_reels_analysis(engagement_rate DESC)
    """)

    logger.debug("  - instagram_reels_analysis 테이블 확인됨")


def _ensure_instagram_hashtag_trends_table(cursor):
    """
    [MC-2] 인스타그램 해시태그 트렌드 테이블
    - 해시태그별 사용량 및 성과 추적
    - 트렌드 변화 모니터링
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS instagram_hashtag_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hashtag TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            post_count INTEGER DEFAULT 0,
            avg_engagement_rate REAL DEFAULT 0,
            top_posts_engagement REAL DEFAULT 0,
            growth_rate REAL DEFAULT 0,
            is_trending INTEGER DEFAULT 0,
            trend_score REAL DEFAULT 0,
            related_hashtags TEXT DEFAULT '[]',
            tracked_date TEXT DEFAULT (DATE('now')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(hashtag, tracked_date)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_instagram_hashtag_date
        ON instagram_hashtag_trends(tracked_date DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_instagram_hashtag_trending
        ON instagram_hashtag_trends(is_trending, trend_score DESC)
    """)

    logger.debug("  - instagram_hashtag_trends 테이블 확인됨")


def _ensure_tiktok_videos_table(cursor):
    """
    [MC-3] 틱톡 비디오 테이블
    - 틱톡 비디오 메타데이터 저장
    - 경쟁사/트렌드 분석용
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tiktok_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL UNIQUE,
            author_username TEXT,
            author_nickname TEXT,
            video_url TEXT,
            description TEXT,
            hashtags TEXT DEFAULT '[]',
            view_count INTEGER DEFAULT 0,
            like_count INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0,
            share_count INTEGER DEFAULT 0,
            save_count INTEGER DEFAULT 0,
            engagement_rate REAL DEFAULT 0,
            duration_seconds INTEGER,
            music_title TEXT,
            music_author TEXT,
            is_original_music INTEGER DEFAULT 0,
            cover_url TEXT,
            category TEXT,
            is_competitor INTEGER DEFAULT 0,
            posted_at TIMESTAMP,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tiktok_videos_author
        ON tiktok_videos(author_username, posted_at DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tiktok_videos_engagement
        ON tiktok_videos(engagement_rate DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tiktok_videos_competitor
        ON tiktok_videos(is_competitor, scraped_at DESC)
    """)

    logger.debug("  - tiktok_videos 테이블 확인됨")


def _ensure_tiktok_trends_table(cursor):
    """
    [MC-4] 틱톡 트렌드 테이블
    - 해시태그/음악 트렌드 추적
    - 일별 트렌드 변화 기록
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tiktok_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trend_type TEXT NOT NULL,
            trend_key TEXT NOT NULL,
            trend_name TEXT,
            category TEXT DEFAULT 'general',
            video_count INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            avg_engagement_rate REAL DEFAULT 0,
            growth_rate REAL DEFAULT 0,
            trend_score REAL DEFAULT 0,
            is_rising INTEGER DEFAULT 0,
            related_trends TEXT DEFAULT '[]',
            sample_video_ids TEXT DEFAULT '[]',
            tracked_date TEXT DEFAULT (DATE('now')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trend_type, trend_key, tracked_date)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tiktok_trends_type
        ON tiktok_trends(trend_type, tracked_date DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tiktok_trends_rising
        ON tiktok_trends(is_rising, trend_score DESC)
    """)

    logger.debug("  - tiktok_trends 테이블 확인됨")


def _ensure_lead_reminder_tables(cursor):
    """
    [Phase 4-2-A] Hot Lead 재알림 테이블 및 컬럼

    mentions 테이블:
    - last_reminder_at: 마지막 재알림 시간
    - reminder_count: 재알림 횟수

    lead_reminder_history 테이블:
    - 재알림 발송 이력
    """
    # mentions 테이블에 재알림 컬럼 추가
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(mentions)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'last_reminder_at' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN last_reminder_at TIMESTAMP")
            logger.info("  - mentions: last_reminder_at 컬럼 추가됨")

        if 'reminder_count' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN reminder_count INTEGER DEFAULT 0")
            logger.info("  - mentions: reminder_count 컬럼 추가됨")

    # 재알림 이력 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lead_reminder_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            lead_type TEXT DEFAULT 'mention',
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reminder_number INTEGER NOT NULL,
            urgency_level TEXT NOT NULL,
            channel TEXT NOT NULL,
            status TEXT DEFAULT 'sent',
            error_message TEXT,
            FOREIGN KEY (lead_id) REFERENCES mentions(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_lead_reminder_history_lead
        ON lead_reminder_history(lead_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_lead_reminder_history_sent
        ON lead_reminder_history(sent_at DESC)
    """)

    # 리드 상태 자동 전이 이력 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lead_status_transition_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            lead_type TEXT DEFAULT 'mention',
            from_status TEXT,
            to_status TEXT NOT NULL,
            reason TEXT NOT NULL,
            transitioned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lead_id) REFERENCES mentions(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_lead_status_transition_lead
        ON lead_status_transition_history(lead_id)
    """)

    logger.debug("  - Hot Lead 재알림 테이블 확인됨")


def _ensure_viral_target_keywords_table(cursor):
    """
    [Phase 4] viral_target_keywords 정규화 테이블

    matched_keywords JSON 배열 검색 최적화를 위한 정규화 테이블
    - LIKE '%keyword%' 풀 스캔 → JOIN 인덱스 검색으로 변경
    - 성능: 100-150ms → 10-20ms (70% 개선)
    """
    # 정규화 테이블 생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS viral_target_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            viral_target_id TEXT NOT NULL,
            keyword TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(viral_target_id, keyword)
        )
    """)

    # 인덱스 생성
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_vtk_keyword
        ON viral_target_keywords(keyword)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_vtk_target_id
        ON viral_target_keywords(viral_target_id)
    """)

    logger.debug("  - viral_target_keywords 정규화 테이블 확인됨")


def _ensure_performance_indexes(cursor):
    """
    [성능 최적화] 쿼리 성능 향상을 위한 핵심 인덱스 추가
    - rank_history: 키워드별 날짜 조회 최적화
    - mentions: 상태/플랫폼별 필터링 최적화
    - keyword_insights: 등급별 조회 최적화
    - viral_targets: 상태별 조회 최적화
    - [Phase 1-2] LIKE 검색 최적화 인덱스 추가
    """
    # rank_history 인덱스
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_rank_history_keyword
        ON rank_history(keyword)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_rank_history_keyword_date
        ON rank_history(keyword, scanned_date DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_rank_history_date
        ON rank_history(scanned_date DESC)
    """)
    # [Phase 2] checked_at 단독 인덱스 (시간 기반 조회 최적화)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_rank_history_checked_at
        ON rank_history(checked_at DESC)
    """)

    # [Phase 1-2] LIKE 검색 최적화 인덱스
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_viral_targets_matched_keyword
        ON viral_targets(matched_keyword)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_mentions_keyword
        ON mentions(keyword)
    """)

    # mentions (리드) 인덱스
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_mentions_status
        ON mentions(status)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_mentions_platform
        ON mentions(source)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_mentions_scraped_at
        ON mentions(scraped_at DESC)
    """)

    # keyword_insights 인덱스
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_keyword_insights_grade
        ON keyword_insights(grade)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_keyword_insights_created
        ON keyword_insights(created_at DESC)
    """)
    # [Phase 2] source 컬럼 인덱스 (LIKE '%legion%' 쿼리 최적화)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_keyword_insights_source
        ON keyword_insights(source)
    """)

    # viral_targets 인덱스
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_viral_targets_status
        ON viral_targets(comment_status)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_viral_targets_platform
        ON viral_targets(platform)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_viral_targets_discovered
        ON viral_targets(discovered_at DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_viral_targets_category
        ON viral_targets(category)
    """)

    # [추가] mentions score 인덱스 (Hot/Warm 리드 필터링)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_mentions_score
        ON mentions(score DESC)
    """)

    # [추가] rank_history device_type 인덱스 (모바일/데스크탑 구분)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_rank_history_device
        ON rank_history(device_type, keyword)
    """)

    # [Phase 5-3] rank_history 복합 인덱스 (키워드+디바이스+시간 조회 최적화)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_rank_history_keyword_device
        ON rank_history(keyword, device_type, checked_at DESC)
    """)

    # [추가] lead_conversions keyword 인덱스 (키워드별 전환 분석)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_lead_conversions_keyword
        ON lead_conversions(keyword)
    """)

    # [추가] competitor_reviews 복합 인덱스 (경쟁사별 최신 리뷰)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_competitor_reviews_name_date
        ON competitor_reviews(competitor_name, scraped_at DESC)
    """)

    logger.debug("  - 성능 최적화 인덱스 확인됨")


# ============================================
# [Phase 9: Intelligence Enhancement] 정보 수집 고도화 테이블
# ============================================


def _ensure_smartplace_stats_table(cursor):
    """스마트플레이스 내부 통계 데이터 (노출, 클릭, 전화, 길찾기, 저장)"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS smartplace_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stat_date TEXT NOT NULL UNIQUE,
            impressions INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            calls INTEGER DEFAULT 0,
            directions INTEGER DEFAULT 0,
            saves INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            bookings INTEGER DEFAULT 0,
            blog_reviews INTEGER DEFAULT 0,
            receipt_reviews INTEGER DEFAULT 0,
            conversion_rate REAL DEFAULT 0.0,
            engagement_rate REAL DEFAULT 0.0,
            source TEXT DEFAULT 'csv',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.debug("  - smartplace_stats 테이블 확인됨")


def _ensure_review_intelligence_table(cursor):
    """리뷰 인텔리전스 (경쟁사별 리뷰 메타데이터 추적)"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS review_intelligence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_name TEXT NOT NULL,
            place_id TEXT,
            total_reviews INTEGER DEFAULT 0,
            avg_rating REAL DEFAULT 0.0,
            rating_distribution TEXT,
            photo_review_count INTEGER DEFAULT 0,
            photo_review_ratio REAL DEFAULT 0.0,
            response_count INTEGER DEFAULT 0,
            response_rate REAL DEFAULT 0.0,
            new_reviews_since_last INTEGER DEFAULT 0,
            suspicious_patterns TEXT,
            suspicious_score INTEGER DEFAULT 0,
            raw_data TEXT,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.debug("  - review_intelligence 테이블 확인됨")


def _ensure_blog_rank_history_table(cursor):
    """블로그 VIEW탭 순위 추적"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blog_rank_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            rank_position INTEGER DEFAULT 0,
            found INTEGER DEFAULT 0,
            result_title TEXT,
            result_url TEXT,
            result_source TEXT,
            total_checked INTEGER DEFAULT 0,
            search_url TEXT,
            tracked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.debug("  - blog_rank_history 테이블 확인됨")


def _ensure_hira_clinics_table(cursor):
    """HIRA 건강보험심사평가원 의료기관 데이터"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hira_clinics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ykiho TEXT UNIQUE,
            name TEXT,
            category TEXT,
            address TEXT,
            phone TEXT,
            sido TEXT,
            sigungu TEXT,
            specialty TEXT,
            doctor_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.debug("  - hira_clinics 테이블 확인됨")


def _ensure_medical_platform_reviews_table(cursor):
    """의료 리뷰 플랫폼 모니터링 (모두닥, 굿닥, 강남언니 등)"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medical_platform_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            clinic_name TEXT NOT NULL,
            is_our_clinic INTEGER DEFAULT 0,
            reviewer TEXT,
            rating REAL,
            content TEXT,
            treatment_type TEXT,
            review_date TEXT,
            review_url TEXT,
            url_hash TEXT UNIQUE,
            scanned_at TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.debug("  - medical_platform_reviews 테이블 확인됨")


def _ensure_competitor_changes_table(cursor):
    """경쟁사 웹사이트/Place 프로필 변경 감지"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS competitor_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_name TEXT NOT NULL,
            place_id TEXT,
            change_type TEXT NOT NULL,
            severity TEXT DEFAULT 'low',
            old_value TEXT,
            new_value TEXT,
            details TEXT,
            notified INTEGER DEFAULT 0,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.debug("  - competitor_changes 테이블 확인됨")


def _ensure_kakao_rank_history_table(cursor):
    """카카오맵 순위 추적"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kakao_rank_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            rank INTEGER,
            total_results INTEGER DEFAULT 0,
            place_name TEXT,
            place_id TEXT,
            category TEXT,
            address TEXT,
            status TEXT DEFAULT 'found',
            scanned_at TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.debug("  - kakao_rank_history 테이블 확인됨")


def _ensure_call_tracking_table(cursor):
    """전화/전환 추적 (스마트콜 데이터)"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS call_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stat_date TEXT NOT NULL,
            total_calls INTEGER DEFAULT 0,
            naver_search_calls INTEGER DEFAULT 0,
            keyword TEXT,
            phone_number TEXT,
            duration_seconds INTEGER DEFAULT 0,
            source TEXT DEFAULT 'csv',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.debug("  - call_tracking 테이블 확인됨")


def _ensure_commercial_district_table(cursor):
    """소상공인 상권 분석 데이터"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS commercial_district_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region TEXT,
            region_code TEXT,
            industry_code TEXT,
            industry_name TEXT,
            store_count INTEGER DEFAULT 0,
            total_medical_count INTEGER DEFAULT 0,
            competition_index REAL DEFAULT 0.0,
            collected_date TEXT,
            raw_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(region, industry_code, collected_date)
        )
    """)
    logger.debug("  - commercial_district_data 테이블 확인됨")


def _ensure_geo_grid_rankings_table(cursor):
    """지오그리드 순위 추적 (지역별 순위 히트맵)"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS geo_grid_rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_session_id TEXT NOT NULL,
            keyword TEXT NOT NULL,
            grid_label TEXT NOT NULL,
            grid_lat REAL NOT NULL,
            grid_lng REAL NOT NULL,
            rank INTEGER,
            total_results INTEGER DEFAULT 0,
            place_name TEXT,
            status TEXT DEFAULT 'found',
            arp REAL,
            scanned_at TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.debug("  - geo_grid_rankings 테이블 확인됨")


def _ensure_naver_ad_keyword_data_table(cursor):
    """네이버 광고 API 키워드 상세 데이터"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS naver_ad_keyword_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT,
            monthly_search_pc INTEGER DEFAULT 0,
            monthly_search_mobile INTEGER DEFAULT 0,
            monthly_click_pc REAL DEFAULT 0.0,
            monthly_click_mobile REAL DEFAULT 0.0,
            monthly_ctr_pc REAL DEFAULT 0.0,
            monthly_ctr_mobile REAL DEFAULT 0.0,
            competition_level TEXT DEFAULT '',
            avg_ad_count REAL DEFAULT 0.0,
            total_search_volume INTEGER DEFAULT 0,
            is_related INTEGER DEFAULT 0,
            source_keyword TEXT DEFAULT '',
            collected_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(keyword, collected_date)
        )
    """)
    # naver_ad_related_keywords 테이블 (연관 키워드 별도 저장)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS naver_ad_related_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_keyword TEXT,
            related_keyword TEXT,
            search_volume INTEGER DEFAULT 0,
            collected_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_keyword, related_keyword, collected_date)
        )
    """)
    logger.debug("  - naver_ad_keyword_data 테이블 확인됨")


def _ensure_community_mentions_table(cursor):
    """커뮤니티 멘션 확장 (당근, 오픈채팅 등)"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS community_mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            keyword TEXT NOT NULL,
            title TEXT,
            content_preview TEXT,
            author TEXT,
            url TEXT UNIQUE,
            url_hash TEXT,
            comment_count INTEGER DEFAULT 0,
            engagement_count INTEGER DEFAULT 0,
            mention_type TEXT DEFAULT 'review',
            is_lead_candidate INTEGER DEFAULT 0,
            is_our_mention INTEGER DEFAULT 0,
            scanned_at TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.debug("  - community_mentions 테이블 확인됨")


def _ensure_intelligence_indexes(cursor):
    """[Phase 9] 인텔리전스 테이블 인덱스"""
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_smartplace_stats_date
        ON smartplace_stats(stat_date DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_review_intel_competitor_date
        ON review_intelligence(competitor_name, collected_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_blog_rank_keyword_date
        ON blog_rank_history(keyword, tracked_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_hira_clinics_sigungu
        ON hira_clinics(sigungu, category)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_medical_reviews_clinic
        ON medical_platform_reviews(clinic_name, platform)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_medical_reviews_date
        ON medical_platform_reviews(scanned_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_competitor_changes_name_date
        ON competitor_changes(competitor_name, detected_at DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_competitor_changes_severity
        ON competitor_changes(severity, detected_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_kakao_rank_keyword_date
        ON kakao_rank_history(keyword, scanned_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_call_tracking_date
        ON call_tracking(stat_date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_geo_grid_session
        ON geo_grid_rankings(scan_session_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_geo_grid_keyword_date
        ON geo_grid_rankings(keyword, scanned_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_naver_ad_keyword
        ON naver_ad_keyword_data(keyword, collected_date DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_community_platform_keyword
        ON community_mentions(platform, keyword)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_community_url_hash
        ON community_mentions(url_hash)
    """)
    logger.debug("  - Phase 9 인텔리전스 인덱스 확인됨")


# 직접 실행 시 테스트
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    ensure_all_tables()

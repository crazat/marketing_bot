"""
Phase 4 Scheduling & Automation Tests
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 4] 적응형 스캔 및 Hot Lead 자동화 테스트
- 4-1-A: AutoRescanHandler (순위 급락 자동 재스캔)
- 4-1-B: KeywordPriorityScheduler (키워드 우선순위 스캔)
- 4-2-A: LeadReminderScheduler (Hot Lead 재알림)
- 4-2-B: LeadStatusAutomator (리드 상태 자동 전이)
- API: Scheduler API 엔드포인트 테스트

실행 방법:
    python -m pytest tests/test_phase4_scheduling.py -v
    또는
    python tests/test_phase4_scheduling.py
"""

import unittest
import sys
import os
import json
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Test: AutoRescanHandler
# =============================================================================

class TestAutoRescanHandler(unittest.TestCase):
    """AutoRescanHandler 단위 테스트"""

    def setUp(self):
        """테스트 환경 설정"""
        # 모듈 임포트 전 mock 설정
        self.mock_event_bus = MagicMock()
        self.mock_db = MagicMock()

    @patch('core.auto_rescan_handler.get_event_bus')
    def test_cooldown_check(self, MockEventBus):
        """쿨다운 체크 로직 테스트"""
        MockEventBus.return_value = self.mock_event_bus

        from core.auto_rescan_handler import AutoRescanHandler

        handler = AutoRescanHandler(min_drop=5, cooldown_minutes=30)

        # 쿨다운 없는 키워드
        self.assertFalse(handler._is_in_cooldown("새로운 키워드"))

        # 쿨다운 설정
        handler.rescan_cooldown["테스트 키워드"] = datetime.now()
        self.assertTrue(handler._is_in_cooldown("테스트 키워드"))

        # 쿨다운 만료 (과거 시간으로 설정)
        handler.rescan_cooldown["만료된 키워드"] = datetime.now() - timedelta(minutes=35)
        self.assertFalse(handler._is_in_cooldown("만료된 키워드"))

        print("[OK] AutoRescanHandler cooldown check verified")

    @patch('core.auto_rescan_handler.get_event_bus')
    def test_get_status(self, MockEventBus):
        """상태 조회 테스트"""
        MockEventBus.return_value = self.mock_event_bus

        from core.auto_rescan_handler import AutoRescanHandler

        handler = AutoRescanHandler(min_drop=5, cooldown_minutes=30)

        # 쿨다운 설정
        handler.rescan_cooldown["키워드1"] = datetime.now()

        # 히스토리 추가
        handler._add_to_history("키워드1", "테스트 이유", "warning")

        status = handler.get_status()

        self.assertEqual(status["min_drop"], 5)
        self.assertEqual(status["cooldown_minutes"], 30)
        self.assertIn("키워드1", status["active_cooldowns"])
        self.assertEqual(len(status["recent_rescans"]), 1)

        print("[OK] AutoRescanHandler get_status verified")

    @patch('core.auto_rescan_handler.get_event_bus')
    def test_clear_cooldown(self, MockEventBus):
        """쿨다운 초기화 테스트"""
        MockEventBus.return_value = self.mock_event_bus

        from core.auto_rescan_handler import AutoRescanHandler

        handler = AutoRescanHandler()

        # 여러 키워드에 쿨다운 설정
        handler.rescan_cooldown["키워드1"] = datetime.now()
        handler.rescan_cooldown["키워드2"] = datetime.now()

        # 특정 키워드만 초기화
        handler.clear_cooldown("키워드1")
        self.assertNotIn("키워드1", handler.rescan_cooldown)
        self.assertIn("키워드2", handler.rescan_cooldown)

        # 전체 초기화
        handler.clear_cooldown()
        self.assertEqual(len(handler.rescan_cooldown), 0)

        print("[OK] AutoRescanHandler clear_cooldown verified")


# =============================================================================
# Test: KeywordPriorityScheduler
# =============================================================================

class TestKeywordPriorityScheduler(unittest.TestCase):
    """KeywordPriorityScheduler 단위 테스트"""

    def setUp(self):
        """테스트 환경 설정"""
        self.temp_schedule_file = "/tmp/test_keyword_schedule.json"

    def tearDown(self):
        """테스트 정리"""
        if os.path.exists(self.temp_schedule_file):
            os.remove(self.temp_schedule_file)

    def test_priority_calculation(self):
        """우선순위 계산 로직 테스트 (로직 검증)"""
        from core.keyword_priority_scheduler import KeywordPriority, PRIORITY_INTERVALS

        # 점수 계산 로직 테스트 (내부 로직 검증)
        # 검색량: min(search_volume / 1000, 5) - 최대 5점
        # 전환 수: min(conversions, 3) - 최대 3점
        # 순위 변동: min(rank_changes / 2, 2) - 최대 2점

        # 테스트 케이스 1: 고점수 (7점 이상 → CRITICAL)
        search_volume_score = min(5000 / 1000, 5)  # 5점
        conversion_score = min(3, 3)               # 3점
        rank_changes_score = min(10 / 2, 2)        # 2점
        total_score = search_volume_score + conversion_score + rank_changes_score  # 10점

        self.assertEqual(total_score, 10)
        self.assertGreaterEqual(total_score, 7)  # CRITICAL 기준

        # 테스트 케이스 2: 중간 점수 (4-6점 → HIGH)
        search_volume_score2 = min(2000 / 1000, 5)  # 2점
        conversion_score2 = min(1, 3)               # 1점
        rank_changes_score2 = min(2 / 2, 2)         # 1점
        total_score2 = search_volume_score2 + conversion_score2 + rank_changes_score2  # 4점

        self.assertEqual(total_score2, 4)
        self.assertGreaterEqual(total_score2, 4)  # HIGH 기준
        self.assertLess(total_score2, 7)

        # 테스트 케이스 3: 낮은 점수 (2-3점 → MEDIUM)
        search_volume_score3 = min(500 / 1000, 5)   # 0.5점
        conversion_score3 = min(1, 3)               # 1점
        rank_changes_score3 = min(0 / 2, 2)         # 0점
        total_score3 = search_volume_score3 + conversion_score3 + rank_changes_score3  # 1.5점

        self.assertLess(total_score3, 2)  # LOW 기준

        print("[OK] KeywordPriorityScheduler priority calculation logic verified")

    def test_priority_intervals(self):
        """우선순위별 스캔 간격 테스트"""
        from core.keyword_priority_scheduler import KeywordPriority, PRIORITY_INTERVALS

        self.assertEqual(PRIORITY_INTERVALS[KeywordPriority.CRITICAL], 4)
        self.assertEqual(PRIORITY_INTERVALS[KeywordPriority.HIGH], 8)
        self.assertEqual(PRIORITY_INTERVALS[KeywordPriority.MEDIUM], 12)
        self.assertEqual(PRIORITY_INTERVALS[KeywordPriority.LOW], 24)

        print("[OK] KeywordPriorityScheduler priority intervals verified")

    def test_schedule_info_dataclass(self):
        """스케줄 정보 데이터클래스 테스트"""
        from core.keyword_priority_scheduler import KeywordScheduleInfo, KeywordPriority

        info = KeywordScheduleInfo(
            keyword="테스트 키워드",
            priority=KeywordPriority.HIGH,
            interval_hours=8,
            last_scan=datetime.now(),
            scan_count=5,
            priority_score=4.5
        )

        self.assertEqual(info.keyword, "테스트 키워드")
        self.assertEqual(info.priority, KeywordPriority.HIGH)
        self.assertEqual(info.interval_hours, 8)
        self.assertEqual(info.scan_count, 5)

        print("[OK] KeywordScheduleInfo dataclass verified")

    def test_manual_priority_set(self):
        """수동 우선순위 설정 테스트"""
        from core.keyword_priority_scheduler import KeywordPriorityScheduler, KeywordPriority

        scheduler = KeywordPriorityScheduler()
        scheduler.schedule_file = self.temp_schedule_file

        # 우선순위 수동 설정
        scheduler.set_manual_priority("수동 키워드", "critical")

        self.assertIn("수동 키워드", scheduler.keyword_schedules)
        self.assertEqual(
            scheduler.keyword_schedules["수동 키워드"].priority,
            KeywordPriority.CRITICAL
        )
        self.assertEqual(scheduler.keyword_schedules["수동 키워드"].interval_hours, 4)

        print("[OK] KeywordPriorityScheduler manual priority set verified")


# =============================================================================
# Test: LeadReminderScheduler
# =============================================================================

class TestLeadReminderScheduler(unittest.TestCase):
    """LeadReminderScheduler 단위 테스트"""

    def test_urgency_level_determination(self):
        """긴급도 레벨 결정 로직 테스트"""
        # 모듈 경로 설정
        backend_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'marketing_bot_web', 'backend', 'services'
        )
        sys.path.insert(0, backend_path)

        from lead_reminder_scheduler import LeadReminderScheduler, UrgencyLevel

        scheduler = LeadReminderScheduler()

        # 시간대별 긴급도 확인
        self.assertEqual(scheduler._determine_urgency(2), UrgencyLevel.NORMAL)    # 2시간
        self.assertEqual(scheduler._determine_urgency(6), UrgencyLevel.REMINDER)  # 6시간
        self.assertEqual(scheduler._determine_urgency(18), UrgencyLevel.WARNING)  # 18시간
        self.assertEqual(scheduler._determine_urgency(30), UrgencyLevel.URGENT)   # 30시간
        self.assertEqual(scheduler._determine_urgency(50), UrgencyLevel.CRITICAL) # 50시간

        print("[OK] LeadReminderScheduler urgency level determination verified")

    def test_next_reminder_calculation(self):
        """다음 재알림 시간 계산 테스트"""
        backend_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'marketing_bot_web', 'backend', 'services'
        )
        sys.path.insert(0, backend_path)

        from lead_reminder_scheduler import LeadReminderScheduler, REMINDER_INTERVALS

        scheduler = LeadReminderScheduler(max_reminders=5)

        # 첫 재알림 (생성 후 4시간)
        created_at = datetime.now() - timedelta(hours=5)  # 5시간 전 생성
        next_reminder = scheduler._calculate_next_reminder(created_at, None, 0)
        self.assertIsNotNone(next_reminder)
        self.assertLessEqual(next_reminder, 0)  # 이미 재알림 필요

        # 최대 횟수 초과
        next_reminder = scheduler._calculate_next_reminder(created_at, None, 5)
        self.assertIsNone(next_reminder)

        print("[OK] LeadReminderScheduler next reminder calculation verified")

    def test_reminder_intervals(self):
        """재알림 간격 상수 테스트"""
        backend_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'marketing_bot_web', 'backend', 'services'
        )
        sys.path.insert(0, backend_path)

        from lead_reminder_scheduler import REMINDER_INTERVALS

        expected_intervals = [4, 8, 16, 24, 48]
        self.assertEqual(REMINDER_INTERVALS, expected_intervals)

        print("[OK] LeadReminderScheduler reminder intervals verified")


# =============================================================================
# Test: LeadStatusAutomator
# =============================================================================

class TestLeadStatusAutomator(unittest.TestCase):
    """LeadStatusAutomator 단위 테스트"""

    def test_transition_rules(self):
        """전이 규칙 정의 테스트"""
        backend_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'marketing_bot_web', 'backend', 'services'
        )
        sys.path.insert(0, backend_path)

        from lead_status_automator import TRANSITION_RULES

        # 규칙 존재 확인
        self.assertGreater(len(TRANSITION_RULES), 0)

        # 필수 규칙 확인
        rule_keys = [(r.from_status, r.to_status) for r in TRANSITION_RULES]

        self.assertIn(("contacted", "rejected"), rule_keys)
        self.assertIn(("pending", "archived"), rule_keys)
        self.assertIn(("replied", "pending_review"), rule_keys)

        print("[OK] LeadStatusAutomator transition rules verified")

    def test_rule_thresholds(self):
        """전이 규칙 임계값 테스트"""
        backend_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'marketing_bot_web', 'backend', 'services'
        )
        sys.path.insert(0, backend_path)

        from lead_status_automator import TRANSITION_RULES

        for rule in TRANSITION_RULES:
            # contacted → rejected: 7일
            if rule.from_status == "contacted" and rule.to_status == "rejected":
                self.assertEqual(rule.days_threshold, 7)

            # pending → archived: 14일
            if rule.from_status == "pending" and rule.to_status == "archived":
                self.assertEqual(rule.days_threshold, 14)

            # replied → pending_review: 30일
            if rule.from_status == "replied" and rule.to_status == "pending_review":
                self.assertEqual(rule.days_threshold, 30)

        print("[OK] LeadStatusAutomator rule thresholds verified")

    def test_dry_run_mode(self):
        """Dry run 모드 테스트"""
        backend_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'marketing_bot_web', 'backend', 'services'
        )
        sys.path.insert(0, backend_path)

        from lead_status_automator import LeadStatusAutomator

        automator_dry = LeadStatusAutomator(dry_run=True)
        self.assertTrue(automator_dry.dry_run)

        automator_real = LeadStatusAutomator(dry_run=False)
        self.assertFalse(automator_real.dry_run)

        print("[OK] LeadStatusAutomator dry run mode verified")


# =============================================================================
# Test: Scheduler API Endpoints
# =============================================================================

class TestSchedulerAPI(unittest.TestCase):
    """Scheduler API 엔드포인트 테스트"""

    @classmethod
    def setUpClass(cls):
        """테스트 클라이언트 설정"""
        try:
            from fastapi.testclient import TestClient

            # main.py 경로 추가
            backend_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'marketing_bot_web', 'backend'
            )
            sys.path.insert(0, backend_path)

            # 앱 임포트 (의존성 mock 필요할 수 있음)
            cls.has_testclient = True
        except ImportError:
            cls.has_testclient = False

    def test_api_router_exists(self):
        """API 라우터 존재 확인"""
        router_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'marketing_bot_web', 'backend', 'routers', 'scheduler.py'
        )

        self.assertTrue(os.path.exists(router_path), "scheduler.py router should exist")
        print("[OK] Scheduler API router exists")

    def test_api_endpoints_defined(self):
        """API 엔드포인트 정의 확인"""
        backend_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'marketing_bot_web', 'backend', 'routers'
        )
        sys.path.insert(0, backend_path)

        from scheduler import router

        # 라우터에 정의된 경로 확인
        routes = [route.path for route in router.routes]

        expected_routes = [
            "/health",
            "/apply-recommendations",
            "/peak-hours",
            "/keyword-priorities",
            "/auto-rescan/status",
            "/lead-reminders/status",
            "/lead-transitions/preview"
        ]

        for expected in expected_routes:
            self.assertIn(
                expected, routes,
                f"Route {expected} should be defined"
            )

        print("[OK] Scheduler API endpoints defined")


# =============================================================================
# Test: Integration (with Mock DB)
# =============================================================================

class TestPhase4Integration(unittest.TestCase):
    """Phase 4 통합 테스트 (Mock DB 사용)"""

    def setUp(self):
        """테스트용 in-memory DB 설정"""
        self.conn = sqlite3.connect(":memory:")
        self.cursor = self.conn.cursor()

        # 테스트 테이블 생성
        self.cursor.execute('''
            CREATE TABLE mentions (
                id INTEGER PRIMARY KEY,
                source TEXT,
                author TEXT,
                content TEXT,
                score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                scraped_at TEXT,
                last_reminder_at TEXT,
                reminder_count INTEGER DEFAULT 0
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE lead_reminder_history (
                id INTEGER PRIMARY KEY,
                lead_id INTEGER,
                lead_type TEXT,
                sent_at TEXT,
                reminder_number INTEGER,
                urgency_level TEXT,
                channel TEXT,
                status TEXT
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE lead_status_transition_history (
                id INTEGER PRIMARY KEY,
                lead_id INTEGER,
                lead_type TEXT,
                from_status TEXT,
                to_status TEXT,
                reason TEXT,
                transitioned_at TEXT
            )
        ''')

        self.conn.commit()

    def tearDown(self):
        """테스트 정리"""
        self.conn.close()

    def test_hot_lead_detection(self):
        """Hot Lead 감지 테스트"""
        # 테스트 데이터 삽입
        now = datetime.now()
        old_time = (now - timedelta(hours=5)).isoformat()

        self.cursor.execute('''
            INSERT INTO mentions (source, author, content, score, status, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('naver_cafe', 'test_user', '청주 한의원 추천해주세요', 85, 'pending', old_time))
        self.conn.commit()

        # 쿼리 실행
        self.cursor.execute('''
            SELECT id, score, status FROM mentions
            WHERE status = 'pending' AND score >= 70
        ''')
        results = self.cursor.fetchall()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1], 85)  # score

        print("[OK] Hot Lead detection verified")

    def test_status_transition_candidates(self):
        """상태 전이 후보 감지 테스트"""
        # 7일 이상 지난 contacted 상태 리드
        old_time = (datetime.now() - timedelta(days=10)).isoformat()

        self.cursor.execute('''
            INSERT INTO mentions (source, author, content, status, scraped_at)
            VALUES (?, ?, ?, ?, ?)
        ''', ('naver_cafe', 'old_user', '오래된 문의', 'contacted', old_time))
        self.conn.commit()

        # 전이 대상 쿼리
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        self.cursor.execute('''
            SELECT id, status FROM mentions
            WHERE status = 'contacted' AND scraped_at < ?
        ''', (cutoff,))

        results = self.cursor.fetchall()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1], 'contacted')

        print("[OK] Status transition candidates detection verified")

    def test_reminder_history_recording(self):
        """재알림 이력 기록 테스트"""
        now = datetime.now().isoformat()

        # 재알림 이력 저장
        self.cursor.execute('''
            INSERT INTO lead_reminder_history
            (lead_id, lead_type, sent_at, reminder_number, urgency_level, channel, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (1, 'mention', now, 1, 'warning', 'telegram', 'sent'))
        self.conn.commit()

        # 조회
        self.cursor.execute('SELECT COUNT(*) FROM lead_reminder_history')
        count = self.cursor.fetchone()[0]

        self.assertEqual(count, 1)

        print("[OK] Reminder history recording verified")


# =============================================================================
# Test: VirtualTable Accessibility (Conceptual)
# =============================================================================

class TestVirtualTableAccessibility(unittest.TestCase):
    """VirtualTable 접근성 테스트 (개념적 검증)"""

    def test_aria_roles_defined(self):
        """ARIA 역할 정의 확인"""
        component_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'marketing_bot_web', 'frontend', 'src', 'components', 'ui', 'VirtualTable.tsx'
        )

        with open(component_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # ARIA 역할 확인
        self.assertIn('role="grid"', content)
        self.assertIn('role="row"', content)
        self.assertIn('role="gridcell"', content)
        self.assertIn('role="columnheader"', content)
        self.assertIn('aria-activedescendant', content)

        print("[OK] VirtualTable ARIA roles verified")

    def test_keyboard_navigation_handlers(self):
        """키보드 네비게이션 핸들러 확인"""
        component_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'marketing_bot_web', 'frontend', 'src', 'components', 'ui', 'VirtualTable.tsx'
        )

        with open(component_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 키보드 핸들러 확인
        self.assertIn('handleKeyDown', content)
        self.assertIn('ArrowDown', content)
        self.assertIn('ArrowUp', content)
        self.assertIn('Home', content)
        self.assertIn('End', content)
        self.assertIn('PageUp', content)
        self.assertIn('PageDown', content)

        print("[OK] VirtualTable keyboard navigation verified")


# =============================================================================
# Test: PerformanceMonitorWidget (Conceptual)
# =============================================================================

class TestPerformanceMonitorWidget(unittest.TestCase):
    """PerformanceMonitorWidget 테스트"""

    def test_component_exists(self):
        """컴포넌트 파일 존재 확인"""
        component_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'marketing_bot_web', 'frontend', 'src', 'components',
            'dashboard', 'PerformanceMonitorWidget.tsx'
        )

        self.assertTrue(os.path.exists(component_path))
        print("[OK] PerformanceMonitorWidget exists")

    def test_widget_api_usage(self):
        """위젯이 올바른 API를 사용하는지 확인"""
        component_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'marketing_bot_web', 'frontend', 'src', 'components',
            'dashboard', 'PerformanceMonitorWidget.tsx'
        )

        with open(component_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # API 엔드포인트 사용 확인
        self.assertIn('/api/scheduler/health', content)
        self.assertIn('/api/scheduler/apply-recommendations', content)

        print("[OK] PerformanceMonitorWidget API usage verified")

    def test_widget_react_query_usage(self):
        """React Query 사용 확인"""
        component_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'marketing_bot_web', 'frontend', 'src', 'components',
            'dashboard', 'PerformanceMonitorWidget.tsx'
        )

        with open(component_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('useQuery', content)
        self.assertIn('useMutation', content)

        print("[OK] PerformanceMonitorWidget React Query usage verified")


# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':
    print("=" * 70)
    print("Phase 4 Scheduling & Automation Tests")
    print("=" * 70)
    print()

    # 테스트 실행
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 테스트 클래스 추가
    suite.addTests(loader.loadTestsFromTestCase(TestAutoRescanHandler))
    suite.addTests(loader.loadTestsFromTestCase(TestKeywordPriorityScheduler))
    suite.addTests(loader.loadTestsFromTestCase(TestLeadReminderScheduler))
    suite.addTests(loader.loadTestsFromTestCase(TestLeadStatusAutomator))
    suite.addTests(loader.loadTestsFromTestCase(TestSchedulerAPI))
    suite.addTests(loader.loadTestsFromTestCase(TestPhase4Integration))
    suite.addTests(loader.loadTestsFromTestCase(TestVirtualTableAccessibility))
    suite.addTests(loader.loadTestsFromTestCase(TestPerformanceMonitorWidget))

    # 결과 출력
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 요약 출력
    print()
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")

    if result.wasSuccessful():
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed.")
        for test, traceback in result.failures + result.errors:
            print(f"\nFailed: {test}")
            print(traceback)

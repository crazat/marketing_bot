"""
HUD (Heads-Up Display) API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

실시간 메트릭 대시보드
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List, Optional
import asyncio
import sys
import os
from pathlib import Path
import sqlite3
import subprocess
import json
import time
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from services.ai_client import ai_generate_json

# 상위 디렉토리를 path에 추가
parent_dir = str(Path(__file__).parent.parent.parent.parent)  # 프로젝트 루트
backend_dir = str(Path(__file__).parent.parent)  # backend 디렉토리
sys.path.insert(0, parent_dir)
sys.path.insert(0, backend_dir)

# 보안 및 유틸리티 import
from core_services.sql_builder import (
    validate_table_name, validate_column_name, select_column_safely
)
from backend_utils.error_handlers import handle_exceptions
from backend_utils.logger import get_router_logger
from schemas.response import success_response, error_response

logger = get_router_logger('hud')


# [R1] DB 연결 누수 방지 공용 헬퍼는 backend_utils.database로 승격
from backend_utils.database import db_conn

# 스케줄러 상태 파일 경로
SCHEDULER_STATE_FILE = os.path.join(parent_dir, 'db', 'scheduler_state.json')
SCHEDULE_CONFIG_FILE = os.path.join(parent_dir, 'config', 'schedule.json')

# Python 실행 명령어 (Windows: python, Linux/Mac: python3)
import platform
PYTHON_CMD = "python" if platform.system() == "Windows" else "python3"


def load_schedule_config():
    """스케줄 설정 파일에서 로드"""
    default_schedule = [
        {"time": "08:00", "name": "Reputation Sentinel", "icon": "🛡️", "cmd": "sentinel"},
        {"time": "09:00", "name": "Place Sniper", "icon": "📍", "cmd": "place_sniper"},
        {"time": "03:00", "name": "Pathfinder", "icon": "🌌", "cmd": "pathfinder"},
    ]
    # [고도화 B-1b] 스크래퍼 엔진 설정에 따라 Place Sniper 명령어 선택
    from config.app_settings import get_settings
    _engine = get_settings().scraper_engine
    _place_sniper_cmd = (
        [PYTHON_CMD, "scrapers/scraper_naver_place_pw.py"]
        if _engine == "playwright"
        else [PYTHON_CMD, "scrapers/scraper_naver_place.py"]
    )

    default_commands = {
        "sentinel": [PYTHON_CMD, "sentinel_agent.py"],
        "place_sniper": _place_sniper_cmd,
        "pathfinder": [PYTHON_CMD, "pathfinder_v3_complete.py", "--save-db"],
    }

    try:
        if os.path.exists(SCHEDULE_CONFIG_FILE):
            with open(SCHEDULE_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)

            schedule = config.get('schedule', default_schedule)
            # enabled=false인 항목 제외
            schedule = [s for s in schedule if s.get('enabled', True)]

            commands = config.get('commands', default_commands)
            # python 명령어를 플랫폼에 맞게 변환
            for cmd_name, cmd_list in commands.items():
                if cmd_list and cmd_list[0] == 'python':
                    commands[cmd_name] = [PYTHON_CMD] + cmd_list[1:]

            return schedule, commands
    except Exception as e:
        logger.warning(f"스케줄 설정 로드 실패: {e}")

    return default_schedule, default_commands


# 스케줄 및 명령어 로드
CHRONOS_SCHEDULE, CMD_MAP = load_schedule_config()

# 실행 중인 프로세스 추적 (스레드 안전을 위한 lock 추가)
running_processes: Dict[str, subprocess.Popen] = {}
running_processes_lock = threading.Lock()

# 스캔 진행률 추적 (SSE용, 스레드 안전을 위한 lock 추가)
scan_progress: Dict[str, Dict[str, Any]] = {}
scan_progress_lock = threading.Lock()
# 예: {"place_sniper": {"status": "running", "progress": 50, "message": "키워드 5/10 스캔 중...", "started_at": "..."}}


def update_scan_progress(module_name: str, status: str, progress: int = 0, message: str = "", extra: Dict = None):
    """스캔 진행률 업데이트 (스레드 안전)"""
    with scan_progress_lock:
        scan_progress[module_name] = {
            "status": status,  # "idle", "running", "completed", "error"
            "progress": progress,  # 0-100
            "message": message,
            "updated_at": datetime.now().isoformat(),
            **(extra or {})
        }


def get_scan_progress_from_log(module_name: str) -> Dict[str, Any]:
    """[T3] 로그 파일에서 진행률 파싱 — services.hud_service로 위임."""
    from services.hud_service import parse_scan_progress_from_log
    return parse_scan_progress_from_log(module_name, parent_dir)


# [성능 최적화] TTL 캐시 클래스
class TTLCache:
    """
    간단한 TTL(Time-To-Live) 캐시
    - 지정된 시간 동안 데이터를 캐시하여 반복 DB 쿼리 방지
    - 스레드 안전
    """
    def __init__(self, ttl_seconds: int = 30):
        self.ttl = ttl_seconds
        self._cache: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """캐시에서 값을 가져옴. TTL 초과시 None 반환"""
        with self._lock:
            if key not in self._cache:
                return None
            if time.time() - self._timestamps[key] > self.ttl:
                # TTL 초과 - 캐시 무효화
                del self._cache[key]
                del self._timestamps[key]
                return None
            return self._cache[key]

    def set(self, key: str, value: Any) -> None:
        """캐시에 값 저장"""
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()

    def invalidate(self, key: str) -> None:
        """특정 키 캐시 무효화"""
        with self._lock:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)

    def clear(self) -> None:
        """전체 캐시 클리어"""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()


# HUD 메트릭 캐시 (30초 TTL)
hud_metrics_cache = TTLCache(ttl_seconds=30)
# 시스템 상태 캐시 (15초 TTL)
system_status_cache = TTLCache(ttl_seconds=15)


from db.database import DatabaseManager
from core_services.sql_builder import validate_table_name, get_table_columns

router = APIRouter()

@router.get("/metrics")
@handle_exceptions
async def get_hud_metrics() -> Dict[str, Any]:
    """
    HUD 메트릭 조회 (30초 TTL 캐시 적용)

    Returns:
        - total_keywords: 총 키워드 수
        - s_grade_keywords: S급 키워드 수
        - a_grade_keywords: A급 키워드 수
        - total_leads: 총 리드 수
        - pending_leads: 대기 중인 리드 수
        - viral_targets: 바이럴 타겟 수
        - ranking_keywords: 순위 추적 중인 키워드 수
    """
    # [성능 최적화] 캐시에서 먼저 조회
    cached = hud_metrics_cache.get('metrics')
    if cached is not None:
        logger.debug("HUD 메트릭 캐시 히트")
        return cached

    try:
        db = DatabaseManager()

        # [성능 최적화] Context Manager로 안전한 연결 관리
        with db.get_new_connection() as conn:
            cursor = conn.cursor()

            # [성능 최적화] 4개 개별 쿼리 → 1개 통합 쿼리
            # 4회 DB 왕복 → 1회, 응답 시간 480ms → 150ms 이하
            cursor.execute("""
                SELECT
                    (SELECT COUNT(*) FROM keyword_insights) as total_keywords,
                    (SELECT SUM(CASE WHEN grade = 'S' THEN 1 ELSE 0 END) FROM keyword_insights) as s_grade,
                    (SELECT SUM(CASE WHEN grade = 'A' THEN 1 ELSE 0 END) FROM keyword_insights) as a_grade,
                    (SELECT COUNT(*) FROM mentions) as total_leads,
                    (SELECT SUM(CASE WHEN status IN ('New', 'pending') THEN 1 ELSE 0 END) FROM mentions) as pending_leads,
                    (SELECT COUNT(*) FROM viral_targets) as viral_total,
                    (SELECT SUM(CASE WHEN comment_status = 'pending' OR comment_status IS NULL THEN 1 ELSE 0 END) FROM viral_targets) as viral_pending,
                    (SELECT SUM(CASE WHEN comment_status = 'completed' OR comment_status = 'posted' THEN 1 ELSE 0 END) FROM viral_targets) as viral_completed,
                    (SELECT COUNT(DISTINCT keyword) FROM rank_history) as ranking_keywords
            """)
            stats = cursor.fetchone()

            # 통합 쿼리 결과 파싱
            total_keywords = stats[0] or 0
            s_grade = stats[1] or 0
            a_grade = stats[2] or 0
            total_leads = stats[3] or 0
            pending_leads = stats[4] or 0
            viral_total = stats[5] or 0
            viral_count = stats[6] or 0
            viral_completed = stats[7] or 0
            ranking_count = stats[8] or 0
            viral_completion_rate = round((viral_completed / viral_total * 100), 1) if viral_total > 0 else 0

        # [Phase B] AI 인사이트 조회
        ai_insights = {
            "rank_alerts": [],
            "timing_recommendations": [],
            "rising_keywords": 0,
            "falling_keywords": 0
        }
        try:
            from services.intelligence import get_marketing_intelligence
            intelligence = get_marketing_intelligence()
            insights = intelligence.get_dashboard_insights()
            ai_insights["rank_alerts"] = insights.get("rank_alerts", [])[:3]  # 상위 3개만
            ai_insights["timing_recommendations"] = insights.get("timing_recommendations", [])
            # 순위 예측에서 상승/하락 키워드 수 계산 (별도 연결 사용)
            with db.get_new_connection() as intel_conn:
                intel_cursor = intel_conn.cursor()
                intel_cursor.execute("""
                    SELECT trend, COUNT(*) FROM rank_predictions
                    WHERE predicted_at >= datetime('now', '-1 day')
                    GROUP BY trend
                """)
                for row in intel_cursor.fetchall():
                    if row[0] == 'rising':
                        ai_insights["rising_keywords"] = row[1]
                    elif row[0] == 'falling':
                        ai_insights["falling_keywords"] = row[1]
        except Exception as intel_err:
            logger.debug(f"AI 인사이트 조회 스킵: {intel_err}")

        result = {
            "total_keywords": total_keywords,
            "s_grade_keywords": s_grade,
            "a_grade_keywords": a_grade,
            "total_leads": total_leads,
            "pending_leads": pending_leads,
            "viral_targets": viral_count,
            "viral_total": viral_total,
            "viral_completed": viral_completed,
            "viral_completion_rate": viral_completion_rate,
            "ranking_keywords": ranking_count,
            "ai_insights": ai_insights  # [Phase B] AI 인사이트
        }

        # [성능 최적화] 캐시에 저장
        hud_metrics_cache.set('metrics', result)
        logger.debug("HUD 메트릭 캐시 업데이트")

        return result

    except Exception as e:
        # 에러 로깅
        logger.error(f"Metrics 오류: {str(e)}", exc_info=True)
        import traceback
        traceback.print_exc()
        # DB 에러 시 500 반환
        raise HTTPException(
            status_code=500,
            detail=f"메트릭 조회 실패: {str(e)}"
        )

def convert_to_kst_legacy(utc_timestamp: str) -> str:  # noqa: F811
    """(보관용) — services.hud_service.convert_to_kst 사용 권장."""
    from services.hud_service import convert_to_kst as _svc
    return _svc(utc_timestamp)


def convert_to_kst(utc_timestamp: str) -> str:
    """UTC 타임스탬프를 한국 시간(KST, UTC+9)으로 변환"""
    if not utc_timestamp:
        return None
    try:
        # SQLite CURRENT_TIMESTAMP 형식: 'YYYY-MM-DD HH:MM:SS'
        dt = datetime.strptime(utc_timestamp.split('.')[0], '%Y-%m-%d %H:%M:%S')
        # UTC+9 (한국 시간)
        kst = dt + timedelta(hours=9)
        return kst.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError, AttributeError):
        return utc_timestamp


@router.get("/system-status")
async def get_system_status() -> Dict[str, Any]:
    """
    시스템 상태 조회 (15초 TTL 캐시 적용)

    Returns:
        - scheduler_status: 스케줄러 상태
        - last_pathfinder_run: 마지막 Pathfinder 실행 시간 (KST)
        - last_rank_check: 마지막 순위 체크 시간 (KST)
        - active_tasks: 활성 작업 수
    """
    # [성능 최적화] 캐시에서 먼저 조회
    cached = system_status_cache.get('status')
    if cached is not None:
        return cached

    conn = None
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 마지막 Pathfinder 실행 시간 (keyword_insights의 최신 created_at)
        # [Phase 2 최적화] LIKE '%x%' → LIKE 'x%'로 변경 (인덱스 활용)
        cursor.execute("""
            SELECT MAX(created_at) FROM keyword_insights
            WHERE source LIKE 'legion%' OR source LIKE 'autocomplete%'
        """)
        last_pathfinder = cursor.fetchone()[0]

        # 마지막 순위 체크 시간
        cursor.execute("SELECT MAX(checked_at) FROM rank_history")
        last_rank_check = cursor.fetchone()[0]

        conn.close()

        result = {
            "scheduler_status": "running",
            "last_pathfinder_run": convert_to_kst(last_pathfinder),
            "last_rank_check": convert_to_kst(last_rank_check),
            "active_tasks": 0
        }

        # [성능 최적화] 캐시에 저장
        system_status_cache.set('status', result)

        return result

    except Exception as e:
        logger.error(f"System Status 오류: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"시스템 상태 조회 실패: {str(e)}"
        )

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
@router.get("/briefing")
@handle_exceptions
async def get_daily_briefing() -> Dict[str, Any]:
    """
    일일 브리핑 조회

    Returns:
        - date: 브리핑 날짜
        - summary: 주요 이벤트 요약
        - keyword_highlights: 주요 키워드 변화
        - lead_summary: 리드 현황
        - recommended_actions: 권장 액션 목록
    """
    default_response = {
        "date": None,
        "summary": "브리핑 데이터를 불러올 수 없습니다.",
        "keyword_highlights": {"new_keywords": 0, "new_s_grade": 0, "top_keywords": []},
        "lead_summary": {"new_leads": 0},
        "recommended_actions": [],
        "recent_insights": []
    }

    conn = None
    try:
        logger.info("Briefing 시작...")
        db = DatabaseManager()
        logger.debug(f"Briefing DB path: {db.db_path}")
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        new_keywords_count = 0
        new_sa_count = 0
        new_leads_count = 0
        top_keywords = []

        # 테이블 존재 여부 확인: keyword_insights
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_insights'")
        if cursor.fetchone():
            # 최근 24시간 키워드 변화
            cursor.execute("""
                SELECT COUNT(*) FROM keyword_insights
                WHERE created_at >= datetime('now', '-1 day')
            """)
            new_keywords_count = cursor.fetchone()[0] or 0

            # 최근 24시간 S/A급 키워드
            cursor.execute("""
                SELECT COUNT(*) FROM keyword_insights
                WHERE created_at >= datetime('now', '-1 day')
                AND grade IN ('S', 'A')
            """)
            new_sa_count = cursor.fetchone()[0] or 0

            # 상위 S급 키워드 (최근 추가)
            cursor.execute("""
                SELECT keyword, search_volume, grade
                FROM keyword_insights
                WHERE grade = 'S'
                AND created_at >= datetime('now', '-7 days')
                ORDER BY search_volume DESC
                LIMIT 5
            """)
            top_keywords = [
                {"keyword": row[0], "volume": row[1], "grade": row[2]}
                for row in cursor.fetchall()
            ]

        # 테이블 존재 여부 확인: mentions
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if cursor.fetchone():
            # 컬럼 확인
            cursor.execute("PRAGMA table_info(mentions)")
            columns = [row[1] for row in cursor.fetchall()]

            # 날짜 컬럼 결정
            date_col = 'detected_at' if 'detected_at' in columns else 'scraped_at'

            # 최근 24시간 리드
            cursor.execute(f"""
                SELECT COUNT(*) FROM mentions
                WHERE {date_col} >= datetime('now', '-1 day')
            """)
            new_leads_count = cursor.fetchone()[0] or 0

        # insights 테이블에서 최근 인사이트 조회
        recent_insights = []
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='insights'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT type, title, content, created_at
                FROM insights
                WHERE status = 'new'
                AND created_at >= datetime('now', '-1 day')
                ORDER BY created_at DESC
                LIMIT 10
            """)
            recent_insights = [
                {
                    "type": row[0] or "unknown",
                    "title": row[1] or "제목 없음",
                    "content": (row[2][:200] + "..." if row[2] and len(row[2]) > 200 else row[2]) or "",
                    "created_at": row[3]
                }
                for row in cursor.fetchall()
            ]

        # 권장 액션 생성
        recommended_actions = []
        if new_sa_count > 0:
            recommended_actions.append({
                "type": "keyword",
                "priority": "high",
                "action": f"새로운 S/A급 키워드 {new_sa_count}개에 대한 콘텐츠 제작 권장"
            })
        if new_leads_count > 10:
            recommended_actions.append({
                "type": "lead",
                "priority": "medium",
                "action": f"최근 24시간 내 {new_leads_count}개 리드 발생, 빠른 응대 필요"
            })

        # [Phase 4.0] 긴급 액션 생성
        urgent_actions = []

        # 1. Hot Lead 미처리 확인
        hot_leads_pending = 0
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(mentions)")
            cols = [row[1] for row in cursor.fetchall()]
            date_col_urgent = 'created_at' if 'created_at' in cols else 'scraped_at'

            # pending 상태인 최근 리드 조회 (Hot Lead 점수 기준은 프론트에서 적용)
            cursor.execute(f"""
                SELECT COUNT(*) FROM mentions
                WHERE status = 'pending'
                AND {date_col_urgent} <= datetime('now', '-24 hours')
            """)
            hot_leads_pending = cursor.fetchone()[0] or 0

        if hot_leads_pending > 0:
            urgent_actions.append({
                "type": "hot_lead",
                "priority": "critical",
                "title": "Hot Lead 미처리",
                "description": f"{hot_leads_pending}개 리드가 24시간 이상 대기 중",
                "action_label": "리드 관리로 이동",
                "action_link": "/leads?status=pending"
            })

        # 2. 순위 급락 키워드 확인 (최적화: CTE 사용)
        rank_drops = 0
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rank_history'")
        if cursor.fetchone():
            # 최적화: 최근 데이터만 조회 + CTE로 한 번에 처리
            cursor.execute("""
                WITH recent_ranks AS (
                    SELECT
                        keyword,
                        rank,
                        DATE(checked_at) as check_date,
                        ROW_NUMBER() OVER (PARTITION BY keyword ORDER BY checked_at DESC) as rn
                    FROM rank_history
                    WHERE status = 'found'
                      AND rank > 0
                      AND checked_at >= datetime('now', '-14 days')
                ),
                latest AS (
                    SELECT keyword, rank as latest_rank
                    FROM recent_ranks WHERE rn = 1
                ),
                week_ago AS (
                    SELECT keyword, rank as week_ago_rank
                    FROM recent_ranks
                    WHERE check_date <= DATE('now', '-6 days')
                      AND check_date >= DATE('now', '-8 days')
                      AND rn <= 2
                    GROUP BY keyword
                )
                SELECT l.keyword
                FROM latest l
                JOIN week_ago w ON l.keyword = w.keyword
                WHERE l.latest_rank - w.week_ago_rank >= 5
            """)
            dropped_keywords = cursor.fetchall()
            rank_drops = len(dropped_keywords)

        if rank_drops > 0:
            urgent_actions.append({
                "type": "rank_drop",
                "priority": "high",
                "title": "순위 급락 감지",
                "description": f"{rank_drops}개 키워드가 지난주 대비 5위 이상 하락",
                "action_label": "순위 분석으로 이동",
                "action_link": "/battle?tab=trends"
            })

        # 3. 경쟁사 신규 리뷰 확인
        new_competitor_reviews = 0
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitor_reviews'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT COUNT(*) FROM competitor_reviews
                WHERE scraped_at >= datetime('now', '-7 days')
            """)
            new_competitor_reviews = cursor.fetchone()[0] or 0

        if new_competitor_reviews > 5:
            urgent_actions.append({
                "type": "competitor",
                "priority": "medium",
                "title": "경쟁사 리뷰 동향",
                "description": f"지난 7일간 경쟁사 리뷰 {new_competitor_reviews}개 수집됨",
                "action_label": "경쟁사 분석으로 이동",
                "action_link": "/competitors?tab=weaknesses"
            })

        conn.close()

        return {
            "date": None,  # 프론트엔드에서 현재 날짜 사용
            "summary": f"최근 24시간 동안 {new_keywords_count}개 키워드 수집, {new_sa_count}개 S/A급 발견",
            "keyword_highlights": {
                "new_keywords": new_keywords_count,
                "new_s_grade": new_sa_count,
                "top_keywords": top_keywords
            },
            "lead_summary": {
                "new_leads": new_leads_count
            },
            "recommended_actions": recommended_actions,
            "recent_insights": recent_insights,
            "urgent_actions": urgent_actions
        }

    except Exception as e:
        import traceback
        logger.error(f"Briefing 오류: {str(e)}", exc_info=True)
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"브리핑 조회 실패: {str(e)}"
        )

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
@router.get("/sentinel-alerts")
@handle_exceptions
async def get_sentinel_alerts() -> Dict[str, Any]:
    """
    Sentinel 경고 알림 조회

    Returns:
        - alert_count: 알림 개수
        - alerts: 알림 목록
        - status: 전체 상태 (normal, warning, critical)
    """
    default_response = {
        "alert_count": 0,
        "alerts": [],
        "status": "normal"
    }

    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        negative_count = 0
        negative_mentions = []

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if cursor.fetchone():
            # 컬럼 확인
            cursor.execute("PRAGMA table_info(mentions)")
            columns = [row[1] for row in cursor.fetchall()]

            # 날짜 컬럼 결정
            date_col = 'detected_at' if 'detected_at' in columns else 'scraped_at'
            has_sentiment = 'sentiment' in columns
            text_col = 'text' if 'text' in columns else 'content'
            platform_col = 'platform' if 'platform' in columns else 'source'

            if has_sentiment:
                # 부정적 멘션 조회
                cursor.execute(f"""
                    SELECT COUNT(*) FROM mentions
                    WHERE sentiment = 'negative'
                    AND {date_col} >= datetime('now', '-7 days')
                """)
                negative_count = cursor.fetchone()[0] or 0

                # 최근 부정적 멘션
                cursor.execute(f"""
                    SELECT {platform_col}, {text_col}, {date_col}
                    FROM mentions
                    WHERE sentiment = 'negative'
                    AND {date_col} >= datetime('now', '-7 days')
                    ORDER BY {date_col} DESC
                    LIMIT 5
                """)
                negative_mentions = [
                    {
                        "platform": row[0],
                        "text": row[1][:100] if row[1] else "",
                        "detected_at": row[2]
                    }
                    for row in cursor.fetchall()
                ]

        conn.close()

        # 알림 생성
        alerts = []
        if negative_count > 0:
            alerts.append({
                "type": "reputation",
                "severity": "warning" if negative_count < 5 else "critical",
                "message": f"최근 7일간 {negative_count}건의 부정적 멘션 발견",
                "details": negative_mentions
            })

        # 전체 상태 결정
        if negative_count >= 5:
            status = "critical"
        elif negative_count > 0:
            status = "warning"
        else:
            status = "normal"

        return {
            "alert_count": len(alerts),
            "alerts": alerts,
            "status": status
        }

    except Exception as e:
        logger.error(f"Sentinel Alerts 오류: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Sentinel 알림 조회 실패: {str(e)}"
        )

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
@router.get("/scheduler-state")
async def get_scheduler_state() -> Dict[str, Any]:
    """
    Chronos Timeline 스케줄러 상태 조회

    Returns:
        - schedule: 전체 스케줄 목록 (상태 포함)
        - current_time: 현재 시간
        - today: 오늘 날짜
    """
    try:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        today_str = now.strftime("%Y-%m-%d")

        # 스케줄러 상태 파일 읽기
        scheduler_state = {}
        if os.path.exists(SCHEDULER_STATE_FILE):
            try:
                with open(SCHEDULER_STATE_FILE, 'r', encoding='utf-8') as f:
                    scheduler_state = json.load(f)
            except (json.JSONDecodeError, IOError):
                scheduler_state = {}

        # 각 스케줄 항목에 상태 추가
        schedule_with_status = []
        for item in CHRONOS_SCHEDULE:
            item_time = item["time"]
            item_minutes = int(item_time.split(":")[0]) * 60 + int(item_time.split(":")[1])
            current_minutes = int(current_time.split(":")[0]) * 60 + int(current_time.split(":")[1])

            # 03:00은 다음날로 처리
            if item_time == "03:00":
                item_minutes += 24 * 60

            # 상태 결정
            last_run = scheduler_state.get(item_time, "")
            with running_processes_lock:
                is_running = item["cmd"] in running_processes and running_processes[item["cmd"]].poll() is None

            if is_running:
                status = "running"
            elif last_run == today_str:
                status = "done"
            elif current_minutes >= item_minutes:
                status = "missed"  # 시간이 지났지만 실행 안됨
            elif abs(current_minutes - item_minutes) <= 30:  # 30분 이내
                status = "upcoming"
            else:
                status = "pending"

            schedule_with_status.append({
                **item,
                "status": status,
                "last_run": last_run
            })

        with running_processes_lock:
            running_count = len([p for p in running_processes.values() if p.poll() is None])
        return {
            "schedule": schedule_with_status,
            "current_time": current_time,
            "today": today_str,
            "running_count": running_count
        }

    except Exception as e:
        return {
            "schedule": CHRONOS_SCHEDULE,
            "current_time": datetime.now().strftime("%H:%M"),
            "today": datetime.now().strftime("%Y-%m-%d"),
            "error": str(e)
        }


def run_module_in_background(module_name: str):
    """백그라운드에서 모듈 실행"""
    global running_processes

    if module_name not in CMD_MAP:
        return

    cmd = CMD_MAP[module_name]

    try:
        # 로그 파일 경로
        log_dir = os.path.join(parent_dir, 'logs')
        os.makedirs(log_dir, exist_ok=True)

        # Pathfinder 모듈은 TeeWriter가 직접 로그 파일을 관리함 (실시간 스트리밍)
        if module_name in ['pathfinder', 'pathfinder_legion']:
            # TeeWriter가 logs/pathfinder_live.log에 직접 쓰므로
            # stdout은 DEVNULL로 설정 (TeeWriter의 터미널 출력은 버림)
            process = subprocess.Popen(
                cmd,
                cwd=parent_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False
            )
            with running_processes_lock:
                running_processes[module_name] = process

            # [Phase 8] Subprocess 모니터링 - 프로세스 완료 시 정리
            def cleanup_pathfinder(proc, mod_name):
                try:
                    # 타임아웃 설정 (최대 30분)
                    proc.wait(timeout=1800)
                except subprocess.TimeoutExpired:
                    logger.warning(f"프로세스 타임아웃 ({mod_name}), 강제 종료")
                    proc.kill()
                    proc.wait()
                finally:
                    with running_processes_lock:
                        if mod_name in running_processes:
                            del running_processes[mod_name]
                    logger.info(f"프로세스 종료 및 정리 완료: {mod_name}")

            threading.Thread(
                target=cleanup_pathfinder,
                args=(process, module_name),
                daemon=True
            ).start()
        else:
            # 다른 모듈은 기존 방식 유지 (stdout을 로그 파일로 리다이렉트)
            log_file = os.path.join(log_dir, f'{module_name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            # [M2] Popen 실패 시 파일 핸들 누수 방지
            log_handle = None
            try:
                log_handle = open(log_file, 'w', encoding='utf-8')
                process = subprocess.Popen(
                    cmd,
                    cwd=parent_dir,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    shell=False
                )
            except Exception as e:
                if log_handle is not None:
                    try:
                        log_handle.close()
                    except Exception:
                        pass
                raise HTTPException(status_code=500, detail=f"프로세스 실행 실패: {e}")

            with running_processes_lock:
                running_processes[module_name] = process

            # [Phase 8] Subprocess 모니터링 - 프로세스 완료 대기 및 정리
            def cleanup_with_monitoring(proc, mod_name, handle):
                try:
                    # 타임아웃 설정 (최대 30분)
                    proc.wait(timeout=1800)
                except subprocess.TimeoutExpired:
                    logger.warning(f"프로세스 타임아웃 ({mod_name}), 강제 종료")
                    proc.kill()
                    proc.wait()
                finally:
                    handle.close()
                    with running_processes_lock:
                        if mod_name in running_processes:
                            del running_processes[mod_name]
                    logger.info(f"프로세스 종료 및 정리 완료: {mod_name}")

            threading.Thread(
                target=cleanup_with_monitoring,
                args=(process, module_name, log_handle),
                daemon=True
            ).start()

        # 스케줄러 상태 업데이트
        scheduler_state = {}
        if os.path.exists(SCHEDULER_STATE_FILE):
            try:
                with open(SCHEDULER_STATE_FILE, 'r', encoding='utf-8') as f:
                    scheduler_state = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"스케줄러 상태 파일 로드 실패: {e}")
                scheduler_state = {}

        # 해당 모듈의 스케줄 시간 찾기
        for item in CHRONOS_SCHEDULE:
            if item["cmd"] == module_name:
                scheduler_state[item["time"]] = datetime.now().strftime("%Y-%m-%d")
                break

        # 상태 파일 저장
        os.makedirs(os.path.dirname(SCHEDULER_STATE_FILE), exist_ok=True)
        with open(SCHEDULER_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(scheduler_state, f, indent=2)

    except Exception as e:
        logger.error(f"모듈 실행 오류 ({module_name}): {e}")


@router.post("/mission/{module_name}")
async def execute_mission(module_name: str, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Mission Control - 모듈 실행

    Args:
        module_name: 실행할 모듈 (pathfinder, battle, sentinel, youtube, etc.)

    Returns:
        - success: 성공 여부
        - message: 실행 메시지
        - module: 실행된 모듈명
    """
    if module_name not in CMD_MAP:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 모듈: {module_name}")

    # 이미 실행 중인지 확인 (스레드 안전)
    with running_processes_lock:
        if module_name in running_processes:
            process = running_processes[module_name]
            if process.poll() is None:  # 아직 실행 중
                return {
                    "success": False,
                    "message": f"{module_name} 모듈이 이미 실행 중입니다.",
                    "module": module_name,
                    "status": "already_running"
                }

    # 백그라운드에서 모듈 실행
    background_tasks.add_task(run_module_in_background, module_name)

    return {
        "success": True,
        "message": f"{module_name} 모듈 실행이 시작되었습니다.",
        "module": module_name,
        "status": "started"
    }


@router.post("/mission/{module_name}/stop")
async def stop_mission(module_name: str) -> Dict[str, Any]:
    """
    실행 중인 모듈 중지

    Args:
        module_name: 중지할 모듈

    Returns:
        - success: 성공 여부
        - message: 메시지
    """
    with running_processes_lock:
        if module_name not in running_processes:
            return {
                "success": False,
                "message": f"{module_name} 모듈이 실행 중이 아닙니다."
            }

        process = running_processes[module_name]
        if process.poll() is not None:  # 이미 종료됨
            del running_processes[module_name]
            return {
                "success": True,
                "message": f"{module_name} 모듈이 이미 종료되었습니다."
            }

        try:
            process.terminate()
            process.wait(timeout=5)
            del running_processes[module_name]
            return {
                "success": True,
                "message": f"{module_name} 모듈이 중지되었습니다."
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"모듈 중지 실패: {str(e)}"
            }


@router.get("/running-modules")
async def get_running_modules() -> Dict[str, Any]:
    """
    현재 실행 중인 모듈 목록 조회
    """
    running = []
    completed = []

    with running_processes_lock:
        for module_name, process in list(running_processes.items()):
            if process.poll() is None:
                running.append(module_name)
            else:
                completed.append(module_name)
                # 완료된 프로세스 정리
                del running_processes[module_name]

    return {
        "running": running,
        "completed": completed,
        "count": len(running)
    }


@router.get("/mission/{module_name}/status")
async def get_mission_status(module_name: str, lines: int = 20) -> Dict[str, Any]:
    """
    모듈 실행 상태 및 최근 로그 조회

    Args:
        module_name: 모듈명
        lines: 반환할 로그 줄 수 (기본 20줄)

    Returns:
        - status: running, completed, not_found
        - logs: 최근 로그 라인들
        - log_file: 로그 파일 경로
        - started_at: 시작 시간 (로그 파일명에서 추출)
    """
    # 실행 중 여부 확인
    is_running = False
    if module_name in running_processes:
        process = running_processes[module_name]
        is_running = process.poll() is None

    # 로그 파일 찾기 (가장 최근 것)
    log_dir = os.path.join(parent_dir, 'logs')
    log_files = []

    if os.path.exists(log_dir):
        for f in os.listdir(log_dir):
            if f.startswith(f'{module_name}_') and f.endswith('.log'):
                log_files.append(os.path.join(log_dir, f))

    if not log_files:
        return {
            "status": "not_found",
            "logs": [],
            "message": f"{module_name} 로그를 찾을 수 없습니다."
        }

    # 가장 최근 로그 파일
    latest_log = max(log_files, key=os.path.getmtime)

    # 로그 파일에서 마지막 N줄 읽기
    log_lines = []
    try:
        with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
            log_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            log_lines = [line.strip() for line in log_lines if line.strip()]
    except Exception as e:
        log_lines = [f"로그 읽기 오류: {str(e)}"]

    # 시작 시간 추출 (파일명에서)
    started_at = None
    try:
        filename = os.path.basename(latest_log)
        # weakness_analyzer_20260205_143022.log 형식
        timestamp_part = filename.replace(f'{module_name}_', '').replace('.log', '')
        started_at = datetime.strptime(timestamp_part, '%Y%m%d_%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError, AttributeError) as e:
        logger.debug(f"로그 파일명에서 시작 시간 추출 실패: {e}")
        started_at = None

    # 진행 상황 파싱 (로그에서 키워드 추출)
    progress_info = {}
    for line in log_lines:
        if '수집' in line or '분석' in line or '완료' in line:
            progress_info['last_action'] = line
        if '경쟁사' in line:
            progress_info['competitor'] = line
        if '%' in line or '/' in line:
            progress_info['progress'] = line

    return {
        "status": "running" if is_running else "completed",
        "logs": log_lines,
        "log_file": latest_log,
        "started_at": started_at,
        "progress": progress_info,
        "total_lines": len(all_lines) if 'all_lines' in locals() else 0
    }


@router.get("/recent-activities")
async def get_recent_activities() -> List[Dict[str, Any]]:
    """
    최근 활동 조회 (실제 DB 데이터 기반)

    Returns:
        - 최근 활동 목록 (타입, 설명, 시간)
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        activities = []

        # 1. 가장 최근 키워드 발굴 (keyword_insights)
        cursor.execute("""
            SELECT MAX(created_at) as last_time, COUNT(*) as count
            FROM keyword_insights
            WHERE created_at >= datetime('now', '-7 days')
        """)
        row = cursor.fetchone()
        if row and row['last_time']:
            activities.append({
                "type": "pathfinder",
                "icon": "🎯",
                "label": "키워드 발굴",
                "description": f"{row['count']}개 키워드 수집",
                "timestamp": row['last_time']
            })

        # 2. 가장 최근 순위 체크 (rank_history)
        cursor.execute("""
            SELECT MAX(checked_at) as last_time, COUNT(DISTINCT keyword) as count
            FROM rank_history
            WHERE checked_at >= datetime('now', '-7 days')
        """)
        row = cursor.fetchone()
        if row and row['last_time']:
            activities.append({
                "type": "battle",
                "icon": "⚔️",
                "label": "순위 체크",
                "description": f"{row['count']}개 키워드 순위 추적",
                "timestamp": row['last_time']
            })

        # 3. 가장 최근 리드 수집 (mentions - platform별)
        cursor.execute("""
            SELECT source, MAX(scraped_at) as last_time, COUNT(*) as count
            FROM mentions
            WHERE scraped_at >= datetime('now', '-7 days')
            GROUP BY source
            ORDER BY last_time DESC
            LIMIT 5
        """)
        for row in cursor.fetchall():
            source = row['source'] or '기타'
            icon = "📋"
            if 'instagram' in source.lower():
                icon = "📸"
            elif 'youtube' in source.lower():
                icon = "📺"
            elif 'cafe' in source.lower():
                icon = "☕"
            elif 'tiktok' in source.lower():
                icon = "🎵"
            elif 'carrot' in source.lower() or '당근' in source.lower():
                icon = "🥕"

            activities.append({
                "type": source,
                "icon": icon,
                "label": f"{source} 스캔",
                "description": f"{row['count']}개 리드 수집",
                "timestamp": row['last_time']
            })

        # 4. 경쟁사 분석 (competitor_reviews 또는 competitor_weaknesses)
        try:
            cursor.execute("""
                SELECT MAX(scraped_at) as last_time, COUNT(*) as count
                FROM competitor_reviews
                WHERE scraped_at >= datetime('now', '-7 days')
            """)
            row = cursor.fetchone()
            if row and row['last_time']:
                activities.append({
                    "type": "competitor",
                    "icon": "💪",
                    "label": "경쟁사 분석",
                    "description": f"{row['count']}개 리뷰 분석",
                    "timestamp": row['last_time']
                })
        except sqlite3.Error as e:
            logger.warning(f"경쟁사 활동 조회 실패: {e}")

        conn.close()

        # 시간순 정렬 (최신 순)
        activities.sort(key=lambda x: x['timestamp'] or '', reverse=True)

        # 상대 시간 계산 추가
        now = datetime.now()
        for activity in activities:
            if activity['timestamp']:
                try:
                    # SQLite datetime 형식 파싱
                    ts = datetime.fromisoformat(activity['timestamp'].replace('Z', '+00:00').split('+')[0])
                    diff = now - ts
                    hours = diff.total_seconds() / 3600

                    if hours < 1:
                        activity['relative_time'] = f"{int(diff.total_seconds() / 60)}분 전"
                    elif hours < 24:
                        activity['relative_time'] = f"{int(hours)}시간 전"
                    elif hours < 168:  # 7일
                        activity['relative_time'] = f"{int(hours / 24)}일 전"
                    else:
                        activity['relative_time'] = activity['timestamp'][:10]
                except (ValueError, TypeError, AttributeError):
                    activity['relative_time'] = activity['timestamp']
            else:
                activity['relative_time'] = '-'

        return activities[:10]  # 최근 10개만

    except Exception as e:
        logger.error(f"Recent Activities 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"최근 활동 조회 실패: {str(e)}")


    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
@router.get("/metrics-trend")
async def get_metrics_trend(days: int = 7) -> Dict[str, Any]:
    """
    [Phase 8.0] 메트릭 트렌드 조회 (최근 N일)

    Args:
        days: 조회 기간 (기본 7일)

    Returns:
        - keywords: 일별 키워드 수
        - s_grade: 일별 S급 키워드 수
        - leads: 일별 리드 수
        - previous_values: 어제 대비 값 (트렌드 계산용)
    """
    default_response = {
        'keywords': [],
        's_grade': [],
        'a_grade': [],
        'leads': [],
        'previous_values': {
            'keywords': None,
            's_grade': None,
            'a_grade': None,
            'leads': None
        }
    }

    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 일별 키워드 수 (created_at 기준)
        cursor.execute("""
            SELECT
                DATE(created_at) as date,
                COUNT(*) as count,
                SUM(CASE WHEN grade = 'S' THEN 1 ELSE 0 END) as s_count,
                SUM(CASE WHEN grade = 'A' THEN 1 ELSE 0 END) as a_count
            FROM keyword_insights
            WHERE created_at >= DATE('now', ? || ' days')
            GROUP BY DATE(created_at)
            ORDER BY date
        """, (f'-{days}',))
        keyword_rows = cursor.fetchall()

        # 일별 리드 수
        cursor.execute("""
            SELECT
                DATE(scraped_at) as date,
                COUNT(*) as count
            FROM mentions
            WHERE scraped_at >= DATE('now', ? || ' days')
            GROUP BY DATE(scraped_at)
            ORDER BY date
        """, (f'-{days}',))
        lead_rows = cursor.fetchall()

        # 날짜별 데이터 구성
        keywords_by_date = {row[0]: row[1] for row in keyword_rows}
        s_grade_by_date = {row[0]: row[2] for row in keyword_rows}
        a_grade_by_date = {row[0]: row[3] for row in keyword_rows}
        leads_by_date = {row[0]: row[1] for row in lead_rows}

        # 모든 날짜 리스트 생성
        dates = []
        keywords_data = []
        s_grade_data = []
        a_grade_data = []
        leads_data = []

        for i in range(days, 0, -1):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            dates.append(date)
            keywords_data.append(keywords_by_date.get(date, 0))
            s_grade_data.append(s_grade_by_date.get(date, 0))
            a_grade_data.append(a_grade_by_date.get(date, 0))
            leads_data.append(leads_by_date.get(date, 0))

        # 누적 합계 계산 (스파크라인용)
        cumulative_keywords = []
        cumulative_s_grade = []
        cumulative_a_grade = []
        cumulative_leads = []
        running_kw = 0
        running_s = 0
        running_a = 0
        running_leads = 0

        for i in range(len(keywords_data)):
            running_kw += keywords_data[i]
            running_s += s_grade_data[i]
            running_a += a_grade_data[i]
            running_leads += leads_data[i]
            cumulative_keywords.append(running_kw)
            cumulative_s_grade.append(running_s)
            cumulative_a_grade.append(running_a)
            cumulative_leads.append(running_leads)

        # 어제 대비 값 계산
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        cursor.execute("""
            SELECT COUNT(*),
                   SUM(CASE WHEN grade = 'S' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN grade = 'A' THEN 1 ELSE 0 END)
            FROM keyword_insights
            WHERE DATE(created_at) < DATE('now')
        """)
        prev_kw = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*) FROM mentions WHERE DATE(scraped_at) < DATE('now')
        """)
        prev_leads = cursor.fetchone()

        conn.close()

        return {
            'dates': dates,
            'keywords': keywords_data,
            's_grade': s_grade_data,
            'a_grade': a_grade_data,
            'leads': leads_data,
            'cumulative': {
                'keywords': cumulative_keywords,
                's_grade': cumulative_s_grade,
                'a_grade': cumulative_a_grade,
                'leads': cumulative_leads
            },
            'previous_values': {
                'keywords': prev_kw[0] if prev_kw else None,
                's_grade': prev_kw[1] if prev_kw else None,
                'a_grade': prev_kw[2] if prev_kw else None,
                'leads': prev_leads[0] if prev_leads else None
            }
        }

    except Exception as e:
        logger.error(f"Metrics Trend 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"메트릭 트렌드 조회 실패: {str(e)}")


# =====================================
# 목표 관리 API
# =====================================

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
from pydantic import BaseModel

class GoalCreate(BaseModel):
    type: str  # leads, keywords, conversions, rank
    target_value: int
    period: str = "monthly"  # monthly, weekly, daily
    title: str = ""

class GoalUpdate(BaseModel):
    target_value: int = None
    title: str = None


@router.get("/goals")
async def get_goals() -> List[Dict[str, Any]]:
    """
    현재 활성화된 목표 목록 조회 (현재 달성률 포함)
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 테이블 존재 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='goals'")
        if not cursor.fetchone():
            conn.close()
            return []

        # [Phase 7] SELECT * 제거 - 현재 활성 목표 조회 (종료일이 오늘 이후)
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("""
            SELECT id, type, target_value, period, start_date, end_date, title, created_at
            FROM goals
            WHERE end_date >= ?
            ORDER BY created_at DESC
        """, (today,))

        goals = []
        for row in cursor.fetchall():
            goal = dict(row)

            # 현재 값 계산 (타입에 따라 다르게)
            current_value = 0
            start_date = goal['start_date']
            end_date = goal['end_date']

            if goal['type'] == 'leads':
                # mentions 테이블에서 기간 내 리드 수
                cursor.execute("""
                    SELECT COUNT(*) FROM mentions
                    WHERE DATE(scraped_at) BETWEEN ? AND ?
                """, (start_date, end_date))
                current_value = cursor.fetchone()[0] or 0

            elif goal['type'] == 'keywords':
                # keyword_insights 테이블에서 기간 내 키워드 수
                cursor.execute("""
                    SELECT COUNT(*) FROM keyword_insights
                    WHERE DATE(created_at) BETWEEN ? AND ?
                """, (start_date, end_date))
                current_value = cursor.fetchone()[0] or 0

            elif goal['type'] == 'conversions':
                # mentions 테이블에서 기간 내 전환 수
                cursor.execute("""
                    SELECT COUNT(*) FROM mentions
                    WHERE status = 'converted'
                    AND DATE(scraped_at) BETWEEN ? AND ?
                """, (start_date, end_date))
                current_value = cursor.fetchone()[0] or 0

            elif goal['type'] == 's_grade':
                # S등급 키워드 수
                cursor.execute("""
                    SELECT COUNT(*) FROM keyword_insights
                    WHERE grade = 'S'
                    AND DATE(created_at) BETWEEN ? AND ?
                """, (start_date, end_date))
                current_value = cursor.fetchone()[0] or 0

            goal['current_value'] = current_value
            goal['progress'] = min(100, round(current_value / goal['target_value'] * 100, 1)) if goal['target_value'] > 0 else 0
            goal['remaining'] = max(0, goal['target_value'] - current_value)

            # 남은 일수 계산
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            days_remaining = (end_dt - datetime.now()).days + 1
            goal['days_remaining'] = max(0, days_remaining)

            goals.append(goal)

        conn.close()
        return goals

    except Exception as e:
        logger.error(f"Goals 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"목표 조회 실패: {str(e)}")


    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
@router.post("/goals")
async def create_goal(goal: GoalCreate) -> Dict[str, Any]:
    """
    새 목표 생성
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 기간 계산
        today = datetime.now()
        if goal.period == "monthly":
            start_date = today.replace(day=1).strftime('%Y-%m-%d')
            # 다음 달 1일 - 1일 = 이번 달 마지막 날
            if today.month == 12:
                end_date = today.replace(year=today.year+1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = today.replace(month=today.month+1, day=1) - timedelta(days=1)
            end_date = end_date.strftime('%Y-%m-%d')
        elif goal.period == "weekly":
            # 이번 주 월요일 ~ 일요일
            start_date = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')
            end_date = (today + timedelta(days=6-today.weekday())).strftime('%Y-%m-%d')
        else:  # daily
            start_date = today.strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')

        # 타이틀 자동 생성
        title = goal.title or f"{goal.period.capitalize()} {goal.type} Goal"

        cursor.execute("""
            INSERT INTO goals (type, target_value, period, start_date, end_date, title)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (goal.type, goal.target_value, goal.period, start_date, end_date, title))

        conn.commit()
        goal_id = cursor.lastrowid
        conn.close()

        return {
            'status': 'success',
            'message': '목표가 생성되었습니다',
            'goal_id': goal_id
        }

    except Exception as e:
        logger.error(f"Create Goal 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"목표 생성 실패: {str(e)}")


    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
@router.delete("/goals/{goal_id}")
async def delete_goal(goal_id: int) -> Dict[str, str]:
    """
    목표 삭제
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
        conn.commit()
        conn.close()

        return {'status': 'success', 'message': '목표가 삭제되었습니다'}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"목표 삭제 실패: {str(e)}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 4.0] 주간 리포트 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
@router.get("/weekly-report")
async def get_weekly_report() -> Dict[str, Any]:
    """
    [Phase 4.0] 주간 마케팅 리포트 생성

    지난 7일간의 마케팅 활동 및 성과를 요약합니다.

    Returns:
        - period: 리포트 기간
        - summary: 요약 통계
        - leads: 리드 관련 통계
        - keywords: 키워드 관련 통계
        - rankings: 순위 변화
        - viral: 바이럴 활동
        - insights: AI 인사이트
        - recommendations: 권장 액션
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        today = datetime.now()
        week_ago = today - timedelta(days=7)
        period_start = week_ago.strftime('%Y-%m-%d')
        period_end = today.strftime('%Y-%m-%d')

        report = {
            "period": {
                "start": period_start,
                "end": period_end,
                "generated_at": today.isoformat()
            },
            "summary": {},
            "leads": {},
            "keywords": {},
            "rankings": {},
            "viral": {},
            "insights": [],
            "recommendations": []
        }

        # ========== 리드 통계 ==========
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(mentions)")
            cols = [row[1] for row in cursor.fetchall()]
            date_col = 'created_at' if 'created_at' in cols else 'scraped_at'

            # 주간 신규 리드
            cursor.execute(f"""
                SELECT COUNT(*) FROM mentions
                WHERE DATE({date_col}) >= DATE(?)
            """, (period_start,))
            new_leads = cursor.fetchone()[0] or 0

            # 상태별 현황
            if 'status' in cols:
                cursor.execute(f"""
                    SELECT status, COUNT(*) FROM mentions
                    WHERE DATE({date_col}) >= DATE(?)
                    GROUP BY status
                """, (period_start,))
                status_counts = {row[0]: row[1] for row in cursor.fetchall()}
            else:
                status_counts = {}

            # 전환율
            total = sum(status_counts.values()) if status_counts else 0
            converted = status_counts.get('converted', 0)
            conversion_rate = round(converted / total * 100, 1) if total > 0 else 0

            # 플랫폼별 현황
            platform_col = 'platform' if 'platform' in cols else 'source'
            cursor.execute(f"""
                SELECT {platform_col}, COUNT(*) FROM mentions
                WHERE DATE({date_col}) >= DATE(?)
                GROUP BY {platform_col}
                ORDER BY COUNT(*) DESC
                LIMIT 5
            """, (period_start,))
            by_platform = [{"platform": row[0], "count": row[1]} for row in cursor.fetchall()]

            report["leads"] = {
                "new_leads": new_leads,
                "status_breakdown": status_counts,
                "conversion_rate": conversion_rate,
                "converted_count": converted,
                "by_platform": by_platform
            }

        # ========== 키워드 통계 ==========
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_insights'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(keyword_insights)")
            kw_cols = [row[1] for row in cursor.fetchall()]
            kw_date_col = 'created_at' if 'created_at' in kw_cols else 'discovered_at'

            # 신규 키워드
            cursor.execute(f"""
                SELECT COUNT(*) FROM keyword_insights
                WHERE DATE({kw_date_col}) >= DATE(?)
            """, (period_start,))
            new_keywords = cursor.fetchone()[0] or 0

            # 등급별 현황
            cursor.execute(f"""
                SELECT grade, COUNT(*) FROM keyword_insights
                WHERE DATE({kw_date_col}) >= DATE(?)
                GROUP BY grade
            """, (period_start,))
            by_grade = {row[0]: row[1] for row in cursor.fetchall()}

            # 상위 키워드
            volume_col = 'search_volume' if 'search_volume' in kw_cols else 'volume'
            cursor.execute(f"""
                SELECT keyword, {volume_col}, grade FROM keyword_insights
                WHERE DATE({kw_date_col}) >= DATE(?)
                ORDER BY {volume_col} DESC
                LIMIT 5
            """, (period_start,))
            top_keywords = [
                {"keyword": row[0], "volume": row[1], "grade": row[2]}
                for row in cursor.fetchall()
            ]

            report["keywords"] = {
                "new_keywords": new_keywords,
                "by_grade": by_grade,
                "top_keywords": top_keywords,
                "s_grade_count": by_grade.get('S', 0)
            }

        # ========== 순위 변화 ==========
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rank_history'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(rank_history)")
            rank_cols = [row[1] for row in cursor.fetchall()]
            rank_date_col = 'checked_at' if 'checked_at' in rank_cols else 'created_at'

            # 순위 스캔 횟수
            cursor.execute(f"""
                SELECT COUNT(DISTINCT DATE({rank_date_col})) FROM rank_history
                WHERE DATE({rank_date_col}) >= DATE(?)
            """, (period_start,))
            scan_days = cursor.fetchone()[0] or 0

            # 순위 변화가 큰 키워드
            cursor.execute(f"""
                SELECT keyword,
                       MIN(rank) as best_rank,
                       MAX(rank) as worst_rank,
                       COUNT(*) as scans
                FROM rank_history
                WHERE DATE({rank_date_col}) >= DATE(?)
                  AND rank IS NOT NULL AND rank > 0
                GROUP BY keyword
                HAVING COUNT(*) >= 2
                ORDER BY (MAX(rank) - MIN(rank)) DESC
                LIMIT 5
            """, (period_start,))
            rank_changes = [
                {
                    "keyword": row[0],
                    "best_rank": row[1],
                    "worst_rank": row[2],
                    "change": row[2] - row[1]
                }
                for row in cursor.fetchall()
            ]

            report["rankings"] = {
                "scan_days": scan_days,
                "significant_changes": rank_changes
            }

        # ========== 바이럴 활동 ==========
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='viral_targets'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(viral_targets)")
            viral_cols = [row[1] for row in cursor.fetchall()]
            viral_date_col = 'discovered_at' if 'discovered_at' in viral_cols else 'created_at'

            cursor.execute(f"""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN comment_status = 'posted' THEN 1 ELSE 0 END) as posted,
                    SUM(CASE WHEN comment_status = 'skipped' THEN 1 ELSE 0 END) as skipped
                FROM viral_targets
                WHERE DATE({viral_date_col}) >= DATE(?)
            """, (period_start,))
            row = cursor.fetchone()

            report["viral"] = {
                "total_targets": row[0] or 0,
                "comments_posted": row[1] or 0,
                "targets_skipped": row[2] or 0,
                "engagement_rate": round((row[1] or 0) / row[0] * 100, 1) if row[0] else 0
            }

        conn.close()

        # ========== 요약 및 인사이트 ==========
        leads_data = report.get("leads", {})
        keywords_data = report.get("keywords", {})

        report["summary"] = {
            "total_new_leads": leads_data.get("new_leads", 0),
            "total_converted": leads_data.get("converted_count", 0),
            "total_new_keywords": keywords_data.get("new_keywords", 0),
            "s_grade_keywords": keywords_data.get("s_grade_count", 0),
            "conversion_rate": leads_data.get("conversion_rate", 0)
        }

        # 인사이트 생성
        insights = []
        if leads_data.get("new_leads", 0) > 0:
            best_platform = leads_data.get("by_platform", [{}])[0] if leads_data.get("by_platform") else {}
            if best_platform:
                insights.append(f"이번 주 가장 많은 리드가 {best_platform.get('platform', '알 수 없음')}에서 유입되었습니다 ({best_platform.get('count', 0)}건)")

        if keywords_data.get("s_grade_count", 0) > 0:
            insights.append(f"S급 키워드 {keywords_data.get('s_grade_count')}개를 발굴했습니다. 콘텐츠 제작을 권장합니다.")

        if leads_data.get("conversion_rate", 0) < 5:
            insights.append("전환율이 5% 미만입니다. 팔로업 전략 개선이 필요합니다.")

        report["insights"] = insights

        # 권장 액션
        recommendations = []
        if leads_data.get("status_breakdown", {}).get("pending", 0) > 10:
            pending = leads_data["status_breakdown"]["pending"]
            recommendations.append({
                "priority": "high",
                "action": f"대기 중인 리드 {pending}건에 대한 첫 연락 필요",
                "link": "/leads?status=pending"
            })

        if keywords_data.get("s_grade_count", 0) > 0:
            recommendations.append({
                "priority": "medium",
                "action": "S급 키워드 기반 콘텐츠 작성 권장",
                "link": "/pathfinder?grade=S"
            })

        report["recommendations"] = recommendations

        return report

    except Exception as e:
        logger.error(f"weekly-report 오류: {str(e)}", exc_info=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"주간 리포트 생성 실패: {str(e)}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 4.0] 미응답 리드 리마인더 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
@router.get("/overdue-leads")
async def get_overdue_leads() -> Dict[str, Any]:
    """
    [Phase 4.0] 미응답/지연 리드 조회

    팔로업이 필요한 리드 목록을 반환합니다.

    Returns:
        - overdue_followups: 팔로업 기한 초과 리드
        - stale_leads: 오래된 pending 리드 (3일 이상)
        - no_response_leads: 연락 후 3일 이상 응답 없는 리드
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if not cursor.fetchone():
            conn.close()
            return {"overdue_followups": [], "stale_leads": [], "no_response_leads": []}

        cursor.execute("PRAGMA table_info(mentions)")
        cols = [row[1] for row in cursor.fetchall()]
        date_col = 'created_at' if 'created_at' in cols else 'scraped_at'
        platform_col = 'platform' if 'platform' in cols else 'source'

        today = datetime.now().strftime('%Y-%m-%d')
        three_days_ago = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')

        results = {
            "overdue_followups": [],
            "stale_leads": [],
            "no_response_leads": [],
            "summary": {}
        }

        # 1. 팔로업 기한 초과 리드
        if 'follow_up_date' in cols:
            cursor.execute(f"""
                SELECT id, title, {platform_col}, follow_up_date, status
                FROM mentions
                WHERE follow_up_date IS NOT NULL
                  AND follow_up_date < ?
                  AND status NOT IN ('converted', 'rejected')
                ORDER BY follow_up_date ASC
                LIMIT 20
            """, (today,))

            results["overdue_followups"] = [
                {
                    "id": row[0],
                    "title": row[1],
                    "platform": row[2],
                    "follow_up_date": row[3],
                    "status": row[4],
                    "days_overdue": (datetime.now() - datetime.strptime(row[3], '%Y-%m-%d')).days
                }
                for row in cursor.fetchall()
            ]

        # 2. 오래된 pending 리드 (3일 이상)
        cursor.execute(f"""
            SELECT id, title, {platform_col}, {date_col}, status
            FROM mentions
            WHERE status = 'pending'
              AND DATE({date_col}) <= DATE(?)
            ORDER BY {date_col} ASC
            LIMIT 20
        """, (three_days_ago,))

        results["stale_leads"] = [
            {
                "id": row[0],
                "title": row[1],
                "platform": row[2],
                "created_at": row[3],
                "status": row[4]
            }
            for row in cursor.fetchall()
        ]

        # 3. 연락 후 응답 없는 리드 (contacted 상태 3일 이상)
        if 'updated_at' in cols:
            cursor.execute(f"""
                SELECT id, title, {platform_col}, updated_at, status
                FROM mentions
                WHERE status = 'contacted'
                  AND DATE(updated_at) <= DATE(?)
                ORDER BY updated_at ASC
                LIMIT 20
            """, (three_days_ago,))

            results["no_response_leads"] = [
                {
                    "id": row[0],
                    "title": row[1],
                    "platform": row[2],
                    "last_contact": row[3],
                    "status": row[4]
                }
                for row in cursor.fetchall()
            ]

        conn.close()

        # 요약
        results["summary"] = {
            "total_overdue": len(results["overdue_followups"]),
            "total_stale": len(results["stale_leads"]),
            "total_no_response": len(results["no_response_leads"]),
            "total_action_needed": (
                len(results["overdue_followups"]) +
                len(results["stale_leads"]) +
                len(results["no_response_leads"])
            )
        }

        return results

    except Exception as e:
        logger.error(f"overdue-leads 오류: {str(e)}", exc_info=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 4.0] 순위 급락 알림 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
@router.get("/rank-alerts")
async def get_rank_alerts() -> Dict[str, Any]:
    """
    [Phase 4.0] 순위 급락 알림

    최근 순위가 크게 하락한 키워드를 감지합니다.

    Returns:
        - critical_drops: 5위 이상 하락 키워드
        - warnings: 3위 이상 하락 키워드
        - recommendations: 대응 권장 사항
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rank_history'")
        if not cursor.fetchone():
            conn.close()
            return {"critical_drops": [], "warnings": [], "recommendations": []}

        cursor.execute("PRAGMA table_info(rank_history)")
        cols = [row[1] for row in cursor.fetchall()]
        date_col = 'checked_at' if 'checked_at' in cols else 'created_at'

        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

        # 최근 순위와 이전 순위 비교
        cursor.execute(f"""
            WITH recent_ranks AS (
                SELECT keyword, rank, {date_col},
                       ROW_NUMBER() OVER (PARTITION BY keyword ORDER BY {date_col} DESC) as rn
                FROM rank_history
                WHERE rank IS NOT NULL AND rank > 0
                  AND DATE({date_col}) >= DATE(?)
            ),
            current_rank AS (
                SELECT keyword, rank as current_rank
                FROM recent_ranks WHERE rn = 1
            ),
            previous_rank AS (
                SELECT keyword, rank as previous_rank
                FROM recent_ranks WHERE rn = 2
            )
            SELECT
                c.keyword,
                c.current_rank,
                p.previous_rank,
                (c.current_rank - p.previous_rank) as rank_change
            FROM current_rank c
            JOIN previous_rank p ON c.keyword = p.keyword
            WHERE c.current_rank > p.previous_rank
            ORDER BY rank_change DESC
        """, (week_ago,))

        rows = cursor.fetchall()
        conn.close()

        critical_drops = []
        warnings = []

        for row in rows:
            keyword, current, previous, change = row
            alert = {
                "keyword": keyword,
                "current_rank": current,
                "previous_rank": previous,
                "rank_change": change
            }

            if change >= 5:
                alert["severity"] = "critical"
                critical_drops.append(alert)
            elif change >= 3:
                alert["severity"] = "warning"
                warnings.append(alert)

        # 권장 사항 생성
        recommendations = []

        if critical_drops:
            recommendations.append({
                "priority": "critical",
                "message": f"🚨 {len(critical_drops)}개 키워드가 5위 이상 하락했습니다",
                "action": "해당 키워드 콘텐츠 점검 및 최적화 필요",
                "keywords": [d["keyword"] for d in critical_drops[:3]]
            })

        if warnings:
            recommendations.append({
                "priority": "warning",
                "message": f"⚠️ {len(warnings)}개 키워드가 3위 이상 하락했습니다",
                "action": "모니터링 강화 권장",
                "keywords": [w["keyword"] for w in warnings[:3]]
            })

        if not critical_drops and not warnings:
            recommendations.append({
                "priority": "info",
                "message": "✅ 모든 키워드 순위가 안정적입니다",
                "action": "현재 전략 유지"
            })

        return {
            "critical_drops": critical_drops,
            "warnings": warnings,
            "recommendations": recommendations,
            "summary": {
                "total_critical": len(critical_drops),
                "total_warnings": len(warnings)
            }
        }

    except Exception as e:
        logger.error(f"rank-alerts 오류: {str(e)}", exc_info=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 4.0] AI 다음 액션 제안 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
@router.get("/suggested-actions")
async def get_suggested_actions() -> Dict[str, Any]:
    """
    [Phase 4.0] AI 기반 다음 액션 제안

    현재 데이터 상태를 분석하여 최적의 다음 행동을 제안합니다.

    Returns:
        - actions: 우선순위별 제안 액션 목록
        - quick_wins: 빠르게 실행 가능한 액션
        - focus_areas: 집중해야 할 영역
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        actions = []
        quick_wins = []
        focus_areas = []

        # ========== 리드 분석 ==========
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(mentions)")
            cols = [row[1] for row in cursor.fetchall()]

            # Hot Lead 확인
            if 'status' in cols:
                cursor.execute("""
                    SELECT COUNT(*) FROM mentions
                    WHERE status = 'pending'
                """)
                pending_count = cursor.fetchone()[0] or 0

                if pending_count > 0:
                    priority = "critical" if pending_count > 10 else "high" if pending_count > 5 else "medium"
                    actions.append({
                        "id": "contact_pending_leads",
                        "priority": priority,
                        "category": "leads",
                        "title": f"대기 중인 리드 {pending_count}건 연락 필요",
                        "description": "새로 발견된 리드에 대한 첫 연락을 진행하세요.",
                        "action_link": "/leads?status=pending",
                        "impact": "high",
                        "effort": "medium"
                    })

                    if pending_count <= 5:
                        quick_wins.append({
                            "action": f"{pending_count}개 리드에 첫 연락하기",
                            "time_estimate": "15분",
                            "link": "/leads?status=pending"
                        })

            # 팔로업 필요 리드
            if 'follow_up_date' in cols:
                today = datetime.now().strftime('%Y-%m-%d')
                cursor.execute("""
                    SELECT COUNT(*) FROM mentions
                    WHERE follow_up_date <= ?
                      AND status NOT IN ('converted', 'rejected')
                """, (today,))
                overdue = cursor.fetchone()[0] or 0

                if overdue > 0:
                    actions.append({
                        "id": "followup_overdue",
                        "priority": "high",
                        "category": "leads",
                        "title": f"팔로업 기한 초과 {overdue}건",
                        "description": "예정된 팔로업 날짜가 지났습니다. 빠른 연락이 필요합니다.",
                        "action_link": "/leads",
                        "impact": "high",
                        "effort": "low"
                    })

        # ========== 키워드 분석 ==========
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_insights'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(keyword_insights)")
            kw_cols = [row[1] for row in cursor.fetchall()]

            # 활용되지 않은 S급 키워드
            cursor.execute("""
                SELECT COUNT(*) FROM keyword_insights
                WHERE grade = 'S'
            """)
            s_grade_count = cursor.fetchone()[0] or 0

            if s_grade_count > 0:
                actions.append({
                    "id": "create_content_s_grade",
                    "priority": "medium",
                    "category": "content",
                    "title": f"S급 키워드 {s_grade_count}개 콘텐츠 제작",
                    "description": "고가치 키워드를 활용한 블로그/영상 콘텐츠를 제작하세요.",
                    "action_link": "/pathfinder?grade=S",
                    "impact": "high",
                    "effort": "high"
                })

                focus_areas.append({
                    "area": "콘텐츠 제작",
                    "reason": f"S급 키워드 {s_grade_count}개 활용 가능",
                    "potential": "높음"
                })

        # ========== 바이럴 분석 ==========
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='viral_targets'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT COUNT(*) FROM viral_targets
                WHERE comment_status = 'pending' OR comment_status IS NULL
            """)
            pending_viral = cursor.fetchone()[0] or 0

            if pending_viral > 0:
                actions.append({
                    "id": "process_viral_targets",
                    "priority": "medium",
                    "category": "viral",
                    "title": f"바이럴 타겟 {pending_viral}건 처리",
                    "description": "발견된 바이럴 기회에 댓글을 작성하세요.",
                    "action_link": "/viral",
                    "impact": "medium",
                    "effort": "low"
                })

                if pending_viral <= 10:
                    quick_wins.append({
                        "action": f"{pending_viral}개 바이럴 타겟 댓글 작성",
                        "time_estimate": "20분",
                        "link": "/viral"
                    })

        conn.close()

        # 우선순위 정렬
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        actions.sort(key=lambda x: priority_order.get(x["priority"], 4))

        return {
            "actions": actions,
            "quick_wins": quick_wins[:3],  # 상위 3개만
            "focus_areas": focus_areas,
            "summary": {
                "total_actions": len(actions),
                "critical_count": len([a for a in actions if a["priority"] == "critical"]),
                "high_count": len([a for a in actions if a["priority"] == "high"])
            }
        }

    except Exception as e:
        logger.error(f"suggested-actions 오류: {str(e)}", exc_info=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# [Phase 3.2] 트렌드 감지 API
# ============================================

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
@router.get("/trending-keywords")
async def get_trending_keywords(
    hours: int = Query(default=24, ge=1, le=168, description="분석 기간 (시간, 최대 7일)"),
    limit: int = Query(default=20, ge=1, le=100, description="최대 반환 개수")
) -> Dict[str, Any]:
    """
    [Phase 3.2] 급상승 키워드 조회

    Args:
        hours: 분석 기간 (시간, 기본 24, 최대 168)
        limit: 최대 반환 개수 (기본 20, 최대 100)

    Returns:
        트렌드 키워드 목록 및 요약
    """
    try:
        # 트렌드 감지 서비스 임포트
        services_path = os.path.join(parent_dir, 'services')
        if services_path not in sys.path:
            sys.path.insert(0, services_path)

        from trend_detector import get_trend_detector

        detector = get_trend_detector()
        summary = detector.get_trend_summary(hours=hours)

        # 상위 N개 제한
        summary['top_keywords'] = summary['top_keywords'][:limit]

        return {
            'status': 'success',
            'data': summary
        }

    except ImportError as e:
        logger.warning(f"trending-keywords Import 오류: {e}")
        return {
            'status': 'error',
            'message': 'Trend detector service not available',
            'data': {
                'period_hours': hours,
                'total_trending': 0,
                'top_keywords': [],
                'by_level': {'HOT': [], 'RISING': [], 'STABLE': [], 'DECLINING': []}
            }
        }
    except Exception as e:
        logger.error(f"trending-keywords 오류: {str(e)}", exc_info=True)
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'message': str(e),
            'data': None
        }


@router.get("/hot-keywords")
async def get_hot_keywords(
    limit: int = Query(default=10, ge=1, le=50, description="최대 반환 개수")
) -> Dict[str, Any]:
    """
    [Phase 3.2] HOT 트렌드 키워드만 조회

    Args:
        limit: 최대 반환 개수 (기본 10, 최대 50)

    Returns:
        HOT 레벨 키워드 목록
    """
    try:
        services_path = os.path.join(parent_dir, 'services')
        if services_path not in sys.path:
            sys.path.insert(0, services_path)

        from trend_detector import get_trend_detector

        detector = get_trend_detector()
        hot_keywords = detector.get_hot_keywords(limit=limit)

        return {
            'status': 'success',
            'count': len(hot_keywords),
            'keywords': hot_keywords
        }

    except Exception as e:
        logger.error(f"hot-keywords 오류: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'message': str(e),
            'keywords': []
        }


# ============================================
# [Phase 5.0] 오늘의 추천 키워드 API
# ============================================

@router.get("/recommended-keywords")
async def get_recommended_keywords(
    limit: int = Query(default=10, ge=1, le=50, description="반환할 키워드 수")
) -> Dict[str, Any]:
    """
    [Phase 5.0] 오늘의 추천 키워드 조회

    S/A급 키워드 중에서 마케팅에 가장 적합한 키워드를 추천합니다.

    추천 기준:
    1. S/A급 키워드 우선
    2. 트렌드 상승(rising) 키워드 우선
    3. 검색량 높은 키워드 우선
    4. 최근 발굴된 키워드 우선

    Args:
        limit: 반환할 키워드 수 (기본 10, 최대 50)

    Returns:
        추천 키워드 목록 및 추천 이유
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. S/A급 + 트렌드 상승 키워드 (최고 우선순위)
        cursor.execute("""
            SELECT keyword, grade, search_volume, trend_status, category, kei, created_at
            FROM keyword_insights
            WHERE grade IN ('S', 'A')
              AND trend_status = 'rising'
            ORDER BY search_volume DESC, kei DESC
            LIMIT ?
        """, (limit,))
        rising_keywords = [dict(row) for row in cursor.fetchall()]

        # 2. S/A급 + 안정 트렌드 키워드 (부족분 채우기)
        remaining = limit - len(rising_keywords)
        stable_keywords = []
        if remaining > 0:
            cursor.execute("""
                SELECT keyword, grade, search_volume, trend_status, category, kei, created_at
                FROM keyword_insights
                WHERE grade IN ('S', 'A')
                  AND (trend_status = 'stable' OR trend_status IS NULL)
                ORDER BY search_volume DESC, kei DESC
                LIMIT ?
            """, (remaining,))
            stable_keywords = [dict(row) for row in cursor.fetchall()]

        # 3. 최근 발굴된 S/A급 (오늘/어제)
        cursor.execute("""
            SELECT keyword, grade, search_volume, trend_status, category, kei, created_at
            FROM keyword_insights
            WHERE grade IN ('S', 'A')
              AND DATE(created_at) >= DATE('now', '-1 day')
            ORDER BY created_at DESC
            LIMIT 5
        """)
        recent_keywords = [dict(row) for row in cursor.fetchall()]

        # 결과 합산 및 중복 제거
        all_keywords = {}
        for kw in rising_keywords:
            kw['recommendation_reason'] = '📈 트렌드 상승 중'
            kw['priority'] = 1
            all_keywords[kw['keyword']] = kw

        for kw in stable_keywords:
            if kw['keyword'] not in all_keywords:
                kw['recommendation_reason'] = '⭐ 고가치 안정 키워드'
                kw['priority'] = 2
                all_keywords[kw['keyword']] = kw

        for kw in recent_keywords:
            if kw['keyword'] not in all_keywords:
                kw['recommendation_reason'] = '🆕 신규 발굴 키워드'
                kw['priority'] = 3
                all_keywords[kw['keyword']] = kw
            elif all_keywords[kw['keyword']].get('priority', 10) > 1:
                # 이미 있지만 최근 발굴된 경우 표시 추가
                all_keywords[kw['keyword']]['recommendation_reason'] += ' + 🆕 신규'

        # 우선순위 + 검색량 기준 정렬
        sorted_keywords = sorted(
            all_keywords.values(),
            key=lambda x: (x.get('priority', 10), -x.get('search_volume', 0))
        )[:limit]

        # 요약 통계
        cursor.execute("""
            SELECT
                COUNT(CASE WHEN grade = 'S' THEN 1 END) as s_count,
                COUNT(CASE WHEN grade = 'A' THEN 1 END) as a_count,
                COUNT(CASE WHEN trend_status = 'rising' THEN 1 END) as rising_count
            FROM keyword_insights
            WHERE grade IN ('S', 'A')
        """)
        stats = cursor.fetchone()

        conn.close()

        return {
            'status': 'success',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'keywords': sorted_keywords,
            'count': len(sorted_keywords),
            'summary': {
                'total_s_grade': stats[0] if stats else 0,
                'total_a_grade': stats[1] if stats else 0,
                'rising_count': stats[2] if stats else 0
            },
            'tips': [
                '트렌드 상승 키워드는 콘텐츠 제작 우선순위가 높습니다',
                '검색량 높은 키워드로 블로그 포스팅을 시작하세요',
                '신규 키워드는 경쟁이 적어 빠르게 노출될 수 있습니다'
            ]
        }

    except Exception as e:
        logger.error(f"recommended-keywords 오류: {str(e)}", exc_info=True)
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'message': str(e),
            'keywords': [],
            'count': 0
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 5.1] 월간 ROI 리포트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
@router.get("/monthly-roi-report")
async def get_monthly_roi_report(
    year: int = None,
    month: int = None
) -> Dict[str, Any]:
    """
    [Phase 5.1] 월간 ROI 리포트 생성

    월별 마케팅 성과를 종합 분석하여 ROI 리포트를 생성합니다.

    분석 항목:
    - 키워드 발굴 현황 (S/A급 키워드 수, 카테고리별 분포)
    - 리드 전환율 (발굴 → 연락 → 전환)
    - 순위 변동 (상승/하락 키워드)
    - 바이럴 활동 (댓글 작성, 승인률)
    - 경쟁사 분석 (약점 발견, 기회 키워드)

    Args:
        year: 연도 (기본값: 현재 연도)
        month: 월 (기본값: 현재 월)

    Returns:
        월간 ROI 리포트
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 기본값 설정
        now = datetime.now()
        if year is None:
            year = now.year
        if month is None:
            month = now.month

        # 해당 월의 시작/끝 날짜
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year + 1}-01-01"
        else:
            end_date = f"{year}-{month + 1:02d}-01"

        report = {
            'period': f"{year}년 {month}월",
            'start_date': start_date,
            'end_date': end_date,
            'generated_at': now.isoformat(),
            'sections': {}
        }

        # 1. 키워드 발굴 현황
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN grade = 'S' THEN 1 ELSE 0 END) as s_grade,
                SUM(CASE WHEN grade = 'A' THEN 1 ELSE 0 END) as a_grade,
                SUM(CASE WHEN grade = 'B' THEN 1 ELSE 0 END) as b_grade,
                AVG(search_volume) as avg_search_volume
            FROM keyword_insights
            WHERE created_at >= ? AND created_at < ?
        """, (start_date, end_date))
        kw_stats = dict(cursor.fetchone())

        # 카테고리별 분포
        cursor.execute("""
            SELECT category, COUNT(*) as count
            FROM keyword_insights
            WHERE created_at >= ? AND created_at < ?
            GROUP BY category
            ORDER BY count DESC
            LIMIT 10
        """, (start_date, end_date))
        kw_by_category = [dict(row) for row in cursor.fetchall()]

        report['sections']['keywords'] = {
            'title': '키워드 발굴 현황',
            'total_discovered': kw_stats.get('total', 0) or 0,
            's_grade': kw_stats.get('s_grade', 0) or 0,
            'a_grade': kw_stats.get('a_grade', 0) or 0,
            'b_grade': kw_stats.get('b_grade', 0) or 0,
            'avg_search_volume': round(kw_stats.get('avg_search_volume', 0) or 0),
            'by_category': kw_by_category
        }

        # 2. 리드 전환 현황
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'contacted' THEN 1 ELSE 0 END) as contacted,
                    SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted,
                    SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected
                FROM mentions
                WHERE created_at >= ? AND created_at < ?
            """, (start_date, end_date))
            lead_stats = dict(cursor.fetchone())

            total_leads = lead_stats.get('total', 0) or 0
            converted = lead_stats.get('converted', 0) or 0
            conversion_rate = (converted / total_leads * 100) if total_leads > 0 else 0

            report['sections']['leads'] = {
                'title': '리드 전환 현황',
                'total_leads': total_leads,
                'pending': lead_stats.get('pending', 0) or 0,
                'contacted': lead_stats.get('contacted', 0) or 0,
                'converted': converted,
                'rejected': lead_stats.get('rejected', 0) or 0,
                'conversion_rate': round(conversion_rate, 1)
            }
        else:
            report['sections']['leads'] = {'title': '리드 전환 현황', 'total_leads': 0}

        # 3. 순위 변동
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rank_history'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT
                    keyword,
                    MIN(rank) as best_rank,
                    MAX(rank) as worst_rank,
                    COUNT(*) as scan_count
                FROM rank_history
                WHERE scan_date >= ? AND scan_date < ?
                  AND status = 'found'
                GROUP BY keyword
                HAVING scan_count >= 2
                ORDER BY best_rank
                LIMIT 20
            """, (start_date, end_date))
            rank_changes = [dict(row) for row in cursor.fetchall()]

            report['sections']['rankings'] = {
                'title': '순위 변동',
                'tracked_keywords': len(rank_changes),
                'top_performers': rank_changes[:5],
                'details': rank_changes
            }
        else:
            report['sections']['rankings'] = {'title': '순위 변동', 'tracked_keywords': 0}

        # 4. 바이럴 활동
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='viral_targets'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN comment_status = 'posted' THEN 1 ELSE 0 END) as posted,
                    SUM(CASE WHEN comment_status = 'approved' THEN 1 ELSE 0 END) as approved,
                    SUM(CASE WHEN comment_status = 'skipped' THEN 1 ELSE 0 END) as skipped
                FROM viral_targets
                WHERE discovered_at >= ? AND discovered_at < ?
            """, (start_date, end_date))
            viral_stats = dict(cursor.fetchone())

            total_viral = viral_stats.get('total', 0) or 0
            posted = viral_stats.get('posted', 0) or 0
            approval_rate = (posted / total_viral * 100) if total_viral > 0 else 0

            report['sections']['viral'] = {
                'title': '바이럴 활동',
                'total_targets': total_viral,
                'comments_posted': posted,
                'approval_rate': round(approval_rate, 1),
                'skipped': viral_stats.get('skipped', 0) or 0
            }
        else:
            report['sections']['viral'] = {'title': '바이럴 활동', 'total_targets': 0}

        # 5. 경쟁사 분석
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitor_weaknesses'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT
                    COUNT(*) as total_weaknesses,
                    COUNT(DISTINCT weakness_type) as weakness_types
                FROM competitor_weaknesses
                WHERE discovered_at >= ? AND discovered_at < ?
            """, (start_date, end_date))
            comp_stats = dict(cursor.fetchone())

            report['sections']['competitors'] = {
                'title': '경쟁사 분석',
                'weaknesses_found': comp_stats.get('total_weaknesses', 0) or 0,
                'weakness_types': comp_stats.get('weakness_types', 0) or 0
            }
        else:
            report['sections']['competitors'] = {'title': '경쟁사 분석', 'weaknesses_found': 0}

        conn.close()

        # 6. ROI 요약 계산
        # 단순화된 ROI 계산: (전환 리드 수 * 예상 고객 가치) / 활동 수
        converted_leads = report['sections'].get('leads', {}).get('converted', 0)
        estimated_value_per_lead = 500000  # 50만원 (예상 고객 가치)
        total_activities = (
            report['sections'].get('keywords', {}).get('total_discovered', 0) +
            report['sections'].get('viral', {}).get('comments_posted', 0)
        )

        estimated_revenue = converted_leads * estimated_value_per_lead
        roi_score = (estimated_revenue / 1000000) if total_activities > 0 else 0  # 백만원 단위

        report['summary'] = {
            'roi_score': round(roi_score, 1),
            'estimated_revenue': estimated_revenue,
            'total_activities': total_activities,
            'converted_leads': converted_leads,
            'highlights': []
        }

        # 하이라이트 생성
        if report['sections']['keywords'].get('s_grade', 0) > 0:
            report['summary']['highlights'].append(
                f"S급 키워드 {report['sections']['keywords']['s_grade']}개 발굴"
            )
        if converted_leads > 0:
            report['summary']['highlights'].append(
                f"리드 {converted_leads}건 전환 성공"
            )
        if report['sections'].get('viral', {}).get('comments_posted', 0) > 10:
            report['summary']['highlights'].append(
                f"바이럴 댓글 {report['sections']['viral']['comments_posted']}건 작성"
            )

        return report

    except Exception as e:
        logger.error(f"monthly-roi-report 오류: {str(e)}", exc_info=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"월간 리포트 생성 실패: {str(e)}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 6.2] KEI 알림 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
@router.get("/kei-alerts")
async def get_kei_alerts(days: int = 7) -> Dict[str, Any]:
    """
    [Phase 6.2] KEI 기반 키워드 알림 조회

    최근 발견된 고효율 KEI 키워드 및 KEI 변동 알림을 제공합니다.

    Args:
        days: 조회 기간 (일, 기본 7일)

    Returns:
        - new_high_kei: 새로 발견된 고KEI 키워드 (KEI >= 50)
        - kei_improved: KEI가 개선된 키워드
        - opportunities: 공략 기회 키워드 (높은 검색량, 낮은 난이도)
        - summary: 요약 통계
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # 1. 새로 발견된 고KEI 키워드 (최근 N일, KEI >= 50)
        cursor.execute("""
            SELECT keyword, grade, search_volume, difficulty, kei, category, created_at
            FROM keyword_insights
            WHERE DATE(created_at) >= DATE(?)
              AND kei >= 50
            ORDER BY kei DESC
            LIMIT 10
        """, (since_date,))
        new_high_kei = [dict(row) for row in cursor.fetchall()]

        # 2. S급 KEI 키워드 (kei_grade가 S인 키워드)
        cursor.execute("""
            SELECT keyword, grade, search_volume, difficulty, kei, category
            FROM keyword_insights
            WHERE kei >= 100
            ORDER BY kei DESC
            LIMIT 5
        """)
        s_grade_kei = [dict(row) for row in cursor.fetchall()]

        # 3. 공략 기회 키워드 (높은 검색량, 낮은 난이도, B/C 등급)
        cursor.execute("""
            SELECT keyword, grade, search_volume, difficulty, kei, category
            FROM keyword_insights
            WHERE grade IN ('B', 'C')
              AND search_volume >= 500
              AND difficulty <= 30
              AND kei >= 30
            ORDER BY kei DESC
            LIMIT 10
        """)
        opportunities = [dict(row) for row in cursor.fetchall()]

        # 4. 요약 통계
        cursor.execute("""
            SELECT
                COUNT(CASE WHEN kei >= 100 THEN 1 END) as s_kei_count,
                COUNT(CASE WHEN kei >= 50 AND kei < 100 THEN 1 END) as a_kei_count,
                COUNT(CASE WHEN kei >= 30 AND kei < 50 THEN 1 END) as b_kei_count,
                AVG(kei) as avg_kei
            FROM keyword_insights
            WHERE kei > 0
        """)
        stats = cursor.fetchone()

        conn.close()

        # 알림 메시지 생성
        alerts = []
        if len(new_high_kei) > 0:
            alerts.append({
                "type": "new_high_kei",
                "severity": "info",
                "message": f"최근 {days}일간 고KEI 키워드 {len(new_high_kei)}개 발견",
                "count": len(new_high_kei)
            })
        if len(s_grade_kei) > 0:
            alerts.append({
                "type": "s_grade_kei",
                "severity": "success",
                "message": f"S급 KEI 키워드 {len(s_grade_kei)}개 보유 중",
                "count": len(s_grade_kei)
            })
        if len(opportunities) > 0:
            alerts.append({
                "type": "opportunity",
                "severity": "warning",
                "message": f"공략 기회 키워드 {len(opportunities)}개 발견",
                "count": len(opportunities)
            })

        return {
            "new_high_kei": new_high_kei,
            "s_grade_kei": s_grade_kei,
            "opportunities": opportunities,
            "alerts": alerts,
            "summary": {
                "s_kei_count": stats[0] if stats else 0,
                "a_kei_count": stats[1] if stats else 0,
                "b_kei_count": stats[2] if stats else 0,
                "avg_kei": round(stats[3], 1) if stats and stats[3] else 0,
                "total_alerts": len(alerts)
            }
        }

    except Exception as e:
        logger.error(f"kei-alerts 오류: {str(e)}", exc_info=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 6.2] 자동 승인 알림 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
@router.get("/auto-approval-alerts")
async def get_auto_approval_alerts(days: int = 7) -> Dict[str, Any]:
    """
    [Phase 6.2] 자동 승인 작업 알림 조회

    자동 승인 규칙에 의해 처리된 작업 내역을 알림으로 제공합니다.

    Args:
        days: 조회 기간 (일, 기본 7일)

    Returns:
        - auto_approved: 자동 승인된 작업 목록
        - pending_review: 수동 검토 필요한 작업
        - summary: 요약 통계
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # 자동 승인된 바이럴 타겟 조회
        auto_approved = []
        pending_review = []

        # viral_targets 테이블에서 자동 승인된 항목 조회
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='viral_targets'")
        if cursor.fetchone():
            # 자동 승인된 항목 (comment_status가 'auto_approved' 또는 승인 관련 메타데이터)
            cursor.execute("""
                SELECT id, platform, title, priority_score, comment_status, matched_keyword, discovered_at
                FROM viral_targets
                WHERE DATE(discovered_at) >= DATE(?)
                  AND comment_status = 'approved'
                ORDER BY discovered_at DESC
                LIMIT 20
            """, (since_date,))
            auto_approved = [dict(row) for row in cursor.fetchall()]

            # 수동 검토 필요 (pending 상태, 높은 점수)
            cursor.execute("""
                SELECT id, platform, title, priority_score, comment_status, matched_keyword, discovered_at
                FROM viral_targets
                WHERE DATE(discovered_at) >= DATE(?)
                  AND (comment_status = 'pending' OR comment_status IS NULL)
                  AND priority_score >= 60
                ORDER BY priority_score DESC
                LIMIT 10
            """, (since_date,))
            pending_review = [dict(row) for row in cursor.fetchall()]

        # 자동 승인 규칙 조회
        auto_rules = []
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='auto_approval_rules'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT id, name, condition_type, condition_value, is_active, created_at
                FROM auto_approval_rules
                WHERE is_active = 1
                ORDER BY created_at DESC
            """)
            auto_rules = [dict(row) for row in cursor.fetchall()]

        conn.close()

        # 알림 생성
        alerts = []
        if len(auto_approved) > 0:
            alerts.append({
                "type": "auto_approved",
                "severity": "success",
                "message": f"최근 {days}일간 {len(auto_approved)}건 자동 승인됨",
                "count": len(auto_approved)
            })
        if len(pending_review) > 0:
            alerts.append({
                "type": "pending_review",
                "severity": "warning",
                "message": f"수동 검토 필요: 고점수 타겟 {len(pending_review)}건",
                "count": len(pending_review)
            })
        if len(auto_rules) == 0:
            alerts.append({
                "type": "no_rules",
                "severity": "info",
                "message": "자동 승인 규칙이 설정되지 않았습니다",
                "count": 0
            })

        return {
            "auto_approved": auto_approved,
            "pending_review": pending_review,
            "active_rules": auto_rules,
            "alerts": alerts,
            "summary": {
                "auto_approved_count": len(auto_approved),
                "pending_review_count": len(pending_review),
                "active_rules_count": len(auto_rules),
                "total_alerts": len(alerts)
            }
        }

    except Exception as e:
        logger.error(f"auto-approval-alerts 오류: {str(e)}", exc_info=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# [Decision Intelligence] AI 브리핑 시스템
# ===========================================================================

# AI 브리핑 캐시 (5분)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
_ai_briefing_cache: Dict[str, Any] = {}
_ai_briefing_cache_time: float = 0
AI_BRIEFING_CACHE_TTL = 300  # 5분


@router.get("/ai-briefing")
@handle_exceptions
async def get_ai_briefing() -> Dict[str, Any]:
    """
    AI 기반 일일 인사이트 브리핑

    Gemini AI를 활용하여 현재 데이터를 분석하고
    의사결정에 도움이 되는 인사이트를 제공합니다.

    Returns:
        - executive_summary: AI가 생성한 핵심 요약
        - key_insights: 주요 인사이트 목록
        - recommended_actions: 우선순위 기반 권장 액션
        - market_signals: 시장 신호 및 트렌드
        - risk_alerts: 주의가 필요한 사항
        - generated_at: 생성 시간
    """
    global _ai_briefing_cache, _ai_briefing_cache_time

    # 캐시 확인
    current_time = time.time()
    if _ai_briefing_cache and (current_time - _ai_briefing_cache_time) < AI_BRIEFING_CACHE_TTL:
        logger.info("AI 브리핑 캐시 반환")
        return _ai_briefing_cache

    try:
        logger.info("AI 브리핑 생성 시작...")

        # 데이터 수집
        data_context = await _collect_briefing_data()

        # AI로 인사이트 생성
        prompt = f"""당신은 한의원 마케팅 전문 분석가입니다.
다음 데이터를 분석하여 경영자가 빠르게 의사결정을 내릴 수 있도록
핵심 인사이트를 제공해주세요.

## 현재 데이터:
{json.dumps(data_context, ensure_ascii=False, indent=2)}

## 응답 형식 (JSON):
{{
  "executive_summary": "오늘의 핵심 상황을 2-3문장으로 요약",
  "key_insights": [
    {{
      "category": "키워드|리드|경쟁|트렌드",
      "title": "인사이트 제목 (15자 이내)",
      "description": "구체적인 설명 (50자 이내)",
      "importance": "high|medium|low"
    }}
  ],
  "recommended_actions": [
    {{
      "priority": 1,
      "action": "구체적인 액션 (30자 이내)",
      "reason": "이유 (20자 이내)",
      "link": "관련 페이지 경로 (예: /pathfinder, /viral, /leads)"
    }}
  ],
  "market_signals": [
    {{
      "signal": "시장 신호 (20자 이내)",
      "trend": "up|down|stable",
      "impact": "긍정적|부정적|중립"
    }}
  ],
  "risk_alerts": [
    {{
      "level": "warning|critical",
      "message": "주의 사항 (30자 이내)"
    }}
  ]
}}

주의사항:
- 실제 데이터에 기반한 분석만 제공
- 추측이나 과장 금지
- 즉시 실행 가능한 액션 제안
- 한국어로 응답
- 반드시 유효한 JSON 형식으로 응답"""

        ai_insights = ai_generate_json(prompt, temperature=0.3, max_tokens=2048)

        if not ai_insights:
            logger.warning("AI 브리핑 JSON 파싱 실패. 기본 브리핑 반환")
            return _generate_default_ai_briefing()

        # 결과 구성
        result = {
            "executive_summary": ai_insights.get("executive_summary", ""),
            "key_insights": ai_insights.get("key_insights", [])[:5],  # 최대 5개
            "recommended_actions": ai_insights.get("recommended_actions", [])[:4],  # 최대 4개
            "market_signals": ai_insights.get("market_signals", [])[:3],  # 최대 3개
            "risk_alerts": ai_insights.get("risk_alerts", []),
            "data_context": {
                "keywords_count": data_context.get("keywords", {}).get("total", 0),
                "viral_targets_count": data_context.get("viral", {}).get("pending", 0),
                "leads_count": data_context.get("leads", {}).get("new_24h", 0)
            },
            "generated_at": datetime.now().isoformat(),
            "source": "ai"
        }

        # 캐시 저장
        _ai_briefing_cache = result
        _ai_briefing_cache_time = current_time

        logger.info("AI 브리핑 생성 완료")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"AI 응답 파싱 오류: {str(e)}")
        return _generate_default_ai_briefing()
    except Exception as e:
        logger.error(f"AI 브리핑 생성 오류: {str(e)}", exc_info=True)
        return _generate_default_ai_briefing()


async def _collect_briefing_data() -> Dict[str, Any]:
    """브리핑에 필요한 데이터 수집"""
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        data = {}

        # 키워드 데이터
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_insights'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) FROM keyword_insights")
            total_keywords = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT COUNT(*) FROM keyword_insights
                WHERE created_at >= datetime('now', '-1 day')
            """)
            new_24h = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT COUNT(*) FROM keyword_insights
                WHERE grade IN ('S', 'A')
            """)
            high_grade = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT keyword, search_volume, grade FROM keyword_insights
                WHERE grade = 'S'
                ORDER BY search_volume DESC
                LIMIT 5
            """)
            top_keywords = [{"keyword": row[0], "volume": row[1], "grade": row[2]} for row in cursor.fetchall()]

            data["keywords"] = {
                "total": total_keywords,
                "new_24h": new_24h,
                "high_grade": high_grade,
                "top_keywords": top_keywords
            }

        # 바이럴 타겟 데이터
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='viral_targets'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) FROM viral_targets WHERE comment_status = 'pending'")
            pending = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM viral_targets WHERE comment_status = 'approved'")
            approved = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM viral_targets WHERE comment_status = 'posted'")
            posted = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT platform, COUNT(*) as cnt FROM viral_targets
                WHERE comment_status = 'pending'
                GROUP BY platform
                ORDER BY cnt DESC
            """)
            by_platform = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("""
                SELECT AVG(priority_score) FROM viral_targets
                WHERE comment_status = 'pending' AND priority_score IS NOT NULL
            """)
            avg_score = cursor.fetchone()[0] or 0

            data["viral"] = {
                "pending": pending,
                "approved": approved,
                "posted": posted,
                "by_platform": by_platform,
                "avg_priority_score": round(avg_score, 1)
            }

        # 리드 데이터
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(mentions)")
            columns = [row[1] for row in cursor.fetchall()]
            date_col = 'detected_at' if 'detected_at' in columns else 'scraped_at'

            cursor.execute(f"""
                SELECT COUNT(*) FROM mentions
                WHERE {date_col} >= datetime('now', '-1 day')
            """)
            new_24h = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM mentions")
            total = cursor.fetchone()[0] or 0

            data["leads"] = {
                "total": total,
                "new_24h": new_24h
            }

        # 순위 데이터
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rank_history'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT COUNT(DISTINCT keyword) FROM rank_history
                WHERE date >= date('now', '-1 day')
            """)
            scanned_24h = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT keyword, rank, status FROM rank_history
                WHERE date >= date('now', '-1 day')
                AND status = 'found'
                ORDER BY rank ASC
                LIMIT 5
            """)
            top_rankings = [{"keyword": row[0], "rank": row[1]} for row in cursor.fetchall()]

            data["rankings"] = {
                "scanned_24h": scanned_24h,
                "top_rankings": top_rankings
            }

        conn.close()
        return data

    except Exception as e:
        logger.error(f"브리핑 데이터 수집 오류: {str(e)}")
        return {}


    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
def _generate_default_ai_briefing() -> Dict[str, Any]:
    """API 키 없거나 오류 시 기본 브리핑 반환"""
    return {
        "executive_summary": "AI 분석을 이용하려면 Gemini API 키를 설정해주세요.",
        "key_insights": [],
        "recommended_actions": [
            {
                "priority": 1,
                "action": "Gemini API 키 설정",
                "reason": "AI 분석 활성화",
                "link": "/settings"
            }
        ],
        "market_signals": [],
        "risk_alerts": [],
        "data_context": {},
        "generated_at": datetime.now().isoformat(),
        "source": "default"
    }


# ============================================================
# SSE (Server-Sent Events) 실시간 진행률 스트리밍
# ============================================================

@router.get("/mission/{module_name}/progress/stream")
async def stream_mission_progress(module_name: str):
    """
    [Phase 3-4] SSE 기반 실시간 스캔 진행률 스트리밍

    클라이언트에서 EventSource로 연결:
    ```javascript
    const evtSource = new EventSource('/api/hud/mission/place_sniper/progress/stream');
    evtSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log(data.progress, data.message);
    };
    ```

    Returns:
        SSE 스트림 (text/event-stream)
        - data: {"status": "running", "progress": 50, "message": "키워드 5/10 스캔 중..."}
    """

    async def event_generator():
        retry_count = 0
        max_idle_count = 60  # 60초 동안 변화 없으면 종료

        while retry_count < max_idle_count:
            # 프로세스 실행 중 여부 확인
            is_running = False
            if module_name in running_processes:
                process = running_processes[module_name]
                is_running = process.poll() is None

            if is_running:
                # 로그 파일에서 진행률 파싱
                progress_data = get_scan_progress_from_log(module_name)
                progress_data["is_running"] = True

                # SSE 형식으로 전송
                yield f"data: {json.dumps(progress_data, ensure_ascii=False)}\n\n"

                if progress_data.get("status") == "completed":
                    # 완료 이벤트 전송 후 종료
                    yield f"data: {json.dumps({'status': 'completed', 'progress': 100, 'message': '완료', 'is_running': False}, ensure_ascii=False)}\n\n"
                    break

                retry_count = 0  # 실행 중이면 카운터 리셋
            else:
                # 실행 중이 아닐 때
                if module_name in running_processes:
                    # 프로세스가 있었다가 종료됨
                    del running_processes[module_name]
                    yield f"data: {json.dumps({'status': 'completed', 'progress': 100, 'message': '완료', 'is_running': False}, ensure_ascii=False)}\n\n"
                    break

                # 아직 시작 안 함 또는 이미 종료
                yield f"data: {json.dumps({'status': 'idle', 'progress': 0, 'message': '대기 중', 'is_running': False}, ensure_ascii=False)}\n\n"
                retry_count += 1

            await asyncio.sleep(1)  # 1초마다 업데이트

        # 타임아웃 시 종료 이벤트
        yield f"data: {json.dumps({'status': 'timeout', 'progress': 0, 'message': '연결 시간 초과', 'is_running': False}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx 버퍼링 비활성화
        }
    )


@router.get("/mission/{module_name}/progress")
async def get_mission_progress(module_name: str) -> Dict[str, Any]:
    """
    스캔 진행률 단일 조회 (polling 방식용)

    Args:
        module_name: 모듈명 (place_sniper, pathfinder 등)

    Returns:
        - status: "idle" | "running" | "completed" | "error"
        - progress: 0-100
        - message: 현재 상태 메시지
        - is_running: 프로세스 실행 중 여부
    """
    # 프로세스 실행 중 여부 확인
    is_running = False
    if module_name in running_processes:
        process = running_processes[module_name]
        is_running = process.poll() is None

    if is_running:
        progress_data = get_scan_progress_from_log(module_name)
        progress_data["is_running"] = True
        return progress_data
    else:
        # 프로세스가 종료되었는지 확인
        if module_name in running_processes:
            del running_processes[module_name]
            return {"status": "completed", "progress": 100, "message": "완료", "is_running": False}

        return {"status": "idle", "progress": 0, "message": "대기 중", "is_running": False}

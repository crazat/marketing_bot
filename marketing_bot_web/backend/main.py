"""
🚀 Marketing Bot Web API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FastAPI 기반 백엔드 서버

실행: uvicorn main:app --reload --host 0.0.0.0 --port 8000
문서: http://localhost:8000/docs
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager, contextmanager
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import asyncio
import threading

# 상위 디렉토리를 path에 추가 (기존 모듈 import용)
# backend -> marketing_bot_web -> marketing_bot (루트)
project_root = str(Path(__file__).parent.parent.parent)  # 프로젝트 루트
backend_dir = str(Path(__file__).parent)  # backend 디렉토리
sys.path.insert(0, project_root)

# 루트 모듈 먼저 import (utils 충돌 방지)
from utils import ConfigManager, logger
from history_manager import HistoryManager
from insight_manager import InsightManager

# [안정성 개선] 중앙화된 설정 로드
from config.app_settings import get_settings
app_settings = get_settings()

# [고도화 A-1] Sentry 에러 모니터링
try:
    import sentry_sdk
    if app_settings.sentry_dsn:
        sentry_sdk.init(
            dsn=app_settings.sentry_dsn,
            traces_sample_rate=app_settings.sentry_traces_sample_rate,
            environment=app_settings.sentry_environment,
            release="marketing-bot@2.0.0",
            send_default_pii=False,
        )
        logger.info(f"✅ Sentry 초기화 완료 (env: {app_settings.sentry_environment})")
except ImportError:
    pass  # sentry-sdk 미설치 시 무시

# 그 후 backend 경로 추가 (백엔드 services용)
sys.path.insert(0, backend_dir)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Lifespan 이벤트 (startup/shutdown)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AppState:
    """애플리케이션 전역 상태"""
    config: ConfigManager = None
    history_mgr: HistoryManager = None
    insight_mgr: InsightManager = None
    websocket_clients: List[WebSocket] = []

app_state = AppState()


# [Phase 7.0] 비즈니스 프로필 로드
def load_business_profile():
    """business_profile.json에서 프로필 로드"""
    profile_path = os.path.join(project_root, 'config', 'business_profile.json')
    try:
        if os.path.exists(profile_path):
            with open(profile_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[Main] business_profile.json 로드 실패: {e}")
    return {"branding": {"tagline": "마케팅 자동화 플랫폼 API"}}


business_profile = load_business_profile()
api_description = business_profile.get("branding", {}).get("tagline", "마케팅 자동화 플랫폼 API")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 시작/종료 시 실행"""
    # Startup
    logger.info("🚀 Marketing Bot Web API 시작")
    app_state.config = ConfigManager()
    app_state.history_mgr = HistoryManager()
    app_state.insight_mgr = InsightManager()
    app_state.websocket_clients = []

    # [Phase Z] Logfire 관측성 — LOGFIRE_TOKEN 있으면 cloud, 없으면 local-only
    try:
        import logfire
        # console 인자는 4.x에서 ConsoleOptions 객체 — 기본값(자동) 사용
        logfire.configure(
            send_to_logfire="if-token-present",
            service_name="marketing_bot",
        )
        logfire.instrument_fastapi(app, capture_headers=False)
        try:
            logfire.instrument_sqlite3()
        except Exception as _e:
            logger.debug(f"logfire sqlite3 instrument 스킵: {_e}")
        logger.info("🔭 Logfire 관측성 초기화됨 (token 있을 때만 cloud 전송)")
    except Exception as e:
        logger.warning(f"Logfire 초기화 실패 (계속): {e}")

    # [Phase 6.1] DB 스키마 초기화 (앱 시작 시 한 번만)
    from services.db_init import ensure_all_tables
    ensure_all_tables()

    # [Phase A] 이벤트 버스 및 자동화 핸들러 초기화
    from services.automation_handlers import initialize_handlers
    handler_count = initialize_handlers()
    logger.info(f"🔗 자동화 핸들러 {len(handler_count)}개 활성화됨")

    # 백그라운드 작업 시작
    hud_task = asyncio.create_task(periodic_hud_update())
    scheduler_task = None

    # FileWatcher 시작 (실시간 로그 스트리밍)
    from services.file_watcher import create_file_watcher
    file_watcher = create_file_watcher(ws_manager)
    await file_watcher.start()

    logger.info("⏰ Chronos 스케줄러 비활성화됨 (Codex 자연어 실행 모드)")
    logger.info("📁 FileWatcher 활성화됨 (실시간 로그 스트리밍)")

    yield

    # Shutdown
    logger.info("🛑 Marketing Bot Web API 종료")

    # FileWatcher 중지
    await file_watcher.stop()

    # 백그라운드 작업 취소
    hud_task.cancel()
    if scheduler_task:
        scheduler_task.cancel()
    try:
        await hud_task
        if scheduler_task:
            await scheduler_task
    except asyncio.CancelledError:
        pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FastAPI 앱 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# [M1] production 환경에서는 API docs 노출 금지 (API 스키마 비공개)
_is_production = os.getenv("ENV", "").lower() in ("production", "prod")
app = FastAPI(
    title="Marketing Bot Web API",
    description=api_description,
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

# [보안 강화] CORS 설정 - 화이트리스트 기반
# 환경 변수로 추가 도메인 설정 가능: ALLOWED_ORIGINS=http://example.com,https://example.com
_default_origins = [
    "http://localhost:8000",
    "http://localhost:3000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:3000",
]
_env_origins = os.getenv("ALLOWED_ORIGINS", "").split(",")
_allowed_origins = _default_origins + [o.strip() for o in _env_origins if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-API-Key"],
    max_age=600,  # 프리플라이트 캐시 10분
)

# [Phase 3-2] 응답 래핑 미들웨어 - 통일된 응답 형식
# 주의: 미들웨어 순서가 중요함. CORS 이후에 추가
# from middleware import ResponseWrapperMiddleware
# app.add_middleware(ResponseWrapperMiddleware)
# 참고: 기존 라우터와의 호환성 문제로 비활성화. 새 라우터는 success_response() 사용 권장

# [Phase 8 / C1] API 인증 미들웨어 - 민감 엔드포인트 보호
from middleware.auth import APIKeyMiddleware
# [C1] Fail-closed: MARKETING_BOT_API_KEY 미설정 시 경고 로그 + 미들웨어는 동작(요청은 500 반환)
# DISABLE_API_AUTH는 로컬 개발 편의용 — 프로덕션에서는 사용 금지
_api_auth_enabled = os.getenv("DISABLE_API_AUTH", "false").lower() != "true"
if not os.getenv("MARKETING_BOT_API_KEY"):
    logger.warning(
        "[C1 보안] MARKETING_BOT_API_KEY 환경변수 미설정 — "
        "보호 엔드포인트(/api/export, /api/backup 등)는 500 반환됩니다. "
        ".env에 키를 설정하세요."
    )
if not _api_auth_enabled:
    logger.warning(
        "[보안] DISABLE_API_AUTH=true 감지 — 인증이 비활성화됐습니다. "
        "프로덕션 환경이 아닌지 확인하세요."
    )
app.add_middleware(APIKeyMiddleware, enabled=_api_auth_enabled)

# [Phase 3-3] Rate Limiting 미들웨어
from middleware.rate_limiter import RateLimiterMiddleware, configure_rate_limits
configure_rate_limits()  # Rate limit 규칙 설정
app.add_middleware(RateLimiterMiddleware)

# [Phase 3-4] 요청 ID 추적 미들웨어
from middleware.request_id import RequestIdMiddleware
app.add_middleware(RequestIdMiddleware)

# [고도화 V2-4] 보안 헤더 미들웨어 (CSP, X-Frame-Options 등)
from middleware.security_headers import SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 6.2] 전역 에러 핸들러 - 일관된 에러 응답 형식
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTPException을 일관된 형식으로 변환"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "error": exc.detail,
            "code": f"HTTP_{exc.status_code}",
            "timestamp": datetime.now().isoformat()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """예상치 못한 에러를 일관된 형식으로 변환"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": "서버 내부 오류가 발생했습니다",
            "code": "INTERNAL_SERVER_ERROR",
            "timestamp": datetime.now().isoformat()
        }
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 헬스체크
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/api")
async def api_root():
    """API 루트 엔드포인트"""
    return {
        "message": "Marketing Bot Web API",
        "version": "2.0.0",
        "status": "healthy",
        "docs": "/docs"
    }

@app.get("/")
async def root(request: Request):
    """API root for non-HTML clients, SPA shell for browser requests."""
    accept = request.headers.get("accept", "").lower()
    frontend_build_dir = Path(__file__).parent.parent / "frontend" / "dist"
    index_file = frontend_build_dir / "index.html"
    if "text/html" in accept and index_file.exists():
        return FileResponse(index_file)
    return {
        "message": "Marketing Bot Web API",
        "version": "2.0.0",
        "status": "healthy",
        "docs": "/docs",
    }

@app.get("/health")
async def simple_health_check():
    """Lightweight health check."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WebSocket
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from services.websocket_manager import ws_manager

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 엔드포인트 (실시간 업데이트용)"""
    await ws_manager.connect(websocket)

    try:
        while True:
            # 클라이언트로부터 메시지 수신
            data = await websocket.receive_text()

            # 핑 메시지 처리 (레거시 호환)
            if data == "ping":
                await websocket.send_text("pong")
                ws_manager.update_activity(websocket)
            else:
                # [고도화 B-5] JSON 메시지 처리 (구독/해제 등)
                try:
                    msg = json.loads(data)
                    await ws_manager.handle_client_message(websocket, msg)
                except (json.JSONDecodeError, Exception):
                    pass

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        logger.info("WebSocket 클라이언트 연결 종료")

# [성능 최적화] ThreadPoolExecutor for DB operations
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=app_settings.thread_pool_workers)


def _fetch_hud_metrics_sync():
    """
    [성능 최적화] 동기 DB 조회 함수
    - run_in_executor에서 호출되어 이벤트 루프 블로킹 방지
    """
    import sqlite3
    from db.database import DatabaseManager

    db = DatabaseManager()
    with db.get_new_connection() as conn:
        cursor = conn.cursor()

        # 통합 쿼리로 한 번에 조회
        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM keyword_insights) as total_keywords,
                (SELECT SUM(CASE WHEN grade = 'S' THEN 1 ELSE 0 END) FROM keyword_insights) as s_grade,
                (SELECT SUM(CASE WHEN grade = 'A' THEN 1 ELSE 0 END) FROM keyword_insights) as a_grade,
                (SELECT COUNT(*) FROM mentions) as total_leads,
                (SELECT SUM(CASE WHEN status IN ('New', 'pending') THEN 1 ELSE 0 END) FROM mentions) as pending_leads
        """)
        stats = cursor.fetchone()

        return {
            'total_keywords': stats[0] or 0,
            's_grade': stats[1] or 0,
            'a_grade': stats[2] or 0,
            'total_leads': stats[3] or 0,
            'pending_leads': stats[4] or 0
        }


# 백그라운드 작업: 주기적으로 HUD 업데이트
async def periodic_hud_update():
    """주기적으로 HUD 메트릭 업데이트"""
    import sqlite3

    while True:
        await asyncio.sleep(app_settings.hud_refresh_interval)
        try:
            # WebSocket 클라이언트가 없으면 스킵
            if not ws_manager.active_connections:
                continue

            # [성능 최적화] run_in_executor로 DB 작업 오프로드
            # 동기 sqlite 호출이 이벤트 루프를 블로킹하지 않음
            loop = asyncio.get_event_loop()
            metrics = await loop.run_in_executor(executor, _fetch_hud_metrics_sync)

            # WebSocket으로 전송
            await ws_manager.send_hud_update(metrics)
        except sqlite3.Error as db_err:
            # DB 오류는 로깅
            logger.warning(f"HUD 메트릭 DB 조회 오류: {db_err}")
        except Exception as e:
            # WebSocket 연결 없음 등의 일반적인 오류는 debug 레벨로
            if ws_manager.active_connections:
                logger.debug(f"HUD 메트릭 업데이트 오류: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Chronos 스케줄러 (자동 실행)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import subprocess

# 스케줄 정의 (hud.py와 동일)
CHRONOS_SCHEDULE = [
    {"time": "08:00", "cmd": "sentinel"},
    {"time": "09:00", "cmd": "place_sniper"},
    {"time": "10:30", "cmd": "briefing"},
    {"time": "12:00", "cmd": "ambassador"},
    {"time": "14:00", "cmd": "cafe_swarm"},
    {"time": "14:30", "cmd": "viral_hunter"},
    {"time": "15:00", "cmd": "carrot_farm"},
    {"time": "16:00", "cmd": "instagram"},
    {"time": "18:30", "cmd": "youtube"},
    {"time": "21:00", "cmd": "place_watch"},
    {"time": "21:30", "cmd": "tiktok"},
    {"time": "03:00", "cmd": "pathfinder"},
]

CMD_MAP = {
    "sentinel": ["python", "sentinel_agent.py"],
    "place_sniper": ["python", "scrapers/scraper_naver_place.py"],
    "briefing": ["python", "insight_manager.py", "--mode", "briefing"],
    "ambassador": ["python", "ambassador.py"],
    "cafe_swarm": ["python", "run_cafe_swarm.py"],
    "viral_hunter": ["python", "viral_hunter.py", "--scan", "--fresh"],
    "carrot_farm": ["python", "carrot_farmer.py"],
    "instagram": ["python", "scrapers/scraper_instagram.py"],
    "youtube": ["python", "scrapers/scraper_youtube.py"],
    "place_watch": ["python", "scrapers/scraper_live_naver.py"],
    "tiktok": ["python", "scrapers/scraper_tiktok_monitor.py"],
    "pathfinder": ["python", "pathfinder_v3_legion.py", "--target", "500", "--save-db"],
}

SCHEDULER_STATE_FILE = os.path.join(project_root, 'db', 'scheduler_state.json')
SCHEDULER_LOCK_FILE = os.path.join(project_root, 'db', '.scheduler.lock')
# 자연어 기반 운영으로 전환: 웹 API는 자동 Chronos 실행을 시작하지 않는다.
SCHEDULER_ENABLED = False

# [안정성 개선] 스케줄러 상태 파일 동시 접근 방지용 락
_scheduler_lock = threading.Lock()


@contextmanager
def scheduler_state_lock():
    """
    [안정성 개선] 스케줄러 상태 파일 접근 시 락 획득
    - 스레드 간 동기화: threading.Lock
    - 프로세스 간 동기화: 파일 기반 락 (Windows 호환)
    """
    lock_acquired = False
    lock_file = None

    try:
        # 1. 스레드 락 획득
        _scheduler_lock.acquire()

        # 2. 파일 락 획득 (프로세스 간 동기화)
        os.makedirs(os.path.dirname(SCHEDULER_LOCK_FILE), exist_ok=True)
        lock_file = open(SCHEDULER_LOCK_FILE, 'w')

        # Windows/Linux 호환 파일 락
        try:
            import msvcrt
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except (ImportError, OSError):
            # Linux/Mac: fcntl 사용 시도, 없으면 스킵
            try:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (ImportError, OSError):
                pass  # 파일 락 불가 시 스레드 락만 사용

        lock_acquired = True
        yield

    finally:
        # 락 해제
        if lock_file:
            try:
                try:
                    import msvcrt
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                except (ImportError, OSError):
                    try:
                        import fcntl
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    except (ImportError, OSError):
                        pass
            except Exception:
                pass
            lock_file.close()

        if _scheduler_lock.locked():
            _scheduler_lock.release()


def load_scheduler_state() -> dict:
    """스케줄러 상태 파일 로드 (락 없이 - 호출자가 락 관리)"""
    if os.path.exists(SCHEDULER_STATE_FILE):
        try:
            with open(SCHEDULER_STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.warning(f"스케줄러 상태 파일 로드 실패: {e}")
    return {}


def save_scheduler_state(state: dict):
    """스케줄러 상태 파일 저장 (락 없이 - 호출자가 락 관리)"""
    os.makedirs(os.path.dirname(SCHEDULER_STATE_FILE), exist_ok=True)
    with open(SCHEDULER_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)


def run_scheduled_module(cmd_key: str):
    """스케줄된 모듈 실행"""
    if cmd_key not in CMD_MAP:
        logger.warning(f"알 수 없는 모듈: {cmd_key}")
        return

    cmd = CMD_MAP[cmd_key]
    log_dir = os.path.join(project_root, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'{cmd_key}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')

    try:
        logger.info(f"⏰ Chronos 스케줄러: {cmd_key} 모듈 자동 실행 시작")
        with open(log_file, 'w', encoding='utf-8') as f:
            subprocess.Popen(
                cmd,
                cwd=project_root,
                stdout=f,
                stderr=subprocess.STDOUT,
                shell=False
            )
        logger.info(f"✅ {cmd_key} 모듈 실행 완료 (로그: {log_file})")
    except Exception as e:
        logger.error(f"❌ {cmd_key} 모듈 실행 실패: {e}")


async def chronos_scheduler():
    """Chronos 타임라인 스케줄러 - 매분 체크하여 자동 실행"""
    logger.info("⏰ Chronos 스케줄러 시작")

    while True:
        if SCHEDULER_ENABLED:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            today_str = now.strftime("%Y-%m-%d")

            modules_to_run = []

            # [안정성 개선] 상태 파일 접근 시 락 사용
            try:
                with scheduler_state_lock():
                    # 스케줄러 상태 로드
                    state = load_scheduler_state()

                    # 각 스케줄 체크
                    for item in CHRONOS_SCHEDULE:
                        scheduled_time = item["time"]
                        cmd_key = item["cmd"]

                        # 현재 시간이 스케줄 시간과 일치하고, 오늘 아직 실행 안했으면
                        if current_time == scheduled_time:
                            last_run = state.get(scheduled_time, "")
                            if last_run != today_str:
                                # 실행 예정 목록에 추가
                                modules_to_run.append((scheduled_time, cmd_key))

                                # 상태 먼저 업데이트 (중복 실행 방지)
                                state[scheduled_time] = today_str

                    # 상태 저장 (락 내에서)
                    if modules_to_run:
                        save_scheduler_state(state)

            except Exception as e:
                logger.warning(f"스케줄러 상태 접근 오류: {e}")
                modules_to_run = []

            # 모듈 실행 (락 해제 후 - 장시간 작업)
            for scheduled_time, cmd_key in modules_to_run:
                run_scheduled_module(cmd_key)

                # WebSocket으로 알림 (연결된 클라이언트에게)
                try:
                    await ws_manager.broadcast({
                        "type": "scheduler_event",
                        "module": cmd_key,
                        "time": scheduled_time,
                        "status": "started"
                    })
                except Exception as e:
                    logger.debug(f"WebSocket 브로드캐스트 실패 (무시): {e}")

        # 설정된 간격으로 대기 후 다시 체크
        await asyncio.sleep(app_settings.scheduler_check_interval)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API 라우터 임포트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from routers import hud, pathfinder, battle, leads, viral, competitors, instagram, backup, agent, qa, export, notifications, preferences, reviews, config, analytics, intelligence, automation, feedback, marketing_enhancement, migration, health, tiktok, data_intelligence, rag, predictive, ads, kakao_channel, telegram_webhook
# [W3] aeo: 프론트 호출자 0건 + services/aeo 미구현으로 등록 제거. _archive/routers/aeo.py 보관
from routers import viral_utm  # [T2] UTM 하위 라우터
from routers import viral_templates  # [U1] 템플릿 하위 라우터
from routers import viral_comments  # [U2] 댓글 성과 하위 라우터
from routers import jobs as jobs_router  # [Phase Z] 잡 실행 이력 + 헬스
from routers import telegram_callback as telegram_callback_router  # [Agent] HITL webhook
from routers import compliance_review as compliance_review_router  # [Eval] 사람 라벨 게이트

app.include_router(jobs_router.router)  # /api/jobs/runs, /api/jobs/summary, /api/jobs/health
app.include_router(telegram_callback_router.router)  # /api/telegram/webhook, /health
app.include_router(compliance_review_router.router)  # /api/compliance-review/queue, /label, /metrics
app.include_router(hud.router, prefix="/api/hud", tags=["HUD"])
app.include_router(pathfinder.router, prefix="/api/pathfinder", tags=["Pathfinder"])
app.include_router(battle.router, prefix="/api/battle", tags=["Battle Intelligence"])
app.include_router(leads.router, prefix="/api/leads", tags=["Lead Manager"])
app.include_router(export.router, prefix="/api/export", tags=["Data Export"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(preferences.router, prefix="/api/preferences", tags=["User Preferences"])
app.include_router(viral.router, prefix="/api/viral", tags=["Viral Hunter"])
app.include_router(viral_utm.router, prefix="/api", tags=["Viral Hunter - UTM"])  # [T2] prefix는 이미 /viral 포함
app.include_router(viral_templates.router, prefix="/api", tags=["Viral Hunter - Templates"])  # [U1]
app.include_router(viral_comments.router, prefix="/api", tags=["Viral Hunter - Comments"])  # [U2]
app.include_router(competitors.router, prefix="/api/competitors", tags=["Competitor Analysis"])
app.include_router(instagram.router, prefix="/api/instagram", tags=["Instagram"])
app.include_router(backup.router, prefix="/api/backup", tags=["Database Backup"])
app.include_router(agent.router, prefix="/api/agent", tags=["AI Agent"])
app.include_router(qa.router, prefix="/api/qa", tags=["Q&A Repository"])  # [Phase 5.0]
app.include_router(reviews.router, prefix="/api/reviews", tags=["Review Response Assistant"])  # [Phase 5.3]
app.include_router(config.router, prefix="/api/config", tags=["Config"])  # [Phase 6.1]
app.include_router(analytics.router)  # [Phase G/H/I/J/K/L] 마케팅 분석
app.include_router(intelligence.router, prefix="/api/intelligence", tags=["Intelligence"])  # [Phase B] AI 기반 지능화
app.include_router(automation.router, prefix="/api/automation", tags=["Automation"])  # [Phase C] 자동화 확장
app.include_router(feedback.router, prefix="/api/feedback", tags=["Feedback"])  # [Phase D] 피드백 루프
app.include_router(marketing_enhancement.router, prefix="/api/marketing", tags=["Marketing Enhancement"])  # [ME] 마케팅 강화
app.include_router(migration.router, prefix="/api/migration", tags=["Database Migration"])  # [Phase 1-4] 마이그레이션 관리
app.include_router(health.router, prefix="/api/health", tags=["Health Check"])  # [Phase 3-1] 헬스체크
app.include_router(tiktok.router, prefix="/api/tiktok", tags=["TikTok"])  # [고도화] 틱톡 멀티채널
## Scheduler router intentionally removed. Jobs are now run on demand from Codex
## natural-language commands instead of exposing scheduler control endpoints.
app.include_router(data_intelligence.router, prefix="/api/data-intelligence", tags=["Data Intelligence"])  # [Phase 9] 정보 수집 고도화
# [W3] app.include_router(aeo.router, ...) — 미사용으로 비활성화
app.include_router(rag.router, prefix="/api/rag", tags=["RAG Intelligence"])  # [고도화 C-2] RAG 마케팅 인텔리전스
app.include_router(predictive.router, prefix="/api/predictive", tags=["Predictive Analytics"])  # [고도화 D-2] 시계열 예측
app.include_router(ads.router, prefix="/api/ads", tags=["Ads Management"])  # [고도화 D-3] 통합 광고 관리
app.include_router(kakao_channel.router, prefix="/api/kakao", tags=["Kakao Channel"])  # [고도화 D-4] 카카오톡 채널
app.include_router(telegram_webhook.router, prefix="/api/telegram/legacy", tags=["Telegram Webhook Legacy"])  # [고도화 V2-2] 텔레그램 승인

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 프론트엔드 정적 파일 서빙 (프로덕션)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 프론트엔드 빌드 경로 (backend 기준 ../frontend/dist)
FRONTEND_BUILD_DIR = Path(__file__).parent.parent / "frontend" / "dist"

# 빌드 폴더가 존재하면 정적 파일 서빙
if FRONTEND_BUILD_DIR.exists():
    # assets 폴더 마운트 (JS, CSS, 이미지 등)
    app.mount("/assets", StaticFiles(directory=FRONTEND_BUILD_DIR / "assets"), name="assets")

    # 루트 경로 - index.html 서빙
    async def _deprecated_serve_index():
        """메인 페이지 서빙"""
        index_file = FRONTEND_BUILD_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "Marketing Bot Web API", "docs": "/docs"}

    # SPA 라우팅: API가 아닌 모든 요청을 index.html로 리다이렉트
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """SPA 프론트엔드 서빙"""
        # API 및 특수 경로 제외
        excluded_paths = ["api", "ws", "docs", "redoc", "openapi.json"]
        if any(full_path.startswith(p) or full_path == p for p in excluded_paths):
            raise HTTPException(status_code=404)

        # 정적 파일 확인 (favicon.ico, robots.txt 등)
        static_file = FRONTEND_BUILD_DIR / full_path
        if static_file.exists() and static_file.is_file():
            return FileResponse(static_file)

        # 나머지는 index.html 반환 (SPA 클라이언트 라우팅)
        index_file = FRONTEND_BUILD_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)

        raise HTTPException(status_code=404, detail="Not found")

    logger.info(f"📦 프론트엔드 빌드 서빙 활성화: {FRONTEND_BUILD_DIR}")
else:
    logger.warning(f"⚠️ 프론트엔드 빌드 폴더 없음: {FRONTEND_BUILD_DIR}")
    logger.warning("   npm run build를 실행하여 프론트엔드를 빌드하세요.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import uvicorn
    import socket

    # 서버 IP 주소 자동 감지
    def get_local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except (OSError, socket.error):
            return "localhost"

    local_ip = get_local_ip()

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🚀 Marketing Bot Web 시작")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"📍 로컬 접속: http://localhost:8000")
    print(f"📍 네트워크 접속: http://{local_ip}:8000")
    print("📖 API 문서: http://localhost:8000/docs")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if not FRONTEND_BUILD_DIR.exists():
        print("")
        print("⚠️  프론트엔드 빌드가 없습니다!")
        print("   다음 명령어로 빌드하세요:")
        print("   cd ../frontend && npm run build")
        print("")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False  # 프로덕션에서는 reload 비활성화
    )

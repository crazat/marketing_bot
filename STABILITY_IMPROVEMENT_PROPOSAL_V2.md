# 안정성 및 속도 개선 제안서 V2

**작성일**: 2026-02-23
**대상**: Marketing Bot 시스템
**범위**: Phase 1 개선 이후 추가 발견된 이슈

---

## 📋 요약

Phase 1에서 구현된 개선 사항(스케줄러 레이스 컨디션, 캐시 메모리 누수, 리드 분류 트랜잭션 등)을 제외하고,
추가로 발견된 **10개의 개선 항목**을 우선순위별로 정리합니다.

| 우선순위 | 항목 수 | 예상 영향 |
|---------|--------|----------|
| 🔴 CRITICAL | 3개 | 시스템 장애 가능 |
| 🟠 HIGH | 3개 | 성능/안정성 저하 |
| 🟡 MEDIUM | 4개 | 코드 품질/유지보수성 |

---

## 🔴 CRITICAL - 즉시 수정 필요

### 1. Database Connection Leak - instagram_reels_analyzer.py

**파일**: `/mnt/c/Projects/marketing_bot/scrapers/instagram_reels_analyzer.py`
**위치**: 362-425줄 `analyze_hashtag_trends()` 메서드

**현재 문제**:
```python
# 라인 392-425
conn = sqlite3.connect(self.db_path)
cursor = conn.cursor()

for tag in hashtags:
    try:
        cursor.execute(...)  # 여기서 예외 발생 시
        ...
    except Exception as e:
        logger.warning(...)
        continue  # conn.close() 호출되지 않고 루프 계속

conn.close()  # for 루프 밖 - 예외 발생 시 도달 안 함
```

**문제점**:
- `for` 루프 내에서 예외가 발생하면 `conn.close()`가 호출되지 않음
- SQLite "too many open connections" 오류 발생 가능
- 메모리 누수 및 파일 핸들 고갈

**해결 방안**:
```python
def analyze_hashtag_trends(self, hashtags: List[str] = None) -> Dict[str, Any]:
    # ... 첫 번째 DB 조회 부분 ...

    conn = None
    try:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for tag in hashtags:
            try:
                # 해시태그별 통계 계산
                cursor.execute(...)
                ...
            except Exception as e:
                logger.warning(f"해시태그 '{tag}' 분석 오류: {e}")
                continue

        return {
            'success': True,
            'analyzed': len(trends),
            'trends': trends[:30]
        }
    except Exception as e:
        logger.error(f"해시태그 트렌드 분석 실패: {e}")
        return {'success': False, 'error': str(e), 'trends': []}
    finally:
        if conn:
            conn.close()
```

---

### 2. Blocking asyncio.run() in EventBus - event_bus.py

**파일**: `/mnt/c/Projects/marketing_bot/marketing_bot_web/backend/services/event_bus.py`
**위치**: 141-151줄 `emit()` 메서드

**현재 문제**:
```python
def emit(self, event_type: EventType, data: Dict[str, Any], source: str = "system") -> None:
    event = Event(type=event_type, data=data, source=source)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(self.publish(event))
    except RuntimeError:
        # 이벤트 루프가 없는 경우 (동기 컨텍스트)
        asyncio.run(self.publish(event))  # ⚠️ 새 루프 생성 - Blocking!
```

**문제점**:
- FastAPI의 async 환경에서 `asyncio.run()`은 새 이벤트 루프를 생성하여 blocking call이 됨
- 중첩 이벤트 루프 오류 ("This event loop is already running") 발생 가능
- 전체 서버 응답 지연

**해결 방안**:
```python
import threading
from queue import Queue

class EventBus:
    def __init__(self):
        # ... 기존 초기화 ...
        self._sync_queue: Queue = Queue()
        self._sync_thread: Optional[threading.Thread] = None
        self._running = True
        self._start_sync_processor()

    def _start_sync_processor(self):
        """동기 컨텍스트에서 발생한 이벤트를 처리하는 백그라운드 스레드"""
        def process_sync_events():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            while self._running:
                try:
                    event = self._sync_queue.get(timeout=1.0)
                    if event is None:  # 종료 신호
                        break
                    loop.run_until_complete(self.publish(event))
                except Exception:
                    continue
            loop.close()

        self._sync_thread = threading.Thread(target=process_sync_events, daemon=True)
        self._sync_thread.start()

    def emit(self, event_type: EventType, data: Dict[str, Any], source: str = "system") -> None:
        event = Event(type=event_type, data=data, source=source)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            # 동기 컨텍스트 - 큐에 넣고 백그라운드 스레드에서 처리
            self._sync_queue.put(event)

    def shutdown(self):
        """EventBus 종료"""
        self._running = False
        self._sync_queue.put(None)  # 종료 신호
        if self._sync_thread:
            self._sync_thread.join(timeout=5.0)
```

---

### 3. Missing try/finally in Database Recovery - recover_data.py

**파일**: `/mnt/c/Projects/marketing_bot/db/recover_data.py`
**위치**: 20-82줄 `recover_data()` 함수

**현재 문제**:
```python
def recover_data():
    # ...
    try:
        conn_old = sqlite3.connect(CORRUPTED_DB)
        conn_new = sqlite3.connect(NEW_DB)

        for table in tables:
            # ... 작업 중 예외 발생 가능 ...

        conn_old.close()  # try 블록 내부 - 예외 시 실행 안 됨
        conn_new.close()

    except Exception as e:
        logger.critical(f"Critical failure: {e}")
        # conn_old, conn_new 닫히지 않음!
```

**문제점**:
- DB 복구 중 오류 발생 시 연결이 닫히지 않음
- 파일 락 유지로 후속 작업 실패 가능
- 데이터 무결성 문제 발생 가능

**해결 방안**:
```python
def recover_data():
    if not os.path.exists(CORRUPTED_DB):
        logger.error(f"Corrupted DB not found: {CORRUPTED_DB}")
        return False

    logger.info(f"Attempting recovery from {CORRUPTED_DB} to {NEW_DB}")

    conn_old = None
    conn_new = None

    try:
        conn_old = sqlite3.connect(CORRUPTED_DB)
        cursor_old = conn_old.cursor()

        conn_new = sqlite3.connect(NEW_DB)
        cursor_new = conn_new.cursor()

        cursor_new.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor_new.fetchall() if row[0] != 'sqlite_sequence']

        for table in tables:
            if table not in ALLOWED_TABLES:
                logger.warning(f"Skipping unknown table: {table}")
                continue

            logger.info(f"Recovering table: {table}")
            try:
                cursor_old.execute(f"SELECT * FROM {table}")
                rows = cursor_old.fetchall()

                if not rows:
                    logger.info(f"  - No data in {table}")
                    continue

                col_count = len(rows[0])
                placeholders = ','.join(['?'] * col_count)

                success_count = 0
                fail_count = 0

                for row in rows:
                    try:
                        cursor_new.execute(f"INSERT OR IGNORE INTO {table} VALUES ({placeholders})", row)
                        success_count += 1
                    except Exception as e:
                        fail_count += 1

                conn_new.commit()
                logger.info(f"  - Recovered {success_count} rows. Failed: {fail_count}")

            except sqlite3.DatabaseError as e:
                logger.error(f"  - Failed to read table {table}: {e}")
            except Exception as e:
                logger.error(f"  - Unexpected error on table {table}: {e}")

        logger.info("Recovery process completed.")
        return True

    except Exception as e:
        logger.critical(f"Critical failure during recovery: {e}")
        return False

    finally:
        # 항상 연결 닫기
        if conn_old:
            try:
                conn_old.close()
            except Exception:
                pass
        if conn_new:
            try:
                conn_new.close()
            except Exception:
                pass
```

---

## 🟠 HIGH - 조속히 수정 필요

### 4. Blocking time.sleep() in Comment Verifier - comment_verifier.py

**파일**: `/mnt/c/Projects/marketing_bot/marketing_bot_web/backend/services/comment_verifier.py`
**위치**: 151, 231, 304, 365, 369, 422, 467줄

**현재 문제**:
```python
def _verify_naver_cafe(self, url: str) -> Dict[str, Any]:
    # ...
    self.driver.get(url)
    time.sleep(2)  # ⚠️ Blocking sleep - 전체 서버 응답 지연
```

**문제점**:
- FastAPI 라우터에서 이 함수를 호출하면 전체 이벤트 루프가 2-3초씩 블로킹됨
- 여러 검증 요청이 들어오면 응답 지연이 누적
- 서버 전체 처리량 감소

**해결 방안 A - ThreadPoolExecutor 사용 (권장)**:
```python
# viral.py에서 호출 시
from concurrent.futures import ThreadPoolExecutor
import asyncio

_verifier_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="verifier")

async def verify_url_async(url: str, platform: str) -> Dict[str, Any]:
    """비동기 URL 검증 - 별도 스레드에서 실행"""
    loop = asyncio.get_event_loop()

    def run_verification():
        with CommentVerifier(headless=True) as verifier:
            return verifier.verify_url(url, platform)

    return await loop.run_in_executor(_verifier_pool, run_verification)
```

**해결 방안 B - 일괄 검증 최적화**:
```python
class BatchCommentVerifier:
    """여러 URL을 효율적으로 검증"""

    def __init__(self, max_workers: int = 3):
        self.max_workers = max_workers

    def verify_batch(self, targets: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        여러 URL 일괄 검증

        Args:
            targets: [{'url': '...', 'platform': '...'}, ...]
        """
        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []

            for target in targets:
                future = executor.submit(
                    self._verify_single,
                    target['url'],
                    target['platform']
                )
                futures.append((target['url'], future))

            for url, future in futures:
                try:
                    result = future.result(timeout=30)
                    results.append({'url': url, **result})
                except Exception as e:
                    results.append({
                        'url': url,
                        'accessible': False,
                        'commentable': False,
                        'reason': f'검증 실패: {str(e)}'
                    })

        return results

    def _verify_single(self, url: str, platform: str) -> Dict[str, Any]:
        with CommentVerifier(headless=True) as verifier:
            return verifier.verify_url(url, platform)
```

---

### 5. Bare except: Clauses

**파일들**:
- `/mnt/c/Projects/marketing_bot/pathfinder_v3_legion.py` (14개소)
- `/mnt/c/Projects/marketing_bot/viral_hunter.py` (3개소)
- `/mnt/c/Projects/marketing_bot/scrapers/instagram_reels_analyzer.py` (2개소)

**현재 문제**:
```python
try:
    # 작업
except:  # ⚠️ 모든 예외 포착 (KeyboardInterrupt, SystemExit 포함)
    pass
```

**문제점**:
- `KeyboardInterrupt`, `SystemExit` 같은 시스템 예외도 잡아서 프로그램 종료 방해
- 어떤 오류가 발생했는지 추적 불가
- 디버깅 및 모니터링 어려움

**해결 방안**:
```python
# 최소한의 수정 - Exception만 포착
try:
    # 작업
except Exception as e:
    logger.debug(f"Non-critical error: {e}")
    pass

# 더 나은 수정 - 특정 예외만 포착
try:
    # 작업
except (ValueError, AttributeError) as e:
    logger.warning(f"Expected error: {e}")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    raise  # 또는 적절한 처리
```

**우선 수정 대상 (viral_hunter.py)**:
```python
# 라인 157
try:
    return {"total": 0, "valid": 0}
except Exception:  # bare except: → Exception
    return {"total": 0, "valid": 0}
```

---

### 6. Subprocess Blocking in BackgroundTasks - pathfinder.py

**파일**: `/mnt/c/Projects/marketing_bot/marketing_bot_web/backend/routers/pathfinder.py`
**위치**: 639-654줄 `run_pathfinder()`

**현재 문제**:
```python
def run_with_log():
    try:
        with open(log_path, 'w', encoding='utf-8') as log_file:
            result = subprocess.run(  # ⚠️ Blocking call
                cmd,
                cwd=parent_dir,
                stdout=log_file,
                stderr=log_file,
                text=True
            )
```

**문제점**:
- `BackgroundTasks`는 FastAPI의 이벤트 루프에서 실행됨
- `subprocess.run()`은 blocking call이라 이벤트 루프를 오래 점유
- 다른 요청 처리 지연

**해결 방안**:
```python
import asyncio
import subprocess as sp

async def run_pathfinder_async(request: PathfinderRequest) -> Dict[str, str]:
    """Pathfinder를 비동기로 실행"""
    script_name = "pathfinder_v3_complete.py" if request.mode == PathfinderMode.TOTAL_WAR else "pathfinder_v3_legion.py"
    script_path = os.path.join(parent_dir, script_name)

    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail=f"스크립트를 찾을 수 없습니다: {script_path}")

    cmd = ["python", script_path]
    if request.mode == PathfinderMode.LEGION:
        cmd.extend(["--target", str(request.target)])
    if request.save_db:
        cmd.append("--save-db")

    log_path = os.path.join(parent_dir, "pathfinder_run.log")

    # 비동기 subprocess 사용
    with open(log_path, 'w', encoding='utf-8') as log_file:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=parent_dir,
            stdout=log_file,
            stderr=log_file,
        )

        # 백그라운드에서 완료 대기 (non-blocking)
        asyncio.create_task(_wait_for_process(process, log_path))

    return {
        "status": "started",
        "message": f"백그라운드 실행 시작됨",
        "mode": request.mode.value,
        "log_file": log_path
    }

async def _wait_for_process(process, log_path: str):
    """프로세스 완료 대기 및 로그 기록"""
    try:
        return_code = await process.wait()
        with open(log_path, 'a', encoding='utf-8') as log_file:
            log_file.write(f"\n\n=== 실행 완료 (exit code: {return_code}) ===\n")
    except Exception as e:
        with open(log_path, 'a', encoding='utf-8') as log_file:
            log_file.write(f"\n\n=== 에러 발생 ===\n{str(e)}\n")
```

---

## 🟡 MEDIUM - 개선 권장

### 7. WebDriver Instance Management - comment_verifier.py

**문제**: 각 검증 요청마다 WebDriver 인스턴스가 새로 생성될 수 있음

**현재 상태**: context manager (`with` 문) 사용으로 어느 정도 관리됨

**개선 방안 - WebDriver Pool**:
```python
from threading import Lock
from queue import Queue
from typing import Optional

class WebDriverPool:
    """Chrome WebDriver 풀 관리"""

    def __init__(self, max_size: int = 3, headless: bool = True):
        self.max_size = max_size
        self.headless = headless
        self._pool: Queue = Queue(maxsize=max_size)
        self._lock = Lock()
        self._created = 0

    def acquire(self) -> 'webdriver.Chrome':
        """풀에서 WebDriver 획득"""
        try:
            return self._pool.get_nowait()
        except:
            with self._lock:
                if self._created < self.max_size:
                    driver = self._create_driver()
                    self._created += 1
                    return driver
            # 풀이 가득 차면 대기
            return self._pool.get(timeout=30)

    def release(self, driver):
        """WebDriver를 풀에 반환"""
        try:
            self._pool.put_nowait(driver)
        except:
            # 풀이 가득 차면 드라이버 종료
            driver.quit()

    def _create_driver(self):
        # ... 기존 드라이버 생성 로직 ...
        pass

    def shutdown(self):
        """모든 WebDriver 종료"""
        while not self._pool.empty():
            try:
                driver = self._pool.get_nowait()
                driver.quit()
            except:
                pass
```

---

### 8. Inefficient Category Lookup - pathfinder.py

**파일**: `/mnt/c/Projects/marketing_bot/marketing_bot_web/backend/routers/pathfinder.py`
**위치**: 235-241줄 `get_category_variants()`

**현재 문제**:
```python
def get_category_variants(standard_category: str) -> List[str]:
    variants = [standard_category]
    for db_cat, std_cat in CATEGORY_MAPPING.items():  # 매번 전체 순회
        if std_cat == standard_category:
            variants.append(db_cat)
    return list(set(variants))
```

**문제점**:
- 호출할 때마다 `CATEGORY_MAPPING` 전체를 순회
- 동일한 카테고리에 대해 반복 계산

**해결 방안 - 역매핑 사전 미리 생성**:
```python
# 모듈 로드 시 한 번만 생성
_REVERSE_CATEGORY_MAPPING: Dict[str, List[str]] = {}

def _build_reverse_mapping():
    """역매핑 사전 생성 (표준 카테고리 → DB 카테고리 목록)"""
    global _REVERSE_CATEGORY_MAPPING
    for db_cat, std_cat in CATEGORY_MAPPING.items():
        if std_cat not in _REVERSE_CATEGORY_MAPPING:
            _REVERSE_CATEGORY_MAPPING[std_cat] = [std_cat]  # 자기 자신 포함
        _REVERSE_CATEGORY_MAPPING[std_cat].append(db_cat)

    # 중복 제거
    for key in _REVERSE_CATEGORY_MAPPING:
        _REVERSE_CATEGORY_MAPPING[key] = list(set(_REVERSE_CATEGORY_MAPPING[key]))

_build_reverse_mapping()

def get_category_variants(standard_category: str) -> List[str]:
    """O(1) 조회"""
    return _REVERSE_CATEGORY_MAPPING.get(standard_category, [standard_category])
```

---

### 9. Silent Error Handling in DB Operations

**여러 파일에서 발견**:
- pathfinder.py: `except Exception as e: print(...)`
- instagram_reels_analyzer.py: `logger.debug(...)` 후 continue

**문제점**:
- 에러가 로그에만 남고 사용자에게 전달되지 않음
- 부분 실패 시 어떤 작업이 성공/실패했는지 알기 어려움

**개선 방안**:
```python
from dataclasses import dataclass
from typing import List, Any

@dataclass
class OperationResult:
    """작업 결과 (부분 실패 지원)"""
    success: bool
    data: Any = None
    errors: List[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        self.errors = self.errors or []
        self.warnings = self.warnings or []

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def add_error(self, msg: str):
        self.errors.append(msg)
        self.success = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'data': self.data,
            'errors': self.errors if self.errors else None,
            'warnings': self.warnings if self.warnings else None
        }
```

---

### 10. Logging Inconsistency

**현재 상태**:
- 일부는 `print()` 사용 (pathfinder.py)
- 일부는 `logger.debug()` 사용 (viral.py)
- 일부는 `logger.info/warning/error()` 사용

**개선 방안**:
- 모든 `print()` 문을 `logger` 호출로 교체
- 로그 레벨 가이드라인 문서화:
  - `DEBUG`: 개발 중 상세 정보
  - `INFO`: 정상 작업 진행 상황
  - `WARNING`: 주의가 필요하지만 계속 진행 가능
  - `ERROR`: 작업 실패
  - `CRITICAL`: 시스템 장애

---

## 📊 구현 우선순위 매트릭스

| 순번 | 항목 | 영향도 | 구현 난이도 | 권장 순서 |
|-----|------|-------|-----------|---------|
| 1 | DB Connection Leak | 높음 | 낮음 | ⭐ 1순위 |
| 3 | recover_data.py try/finally | 높음 | 낮음 | ⭐ 1순위 |
| 5 | Bare except: | 중간 | 낮음 | ⭐ 2순위 |
| 2 | EventBus asyncio.run() | 높음 | 중간 | ⭐ 2순위 |
| 4 | Comment Verifier blocking | 중간 | 중간 | 3순위 |
| 6 | Subprocess blocking | 중간 | 중간 | 3순위 |
| 8 | Category lookup 최적화 | 낮음 | 낮음 | 4순위 |
| 7 | WebDriver Pool | 낮음 | 높음 | 선택 |
| 9 | Silent error handling | 낮음 | 중간 | 선택 |
| 10 | Logging 일관성 | 낮음 | 낮음 | 선택 |

---

## ✅ Phase 1에서 이미 구현된 항목

다음 항목들은 이미 개선되어 이 제안서에서 제외되었습니다:

1. ✅ **스케줄러 레이스 컨디션** - main.py에 스레드/파일 락 추가
2. ✅ **검증 캐시 메모리 누수** - viral.py에 TTL 기반 정리 추가
3. ✅ **리드 분류 레이스 컨디션** - automation.py에 BEGIN IMMEDIATE 트랜잭션 추가
4. ✅ **설정 중앙화** - app_settings.py 생성
5. ✅ **공통 경로 설정** - setup_paths.py 생성
6. ✅ **에러 핸들링 유틸리티** - error_handlers.py 강화
7. ✅ **React Query 설정 프리셋** - queryConfig.ts 생성
8. ✅ **진행률 표시 컴포넌트** - ProgressIndicator.tsx 생성

---

## 📝 변경 이력

| 버전 | 날짜 | 내용 |
|-----|------|------|
| V2.0 | 2026-02-23 | Phase 1 이후 추가 이슈 10개 식별 |
| V1.0 | 2026-02-22 | Phase 1 개선 구현 (8개 항목) |

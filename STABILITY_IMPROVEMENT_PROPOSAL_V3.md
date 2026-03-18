# 성능 및 안정성 개선 제안서 V3
> 작성일: 2026-02-25
> 대상: Marketing Bot 전체 시스템

---

## 개요

전체 코드베이스에 대한 전수 검토 결과, **보안**, **안정성**, **성능** 측면에서 개선이 필요한 항목들을 발견했습니다. 이 문서는 각 문제점과 해결 방안을 우선순위별로 정리합니다.

### 검토 범위
- Python 백엔드: 40+ 파일
- React 프론트엔드: 주요 API 및 컴포넌트
- 스크래퍼: 8개 모듈
- 데이터베이스: SQLite 연결 패턴

### 심각도 분류
| 등급 | 설명 | 조치 기한 |
|------|------|----------|
| 🔴 CRITICAL | 보안 취약점, 데이터 손실 위험 | 24-48시간 |
| 🟠 HIGH | 안정성 문제, 리소스 누수 | 1주일 |
| 🟡 MEDIUM | 성능 저하, 유지보수 어려움 | 2주일 |
| 🟢 LOW | 코드 품질, 모범 사례 | 1개월 |

---

## Phase 1: 보안 취약점 (CRITICAL)

### 1.1 하드코딩된 API 자격증명 🔴

**현재 상태**: `.env` 및 `secrets.json`에 모든 API 키가 평문으로 저장되어 있음

**영향받는 파일**:
- `.env` (라인 2-46)
- `config/secrets.json` (라인 2-55)

**노출된 자격증명**:
| 서비스 | 키 종류 | 위험도 |
|--------|---------|--------|
| Gemini | API Key | 비용 도용 |
| Naver | Client ID/Secret (5쌍) | API 쿼터 남용 |
| Kakao | REST API Key | 서비스 접근 |
| Telegram | Bot Token + Chat ID | 봇 탈취 |
| Instagram | App Secret + Access Token | 계정 접근 |
| YouTube | API Key | 쿼터 남용 |
| OpenAI | API Key | 비용 도용 |

**해결 방안**:
```bash
# 1. 즉시 .gitignore에 추가
echo ".env" >> .gitignore
echo "config/secrets.json" >> .gitignore
echo "*.pem" >> .gitignore
echo "*.key" >> .gitignore

# 2. Git 히스토리에서 제거 (선택)
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env config/secrets.json" \
  --prune-empty --tag-name-filter cat -- --all

# 3. 모든 API 키 재발급 (필수!)
```

**코드 수정**:
```python
# Before (위험)
API_KEY = "AIzaSyBCiBNi186ZriAzp..."

# After (안전)
import os
API_KEY = os.getenv('GEMINI_API_KEY')
if not API_KEY:
    raise EnvironmentError("GEMINI_API_KEY not configured")
```

---

### 1.2 경로 탐색(Path Traversal) 취약점 🔴

**영향받는 파일**: `backend/routers/backup.py:224`

**현재 코드**:
```python
@router.post("/restore/{filename}")
async def restore_backup(filename: str):
    backup_path = os.path.join(backup.backup_dir, filename)
    # filename 검증 없음! "../../../etc/passwd" 가능
```

**공격 시나리오**:
```
POST /api/backup/restore/../../../config/secrets.json
→ 시스템 파일 접근 가능
```

**해결 방안**:
```python
import re
from pathlib import Path

@router.post("/restore/{filename}")
async def restore_backup(filename: str) -> Dict[str, Any]:
    # 1. 파일명 패턴 검증
    if not re.match(r'^[a-zA-Z0-9_\-\.]+\.db$', filename):
        raise HTTPException(400, "유효하지 않은 파일명")

    # 2. 경로 정규화 및 범위 확인
    backup_path = (Path(backup.backup_dir) / filename).resolve()
    backup_dir = Path(backup.backup_dir).resolve()

    # 3. 경로가 백업 디렉토리 내부인지 확인
    if not str(backup_path).startswith(str(backup_dir)):
        raise HTTPException(400, "잘못된 파일 경로")

    # 4. 파일 존재 확인 후 복구 진행
    ...
```

---

### 1.3 CORS 설정 과도하게 허용 🔴

**영향받는 파일**: `backend/main.py:132-139`

**현재 코드**:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # 모든 도메인 허용
    allow_credentials=True,      # 쿠키 포함 허용
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**문제점**: `allow_origins=["*"]` + `allow_credentials=True` 조합은 CSRF 공격에 취약

**해결 방안**:
```python
# 환경 변수로 관리
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:8000,http://localhost:3000').split(',')

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
    max_age=600,
)
```

---

## Phase 2: DB 연결 누수 (HIGH)

### 2.1 try/finally 패턴 미적용 🟠

**영향받는 파일 및 라인**:

| 파일 | 라인 | 문제 |
|------|------|------|
| `pathfinder_upgrades.py` | 66-93 | `conn.close()` 없음 |
| `pathfinder_upgrades.py` | 104-113 | `conn.close()` 없음 |
| `backend/routers/viral.py` | 220-290 | 예외 시 close() 미호출 (10+ 블록) |
| `backend/routers/viral.py` | 1348-1424 | 예외/조건부 반환 시 누락 |
| `backend/services/notification_trigger.py` | 40-272 | 4개 메서드 |
| `backend/services/notification_sender.py` | 41-294 | 2개 메서드 |

**현재 코드 (문제)**:
```python
# viral.py:220-283
try:
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT ...")
    target = cursor.fetchone()

    if not target:
        conn.close()    # 조건부 close
        return False

    conn.commit()
    conn.close()        # 정상 경로만 close
except Exception as e:
    logger.error(...)
    return False        # 예외 시 close() 없음!
```

**해결 방안**:
```python
# 패턴 1: try/finally
conn = None
try:
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    # 작업 수행
    conn.commit()
    return True
except Exception as e:
    logger.error(f"Error: {e}")
    return False
finally:
    if conn:
        conn.close()

# 패턴 2: Context Manager (권장)
with sqlite3.connect(db.db_path) as conn:
    cursor = conn.cursor()
    # 작업 수행
    conn.commit()
# 자동으로 close() 호출
```

**수정 필요 파일 목록**:
```
□ pathfinder_upgrades.py (2개소)
□ backend/routers/viral.py (10+ 개소)
□ backend/services/notification_trigger.py (4개소)
□ backend/services/notification_sender.py (2개소)
```

---

### 2.2 Selenium 드라이버 누수 🟠

**영향받는 파일**: `scrapers/cafe_spy.py:1088`

**현재 코드**:
```python
def run_scan(self):
    # ... 스캔 로직
    self.driver.quit()  # 예외 발생 시 실행 안 됨
```

**해결 방안**:
```python
def run_scan(self):
    try:
        # 스캔 로직
        pass
    finally:
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.warning(f"드라이버 종료 실패: {e}")
```

---

## Phase 3: 동시성 문제 (HIGH)

### 3.1 스레드 안전하지 않은 싱글톤 🟠

**영향받는 파일**: `carrot_farmer.py:16-43`

**현재 코드**:
```python
_shared_config = None

def _get_shared_config():
    global _shared_config
    if _shared_config is None:      # TOCTOU 경쟁 조건
        _shared_config = ConfigManager()
    return _shared_config
```

**문제점**: 두 스레드가 동시에 `None` 체크 시 중복 인스턴스 생성

**해결 방안**:
```python
import threading
from functools import lru_cache

_config_lock = threading.Lock()
_shared_config = None

def _get_shared_config():
    global _shared_config
    if _shared_config is None:
        with _config_lock:
            if _shared_config is None:  # Double-checked locking
                _shared_config = ConfigManager()
    return _shared_config

# 또는 더 간단하게
@lru_cache(maxsize=1)
def _get_shared_config():
    return ConfigManager()
```

---

### 3.2 EventBus 구독자 딕셔너리 동시성 🟠

**영향받는 파일**: `backend/services/event_bus.py:143-148`

**현재 코드**:
```python
def subscribe(self, event_type, handler):
    if event_type not in self._subscribers:   # 읽기
        self._subscribers[event_type] = []     # 쓰기 (Race condition!)
    self._subscribers[event_type].append(handler)
```

**해결 방안**:
```python
import threading
from collections import defaultdict

class EventBus:
    def __init__(self):
        self._subscribers = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event_type, handler):
        with self._lock:
            self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type, handler):
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type].remove(handler)
```

---

### 3.3 메인 스레드 블로킹 🟠

**영향받는 파일**: `scrapers/scraper_naver_place.py:469`

**현재 코드**:
```python
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    for idx, keyword in enumerate(keywords):
        if idx > 0:
            time.sleep(delay_between_starts)  # 메인 스레드 블로킹!
        future = executor.submit(...)
```

**해결 방안**:
```python
def _scan_single_keyword_with_delay(pool, keyword, start_delay=0, **kwargs):
    """워커 스레드에서 딜레이 후 스캔"""
    if start_delay > 0:
        time.sleep(start_delay)  # 워커 스레드에서 대기
    return _scan_single_keyword(pool, keyword, **kwargs)

# 메인 스레드는 블로킹 없이 즉시 제출
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {}
    for idx, keyword in enumerate(keywords):
        delay = idx * delay_between_starts
        future = executor.submit(
            _scan_single_keyword_with_delay,
            pool, keyword,
            start_delay=delay,
            **kwargs
        )
        futures[future] = keyword
```

---

## Phase 4: 에러 처리 개선 (MEDIUM)

### 4.1 Bare Except 패턴 🟡

**영향받는 파일**:

| 파일 | 라인 | 현재 코드 |
|------|------|----------|
| `pathfinder_upgrades.py` | 26, 198 | `except:` |
| `pathfinder_ultra.py` | 823, 832, 841, 865, 876, 896 | `except:` |
| `pathfinder.py` | 390, 1143, 1364, 1374 | `except:` |
| `weakness_content_generator.py` | 185, 261 | `except:` |
| `logging_config.py` | 105 | `except:` |
| `background_scheduler.py` | 401, 409, 441, 452 | `except Exception: pass` |

**해결 방안**:
```python
# Before
try:
    risky_operation()
except:
    pass

# After
try:
    risky_operation()
except Exception as e:
    logger.warning(f"작업 실패: {e}", exc_info=True)
```

---

### 4.2 에러 메시지 정보 노출 🟡

**영향받는 파일**: `backend/routers/backup.py:228, 241`

**현재 코드**:
```python
raise HTTPException(400, detail=f"백업 파일 검증 실패: {str(e)}")
# SQLite 내부 오류 메시지가 클라이언트에 노출됨
```

**해결 방안**:
```python
try:
    conn = sqlite3.connect(backup_path)
    cursor.execute("PRAGMA integrity_check")
except sqlite3.Error as e:
    logger.error(f"DB 검증 실패 [{backup_path}]: {e}")  # 로그에만 상세 정보
    raise HTTPException(400, detail="백업 파일 검증에 실패했습니다")  # 일반 메시지
```

---

## Phase 5: 성능 최적화 (MEDIUM)

### 5.1 SELECT * 제거 🟡

**영향받는 파일**:

| 파일 | 라인 | 쿼리 |
|------|------|------|
| `db/database.py` | 1088 | `SELECT * FROM ...` |
| `insight_manager.py` | 55 | `SELECT * FROM insights` |
| `history_manager.py` | 53 | `SELECT * FROM chat_messages` |

**해결 방안**:
```python
# Before
cursor.execute("SELECT * FROM keyword_insights")

# After (필요한 컬럼만)
cursor.execute("""
    SELECT id, keyword, grade, search_volume, kei, created_at
    FROM keyword_insights
    WHERE status = 'active'
""")
```

---

### 5.2 하드코딩된 설정값 외부화 🟡

**영향받는 파일 및 값**:

| 파일 | 값 | 현재 |
|------|-----|------|
| `scraper_naver_place.py` | sleep | `3 + random.random() * 2` |
| `instagram_reels_analyzer.py` | sleep | `time.sleep(3)` |
| `tiktok_creative_center.py` | sleep | `time.sleep(5)` (4곳) |
| `naver_autocomplete.py` | timeout | `10` |
| `db/database.py` | timeout | `30.0` |
| `weakness_content_generator.py` | history_limit | `100` |

**해결 방안**: `config/performance.json` 추가
```json
{
  "timeouts": {
    "db_connection": 30,
    "http_request": 10,
    "selenium_page_load": 30
  },
  "delays": {
    "scraper_between_requests": [3, 5],
    "parallel_task_start": 2
  },
  "limits": {
    "history_max_entries": 100,
    "cache_max_size": 500
  },
  "retries": {
    "api_call": 3,
    "db_operation": 2
  }
}
```

---

### 5.3 인덱스 추가 🟡

**권장 인덱스**:
```sql
-- rank_history 테이블
CREATE INDEX IF NOT EXISTS idx_rank_history_keyword
ON rank_history(keyword);

CREATE INDEX IF NOT EXISTS idx_rank_history_scanned_at
ON rank_history(scanned_at);

CREATE INDEX IF NOT EXISTS idx_rank_history_keyword_date
ON rank_history(keyword, scanned_date);

-- competitor_reviews 테이블
CREATE INDEX IF NOT EXISTS idx_competitor_reviews_name
ON competitor_reviews(competitor_name);

-- viral_targets 테이블
CREATE INDEX IF NOT EXISTS idx_viral_targets_status
ON viral_targets(status);

CREATE INDEX IF NOT EXISTS idx_viral_targets_platform
ON viral_targets(platform);
```

---

## Phase 6: 코드 품질 (LOW)

### 6.1 메모리 누적 방지 🟢

**영향받는 파일**: `background_scheduler.py:122`

**현재 코드**:
```python
# 상태 파일이 무한히 커질 수 있음
data[time_str] = today
json.dump(data, f)  # 정기 정리 없음
```

**해결 방안**:
```python
import time

def _cleanup_old_state(data: dict, max_age_days: int = 7) -> dict:
    """오래된 상태 항목 제거"""
    cutoff = time.time() - (max_age_days * 86400)
    return {k: v for k, v in data.items()
            if _parse_timestamp(k) > cutoff}

# 저장 전 정리
data = _cleanup_old_state(data)
data[time_str] = today
json.dump(data, f)
```

---

### 6.2 JSON 파싱 타입 검증 🟢

**영향받는 파일**: `frontend/src/services/api/index.ts:191`

**현재 코드**:
```typescript
const data = JSON.parse(event.data)  // 타입 검증 없음
```

**해결 방안**:
```typescript
interface WebSocketMessage {
    type: string;
    payload: unknown;
    timestamp?: string;
}

function parseWebSocketMessage(raw: string): WebSocketMessage | null {
    try {
        const data = JSON.parse(raw);

        if (typeof data !== 'object' || data === null) {
            console.error('Invalid message format');
            return null;
        }

        if (typeof data.type !== 'string') {
            console.error('Missing or invalid type field');
            return null;
        }

        return data as WebSocketMessage;
    } catch (e) {
        console.error('JSON parse error:', e);
        return null;
    }
}

// 사용
const message = parseWebSocketMessage(event.data);
if (message) {
    handleMessage(message);
}
```

---

## 구현 체크리스트

### Phase 1: 보안 (24-48시간) 🔴
- [ ] `.env`, `secrets.json`을 `.gitignore`에 추가
- [ ] 모든 API 키 재발급
- [ ] `backup.py` 경로 탐색 방어 구현
- [ ] CORS 설정 도메인 화이트리스트로 변경

### Phase 2: DB 연결 (1주일) 🟠
- [ ] `viral.py` DB 연결 try/finally 패턴 적용 (10+ 개소)
- [ ] `pathfinder_upgrades.py` DB 연결 수정 (2개소)
- [ ] `notification_trigger.py` DB 연결 수정 (4개소)
- [ ] `notification_sender.py` DB 연결 수정 (2개소)
- [ ] `cafe_spy.py` Selenium 드라이버 try/finally

### Phase 3: 동시성 (1주일) 🟠
- [ ] `carrot_farmer.py` 싱글톤 스레드 안전하게 수정
- [ ] `event_bus.py` 구독자 딕셔너리에 Lock 추가
- [ ] `scraper_naver_place.py` 딜레이를 워커 스레드로 이동

### Phase 4: 에러 처리 (2주일) 🟡
- [ ] Bare except 패턴 수정 (15+ 개소)
- [ ] 에러 메시지 정보 노출 방지

### Phase 5: 성능 (2주일) 🟡
- [ ] SELECT * 제거 (3개소)
- [ ] `config/performance.json` 추가
- [ ] DB 인덱스 추가

### Phase 6: 코드 품질 (1개월) 🟢
- [ ] 상태 파일 정기 정리 로직
- [ ] WebSocket 메시지 타입 검증

---

## 예상 효과

| 항목 | 개선 전 | 개선 후 |
|------|---------|---------|
| 보안 점수 | 40/100 | 85/100 |
| DB 연결 누수 | 발생 가능 | 방지됨 |
| 동시성 안정성 | 불안정 | 안정 |
| 에러 추적 | 어려움 | 용이 |
| 유지보수성 | 중간 | 높음 |

---

## 참고: 이미 완료된 개선 사항

V2 제안서에서 완료된 항목:
- ✅ `instagram_reels_analyzer.py`: DB 연결 try/finally 적용
- ✅ `db/recover_data.py`: try/finally 추가
- ✅ `event_bus.py`: asyncio.run() → 백그라운드 스레드 큐
- ✅ `viral_hunter.py`: Bare except → except Exception
- ✅ `pathfinder_v3_legion.py`: Bare except → except Exception
- ✅ `comment_verifier.py`: 비동기 래퍼 추가
- ✅ `pathfinder.py` (routers): asyncio.create_subprocess_exec() 사용

V3에서 새로 발견된 항목은 위 체크리스트 참조.

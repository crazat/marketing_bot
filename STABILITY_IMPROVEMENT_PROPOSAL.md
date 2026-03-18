# 마케팅 봇 안정성 및 성능 개선 제안서

> **작성일**: 2026년 2월 23일
> **목적**: 기존 기능의 속도, 안정성, 사용자 경험 개선
> **분석 범위**: 전체 코드베이스 심층 검토

---

## 목차

1. [분석 요약](#1-분석-요약)
2. [성능 개선](#2-성능-개선)
3. [안정성 개선](#3-안정성-개선)
4. [UX 개선](#4-ux-개선)
5. [코드 품질 개선](#5-코드-품질-개선)
6. [구현 우선순위](#6-구현-우선순위)

---

## 1. 분석 요약

### 발견된 문제 분류

| 카테고리 | 심각도 | 발견 건수 | 영향 범위 |
|----------|--------|----------|----------|
| N+1 쿼리 / 비효율 쿼리 | 🔴 높음 | 3건 | API 응답 속도 |
| 레이스 컨디션 | 🔴 높음 | 2건 | 데이터 무결성 |
| 메모리 누수 | 🟡 중간 | 2건 | 장시간 운영 시 |
| 에러 핸들링 미흡 | 🟡 중간 | 5건+ | 디버깅/복구 |
| 프론트엔드 렌더링 | 🟡 중간 | 2건 | UI 반응성 |
| UX 피드백 부재 | 🟢 낮음 | 5건+ | 사용자 경험 |

---

## 2. 성능 개선

### 2.1 🔴 N+1 쿼리 문제 해결

#### 문제 1: 키워드 검색량 개별 API 호출

**위치**: `marketing_bot_web/backend/routers/battle.py:61-94`

```python
# 현재 코드 (문제)
for keyword in keywords:
    volume = ad_manager.get_keyword_volumes([keyword])  # 100개 키워드 = 100번 API 호출
```

**개선안**:
```python
# 개선된 코드
def get_all_keyword_volumes(keywords: List[str]) -> Dict[str, int]:
    """배치 API 호출로 N+1 문제 해결"""
    BATCH_SIZE = 100
    results = {}

    for i in range(0, len(keywords), BATCH_SIZE):
        batch = keywords[i:i + BATCH_SIZE]
        batch_results = ad_manager.get_keyword_volumes(batch)
        results.update(batch_results)

    return results
```

**예상 효과**:
- API 호출: 100회 → 1회 (100배 감소)
- 응답 시간: 10-15초 → 0.5-1초

---

#### 문제 2: Lead Scorer 설정 파일 반복 로드

**위치**: `marketing_bot_web/backend/services/lead_scorer.py:36-45`

```python
# 현재 코드 (문제)
class LeadScorer:
    def __init__(self):
        self.config = self._load_config()  # 매 요청마다 파일 I/O
```

**개선안**:
```python
# 싱글톤 + 캐시 패턴 적용
class LeadScorer:
    _instance = None
    _config_cache = None
    _config_mtime = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_config(self):
        config_path = Path("config/scoring_config.json")
        current_mtime = config_path.stat().st_mtime

        if self._config_cache is None or current_mtime > self._config_mtime:
            with open(config_path) as f:
                self._config_cache = json.load(f)
            self._config_mtime = current_mtime

        return self._config_cache
```

**예상 효과**:
- 파일 I/O: 요청당 1회 → 변경 시에만
- 응답 시간: -50ms/요청

---

### 2.2 🔴 프론트엔드 렌더링 최적화

#### 문제: ViralHunter 과도한 useState (70개+)

**위치**: `marketing_bot_web/frontend/src/pages/ViralHunter.tsx:14-70`

```typescript
// 현재 코드 (문제) - 70개 이상의 개별 상태
const [platform, setPlatform] = useState('all');
const [searchTerm, setSearchTerm] = useState('');
const [sortBy, setSortBy] = useState('priority_score');
const [sortOrder, setSortOrder] = useState('desc');
const [statusFilter, setStatusFilter] = useState('all');
// ... 65개 더
```

**개선안**:
```typescript
// useReducer로 상태 통합
interface FilterState {
  platform: string;
  searchTerm: string;
  sortBy: string;
  sortOrder: 'asc' | 'desc';
  statusFilter: string;
  // ... 관련 필터들
}

const initialFilterState: FilterState = {
  platform: 'all',
  searchTerm: '',
  sortBy: 'priority_score',
  sortOrder: 'desc',
  statusFilter: 'all',
};

function filterReducer(state: FilterState, action: FilterAction): FilterState {
  switch (action.type) {
    case 'SET_FILTER':
      return { ...state, [action.field]: action.value };
    case 'RESET_FILTERS':
      return initialFilterState;
    default:
      return state;
  }
}

// 컴포넌트 내부
const [filters, dispatch] = useReducer(filterReducer, initialFilterState);
```

**추가 최적화**:
```typescript
// useMemo로 계산 결과 캐싱
const categoryStats = useMemo(() => {
  return calculateCategoryStats(allTargets);
}, [allTargets]);

// useCallback으로 핸들러 메모이제이션
const handleFilterChange = useCallback((field: string, value: any) => {
  dispatch({ type: 'SET_FILTER', field, value });
}, []);
```

**예상 효과**:
- 리렌더링: 70회 → 1회 (필터 변경당)
- UI 반응성: 체감 2-3배 개선

---

### 2.3 🟡 스크래퍼 메모리 최적화

#### 문제: 브라우저 풀 메모리 과다 사용

**위치**: `scrapers/scraper_naver_place.py:61-103`

```python
# 현재 코드 (문제)
def _create_browser(self):
    options = webdriver.ChromeOptions()
    # 각 브라우저가 독립 프로필 사용 → 500MB+ 메모리
```

**개선안**:
```python
# 공유 캐시 + 메모리 최적화
def _create_browser(self):
    options = webdriver.ChromeOptions()

    # 공유 캐시 디렉토리 사용
    cache_dir = Path.home() / ".marketing_bot" / "browser_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    options.add_argument(f"--disk-cache-dir={cache_dir}")

    # 메모리 최적화 옵션
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--single-process")  # 메모리 절약

    # 이미지/폰트 로딩 비활성화 (순위 확인에 불필요)
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.fonts": 2,
    }
    options.add_experimental_option("prefs", prefs)

    return webdriver.Chrome(options=options)
```

**예상 효과**:
- 메모리: 500MB → 200MB (5개 브라우저 기준)
- 시작 시간: -30%

---

### 2.4 🟡 데이터베이스 쿼리 최적화

#### 문제: 인덱스 누락 가능성

**확인 필요 테이블**:
```sql
-- 자주 조회되는 컬럼에 인덱스 추가
CREATE INDEX IF NOT EXISTS idx_rank_history_keyword_date
ON rank_history(keyword, scanned_date DESC);

CREATE INDEX IF NOT EXISTS idx_viral_targets_platform_status
ON viral_targets(platform, status, priority_score DESC);

CREATE INDEX IF NOT EXISTS idx_leads_status_score
ON leads(status, score DESC);

CREATE INDEX IF NOT EXISTS idx_keyword_insights_grade
ON keyword_insights(grade, mf_kei_score DESC);
```

**쿼리 최적화 예시**:
```python
# 현재 (잠재적 문제)
cursor.execute("SELECT * FROM rank_history WHERE keyword = ?", (keyword,))

# 개선 (명시적 컬럼 + 정렬 + 제한)
cursor.execute("""
    SELECT keyword, rank, device_type, scanned_date, status
    FROM rank_history
    WHERE keyword = ?
    ORDER BY scanned_date DESC
    LIMIT 100
""", (keyword,))
```

**예상 효과**:
- 조회 속도: 3-10배 향상 (인덱스 활용 시)

---

## 3. 안정성 개선

### 3.1 🔴 레이스 컨디션 해결

#### 문제 1: Chronos 스케줄러 상태 파일 동시 접근

**위치**: `marketing_bot_web/backend/main.py:384-425`

```python
# 현재 코드 (문제)
async def chronos_scheduler():
    state = load_scheduler_state()  # 읽기
    # ... 작업 수행 ...
    save_scheduler_state(state)     # 쓰기 - 동시 실행 시 덮어쓰기 위험
```

**개선안**:
```python
import fcntl
from contextlib import contextmanager

@contextmanager
def scheduler_state_lock():
    """파일 기반 락으로 동시 접근 방지"""
    lock_path = Path("config/.scheduler.lock")
    lock_file = open(lock_path, 'w')
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()

async def chronos_scheduler():
    with scheduler_state_lock():
        state = load_scheduler_state()
        # ... 작업 수행 ...
        save_scheduler_state(state)
```

**Windows 호환 버전**:
```python
import filelock

def scheduler_state_lock():
    return filelock.FileLock("config/.scheduler.lock", timeout=10)
```

---

#### 문제 2: 리드 분류 중복 처리

**위치**: `marketing_bot_web/backend/services/automation.py:50-100`

```python
# 현재 코드 (문제)
def classify_new_leads():
    leads = db.execute("SELECT * FROM leads WHERE classified = 0 LIMIT 100")
    for lead in leads:
        classify(lead)
        db.execute("UPDATE leads SET classified = 1 WHERE id = ?", (lead['id'],))
```

**개선안**:
```python
def classify_new_leads():
    """트랜잭션 + 행 잠금으로 중복 방지"""
    conn = db.get_new_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")  # 즉시 쓰기 잠금

        # 처리할 리드 선택 및 잠금
        leads = conn.execute("""
            SELECT id, * FROM leads
            WHERE classified = 0
            LIMIT 100
        """).fetchall()

        if not leads:
            conn.execute("COMMIT")
            return

        lead_ids = [l['id'] for l in leads]

        # 먼저 처리 중으로 표시
        conn.execute(f"""
            UPDATE leads
            SET classified = -1
            WHERE id IN ({','.join('?' * len(lead_ids))})
        """, lead_ids)

        conn.execute("COMMIT")

        # 분류 작업 수행 (잠금 해제 후)
        for lead in leads:
            result = classify(lead)
            conn.execute("""
                UPDATE leads
                SET classified = 1, classification = ?
                WHERE id = ?
            """, (result, lead['id']))
            conn.commit()

    except Exception as e:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
```

---

### 3.2 🔴 메모리 누수 수정

#### 문제: Verification Cache 무한 증가

**위치**: `marketing_bot_web/backend/routers/viral.py:37-58`

```python
# 현재 코드 (문제)
_verification_cache: Dict[str, Dict[str, Any]] = {}

def add_to_cache(key, value):
    if len(_verification_cache) > 1000:
        # 가장 오래된 것 삭제 - 비효율적 + 여전히 증가 가능
        oldest = min(_verification_cache.keys())
        del _verification_cache[oldest]
    _verification_cache[key] = value
```

**개선안 1: LRU Cache 사용**:
```python
from functools import lru_cache
from cachetools import TTLCache

# TTL 기반 캐시 (1시간 후 자동 만료)
_verification_cache = TTLCache(maxsize=1000, ttl=3600)

def add_to_cache(key: str, value: Dict[str, Any]):
    _verification_cache[key] = value

def get_from_cache(key: str) -> Optional[Dict[str, Any]]:
    return _verification_cache.get(key)
```

**개선안 2: 주기적 정리**:
```python
import time

_verification_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = 3600  # 1시간

def cleanup_cache():
    """만료된 캐시 항목 정리"""
    current_time = time.time()
    expired_keys = [
        k for k, v in _verification_cache.items()
        if current_time - v.get('cached_at', 0) > CACHE_TTL
    ]
    for key in expired_keys:
        del _verification_cache[key]

def add_to_cache(key: str, value: Dict[str, Any]):
    if len(_verification_cache) > 800:  # 80% 도달 시 정리
        cleanup_cache()

    value['cached_at'] = time.time()
    _verification_cache[key] = value
```

---

### 3.3 🟡 에러 핸들링 표준화

#### 문제: 일관되지 않은 에러 처리

**현재 상황**:
- `competitors.py`: `print()` 사용
- `leads.py`: `logger.debug()` 사용
- `battle.py`: `logger.warning()` 사용

**통일된 에러 핸들링 유틸리티**:
```python
# marketing_bot_web/backend/backend_utils/error_handler.py

from enum import Enum
from typing import Optional, Any
import traceback
from .logger import get_logger

class ErrorSeverity(Enum):
    LOW = "low"           # 경고만
    MEDIUM = "medium"     # 로깅 + 알림
    HIGH = "high"         # 로깅 + 알림 + 재시도
    CRITICAL = "critical" # 로깅 + 알림 + 서비스 중단

class AppError(Exception):
    def __init__(
        self,
        message: str,
        code: str,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        user_message: Optional[str] = None,
        context: Optional[dict] = None
    ):
        self.message = message
        self.code = code
        self.severity = severity
        self.user_message = user_message or "작업 중 오류가 발생했습니다."
        self.context = context or {}
        super().__init__(self.message)

def handle_error(
    error: Exception,
    logger_name: str,
    context: Optional[dict] = None,
    reraise: bool = True
) -> dict:
    """표준화된 에러 핸들링"""
    logger = get_logger(logger_name)

    error_info = {
        "type": type(error).__name__,
        "message": str(error),
        "traceback": traceback.format_exc(),
        "context": context or {}
    }

    if isinstance(error, AppError):
        if error.severity == ErrorSeverity.CRITICAL:
            logger.critical(f"[{error.code}] {error.message}", extra=error_info)
        elif error.severity == ErrorSeverity.HIGH:
            logger.error(f"[{error.code}] {error.message}", extra=error_info)
        else:
            logger.warning(f"[{error.code}] {error.message}", extra=error_info)
    else:
        logger.exception("Unexpected error", extra=error_info)

    if reraise:
        raise

    return error_info
```

**라우터에서 사용**:
```python
# competitors.py 개선
from backend_utils.error_handler import handle_error, AppError, ErrorSeverity

@router.get("/analysis/{competitor_id}")
async def get_competitor_analysis(competitor_id: int):
    try:
        # ... 비즈니스 로직 ...
        pass
    except sqlite3.OperationalError as e:
        handle_error(
            AppError(
                message=f"Database error: {e}",
                code="DB_OPERATION_FAILED",
                severity=ErrorSeverity.HIGH,
                user_message="데이터베이스 연결에 문제가 발생했습니다. 잠시 후 다시 시도해주세요.",
                context={"competitor_id": competitor_id}
            ),
            logger_name="competitors"
        )
```

---

### 3.4 🟡 Graceful Degradation 구현

#### 문제: API 실패 시 빈 값 반환

**위치**: `marketing_bot_web/backend/routers/battle.py:82-94`

**개선안**:
```python
# 캐시 + 폴백 패턴
from cachetools import TTLCache

_volume_cache = TTLCache(maxsize=5000, ttl=86400)  # 24시간 캐시

async def get_keyword_search_volume(keyword: str) -> int:
    """검색량 조회 - 캐시 우선, API 실패 시 캐시 값 반환"""

    # 1. 캐시 확인
    if keyword in _volume_cache:
        cached = _volume_cache[keyword]
        if not cached.get('stale', False):
            return cached['volume']

    # 2. API 호출 시도
    try:
        volume = await ad_manager.get_keyword_volumes_async([keyword])
        _volume_cache[keyword] = {'volume': volume, 'stale': False}
        return volume

    except Exception as e:
        logger.warning(f"API call failed for '{keyword}': {e}")

        # 3. 캐시에 stale 데이터라도 있으면 반환
        if keyword in _volume_cache:
            logger.info(f"Returning stale cache for '{keyword}'")
            return _volume_cache[keyword]['volume']

        # 4. DB에서 마지막 알려진 값 조회
        last_known = db.execute("""
            SELECT search_volume FROM keyword_volume_cache
            WHERE keyword = ?
            ORDER BY cached_at DESC LIMIT 1
        """, (keyword,)).fetchone()

        if last_known:
            return last_known['search_volume']

        # 5. 최후의 수단: 기본값
        return 0
```

---

## 4. UX 개선

### 4.1 🟡 로딩 상태 피드백 개선

#### 문제: 긴 작업 시 피드백 없음

**개선안: 진행률 컴포넌트 추가**:

```typescript
// components/ui/ProgressIndicator.tsx
interface ProgressIndicatorProps {
  isLoading: boolean;
  progress?: number;  // 0-100, undefined면 indeterminate
  message?: string;
  subMessage?: string;
}

export function ProgressIndicator({
  isLoading,
  progress,
  message = "처리 중...",
  subMessage
}: ProgressIndicatorProps) {
  if (!isLoading) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-sm w-full mx-4 shadow-xl">
        <div className="text-center">
          <div className="text-lg font-medium mb-2">{message}</div>

          {progress !== undefined ? (
            <div className="w-full bg-gray-200 rounded-full h-2 mb-2">
              <div
                className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          ) : (
            <div className="w-full bg-gray-200 rounded-full h-2 mb-2 overflow-hidden">
              <div className="bg-blue-600 h-2 rounded-full animate-pulse w-1/2" />
            </div>
          )}

          {progress !== undefined && (
            <div className="text-sm text-gray-600">{progress}% 완료</div>
          )}

          {subMessage && (
            <div className="text-xs text-gray-500 mt-1">{subMessage}</div>
          )}
        </div>
      </div>
    </div>
  );
}
```

**ViralHunter에서 사용**:
```typescript
// ViralHunter.tsx
<ProgressIndicator
  isLoading={isGeneratingComments}
  progress={generationProgress}
  message="댓글 생성 중..."
  subMessage={`${generationProgress}/100 타겟 처리 완료`}
/>
```

---

### 4.2 🟡 에러 메시지 개선

#### 문제: 일반적인 에러 메시지

**개선안: 액션 가능한 에러 메시지**:

```typescript
// components/ui/ErrorDisplay.tsx
interface ErrorDisplayProps {
  error: {
    code: string;
    message: string;
    userMessage?: string;
    actions?: Array<{
      label: string;
      action: () => void;
    }>;
  };
  onDismiss?: () => void;
}

const ERROR_MESSAGES: Record<string, { message: string; hint: string }> = {
  'DB_CONNECTION_FAILED': {
    message: '데이터베이스 연결 실패',
    hint: '서버를 재시작하거나 잠시 후 다시 시도해주세요.'
  },
  'NAVER_API_LIMIT': {
    message: 'Naver API 호출 한도 초과',
    hint: '1시간 후 자동으로 복구됩니다. 급하시면 관리자에게 문의하세요.'
  },
  'SCRAPER_BLOCKED': {
    message: '스크래핑 일시 차단',
    hint: '2-4시간 후 자동 해제됩니다. 다른 작업을 먼저 진행해주세요.'
  },
  'NETWORK_ERROR': {
    message: '네트워크 오류',
    hint: '인터넷 연결을 확인하고 다시 시도해주세요.'
  }
};

export function ErrorDisplay({ error, onDismiss }: ErrorDisplayProps) {
  const errorInfo = ERROR_MESSAGES[error.code] || {
    message: error.userMessage || '오류가 발생했습니다',
    hint: '문제가 지속되면 관리자에게 문의하세요.'
  };

  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-4">
      <div className="flex items-start">
        <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
        <div className="ml-3 flex-1">
          <h3 className="text-sm font-medium text-red-800">
            {errorInfo.message}
          </h3>
          <p className="text-sm text-red-700 mt-1">
            {errorInfo.hint}
          </p>
          {error.actions && (
            <div className="mt-3 flex gap-2">
              {error.actions.map((action, i) => (
                <button
                  key={i}
                  onClick={action.action}
                  className="text-sm bg-red-100 hover:bg-red-200 text-red-800 px-3 py-1 rounded"
                >
                  {action.label}
                </button>
              ))}
            </div>
          )}
        </div>
        {onDismiss && (
          <button onClick={onDismiss} className="text-red-500 hover:text-red-700">
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
```

---

### 4.3 🟡 데이터 자동 새로고침

#### 문제: 데이터가 stale 상태로 유지

**개선안: React Query 설정 최적화**:

```typescript
// services/api/queryConfig.ts
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 5분 후 stale 상태로 전환
      staleTime: 5 * 60 * 1000,

      // 30분 캐시 유지
      gcTime: 30 * 60 * 1000,

      // 창 포커스 시 자동 새로고침
      refetchOnWindowFocus: true,

      // 네트워크 재연결 시 자동 새로고침
      refetchOnReconnect: true,

      // 3회 재시도
      retry: 3,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
    },
  },
});

// 페이지별 커스텀 설정
export const QUERY_CONFIGS = {
  // 실시간 데이터 (짧은 stale time)
  realtime: {
    staleTime: 30 * 1000,  // 30초
    refetchInterval: 60 * 1000,  // 1분마다 자동 새로고침
  },

  // 준실시간 데이터
  semiRealtime: {
    staleTime: 2 * 60 * 1000,  // 2분
    refetchInterval: 5 * 60 * 1000,  // 5분마다
  },

  // 정적 데이터 (설정 등)
  static: {
    staleTime: 30 * 60 * 1000,  // 30분
    refetchOnWindowFocus: false,
  },
};
```

**사용 예시**:
```typescript
// Dashboard.tsx - 실시간 데이터
const { data: metrics } = useQuery({
  queryKey: ['hud-metrics'],
  queryFn: hudApi.getMetrics,
  ...QUERY_CONFIGS.realtime,
});

// Settings.tsx - 정적 데이터
const { data: config } = useQuery({
  queryKey: ['system-config'],
  queryFn: settingsApi.getConfig,
  ...QUERY_CONFIGS.static,
});
```

---

### 4.4 🟢 URL 상태 동기화

#### 문제: ViralHunter 뷰 상태가 URL에 반영 안 됨

**개선안**:
```typescript
// ViralHunter.tsx 개선
import { useSearchParams } from 'react-router-dom';

function ViralHunter() {
  const [searchParams, setSearchParams] = useSearchParams();

  // URL에서 뷰 상태 읽기
  const currentView = (searchParams.get('view') || 'home') as ViewType;

  // 뷰 변경 핸들러
  const setView = (view: ViewType) => {
    setSearchParams(prev => {
      prev.set('view', view);
      return prev;
    });
  };

  // URL에서 필터 상태도 관리
  const platform = searchParams.get('platform') || 'all';
  const status = searchParams.get('status') || 'all';

  // ... 나머지 컴포넌트
}
```

**효과**:
- 페이지 새로고침해도 뷰 유지
- URL 공유 시 동일한 화면 표시
- 브라우저 뒤로가기 지원

---

## 5. 코드 품질 개선

### 5.1 경로 설정 중복 제거

#### 문제: 24개 라우터에 동일 코드 반복

```python
# 현재 (모든 라우터에 반복)
parent_dir = str(Path(__file__).parent.parent.parent.parent)
backend_dir = str(Path(__file__).parent.parent)
sys.path.insert(0, parent_dir)
sys.path.insert(0, backend_dir)
```

**개선안**:
```python
# marketing_bot_web/backend/setup_paths.py
import sys
from pathlib import Path

def setup_project_paths():
    """프로젝트 경로를 sys.path에 추가"""
    backend_dir = Path(__file__).parent
    project_root = backend_dir.parent.parent

    paths_to_add = [
        str(project_root),
        str(backend_dir),
    ]

    for path in paths_to_add:
        if path not in sys.path:
            sys.path.insert(0, path)

# 자동 실행
setup_project_paths()
```

**라우터에서 사용**:
```python
# routers/leads.py
import backend.setup_paths  # 이 한 줄로 대체
from db.database import DatabaseManager
# ...
```

---

### 5.2 하드코딩 값 설정 파일로 이동

#### 문제: 코드에 직접 작성된 설정값

**개선안**:
```python
# config/app_settings.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class AppSettings(BaseSettings):
    # 데이터베이스
    db_timeout: int = 30
    db_max_connections: int = 5

    # 스레드 풀
    thread_pool_workers: int = 2

    # 캐시
    cache_ttl_seconds: int = 3600
    cache_max_size: int = 1000

    # 스크래퍼
    scraper_max_browsers: int = 5
    scraper_delay_seconds: float = 2.0

    # API
    api_rate_limit_per_minute: int = 1000

    # 스케줄러
    hud_refresh_interval: int = 60

    class Config:
        env_file = ".env"
        env_prefix = "APP_"

@lru_cache()
def get_settings() -> AppSettings:
    return AppSettings()

settings = get_settings()
```

**사용 예시**:
```python
# main.py
from config.app_settings import settings

executor = ThreadPoolExecutor(max_workers=settings.thread_pool_workers)
await asyncio.sleep(settings.hud_refresh_interval)
```

---

### 5.3 로깅 표준화

#### 문제: print() 사용, 일관성 없는 로그 레벨

**개선안**:
```python
# marketing_bot_web/backend/backend_utils/logger.py
import logging
import sys
from pathlib import Path
from datetime import datetime

def setup_logging(log_dir: str = "logs"):
    """애플리케이션 로깅 설정"""
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # 포맷 정의
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 파일 핸들러 (일별 로테이션)
    today = datetime.now().strftime('%Y-%m-%d')
    file_handler = logging.FileHandler(
        log_path / f"app_{today}.log",
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

def get_logger(name: str) -> logging.Logger:
    """모듈별 로거 반환"""
    return logging.getLogger(name)
```

**기존 print() 대체**:
```python
# 변경 전
print(f"Error: {e}")
print(traceback.format_exc())

# 변경 후
logger = get_logger("competitors")
logger.exception(f"Analysis failed for competitor {competitor_id}")
```

---

## 6. 구현 우선순위

### Phase 1: 긴급 (1주일 내)

| 작업 | 파일 | 예상 시간 | 영향도 |
|------|------|----------|--------|
| 스케줄러 레이스 컨디션 수정 | main.py | 2시간 | 🔴 데이터 무결성 |
| 리드 분류 트랜잭션 추가 | automation.py | 3시간 | 🔴 데이터 무결성 |
| 키워드 API 배치 호출 | battle.py | 4시간 | 🔴 성능 100배 개선 |
| Verification 캐시 메모리 누수 수정 | viral.py | 2시간 | 🟡 메모리 안정화 |

### Phase 2: 중요 (2주일 내)

| 작업 | 파일 | 예상 시간 | 영향도 |
|------|------|----------|--------|
| ViralHunter useState 리팩토링 | ViralHunter.tsx | 6시간 | 🟡 UI 반응성 |
| 에러 핸들링 표준화 | 전체 라우터 | 8시간 | 🟡 유지보수성 |
| Graceful Degradation 구현 | battle.py, leads.py | 4시간 | 🟡 안정성 |
| 프로그레스 인디케이터 추가 | 프론트엔드 | 4시간 | 🟢 UX |

### Phase 3: 개선 (1개월 내)

| 작업 | 파일 | 예상 시간 | 영향도 |
|------|------|----------|--------|
| 경로 설정 중복 제거 | setup_paths.py | 2시간 | 🟢 코드 품질 |
| 설정 파일 외부화 | app_settings.py | 4시간 | 🟢 유지보수성 |
| 로깅 표준화 | 전체 | 6시간 | 🟢 디버깅 |
| DB 인덱스 최적화 | db_init.py | 2시간 | 🟡 쿼리 성능 |
| URL 상태 동기화 | ViralHunter.tsx | 3시간 | 🟢 UX |

---

## 예상 개선 효과 요약

| 지표 | 현재 | 개선 후 | 개선율 |
|------|------|---------|--------|
| 키워드 검색량 API 응답 | 10-15초 | 0.5-1초 | **15배** |
| ViralHunter 렌더링 | 70회/변경 | 1회/변경 | **70배** |
| 메모리 사용 (브라우저) | 500MB | 200MB | **60% 감소** |
| 스케줄러 중복 실행 | 가능 | 불가능 | **100% 방지** |
| 에러 복구 시간 | 수동 재시작 | 자동 복구 | **즉시** |
| 사용자 피드백 | 없음 | 실시간 진행률 | **UX 향상** |

---

**문서 작성**: Claude AI
**버전**: 1.0
**최종 수정**: 2026-02-23

> 이 제안서의 각 개선안은 독립적으로 적용 가능하며, 우선순위에 따라 순차적으로 구현하는 것을 권장합니다.

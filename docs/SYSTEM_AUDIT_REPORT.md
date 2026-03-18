# Marketing Bot 시스템 종합 점검 보고서

**작성일:** 2026-02-09
**버전:** v5.0 Post-Implementation Audit

---

## Executive Summary

### 프로젝트 규모
| 영역 | 규모 |
|------|------|
| 프론트엔드 | 24,751줄 / 86개 컴포넌트 |
| 백엔드 | 14,134줄 / 124개 API 엔드포인트 |
| 데이터베이스 | 17개+ 테이블 |
| 스크래핑 모듈 | 26개 파일 |

### 발견된 이슈 요약
| 심각도 | 개수 | 주요 이슈 |
|--------|------|----------|
| CRITICAL | 3 | API 키 노출, SQL 인젝션 위험, DB 동시성 |
| HIGH | 4 | API 일관성, 재시도 로직, 테스트 부재, 타입 힌트 |
| MEDIUM | 4 | 컴포넌트 구조, N+1 쿼리, 문서화, 성능 모니터링 |
| LOW | 4 | 번들 크기, 모바일 UX, 로깅, 프로세스 관리 |

---

## 1. 보안 이슈 (CRITICAL)

### 1.1 API 키 평문 노출

**발견 위치:**
- `.env` 파일
- `config/secrets.json`

**노출된 키:**
- Gemini API Key
- Kakao REST API Key
- Naver Client ID/Secret
- Instagram Access Token

**즉각 조치 필요:**
```bash
# 1. 모든 API 키 즉시 재발급
# 2. .gitignore 확인 및 파일 제거
# 3. Git 히스토리에서 제거 (필요시)
git filter-branch --tree-filter 'rm -f .env config/secrets.json' HEAD
```

**권장 구현:**
```python
# services/secret_manager.py
import os
from dotenv import load_dotenv

class SecretManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            load_dotenv()
        return cls._instance

    def get_secret(self, key: str) -> str:
        value = os.getenv(key)
        if value is None:
            raise ValueError(f"Secret not found: {key}")
        return value
```

---

### 1.2 SQL 인젝션 위험

**발견 위치:**
```python
# 위험한 패턴
cursor.execute(f"SELECT * FROM keywords WHERE keyword = '{keyword}'")
cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name}")
```

**권장 구현:**
```python
# 안전한 패턴
cursor.execute("SELECT * FROM keywords WHERE keyword = ?", (keyword,))

# 동적 테이블/컬럼명은 화이트리스트 검증
ALLOWED_TABLES = ['mentions', 'keyword_insights', 'viral_targets']
if table_name not in ALLOWED_TABLES:
    raise ValueError(f"Invalid table: {table_name}")
```

---

### 1.3 데이터베이스 동시성 문제

**현황:**
- SQLite 사용 중 (단일 writer 제한)
- WAL 모드 활성화되어 있으나 동시 쓰기 충돌 가능

**권장 조치:**
```python
# 1. 연결 풀링 강화
from contextlib import contextmanager
import threading

class DatabasePool:
    _lock = threading.Lock()

    @contextmanager
    def get_connection(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path, timeout=30)
            try:
                yield conn
            finally:
                conn.close()
```

---

## 2. 백엔드 개선 사항 (HIGH)

### 2.1 API 응답 형식 불일치

**현재 상태:**
```python
# 다양한 응답 형식이 혼재
return {"message": "Updated", "id": lead_id}
return {"status": "success", "data": lead}
return {"error": "Lead not found"}, 404
```

**권장 구현:**
```python
# schemas/response.py
from pydantic import BaseModel
from typing import Generic, TypeVar, Optional
from datetime import datetime

T = TypeVar('T')

class ApiResponse(BaseModel, Generic[T]):
    status: str  # "success" | "error"
    data: Optional[T] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)

# 사용법
@router.get("/keywords")
async def get_keywords() -> ApiResponse[List[Keyword]]:
    try:
        data = fetch_keywords()
        return ApiResponse(status="success", data=data)
    except Exception as e:
        return ApiResponse(status="error", error=str(e))
```

---

### 2.2 재시도 로직 미흡

**현재 상태:**
```python
# 고정 대기 시간
time.sleep(2)  # 모든 실패에 2초
```

**권장 구현:**
```python
# services/retry_helper.py
import time
from functools import wraps

def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exponential_base: float = 2.0
):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    delay = base_delay * (exponential_base ** attempt)
                    time.sleep(delay)
        return wrapper
    return decorator

# 사용법
@retry_with_backoff(max_retries=3, base_delay=2)
def scrape_naver_blog(keyword):
    return requests.get(url, timeout=10)
```

---

### 2.3 테스트 자동화 부재

**현재 상태:**
- pytest 설정은 있으나 커버리지 리포트 없음
- CI/CD 파이프라인 없음

**권장 구현:**
```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pip install pytest-cov
      - run: pytest --cov=. --cov-report=xml
      - uses: codecov/codecov-action@v3
```

---

## 3. 프론트엔드 개선 사항 (MEDIUM)

### 3.1 컴포넌트 재사용성

**현재 이슈:**
- Dashboard에서 8개 useQuery 동시 호출
- 상태 관리 일관성 부재
- Props drilling 발생

**권장 구현:**
```typescript
// hooks/useDashboardData.ts
export function useDashboardData() {
  const queries = useQueries({
    queries: [
      { queryKey: ['metrics'], queryFn: fetchMetrics },
      { queryKey: ['alerts'], queryFn: fetchAlerts },
      // ...
    ]
  });

  return {
    isLoading: queries.some(q => q.isLoading),
    isError: queries.some(q => q.isError),
    data: {
      metrics: queries[0].data,
      alerts: queries[1].data,
      // ...
    }
  };
}
```

---

### 3.2 N+1 쿼리 문제

**현재 상태:**
```python
# leads.py: 각 리드마다 추가 쿼리
leads = cursor.execute("SELECT * FROM mentions").fetchall()
for lead in leads:
    cursor.execute("SELECT * FROM keyword_insights WHERE keyword = ?", ...)
```

**권장 구현:**
```python
# JOIN으로 N+1 제거
cursor.execute("""
    SELECT m.*, k.grade, k.search_volume
    FROM mentions m
    LEFT JOIN keyword_insights k ON m.keyword = k.keyword
    WHERE m.status = ?
    ORDER BY m.created_at DESC
    LIMIT ?
""", (status, limit))
```

---

## 4. 데이터베이스 최적화 (MEDIUM)

### 4.1 인덱스 누락

**추가 필요한 인덱스:**
```sql
-- 자주 사용되는 필터 컬럼
CREATE INDEX IF NOT EXISTS idx_mentions_status ON mentions(status);
CREATE INDEX IF NOT EXISTS idx_mentions_source ON mentions(source);
CREATE INDEX IF NOT EXISTS idx_keyword_insights_grade ON keyword_insights(grade);
CREATE INDEX IF NOT EXISTS idx_rank_history_checked ON rank_history(checked_at);
CREATE INDEX IF NOT EXISTS idx_viral_targets_score ON viral_targets(priority_score);
```

### 4.2 스키마 정규화

**현재 이슈:**
```python
# TEXT 필드에 JSON 저장
matched_keywords TEXT DEFAULT '[]'
```

**권장 구현:**
```sql
-- 정규화된 스키마
CREATE TABLE viral_keywords (
    viral_target_id TEXT,
    keyword TEXT,
    PRIMARY KEY (viral_target_id, keyword),
    FOREIGN KEY (viral_target_id) REFERENCES viral_targets(id)
);
```

---

## 5. 코드 품질 개선 (LOW-MEDIUM)

### 5.1 타입 힌트 추가

**현재 상태:**
```python
def __init__(self):  # 반환 타입 없음
    self.config = ConfigManager()
```

**권장 구현:**
```python
from typing import Dict, List, Optional

class Pathfinder:
    def __init__(self) -> None:
        self.config: ConfigManager = ConfigManager()

    def run_campaign(self) -> int:
        total_found: int = 0
        return total_found
```

### 5.2 문서화 강화

**권장 docstring 형식:**
```python
def _normalize_platform(source: str) -> str:
    """
    소스 문자열을 표준 플랫폼 키로 정규화

    Args:
        source: 원본 플랫폼명 (예: "youtube", "naver_cafe")

    Returns:
        표준화된 플랫폼 키 (예: "youtube", "naver")

    Examples:
        >>> _normalize_platform("youtube")
        'youtube'
    """
```

---

## 6. 성능 최적화

### 6.1 번들 크기 분석

**권장 설정:**
```javascript
// vite.config.ts
import { visualizer } from 'rollup-plugin-visualizer';

export default defineConfig({
  plugins: [
    visualizer({
      filename: 'dist/stats.html',
      open: true
    })
  ]
});
```

### 6.2 이미지 최적화

**권장 구현:**
```typescript
// 이미지 lazy loading
<img
  src={src}
  loading="lazy"
  decoding="async"
  alt={alt}
/>
```

---

## 7. 우선순위별 실행 계획

### Phase A: 즉시 조치 (1-2일)

| 작업 | 파일 | 예상 시간 |
|------|------|----------|
| API 키 재발급 및 .env 정리 | .env, secrets.json | 2시간 |
| SQL 인젝션 취약점 수정 | routers/*.py | 4시간 |
| DB 연결 풀링 구현 | database.py | 2시간 |

### Phase B: 높은 우선순위 (1주일)

| 작업 | 파일 | 예상 시간 |
|------|------|----------|
| API 응답 스키마 통일 | schemas/response.py | 4시간 |
| 재시도 로직 구현 | services/retry_helper.py | 3시간 |
| CI/CD 파이프라인 구축 | .github/workflows/ | 4시간 |
| 타입 힌트 추가 | 주요 모듈 | 8시간 |

### Phase C: 중간 우선순위 (2주일)

| 작업 | 파일 | 예상 시간 |
|------|------|----------|
| 컴포넌트 리팩토링 | frontend/src/hooks/ | 8시간 |
| N+1 쿼리 최적화 | routers/*.py | 6시간 |
| 인덱스 추가 | database.py | 2시간 |
| 문서화 강화 | 전체 | 8시간 |

### Phase D: 낮은 우선순위 (개선)

| 작업 | 파일 | 예상 시간 |
|------|------|----------|
| 번들 분석 및 최적화 | vite.config.ts | 4시간 |
| 모바일 UX 개선 | components/*.tsx | 8시간 |
| 로깅 전략 통합 | logging_config.py | 4시간 |
| 프로세스 관리 강화 | main.py | 4시간 |

---

## 8. 추가 권장 사항

### 8.1 모니터링 도구 도입

```python
# Sentry 에러 모니터링
import sentry_sdk
sentry_sdk.init(dsn="your-sentry-dsn")

# Prometheus 메트릭
from prometheus_client import Counter, Histogram
api_requests = Counter('api_requests_total', 'Total API requests')
```

### 8.2 헬스체크 엔드포인트

```python
@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": check_db_connection(),
        "cache": check_cache_connection(),
        "version": "5.0.0"
    }
```

### 8.3 Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.get("/api/scan")
@limiter.limit("10/minute")
async def scan_endpoint():
    ...
```

---

## 9. 결론

### 즉시 해결해야 할 이슈

1. **API 키 노출** - 보안 위험, 즉시 재발급 필요
2. **SQL 인젝션** - 보안 위험, 파라미터화 쿼리로 전환
3. **DB 동시성** - 안정성 위험, 연결 풀링 필요

### 장기적 개선 방향

1. **PostgreSQL 마이그레이션** - 동시성 및 확장성 개선
2. **마이크로서비스 분리** - 스크래핑/분석/API 분리
3. **캐싱 레이어 추가** - Redis 도입
4. **테스트 커버리지 80%+** - 품질 보장

---

**작성:** Claude Code AI Assistant
**검토 대상:** 개발팀, 보안팀
**다음 리뷰 예정:** 구현 완료 후

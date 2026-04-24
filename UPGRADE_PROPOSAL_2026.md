# Marketing Bot 고도화 제안서 (2026-03-23)

> 6개 영역 인터넷 광범위 리서치 기반 종합 제안서
> 현재 시스템: FastAPI + React 18 + SQLite + Gemini AI + Selenium 기반

---

## 목차

1. [Executive Summary](#1-executive-summary)
2. [Phase A: 즉시 적용 (1~2주)](#2-phase-a-즉시-적용-12주)
3. [Phase B: 단기 고도화 (1~2개월)](#3-phase-b-단기-고도화-12개월)
4. [Phase C: 중기 전략 (2~4개월)](#4-phase-c-중기-전략-24개월)
5. [Phase D: 장기 비전 (4~6개월+)](#5-phase-d-장기-비전-46개월)
6. [기술 상세: 네이버 알고리즘 대응](#6-기술-상세-네이버-알고리즘-대응)
7. [기술 상세: AI 고도화](#7-기술-상세-ai-고도화)
8. [기술 상세: 스크래핑 고도화](#8-기술-상세-스크래핑-고도화)
9. [기술 상세: 인프라 현대화](#9-기술-상세-인프라-현대화)
10. [기술 상세: 의료마케팅 규제 대응](#10-기술-상세-의료마케팅-규제-대응)
11. [구현 우선순위 매트릭스](#11-구현-우선순위-매트릭스)

---

## 1. Executive Summary

### 핵심 발견사항

2025-2026년 마케팅 자동화 환경에서 **5가지 메가 트렌드**가 확인되었습니다:

| # | 메가 트렌드 | 현재 시스템 대응 | 고도화 필요성 |
|---|-----------|----------------|-------------|
| 1 | **네이버 AI 검색 전환** (AiRSearch, AI 브리핑, 스마트블록) | 미대응 | 🔴 Critical |
| 2 | **네이버 플레이스 알고리즘 근본 변화** (행동 데이터 > 리뷰 수) | 순위 추적만 | 🔴 Critical |
| 3 | **AI 에이전트 마케팅** (멀티 에이전트, RAG, 자동화) | Gemini 단순 호출 | 🟡 High |
| 4 | **스크래핑 기술 세대 교체** (Selenium → Playwright/camoufox) | Selenium 의존 | 🟡 High |
| 5 | **의료광고 규제 강화** (사전심의 의무화 부활) | 미대응 | 🟠 Important |

### ROI 예상

| 고도화 영역 | 예상 효과 |
|-----------|---------|
| 스크래핑 현대화 | 스캔 속도 5~10배 향상, 차단율 80% 감소 |
| AI 에이전트 도입 | 수작업 80% 절감, 인사이트 품질 향상 |
| AEO/GEO 최적화 | AI 검색 노출 확보 (현재 미노출 → 노출) |
| 실시간 대시보드 | 의사결정 속도 3배 향상 |
| 리뷰 자동 응답 | 응답률 100% 달성, 신뢰도 점수 향상 |

---

## 2. Phase A: 즉시 적용 (1~2주)

### A-1. SQLite WAL 모드 활성화 ⭐ P0

**현재**: 기본 SQLite 설정 (동시 읽기/쓰기 제한)
**개선**: WAL 모드로 동시 읽기 허용, 쓰기 성능 향상

```python
# backend/services/db_init.py에 추가
def optimize_sqlite(conn):
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA cache_size=-64000")  # 64MB 캐시
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA temp_store=MEMORY")
```

**효과**: 읽기 성능 2~5배 향상, 동시성 문제 해결

---

### A-2. Sentry 에러 모니터링 도입 ⭐ P0

**현재**: 로그 파일 기반 수동 디버깅
**개선**: 실시간 에러 추적 + 성능 모니터링

```bash
pip install sentry-sdk[fastapi]
```

```python
# backend/main.py
import sentry_sdk
sentry_sdk.init(
    dsn="YOUR_SENTRY_DSN",
    traces_sample_rate=0.1,  # 10% 트레이싱
    profiles_sample_rate=0.1,
)
```

**효과**: 에러 즉시 감지, 스택 트레이스 자동 수집, 무료 플랜 가용

---

### A-3. Health Check 엔드포인트 ⭐ P0

```python
# backend/routers/health.py
@router.get("/health")
async def health():
    db_ok = await check_db_connection()
    return {
        "status": "healthy" if db_ok else "degraded",
        "db": db_ok,
        "version": APP_VERSION,
        "uptime": get_uptime(),
        "last_scan": get_last_scan_time(),
    }
```

---

### A-4. 네이버 플레이스 별점 5점 척도 대응 ⭐ P0

**변경사항 (2026년 4월 6일부터 순차 적용)**:
- 네이버 플레이스 리뷰에 **별점 5점 척도** 도입
- 리뷰 수정 가능 기간: 작성 후 **3개월 이내**로 제한
- 가짜 리뷰 탐지 알고리즘 대폭 강화

**대응**:
- `competitor_reviews` 테이블에 `star_rating REAL` 컬럼 추가
- 경쟁사 평균 별점 추적 로직 추가
- 별점 트렌드 시각화 (Battle Intelligence 페이지)

---

### A-5. 구조화된 로깅 (structlog) ⭐ P0

```bash
pip install structlog
```

**현재**: 비정형 로그 → **개선**: JSON 구조화 로그 (검색/분석 가능)

---

## 3. Phase B: 단기 고도화 (1~2개월)

### B-1. 스크래핑 엔진 현대화 (Selenium → Playwright + camoufox) 🔴 Critical

**현재 문제점**:
- Selenium + undetected-chromedriver (2024년 2월 이후 업데이트 중단)
- 네이버 차단 리스크 높음
- 브라우저 리소스 과다 사용

**신규 스택 제안**:

| 계층 | 현재 | 제안 | 이점 |
|------|------|------|------|
| HTTP 클라이언트 | requests | **curl-cffi** | TLS 지문 위장, 브라우저 불필요 |
| 브라우저 (스텔스) | Selenium | **camoufox** (Firefox 기반) | 최강 지문 랜덤화 |
| 브라우저 (Chromium) | undetected-chromedriver | **rebrowser-playwright** | Playwright API + 안티탐지 |
| 지문 생성 | 없음 | **browserforge** | 실제 트래픽 분포 모방 (0.1ms) |
| CAPTCHA | 수동 | **CapSolver** | AI 기반 자동 해결 |

**마이그레이션 단계**:

1. **API 우선 전환**: Naver Search API로 대체 가능한 스크래핑을 API 호출로 전환
2. **HTTP 클라이언트 전환**: `curl-cffi`로 API/비렌더링 페이지 수집
3. **브라우저 엔진 전환**: Place Sniper를 `rebrowser-playwright`로 마이그레이션
4. **한국 레지덴셜 프록시 도입**: 네이버 차단 방지 필수

**Playwright 마이그레이션 이점**:
- 속도 20% 향상 (CDP 직접 통신)
- Browser Context로 병렬 실행 최적화 (별도 프로세스 불필요)
- 내장 자동 대기 (ActionabilityCheck) → 불안정한 explicit wait 제거
- iframe 처리 단순화 (DOM 요소처럼 접근)
- 리소스 차단 내장 (이미지/폰트/CSS 차단으로 대역폭 2~5배 절약)

```python
# 예시: rebrowser-playwright로 네이버 플레이스 스크래핑
from rebrowser_playwright.async_api import async_playwright

async def scan_naver_place(keyword: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            # 리소스 차단으로 속도 향상
        )
        page = await context.new_page()
        await page.route("**/*.{png,jpg,gif,svg,woff,woff2}", lambda route: route.abort())
        await page.goto(f"https://m.place.naver.com/place/list?query={keyword}")
        # ... 스크래핑 로직
```

---

### B-2. AI 검색 최적화 (AEO/GEO) 대응 모듈 🔴 Critical

**배경**: 2025년 12월 기준 네이버 전체 검색의 **20% 이상**이 AI 브리핑을 통해 이루어짐

**새로운 최적화 패러다임 3계층**:

| 구분 | 설명 | 대응 전략 |
|------|------|----------|
| **SEO** | 기존 검색엔진 최적화 | 현재 시스템 (키워드 순위 추적) |
| **AEO** (Answer Engine Optimization) | AI 요약/브리핑 노출 최적화 | **신규 필요** |
| **GEO** (Generative Engine Optimization) | 생성형 AI가 브랜드 인용/추천 | **신규 필요** |

**구현 제안 - AI 검색 노출 트래커**:

```
새 수집기: scrapers/ai_search_tracker.py

기능:
1. 네이버 AI 브리핑에서 한의원 관련 키워드 검색 시 노출 여부 추적
2. 경쟁사 AI 브리핑 노출 모니터링
3. AI가 인용하는 소스 URL 수집 → 콘텐츠 전략 수립

새 DB 테이블: ai_search_visibility
- keyword, ai_briefing_mentioned (bool), source_urls, competitor_mentioned
- scanned_date, briefing_content_summary
```

**콘텐츠 최적화 가이드 자동 생성**:
- Gemini로 기존 블로그 콘텐츠 분석
- AEO 최적화 점수 산출 (구조화 정도, FAQ 포함 여부, 전문성 지표)
- 개선 제안 자동 생성

---

### B-3. 네이버 플레이스 행동 데이터 추적 모듈 🔴 Critical

**2025년 5월 알고리즘 대변화**: 순위 결정이 '리뷰 수'에서 **실제 고객 행동 데이터**로 전환

**4대 핵심 평가 지표 추적**:

| 지표 | 추적 방법 | 구현 |
|------|----------|------|
| **적합도** | 키워드-업체 매칭 분석 | Gemini로 자동 분석 |
| **인기도** | 전화, 길찾기, 예약, 저장 수 | 스마트플레이스 통계 CSV 연동 강화 |
| **최신성** | 소식 탭 업데이트 빈도 | 자동 알림 (N일 미업데이트 시) |
| **신뢰성** | 리뷰 응답률, NAP 일관성 | 자동 점검 + 리뷰 응답 지원 |

**구현 - 스마트플레이스 통계 자동 임포트 강화**:
```
현재: smartplace_stats 테이블 (CSV 수동 임포트)
개선:
- 네이버 스마트플레이스 통계 항목별 트렌드 시각화
- 전화 / 길찾기 / 예약 / 저장 각각의 일별 추이
- 키워드별 유입 경로 분석
- 경쟁사 대비 상대적 위치 추정
```

---

### B-4. 리뷰 자동 응답 시스템 🟡 High

**배경**: 네이버 플레이스에서 **리뷰 응답률 100%**가 신뢰도 점수에 직접 영향

**구현 설계**:

```
새 모듈: review_response_generator.py

워크플로우:
1. 새 리뷰 감지 (place_scan_enrichment 연동)
2. Gemini로 리뷰 분석:
   - 감성 분류 (긍정/중립/부정)
   - 주제 분류 (서비스, 가격, 시설, 효과, 대기)
   - 별점 (5점 척도 대응)
3. 응답 초안 자동 생성:
   - 긍정: 감사 + 재방문 유도
   - 부정: 공감 + 개선 의지 + 연락 안내
4. 텔레그램으로 초안 전송 → 원장님 확인/수정 후 게시

DB 테이블: review_responses
- review_id, sentiment, topics[], star_rating
- draft_response, final_response, status (draft/approved/posted)
- response_time_minutes
```

---

### B-5. SSE(Server-Sent Events) 실시간 대시보드 🟡 High

**현재**: TanStack Query 120초 폴링 → **개선**: SSE로 실시간 업데이트

```python
# backend/routers/stream.py
from sse_starlette.sse import EventSourceResponse

@router.get("/api/stream/dashboard")
async def dashboard_stream():
    async def event_generator():
        while True:
            # 스캔 진행률, 새 알림, 순위 변동 등 실시간 전송
            data = await get_dashboard_updates()
            yield {"event": "update", "data": json.dumps(data)}
            await asyncio.sleep(5)
    return EventSourceResponse(event_generator())
```

**이점**: 서버 부하 감소, 즉시 업데이트, 자동 재연결 내장

---

### B-6. Redis 캐싱 레이어 도입 🟡 High

```python
# API 응답 캐싱 (fastapi-cache2)
from fastapi_cache.decorator import cache

@router.get("/api/battle/rankings")
@cache(expire=300)  # 5분 캐시
async def get_rankings():
    ...
```

**캐싱 전략**:
| 엔드포인트 | TTL | 이유 |
|-----------|-----|------|
| 대시보드 메트릭 | 30초 | 자주 조회, 빈번 변경 |
| 순위 데이터 | 5분 | 스캔 주기 대비 충분 |
| 키워드 통계 | 10분 | 변경 빈도 낮음 |
| 경쟁사 분석 | 30분 | 일 1회 업데이트 |

---

## 4. Phase C: 중기 전략 (2~4개월)

### C-1. AI 에이전트 시스템 (멀티 에이전트) 🟡 High

**현재**: Gemini 단발성 호출 (분석 요청 → 응답)
**개선**: 역할 기반 AI 에이전트 팀 구성

**에이전트 아키텍처 (CrewAI 기반)**:

```
┌─────────────────────────────────────────────────┐
│              Orchestrator Agent                   │
│  (작업 분배, 우선순위 결정, 승인 게이트)            │
└──────────┬────────────┬────────────┬─────────────┘
           │            │            │
    ┌──────▼──────┐ ┌───▼────┐ ┌────▼─────┐
    │ SEO Analyst │ │ Review │ │ Content  │
    │   Agent     │ │ Agent  │ │  Agent   │
    │             │ │        │ │          │
    │• 순위 분석   │ │• 감성분석│ │• 블로그  │
    │• 키워드 추천 │ │• 응답생성│ │  초안 생성│
    │• 경쟁사 비교 │ │• 트렌드 │ │• AEO 최적화│
    └─────────────┘ └────────┘ └──────────┘
           │            │            │
    ┌──────▼──────┐ ┌───▼────┐ ┌────▼─────┐
    │ Competitor  │ │ Lead   │ │ Report   │
    │ Intel Agent │ │ Agent  │ │  Agent   │
    │             │ │        │ │          │
    │• 변경 감지   │ │• 스코어링│ │• 주간보고 │
    │• 약점 분석   │ │• 우선순위│ │• 인사이트 │
    │• 기회 포착   │ │• 접근전략│ │• 브리핑   │
    └─────────────┘ └────────┘ └──────────┘
```

**Gemini 활용 고도화**:
- **Grounding with Google Search**: 실시간 웹 데이터 기반 분석
- **Grounding with Google Maps**: 위치 기반 경쟁사 인텔리전스
- **Function Calling**: 에이전트가 DB 쿼리, API 호출을 직접 실행
- **Structured Output**: JSON 스키마 기반 정형 데이터 추출

```python
# Gemini 3 Flash - Grounding + Function Calling 예시
from google import genai
from google.genai import types

client = genai.Client(api_key=api_key)

# Google Search Grounding으로 실시간 경쟁사 정보 수집
response = client.models.generate_content(
    model='gemini-3-flash-preview',
    contents="청주 한의원 최근 마케팅 동향과 경쟁사 활동을 분석해줘",
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        response_mime_type="application/json",
        response_schema={...}  # 구조화된 출력 스키마
    )
)
# response.candidates[0].grounding_metadata.web_search_queries
# response.candidates[0].grounding_metadata.grounding_chunks (소스 URL)
```

---

### C-2. RAG 기반 마케팅 인텔리전스 🟡 High

**목적**: 축적된 마케팅 데이터(리뷰, 키워드, 경쟁사 분석, 블로그 등)를 AI가 통합 분석

**아키텍처**:

```
[마케팅 데이터]     [벡터 DB]      [AI 에이전트]

리뷰 데이터    ──→  Chroma/     ──→  "경쟁사 A의 최근
키워드 분석    ──→  Qdrant에    ──→   약점은 무엇이고
경쟁사 정보    ──→  임베딩 저장  ──→   우리가 활용할
블로그 콘텐츠  ──→              ──→   전략은?"
인텔리전스 보고서                     → 즉각적인 데이터 기반 답변
```

**추천 벡터 DB**:
- **프로토타입**: Chroma (경량, 로컬 설치, 설정 최소)
- **프로덕션**: Qdrant (Rust 기반 고성능, Docker로 설치)

**RAG 활용 시나리오**:
1. "이번 달 가장 효과적이었던 키워드 전략은?"
2. "경쟁사 B가 최근 3개월간 변경한 사항은?"
3. "부정 리뷰에서 반복되는 패턴은 무엇인가?"
4. "다음 주 블로그에 다룰 최적의 주제는?"

---

### C-3. 커뮤니티 & 바이럴 감지 고도화 🟡 High

**현재**: 네이버 카페/블로그 + 지식인 수집
**추가**: 실시간 바이럴 감지 + 속도 기반 스파이크 탐지

```
새 기능: 바이럴 속도 감지기 (Viral Velocity Detector)

메커니즘:
1. 각 키워드/멘션의 시간당 발생 빈도 추적
2. 이동 평균(MA) 대비 3σ 초과 시 바이럴 스파이크 판정
3. 즉시 텔레그램 P1 알림 발송
4. 관련 콘텐츠 자동 수집 및 분석

DB 테이블: viral_velocity
- keyword, mention_count_hourly, moving_average
- spike_detected (bool), spike_magnitude, detected_at
```

---

### C-4. 환자 여정(Patient Journey) 추적 대시보드 🟠 Important

**새 페이지**: `/patient-journey`

```
환자 여정 퍼널 시각화:

[블로그/SNS 노출] → [플레이스 조회] → [전화/길찾기] → [예약] → [내원] → [리뷰] → [재방문]
     1,000            500             200           80       60      20       12

각 단계 간 전환율 추적 + 개선 포인트 자동 식별
```

---

### C-5. Docker Compose 로컬 개발환경 🟡 High

```yaml
# docker-compose.yml
services:
  backend:
    build: ./marketing_bot_web/backend
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - ./marketing_bot_web/backend:/app
      - ./db:/app/db
      - ./config:/app/config
    env_file: .env
    healthcheck:
      test: curl -f http://localhost:8000/health
      interval: 30s

  frontend:
    build: ./marketing_bot_web/frontend
    command: npm run dev -- --host 0.0.0.0
    volumes:
      - ./marketing_bot_web/frontend:/app
    ports:
      - "5173:5173"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

---

### C-6. React 19 마이그레이션 🟡 High

**주요 변경사항**:
- `forwardRef` 단순화 (이제 일반 prop)
- Context가 직접 Provider로 동작
- `use()` 훅으로 Promise 처리 (Suspense 연동)
- `useOptimistic()` 으로 낙관적 업데이트

**마이그레이션 절차**:
1. React 18 최신 버전으로 업데이트, deprecation 경고 해결
2. 공식 codemod 실행: `npx codemod@latest react/19/migration-recipe`
3. 서드파티 라이브러리 호환성 확인 (TanStack Query, Tailwind 등)
4. 스테이징 환경에서 테스트

---

## 5. Phase D: 장기 비전 (4~6개월+)

### D-1. Naver MCP 서버 연동 (AI 에이전트 기반)

2025년 등장한 **Naver Search MCP Server**를 활용하여 AI 에이전트가 네이버 검색/DataLab API를 직접 호출:

```
기존: 스크립트가 API 호출 → DB 저장 → UI 표시
개선: AI 에이전트가 MCP로 직접 검색 → 분석 → 의사결정 → 실행
```

**활용 MCP 프로젝트**:
- `isnow890/naver-search-mcp`: 종합 검색 + DataLab 트렌드
- `pfldy2850/py-mcp-naver`: Python 기반 Naver MCP

---

### D-2. 예측 분석 (Predictive Analytics) 도입

**모델**:
1. **순위 예측**: 과거 순위 + 리뷰 추세 + 계절성 → 향후 순위 예측
2. **리드 전환 예측**: 리드 속성 → 전환 확률 스코어링
3. **키워드 트렌드 예측**: DataLab 시계열 → 향후 검색량 예측
4. **이탈 예측**: 환자 방문 패턴 → 이탈 위험 환자 조기 감지

```python
# 시계열 예측 (prophet 또는 statsforecast)
from statsforecast import StatsForecast
from statsforecast.models import AutoARIMA

sf = StatsForecast(models=[AutoARIMA(season_length=7)], freq='D')
forecast = sf.forecast(df=rank_history_df, h=30)  # 30일 예측
```

---

### D-3. 통합 광고 관리 (네이버 검색+디스플레이)

**배경**: 2026년 상반기 네이버 검색광고 + 성과형 디스플레이 광고 **통합 관리 화면** 제공 예정

**대비**:
- 검색광고 API + GFA API 통합 모니터링 구축
- 광고비 대비 전환율(ROAS) 자동 추적
- AI 기반 입찰가 조정 제안

---

### D-4. AI 챗봇 연동 (카카오톡 기반)

**추천 솔루션**: 메이크봇H (h.makebot.ai) - 카카오톡 기반 24시간 예약 챗봇

**연동 시나리오**:
1. 카카오톡 채널 → 메이크봇H 챗봇 → 네이버 예약 연동
2. 증상 사전 상담 → 관련 진료 안내
3. 진료 후 자동 팔로우업 메시지
4. 휴면 환자 자동 리텐션

---

### D-5. TimescaleDB 마이그레이션 (조건부)

**SQLite 한계에 도달할 경우**에만 실행:

| 트리거 | 증상 |
|--------|------|
| 동시 쓰기 충돌 | WAL 모드에서도 쓰기 대기 발생 |
| 데이터 규모 | 100GB+ |
| 분석 쿼리 성능 | 복잡한 집계 쿼리가 10초+ |

**TimescaleDB 이점**:
- PostgreSQL 완전 호환 (기존 SQL 그대로 사용)
- 시계열 자동 파티셔닝 (hypertable)
- 연속 집계 (continuous aggregates) → 대시보드 즉시 응답
- 10~20배 압축
- Grafana 네이티브 연동

---

## 6. 기술 상세: 네이버 알고리즘 대응

### 6.1 네이버 플레이스 2025-2026 알고리즘 핵심 변화

**순위 결정 공식 변화**:
```
이전: 리뷰 수 + 운영 기간 + 키워드 매칭
현재: 유입의 구조와 비율 + 실제 행동 데이터 + 맥락적 검색
```

**4대 핵심 평가 지표**:
1. **적합도**: 키워드-업체 정보 매칭 정도
2. **인기도**: 실제 고객 행동 (전화, 길찾기, 예약, 저장)
3. **최신성**: 정보 업데이트 빈도, 소식 탭 활성화
4. **신뢰성**: 리뷰 품질, NAP 일관성, 응답률

**맥락적 검색 (Contextual Search)**:
- AI가 사용자의 현재 위치, 시간대, 과거 취향을 분석
- 동일 키워드라도 사용자마다 다른 결과 노출
- → 다양한 페르소나에서의 순위 추적 필요

### 6.2 네이버 블로그 SEO 변화

**C-Rank + D.I.A. 알고리즘 업데이트**:
- **시맨틱 깊이** 중시: 키워드 반복 ❌ → 주제의 포괄적/맥락적 커버 ✅
- **AuthGR**: AI 스팸 탐지 시스템 도입 → AI 생성 콘텐츠 필터링
- **VIEW탭 → 스마트블록 통합**: 별도 VIEW탭 대신 검색 의도별 유동적 조합

**대응 전략**:
- AI로 생성한 콘텐츠도 반드시 인간의 전문 지식/경험 추가
- 구조화된 글쓰기 (소제목, 표, 불릿 포인트)
- 실제 촬영 사진/영상 필수 (AI 스팸 필터 통과 핵심)

### 6.3 네이버 서비스 연동 점수

동일 최적화 지수에서 **네이버 생태계 연동도**가 순위 차별화 요소:

| 서비스 | 연동 효과 |
|--------|----------|
| 네이버 톡톡 | 실시간 상담 → 인기도 가산 |
| 네이버 예약 | 예약 전환 → 인기도 가산 |
| 네이버 스마트콜 | 전화 추적 → 인기도 가산 |
| 네이버페이 | 결제 연동 → 인기도 가산 |
| 네이버 쇼츠 | 15초~1분 영상 → 최신성 가산 |
| 네이버 블로그 | 콘텐츠 연동 → 적합도+신뢰성 가산 |

---

## 7. 기술 상세: AI 고도화

### 7.1 Gemini API 최신 기능 활용

| 기능 | 모델 | 활용처 |
|------|------|--------|
| **Grounding with Google Search** | 2.5+ | 실시간 경쟁사 모니터링, 시장 조사 |
| **Grounding with Google Maps** | 3.0+ | 위치 기반 경쟁사 인텔리전스 |
| **Function Calling** | 2.5+ | 에이전트가 DB/API 직접 호출 |
| **Structured Output** | 3.0+ | JSON 스키마 기반 정형 데이터 추출 |
| **Multimodal Input** | 2.5+ | 경쟁사 이미지/영상 분석 |

### 7.2 Gemini 모델 비교 (2026년 3월 기준)

| 모델 | 입력 비용 | 출력 비용 | 컨텍스트 | 추천 용도 |
|------|----------|----------|---------|----------|
| Gemini 2.5 Flash | $0.30/M | $2.50/M | 1M | 대량 콘텐츠 생성, 리뷰 분석 |
| Gemini 2.5 Pro | $1.00/M | $10.00/M | 1M | 복잡한 추론, 전략 분석 |
| **Gemini 3 Flash** | $0.50/M | $3.00/M | 1M | 시각/공간 추론, 현재 사용 중 |
| Gemini 3.1 Pro | $2.00/M | $12.00/M | 1M | 최고 성능 분석 |

**비용 최적화 전략**:
- 대량 처리 (리뷰 분류, 키워드 분석): **2.5 Flash** ($0.30/M)
- 일반 분석 (경쟁사, 콘텐츠): **3 Flash** (현행 유지)
- 심층 전략 (주간 보고서, 종합 분석): **2.5 Pro** 또는 **3.1 Pro**

### 7.3 AI 에이전트 프레임워크 비교

| 프레임워크 | 아키텍처 | 개발 속도 | 추천 |
|-----------|---------|----------|------|
| **CrewAI** | 역할 기반 팀 | 가장 빠름 (40%) | ✅ 1순위 |
| **LangGraph** | 그래프 기반 워크플로우 | 유연하지만 느림 | 복잡한 워크플로우 |
| **AutoGen** | 대화형 에이전트 | 빠른 프로토타입 | MS 생태계 |

---

## 8. 기술 상세: 스크래핑 고도화

### 8.1 안티탐지 기술 스택 (2026년)

| 도구 | 방식 | 탐지 우회 수준 | 용도 |
|------|------|-------------|------|
| **nodriver** | CDP 직접 통신 (Selenium 제거) | ⭐⭐⭐⭐ | Cloudflare 우회 |
| **camoufox** | Firefox 기반 + 지문 랜덤화 | ⭐⭐⭐⭐⭐ | 최강 스텔스 |
| **rebrowser-playwright** | Playwright + 안티탐지 패치 | ⭐⭐⭐⭐ | Playwright 호환 |
| **botasaurus** | 올인원 + 인간형 마우스 | ⭐⭐⭐⭐ | 간편 사용 |
| **curl-cffi** | TLS 지문 위장 HTTP | ⭐⭐⭐ | API/HTTP 전용 |
| **browserforge** | 통계 기반 지문 생성 | - (보조) | 지문 데이터 제공 |

### 8.2 네이버 특화 안티봇 대응

**네이버 탐지 방법**:
1. IP 기반 속도 제한 (비한국 IP, 데이터센터 IP 차단)
2. 브라우저 지문 검사 (자동화 시그니처)
3. 행동 패턴 분석 (클릭, 스크롤, 요청 타이밍)
4. 지역 제한 (한국 IP 필수)

**필수 체크리스트**:
- [x] 한국 레지덴셜 프록시 (필수)
- [x] 한국 로케일 헤더 (`ko-KR`)
- [x] 한국 타임존 (`Asia/Seoul`)
- [x] 현실적 요청 타이밍 (2~5초 랜덤 딜레이)
- [x] 세션 쿠키 유지
- [x] UTF-8 인코딩 전체 파이프라인
- [x] 지수 백오프 (4xx/5xx 응답 시)
- [x] API 우선 사용 (스크래핑 전에 API 확인)

### 8.3 데이터 품질 파이프라인

```
[Raw HTML/JSON] → [인코딩 정규화] → [Unicode 정리] → [HTML 추출]
                                                         ↓
[비즈니스 규칙 검증] ← [스키마 검증 (Pydantic)] ← [중복 제거]
         ↓
[메타데이터 추가] → [DB 저장]
```

**한국어 텍스트 특화**:
- UTF-8 강제 (`response.apparent_encoding` 감지)
- NFC 정규화 (한글 자모 분리 방지)
- 불가시 유니코드 문자 제거 (zero-width spaces, BOM)

---

## 9. 기술 상세: 인프라 현대화

### 9.1 태스크 큐/스케줄링 개선

**현재**: `schedule.json` + subprocess 호출
**권장 진화 경로**:

```
현재 (Chronos Timeline)
  ↓ Phase B
APScheduler (AsyncIOScheduler)  ← FastAPI 내장, 외부 브로커 불필요
  ↓ Phase C (필요 시)
Dramatiq + Redis               ← 분산 워커, 재시도, 태스크 체이닝
  ↓ Phase D (필요 시)
Temporal                        ← 미션 크리티컬 장기 워크플로우
```

**APScheduler 장점**:
- FastAPI `AsyncIOScheduler`와 네이티브 통합
- cron 표현식 직접 지원
- 외부 브로커 불필요 (현재 시스템과 동일한 단순성)
- 재시도, 태스크 상태 추적 가능

### 9.2 알림 체계 고도화

**3단계 우선순위 라우팅**:

| 우선순위 | 채널 | 예시 |
|---------|------|------|
| **P1 (Critical)** | 텔레그램 DM 즉시 | 바이럴 스파이크, 부정 리뷰 급증, 순위 급락 |
| **P2 (Important)** | 텔레그램 채널 | 순위 변동, 경쟁사 활동, 새 리드 |
| **P3 (Info)** | 일일 다이제스트 | 일상 메트릭, 주간 요약 |

---

### 9.3 보안 강화

| 항목 | 현재 | 제안 |
|------|------|------|
| 인증 | API Key | JWT + Refresh Token 회전 |
| 속도 제한 | 없음 | slowapi (Redis 기반) |
| CORS | 전체 허용? | 특정 오리진만 허용 |
| 데이터 암호화 | 없음 | API 키/비밀 환경변수 분리 |

---

## 10. 기술 상세: 의료마케팅 규제 대응

### 10.1 의료광고 사전심의 의무화 (부활)

**핵심 규제**:
- 플랫폼 이용자 수 **10만 명 이상**이면 사전심의 필수
- 네이버 블로그, 인스타그램, 유튜브, 틱톡 **모두 해당**
- 위반 시: **1년 이하 징역 또는 1,000만원 이하 벌금 + 업무정지**

**시스템 대응 - 콘텐츠 심의 체크리스트 모듈**:

```
새 기능: 콘텐츠 심의 가이드

워크플로우:
1. 블로그/SNS 콘텐츠 작성
2. Gemini로 의료광고 규정 위반 사항 사전 점검:
   - 치료 전후 사진 사용 여부
   - 과장 표현 여부 ("100% 효과", "완치" 등)
   - 환자 후기 게시 규정 준수 여부
   - 의료인 자격 표시 여부
3. 심의 필요 항목 자동 플래그
4. 대한한의사협회 심의위원회 제출 안내

DB: content_compliance_checks
- content_type, content_url, ai_check_result
- compliance_issues[], severity, review_status
```

### 10.2 SNS/블로그 콘텐츠 규정 체크리스트

| 항목 | 허용 | 금지 |
|------|------|------|
| 진료 과목 안내 | ✅ | |
| 치료 원리 설명 | ✅ | |
| 치료 전후 사진 | ✅ (심의 후) | ❌ (심의 없이) |
| "완치", "100% 효과" | | ❌ |
| 타 의료기관 비방 | | ❌ |
| 인플루언서 협찬 | | ❌ |
| 환자 후기 | ✅ (동의+심의) | ❌ (무단 사용) |
| 할인/이벤트 | ✅ (조건부) | ❌ (과도한 유인) |

---

## 11. 구현 우선순위 매트릭스

### 영향도 × 난이도 매트릭스

```
영향도 높음
    │
    │  A-1 SQLite WAL ★      B-1 스크래핑 현대화
    │  A-2 Sentry ★           B-2 AEO/GEO 대응
    │  A-4 별점 대응 ★         B-3 행동 데이터 추적
    │  B-4 리뷰 자동응답       B-5 SSE 실시간
    │  B-6 Redis 캐싱         C-1 AI 에이전트
    │                         C-2 RAG 인텔리전스
    │
    │  A-3 Health Check ★     C-3 바이럴 감지 고도화
    │  A-5 structlog ★        C-5 Docker Compose
    │                         C-6 React 19
    │                         C-4 환자 여정
    │                         D-1 MCP 연동
    │                         D-2 예측 분석
영향도 낮음 ──────────────────────────────────────────
          난이도 낮음                        난이도 높음

★ = 1~2주 내 즉시 적용 가능
```

### 실행 로드맵 요약

| Phase | 기간 | 핵심 항목 | 예상 효과 |
|-------|------|----------|----------|
| **A** | 1~2주 | SQLite WAL, Sentry, 별점 대응, structlog | 안정성 +50% |
| **B** | 1~2개월 | 스크래핑 현대화, AEO/GEO, 행동 데이터, 리뷰 자동응답, SSE, Redis | 수집 성능 5x, AI 검색 노출 확보 |
| **C** | 2~4개월 | AI 에이전트, RAG, 바이럴 고도화, Docker, React 19 | 자동화 80%, 인사이트 품질 대폭 향상 |
| **D** | 4~6개월+ | MCP 연동, 예측 분석, 통합 광고, 챗봇, TimescaleDB | 풀스택 마케팅 인텔리전스 플랫폼 |

---

## 부록: 참고 자료

### 네이버 마케팅
- 네이버 플레이스 2025년 5월 알고리즘 대변경 (행동 데이터 중심)
- 네이버 플레이스 별점 5점 척도 도입 (2026.04.06~)
- 네이버 AI 브리핑 전체 검색의 20%+ 차지 (2025.12~)
- VIEW탭 → 스마트블록 완전 통합 (2025~)
- AuthGR AI 스팸 탐지 시스템 도입
- Naver Search MCP Server 등장 (AI 에이전트 연동)

### AI 기술
- Gemini 3 Flash/Pro 출시 (2025.12~), Google Maps Grounding 지원
- CrewAI 에이전트 프레임워크 (LangGraph 대비 40% 빠른 개발)
- RAG 시장 $9.86B by 2030 (CAGR 38.4%)
- AI 에이전트 시장 $52.62B by 2030 (CAGR 46.3%)

### 스크래핑
- undetected-chromedriver 사실상 중단 (2024.02 마지막 릴리스)
- camoufox: Firefox 기반 최강 지문 랜덤화 (2025.01)
- rebrowser-playwright: Playwright 드롭인 안티탐지 대체
- curl-cffi: TLS 지문 위장 HTTP (Chrome 136까지 지원)

### 의료마케팅
- 의료광고 사전심의 의무화 부활 (위반 시 1년 징역/1000만원 벌금)
- 한의사협회 SNS 의료광고 심의 가이드북 발간 (2025.09)
- 의료 CRM 시장 $54.95B by 2029 (CAGR 13.7%)
- 헬스케어 챗봇 시장 $17.74B by 2035 (CAGR 23.5%)

### 인프라
- SQLite Renaissance: WAL + Litestream = 90% PostgreSQL 대체
- SSE > WebSocket (95% 대시보드 사용 사례)
- APScheduler → Dramatiq → Temporal (점진적 진화)
- React 19 정식 출시 (2024.12, 안정화 완료)

---

*이 제안서는 2026년 3월 23일 기준 인터넷 리서치 결과를 바탕으로 작성되었습니다.*
*실제 구현 시 각 항목의 현재 버전과 호환성을 재확인하시기 바랍니다.*

# Claude Code 프로젝트 가이드라인

## 프로젝트 개요

**Marketing Bot** - 한의원 마케팅 자동화 시스템
- 네이버 플레이스 순위 추적
- 키워드 발굴 (Pathfinder)
- 경쟁사 분석 및 약점 공략
- 바이럴 콘텐츠 수집
- 리드(잠재고객) 발굴

---

## 핵심 기술 스택

### 백엔드
- **FastAPI** (Python 3.11+)
- **SQLite** 데이터베이스
- **Gemini 2.5 Flash Lite + 3.1 Flash Lite Preview** (google-genai SDK, 중앙 클라이언트: `services/ai_client.py`)

### 프론트엔드
- **React 18** + TypeScript
- **TanStack Query** (데이터 페칭)
- **Tailwind CSS** (스타일링)
- **Vite** (빌드)

---

## 중요: 실행 환경

### ⚠️ Windows에서만 실행
사용자는 **Windows에서만** 실행합니다. WSL은 사용하지 않습니다.

```bash
# 서버 실행 (Windows CMD/PowerShell에서)
build_and_run.bat
```

### Python 스크립트 직접 실행 권장
웹 UI에서 스캔 실행보다 터미널에서 직접 실행이 더 안정적:

```bash
# Pathfinder 키워드 수집
python pathfinder_v3_complete.py --save-db

# 순위 스캔 (모바일 + 데스크탑) - [Phase 3] 기본값: 병렬 모드
python scrapers/scraper_naver_place.py

# [Phase 3] 병렬 모드 옵션
python scrapers/scraper_naver_place.py -w 5        # 5개 브라우저 동시 실행
python scrapers/scraper_naver_place.py --sequential  # 순차 모드 (기존 방식)
python scrapers/scraper_naver_place.py --skip-reviews  # 경쟁사 리뷰 수집 스킵

# 데스크탑 스크래핑 테스트 (모바일 제외)
python test_desktop_only.py

# LEGION 모드 (대량 키워드 수집)
python pathfinder_v3_legion.py --target 500 --save-db
```

> **참고**: 웹 서버에서 Place Sniper 실행 시에도 `scrapers/scraper_naver_place.py`를 subprocess로 호출합니다 (hud.py:56). 새 스캔 실행 시 최신 코드가 바로 적용됩니다.

---

## 프로젝트 구조

```
/mnt/c/projects/marketing_bot/
├── config/
│   ├── config.json          # API 키 설정 (Gemini, Naver)
│   ├── keywords.json         # 키워드 설정 (naver_place, blog_seo)
│   ├── schedule.json         # Chronos Timeline 스케줄 설정
│   └── business_profile.json # 업체 정보
├── db/
│   ├── marketing_data.db     # 메인 데이터베이스
│   └── backups/              # DB 백업
├── marketing_bot_web/
│   ├── backend/              # FastAPI 백엔드
│   │   ├── main.py
│   │   ├── routers/          # API 라우터들
│   │   │   ├── battle.py     # Battle Intelligence API
│   │   │   ├── competitors.py # 경쟁사 분석 API
│   │   │   ├── hud.py        # 대시보드 API
│   │   │   ├── leads.py      # 리드 관리 API
│   │   │   ├── pathfinder.py # 키워드 발굴 API
│   │   │   ├── qa.py         # Q&A Repository API (Phase 5.0)
│   │   │   └── viral.py      # 바이럴 콘텐츠 API
│   │   ├── services/
│   │   │   └── db_init.py    # DB 스키마 초기화 (Phase 6.1)
│   │   └── backend_utils/    # 백엔드 유틸리티 (⚠️ utils 아님!)
│   │       ├── logger.py     # 로깅 시스템
│   │       └── error_handlers.py
│   └── frontend/             # React 프론트엔드
│       └── src/
│           ├── pages/        # 페이지 컴포넌트
│           ├── components/   # UI 컴포넌트
│           │   ├── settings/     # Settings 페이지 탭 컴포넌트 (8개)
│           │   └── viral/views/  # ViralHunter 뷰 컴포넌트
│           └── services/api/ # API 클라이언트 (도메인별 분리)
├── scrapers/
│   ├── scraper_naver_place.py # 네이버 플레이스 순위 스크래핑 (모바일+데스크탑)
│   ├── scraper_instagram.py   # Instagram 스크래핑
│   ├── scraper_youtube.py     # YouTube 스크래핑
│   ├── scraper_tiktok_monitor.py # TikTok 모니터링
│   ├── cafe_spy.py            # 네이버 카페 스크래핑
│   └── competitor_analyzer.py # 경쟁사 분석
├── pathfinder_v3_complete.py # 키워드 발굴 스크립트
├── pathfinder_v3_legion.py   # LEGION 모드 (대량 키워드 수집)
├── test_desktop_only.py      # 데스크탑 스크래핑 테스트 (모바일 제외)
└── vision_analyst.py         # 이미지 분석 (Gemini Vision)
```

> ⚠️ **주의**: `backend/backend_utils/` 폴더명은 프로젝트 루트의 `utils.py`와 충돌을 피하기 위해 `backend_utils`로 명명됨. `from backend_utils.logger import ...` 형태로 import.

---

## 주요 페이지 및 기능

| 페이지 | 경로 | 기능 |
|--------|------|------|
| Dashboard | `/` | 메트릭, 브리핑, Sentinel Alerts, Chronos Timeline |
| Pathfinder | `/pathfinder` | 키워드 수집/분석/활용/히스토리/클러스터 |
| Viral Hunter | `/viral` | 바이럴 콘텐츠 수집 |
| Battle Intelligence | `/battle` | 순위 추적, 트렌드, 경쟁사 활력 |
| Lead Manager | `/leads` | 6개 플랫폼 리드 관리 |
| Competitor Analysis | `/competitors` | 약점 공략, 기회 키워드, Instagram 분석 |
| Settings | `/settings` | 시스템 정보 |

---

## 데이터베이스 테이블

### 핵심 테이블
- `keyword_insights` - 발굴된 키워드 (grade, search_volume, category, status)
- `rank_history` - 순위 스캔 이력 (keyword, rank, status, device_type, scanned_date)
  - `device_type`: "mobile" 또는 "desktop" (2026-02-12부터 분리 추적)
- `competitor_reviews` - 경쟁사 리뷰 데이터
- `competitor_weaknesses` - 경쟁사 약점 분석 결과
- `opportunity_keywords` - 기회 키워드
- `viral_targets` - 바이럴 콘텐츠 (matched_keyword 컬럼 포함)

### Phase 5.0/6.x 추가 테이블
- `qa_repository` - Q&A 패턴 및 표준 응답 (question_pattern, standard_answer, variations)
- `scan_runs` - Pathfinder 스캔 실행 기록 (mode, status, grade별 count)
- `auto_approval_rules` - AI Agent 자동 승인 규칙
- `competitor_rankings` - 경쟁사 순위 추적 (scanned_date 컬럼 사용)
- `contact_history` - 리드 컨택 히스토리
- `notifications` - 알림 (reference_keyword, link 컬럼 포함)
- `comment_templates` - 댓글 템플릿 (situation_type, engagement_signal)

### rank_history.status 값
- `found` - 순위 발견됨
- `not_in_results` - 검색 결과 100위 내에 없음
- `no_results` - 검색 결과 자체가 없음
- `error` - 스캔 오류

---

## keywords.json 구조

```json
{
  "naver_place": [
    "청주 한의원",
    "청주 다이어트 한약",
    // ... 플레이스 순위가 존재하는 키워드만
  ],
  "blog_seo": [
    "청주 새살침",
    "청주 안면비대칭 교정"
    // ... 플레이스 순위가 없는 블로그 SEO용 키워드
  ]
}
```

---

## AI 모델 사용 규칙

**Gemini (google-genai SDK) — 중앙 클라이언트 사용. 용도별 2단 구성.**

| 함수 | 모델 | 가격 (1M tok) | 용도 |
|------|------|:---:|------|
| `ai_generate()` | **gemini-2.5-flash-lite** (GA) | $0.10 / $0.40 | 분류·판단·요약 (바이럴 적합성 등) |
| `ai_generate_json()` | **gemini-2.5-flash-lite** (GA) | $0.10 / $0.40 | 구조화 JSON (response_mime_type) |
| `ai_generate_korean()` | **gemini-3.1-flash-lite-preview** | $0.25 / $1.50 | 한국어 댓글·창작 (자연스러움 우선) |

모든 AI 호출은 `services/ai_client.py`를 통해 이루어집니다. 모델 변경 시 이 파일만 수정.

```python
# 올바른 사용법 (중앙 클라이언트)
from services.ai_client import ai_generate, ai_generate_json, ai_generate_korean

# 텍스트 생성 / 분류 / 판단 (저렴한 기본 모델)
result = ai_generate(prompt, temperature=0.7, max_tokens=4096)

# JSON 생성 (자동 파싱 + 복구)
data = ai_generate_json(prompt, temperature=0.3, max_tokens=4096)

# 한국어 댓글·창작 (더 자연스러운 preview 모델)
comment = ai_generate_korean(prompt, temperature=0.6, max_tokens=800)

# 잘못된 사용 (금지)
from google import genai              # X - 직접 호출 금지
from openai import OpenAI             # X - 사용 안 함 (Qwen 전환 완료)
client = genai.Client(api_key=...)    # X - 중앙 클라이언트 사용
```

**환경변수**:
- `GEMINI_API_KEY` (필수) — `config/secrets.json`에 있음, 자동 폴백
- `GEMINI_CLASSIFY_MODEL` (선택) — 기본 모델 오버라이드
- `GEMINI_KOREAN_MODEL` (선택) — 한국어 모델 오버라이드

**예외**: `vision_analyst.py`만 Gemini Vision (이미지 분석)을 직접 사용

**폴백 동작**: `ai_generate_korean()` 호출 실패 시 자동으로 `ai_generate()`(기본 모델)로 재시도

---

## 최근 개선 사항 (2026-04-25) — UX 대규모 정비 (4 ultrathink 라운드)

4회 연속 UX 감사를 통해 Critical 5건, High 8건, Medium 7건의 사용성 문제를 해결. 각 라운드마다 문제를 찾고 → 검증 → 구현 → TypeScript 체크 → 다음 라운드 루프.

### 1차 — 구조적 마찰 제거

- Dashboard 중복 "📊 상세 분석" Collapsible 2개 → 1개로 병합
- Dashboard 섹션 순서 재배치 (배너 → 메트릭 → 목표 → 스마트액션 → 알림/빠른실행 → 상세분석)
- Settings 탭 **10개 → 7개** (알림+외부알림, 자동화+연동, 시스템+설정파일 병합)
- LeadManager 뷰 모드 3개 → **2개** (카드뷰 제거, 테이블/칸반만 유지)
- ViralHunter "전체 목록 보기" → **"일괄 작업 모드"**로 라벨 명확화
- 모바일 햄버거 메뉴 열림 시 MobileTabBar 자동 숨김

### 2차 — MarketingHub 통합 (1차에서 놓친 발견)

- MarketingHub 탭 **8개 → 5개** (golden-time+lead-quality→performance 등 병합)
- MarketingHub Overview compact 위젯 **6개 → 3개**로 축소
- MarketingHub 탭을 공용 `TabNavigation` 컴포넌트로 전환
- Dashboard ROI·WeeklyReport → MarketingHub로 이관 (Dashboard에서 링크만 안내)
- Pathfinder 필터 그리드 반응형 (`grid-cols-1 md:grid-cols-4` → `sm:grid-cols-2 lg:grid-cols-4`)
- LeadManager "잠재 고객" → "리드" 용어 통일
- BattleIntelligence 예측 카드 부가 지표 모바일 숨김 (`hidden sm:block`)
- CompetitorAnalysis 탭 밑줄 겹침 수정 (`-bottom-px`)

### 3차 — Analytics 페이지 폐지 (A안 선택)

- **Analytics 페이지 완전 흡수** → Marketing Hub에 통합. Sidebar "마케팅 분석" 메뉴 제거
- MarketingHub 탭 **5개 → 6개** (🔗 어트리뷰션 신설)
- Analytics 흡수 컴포넌트 8종: AIInsights, PerformanceFeedback, AttributionChain, KeywordLifecycle, ResponseGoldenTime, ChannelROI, CompetitorMovements, WeeklyBriefing
- `/analytics?tab=*` → `/marketing?tab=*` 자동 리다이렉트 (레거시 북마크 호환)
- 전역 단축키 `g+a` (Analytics) → `g+m` (Marketing Hub) 재매핑
- Toast `defaultDuration` **4000ms → 5500ms** (연속 액션 시 빨리 사라지는 문제 해결)
- LeadTable 컬럼 **11개 → 9개** (감성 제거, 발견일은 xl 이상만)
- ConversionModal ESC/오버레이 클릭 보호 (입력값 있을 때 차단)
- WorkView 자동 다음 타겟 `scrollIntoView` 추가 (연속 A/S/D 처리 시 화면 자동 스크롤)

### 4차 — 탭 일관성 완성

- `TabNavigation` 컴포넌트에 `badge?: number` prop 지원 추가
- BattleIntelligence 7탭 → `TabNavigation` 전환 (하락 알림 badge 유지)
- CompetitorAnalysis 7탭 → `TabNavigation` 전환
- Dashboard "오늘 할 일" 위젯 **3개 → 2개** (`SuggestedActions` 제거, `SmartActionPanel` 상시 노출로 승격)

### 누적 효과

| 항목 | Before | After |
|------|:----:|:----:|
| Dashboard 중복 "상세 분석" Collapsible | 2개 | 1개 |
| Dashboard 중복 "오늘 할 일" 위젯 | 3개 | 2개 |
| Settings 탭 | 10 | 7 |
| MarketingHub 탭 | 8 | 6 (Analytics 흡수 포함) |
| LeadManager 뷰 모드 | 3 | 2 |
| LeadTable 컬럼 | 11 | 9 |
| 페이지 탭 `TabNavigation` 통일 | 6/8 | **8/8** |
| 사이드바 최상위 메뉴 | 12 | 11 |
| Toast 표시 시간 | 4초 | 5.5초 |

### URL 마이그레이션 (모두 자동 리다이렉트)

**Analytics 폐지**:
- `/analytics?tab=ai-insights` → `/marketing?tab=growth`
- `/analytics?tab=golden-time` → `/marketing?tab=performance`
- `/analytics?tab=competitor` → `/marketing?tab=monitoring`
- `/analytics?tab=lifecycle` → `/marketing?tab=attribution`
- `/analytics?tab=roi|attribution|performance|overview` → 같은 ID 재사용

**MarketingHub 탭 통합**:
- `?tab=golden-time|lead-quality` → `performance`
- `?tab=campaigns|ab-tests` → `growth`
- `?tab=competitor-radar|alerts` → `monitoring`

**Settings 탭 통합**:
- `?tab=external-notifications` → `notifications`
- `?tab=integrations` → `automation`
- `?tab=config` → `system`

**LeadManager 뷰**: `?view=card` → `table`

### 기능 삭제 0건

- Analytics의 모든 컴포넌트는 MarketingHub 내부 탭/섹션으로 유지
- 제거된 것은 **중복 위젯·중복 개념**만 (SuggestedActions, 2번 렌더되던 Collapsible)
- 폐지된 Analytics 페이지도 리다이렉트 셔임으로 보존

### 감사 프로세스 교훈

1·2·3차 라운드에서 false positive를 경험함 → 에이전트 보고를 **파일 내용으로 직접 검증** 후에만 구현. 이미 구현돼 있던 것들 (ConversionModal 라벨, Pathfinder 빈 상태, WorkView 자동 이동 로직)은 잘못된 플래그였음.

특히 **1차에서 MarketingHub(8탭)를 놓친 것**과 **2차에서 Analytics(8탭)를 놓친 것**이 큰 교훈 — 사이드바의 모든 페이지를 체크리스트로 순회해야 함.

---

## 최근 개선 사항 (2026-04-25)

### Qwen → Gemini 전면 마이그레이션

Qwen3.5-Flash 무료 한도 초과로 전면 교체. 용도별 2단 구성으로 비용과 품질 양쪽 최적화.

**모델 선정 근거**:
- **분류/판단 (대량)**: `gemini-2.5-flash-lite` — GA, 최저가, 10k 타겟 스캔 1회 $0.36
- **한국어 댓글 생성**: `gemini-3.1-flash-lite-preview` — 2.5 Flash보다 **싸고**(-17%/-40%), **빠르고**(+64%), **우수** (Intelligence Index +62%, GPQA +4p, SimpleQA +16p)
- 세대 차이(3.1 vs 2.5)가 등급 차이(Lite vs 표준)를 압도. 단 FACTS Grounding이 85→41로 급락하므로 팩트는 프롬프트에 RAG 주입 필수

**변경된 파일**: `marketing_bot_web/backend/services/ai_client.py` 전면 재작성

**호출부 호환성**: 모든 기존 함수 시그니처 유지. 호출자 코드 변경 불필요 (21개 파일).

**SDK 변경**:
- 이전: `openai.OpenAI` + DashScope 엔드포인트
- 현재: `google.genai.Client` (v1.60.0)

**환경변수 이전**:
- `QWEN_API_KEY` 제거 → `GEMINI_API_KEY` 재사용 (`config/secrets.json`에 이미 있음)

**레거시 방어**: 호출자가 실수로 `model="qwen-..."` 넘겨도 자동으로 기본 Gemini 모델로 대체.

**스모크 검증 통과**: `ai_generate` / `ai_generate_json` / `ai_generate_korean` 3개 함수 모두 실 API 호출 성공 확인.

---

## 최근 개선 사항 (2026-03-18)

### Phase 9-10: 정보 수집 고도화 (Intelligence Enhancement)

26개 데이터 수집기, 25개 DB 테이블, 34→27개 스케줄 작업 구현 및 정리.

#### 핵심 수집기 (활성 - 테스트 완료)

| 파일 | 기능 | 수집 건수 |
|------|------|:--------:|
| `scrapers/naver_api_community_monitor.py` | 블로그+카페 커뮤니티 멘션 (Naver Search API) | 523건 |
| `scrapers/naver_kin_lead_finder.py` | 지식인 리드 자동 발굴 + 바이럴 등록 | 1,118건 |
| `scrapers/naver_ad_keyword_collector.py` | 네이버 광고 키워드 + 경쟁 분석 (ad_bid 통합) | 759건 |
| `scrapers/keyword_trend_collector.py` | DataLab 키워드 트렌드 시계열 | 203건 |
| `scrapers/competitor_blog_tracker.py` | 경쟁사 블로그 포스팅 추적 | 215건 |
| `scrapers/competitor_change_detector.py` | 경쟁사 Place 변경 감지 | 베이스라인 |
| `scrapers/healthcare_news_monitor.py` | 의료/경쟁사 뉴스 모니터링 | 859건 |
| `scrapers/web_visibility_tracker.py` | 웹 검색 가시성 추적 | 19건 |
| `scrapers/search_demographics_analyzer.py` | 키워드별 연령/성별 인구통계 | 19건 |
| `scrapers/blog_rank_tracker.py` | 블로그 VIEW탭 순위 | 19건 |
| `scrapers/naver_shop_trend_monitor.py` | 한약/건강식품 쇼핑 트렌드 | 7건 |
| `scrapers/intelligence_synthesizer.py` | 6종 종합 인텔리전스 리포트 + 텔레그램 | 6건 |
| `scrapers/data_health_monitor.py` | 수집 파이프라인 헬스체크 | - |
| `scrapers/place_scan_enrichment.py` | Place Sniper 후처리 (리뷰메타+SERP) | Selenium |

#### 보조 수집기 (비활성 - 조건부)

| 파일 | 비활성 사유 |
|------|-----------|
| `scrapers/kakao_map_tracker.py` | Kakao REST API 키 만료 |
| `scrapers/hira_api_client.py` | data.go.kr API 키 미발급 |
| `scrapers/commercial_data_collector.py` | data.go.kr API 키 미발급 |
| `scrapers/medical_review_monitor.py` | 모두닥/굿닥 URL 404 |
| `scrapers/review_intelligence_collector.py` | GraphQL 차단 → place_scan_enrichment로 대체 |
| `scrapers/geo_grid_tracker.py` | Naver Local API 위치 미지원 |
| `scrapers/review_nlp_analyzer.py` | google-genai 패키지 필요 (Windows 전용) |

#### 삭제된 파일

- `scrapers/community_monitor_expanded.py` → `naver_api_community_monitor`로 대체

#### 통합 사항

- `ad_bid_monitor` → `naver_ad_keyword_collector`에 내장
- `naver_api_community_monitor`에서 지식인 제거 → `naver_kin_lead_finder` 전담
- `review_intelligence` + `serp_features` → `place_scan_enrichment` (Place Sniper 후처리)

#### DB 테이블 (Phase 9-10)

| 테이블 | 용도 |
|--------|------|
| `community_mentions` | 커뮤니티 멘션 (블로그/카페/지식인) |
| `naver_ad_keyword_data` | 네이버 광고 키워드 상세 데이터 |
| `naver_ad_related_keywords` | 연관 키워드 |
| `keyword_trend_daily` | 일별 키워드 검색 트렌드 |
| `competitor_blog_activity` | 경쟁사 블로그 포스팅 추적 |
| `review_intelligence` | 경쟁사 리뷰 메타데이터 |
| `blog_rank_history` | 블로그 VIEW탭 순위 |
| `geo_grid_rankings` | 지오그리드 순위 |
| `competitor_changes` | 경쟁사 변경 감지 |
| `kakao_rank_history` | 카카오맵 순위 |
| `intelligence_reports` | 종합 인텔리전스 리포트 |
| `search_demographics` | 키워드별 연령/성별 분석 |
| `healthcare_news` | 의료 뉴스 모니터링 |
| `web_visibility` | 웹 검색 가시성 |
| `ad_competition_tracking` | 광고 경쟁 강도 추적 |
| `shop_trend_monitoring` | 쇼핑 트렌드 |
| `keyword_clusters` | 키워드 클러스터 분석 |
| `viral_conversion_patterns` | 바이럴 전환 패턴 |
| `serp_features` | SERP 기능 모니터링 |
| `review_nlp_analysis` | 리뷰 NLP 분석 (Gemini) |
| `smartplace_stats` | 스마트플레이스 통계 (CSV 임포트) |
| `call_tracking` | 전화 추적 (CSV 임포트) |
| `hira_clinics` | HIRA 의료기관 데이터 |
| `medical_platform_reviews` | 의료 리뷰 플랫폼 |
| `commercial_district_data` | 소상공인 상권 데이터 |

#### API 엔드포인트

**라우터**: `backend/routers/data_intelligence.py` → `/api/data-intelligence/`

16개 엔드포인트: smartplace, reviews, blog, hira, medical-reviews, competitor-changes, kakao, call-tracking, commercial, geo-grid, naver-ads, community, dashboard 등

#### 프론트엔드

- `frontend/src/services/api/dataIntelligence.ts` - Data Intelligence API 클라이언트
- `frontend/src/services/api/index.ts` - `dataIntelligenceApi` export 추가

#### Chronos Timeline (27개 활성 작업)

```
03:00 🌌 Pathfinder        05:00 👤 Demographics     06:00 📈 Trends
06:30 📰 News              07:30 🔔 Changes          08:00 🛡️ Sentinel
08:30 💬 Community(API)    09:00 📍 Place Sniper     09:30 🎯 Kin Leads
10:00 📝 Blog Rank         10:15 🌐 Web Visibility   10:30 📊 Briefing
11:00 💰 Ad Keywords+Comp  11:30 📝 Comp Blogs       12:00 🎖️ Ambassador
14:00 ☕ Cafe Swarm        14:30 🎯 Viral Hunter     15:00 🥕 Carrot Farm
16:00 📸 Instagram         18:30 📺 YouTube          19:00 🛒 Shop Trends
21:00 👁️ Place Watch       21:30 🎵 TikTok           21:45 🧪 Review NLP
22:00 🧠 Intelligence      23:00 💊 Health Check
```

#### 텔레그램 알림 수정

`alert_bot.py`에 Markdown 파싱 실패 시 plain text 폴백 추가.

#### 비활성 기능 사유 (schedule.json `disabled_reason`)

| 기능 | 사유 |
|------|------|
| `kakao_map` | Kakao REST API 키 만료 |
| `geo_grid` | Naver Local API 위치 기반 미지원 |
| `hira_update` / `commercial_data` | data.go.kr API 키 미발급 |
| `medical_reviews` | 모두닥/굿닥 URL 404 |
| `serp_features` | 네이버 캡차 차단 → Selenium 전용 |
| `review_intel` | GraphQL 차단 → place_scan_enrichment 대체 |
| `keyword_clusters` | 테마 기반 분리로 개선 완료 (1→11 클러스터) |
| `viral_conversion` | source_target_id 미연결 (리드 시스템 연동 필요) |

---

## 최근 개선 사항 (2026-03-02)

### 1. mentions 테이블 스키마 수정

**파일**: `backend/services/db_init.py`

**문제**: `viral.py`의 `_create_lead_from_viral` 함수에서 mentions 테이블에 없는 컬럼들을 사용하여 `sqlite3.OperationalError: table mentions has no column named platform` 오류 발생

**해결**: db_init.py에 누락된 컬럼 자동 추가 코드 추가

| 컬럼명 | 타입 | 용도 |
|--------|------|------|
| `platform` | TEXT | 플랫폼 (youtube, tiktok, naver 등) |
| `summary` | TEXT | 콘텐츠 요약 |
| `author` | TEXT | 작성자 |
| `category` | TEXT | 카테고리 |
| `source_module` | TEXT | 소스 모듈 (viral_hunter 등) |
| `created_at` | TIMESTAMP | 생성일시 |

### 2. Google Generative AI 패키지 마이그레이션

**문제**: `google.generativeai` 패키지가 deprecated 되어 경고 발생

**해결**: `google.genai` 신규 API로 마이그레이션

| 파일 | 변경 내용 |
|------|----------|
| `viral_hunter.py` | `google.generativeai` → `google.genai` |
| `backend/routers/competitors.py` | `google.generativeai` → `google.genai` |
| `backend/routers/pathfinder.py` | `google.generativeai` → `google.genai` |

**구 API vs 신 API 비교**:

```python
# 구 API (deprecated)
import google.generativeai as genai
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-3-flash-preview')
response = model.generate_content(prompt)

# 신 API (현재 사용)
from google import genai
from google.genai import types
client = genai.Client(api_key=api_key)
response = client.models.generate_content(
    model='gemini-3-flash-preview',
    contents=prompt,
    config=types.GenerateContentConfig(temperature=0.7)
)
```

---

## 최근 개선 사항 (2026-03-01)

### Phase 8: 시스템 안정성 및 효율성 개선

코드베이스 전체 분석을 통해 보안, 안정성, 코드 품질을 개선했습니다.

#### 1. API 키 기반 인증 미들웨어 (Critical)

**파일**: `backend/middleware/auth.py` (신규)

민감 엔드포인트에 대한 API 키 인증 추가:

```python
# 보호된 엔드포인트
PROTECTED_PATHS = [
    "/api/export",
    "/api/backup",
    "/api/automation",
    "/api/scheduler",
    "/api/migration",
    "/api/preferences",
]

# 사용법: X-API-Key 헤더로 인증
curl -H "X-API-Key: your-api-key" http://localhost:8000/api/export/keywords

# 환경변수로 API 키 설정
export MARKETING_BOT_API_KEY=your-secure-api-key

# 개발 시 인증 비활성화
export DISABLE_API_AUTH=true
```

#### 2. SQL Injection 취약점 제거 (Critical)

**파일**: `backend/routers/pathfinder.py`

```python
# Before: 취약한 문자열 삽입
date_filter = f"AND created_at >= datetime('now', '-{days} days')"

# After: 파라미터 바인딩
async def get_pathfinder_stats(
    days: Optional[int] = Query(None, ge=1, le=365, description="조회 기간")
):
    if days:
        where_conditions.append("created_at >= datetime('now', ?)")
        params.append(f"-{days} days")
```

#### 3. Subprocess 모니터링 및 Zombie 방지 (Critical)

**파일**: `backend/routers/hud.py`

```python
# Pathfinder 모듈에 cleanup 스레드 추가
def cleanup_pathfinder(proc, mod_name):
    try:
        # 타임아웃 30분
        proc.wait(timeout=1800)
    except subprocess.TimeoutExpired:
        logger.warning(f"프로세스 타임아웃 ({mod_name}), 강제 종료")
        proc.kill()
        proc.wait()
    finally:
        with running_processes_lock:
            if mod_name in running_processes:
                del running_processes[mod_name]

threading.Thread(target=cleanup_pathfinder, args=(process, module_name), daemon=True).start()
```

#### 4. LIMIT/OFFSET Query 검증 (High)

**파일**: `automation.py`, `hud.py`, `notifications.py`

```python
# Before: 제한 없는 limit
async def get_priority_queue(limit: int = 20):

# After: 최대값 검증
async def get_priority_queue(
    limit: int = Query(default=20, ge=1, le=100, description="조회할 리드 수")
):
```

#### 5. TypeScript any 타입 제거 (High)

**파일**: `frontend/src/components/pathfinder/KeywordAnalysisTab.tsx`

```typescript
// Before
interface KeywordAnalysisTabProps {
  stats: any
}
const icons: any = { S: '🔥', A: '🟢', B: '🔵', C: '⚪' }

// After
import type { Keyword, PathfinderStats } from '@/types'
import { GRADE_ICONS, GRADE_COLORS, TREND_ICONS } from '@/types'

interface KeywordAnalysisTabProps {
  stats: PathfinderStats | null
}
```

#### 6. 설정 파일 로드 중앙화 (Medium)

**파일**: `backend/setup_paths.py`

```python
# 새로 추가된 헬퍼 함수
from setup_paths import get_api_key, load_config, get_config_path

# API 키 조회
api_key = get_api_key('gemini')

# 설정 파일 로드 (캐싱 지원)
config = load_config('config.json')

# 캐시 클리어 (설정 파일 수정 후)
clear_config_cache()
```

#### 7. 긴 함수 분해 (Medium)

**파일**: `backend/routers/leads.py`

Q&A 매칭 로직을 헬퍼 함수로 분리:

```python
def _find_qa_matches(cursor, lead_text: str, max_matches: int = 3) -> List[Dict[str, Any]]:
    """Q&A 매칭 헬퍼 함수"""
    # 251줄 generate_ai_response에서 분리
```

#### 수정된 파일 목록

| 파일 | 내용 |
|------|------|
| `middleware/auth.py` | 신규 - API 키 인증 미들웨어 |
| `middleware/__init__.py` | auth 모듈 export 추가 |
| `main.py` | APIKeyMiddleware 등록, CORS 헤더에 X-API-Key 추가 |
| `routers/pathfinder.py` | SQL Injection 제거 (파라미터 바인딩) |
| `routers/hud.py` | Subprocess 모니터링, LIMIT Query 검증 |
| `routers/automation.py` | LIMIT Query 검증 |
| `routers/notifications.py` | LIMIT Query 검증 |
| `routers/leads.py` | 설정 중앙화, 함수 분해 |
| `setup_paths.py` | `load_config()`, `get_api_key()` 헬퍼 추가 |
| `KeywordAnalysisTab.tsx` | any 타입 → Keyword/PathfinderStats 타입 |

---

## 최근 개선 사항 (2026-02-28)

### 종합 성능 및 안정성 개선

코드베이스 전체 분석을 통해 Critical/High 이슈 27건을 수정했습니다.

#### 1. DB 연결 누수 수정 (Critical)

**파일**: instagram.py, export.py, qa.py 등 16개 파일

```python
# Before: 예외 발생 시 연결 누수
conn = sqlite3.connect(db_path)
cursor.execute(...)
conn.close()  # 예외 발생 시 실행 안 됨

# After: try-finally 패턴
conn = None
try:
    conn = sqlite3.connect(db_path)
    cursor.execute(...)
finally:
    if conn:
        conn.close()
```

#### 2. bare except → except Exception (Critical)

**파일**: 17+ 파일 (pathfinder.py, viral_hunter.py, ai_keyword_enhancer.py 등)

```python
# Before: SystemExit, KeyboardInterrupt도 잡힘
except:
    pass

# After: 시스템 시그널 정상 처리
except Exception:
    pass
```

#### 3. Threading Locks 추가 (Critical)

**파일**: hud.py, viral.py

```python
# hud.py - 전역 상태 보호
running_processes: Dict[str, subprocess.Popen] = {}
running_processes_lock = threading.Lock()

scan_progress: Dict[str, Dict[str, Any]] = {}
scan_progress_lock = threading.Lock()

# viral.py - 캐시 보호
_verification_cache: Dict[str, Dict[str, Any]] = {}
_verification_cache_lock = threading.Lock()
```

#### 4. N+1 쿼리 수정 (Critical)

**파일**: leads.py

```python
# Before: 개별 UPDATE 반복 (N회)
for lead_id in lead_ids:
    cursor.execute("UPDATE ... WHERE id = ?", [lead_id])

# After: 배치 UPDATE (1회)
placeholders = ','.join('?' * len(lead_ids))
cursor.execute(f"UPDATE ... WHERE id IN ({placeholders})", lead_ids)
```

#### 5. Export API 스트리밍 (High)

**파일**: export.py (6개 엔드포인트)

```python
# Before: 전체 메모리 로드
rows = cursor.fetchall()
csv_content = _generate_csv([dict(row) for row in rows], columns)

# After: 배치 스트리밍 (1000행씩)
def _generate_csv_streaming(conn, cursor, columns):
    while True:
        rows = cursor.fetchmany(STREAMING_BATCH_SIZE)
        if not rows:
            break
        yield csv_chunk

return StreamingResponse(_generate_csv_streaming(conn, cursor, columns), ...)
```

#### 6. React 메모이제이션 (High)

**파일**: Dashboard.tsx

| 최적화 | 내용 |
|--------|------|
| `formatTime` | `useCallback`으로 메모이제이션 |
| `GOAL_TYPE_LABELS`, `GOAL_TYPE_ICONS` | 컴포넌트 외부 상수로 이동 |
| 네비게이션 핸들러 | `useCallback`으로 메모이제이션 |

#### 수정된 파일 목록

| 카테고리 | 파일 |
|----------|------|
| DB 연결 | instagram.py, export.py, qa.py, hud.py, viral.py |
| bare except | pathfinder.py, pathfinder_ultra.py, viral_hunter_enhanced.py, ai_keyword_enhancer.py, ambassador_v2.py, carrot_farmer.py, api_tracker.py, alert_bot.py, competitor_discovery.py, ai_orchestrator.py, librarian.py, core/knowledge_base.py, core/analytics.py, keyword_discovery/*.py, monitor_pathfinder.py |
| Thread Safety | hud.py, viral.py |
| N+1 쿼리 | leads.py |
| 스트리밍 | export.py |
| React | Dashboard.tsx |

---

## 최근 개선 사항 (2026-02-27)

### 병렬 스캔 DB 연결 오류 수정

**파일**: `scrapers/scraper_naver_place.py`

**문제**: 병렬 스캔 시 `sqlite3.ProgrammingError: Cannot operate on a closed database` 오류 발생

**원인**:
- `DatabaseManager`가 **싱글톤 패턴**으로 구현되어 애플리케이션 전체에서 하나의 인스턴스만 존재
- `_scan_single_keyword()` 함수 끝에서 `db.conn.close()` 호출
- 병렬 실행 시 한 스레드가 연결을 닫으면 다른 스레드들이 닫힌 연결 사용 시도 → 오류

**수정 내용**:

| 위치 | 변경 |
|------|------|
| Line 416 | `db.conn.close()` 제거 (`_scan_single_keyword` 함수) |
| Line 1370 | `db.conn.close()` 제거 (`scrape_competitor_reviews` 함수) |

**핵심 원칙**: 싱글톤 DB 연결은 개별 함수에서 닫지 않음. 연결 관리는 `DatabaseManager` 클래스가 담당.

---

## 최근 개선 사항 (2026-02-26)

### 프론트엔드 성능 최적화

#### 1. Dashboard 병렬 로드 최적화

**파일**: `frontend/src/pages/Dashboard.tsx`

| 변경 | 내용 |
|------|------|
| 쿼리 병렬화 | `enabled: !metricsLoading` 조건 제거 → 4개 쿼리 동시 실행 |
| refetchInterval 조정 | 60초 → 120초 (서버 부하 감소) |

**예상 효과**: 대시보드 로딩 시간 30% 단축

#### 2. React.memo 적용

| 컴포넌트 | 비교 함수 |
|----------|----------|
| `LeadTable.tsx` | leads, viewMode, initialPageSize |
| `KeywordTable.tsx` | keywords, showCategory, showActions |
| `MetricCard.tsx` | 기본 shallow 비교 |
| `LeadCard.tsx` | lead.id, lead.status, isFocused |
| `ViralTargetCard.tsx` | target.id, target.generated_comment, isGenerating |

#### 3. Vite 빌드 압축 플러그인

**파일**: `frontend/vite.config.ts`, `frontend/package.json`

```typescript
// vite.config.ts
import compression from 'vite-plugin-compression'

plugins: [
  compression({ algorithm: 'gzip', ext: '.gz' }),
  compression({ algorithm: 'brotliCompress', ext: '.br' }),
]
```

**예상 효과**: 번들 크기 50-70% 감소

#### 4. React Query 프리페칭

**파일**: `frontend/src/hooks/usePrefetch.ts`, `frontend/src/components/Layout.tsx`

- 사이드바 메뉴 hover 시 100ms 딜레이 후 데이터 미리 로드
- 페이지 전환 시 즉각적인 렌더링

| 페이지 | 프리페칭 데이터 |
|--------|----------------|
| `/pathfinder` | 키워드 목록, 통계 |
| `/battle` | 랭킹 키워드, 트렌드 |
| `/viral` | 통계, 스캔 배치 |
| `/leads` | 리드 목록, 긴급 알림 |
| `/competitors` | 약점 분석, 경쟁사 목록 |

#### 5. 기타 UI 개선

| 파일 | 내용 |
|------|------|
| `BatchProgressIndicator.tsx` | 신규 - 배치 작업 진행률 표시 |
| `OfflineBanner.tsx` | 자동 새로고침 기능 추가 |

---

## 최근 개선 사항 (2026-02-23)

### 안정성 및 속도 개선 Phase 2

**제안서**: `STABILITY_IMPROVEMENT_PROPOSAL_V2.md`

#### 🔴 CRITICAL 수정 완료

| 파일 | 수정 내용 |
|------|----------|
| `scrapers/instagram_reels_analyzer.py` | DB 연결 누수 수정 - `try/finally` 패턴 적용 |
| `db/recover_data.py` | `try/finally` 추가 - 예외 시에도 연결 닫힘 보장 |
| `backend/services/event_bus.py` | `asyncio.run()` 블로킹 제거 - 백그라운드 스레드 큐 사용 |

#### 🟠 HIGH 수정 완료

| 파일 | 수정 내용 |
|------|----------|
| `viral_hunter.py` | Bare `except:` → `except Exception:` 변경 (3개소) |
| `pathfinder_v3_legion.py` | Bare `except:` → `except Exception:` 변경 (핵심 6개소) |
| `backend/services/comment_verifier.py` | 비동기 래퍼 추가 (`verify_url_async`, `verify_batch_async`) |
| `backend/routers/viral.py` | 비동기 검증 함수 사용으로 서버 블로킹 방지 |
| `backend/routers/pathfinder.py` | `asyncio.create_subprocess_exec()` 사용 |

#### 새로 추가된 함수/클래스

**`backend/services/event_bus.py`:**
```python
class EventBus:
    def _start_sync_processor(self)  # 백그라운드 스레드로 동기 이벤트 처리
    def shutdown(self)               # 서버 종료 시 정리
```

**`backend/services/comment_verifier.py`:**
```python
async def verify_url_async(url, platform)       # 비동기 단일 URL 검증
async def verify_batch_async(targets, max_concurrent=3)  # 비동기 일괄 검증
def shutdown_verifier_pool()                     # 스레드 풀 정리
```

#### 주요 패턴 변경

**DB 연결 관리 (모든 새 코드에 적용):**
```python
conn = None
try:
    conn = sqlite3.connect(db_path)
    # 작업 수행
finally:
    if conn:
        conn.close()
```

**동기 컨텍스트에서 async 함수 호출 (EventBus):**
```python
# Before: asyncio.run() - 블로킹!
asyncio.run(self.publish(event))

# After: 큐 기반 백그라운드 처리 - Non-blocking
self._sync_queue.put(event)  # 백그라운드 스레드가 처리
```

**Selenium 검증 비동기화 (viral.py):**
```python
# Before: 동기 호출 - 서버 블로킹
with CommentVerifier() as verifier:
    result = verifier.verify_url(url, platform)

# After: 비동기 래퍼 - Non-blocking
result = await verify_url_async(url, platform)
```

---

## 최근 개선 사항 (2026-02-22)

### [Phase 3] 스크래퍼 병렬화 구현

**파일**: `/mnt/c/Projects/marketing_bot/scrapers/scraper_naver_place.py`

**구현 내용:**

| 구성 요소 | 설명 |
|-----------|------|
| `BrowserPool` 클래스 | 스레드 안전한 브라우저 인스턴스 풀 관리 |
| `_scan_single_keyword()` | 단일 키워드 스캔 (병렬 실행용, 독립 DB 연결) |
| `_scan_keywords_parallel()` | ThreadPoolExecutor로 병렬 실행 |
| `check_naver_place_rank(parallel=True)` | 병렬/순차 모드 선택 가능 |

**사용법:**
```bash
# 기본: 병렬 모드 (3개 브라우저)
python scrapers/scraper_naver_place.py

# 5개 브라우저로 병렬 실행
python scrapers/scraper_naver_place.py -w 5

# 순차 모드 (기존 방식)
python scrapers/scraper_naver_place.py --sequential
```

**예상 효과:**
- 스캔 시간: 2-3분 → 30-40초 (5배 단축)
- 네이버 차단 방지: 작업 시작 간 2초 딜레이

**주의사항:**
- 브라우저 수를 너무 많이 늘리면 네이버 차단 리스크 증가
- SQLite 스레드 안전성을 위해 각 스레드에서 독립적으로 DB 연결 생성

---

## 최근 개선 사항 (2026-02-19)

### 네이버 플레이스 데스크탑 스크래핑 재수정

**이전 문제점 (2026-02-12 수정 후에도 발생)**
- 페이지네이션 로직이 stale element 오류 유발
- Apollo State 접근 시 iframe 전환 순서 오류
- 업체명이 빈 문자열로 추출됨

**최종 해결 (2026-02-19)**

| 수정 | 내용 |
|------|------|
| 페이지네이션 제거 | 스크롤 기반으로 단순화 (stale element 방지) |
| extracted_places 순서 | Apollo State 전환 **전에** DOM에서 업체명 추출 |
| 광고 감지 | "광고" 텍스트 포함 여부로 판단, 순위에서 제외 |

**스크롤 로직 개선 (2026-02-20 추가 수정)**

| 문제 | 해결 |
|------|------|
| 스크롤이 3회에서 조기 종료 | 최소 10회 스크롤 강제 |
| 한 번에 끝까지 스크롤 | 점진적 스크롤 (800px씩) |
| 52개에서 멈춤 | 82개 이상 로드 가능 |
| 모바일/데스크탑 순위 불일치 | 완전 일치 확인 |

**현재 로직 (scraper_naver_place.py)**
```python
# 1. iframe 전환
driver.switch_to.frame(iframe)

# 2. 점진적 스크롤로 항목 로드 (최소 10회, 최대 50회)
for scroll_attempt in range(50):
    # 점진적 스크롤 (한 번에 800px씩)
    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollTop + 800;", scroll_container)
    time.sleep(0.5)

    # 최소 10회까지는 계속 진행
    if scroll_attempt < 10:
        continue

    # 끝 도달 판정: scrollTop + clientHeight >= scrollHeight
    at_bottom = (new_scroll + viewport_height >= new_height - 10)

# 3. 텍스트 기반 항목 수집 (한의원/병원/약국 등 포함)
for li in driver.find_elements(By.TAG_NAME, "li"):
    if ("km" in text or "m " in text) and ("진료" in text or "영업" in text):
        place_items.append(li)

# 4. DOM에서 업체명 추출 (iframe 전환 전에 완료!)
for item in place_items:
    place_name, is_ad = _extract_place_name(item)
    extracted_places.append((place_name, is_ad, idx))

# 5. Apollo State 파싱 (항목이 적으면 시도)
driver.switch_to.default_content()  # 메인 프레임으로 전환
apollo_state = driver.execute_script("return window.__APOLLO_STATE__ || null;")
```

**전체 스캔 결과 (2026-02-20) - 16/17 성공 (94%)**

| 키워드 | 모바일 | 데스크탑 | 일치 |
|--------|:------:|:--------:|:----:|
| 청주 한의원 | 20위 | 20위 | ✅ |
| 청주 다이어트 한약 | 11위 | 11위 | ✅ |
| 청주 다이어트 한의원 | 37위 | 37위 | ✅ |
| 청주 교통사고 한의원 | 23위 | 23위 | ✅ |
| 청주 교통사고 병원 | 31위 | 31위 | ✅ |
| 청주 성안길 한의원 | 1위 | 1위 | ✅ |
| 청주 상당구 한의원 | 4위 | 4위 | ✅ |
| 청주 시내 한의원 | - | - | 결과 1개뿐 |

> **결론**: 스크롤 수정 후 모바일/데스크탑 순위가 **완전 일치**함. 이전에 순위 차이가 나던 것은 스크롤 조기 종료로 인한 파싱 실패였음.

### API 타입 오류 수정
- `viral.py`: `target_action` 반환 타입 `Dict[str, str]` → `Dict[str, Any]` (lead_created boolean 처리)

---

## 최근 개선 사항 (2026-02-17)

### Settings.tsx 컴포넌트 분리 리팩토링
- ✅ **2,272줄 → ~200줄** (91% 감소)
- ✅ 8개 탭 컴포넌트로 분리:

| 컴포넌트 | 파일명 | 줄수 | 기능 |
|---------|--------|------|------|
| BackupTab | `BackupTab.tsx` | ~240 | DB 백업/복원, 무결성 검사, VACUUM |
| SystemTab | `SystemTab.tsx` | ~280 | 시스템 상태, 진단, DB 마이그레이션 |
| AutomationTab | `AutomationTab.tsx` | ~350 | 리드 분류, 바이럴 추천, 경쟁사 모니터링 |
| KeywordsTab | `KeywordsTab.tsx` | ~300 | keywords.json 편집 (naver_place/blog_seo) |
| QATab | `QATab.tsx` | ~330 | Q&A Repository CRUD |
| NotificationsTab | `NotificationsTab.tsx` | ~90 | 브라우저 알림 권한 관리 |
| IntegrationsTab | `IntegrationsTab.tsx` | ~150 | API 연동 상태 (Instagram 등) |
| ExternalNotificationsTab | `ExternalNotificationsTab.tsx` | ~540 | 텔레그램/카카오톡 알림 설정 |

- ✅ 경로: `frontend/src/components/settings/`
- ✅ 통합 export: `index.ts`

### TypeScript 타입 정합성 수정
- ✅ `AutomationTab`: 로컬 인터페이스 제거, `@/services/api/automation` 타입 사용
- ✅ `ExternalNotificationsTab`: `NotificationHistory` 타입 API에서 import
- ✅ `KeywordsTab`: `KeywordsData` 타입 `@/services/api/base`에서 import
- ✅ `AIInsights.tsx`, `PerformanceFeedback.tsx`: 미사용 import(`RefreshCw`) 제거

### 빌드 검증
- ✅ TypeScript 컴파일 성공 (`tsc --noEmit`)
- ⚠️ Vite/Rollup 빌드: WSL↔Windows 환경 이슈 (`@rollup/rollup-linux-x64-gnu` 모듈 경고, 실행에는 문제 없음)

---

## 개선 사항 (2026-02-12)

### 네이버 플레이스 데스크탑 스크래핑 초기 구현

**문제 상황**
- ✅ 모바일 스크래핑 (`m.place.naver.com`): 정상 작동
- ❌ 데스크탑 스크래핑 (`map.naver.com`): 파싱 실패

**초기 해결 (2026-02-12)**
1. iframe 전환 (`#searchIframe`)
2. 스크롤 컨테이너 스크롤
3. Apollo State JSON 파싱 시도

> ⚠️ **주의**: 이 버전에는 페이지네이션 로직이 있었으나, stale element 오류가 발생하여 2026-02-19에 스크롤 기반으로 단순화됨. 최신 로직은 상단 2026-02-19 섹션 참조.

---

## 최근 개선 사항 (2026-02-11)

### ViralHunter.tsx 뷰 컴포넌트 분리
- ✅ **1,926줄 → 826줄** (57% 감소)
- ✅ 4개 뷰 컴포넌트로 분리:
  - `HomeView.tsx` (465줄): 홈 화면, 통계, 스캔 설정, 검증
  - `WorkView.tsx` (411줄): 아코디언 방식 개별 타겟 처리
  - `ListView.tsx` (521줄): 테이블 형식 전체 관리, 대량 처리
  - `CompletionView.tsx` (79줄): 카테고리 작업 완료 화면
- ✅ 경로: `frontend/src/components/viral/views/`

### API 클라이언트 도메인 분리
- ✅ **api.ts 2,260줄 → 도메인별 15개 모듈로 분리**
- ✅ 경로: `frontend/src/services/api/`
  - `base.ts`: 공통 설정 (axios instance, 타입)
  - `hud.ts`, `viral.ts`, `pathfinder.ts`, `leads.ts`
  - `battle.ts`, `competitors.ts`, `qa.ts`, `settings.ts`
  - `export.ts`, `reviews.ts`, `analytics.ts`, `websocket.ts`
  - `index.ts`: 통합 재내보내기
- ✅ 하위 호환성 유지: 기존 `import { viralApi } from '@/services/api'` 동작

---

## 개선 사항 (2026-02-09)

### Phase 5.0 구현 완료
- ✅ **LeadScorer 확장**: `opportunity_bonus` 필드 추가 (질문형/신선도/댓글수 기반)
- ✅ **TrustScorer 확장**: `engagement_signal` 필드 추가 (seeking_info/ready_to_act/passive)
- ✅ **Q&A Repository**: `/api/qa/*` API 및 테이블 구현
- ✅ **Comment Templates 고도화**: situation_type, engagement_signal 필터링

### Phase 6.1 DB 초기화 시스템
- ✅ `services/db_init.py` - 앱 시작 시 스키마 초기화 (매 요청마다 확인 X)
- ✅ 모든 테이블 및 컬럼 자동 생성/마이그레이션

### 폴더 구조 변경 (중요!)
- ✅ `backend/utils/` → `backend/backend_utils/` 이름 변경
  - **이유**: 프로젝트 루트의 `utils.py`와 Python import 충돌
  - **영향**: 11개 파일의 import 경로 수정됨

### API 응답 구조 수정
- ✅ Pathfinder 히스토리 탭: `scanHistory.runs` 접근 방식 수정
- ✅ Lead Manager 중복 탭: `success_response()` 래핑 데이터 추출 수정

### 데이터베이스 및 API 개선 (2026-02-07)
- ✅ `instagram_competitors` 테이블 생성
- ✅ HUD API 에러 처리 개선 (200 → 500 반환)
- ✅ Dashboard 에러 상태 UI 추가
- ✅ LeadManager 상태 필터 UI 구현
- ✅ `volume`/`search_volume` 컬럼 중복 정리
  - `search_volume`: 검색량 (표준)
  - `document_count`: 블로그 문서 수
  - `volume`: 레거시 (사용하지 않음)

### 설정 파일 분리
- ✅ `config/schedule.json`: Chronos Timeline 스케줄 설정
  - 각 모듈의 실행 시간, 이름, 아이콘, 명령어 정의
  - `enabled: false`로 특정 모듈 비활성화 가능

### Battle Intelligence
- ✅ 순위 상태 분류 개선 (scanned/not_found/error/pending)
- ✅ competitor-vitals API: competitor_reviews 테이블 사용
- ✅ RankingKeywordsList: 상태별 스타일 및 안내 메시지

### Competitor Analysis
- ✅ analyze-reviews API: Gemini AI 기반 약점 분석
- ✅ 약점 유형별 분류 (서비스, 가격, 시설, 대기시간, 효과)
- ✅ 기회 키워드 자동 생성

### Settings 페이지
- ✅ Hollow features 제거 ("곧 추가됩니다", "준비 중..." 제거)
- ✅ 실제 유용한 시스템 정보 표시

### Gemini 모델 통일
- ✅ vision_analyst.py 폴백 모델 수정
- ✅ 모든 Gemini 사용처에서 gemini-3-flash-preview 사용 확인

### 데이터베이스 백업 시스템 (신규)
- ✅ `/api/backup/*` API 라우터 추가 (상태조회, 수동백업, 무결성검사, VACUUM)
- ✅ Settings 페이지에 백업 관리 UI 추가
  - 마지막 백업 일자 및 경고 레벨 표시 (7일 이상: critical, 3일 이상: warning)
  - 수동 백업, 무결성 검사, DB 최적화 버튼
  - 최근 백업 목록 표시
- ✅ `setup_backup_scheduler.bat` - Windows Task Scheduler 자동 백업 설정 스크립트

### UI/UX 개선
- ✅ 사이드바 메뉴 순서 변경: Viral Hunter를 Pathfinder 바로 아래로 이동
- ✅ ConfirmModal 통합: window.confirm → ConfirmModal 컴포넌트 사용
  - ViralHunter.tsx: 대량 작업 확인 모달
  - CompetitorList.tsx: 경쟁사 삭제 확인 모달
- ✅ 모바일 반응형 개선: grid-cols-2 md:grid-cols-4 패턴 적용
- ✅ Modal 컴포넌트 리팩토링: AddKeywordModal, EditKeywordModal
- ✅ EmptyState 컴포넌트 통일: RankingKeywordsList, LeadTable
- ✅ 접근성(a11y) 개선
  - focus:ring 스타일 추가 (버튼, 입력 필드)
  - aria 속성 추가 (aria-label, aria-expanded, aria-controls, aria-pressed)
  - focus-visible:ring 최적화 (키보드 전용 포커스)
- ✅ 에러 UI 컴포넌트 추가: ErrorIcon, WarningIcon, FormErrorMessage

---

## 알려진 이슈 및 TODO

### 해결 완료
- [x] **네이버 플레이스 데스크탑 스크래핑 완전 해결** (2026-02-20)
  - 점진적 스크롤 (800px씩) + 최소 10회 스크롤 강제
  - 전체 스캔 성공률: 16/17 (94%)
  - 모바일/데스크탑 순위 완전 일치 확인
- [x] **네이버 플레이스 데스크탑 스크래핑 재수정** (2026-02-19)
  - 페이지네이션 제거 → 스크롤 기반으로 단순화
  - extracted_places 추출 순서 수정 (iframe 전환 전에 완료)
- [x] **Settings.tsx 컴포넌트 분리** (2026-02-17)
  - 2,272줄 → ~200줄 (91% 감소), 8개 탭 컴포넌트로 분리
  - 경로: `frontend/src/components/settings/`
- [x] **네이버 플레이스 데스크탑 스크래핑 초기 구현** (2026-02-12)
  - iframe 전환, 스크롤, Apollo State JSON 파싱 구현
- [x] Instagram 스캔 모듈: `scrapers/scraper_instagram.py` 존재 (Graph API + Google 폴백)
- [x] `instagram_competitors` 테이블 생성됨
- [x] Pathfinder 히스토리 탭 크래시 수정 (API 응답 구조)
- [x] Lead Manager 중복 탭 크래시 수정 (success_response 래핑)
- [x] `backend/utils` → `backend_utils` 충돌 해결

### 주의사항
- 플레이스 순위가 없는 키워드는 `blog_seo` 카테고리로 분리
- Battle Intelligence에서 "순위권 밖" 키워드 삭제 시 keywords.json도 함께 수정됨
- `volume` 컬럼은 레거시 - 새 코드에서는 `search_volume`, `document_count` 사용
- **import 경로**: `from backend_utils.xxx` 사용 (`from utils.xxx` 아님!)
- **API 응답**: `success_response()` 사용 시 실제 데이터는 `.data` 속성에 있음
- **데스크탑 vs 모바일 순위**: 스크롤 수정 후 완전 일치 확인됨 (2026-02-20). 순위 차이가 나면 스크래핑 오류일 가능성 높음
- **Apollo State 활용**: 네이버 플레이스 데스크탑 스크래핑 시 DOM보다 Apollo State에 더 많은 항목이 있으면 Apollo State 사용
- **스크래핑 실행**: 웹 서버에서 스캔 시 `scrapers/scraper_naver_place.py`를 subprocess로 호출하므로 파일 수정 후 즉시 적용됨 (서버 재시작 불필요)

---

## 중요: 데이터베이스 작업 규칙

### 1. DB 파일 수정/복사/이동 전 필수 백업

**절대 규칙: DB 파일을 수정, 복사, 이동, 덮어쓰기 전에 반드시 백업을 먼저 생성할 것**

```bash
# 백업 명령어 (반드시 실행)
cp /mnt/c/projects/marketing_bot/db/marketing_data.db \
   /mnt/c/projects/marketing_bot/db/backups/marketing_data.db.backup_$(date +%Y%m%d_%H%M%S)
```

### 2. DB 복사/동기화 시 주의사항

- **WSL DB → Windows DB 복사 금지**: 데이터 손실 위험
- 동기화가 필요한 경우 **병합(merge)** 방식 사용
- 복사 전 양쪽 DB의 데이터 개수 확인 필수

```bash
# 복사 전 확인 명령어
echo "=== 원본 DB ===" && sqlite3 원본.db "SELECT COUNT(*) FROM viral_targets"
echo "=== 대상 DB ===" && sqlite3 대상.db "SELECT COUNT(*) FROM viral_targets"
```

### 3. 백업 및 안전 스크립트

**수동 백업:**
```bash
/mnt/c/projects/marketing_bot/scripts/backup_db.sh [설명]
# 예: ./backup_db.sh "before_schema_change"
```

**Python 백업 스크립트:**
```bash
python db_backup.py
# SQLite Backup API 사용, 무결성 검사 포함
```

**안전한 DB 복사 (cp 대신 사용):**
```bash
/mnt/c/projects/marketing_bot/scripts/safe_db_copy.sh <원본> <대상>
# 자동으로 데이터 개수 비교, 경고, 백업 생성
```

**⛔ 절대 금지:**
```bash
# 이렇게 하지 말 것!
cp source.db target.db  # 직접 복사 금지
```

### 4. 자동 백업 설정 (권장)

**Windows Task Scheduler 등록:**
```cmd
# 관리자 권한으로 실행
setup_backup_scheduler.bat
```
- 매일 오전 2시에 자동 백업 실행
- 7일치 백업 보관

**웹 UI에서 백업 관리:**
- Settings 페이지 (http://localhost:8000/settings)
- 마지막 백업 상태 확인
- 수동 백업, 무결성 검사, DB 최적화 가능

### 4. 백업 보관 정책

- 위치: `/mnt/c/projects/marketing_bot/db/backups/`
- 보관 기간: 최근 30개 백업 유지
- 명명 규칙: `marketing_data.db.backup_YYYYMMDD_HHMMSS`

---

## 개발 규칙

### 코드 수정 전 확인사항
1. 영향받는 파일 목록 파악
2. 테스트 방법 확인
3. 롤백 방법 준비

### 커밋 전 확인사항
1. TypeScript 컴파일 오류 없음
2. 기존 기능 정상 동작
3. DB 스키마 변경 시 마이그레이션 스크립트 준비

### UI 개발 원칙
- **허울 뿐인 기능 금지**: "준비 중...", "곧 추가됩니다" 같은 placeholder 사용 금지
- 기능이 없으면 UI 요소 자체를 표시하지 않거나 실제 구현
- 에러 처리: API 호출 실패 시 사용자에게 명확한 메시지 표시

---

## 사고 이력 및 교훈

### 2026-02-06: DB 덮어쓰기로 인한 데이터 손실
- **원인**: WSL DB를 Windows DB로 `cp` 명령으로 복사하여 기존 데이터 덮어씀
- **손실**: 이전 스캔 데이터 전체
- **교훈**: DB 작업 전 반드시 백업 생성
- **방지책**: 이 문서의 규칙 및 backup_db.sh 스크립트 추가

---

## 새로운 대화에서 이어서 작업할 때

1. **이 파일(CLAUDE.md)을 먼저 읽기**
2. **현재 상태 확인**: `build_and_run.bat` 실행 후 웹 UI 확인
3. **DB 상태 확인**: 테이블별 데이터 개수 확인
4. **keywords.json 확인**: 플레이스/블로그 키워드 분리 상태

```bash
# DB 상태 빠른 확인
sqlite3 /mnt/c/projects/marketing_bot/db/marketing_data.db "
SELECT 'keyword_insights' as tbl, COUNT(*) FROM keyword_insights
UNION ALL SELECT 'rank_history', COUNT(*) FROM rank_history
UNION ALL SELECT 'competitor_reviews', COUNT(*) FROM competitor_reviews
UNION ALL SELECT 'viral_targets', COUNT(*) FROM viral_targets
UNION ALL SELECT 'qa_repository', COUNT(*) FROM qa_repository
UNION ALL SELECT 'scan_runs', COUNT(*) FROM scan_runs
UNION ALL SELECT 'auto_approval_rules', COUNT(*) FROM auto_approval_rules;
"
```

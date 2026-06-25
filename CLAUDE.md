# Claude Code 프로젝트 가이드라인

> 📌 상세 구현 이력은 `C:\Users\craza\.claude\projects\C--Projects-marketing-bot\memory\MEMORY.md` 참조

---

## ⚠️ 바이럴 댓글 핵심 운영 원칙 (USER DIRECTIVE — 확인 없이 변경 금지)

- 바이럴 댓글 = 실제로 한의원에 다녀온 **1인칭 환자 경험담 톤** ("저도 규림한의원 다녀왔는데 좋았어요")
- 풀네임 "규림한의원" 사용 = 의도된 투명성 정책 (변경 금지)
- 1인칭 방문/효과 경험담을 의료광고법 위반으로 제거하지 말 것
- `task="viral_comment"` → AI 공개 footer 없음, first-person 스트리핑 없음
- 댓글 톤·페르소나·네이밍은 사용자 소유 — 확인 없이 변경 금지

## ⚠️ Pathfinder/Viral Hunter 시스템 핵심 가드레일 (변경 금지)

- `_load_keyword_feedback` 시드-축 acceptance는 SEED 축으로 올바르게 측정됨 — "fix" 하지 말 것
- `SIGNATURE_ROUTING_AXES = {흉터/여드름흉터, 안면비대칭}` — 의도적으로 좁게 설정
- 교통사고 축은 전략적 판단(고LTV) 없이 자동 게이트 금지
- KIN은 provider-venue-author 게이트에서 의도적 제외 (author=질문자 닉네임)
- flat global lens prior 추가 금지 — 카테고리별 per-(axis,lens) 증거 사용
- 지역 매칭은 substring-only 금지 — `_has_active_region_anchor()` 유지
- `_normalize_transparency_terms` in viral_hunter 변경 금지 (naming normalization 의도)
- `competitors.json` 단일 소스 — 로랑/데이릴 포함 (직접 수정 시 prompts.json과 동기화 필요)
- 의미기반 발견은 `.env MARKETING_BOT_SEMANTIC_DISCOVERY=1`로 **프로덕션 ON**(2026-06-21, 실측 net-positive). 테스트는 `tests/conftest.py` autouse fixture로 격리(기본-off 계약 검증) — 이 격리 제거 금지. 끄려면 `.env` line만 삭제
- `SIGNATURE_BACKLOG_AXES`(viral_hunter)는 `routers/viral.py SIGNATURE_ROUTING_AXES`와 **동일 집합 유지**(수정 시 양쪽 동기화). 시그니처 백로그 레인(`--rescue-signature`)은 raw_backlog만 대상(이미 게이트 통과분) — 자동 승격 없음
- Q&A 적재(`scripts/seed_signature_qa.py`)는 DML이므로 **반드시 마이그레이션 스크립트로만**(백업+멱등). 적재 후 `QASearchEngine.index_all()` RAG 재인덱스 필수(안 하면 드래프터가 못 찾음)
- `viral_scan_audits.pending_count`/`summary.pending`은 과거 posted/generated/manual_review 포함 **actionable 누계**임 — 실제 열린 대기열은 `open_pending`, 신규 수율은 `fresh_pending`으로 판단. Pathfinder zero-yield/blind-spot 판정은 `fresh_discovered >= 25 && fresh_pending == 0` 기준 유지
- 중고거래/판매/양도 글은 의료 리드가 아님. `marketplace_sale` final reject reason(`팔아요/팝니다/직거래/네고/중고나라/번개장터`) 유지하고 generic `non_relevant`로 묻지 말 것

---

## 프로젝트 개요

**Marketing Bot** - 규림한의원(청주) 마케팅 자동화 시스템
- 네이버 플레이스 순위 추적 · 키워드 발굴 (Pathfinder/Legion)
- 경쟁사 분석 · 바이럴 콘텐츠 수집 (Viral Hunter)
- 리드(잠재고객) 발굴 · AI 댓글 생성

---

## 핵심 기술 스택

**백엔드**: FastAPI · SQLite · Codex CLI (중앙 클라이언트: `services/ai_client.py`)
**프론트엔드**: React 19 · TypeScript 5.6 · TanStack Query v5 · Tailwind CSS · Vite 8 · PWA
**AI/RAG**: sqlite-vec + BGE-M3 + bge-reranker-v2-m3 · Pydantic AI · Camoufox (SERP 캡차 우회)
**관측성**: Logfire + Langfuse (토큰 있을 때만 cloud) · ai_call_log 테이블

---

## 중요: 실행 환경

**⚠️ Windows에서만 실행** (WSL 없음). `wsl --shutdown` 등 WSL 종료 명령 절대 금지.

```bash
# 서버 실행
build_and_run.bat                                              # 포트 8000 필수

# 핵심 스크립트
python pathfinder_v3_legion.py --target 500 --save-db         # 키워드 수집
python viral_hunter.py --scan --fresh --top-n-for-ai 300 --ai-parallel 5  # 바이럴
python scrapers/scraper_naver_place.py                        # 순위 스캔 (병렬)
python scrapers/scraper_naver_place.py -w 5                   # 병렬 5개 브라우저
python scrapers/scraper_naver_place.py --sequential           # 순차 모드
```

---

## 🤖 Claude Code 자연어 운영 가이드

### 자연어 의도 → 스킬 매핑

| 사용자 의도 (예시) | 스킬 | 위치 |
|---|---|---|
| "순위 스캔" / "오늘 순위 어때" | **scan-ranks** | `skills/scan-ranks/SKILL.md` |
| "키워드 발굴" / "S급 찾아" / "Legion 모드" | **scan-pathfinder** | `skills/scan-pathfinder/SKILL.md` |
| "경쟁사 변화" / "리뷰 새로 들어온 거" | **scan-competitors** | `skills/scan-competitors/SKILL.md` |
| "오늘 종합" / "주간 브리핑" / "임원 보고용" | **brief** | `skills/brief/SKILL.md` |
| "헬스체크" / "수집 상태" / "API 키 만료된 거" | **data-health** | `skills/data-health/SKILL.md` |
| 일반 데이터 질문 ("최근 30일 1위") | **query** | `skills/query/SKILL.md` |
| 바이럴 댓글 초안 (cron/자동) | **viral-comment-drafter** | `skills/viral-comment-drafter/SKILL.md` |
| "카페 본문 채워줘" / "hot 글 재방문" | **viral-enrich** | `skills/viral-enrich/SKILL.md` |
| "garbage 정리" / "광고 데이터 갱신" | **pathfinder-quality** | `skills/pathfinder-quality/SKILL.md` |
| "PAA 수집" / "쇼핑 인사이트" / "보조 키워드" | **scan-keywords-extra** | `skills/scan-keywords-extra/SKILL.md` |
| "AEO 측정" / "AI 검색 노출" | **aeo-tracker** | `skills/aeo-tracker/SKILL.md` |
| "경쟁사 별점" / "비공개 전환" / "단가 비교" | **competitor-watch** | `skills/competitor-watch/SKILL.md` |
| "의료광고법 컴플라이언스" / "가이드북 임베딩" | **medical-compliance** | `skills/medical-compliance/SKILL.md` |
| "SERP 변동" / "MY플레이스 클립" | **serp-content-vitality** | `skills/serp-content-vitality/SKILL.md` |
| "GSC 검색어" / "PageSpeed" / "Core Web Vitals" | **inbound-analytics** | `skills/inbound-analytics/SKILL.md` |
| "p-value" / "A/B 통계" / "Schema.org" | **content-quality** | `skills/content-quality/SKILL.md` |

### 호출 절차 (4단계)

1. **발화 분류** — 위 표에서 매칭 스킬 결정 (모호하면 한 번 확인)
2. **SKILL.md 읽기** — Read로 워크플로우/명령어/가드레일 파악
3. **Bash 실행** — SKILL.md 명령 그대로 실행 (5분+ 작업: `run_in_background=true`)
4. **자연어 보고** — SKILL.md 보고 템플릿 따라 인사이트로 응답 (**stdout raw 덤프 절대 금지**)

### 보고 원칙

- 숫자는 SQL로 직접 검증 (캐시된 리포트 텍스트 복붙 금지)
- 인사이트 = 데이터 + 원인 추정 + 다음 액션 1~3개 제안
- 출력: 변화 10건 이내→전부, 초과→top 5 + "외 N개"
- 법규 자동 적용: `ai_generate_korean()` → `services/content_compliance.py` 의료광고법 자동 게이트

### 절대 금지

- ❌ **자동 게시** — 모든 게시는 web UI 또는 Telegram HITL 4-button 통과 필수
- ❌ **DML SQL** — INSERT/UPDATE/DELETE/DROP은 명시적 마이그레이션 스크립트로만
- ❌ **DB 직접 cp 복사** — `scripts/safe_db_copy.sh` 또는 `db_backup.py` 사용 (2026-02-06 사고)
- ❌ **자기 한의원 타게팅** — `business_profile.json::self_exclusion` 매칭 제외
- ❌ **cron/자동 댓글 생성** — 의도적으로 제거됨, 새로 추가 금지 (사용자 명시 거부)
- ❌ **30분/24시간 내 중복 스캔** — 명시적 "다시" 요청 없으면 직전 시각 보여주고 확인

### Web UI에서만 처리 (Claude가 대신 안 함)

바이럴 댓글 검토/수정/승인 · 리드 카드 처리 · Q&A 큐레이션 · Battle 키워드 등급 조정 · Competitor 약점 라벨링

---

## 프로젝트 구조

```
C:\Projects\marketing_bot\
├── config/
│   ├── config.json           # API 키 설정
│   ├── keywords.json          # 키워드 설정 (naver_place / blog_seo)
│   ├── competitors.json       # 경쟁사 목록 (로랑/데이릴 포함)
│   ├── business_profile.json  # 업체 정보 + self_exclusion
│   └── prompts.json           # AI 프롬프트 (comment_generation 변경 시 사용자 확인)
├── db/
│   ├── marketing_data.db      # 메인 DB
│   └── backups/               # 백업 (DB 작업 전 필수)
├── marketing_bot_web/
│   ├── backend/
│   │   ├── main.py
│   │   ├── routers/           # viral.py / pathfinder.py / hud.py / leads.py 등
│   │   ├── services/
│   │   │   ├── ai_client.py   # ← 모든 AI 호출의 단일 진입점
│   │   │   └── db_init.py     # 스키마 초기화
│   │   └── backend_utils/     # (utils/ 아님 — import 충돌 방지)
│   └── frontend/src/
│       ├── pages/
│       ├── components/
│       │   ├── settings/      # 7개 탭 컴포넌트
│       │   └── viral/views/   # HomeView/WorkView/ListView/CompletionView
│       └── services/api/      # 도메인별 분리 (api.ts 단일 파일 아님)
├── scrapers/
│   ├── scraper_naver_place.py  # 순위 스크래핑 (모바일+데스크탑 병렬)
│   └── competitor_analyzer.py
├── core_services/
│   ├── viral_seed_builder.py   # 시드 선택 + 카테고리 수요 게이트
│   ├── gyulim_keyword_profile.py  # 규림 치료 축 프로필 (단일 소스)
│   ├── pathfinder_insight_broker.py
│   └── viral_handoff_audit.py
├── viral_hunter.py             # 바이럴 헌터 (핵심 — 자주 수정)
├── pathfinder_v3_legion.py     # Legion 모드
├── repositories/
│   └── viral_target_repo.py    # viral_targets 레포지토리
├── tests/
│   ├── test_pathfinder_viral_stability.py  # 현재 553 passed, 1 skipped
│   └── test_router_smoke.py
└── scripts/
    ├── recanonicalize_viral_categories.py  # 카테고리 재정규화 (1회성 마이그레이션)
    └── expire_stale_pending.py
```

> ⚠️ import 경로: `from backend_utils.xxx` (not `from utils.xxx`)

---

## 주요 페이지 및 기능

| 페이지 | 경로 | 기능 |
|--------|------|------|
| Dashboard | `/` | 메트릭, 브리핑, Sentinel Alerts, Chronos Timeline |
| Pathfinder | `/pathfinder` | 키워드 수집/분석/클러스터 |
| Viral Hunter | `/viral` | 바이럴 콘텐츠 수집 + 댓글 생성 |
| Battle Intelligence | `/battle` | 순위 추적, 트렌드, 경쟁사 활력 |
| Lead Manager | `/leads` | 6개 플랫폼 리드 관리 |
| Competitor Analysis | `/competitors` | 약점 공략, 기회 키워드 |
| Marketing Hub | `/marketing` | Analytics 통합 (구 `/analytics` 리다이렉트) |
| Settings | `/settings` | 백업, 시스템, 자동화, 키워드 편집 |

---

## 데이터베이스 핵심 테이블

| 테이블 | 용도 | 주요 컬럼 |
|--------|------|----------|
| `keyword_insights` | 발굴 키워드 | grade, search_volume, category, business_core, last_scan_run_id |
| `rank_history` | 순위 이력 | keyword, rank, device_type(mobile/desktop), scanned_date |
| `viral_targets` | 바이럴 콘텐츠 | comment_status, priority_score, score_breakdown(JSON), matched_keyword_category |
| `viral_scan_audits` | 스캔 감사 | per_query_variant, per_category_lens, fresh_discovered, rediscovered |
| `scan_runs` | 스캔 실행 기록 | status('completed'만 유효), new_keywords, updated_keywords |
| `competitor_reviews` | 경쟁사 리뷰 | star_rating |
| `pending_approvals` | HITL 승인 큐 | 30분 만료 |
| `ai_call_log` | AI 비용 추적 | model, module, cost |
| `qa_repository` | Q&A 패턴 | question_pattern, standard_answer |
| `job_runs` | 잡 실행 이력 | job_name, status, started_at |

**`rank_history.status`**: `found` / `not_in_results` / `no_results` / `error`

**`viral_targets.comment_status`**: `pending`(골든큐) / `raw_backlog` / `needs_ai_retry` / `generated` / `posted` / `skipped` / `filtered_out` / `filtered_out_ad` / `filtered_out_ai`

**`viral_targets` 핵심 score_breakdown 키**: `clinic_treatment_fit_score`, `worksite_efficiency_score`, `matched_keyword_category`, `final_reject_reason`, `provider_venue_author`(신규)

---

## keywords.json 구조

```json
{
  "naver_place": ["청주 한의원", "청주 다이어트 한약"],
  "blog_seo": ["청주 새살침", "청주 안면비대칭 교정"]
}
```

플레이스 순위 없는 키워드 → `blog_seo` 카테고리 분리

---

## AI 모델 사용 규칙

**중앙 클라이언트**: `marketing_bot_web/backend/services/ai_client.py` — 모든 AI 호출 여기서

```python
from services.ai_client import ai_generate, ai_generate_json, ai_generate_korean

# 잘못된 사용 (금지)
from google import genai              # X - 직접 호출 금지
from openai import OpenAI             # X - 사용 안 함
```

| 함수 | 모델 (task 기준) | 용도 |
|------|-----------------|------|
| `ai_generate()` | fast_json/structured → gpt-5.4-mini | 분류·판단·요약 |
| `ai_generate_json()` | fast_json → gpt-5.4-mini | 구조화 JSON |
| `ai_generate_korean(task="viral_comment")` | viral_comment → gpt-5.5 | 바이럴 댓글 (footer 없음, 1인칭 보존) |
| `ai_generate_korean()` | gpt-5.4 | 일반 한국어 콘텐츠 |

**예외**: `vision_analyst.py`만 Codex CLI Vision 직접 사용

---

## 현재 시스템 상태 요약 (2026-06-25 기준)

**브랜치**: `codex/pathfinder-discovery-audit`
**테스트**: `pytest tests` → 620 passed, 1 skipped

### 2026-06-22: Pathfinder #85 + Viral Hunter #13 퍼널 정밀화

> 상세: memory `project_pathfinder_viral_scan_2026_06_22.md`. 500+ Legion 완수 후 Viral Hunter 순차 스캔 완료. 결론: Pathfinder 공급은 충분하고, Viral 신규 전환/중복 재발견이 병목.

| 영역 | 결과 / 변경 |
|------|-------------|
| Pathfinder #85 | `7,535` keywords, 신규 `401`, 갱신 `7,134`, `S=78`, `A=1,560`, `S+A=1,638`, 완료 `9,044s`. scan #84 실패 원인인 final diversity rerank O(n^2) 병목은 precise top `1,500`만 정밀 rerank + tail append로 완화 |
| Viral audit #13 | source_scan_run_id=85, `12,055` discovered, `507` fresh, `403` actionable, `60` open_pending, `10` fresh_pending, `3,104` ad_filtered, rediscovered `95.8%` |
| 병목 해석 | `pending_count=403`은 열린 큐가 아니라 과거 actionable 누계. 신규 성과는 `fresh_pending=10` / `fresh_pending_rate=1.97%`로 봐야 함 |
| 카테고리 | 다이어트 fresh `95` → fresh_pending `6` 최상. 피부/여드름 fresh `198` → fresh_pending `0`, 교통사고 fresh `27` → `0`이라 쿼리/필터 정밀도 개선 대상 |
| 코드 개선 | `viral_hunter.py` audit alias(`actionable`, `fresh_actionable_rate`, `fresh_discovery_rate`) + `marketplace_sale` 게이트. `pathfinder_insight_broker.py` zero-yield를 `pending==0`에서 `fresh_pending==0` 기준으로 교정. `signature_axis_sla.py` fresh/open/actionable 분리 표시 |
| 데이터 정리 | CSV에 섞인 `청주) 보몬 e54 LV60 팔아요` legacy pending 행을 `filtered_out`, `final_reject_reason=marketplace_sale`로 정리 |
| 검증 | `py_compile` 통과 + 브로커 fresh_pending 회귀 + marketplace_sale 회귀 테스트 통과 |

### 2026-06-23: Pathfinder #87 + Viral Hunter #14 base-query budget gate

> 상세: memory `project_pathfinder_viral_scan_2026_06_23.md`. 500+ Legion 완수 후 Viral Hunter 순차 스캔 완료. 결론: Pathfinder 공급은 충분하고, Viral 병목은 `base`/`community_base`의 반복 재발견과 fresh-zero-yield 레인.

| 영역 | 결과 / 변경 |
|------|-------------|
| Pathfinder #87 | `7,506` keywords, 신규 `321`, 갱신 `7,185`, `S=80`, `A=1,585`, `S+A=1,665`, 완료 `8,384s`. 500+ 조건 충족 |
| Viral audit #14 | source_scan_run_id=87, `13,212` discovered, `516` fresh, `361` actionable, `12` open_pending, `5` fresh_pending, `3,436` ad_filtered, rediscovered `96.1%` |
| 직전 대비 | audit #13 대비 discovered/fresh는 증가했지만 fresh_pending `10 -> 5`, open_pending `60 -> 12`로 실전환 하락. 신규 공급보다 반복 검색면 관리가 병목 |
| 핵심 쿼리면 | `base`: `5,804` discovered, `169` fresh, `0` fresh_pending. `patient_voice_kin`: `1,248` discovered, `223` fresh, `0` fresh/open pending이라 다음 계획에서 64건 자동 drop |
| 코드 개선 | `viral_hunter.py`에 mandatory `base`/`community_base` 차단 대신 budget scaling 추가. fresh/open pending 있는 레인은 보호하고, fresh-zero/high-rediscovery/high-ad 레인은 `0.45~0.80` 계수로 검색 예산 축소 |
| 관측성 | audit `coverage_bounds.base_variant_budget_scales` 추가. 다음 스캔에서 어떤 base 레인이 얼마나 축소됐는지 추적 가능 |
| 검증 | base budget 테스트 2개 추가. `pytest -q tests/test_pathfinder_viral_stability.py -k "variant_yield_gate or variant_proven_zero_yield or base_variant_budget"` → 9 passed |

### 2026-06-20~21: 바이럴 발견 시스템 심층검토 + 13개 개선 (discovery review + 1인칭 정책 end-to-end 완성)

> 상세: memory `project_viral_discovery_review_2026_06_20.md`. 발견 퍼널 핵심 메커니즘은 견고함을 확인(실데이터 포렌식); 개선은 관측성·정밀도·1인칭 정책 일관성에 집중.

| 영역 | 변경 내용 |
|------|----------|
| 관측성 | `_persist_viral_discovery_audit` → `coverage_bounds`(funnel 거절·변형/플랫폼/구조 차단·키워드 한도 영속화) + `per_category_reject_reason`(축×사유 포렌식) |
| 1인칭 경험담 스코어링 | `_assess_viral_need` `peer_experience_opportunity`(per-axis 증거) + diet 후기 광고오탐(`diet_testimonial_promo`) 완화 |
| venue 다양성 | 골든큐 `_select_targets_with_venue_diversity`(하드캡) + AI배치 `_ai_target_venue_key`(소프트+예산폴백) — 한 카페 독점·스팸지문 방지 |
| 랭킹 정렬 | `routers/viral.py` 플랫폼 수용도(`_platform_acceptance_factors`, KIN>cafe>blog) + lens_fit(`_staff_signal_rank_adjustment`) — 직원 실수요 정렬(읽기경로만, worksite frozen 불변) |
| liveness | enrichment 후 `_resaturate_worksite_after_enrichment` — 선택 시점 死코드(comment_count=0 미답변)였던 포화 신호를 실수치로 보정 |
| 의미기반 발견 | `core_services/semantic_axis_matcher.py`(BGE-M3, fail-soft·**opt-in** `MARKETING_BOT_SEMANTIC_DISCOVERY`) 매칭측 axis 구제 + `COLLOQUIAL_AXIS_TERMS` 구어 쿼리 확장. 기본 off → 회귀 0 |
| ⚠️ 1인칭 정책 완성 (USER DIRECTIVE) | `prompts.json`(unified_analysis 후기 수용·comment_generation·category_templates 1인칭) + `content_compliance.py`(viral `allow_first_person_experience` → "환자 치료경험담" 면제, **경성 위반은 유지**) + `ai_client.py`(task=viral_comment 면제 전달) + `_compliance_guardrail` → 발견→생성→게이트→fallback 일관화 |
| 스팸 지문 방지 | `VIRAL_COMMENT_PERSONA_FRAMES` — 1인칭 프레임 시작 방식 결정적 회전(정식명칭 유지) |

### 2026-06-21: 의미기반 발견 실가동 + 시그니처 축(흉터/안면비대칭) 강화 5레인

> 상세: memory `project_viral_discovery_review_2026_06_20.md`. semantic 켜니 recall은 breadth로 net-positive(fresh +155%·AI적합 +73%·실대기축 7→10/19)지만 시그니처 갭은 구조적(Naver 로컬 콘텐츠 희소)이라 발견 레버로 못 메움 → 공급/채널 재라우팅 5레인.

| 레인 | 변경 내용 |
|------|----------|
| 의미기반 실가동 | `.env MARKETING_BOT_SEMANTIC_DISCOVERY=1` ON(BGE-M3 로컬 캐시·실측 net-positive). `tests/conftest.py` autouse fixture로 테스트 격리(기본-off 계약 유지·회귀 0) |
| Lane A 백로그 레인 | `viral_hunter.py` `SIGNATURE_BACKLOG_AXES`+`_load_backlog_rescue_targets(categories=,days=180)`+`--rescue-signature`(기본40). 일반 레스큐(21일·category-blind)가 굶기던 안면비대칭 raw_backlog 912 해금(실측 21일창 0→180일창 912). **프로덕션 가동 실측**: 레인 17개 투입(3 pending 진입)→흉터 pending 0→2(첫 골든큐 진입)·raw_backlog 흉터18→4/안면885·실대기축 10→12/19 |
| Lane B Q&A 시딩 | `scripts/generate_signature_qa_drafts.py`→9개 드래프트(0 compliance flag·1인칭) + `scripts/seed_signature_qa.py`(DML·백업·멱등·dry-run). **적재 완료**: qa_repository 10→19행 + `QASearchEngine.index_all()` RAG 재인덱스·검색 검증(패인자국 0.912) |
| Lane C 콘텐츠 브리프+본문 | `scripts/generate_signature_content_briefs.py`→pillar 브리프 2개 + `scripts/generate_signature_post_drafts.py`→발행 초안 본문 2개(★자체 콘텐츠=교육 톤, 1인칭 환자후기 사칭 금지=owned content 가짜후기는 의료광고법 위반·viral_comment 면제와 구분, `check_content_compliance(content_type='blog')` 2/2 통과) + keywords.json blog_seo 시그니처 타겟 추가. HITL 수동 발행 |
| Lane E 측정 SLA | `scripts/signature_axis_sla.py`(read-only) — 골든큐·백로그 윈도우 갭·Q&A 커버리지·자체 랭크·발견 퍼널 트렌드(viral_scan_audits) |

**Lane D(전국 정보성) — 설계 후 D1 엄밀검증 기각(코드변경 0)**: 거절풀 3버킷 재정의 + 3-tier 설계(D1 충북회수·D2 새살침전국·D3 전국일반). 사용자 D1 선택했으나 `final_reject_reason='region_mismatch'`+충북생활권+NOT타지역=**0건**(앵커 어휘가 이미 오송/오창/청원/진천/증평/괴산/음성/보은 커버)·세종 region_mismatch 11건은 전부 대전 경쟁사 광고(추가 시 HARM)·초기 "215"는 substring 오버카운트 → **허울 기능 금지로 미구현**, region 게이트 정밀도 검증됨. **교훈**: 거절 사이징은 `final_reject_reason`로 검증, 지명 substring 카운트 금지. **잔여 운영**: Lane C 수동 발행(초안 본문 준비 완료, 사람이 검수→게시)·매 스캔 Lane A가 912 점진 배수·D2(새살침 전국·informational·opt-in) 원하면 별도 구현.

**신규 가드레일**: 위 "핵심 가드레일" 섹션의 semantic ON/conftest 격리·SIGNATURE_BACKLOG_AXES 동기화·Q&A DML+RAG재인덱스 4건 참조.

**신규 가드레일(변경 시 주의)**: ① 의미기능은 opt-in(`MARKETING_BOT_SEMANTIC_DISCOVERY=1`+BGE-M3 설치 시 가동) ② `content_compliance` viral 1인칭 면제는 "환자 치료경험담" 카테고리만 — 단정효과·할인·이벤트·AI의료진추천·비교·전후비교는 viral여도 계속 차단 ③ 랭킹/venue 변경은 읽기경로(`routers/viral.py`)만, frozen worksite/스코어링 불변.

### 최근 주요 변경 (2026-06-19)

| 파일 | 변경 내용 |
|------|----------|
| `viral_hunter.py` | Provider-Venue Author Gate (`_provider_venue_author_signal`) — 클리닉 브랜드 카페 +7 → filtered_out_ad |
| `viral_hunter.py` | Comment Input Isolation (`_comment_input_text`) — KIN [기존답변] 이전 질문 500자만 |
| `viral_hunter.py` | Timing Window Hard Cap — posted_at > 270d → `return 0,"stale"` |
| `viral_hunter.py` | Sentinel Fix (`_is_failed_comment_text`) — 실패 sentinel → "" (status flip 방지) |
| `viral_hunter.py` | Phrase Variation (`_phrasing_variation_directive`) — location rotation + cliché ban, temp 0.72 |
| `viral_hunter.py` | Variant Gate Regression Fix (`_variant_gate_should_drop`) — global aggregate fallback |
| `viral_hunter.py` | Proxy Penalty Damping — 직원 수요 ≥15% → proxy ×0.30 |
| `viral_hunter.py` | Lens Budget Dead-Zone — `_staff_outcome_adjustment` 0.12-0.20 구간 +4 추가 |
| `routers/viral.py` | Signature-Aware Routing — `SIGNATURE_ROUTING_AXES` → content-axis 우선 |
| `routers/viral.py` | Competitor Name Gate (`_competitor_name_is_identifiable`) — N/A 차단 |
| `core_services/viral_seed_builder.py` | Discovery Audit Fresh Metric — zero_yield_seeds → fresh_discovered 기준 |
| `marketing_bot_web/backend/services/ai_client.py` | Viral Comment Tone Fix — task="viral_comment" → footer 없음, 1인칭 보존 |
| `scripts/recanonicalize_viral_categories.py` | Legacy Category Migration — 흉터 51→122, 안면비대칭 44→85 |

### 2026-06-13 ~ 06-18 주요 변경

- **Provider-Venue Author Gate 이전 레이어**: `_has_local_venue_anchor()` → 청주 카페 author +15 크레딧
- **Category Demand Gate**: `_apply_category_demand_gate()` → 흉터 12→18, 안면비대칭 10→16 시드
- **Structure-Yield HARD BLOCK**: `_structure_proven_zero_yield()` → suffix+neigh 제로수율 차단
- **Queue Ranking Tiebreak**: priority sort → worksite_efficiency → clinic_treatment_fit 순
- **Competitor Counter-Attack**: `competitors.json` 단일 소스, 로랑/데이릴 critical
- **Timeliness + Platform-Yield**: KIN/cafe 날짜 복구, pending TTL, 플랫폼 수율 예산 게이트
- **Body Enrichment**: KIN/blog/cafe 본문 fetch + 질문 세그먼트 regate
- **Backlog Rescue**: raw_backlog 재처리 (40% 합격률)
- **Variant Yield Gate + Patient-Voice KIN Lane**: 증거 기반 variant 자동 폐기
- **Scar-Axis Calibration**: cosmetic_clinic off-domain 완화 (탐색 의향 환자 보존)
- **BRIDGE Predictiveness**: 시드-적합 점수 → learned workable yield 직접 반영

### 2026-06-02 ~ 06-12: Codex CLI 런타임 잠금 + 통합 라이브 런

- Codex CLI 전용 잠금 (`codex exec --dangerously-bypass-approvals-and-sandbox`)
- 모든 AI 호출 `ai_client.py` 단일 진입점
- 포트 8000 안전 잠금 (기존 서버 유지, 명시적 `--restart` 필요)
- `COALESCE(last_scanned_at, discovered_at)` — 재발견 = 현재 작업

### 2026-04 ~ 05: 시스템 고도화

- **Codex CLI 전면 전환** (Qwen3.5-Flash 무료 한도 초과)
- **의료광고법 규제 대응** (2026-04 규제 4건): 컴플라이언스 게이트, AI 고지 footer
- **AI 인프라**: Camoufox (SERP 캡차 우회), RAG (sqlite-vec+BGE-M3), Pydantic AI agent loop, Logfire, Langfuse
- **UX 정비**: Settings 7탭, Analytics → Marketing Hub 통합, 탭 TabNavigation 통일

### 2026-04-28: 바이럴 수집 근본 개혁

- 골든큐: `기타` 87.5% → 미용 주력 카테고리 100% (confidence ≥0.85 + category 필터)
- AI 댓글 생성 버그: DB 저장 + 표시 동시 수정 (단건/일괄 모두)
- Rules of Hooks 위반: `SmartFilterBar.tsx` early return 이후 useCallback 이동
- 댓글 프롬프트: 자연 후기 톤, ㄱㄹ 초성 표현 → 2026-06-19에 풀네임으로 재변경

### 2026-02 ~ 2026-03: 인프라 정비

- 네이버 플레이스 데스크탑 스크래핑 완성 (점진적 스크롤, 94% 성공률)
- `Settings.tsx` 8개 탭 컴포넌트 분리 (2272줄 → 200줄)
- `ViralHunter.tsx` 4개 뷰 컴포넌트 분리 (1926줄 → 826줄)
- API 클라이언트 도메인별 15개 모듈 분리 (`services/api/`)
- 병렬 스캔 DB 연결 누수 수정 (싱글톤 내 `conn.close()` 제거)
- Phase 8/9/10: 27개 수집기, 25개 DB 테이블, 34→27개 스케줄 작업
- Phase 5.0/6.x: Q&A Repository, LeadScorer 확장, `backend_utils/` 이름 변경

---

## 개발 규칙

- **허울 기능 금지**: "준비 중...", "곧 추가됩니다" placeholder 금지. 기능 없으면 UI 요소 숨김
- **에러 처리**: API 호출 실패 시 명확한 메시지 (500 반환 → 사용자에게 노출)
- **코드 수정 전**: 영향 파일 목록 파악 → 테스트 방법 확인 → 롤백 준비
- **TypeScript**: `any` 타입 지양, 도메인별 타입 import (`@/types` 또는 `services/api/`)
- **DB 연결**: `try/finally conn.close()` 패턴 (bare `except:` 금지 → `except Exception:`)
- **비동기**: `asyncio.run()` 직접 호출 금지 → 백그라운드 스레드 큐 또는 `asyncio.to_thread`

---

## 알려진 이슈 및 주의사항

**완료됨:**
- [x] 네이버 플레이스 데스크탑 스크래핑 (스크롤 방식, 94% 성공)
- [x] Settings.tsx 컴포넌트 분리, ViralHunter.tsx 뷰 분리
- [x] Codex CLI 전면 마이그레이션 (Qwen 제거)
- [x] 바이럴 댓글 AI footer + 1인칭 보존 (2026-06-19)
- [x] Provider-Venue Author Gate (2026-06-19)
- [x] Legacy category migration (흉터 51→122)

**진행 중 / 주의:**
- 14개 stuck "running" scan_runs: 코스메틱 이슈. `latest_completed_legion_scan_id()` → `status='completed'` 필터링으로 영향 없음
- 의료 리뷰 수집기(`medical_review_monitor.py`) 비활성: 모두닥 ToS 금지, 굿닥 SPA noindex
- Kakao/HIRA 수집기 비활성: API 키 미발급/만료
- `medical_review_monitor.py` / `geo_grid_tracker.py` / `review_nlp_analyzer.py` 비활성: 이유는 `config/schedule.json::disabled_reason` 참조
- 스크래핑 파일 수정 후 서버 재시작 불필요 (subprocess 호출 방식)
- 병렬 스캔 브라우저 수 과다 → 네이버 차단 리스크 (권장: 3-5개)

---

## 중요: 데이터베이스 작업 규칙

**⚠️ DB 파일 수정/복사/이동 전 반드시 백업 먼저 생성 (2026-02-06 데이터 손실 사고 이력)**

```bash
# SQLite Backup API 사용 (권장)
python db_backup.py

# 또는 수동 백업
cp db/marketing_data.db "db/backups/marketing_data.db.backup_$(date +%Y%m%d_%H%M%S)"

# 안전한 복사 (자동 비교/경고/백업)
scripts/safe_db_copy.sh <원본> <대상>

# 절대 금지
cp source.db target.db   # X - 직접 덮어쓰기 금지
```

**백업 위치**: `db/backups/` · **보관**: 최근 30개 · **자동 백업**: Settings 페이지 또는 Task Scheduler

**DB 연결 원칙**: `DatabaseManager` 싱글톤 — 개별 함수에서 `conn.close()` 호출 금지. 연결 관리는 클래스가 담당.

---

## 새로운 대화에서 이어서 작업할 때

```bash
# DB 상태 빠른 확인
sqlite3 db/marketing_data.db "
SELECT 'keyword_insights' as tbl, COUNT(*) FROM keyword_insights
UNION ALL SELECT 'rank_history', COUNT(*) FROM rank_history
UNION ALL SELECT 'viral_targets', COUNT(*) FROM viral_targets
UNION ALL SELECT 'pending' as tbl, COUNT(*) FROM viral_targets WHERE comment_status='pending'
UNION ALL SELECT 'scan_runs', COUNT(*) FROM scan_runs WHERE status='completed';
"

# 직전 순위 스캔 시각
sqlite3 db/marketing_data.db "SELECT MAX(checked_at) FROM rank_history"

# 최신 Legion 스캔
sqlite3 db/marketing_data.db "SELECT id, status, new_keywords, created_at FROM scan_runs ORDER BY id DESC LIMIT 3"
```

**체크리스트**:
1. 이 파일(CLAUDE.md) 읽기
2. 현재 브랜치 확인 (`git branch`)
3. DB 상태 확인 (위 명령)
4. 테스트 회귀 확인: `python -m pytest tests -q` (목표: 620+ passed)
5. 서버 상태: `build_and_run.bat` 후 `http://localhost:8000/health`

---

## 2026-06-24 Memory: Pathfinder -> Viral Hunter handoff audit hardening

- Branch: `codex/pathfinder-discovery-audit`.
- Scope committed in this round should stay limited to:
  - `core_services/viral_handoff_audit.py`
  - `scripts/viral_handoff_audit.py`
  - `tests/test_viral_handoff_audit.py`
  - `CLAUDE.md`
- New audit axis: `seed_candidate_alignment`.
  - Purpose: verify that Pathfinder source-keyword intent survives inside Viral Hunter candidate title/body text.
  - Signals: source-specific terms, treatment-axis semantic terms, lens/route terms, and Cheongju/local tokens.
  - World-class gate now fails when candidates are strict/actionable but only preserve generic terms.
- Previous audit hardening in same workstream:
  - `reply_workability_quality`
  - `treatment_signal_diversity_quality`
  - `execution_readiness_quality`
  - `execution_priority_alignment_quality`
- Current operating DB (`db/marketing_data.db`, scan 87) remains `critical`, score `33.51`.
  - `execution_priority_alignment`: category `3/7`, category_lens `6/42`.
  - `seed_candidate_alignment`: category `6/7`, category_lens `9/42`.
  - Representative seed/candidate drift lanes: `피부/여드름::consultation`, `다이어트::safety`.
- Verification completed:
  - `python -m py_compile core_services\viral_handoff_audit.py scripts\viral_handoff_audit.py tests\test_viral_handoff_audit.py`
  - `python -m pytest tests\test_viral_handoff_audit.py -q` -> `34 passed`
  - `python -m pytest tests\test_pathfinder_viral_stability.py tests\test_viral_handoff_audit.py tests\test_gyulim_keyword_profile.py -q` -> `381 passed`
  - `git diff --check -- core_services\viral_handoff_audit.py scripts\viral_handoff_audit.py tests\test_viral_handoff_audit.py` -> no whitespace errors, LF/CRLF warnings only.

## 2026-06-25 Memory: Pathfinder -> Viral Hunter world-class discovery loop

- Branch: `codex/pathfinder-discovery-audit`.
- Scope of this commit:
  - `core_services/gyulim_keyword_profile.py`
  - `core_services/viral_handoff_audit.py`
  - `core_services/viral_seed_builder.py`
  - `scripts/viral_handoff_audit.py`
  - `tests/test_gyulim_keyword_profile.py`
  - `tests/test_pathfinder_viral_stability.py`
  - `tests/test_viral_handoff_audit.py`
  - `viral_hunter.py`
  - `CLAUDE.md`
- System-level conclusion:
  - Pathfinder now explores Gyulim treatment demand broadly enough for scars, asymmetry, skin/acne, diet, pain, sleep, digestion, etc.
  - Viral Hunter no longer relies on broad category matching alone. The handoff loop now preserves category, lens, platform surface, exact category-lens gaps, source seed intent, venue diversity, and treatment-signal diversity into the candidate queue.
- Key hardening added in this workstream:
  - Gyulim profile expansion and patient-question seed coverage.
  - Patient-voice query variants and zero-yield gates.
  - Query plan cache and source seed audit feedback loop.
  - Variant-quality feedback from `viral_handoff_audit.py` into `viral_hunter.py`.
  - Platform surface quality feedback with `naver_kin` -> `kin` normalization.
  - Auto handoff playbook boosts for categories, lenses, and exact `category::lens` lanes.
  - Deep audit gap parser so missing audit lanes become next-run exact boosts even without explicit `boost_*` fields.
  - AI target venue diversity inside category floors.
  - AI target treatment-signal diversity so one scar subtype such as `패인흉터` cannot dominate the entire scar queue when `수술흉터`, `모공흉터`, `켈로이드`, `여드름자국` candidates exist.
- Important behavior:
  - Treatment-signal caps are soft. Viral Hunter preserves budget by falling back when a lane has only one viable signal, such as a narrow diet pool.
  - Base/community-base lanes are protected from hard deletion but can be budget-scaled when audit evidence shows high rediscovery, high ad filtering, or fresh-zero yield.
  - Explicit CLI boosts still take precedence over auto handoff boosts.
- Verification completed:
  - `python -m pytest tests/test_pathfinder_viral_stability.py -k "treatment_signal_inside_category_floor or treatment_signal_cap or venue_inside_category_floor or category_floor_venue_cap or prefers_boosted_lens_inside_category_floor"` -> `5 passed`
  - `python -m pytest` -> `620 passed, 1 skipped`
  - `python -m compileall -q viral_hunter.py core_services tests scripts`
  - `git diff --check -- viral_hunter.py tests/test_pathfinder_viral_stability.py` -> no whitespace errors, LF/CRLF warnings only.

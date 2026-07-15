# Marketing Bot 작업 맥락

> 이 파일은 모든 작업에 항상 필요한 짧은 운영·개발 컨텍스트만 담는다.
> 상세 계약은 [docs/OPERATING_CONTRACTS.md](docs/OPERATING_CONTRACTS.md),
> 변경 이력은 [docs/operations_history.md](docs/operations_history.md),
> 실행 명령 전체는 [docs/TERMINAL_GUIDE.md](docs/TERMINAL_GUIDE.md)에서 확인한다.

## 프로젝트 요약

- 목적: 규림한의원(청주)의 플레이스 순위·키워드·경쟁사·바이럴 리드 운영 지원.
- 스택: FastAPI + SQLite 백엔드, React/TypeScript/Vite 프론트엔드.
- AI 호출은 `marketing_bot_web/backend/services/ai_client.py`를 단일 진입점으로 사용한다.
- 주 파이프라인: `pathfinder_v3_legion.py` → `core_services/viral_seed_builder.py` →
  `viral_hunter.py` → `core_services/viral_handoff_audit.py`.
- 운영 DB: `db/marketing_data.db`. 바이럴 상태와 점수는 `viral_targets` 및
  `score_breakdown`을 기준으로 확인한다.

## 항상 지키는 운영 계약

세부 규칙은 [운영 계약 문서](docs/OPERATING_CONTRACTS.md)를 따른다. 핵심만 요약하면:

- 자동 게시·자동 댓글 생성은 구현하지 않는다. 게시·승인은 Web UI 또는 Telegram HITL에서만 한다.
- 사용자 소유의 바이럴 댓글 톤·네이밍·프롬프트 정책은 사용자 확인 없이 바꾸지 않는다.
- `manual_review`, `needs_enrichment`, `filtered_out*`, `skipped`, `deleted`, `posted` 후보를
  자동 실행 큐에 섞지 않는다. 영속 DB 상태를 in-memory 후보보다 우선한다.
- Pathfinder의 검색·지역·출처·세부의도·rescue 가드를 우회하거나 안전 게이트를 완화하지 않는다.
- `competitors.json`이 경쟁사 단일 소스이며, 직접 변경 시 `prompts.json`과 동기화한다.
- 의미기반 발견의 프로덕션 설정과 테스트 격리를 유지한다.

## 실행 및 검증

- Windows PowerShell 환경을 기준으로 한다. 장시간 작업은 백그라운드 실행 후 진행·완료를 확인한다.
- `scan_runs`는 `status='completed'`만 유효 결과로 취급한다. worker 없는 오래된 `running`은 근거를
  남기고 `failed`로 정리한다.
- 기본 검증: `python -m pytest -q`, `git diff --check`.
- 새 Viral 결과는 audit → metric backfill → body enrichment → export reconciliation 순으로 점검한다.
- `scripts/viral_hunter_curated.py` 실행은 completed Legion scan을 `--source-scan-id`로 명시한다.
  기본값은 S/A seed 우선이며, B 등급은 해당 치료축에 S/A seed가 없을 때만 보완 용도로 쓴다.
- AI 응답에 `SUITABLE` 판정이 없으면 영구 제외하지 않고 `needs_ai_retry`로 남긴다. 근거 없는
  AI 제외라도 결정론적 점수가 높은 후보는 자동 실행하지 않고 `manual_review`로 보낸다.
- 청주 타깃의 제목·본문 지역 게이트는 세종을 타지역으로 취급한다. 지역 불일치 후보는
  `filtered_out` 상태를 유지하며 실행 큐에 되돌리지 않는다.
- 주요 명령은 [터미널 실행 가이드](docs/TERMINAL_GUIDE.md)를 복사해 사용한다.

## DB 및 변경 안전

- DB 수정·복사·이동 전 SQLite Backup API 또는 `db_backup.py`로 백업한다.
- 임의 DML을 실행하지 않는다. 데이터 변경은 백업·멱등성·dry-run을 갖춘 운영/마이그레이션
  스크립트로 수행한다.
- `DatabaseManager` 싱글톤 연결을 개별 함수에서 닫지 않는다.
- `qa_repository` 적재 후에는 `QASearchEngine.index_all()`을 재실행한다.
- 작업 트리가 더러울 수 있으므로 현재 범위와 무관한 DB·보고서·스크린샷·임시 파일은
  수정·stage·삭제하지 않는다.

## 개발 규칙

- placeholder UI를 만들지 않고, 미구현 기능은 숨긴다. API 오류는 이해 가능한 메시지로 전달한다.
- TypeScript에서 `any`를 피하고 도메인 타입을 사용한다.
- `bare except` 대신 구체적인 예외 처리를 사용한다. 비동기 작업은 직접적인 `asyncio.run()` 호출보다
  백그라운드 큐 또는 `asyncio.to_thread`를 사용한다.
- 변경 전 영향 파일과 검증 방법을 파악하고, 작업 범위 테스트와 `git diff --check`를 실행한다.

## 작업 재개 체크리스트

1. `git status -sb`로 브랜치와 기존 사용자 변경을 확인한다.
2. 최신 completed Legion run과 열린 바이럴 큐를 DB에서 확인한다.
3. 변경 범위 테스트를 먼저 실행하고 가능하면 관련 전체 suite를 실행한다.
4. 결과 보고에는 raw stdout 대신 검증 수치, 원인, 다음 액션만 간결히 적는다.

## 문서 관리 원칙

- 이 파일에는 안정적인 규칙과 탐색에 필요한 진입점만 추가한다. 일회성 수치·실행 결과·긴 절차는 넣지 않는다.
- 결정의 배경과 날짜별 변경은 `docs/operations_history.md`, 원본 증거와 감사 결과는 `reports/`에 둔다.
- 제안서·설계서·완료 보고서는 현재 동작의 규범이 아니므로 이 파일에서 재서술하지 않는다.

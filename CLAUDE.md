# Marketing Bot 작업 맥락

> 이 파일에는 모든 작업에서 반복적으로 필요한 운영·개발 규칙과 진입점만 둔다.
> 상세 계약은 [docs/OPERATING_CONTRACTS.md](docs/OPERATING_CONTRACTS.md),
> 날짜별 변경 이력은 [docs/operations_history.md](docs/operations_history.md),
> 실행 명령 전체는 [docs/TERMINAL_GUIDE.md](docs/TERMINAL_GUIDE.md)를 확인한다.

## 프로젝트 요약

- 목적: 청주 중심의 로컬 마케팅 키워드 탐색, 바이럴 후보 발굴, 안전한 실행 큐 관리를 지원한다.
- 구성: FastAPI + SQLite 백엔드와 React/TypeScript/Vite 프런트엔드.
- AI 호출은 `marketing_bot_web/backend/services/ai_client.py`를 단일 진입점으로 사용한다.
- 주요 파이프라인: `pathfinder_v3_legion.py` → `core_services/viral_seed_builder.py` →
  `viral_hunter.py` → `core_services/viral_handoff_audit.py`.
- 운영 DB는 `db/marketing_data.db`다. 바이럴 후보의 최종 상태와 점수 근거는
  `viral_targets`와 `score_breakdown`을 기준으로 확인한다.

## 운영 계약

- 자동 게시·자동 답글 생성은 구현하지 않는다. 게시와 최종 확인은 Web UI 또는 Telegram HITL에서만 수행한다.
- 사용자 소유 바이럴·댓글·퍼블리시 결과·프로젝트 설정·프롬프트 정책은 명시적 승인 없이 바꾸지 않는다.
- `manual_review`, `needs_enrichment`, `filtered_out*`, `skipped`, `deleted`, `posted` 상태를 자동 실행 큐에 다시 넣지 않는다.
  영속 DB 상태가 in-memory 상태보다 우선한다.
- Pathfinder의 검색량·추출 수·rescue 가능성을 이유로 안전 게이트를 완화하지 않는다.
- `competitors.json`은 경쟁사 식별용이며 직접 변경하지 않는다. 프롬프트 변경은 `prompts.json`과 함께 검토한다.
- 교통사고 카테고리는 `교통사고`, `자동차사고`, 과실, 보험, 충돌 등 사고 고유 의도가 있는 시드만 허용한다.
  단순 `입원`, `병원` 등의 모호한 시드는 Pathfinder와 Viral 최종 게이트에서 차단한다.
- 청주 로컬 대상과 제목·본문 지역이 맞지 않는 후보는 `filtered_out`으로 유지하며 실행 큐로 되돌리지 않는다.

## 실행 및 검증

- Windows PowerShell을 기준으로 실행한다. 장시간 작업은 백그라운드 실행 뒤 진행·완료를 확인한다.
- `scan_runs.status='completed'`인 Legion 결과만 유효한 입력으로 취급한다. 유휴 worker의 오래된 `running` 상태는 원인을 확인한 뒤 정리한다.
- `scripts/viral_hunter_curated.py` 실행 시 완료된 Legion run을 `--source-scan-id`로 명시한다.
  기본적으로 S/A seed를 우선하고, B 등급은 같은 카테고리에 S/A seed가 없을 때만 보완 용도로 사용한다.
- AI 응답이 `SUITABLE`로 확정되지 않으면 후보를 실행하지 않는다. 재판정이 필요한 경우 `needs_ai_retry`를 유지하고,
  AI 제외 후보도 점수가 높다는 이유만으로 자동 실행하지 않는다.
- 기본 검증은 `python -m pytest -q`와 `git diff --check`다. 변경 범위의 표적 테스트를 먼저 실행한다.

## Legion → Viral 사후 처리

- 완료된 Legion run을 DB에서 확인한 뒤 Viral Hunter에 연결한다.
- 새 Viral 결과의 표준 순서는 `handoff audit → quality metric backfill → pending body enrichment → execution export reconciliation`이다.
  감사가 오래 걸릴 수 있으므로 다른 쓰기 작업과 묶지 말고 완료·저장 여부를 확인한다.
- `viral_quality_metric_backfill.py`는 저장된 제목·본문·메타데이터로 `score_breakdown`의 실행 품질 지표를 보강한다.
  먼저 dry-run으로 범위를 확인하고 SQLite Backup API 또는 `db_backup.py`로 백업한 뒤 `--apply`를 사용한다.
  이 작업은 `comment_status`를 바꾸거나 후보를 재큐잉해서는 안 된다.
- `enrich_pending_bodies.py`는 짧은 본문을 보강할 수 있지만, 게시일·작성자 등 필수 메타데이터가 복원되지 않으면
  자동 실행으로 승격하지 않는다.
- 실행 export는 메모리의 중간 상태가 아니라 최종 DB 상태로 재조정한다.
- `viral_scan_audits.summary`는 재발견 및 사전 게이트 저장 행을 포함할 수 있는 영속 DB 스냅샷이다. 검색 수집량이나 실행 수율의 분모로 사용하지 않는다.
- 런 단위 수율 분석은 `audit_json.run_funnel`의 불변 단계 카운트(검색 → 게이트 → 필터 → 중복 제거 → 보강 → AI → 최종 큐)를 우선한다. 기존 감사에 `run_funnel`이 없으면 `coverage_bounds`와 완료 로그를 별도 범위로 교차 확인하며, 서로 다른 스코프의 수치를 하나의 분모로 섞지 않는다.
- `viral_handoff_audit.py`가 저장한 `variant_quality_feedback`은 다음 Viral 계획의 입력이다.
  충분한 표본에서 생존·엄격 적합이 모두 0인 `retire_or_pause` 변형은 다음 계획에서 제외되어야 하며,
  재실행 전에는 해당 게이트의 표적 테스트로 이를 확인한다.
- 품질 커버리지 개선과 실제 전환 성과를 구분한다. 제외된 후보를 되살려 엄격 적합 수를 인위적으로 늘리지 말고,
  콘텐츠 카테고리 불일치·렌즈 표면 불일치·변형별 생존률을 다음 탐색 예산의 근거로 사용한다.

## DB 및 변경 안전

- DB 수정·복사·이동 전에는 SQLite Backup API 또는 `db_backup.py`로 백업한다.
- 임의 DML을 실행하지 않는다. 데이터 변경은 백업, 명시적 dry-run, 전용 마이그레이션 또는 스크립트를 통해 수행한다.
- `DatabaseManager` 싱글턴 연결을 개별 함수에서 닫지 않는다.
- `qa_repository` 적재 전에 `QASearchEngine.index_all()`을 수행한다.
- 작업 트리가 혼합돼 있을 수 있으므로 현재 범위와 무관한 DB·보고서·소스 파일은 수정·stage·삭제하지 않는다.

## 개발 규칙

- placeholder UI를 만들지 않는다. 미구현 기능은 API 오류를 이해 가능한 메시지로 전달한다.
- TypeScript에서 `any`를 피하고 구체적인 타입을 사용한다.
- `bare except` 대신 구체적 예외 처리를 사용한다. 비동기 작업은 직접 `asyncio.run()`보다 백그라운드 작업 또는 `asyncio.to_thread`를 선호한다.
- 변경 전 영향 파일과 검증 방법을 확인하고, 변경 후 범위 테스트와 `git diff --check`를 실행한다.

## Git 및 문서 관리

- 시작 시 `git status -sb`로 브랜치와 기존 사용자 변경을 확인한다.
- 혼합 작업 트리에서는 `git add -A`를 사용하지 않는다. 문서·소스 파일을 명시적으로 stage한다.
- 생성된 DB, 백업, lock 파일, 실행 로그, 대용량 감사 JSON, CSV export는 기본적으로 커밋 대상이 아니다.
  재현에 필요한 코드·테스트·문서만 의도적으로 커밋한다.
- 이 파일에는 안정적인 규칙과 탐색 진입점만 추가한다. 일회성 수치·실행 결과·긴 절차는 넣지 않는다.
- 결정 배경과 날짜별 변경은 `docs/operations_history.md`, 원본 증거와 감사 결과는 `reports/`에 둔다.
- 제안서·설계서·완료 보고서는 현재 동작의 규범이 아니므로 이 파일에서 재서술하지 않는다.

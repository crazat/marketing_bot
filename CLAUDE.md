# Marketing Bot 작업 맥락

> 이 파일은 모든 작업에서 먼저 읽을 최소 운영 맥락만 담는다. 상세 계약·명령·실행 이력은 아래 문서를 기준으로 한다.

## 문서 기준

- [운영 계약](docs/OPERATING_CONTRACTS.md): 현재 유효한 도메인·안전·데이터 정합성 규칙
- [운영 이력](docs/operations_history.md): 날짜별 변경 배경, 스캔 결과, 재발 방지 메모
- [터미널 실행 가이드](docs/TERMINAL_GUIDE.md): Pathfinder/Viral Hunter 및 DB 검증 명령

문서 간 충돌이 있으면 현재 동작을 정의하는 운영 계약과 코드·테스트를 우선 확인하고, 과거 결과는 이력으로만 취급한다.

## 프로젝트 지도

- 목적: 청주 중심 로컬 마케팅 키워드 탐색, 바이럴 후보 발굴, 안전한 실행 큐 관리
- 구성: FastAPI + SQLite 백엔드, React/TypeScript/Vite 프런트엔드
- AI 진입점: `marketing_bot_web/backend/services/ai_client.py`
- 핵심 흐름: `pathfinder_v3_legion.py` → `core_services/viral_seed_builder.py` →
  `viral_hunter.py` → `core_services/viral_handoff_audit.py`
- 운영 DB: `db/marketing_data.db`; 후보 상태·점수 근거는 `viral_targets`와 `score_breakdown`에서 확인

## 변하지 않는 운영 원칙

- 자동 게시·자동 답글 생성은 하지 않는다. 게시·승인은 Web UI 또는 Telegram HITL에서만 처리한다.
- `manual_review`, `needs_enrichment`, `filtered_out*`, `skipped`, `deleted`, `posted`를 자동 실행 큐로 되돌리지 않는다.
  영속 DB 상태가 메모리 상태보다 우선한다.
- 검색량·추출 수·rescue 가능성을 이유로 의료·지역·광고·시점·AI·최종 실행 게이트를 완화하지 않는다.
- 사용자 소유 결과·설정·프롬프트 정책은 명시적 승인 없이 바꾸지 않는다.
- 세부 카테고리, 지역, rescue, 실행 큐, 백업 규칙은 [운영 계약](docs/OPERATING_CONTRACTS.md)을 따른다.

## 표준 작업 흐름

- `scan_runs.status='completed'`인 Legion run만 Viral 입력으로 사용하고, 실행 시 `--source-scan-id`를 명시한다.
- 일반 순서는 `handoff audit → quality metric backfill → pending body enrichment → execution export reconciliation`이다.
- 감사 수율은 `audit_json.run_funnel`의 동일 런·동일 범위 지표로 분석한다. 영속 snapshot의 누계·재발견 수를 신규 기회나 실행 수율로 사용하지 않는다.
- AI가 `SUITABLE`로 확정되지 않은 후보는 실행하지 않는다. 최종 export·alert 전에는 DB 상태를 다시 읽는다.

## 변경·검증 안전

- DB 수정·복사·이동 전 SQLite Backup API 또는 `db_backup.py`로 백업하고, 임의 DML 대신 전용 스크립트·마이그레이션을 사용한다.
- `DatabaseManager` 싱글턴 연결은 개별 함수에서 닫지 않는다. `qa_repository` 적재 후에는 `QASearchEngine.index_all()`을 수행한다.
- Windows PowerShell 기준으로 작업한다. 변경 전 `git status -sb`와 영향 범위를 확인한다.
- 표적 테스트를 먼저 실행하고 `python -m pytest -q`, `git diff --check`로 마무리한다.
- 혼합 작업 트리에서는 `git add -A`를 사용하지 않고, 의도한 파일만 명시적으로 stage한다.
- DB·백업·lock·로그·대용량 감사 JSON·CSV 등 생성 산출물은 재현에 꼭 필요하지 않으면 커밋하지 않는다.

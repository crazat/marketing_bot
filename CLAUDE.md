# Marketing Bot 운영 메모

> 마지막 정리: 2026-07-12. 이 문서는 현재 작업에 필요한 계약과 운영 절차만 담는다.
> 과거 개선 이력은 [docs/operations_history.md](docs/operations_history.md), 상세 대화 메모는
> `C:\Users\craza\.claude\projects\C--Projects-marketing-bot\memory\MEMORY.md`를 참고한다.

## 변경 금지: 사용자 소유 바이럴 정책

- 바이럴 댓글은 실제 방문자 1인칭 경험담 톤을 사용한다. 예: “저도 규림한의원 다녀왔는데 좋았어요.”
- `규림한의원` 풀네임은 의도된 투명성 정책이다. 축약하거나 숨기지 않는다.
- `task="viral_comment"`는 AI 공개 footer와 1인칭 스트리핑을 적용하지 않는다.
- 1인칭 방문·효과 경험을 의료광고 위반으로 일괄 제거하지 않는다. 단정 효과, 할인·이벤트,
  의료진 추천, 비교, 전후 비교 같은 경성 위반은 계속 차단한다.
- 댓글 톤·페르소나·네이밍·프롬프트 변경은 사용자 확인 없이는 하지 않는다.
- 자동 게시와 자동 댓글 생성을 만들지 않는다. 게시·승인은 Web UI 또는 Telegram HITL에서만 처리한다.

## 변경 금지: Pathfinder → Viral Hunter 가드레일

- `SIGNATURE_ROUTING_AXES`와 `SIGNATURE_BACKLOG_AXES`는 같은 집합을 유지한다.
  현재 시그니처 축은 `흉터/여드름흉터`, `안면비대칭`이다.
- 교통사고 축은 고LTV 전략 판단 없이 자동 게이트로 차단하지 않는다.
- KIN은 provider-venue-author 게이트에서 의도적으로 제외한다. 질문자 author를 업체 author로 오인하지 않는다.
- 지역 판정은 substring-only가 아니라 `_has_active_region_anchor()`를 사용한다.
- `competitors.json`이 경쟁사 단일 소스다. 직접 수정하면 `prompts.json`과 동기화한다.
- 의미기반 발견은 `.env`의 `MARKETING_BOT_SEMANTIC_DISCOVERY=1`로 프로덕션 활성화돼 있다.
  테스트의 기본-off 격리(`tests/conftest.py`)를 제거하지 않는다.
- 검색 쿼리에 Pathfinder의 기계적 접미사 뭉치를 그대로 보내지 않는다.
  `normalize_seed_keyword_text()`와 `strip_transactional_suffix()`를 유지한다.
- `cost`/`availability` 렌즈는 질문 본문의 직접 route 신호가 없으면 community 추천 신호만으로 통과시키지 않는다.
- `reply_risk_flags` 또는 `score_breakdown.manual_review`가 있으면 자동 큐가 아니라
  `comment_status='manual_review'`로 격리한다.
- `filtered_out_stale_window`·명시적 광고·현재 거절 사유가 있는 글은 자동 rescue 하지 않는다.
  `skipped`/`deleted`는 수동 검토 후보일 뿐 자동 재큐 대상이 아니다.
- post-enrichment refill은 AI 예산을 보충하는 장치이며, final gate·timing gate를 완화하는 장치가 아니다.
- `base`/`community_base` 또는 query variant의 retire/repair 피드백은 실제 검색 예산에 반영한다.
  high-volume zero-yield lane을 최소 probe floor로 되살리지 않는다.

## 시스템 개요와 핵심 위치

- 목적: 규림한의원(청주)의 플레이스 순위·키워드·경쟁사·바이럴 리드 운영 자동화.
- 백엔드: FastAPI, SQLite. 프론트엔드: React/TypeScript/Vite. AI: `services/ai_client.py` 단일 진입점.
- 핵심 파이프라인: `pathfinder_v3_legion.py` → `core_services/viral_seed_builder.py` →
  `viral_hunter.py` → `core_services/viral_handoff_audit.py`.
- 핵심 DB: `db/marketing_data.db`. 바이럴 상태·점수는 `viral_targets`와 `score_breakdown`에 있다.
- 주요 코드:
  - `viral_hunter.py`: 검색, 필터, AI 분석, 실행 큐와 CSV export
  - `core_services/viral_seed_builder.py`: Pathfinder 시드 선택·카테고리/세부의도 균형
  - `core_services/viral_handoff_audit.py`: handoff 품질 진단과 다음 런 피드백
  - `db/database.py`: 바이럴 upsert와 실행 큐 영속화
  - `repositories/viral_target_repo.py`, `marketing_bot_web/backend/routers/viral.py`: UI 조회 계약

## 운영 명령 (Windows PowerShell)

```powershell
build_and_run.bat
python pathfinder_v3_legion.py --target 500 --save-db
python viral_hunter.py --scan --source-scan-id <scan_id>
python scripts/viral_handoff_audit.py --scan-id <scan_id> --out reports/<name>.json
python scripts/viral_quality_metric_backfill.py --scanned-since <ISO_TIMESTAMP> --apply
python scripts/enrich_pending_bodies.py --days 1 --limit 60 --dry-run
python -m pytest -q
```

- Windows 전용이다. WSL 종료·변경 명령은 사용하지 않는다.
- 5분 이상 걸리는 수집·감사는 백그라운드로 실행하고, 진행·완료를 확인한다.
- `scan_runs`는 `status='completed'`만 유효 결과로 취급한다. 실제 worker가 없는 오래된
  `running`은 사유를 남겨 `failed`로 정리한다.

## 바이럴 실행 큐 계약

- 자동 실행 가능 상태는 `pending`, `generated`, `approved`, `ai_approved`뿐이다.
- `auto_ready`는 본문·게시일·작성자·AI 검토 등 evidence 조건을 모두 충족해야 한다.
- `manual_review`는 별도 export이며 자동 알림·Tier-1 대상이 아니다.
- `needs_enrichment`은 실행 대상이 아니다. 본문 또는 날짜를 보강·재게이트한 뒤에만 승격한다.
- 영속 DB 상태가 in-memory 후보보다 항상 우선한다. 최종 export와 alert 전에 DB를 다시 읽어
  `filtered_out*`, `skipped`, `deleted`, `posted`를 제거한다.
- legacy CSV가 남아 있으면 다음으로 재정합한다. 원본은 감사 증적으로 보존한다.

```powershell
python scripts/reconcile_viral_execution_exports.py --timestamp <YYYYMMDD_HHMMSS>
```

## 품질·발견 운영 원칙

- `viral_scan_audits.pending_count`는 historical actionable 누계일 수 있다. 실제 작업량은
  `open_pending`/`open_execution_queue`, 신규 전환은 `fresh_pending`/`fresh_open_queue`로 판단한다.
- audit의 `metric_coverage` 부족은 먼저 backfill로 해소한다. backfill은 quality metric만 갱신하고
  `comment_status`를 바꾸지 않는다.
- 재발견 행의 최신성은 `COALESCE(last_scanned_at, discovered_at)` 기준이다.
  본문 보강도 이 기준으로 대상 선택한다.
- audit의 source-seed·variant feedback은 다음 Seed Builder/Viral Hunter 실행에 자동 반영된다.
  낮은 survival을 감추려고 필터를 완화하거나 차단 상태를 `pending`으로 되돌리지 않는다.
- 시드 quota는 카테고리뿐 아니라 치료 세부의도(`SEED_TREATMENT_SUBINTENT_BUCKETS`)도 분산한다.
  좁은 lane은 viable 후보가 하나일 때 soft fallback을 허용한다.

## DB 및 안전 규칙

- DB 파일 수정·복사·이동 전에는 반드시 SQLite Backup API 또는 `db_backup.py`로 백업한다.
- 일반 작업에서 임의 DML SQL을 실행하지 않는다. 데이터 수정은 백업·멱등성·dry-run을 갖춘
  마이그레이션/운영 스크립트로 수행한다.
- `DatabaseManager` 싱글톤 연결을 개별 함수에서 닫지 않는다.
- `qa_repository` 적재는 마이그레이션 스크립트로만 하고, 후속 `QASearchEngine.index_all()`
  재인덱스를 반드시 수행한다.
- 작업 트리가 더러울 수 있다. 현재 범위와 무관한 DB, 보고서, 스크린샷, 임시 파일은 수정·stage·삭제하지 않는다.

## 개발 규칙

- AI는 `marketing_bot_web/backend/services/ai_client.py`를 통해서만 호출한다.
- placeholder UI를 만들지 않는다. 구현되지 않은 기능은 숨긴다.
- API 오류는 사용자에게 이해 가능한 메시지로 전달한다.
- TypeScript에서 `any`를 피하고 도메인 타입을 사용한다.
- `bare except` 대신 `except Exception`을 사용하고, 비동기는 `asyncio.run()` 직접 호출 대신
  백그라운드 큐 또는 `asyncio.to_thread`를 사용한다.
- 코드 변경 전 영향 파일과 검증 방법을 파악하고, 작업 범위 테스트와 `git diff --check`를 실행한다.

## 대화 재개 체크리스트

1. `git status -sb`로 브랜치와 사용자 변경을 확인한다.
2. 최신 completed Legion run과 열린 바이럴 큐를 DB에서 확인한다.
3. 새 Viral 결과면 audit → metric backfill → body enrichment → export reconciliation 순으로 점검한다.
4. 테스트는 변경 범위부터 실행하고, 가능하면 관련 전체 suite를 실행한다.
5. 결과 보고에는 raw stdout 대신 검증 수치, 원인, 다음 액션만 간결히 담는다.

## 최신 기준선 (2026-07-12)

- Legion scan `109`는 target 500 이상을 만족했고 `9,237` keywords로 완료됐다.
- 후속 Viral Hunter 결과는 DB 상태 재정합 후 자동 실행 `2`, 수동 검수 `1`, 본문 보강 `15`건이다.
  legacy export 39건 중 차단·만료·삭제 상태 21건은 실행 후보에서 제거됐다.
- 최근 스캔 3,774건의 quality metric 누락 3,597건을 보강해 clinic/worksite metric coverage를
  `35.27% → 100%`로 개선했다.
- 최신 handoff audit은 `reports/viral_handoff_audit_scan109_improved_20260712.json`이다.
  metric backfill 필요는 해소됐고, 남은 낮은 survival/strict-fit은 안전 게이트를 우회하지 않고
  다음 런의 source-seed·variant feedback으로 개선한다.
- 이번 범위 검증: `python -m pytest -q` 관련 491개 통과.

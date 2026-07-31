# Persistent Memory — 2026-07-23 Scan #124 hardening

- Legion #124 completed the bounded 500+ pipeline (2,619 total; 59 S / 736 A).
  Viral Hunter must consume the fixed completed source scan and never publish or
  generate comments automatically.
- A rediscovered URL with no usable current SERP date must reuse a valid stored
  `viral_targets.posted_at` before the final timing gate. Expired posts must be
  persisted as `filtered_out_stale_window`, without inflating scan/freshness
  counters.
- Source-seed audit reports are deduplicated by `source_scan_run_id`. Aggregate
  only zero-fit negative evidence from distinct scans; a prior confirmed fit
  keeps the seed as a ranked repair candidate and prevents automatic retirement.
- Validate this handoff with `python -m pytest tests/test_pathfinder_viral_stability.py -q`
  and inspect the staged allowlist before publishing in a mixed worktree.

# Persistent Memory — 2026-07-24 Scan #125 zero-yield patient-voice gate

- Legion #125 completed the bounded 500+ pipeline with 869 S/A results.
  Viral Hunter must keep the completed source scan fixed, and its immutable
  `viral_scan_audits.run_funnel` is the only current-run conversion record.
  Do not evaluate the run from a rediscovery-inclusive `viral_targets` snapshot.
- The #125 Viral funnel was 5,263 collected, 581 post-filter, 45 after existing
  URL deduplication, 22 after enrichment, 1 AI-suitable, and 0 auto-ready.
  Treat this as a seed-quality and deduplication bottleneck, not a reason to
  weaken final execution gates or authorize posting/comments.
- A patient-voice variant with one completed run, at least 500 discovered and
  120 genuinely fresh rows, and no pending/fresh-pending survivor is proven
  zero-yield for the gate. Block it before it consumes a second full run; the
  #115 profile (543 discovered, 149 fresh, zero survivors) otherwise repeated
  as #125's 1,217 discoveries with zero strict fits.
- Validate this behavior with `python -m pytest tests/test_pathfinder_viral_stability.py -q`,
  `python -m py_compile viral_hunter.py`, and a scoped `git diff --check`.
  Re-measure the change only on the next fresh completed Legion source scan,
  not by re-running the rediscovery-biased #125 input.

# Persistent Memory — 2026-07-25 Scan #126 execution-context and priority-stability gate

- After a completed Legion run, keep the fixed `--source-scan-id`; #126 produced
  2,670 keywords (45 S / 783 A), and Viral audit #55 recorded
  `2,603 collected -> 426 filtered -> 54 novel after URL dedup -> 12 AI-suitable
  -> 10 final`. Analyze this immutable funnel, not `viral_targets` refresh
  totals. A 90.1% existing-URL exclusion rate is a novelty/query-surface
  bottleneck, not justification to weaken gates.
- Final `auto_ready` requires full evidence plus both
  `clinic_treatment_fit_score >= 55` and `journey_fit_score >= 55`. Discovery
  can retain weaker matches for review, but they must be `context_review` /
  `needs_enrichment`, never automatic execution. #126's scan-time 4/2/4 queue
  became current 3 auto-ready / 2 manual-review / 5 needs-enrichment after this
  safe reconciliation; the original audit remains immutable.
- `_sync_execution_quality()` can run during persistence/reload reconciliation.
  Use stored pre-quality priority only when current priority still equals the
  recorded post-quality value, so evidence multipliers are idempotent; a true
  upstream re-score remains a new baseline. Validate a repeat replay leaves
  priorities unchanged, use `DatabaseManager.update_viral_execution_queue()`
  only for the exact queue scope, make an SQLite online backup first, and run
  `PRAGMA integrity_check`.

# Persistent Memory — 2026-07-26 Scan #128 quality-backfill execution contract

- Legion #128 completed the bounded 500+ handoff with 2,643 total keywords
  (52 S / 786 A; 838 S/A). Viral audit #56's immutable funnel was
  `2,836 collected -> 394 filter survivors -> 52 novel after URL dedup ->
  20 AI-suitable -> 17 final` (4 auto-ready / 4 manual-review / 9 needs-
  enrichment). Compare this audit payload with the same-scope #126 funnel;
  never infer run conversion from the 2,162-row rediscovery-inclusive target
  snapshot.
- Run `quality metric backfill` after the handoff audit. On #128 it raised
  clinic/worksite score coverage from 18.22% to 100% without changing any
  `comment_status` or generating/posting comments. Persist the full execution
  contract: contextual-fit fields, queue status and actionable flag, quality
  fields, and priority-cap fields.
- A final contract can be stale even when all old score keys exist. The
  backfill must load the intended scope then use the exact Python predicate:
  recompute when stored `execution_queue_status` or its actionable flag differs
  from the persisted target state. When repair is needed, force the complete
  execution-quality merge so a filtered row cannot retain `auto_ready=true`.
  Make an SQLite backup, dry-run first, verify `PRAGMA integrity_check`, status
  counts, zero queue-status mismatches, and zero non-actionable auto-ready rows.
  Validate with `python -m pytest tests/test_viral_quality_metric_backfill.py
  tests/test_viral_handoff_audit.py -q` and stage only source, test, and this
  memory file in the mixed worktree.

# Persistent Memory — 2026-07-27 Scan #129 pinned-source fail-closed handoff

- Legion #129 completed the bounded 500+ handoff with 2,581 total keywords
  (37 S / 746 A; 783 S/A). Viral audit #57's immutable funnel was
  `3,897 collected -> 383 filter survivors -> 34 novel after URL dedup ->
  14 AI-suitable -> 9 final` (2 auto-ready / 1 manual-review / 6 needs-
  enrichment). The 94.3% existing-URL exclusion rate is a query-surface
  novelty bottleneck, not authorization to weaken quality gates or publish.
- An explicitly requested `--source-scan-id` is a lineage contract: if the
  completed Pathfinder source has no eligible Viral seeds,
  `ViralHunter._load_keywords()` must raise instead of falling back to legacy
  keywords. `ViralHunter.hunt()` must resolve that pinned source before pending
  TTL cleanup, so an invalid handoff cannot mutate unrelated pending rows.
- Validate this contract with `python -m pytest
  tests/test_pathfinder_viral_stability.py -q`, `python -m py_compile
  viral_hunter.py`, scoped `git diff --check`, and `PRAGMA integrity_check`.
  Scan outputs remain review-only; do not automatically re-run, comment,
  publish, or create ads after a code-only repair.

# Marketing Bot 작업 맥락

## Persistent Memory — 2026-07-22 Scan #123

- Legion scan #123 satisfied the 500+ operational target with 645 S/A keywords
  (47 S, 598 A; 2,521 total). Interpret current-run performance from immutable
  `viral_scan_audits.run_funnel`, not the rediscovery-inclusive snapshot.
- Viral Hunter #123 ended at 12 execution candidates. Post-run QA quarantined
  one stale `pending` item whose `여성/산후` lineage did not match its knee-care
  question; the current queue is 11 (3 auto-ready, 8 needs enrichment).
- The profile-axis mismatch safeguard applies only to seed categories that map
  to the broad `general` domain. Focused domains keep cross-axis rescue; scar
  and skin remain compatible.
- `DatabaseManager.update_viral_execution_queue()` can persist a deterministic
  final-gate rejection without increasing `scan_count` or freshness metrics.
- Remaining operating risk: multi-source verification was 12.26%, below the
  20% source-health guard. Treat this as upstream source-yield work, not a
  missed Legion target.

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

# Persistent Memory - 2026-07-28 Scan #130 deep audit and scoped Cafe enrichment

- Legion #130 completed with 2,530 keywords (38 S / 729 A; 767 S/A) and Viral
  audit #58 consumed the explicit `--source-scan-id 130`. Its immutable funnel
  was `3,722 collected -> 1,148 filter input -> 378 survivors -> 34 novel ->
  22 after enrichment -> 13 AI-suitable -> 8 final`; all eight were
  `needs_enrichment`, with no auto-ready or manual-review execution item.
- Treat the 351 existing-URL exclusions from 378 survivors as a query-surface
  novelty bottleneck, and the 50.1% lens-surface mismatch as planning feedback;
  do not weaken quality gates or infer conversion from the 2,952-row persisted
  target snapshot. Generate a scoped handoff audit so its seed/variant repair
  and retirement feedback is available to the next fresh run.
- `scripts/enrich_cafe_bodies.py --scan-id <run_id>` must constrain Selenium
  evidence collection to that source lineage. Perform a dry-run first and make
  an online SQLite backup before an actual run. It may update only body/preview
  evidence, `last_scanned_at`, and `scan_count`; it must never change statuses,
  AI decisions, comments, or publication. For #130, 2/8 scoped Cafe bodies were
  recovered while six inaccessible posts remained unchanged.
- Validate the scoped enrichment guard with
  `python -m pytest tests/test_enrich_cafe_bodies.py tests/test_viral_handoff_audit.py -q`,
  the full Pathfinder/Viral stability suite, `py_compile`, scoped diff checks,
  and SQLite integrity/FK checks. Keep DBs, backups, logs, and audit reports
  out of commits in this mixed worktree.

# Persistent Memory - 2026-07-29 Scan #131 handoff diagnosis and metric repair

- Legion #131 completed with 2,524 keywords (33 S / 679 A; 712 S/A), and Viral
  audit #59 consumed the explicit `--source-scan-id 131`. Its immutable funnel
  was `2,759 collected -> 1,065 filter input -> 352 survivors -> 29 novel ->
  21 after enrichment -> 1 AI-suitable -> 0 final execution`. Treat the 332
  existing-URL exclusions (94.3% of filter survivors) as a novelty/query-shape
  bottleneck, never as permission to lower quality, safety, or execution gates.
- The 2,046-row handoff-audit scope contains refreshed/rediscovered historical
  targets. Its 7 surviving and 3 strict-fit rows are not #131 run conversions;
  use `viral_scan_audits.audit_json.run_funnel.final_execution_candidates` for
  current-run outcome. Do not immediately re-run the same source scan merely to
  improve this number.
- Run quality-metric repair only after a scoped handoff audit. First dry-run
  `scripts/viral_quality_metric_backfill.py --scan-id 131 --scanned-since
  <run-start>`, make an online SQLite backup, then apply the identical scope.
  The #131 repair synchronized 1,886 missing execution-quality contracts,
  raising clinic/worksite coverage from 17.2% to 100% without changing
  `comment_status`, publishing, comments, or requeueing. Verify backup-vs-live
  status counts, zero actionable execution rows, `PRAGMA integrity_check`, and
  `PRAGMA foreign_key_check` after the write; quality-score improvement alone
  is not yield improvement.
- Generate and retain the post-backfill scoped handoff audit. The next fresh
  planner loads its variant feedback: #131 marked the zero-strict-fit
  `axis_specific` family (234 rows) for retirement/pause and `community_base`
  (260 rows) for query-shape repair. Apply that evidence only to the next fresh
  scan; never auto-requeue discarded/manual-review rows or weaken gates to
  manufacture execution candidates.
- Validate this workflow with
  `python -m pytest tests/test_viral_quality_metric_backfill.py
  tests/test_viral_handoff_audit.py -q`, scoped diff checks, and explicit
  allowlist staging. Keep database files, backups, locks, audit JSON, report
  artifacts, and screenshots out of the commit.

# Persistent Memory - 2026-07-30 Scan #132 partial AI-response recovery

- Legion #132 completed with 2,491 keywords (30 S / 766 A; 796 S/A), and Viral
  audit #60 consumed the explicit `--source-scan-id 132`. Its immutable funnel
  was `3,362 collected -> 1,220 filter input -> 459 survivors -> 45 novel after
  426 existing-URL exclusions -> 72 AI candidates -> 14 after enrichment -> 1
  AI-suitable -> 0 final execution`. This is a novelty/recency and query-shape
  bottleneck, never a reason to weaken final quality, safety, or execution
  gates; use the next fresh source scan to evaluate query-shape repair.
- A structured multi-post AI response may contain valid early decisions while
  omitting later `POST_ID`s. Preserve parsed decisions, retry each omitted post
  once with a single-post prompt, and leave a second incomplete result as
  `needs_ai_retry`; do not convert parser failure into AI rejection or an
  execution candidate. A later complete suitable verdict must resolve
  `needs_ai_retry` to `pending`, remove stale parse-error markers, and still
  pass every final gate.
- For a scoped retry recovery, make an SQLite online backup first and select the
  exact source lineage plus `missing_or_invalid_post_result`; do not refresh
  unrelated backlog. #132 reprocessed nine such rows to four explicit AI
  rejections, three pending, and two manual-review items, with zero auto-ready
  rows and no comments or publication. The original audit remains the
  authoritative current-run record.
- Validate with `python -m pytest tests/test_pathfinder_viral_stability.py -q`,
  `python -m py_compile viral_hunter.py`, scoped `git diff --check`, and
  `PRAGMA integrity_check` plus `PRAGMA foreign_key_check`. Keep DBs, backups,
  locks, logs, and generated audit reports out of the commit.

# Persistent Memory - 2026-07-31 Scan #133 funnel diagnosis and scoped quality repair

- Legion #133 completed with 2,502 keywords (40 S / 605 A; 645 S/A), and Viral
  audit #61 consumed the explicit `--source-scan-id 133`. Its immutable funnel
  was `2,635 collected -> 1,038 filter input -> 379 survivors -> 23 novel after
  368 existing-URL exclusions -> 13 after enrichment -> 6 AI-suitable -> 2
  final execution`. Use `viral_scan_audits.audit_json.run_funnel` for this
  conversion; do not mix it with the 1,976-row current `viral_targets` snapshot.
- The 97.1% existing-URL exclusion rate (368/379) and zero survival in several
  high-volume axis variants are novelty/query-shape findings, not authority to
  lower gates, auto-requeue discarded/manual-review rows, post comments, or
  publish. The #133 post-backfill audit supplies next-fresh-run feedback: pause
  the zero-survival `모공흉터`, `지루성피부염`, `골반교정`, and `얼굴교정` variants;
  keep lower-volume repair variants budgeted and re-evaluate only on a new scan.
- Run `scripts/viral_quality_metric_backfill.py` only after the scoped handoff
  audit, with `--scan-id` and `--scanned-since`, a dry-run, and an online SQLite
  backup. For #133, the identical-scope apply repaired 1,751 quality contracts,
  lifting clinic/worksite coverage from 19.18% to 100% while leaving the target
  count and `comment_status` distribution unchanged. A zero-update repeat
  dry-run is required evidence of idempotence; score-contract repair is not a
  yield or execution-authority improvement.
- Validate with `python -m pytest tests/test_viral_quality_metric_backfill.py
  tests/test_viral_handoff_audit.py -q`, backup-versus-live status counts, zero
  contract mismatches, `PRAGMA integrity_check`, and `PRAGMA foreign_key_check`.
  Preserve DBs, backups, logs, audit JSON, report artifacts, and screenshots in
  the mixed worktree; stage only the explicit source/test/documentation allowlist.

# Persistent Memory - 2026-07-31 novelty-depth recovery

- Audit #61 proved that the next yield repair belongs before the final quality
  gates: 368 of 379 filter survivors were existing URLs. The live 24-hour search
  cache also had 99 depth-agnostic entries, all below 100 results (maximum 42),
  so a shallow companion search could silently cap a later 100/180-result plan.
- Cache Naver search results by platform plus requested depth. When a unique
  high-priority query plan returns at least 20 URLs and 75% are already persisted
  or already seen in the current run, probe below the first-pass depth while
  excluding those URL identities. Bound this novelty backfill to 60 query plans,
  60 candidates per platform, and three pages per sort; persist its eligible
  plans, triggered plans, overlap, returned candidates, and extra API requests
  in `viral_scan_audits.audit_json.run_funnel`.
- `--max-per-platform` controls the base depth before adaptive scaling; the
  default remains 100 and a deliberate deeper run can use 200. This increases
  time and API work only; it must not lower deterministic, medical, AI, evidence,
  or execution gates, nor authorize comment generation or publication.
- Validate with the full Pathfinder/Viral stability suite, the handoff-audit and
  quality-backfill suites, `py_compile`, and `git diff --check`. Measure actual
  yield only on the next fresh completed Legion source with an explicit
  `--source-scan-id`; do not rerun #133 or reinterpret its immutable audit.

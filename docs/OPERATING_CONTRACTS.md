# Marketing Bot 운영 계약

이 문서는 `CLAUDE.md`의 요약을 보완하는 현재 유효한 운영 계약이다. 여기의 규칙은
구현·프롬프트·데이터 정합성 변경 시 함께 검토한다. 날짜가 붙은 판단과 과거 변경은
[운영 이력](operations_history.md)에 둔다.

## 사용자 소유 바이럴 정책

- 바이럴 댓글은 실제 방문자 1인칭 경험담 톤을 사용한다.
- `규림한의원` 풀네임은 의도된 투명성 정책이므로 축약하거나 숨기지 않는다.
- `task="viral_comment"`에는 AI 공개 footer와 1인칭 스트리핑을 적용하지 않는다.
- 1인칭 방문·효과 경험을 의료광고 위반으로 일괄 제거하지 않는다. 단정 효과, 할인·이벤트,
  의료진 추천, 비교, 전후 비교 같은 경성 위반은 계속 차단한다.
- 댓글 톤·페르소나·네이밍·프롬프트 변경은 사용자 확인 없이 하지 않는다.
- 자동 게시와 자동 댓글 생성을 만들지 않는다. 게시·승인은 Web UI 또는 Telegram HITL에서만 처리한다.

## Pathfinder → Viral Hunter 가드레일

- `SIGNATURE_ROUTING_AXES`와 `SIGNATURE_BACKLOG_AXES`는 같은 집합을 유지한다.
- 교통사고 축은 고LTV 전략 판단 없이 자동 게이트로 차단하지 않는다.
- 교통사고 후보는 `교통사고`, `자동차사고`, 과실, 보험, 충돌 등 사고 고유 의도가 있는 시드만 허용한다.
  단순 `입원`, `병원` 등의 모호한 시드는 Pathfinder와 Viral 최종 게이트에서 차단한다.
- KIN은 provider-venue-author 게이트에서 제외한다. 질문자 author를 업체 author로 오인하지 않는다.
- 지역 판정은 substring-only가 아니라 `_has_active_region_anchor()`를 사용한다.
- `competitors.json`이 경쟁사 단일 소스다. 직접 수정하면 `prompts.json`과 동기화한다.
- 프로덕션 semantic discovery 설정(`MARKETING_BOT_SEMANTIC_DISCOVERY=1`)과 테스트 기본-off
  격리(`tests/conftest.py`)를 유지한다.
- 검색 쿼리에 Pathfinder의 기계적 접미사 뭉치를 보내지 않는다. `normalize_seed_keyword_text()`와
  `strip_transactional_suffix()`를 유지한다.
- `cost`/`availability`는 질문 본문의 직접 route 신호 없이 community 추천만으로 통과시키지 않는다.
- `reply_risk_flags` 또는 `score_breakdown.manual_review`가 있으면 `comment_status='manual_review'`로 격리한다.
- `filtered_out_stale_window`, 명시적 광고, 현재 거절 사유가 있는 글은 자동 rescue하지 않는다.
  `skipped`/`deleted`는 수동 검토 후보일 뿐 자동 재큐 대상이 아니다.
- post-enrichment refill은 AI 예산 보충 장치이며 final gate·timing gate를 완화하지 않는다.
- `base`/`community_base` 및 query variant의 retire/repair 피드백은 실제 검색 예산에 반영한다.
  high-volume zero-yield lane을 최소 probe floor로 되살리지 않는다.
- curated Viral 실행은 기본적으로 S/A seed를 우선하고, 같은 카테고리에 S/A seed가 없을 때만 B 등급을 보완한다.

## 바이럴 실행 큐 계약

- 자동 실행 가능 상태는 `pending`, `generated`, `approved`, `ai_approved`뿐이다.
- `auto_ready`는 본문·게시일·작성자·AI 검토 등 evidence 조건을 모두 충족해야 한다.
- `manual_review`는 별도 export이며 자동 알림·Tier-1 대상이 아니다.
- `needs_enrichment`는 실행 대상이 아니다. 본문 또는 날짜를 보강·재게이트한 뒤 승격한다.
- 영속 DB 상태가 in-memory 후보보다 우선한다. 최종 export·alert 전에 DB를 다시 읽어
  `filtered_out*`, `skipped`, `deleted`, `posted`를 제거한다.
- legacy CSV는 감사 증적으로 보존하되, 필요하면 다음 명령으로 DB와 재정합한다.

```powershell
python scripts/reconcile_viral_execution_exports.py --timestamp <YYYYMMDD_HHMMSS>
```

## 품질·발견 계약

- `viral_scan_audits.pending_count`는 historical actionable 누계일 수 있다. 실제 작업량은
  `open_pending`/`open_execution_queue`, 신규 전환은 `fresh_pending`/`fresh_open_queue`로 판단한다.
- `viral_scan_audits.summary`의 discovered/pending 수에는 재발견과 과거 pending 행이 포함될 수 있다.
  신규 기회는 `fresh_discovered`/`fresh_pending`으로 분리하고, 실행 수율의 분모로 persisted snapshot을 사용하지 않는다.
- 런 단위 수율은 `audit_json.run_funnel`의 불변 단계 카운트를 사용한다. enrichment 이후 AI 후보가
  줄어들면 first-pass 생존자, 일반 backlog refill, discarded-backlog refill을 별도 지표로 유지한다.
- `metric_coverage` 부족은 먼저 backfill로 해소한다. backfill은 quality metric만 갱신하고
  `comment_status`를 바꾸지 않는다.
- 재발견 최신성은 `COALESCE(last_scanned_at, discovered_at)` 기준이며 본문 보강도 같은 기준을 사용한다.
- source-seed·variant feedback은 다음 실행에 반영한다. 낮은 survival을 감추기 위해 필터를 완화하거나
  차단 상태를 `pending`으로 되돌리지 않는다.
- handoff audit 파일이 여러 개면 `source_scan_run_id`별 최신 snapshot만 variant feedback 입력으로 사용한다.
- 콘텐츠 카테고리 detector가 빈 값을 반환하면 `기타`로 간주하지 않는다. 관측된 두 카테고리가 있고
  profile이 유효할 때만 category drift mismatch를 계산한다.
- 시드 quota는 카테고리와 치료 세부의도(`SEED_TREATMENT_SUBINTENT_BUCKETS`)를 분산한다.
  좁은 lane은 viable 후보가 하나일 때만 soft fallback을 허용한다.

## DB 안전 계약

- DB 파일 수정·복사·이동 전 SQLite Backup API 또는 `db_backup.py`로 백업한다.
- 일반 작업에서 임의 DML SQL을 실행하지 않는다. 데이터 변경은 백업·멱등성·dry-run을 갖춘
  마이그레이션/운영 스크립트로 수행한다.
- `DatabaseManager` 싱글톤 연결은 개별 함수에서 닫지 않는다.
- `qa_repository` 적재는 마이그레이션 스크립트로만 하고, 후속 `QASearchEngine.index_all()`을 반드시 수행한다.

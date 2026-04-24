# 감사 리포트

## `empty_tables_20260424.json`
DB 119개 테이블 중 72개가 0건. 모두 코드에서 최소 1회 참조되므로 자동 DROP 불가.

- `never_referenced`: 0개 (모두 참조 있음)
- `low_referenced`: 17개 (참조 1~3건, 모니터링)
- `keep`: 55개 (참조 4+건, 기능은 있으나 데이터 미수집)

## `unimplemented_tables_20260424.json`
위 72개 중 **미구현 기능으로 추정되는 31개** 목록. 다음 중 하나 선택:

1. **기능 구현**: `ab_experiments`, `campaigns`, `agent_actions` 등 실제 기능 추가
2. **스키마 제거**: 미사용 확정 시 db_init.py에서 CREATE 제거
3. **현상 유지**: 다음 분기에 재검토

### 주의: 최근 구현된 것 제외 필요
- `viral_adaptive_penalties`, `viral_skip_reasons`: 2026-04 D2 기능, 스캔이 진행되면 데이터 쌓임
- `competitor_viral_mentions`, `medical_platform_reviews`: 외부 API 키 복구 대기

### 안전한 정리 순서
1. 한 분기(90일) 데이터 수집 기다림
2. 여전히 0건인 테이블 → `DROP TABLE`
3. `db_init.py`의 `CREATE TABLE IF NOT EXISTS` 제거
4. `schema_migrations`에 `"v2026.07_drop_unused"` 같은 마이그레이션 기록

## 권장
- **이번 세션에서는 실제 스키마 변경 없음** (최근 구현 기능이 섞여 있어 위험)
- 다음 분기 재감사 후 결정

## [Y1] 17개 미구현 테이블 일시 DROP 수행 (2026-04-24)
`safe_to_drop_20260424.json` 참조 — INSERT 경로 0건 확정 17개를 실제 DROP.
`schema_migrations`에 `drop_unimplemented_v2026_04_24` 기록.

**주의**: db_init.py의 `CREATE TABLE IF NOT EXISTS`가 다음 앱 기동 시 재실행되어
빈 테이블이 자동 복구됨. 영구 제거하려면 다음 작업 필요:

1. `marketing_bot_web/backend/services/db_init.py` 편집
2. 17개 테이블 각각의 `CREATE TABLE IF NOT EXISTS <테이블>` 블록 제거 또는 주석
3. `db/database.py`의 `influencer_collaborations` CREATE 블록 제거

영구 제거 목록은 `safe_to_drop_20260424.json`의 `safe_to_drop` 배열 참조.


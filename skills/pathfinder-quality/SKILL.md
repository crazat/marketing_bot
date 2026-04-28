---
name: pathfinder-quality
description: keyword_insights의 garbage S/A 키워드를 일괄 강등하거나 naver_ad_keyword_data를 수동 갱신. search_volume=0인데 grade=S 같은 등급 인플레와 광고 데이터 노화로 인한 신뢰도 부족 해결.
license: Internal
---

# Pathfinder Quality — 키워드 품질 백필 + 광고 데이터 갱신

`backfill_low_quality_grades.py`로 신뢰도 부족 키워드를 C급 강등하거나, `refresh_ad_data.py`로 네이버 광고 키워드 데이터(검색량/경쟁)를 갱신. 둘 다 cron 안 쓰고 운영자 수동 트리거.

## When to use

- "garbage 정리" / "S급 검색량 0 인 거 정리" / "등급 인플레 정리"
- "저품질 키워드 강등"
- "광고 데이터 갱신" / "ad_keyword 다시 수집"
- "검색량 데이터 오래됐어"
- Pathfinder UI에서 "이상한 S급 너무 많아" — 백필이 root cause

## Decision tree

```
사용자 의도 → 도구 선택
─────────────────────────────────
"garbage" / "강등" / "저품질"      → backfill_low_quality_grades.py
"검색량 신뢰도" / "ad_keyword"      → refresh_ad_data.py
명시 X + S급 이상 많아 보이면       → backfill 먼저 (즉효, dry-run으로 검증)

backfill 모드 선택:
"명백한 garbage만"                 → --mode=conservative (search_volume<50)
"공격적 정리" / "SERP 미분석도"      → --mode=strict
명시 X                              → conservative (안전한 디폴트)
```

## Commands

```bash
# === Backfill (등급 강등) ===

# 보수 dry-run (search_volume<50만, 명백한 garbage)
python scripts/backfill_low_quality_grades.py

# 공격 dry-run (SERP 미분석 의심도 포함)
python scripts/backfill_low_quality_grades.py --mode=strict

# 실제 적용
python scripts/backfill_low_quality_grades.py --apply
python scripts/backfill_low_quality_grades.py --mode=strict --apply

# === Ad data 갱신 ===

# 상태만 확인 (마지막 갱신 일자 + age)
python scripts/refresh_ad_data.py --status

# 실제 갱신 (네이버 광고 API 호출)
python scripts/refresh_ad_data.py
```

## Workflow

### Backfill 흐름

1. **dry-run 먼저, mode 두 개 다 보여주기**
   ```bash
   python scripts/backfill_low_quality_grades.py            # conservative
   python scripts/backfill_low_quality_grades.py --mode=strict
   ```
   영향 건수 차이를 사용자에게 비교 제시: "보수 N건 vs 공격 M건. 어느 쪽으로 갈까요?"

2. **DB 백업 확인** — `--apply` 전:
   ```bash
   python -c "
   import os, time
   d = 'db/backups'
   files = sorted([f for f in os.listdir(d) if 'marketing_data' in f], reverse=True)
   if files:
     last = os.path.getmtime(os.path.join(d, files[0]))
     print(f'마지막 백업: {files[0]} ({(time.time()-last)/3600:.1f}시간 전)')
   "
   ```
   24시간 이상 묵었으면 `python db_backup.py` 권장.

3. **--apply 실행** — 사용자 명시 동의 후.

4. **사용자 보고** + 후속 액션 제안 (UI 영향, Pathfinder 재발굴 권장 등)

### Refresh ad data 흐름

1. **--status로 age 확인** — 40일 이상이면 갱신 권장 강도 높임.
2. **소요 시간 안내** — 광고 API 호출 (300+ 키워드 기준 5~15분).
3. **갱신 후** Pathfinder 재발굴 권장 — 새 search_volume 반영해야 등급 산정 정확.

## 보고 템플릿

### Backfill 결과
```markdown
**저품질 키워드 강등 완료** (mode=[conservative|strict])

**영향 건수**
- S → C: N건
- A → C: N건
- B → C: N건
- 총: M건

**샘플 강등 사유**
- "청주XXX" — search_volume=10, KEI=0 (검색량 신뢰도 부족)
- "청주YYY" — difficulty=0 (SERP 미분석 의심)

**Pathfinder UI 영향**
- 디폴트 필터(max_age_days=60 + search_volume>=50) 하에서는 자동으로 안 보임
- "60일 이상 묵은 키워드 포함" 토글 켜야 강등된 키워드 노출

**다음 액션**
- 새 발굴로 빈 자리 채우기: `/scan-pathfinder` (또는 "키워드 발굴해줘")
- 광고 데이터가 40일+ 묵었으면 갱신 권장: `/pathfinder-quality refresh ad data`
```

### Refresh ad data 결과
```markdown
**광고 키워드 데이터 갱신 완료** (소요 X분)

**변화**
- 갱신 전: 457행, 마지막 2026-03-18 (40일 전)
- 갱신 후: M행, 마지막 YYYY-MM-DD (오늘)
- 신규 N행 추가 / 기존 K행 업데이트

**다음 액션**
- 새 search_volume 반영하려면 Pathfinder 재발굴 필요
- 직전 발굴이 N일 전 → "키워드 재발굴해줘" 트리거 권장
```

## Guardrails

1. **--apply 전 dry-run 필수** — backfill은 grade='C' UPDATE 영구 변경. 사용자 명시 동의 받기.
2. **DB 백업 24h 이내** — backfill --apply 전 확인. 묵었으면 백업 먼저.
3. **mode 디폴트는 conservative** — strict는 사용자가 명시적으로 요청한 경우에만 추천.
4. **Pathfinder UI 동시 사용 회피** — backfill 중 운영자가 Pathfinder 페이지에서 작업 중이면 보이는 키워드가 갑자기 바뀜. 평일 업무시간이면 확인.
5. **광고 API 할당량** — refresh_ad_data는 네이버 광고 API 호출. 일일 할당량 있으면 동시 다른 작업 회피.
6. **legion 스캔과 동시 회피** — Pathfinder legion 모드 돌고 있으면 keyword_insights 동시 INSERT/UPDATE 충돌 가능. 직전 5분 내 legion 실행 여부 점검.

## 출력 길이

- 영향 건수 표는 한 표로 압축
- 강등 사유 샘플 3건 이내
- 다음 액션 1~2개

## 관련 파일/테이블

- `scripts/backfill_low_quality_grades.py` (신규, Q7)
- `scripts/refresh_ad_data.py` (신규, Q9)
- `scrapers/naver_ad_keyword_collector.py` (refresh가 호출)
- `keyword_insights` 테이블 (UPDATE: grade)
- `naver_ad_keyword_data` 테이블 (UPSERT)
- 디폴트 게이트 적용 위치: `pathfinder_v3_complete.py:1199-1230`, `pathfinder_v3_legion.py:1817-1822`
- UI 필터: `routers/pathfinder.py::get_keywords` (max_age_days=60, include_low_volume=False)

---
name: clinic-lifecycle
description: 한의원 인허가 라이프사이클 추적 — localdata.go.kr 신규 개원·폐업 + HIRA 환자수·진료비 + 정부 정책 시드 키워드 등록. 청주권 한의원 시장 변화를 공공 데이터로 즉시 감지.
license: Internal
---

# Clinic Lifecycle — 인허가·정부 정책 시드

청주권 한의원 시장의 외부 신호 3가지를 동시 추적: (1) 행정안전부 LOCALDATA로 인허가 변동, (2) 심평원 HIRA로 한의원 기본정보·환자수, (3) 정부 정책(어르신 한의 주치의 + 첩약 보험 2단계) 시드 키워드 자동 등록.

## When to use

- "신규 한의원 개원" / "폐업 / 이전" / "인허가 변동"
- "청주 한의원 몇 곳" / "HIRA 데이터" / "심평원 통계"
- "정부 정책 키워드" / "어르신 주치의" / "첩약 보험"
- "정부 시드 키워드 등록"
- 명시 X — 월 1-2회 정기 점검 (청주 한의원 시장 변화 모니터)

## Decision tree

```
사용자 의도 → 도구
─────────────────────────────────
"신규/폐업/인허가"            → localdata_clinic_tracker.py
"HIRA / 심평원 / 한의원 수"    → hira_api_client.py
"정부 정책 / 시드 / 어르신"    → seed_government_keywords.py
"전부 점검"                    → 3개 순차 (status 먼저)
```

## Commands

```bash
# === R3-1 LOCALDATA 인허가 ===
python scrapers/localdata_clinic_tracker.py --status
python scrapers/localdata_clinic_tracker.py --region "청주" --service-type 한의원
python scrapers/localdata_clinic_tracker.py --since 2026-04-01
python scrapers/localdata_clinic_tracker.py --dry-run

# === R3-7 HIRA 활성화 ===
python scrapers/hira_api_client.py --status
python scrapers/hira_api_client.py --region "충북" --sigungu "청주시" --type 한의원
python scrapers/hira_api_client.py --year 2025
python scrapers/hira_api_client.py --dry-run

# === R3-6 정부 시드 키워드 ===
python scripts/seed_government_keywords.py --status
python scripts/seed_government_keywords.py
python scripts/seed_government_keywords.py --dry-run
```

## Workflow

1. **--status 먼저** — 세 도구 모두 status 모드 지원. 데이터 양·최근 갱신일 확인.
2. **LOCALDATA = 빠른 변동 감지** — 7일 이내 신규 개원·폐업이 핵심 신호. 검출 시 `competitor_change_detector.py` 후속 검토 안내.
3. **HIRA = 정합성 데이터** — 청주 한의원 약 250-280곳 baseline. ±10건 변동 시 LOCALDATA로 교차 검증.
4. **정부 시드 = 1회 실행 충분** — 첩약 보험 추가 질환 발표 시 GOVERNMENT_SEEDS 리스트 업데이트 후 재실행.

## 보고 템플릿

```markdown
**한의원 인허가 라이프사이클** (수집 X분)

**신규 변동 (최근 7일)**
- 청주 [한의원명] 개원 (2026-04-XX) — 주소 [...]
- 청주 [한의원명] 폐업 (2026-04-XX)

**HIRA 청주 한의원 현황**
- 전체: N곳 (직전 +/-N)
- 카테고리별: 한의원 N / 한방병원 K

**정부 정책 키워드** (적재 시점)
- 어르신 한의 주치의: 4개
- 첩약 보험 2단계: 7개
- 등급 B로 자동 분류, 순위 추적 대상

**다음 액션**
- 신규 개원 [N]곳은 web UI(/competitors)에서 모니터링 등록 검토
- 첩약 보험 키워드는 Pathfinder 다음 스캔에 자동 포함
```

## Guardrails

1. **LOCALDATA_AUTH_KEY 또는 DATA_GO_KR_API_KEY 등록** — `python -c "import json; print(bool(json.load(open('config/secrets.json')).get('DATA_GO_KR_API_KEY')))"` 확인.
2. **분류는 휴리스틱** — `event_type='renamed'`은 정확하지 않을 수 있음. 운영자 검토 안내.
3. **자기 한의원 제외** — `business_profile.json::self_exclusion` 매칭은 보고에서 제외.
4. **자동 게시 금지** — 정부 시드 키워드 등록은 keyword_insights 적재만. 콘텐츠 생성·게시는 web UI HITL.
5. **DML SQL 금지** — 데이터 수정은 명시적 마이그레이션 스크립트로만.

## 출력 길이

- 신규 변동 최대 10건 (초과 시 top 5 + 외 N건)
- HIRA 카테고리 5개 이내
- 다음 액션 1-2개

## 관련 파일/테이블

- `scrapers/localdata_clinic_tracker.py` (R3-1)
- `scrapers/hira_api_client.py` (R3-7)
- `scripts/seed_government_keywords.py` (R3-6)
- `clinic_lifecycle_events` 테이블
- `hira_clinics` 테이블
- `keyword_insights` (source='government_seed')
- 후속 스킬: `scan-competitors`, `competitor-watch`

---
name: data-health
description: 데이터 수집 파이프라인 헬스체크. 모든 수집기의 마지막 수집 시각·24h/7d 카운트·품질 이슈·API 키 상태를 점검하고 severity별로 보고. 매일 23:00 cron, ad-hoc 호출 가능.
license: Internal
---

# Data Health — 수집 파이프라인 헬스체크

`scrapers/data_health_monitor.py`로 모든 수집기의 상태를 점검하고, **severity별로 그룹핑한 인사이트 + 즉시 권고 액션**을 보고.

## When to use

- "헬스체크" / "수집 상태" / "파이프라인 상태"
- "데이터 잘 모이고 있어?" / "뭐 안 돌고 있어?"
- "API 키 만료된 거 있어?"
- "어제부터 빈 테이블 있어?"

## Commands

```bash
# 전체 헬스체크 (1~2분)
python scrapers/data_health_monitor.py

# 최근 cron 실행 결과만 빠르게 (즉시)
python -c "
import sqlite3
c = sqlite3.connect('db/marketing_data.db').cursor()
print('=== 최근 24h 잡 실행 ===')
for row in c.execute('SELECT job_name, status, started_at, duration_seconds FROM job_runs WHERE started_at >= datetime(\"now\", \"-24 hours\") ORDER BY started_at DESC LIMIT 30'):
    print(row)
"
```

## Workflow

1. **헬스 모니터 실행** — `data_health_monitor.py`가 stdout으로 dashboard 출력 + JSON return.

2. **stdout 파싱** — 각 테이블별 status (OK/WARN/CRIT) + last_record + 24h count.

3. **API 키 상태** — 같은 스크립트에서 점검 (Naver/Gemini/Telegram 등).

4. **job_runs 보강** — cron 잡 실행 결과:
   ```sql
   -- 최근 7일 잡별 성공률
   SELECT job_name,
          SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) ok,
          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) fail,
          SUM(CASE WHEN status='timeout' THEN 1 ELSE 0 END) tmo
   FROM job_runs
   WHERE started_at >= datetime('now', '-7 days')
   GROUP BY job_name
   ORDER BY fail DESC;
   ```

5. **사용자 보고** (필수 — severity별로 그룹)

## 보고 템플릿

```markdown
**🩺 데이터 파이프라인 헬스체크** (점검 시각: HH:MM)

**전체 상태**: 🟢 정상 / 🟡 주의 / 🔴 위험 (한 단어)

---

**🔴 즉시 조치 필요** (있을 때만)
- [테이블명/잡명]: [구체적 문제 — 예: "rank_history 마지막 수집 36시간 전, cron 미작동 의심"]
- ...

**🟡 주의 필요**
- [테이블명/잡명]: [경고 — 예: "competitor_reviews 24h 카운트 0, 직전 7d 평균 12"]
- ...

**🟢 정상 작동** (간략)
- 활성 수집기 N개, 최근 24h 신규 N건 (top 3 테이블만 표시)
- API 키: Naver ✅ / Gemini ✅ / Telegram ✅

---

**📊 잡 실행 통계** (최근 7일)
- 성공: N건 / 실패: N건 / 타임아웃: N건
- 실패율 ≥ 30% 잡:
  - [잡명]: 실패 N/N (사유: ...)

**🚨 비활성 모듈 확인** (의도된 비활성)
- kakao_map (API 키 만료) / geo_grid (API 미지원) / hira (키 미발급)
- 위 외 비활성이 있으면 의심.

---

**💡 권고 액션**
1. [구체적 — 예: "competitor_change_detector 어제 timeout — 로그 확인 필요"]
2. ...
```

## Guardrails

1. **빈 stat을 success로 보고 금지** — total_records=0 이지만 status=success인 잡은 의심.
2. **API 키 만료는 RED** — Gemini 키 만료 시 전체 시스템 멈춤. 즉시 알림.
3. **disabled_reason 명시된 모듈은 정상으로 분류** — schedule.json의 `disabled_reason` 참조.
4. **마지막 수집 시각이 cron 빈도의 2배 초과** → CRIT.
   - 매일 잡: 48h 초과 시 CRIT
   - 매시간 잡: 2h 초과 시 CRIT

## 출력 길이

- 정상 시: 15줄 이내 (요약 + "정상" 한 줄)
- 주의 시: 30줄
- 위험 시: 모든 문제 나열 (제한 없음)

## 알려진 비활성 모듈 (정상)

```
kakao_map_tracker         — Kakao REST API 키 만료
geo_grid_tracker          — Naver Local API 위치 미지원
hira_api_client           — data.go.kr API 키 미발급
commercial_data_collector — data.go.kr API 키 미발급
medical_review_monitor    — 모두닥/굿닥 URL 404
review_intelligence_collector — GraphQL 차단 → place_scan_enrichment로 대체
```

## 관련 파일/테이블

- `scrapers/data_health_monitor.py` (23:00 cron)
- `job_runs` (cron 실행 이력 + duration + status)
- `config/schedule.json` (disabled_reason 참조)
- API 키: `config/secrets.json` / `config/config.json`

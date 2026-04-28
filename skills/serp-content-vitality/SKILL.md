---
name: serp-content-vitality
description: SERP 변동성·MY플레이스 클립 출처·경쟁사 AI FAQ 도입 추적. 알고리즘/플랫폼 변화로 우리 콘텐츠 수명이 줄어드는지 객관적으로 측정.
license: Internal
---

# SERP & Content Vitality — 검색 변동성 + MY플레이스 클립 + AI FAQ

검색 환경 자체의 변화 신호 3축: (1) `serp_volatility`로 top10 turnover 자체 측정 (Mozcast 대체), (2) MY플레이스 클립 ↔ 일반 클립 출처 분리 (2026-04-14 시행), (3) 경쟁사 AI FAQ 도입 여부 (네이버 톡톡/온서비스).

## When to use

- "SERP 변동" / "top10 turnover" / "알고리즘 변화"
- "MY플레이스 클립" / "클립 출처" / "마이플레이스 후기 클립"
- "AI FAQ 도입한 경쟁사" / "AI 자동응답"
- "검색 환경 변화"

## Decision tree

```
사용자 의도 → 도구
─────────────────────────────────────
"변동성/turnover/알고리즘"     → serp_volatility.py
"클립 / MY플레이스 / 비율"      → place_scan_enrichment.py 재실행 + 컬럼 조회
"AI FAQ / 톡톡 AI"             → competitor_visual_analyzer.py 재실행
```

## Commands

```bash
# === R3-8 SERP 자체 변동성 ===
python scripts/serp_volatility.py --status
python scripts/serp_volatility.py
python scripts/serp_volatility.py --days 14
python scripts/serp_volatility.py --dry-run

# === R3-4 MY플레이스 클립 출처 (Place Sniper 후처리) ===
# place_scan_enrichment.py를 다시 실행하면 신규 컬럼 자동 적재
# 조회는 SQL로:
sqlite3 db/marketing_data.db "
  SELECT keyword, place_clip_count, clip_source_my_place,
         clip_source_general, clip_my_place_link_rate
    FROM serp_features
   WHERE place_clip_count > 0
   ORDER BY scanned_at DESC LIMIT 20;"

# === R3-5 경쟁사 AI FAQ 도입 ===
python scrapers/competitor_visual_analyzer.py
sqlite3 db/marketing_data.db "
  SELECT competitor_name, ai_faq_enabled, ai_faq_detected_at
    FROM competitor_visual_scores
   WHERE scanned_date >= date('now', '-7 days');"
```

## Workflow

1. **--status 먼저 (R3-8만 해당)** — `serp_volatility` 행수와 마지막 측정일. 7일 이상이면 재계산 추천.
2. **R3-8은 rank_history 의존** — `rank_history`에 device_type별 top 10 데이터가 있어야 작동. 데이터 부족 시 안내.
3. **R3-4 클립 출처 비율 = my_place_link_rate** — 0.5 이상이면 MY플레이스 후기 자동변환이 우세. 우리도 후기 작성 권장.
4. **R3-5 AI FAQ 미도입 = 약점** — 경쟁사가 AI 응답 미도입이면 우리가 빠른 응대로 차별화.

## 보고 템플릿

```markdown
**SERP & Content Vitality** (소요 X분)

**🔥 SERP 변동성 top 10 (최근 14일)**
| 키워드 | 디바이스 | 변동성 | 신규 진입 | 이탈 |
|--------|---------|--------|----------|------|
| 청주 한의원 | mobile | 0.45 | [경쟁사A] | [경쟁사B] |

→ 변동성 ≥ 0.4: 알고리즘 변화 의심 — 우리 콘텐츠 점검 권장
→ 변동성 ≤ 0.1: 안정 — 현 콘텐츠 유지

**📹 MY플레이스 클립 출처 분포**
- MY플레이스 후기 자동변환: N개 키워드, 평균 link_rate=X.XX
- 일반 클립: N개 키워드
→ link_rate ≥ 0.5인 키워드는 후기 자동변환이 우세 → 우리도 후기 늘려서 자동 클립 노출

**🤖 경쟁사 AI FAQ 도입 현황**
- 도입: [경쟁사 N곳]
- 미도입: [경쟁사 K곳] ← 우리가 빠른 응대로 차별화 가능

**다음 액션**
- 변동성 0.4↑ 키워드 N개에서 우리 순위 변화 web UI(/battle)에서 확인
- AI FAQ 미도입 경쟁사 [N곳] 대비 우리 톡톡 응대 시간 단축 검토
```

## Guardrails

1. **R3-8은 SQL 분석만** — 외부 API 호출 X. 비용 0.
2. **R3-4 컬럼 신선도** — `place_scan_enrichment.py` 재실행한 키워드만 신규 컬럼이 채워짐. 미실행 키워드는 NULL/0.
3. **R3-5 AI FAQ는 휴리스틱** — 마크 텍스트 매칭이라 false negative 가능. 캡차 차단 시 detect 실패.
4. **자기 한의원 제외** — turnover 계산에서 자기 한의원 제외 필요 (현재 제외 X — 운영자 인지 권장).
5. **DML SQL 금지** — 결과 조회만. 변경은 web UI 또는 마이그레이션.

## 출력 길이

- 변동성 top 10
- 클립 비율 5개 핵심 키워드
- AI FAQ 미도입 경쟁사 최대 5곳
- 다음 액션 1-2개

## 관련 파일/테이블

- `scripts/serp_volatility.py` (R3-8)
- `scrapers/place_scan_enrichment.py` (R3-4 컬럼 추가)
- `scrapers/competitor_visual_analyzer.py` (R3-5 AI FAQ)
- `serp_volatility` 테이블 (신규)
- `serp_features` (clip_source_my_place, clip_source_general, clip_my_place_link_rate 컬럼 추가)
- `competitor_visual_scores` (ai_faq_enabled, ai_faq_detected_at 컬럼 추가)
- 후속 스킬: `scan-competitors`, `competitor-watch`

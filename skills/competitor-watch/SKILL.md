---
name: competitor-watch
description: 경쟁사 모니터링 — 네이버 플레이스 별점 부활(2026-4-6 시행) 비공개 전환 감지 + 심평원 비급여 단가 변화 추적. 점주가 별점 가린 시점·단가 인상/인하 시점이 마케팅 전략 신호.
license: Internal
---

# Competitor Watch — 경쟁사 별점·단가 변화 감지

기존 `scan-competitors`(리뷰/블로그/Place 변경)에 추가로 **별점 부활 + 비급여 단가 공개 의무**라는 2026 신규 신호 두 축을 추적.

## When to use

- "경쟁사 별점 변화" / "별점 비공개 전환"
- "비급여 단가 비교" / "경쟁사 가격 추적"
- "심평원 단가 갱신"
- "경쟁사 평점 추적"
- 명시 X — 월 1-2회 또는 비급여 공개 마감(2026-6-12) 전후 정기 점검

## Decision tree

```
사용자 의도 → 도구 선택
──────────────────────────────────────
"별점" / "평점" / "비공개 전환"             → track_star_visibility.py
"단가" / "비급여" / "가격 비교"             → competitor_pricing_collector.py
"전부 다" / "경쟁사 점검"                  → 두 개 순차 + scan-competitors 권장
명시 X                                      → --status로 양쪽 현황 먼저 보고
```

## Commands

```bash
# === R8 별점·비공개 전환 ===
python scripts/track_star_visibility.py --status         # 직전 스냅샷
python scripts/track_star_visibility.py                  # 모든 경쟁사 1회 체크
python scripts/track_star_visibility.py --diff-only      # 변화만 출력

# === R15 경쟁사 비급여 단가 ===
python scripts/competitor_pricing_collector.py --status            # 적재 현황
python scripts/competitor_pricing_collector.py                     # targets.json 경쟁사 일괄 수집
python scripts/competitor_pricing_collector.py --hospital ykiho1   # 특정 기관만
python scripts/competitor_pricing_collector.py --dry-run

# === 사전 단계 (R15 의존) ===
python scripts/hira_oasis_harvester.py --hira-hospitals  # 청주권 한의원 ykiho 확보
```

## Workflow

1. **--status 먼저** — 두 도구 모두 `--status` 지원. 마지막 측정 시각 + 데이터 양 확인. 1주 이내면 "재측정할까요?" 확인.

2. **R15 단가는 R2 의존** — `hira_hospitals` 비어있으면 `hira_oasis_harvester.py --hira-hospitals` 먼저 실행. 사용자에게 안내.

3. **별점 비공개 전환 = 강한 신호** — `transition_event='visibility_lost'` 발견 시 즉시 보고. 평점 낮음 추정 (점주가 의도적 가림).

4. **단가 변화 = 가격 전략 신호** — 직전 대비 ±10% 이상 변동 한의원은 별도 강조. 자기 한의원 단가도 같이 보여주기.

5. **사용자 보고**

## 보고 템플릿

```markdown
**경쟁사 모니터링 완료** (별점 N곳 / 단가 K곳, 소요 X분)

**🚨 별점 변화 감지** (transition_event != 'first_seen')
- [한의원명] — visibility_lost (평점 ❌ 비공개 전환) — 직전 X.X점 → 가림
  → 가림 사유 추정: 평점 하락 / 점주 정책 변경
- [한의원명] — rating_drop_-0.6 (X.X → Y.Y)

**💰 비급여 단가 변화** (직전 ±10% 이상)
| 한의원 | 항목 | 직전 | 현재 | 편차 |
|--------|------|------|------|------|
| [경쟁사A] | 추나치료 | 50,000 | 60,000 | +20% |

**📊 우리 vs 경쟁 단가 비교** (top 5 항목)
| 항목 | 우리 | 청주 평균 | 충북 평균 |
|------|------|-----------|-----------|
| 추나치료 | 50,000 | 55,000 | 53,000 |

**다음 액션**
- 별점 비공개로 전환한 [N]곳은 콘텐츠 마케팅 약점 시점 — 우리 차별화 콘텐츠 작성 권장
- 단가 ±10% 변동 K곳은 가격 전략 검토 자료
- 자기 한의원 단가 표기 콘텐츠는 R14 verify_price_consistency 게이트가 자동 검증 (±10% 허용)
```

## Guardrails

1. **별점 데이터 출처** — `rank_history.star_rating` 컬럼 (라운드 2 C4에서 추가). `scraper_naver_place.py` 실행 후 적재됨. 별도 cron 없음 — 운영자가 수동 트리거.
2. **R15는 R2 선행 필요** — `hira_hospitals` 비어있으면 작동 안 함. 의존 안내 자동.
3. **DATA_GO_KR_API_KEY 등록 확인** — `python -c "import json; print(bool(json.load(open('config/secrets.json')).get('DATA_GO_KR_API_KEY')))"`
4. **public_avg는 청주권 한정 평균** — 충북 전체 평균과 다를 수 있음. 보고 시 명시.
5. **단가 데이터 신선도** — 비급여 공개 마감 2026-6-12. 그 전엔 데이터 부분 적재 가능성. 적재 시점 함께 보고.
6. **자기 한의원 단가는 별도 입력** — 자동 수집 안 됨. `business_profile.json` 또는 별도 테이블에 운영자가 입력해야 비교 정확.

## 출력 길이

- 별점 변화는 모두 나열 (5건 이내)
- 단가 변화 ±10% 이상만 나열 (top 5)
- 단가 비교 표는 항목 5개
- 다음 액션 1-2개

## 관련 파일/테이블

- `scripts/track_star_visibility.py` (R8)
- `scripts/competitor_pricing_collector.py` (R15)
- `scripts/hira_oasis_harvester.py` (R2 — 사전 단계)
- `competitor_star_history` 테이블 (transition_event)
- `hira_nonpay_items` 테이블 (R14가 단가 게이트로 활용)
- 후속 스킬: `medical-compliance` (단가 일치성 게이트), `scan-competitors` (리뷰/블로그)

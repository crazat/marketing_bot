---
name: scan-ranks
description: 네이버 플레이스 순위를 스캔하고 결과를 자연어 인사이트로 사용자에게 보고. 단일 키워드 또는 전체 키워드, 모바일/데스크탑/둘 다 선택 가능. 스캔 후 rank_history에서 직전 스캔과 비교해 변화를 요약.
license: Internal
---

# Scan Ranks — 순위 스캔 + 인사이트 보고

`scrapers/scraper_naver_place.py`를 호출해 순위를 스캔하고, **DB 변화를 자연어로 사용자에게 보고**.

## When to use (트리거 예시)

- "순위 스캔해줘" / "순위 다시 봐" / "오늘 순위 어때"
- "[키워드] 순위 확인" — 단일 키워드 빠른 스캔
- "모바일만 봐" / "데스크탑만" — 디바이스 한정
- "리뷰 빼고 빨리" — `--skip-reviews`
- "병렬 5개로" / "순차로 천천히" — workers 조정

## Decision tree (인자 결정)

```
사용자 의도 → CLI 옵션 매핑
─────────────────────────────────────────────
단일 키워드?    → -k "키워드명"
디바이스 제한?  → -d mobile|desktop|both (기본 both)
경쟁사 리뷰?    → 단일 스캔은 자동 제외, 전체는 --skip-reviews 옵션
워커 수?        → -w 3 (기본). 빠르게=5, 안전하게=--sequential
```

## Commands

```bash
# 단일 키워드 (빠름, 30초~1분)
python scrapers/scraper_naver_place.py -k "청주 다이어트 한약" -d both

# 전체 스캔 (병렬, 리뷰 포함, 5~10분)
python scrapers/scraper_naver_place.py

# 전체 스캔 (병렬, 리뷰 제외, 2~3분)
python scrapers/scraper_naver_place.py --skip-reviews

# 전체 스캔 (5워커 병렬, 가장 빠름)
python scrapers/scraper_naver_place.py -w 5 --skip-reviews
```

## Workflow

1. **사전 점검** — 스캔 시작 전 직전 스캔 시각 확인:
   ```bash
   python -c "import sqlite3; c=sqlite3.connect('db/marketing_data.db').cursor(); print(c.execute('SELECT MAX(checked_at) FROM rank_history').fetchone())"
   ```
   30분 이내 스캔이면 사용자에게 "직전 스캔이 X분 전인데 다시 돌릴까요?" 확인.

2. **스캔 실행** — 위 command 중 적절한 것 실행. 실시간 stdout은 사용자에게 보여주지 말고 Claude가 읽기만.

3. **결과 수집** — DB 직접 조회:
   ```python
   # 가장 최근 스캔 batch (같은 분 단위)
   SELECT keyword, device_type, rank, status
   FROM rank_history
   WHERE checked_at >= datetime('now', '-15 minutes')
   ORDER BY keyword, device_type
   ```

4. **변화 계산** — 직전 스캔과 비교:
   ```python
   # 키워드별 (device=mobile 기준) 직전 vs 이번 rank 차이
   WITH ranked AS (
     SELECT keyword, rank, checked_at,
            ROW_NUMBER() OVER (PARTITION BY keyword ORDER BY checked_at DESC) rn
     FROM rank_history WHERE device_type='mobile' AND status='found'
   )
   SELECT a.keyword, a.rank current, b.rank previous, (b.rank - a.rank) delta
   FROM ranked a LEFT JOIN ranked b ON a.keyword=b.keyword AND b.rn=2
   WHERE a.rn=1
   ```

5. **사용자에게 보고** (필수 — 아래 템플릿)

## 보고 템플릿 (사용자에게 출력할 형식)

```markdown
**순위 스캔 완료** (모바일 N개 / 데스크탑 N개, 소요 X분)

**상승 ▲** (delta < 0 = 상승)
- 청주 다이어트 한약: 11위 → 8위 (▲3)
- ...

**하락 ▼** (delta > 0)
- ...

**신규 진입 ✨** (직전 not_in_results → 이번 found)
- ...

**탈락 ❌** (직전 found → 이번 not_in_results)
- ...

**유지** N개 (변화 없음)

**오류/캡차** N개 (있을 때만)
- ...

**한 줄 인사이트**: (예) "다이어트 계열 키워드 3개 동시 상승. 지난주 블로그 포스팅 효과로 추정."
```

## Guardrails

1. **30분 내 중복 스캔 차단** — 사용자가 명시적으로 "다시" 요청 안 했으면 직전 스캔 시각 보여주고 확인.
2. **모바일/데스크탑 불일치 무시 금지** — 같은 키워드에서 모바일↔데스크탑 차이가 5위 이상이면 "스크래핑 오류 가능성" 경고.
3. **status='error' 누락 금지** — 캡차/타임아웃은 반드시 보고에 포함.
4. **Telegram/UI에 자동 게시 절대 금지** — 결과는 이 대화창 내에서만 보고.

## 출력 길이

- 변화 항목이 10개 이내면 모두 나열
- 10개 초과면 상승/하락 각 top 5 + "외 N개"
- 한 줄 인사이트는 항상 포함 (없으면 "큰 변화 없음")

## 관련 테이블

- `rank_history` (keyword, device_type, rank, status, checked_at) — 8400+ 행
- `competitor_reviews` (--skip-reviews 안 쓸 때만 갱신)
- `serp_features` (place_scan_enrichment 자동 후처리)

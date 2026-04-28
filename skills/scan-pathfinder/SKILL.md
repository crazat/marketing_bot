---
name: scan-pathfinder
description: Pathfinder 키워드 발굴을 실행하고 신규 등급별 키워드 + 추천 액션을 자연어로 보고. complete 모드(50개) vs legion 모드(300+) 자동 선택, MF-KEI 5.0 점수 기반.
license: Internal
---

# Scan Pathfinder — 키워드 발굴 + 인사이트 보고

`pathfinder_v3_complete.py` 또는 `pathfinder_v3_legion.py`로 신규 키워드를 발굴하고, **신규 등급별 분포 + 상위 S/A급 + 추천 다음 액션**을 보고.

## When to use

- "키워드 발굴해줘" / "신규 키워드 찾아"
- "S급 키워드 찾아" / "Legion 모드로 대량"
- "300개 발굴" / "이번주 발굴 돌려"

## Decision tree (모드 선택)

```
사용자 의도 → 모드 선택
────────────────────────────────────
"빨리" / "조금" / 명시 X      → complete 모드 (--max 50, 5~10분)
"대량" / "많이" / "Legion"    → legion 모드 (--target 300, 30~60분)
숫자 명시 (예: "100개")        → --max N (complete) 또는 --target N (legion if ≥150)
```

## Commands

```bash
# 일반 발굴 (50개, 5~10분)
python pathfinder_v3_complete.py --save-db

# 발굴 개수 조정 (예: 100개)
python pathfinder_v3_complete.py --max 100 --save-db

# Legion 모드 (300+ 대량, 30~60분)
python pathfinder_v3_legion.py --target 300 --save-db

# Legion 대량 (500개)
python pathfinder_v3_legion.py --target 500 --save-db
```

## Workflow

1. **사전 점검** — 직전 발굴 시각 확인:
   ```bash
   python -c "import sqlite3; c=sqlite3.connect('db/marketing_data.db').cursor(); print(c.execute('SELECT MAX(created_at) FROM keyword_insights').fetchone())"
   ```
   24시간 이내 발굴이면 "직전 발굴이 X시간 전인데 다시 돌릴까요?" 확인.

2. **모드 선택 + 실행** — Legion은 시간이 오래 걸리므로 사용자에게 예상 소요시간 알리고 실행.
   - Complete: 5~10분 → 동기 실행 OK
   - Legion 300: 30~60분 → 백그라운드 실행 권장 (`run_in_background=true`)

3. **결과 집계** — 이번 run에서 생긴 신규 키워드:
   ```sql
   SELECT grade, COUNT(*) cnt
   FROM keyword_insights
   WHERE created_at >= datetime('now', '-2 hours')
   GROUP BY grade
   ORDER BY CASE grade WHEN 'S' THEN 1 WHEN 'A' THEN 2 WHEN 'B' THEN 3 ELSE 4 END;

   -- 상위 S/A급 키워드 (점수 순)
   SELECT keyword, grade, search_volume, document_count, kei, category
   FROM keyword_insights
   WHERE created_at >= datetime('now', '-2 hours')
     AND grade IN ('S', 'A')
   ORDER BY kei DESC
   LIMIT 10;
   ```

4. **사용자 보고** (필수)

## 보고 템플릿

```markdown
**키워드 발굴 완료** ([complete|legion] 모드, 신규 N개, 소요 X분)

**등급별 분포**
- 🔥 S급: N개 (검색량 ≥ 1000 + 경쟁 낮음)
- 🟢 A급: N개
- 🔵 B급: N개
- ⚪ C급: N개

**🔥 S급 신규 키워드** (KEI 점수 순)
1. [키워드명] (검색량 X, 문서수 X, KEI X.XX, 카테고리)
2. ...

**🟢 A급 추천 키워드** (top 5)
1. ...

**카테고리 요약**
- 다이어트: N개 (S 1, A 3, B 5)
- 교통사고: N개
- ...

**추천 다음 액션**
- [구체적 제안 — 예: "S급 '청주 비만 한약' 검색량 1500, 즉시 콘텐츠 작성 추천"]
- [예: "A급 '청주 산후조리' 4건은 같은 클러스터, 시리즈 포스팅 가능"]
- [예: "C급이 70% — 다음 발굴은 카테고리 필터 좁힐 것 추천"]
```

## Guardrails

1. **24시간 내 중복 발굴 차단** — 명시적 요청 없으면 확인.
2. **legion + 600+ 요청 시 경고** — 1시간 이상, API 호출 비용 큼.
3. **--save-db 누락 금지** — 결과는 반드시 DB에 적재 (CSV만 저장하면 의미 없음).
4. **카테고리 자동 분류 검증** — uncategorized가 50% 넘으면 카테고리 표준화 작업 권장.

## 출력 길이

- S급은 최대 10개 모두 나열
- A급은 top 5
- B/C급은 카운트만
- 추천 액션은 2~4개

## 관련 파일/테이블

- `pathfinder_v3_complete.py` (50개, MF-KEI 5.0)
- `pathfinder_v3_legion.py` (300+ 대량 모드)
- `keyword_insights` 테이블 (현재 6200+ 행)
- 카테고리: `services/category_standardizer.py`
- 로그: `logs/pathfinder_live.log` (TeeWriter 실시간)

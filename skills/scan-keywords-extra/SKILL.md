---
name: scan-keywords-extra
description: PAA(People Also Ask), DataLab 쇼핑 인사이트, HIRA/OASIS 의료 시드를 활용한 보조 키워드 발굴. 기존 scan-pathfinder가 못 잡는 자연어 질문형·인구통계 결합·의학 long-tail 키워드 풀을 keyword_insights에 보강.
license: Internal
---

# Scan Keywords Extra — 보조 키워드 풀 확장

기존 `scan-pathfinder`(자동완성·갭·SERP)가 못 잡는 영역을 3개 신규 소스로 보강:
PAA 자연어 질문 / DataLab 쇼핑 카테고리 인구통계 / HIRA·OASIS 의학 공식 항목명.

## When to use

- "PAA 키워드 모아줘" / "사람들이 묻는 질문 수집"
- "20대 다이어트", "임산부 한약" 같은 인구통계 결합 키워드 발굴
- "한약재 시드 키워드", "HIRA 비급여 항목명"
- "AEO/Cross-User 대응 키워드 부족" — 검증 의도 키워드 보강 필요 시
- 명시 X — `scan-pathfinder` 1차 발굴 후 보조 작업으로 자연 진행

## Decision tree

```
사용자 의도 → 도구 선택
─────────────────────────────────────────
"PAA" / "사람들이 묻는" / "자연어 질문"        → pathfinder_paa.py
"인구통계" / "20대" / "쇼핑 카테고리"           → datalab_shop_insight.py
"HIRA" / "한약재" / "OASIS" / "비급여 항목"   → hira_oasis_harvester.py
"전부 다" / "보조 발굴 한바퀴"                → 위 3개 순차 실행
```

## Commands

```bash
# === R1 PAA — 자연어 질문 트리 (depth 2~3) ===
python scripts/pathfinder_paa.py --dry-run                  # 시드만 확인
python scripts/pathfinder_paa.py --depth 2 --max 200        # 기본
python scripts/pathfinder_paa.py --depth 3 --max 500        # 더 깊게
python scripts/pathfinder_paa.py --seed "청주 다이어트 한약"  # 단일 시드

# === R3 DataLab Shopping (인구통계 결합) ===
python scripts/datalab_shop_insight.py --dry-run            # 변형만
python scripts/datalab_shop_insight.py                      # 기본 시드 + 9개 변형
python scripts/datalab_shop_insight.py --seeds 다이어트 한약 면역

# === R2 HIRA + OASIS (의학 공식 항목명) ===
python scripts/hira_oasis_harvester.py --dry-run
python scripts/hira_oasis_harvester.py --hira-hospitals     # 청주 한의원 명단
python scripts/hira_oasis_harvester.py --oasis-herbs        # 한약재 시드 → keyword_insights
python scripts/hira_oasis_harvester.py --all                # 전부
```

## Workflow

1. **사전 점검** — 직전 발굴 + 보조 발굴 시각 확인:
   ```bash
   python -c "import sqlite3; c=sqlite3.connect('db/marketing_data.db').cursor(); print(dict(c.execute(\"SELECT source, MAX(created_at) FROM keyword_insights GROUP BY source\").fetchall()))"
   ```
   24시간 이내 같은 source 발굴이면 사용자에게 "재실행할까요?" 확인.

2. **dry-run 우선** — PAA/Shopping은 외부 API 호출 비용 있음. 시드/변형 수만 먼저 보여주고 동의 후 실행.

3. **실행** — Camoufox(PAA)/네이버 API(Shopping)/data.go.kr(HIRA) 호출. 최대 5-10분.

4. **결과 집계 + 보고**:
   ```sql
   SELECT source, COUNT(*) cnt, search_intent, MIN(created_at) ts
     FROM keyword_insights
    WHERE created_at >= datetime('now', '-1 hours')
    GROUP BY source, search_intent
    ORDER BY cnt DESC;
   ```

## 보고 템플릿

```markdown
**보조 키워드 발굴 완료** (소스 N개, 신규 M개, 소요 X분)

**소스별 분포**
- PAA: N개 (validation N, comparison N, informational N)
- shop_insight: N개 (인구통계 결합)
- oasis: N개 (한약재 × 효능/부작용/복용법)

**의도별 분포 — Cross-User 대응**
- ✅ validation (신뢰 검증): N개
- ⚖️ comparison (비교): N개
- ⚠️ red_flag (부정): N개
- 🔍 commercial: N개
- 📚 informational: N개

**🔥 즉시 활용 키워드 top 5**
1. [키워드] (소스, 의도) — [추천 사용 맥락]

**다음 액션**
- 신규 키워드는 디폴트 grade='C'. SERP 분석은 다음 scan-pathfinder 시 자동 처리.
- validation/red_flag 키워드는 viral-comment-drafter에서 별도 톤으로 응답 검토 권장.
- HIRA 비급여는 R15 competitor_pricing_collector.py와 결합 시 단가 일치성 게이트 작동.
```

## Guardrails

1. **Camoufox SERP 비용** — PAA는 Google 검색 진입. depth 3 + max 500은 ~5분 + 봇 탐지 위험. 1일 1회 권장.
2. **DataLab API 할당량** — NAVER_DATALAB_KEYS 5개 로테이션. 카테고리 3개 × 변형 9개 × 시드 5개 = 135회 호출 (한도 내).
3. **HIRA 키 등록 확인** — DATA_GO_KR_API_KEY 없으면 R2 비활성. `python -c "import json; print('DATA_GO_KR_API_KEY' in json.load(open('config/secrets.json')))"`
4. **신규 키워드 디폴트 grade='C'** — SERP 분석 전이라 신뢰도 부족. Pathfinder UI 디폴트 필터에 안 보임 (Q12 필터 적용).
5. **search_intent 자동 분류 검증** — validation/red_flag 키워드 비율이 50% 넘으면 시드 편향 의심.

## 출력 길이

- 소스별 카운트 표 (3행)
- 의도별 분포 (max 7개 모두)
- 즉시 활용 키워드 top 5만
- 다음 액션 1-3개

## 관련 파일/테이블

- `scripts/pathfinder_paa.py` (R1, Camoufox 의존)
- `scripts/datalab_shop_insight.py` (R3, NAVER_DATALAB_KEYS)
- `scripts/hira_oasis_harvester.py` (R2, DATA_GO_KR_API_KEY)
- `keyword_insights` 테이블 (source = paa / shop_insight / oasis)
- `hira_hospitals`, `oasis_herbs` (R2 부산물)
- 후속 스킬: `scan-pathfinder` (SERP 등급 부여), `pathfinder-quality` (저품질 정리)

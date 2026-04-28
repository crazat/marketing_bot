---
name: viral-enrich
description: viral_targets 카페 글의 본문을 Selenium으로 재수집하거나, 시간 지난 hot 글을 재방문해 댓글/뷰 변화를 감지. Naver Search API description이 300자에서 잘려 자연질문 분류가 부정확한 문제 해결용.
license: Internal
---

# Viral Enrich — 카페 글 본문 풍부화 + Hot 글 재방문

`enrich_cafe_bodies.py`로 새 카페 글 본문을 Selenium으로 다시 수집하거나, `rescan_hot_targets.py`로 시간 지난 hot 글을 재방문해 변화를 감지. 둘 다 cafe_spy의 `_deep_read_leads`를 재사용하여 일관된 본문 추출.

## When to use

- "카페 본문 채워줘" / "본문 짧은 거 다시 가져와"
- "AI 분류 이상해" / "카페 글 자연질문이 광고로 잘못 분류됨" — 본문 부족이 원인일 가능성, enrich 권장
- "hot 글 다시 봐줘" / "댓글 더 달렸나 확인" / "재방문"
- "1주일 전 글 변화 봤어"

**유스케이스 분리:**
- **enrich** = 본문이 짧은 새 글 (`<200자`) 본문 채우기
- **rescan** = 이미 본문 있고 일정 시간 지난 글 재방문 (변화 감지)

## Decision tree

```
사용자 의도 → 도구 선택
─────────────────────────────────
"본문 짧아" / "preview 부실"        → enrich_cafe_bodies.py
"AI 분류 다시 돌려야겠어"            → enrich_cafe_bodies.py 먼저
"댓글 달렸나" / "변화 감지"          → rescan_hot_targets.py
"1주일/N일 전 글"                   → rescan_hot_targets.py --age-hours N*24
명시 X + viral_targets 자연질문 부족 → enrich (본문 부족이 root cause 가능성)
```

## Commands

```bash
# === Enrich (본문 채우기) ===

# 기본: priority>=80 + content<200자 상위 30건
python scripts/enrich_cafe_bodies.py --dry-run    # 대상만 확인
python scripts/enrich_cafe_bodies.py              # 실제 fetch

# 더 많이
python scripts/enrich_cafe_bodies.py --top 100

# priority 임계값 조정
python scripts/enrich_cafe_bodies.py --min-score 100

# === Rescan (재방문) ===

# 기본: 7일 전 + priority>=100 top 20
python scripts/rescan_hot_targets.py --dry-run
python scripts/rescan_hot_targets.py

# 3일 전 글
python scripts/rescan_hot_targets.py --age-hours 72 --top 30
```

## Workflow

1. **dry-run 먼저** — 대상 건수와 샘플 5건 확인. 사용자에게 "N건 대상, 진행할까요?" 묻기.

2. **Selenium driver 초기화 시간 안내** — 두 스크립트 모두 cafe_spy CafeSpy 사용. 초기화에 5~10초 + 글당 1~3초.

3. **실행 후 즉시 후속 단계 안내**
   - **enrich 후**: 본문이 새로 생긴 글이 있으면 AI 재분류 권장
     ```bash
     python scripts/ai_ad_classify_submit.py --limit 200
     # 배치 SUCCEEDED 후
     python scripts/ai_ad_classify_apply.py db/batch_jobs/ad_classify_<TS>
     ```
   - **rescan 후**: 변화한(`CHANGED`) 글이 있으면 동일하게 재분류 권장.

4. **사용자 보고** (필수)

## 보고 템플릿

### Enrich 결과
```markdown
**카페 본문 풍부화 완료** (대상 N건, 소요 X분)

**결과**
- 본문 업데이트: N/M건
- 본문 너무 짧음 (<50자): K건 (회원전용/삭제글 가능성)

**샘플 — 본문 확보된 글 top 3**
1. [priority] [제목] — preview 19자 → 본문 1,234자
2. ...

**다음 액션**
- AI 재분류 권장: `python scripts/ai_ad_classify_submit.py --limit N`
- 본문 부족 K건은 회원전용 카페 글 — cafe_spy 로그인 설정 점검 권장
```

### Rescan 결과
```markdown
**Hot 글 재방문 완료** (대상 N건, 소요 X분)

**변화 감지**
- 변화 (CHANGED): N건 — 본문/댓글 추가됨
- 동일 (UNCHANGED): N건
- 실패: K건 (삭제/접근불가)

**변화한 글 top 3**
1. [priority] [제목] — 마지막 스캔 X일 전, 본문 길이 변화 +Y자
2. ...

**다음 액션**
- 변화한 N건 AI 재분류: `python scripts/ai_ad_classify_submit.py --limit N`
- (변화 0건이면) "현재 hot 큐는 안정 상태. 새 키워드로 viral_hunter 재실행 검토"
```

## Guardrails

1. **직원 작업 시간 회피** — 두 스크립트 모두 viral_targets를 UPDATE하므로 web UI에서 작업 중인 운영자가 영향받을 수 있음. 평일 업무시간이면 "직원 작업 중일 가능성, 진행할까요?" 확인.
2. **dry-run 우선** — 대상 건수가 100건 넘으면 반드시 dry-run으로 먼저 보여주고 확인.
3. **Selenium driver 충돌** — 같은 시간에 다른 cafe_spy 작업(viral_hunter cafe 모드 등) 돌고 있으면 driver 경합. 운영자에게 동시 실행 여부 확인.
4. **DB UPDATE 발생** — content/content_preview/last_scanned_at/scan_count 변경. 백업이 24h 이내인지 점검 권장.
5. **본문 50자 미만 결과 무시** — 회원전용/삭제글이거나 selector miss. 자동으로 무시되지만 비율 보고.

## 출력 길이

- 변화/업데이트 5건 이내면 모두 나열
- 초과 시 top 3 + "외 N건"
- 다음 액션은 1~2개 명령으로 압축

## 관련 파일/테이블

- `scripts/enrich_cafe_bodies.py` (신규, Q1)
- `scripts/rescan_hot_targets.py` (신규, Q3)
- `scrapers/cafe_spy.py::_deep_read_leads` (선행 의존)
- `viral_targets` 테이블 (UPDATE: content, content_preview, content_hash, last_scanned_at, scan_count)
- 후속 스킬: `scripts/ai_ad_classify_submit.py` + `apply.py`

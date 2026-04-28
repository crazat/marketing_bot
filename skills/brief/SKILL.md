---
name: brief
description: 일/주/월 종합 인텔리전스 브리핑을 생성. 순위·키워드·경쟁사·바이럴·리드·헬스 6개 도메인을 한 페이지로 요약. intelligence_synthesizer.py를 트리거하거나 기존 리포트를 조회해 자연어로 보고.
license: Internal
---

# Brief — 종합 인텔리전스 브리핑

`intelligence_synthesizer.py`(매일 22:00 cron)가 6개 도메인 리포트를 생성. 사용자 요청 시 최신 리포트를 조회하거나 새로 생성해 **한 페이지 임원 브리핑**으로 보고.

## When to use

- "오늘 종합" / "오늘 브리핑" / "요약해"
- "주간 브리핑" / "이번주 정리"
- "월간 리포트" / "이번달 어땠어"
- "지금 상태 한눈에" / "임원 보고용"

## Decision tree

```
사용자 의도 → 데이터 소스
────────────────────────────────────
"오늘" / "지금" / "현재"   → intelligence_reports 테이블 최신 (22:00 cron 결과)
                            → 6시간 이상 묵었으면 ad-hoc run 권장
"주간" / "이번주"          → 최근 7일 데이터 직접 집계 (synthesizer 다시 안 돌림)
"월간"                     → 최근 30일 직접 집계
"새로 만들어"              → python scrapers/intelligence_synthesizer.py
```

## Commands

```bash
# 새 종합 리포트 생성 (5~10분, 22:00 자동, ad-hoc은 명시적 요청 때만)
python scrapers/intelligence_synthesizer.py

# 기존 리포트 조회 (즉시)
sqlite3 db/marketing_data.db "SELECT report_type, summary, created_at FROM intelligence_reports ORDER BY created_at DESC LIMIT 6"
```

## Workflow

1. **데이터 신선도 확인**
   ```sql
   SELECT MAX(created_at) FROM intelligence_reports;
   ```
   - 6시간 이내 → 그대로 사용
   - 6~24시간 → 사용자에게 "어제 22시 데이터인데 그대로 쓸까요, 새로 돌릴까요?"
   - 24시간 초과 → 새로 생성 권장

2. **6개 도메인 데이터 수집** (DB 직접):
   ```sql
   -- 1. 순위 도메인
   SELECT keyword, MAX(rank) prev, MIN(rank) curr, COUNT(*) scans
   FROM rank_history
   WHERE checked_at >= datetime('now', '-7 days') AND device_type='mobile' AND status='found'
   GROUP BY keyword;

   -- 2. 키워드 발굴
   SELECT grade, COUNT(*) FROM keyword_insights
   WHERE created_at >= datetime('now', '-7 days') GROUP BY grade;

   -- 3. 경쟁사
   SELECT COUNT(*) changes FROM competitor_changes
   WHERE detected_at >= datetime('now', '-7 days');

   -- 4. 바이럴 타겟
   SELECT platform, comment_status, COUNT(*) FROM viral_targets
   WHERE discovered_at >= datetime('now', '-7 days') GROUP BY platform, comment_status;

   -- 5. 리드 처리 (mentions + community_mentions)
   SELECT source_module, COUNT(*) FROM mentions
   WHERE created_at >= datetime('now', '-7 days') GROUP BY source_module;

   -- 6. 시스템 헬스
   SELECT job_name, status, COUNT(*) FROM job_runs
   WHERE started_at >= datetime('now', '-7 days') GROUP BY job_name, status;
   ```

3. **사용자 보고** (필수)

## 보고 템플릿

```markdown
# 📊 [기간] 종합 브리핑 (YYYY-MM-DD)

## 🎯 핵심 KPI (한 줄씩)
- 추적 키워드 평균 순위: 12.3 → 10.8 (▲1.5, 모바일 기준)
- 신규 발굴 키워드: N개 (S급 N, A급 N)
- 신규 바이럴 타겟: N개 (게시 완료 N)
- 신규 리드: N건
- 시스템 가동률: XX% (실패 잡 N건)

## 🏆 이번 주 하이라이트 (top 3)
1. [구체적 성과 — 예: "청주 다이어트 한약" 11위 → 8위 진입]
2. ...

## ⚠️ 주의 사항 (top 3)
1. [구체적 위험 — 예: 경쟁사 A가 24h 내 리뷰 5개 동시 등록]
2. ...

## 📈 도메인별 상세

**1. 순위 (Battle)**
- 상승 N개 / 하락 N개 / 신규 진입 N개
- 주요 변화: ...

**2. 키워드 (Pathfinder)**
- 신규 발굴 N개 (S급 X, A급 X)
- top S급: ...

**3. 경쟁사**
- Place 변경 N건 / 신규 리뷰 N건 / 블로그 N건
- 주목할 움직임: ...

**4. 바이럴**
- 신규 타겟 N개 / 댓글 게시 N개 / 승인 대기 N개

**5. 리드**
- 신규 리드 N건 (지식인 X, 카페 X, 블로그 X)

**6. 시스템 헬스**
- 가동률 XX% / 실패 잡 N건 / API 비용 $X.XX

## 💡 다음 주 추천 액션 (3개)
1. [구체적 액션 — 예: "S급 '청주 비만 한약' 콘텐츠 작성"]
2. ...
3. ...
```

## Guardrails

1. **6시간 이내 데이터 우선** — 새로 생성은 비싸고 느림.
2. **숫자 인용 시 반드시 SQL로 직접 확인** — 캐시된 리포트 텍스트 그대로 베끼면 stale 위험.
3. **추천 액션은 항상 3개 이내** — 너무 많으면 신호 실종.
4. **임원 보고용 톤** — 마케팅 잘 모르는 사람이 읽어도 이해되게.

## 출력 길이

- 일간: 30줄 이내
- 주간: 50줄 이내
- 월간: 80줄 이내

## 관련 파일/테이블

- `scrapers/intelligence_synthesizer.py` (22:00 cron, 6 reports/run)
- `intelligence_reports` 테이블 (최신 6개 = 어제 22시 결과)
- `services/telegram_reporter.py` (포맷 참고용)
- 모든 도메인 테이블 (rank_history, keyword_insights, competitor_*, viral_targets, mentions, job_runs)

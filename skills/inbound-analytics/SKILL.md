---
name: inbound-analytics
description: 자사 inbound 측정 인프라 — GSC API + Naver Search Advisor 진입 검색어, Microsoft Clarity 히트맵·세션 메트릭, PageSpeed Insights Core Web Vitals 추적. 4개 수동 트리거 스크립트로 수집·발견만 (자동 게시 없음).
license: Internal
---

# Inbound Analytics — 자사 진입 측정 4종 세트

방문자가 **어떤 검색어로 / 우리 사이트 어디에 / 얼마나 빠르게 / 무엇을 답답해하며** 도달하는지 측정. Pathfinder가 "발굴할 키워드"라면, 이 스킬은 "이미 들어오고 있는 키워드/세션"을 본다. 한 번 측정하고 1주 이상 누적해서 추세로 본다.

## When to use

- "GSC 검색어" / "사이트 진입 키워드" / "어떤 검색어로 들어왔어"
- "Naver Search Advisor" / "네이버 웹마스터" / "네이버 진입 검색어"
- "Clarity 히트맵" / "사용자 세션" / "rage click" / "dead click"
- "PageSpeed" / "Core Web Vitals" / "LCP" / "INP" / "CLS"
- "사이트 속도" / "사용자 경험 지표"
- 명시 X — Pathfinder/Battle 사이클 끝나고 "근데 우리 사이트로는 실제 뭐로 들어와?" 흐름

## Decision tree

```
사용자 의도 → 스크립트
─────────────────────────────────────────────────────────
"GSC", "구글 검색어", "Search Console"   → gsc_inbound_collector
"네이버 진입 검색어", "Search Advisor"    → naver_advisor_scraper
"히트맵", "Clarity", "rage/dead click"   → clarity_metrics_collector
"PageSpeed", "Core Web Vitals", "LCP"    → pagespeed_tracker
"전체 inbound 점검" / 처음 1회           → 4개 모두 --status 후 키 있는 것만 실행
```

## Commands

```bash
# 1) GSC — 직전 28일 query/page 클릭·노출·CTR·평균순위
python scripts/gsc_inbound_collector.py --status         # 직전 적재 확인
python scripts/gsc_inbound_collector.py --dry-run        # 키 검증만
python scripts/gsc_inbound_collector.py                  # 28일 수집 (기본)
python scripts/gsc_inbound_collector.py --days 7

# 2) Naver Search Advisor — Camoufox 로그인 후 CSV 자동 다운로드 (90일)
python scripts/naver_advisor_scraper.py --status
python scripts/naver_advisor_scraper.py --dry-run        # 로그인까지만
python scripts/naver_advisor_scraper.py                  # 기본 90일
# 자동화 실패 시: 콘솔에서 직접 export한 CSV를 db/naver_advisor_csv/ 폴더에 두고 재실행

# 3) Microsoft Clarity — 일별 sessions/PV/dead/rage/quick-back/scroll
python scripts/clarity_metrics_collector.py --status
python scripts/clarity_metrics_collector.py              # 직전 7일

# 4) PageSpeed Insights — 모바일+데스크탑 Core Web Vitals
python scripts/pagespeed_tracker.py --status
python scripts/pagespeed_tracker.py                      # mobile+desktop
python scripts/pagespeed_tracker.py --strategy mobile
```

## Workflow

1. **--status 먼저** — 직전 측정이 1주 이내면 사용자에게 "재측정할까요?" 묻기. inbound 메트릭은 일 단위 변동이 작아 주~월 추적이 적정.
2. **키 미등록은 graceful skip** — 각 스크립트는 키/자격증명 없으면 안내 출력 후 정상 종료. 사용자가 어떤 키 등록할지 결정 후 재실행.
3. **GSC와 Naver Advisor는 분리** — GSC는 google.com 진입, Advisor는 네이버 진입. 두 채널 점유율 비교 자체가 인사이트.
4. **재측정 권장 주기** — GSC/Advisor: 주 1회, Clarity: 주 1회 (메트릭은 누적 추세로 봄), PageSpeed: 월 1회 또는 사이트 배포 직후.
5. **인사이트 추출 SQL 예시** (사용자가 의뢰하면):
   ```sql
   -- GSC top 클릭 vs Pathfinder 등록 여부 (등록 안된 진입 키워드 = 보강 기회)
   SELECT i.query, SUM(i.clicks) c, AVG(i.position) p
     FROM inbound_search_queries i
     LEFT JOIN keyword_insights k ON k.keyword = i.query
    WHERE i.source='gsc' AND k.id IS NULL
      AND i.measured_date >= date('now','-28 days')
    GROUP BY i.query ORDER BY c DESC LIMIT 20;

   -- LCP 악화 추세 (모바일 + 1주 평균)
   SELECT site_url,
          AVG(CASE WHEN measured_at >= datetime('now','-7 days') THEN lcp_ms END) cur,
          AVG(CASE WHEN measured_at <  datetime('now','-7 days') THEN lcp_ms END) prev
     FROM pagespeed_history WHERE strategy='mobile'
    GROUP BY site_url
   HAVING cur > prev * 1.1;

   -- rage click 급증일 (이상치 감지)
   SELECT measured_date, rage_clicks
     FROM clarity_metrics
    WHERE rage_clicks > (SELECT AVG(rage_clicks)*1.5 FROM clarity_metrics);
   ```

## 보고 템플릿

```markdown
**Inbound 측정 완료** (활성 채널 N/4)

**🔍 진입 검색어 (GSC × Naver Advisor)**
- 28일 누적 클릭 X건 / 노출 Y건 / 평균순위 Z위
- 신규 등장 검색어 N개 (Pathfinder 미등록 → 콘텐츠 보강 후보)
  1. "[검색어]" — 클릭 N, 평균 N위 / Pathfinder ⨯
- 채널 분포: GSC X% / Naver Y% (이전 측정 대비 ±Z%p)

**🖱️ 사용자 행동 (Clarity)**
- 7일 평균 세션 N, PV N
- ⚠️ rage click +Z% 증가 — 페이지 [URL] 의심 (수동 세션 리플레이 권장)
- scroll depth 평균 X% (전주 Y%) → 콘텐츠 길이/관심도 변화

**⚡ Core Web Vitals (PSI)**
- 모바일 perf score N → 직전 M (+/−)
- LCP N ms (목표 ≤2500), INP N ms (≤200), CLS N (≤0.1)
- 위반 페이지 [URL] — 이미지 lazy/preload 점검 필요

**다음 액션**
- 미보강 진입 키워드 top 3 → Pathfinder 등록 + 콘텐츠 작성
- rage click 핫스팟 [URL] → Clarity 세션 리플레이로 사용자 어디서 막혔는지 직접 확인
- LCP 위반은 1주 후 재측정으로 개선 검증
```

## Guardrails

1. **Gemini-only 정책 유지** — 4개 스크립트 모두 추가 LLM 키 요구 없음. 인사이트 자연어 변환은 보고 단계에서 사용자 요청 시 `ai_generate()` 한 번만.
2. **cron 자동화 금지** — 수동 트리거 패턴. "주 1회 cron 걸까요?" 제안 금지.
3. **자동 게시·알림 없음** — 측정·발견까지만. 텔레그램 알림 추가 요청 시 별도 작업으로 분리.
4. **키 누락은 안내만** — 4개 모두 graceful skip. "키 발급해줘"는 사용자가 직접.
5. **재측정 간격 검증** — `--status` 출력으로 직전 측정일 확인 후, 24시간 내 재실행은 사용자 명시 요청 시만.
6. **PSI 무료 한도** — API 키 없어도 일 5~25건. 사이트 많거나 자주 측정 시 PAGESPEED_API_KEY 필수.
7. **Clarity 쿼터** — Project당 일 10회 호출 제한. --days 인자가 1/2/3이면 한 번에 끝, 그 이상은 평균 분할 (정밀하지 않음 — 정확도 필요하면 일 단위 호출).
8. **Naver Advisor는 사이트 변경에 취약** — 자동 셀렉터 깨지면 수동 export CSV를 db/naver_advisor_csv/ 폴더에 두고 재실행하면 적재만 시도함.
9. **자기 한의원 자동 제외 무관** — 진입 측정은 자사 사이트 대상이라 self_exclusion 적용 X.

## 출력 길이

- 활성 채널 1줄 요약
- GSC/Advisor 합산 지표 3-5줄
- Clarity 행동 지표 2-3줄 (이상치만)
- PSI 위반 페이지 top 3까지
- 다음 액션 1-3개

## 관련 파일/테이블

스크립트:
- `scripts/gsc_inbound_collector.py`
- `scripts/naver_advisor_scraper.py`
- `scripts/clarity_metrics_collector.py`
- `scripts/pagespeed_tracker.py`

테이블 (db_init.py 자동 생성):
- `inbound_search_queries` (source, query, landing_url, impressions, clicks, ctr, position, measured_date)
- `clarity_metrics` (measured_date, sessions, page_views, dead_clicks, rage_clicks, quick_backs, scroll_depth_avg)
- `pagespeed_history` (site_url, strategy, performance_score, lcp_ms, inp_ms, cls, fcp_ms, ttfb_ms, crux_origin_summary)

설정:
- `config/secrets.json` — GSC_SITE_URL, GSC_OAUTH_CREDENTIALS_PATH, NAVER_ADVISOR_ID/PW or COOKIES_PATH, NAVER_ADVISOR_SITE_URL, CLARITY_API_TOKEN, PAGESPEED_API_KEY
- `config/business_profile.json::sites_to_monitor` — PSI 측정 URL 리스트
- `db/naver_advisor_csv/` — 수동 export CSV 폴더 (자동 생성)

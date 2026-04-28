---
name: viral-channels
description: 카카오맵 리뷰, Threads 한국 멘션, 네이버 클립 댓글 등 네이버 외 신규 채널에서 청주 한의원 잠재고객 자연 질문/리뷰를 수집해 mentions 테이블에 적재. cron 안 씀, 운영자 수동 트리거.
license: Internal
---

# Viral Channels — 신규 콘텐츠 수집 채널

기존 viral_hunter(네이버 카페/블로그/지식인) + cafe_spy(맘카페) 외에 **2026 한국 사용자 행동 변화에 맞춘 3개 신규 채널**:
카카오맵 리뷰(MAU 1,282만) / Threads 한국(MAU 543만, +500%) / 네이버 클립 댓글.

## When to use

- "카카오맵 리뷰 가져와" / "청주 한의원 카카오맵 후기"
- "Threads 멘션" / "스레드 솔직 후기 모아줘"
- "클립 댓글 lead" / "영상 댓글에서 질문 찾아"
- "네이버 외 어디서 사람들 얘기하나" — 3개 채널 모두 한 번에
- "부정 리뷰 조기 감지" — 카카오맵 sentiment

## Decision tree

```
사용자 의도 → 도구 선택
─────────────────────────────────────
"카카오맵" / "별점 후기"               → kakao_map_reviews.py
"Threads" / "스레드"                   → threads_collector.py
"클립" / "영상 댓글"                   → naver_clip_collector.py
"신규 채널 한바퀴"                     → 3개 순차 실행 (각 keyword 동일)
"부정 리뷰" / "부정적 후기"            → kakao_map_reviews.py (sentiment 자동 분류)
```

## Commands

```bash
# === R4 카카오맵 리뷰 ===
python scrapers/kakao_map_reviews.py --keyword "청주 한의원" --top 10 --dry-run
python scrapers/kakao_map_reviews.py --keyword "청주 한의원" --top 10
python scrapers/kakao_map_reviews.py --place-id 12345 --reviews 50

# === R5 Threads 한국 ===
python scrapers/threads_collector.py --keyword "청주 한의원" --dry-run
python scrapers/threads_collector.py --keyword "청주 한의원" --top 30
python scrapers/threads_collector.py --keyword "다이어트 한약" --top 50

# === R9 네이버 클립 댓글 ===
python scrapers/naver_clip_collector.py --keyword "청주 한의원" --top 20 --dry-run
python scrapers/naver_clip_collector.py --keyword "청주 한의원" --top 20
```

## Workflow

1. **사전 점검** — 같은 키워드 24h 내 수집 이력:
   ```sql
   SELECT source, source_subtype, COUNT(*) FROM mentions
    WHERE keyword = ? AND scraped_at >= datetime('now','-24 hours')
    GROUP BY source, source_subtype;
   ```

2. **dry-run 우선** — 각 도구 모두 `--dry-run` 지원. 대상 수 확인 후 사용자 동의.

3. **실행 + 후속 안내** — 모든 신규 mentions는 status='pending'으로 적재. AI 분류 권장:
   ```bash
   python scripts/ai_ad_classify_submit.py --limit 200
   # SUCCEEDED 후
   python scripts/ai_ad_classify_apply.py db/batch_jobs/ad_classify_<TS>
   ```

4. **부정 리뷰 알림** — 카카오맵 sentiment='negative' 발견 시 즉시 사용자에게 보고.

## 보고 템플릿

```markdown
**신규 채널 수집 완료** (채널 N개, 키워드 "K", 신규 M건)

**채널별 결과**
| 채널 | 수집 | 자연 질문 | 부정 리뷰 | 게시 가능 |
|------|------|-----------|-----------|-----------|
| 카카오맵 | N | - | N (⚠️ X건) | - |
| Threads | N | N | - | N |
| 클립 댓글 | N | N | - | N |

**🚨 부정 리뷰 알림** (해당 시만)
- "[제목/내용 첫 30자]" — sentiment=negative, 작성일 X일 전
- 권장: web UI에서 직접 검토 + 응답 작성

**🔥 자연 질문 lead top 3**
1. [content 첫 50자] (channel, 작성자)

**다음 액션**
- AI 분류: `python scripts/ai_ad_classify_submit.py --limit N`
- 부정 리뷰 X건은 web UI /leads 또는 /viral에서 우선 검토
```

## Guardrails

1. **ToS/rate limit 준수**
   - 카카오맵: robots.txt 허용 영역만, 1초 간격
   - Threads: Meta ToS — 공개 게시물만, 1 req/sec, 인증 우회 금지
   - 클립: 네이버 SERP rate limit 준수, 봇 탐지 회피용 Camoufox
2. **Selenium driver 충돌 회피** — 같은 시간대에 cafe_spy/scraper_naver_place 동시 실행 시 driver 경합. 사용자에게 동시 실행 여부 확인.
3. **신규 mentions은 status='pending'** — 직접 사용 안 함. AI 분류 거쳐야 lead 큐 진입.
4. **AI 분류 재실행** — 신규 채널 수집 후 반드시 안내. 본문 짧은 카페·블로그처럼 분류 누락 방지.
5. **stub/휴리스틱 영역** — 클립 검색·Threads SERP·카카오맵 검색은 selector 변동 가능. 결과 0건이면 selector 정밀화 필요.
6. **AEO 모니터링과 함께** — 신규 채널 수집 후 `aeo-tracker`로 LLM 검색 노출 변화도 함께 추적 권장.

## 출력 길이

- 채널별 결과 표 (3행)
- 부정 리뷰는 모두 나열 (5건 이상이면 top 5 + 외 N개)
- 자연 질문 top 3
- 다음 액션 1-2개

## 관련 파일/테이블

- `scrapers/kakao_map_reviews.py` (R4) → `kakao_map_reviews` 테이블
- `scrapers/threads_collector.py` (R5) → `mentions.source_subtype='threads_post'`
- `scrapers/naver_clip_collector.py` (R9) → `mentions.source_subtype='clip_comment'`
- 의존: `scrapers/camoufox_engine.py`, `scrapers/cafe_spy.py` (Selenium driver)
- 후속 스킬: `viral-comment-drafter` (단일 lead → 댓글 초안), `viral-enrich` (본문 풍부화)

---
name: query
description: 자연어 데이터 질문을 받아 SQLite DB(marketing_data.db)를 조회하고 자연어로 답변. SELECT 전용, DML 절대 금지, 화이트리스트 테이블만 사용. 적절한 스캔 스킬이 따로 있으면 그쪽으로 안내.
license: Internal
---

# Query — 자연어 DB 조회

"최근 30일 1위 키워드", "뷰가 가장 많은 바이럴", "전환율 가장 높은 카테고리" 같은 ad-hoc 질문을 받아 **SELECT 쿼리로 답하고 자연어로 요약**.

## When to use

- 다른 scan-* 스킬이 매칭 안 되는 일반 데이터 질문
- "뭐가 제일 많아", "어떤 게 가장 X해", "지난주 평균 Y" 같은 집계 질문
- "이 키워드 히스토리", "이 경쟁사 리뷰 추이" 같은 단일 엔티티 조회

## When NOT to use (다른 스킬로 위임)

| 질문 | 위임 스킬 |
|---|---|
| "순위 다시 스캔해" | `scan-ranks` (스캔 트리거) |
| "키워드 발굴해" | `scan-pathfinder` |
| "경쟁사 변화 봐줘" | `scan-competitors` |
| "오늘 종합 브리핑" | `brief` |
| "수집 상태 어때" | `data-health` |
| **"~ 보여줘" / "~ 알려줘" / "~ 어떤 게 가장"** | ✅ 이 스킬 사용 |

## Workflow

1. **질문 의도 파악** — 다음 중 어디에 해당?
   - **단일 엔티티 조회**: "이 키워드 히스토리" → WHERE keyword = ?
   - **집계**: "가장 많은", "평균", "총합" → GROUP BY + ORDER BY
   - **시계열**: "지난주 / 한 달 / 어제" → WHERE 날짜 절
   - **비교**: "X와 Y" → 두 쿼리 후 비교

2. **테이블 화이트리스트 확인** (아래 표만 허용. 그 외는 거부):

   | 테이블 | 컬럼 (핵심) | 행수 |
   |---|---|---|
   | `rank_history` | keyword, device_type, rank, status, checked_at, date, star_rating | 8400+ |
   | `keyword_insights` | keyword, grade, search_volume, document_count, kei, mf_kei_score, priority_v3, category, created_at | 6200+ |
   | `competitor_reviews` | competitor_name, star_rating, content, sentiment, scraped_at | 350+ |
   | `competitor_changes` | competitor_name, change_type, severity, old_value, new_value, detected_at | varies |
   | `competitor_blog_activity` | competitor_name, blog_title, blog_link, post_date, detected_at | varies |
   | `competitor_visual_scores` | competitor_name, interior_cleanliness, facility_modernity, staff_visible, patient_review_photos, weakness_summary, scanned_date, created_at | varies |
   | `viral_targets` | platform, url, comment_status, matched_keyword, view_count, like_count, comment_count, discovered_at, first_seen_at | 53800+ |
   | `mentions` | platform, summary, author, source_module, category, created_at, scraped_at | 890 |
   | `community_mentions` | platform, content_preview, mention_type, is_lead_candidate, scanned_at, created_at | 1640+ |
   | `healthcare_news` | title, source, pub_date, is_competitor_mention, is_our_mention, created_at | 859 |
   | `intelligence_reports` | report_type, report_date, summary, details, alerts, created_at | varies |
   | `serp_features` | keyword, has_place_pack, has_ai_briefing, ai_briefing_text, ai_briefing_includes_us, place_clip_count, scanned_at | varies |
   | `job_runs` | job_name, status, started_at, ended_at, duration_seconds, exit_code | varies |
   | `ai_call_log` | model, caller_module, input_tokens, output_tokens, cost_usd, cache_hit, created_at | varies |
   | `qa_repository` | question_pattern, question_category, standard_answer, variations, use_count | varies |

3. **SELECT 쿼리 작성** — 다음 규칙:
   - **반드시 SELECT만**. INSERT/UPDATE/DELETE/DROP/ALTER 절대 금지.
   - **LIMIT 항상 명시** (기본 100, 사용자가 더 많이 요청해도 1000 상한).
   - **시계열 필터**는 `datetime('now', '-N days')` 사용.
   - **파라미터 바인딩** — 사용자 입력은 `?` 플레이스홀더로.

4. **실행 + 자연어 요약** — `python -c` 또는 sqlite3 CLI로:
   ```bash
   sqlite3 db/marketing_data.db "SELECT ... LIMIT 100"
   ```
   결과를 raw로 던지지 말고 **요약 + 핵심 숫자 강조**.

5. **사용자 보고** (필수)

## 보고 템플릿

```markdown
**[질문 한 줄 재서술]**

**핵심 숫자**
- (예) 총 N개 / 평균 X / 최고 Y
- (예) 1위: A (값 N), 2위: B (값 M), 3위: C (값 L)

**상세** (top 5 또는 그래프형 데이터)
- ...

**한 줄 인사이트**
- (예) "다이어트 카테고리가 평균 검색량 1.5배 높음 — 리소스 집중 추천"
```

## Guardrails

1. **DML 절대 금지** — `INSERT|UPDATE|DELETE|DROP|ALTER|REPLACE|CREATE|TRUNCATE` 키워드 감지 시 즉시 거부.
2. **테이블 화이트리스트 위반 거부** — 위 표에 없는 테이블 조회 요청은 "지원하지 않는 테이블입니다, 직접 SQL을 작성하세요"로 응답.
3. **사용자 입력 SQL injection 방어** — 키워드명 등은 반드시 파라미터 바인딩.
4. **개인정보 컬럼 마스킹** — `viral_targets.author`, `mentions.author` 등은 일부만 표시 (예: "user_*" → "u***").
5. **쿼리 결과 1000행 초과 시** 요약만 보고 + "정확한 추출이 필요하면 export 사용 권장" 안내.

## 자주 쓰는 패턴

```sql
-- 최근 30일 1위 키워드
SELECT keyword, COUNT(*) days_at_top, MAX(checked_at) last_seen
FROM rank_history
WHERE rank=1 AND device_type='mobile' AND checked_at >= datetime('now', '-30 days')
GROUP BY keyword ORDER BY days_at_top DESC LIMIT 20;

-- 등급별 키워드 분포
SELECT grade, COUNT(*), AVG(search_volume), AVG(kei)
FROM keyword_insights GROUP BY grade;

-- 카테고리별 평균 KEI
SELECT category, COUNT(*), AVG(kei)
FROM keyword_insights WHERE category IS NOT NULL
GROUP BY category ORDER BY AVG(kei) DESC;

-- 경쟁사별 리뷰 평균/최근
SELECT competitor_name, COUNT(*) total, AVG(star_rating) avg_rating, MAX(scraped_at) last
FROM competitor_reviews GROUP BY competitor_name;

-- 바이럴 플랫폼별 처리율
SELECT platform, comment_status, COUNT(*) FROM viral_targets
WHERE discovered_at >= datetime('now', '-30 days')
GROUP BY platform, comment_status;

-- AI 비용 (지난 7일)
SELECT model, caller_module, SUM(cost_usd) total, COUNT(*) calls
FROM ai_call_log
WHERE created_at >= datetime('now', '-7 days')
GROUP BY model, caller_module ORDER BY total DESC;
```

## 출력 길이

- 단일 답변: 5~10줄
- top N 리스트: 최대 20개 (그 이상은 "외 M개")
- 인사이트는 항상 1~2줄로 마무리

## 관련 파일

- DB: `db/marketing_data.db`
- 백업 정책 위반 절대 금지 (DML이 차단되어 있으므로 read-only 안전)

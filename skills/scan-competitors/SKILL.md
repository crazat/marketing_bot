---
name: scan-competitors
description: 경쟁사 변화(영업정보·사진·메뉴), 신규 리뷰, 블로그 활동, 시각 콘텐츠 점수를 스캔/조회하고 자연어로 보고. 어제 대비 / 지난주 대비 변화를 요약.
license: Internal
---

# Scan Competitors — 경쟁사 변화 감지 + 인사이트 보고

경쟁사 한의원/병원의 (a) Place 정보 변경, (b) 신규 리뷰, (c) 블로그 포스팅, (d) Instagram 시각 점수를 추적하고 변화를 보고.

## When to use

- "경쟁사 변화 보여줘" / "어제부터 경쟁사 뭐 했어"
- "경쟁사 리뷰 새로 들어온 거" / "리뷰 변화"
- "경쟁사 블로그 활동" / "경쟁사 포스팅 본 거"
- "경쟁사 사진 비교" / "시각 점수"

## Decision tree

```
사용자 의도 → 어떤 모듈을 돌릴지
────────────────────────────────────
Place 정보 변경 (영업정보/사진/메뉴) → competitor_change_detector.py
신규 리뷰만                          → scraper_naver_place.py (--skip-reviews 빼고 전체)
블로그 활동                          → competitor_blog_tracker.py
Instagram 시각 점수                  → competitor_visual_analyzer.py
"전반적으로 봐" 모호한 요청            → DB만 조회 (이미 cron이 매일 돌고 있음)
```

## Commands

```bash
# Place 변경 감지 (07:30 cron 활성, ad-hoc 실행 시)
python scrapers/competitor_change_detector.py

# 경쟁사 블로그 포스팅 추적 (11:30 cron)
python scrapers/competitor_blog_tracker.py

# Instagram 시각 분석 (월 $0.90, 9곳 × 20장)
python scrapers/competitor_visual_analyzer.py

# 신규 리뷰 (전체 순위 스캔에 포함됨)
python scrapers/scraper_naver_place.py
```

## Workflow

1. **DB 우선 조회** — cron이 이미 매일 돌고 있음. 신선한 데이터가 있으면 스크립트 다시 안 돌림.
   ```sql
   -- 어제 이후 변경
   SELECT competitor_name, change_type, old_value, new_value, detected_at
   FROM competitor_changes
   WHERE detected_at >= datetime('now', '-1 day')
   ORDER BY detected_at DESC;

   -- 신규 리뷰 (24h)
   SELECT competitor_name, COUNT(*) new_reviews, AVG(star_rating) avg_rating
   FROM competitor_reviews
   WHERE scraped_at >= datetime('now', '-1 day')
   GROUP BY competitor_name
   HAVING new_reviews > 0;

   -- 블로그 신규 포스팅 (7d)
   SELECT competitor_name, blog_link, blog_title, post_date
   FROM competitor_blog_activity
   WHERE detected_at >= datetime('now', '-7 days')
   ORDER BY post_date DESC LIMIT 20;

   -- Visual 점수 (월간)  -- 컬럼: interior_cleanliness, facility_modernity (REAL), staff_visible, patient_review_photos (INTEGER)
   SELECT competitor_name,
          interior_cleanliness, facility_modernity, staff_visible, patient_review_photos,
          weakness_summary
   FROM competitor_visual_scores
   WHERE created_at >= datetime('now', '-30 days')
   ORDER BY created_at DESC;
   ```

2. **데이터 부족 시에만 스크립트 실행** — 마지막 scraped_at/detected_at이 25시간 이상 지났으면 ad-hoc 실행 권장하고 사용자 확인.

3. **사용자 보고** (필수)

## 보고 템플릿

```markdown
**경쟁사 변화 리포트** (기간: 최근 N일, 데이터 신선도: X시간 전 수집)

**📍 Place 정보 변경** (어제 이후 N건)
- [경쟁사명] 영업시간 변경: "월~금 09:00-18:00" → "월~토 09:00-20:00"
- [경쟁사명] 대표사진 교체 (이미지 URL)
- ...

**⭐ 신규 리뷰** (24시간)
- [경쟁사명] 신규 N개, 평균 ★X.X
  - 인상 깊은 리뷰: "..." (★1, 부정 키워드: 대기시간)
- ...

**📝 블로그 활동** (지난 7일)
- [경쟁사명] N개 포스팅
  - "포스팅 제목" (YYYY-MM-DD, 키워드: 다이어트, 산후조리)
- ...

**🎨 Place 시각 점수** (월간 — 인테리어/시설 모더니티 0~5, 직원/리뷰사진 카운트)
- [경쟁사명] 인테리어 X.X / 시설 X.X / 직원 N명 / 환자 사진 N장 — 약점: ...
- 우리 평균과 비교: ...

**한 줄 인사이트**
- (예) "[경쟁사 A]가 어제 신규 리뷰 5개 동시 등록 — 마케팅 캠페인 의심"
- (예) "블로그 활동은 [경쟁사 B]가 최근 가장 활발 (주 4회 포스팅)"

**추천 액션**
- [구체적 제안]
```

## Guardrails

1. **DB 데이터 우선** — 스크립트는 비싸고 느림. 24시간 이내 데이터면 그대로 사용.
2. **대량 리뷰 등록 의심** — 한 경쟁사가 24h 내 5개 이상 리뷰 받았으면 "조작 의심" 플래그.
3. **시각 분석은 월 1회** — 비용($0.90/월) 고려, ad-hoc 실행 자제.
4. **자기 한의원 제외** — `business_profile.json::self_exclusion` 매칭은 결과에서 제외.

## 출력 길이

- 변화 5건 이내 → 모두 나열
- 5건 초과 → 카테고리별 top 3 + "외 N건"
- 인사이트 1~3줄

## 관련 테이블

- `competitor_changes` — Place 정보 변경 이력
- `competitor_reviews` (356+ 행) — 리뷰 데이터
- `competitor_blog_activity` — 블로그 포스팅 추적
- `competitor_visual_scores` — Place 사진 시각 점수 (interior_cleanliness/facility_modernity/staff_visible/patient_review_photos)
- `competitor_weaknesses` — AI 약점 분석

# Pathfinder V3 - 전체 재설계 계획

**작성일**: 2026-01-26
**목표**: 실제 SEO 경쟁력 기반 키워드 분석 시스템

---

## 1. 현재 시스템 (V2) 문제점

| 문제 | 영향 |
|------|------|
| KEI = 검색량/블로그수 단순 공식 | 실제 경쟁 강도 반영 못함 |
| AI 생성 비현실적 키워드 | 가짜 Golden 대량 생성 |
| SERP 분석 없음 | 상위 블로그 품질 모름 |
| 경쟁사 분석 없음 | 검증된 키워드 놓침 |

---

## 2. V3 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                    PATHFINDER V3                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Phase 1    │  │   Phase 2    │  │   Phase 3    │          │
│  │  실제 키워드  │→│  SERP 분석   │→│  경쟁사 역분석 │          │
│  │    수집      │  │              │  │              │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         │                │                  │                   │
│         ▼                ▼                  ▼                   │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              Phase 4: 통합 점수 계산                 │       │
│  │                                                      │       │
│  │  Priority = 검색량 × (1/난이도) × 의도가중치 × 틈새보너스  │       │
│  └─────────────────────────────────────────────────────┘       │
│                           │                                     │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              최종 키워드 우선순위 리스트               │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Phase 1: 실제 키워드 수집

### 3.1 Naver 자동완성 수집기

**파일**: `scrapers/naver_autocomplete.py`

```python
class NaverAutocompleteScraper:
    """
    Naver 자동완성 API를 통해 실제 검색되는 키워드 수집
    """

    def get_autocomplete(self, seed: str) -> List[str]:
        """
        "청주 다이어트" 입력 시:
        → ["청주 다이어트 한의원", "청주 다이어트 가격",
           "청주 다이어트 후기", "청주 다이어트 약", ...]
        """
        url = f"https://ac.search.naver.com/nx/ac"
        params = {
            "q": seed,
            "con": 1,
            "frm": "nv",
            "ans": 2,
            "r_format": "json",
            "r_enc": "UTF-8",
            "r_unicode": 0,
            "t_koreng": 1,
            "run": 2,
            "rev": 4,
            "q_enc": "UTF-8"
        }
        # ... 구현
```

### 3.2 Naver 연관검색어 수집기

```python
def get_related_keywords(self, keyword: str) -> List[str]:
    """
    네이버 검색 결과 페이지에서 연관검색어 추출

    "청주 한의원" 검색 시:
    → 연관검색어: ["청주 한의원 추천", "청주 한의원 잘하는곳",
                   "청주 교통사고 한의원", ...]
    """
    # 네이버 검색 결과 페이지 크롤링
    # 연관검색어 섹션 파싱
```

### 3.3 시드 확장 로직

```python
def expand_seeds(base_seeds: List[str]) -> List[str]:
    """
    기본 시드 → 자동완성 → 연관검색어 → 중복 제거

    입력: ["청주 다이어트", "청주 한의원"]
    출력: 200-500개의 실제 검색 키워드
    """
    all_keywords = set()

    for seed in base_seeds:
        # 1. 자동완성 (1차 확장)
        autocomplete = get_autocomplete(seed)
        all_keywords.update(autocomplete)

        # 2. 연관검색어 (2차 확장)
        for kw in autocomplete[:10]:  # 상위 10개만
            related = get_related_keywords(kw)
            all_keywords.update(related)

    return list(all_keywords)
```

---

## 4. Phase 2: SERP 분석

### 4.1 검색 결과 크롤러

**파일**: `scrapers/naver_serp_analyzer.py`

```python
class NaverSERPAnalyzer:
    """
    네이버 검색 결과 1페이지 분석
    """

    def analyze_serp(self, keyword: str) -> SERPAnalysis:
        """
        검색 결과 상위 10개 블로그 분석

        반환:
        - top_10_blogs: 상위 10개 블로그 정보
        - difficulty_score: 난이도 점수 (0-100)
        - opportunity_score: 기회 점수 (0-100)
        """
```

### 4.2 블로그 품질 분석

```python
@dataclass
class BlogAnalysis:
    url: str
    title: str

    # 콘텐츠 품질 지표
    word_count: int          # 글자 수
    image_count: int         # 이미지 수
    video_count: int         # 동영상 수

    # 블로그 권위 지표
    blog_type: str           # "official" | "personal" | "influencer"
    subscriber_count: int    # 이웃/구독자 수
    total_posts: int         # 총 게시글 수

    # 시간 지표
    publish_date: datetime   # 발행일
    days_since_publish: int  # 발행 후 경과일

    # 경쟁력 점수
    quality_score: int       # 0-100

def analyze_blog(blog_url: str) -> BlogAnalysis:
    """
    개별 블로그 포스트 품질 분석
    """
    # 글자 수: 2000자 이상 = 강함, 1000자 미만 = 약함
    # 이미지 수: 5개 이상 = 강함, 3개 미만 = 약함
    # 발행일: 3개월 이내 = 강함, 1년 이상 = 약함
    # 블로그 타입: 공식 블로그 = 강함, 개인 블로그 = 약함
```

### 4.3 키워드 난이도 계산

```python
def calculate_difficulty(serp_analysis: SERPAnalysis) -> int:
    """
    SERP 분석 결과를 바탕으로 키워드 난이도 계산

    난이도 점수 (0-100):
    - 0-30: 쉬움 (개인 블로그 위주, 오래된 글)
    - 31-60: 보통 (혼합)
    - 61-100: 어려움 (공식 블로그 위주, 최신 글, 고품질)
    """
    scores = []

    for blog in serp_analysis.top_10_blogs:
        score = 0

        # 글자 수 점수
        if blog.word_count >= 3000: score += 25
        elif blog.word_count >= 2000: score += 20
        elif blog.word_count >= 1000: score += 10

        # 이미지 수 점수
        if blog.image_count >= 10: score += 20
        elif blog.image_count >= 5: score += 15
        elif blog.image_count >= 3: score += 10

        # 블로그 타입 점수
        if blog.blog_type == "official": score += 30
        elif blog.blog_type == "influencer": score += 20
        else: score += 5

        # 발행일 점수
        if blog.days_since_publish <= 30: score += 25
        elif blog.days_since_publish <= 90: score += 15
        elif blog.days_since_publish <= 180: score += 10

        scores.append(score)

    # 상위 5개 평균
    return int(sum(sorted(scores, reverse=True)[:5]) / 5)
```

### 4.4 기회 점수 계산

```python
def calculate_opportunity(serp_analysis: SERPAnalysis) -> int:
    """
    기회 점수 = 약한 경쟁자가 많을수록 높음

    기회 지표:
    - 오래된 글이 상위에 있음 (6개월+)
    - 글자 수 적은 글이 상위에 있음 (1000자 미만)
    - 이미지 없는 글이 상위에 있음
    - 개인 블로그가 상위 5개 안에 있음
    """
    opportunity = 0

    for i, blog in enumerate(serp_analysis.top_10_blogs[:5]):
        position_weight = (5 - i) * 2  # 상위일수록 가중치

        if blog.days_since_publish > 180:
            opportunity += 15 * position_weight

        if blog.word_count < 1000:
            opportunity += 10 * position_weight

        if blog.image_count < 3:
            opportunity += 10 * position_weight

        if blog.blog_type == "personal":
            opportunity += 20 * position_weight

    return min(opportunity, 100)  # 최대 100
```

---

## 5. Phase 3: 경쟁사 역분석

### 5.1 경쟁사 블로그 목록

**파일**: `config/competitors.json`

```json
{
    "competitors": [
        {
            "name": "A한의원",
            "blog_url": "https://blog.naver.com/a_clinic",
            "naver_place_id": "12345678"
        },
        {
            "name": "B한의원",
            "blog_url": "https://blog.naver.com/b_clinic",
            "naver_place_id": "23456789"
        }
    ]
}
```

### 5.2 경쟁사 키워드 역추적

**파일**: `scrapers/competitor_analyzer.py`

```python
class CompetitorAnalyzer:
    """
    경쟁사 블로그 분석 및 키워드 역추적
    """

    def get_competitor_keywords(self, blog_url: str) -> List[KeywordData]:
        """
        경쟁사 블로그의 상위 노출 키워드 역추적

        방법 1: 블로그 글 제목에서 키워드 추출
        방법 2: 각 글의 검색 순위 확인
        """

    def find_gap_keywords(self,
                          competitor_keywords: List[str],
                          our_keywords: List[str]) -> List[str]:
        """
        경쟁사는 공략하지만 우리는 없는 키워드 (갭 분석)
        """

    def find_weak_spots(self, keyword: str) -> List[str]:
        """
        경쟁사가 약한 키워드 찾기
        - 경쟁사 글이 없거나
        - 경쟁사 글이 품질 낮음
        """
```

### 5.3 블로그 포스트 분석

```python
def analyze_competitor_blog(blog_url: str) -> CompetitorAnalysis:
    """
    경쟁사 블로그 전체 분석

    반환:
    - total_posts: 총 게시글 수
    - posts_by_category: 카테고리별 게시글 분포
    - top_performing_posts: 상위 노출 게시글
    - keyword_frequency: 자주 사용하는 키워드
    - posting_frequency: 발행 빈도
    - avg_word_count: 평균 글자 수
    """
```

---

## 6. Phase 4: 통합 점수 계산

### 6.1 새로운 우선순위 공식

```python
def calculate_priority_v3(keyword_data: KeywordData) -> float:
    """
    V3 우선순위 점수 계산

    Priority = 검색량 × (1/난이도) × 의도가중치 × 틈새보너스

    - 검색량: Naver Ad API
    - 난이도: SERP 분석 결과 (0-100)
    - 의도가중치: 구매 의도 키워드 보너스
    - 틈새보너스: 경쟁사 갭 키워드 보너스
    """

    # 기본 점수: 검색량
    base_score = keyword_data.search_volume

    # 난이도 보정 (난이도 낮을수록 높은 점수)
    difficulty_factor = (100 - keyword_data.difficulty) / 100

    # 기회 보너스
    opportunity_factor = 1 + (keyword_data.opportunity / 100)

    # 의도 가중치
    intent_weight = 1.0
    if any(w in keyword_data.keyword for w in ["가격", "비용"]):
        intent_weight = 1.5  # 구매 의도 50% 보너스
    elif any(w in keyword_data.keyword for w in ["후기", "추천"]):
        intent_weight = 1.3  # 신뢰 의도 30% 보너스

    # 틈새 보너스 (경쟁사 갭 키워드)
    gap_bonus = 1.5 if keyword_data.is_gap_keyword else 1.0

    # 최종 점수
    priority = (base_score
                * difficulty_factor
                * opportunity_factor
                * intent_weight
                * gap_bonus)

    return priority
```

### 6.2 키워드 등급 재정의

```python
def assign_grade(keyword_data: KeywordData) -> str:
    """
    새로운 등급 시스템 (난이도 + 기회 기반)

    등급 기준:
    - S급: 난이도 낮음 + 기회 높음 + 검색량 100+
    - A급: 난이도 낮음 + 검색량 50+ 또는 기회 높음
    - B급: 난이도 보통 + 검색량 30+
    - C급: 난이도 높음 또는 검색량 낮음
    """

    if (keyword_data.difficulty <= 30
        and keyword_data.opportunity >= 70
        and keyword_data.search_volume >= 100):
        return "S"  # 최우선 공략

    elif (keyword_data.difficulty <= 40
          and (keyword_data.search_volume >= 50
               or keyword_data.opportunity >= 60)):
        return "A"  # 적극 공략

    elif (keyword_data.difficulty <= 60
          and keyword_data.search_volume >= 30):
        return "B"  # 보조 공략

    else:
        return "C"  # 장기 전략
```

---

## 7. 데이터베이스 스키마 확장

```sql
-- 기존 keyword_insights 테이블 확장
ALTER TABLE keyword_insights ADD COLUMN difficulty INTEGER DEFAULT 50;
ALTER TABLE keyword_insights ADD COLUMN opportunity INTEGER DEFAULT 50;
ALTER TABLE keyword_insights ADD COLUMN priority_v3 REAL DEFAULT 0;
ALTER TABLE keyword_insights ADD COLUMN grade TEXT DEFAULT 'C';
ALTER TABLE keyword_insights ADD COLUMN is_gap_keyword BOOLEAN DEFAULT FALSE;
ALTER TABLE keyword_insights ADD COLUMN serp_analyzed_at TIMESTAMP;

-- 새로운 테이블: SERP 분석 결과
CREATE TABLE serp_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT UNIQUE,
    top_10_json TEXT,  -- 상위 10개 블로그 JSON
    difficulty INTEGER,
    opportunity INTEGER,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 새로운 테이블: 경쟁사 분석
CREATE TABLE competitor_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor_name TEXT,
    blog_url TEXT,
    total_posts INTEGER,
    top_keywords_json TEXT,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 새로운 테이블: 갭 키워드
CREATE TABLE gap_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT UNIQUE,
    found_in_competitor TEXT,
    our_status TEXT,  -- "없음" | "약함" | "강함"
    priority REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 8. 새로운 대시보드 메트릭

```python
# dashboard_ultra.py 추가 섹션

# 1. 난이도 분포 차트
difficulty_distribution = {
    "쉬움 (0-30)": count_easy,
    "보통 (31-60)": count_medium,
    "어려움 (61-100)": count_hard
}

# 2. 기회 매트릭스 (검색량 vs 난이도)
opportunity_matrix = plot_scatter(
    x=search_volume,
    y=difficulty,
    size=opportunity,
    color=grade
)

# 3. 경쟁사 갭 키워드 리스트
gap_keywords_table = display_gap_keywords()

# 4. 등급별 키워드 현황
grade_summary = {
    "S급 (즉시 공략)": count_s,
    "A급 (적극 공략)": count_a,
    "B급 (보조 공략)": count_b,
    "C급 (장기 전략)": count_c
}
```

---

## 9. 구현 로드맵

### Week 1: Phase 1 (실제 키워드 수집)
- Day 1-2: `naver_autocomplete.py` 구현
- Day 3-4: 연관검색어 수집 구현
- Day 5: 시드 확장 로직 통합

### Week 2: Phase 2 (SERP 분석)
- Day 1-2: `naver_serp_analyzer.py` 구현
- Day 3-4: 블로그 품질 분석 구현
- Day 5: 난이도/기회 점수 계산

### Week 3: Phase 3 (경쟁사 역분석)
- Day 1-2: `competitor_analyzer.py` 구현
- Day 3-4: 갭 키워드 분석
- Day 5: 경쟁사 약점 분석

### Week 4: Phase 4 (통합)
- Day 1-2: 새로운 우선순위 공식 구현
- Day 3-4: DB 스키마 확장 및 마이그레이션
- Day 5: 대시보드 업데이트

---

## 10. 예상 결과

### Before (V2)
```
- 총 키워드: 1,172개
- KEI 500+: 1개 (0.1%)
- 실제 공략 가능 여부: 알 수 없음
- 경쟁사 대비 우위: 알 수 없음
```

### After (V3)
```
- 총 키워드: 300-500개 (실제 검색되는 것만)
- S급 (즉시 공략): 10-20개
- A급 (적극 공략): 30-50개
- B급 (보조 공략): 50-100개
- 갭 키워드: 20-50개
- 실제 공략 가능 여부: SERP 분석으로 검증
- 경쟁사 대비 우위: 갭 분석으로 확인
```

---

## 11. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| Naver 크롤링 차단 | SERP 분석 불가 | User-Agent 로테이션, 딜레이 |
| 분석 시간 증가 | 전체 실행 시간 증가 | 비동기 처리, 캐싱 |
| 경쟁사 블로그 비공개 | 역분석 제한 | 공개 데이터만 활용 |

---

## 12. 성공 지표

| 지표 | 목표 |
|------|------|
| S급 키워드 발굴 | 10개 이상 |
| A급 키워드 발굴 | 30개 이상 |
| 갭 키워드 발굴 | 20개 이상 |
| SERP 분석 정확도 | 실제 순위와 80% 일치 |
| 블로그 포스팅 후 상위 노출 | S급 키워드 70% 이상 |

---

*설계 문서 끝*

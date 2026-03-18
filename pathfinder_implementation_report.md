# Pathfinder V4 구현 보고서: 트렌드 속도 감지 및 경쟁사 갭 분석 (수정안)

본 보고서는 Pathfinder V4 "The Oracle"의 두 가지 핵심 기능인 **트렌드 속도 감지(Trend Velocity Detection)**와 **경쟁사 키워드 갭 분석(Competitive Gap Analysis)**에 대한 상세 구현 방안을 기술합니다.

사용자의 피드백을 반영하여, **키워드 수집의 다양성(Random Diversity)**으로 인해 내부 데이터 비교가 어렵다는 점을 감안, **네이버 데이터랩 API**를 메인 트렌드 분석 도구로 선정하였습니다.

---

## 1. 📈 트렌드 속도 감지 (Trend Velocity Detection: API First Strategy)

### 1.1 전략 변경 배경
*   **기존 제한점**: Pathfinder가 매번 랜덤하고 다양한 키워드(Legion Mode)를 수집하므로, "지난주 수집된 키워드"와 "오늘 수집된 키워드"가 일치할 확률이 낮습니다. 따라서 `(현재 - 과거) / 과거` 식의 내부 데이터 비교는 데이터 희소성(Sparsity) 문제로 인해 실효성이 떨어집니다.
*   **해결책**: 외부의 절대적인 기준인 **Naver Datalab API**를 적극 활용하여, 키워드가 언제 수집되었든 관계없이 "현재 시점의 트렌드 기울기"를 즉시 확인하는 **API First 전략**을 채택합니다.

### 1.2 핵심 로직: 스마트 샘플링 & Datalab API
모든 키워드(10만 개)에 대해 API를 호출할 수는 없으므로(일일 호출 제한 1,000회 예상), **"될성부른 떡잎(Golden Candidates)"**만 선별하여 정밀 검사를 수행합니다.

1.  **1차 필터링 (Volume Check)**:
    *   Naver Ad API(Keyword Tool)를 통해 확보한 `monthly_search_volume`이 의미 있는 수준(예: 1,000 이상)인 키워드만 1차 후보로 선정합니다.
    *   또는, 경쟁도가 낮은 'Blue Ocean' 키워드를 선정합니다.

2.  **2차 정밀 검사 (Trend Verification)**:
    *   선정된 후보군에 대해서만 `TheProphet._fetch_datalab_trend(keyword)`를 호출합니다.
    *   **Trend Slope(기울기)**를 계산하여 성장세인지 하락세인지 판별합니다.
    *   Slope > 0.5 (급상승) 인 경우 "Golden Key 🔥"로 최종 확정합니다.

### 1.3 데이터베이스 스키마 변경 (SQLite)
`keyword_insights` 테이블에 트렌드 지표를 저장합니다.

```sql
ALTER TABLE keyword_insights ADD COLUMN trend_slope REAL DEFAULT 0.0;         -- 데이터랩 추세선 기울기 (-1.0 ~ 1.0)
ALTER TABLE keyword_insights ADD COLUMN trend_status TEXT DEFAULT 'unknown';  -- 'rising', 'falling', 'flat'
ALTER TABLE keyword_insights ADD COLUMN last_trend_check TIMESTAMP;           -- API 호출 시점
```

### 1.4 구현 코드 (Pseudo-code)

**Pathfinder 클래스 내 로직 변경:**

```python
def verify_trends_smartly(self, candidates):
    """
    1차로 선별된 유망 키워드(candidates)에 대해서만 Datalab API를 호출하여 트렌드를 검증합니다.
    """
    from prophet import TheProphet
    prophet = TheProphet()
    
    verified_results = []
    
    # API 쿼타 보호를 위해 상위 N개만 수행
    target_kws = candidates[:50] 
    
    for kw_data in target_kws:
        kw = kw_data['keyword']
        
        # Datalab API 호출 (이미 prophet.py에 구현됨)
        # 최근 30일 데이터의 Linear Regression Slope 반환
        slope = prophet._fetch_datalab_trend(kw) 
        
        status = 'flat'
        if slope is None:
            status = 'unknown' # API 에러 또는 데이터 부족
        elif slope > 0.3:
            status = 'rising'
        elif slope < -0.3:
            status = 'falling'
            
        # 결과 업데이트
        kw_data['trend_slope'] = slope
        kw_data['trend_status'] = status
        
        if status == 'rising':
            self.send_golden_alert(kw, slope)
            
        verified_results.append(kw_data)
        
    return verified_results
```

### 1.5 실행 전략 (Cost-Effective)
*   **Ad API (Bulk)**: 검색량 확인용. 쿼타가 넉넉하므로 하베스팅 단계에서 전수 조사.
*   **Datalab API (Selective)**: 트렌드 검증용. 검색량 상위 10% 또는 '다이어트', '교통사고' 등 핵심 키워드 조합에 대해서만 선별적 호출.

---

## 2. 🎯 경쟁사 키워드 갭 분석 (Competitive Gap Analysis)

### 2.1 개요
경쟁 한의원(또는 병원)이 상위 노출을 점유하고 있는 키워드를 추출하여, 우리가 아직 공략하지 않은 "Gap 키워드"를 찾아내는 기능입니다.

### 2.2 분석 대상 및 방식
*   **대상**: 경쟁사 네이버 플레이스 주소 또는 블로그 ID 리스트 (설정 파일 `competitors.json` 관리)
*   **방식**: 경쟁사 블로그의 최근 게시글 제목과 태그를 크롤링하여 키워드를 추출합니다.

### 2.3 프로세스 상세
1.  **경쟁사 식별**: `config/competitors.json`에서 타겟 리스트 로드.
2.  **콘텐츠 수집**: 셀레니움 또는 Requests를 사용하여 경쟁사 블로그의 최근 20개 게시글 제목 수집.
3.  **키워드 추출**: 형태소 분석기(Kiwi 등) 또는 간단한 명사 추출 로직으로 핵심 키워드 분리.
4.  **갭(Gap) 연산**: 
    *   `Gap Set` = `Competitor Keywords` - `My Keywords (DB)`
    *   즉, 경쟁사는 쓰고 있지만 우리 DB에는 없거나(미발굴), 우리가 상위에 없는 키워드.

### 2.4 구현 코드 구조

**신규 모듈 `scrapers/competitor_spy.py` 생성:**

```python
class CompetitorSpy:
    def __init__(self):
        self.competitors = self._load_competitors() # config/competitors.json
        
    def scan_competitors(self):
        all_gaps = []
        for comp in self.competitors:
             # 1. 경쟁사 블로그 크롤링 (Mobile View 활용)
             # https://m.blog.naver.com/{blog_id}
             posts = self._scrape_blog_titles(comp['blog_id'])
             
             # 2. 키워드 추출 (간단한 명사 추출 또는 정규식)
             extracted_kws = self._extract_keywords(posts)
             
             # 3. 갭 분석 
             # (1) 우리 DB에 있는지 확인
             # (2) 없다면 -> 신규 발견 (Gap)
             for kw in extracted_kws:
                 if not self._check_db_existence(kw):
                     all_gaps.append({
                         "keyword": kw,
                         "source": comp['name'],
                         "type": "competitor_gap"
                     })
                     
        return all_gaps
```

### 2.5 데이터베이스 활용
*   발견된 Gap 키워드는 `keyword_insights` 테이블에 `tag='Competitor Gap'`으로 저장하여 우선적으로 콘텐츠를 생성하도록 유도합니다.

---

## 3. 통합 구현 로드맵 (수정됨)

안정성과 실효성을 최우선으로 하여 로드맵을 수정했습니다.

1.  **Phase 1: DB 스키마 & Datalab 연동 (D+1)**
    *   `keyword_insights` 테이블에 `trend_slope`, `trend_status` 컬럼 추가.
    *   `pathfinder.py`에서 **수집(Harvest) 직후**가 아니라, **저장(Save) 직전**에 상위 키워드만 선별하여 `prophet.py`를 호출하도록 로직 삽입.

2.  **Phase 2: 경쟁사 스파이 모듈 (D+2)**
    *   `competitors.json` 작성 및 `CompetitorSpy` 구현.
    *   경쟁사 블로그 크롤링은 네이버 차단을 피하기 위해 보수적인 주기(Daily 1회)로 설정.

3.  **Phase 3: 대시보드 시각화 (D+3)**
    *   "급상승(Rising) 키워드"와 "경쟁사 갭(Gap) 키워드"를 위한 전용 위젯 추가.

이 방식으로 구현하면, 복잡하고 부정확한 내부 데이터 비교 로직을 제거하고, **검증된 네이버 공식 데이터(Datalab)**를 통해 신뢰도 높은 트렌드 정보를 얻을 수 있습니다.

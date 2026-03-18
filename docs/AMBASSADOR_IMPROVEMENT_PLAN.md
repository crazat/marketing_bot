# Ambassador (인플루언서 발굴) 개선안

## 1. 현재 문제점 요약

| 문제 | 영향도 | 원인 |
|------|--------|------|
| Google 검색 불안정 | 🔴 High | 봇 감지, captcha, rate limit |
| Instagram 데이터 없음 | 🔴 High | 로그인 필요, API 제한 |
| 검색 결과 품질 낮음 | 🟠 Medium | 키워드 전략 부재 |
| 핵심 지표 없음 | 🔴 High | 팔로워/참여율 조회 불가 |

---

## 2. 개선 방향

### Option A: 네이버 블로그 인플루언서 (권장 ⭐)

**장점:**
- 네이버 Search API 활용 (안정적, 이미 사용 중)
- 블로그 지수, 이웃 수, 게시글 수 간접 추정 가능
- 한의원 업종과 블로그 마케팅 궁합 좋음
- 체험단/협찬 블로거 직접 발굴 가능

**구현 방식:**
```
1. 네이버 블로그 API로 "청주 한의원 후기", "청주 다이어트 후기" 검색
2. 상위 블로거 프로필 추출 (블로그 주소 → 블로그 ID)
3. 블로그 메타 정보 수집:
   - 이웃 수 (인기도 지표)
   - 총 게시글 수 (활동량)
   - 카테고리별 포스트 수 (관심 분야)
4. "체험단", "협찬", "리뷰" 키워드 포함 포스트 분석
5. AI로 협업 제안서 자동 생성
```

**예상 산출물:**
| 필드 | 예시 |
|------|------|
| blog_id | `happymom_cj` |
| blog_name | 청주 행복맘의 일상 |
| neighbor_count | 2,450 |
| total_posts | 1,230 |
| review_posts | 45 |
| sponsored_exp | ✅ 체험단 경험 있음 |
| relevance_score | 85/100 |
| draft_proposal | AI 생성 협업 제안서 |

---

### Option B: 유튜브 크리에이터

**장점:**
- YouTube Data API v3 공식 지원 (안정적)
- 구독자 수, 평균 조회수, 참여율 정확히 조회 가능
- 영상 콘텐츠 = 신뢰도 높음

**구현 방식:**
```
1. YouTube API로 "청주 맛집", "충북 일상", "청주 브이로그" 검색
2. 채널 정보 수집:
   - 구독자 수
   - 평균 조회수 (최근 10개 영상)
   - 영상 업로드 빈도
3. 지역 기반 필터링 (제목/설명에 "청주", "충북" 포함)
4. 협업 제안 DM/이메일 초안 생성
```

**필요 리소스:**
- YouTube Data API 키 (Google Cloud Console에서 발급)
- 일일 쿼터: 10,000 units/day (충분)

---

### Option C: 인플루언서 DB 수동 관리 + AI 보조

**장점:**
- 가장 정확한 데이터 (직접 검증)
- 협업 이력 추적 가능
- 장기적 관계 관리

**구현 방식:**
```
1. DB 테이블 생성: influencers
   - name, platform, handle, followers, avg_engagement
   - contact_info, collaboration_history, notes

2. 대시보드 UI:
   - 인플루언서 수동 등록 폼
   - 협업 상태 관리 (제안 → 협의 중 → 진행 → 완료)

3. AI 기능:
   - 인플루언서 프로필 기반 협업 제안서 자동 생성
   - 과거 협업 성과 분석
   - 최적 협업 대상 추천
```

---

### Option D: 기존 데이터 활용 (mentions 테이블)

**장점:**
- 추가 개발 최소화
- 이미 규림한의원에 관심 있는 사용자 타겟팅

**구현 방식:**
```
1. mentions 테이블에서 긍정적 콘텐츠 작성자 추출
2. 블로그/카페에서 규림한의원 언급한 사용자 우선 접근
3. AI로 감사 메시지 + 협업 제안 생성
```

---

## 3. 권장 구현 순서

### Phase 1: 네이버 블로그 인플루언서 (2주)
```
Week 1:
- [ ] 네이버 블로그 검색 API 연동
- [ ] 블로거 프로필 추출 로직
- [ ] influencers DB 테이블 생성

Week 2:
- [ ] 블로거 점수화 알고리즘 (활동량, 관련성)
- [ ] AI 협업 제안서 생성 프롬프트
- [ ] 대시보드 UI (인플루언서 목록, 상태 관리)
```

### Phase 2: 유튜브 크리에이터 (1주)
```
- [ ] YouTube Data API 키 발급
- [ ] 채널 검색 및 정보 수집
- [ ] 기존 influencers 테이블에 통합
```

### Phase 3: 협업 관리 시스템 (1주)
```
- [ ] 협업 상태 워크플로우 (제안 → 협의 → 진행 → 완료 → 성과분석)
- [ ] 협업 이력 추적
- [ ] ROI 분석 (협업 비용 vs 유입 효과)
```

---

## 4. 새로운 DB 스키마 제안

```sql
CREATE TABLE influencers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 기본 정보
    name TEXT NOT NULL,
    platform TEXT NOT NULL,  -- 'naver_blog', 'youtube', 'instagram', 'tiktok'
    handle TEXT NOT NULL,    -- 블로그ID, 채널ID, @handle
    profile_url TEXT,

    -- 지표 (플랫폼별로 의미 다름)
    followers INTEGER DEFAULT 0,      -- 이웃수/구독자수/팔로워
    avg_engagement REAL DEFAULT 0,    -- 평균 좋아요/조회수
    total_posts INTEGER DEFAULT 0,    -- 총 게시물 수

    -- 분석 결과
    relevance_score INTEGER DEFAULT 0,  -- 관련성 점수 (0-100)
    sponsored_experience BOOLEAN DEFAULT FALSE,  -- 협찬 경험 유무
    content_categories TEXT DEFAULT '[]',  -- JSON: ["다이어트", "육아", "맛집"]

    -- 연락처
    contact_email TEXT,
    contact_phone TEXT,
    contact_dm TEXT,

    -- 상태 관리
    status TEXT DEFAULT 'discovered',  -- discovered, contacted, negotiating, collaborated, declined

    -- 메타
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_contacted_at TIMESTAMP,

    UNIQUE(platform, handle)
);

CREATE TABLE influencer_collaborations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    influencer_id INTEGER NOT NULL,

    -- 협업 정보
    campaign_name TEXT,
    collaboration_type TEXT,  -- 'review', 'sponsored_post', 'event', 'giveaway'
    start_date TEXT,
    end_date TEXT,

    -- 비용/성과
    cost INTEGER DEFAULT 0,
    deliverables TEXT,  -- JSON: ["블로그 포스트 1건", "인스타 스토리 2건"]

    -- 결과
    result_url TEXT,
    impressions INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    conversions INTEGER DEFAULT 0,

    -- 평가
    satisfaction_score INTEGER,  -- 1-5
    notes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (influencer_id) REFERENCES influencers(id)
);
```

---

## 5. 개선된 Ambassador 클래스 구조

```python
class AmbassadorV2:
    """
    Multi-Platform Influencer Discovery & Management
    """
    def __init__(self):
        self.naver_client = NaverApiClient()
        self.youtube_client = YouTubeClient()  # Optional
        self.crew = AgentCrew()
        self.db = DatabaseManager()

    # 발굴
    def discover_naver_bloggers(self, keywords, location="청주"):
        """네이버 블로그 인플루언서 발굴"""
        pass

    def discover_youtube_creators(self, keywords, location="청주"):
        """유튜브 크리에이터 발굴"""
        pass

    def discover_from_mentions(self):
        """기존 mentions 데이터에서 잠재 인플루언서 발굴"""
        pass

    # 분석
    def analyze_blogger(self, blog_id):
        """블로거 상세 분석 (활동량, 관련성, 협찬 경험)"""
        pass

    def calculate_relevance_score(self, influencer):
        """관련성 점수 계산"""
        pass

    # 협업 관리
    def generate_proposal(self, influencer_id, campaign_type):
        """AI 협업 제안서 생성"""
        pass

    def update_status(self, influencer_id, status):
        """상태 업데이트"""
        pass

    def record_collaboration(self, influencer_id, collaboration_data):
        """협업 결과 기록"""
        pass

    # 리포트
    def get_discovery_report(self):
        """발굴 현황 리포트"""
        pass

    def get_collaboration_roi(self):
        """협업 ROI 분석"""
        pass
```

---

## 6. 예상 효과

| 지표 | 현재 | 개선 후 |
|------|------|---------|
| 발굴 성공률 | ~5% | 60%+ |
| 데이터 정확도 | 낮음 (추정) | 높음 (API 기반) |
| 플랫폼 커버리지 | Instagram만 | 네이버 블로그 + YouTube + Instagram |
| 협업 관리 | 없음 | 전체 워크플로우 추적 |
| ROI 측정 | 불가 | 협업별 성과 분석 가능 |

---

## 7. 결론

**즉시 적용 권장: Option A (네이버 블로그)**
- 이미 네이버 API 인프라 있음
- 한의원 업종과 블로그 마케팅 궁합 좋음
- 안정적인 데이터 수집 가능

**중기 확장: Option B (유튜브) + Option C (DB 관리)**
- 멀티 플랫폼 인플루언서 풀 구축
- 장기적 협업 관계 관리

---

*작성일: 2026-01-26*
*작성: Claude Code*

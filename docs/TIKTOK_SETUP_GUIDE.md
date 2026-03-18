# TikTok Research API 설정 가이드

## ⚠️ 중요 공지

TikTok Research API는 **승인 기반 액세스**가 필요합니다.

### 승인 대상
- ✅ 학술 연구자 (대학 소속)
- ✅ 비영리 단체
- ✅ 정부 기관
- ✅ 승인된 미디어 조직

### ❌ 승인 불가
- ❌ 마케팅 목적
- ❌ 상업적 데이터 수집
- ❌ 개인 사용자

**결론**: 규림한의원 마케팅 목적으로는 **TikTok Research API 승인이 어려울 수 있습니다.**

---

## 🔀 대안 방법

### 옵션 1: TikTok Creative Center (승인 불필요)

TikTok Creative Center는 공개 API 없이도 트렌드 데이터를 크롤링할 수 있습니다.

**장점:**
- ✅ 승인 불필요
- ✅ 트렌드 해시태그 분석
- ✅ 인기 영상 조회수 확인

**단점:**
- ❌ 댓글 수집 불가
- ❌ 실시간 검색 제한

**사용 방법:**
```bash
# 이미 구현된 크롤러 사용
python3 scrapers/tiktok_creative_center.py

# 트렌드 분석
python3 scrapers/tiktok_creative_center.py --trends

# 특정 키워드 검색
python3 scrapers/tiktok_creative_center.py --search "청주 다이어트"
```

### 옵션 2: TikTok Research API 신청 (승인 필요)

승인 가능성이 낮지만, 학술적 목적으로 신청할 수 있습니다.

---

## 📝 Research API 신청 절차 (참고용)

### 1단계: TikTok 개발자 계정 생성

1. https://developers.tiktok.com/ 접속
2. **"Apply for Access"** 클릭
3. TikTok 계정으로 로그인 (없으면 생성)

### 2단계: Research API 신청

1. https://developers.tiktok.com/products/research-api 접속
2. **"Apply Now"** 클릭
3. 신청서 작성:
   ```
   Organization Type: [Academic/Non-profit/Government/Media]
   Organization Name: [소속 기관명]
   Research Purpose: [연구 목적 상세 설명]
   Data Usage: [데이터 사용 계획]
   ```
4. 증빙 자료 제출:
   - 재직 증명서 (학술 기관)
   - 연구 계획서
   - IRB 승인서 (인간 대상 연구)

### 3단계: 승인 대기

- 검토 기간: 2-4주
- 승인 시: Client Key/Secret 발급
- 거부 시: 재신청 가능 (6개월 후)

### 4단계: API 키 발급 (승인 시)

1. 대시보드 → **"Apps"** → **"Create App"**
2. 앱 정보 입력:
   ```
   App Name: Kyurim Research Bot
   App Description: Academic research for healthcare marketing
   ```
3. **"Research API"** 제품 추가
4. Client Key/Secret 복사

### 5단계: secrets.json에 저장

```json
{
  "TIKTOK_CLIENT_KEY": "your_client_key_here",
  "TIKTOK_CLIENT_SECRET": "your_client_secret_here"
}
```

### 6단계: 테스트

```bash
# API 연결 테스트
python3 scrapers/tiktok_api_client.py --test

# 성공 시 출력:
# Success: True
# Message: Successfully connected to TikTok API
```

---

## 🚀 권장 방법: Creative Center 사용

Research API 승인이 어려우므로, **TikTok Creative Center 크롤러 사용을 권장**합니다.

### 즉시 사용 가능 기능

```bash
# 1. 트렌드 해시태그 분석
python3 scrapers/tiktok_creative_center.py --trends

# 출력 예시:
# Top Trending Hashtags (Korea):
#   1. #다이어트 (조회수: 1.2B)
#   2. #한의원 (조회수: 45M)
#   3. #청주 (조회수: 23M)
```

```bash
# 2. 키워드 검색
python3 scrapers/tiktok_creative_center.py --search "청주 한의원"

# 출력 예시:
# Found 25 videos for "청주 한의원"
#   - 청주 유명 한의원 추천 (조회수: 45K)
#   - 청주 다이어트 한의원 후기 (조회수: 32K)
```

```bash
# 3. 경쟁사 계정 모니터링
python3 scrapers/tiktok_creative_center.py --monitor
```

### Creative Center vs Research API

| 기능 | Creative Center | Research API |
|------|----------------|--------------|
| 승인 필요 | ❌ 불필요 | ✅ 필요 |
| 트렌드 분석 | ✅ 가능 | ✅ 가능 |
| 해시태그 검색 | ✅ 가능 | ✅ 가능 |
| 영상 조회수 | ✅ 가능 | ✅ 가능 |
| 댓글 수집 | ❌ 불가 | ✅ 가능 |
| 실시간 알림 | ❌ 불가 | ✅ 가능 |
| 비용 | 무료 | 무료 (승인 시) |

---

## 💡 실전 활용 전략

### 1. TikTok Creative Center로 트렌드 파악

```bash
# 매일 오전 트렌드 체크
python3 scrapers/tiktok_creative_center.py --trends > reports/tiktok_trends.txt
```

### 2. 경쟁사 해시태그 분석

```bash
# 경쟁사가 사용하는 해시태그 확인
python3 scrapers/tiktok_creative_center.py --account "competitor_account"
```

### 3. 멀티 플랫폼 연동

```bash
# TikTok 트렌드 → Pathfinder 키워드로 활용
python3 scrapers/tiktok_creative_center.py --export-keywords
python3 pathfinder_v3_legion.py --import tiktok_keywords.json
```

---

## 🔧 Creative Center 크롤러 커스터마이징

기존 크롤러를 수정하여 원하는 데이터만 수집할 수 있습니다.

### 파일 위치
- `scrapers/tiktok_creative_center.py`

### 수정 예시

```python
# 청주 관련 영상만 필터링
def filter_cheongju_videos(videos):
    keywords = ["청주", "율량동", "가경동", "오창"]
    return [v for v in videos if any(kw in v['title'] for kw in keywords)]

# 조회수 100K 이상만
def filter_viral_videos(videos, min_views=100000):
    return [v for v in videos if v['views'] >= min_views]
```

---

## 📊 성과 측정

### Creative Center로 수집 가능한 데이터

1. **트렌드 해시태그**
   - 상위 100개 해시태그
   - 조회수, 영상 수
   - 증가율 (일/주/월)

2. **인기 영상**
   - 제목, 설명
   - 조회수, 좋아요, 공유
   - 업로드 날짜

3. **키워드 분석**
   - 관련 해시태그
   - 경쟁도 (영상 수)
   - 참여율 (좋아요/조회수)

---

## 🎯 결론 및 추천

### 현재 시점 권장사항

1. **즉시 사용**: TikTok Creative Center 크롤러
   - 승인 불필요
   - 트렌드 파악 충분
   - 해시태그 전략 수립 가능

2. **장기 계획**: Research API 신청 (선택)
   - 학술 연구 목적으로 재포장
   - 대학 연구실과 협력 검토
   - 승인 시 댓글 수집 가능

3. **대안 플랫폼 집중**
   - YouTube (이미 46.2% 성과)
   - Instagram (API 설정 가능)
   - 네이버 플레이스 (즉시 사용)

### 비용 대비 효과

| 플랫폼 | 설정 난이도 | 승인 필요 | 타겟 품질 | 권장도 |
|--------|------------|----------|----------|--------|
| YouTube | 쉬움 | ❌ | ⭐⭐⭐⭐⭐ | 최우선 |
| Instagram | 보통 | ❌ | ⭐⭐⭐⭐ | 높음 |
| 네이버 플레이스 | 쉬움 | ❌ | ⭐⭐⭐⭐ | 높음 |
| **TikTok Creative** | 쉬움 | ❌ | ⭐⭐⭐ | **권장** |
| TikTok API | 매우 어려움 | ✅ | ⭐⭐⭐⭐⭐ | 보류 |

---

## 📞 지원

- TikTok Creative Center: 즉시 사용 가능
- Research API 문의: https://developers.tiktok.com/support
- 기술 지원: scrapers/tiktok_creative_center.py 주석 참조

---

**권장 결론**:
현재는 **TikTok Creative Center** 사용을 권장합니다.
Research API는 승인 가능성이 낮으므로, YouTube와 Instagram에 우선 집중하는 것이 효율적입니다.

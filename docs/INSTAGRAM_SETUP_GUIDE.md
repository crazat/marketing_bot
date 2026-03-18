# Instagram Graph API 설정 가이드

Instagram Graph API를 사용하여 실시간 해시태그 검색 및 미디어 데이터를 수집하기 위한 설정 가이드입니다.

## 사전 요구사항

- Instagram 비즈니스 계정 (또는 크리에이터 계정)
- Facebook 계정

---

## Step 1: Facebook 페이지 생성

Instagram Graph API는 **Facebook 페이지와 연결된 Instagram 비즈니스 계정**이 필요합니다.

1. [facebook.com](https://facebook.com) 접속 후 로그인
2. 좌측 메뉴 → **"페이지"** 클릭
3. **"새 페이지 만들기"** 클릭
4. 페이지 정보 입력:
   - 페이지 이름: 비즈니스 이름 (예: "규림한의원")
   - 카테고리: "한의원" 또는 "의료/건강"
   - 설명: 간단한 소개
5. **"페이지 만들기"** 클릭

---

## Step 2: Instagram 비즈니스 계정과 Facebook 페이지 연결

### 모바일 앱에서 설정

1. **Instagram 앱** 열기
2. **프로필** → **설정** (☰ 또는 ⚙️)
3. **계정** → **프로페셔널 계정으로 전환** (이미 비즈니스 계정이면 생략)
4. **비즈니스** 선택
5. **Facebook 페이지 연결** 선택
6. Step 1에서 만든 페이지 선택
7. **완료**

### 웹에서 확인

1. [instagram.com](https://instagram.com) → 프로필 → 설정
2. **계정 센터** → **연결된 환경**에서 Facebook 페이지 연결 확인

---

## Step 3: Facebook 개발자 계정 생성

1. [developers.facebook.com](https://developers.facebook.com) 접속
2. 우측 상단 **"로그인"** → Facebook 계정으로 로그인
3. **"시작하기"** 또는 **"Get Started"** 클릭
4. 약관 동의 → **"다음"**
5. 전화번호 인증 (필요시)
6. **개발자 계정 활성화 완료**

---

## Step 4: Facebook 앱 생성

1. 개발자 대시보드에서 **"앱 만들기"** 클릭
2. **앱 유형 선택**: "비즈니스" 선택 → **"다음"**
3. **앱 세부정보 입력**:
   - 앱 이름: `MarketingBot-Instagram`
   - 앱 연락처 이메일: 본인 이메일
   - 비즈니스 계정: (없으면 "나중에 선택" 또는 새로 생성)
4. **"앱 만들기"** 클릭
5. 보안 확인 완료

---

## Step 5: Instagram Graph API 제품 추가

1. 앱 대시보드 좌측 메뉴에서 **"제품 추가"** 또는 **"Add Product"**
2. **"Instagram"** 찾기 → **"설정"** 클릭
3. **"Instagram Graph API"** 선택 (Basic Display API 아님!)
4. 앱 설정 완료 메시지 확인

---

## Step 6: Instagram 계정 테스터 추가

1. 좌측 메뉴 → **Instagram** → **Basic Display** (또는 API Setup)
2. **"Add or Remove Instagram Testers"** 클릭
3. 본인 Instagram 계정 추가
4. Instagram 앱에서 알림 확인 → **수락**

---

## Step 7: Access Token 발급

### Graph API Explorer 사용

1. [developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer) 접속
2. 우측 상단 **앱 선택** → `MarketingBot-Instagram` 선택
3. **"User Token"** 선택
4. **권한 추가** (Add Permissions):
   - `pages_show_list`
   - `pages_read_engagement`
   - `instagram_basic`
   - `instagram_manage_insights`
   - `business_management`
5. **"Generate Access Token"** 클릭
6. Facebook 로그인 → 권한 승인
7. **토큰 복사해서 저장** (이것은 임시 토큰, 1시간 유효)

---

## Step 8: 장기 토큰으로 교환 (60일 유효)

### App ID와 App Secret 확인

1. 앱 대시보드 → **설정** → **기본 설정**
2. **App ID** 복사
3. **App Secret** → "표시" 클릭 → 복사

### 토큰 교환

브라우저 주소창에 아래 URL 입력 (값 대체):

```
https://graph.facebook.com/v18.0/oauth/access_token?grant_type=fb_exchange_token&client_id={APP_ID}&client_secret={APP_SECRET}&fb_exchange_token={SHORT_LIVED_TOKEN}
```

예시:
```
https://graph.facebook.com/v18.0/oauth/access_token?grant_type=fb_exchange_token&client_id=1234567890&client_secret=abcdef123456&fb_exchange_token=EAAG...
```

응답에서 `access_token` 값이 **장기 토큰** (60일 유효)

```json
{
  "access_token": "EAAG...(긴 토큰)...",
  "token_type": "bearer",
  "expires_in": 5184000
}
```

---

## Step 9: Instagram Business Account ID 확인

### 페이지 ID 확인

장기 토큰으로 아래 API 호출:

```
https://graph.facebook.com/v18.0/me/accounts?access_token={LONG_LIVED_TOKEN}
```

응답에서 **페이지 ID** 확인:

```json
{
  "data": [
    {
      "id": "123456789012345",
      "name": "규림한의원",
      "access_token": "..."
    }
  ]
}
```

### Instagram Business Account ID 확인

페이지 ID로 Instagram 계정 ID 조회:

```
https://graph.facebook.com/v18.0/{PAGE_ID}?fields=instagram_business_account&access_token={LONG_LIVED_TOKEN}
```

응답:

```json
{
  "instagram_business_account": {
    "id": "17841400000000000"
  },
  "id": "123456789012345"
}
```

`instagram_business_account.id` 값이 필요한 **Instagram Business Account ID**

---

## Step 10: secrets.json 설정

`config/secrets.json`에 아래 키 추가:

```json
{
  "INSTAGRAM_APP_ID": "앱 ID (Step 8에서 확인)",
  "INSTAGRAM_APP_SECRET": "앱 시크릿 (Step 8에서 확인)",
  "INSTAGRAM_ACCESS_TOKEN": "장기 토큰 (Step 8에서 얻은 값)",
  "INSTAGRAM_BUSINESS_ACCOUNT_ID": "Instagram Business Account ID (Step 9에서 얻은 값)",
  "INSTAGRAM_TOKEN_EXPIRY": "2026-03-27T00:00:00"
}
```

### 환경변수로 설정 (대안)

`.env` 파일:
```
INSTAGRAM_APP_ID=1234567890
INSTAGRAM_APP_SECRET=abcdef123456
INSTAGRAM_ACCESS_TOKEN=EAAG...
INSTAGRAM_BUSINESS_ACCOUNT_ID=17841400000000000
INSTAGRAM_TOKEN_EXPIRY=2026-03-27T00:00:00
```

---

## 검증

### API 연결 테스트

```bash
cd marketing_bot
python scrapers/instagram_api_client.py
```

정상 출력 예시:
```
[2026-01-26 ...] Instagram Graph API 연결 테스트
--------------------------------------------------
[OK] 연결 성공: @kyurim_clinic

계정 정보:
  Username: @kyurim_clinic
  Followers: 1234
  Media Count: 56

해시태그 검색 테스트 (#청주다이어트)...
  결과: 25개 미디어
    - 청주 다이어트 한의원 추천...
    - 살빼기 성공 후기...
    - ...
```

### Instagram Monitor 실행

```bash
python scrapers/scraper_instagram.py
```

API 모드로 실행되면:
```
[2026-01-26 ...] Instagram Graph API MODE (Real-time data)
[2026-01-26 ...] Starting Instagram Monitor...
[2026-01-26 ...] Running in API mode...
   Checking #청주다이어트 via Graph API...
      Found: 다이어트 성공 후기...
```

---

## 토큰 갱신

### 자동 갱신

`InstagramMonitor`가 시작될 때 토큰 만료 7일 전이면 자동으로 갱신을 시도합니다.

### 수동 갱신

```python
from scrapers.instagram_api_client import InstagramGraphAPI

api = InstagramGraphAPI()
new_token = api.refresh_token()
print(f"새 토큰: {new_token}")
```

---

## API 제한사항

### 해시태그 검색 제한

- 7일 내 **30개 고유 해시태그** 검색 가능
- 동일 해시태그 재검색은 제한에 포함 안 됨
- 해시태그당 최대 **50개 미디어** 반환

### 레이트 리밋

- 앱당 시간당 **200 호출** (개발 모드)
- 앱 검토 승인 후 더 높은 한도 가능

### 데이터 접근

- **자사 계정**: 모든 인사이트 (reach, impressions 등)
- **타사 계정**: 공개 정보만 (caption, permalink, timestamp 등)

---

## 문제 해결

### "Invalid OAuth access token" 오류

- 토큰 만료됨 → Step 8 다시 수행하여 새 토큰 발급

### "Instagram account is not connected" 오류

- Step 2 재확인: Instagram 앱에서 Facebook 페이지 연결 확인

### 해시태그 검색 결과 없음

- 7일 내 30개 해시태그 제한 도달 확인
- 해시태그 철자 확인 (# 기호 제외하고 검색)

### API 모드가 활성화되지 않음

- `secrets.json` 또는 `.env`에 4개 키가 모두 설정되었는지 확인
- `python scrapers/instagram_api_client.py`로 연결 테스트

---

## 참고 자료

- [Instagram Graph API 공식 문서](https://developers.facebook.com/docs/instagram-api)
- [Graph API Explorer](https://developers.facebook.com/tools/explorer)
- [Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken)

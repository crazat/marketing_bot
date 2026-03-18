# Instagram Graph API 빠른 설정 (20분)

## ✅ 이미 얻은 정보

- **앱 ID**: `737337855781724`
- **앱 이름**: MarketingBot-inbyul-IG
- **앱 시크릿**: (화면에서 "표시" 클릭)

---

## 🚀 빠른 시작 (5단계)

### 1단계: Instagram Graph API 제품 추가 (2분)

**현재 위치**: Instagram API 설정 화면

**이동 경로**:
```
좌측 상단 "MarketingBot-inbyul-IG" 클릭
→ 대시보드 화면
→ 좌측 메뉴 "제품 추가" 또는 "Add Products"
→ "Instagram Graph API" 찾기 (Instagram API 아님!)
→ "설정" 버튼 클릭
```

**확인**:
- 좌측 메뉴에 "Instagram Graph API" 추가됨 ✅

---

### 2단계: Access Token 생성 (10분)

**이동**:
```
https://developers.facebook.com/tools/explorer
```

**설정**:
1. **Facebook 앱**: `MarketingBot-inbyul-IG` 선택
2. **사용자 또는 페이지**: Facebook 페이지 선택
3. **권한 추가** 클릭 → 체크:
   - ✅ `pages_show_list`
   - ✅ `pages_read_engagement`
   - ✅ `instagram_basic`
   - ✅ `instagram_manage_comments`
   - ✅ `instagram_manage_insights`
4. **액세스 토큰 생성** 클릭
5. 생성된 토큰 복사 (메모장에 임시 저장)

**토큰 예시**:
```
EAAKh4ZBgK...ABC123 (약 200자)
```

---

### 3단계: Instagram Business Account ID 확인 (5분)

**Graph API Explorer에서 쿼리 실행**:

**쿼리 1**: Facebook 페이지 ID 조회
```
GET /me/accounts
```

**응답 예시**:
```json
{
  "data": [
    {
      "id": "123456789012345",  ← 이것이 페이지 ID
      "name": "규림한의원"
    }
  ]
}
```

**쿼리 2**: Instagram Business Account ID 조회
```
GET /123456789012345?fields=instagram_business_account
```
(123456789012345를 위에서 찾은 페이지 ID로 교체)

**응답 예시**:
```json
{
  "instagram_business_account": {
    "id": "17841400123456789"  ← 이것이 Instagram Business Account ID
  }
}
```

---

### 4단계: 장기 토큰으로 변환 (3분)

**브라우저 주소창에 입력** (한 줄로):

```
https://graph.facebook.com/v18.0/oauth/access_token?grant_type=fb_exchange_token&client_id=737337855781724&client_secret={시크릿}&fb_exchange_token={단기토큰}
```

**값 교체**:
- `{시크릿}`: 앱 시크릿 (설정 → 기본 설정 → "표시" 클릭)
- `{단기토큰}`: 2단계에서 생성한 토큰

**응답 예시**:
```json
{
  "access_token": "EAAKh4ZBgK...XYZ789",  ← 장기 토큰 (60일 유효)
  "token_type": "bearer",
  "expires_in": 5183944
}
```

---

### 5단계: API 키 입력 및 테스트 (2분)

**터미널에서 실행**:
```bash
python3 scripts/setup_api_keys.py
```

**메뉴에서 "1" 선택** → Instagram API 키 설정

**입력할 값**:

| 키 | 값 | 어디서 얻었나 |
|----|-----|--------------|
| `INSTAGRAM_APP_ID` | `737337855781724` | 이미 있음 |
| `INSTAGRAM_APP_SECRET` | `abc123...` | 설정 → 기본 설정 → "표시" |
| `INSTAGRAM_ACCESS_TOKEN` | `EAAKh4ZBgK...XYZ789` | 4단계 장기 토큰 |
| `INSTAGRAM_BUSINESS_ACCOUNT_ID` | `17841400123456789` | 3단계 ID |

**저장 후 테스트**:
- 메뉴에서 "3" 선택 → Instagram API 테스트

**성공 시 출력**:
```
✅ 연결 성공: @your_account

계정 정보:
  Username: @your_account
  Followers: 1,234
  Media: 56
```

---

## 🎯 완료 체크리스트

- [ ] Instagram Graph API 제품 추가
- [ ] Graph API Explorer에서 단기 토큰 생성
- [ ] Facebook 페이지 ID 확인
- [ ] Instagram Business Account ID 확인
- [ ] 장기 토큰 변환
- [ ] secrets.json에 4개 키 저장
- [ ] API 테스트 성공

---

## ❓ 문제 해결

### "Instagram Graph API 제품을 찾을 수 없습니다"

**확인**:
- "Instagram API" (새 버전) 말고 "Instagram Graph API" (구버전) 찾기
- 제품 목록을 아래로 스크롤

**대안**:
- 좌측 메뉴 → Instagram Graph API 직접 클릭 (이미 추가된 경우)

---

### "권한을 찾을 수 없습니다"

**확인**:
- Graph API Explorer → 앱 선택 확인
- "사용자 또는 페이지"에서 **Facebook 페이지** 선택 (사용자 아님)

---

### "instagram_business_account가 없습니다"

**원인**:
- Instagram 계정이 비즈니스 계정이 아님
- Facebook 페이지와 연결 안됨

**해결**:
1. Instagram 앱 → 설정 → 프로페셔널 계정으로 전환
2. 계정 센터 → Facebook 페이지 연결

---

### "장기 토큰 변환 실패"

**확인**:
- URL이 한 줄로 입력되었는지 (줄바꿈 없이)
- `client_secret`과 `fb_exchange_token` 값이 올바른지
- 중괄호 `{}` 제거했는지

---

## 🚀 다음 단계

### Instagram 포함 스캔

```bash
python3 viral_hunter_multi_platform.py \
  --platforms naver,youtube,karrot,instagram \
  --limit 10 \
  --save-db
```

### 해시태그 검색 테스트

```bash
python3 scrapers/instagram_api_client.py
```

---

## 📞 지원

- 상세 가이드: `docs/INSTAGRAM_SETUP_GUIDE.md`
- API 키 설정: `python3 scripts/setup_api_keys.py`
- 문제 발생 시: 화면 캡처 + 에러 메시지 공유

---

**예상 소요 시간**: 20-25분
**난이도**: 보통
**효과**: ⭐⭐⭐⭐ (해시태그 타겟팅 가능)

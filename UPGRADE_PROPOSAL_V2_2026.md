# Marketing Bot 추가 고도화 제안서 V2 (2026-03-24)

> Phase A~D 구현 완료 후 추가 고도화 방안
> 4개 영역 인터넷 리서치 기반

---

## 1. 프론트엔드 UX 고도화

### 1-1. shadcn/ui + Tremor 디자인 시스템 도입
- **shadcn/ui**: Radix UI + Tailwind 기반 복사형 컴포넌트 (현재 커스텀 UI 대체)
- **Tremor**: 대시보드 특화 KPI 카드, 스파크라인, 델타 지표 (`npm install @tremor/react`)
- 기존 Tailwind 기반이므로 점진적 마이그레이션 가능

### 1-2. 고급 데이터 시각화
- **@nivo/heatmap**: 지오그리드 히트맵 (키워드×시간 매트릭스)
- **@nivo/funnel**: 환자 여정 퍼널 차트
- **react-calendar-heatmap**: GitHub 스타일 활동 히트맵 (스캔 실행 이력)
- **react-simple-maps**: 지역별 마케팅 성과 지도

### 1-3. 드래그앤드롭 대시보드 커스터마이징
- **react-grid-layout** (`npm install react-grid-layout`): 위젯 드래그/리사이즈
- 사용자별 레이아웃을 DB에 저장 → 개인화된 대시보드
- 위젯 팔레트에서 원하는 차트/KPI 선택하여 배치

### 1-4. PWA (Progressive Web App)
- Service Worker + Workbox로 오프라인 대시보드 지원
- Push Notification으로 순위 급변/리뷰 알림
- IndexedDB로 마지막 대시보드 상태 캐싱
- iOS Safari 16.4+ 푸시 알림 지원 (모든 플랫폼 커버)

### 1-5. 다크 모드
- Tailwind `darkMode: 'class'` + CSS 변수 기반 시맨틱 컬러 토큰
- Recharts/Tremor 차트 색상도 다크 모드 대응
- localStorage 저장 + 시스템 설정 폴백

### 1-6. 알림 센터
- **Sonner**: shadcn/ui 공식 토스트 (`npm install sonner`)
- 인앱 알림 벨 + 읽음/안읽음 상태 + 액션 버튼
- 기존 WebSocket 이벤트 채널(B-5)과 연동

---

## 2. 자동 콘텐츠 생성 파이프라인

### 2-1. AI 블로그 포스트 생성 워크플로우
```
[키워드 선정] → [아웃라인 생성] → [초안 작성] → [SEO 최적화]
     ↓                                              ↓
[Gemini]        [Gemini]         [Gemini]      [AEO 점수화]
                                                    ↓
                                            [의료광고 규정 체크(C-5)]
                                                    ↓
                                            [원장님 검토 (텔레그램)]
                                                    ↓
                                            [네이버 블로그 발행]
```
- 네이버 블로그 API (`writePost.json`)로 자동 발행 가능 (OAuth 2.0 필요)
- **주의**: 네이버 AuthGR이 AI 생성 콘텐츠 필터링 → 반드시 인간 검토/편집 필수

### 2-2. AI 이미지 자동 생성
- **Gemini Imagen**: 무료 500장/일, $0.039/장 (유료)
- 블로그 썸네일, SNS 그래픽 자동 생성
- 의료 콘텐츠 특화 프롬프트 템플릿 제공

### 2-3. 숏폼 영상 자동 생성
- 블로그 → 스크립트 추출 → TTS → 자막 → 영상 조합
- Hook(0-3초) → Problem(3-8초) → Solution(8-25초) → CTA(25-30초) 구조
- AutoShorts.ai 또는 n8n + ElevenLabs 워크플로우

### 2-4. Schema Markup 자동 삽입
- MedicalClinic, FAQPage, MedicalProcedure, IndividualPhysician 스키마
- 블로그 발행 시 JSON-LD 자동 생성 → AEO/GEO 노출 극대화
- 의료기관 구조화 데이터는 Google AI Overview 노출에 필수

### 2-5. 자동 FAQ 생성
- 리뷰 + 지식인 질문 클러스터링 → FAQ 쌍 자동 생성
- FAQPage Schema 자동 적용
- 고객 문의 30-50% 감소 효과

---

## 3. 보안/성능/테스트 강화

### 3-1. 보안 강화 (P0)
| 항목 | 구현 방법 |
|------|---------|
| **비밀 관리** | `keyring` 라이브러리 → Windows DPAPI (Credential Manager) |
| **DB 암호화** | SQLCipher (AES-256, 성능 오버헤드 5-15%) |
| **CSP 헤더** | nonce 기반 Content-Security-Policy 미들웨어 |
| **한국어 XSS 방지** | Unicode NFC 정규화 → 전각 문자 위장 공격 차단 |
| **API 키 로테이션** | 듀얼 키 유예 기간 + 90일 자동 로테이션 |
| **OWASP API Top 10** | BOLA 방지 (리소스 소유권 검증), 응답 필드 제한 (Pydantic response_model) |

### 3-2. 성능 최적화 (P1)
| 항목 | 효과 |
|------|------|
| **aiosqlitepool** | 비동기 SQLite 연결 풀링 → 이벤트 루프 블로킹 제거 |
| **PRAGMA mmap_size=256MB** | 메모리 매핑 I/O → 읽기 성능 향상 |
| **Vite code splitting** | route 기반 청크 분리 → FCP 1.5초 미만 |
| **WebP 변환** | 스크래핑 이미지 80-92% 크기 절감 |
| **Slow query 로깅** | 100ms 초과 쿼리 자동 경고 |

### 3-3. 테스트 전략 (P1)
| 계층 | 도구 | 커버리지 목표 |
|------|------|-------------|
| **계약 테스트** | Schemathesis | 320+ 엔드포인트 100% (자동 생성) |
| **단위 테스트** | pytest + in-memory SQLite (StaticPool) | 핵심 비즈니스 로직 80% |
| **컴포넌트 테스트** | Vitest + React Testing Library | UI 컴포넌트 60% |
| **E2E 테스트** | Playwright | 핵심 5개 플로우 |

### 3-4. 관찰성 (P2)
- **structlog + asgi-correlation-id**: JSON 구조화 로그 + 요청 상관 ID
- **Prometheus 메트릭**: 마케팅 KPI 커스텀 메트릭 (스캔 성공률, 캐시 히트율)
- **Circuit Breaker**: pybreaker로 외부 API 장애 전파 방지
- **SLO 모니터링**: API 가용성 99.5%, P95 레이턴시 3초, 스캔 성공률 98%

---

## 4. 마케팅 자동화 고급 기능

### 4-1. 통합 평판 점수 엔진 (P1)
- 네이버 플레이스(40%) + 구글(20%) + 카카오맵(15%) + 커뮤니티 감성(25%) 가중 합산
- 경쟁사 대비 상대적 평판 지수 산출
- 2026-04-06 네이버 별점 5점 척도 도입 대응 (A-2에서 DB 준비 완료)

### 4-2. 날씨 기반 마케팅 트리거 (P1)
| 기상 조건 | 트리거 콘텐츠 | 키워드 |
|----------|------------|--------|
| 기온 급락 (5°C+) | 환절기 면역 콘텐츠 | "환절기 한의원", "면역력" |
| 미세먼지 나쁨 | 호흡기/비염 콘텐츠 | "비염 한방치료" |
| 폭염 (33°C+) | 보양/더위 콘텐츠 | "여름 보양", "더위 한약" |
| 봄 꽃가루 | 알레르기 콘텐츠 | "알레르기 한의원" |
| 한파 (-10°C) | 면역/관절 콘텐츠 | "겨울 관절", "한방 온열" |
- OpenWeatherMap API (무료 1000건/일) + 기상청 API 연동

### 4-3. 시즌별 캠페인 자동화 (P1)
| 시즌 | 기간 | 핵심 캠페인 |
|------|------|-----------|
| 봄 알레르기 | 3-5월 | 비염/피부 한방치료 |
| 여름 보양 | 6-8월 | 보양식/한약, 다이어트 |
| 가을 환절기 | 9-10월 | 면역력, 피로회복 |
| 겨울 면역 | 11-2월 | 겨울 한약, 관절 |
| 수능 시즌 | 10-11월 | 집중력, 수면, 수험생 건강 |
| 신학기 | 2-3월 | 성장클리닉, 체력 |

### 4-4. 환자 치료별 팔로우업 시퀀스 (P2)
```
다이어트 한약 환자:
  D+1: 복용 안내 → D+3: 경과 확인 → D+7: 식단 팁 →
  D+14: 중간 점검 안내 → D+30: 효과 확인 + 재처방 안내 →
  D+45: 리뷰 요청 → D+60: 유지 관리 안내

교통사고 치료 환자:
  D+1: 주의사항 → D+3: 경과 확인 → D+7: 다음 내원 리마인드 →
  D+14: 보험 안내 → D+90: 종료 후 관리 안내
```

### 4-5. 마케팅 기여도 분석 (Attribution) (P2)
- First-touch / Last-touch / Linear / Time-decay 모델
- 이미 수집 중인 데이터 소스 활용:
  - `community_mentions` (블로그/카페 인지)
  - `call_tracking` (전화 전환)
  - `smartplace_stats` (플레이스 행동)
  - `web_visibility` (검색 노출)
  - `naver_ad_keyword_data` (광고 데이터)

### 4-6. 텔레그램 승인 워크플로우 (P1)
- Inline Keyboard로 승인/수정/거부 버튼
- 리뷰 응답 초안 → 원장님 텔레그램에서 바로 승인
- 콘텐츠 게시 전 최종 확인
- 예시: `[승인✅] [수정✏️] [거부❌]` 인라인 버튼

### 4-7. Google Business Profile 듀얼 관리 (P3)
- GBP API로 구글 리뷰도 통합 모니터링
- 네이버 + 구글 리뷰 통합 대시보드
- 외국인 환자 타겟 시 필수

---

## 5. 구현 우선순위

### 즉시 (1-4주)
- 3-1. keyring 비밀 관리 + CSP 헤더
- 4-2. 날씨 기반 트리거 (OpenWeatherMap 연동)
- 4-6. 텔레그램 승인 워크플로우 (인라인 키보드)
- 1-5. 다크 모드
- 1-6. Sonner 토스트 알림

### 단기 (1-3개월)
- 3-3. Schemathesis 계약 테스트
- 4-1. 통합 평판 점수 엔진
- 4-3. 시즌별 캠페인 자동화
- 2-1. 블로그 포스트 생성 파이프라인
- 2-4. Schema Markup 자동 삽입
- 1-1. shadcn/ui 컴포넌트 마이그레이션

### 중기 (3-5개월)
- 4-4. 치료별 팔로우업 시퀀스
- 4-5. 마케팅 기여도 분석
- 3-2. aiosqlitepool + 성능 최적화
- 2-2. AI 이미지 생성
- 1-2. Nivo 고급 시각화
- 1-3. react-grid-layout 커스텀 대시보드

### 장기 (5개월+)
- 1-4. PWA 전환
- 2-3. 숏폼 영상 자동 생성
- 4-7. Google Business Profile 통합
- 3-4. Prometheus + SLO 모니터링

---

*2026-03-24 기준 인터넷 리서치 결과*

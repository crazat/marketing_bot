# Marketing Bot Web

청주 규림한의원 마케팅 자동화 플랫폼의 순수 웹앱 버전입니다.

## 🎯 개요

Streamlit 기반 dashboard_ultra.py를 FastAPI + React로 완전히 재구성한 프로젝트입니다.

### 기술 스택

**백엔드:**
- FastAPI (Python 3.12+)
- SQLite (데이터베이스)
- WebSocket (실시간 업데이트)
- Uvicorn (ASGI 서버)

**프론트엔드:**
- React 18 + TypeScript
- Vite (빌드 도구)
- Tailwind CSS (스타일링)
- React Query (데이터 fetching)
- Zustand (상태 관리)
- Recharts (차트 라이브러리)

## 🚀 빠른 시작

### 1. 백엔드 설정

```bash
cd backend

# 가상환경 생성 (선택사항)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 서버 실행
python main.py
# 또는
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

백엔드 서버:
- API: http://localhost:8000
- 문서: http://localhost:8000/docs

### 2. 프론트엔드 설정

```bash
cd frontend

# 의존성 설치
npm install
# 또는
yarn install

# 개발 서버 실행
npm run dev
# 또는
yarn dev
```

프론트엔드 서버: http://localhost:5173

## 📁 프로젝트 구조

```
marketing_bot_web/
├── backend/
│   ├── main.py              # FastAPI 메인 앱
│   ├── requirements.txt     # Python 의존성
│   ├── routers/             # API 라우터
│   │   ├── hud.py          # HUD 메트릭
│   │   ├── pathfinder.py   # Pathfinder V3
│   │   ├── battle.py       # 순위 추적 (예정)
│   │   ├── leads.py        # 리드 관리 (예정)
│   │   └── ...
│   ├── models/              # 데이터 모델
│   └── services/            # 비즈니스 로직
│
└── frontend/
    ├── package.json         # Node 의존성
    ├── vite.config.ts       # Vite 설정
    ├── tsconfig.json        # TypeScript 설정
    ├── tailwind.config.js   # Tailwind 설정
    └── src/
        ├── main.tsx         # 앱 진입점
        ├── App.tsx          # 루트 컴포넌트
        ├── components/      # UI 컴포넌트
        │   ├── Layout.tsx
        │   ├── MetricCard.tsx
        │   ├── ChronosTimeline.tsx
        │   └── ...
        ├── pages/           # 페이지 컴포넌트
        │   ├── Dashboard.tsx
        │   ├── Pathfinder.tsx
        │   ├── BattleIntelligence.tsx
        │   └── ...
        ├── services/        # API 클라이언트
        │   └── api.ts
        ├── hooks/           # 커스텀 훅
        ├── lib/             # 유틸리티
        └── types/           # 타입 정의
```

## 🎨 주요 기능

### ✅ 구현 완료
- [x] 프로젝트 구조 설정
- [x] 다크 테마 UI
- [x] 반응형 레이아웃 (모바일 지원)
- [x] HUD 메트릭 대시보드
- [x] Chronos Timeline 시각화
- [x] WebSocket 실시간 업데이트
- [x] API 자동 문서화

### 🚧 구현 예정
- [ ] Pathfinder V3 전체 기능
- [ ] Battle Intelligence
- [ ] Lead Manager (YouTube/TikTok/Naver)
- [ ] Viral Hunter
- [ ] 경쟁사 분석
- [ ] Instagram 분석
- [ ] 설정 페이지

## 🔄 Streamlit 대비 개선사항

| 항목 | Streamlit | 웹앱 |
|------|-----------|------|
| **성능** | 느림 (전체 재실행) | 빠름 (선택적 렌더링) |
| **상태 관리** | 복잡 | 간단 (Zustand) |
| **실시간 업데이트** | polling | WebSocket |
| **모바일 지원** | 제한적 | 완벽한 반응형 |
| **커스터마이징** | 제약적 | 자유로움 |
| **배포** | 복잡 | 간단 (Docker) |
| **UX** | 전통적 | 모던 SPA |

## 📊 API 엔드포인트

### HUD
- `GET /api/hud/metrics` - 실시간 메트릭
- `GET /api/hud/system-status` - 시스템 상태

### Pathfinder
- `GET /api/pathfinder/stats` - 통계
- `GET /api/pathfinder/keywords` - 키워드 목록
- `POST /api/pathfinder/run` - Pathfinder 실행
- `GET /api/pathfinder/clusters` - 키워드 클러스터

### WebSocket
- `WS /ws` - 실시간 업데이트

자세한 API 문서: http://localhost:8000/docs

## 🛠️ 개발

### 환경 변수

백엔드에서 `.env` 파일 또는 환경 변수로 설정:

```env
GEMINI_API_KEY=your_api_key
NAVER_CLIENT_ID=your_client_id
NAVER_CLIENT_SECRET=your_client_secret
```

### 코드 스타일

**백엔드:**
- PEP 8 준수
- 타입 힌팅 사용

**프론트엔드:**
- ESLint + Prettier
- TypeScript strict 모드

## 🚀 배포

### Docker Compose (권장)

```bash
# 빌드 및 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 중지
docker-compose down
```

### 수동 배포

**백엔드:**
```bash
cd backend
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
```

**프론트엔드:**
```bash
cd frontend
npm run build
# build/ 디렉토리를 Nginx로 서빙
```

## 📝 라이선스

Private - 청주 규림한의원 전용

## 👨‍💻 개발자

Claude Code + 사용자

## 📞 지원

이슈나 질문이 있으면 GitHub Issues에 올려주세요.

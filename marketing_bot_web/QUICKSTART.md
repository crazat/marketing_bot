# 🚀 Marketing Bot Web - 빠른 시작 가이드

## 5분 안에 시작하기

### 1️⃣ 백엔드 실행

```bash
cd marketing_bot/marketing_bot_web/backend
pip install -r requirements.txt
python main.py
```

✅ 백엔드 서버: http://localhost:8000
✅ API 문서: http://localhost:8000/docs

### 2️⃣ 프론트엔드 실행

**새 터미널**에서:

```bash
cd marketing_bot/marketing_bot_web/frontend
npm install
npm run dev
```

✅ 프론트엔드: http://localhost:5173

### 3️⃣ 접속

브라우저에서 http://localhost:5173 열기

---

## 🎯 주요 기능

### ✅ 현재 사용 가능

| 기능 | 설명 |
|------|------|
| 🏠 **대시보드** | 실시간 HUD 메트릭, Chronos Timeline |
| 🎯 **Pathfinder** | 키워드 발굴, S/A/B/C 등급 분류, 클러스터링 |
| ⚔️ **Battle Intelligence** | 순위 추적, 트렌드 분석 (API 구현 완료) |
| 📋 **Lead Manager** | YouTube/TikTok/Naver 리드 관리 (API 구현 완료) |
| 🎯 **Viral Hunter** | 바이럴 타겟 발굴 (API 구현 완료) |
| 💪 **경쟁사 분석** | 약점 공략, Instagram 분석 (API 구현 완료) |

### 🚧 UI 구현 예정

Battle Intelligence, Lead Manager, Viral Hunter, 경쟁사 분석 페이지의 UI는 곧 추가됩니다.

---

## 🔥 Streamlit 대비 개선점

| 항목 | Before (Streamlit) | After (웹앱) |
|------|-------------------|-------------|
| **성능** | 느림 😞 | 빠름 ⚡ |
| **상태 관리** | 복잡 🤯 | 간단 😊 |
| **실시간 업데이트** | polling | WebSocket 🔄 |
| **모바일** | 제한적 📱 | 완벽 반응형 📱✨ |
| **커스터마이징** | 제약적 | 자유로움 🎨 |

---

## 📖 API 문서

모든 API는 자동으로 문서화됩니다:

👉 http://localhost:8000/docs

### 주요 엔드포인트

```
GET  /api/hud/metrics              # HUD 메트릭
GET  /api/pathfinder/stats         # Pathfinder 통계
POST /api/pathfinder/run           # Pathfinder 실행
GET  /api/battle/ranking-keywords  # 순위 추적 키워드
GET  /api/leads/stats              # 리드 통계
GET  /api/viral/targets            # 바이럴 타겟
WS   /ws                           # 실시간 업데이트
```

---

## 🐛 문제 해결

### 백엔드 오류

```bash
# Python 버전 확인
python --version  # 3.12+ 필요

# 의존성 재설치
pip install -r requirements.txt --force-reinstall
```

### 프론트엔드 오류

```bash
# Node 버전 확인
node --version  # 20+ 권장

# node_modules 재설치
rm -rf node_modules package-lock.json
npm install
```

### 포트 충돌

```bash
# 8000번 포트 사용 중인 프로세스 종료 (Windows)
netstat -ano | findstr :8000
taskkill /PID [PID번호] /F

# 5173번 포트 사용 중인 프로세스 종료
netstat -ano | findstr :5173
taskkill /PID [PID번호] /F
```

---

## 💡 개발 팁

### Hot Reload

- **백엔드**: `uvicorn main:app --reload` (자동 재시작)
- **프론트엔드**: Vite가 자동으로 Hot Reload

### API 테스트

Swagger UI 사용: http://localhost:8000/docs

### 디버깅

```python
# 백엔드 로그 확인
tail -f logs/app.log

# 프론트엔드 콘솔
브라우저 F12 → Console 탭
```

---

## 🚢 프로덕션 배포

```bash
# Docker Compose로 한 번에 실행
docker-compose up -d

# 접속
http://localhost
```

---

## 📞 지원

- GitHub Issues: 문제 보고
- README.md: 상세 문서
- API Docs: http://localhost:8000/docs

---

**즐거운 마케팅 자동화! 🎉**

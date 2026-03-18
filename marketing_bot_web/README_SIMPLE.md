# ⚡ 초간단 실행 가이드 (Docker 불필요)

Docker 없이 로컬에서 바로 실행하는 가장 간단한 방법입니다.

## 📋 필수 요구사항

- **Node.js 20+**: https://nodejs.org
- **Python 3.11+**: https://www.python.org

## 🚀 실행 방법

### 1️⃣ 한 번만: 첫 설정

```cmd
REM frontend 폴더에서
cd frontend
npm install
cd ..

REM backend 폴더에서
cd backend
pip install -r requirements.txt
cd ..
```

### 2️⃣ 매번: 서버 시작

```cmd
start-simple.bat
```

**끝!** 자동으로:
- ✅ 백엔드 서버 시작 (포트 8000)
- ✅ 프론트엔드 서버 시작 (포트 5173)
- ✅ 브라우저 오픈

### 3️⃣ 서버 중지

```cmd
stop-simple.bat
```

## 📂 실행 파일 비교

| 파일 | 필요 환경 | 속도 | 추천 |
|------|----------|------|------|
| `start-simple.bat` | Node.js + Python | ⚡ 빠름 | ✅ 개발용 |
| `start-dev.bat` | Docker Desktop | 🐳 중간 | 팀 작업 |
| `start-prod.bat` | Docker Desktop | 🚀 느림 | 배포용 |

## 💡 장단점

### ✅ 장점
- Docker 설치 불필요
- 빠른 시작 (3-5초)
- 메모리 사용량 적음
- 디버깅 쉬움

### ⚠️ 단점
- Node.js, Python 직접 설치 필요
- 포트 충돌 가능성
- 환경 차이 발생 가능

## 🔧 트러블슈팅

### 포트가 이미 사용 중

```cmd
REM 포트 확인
netstat -ano | findstr ":5173"
netstat -ano | findstr ":8000"

REM 또는 그냥
stop-simple.bat
```

### Node.js 없음

https://nodejs.org 에서 다운로드

### Python 없음

https://www.python.org 에서 다운로드

### npm install 실패

```cmd
cd frontend
rmdir /s /q node_modules
del package-lock.json
npm install
```

### pip install 실패

```cmd
cd backend
pip install --upgrade pip
pip install -r requirements.txt
```

## 📍 접속 URL

| 페이지 | URL |
|--------|-----|
| **메인 앱** | http://localhost:5173 |
| 백엔드 API | http://localhost:8000 |
| API 문서 | http://localhost:8000/docs |

## 🎯 개발 워크플로우

```cmd
REM 1. 서버 시작
start-simple.bat

REM 2. 코드 수정
REM    - frontend/src/ 수정 → 자동 새로고침
REM    - backend/ 수정 → 자동 재시작

REM 3. 서버 중지
stop-simple.bat
```

## 🆚 Docker vs Simple

### Docker 방식 (start-dev.bat)
```
✅ 환경 일관성
✅ 팀 협업 편리
❌ Docker Desktop 필요
❌ 느린 시작
```

### Simple 방식 (start-simple.bat)
```
✅ 빠른 시작
✅ Docker 불필요
✅ 메모리 효율
❌ 환경 차이 가능
```

## 💻 수동 실행 (고급)

원한다면 각각 직접 실행도 가능:

```cmd
REM 터미널 1: 백엔드
cd backend
python -m uvicorn main:app --reload --port 8000

REM 터미널 2: 프론트엔드
cd frontend
npm run dev
```

---

**추천: 개발할 때는 `start-simple.bat`, 배포할 때는 `start-prod.bat`** 🚀

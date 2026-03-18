# 🪟 Windows 사용자 가이드

Marketing Bot Web을 Windows에서 쉽게 실행할 수 있는 배치 파일(.bat) 모음입니다.

## 📋 필수 요구사항

실행 전 다음 프로그램이 설치되어 있어야 합니다:

- **Docker Desktop**: https://www.docker.com/products/docker-desktop
- **Node.js 20+**: https://nodejs.org
- **Python 3.11+**: https://www.python.org

## 🚀 빠른 시작

### 1️⃣ 개발 서버 시작

```cmd
start-dev.bat
```

- 프론트엔드 빌드
- 백엔드 의존성 설치
- Docker 컨테이너 시작
- 브라우저 자동 오픈 (http://localhost)

### 2️⃣ 프로덕션 서버 시작

```cmd
start-prod.bat
```

- 프로덕션 최적화 빌드
- Gunicorn 4 workers
- Nginx 정적 파일 캐싱 + Gzip 압축
- 성능 최적화 설정

## 📂 배치 파일 목록

| 파일 | 설명 |
|------|------|
| `start-dev.bat` | 개발 서버 시작 |
| `start-prod.bat` | 프로덕션 서버 시작 |
| `stop.bat` | 서버 중지 |
| `restart.bat` | 서버 재시작 |
| `status.bat` | 서버 상태 확인 |
| `logs.bat` | 실시간 로그 확인 |
| `open-browser.bat` | 브라우저에서 앱 열기 |

## 💡 사용 예시

### 서버 시작 → 브라우저 열기 → 로그 확인

```cmd
REM 1. 서버 시작
start-dev.bat

REM 2. 브라우저에서 열기
open-browser.bat

REM 3. 로그 확인 (Ctrl+C로 종료)
logs.bat
```

### 서버 상태 확인

```cmd
status.bat
```

출력 예시:
```
✅ Docker 설치 확인
Docker version 24.0.7

✅ Docker Compose 설치 확인
docker-compose version 2.23.3

📦 컨테이너 상태
NAME                    STATUS
backend                 Up 2 hours
frontend                Up 2 hours
nginx                   Up 2 hours

✅ 서버가 실행 중입니다

📍 접속 URL:
   - 웹앱: http://localhost
   - API: http://localhost/api
```

### 서버 재시작

```cmd
restart.bat
```

### 서버 중지

```cmd
stop.bat
```

## 🔧 트러블슈팅

### Docker가 실행 중이 아닙니다

**증상**: `Cannot connect to the Docker daemon` 에러

**해결**:
1. Docker Desktop을 실행하세요
2. 작업 관리자에서 Docker Desktop이 실행 중인지 확인
3. `status.bat` 실행하여 Docker 상태 확인

### 포트가 이미 사용 중입니다

**증상**: `port is already allocated` 에러

**해결**:
```cmd
REM 1. 기존 컨테이너 중지
stop.bat

REM 2. 다른 프로그램이 80번 포트를 사용 중인지 확인
netstat -ano | findstr :80

REM 3. 프로세스 종료 (관리자 권한 필요)
taskkill /PID <프로세스번호> /F

REM 4. 서버 재시작
start-dev.bat
```

### npm install 실패

**증상**: `npm ERR!` 에러

**해결**:
```cmd
REM frontend 폴더로 이동
cd frontend

REM node_modules 삭제
rmdir /s /q node_modules

REM package-lock.json 삭제
del package-lock.json

REM 재설치
npm install

REM 상위 폴더로 돌아가기
cd ..
```

### pip install 실패

**증상**: `pip ERROR` 에러

**해결**:
```cmd
REM backend 폴더로 이동
cd backend

REM 가상환경 생성 (선택사항)
python -m venv venv
venv\Scripts\activate

REM pip 업그레이드
python -m pip install --upgrade pip

REM 의존성 설치
pip install -r requirements.txt

cd ..
```

## 📊 성능 모니터링

### 실시간 리소스 사용량 확인

```cmd
docker stats
```

### 로그 파일 위치

- **프론트엔드**: Docker 컨테이너 로그
- **백엔드**: Docker 컨테이너 로그
- **Nginx**: Docker 컨테이너 로그

로그 확인:
```cmd
REM 모든 서비스 로그
logs.bat

REM 특정 서비스 로그
docker-compose logs backend
docker-compose logs frontend
docker-compose logs nginx
```

## 🌐 접속 URL

| 페이지 | URL |
|--------|-----|
| 메인 대시보드 | http://localhost |
| HUD | http://localhost |
| Pathfinder | http://localhost/pathfinder |
| Battle Intelligence | http://localhost/battle |
| Lead Manager | http://localhost/leads |
| API 문서 (Swagger) | http://localhost/docs |
| API 루트 | http://localhost/api |

## 🎯 권장 워크플로우

### 개발 중

```cmd
REM 1. 서버 시작
start-dev.bat

REM 2. 브라우저 열기
open-browser.bat

REM 3. 코드 수정 후 재시작
restart.bat
```

### 배포 전 테스트

```cmd
REM 1. 프로덕션 모드로 빌드 및 실행
start-prod.bat

REM 2. 성능 확인
docker stats

REM 3. 로그 확인
logs.bat
```

## 📝 추가 명령어

### Docker 컨테이너 내부 접속

```cmd
REM 백엔드 컨테이너
docker-compose exec backend bash

REM 프론트엔드 컨테이너 (Nginx)
docker-compose exec frontend sh
```

### 데이터베이스 초기화

```cmd
REM 백엔드 컨테이너 접속
docker-compose exec backend bash

REM SQLite DB 삭제 (주의!)
rm db/marketing_data.db

REM 컨테이너 재시작으로 DB 재생성
exit
restart.bat
```

### 전체 클린업

```cmd
REM 컨테이너, 이미지, 볼륨 모두 삭제 (주의!)
docker-compose down -v --rmi all

REM 재시작
start-dev.bat
```

## 🆘 도움말

문제가 계속되면:

1. `status.bat` 실행하여 시스템 상태 확인
2. `logs.bat` 실행하여 에러 로그 확인
3. GitHub Issues에 문의: [링크]

## 🎉 완료!

이제 `.bat` 파일을 더블 클릭하거나 명령 프롬프트에서 실행하여 쉽게 서버를 관리할 수 있습니다!

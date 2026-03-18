@echo off
chcp 65001 > nul
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 🚀 Marketing Bot Web - 프로덕션 서버 시작
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

REM 프론트엔드 빌드
echo 📦 프론트엔드 빌드 중...
cd frontend
call npm install
if %errorlevel% neq 0 (
    echo ❌ npm install 실패
    pause
    exit /b 1
)

call npm run build
if %errorlevel% neq 0 (
    echo ❌ 프론트엔드 빌드 실패
    pause
    exit /b 1
)

echo ✅ 프론트엔드 빌드 완료
cd ..

REM 백엔드 의존성 설치
echo.
echo 📦 백엔드 의존성 설치 중...
cd backend
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ❌ 백엔드 의존성 설치 실패
    pause
    exit /b 1
)

echo ✅ 백엔드 의존성 설치 완료
cd ..

REM Docker 이미지 빌드 및 컨테이너 시작 (프로덕션 모드)
echo.
echo 🐳 프로덕션 Docker 이미지 빌드 중...
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build

if %errorlevel% neq 0 (
    echo ❌ Docker 빌드 실패
    pause
    exit /b 1
)

echo.
echo 🚀 프로덕션 컨테이너 시작 중...
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

if %errorlevel% neq 0 (
    echo ❌ 컨테이너 시작 실패
    pause
    exit /b 1
)

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ✨ 프로덕션 서버 시작 완료!
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo 📍 접속 URL:
echo    - 웹앱: http://localhost
echo    - API: http://localhost/api
echo    - API 문서: http://localhost/docs
echo.
echo 📊 컨테이너 상태:
docker-compose -f docker-compose.yml -f docker-compose.prod.yml ps
echo.
echo ⚙️  프로덕션 설정:
echo    - Gunicorn 4 workers
echo    - Nginx 정적 파일 캐싱
echo    - Gzip 압축 활성화
echo.
echo 📝 유용한 명령어:
echo    - 로그 확인: logs.bat
echo    - 서버 중지: stop.bat
echo    - 브라우저 열기: open-browser.bat
echo.

timeout /t 3 > nul
start http://localhost

pause

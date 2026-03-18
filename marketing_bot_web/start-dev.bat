@echo off
chcp 65001 > nul
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 🚀 Marketing Bot Web - 개발 서버 시작
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

REM Docker가 실행 중인지 확인
docker info > nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker가 실행 중이 아닙니다
    echo.
    echo 💡 Docker Desktop을 먼저 실행해주세요
    echo    https://www.docker.com/products/docker-desktop
    echo.
    pause
    exit /b 1
)

echo ✅ Docker 실행 확인
echo.

REM Docker 컨테이너 시작 (개발 모드)
echo 🐳 개발 서버 시작 중...
echo.
echo 📦 자동 설정:
echo    - 프론트엔드: Vite 개발 서버 (Hot Reload)
echo    - 백엔드: FastAPI + Uvicorn (Auto Reload)
echo    - 빌드 없음 (즉시 실행!)
echo.

docker-compose up -d

if %errorlevel% neq 0 (
    echo.
    echo ❌ 서버 시작 실패
    echo.
    echo 💡 문제 해결:
    echo    1. docker-compose down (기존 컨테이너 중지)
    echo    2. start-dev.bat 다시 실행
    echo.
    pause
    exit /b 1
)

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ✨ 개발 서버 시작 완료!
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo 📍 접속 URL:
echo    - 메인 앱: http://localhost
echo    - 프론트엔드 직접: http://localhost:5173
echo    - 백엔드 API: http://localhost:8000
echo    - API 문서: http://localhost:8000/docs
echo.
echo 🔥 개발 모드 특징:
echo    - 파일 수정 시 자동 새로고침
echo    - 빌드 불필요
echo    - 빠른 시작
echo.
echo 📊 컨테이너 상태:
docker-compose ps
echo.
echo 📝 유용한 명령어:
echo    - 로그 확인: logs.bat
echo    - 서버 중지: stop.bat
echo    - 서버 재시작: restart.bat
echo    - 브라우저 열기: open-browser.bat
echo.

REM 3초 대기 후 브라우저 자동 오픈
echo 🌐 3초 후 브라우저가 자동으로 열립니다...
timeout /t 3 > nul
start http://localhost

pause

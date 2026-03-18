@echo off
chcp 65001 > nul
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 📊 Marketing Bot Web - 서버 상태 확인
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

REM Docker 설치 확인
docker --version > nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker가 설치되어 있지 않습니다
    echo.
    echo 💡 Docker Desktop을 설치해주세요:
    echo    https://www.docker.com/products/docker-desktop
    echo.
    pause
    exit /b 1
)

echo ✅ Docker 설치 확인
docker --version
echo.

REM Docker Compose 설치 확인
docker-compose --version > nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker Compose가 설치되어 있지 않습니다
    pause
    exit /b 1
)

echo ✅ Docker Compose 설치 확인
docker-compose --version
echo.

echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 📦 컨테이너 상태
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
docker-compose ps
echo.

REM 서버 실행 여부 확인
docker-compose ps | findstr "Up" > nul
if %errorlevel% equ 0 (
    echo ✅ 서버가 실행 중입니다
    echo.
    echo 📍 접속 URL:
    echo    - 웹앱: http://localhost
    echo    - API: http://localhost/api
    echo    - API 문서: http://localhost/docs
    echo.

    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    echo 💻 시스템 리소스 사용량
    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    docker stats --no-stream
    echo.
) else (
    echo ⚠️  서버가 실행 중이 아닙니다
    echo.
    echo 💡 서버 시작 방법:
    echo    - 개발 서버: start-dev.bat
    echo    - 프로덕션 서버: start-prod.bat
    echo.
)

echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 📝 유용한 명령어
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo    start-dev.bat       - 개발 서버 시작
echo    start-prod.bat      - 프로덕션 서버 시작
echo    stop.bat            - 서버 중지
echo    restart.bat         - 서버 재시작
echo    logs.bat            - 로그 확인
echo    open-browser.bat    - 브라우저에서 열기
echo    status.bat          - 현재 상태 확인
echo.

pause

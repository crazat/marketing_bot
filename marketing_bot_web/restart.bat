@echo off
chcp 65001 > nul
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 🔄 Marketing Bot Web - 서버 재시작
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

echo 🛑 기존 컨테이너 중지 중...
docker-compose down

if %errorlevel% neq 0 (
    echo ❌ 컨테이너 중지 실패
    pause
    exit /b 1
)

echo ✅ 컨테이너 중지 완료
echo.

echo 🚀 컨테이너 재시작 중...
docker-compose up -d

if %errorlevel% neq 0 (
    echo ❌ 컨테이너 시작 실패
    pause
    exit /b 1
)

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ✅ 서버 재시작 완료!
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo 📍 접속 URL:
echo    - 웹앱: http://localhost
echo    - API: http://localhost/api
echo.
echo 📊 컨테이너 상태:
docker-compose ps
echo.

timeout /t 2 > nul
start http://localhost

pause

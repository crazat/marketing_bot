@echo off
chcp 65001 > nul
echo.
echo ⚡ Marketing Bot Web - 초간단 실행
echo.
echo 시작 중...

docker-compose up -d > nul 2>&1

if %errorlevel% equ 0 (
    echo ✅ 서버 시작 완료!
    echo.
    echo 📍 http://localhost
    echo.
    timeout /t 2 > nul
    start http://localhost
) else (
    echo ❌ 실패. Docker Desktop을 실행하고 다시 시도하세요.
    pause
)

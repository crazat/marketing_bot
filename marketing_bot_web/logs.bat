@echo off
chcp 65001 > nul
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 📝 Marketing Bot Web - 로그 확인
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

REM 서버 상태 확인
docker-compose ps | findstr "Up" > nul
if %errorlevel% neq 0 (
    echo ❌ 서버가 실행 중이 아닙니다
    echo.
    echo 💡 서버를 먼저 시작해주세요:
    echo    - 개발 서버: start-dev.bat
    echo    - 프로덕션 서버: start-prod.bat
    echo.
    pause
    exit /b 1
)

echo 📊 실시간 로그 스트림 시작...
echo.
echo 💡 로그 종료: Ctrl + C
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

docker-compose logs -f --tail=100

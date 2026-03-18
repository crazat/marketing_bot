@echo off
chcp 65001 > nul
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 🌐 브라우저에서 앱 열기
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

echo ✅ 서버가 실행 중입니다
echo.
echo 🌐 브라우저를 여는 중...
echo.
echo 📍 열리는 페이지:
echo    1. 메인 대시보드: http://localhost
echo    2. API 문서: http://localhost/docs
echo.

REM 메인 대시보드 열기
start http://localhost

REM 1초 대기 후 API 문서 열기
timeout /t 1 > nul
start http://localhost/docs

echo ✅ 브라우저에서 앱이 열렸습니다
echo.

pause

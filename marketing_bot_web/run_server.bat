@echo off
chcp 65001 > nul
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 🚀 Marketing Bot Web 서버 시작
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

cd /d "%~dp0"
cd backend

REM 빌드 폴더 확인
if not exist "..\frontend\dist" (
    echo.
    echo ⚠️  프론트엔드 빌드가 없습니다!
    echo    build_and_run.bat를 먼저 실행하세요.
    echo.
    pause
    exit /b 1
)

python main.py

pause

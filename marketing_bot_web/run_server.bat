@echo off
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
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

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\server_port_check.ps1" -Port 8000
set "PORT_CHECK=%ERRORLEVEL%"
if "%PORT_CHECK%"=="2" (
    echo.
    echo Existing Marketing Bot server was left running.
    exit /b 0
)
if not "%PORT_CHECK%"=="0" (
    pause
    exit /b %PORT_CHECK%
)

python main.py

pause

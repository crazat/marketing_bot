@echo off
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================================
echo Marketing Bot Web build and run
echo ============================================================

cd /d "%~dp0"

echo.
echo [1/2] Building frontend...
echo ============================================================
cd frontend
call npm run build
if errorlevel 1 (
    echo Frontend build failed.
    pause
    exit /b 1
)
cd ..

echo.
echo [2/2] Starting server...
echo ============================================================

set "RESTART_ARG="
if /I "%~1"=="--restart" set "RESTART_ARG=-Restart"
if "%MARKETING_BOT_RESTART%"=="1" set "RESTART_ARG=-Restart"

REM Port 8000 is normally a long-running workspace server. By default this
REM script leaves an existing Marketing Bot server alone and exits cleanly.
REM To force a restart, run: build_and_run.bat --restart
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\server_port_check.ps1" -Port 8000 %RESTART_ARG%
set "PORT_CHECK=%ERRORLEVEL%"
if "%PORT_CHECK%"=="2" (
    echo.
    echo Build finished. Existing Marketing Bot server was left running.
    exit /b 0
)
if not "%PORT_CHECK%"=="0" (
    pause
    exit /b %PORT_CHECK%
)

cd backend
python main.py

pause

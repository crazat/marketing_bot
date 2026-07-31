@echo off
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================================
echo Marketing Bot Web start
echo ============================================================

cd /d "%~dp0"

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

echo Starting backend...
pushd backend
start "Marketing Bot Backend" cmd /k "python main.py"
popd

timeout /t 3 /nobreak > nul

echo Starting frontend dev server...
cd frontend
npm run dev

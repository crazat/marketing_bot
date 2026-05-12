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

REM Make this script safe to run repeatedly. If an older Python main.py
REM backend is already listening on port 8000, stop it before starting
REM the freshly built server. If another app owns the port, fail clearly.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$connections = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; foreach ($connection in $connections) { $owner = $connection.OwningProcess; $process = Get-CimInstance Win32_Process | Where-Object ProcessId -eq $owner; if ($process.Name -match 'python' -and $process.CommandLine -match 'main.py') { Stop-Process -Id $owner -Force; Start-Sleep -Seconds 1; Write-Host 'Stopped existing Marketing Bot server on port 8000.' } else { Write-Host ('Port 8000 is already in use by PID ' + $owner + '. Stop that process first.'); exit 1 } }"
if errorlevel 1 (
    pause
    exit /b 1
)

cd backend
python main.py

pause

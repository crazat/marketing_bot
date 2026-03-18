@echo off
chcp 65001 > nul
echo 🤖 Setting up Always-On Marketing Sentinel...
echo ---------------------------------------------

set "PYTHON_PATH=python"
set "SCRIPT_PATH=%~dp0sentinel_guardian.py"

echo Target Script: %SCRIPT_PATH%

echo.
echo [1] Register Guardian Service (Startup)
echo [2] Delete Existing Service
echo.
set /p choice="Select Option (1/2): "

if "%choice%"=="1" (
    REM Register to run on System Startup (ONSTART) so it persists reboot
    schtasks /create /sc onstart /tn "KyurimMarketingGuardian" /tr "cmd /c chcp 65001 > nul && cd /d %~dp0 && %PYTHON_PATH% sentinel_guardian.py >> guardian.log 2>&1" /f
    echo.
    echo ✅ Service "KyurimMarketingGuardian" registered!
    echo It will start automatically when Windows starts.
    echo To start it NOW manually, run the bat file monitoring, or reboot.
) else (
    schtasks /delete /tn "KyurimMarketingGuardian" /f
    echo.
    echo 🗑️ Service deleted.
)

pause

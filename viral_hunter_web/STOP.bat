@echo off
chcp 65001 >nul
title 바이럴 헌터 종료
color 0C

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo     🛑 바이럴 헌터 워크스테이션 종료
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

echo [1/2] 실행 중인 서버 확인...
echo.

REM 바이럴 헌터 서버 프로세스 종료
tasklist /FI "WINDOWTITLE eq 바이럴 헌터 서버*" 2>nul | find /I "python.exe" >nul
if "%ERRORLEVEL%"=="0" (
    echo [2/2] 서버 종료 중...
    taskkill /F /FI "WINDOWTITLE eq 바이럴 헌터 서버*" >nul 2>&1
    echo.
    echo ✅ 바이럴 헌터 서버가 종료되었습니다.
) else (
    echo.
    echo ⚠️  실행 중인 서버가 없습니다.
)

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

timeout /t 3

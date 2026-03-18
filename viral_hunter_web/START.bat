@echo off
chcp 65001 >nul
title 바이럴 헌터 워크스테이션
color 0A

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo     🎯 바이럴 헌터 워크스테이션 시작
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo [1/3] 서버 시작 중...
echo.

cd /d "%~dp0"

REM 기존 프로세스 종료
taskkill /F /IM python.exe /FI "WINDOWTITLE eq 바이럴 헌터*" >nul 2>&1

echo [2/3] Flask 웹 서버 실행 중...
echo.

start "바이럴 헌터 서버" python app.py

REM 서버 시작 대기
timeout /t 3 /nobreak >nul

echo [3/3] 브라우저 열기...
echo.
start http://localhost:5000

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo     ✅ 바이럴 헌터가 시작되었습니다!
echo.
echo     📍 URL: http://localhost:5000
echo.
echo     🛑 종료하려면 STOP.bat을 실행하세요
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

pause

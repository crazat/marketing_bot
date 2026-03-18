@echo off
chcp 65001 > nul
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 🛑 Marketing Bot Web - 서버 중지
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

echo 🔍 실행 중인 서버 확인...

REM Uvicorn 프로세스 종료
tasklist | findstr "uvicorn" > nul 2>&1
if %errorlevel% equ 0 (
    echo 🔧 백엔드 서버 중지 중...
    taskkill /F /IM python.exe /FI "WINDOWTITLE eq Marketing Bot Backend*" > nul 2>&1
    echo ✅ 백엔드 중지 완료
)

REM Node 프로세스 종료
tasklist | findstr "node.exe" > nul 2>&1
if %errorlevel% equ 0 (
    echo 🎨 프론트엔드 서버 중지 중...
    taskkill /F /IM node.exe /FI "WINDOWTITLE eq Marketing Bot Frontend*" > nul 2>&1
    echo ✅ 프론트엔드 중지 완료
)

REM 포트 확인
netstat -ano | findstr ":5173" > nul 2>&1
if %errorlevel% equ 0 (
    echo ⚠️  포트 5173이 여전히 사용 중입니다
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173"') do (
        taskkill /F /PID %%a > nul 2>&1
    )
)

netstat -ano | findstr ":8000" > nul 2>&1
if %errorlevel% equ 0 (
    echo ⚠️  포트 8000이 여전히 사용 중입니다
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000"') do (
        taskkill /F /PID %%a > nul 2>&1
    )
)

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ✅ 모든 서버가 중지되었습니다
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

pause

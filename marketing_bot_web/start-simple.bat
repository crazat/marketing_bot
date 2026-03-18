@echo off
chcp 65001 > nul
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ⚡ Marketing Bot Web - 간편 실행 (Docker 불필요)
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

REM Node.js 확인
where node > nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Node.js가 설치되어 있지 않습니다
    echo.
    echo 💡 Node.js를 설치해주세요:
    echo    https://nodejs.org
    echo.
    pause
    exit /b 1
)

REM Python 확인
where python > nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python이 설치되어 있지 않습니다
    echo.
    echo 💡 Python을 설치해주세요:
    echo    https://www.python.org
    echo.
    pause
    exit /b 1
)

echo ✅ Node.js 설치 확인
node --version
echo ✅ Python 설치 확인
python --version
echo.

REM 프론트엔드 의존성 확인
if not exist "frontend\node_modules" (
    echo 📦 프론트엔드 의존성 설치 중...
    cd frontend
    call npm install
    if %errorlevel% neq 0 (
        echo ❌ npm install 실패
        cd ..
        pause
        exit /b 1
    )
    cd ..
    echo ✅ 설치 완료
    echo.
)

REM 백엔드 의존성 확인
echo 📦 백엔드 의존성 확인 중...
cd backend
pip list | findstr "fastapi" > nul 2>&1
if %errorlevel% neq 0 (
    echo 📦 백엔드 의존성 설치 중...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ❌ pip install 실패
        cd ..
        pause
        exit /b 1
    )
)
cd ..
echo ✅ 백엔드 준비 완료
echo.

REM 서버 시작
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 🚀 서버 시작 중...
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

REM 백엔드 시작 (백그라운드)
echo 🔧 백엔드 서버 시작 (백그라운드)...
cd backend
start /b python -m uvicorn main:app --reload --port 8000 > nul 2>&1
cd ..
timeout /t 3 > nul

REM 프론트엔드 시작 (백그라운드)
echo 🎨 프론트엔드 서버 시작 (백그라운드)...
cd frontend
start /b npm run dev > nul 2>&1
cd ..
timeout /t 5 > nul

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ✨ 서버 시작 완료!
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo 📍 접속 URL:
echo    - 프론트엔드: http://localhost:5173
echo    - 백엔드 API: http://localhost:8000
echo    - API 문서: http://localhost:8000/docs
echo.
echo 💡 이 창을 닫지 마세요!
echo    서버가 백그라운드에서 실행 중입니다.
echo.
echo 🛑 서버 중지 방법:
echo    1. 이 창에서 아무 키나 누르면 중지됩니다
echo    2. 또는 stop-simple.bat 실행
echo.
echo 🌐 3초 후 브라우저가 열립니다...
timeout /t 3 > nul

start http://localhost:5173

echo.
echo ✅ 서버 실행 중... (아무 키나 누르면 중지)
echo.
pause > nul

REM 서버 중지
echo.
echo 🛑 서버 중지 중...

REM Node 프로세스 종료
tasklist | findstr "node.exe" > nul 2>&1
if %errorlevel% equ 0 (
    echo 🎨 프론트엔드 서버 중지...
    taskkill /F /IM node.exe > nul 2>&1
)

REM Python/Uvicorn 프로세스 종료
tasklist | findstr "python.exe" > nul 2>&1
if %errorlevel% equ 0 (
    echo 🔧 백엔드 서버 중지...
    for /f "tokens=2" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
        for /f "tokens=5" %%b in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
            taskkill /F /PID %%b > nul 2>&1
        )
    )
)

echo.
echo ✅ 서버가 중지되었습니다
echo.
pause

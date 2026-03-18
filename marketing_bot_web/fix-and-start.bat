@echo off
chcp 65001 > nul
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 🔧 Marketing Bot Web - 완전 초기화 및 재시작
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

REM 1. 기존 프로세스 모두 종료
echo 🛑 기존 프로세스 종료 중...
taskkill /F /IM node.exe > nul 2>&1
taskkill /F /IM python.exe > nul 2>&1
timeout /t 2 > nul

REM 2. 포트 확인 및 정리
echo 🔍 포트 8000, 5173 정리 중...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /F /PID %%a > nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do taskkill /F /PID %%a > nul 2>&1
timeout /t 2 > nul

REM 3. 프론트엔드 의존성 완전 재설치
echo.
echo 📦 프론트엔드 의존성 완전 재설치 중...
cd frontend

if exist node_modules (
    echo    - node_modules 삭제 중...
    rmdir /S /Q node_modules 2>nul
)

if exist package-lock.json (
    echo    - package-lock.json 삭제 중...
    del /F /Q package-lock.json 2>nul
)

echo    - npm install 실행 중... (시간이 걸릴 수 있습니다)
call npm install --legacy-peer-deps
if %errorlevel% neq 0 (
    echo.
    echo ❌ npm install 실패
    echo.
    echo 💡 다음을 시도해보세요:
    echo    1. Node.js 재설치: https://nodejs.org
    echo    2. npm cache clean --force
    echo    3. 관리자 권한으로 PowerShell 실행
    echo.
    pause
    exit /b 1
)

cd ..
echo    ✅ 프론트엔드 의존성 설치 완료

REM 4. 백엔드 의존성 확인
echo.
echo 📦 백엔드 의존성 확인 중...
cd backend
python -c "import fastapi" 2>nul
if %errorlevel% neq 0 (
    echo    - 백엔드 의존성 설치 중...
    pip install -r requirements.txt
)
cd ..
echo    ✅ 백엔드 준비 완료

REM 5. 서버 시작
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 🚀 서버 시작 중...
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

REM 백엔드 시작
echo 🔧 백엔드 서버 시작 중...
cd backend
start /b python -m uvicorn main:app --reload --port 8000 > ..\backend.log 2>&1
cd ..
timeout /t 3 > nul

REM 프론트엔드 시작
echo 🎨 프론트엔드 서버 시작 중...
cd frontend
start /b npm run dev > ..\frontend.log 2>&1
cd ..
timeout /t 5 > nul

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ✅ 서버 시작 완료!
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo 📍 접속 URL:
echo    - 프론트엔드: http://localhost:5173
echo    - 백엔드 API: http://localhost:8000
echo    - API 문서: http://localhost:8000/docs
echo.
echo 📝 로그 파일:
echo    - backend.log (백엔드 로그)
echo    - frontend.log (프론트엔드 로그)
echo.
echo 💡 서버가 시작되지 않으면:
echo    1. backend.log 파일을 열어 에러 확인
echo    2. frontend.log 파일을 열어 에러 확인
echo    3. 아래 명령어로 로그 실시간 확인:
echo       type backend.log
echo       type frontend.log
echo.
echo 🌐 5초 후 브라우저가 열립니다...
timeout /t 5 > nul

start http://localhost:5173

echo.
echo ✅ 서버 실행 중...
echo.
echo 🛑 서버 중지: Ctrl+C 또는 이 창을 닫으세요
echo    (또는 stop-simple.bat 실행)
echo.
pause

@echo off
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 🚀 Marketing Bot Web 시작
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo 📡 백엔드 서버 시작 중...
start cmd /k "cd backend && python main.py"

timeout /t 3 /nobreak >nul

echo 🎨 프론트엔드 서버 시작 중...
cd frontend
npm run dev

#!/bin/bash

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Marketing Bot Web 시작"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 백엔드 시작 (백그라운드)
echo "📡 백엔드 서버 시작 중..."
cd backend
python main.py &
BACKEND_PID=$!
cd ..

# 잠시 대기 (백엔드 시작)
sleep 3

# 프론트엔드 시작
echo "🎨 프론트엔드 서버 시작 중..."
cd frontend
npm run dev

# Ctrl+C 시 백엔드도 종료
trap "kill $BACKEND_PID" EXIT

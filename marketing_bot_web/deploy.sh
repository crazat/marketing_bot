#!/bin/bash

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Marketing Bot Web 배포 스크립트"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. 프론트엔드 빌드
echo "📦 프론트엔드 빌드 중..."
cd frontend
npm install
npm run build

if [ $? -ne 0 ]; then
    echo "❌ 프론트엔드 빌드 실패"
    exit 1
fi

echo "✅ 프론트엔드 빌드 완료"
cd ..

# 2. 백엔드 의존성 설치
echo "📦 백엔드 의존성 설치 중..."
cd backend
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ 백엔드 의존성 설치 실패"
    exit 1
fi

echo "✅ 백엔드 의존성 설치 완료"
cd ..

# 3. Docker 이미지 빌드
echo "🐳 Docker 이미지 빌드 중..."
docker-compose build

if [ $? -ne 0 ]; then
    echo "❌ Docker 빌드 실패"
    exit 1
fi

echo "✅ Docker 이미지 빌드 완료"

# 4. 컨테이너 시작
echo "🚀 컨테이너 시작 중..."
docker-compose up -d

if [ $? -ne 0 ]; then
    echo "❌ 컨테이너 시작 실패"
    exit 1
fi

echo "✅ 컨테이너 시작 완료"

# 5. 상태 확인
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ 배포 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📍 접속 URL:"
echo "   - 웹앱: http://localhost"
echo "   - API: http://localhost/api"
echo "   - API 문서: http://localhost/docs"
echo ""
echo "📊 컨테이너 상태:"
docker-compose ps
echo ""
echo "📝 로그 확인: docker-compose logs -f"
echo "🛑 중지: docker-compose down"
echo ""

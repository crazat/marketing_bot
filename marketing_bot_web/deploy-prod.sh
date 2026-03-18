#!/bin/bash

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Marketing Bot Web 프로덕션 배포"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 환경 변수 확인
if [ ! -f ".env" ]; then
    echo "❌ .env 파일이 없습니다. .env.example을 참고하여 생성하세요."
    exit 1
fi

# 1. Git 최신 코드 가져오기 (선택사항)
echo "📥 Git 업데이트..."
git pull origin main

# 2. 기존 컨테이너 중지
echo "🛑 기존 컨테이너 중지 중..."
docker-compose down

# 3. 프론트엔드 프로덕션 빌드
echo "📦 프론트엔드 프로덕션 빌드 중..."
cd frontend
npm ci  # clean install (lock 파일 기준)
npm run build

if [ $? -ne 0 ]; then
    echo "❌ 프론트엔드 빌드 실패"
    exit 1
fi

echo "✅ 프론트엔드 빌드 완료 (dist/ 폴더)"
cd ..

# 4. Docker 이미지 빌드 (캐시 없이)
echo "🐳 Docker 이미지 빌드 중 (캐시 없음)..."
docker-compose build --no-cache

if [ $? -ne 0 ]; then
    echo "❌ Docker 빌드 실패"
    exit 1
fi

# 5. 프로덕션 모드로 컨테이너 시작
echo "🚀 프로덕션 컨테이너 시작 중..."
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

if [ $? -ne 0 ]; then
    echo "❌ 컨테이너 시작 실패"
    exit 1
fi

# 6. 헬스체크
echo "🏥 헬스체크 중..."
sleep 5

# 백엔드 헬스체크
if curl -f http://localhost/api/health > /dev/null 2>&1; then
    echo "✅ 백엔드 정상"
else
    echo "❌ 백엔드 헬스체크 실패"
    exit 1
fi

# 7. 완료
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ 프로덕션 배포 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📍 서비스 URL:"
echo "   - 웹앱: http://localhost"
echo "   - API 문서: http://localhost/docs"
echo ""
echo "📊 컨테이너 상태:"
docker-compose ps
echo ""
echo "📝 실시간 로그: docker-compose logs -f"
echo "🔍 백엔드 로그: docker-compose logs -f backend"
echo "🔍 프론트엔드 로그: docker-compose logs -f frontend"
echo "🛑 서비스 중지: docker-compose down"
echo ""
echo "⚠️  데이터베이스 백업을 잊지 마세요!"
echo ""

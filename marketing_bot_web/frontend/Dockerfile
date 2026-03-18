FROM node:20-alpine

WORKDIR /app

# 의존성 설치
COPY package*.json ./
RUN npm install

# 앱 코드 복사
COPY . .

# 포트 노출
EXPOSE 5173

# 개발 서버 실행
CMD ["npm", "run", "dev", "--", "--host"]

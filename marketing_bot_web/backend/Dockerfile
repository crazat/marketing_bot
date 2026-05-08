FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
# 이 Dockerfile은 프로젝트 루트를 build context로 사용한다.
COPY requirements.txt /tmp/root-requirements.txt
COPY marketing_bot_web/backend/requirements.txt /tmp/backend-requirements.txt
RUN pip install --no-cache-dir -r /tmp/root-requirements.txt -r /tmp/backend-requirements.txt

# 앱 코드 복사
COPY . .

ENV PYTHONPATH=/app:/app/marketing_bot_web/backend
WORKDIR /app/marketing_bot_web/backend

# 포트 노출
EXPOSE 8000

# 실행 명령
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

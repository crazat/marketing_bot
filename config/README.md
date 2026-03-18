# Config Directory

이 디렉토리는 Marketing Bot의 모든 설정 파일을 포함합니다.

## 파일 설명

| 파일 | 설명 | 중요도 |
|-----|-----|--------|
| `secrets.json` | API 키 및 인증 정보 | 🔴 **Git 제외 필수** |
| `keywords_master.json` | 마스터 키워드 목록 (카테고리별) | 🟡 |
| `targets.json` | 경쟁사 및 모니터링 타겟 | 🟡 |
| `prompts.json` | AI 프롬프트 템플릿 | 🟢 |
| `campaigns.json` | Pathfinder 캠페인 설정 | 🟢 |

## secrets.json 구조

```json
{
  "GEMINI_API_KEY": "your-gemini-api-key",
  "NAVER_CLIENT_ID": "your-naver-client-id",
  "NAVER_CLIENT_SECRET": "your-naver-client-secret",
  "NAVER_AD_API_KEY": "optional-ad-api-key",
  "NAVER_AD_SECRET": "optional-ad-secret",
  "NAVER_AD_CUSTOMER_ID": "optional-customer-id",
  "TELEGRAM_BOT_TOKEN": "your-telegram-bot-token",
  "TELEGRAM_CHAT_ID": "your-telegram-chat-id"
}
```

## 환경변수 대안

`.env` 파일을 루트에 생성하여 환경변수로 설정할 수도 있습니다:

```env
GEMINI_API_KEY=your-key
NAVER_CLIENT_ID=your-id
CHROMEDRIVER_PATH=C:\path\to\chromedriver.exe
```

## 보안 주의사항

- `secrets.json`은 `.gitignore`에 포함되어 있습니다
- 절대로 API 키를 Git에 커밋하지 마세요
- 팀 공유 시 `.env.example` 형식으로 공유하세요

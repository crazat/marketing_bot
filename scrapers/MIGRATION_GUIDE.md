# 스크래퍼 BaseScraperMixin 마이그레이션 가이드

[X2] 공용 패턴 중복을 제거하기 위한 점진 이관 가이드.

## Before / After

### Before (자체 구현)
```python
class MyScraper:
    def __init__(self, delay=1.0):
        self.delay = delay
        self._last_call = 0
        self.headers = {
            "User-Agent": "Mozilla/5.0 ...",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()
```

### After (공용 Mixin)
```python
from scrapers.common import BaseScraperMixin, default_headers, rate_limited_session

class MyScraper(BaseScraperMixin):
    def __init__(self, delay=1.0):
        super().__init__(delay=delay)
        self.session = rate_limited_session()  # 재시도·풀 설정된 Session
        self.headers = default_headers()       # 랜덤 UA + 한국어 헤더
```

## 이관 완료

| 파일 | 상태 |
|---|---|
| `competitor_analyzer.py` | ✅ 전환됨 (X2 PoC) |
| `naver_autocomplete.py` | ✅ 전환됨 (Y3) |

## 이관 대기

| 파일 | 자체 rate_limit | 자체 headers | 우선도 |
|---|:---:|:---:|---|
| `cafe_spy.py` | ✓ | ✓ | High |
| `competitor_blog_tracker.py` | ✓ | ✓ | High |
| `healthcare_news_monitor.py` | ✓ | ✓ | Medium |
| `blog_rank_tracker.py` | ✓ | ✓ | Medium |
| `web_visibility_tracker.py` | ✓ | ✓ | Medium |
| `search_demographics_analyzer.py` | ✓ | ✓ | Low |

## 이관 시 주의
- `super().__init__(delay=...)` 호출 필수 (카운터 초기화)
- 기존 `_rate_limit` 메서드 제거 (Mixin이 제공)
- `requests.get` 직접 호출 → `self.safe_get(self.session, url, ...)`로 전환 권장 (에러 통계 수집)
- 기존 로컬 state(`_last_call`)는 Mixin의 `self._last_call`이 대체

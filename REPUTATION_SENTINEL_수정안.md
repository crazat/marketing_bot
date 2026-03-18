# Reputation Sentinel 문제 분석 및 수정안 계획서

**작성일**: 2026-01-26
**작성자**: Claude Opus 4.5
**대상 파일**: `sentinel_agent.py`, `scheduler.py`

---

## 1. 문제 현상

- **증상**: 09:00에 Reputation Sentinel 실행 후 "계속 실행중" 상태로 무한 대기
- **영향**: 대시보드에서 RUNNING 상태 지속, 완료 알림 없음

---

## 2. 근본 원인 분석

### 2.1 Critical - Gemini API 타임아웃 부재
**위치**: `sentinel_agent.py:136-140`

```python
response = self.client.models.generate_content(
    model=self.model_name,
    contents=prompt,
    config={'response_mime_type': 'application/json'}
)
# ⚠️ timeout 파라미터 없음 → 무한 대기 가능
```

**문제점**: Gemini API 서버 지연/장애 시 응답을 무한히 대기함

---

### 2.2 Critical - patrol() 루프 내 에러 격리 부재
**위치**: `sentinel_agent.py:280-392`

```python
def patrol(self):
    while True:  # 무한 루프
        # 에러 발생 시 루프 전체가 멈춤
        for kw in self.targets.get('brand_keywords', []):
            analysis = brain.analyze_threat(kw, res['text'])  # 여기서 멈춤
```

**문제점**: `analyze_threat()` 내부에서 예외 처리가 있지만, 네트워크 레벨 타임아웃은 처리 못함

---

### 2.3 High - 상태 관리 불완전
**위치**: `sentinel_agent.py:448-458`

```python
if __name__ == "__main__":
    status_manager.update_status("Reputation Sentinel", "RUNNING", ...)
    scout.patrol()  # ← 여기서 무한 대기
    # patrol()이 리턴하지 않으므로 상태 업데이트 불가
```

**문제점**:
- daemon 모드로 실행되어 patrol()이 while True 루프
- 한 사이클 완료 후에도 상태가 "RUNNING"으로 유지
- 사이클 완료 시점의 상태 피드백 없음

---

### 2.4 Medium - daemon 프로세스 로깅 누락
**위치**: `scheduler.py:83-88`

```python
subprocess.Popen(
    full_cmd,
    stdout=subprocess.DEVNULL,  # 출력 무시
    stderr=subprocess.DEVNULL   # 에러 무시
)
```

**문제점**: daemon 프로세스의 모든 출력이 무시되어 디버깅 어려움

---

## 3. 수정안

### 수정 1: Gemini API 호출에 타임아웃 추가
**파일**: `sentinel_agent.py`
**위치**: `analyze_threat()` 메서드 (라인 96-150)

```python
# 수정 전
response = self.client.models.generate_content(
    model=self.model_name,
    contents=prompt,
    config={'response_mime_type': 'application/json'}
)

# 수정 후
from google.genai import types

response = self.client.models.generate_content(
    model=self.model_name,
    contents=prompt,
    config=types.GenerateContentConfig(
        response_mime_type='application/json',
        timeout=30  # 30초 타임아웃
    )
)
```

**대안 (httpx 레벨 타임아웃)**:
```python
# genai Client 초기화 시
self.client = genai.Client(
    api_key=self.api_key,
    http_options={'timeout': 30000}  # 30초 (밀리초)
)
```

---

### 수정 2: patrol() 사이클별 에러 격리
**파일**: `sentinel_agent.py`
**위치**: `patrol()` 메서드 (라인 280-392)

```python
def patrol(self):
    brain = SentinelBrain()
    logger.info("[Sentinel] Patrol Started...")

    while True:
        try:  # 사이클 단위 에러 격리
            scan_id = str(uuid.uuid4())[:8]
            logger.info(f"[Sentinel] Scan Batch: {scan_id}")

            # ... 기존 스캔 로직 ...

            self.update_state(health, threats, unknown_threats)
            logger.info(f"[Sentinel] Cycle Complete. Health: {health}")

        except Exception as e:
            logger.error(f"[Sentinel] Cycle Failed: {e}")
            # 사이클 실패해도 다음 사이클 진행
            self.update_state(0, [], [])  # 실패 상태 기록

        finally:
            sleep_time = 1800
            logger.info(f"[Sentinel] Resting for {sleep_time / 60} mins...")
            time.sleep(sleep_time)
```

---

### 수정 3: 사이클 완료 시 상태 업데이트
**파일**: `sentinel_agent.py`
**위치**: `update_state()` 호출 후 (라인 386)

```python
# 기존 update_state 호출 후 추가
from db.status_manager import status_manager

# update_state() 호출 후
status_manager.update_status(
    "Reputation Sentinel",
    "IDLE",  # 대기 상태
    f"Cycle complete. Health: {health}. Next scan in 30m"
)
```

---

### 수정 4: daemon 프로세스 로깅 활성화
**파일**: `scheduler.py`
**위치**: `run_task()` 메서드 (라인 78-90)

```python
if task['type'] == 'daemon':
    # 로그 파일로 출력 리디렉션
    log_path = os.path.join(self.root_dir, 'logs', f"{task['label'].lower().replace(' ', '_')}.log")
    log_file = open(log_path, 'a', encoding='utf-8')

    creation_flags = 0x00000008 | 0x00000200 if sys.platform == 'win32' else 0
    subprocess.Popen(
        full_cmd,
        creationflags=creation_flags,
        shell=False,
        stdout=log_file,
        stderr=log_file
    )
```

---

### 수정 5: 개별 키워드 스캔 타임아웃
**파일**: `sentinel_agent.py`
**위치**: Brand/Battleground 스캔 루프

```python
import signal
from contextlib import contextmanager

@contextmanager
def timeout_context(seconds):
    """단일 작업 타임아웃 컨텍스트"""
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Operation timed out after {seconds}s")

    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

# 사용 예시
for kw in self.targets.get('brand_keywords', []):
    try:
        with timeout_context(60):  # 키워드당 60초 제한
            results = self.search_naver_view(kw)
            for res in results:
                analysis = brain.analyze_threat(kw, res['text'])
                # ...
    except TimeoutError:
        logger.warning(f"[Timeout] Keyword scan timed out: {kw}")
        continue
```

> **참고**: Windows에서는 `signal.SIGALRM` 미지원. `threading.Timer` 기반 대안 필요.

---

## 4. 수정 우선순위

| 순위 | 수정안 | 영향도 | 난이도 | 예상 효과 |
|------|--------|--------|--------|-----------|
| 1 | Gemini API 타임아웃 | Critical | 낮음 | 무한 대기 방지 |
| 2 | patrol() 에러 격리 | Critical | 낮음 | 크래시 복원력 |
| 3 | 상태 업데이트 개선 | High | 낮음 | 모니터링 개선 |
| 4 | daemon 로깅 활성화 | Medium | 낮음 | 디버깅 용이성 |
| 5 | 키워드별 타임아웃 | Medium | 중간 | 세밀한 제어 |

---

## 5. 테스트 계획

### 5.1 단위 테스트
```python
def test_analyze_threat_timeout():
    """Gemini API 타임아웃 동작 테스트"""
    brain = SentinelBrain()
    # Mock slow API response
    result = brain.analyze_threat("test", "content")
    assert result['classification'] in ['SAFE', 'UNKNOWN', ...]

def test_patrol_cycle_error_recovery():
    """patrol 사이클 에러 복구 테스트"""
    scout = SentinelScout()
    # 첫 사이클 실패 시뮬레이션
    # 두 번째 사이클 정상 동작 확인
```

### 5.2 통합 테스트
1. sentinel_agent.py 단독 실행 → 1 사이클 후 상태 확인
2. 네트워크 차단 상태에서 실행 → 타임아웃 동작 확인
3. scheduler.py와 함께 실행 → 로그 파일 생성 확인

---

## 6. 롤백 계획

수정 전 백업 파일 생성:
```bash
cp sentinel_agent.py sentinel_agent.py.bak
cp scheduler.py scheduler.py.bak
```

문제 발생 시 즉시 원복:
```bash
cp sentinel_agent.py.bak sentinel_agent.py
```

---

## 7. 예상 결과

- Gemini API 장애 시에도 30초 후 다음 작업 진행
- patrol() 사이클 중 오류 발생해도 다음 사이클 정상 실행
- 대시보드에서 "RUNNING" → "IDLE" 상태 전환 확인 가능
- daemon 로그 파일로 문제 추적 가능

---

## 8. 구현 승인 요청

위 수정안에 대해 검토 후 승인해 주시면 순차적으로 구현 진행하겠습니다.

- [ ] 수정안 1: Gemini API 타임아웃
- [ ] 수정안 2: patrol() 에러 격리
- [ ] 수정안 3: 상태 업데이트 개선
- [ ] 수정안 4: daemon 로깅 활성화
- [ ] 수정안 5: 키워드별 타임아웃 (선택사항)

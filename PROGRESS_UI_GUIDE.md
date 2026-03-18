# 실시간 진행 상황 UI 가이드

## 적용된 개선사항 (2026-01-27)

### ✅ 개선된 명령어

다음 명령어들은 **실시간 진행 상황**을 표시합니다:

1. **🚀 LEGION MODE 실행**
   - 수집된 키워드 수 실시간 표시
   - S/A급 키워드 카운트
   - 현재 라운드 표시
   - 경과 시간 표시

2. **⚔️ Total War 실행**
   - 동일한 실시간 진행 상황

3. **📺 YouTube 스캔**
   - 실시간 로그 표시
   - 경과 시간

4. **🎵 TikTok 스캔**
   - 실시간 로그 표시
   - 경과 시간

---

## UI 구성 요소

### 1. st.status() - 상태 표시기
```
🚀 LEGION MODE 실행 중...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⏱️ 경과 시간: 2분 15초
📍 현재 작업: Round 3: 지역 확장

수집된 키워드: 234개
  △ 🔥 S급 87개 | 🟢 A급 45개

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[실시간 로그]
   진행: 230/560...
   청주 한의원 수집 중...
   난이도: 25, 기회: 75, 등급: S
   ...
```

### 2. 자동 파싱 기능

로그에서 자동으로 정보를 추출합니다:

- `총 키워드: 234개` → 키워드 수
- `S급: 87개` → S급 카운트
- `A급: 45개` → A급 카운트
- `Round 3` → 현재 라운드

### 3. 업데이트 주기

- 로그: 0.5초마다 업데이트
- 부드러운 사용자 경험
- 최근 30줄만 표시 (메모리 절약)

---

## 사용 방법

### 키워드 공략 탭
1. **LEGION MODE 탭** 이동
2. "🚀 LEGION 실행 (500개 S/A급)" 버튼 클릭
3. 실시간 진행 상황 창이 자동으로 열림
4. 완료 시 자동으로 페이지 새로고침

### Battle Intelligence 탭
1. **YouTube Leads** 또는 **TikTok Leads** 탭 이동
2. "▶️ 스캔 실행" 버튼 클릭
3. 실시간 로그 표시

---

## 기술적 세부사항

### execute_command() 함수

```python
def execute_command(cmd_key, args=None, show_progress=False):
    # show_progress=True 면 실시간 진행 표시
    # show_progress=False 면 백그라운드 실행 (기존)
```

**백그라운드 실행** (Chronos Timeline 자동 실행):
- 로그 파일에만 저장
- UI 방해 안 함
- `logs/exec_{cmd_key}.log` 파일 확인 가능

**실시간 진행 표시** (수동 버튼 클릭):
- subprocess의 stdout을 실시간 캡처
- st.status()로 UI 표시
- 완료 시 결과 요약

### 로그 파싱

```python
# 예시 로그 라인
"   총 키워드: 234개"
"   🔥 S급: 87개"
"   🟢 A급: 45개"

# 파싱 코드
if "총 키워드:" in log_line:
    total_keywords = int(log_line.split("총 키워드:")[1].split("개")[0].strip())
```

---

## 다른 명령어에도 적용하기

### 1. Cafe Swarm에 적용

```python
# 현재 (백그라운드만)
execute_command("cafe_swarm")

# 진행 상황 표시로 변경
execute_command("cafe_swarm", show_progress=True)
```

### 2. 커스텀 명령어 추가

```python
# dashboard_ultra.py의 cmd_map에 추가
cmd_map = {
    "my_command": [python_exe, "my_script.py"]
}

cmd_titles = {
    "my_command": "🎯 My Command"
}

# 호출
execute_command("my_command", show_progress=True)
```

### 3. 스크립트에서 진행 상황 출력

스크립트가 다음 형식으로 출력하면 자동 파싱됩니다:

```python
# my_script.py
print("   진행: 10/100...")
print("   현재: 청주 한의원 처리 중")
print("   총 키워드: 50개")
print("   🔥 S급: 20개")
```

---

## 추가 개선 아이디어

### 1. 프로그레스 바 추가
```python
progress_bar = st.progress(0)
# 진행률 계산
progress = current / total
progress_bar.progress(progress)
```

### 2. 예상 완료 시간
```python
# 평균 속도 계산
speed = current / elapsed_time  # 키워드/초
remaining = (total - current) / speed
print(f"예상 완료: {int(remaining // 60)}분 {int(remaining % 60)}초")
```

### 3. 중간 결과 미리보기
```python
# 수집한 키워드 상위 10개 표시
with st.expander("수집 중인 키워드 미리보기"):
    st.dataframe(preview_df)
```

---

## 문제 해결

### 로그가 표시되지 않음
- 스크립트가 stdout으로 출력하는지 확인
- `print()` 대신 `sys.stdout.write()` 사용
- `flush=True` 옵션 사용: `print(..., flush=True)`

### 업데이트가 느림
- `time.sleep(0.5)` 조정
- 로그 버퍼 크기 조정

### 메모리 사용량 증가
- `logs` 리스트 크기 제한 (현재 30줄)
- 필요시 줄이기: `logs = logs[-20:]`

---

## 참고 자료

- [Streamlit st.status 문서](https://docs.streamlit.io/develop/api-reference/status/st.status)
- [Python subprocess 실시간 출력](https://docs.python.org/3/library/subprocess.html#subprocess.Popen)
- [Threading과 Queue](https://docs.python.org/3/library/queue.html)

# Streamlit 최적화 가이드

## 적용된 최적화 (2026-01-27)

### 1. st.fragment 패턴
- 필터+테이블 섹션을 fragment로 분리
- 부분 업데이트로 스크롤 위치 유지
- 상단 메트릭은 재계산하지 않음

### 2. 캐싱 전략
- `@st.cache_data(ttl=300)` - DB 쿼리 결과 5분 캐시
- 불필요한 재쿼리 방지

### 3. UI 구조 개선
- 차트를 expander로 감싸서 선택적 표시
- 테이블 높이 증가 (400px → 600px)

---

## 추가 최적화 방법

### 📊 더 공격적인 캐싱
```python
@st.cache_data(ttl=3600)  # 1시간
def load_static_data():
    # 거의 변하지 않는 데이터
    pass

@st.cache_resource
def get_db_connection():
    # DB 커넥션 재사용
    return sqlite3.connect("db/marketing_data.db")
```

### 🎯 페이지 분리
현재 단일 파일 (2800+ 라인) → 여러 페이지로 분리:
```
pages/
├── 1_keywords.py      # 키워드 공략
├── 2_leads.py         # 리드 관리
├── 3_insights.py      # 인사이트
└── 4_settings.py      # 설정
```

**장점**:
- 각 페이지가 독립적으로 로드
- 코드 관리 용이
- 초기 로딩 속도 향상

### ⚡ Lazy Loading
```python
if st.button("차트 보기"):
    # 버튼 클릭 시에만 차트 렌더링
    render_heavy_charts()
```

### 🔄 Session State 활용
```python
if "keywords_df" not in st.session_state:
    st.session_state.keywords_df = load_keywords()

# 이후 재사용
df = st.session_state.keywords_df
```

---

## 성능 모니터링

### Streamlit Profiler 사용
```bash
streamlit run dashboard_ultra.py --logger.level=debug
```

### 병목 지점 확인
- DB 쿼리 시간
- DataFrame 처리 시간
- 차트 렌더링 시간

---

## 장기 전략

### 현재 (Streamlit 최적화)
- 내부 도구로 충분
- 1-2명 사용
- 빠른 개발

### 6개월 후 (Dash 고려)
- 사용자 5명+
- 더 복잡한 인터랙션 필요
- 부분 업데이트 필수

### 1년 후 (웹 프레임워크)
- 외부 고객에게 제공
- 모바일 지원 필요
- SaaS 제품화

---

## 체크리스트

개발 시 성능을 위해 확인할 것:

- [ ] 무거운 계산은 `@st.cache_data` 사용
- [ ] DB 쿼리는 필요한 컬럼만 SELECT
- [ ] 큰 DataFrame은 .head() 또는 샘플링
- [ ] 차트는 expander나 조건부 렌더링
- [ ] fragment 패턴으로 부분 업데이트
- [ ] 불필요한 st.rerun() 호출 제거

---

## 참고 자료

- [Streamlit Fragment 문서](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment)
- [Streamlit Caching 가이드](https://docs.streamlit.io/develop/concepts/architecture/caching)
- [Performance Best Practices](https://docs.streamlit.io/develop/concepts/architecture/app-chrome#performance-best-practices)

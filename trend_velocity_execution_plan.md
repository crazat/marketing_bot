# 📈 트렌드 속도 감지 (Trend Velocity Detection) 구체적 실행 계획서 (Refactored)

**목표**: Pathfinder가 수집한 키워드 중 유망한 후보군(Golden Candidates)에 대해 Naver Datalab API를 연동, 실시간 트렌드 성장세 (Slope)를 분석하여 급상승 키워드를 포착한다.

**변경사항**: `prophet.py`(날씨/시즌 잡합)에 의존하는 대신, 전용 API 모듈(`NaverDataLabManager`)을 분리하여 경량화 및 모듈화를 진행합니다.

---

## 1단계: 데이터베이스 스키마 확장 (Database Schema Extension)
**작업 내용**: SQLite `keyword_insights` 테이블에 트렌드 관련 데이터를 저장할 컬럼을 추가합니다.

*   **Target File**: `scripts/update_db_schema.py`
*   **SQL Commands**:
    ```sql
    ALTER TABLE keyword_insights ADD COLUMN trend_slope REAL DEFAULT 0.0;
    ALTER TABLE keyword_insights ADD COLUMN trend_status TEXT DEFAULT 'unknown'; -- 'rising', 'falling', 'flat'
    ALTER TABLE keyword_insights ADD COLUMN trend_checked_at TIMESTAMP;
    ```

## 2단계: Naver Datalab 전용 모듈 분리 (Create DataLab Manager)
**작업 내용**: `prophet.py`에 섞여 있던 API 로직을 추출하여 순수 API 클라이언트 모듈로 만듭니다.

*   **New File**: `scrapers/naver_datalab_manager.py`
*   **기능**:
    *   `get_trend_slope(keyword)`: 특정 키워드의 30일간 추세 기울기 반환.
    *   API 인증 처리 및 에러 핸들링 (기존 `NaverAdManager` 스타일 따름).
    *   타임아웃 및 재시도 로직 포함.

## 3단계: Pathfinder 스마트 샘플링 로직 구현 (Smart Sampling)
**작업 내용**: 선별된 키워드에 대해 신규 모듈을 호출하여 트렌드를 조회합니다.

*   **Target File**: `pathfinder.py`
*   **구현 로직 (`verify_trends_smartly`)**:
    1.  **모듈 임포트**: `from scrapers.naver_datalab_manager import NaverDataLabManager`
    2.  **필터링**: 검색량 1,000 이상, 경쟁도 Low 인 키워드 선별.
    3.  **실행**: `dl_mgr.get_trend_slope(keyword)` 호출.
    4.  **병합**: 결과를 딕셔너리에 업데이트.

## 4단계: 배치 저장 프로세스 통합 (Integration) 
**작업 내용**: 트렌드 분석이 끝난 데이터를 DB에 저장하도록 `_batch_save_to_db` 로직을 수정합니다.

*   **Target File**: `pathfinder.py`
*   **작업**:
    *   `INSERT` 쿼리에 새로 추가된 컬럼(`trend_slope`, `trend_status`) 반영.

## 5단계: 통합 테스트 (End-to-End Test)
**작업 내용**: 실제 Pathfinder를 실행하여 트렌드 데이터가 DB에 쌓이는지 확인합니다.

*   **Command**: `python pathfinder.py --legion 100`
*   **검증**:
    *   로그 확인 및 DB에 `trend_slope` 값이 적재되는지 확인.

---

## 📅 예상 소요 시간 (변경 없음)
*   1~2단계 (DB & Manager분리): 40분
*   3~4단계 (Pathfinder 통합): 50분
*   5단계 (테스트): 30분
*   **총합: 약 2시간**

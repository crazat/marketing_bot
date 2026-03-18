# 🏷️ 진료과목 카테고리 분류 복구 실행 계획 (Category Restoration)

**목표**: `Pathfinder`의 Legion Mode 실행 시 각 키워드가 어떤 진료과목(카테고리)에 속하는지 추적하고 DB에 저장하여, 대시보드에서 12가지 영역별 분석이 가능하게 한다.

---

## 1단계: 데이터베이스 스키마 확장 (DB Update)
**작업 내용**: `keyword_insights` 테이블에 `category` 컬럼을 추가합니다.

*   **Target File**: `scripts/update_db_schema.py`
*   **SQL Command**:
    ```sql
    ALTER TABLE keyword_insights ADD COLUMN category TEXT DEFAULT '기타';
    ```

## 2단계: Pathfinder 카테고리 추적 로직 구현 (Category Tracking)
**작업 내용**: 시드 로딩부터 수집, 저장까지 카테고리 정보를 유지하도록 로직을 재설계합니다.

*   **Target File**: `pathfinder.py`
*   **상세 변경 계획**:
    1.  **`_load_all_seeds()` 수정**:
        *   단순 리스트가 아닌 `[(keyword, category), ...]` 형태의 리스트 반환.
        *   반환 서명 변경에 따른 호출부 수정.
    2.  **`run_campaign_legion()` 수정**:
        *   `self.keyword_category_map = {}` 생성하여 메모리 상에서 `키워드 -> 카테고리` 맵핑 유지.
        *   초기 시드 로딩 시 맵핑 초기화.
        *   **카테고리별 배치 처리**: `_expand_via_ad_api` 호출 시 카테고리별로 그룹핑하여 호출. 즉, 다이어트 시드는 다이어트끼리 모아서 API 호출 -> 결과도 다이어트로 분류.
    3.  **`_select_next_seeds_diverse()` 수정**:
        *   다음 라운드 시드 선정 시, 후보 키워드의 카테고리 정보도 함께 반환.
    4.  **`_parallel_supply_scan()` 및 `_batch_save_to_db()` 수정**:
        *   DB 저장 시 `keyword_category_map`에서 카테고리를 조회하여 `category` 컬럼에 저장.

## 3단계: 통합 프로세스 검증 (Verification)
**작업 내용**: 짧은 테스트 실행으로 카테고리가 제대로 박히는지 확인합니다.

*   **Test Command**: `python pathfinder.py --legion 100` (소량 실행)
*   **Validation**:
    *   DB 조회: `SELECT keyword, category FROM keyword_insights LIMIT 10;`
    *   '기타'가 아닌 '다이어트', '통증' 등이 들어있는지 확인.

---

## 📅 예상 소요 시간
*   1단계 (DB Schema): 10분
*   2단계 (Logic Refactoring): 40분
*   3단계 (Verification): 10분
*   **총합: 1시간**

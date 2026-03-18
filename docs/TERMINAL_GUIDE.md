# 터미널 실행 가이드

이 가이드는 Marketing Bot의 주요 스크립트를 터미널에서 직접 실행하는 방법과 DB 저장을 검증하는 방법을 안내합니다.

---

## 목차

1. [왜 터미널에서 실행하나요?](#왜-터미널에서-실행하나요)
2. [빠른 시작 (3단계)](#빠른-시작-3단계)
3. [페이지별 명령어](#페이지별-명령어)
   - [Pathfinder - 키워드 발굴](#pathfinder---키워드-발굴)
   - [Viral Hunter - 바이럴 콘텐츠 수집](#viral-hunter---바이럴-콘텐츠-수집)
   - [Battle Intelligence - 순위 추적](#battle-intelligence---순위-추적)
   - [Competitor Analysis - 경쟁사 분석](#competitor-analysis---경쟁사-분석)
   - [Lead Manager - 리드 관리](#lead-manager---리드-관리)
4. [DB 검증 명령어](#db-검증-명령어)
5. [실행 후 워크플로우](#실행-후-워크플로우)
6. [문제 해결 (Troubleshooting)](#문제-해결-troubleshooting)

---

## 왜 터미널에서 실행하나요?

### 웹 UI vs 터미널 비교

| 항목 | 웹 UI | 터미널 (권장) |
|------|-------|-------------|
| 실행 방법 | 클릭 한 번 | 명령어 복사 & 붙여넣기 |
| 안정성 | 백그라운드 실행 시 불안정 | ✅ 매우 안정적 |
| 실시간 로그 | 제한적 | ✅ 모든 로그 실시간 확인 |
| DB 저장 검증 | 수동 확인 필요 | ✅ 명령어로 즉시 검증 |
| 에러 디버깅 | 어려움 | ✅ 상세한 에러 메시지 |

**결론**: 장시간 실행되는 작업(Pathfinder LEGION, Viral Hunter 대량 스캔)은 터미널 실행을 강력히 권장합니다.

---

## 빠른 시작 (3단계)

### 1단계: PowerShell 또는 CMD 열기

```powershell
# 프로젝트 디렉토리로 이동
cd C:\Projects\marketing_bot
```

### 2단계: 명령어 실행

웹 UI의 각 페이지에서 "터미널에서 직접 실행하기" 섹션을 펼치고, 원하는 명령어를 복사하여 실행합니다.

예시:
```powershell
python pathfinder_v3_complete.py --save-db
```

### 3단계: DB 저장 확인

스크립트 실행 완료 후 검증 명령어를 실행합니다.

```powershell
python utils/check_db.py --verify-scan pathfinder
```

---

## 페이지별 명령어

### Pathfinder - 키워드 발굴

#### Total War 모드 (빠른 수집)

**실행 시간**: 약 5분
**예상 결과**: 50-100개의 키워드

```powershell
python pathfinder_v3_complete.py --save-db
```

**DB 확인**:
```powershell
python utils/check_db.py --table keyword_insights --since 10
```

**예상 출력**:
```
📊 분포:
  grades:
    S: 5개
    A: 15개
    B: 30개
    C: 20개
```

---

#### LEGION 모드 (대량 수집)

**실행 시간**: 약 15-30분
**예상 결과**: 500개 이상의 키워드

```powershell
python pathfinder_v3_legion.py --target 500 --save-db
```

**DB 확인**:
```powershell
python utils/check_db.py --verify-scan pathfinder
```

**참고사항**:
- 목표 개수(`--target`)에 도달할 때까지 계속 수집합니다.
- 네이버 API 제한으로 인해 실행 시간이 길어질 수 있습니다.
- 중간에 중지하려면 `Ctrl+C`를 누르세요.

---

### Viral Hunter - 바이럴 콘텐츠 수집

**실행 시간**: 약 10-20분
**예상 결과**: 100-500개의 바이럴 타겟

```powershell
python viral_hunter.py --scan
```

**DB 확인**:
```powershell
python utils/check_db.py --table viral_targets --since 15
```

**예상 출력**:
```
📊 분포:
  platforms:
    naver_blog: 150개
    naver_cafe: 120개
    naver_kin: 80개
    instagram: 50개
```

**참고사항**:
- 네이버 블로그, 카페, 지식iN, Instagram에서 잠재고객을 발굴합니다.
- `comment_status`가 `writable`인 항목만 댓글 작성이 가능합니다.

---

### Battle Intelligence - 순위 추적

**실행 시간**: 약 5-10분
**예상 결과**: 키워드별 모바일/데스크탑 순위

```powershell
python scrapers/scraper_naver_place.py
```

**DB 확인**:
```powershell
python utils/check_db.py --table rank_history --latest 10
```

**예상 출력**:
```
📊 분포:
  statuses:
    found: 25개 (순위권 내 발견)
    not_in_results: 5개 (100위권 밖)
    error: 0개
```

**참고사항**:
- 모바일과 데스크탑 순위를 별도로 수집합니다.
- `device_type`: "mobile" 또는 "desktop"
- 순위는 1-100위 내에서만 추적됩니다.

---

### Competitor Analysis - 경쟁사 분석

**실행 시간**: 약 10-15분
**예상 결과**: 경쟁사별 약점 분석 결과

```powershell
python competitor_weakness_analyzer.py
```

**DB 확인**:
```powershell
python utils/check_db.py --table competitor_weaknesses
```

**예상 출력**:
```
📊 분포:
  types:
    service: 15개 (서비스 불만)
    price: 10개 (가격 불만)
    facility: 8개 (시설 불만)
    waiting: 5개 (대기시간 불만)
```

**참고사항**:
- Gemini AI를 사용하여 리뷰에서 약점을 추출합니다.
- `gemini-3-flash-preview` 모델만 사용합니다.

---

### Lead Manager - 리드 관리

**실행 시간**: 약 5-10분
**예상 결과**: 플랫폼별 리드 수집

```powershell
python lead_manager.py
```

**DB 확인**:
```powershell
python utils/check_db.py --table leads
```

**참고사항**:
- 6개 플랫폼(네이버 블로그/카페, YouTube, TikTok, Instagram, 당근마켓)에서 리드를 수집합니다.
- `status`: pending, contacted, replied, converted, rejected

---

## DB 검증 명령어

### 기본 사용법

```powershell
# 테이블 전체 확인
python utils/check_db.py --table <테이블명>

# 최근 N분 이내 데이터만 확인
python utils/check_db.py --table <테이블명> --since 10

# 최근 N개 레코드 확인
python utils/check_db.py --table <테이블명> --latest 20
```

### 주요 테이블

| 테이블명 | 설명 |
|---------|------|
| `keyword_insights` | Pathfinder 키워드 |
| `viral_targets` | Viral Hunter 바이럴 타겟 |
| `rank_history` | Battle Intelligence 순위 기록 |
| `competitor_weaknesses` | 경쟁사 약점 |
| `leads` | 리드 (잠재고객) |
| `scan_runs` | 스캔 실행 기록 |

### 스캔 실행 기록 확인

```powershell
python utils/check_db.py --scan-runs
```

**예상 출력**:
```
모드: total_war
상태: completed
등급: S:5 A:15 B:30 C:20
시작: 2026-02-12 10:00:00
완료: 2026-02-12 10:05:23
```

### 전체 요약

```powershell
python utils/check_db.py --summary
```

**예상 출력**:
```
✓ keyword_insights: 1,234개
✓ viral_targets: 567개
✓ rank_history: 890개
✓ competitor_weaknesses: 123개
✓ leads: 456개
```

---

## 실행 후 워크플로우

### 표준 절차

1. **터미널에서 스크립트 실행**
   ```powershell
   python pathfinder_v3_complete.py --save-db
   ```

2. **실행 완료 확인**
   - 로그에서 `✓ 완료` 메시지 확인
   - 에러 메시지가 없는지 확인

3. **DB 저장 검증**
   ```powershell
   python utils/check_db.py --verify-scan pathfinder
   ```

4. **웹 UI 확인**
   - 브라우저에서 `F5` 새로고침
   - 데이터가 올바르게 표시되는지 확인

5. **필요 시 재실행**
   - 데이터가 부족하면 다시 실행
   - LEGION 모드로 대량 수집

---

## 문제 해결 (Troubleshooting)

### 1. "DB 파일을 찾을 수 없습니다" 오류

**증상**:
```
❌ DB 파일을 찾을 수 없습니다: C:\Projects\marketing_bot\db\marketing_data.db
```

**해결**:
```powershell
# 프로젝트 디렉토리 확인
cd C:\Projects\marketing_bot

# DB 파일 존재 확인
dir db\marketing_data.db
```

---

### 2. "모듈을 찾을 수 없습니다" 오류

**증상**:
```
ModuleNotFoundError: No module named 'colorama'
```

**해결**:
```powershell
# 패키지 설치
pip install colorama

# 또는 전체 의존성 설치
pip install -r requirements.txt
```

---

### 3. "API 키가 설정되지 않았습니다" 오류

**증상**:
```
❌ Gemini API 키가 설정되지 않았습니다
```

**해결**:
```powershell
# .env 파일 확인
type .env

# API 키 설정
echo GEMINI_API_KEY=your_api_key_here >> .env
```

---

### 4. 데이터가 DB에 저장되지 않음

**증상**:
- 스크립트는 정상 실행되었지만 DB에 데이터가 없음

**해결**:
```powershell
# 스크립트 실행 시 --save-db 플래그 확인
python pathfinder_v3_complete.py --save-db  # ✅ 올바름
python pathfinder_v3_complete.py            # ❌ DB에 저장 안 됨

# DB 파일 권한 확인
icacls db\marketing_data.db
```

---

### 5. 웹 UI에서 데이터가 보이지 않음

**증상**:
- DB에는 데이터가 있지만 웹 UI에서 표시되지 않음

**해결**:
```powershell
# 1. 브라우저 캐시 삭제
# Ctrl+Shift+R (하드 새로고침)

# 2. 백엔드 서버 재시작
build_and_run.bat

# 3. DB 무결성 검사
python utils/check_db.py --summary
```

---

### 6. "너무 많은 요청" 오류 (Rate Limit)

**증상**:
```
❌ Naver API Rate Limit Exceeded
```

**해결**:
```powershell
# 잠시 대기 후 재실행 (5-10분)
timeout /t 300

# 또는 요청 간격 조정
python pathfinder_v3_legion.py --target 100 --delay 2
```

---

## 추가 팁

### 1. 로그 파일 저장

실행 로그를 파일로 저장하려면:

```powershell
python pathfinder_v3_complete.py --save-db > pathfinder_log.txt 2>&1
```

### 2. 백그라운드 실행 (Windows)

터미널을 닫아도 계속 실행하려면:

```powershell
start /B python pathfinder_v3_legion.py --target 500 --save-db
```

### 3. 자동 백업

DB 백업 자동화:

```powershell
# 관리자 권한으로 실행
setup_backup_scheduler.bat
```

---

## 요약

1. **터미널 실행이 더 안정적**입니다. 특히 장시간 작업에서는 필수입니다.
2. **DB 검증 명령어**로 저장 여부를 즉시 확인할 수 있습니다.
3. **웹 UI는 결과 확인용**으로 사용하고, 실제 수집은 터미널에서 하세요.
4. **문제 발생 시** 이 가이드의 Troubleshooting 섹션을 참고하세요.

---

**문의**: 문제가 해결되지 않으면 GitHub Issues에 보고해주세요.

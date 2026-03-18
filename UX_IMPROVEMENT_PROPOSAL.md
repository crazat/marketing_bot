# 사용자 경험(UX) 개선 제안서

> 작성일: 2026-02-25
> 분석 범위: 프론트엔드 전체 + 백엔드 API 331개 엔드포인트

---

## 목차
1. [현황 요약](#현황-요약)
2. [프론트엔드 개선 사항](#프론트엔드-개선-사항)
3. [백엔드 API 개선 사항](#백엔드-api-개선-사항)
4. [개선 우선순위 및 로드맵](#개선-우선순위-및-로드맵)

---

## 현황 요약

### 전체 UX 완성도

| 영역 | 현재 상태 | 완성도 | 우선 개선 필요 |
|------|----------|--------|--------------|
| 로딩 상태 처리 | 좋음 | 85% | 일부 페이지 통합 필요 |
| 에러 상태 처리 | 부분적 | 60% | **즉시 개선** |
| 빈 상태 처리 | 부분적 | 70% | 안내 메시지 강화 |
| 폼 유효성 검사 | 좋음 | 80% | 일부 폼 미적용 |
| 사용자 피드백 | 부분적 | 65% | **자동 저장 피드백** |
| 키보드 접근성 | 좋음 | 75% | 드롭다운/날짜 선택기 |
| 반응형 디자인 | 부분적 | 70% | **태블릿 최적화** |
| API 응답 일관성 | 우수 | 90% | 유지 |
| 페이지네이션 | 불일관 | 65% | **파라미터 통일** |
| 실시간 진행률 | 미구현 | 0% | **WebSocket 활성화** |

---

## 프론트엔드 개선 사항

### 1. 에러 상태 처리 일관화 🔴 Critical

**문제**: API 오류 시 일부 페이지에서 toast만 표시하거나 아무 UI도 없음

**영향받는 파일**:
- `LeadTable.tsx` - API 오류 시 빈 화면
- `ViralHunter.tsx` - 스캔 실패 시 console.error만
- `Pathfinder.tsx` - 키워드 수집 오류 처리 미흡
- `BattleIntelligence.tsx` - 순위 스캔 실패 UI 없음
- `CompetitorAnalysis.tsx` - 약점 분석 오류 메시지 없음

**개선 방안**:
```tsx
// Before (현재 패턴)
const { data, isLoading, error } = useQuery(...)
if (error) {
  toast.error('데이터 로드 실패')
  return null // 아무것도 표시 안함
}

// After (권장 패턴)
if (error) {
  return (
    <ErrorState
      error={error}
      onRetry={() => refetch()}
      showRetry
      actions={[
        { label: '다시 시도', onClick: () => refetch() }
      ]}
    />
  )
}
```

---

### 2. 자동 저장 피드백 추가 🔴 Critical

**문제**: `LeadNoteEditor` 등에서 자동 저장 시 사용자에게 피드백 없음

**개선 방안**:
```tsx
const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle')

const handleNoteChange = (text: string) => {
  setNote(text)
  setSaveStatus('saving')

  updateNoteMutation.mutate(text, {
    onSuccess: () => {
      setSaveStatus('saved')
      setTimeout(() => setSaveStatus('idle'), 2000)
    },
    onError: () => {
      setSaveStatus('idle')
      toast.error('저장 실패')
    }
  })
}

// UI
<div className="relative">
  <Textarea value={note} onChange={(e) => handleNoteChange(e.target.value)} />
  <div className="absolute top-2 right-2 text-xs text-muted-foreground">
    {saveStatus === 'saving' && <span className="animate-pulse">저장 중...</span>}
    {saveStatus === 'saved' && <span className="text-green-500">✓ 저장됨</span>}
  </div>
</div>
```

---

### 3. 빈 상태 안내 강화 🟠 High

**문제**: 데이터가 없을 때 다음 행동을 안내하지 않음

**개선이 필요한 페이지**:

| 페이지 | 현재 상태 | 개선 방안 |
|--------|----------|----------|
| Pathfinder 분석 결과 | 아무 UI 없음 | "키워드를 발굴하세요" + 시작 버튼 |
| CompetitorAnalysis 경쟁사 | 추가 안내 없음 | "경쟁사를 등록하세요" + 등록 버튼 |
| BattleIntelligence 순위 | 스캔 권장 없음 | "첫 스캔을 시작하세요" + 스캔 버튼 |

**통일된 패턴**:
```tsx
<EmptyState
  type="initial"
  title="분석 결과가 없습니다"
  description="먼저 데이터를 수집하세요"
  suggestion="Pathfinder에서 키워드를 발굴해보세요"
  actions={[
    {
      label: '키워드 발굴 시작',
      onClick: () => navigate('/pathfinder'),
      variant: 'primary'
    }
  ]}
/>
```

---

### 4. 폼 유효성 검사 확대 🟠 High

**검증이 누락된 폼**:
- `CompetitorAnalysis` - 목표 순위 입력 (숫자 형식)
- `ViralHunter` - 날짜 범위 (startDate > endDate 체크)
- `Settings` - API 키 입력 (형식 검증 + 테스트)
- `ConversionModal` - 금액 입력 (숫자, 범위)

**useFormValidation 활용**:
```tsx
const form = useFormValidation({
  targetRank: {
    required: '목표 순위 필수',
    min: { value: 1, message: '1 이상' },
    max: { value: 100, message: '100 이하' }
  },
  dateRange: {
    custom: (value) => {
      if (value.start > value.end) return '시작일이 종료일보다 늦습니다'
      return null
    }
  }
})
```

---

### 5. 태블릿 반응형 최적화 🟠 High

**문제가 있는 컴포넌트**:

| 컴포넌트 | 모바일 | 태블릿 | 데스크톱 | 문제 |
|---------|--------|--------|---------|------|
| Pathfinder 클러스터 | ❌ 가로 스크롤 | ⚠️ 가로 스크롤 | ✅ 그리드 | 모바일 사용성 낮음 |
| Settings 사이드바 | ✅ 탭 스택 | ⚠️ 1열 사이드바 | ✅ 완전 | 태블릿 비효율 |
| Modal | ✅ 전체 너비 | ⚠️ 너무 큼 | ✅ 제한 | 태블릿에서 과도 |
| Layout 사이드바 | ❌ 햄버거만 | ⚠️ 축소 | ✅ 완전 | 태블릿 네비게이션 불편 |

**개선 방안**:
```tsx
// Pathfinder 클러스터
// Before
<div className="overflow-x-auto">
  <div className="inline-flex gap-4">...</div>
</div>

// After
<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
  ...
</div>

// Modal 크기
// Before
<div className="max-w-md">

// After
<div className="max-w-sm md:max-w-md lg:max-w-lg">
```

---

### 6. 로딩 상태 통합 🟡 Medium

**useLoadingState 미사용 페이지**:
- `LeadTable.tsx`
- `ViralHunter.tsx`
- `CompetitorAnalysis.tsx`

**통합 방안**:
```tsx
const { isInitialLoad, isRefreshing } = useLoadingState(query)

if (isInitialLoad) {
  return <LoadingSpinner size="lg" text="데이터를 불러오는 중..." />
}

// 데이터 새로고침 중에는 오버레이
{isRefreshing && <RefreshingIndicator />}
```

---

### 7. 키보드 접근성 개선 🟡 Medium

**개선이 필요한 컴포넌트**:

| 컴포넌트 | 문제 | 해결 |
|---------|------|------|
| ResponsiveDataView 체크박스 | aria-label 없음 | `aria-label="행 선택"` 추가 |
| Pagination 버튼 | aria-label 없음 | `aria-label="이전 페이지"` 추가 |
| BulkActions 드롭다운 | 키보드 네비게이션 없음 | Arrow 키 지원 추가 |
| 날짜 선택기 | 키보드 미지원 | react-datepicker 설정 활성화 |

---

## 백엔드 API 개선 사항

### 1. 외부 API 타임아웃 설정 🔴 Critical

**문제**: 대부분의 외부 API 호출에 타임아웃 미설정 (무한 대기 가능)

**영향받는 API**:
- Naver API 호출
- Instagram API 호출
- 경쟁사 리뷰 수집

**개선 방안**:
```python
# config/app_settings.py에 추가
self.api_timeout_external: int = self._get_int('API_TIMEOUT_EXTERNAL', 10)
self.api_timeout_scraping: int = self._get_int('API_TIMEOUT_SCRAPING', 300)
self.api_timeout_analysis: int = self._get_int('API_TIMEOUT_ANALYSIS', 120)

# 모든 외부 호출에 적용
import requests
from config.app_settings import get_settings
settings = get_settings()

response = requests.get(url, timeout=settings.api_timeout_external)
```

---

### 2. 페이지네이션 파라미터 통일 🔴 Critical

**현재 불일치**:
```python
# agent.py - offset/limit
async def get_actions_log(limit: int = 50, offset: int = 0)

# analytics.py - page/page_size
async def get_keyword_lifecycle(page: int = 1, page_size: int = 50)
```

**통일 기준**:
```python
# 모든 API에 적용할 표준
from fastapi import Query

async def list_items(
    offset: int = Query(default=0, ge=0, description="건너뛸 항목 수"),
    limit: int = Query(default=20, ge=1, le=100, description="조회할 항목 수"),
    sort_by: str = Query(default="created_at", description="정렬 기준"),
    order: str = Query(default="desc", regex="^(asc|desc)$", description="정렬 방향"),
):
    ...
```

---

### 3. 에러 메시지 시스템 활성화 🟠 High

**문제**: `AppError` 클래스가 정의되어 있지만 거의 사용되지 않음

**현재**:
```python
raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")
```

**개선**:
```python
from backend_utils.error_handlers import DatabaseError, ExternalAPIError

try:
    result = db_query()
except Exception as e:
    raise DatabaseError(f"조회 실패: {e}")  # 자동으로 힌트 메시지 포함
```

---

### 4. 정렬 파라미터 추가 🟠 High

**현재 문제**: ORDER BY가 하드코딩되어 사용자 정렬 불가

**개선 방안**:
```python
from fastapi import Query

ALLOWED_SORT_COLUMNS = {
    "leads": ["created_at", "score", "status", "keyword"],
    "keywords": ["created_at", "grade", "search_volume"],
    "viral_targets": ["discovered_at", "priority_score", "platform"]
}

async def get_leads(
    sort_by: str = Query(
        default="created_at",
        description="정렬 기준 컬럼"
    ),
    order: str = Query(
        default="desc",
        regex="^(asc|desc)$",
        description="정렬 방향"
    )
):
    if sort_by not in ALLOWED_SORT_COLUMNS["leads"]:
        raise HTTPException(400, f"허용되지 않는 정렬 기준: {sort_by}")

    query = f"SELECT * FROM leads ORDER BY {sort_by} {order.upper()}"
```

---

### 5. 실시간 진행률 구현 🟡 Medium

**현재**: WebSocketManager가 구현되어 있지만 미사용

**활용 방안 1: WebSocket 연결**:
```python
# routers/websocket.py
from fastapi import WebSocket
from services.websocket_manager import manager

@router.websocket("/ws/scan/{scan_id}")
async def websocket_scan_progress(websocket: WebSocket, scan_id: str):
    await manager.connect(websocket)
    try:
        while True:
            progress = await get_scan_progress(scan_id)
            await websocket.send_json(progress)
            if progress["status"] == "completed":
                break
            await asyncio.sleep(1)
    finally:
        manager.disconnect(websocket)
```

**활용 방안 2: SSE (더 간단)**:
```python
from fastapi.responses import StreamingResponse

@router.get("/scan/{scan_id}/progress")
async def stream_scan_progress(scan_id: str):
    async def event_generator():
        while True:
            progress = await get_scan_progress(scan_id)
            yield f"data: {json.dumps(progress)}\n\n"
            if progress["status"] == "completed":
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

---

## 개선 우선순위 및 로드맵

### Phase 1: 즉시 개선 (1-2일) 🔴

| 항목 | 파일 | 예상 시간 |
|------|------|----------|
| 에러 상태 일관화 | LeadTable, ViralHunter, Pathfinder 등 5개 | 4시간 |
| 자동 저장 피드백 | LeadNoteEditor | 1시간 |
| 외부 API 타임아웃 | 모든 requests/aiohttp 호출 | 2시간 |
| limit 최대값 제한 | 모든 페이지네이션 API | 1시간 |

### Phase 2: 1주일 내 개선 🟠

| 항목 | 파일 | 예상 시간 |
|------|------|----------|
| 빈 상태 안내 강화 | 5개 페이지 | 3시간 |
| 폼 유효성 검사 확대 | 4개 폼 | 3시간 |
| 페이지네이션 통일 | 15개+ API | 4시간 |
| 정렬 파라미터 추가 | 10개+ API | 3시간 |
| 에러 메시지 시스템 활성화 | 모든 라우터 | 4시간 |

### Phase 3: 2주일 내 개선 🟡

| 항목 | 파일 | 예상 시간 |
|------|------|----------|
| 태블릿 반응형 최적화 | 5개 컴포넌트 | 6시간 |
| 로딩 상태 통합 | 3개 페이지 | 2시간 |
| 키보드 접근성 개선 | 4개 컴포넌트 | 4시간 |
| WebSocket/SSE 진행률 | 스캔/분석 API | 8시간 |

---

## 체크리스트

### 프론트엔드
- [ ] 모든 API 호출에 ErrorState 적용
- [ ] 자동 저장 필드에 저장 상태 표시
- [ ] 빈 상태에 다음 행동 안내 추가
- [ ] 모든 폼에 useFormValidation 적용
- [ ] Pathfinder 클러스터 그리드 레이아웃
- [ ] Settings 사이드바 태블릿 최적화
- [ ] Modal 반응형 크기 조정
- [ ] 체크박스/버튼 aria-label 추가
- [ ] 드롭다운 키보드 네비게이션

### 백엔드
- [ ] 모든 외부 API 호출 타임아웃 설정
- [ ] 페이지네이션 offset/limit 통일
- [ ] limit 최대값 100 제한
- [ ] 정렬 파라미터 (sort_by, order) 추가
- [ ] AppError 기반 에러 메시지 통일
- [ ] 장시간 작업 진행률 API 구현

---

## 참고 파일 경로

### 핵심 UI 컴포넌트
- `frontend/src/components/ui/LoadingSpinner.tsx`
- `frontend/src/components/ui/ErrorState.tsx`
- `frontend/src/components/ui/EmptyState.tsx`
- `frontend/src/components/ui/Toast.tsx`

### 커스텀 훅
- `frontend/src/hooks/useFormValidation.ts`
- `frontend/src/hooks/useLoadingState.ts`
- `frontend/src/hooks/useResponsiveView.ts`

### 개선 필요 페이지
- `frontend/src/pages/LeadManager.tsx`
- `frontend/src/pages/Pathfinder.tsx`
- `frontend/src/pages/ViralHunter.tsx`
- `frontend/src/pages/BattleIntelligence.tsx`
- `frontend/src/pages/CompetitorAnalysis.tsx`

### 백엔드 설정
- `backend/backend_utils/error_handlers.py`
- `backend/services/websocket_manager.py`
- `config/app_settings.py`

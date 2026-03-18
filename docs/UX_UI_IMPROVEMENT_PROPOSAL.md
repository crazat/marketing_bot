# Marketing Bot UX/UI 개선 제안서

**작성일**: 2026-02-09
**기반 문서**: UX_UI_ANALYSIS_REPORT.md

---

## 개선 원칙

1. **점진적 개선**: 기존 기능 유지하면서 단계적 적용
2. **사용자 중심**: 실제 사용 패턴 기반 우선순위
3. **최소 변경 최대 효과**: 작은 수정으로 큰 개선 달성
4. **측정 가능**: 개선 전후 비교 가능한 지표

---

## Phase 1: Quick Wins (1-2일)

### 1.1 Dashboard 정보 계층 재구성

**현재 문제**: 10개 이상 섹션이 동등하게 나열

**개선안**:
```
[Before]
├── 메트릭 카드
├── 브리핑
├── 알림
├── 타임라인
├── Hot Lead
├── Funnel
├── ROI
├── Actions
├── Report
└── 활동 로그

[After]
├── [최상단] 오늘의 핵심 (1줄 요약)
│   "오늘 처리할 리드 12건, 스캔 예정 3개"
│
├── [섹션 1] 즉시 대응 필요
│   ├── Hot Lead 배너 (있을 때만)
│   └── Sentinel 알림 (Critical만)
│
├── [섹션 2] 핵심 메트릭 (4개)
│
├── [접이식] 상세 정보
│   ├── 브리핑
│   ├── 타임라인
│   └── 활동 로그
│
└── [하단] 분석 (선택 조회)
    ├── Funnel
    ├── ROI
    └── Report
```

**구현 방법**:
- 기존 Collapsible 컴포넌트 활용
- "오늘의 핵심" 요약 문구 API 추가
- 섹션 기본 접힘 상태 조정

**예상 효과**: 초기 로딩 시 핵심 정보만 표시, 스크롤 감소

---

### 1.2 빈 상태 개선 - 다음 단계 안내

**현재 문제**: "데이터가 없습니다"만 표시

**개선안**:

```tsx
// 현재
<EmptyState
  icon="📊"
  title="리드가 없습니다"
/>

// 개선
<EmptyState
  icon="📊"
  title="맘카페 리드가 없습니다"
  description="맘카페 스캔을 실행하여 잠재 고객을 발굴하세요"
  primaryAction={{
    label: "스캔 시작",
    onClick: () => handleScan('cafe')
  }}
  secondaryAction={{
    label: "다른 플랫폼 보기",
    onClick: () => setActiveTab('youtube')
  }}
/>
```

**수정 대상**:
- LeadManager: 각 플랫폼별 빈 상태
- Pathfinder: 키워드 없을 때
- Viral Hunter: 타겟 없을 때
- Battle: 순위 데이터 없을 때

**예상 효과**: 사용자가 다음 행동을 명확히 인지

---

### 1.3 필터 상태 시각화

**현재 문제**: 어떤 필터가 적용되었는지 불명확

**개선안**:
```tsx
// 필터 적용 시 상단에 칩 표시
<div className="flex gap-2 mb-4">
  {statusFilter && (
    <Chip onRemove={() => setStatusFilter('')}>
      상태: {statusFilter}
    </Chip>
  )}
  {trustFilter && (
    <Chip onRemove={() => setTrustFilter('')}>
      신뢰도: {trustFilter}
    </Chip>
  )}
  {(statusFilter || trustFilter) && (
    <Button variant="ghost" onClick={clearAllFilters}>
      모두 초기화
    </Button>
  )}
</div>
```

**예상 효과**: 필터 상태 한눈에 파악, 쉬운 초기화

---

### 1.4 아이콘 호버 툴팁 추가

**현재 문제**: 이모지 의미 불명확

**개선안**:
```tsx
// 현재
<span>🎯</span>

// 개선
<Tooltip content="기회 점수가 높은 리드입니다">
  <span>🎯</span>
</Tooltip>
```

**적용 대상**:
- LeadCard: 모든 배지 (신뢰도, 기회, 참여신호)
- ViralTargetCard: 우선순위 점수
- RankingKeywordsList: 상태 아이콘

**예상 효과**: 아이콘 의미 즉시 이해

---

## Phase 2: 워크플로우 개선 (3-5일)

### 2.1 권장 워크플로우 가이드

**새 컴포넌트**: `WorkflowGuide.tsx`

```tsx
// Dashboard 상단에 추가
<WorkflowGuide
  steps={[
    {
      label: "순위 확인",
      page: "/battle",
      status: lastScan < 24h ? 'done' : 'pending',
      tooltip: "마지막 스캔: 2시간 전"
    },
    {
      label: "키워드 수집",
      page: "/pathfinder",
      status: 'done'
    },
    {
      label: "타겟 처리",
      page: "/viral",
      status: pendingTargets > 0 ? 'action' : 'done',
      badge: pendingTargets
    },
    {
      label: "리드 관리",
      page: "/leads",
      status: newLeads > 0 ? 'action' : 'done',
      badge: newLeads
    },
  ]}
/>
```

**UI 디자인**:
```
[✓ 순위 확인] → [✓ 키워드 수집] → [! 타겟 처리 (5)] → [• 리드 관리]
```

**예상 효과**: 일일 워크플로우 명확화, 다음 단계 자동 안내

---

### 2.2 글로벌 검색 추가

**새 컴포넌트**: `GlobalSearch.tsx`

```tsx
// Layout.tsx 헤더에 추가
<GlobalSearch
  placeholder="키워드, 리드, 경쟁사 검색..."
  onSearch={handleGlobalSearch}
  shortcuts={[
    { key: 'k', modifier: 'cmd', action: 'focus' }
  ]}
  results={[
    { type: 'keyword', title: '청주 한의원', page: '/pathfinder?search=...' },
    { type: 'lead', title: '김XX님', page: '/leads?id=...' },
    { type: 'page', title: 'Battle Intelligence', page: '/battle' },
  ]}
/>
```

**기능**:
- `Cmd/Ctrl + K`로 포커스
- 키워드, 리드, 페이지 통합 검색
- 최근 검색어 저장

**예상 효과**: 원하는 정보 빠른 접근

---

### 2.3 키보드 단축키 시스템

**새 훅**: `useKeyboardShortcuts.ts`

```tsx
// 전역 단축키
useKeyboardShortcuts({
  'g d': () => navigate('/'),           // Go to Dashboard
  'g p': () => navigate('/pathfinder'), // Go to Pathfinder
  'g v': () => navigate('/viral'),      // Go to Viral
  'g b': () => navigate('/battle'),     // Go to Battle
  'g l': () => navigate('/leads'),      // Go to Leads
  '?': () => setShowShortcutsModal(true), // Show shortcuts
  'r': () => refetch(),                 // Refresh current
})

// 페이지별 단축키
// Battle Intelligence
useKeyboardShortcuts({
  's': () => startScan(),  // Start scan
  'n': () => addKeyword(), // New keyword
})
```

**단축키 도움말 모달**:
```
┌─────────────────────────────────┐
│ 키보드 단축키                    │
├─────────────────────────────────┤
│ 네비게이션                       │
│ g d    Dashboard 이동            │
│ g p    Pathfinder 이동           │
│ g b    Battle 이동               │
│                                  │
│ 액션                             │
│ s      스캔 시작                 │
│ r      새로고침                  │
│ n      새 항목 추가              │
│                                  │
│ ?      이 도움말 표시            │
└─────────────────────────────────┘
```

**예상 효과**: 파워 유저 생산성 향상

---

### 2.4 리드 상세 모달

**현재 문제**: 리드 정보가 카드에 압축되어 있음

**새 컴포넌트**: `LeadDetailModal.tsx`

```tsx
<LeadDetailModal
  lead={selectedLead}
  onClose={() => setSelectedLead(null)}
>
  {/* 탭 구조 */}
  <Tabs>
    <Tab label="기본 정보">
      - 제목, 내용 전문
      - 작성자, 작성일
      - 원본 링크
    </Tab>
    <Tab label="분석">
      - 점수 breakdown (source, relevance, freshness, engagement)
      - 신뢰도 이유
      - 참여 신호
    </Tab>
    <Tab label="히스토리">
      - 상태 변경 이력
      - 노트
      - 관련 활동
    </Tab>
  </Tabs>

  {/* 하단 액션 */}
  <Actions>
    <Button>상태 변경</Button>
    <Button>노트 추가</Button>
    <Button>원본 보기</Button>
  </Actions>
</LeadDetailModal>
```

**예상 효과**: 리드 정보 완전 파악, 컨텍스트 스위칭 감소

---

## Phase 3: 온보딩 시스템 (5-7일)

### 3.1 첫 사용자 튜토리얼

**새 컴포넌트**: `OnboardingTour.tsx`

```tsx
<OnboardingTour
  steps={[
    {
      target: '#sidebar-dashboard',
      title: '대시보드',
      content: '모든 핵심 지표를 한눈에 확인하세요',
      placement: 'right'
    },
    {
      target: '#sidebar-battle',
      title: '순위 추적',
      content: '네이버 플레이스 순위를 실시간으로 모니터링합니다',
      placement: 'right'
    },
    {
      target: '#sidebar-pathfinder',
      title: '키워드 발굴',
      content: 'AI가 새로운 마케팅 키워드를 찾아냅니다',
      placement: 'right'
    },
    // ...
  ]}
  onComplete={() => markOnboardingComplete()}
/>
```

**트리거 조건**:
- 첫 로그인 시 자동 시작
- localStorage에 완료 상태 저장
- Settings에서 다시 보기 가능

### 3.2 기능별 힌트 시스템

**새 컴포넌트**: `FeatureHint.tsx`

```tsx
// 처음 해당 기능 사용 시 표시
<FeatureHint
  id="kanban-view"
  title="칸반 보드를 사용해보세요"
  content="리드를 드래그하여 상태를 쉽게 변경할 수 있습니다"
  trigger="first-visit"
>
  <ViewModeToggle />
</FeatureHint>
```

**표시 조건**:
- 해당 페이지 첫 방문
- 기능 미사용 3일 이상
- 한 번 닫으면 다시 안 나옴

### 3.3 빈 대시보드 시작 가이드

**현재 문제**: 데이터 없을 때 무엇을 해야 할지 모름

**개선안**:
```tsx
// Dashboard.tsx - 데이터 없을 때
{isEmpty && (
  <StartGuide>
    <h2>Marketing Bot 시작하기</h2>

    <Step number={1} status="pending">
      <StepTitle>키워드 설정</StepTitle>
      <StepDesc>추적할 키워드를 등록하세요</StepDesc>
      <Button onClick={() => navigate('/battle')}>
        키워드 추가
      </Button>
    </Step>

    <Step number={2} status="locked">
      <StepTitle>첫 스캔 실행</StepTitle>
      <StepDesc>네이버 플레이스 순위를 확인합니다</StepDesc>
    </Step>

    <Step number={3} status="locked">
      <StepTitle>리드 수집</StepTitle>
      <StepDesc>잠재 고객을 자동으로 발굴합니다</StepDesc>
    </Step>
  </StartGuide>
)}
```

---

## Phase 4: 접근성 완전 지원 (3-5일)

### 4.1 칸반 키보드 지원

**개선 방법**:
```tsx
// KanbanColumn.tsx
<div
  role="listbox"
  aria-label={`${status} 상태 리드 목록`}
  onKeyDown={(e) => {
    if (e.key === 'ArrowRight') moveLead(lead, nextStatus);
    if (e.key === 'ArrowLeft') moveLead(lead, prevStatus);
    if (e.key === 'ArrowUp') focusPrevLead();
    if (e.key === 'ArrowDown') focusNextLead();
  }}
>
```

**키보드 조작**:
- `←/→`: 상태 이동
- `↑/↓`: 리드 간 이동
- `Enter`: 상세 보기
- `Space`: 선택

### 4.2 차트 대체 텍스트

**개선 방법**:
```tsx
// RankingTrends.tsx
<div role="img" aria-label={generateChartDescription(data)}>
  <Chart data={data} />
</div>

// 또는 데이터 테이블 제공
<details>
  <summary>데이터 테이블로 보기</summary>
  <table>
    {data.map(row => (
      <tr>
        <td>{row.date}</td>
        <td>{row.rank}</td>
      </tr>
    ))}
  </table>
</details>
```

### 4.3 ARIA 레이블 보완

**체크리스트**:
```tsx
// 모든 아이콘 버튼
<button aria-label="설정 열기">
  <SettingsIcon />
</button>

// 상태 변경 컨트롤
<select aria-label="리드 상태 선택">

// 로딩 상태
<div aria-busy="true" aria-live="polite">
  로딩 중...
</div>

// 에러 알림
<div role="alert" aria-live="assertive">
  오류가 발생했습니다
</div>
```

---

## 우선순위 및 일정

### 즉시 적용 (Phase 1) - 1-2일

| 항목 | 난이도 | 영향도 | 우선순위 |
|------|--------|--------|---------|
| 빈 상태 다음 단계 안내 | 낮음 | 높음 | **P0** |
| 필터 상태 시각화 | 낮음 | 중간 | **P0** |
| 아이콘 툴팁 추가 | 낮음 | 중간 | **P1** |
| Dashboard 섹션 재구성 | 중간 | 높음 | **P1** |

### 단기 개선 (Phase 2) - 3-5일

| 항목 | 난이도 | 영향도 | 우선순위 |
|------|--------|--------|---------|
| 권장 워크플로우 가이드 | 중간 | 높음 | **P1** |
| 리드 상세 모달 | 중간 | 중간 | **P2** |
| 글로벌 검색 | 높음 | 높음 | **P2** |
| 키보드 단축키 | 중간 | 낮음 | **P3** |

### 중기 개선 (Phase 3-4) - 5-10일

| 항목 | 난이도 | 영향도 | 우선순위 |
|------|--------|--------|---------|
| 온보딩 튜토리얼 | 높음 | 높음 | **P2** |
| 칸반 키보드 지원 | 중간 | 낮음 | **P3** |
| 차트 접근성 | 중간 | 낮음 | **P3** |

---

## 성과 측정 방법

### 정량 지표

| 지표 | 현재 (추정) | 목표 |
|------|------------|------|
| 첫 스캔까지 시간 | 10분+ | 3분 |
| 일일 활성 기능 사용률 | 40% | 70% |
| 리드 처리 완료율 | 60% | 80% |
| 에러 후 이탈률 | 높음 | 낮음 |

### 정성 지표

- 사용자 피드백 수집 (인앱 설문)
- 기능 발견 테스트 (5초 테스트)
- 워크플로우 완료 추적

---

## 결론

### 즉시 실행 권장 (P0)

1. **빈 상태 개선**: EmptyState 컴포넌트에 `primaryAction` 추가
2. **필터 칩 표시**: 적용된 필터를 상단에 칩으로 표시

### 다음 스프린트 권장 (P1)

1. **Dashboard 재구성**: 정보 계층화, 접이식 섹션
2. **워크플로우 가이드**: 일일 작업 흐름 시각화
3. **아이콘 툴팁**: 모든 배지에 설명 추가

### 장기 로드맵 (P2-P3)

1. 온보딩 시스템 구축
2. 글로벌 검색 구현
3. 완전한 접근성 지원

---

*이 제안서는 UX_UI_ANALYSIS_REPORT.md의 분석 결과를 기반으로 작성되었습니다.*

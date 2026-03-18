# Marketing Bot UI 통합 전략 보고서

## 작성일: 2026-02-09
## 목적: 모든 기능의 유기적 연결 및 사용자 주도 마케팅 워크플로우 설계

---

## 1. 현황 분석

### 1.1 시스템 구조
| 구분 | 수량 | 주요 항목 |
|------|------|----------|
| 백엔드 라우터 | 16개 | hud, pathfinder, battle, leads, viral, competitors, instagram, reviews, agent, qa, notifications, preferences, config, backup, export |
| 프론트엔드 페이지 | 9개 | Dashboard, Pathfinder, ViralHunter, BattleIntelligence, LeadManager, CompetitorAnalysis, AIAgent, Settings |
| 데이터베이스 테이블 | 43개 | keyword_insights, rank_history, viral_targets, leads, competitor_reviews 등 |
| API 엔드포인트 | 120+개 | CRUD + 분석 + AI 생성 기능 |

### 1.2 핵심 문제점

```
문제 1: 사일로화된 페이지
├── 각 페이지가 독립적으로 작동
├── 데이터 흐름이 페이지 간에 단절
└── 사용자가 전체 마케팅 퍼널을 파악하기 어려움

문제 2: 미사용 API 다수 존재
├── hudApi.getRecommendedKeywords() - 미사용
├── hudApi.getSuggestedActions() - 미사용
├── pathfinderApi.getContentCalendar() - 미사용
├── competitorsApi.getContentGap() - 미사용
└── qaApi 전체 - 미사용

문제 3: 자동화 vs 사용자 제어 불균형
├── 스캔/분석은 사용자 트리거
├── 결과 활용은 수동으로 복사/이동 필요
└── "다음 단계로 보내기" 기능 부재
```

---

## 2. 마케팅 퍼널 데이터 흐름

### 2.1 이상적인 5단계 퍼널

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        마케팅 파이프라인 흐름                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [1. 발견]      [2. 추적]      [3. 콘텐츠]     [4. 유입]      [5. 전환]   │
│  Discovery     Tracking      Content       Acquisition   Conversion    │
│      │            │             │              │             │          │
│      ▼            ▼             ▼              ▼             ▼          │
│  Pathfinder    Battle        Viral         Leads        Revenue       │
│  Competitors   Intelligence  Hunter        Manager      Tracking      │
│      │            │             │              │             │          │
│      └────────────┴─────────────┴──────────────┴─────────────┘          │
│                                                                         │
│  keyword_      rank_         viral_        leads         conversion_   │
│  insights      history       targets       contact_      records       │
│                              posted_       history                      │
│                              comments                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 현재 데이터 연결 상태

| 연결 | 상태 | 문제점 |
|------|------|--------|
| Pathfinder → Battle | ❌ 단절 | 키워드 발굴 후 순위 추적 별도 등록 필요 |
| Battle → Viral | ❌ 단절 | 순위 하락 키워드로 바이럴 찾기 불가 |
| Viral → Leads | ⚠️ 약함 | 댓글 게시 후 리드 전환 추적 미흡 |
| Competitors → Content | ❌ 단절 | 약점 분석 후 콘텐츠 제작 연결 없음 |
| Leads → Conversion | ✅ 구현됨 | ConversionModal로 전환 기록 가능 |

---

## 3. 사용자 주도 워크플로우 설계

### 3.1 핵심 원칙

```
자동 실행 (X)  →  추천 → 확인 → 실행 (O)
─────────────────────────────────────────
시스템이 자동으로    시스템이 추천하고
모든 것을 처리      사용자가 승인/실행
```

### 3.2 워크플로우 1: 키워드 → 순위 추적

```
[Pathfinder 페이지]
    │
    │ S등급 키워드 발굴: "청주 다이어트 한약"
    │
    ▼
┌─────────────────────────────────────────────┐
│ 💡 이 키워드를 순위 추적에 추가하시겠습니까?    │
│                                             │
│   키워드: 청주 다이어트 한약                   │
│   예상 검색량: 2,400                         │
│   현재 순위: 미확인                           │
│   경쟁 강도: 중간                            │
│                                             │
│   [순위 추적 추가]  [나중에]  [관심없음]        │
└─────────────────────────────────────────────┘
    │
    │ 사용자 클릭: [순위 추적 추가]
    │
    ▼
[Battle Intelligence]
    키워드 목록에 추가됨
    → 다음 스캔 시 순위 확인 예정
```

**구현 방법:**
- `KeywordCard` 컴포넌트에 "순위 추적 시작" 버튼 추가
- 클릭 시 `battleApi.addRankingKeyword(keyword, target_rank)` 호출
- S/A등급 키워드에 `🎯 추적 권장` 배지 표시

### 3.3 워크플로우 2: 바이럴 댓글 → 리드 생성

```
[Viral Hunter 페이지]
    │
    │ 댓글 게시 완료
    │   플랫폼: 네이버 카페
    │   게시물: "청주 한의원 추천해주세요"
    │   내 댓글: "규림한의원 다녀왔는데..."
    │
    ▼
┌─────────────────────────────────────────────┐
│ 💡 이 댓글의 응답을 추적하시겠습니까?          │
│                                             │
│   댓글 작성자가 답글을 달면 알림을 받고        │
│   잠재 고객으로 관리할 수 있습니다.            │
│                                             │
│   [리드 생성 & 추적]  [댓글만 기록]  [건너뛰기]  │
└─────────────────────────────────────────────┘
    │
    │ 사용자 클릭: [리드 생성 & 추적]
    │
    ▼
[Lead Manager]
    새 리드 자동 생성
    - 플랫폼: 네이버
    - 상태: 댓글 응답 대기
    - 출처: 바이럴 댓글 #123
```

**구현 방법:**
- `viralApi.postComment()` 호출 후 모달 표시
- "리드 생성" 선택 시 `leadsApi.addContactHistory()` + 리드 생성
- posted_comments 테이블에 lead_id 참조 추가

### 3.4 워크플로우 3: 경쟁사 약점 → 콘텐츠 제작

```
[Competitor Analysis 페이지]
    │
    │ 약점 발견: "대기시간 불만 많음"
    │   관련 리뷰: 12건
    │   심각도: 높음
    │
    ▼
┌─────────────────────────────────────────────┐
│ 💡 이 약점을 공략하는 콘텐츠를 만드시겠습니까?  │
│                                             │
│   약점 유형: 대기시간                         │
│   추천 키워드:                               │
│     • 예약제 한의원                          │
│     • 대기 없는 한의원                        │
│                                             │
│   [콘텐츠 아웃라인 생성]  [키워드만 저장]  [무시] │
└─────────────────────────────────────────────┘
    │
    │ 사용자 클릭: [콘텐츠 아웃라인 생성]
    │
    ▼
[Pathfinder - Content Calendar]
    새 콘텐츠 계획 추가
    - 주제: "예약제로 대기시간 0분"
    - 타겟 키워드: ["청주 예약제 한의원"]
    - 출처: 경쟁사 약점 분석
```

**구현 방법:**
- 약점 카드에 "콘텐츠 제작" 버튼 추가
- `competitorsApi.generateContentOutline(weakness_type)` 호출
- 결과를 Content Calendar에 등록하는 흐름

### 3.5 워크플로우 4: 순위 하락 → 바이럴 대응

```
[Battle Intelligence]
    │
    │ 순위 하락 알림
    │   "청주 한의원" 5위 → 9위 (▼4)
    │
    ▼
┌─────────────────────────────────────────────┐
│ ⚠️ 순위 하락 대응 액션                        │
│                                             │
│   키워드: 청주 한의원                         │
│   하락 폭: 4순위                             │
│   관련 바이럴 타겟: 8개 발견                  │
│                                             │
│   [바이럴 댓글 작성하기]  [콘텐츠 계획]  [무시]  │
└─────────────────────────────────────────────┘
    │
    │ 사용자 클릭: [바이럴 댓글 작성하기]
    │
    ▼
[Viral Hunter]
    해당 키워드로 필터링된 타겟 목록 표시
    → matched_keyword = "청주 한의원"
```

---

## 4. Dashboard 통합 허브 설계

### 4.1 현재 Dashboard 위젯
1. Metrics (총 키워드, S/A등급, 리드 수)
2. Briefing (요약 브리핑)
3. Sentinel Alerts (경고 알림)
4. Chronos Timeline (스케줄)
5. Weekly Report
6. Recent Activities

### 4.2 신규 위젯 제안

#### 4.2.1 Pipeline Overview (마케팅 파이프라인 현황)

```
┌─────────────────────────────────────────────────────────────────────┐
│                     마케팅 파이프라인 현황                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  발견          추적          콘텐츠         유입          전환       │
│   ◉ ─────────── ◉ ─────────── ◉ ─────────── ◉ ─────────── ◉        │
│                                                                     │
│  신규 키워드    순위 추적      바이럴 대기    활성 리드     이번달     │
│   +15개        32개          48개          12개 HOT     3건        │
│   ↑ 3개        3개 순위↑      5개 신규      2개 신규     ₩1.2M     │
│                                                                     │
│  [키워드 보기]  [순위 보기]    [바이럴 보기]  [리드 보기]   [ROI 보기]  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**사용 API:**
- `pathfinderApi.getStats()` - 키워드 통계
- `battleApi.getRankingKeywords()` - 순위 추적 키워드
- `viralApi.getStats()` - 바이럴 통계
- `leadsApi.getStats()` - 리드 통계
- `leadsApi.getConversionTracking()` - 전환 통계

#### 4.2.2 Quick Actions (오늘의 권장 액션)

```
┌─────────────────────────────────────────────────────────────────────┐
│                       오늘의 권장 액션                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. ⭐ [키워드] "청주 다이어트 한약" 순위 추적 등록 권장               │
│     검색량 2,400 | S등급 | 경쟁 중간                   [추가하기 →]  │
│                                                                     │
│  2. 🎯 [바이럴] "청주 안면비대칭" 관련 댓글 3개 대기 중                │
│     네이버 카페 2개, 블로그 1개                        [댓글 작성 →]  │
│                                                                     │
│  3. 🔥 [리드] 당근마켓 HOT 리드 2건 응답 대기                        │
│     점수 92점, 87점 | 컨택 필요                        [응답하기 →]  │
│                                                                     │
│  4. ⚠️ [순위] "청주 한의원" 5위→9위 하락                             │
│     4순위 하락 | 바이럴 타겟 8개 발견                   [분석하기 →]  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**사용 API:**
- `hudApi.getSuggestedActions()` - AI 추천 액션
- `hudApi.getRecommendedKeywords()` - 추천 키워드
- `battleApi.getRankDropAlerts()` - 순위 하락 알림
- `leadsApi.getHotLeads()` - HOT 리드

---

## 5. 페이지별 개선 사항

### 5.1 Pathfinder

| 개선 항목 | 현재 | 개선 후 |
|----------|------|---------|
| 키워드 카드 액션 | 수정/삭제만 | + "순위 추적 시작" 버튼 |
| S등급 키워드 | 배지만 표시 | + "🎯 추적 권장" 표시 |
| 클러스터 액션 | 보기만 | + "콘텐츠 아웃라인 생성" 버튼 |
| 탭 구성 | 수집/분석/활용/히스토리/클러스터 | + "콘텐츠 플랜" 탭 추가 |

**신규 탭: 콘텐츠 플랜**
- `pathfinderApi.getContentCalendar()` 활용
- 주차별 콘텐츠 계획 표시
- "블로그 글 아웃라인 생성" 기능

### 5.2 Battle Intelligence

| 개선 항목 | 현재 | 개선 후 |
|----------|------|---------|
| 순위 하락 알림 | 알림만 표시 | + "바이럴 찾기" 링크 |
| 경쟁사 순위 | 없음 | + "경쟁사 비교" 탭 추가 |
| 키워드 상세 | 트렌드 차트 | + "관련 바이럴 타겟" 섹션 |

**신규 탭: 경쟁사 비교**
- `battleApi.compareRankingsWithCompetitors()` 활용
- 같은 키워드에서 경쟁사 순위 비교
- 순위 변동 트렌드 시각화

### 5.3 Viral Hunter

| 개선 항목 | 현재 | 개선 후 |
|----------|------|---------|
| 댓글 게시 후 | 완료 메시지만 | + "리드 추적" 모달 |
| 댓글 생성 | AI 생성만 | + Q&A Repository 참조 |
| 키워드 연결 | matched_keyword 표시 | + Battle 키워드와 연동 필터 |

**신규 기능: Q&A 참조**
- `qaApi.match(text)` 활용
- 유사한 질문에 대한 기존 답변 참조
- "이 답변 사용하기" 버튼

### 5.4 Lead Manager

| 개선 항목 | 현재 | 개선 후 |
|----------|------|---------|
| 전환 기록 | ✅ ConversionModal 구현됨 | - |
| 분석 기능 | 없음 | + "분석" 탭 추가 |
| 출처 추적 | platform만 | + source_keyword, source_content |

**신규 탭: 분석**
- `leadsApi.getBottleneckAnalysis()` 활용
- 단계별 전환율 퍼널 시각화
- 병목 구간 하이라이트

### 5.5 Competitor Analysis

| 개선 항목 | 현재 | 개선 후 |
|----------|------|---------|
| 약점 분석 | 목록 표시 | + "콘텐츠 제작" 워크플로우 |
| 시각화 | 없음 | + Weakness Radar 차트 |
| Content Gap | 없음 | + "콘텐츠 기회" 탭 |

**신규 탭: 콘텐츠 기회**
- `competitorsApi.getContentGap()` 활용
- 경쟁사가 다루지 않는 주제 발굴
- "이 주제로 콘텐츠 계획" 버튼

---

## 6. 미사용 API 활용 계획

### 6.1 즉시 활용 가능 (Dashboard 연동)

| API | 현재 상태 | 활용 방안 |
|-----|----------|----------|
| `hudApi.getRecommendedKeywords()` | 미사용 | Quick Actions 위젯 |
| `hudApi.getSuggestedActions()` | 미사용 | Quick Actions 위젯 |
| `hudApi.getKeiAlerts()` | 미사용 | Sentinel Alerts 확장 |

### 6.2 페이지 탭 추가로 활용

| API | 현재 상태 | 활용 방안 |
|-----|----------|----------|
| `pathfinderApi.getContentCalendar()` | 미사용 | Pathfinder "콘텐츠 플랜" 탭 |
| `pathfinderApi.generateOutline()` | 미사용 | 클러스터 상세에서 호출 |
| `battleApi.compareRankingsWithCompetitors()` | 미사용 | Battle "경쟁사 비교" 탭 |
| `leadsApi.getBottleneckAnalysis()` | 미사용 | Lead Manager "분석" 탭 |
| `leadsApi.getGoalForecast()` | 미사용 | Dashboard 목표 위젯 |
| `competitorsApi.getContentGap()` | 미사용 | Competitors "콘텐츠 기회" 탭 |
| `competitorsApi.getWeaknessRadar()` | 미사용 | Competitors 시각화 |

### 6.3 신규 기능 영역

| API | 현재 상태 | 활용 방안 |
|-----|----------|----------|
| `qaApi.*` (전체) | 미사용 | Q&A Repository 페이지 신설 또는 Viral 댓글 생성 시 참조 |

---

## 7. 구현 로드맵

### Phase A: Dashboard 통합 허브 (1주차)

```
A-1: Pipeline Overview 위젯
     └── 5단계 파이프라인 시각화
     └── 각 단계 클릭 시 해당 페이지 이동

A-2: Quick Actions 위젯
     └── getSuggestedActions() 연동
     └── 액션별 "실행" 버튼 → 해당 페이지 이동

A-3: Today's Keywords 섹션
     └── getRecommendedKeywords() 연동
     └── "순위 추적 추가" 원클릭 버튼
```

### Phase B: 페이지 간 연결 (2-3주차)

```
B-1: Pathfinder → Battle 연결
     └── KeywordCard "순위 추적 시작" 버튼
     └── S/A등급 "추적 권장" 배지

B-2: Battle → Viral 연결
     └── 순위 하락 알림에 "바이럴 찾기" 링크
     └── 키워드 기반 바이럴 타겟 필터링

B-3: Viral → Leads 연결
     └── 댓글 게시 후 "리드 추적" 모달
     └── posted_comments → leads 연결

B-4: Competitors → Content 연결
     └── 약점에서 "콘텐츠 제작" 워크플로우
     └── Content Calendar 연동
```

### Phase C: 신규 기능 (4주차)

```
C-1: Q&A Repository 관리
     └── 새 페이지 또는 Settings 하위 탭
     └── Viral 댓글 생성 시 참조 연동

C-2: 고급 분석 탭들
     └── Battle: 경쟁사 비교 탭
     └── Leads: 병목 분석 탭
     └── Competitors: 콘텐츠 기회 탭
```

---

## 8. 기대 효과

### 8.1 사용자 경험 개선

| 현재 | 개선 후 |
|------|---------|
| 각 페이지에서 개별 작업 | Dashboard에서 "오늘 할 일" 한눈에 파악 |
| 키워드 발굴 → 수동으로 순위 등록 | 원클릭으로 순위 추적 시작 |
| 댓글 게시 후 추적 불가 | 자동 리드 생성 및 응답 추적 |
| 약점 분석 → 메모만 | 콘텐츠 아웃라인 자동 생성 |

### 8.2 데이터 흐름 가시화

```
Before: 키워드 → ??? → 리드 → ???
After:  키워드 → 순위추적 → 바이럴 → 리드 → 전환 (출처 추적)
```

### 8.3 ROI 측정 정확도 향상

- 전환 시 출처 키워드 자동 기록
- 채널별/키워드별 ROI 분석 가능
- 마케팅 예산 배분 근거 확보

---

## 9. 기술적 구현 노트

### 9.1 필요한 백엔드 변경

1. **viral_targets 테이블**: `source_lead_id` 컬럼 추가 (리드 전환 추적용)
2. **leads 테이블**: `source_viral_id`, `source_keyword` 컬럼 추가
3. **conversion_records 테이블**: `source_keyword` 컬럼이 있는지 확인

### 9.2 필요한 프론트엔드 컴포넌트

1. **PipelineOverview.tsx** - Dashboard 파이프라인 위젯
2. **QuickActions.tsx** - Dashboard 권장 액션 위젯
3. **TrackKeywordModal.tsx** - Pathfinder → Battle 연결 모달
4. **LeadFromViralModal.tsx** - Viral → Leads 연결 모달
5. **ContentPlanTab.tsx** - Pathfinder 콘텐츠 플랜 탭

### 9.3 라우팅 변경 불필요

- 기존 페이지 구조 유지
- 페이지 간 이동은 `useNavigate()` + query parameter로 처리
- 예: `/viral?keyword=청주+한의원` (키워드 필터 적용)

---

## 10. 결론

### 핵심 메시지

> **"모든 마케팅 활동이 하나의 흐름으로 연결되고, 사용자가 각 단계에서 명확한 '다음 액션'을 선택할 수 있는 시스템"**

### 성공 기준

1. Dashboard에서 "오늘 해야 할 일"을 3개 이상 제안
2. 모든 페이지에서 최소 1개의 "다음 단계로" 액션 제공
3. 리드 전환 시 출처 키워드 90% 이상 추적
4. 사용자가 5단계 파이프라인 전체를 한 세션에서 경험 가능

---

*이 문서는 기술적 분석을 기반으로 작성되었으며, 실제 구현 시 사용자 피드백에 따라 조정될 수 있습니다.*

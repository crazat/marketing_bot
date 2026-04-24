# 중복 프론트 컴포넌트 6쌍 재검증 (Y4)

Agent가 "중복"으로 지목한 6쌍을 개별 실측한 결과.

## 판정 결과

| 쌍 | 판정 | 근거 |
|---|---|---|
| KeywordHub (776줄) ↔ KeywordLifecycleView (436줄) | **역할 분리** | Hub는 탭형 다중 데이터, Lifecycle은 타임라인 뷰. BattleIntelligence에서 상호 보완 |
| LeadTable (1083줄) ↔ LeadCard (279줄) | **역할 분리** | Table=전체 리스트(LeadManager), Card=칸반 컬럼의 개별 카드(KanbanColumn) |
| SmartActionPanel (419줄) ↔ SuggestedActions (209줄) | **유사하지만 전략 다름** | SmartAction: 클라이언트 측 다중 API 집계 / Suggested: 서버 hudApi 집계 — 통합 가능성 있으나 제거 위험 |
| ChannelROI (211줄, Analytics) ↔ ROIDashboard (282줄, MarketingHub) | **페이지 분리** | 다른 페이지에서 다른 역할. 분석 vs 허브 |
| RecommendedKeywords (173줄) ↔ TopKeiKeywords (261줄) | **역할 분리** | 오늘의 추천 vs 상위 KEI 키워드 — 다른 데이터 소스 |
| ViralStats (38줄) ↔ TrendInsights (304줄) | **규모·목적 다름** | ViralStats는 경량 메트릭 래퍼, TrendInsights는 트렌드 인사이트 분석 |

## 조치

- **통합된 것**: 0쌍 (실제 중복 없음)
- **기록됨**: 6쌍 모두 "중복 아님" 또는 "제거 위험으로 보류"

## Agent 오판 총합

이번 감사에서 Agent가 중복으로 지목한 것 중 실제 중복은 **0쌍**. 에이전트의
프론트엔드 grep은 컴포넌트 이름만으로 판단했지만, 실제로는 대부분 **역할
분리**된 설계였음.

## 후속

SmartActionPanel vs SuggestedActions만 **통합 후보**로 유지. 다음 세션에서:
1. 양쪽 기능 모두 포괄하는 단일 `ActionRecommender` 설계
2. Dashboard에서 하나만 노출
3. 나머지는 archive

지금은 두 컴포넌트 모두 정상 작동하므로 **긴급성 낮음**.

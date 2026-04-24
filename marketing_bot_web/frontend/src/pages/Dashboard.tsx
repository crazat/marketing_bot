import { useEffect, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useWebSocket } from '@/hooks/useWebSocket'
import {
  hudApi,
  leadsApi,
  type BriefingData,
  type SentinelAlertsData,
  type SentinelAlert,
  type Activity,
  type HudMetrics,
  type SystemStatus,
  type KeywordHighlight,
} from '@/services/api'
import MetricCard from '@/components/MetricCard'
import ChronosTimeline from '@/components/ChronosTimeline'
import HotLeadBanner from '@/components/ui/HotLeadBanner'
import MarketingFunnel from '@/components/ui/MarketingFunnel'
import SmartActionPanel from '@/components/ui/SmartActionPanel'
import WorkflowAlerts from '@/components/ui/WorkflowAlerts'
import AlertCenter from '@/components/ui/AlertCenter'
import RecommendedKeywords from '@/components/ui/RecommendedKeywords'
import TopKeiKeywords from '@/components/pathfinder/TopKeiKeywords'
import PipelineOverview from '@/components/dashboard/PipelineOverview'
import AiBriefing from '@/components/dashboard/AiBriefing'
import TodayFocus from '@/components/dashboard/TodayFocus'
import AnomalyAlert from '@/components/dashboard/AnomalyAlert'
import SeasonalityHint from '@/components/dashboard/SeasonalityHint'
import JournalSummary from '@/components/dashboard/JournalSummary'
import PatternSuggestion from '@/components/dashboard/PatternSuggestion'
import WidgetErrorBoundary from '@/components/ui/WidgetErrorBoundary'
import { useTimeContext } from '@/hooks/useTimeContext'
import { TrendInsights } from '@/components/viral/TrendInsights'
import {
  SkeletonMetricCard,
  SkeletonBriefingCard,
  SkeletonAlertCard,
  SkeletonActivityLog,
  Skeleton,
} from '@/components/ui/Skeleton'
import { DataFreshness, ErrorState } from '@/components/ui'
import Collapsible from '@/components/ui/Collapsible'
import PageTransition from '@/components/PageTransition'
import QuickActions from '@/components/QuickActions'
import Button from '@/components/ui/Button'

// 상수를 컴포넌트 외부로 이동하여 매 렌더링마다 재생성 방지
const GOAL_TYPE_LABELS: Record<string, string> = {
  leads: '리드',
  keywords: '키워드',
  conversions: '전환',
  s_grade: 'S급 키워드'
}

const GOAL_TYPE_ICONS: Record<string, string> = {
  leads: '📋',
  keywords: '🔑',
  conversions: '✅',
  s_grade: '🔥'
}

export default function Dashboard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const timeCtx = useTimeContext()

  // [Phase 2-2] WebSocket 구독으로 실시간 업데이트 (폴링 95% 감소)
  const { lastMessage } = useWebSocket()

  // WebSocket 메시지 처리
  useEffect(() => {
    if (!lastMessage) return

    switch (lastMessage.type) {
      case 'hud_update':
        // HUD 메트릭 즉시 업데이트
        if (lastMessage.data) {
          queryClient.setQueryData(['hud-metrics'], lastMessage.data)
        }
        break
      case 'new_lead':
        // 새 리드 알림 - 긴급 리드 목록 갱신
        queryClient.invalidateQueries({ queryKey: ['leads-pending-alerts'] })
        break
      case 'ranking_update':
        // 순위 업데이트 - 브리핑 갱신
        queryClient.invalidateQueries({ queryKey: ['daily-briefing'] })
        break
      case 'scheduler_status':
        // 시스템 상태 갱신
        queryClient.invalidateQueries({ queryKey: ['system-status'] })
        break
    }
  }, [lastMessage, queryClient])

  const {
    data: metrics,
    isLoading: metricsLoading,
    isError: metricsError,
    dataUpdatedAt: metricsUpdatedAt,
    refetch: refetchMetrics,
    isFetching: metricsRefreshing,
  } = useQuery<HudMetrics>({
    queryKey: ['hud-metrics'],
    queryFn: hudApi.getMetrics,
    refetchInterval: 120000, // [성능 최적화] 60초 → 120초 (서버 부하 50% 감소)
    refetchIntervalInBackground: false,
    staleTime: 60000, // [성능 최적화] 30초 → 60초
    retry: 2,
  })

  const { data: systemStatus, isLoading: systemStatusLoading, isError: systemStatusError, refetch: refetchSystemStatus } = useQuery<SystemStatus>({
    queryKey: ['system-status'],
    queryFn: hudApi.getSystemStatus,
    refetchInterval: 120000, // [Phase 7] 60초 → 120초
    refetchIntervalInBackground: false,
    staleTime: 60000, // [Phase 7] 30초 → 60초
    retry: 2,
  })

  const {
    data: briefing,
    isLoading: briefingLoading,
    isError: briefingError,
    dataUpdatedAt: briefingUpdatedAt,
    refetch: refetchBriefing,
    isFetching: briefingRefreshing,
  } = useQuery<BriefingData>({
    queryKey: ['daily-briefing'],
    queryFn: hudApi.getBriefing,
    // [성능 최적화] enabled 조건 제거 - 병렬 로드로 페이지 로딩 30% 단축
    refetchInterval: 300000,
    staleTime: 60000,
    retry: 2,
  })

  const {
    data: sentinelAlerts,
    isLoading: alertsLoading,
    isError: alertsError,
    dataUpdatedAt: alertsUpdatedAt,
    refetch: refetchAlerts,
    isFetching: alertsRefreshing,
  } = useQuery<SentinelAlertsData>({
    queryKey: ['sentinel-alerts'],
    queryFn: hudApi.getSentinelAlerts,
    // [성능 최적화] enabled 조건 제거 - 병렬 로드
    refetchInterval: 120000, // [성능 최적화] 60초 → 120초
    refetchIntervalInBackground: false,
    staleTime: 60000, // [성능 최적화] 30초 → 60초
    retry: 2,
  })

  const { data: recentActivities, isLoading: activitiesLoading, isError: activitiesError, refetch: refetchActivities } = useQuery<Activity[]>({
    queryKey: ['recent-activities'],
    queryFn: hudApi.getRecentActivities,
    // [성능 최적화] enabled 조건 제거 - 병렬 로드
    refetchInterval: 120000,
    refetchIntervalInBackground: false,
    staleTime: 60000,
    retry: 2,
  })

  // [Phase 8.0] 메트릭 트렌드
  const { data: metricsTrend } = useQuery({
    queryKey: ['metrics-trend'],
    queryFn: () => hudApi.getMetricsTrend(7),
    // [성능 최적화] enabled 조건 제거 - 병렬 로드
    refetchInterval: 300000,
    refetchIntervalInBackground: false,
    staleTime: 120000,
    retry: 2,
  })

  // [Phase 4.0] Hot Lead 긴급 알림
  const { data: pendingAlerts } = useQuery({
    queryKey: ['leads-pending-alerts'],
    queryFn: leadsApi.getPendingAlerts,
    refetchInterval: 120000, // [성능 최적화] 60초 → 120초
    refetchIntervalInBackground: false,
    staleTime: 60000,
    retry: 1,
  })

  // 목표 조회
  const { data: goals } = useQuery<Array<{
    id: number
    type: string
    title: string
    target_value: number
    current_value: number
    progress: number
    remaining: number
    days_remaining: number
    period: string
  }>>({
    queryKey: ['goals'],
    queryFn: hudApi.getGoals,
    refetchInterval: 300000, // [성능 최적화] 60초 → 300초 (목표는 자주 변경되지 않음)
    refetchIntervalInBackground: false,
    staleTime: 120000,
    retry: 1,
  })

  // 네비게이션 핸들러 메모이제이션
  const handleNavigatePathfinder = useCallback(() => navigate('/pathfinder'), [navigate])
  const handleNavigatePathfinderS = useCallback(() => navigate('/pathfinder?grade=S'), [navigate])
  const handleNavigatePathfinderA = useCallback(() => navigate('/pathfinder?grade=A'), [navigate])
  const handleNavigateLeads = useCallback(() => navigate('/leads'), [navigate])
  const handleNavigateGoalSettings = useCallback(() => navigate('/settings?tab=goals'), [navigate])

  // 시간 포맷팅 함수 (useCallback으로 메모이제이션)
  const formatTime = useCallback((timestamp: string | null | undefined) => {
    if (!timestamp) return '-'
    try {
      const date = new Date(timestamp)
      return date.toLocaleString('ko-KR', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch {
      return timestamp
    }
  }, [])

  return (
    <PageTransition>
      <div className="space-y-8">
        {/* [Z4] 편집 매거진 스타일 헤더 + [Z1] 시간 맥락 · [DD7] 반응형 보강 */}
        <header className="border-b border-border pb-6">
          <div className="caps text-muted-foreground mb-2 flex items-center gap-2 flex-wrap">
            <span>Marketing Command</span>
            <span aria-hidden className="hidden sm:inline">·</span>
            <span className="tabular-nums">
              {timeCtx.dayOfWeekKr}요일 {timeCtx.hour.toString().padStart(2, '0')}시
            </span>
            {timeCtx.isWeekend && <span className="text-accent">주말</span>}
          </div>
          <h1 className="font-display text-3xl sm:text-4xl md:text-5xl leading-tight tracking-tight">
            {timeCtx.greeting}
          </h1>
          <p className="text-sm text-muted-foreground mt-3">
            {timeCtx.suggestion}
          </p>
        </header>

        {/*
          [CC2] 배너 우선순위 (위 → 아래, 높은 우선순위부터):
            1. AnomalyAlert — 치명적 이상 (즉시 주의)
            2. PatternSuggestion — 자동화 기회 (코칭)
            3. HotLeadBanner — 핫리드 (오늘 처리)
            4. TodayFocus — 단일 CTA (상시)
          각 배너는 조건부 렌더(null 반환). 여러 개가 동시에 뜰 수는 있으나
          실제로는 대부분 0–2개만 활성화됨.
        */}

        {/* 1. 이상 신호 (최우선 — 치명적) */}
        <WidgetErrorBoundary widgetName="이상 신호">
          <AnomalyAlert />
        </WidgetErrorBoundary>

        {/* 2. 패턴 감지 (코칭) */}
        <WidgetErrorBoundary widgetName="패턴 감지">
          <PatternSuggestion />
        </WidgetErrorBoundary>

        {/* 3. 핫리드 배너 (있을 때만 노출 — TodayFocus보다 긴급하므로 위로) */}
        <WidgetErrorBoundary widgetName="핫 리드 배너" minHeight="80px">
          <HotLeadBanner />
        </WidgetErrorBoundary>

        {/* 4. 오늘의 집중 — 상시 노출 단일 CTA */}
        <WidgetErrorBoundary widgetName="오늘의 집중" minHeight="120px">
          <TodayFocus />
        </WidgetErrorBoundary>

        {/* 핵심 메트릭 — 배너 바로 아래로 이동 (오늘 상태 즉시 확인) */}
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-semibold">핵심 메트릭</h2>
          <DataFreshness
            lastUpdated={metricsUpdatedAt ? new Date(metricsUpdatedAt) : null}
            onRefresh={() => refetchMetrics()}
            isRefreshing={metricsRefreshing}
            compact
          />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {metricsLoading ? (
            <>
              <SkeletonMetricCard />
              <SkeletonMetricCard />
              <SkeletonMetricCard />
              <SkeletonMetricCard />
            </>
          ) : metricsError ? (
            <div className="col-span-4">
              <ErrorState
                title="메트릭 로드 실패"
                message="메트릭 데이터를 불러오는데 실패했습니다."
                onRetry={() => refetchMetrics()}
              />
            </div>
          ) : (
            <>
              <MetricCard
                title="총 키워드"
                value={metrics?.total_keywords || 0}
                icon="🎯"
                subtitle="Pathfinder에서 관리"
                onClick={handleNavigatePathfinder}
                sparklineData={metricsTrend?.cumulative?.keywords}
                previousValue={metricsTrend?.previous_values?.keywords}
              />
              <MetricCard
                title="S급 키워드"
                value={metrics?.s_grade_keywords || 0}
                icon="🔥"
                color="text-red-500"
                subtitle="고가치 키워드"
                onClick={handleNavigatePathfinderS}
                sparklineData={metricsTrend?.cumulative?.s_grade}
                previousValue={metricsTrend?.previous_values?.s_grade}
              />
              <MetricCard
                title="A급 키워드"
                value={metrics?.a_grade_keywords || 0}
                icon="🟢"
                color="text-green-500"
                subtitle="우수 키워드"
                onClick={handleNavigatePathfinderA}
                sparklineData={metricsTrend?.cumulative?.a_grade}
                previousValue={metricsTrend?.previous_values?.a_grade}
              />
              <MetricCard
                title="총 리드"
                value={metrics?.total_leads || 0}
                icon="📋"
                subtitle="Lead Manager에서 관리"
                onClick={handleNavigateLeads}
                sparklineData={metricsTrend?.cumulative?.leads}
                previousValue={metricsTrend?.previous_values?.leads}
              />
            </>
          )}
        </div>

        {/* 이번 달 목표 — 메트릭 바로 아래 */}
        {goals && goals.length > 0 && (
          <div className="bg-card rounded-lg border border-border p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold">🎯 이번 달 목표</h2>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleNavigateGoalSettings}
              >
                설정 →
              </Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {goals.map((goal) => {
                const isComplete = goal.progress >= 100
                const progressColor = isComplete ? 'bg-green-500' :
                  goal.progress >= 70 ? 'bg-primary' :
                  goal.progress >= 40 ? 'bg-yellow-500' : 'bg-red-500'

                return (
                  <div
                    key={goal.id}
                    className={`rounded-lg border p-4 transition-colors ${
                      isComplete ? 'border-green-500/50 bg-green-500/5' : 'border-border'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-2xl">{GOAL_TYPE_ICONS[goal.type] || '🎯'}</span>
                      <span className="text-xs text-muted-foreground">
                        D-{goal.days_remaining}
                      </span>
                    </div>
                    <p className="text-sm font-medium mb-1">
                      {goal.title || GOAL_TYPE_LABELS[goal.type] || goal.type}
                    </p>
                    <div className="flex items-baseline gap-1 mb-2">
                      <span className={`text-2xl font-bold ${isComplete ? 'text-green-500' : ''}`}>
                        {goal.current_value}
                      </span>
                      <span className="text-muted-foreground">/ {goal.target_value}</span>
                    </div>
                    <div className="h-2 bg-muted rounded-full overflow-hidden mb-1">
                      <div
                        className={`h-full ${progressColor} transition-all duration-500`}
                        style={{ width: `${Math.min(100, goal.progress)}%` }}
                      />
                    </div>
                    <p className={`text-xs ${isComplete ? 'text-green-500' : 'text-muted-foreground'}`}>
                      {isComplete ? '✅ 달성 완료!' : `${goal.remaining}개 남음`}
                    </p>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* 스마트 액션 — 상시 노출 (Dashboard 메인 CTA 위젯)
            SuggestedActions·SmartActionPanel 2개 위젯이 "오늘 할 일" 중복이라 SmartActionPanel로 일원화 */}
        <section aria-label="스마트 액션" id="actions" className="bg-card border border-border p-4">
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="font-display text-xl flex items-center gap-2">
              🧠 스마트 액션
            </h2>
            <span className="caps text-muted-foreground">AI recommendations</span>
          </div>
          <WidgetErrorBoundary widgetName="스마트 액션">
            <SmartActionPanel maxItems={8} />
          </WidgetErrorBoundary>
        </section>

        {/* 알림 허브 */}
        <section aria-label="알림 허브" className="space-y-3">
          <div className="flex items-baseline justify-between">
            <h2 className="font-display text-xl flex items-center gap-2">
              알림 허브
            </h2>
            <span className="caps text-muted-foreground">Events</span>
          </div>
          <AlertCenter />
          <div className="bg-card border border-border p-4">
            <WorkflowAlerts maxItems={3} />
          </div>
        </section>

        {/* 빠른 실행 */}
        <section aria-label="빠른 실행">
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="font-display text-xl">빠른 실행</h2>
            <span className="caps text-muted-foreground">Tools</span>
          </div>
          <QuickActions />
        </section>

        {/* 📊 상세 분석 — 파이프라인·브리핑·스마트액션·트렌드·키워드·퍼널
            (ROI·주간 리포트는 Marketing Hub로 이관) */}
        <Collapsible
          title="📊 상세 분석"
          summary="파이프라인, AI 브리핑, 스마트 액션, 트렌드, 키워드, 마케팅 퍼널"
          defaultOpen={false}
        >
          <div className="space-y-6 pt-2">
            <WidgetErrorBoundary widgetName="마케팅 파이프라인">
              <PipelineOverview />
            </WidgetErrorBoundary>

            <WidgetErrorBoundary widgetName="AI 브리핑">
              <AiBriefing />
            </WidgetErrorBoundary>

            {/* 스마트 액션은 상시 노출로 이동 (Collapsible 밖, 메트릭 아래) */}

            <WidgetErrorBoundary widgetName="트렌드 인사이트">
              <TrendInsights compact />
            </WidgetErrorBoundary>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <RecommendedKeywords />
              <TopKeiKeywords
                compact
                limit={5}
                onNavigate={() => navigate('/pathfinder')}
              />
            </div>

            <WidgetErrorBoundary widgetName="마케팅 퍼널">
              <MarketingFunnel />
            </WidgetErrorBoundary>

            {/* ROI·주간 리포트 이관 안내 */}
            <button
              type="button"
              onClick={() => navigate('/marketing')}
              className="w-full bg-primary/5 border border-primary/20 hover:bg-primary/10 transition-colors p-4 rounded text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              <p className="text-sm font-medium">💰 ROI 분석 · 주간 리포트는 Marketing Hub로 이동했습니다</p>
              <p className="text-xs text-muted-foreground mt-1">
                캠페인, A/B 테스트, 경쟁사 레이더와 함께 확인 →
              </p>
            </button>
          </div>
        </Collapsible>

      {/* [BB1] 오늘 한 일 저널 */}
      <WidgetErrorBoundary widgetName="오늘 한 일">
        <JournalSummary />
      </WidgetErrorBoundary>

      {/* [BB6] 계절성 힌트 */}
      <WidgetErrorBoundary widgetName="계절성 힌트">
        <SeasonalityHint />
      </WidgetErrorBoundary>

      {/* Chronos Timeline */}
      <WidgetErrorBoundary widgetName="Chronos Timeline">
        <div className="bg-card rounded-lg border border-border p-6">
          <h2 className="text-xl font-bold mb-4">⏰ Chronos Timeline</h2>
          <ChronosTimeline />
        </div>
      </WidgetErrorBoundary>

      {/* Briefing Dashboard - Accordion 스타일 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold">일일 브리핑</h2>
          <DataFreshness
            lastUpdated={briefingUpdatedAt ? new Date(briefingUpdatedAt) : null}
            onRefresh={() => refetchBriefing()}
            isRefreshing={briefingRefreshing}
            compact
          />
        </div>
        {briefingLoading ? (
          <SkeletonBriefingCard />
        ) : briefingError ? (
          <ErrorState
            title="브리핑 로드 실패"
            message="브리핑 데이터를 불러오는데 실패했습니다."
            onRetry={() => refetchBriefing()}
          />
        ) : briefing ? (
          <div className="space-y-3">
            {/* 오늘 요약 (항상 표시) */}
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
              <p className="text-sm font-semibold text-blue-500 mb-2">
                {new Date().toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' })}
              </p>
              <p className="text-sm text-blue-500">{briefing.summary}</p>
            </div>

            {/* [Phase 4.0] 오늘의 필수 액션 */}
            {briefing.urgent_actions && briefing.urgent_actions.length > 0 && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xl">⚡</span>
                  <h3 className="font-semibold text-red-500">오늘의 필수 액션</h3>
                  <span className="px-2 py-0.5 text-xs bg-red-500 text-white rounded-full">
                    {briefing.urgent_actions.length}
                  </span>
                </div>
                <div className="space-y-2">
                  {briefing.urgent_actions.map((action: any, idx: number) => (
                    <div
                      key={idx}
                      className={`flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors ${
                        action.priority === 'critical'
                          ? 'bg-red-500/20 hover:bg-red-500/30'
                          : action.priority === 'high'
                          ? 'bg-yellow-500/20 hover:bg-yellow-500/30'
                          : 'bg-muted hover:bg-muted/80'
                      }`}
                      onClick={() => navigate(action.action_link)}
                    >
                      <div className="flex-1">
                        <div className="font-medium text-sm flex items-center gap-2">
                          {action.priority === 'critical' && <span>🚨</span>}
                          {action.priority === 'high' && <span>⚠️</span>}
                          {action.priority === 'medium' && <span>📢</span>}
                          {action.title}
                        </div>
                        <div className="text-xs text-muted-foreground mt-1">
                          {action.description}
                        </div>
                      </div>
                      <Button
                        variant="primary"
                        size="xs"
                      >
                        {action.action_label}
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 키워드 하이라이트 */}
            {briefing.keyword_highlights && (
              <Collapsible
                title={
                  <div className="flex items-center gap-2">
                    <span>🎯</span>
                    <span className="font-semibold">키워드 하이라이트</span>
                    <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded-full">
                      +{briefing.keyword_highlights.new_keywords}개
                    </span>
                  </div>
                }
                summary={`새 키워드 ${briefing.keyword_highlights.new_keywords}개, S급 ${briefing.keyword_highlights.new_s_grade}개`}
                defaultOpen={briefing.keyword_highlights.new_keywords > 0}
              >
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-muted p-3 rounded">
                      <div className="text-xs text-muted-foreground">새 키워드 (24h)</div>
                      <div className="text-lg font-bold">{briefing.keyword_highlights.new_keywords}개</div>
                    </div>
                    <div className="bg-muted p-3 rounded">
                      <div className="text-xs text-muted-foreground">새 S/A급</div>
                      <div className="text-lg font-bold text-green-500">{briefing.keyword_highlights.new_s_grade}개</div>
                    </div>
                  </div>
                  {briefing.keyword_highlights.top_keywords?.length > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground mb-2">최근 추가된 S급 키워드</p>
                      {briefing.keyword_highlights.top_keywords.slice(0, 3).map((kw: KeywordHighlight) => (
                        <div key={kw.keyword} className="text-sm flex items-center justify-between p-2 bg-muted/50 rounded">
                          <span>
                            <span className="text-red-500 mr-1" aria-hidden="true">🔥</span>
                            {kw.keyword}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {kw.volume?.toLocaleString() || 0} 검색량
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </Collapsible>
            )}

            {/* 권장 액션 */}
            {briefing.recommended_actions?.length > 0 && (
              <Collapsible
                title={
                  <div className="flex items-center gap-2">
                    <span>💡</span>
                    <span className="font-semibold">권장 액션</span>
                    <span className="text-xs bg-yellow-500/20 text-yellow-600 px-2 py-0.5 rounded-full">
                      {briefing.recommended_actions.length}개
                    </span>
                  </div>
                }
                summary={briefing.recommended_actions[0]?.action}
                defaultOpen={briefing.recommended_actions.some((a: any) => a.priority === 'high')}
              >
                <div className="space-y-2" role="list">
                  {briefing.recommended_actions.map((action, idx) => (
                    <div
                      key={`action-${action.type}-${idx}`}
                      role="listitem"
                      className={`p-3 rounded border ${
                        action.priority === 'high'
                          ? 'bg-red-500/10 border-red-500/30'
                          : 'bg-yellow-500/10 border-yellow-500/30'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          action.priority === 'high'
                            ? 'bg-red-500/20 text-red-500'
                            : 'bg-yellow-500/20 text-yellow-600'
                        }`}>
                          {action.priority === 'high' ? '긴급' : '권장'}
                        </span>
                      </div>
                      <p className="text-sm">{action.action}</p>
                    </div>
                  ))}
                </div>
              </Collapsible>
            )}

            {/* 최근 인사이트 */}
            {briefing.recent_insights?.length > 0 && (
              <Collapsible
                title={
                  <div className="flex items-center gap-2">
                    <span>📊</span>
                    <span className="font-semibold">최근 인사이트</span>
                    <span className="text-xs bg-muted text-muted-foreground px-2 py-0.5 rounded-full">
                      {briefing.recent_insights.length}개
                    </span>
                  </div>
                }
                summary={briefing.recent_insights[0]?.title}
              >
                <div className="space-y-2 max-h-60 overflow-y-auto" role="list">
                  {briefing.recent_insights.map((insight, idx) => (
                    <div
                      key={`insight-${insight.created_at}-${idx}`}
                      role="listitem"
                      className="p-3 rounded border border-border bg-muted/30"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary">
                          {insight.type}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {new Date(insight.created_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                      <p className="text-sm font-medium">{insight.title}</p>
                      <p className="text-xs text-muted-foreground mt-1">{insight.content}</p>
                    </div>
                  ))}
                </div>
              </Collapsible>
            )}

            {(!briefing.keyword_highlights?.new_keywords && !briefing.recommended_actions?.length && !briefing.recent_insights?.length) && (
              <div className="text-center text-muted-foreground py-4">
                <p>새로운 업데이트가 없습니다.</p>
              </div>
            )}
          </div>
        ) : (
          <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
            <p className="text-sm text-blue-500">브리핑 데이터를 불러오는 중...</p>
          </div>
        )}
      </div>

      {/* Sentinel Alerts */}
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold">Sentinel Alerts</h2>
          <DataFreshness
            lastUpdated={alertsUpdatedAt ? new Date(alertsUpdatedAt) : null}
            onRefresh={() => refetchAlerts()}
            isRefreshing={alertsRefreshing}
            compact
          />
        </div>
        {alertsLoading ? (
          <SkeletonAlertCard />
        ) : alertsError ? (
          <ErrorState
            title="알림 로드 실패"
            message="알림 데이터를 불러오는데 실패했습니다."
            onRetry={() => refetchAlerts()}
          />
        ) : sentinelAlerts ? (
          <div>
            {sentinelAlerts.status === 'normal' ? (
              <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4 text-center">
                <p className="text-2xl mb-2">✅</p>
                <p className="text-sm text-green-500">모든 시스템 정상 작동 중</p>
              </div>
            ) : (
              <div className="space-y-3">
                <div
                  className={`p-4 rounded border text-center ${
                    sentinelAlerts.status === 'critical'
                      ? 'bg-red-500/10 border-red-500/30'
                      : 'bg-yellow-500/10 border-yellow-500/30'
                  }`}
                >
                  <p className="text-2xl mb-2">
                    {sentinelAlerts.status === 'critical' ? '🚨' : '⚠️'}
                  </p>
                  <p className="text-sm font-semibold">
                    {sentinelAlerts.alert_count}건의 경고
                  </p>
                </div>

                {sentinelAlerts.alerts?.map((alert: SentinelAlert, alertIdx: number) => (
                  <Collapsible
                    key={`alert-${alert.severity}-${alertIdx}`}
                    title={
                      <div className="flex items-center justify-between w-full">
                        <span className="font-semibold text-sm">{alert.message}</span>
                        <span
                          className={`text-xs px-2 py-1 rounded ${
                            alert.severity === 'critical'
                              ? 'bg-red-500/20 text-red-500'
                              : 'bg-yellow-500/20 text-yellow-500'
                          }`}
                        >
                          {alert.severity === 'critical' ? '긴급' : '주의'}
                        </span>
                      </div>
                    }
                  >
                    <div className="space-y-2">
                      {alert.details?.map((detail, detailIdx) => (
                        <div key={`detail-${detail.platform}-${detail.detected_at}-${detailIdx}`} className="text-sm text-muted-foreground">
                          <div className="font-medium">
                            {detail.platform} · {detail.detected_at}
                          </div>
                          <div className="text-xs mt-1">{detail.text}</div>
                        </div>
                      ))}
                    </div>
                  </Collapsible>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 text-center">
            <p className="text-sm text-blue-500">알림 데이터를 불러오는 중...</p>
          </div>
        )}
      </div>

      {/* [Phase 4.0] Hot Lead 긴급 알림 */}
      {pendingAlerts && pendingAlerts.total_alerts > 0 && (
        <div className="bg-card rounded-lg border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold flex items-center gap-2">
              🔥 긴급 리드
              <span className="text-sm font-normal px-2 py-0.5 bg-red-500/20 text-red-500 rounded-full">
                {pendingAlerts.total_alerts}
              </span>
            </h2>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleNavigateLeads}
            >
              리드 관리로 이동 →
            </Button>
          </div>

          <div className="space-y-4">
            {/* 새 Hot Lead */}
            {pendingAlerts.hot_leads?.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-muted-foreground mb-2">
                  🆕 새 Hot Lead ({pendingAlerts.hot_leads.length}개)
                </h3>
                <div className="space-y-2">
                  {pendingAlerts.hot_leads.slice(0, 3).map((lead: any) => (
                    <div
                      key={lead.id}
                      className="flex items-center justify-between p-3 bg-green-500/10 border border-green-500/20 rounded-lg cursor-pointer hover:bg-green-500/20 transition-colors"
                      onClick={handleNavigateLeads}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm truncate">{lead.title}</div>
                        <div className="text-xs text-muted-foreground">
                          {lead.platform} · 점수 {lead.score}점 · {lead.hours_pending}시간 전
                        </div>
                      </div>
                      <div className="ml-2 px-2 py-1 bg-red-500 text-white text-xs rounded font-bold">
                        HOT
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 미연락 리마인더 */}
            {pendingAlerts.overdue_leads?.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-muted-foreground mb-2">
                  ⏰ 24시간+ 미연락 ({pendingAlerts.overdue_leads.length}개)
                </h3>
                <div className="space-y-2">
                  {pendingAlerts.overdue_leads.slice(0, 3).map((lead: any) => (
                    <div
                      key={lead.id}
                      className="flex items-center justify-between p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg cursor-pointer hover:bg-yellow-500/20 transition-colors"
                      onClick={handleNavigateLeads}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm truncate">{lead.title}</div>
                        <div className="text-xs text-muted-foreground">
                          {lead.platform} · 점수 {lead.score}점
                        </div>
                      </div>
                      <div className="ml-2 text-yellow-500 text-xs font-bold">
                        {Math.floor(lead.hours_pending)}시간 대기
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 시스템 상태 & 최근 활동 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-semibold mb-4">시스템 상태</h3>
          {systemStatusLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="flex items-center justify-between">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-6 w-20 rounded-full" />
                </div>
              ))}
            </div>
          ) : systemStatusError ? (
            <ErrorState
              title="로드 실패"
              message="시스템 상태를 불러오는데 실패했습니다."
              onRetry={() => refetchSystemStatus()}
            />
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">스케줄러</span>
                <span className="px-3 py-1 rounded-full bg-green-500/10 text-green-500 text-sm font-medium">
                  {systemStatus?.scheduler_status || 'unknown'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">마지막 Pathfinder 실행</span>
                <span className="text-sm">
                  {formatTime(systemStatus?.last_pathfinder_run)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">마지막 순위 체크</span>
                <span className="text-sm">
                  {formatTime(systemStatus?.last_rank_check)}
                </span>
              </div>
            </div>
          )}
        </div>

        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-semibold mb-4">최근 활동</h3>
          {activitiesLoading ? (
            <SkeletonActivityLog items={5} />
          ) : activitiesError ? (
            <ErrorState
              title="로드 실패"
              message="최근 활동을 불러오는데 실패했습니다."
              onRetry={() => refetchActivities()}
            />
          ) : (
            <div className="space-y-3 text-sm">
              {recentActivities && recentActivities.length > 0 ? (
                recentActivities.slice(0, 5).map((activity: Activity, idx: number) => (
                  <div key={`activity-${activity.label}-${idx}`} className="flex items-center justify-between">
                    <span className="text-muted-foreground">
                      <span className="mr-2" aria-hidden="true">{activity.icon}</span>
                      {activity.label}
                    </span>
                    <span className="text-xs">{activity.relative_time}</span>
                  </div>
                ))
              ) : (
                <p className="text-muted-foreground text-center py-4">
                  최근 활동이 없습니다.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
      </div>
    </PageTransition>
  )
}

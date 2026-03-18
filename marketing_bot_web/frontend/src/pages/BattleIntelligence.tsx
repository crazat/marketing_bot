import { useState, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { battleApi, hudApi, exportApi } from '@/services/api'
import PageTransition from '@/components/PageTransition'
import RankingKeywordsList from '@/components/battle/RankingKeywordsList'
import RankingTrends from '@/components/battle/RankingTrends'
import CompetitorVitals from '@/components/battle/CompetitorVitals'
import CompetitorRankingCompare from '@/components/battle/CompetitorRankingCompare'
import CompetitorInsights from '@/components/battle/CompetitorInsights'
import LocalSeoDashboard from '@/components/battle/LocalSeoDashboard'
import AddKeywordModal from '@/components/battle/AddKeywordModal'
import EditKeywordModal from '@/components/battle/EditKeywordModal'
import ErrorState from '@/components/ui/ErrorState'
import EmptyState from '@/components/ui/EmptyState'
import { SkeletonChart, SkeletonStatsGrid, SkeletonList } from '@/components/ui/Skeleton'
import MissionProgress from '@/components/ui/MissionProgress'
import { ConfirmModal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { useUrlState } from '@/hooks/useUrlState'
import ContextInsightPanel from '@/components/ui/ContextInsightPanel'
import KeywordLifecycleView from '@/components/ui/KeywordLifecycleView'
import { TerminalGuide } from '@/components/ui/TerminalGuide'
import { getPageCommands } from '@/utils/terminalCommands'
import KeywordHub from '@/components/ui/KeywordHub'
import Button, { IconButton } from '@/components/ui/Button'
import { RefreshCw, Download, Plus, Play, Square } from 'lucide-react'

export default function BattleIntelligence() {
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingKeyword, setEditingKeyword] = useState<{ keyword: string; category: string } | null>(null)
  const [keywordToDelete, setKeywordToDelete] = useState<string | null>(null)
  // [Phase 5.0] URL 상태 관리
  const [selectedPeriod, setSelectedPeriod] = useUrlState<number>('period', { defaultValue: 14 })
  const [activeTab, setActiveTab] = useUrlState<string>('tab', { defaultValue: 'trends' })
  const [keywordFilter, setKeywordFilter] = useUrlState<string>('keyword', { defaultValue: '' })
  const [scanningModule, setScanningModule] = useState<string | null>(null)
  // [Phase D-2] Context Insight Panel 상태
  const [showInsightPanel, setShowInsightPanel] = useState(false)
  // [Phase D-3] Keyword Lifecycle View 상태
  const [showLifecycleView, setShowLifecycleView] = useState(false)
  // [Phase E-1] Keyword Hub 상태
  const [showKeywordHub, setShowKeywordHub] = useState(false)
  const queryClient = useQueryClient()
  const toast = useToast()

  // 실행 중인 모듈 조회 (페이지 로드 시 상태 복원)
  const { data: runningModules } = useQuery({
    queryKey: ['running-modules'],
    queryFn: () => hudApi.getRunningModules().catch(() => ({ running: [] })),
    refetchInterval: 60000, // 60초마다 확인 (서버 부하 감소)
    retry: 1,
  })

  // battle 모듈이 실행 중이면 scanningModule 상태 복원
  useEffect(() => {
    if (runningModules?.running?.includes('battle') && !scanningModule) {
      setScanningModule('battle')
    }
  }, [runningModules, scanningModule])

  // 순위 추적 키워드 조회
  const { data: rankingKeywords, isLoading: keywordsLoading, isError: keywordsError, refetch: refetchKeywords } = useQuery({
    queryKey: ['ranking-keywords'],
    queryFn: battleApi.getRankingKeywords,
    staleTime: 60000, // 1분간 캐시
    refetchInterval: 300000, // 5분마다 새로고침
    retry: 2,
  })

  // 순위 트렌드 조회
  const { data: trends, isLoading: trendsLoading, isError: trendsError, refetch: refetchTrends } = useQuery({
    queryKey: ['ranking-trends', selectedPeriod, keywordFilter],
    queryFn: () => battleApi.getRankingTrends(selectedPeriod, keywordFilter || undefined),
    staleTime: 60000, // 1분간 캐시
    retry: 2,
  })

  // [P1-3] 예측에서 트렌드로 이동
  const handleViewTrend = (keyword: string) => {
    setKeywordFilter(keyword)
    setActiveTab('trends')
  }

  // 경쟁사 활력 조회
  const { data: competitorVitals, isLoading: vitalsLoading, isError: vitalsError, refetch: refetchVitals } = useQuery({
    queryKey: ['competitor-vitals'],
    queryFn: battleApi.getCompetitorVitals,
    staleTime: 120000, // 2분간 캐시
    retry: 2,
  })

  // [Phase 4.0] 순위 예측 조회
  const { data: rankingForecast, isLoading: forecastLoading } = useQuery({
    queryKey: ['ranking-forecast', selectedPeriod],
    queryFn: () => battleApi.getRankingForecast(selectedPeriod, 7).catch(() => null),
    staleTime: 120000, // 2분간 캐시
    retry: 1,
  })

  // [P2-3] 예측 정확도 검증
  const { data: forecastAccuracy } = useQuery({
    queryKey: ['forecast-accuracy'],
    queryFn: () => battleApi.getForecastAccuracy(7, 14).catch(() => null),
    staleTime: 300000, // 5분간 캐시 (변동이 적은 데이터)
    retry: 1,
  })

  // [Phase 6.1] 순위 하락 알림
  const { data: rankDropAlerts, isLoading: alertsLoading, isError: alertsError, refetch: refetchAlerts } = useQuery({
    queryKey: ['rank-drop-alerts'],
    queryFn: () => battleApi.getRankDropAlerts(3, true),
    staleTime: 60000, // 1분간 캐시
    retry: 1,
  })

  // 순위 스캔 mutation (hudApi.executeMission 사용)
  const runScan = useMutation({
    mutationFn: () => hudApi.executeMission('battle'),
    onSuccess: () => {
      toast.success('순위 스캔이 시작되었습니다')
      setScanningModule('battle')
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`스캔 실패: ${error.response?.data?.detail || error.message}`)
      setScanningModule(null)
    },
  })

  // 키워드 삭제 mutation
  const removeKeyword = useMutation({
    mutationFn: (keyword: string) => battleApi.removeRankingKeyword(keyword),
    onSuccess: () => {
      toast.success('키워드가 삭제되었습니다')
      queryClient.invalidateQueries({ queryKey: ['ranking-keywords'] })
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`삭제 실패: ${error.response?.data?.detail || error.message}`)
    },
  })

  const handleRemoveKeyword = (keyword: string) => {
    setKeywordToDelete(keyword)
  }

  const confirmRemoveKeyword = () => {
    if (keywordToDelete) {
      removeKeyword.mutate(keywordToDelete)
      setKeywordToDelete(null)
    }
  }

  const handleEditKeyword = (keyword: string, category: string) => {
    setEditingKeyword({ keyword, category })
  }

  // 검색량 새로고침 mutation
  const refreshVolumes = useMutation({
    mutationFn: () => battleApi.refreshKeywordVolumes(),
    onSuccess: (data) => {
      toast.success(`검색량 업데이트: ${data.updated}개 키워드`)
      queryClient.invalidateQueries({ queryKey: ['ranking-keywords'] })
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`검색량 조회 실패: ${error.response?.data?.detail || error.message}`)
    },
  })

  // 목표 순위 업데이트 mutation
  const updateTargetRank = useMutation({
    mutationFn: ({ keyword, targetRank }: { keyword: string; targetRank: number }) =>
      battleApi.updateTargetRank(keyword, targetRank),
    onSuccess: () => {
      toast.success('목표 순위가 업데이트되었습니다')
      queryClient.invalidateQueries({ queryKey: ['ranking-keywords'] })
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`목표 순위 업데이트 실패: ${error.response?.data?.detail || error.message}`)
    },
  })

  const handleUpdateTargetRank = (keyword: string, targetRank: number) => {
    updateTargetRank.mutate({ keyword, targetRank })
  }

  const handleRefreshVolumes = () => {
    refreshVolumes.mutate()
  }

  const handleRunScan = () => {
    runScan.mutate()
  }

  const handleMissionComplete = () => {
    toast.success('순위 스캔이 완료되었습니다')
    setScanningModule(null)
    queryClient.invalidateQueries({ queryKey: ['ranking-keywords'] })
    queryClient.invalidateQueries({ queryKey: ['ranking-trends'] })
    queryClient.invalidateQueries({ queryKey: ['competitor-vitals'] })
  }

  const handleMissionStop = () => {
    toast.info('순위 스캔이 중지되었습니다')
    setScanningModule(null)
  }

  const handleRefreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ['ranking-keywords'] })
    queryClient.invalidateQueries({ queryKey: ['ranking-trends'] })
    queryClient.invalidateQueries({ queryKey: ['competitor-vitals'] })
  }

  // 순위 키워드 타입 정의
  interface RankingKeyword {
    keyword: string
    current_rank: number
    rank_change: number
    target_rank: number
    category: string
  }

  // 통계 계산 (메모이제이션)
  const stats = useMemo(() => ({
    total: rankingKeywords?.length || 0,
    improving: rankingKeywords?.filter((k: RankingKeyword) => k.rank_change > 0).length || 0,
    declining: rankingKeywords?.filter((k: RankingKeyword) => k.rank_change < 0).length || 0,
    stable: rankingKeywords?.filter((k: RankingKeyword) => k.rank_change === 0).length || 0,
    top10: rankingKeywords?.filter((k: RankingKeyword) => k.current_rank <= 10).length || 0,
  }), [rankingKeywords])

  // [Phase D-2] 선택된 키워드의 context 정보 계산
  const keywordContext = useMemo(() => {
    if (!keywordFilter || !rankingKeywords) return undefined

    const kw = rankingKeywords.find((k: RankingKeyword) => k.keyword === keywordFilter)
    if (!kw) return undefined

    return {
      currentRank: kw.current_rank,
      targetRank: kw.target_rank,
      trend: kw.rank_change > 0 ? 'up' as const :
             kw.rank_change < 0 ? 'down' as const : 'stable' as const,
    }
  }, [keywordFilter, rankingKeywords])

  const isScanning = scanningModule !== null || runScan.isPending

  if (keywordsLoading) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold mb-2">⚔️ Battle Intelligence</h1>
            <p className="text-muted-foreground">네이버 플레이스 순위 추적 및 경쟁 분석</p>
          </div>
        </div>
        <SkeletonStatsGrid cards={5} />
        <div className="bg-card rounded-lg border border-border p-6">
          <SkeletonChart height="h-80" />
        </div>
      </div>
    )
  }

  if (keywordsError) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <ErrorState
          title="키워드 로드 실패"
          message="순위 추적 키워드를 불러오는데 실패했습니다."
          onRetry={() => refetchKeywords()}
        />
      </div>
    )
  }

  return (
    <PageTransition>
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold mb-2">⚔️ Battle Intelligence</h1>
          <p className="text-muted-foreground">
            네이버 플레이스 순위 추적 및 경쟁 분석
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {isScanning ? (
            <Button
              variant="danger"
              onClick={async () => {
                if (scanningModule) {
                  await hudApi.stopMission(scanningModule)
                  handleMissionStop()
                }
              }}
              icon={<Square size={16} />}
            >
              스캔 중지
            </Button>
          ) : (
            <Button
              variant="primary"
              onClick={handleRunScan}
              icon={<Play size={16} />}
            >
              순위 스캔
            </Button>
          )}
          {/* Excel 내보내기 버튼 */}
          <Button
            variant="success"
            onClick={() => {
              exportApi.downloadRankHistory({
                keyword: keywordFilter || undefined
              })
            }}
            icon={<Download size={16} />}
            title="순위 히스토리를 Excel로 내보내기"
          >
            Excel 내보내기
          </Button>
          <Button
            variant="outline"
            onClick={handleRefreshAll}
            icon={<RefreshCw size={16} />}
          >
            새로고침
          </Button>
          <Button
            variant="primary"
            onClick={() => setShowAddModal(true)}
            icon={<Plus size={16} />}
          >
            키워드 추가
          </Button>
        </div>
      </div>

      {/* 터미널 실행 가이드 */}
      <TerminalGuide commands={getPageCommands('battle')} />

      {/* 실시간 스캔 진행 상황 */}
      {scanningModule && (
        <MissionProgress
          moduleName={scanningModule}
          missionName="순위 스캔"
          onComplete={handleMissionComplete}
          onStop={handleMissionStop}
        />
      )}

      {/* 통계 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="bg-card rounded-lg border border-border p-4">
          <div className="text-sm text-muted-foreground mb-1">총 추적 키워드</div>
          <div className="text-3xl font-bold">{stats.total}</div>
        </div>
        <div className="bg-card rounded-lg border border-border p-4">
          <div className="text-sm text-muted-foreground mb-1">Top 10 진입</div>
          <div className="text-3xl font-bold text-primary">{stats.top10}</div>
        </div>
        <div className="bg-card rounded-lg border border-border p-4">
          <div className="text-sm text-muted-foreground mb-1">📈 순위 상승</div>
          <div className="text-3xl font-bold text-green-500">{stats.improving}</div>
        </div>
        <div className="bg-card rounded-lg border border-border p-4">
          <div className="text-sm text-muted-foreground mb-1">📉 순위 하락</div>
          <div className="text-3xl font-bold text-red-500">{stats.declining}</div>
        </div>
        <div className="bg-card rounded-lg border border-border p-4">
          <div className="text-sm text-muted-foreground mb-1">➡️ 순위 유지</div>
          <div className="text-3xl font-bold text-blue-500">{stats.stable}</div>
        </div>
      </div>

      {/* 탭 네비게이션 */}
      <div className="bg-card rounded-lg border border-border">
        <div className="border-b border-border">
          <nav className="flex">
            {[
              { id: 'trends', label: '📈 순위 트렌드', icon: '📈' },
              { id: 'forecast', label: '🔮 순위 예측', icon: '🔮' },
              { id: 'alerts', label: '🚨 하락 알림', icon: '🚨', badge: rankDropAlerts?.alerts?.length || 0 },
              { id: 'keywords', label: '🎯 추적 키워드', icon: '🎯' },
              { id: 'competitors', label: '💪 경쟁사 활력', icon: '💪' },
              { id: 'insights', label: '📊 경쟁 인사이트', icon: '📊' },
              { id: 'local-seo', label: '📍 Local SEO', icon: '📍' },
            ].map((tab) => (
              <button
                key={tab.id}
                role="tab"
                aria-selected={activeTab === tab.id}
                aria-controls={`tabpanel-${tab.id}`}
                onClick={() => setActiveTab(tab.id)}
                className={`px-6 py-4 font-medium transition-colors relative ${
                  activeTab === tab.id
                    ? 'text-primary'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {tab.label}
                {'badge' in tab && (tab.badge ?? 0) > 0 && (
                  <span className="ml-2 px-1.5 py-0.5 text-xs bg-red-500 text-white rounded-full">
                    {tab.badge}
                  </span>
                )}
                {activeTab === tab.id && (
                  <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
                )}
              </button>
            ))}
          </nav>
        </div>

        <div className="p-6">
          {/* 순위 트렌드 탭 */}
          {activeTab === 'trends' && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-bold">📈 순위 트렌드</h2>
                  {keywordFilter && (
                    <div className="flex items-center gap-2 px-3 py-1 bg-primary/10 text-primary rounded-full text-sm">
                      <span>🔍 {keywordFilter}</span>
                      <IconButton
                        icon={<span>✕</span>}
                        onClick={() => setKeywordFilter('')}
                        size="xs"
                        title="필터 해제"
                        className="hover:text-primary/70"
                      />
                    </div>
                  )}
                  {/* [Phase D-2] 인사이트 버튼 */}
                  {keywordFilter && (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => setShowInsightPanel(true)}
                      className="bg-gradient-to-r from-purple-500 to-indigo-500"
                    >
                      💡 인사이트
                    </Button>
                  )}
                  {/* [Phase D-3] 라이프사이클 버튼 */}
                  {keywordFilter && (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => setShowLifecycleView(true)}
                      className="bg-gradient-to-r from-cyan-500 to-teal-500"
                    >
                      📅 라이프사이클
                    </Button>
                  )}
                  {/* [Phase E-1] KeywordHub 버튼 */}
                  {keywordFilter && (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => setShowKeywordHub(true)}
                      className="bg-gradient-to-r from-amber-500 to-orange-500"
                    >
                      🎯 Hub
                    </Button>
                  )}
                </div>
                <select
                  value={selectedPeriod}
                  onChange={(e) => setSelectedPeriod(Number(e.target.value))}
                  className="px-3 py-2 bg-background border border-border rounded-md"
                >
                  <option value={7}>최근 7일</option>
                  <option value={14}>최근 14일</option>
                  <option value={30}>최근 30일</option>
                </select>
              </div>
              {trendsLoading ? (
                <SkeletonChart height="h-80" />
              ) : trendsError ? (
                <ErrorState
                  title="트렌드 로드 실패"
                  message="순위 트렌드 데이터를 불러오는데 실패했습니다."
                  onRetry={() => refetchTrends()}
                />
              ) : (
                <RankingTrends trends={trends} rankingKeywords={rankingKeywords} />
              )}
            </div>
          )}

          {/* [Phase 4.0] 순위 예측 탭 */}
          {activeTab === 'forecast' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold">🔮 순위 예측 (7일 후)</h2>
                <div className="text-sm text-muted-foreground">
                  최근 {selectedPeriod}일 데이터 기반 선형 회귀 분석
                </div>
              </div>

              {forecastLoading ? (
                <SkeletonList items={5} />
              ) : !rankingForecast?.forecasts?.length ? (
                <EmptyState
                  type="initial"
                  icon="🔮"
                  title="예측 데이터가 부족합니다"
                  description="순위 예측을 위해서는 최소 3일 이상의 순위 스캔 데이터가 필요합니다."
                  suggestion="매일 순위 스캔을 실행하면 더 정확한 예측이 가능합니다."
                  actions={[
                    {
                      label: '순위 스캔 시작',
                      onClick: handleRunScan,
                      variant: 'primary',
                      disabled: isScanning,
                    }
                  ]}
                  compact
                />
              ) : (
                <>
                  {/* 요약 통계 */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4 text-center">
                      <div className="text-2xl font-bold text-green-500">
                        {rankingForecast.summary.improving}
                      </div>
                      <div className="text-xs text-muted-foreground">상승 예상</div>
                    </div>
                    <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 text-center">
                      <div className="text-2xl font-bold text-red-500">
                        {rankingForecast.summary.declining}
                      </div>
                      <div className="text-xs text-muted-foreground">하락 예상</div>
                    </div>
                    <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-4 text-center">
                      <div className="text-2xl font-bold text-blue-500">
                        {rankingForecast.summary.stable}
                      </div>
                      <div className="text-xs text-muted-foreground">유지 예상</div>
                    </div>
                  </div>

                  {/* 예측 카드 목록 */}
                  <div className="space-y-3">
                    {rankingForecast.forecasts.map((forecast: any) => (
                      <div
                        key={forecast.keyword}
                        className={`bg-card rounded-lg border p-4 ${
                          forecast.on_track
                            ? 'border-green-500/30'
                            : 'border-yellow-500/30'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-3">
                          <div className="font-semibold">{forecast.keyword}</div>
                          <div className={`px-2 py-0.5 rounded text-xs font-medium ${
                            forecast.trend === 'improving'
                              ? 'bg-green-500/20 text-green-500'
                              : forecast.trend === 'declining'
                              ? 'bg-red-500/20 text-red-500'
                              : 'bg-blue-500/20 text-blue-500'
                          }`}>
                            {forecast.trend === 'improving' ? '📈 상승세' :
                             forecast.trend === 'declining' ? '📉 하락세' : '➡️ 유지'}
                          </div>
                        </div>

                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                          <div>
                            <div className="text-xs text-muted-foreground mb-1">현재</div>
                            <div className="text-xl font-bold">{forecast.current_rank}위</div>
                          </div>
                          <div>
                            <div className="text-xs text-muted-foreground mb-1">7일 후 예측</div>
                            <div className={`text-xl font-bold ${
                              forecast.rank_change < 0 ? 'text-green-500' :
                              forecast.rank_change > 0 ? 'text-red-500' : ''
                            }`}>
                              {forecast.predicted_rank}위
                              {forecast.rank_change !== 0 && (
                                <span className="text-sm ml-1">
                                  ({forecast.rank_change > 0 ? '+' : ''}{forecast.rank_change})
                                </span>
                              )}
                            </div>
                            {/* 신뢰 구간 표시 (새 API 필드) */}
                            {forecast.predicted_lower && forecast.predicted_upper && (
                              <div className="text-xs text-muted-foreground mt-1">
                                예측 범위: {forecast.predicted_lower}~{forecast.predicted_upper}위
                              </div>
                            )}
                          </div>
                          <div>
                            <div className="text-xs text-muted-foreground mb-1">목표</div>
                            <div className="text-xl font-bold">{forecast.target_rank}위</div>
                          </div>
                          <div>
                            <div className="text-xs text-muted-foreground mb-1">신뢰도</div>
                            <div className={`text-xl font-bold ${
                              forecast.confidence >= 70 ? 'text-green-500' :
                              forecast.confidence >= 40 ? 'text-yellow-500' :
                              'text-gray-500'
                            }`}>
                              {forecast.confidence}%
                            </div>
                          </div>
                        </div>

                        {/* 목표 달성 상태 & 트렌드 보기 */}
                        <div className="mt-3 pt-3 border-t border-border">
                          <div className="flex items-center justify-between text-sm">
                            <span className="text-muted-foreground">목표 달성 예측</span>
                            <span className={forecast.on_track ? 'text-green-500' : 'text-yellow-500'}>
                              {forecast.on_track ? '✅ 목표 달성 가능' : '⚠️ 추가 노력 필요'}
                            </span>
                          </div>
                          <div className="flex items-center justify-between mt-2">
                            <div className="text-xs text-muted-foreground">
                              일일 변화율: {forecast.slope > 0 ? '+' : ''}{forecast.slope} · 데이터 {forecast.data_points}개
                              {forecast.model_factors?.acceleration !== undefined && (
                                <span className="ml-2">
                                  가속도: {forecast.model_factors.acceleration > 0 ? '+' : ''}{forecast.model_factors.acceleration}
                                </span>
                              )}
                            </div>
                            <Button
                              variant="ghost"
                              size="xs"
                              onClick={() => handleViewTrend(forecast.keyword)}
                            >
                              📈 트렌드 보기
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* [P2-3] 예측 정확도 검증 섹션 */}
                  {forecastAccuracy?.accuracy_results?.length > 0 && (
                    <div className="mt-8 pt-6 border-t border-border">
                      <h3 className="text-lg font-semibold mb-4">📊 예측 정확도 검증 (7일 전 예측 vs 실제)</h3>

                      {/* 정확도 요약 카드 */}
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                        <div className="bg-muted/50 rounded-lg p-4 text-center">
                          <p className="text-sm text-muted-foreground">평균 정확도</p>
                          <p className={`text-2xl font-bold ${
                            forecastAccuracy.summary.avg_accuracy_pct >= 80 ? 'text-green-500' :
                            forecastAccuracy.summary.avg_accuracy_pct >= 60 ? 'text-yellow-500' :
                            'text-red-500'
                          }`}>
                            {forecastAccuracy.summary.avg_accuracy_pct}%
                          </p>
                        </div>
                        <div className="bg-muted/50 rounded-lg p-4 text-center">
                          <p className="text-sm text-muted-foreground">정확 예측 비율</p>
                          <p className="text-2xl font-bold text-primary">
                            {forecastAccuracy.summary.accuracy_rate}%
                          </p>
                          <p className="text-xs text-muted-foreground">±3 이내</p>
                        </div>
                        <div className="bg-muted/50 rounded-lg p-4 text-center">
                          <p className="text-sm text-muted-foreground">평균 오차</p>
                          <p className="text-2xl font-bold">
                            ±{forecastAccuracy.summary.avg_error}
                          </p>
                          <p className="text-xs text-muted-foreground">순위 차이</p>
                        </div>
                        <div className="bg-muted/50 rounded-lg p-4 text-center">
                          <p className="text-sm text-muted-foreground">완벽 예측</p>
                          <p className="text-2xl font-bold text-green-500">
                            {forecastAccuracy.summary.perfect_predictions}
                          </p>
                          <p className="text-xs text-muted-foreground">±1 이내</p>
                        </div>
                      </div>

                      {/* 상세 결과 테이블 */}
                      <div className="bg-card rounded-lg border border-border overflow-hidden">
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead className="bg-muted/50">
                              <tr>
                                <th className="px-4 py-3 text-left font-medium">키워드</th>
                                <th className="px-4 py-3 text-center font-medium">예측 순위</th>
                                <th className="px-4 py-3 text-center font-medium">실제 순위</th>
                                <th className="px-4 py-3 text-center font-medium">오차</th>
                                <th className="px-4 py-3 text-center font-medium">정확도</th>
                                <th className="px-4 py-3 text-center font-medium">신뢰도</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border">
                              {forecastAccuracy.accuracy_results.slice(0, 10).map((result: any) => (
                                <tr key={result.keyword} className={result.is_accurate ? 'bg-green-500/5' : ''}>
                                  <td className="px-4 py-3 font-medium">{result.keyword}</td>
                                  <td className="px-4 py-3 text-center">{result.predicted_rank}위</td>
                                  <td className="px-4 py-3 text-center font-bold">{result.actual_rank}위</td>
                                  <td className={`px-4 py-3 text-center font-medium ${
                                    result.abs_error <= 1 ? 'text-green-500' :
                                    result.abs_error <= 3 ? 'text-yellow-500' :
                                    'text-red-500'
                                  }`}>
                                    {result.error > 0 ? '+' : ''}{result.error}
                                  </td>
                                  <td className={`px-4 py-3 text-center font-medium ${
                                    result.accuracy_pct >= 90 ? 'text-green-500' :
                                    result.accuracy_pct >= 70 ? 'text-yellow-500' :
                                    'text-red-500'
                                  }`}>
                                    {result.accuracy_pct}%
                                  </td>
                                  <td className="px-4 py-3 text-center text-muted-foreground">
                                    {result.confidence}%
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>

                      <p className="text-xs text-muted-foreground mt-3">
                        💡 7일 전 시점의 데이터로 오늘의 순위를 예측하고, 실제 순위와 비교한 결과입니다.
                        정확도가 높을수록 예측 모델의 신뢰성이 높습니다.
                      </p>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* [Phase 6.1] 순위 하락 알림 탭 */}
          {activeTab === 'alerts' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold">🚨 순위 하락 알림</h2>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => refetchAlerts()}
                >
                  🔄 새로고침
                </Button>
              </div>

              {alertsLoading ? (
                <SkeletonList items={5} />
              ) : alertsError ? (
                <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-8 text-center">
                  <p className="text-4xl mb-2">❌</p>
                  <p className="font-medium text-lg mb-1">알림 데이터를 불러올 수 없습니다</p>
                  <p className="text-sm text-muted-foreground mb-3">
                    네트워크 오류가 발생했습니다. 다시 시도해주세요.
                  </p>
                  <Button
                    variant="primary"
                    onClick={() => refetchAlerts()}
                  >
                    🔄 다시 시도
                  </Button>
                </div>
              ) : !rankDropAlerts?.alerts?.length ? (
                <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-8 text-center">
                  <p className="text-4xl mb-2">✅</p>
                  <p className="font-medium text-lg mb-1">순위 하락 알림 없음</p>
                  <p className="text-sm text-muted-foreground">
                    모든 키워드가 안정적으로 유지되고 있습니다
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* 요약 통계 */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 text-center">
                      <div className="text-2xl font-bold text-red-500">
                        {rankDropAlerts.summary?.total_alerts || rankDropAlerts.alerts.length}
                      </div>
                      <div className="text-xs text-muted-foreground">하락 키워드</div>
                    </div>
                    <div className="bg-orange-500/10 border border-orange-500/20 rounded-lg p-4 text-center">
                      <div className="text-2xl font-bold text-orange-500">
                        {rankDropAlerts.summary?.critical_drops || rankDropAlerts.alerts.filter((a: any) => a.severity === 'critical').length}
                      </div>
                      <div className="text-xs text-muted-foreground">심각한 하락 (5+)</div>
                    </div>
                    <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-4 text-center">
                      <div className="text-2xl font-bold text-yellow-500">
                        {rankDropAlerts.summary?.avg_drop ||
                          Math.round(rankDropAlerts.alerts.reduce((sum: number, a: any) => sum + a.rank_drop, 0) / rankDropAlerts.alerts.length)}
                      </div>
                      <div className="text-xs text-muted-foreground">평균 하락폭</div>
                    </div>
                    <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-4 text-center">
                      <div className="text-2xl font-bold text-blue-500">
                        {rankDropAlerts.summary?.keywords_outside_top10 ||
                          rankDropAlerts.alerts.filter((a: any) => a.current_rank > 10).length}
                      </div>
                      <div className="text-xs text-muted-foreground">Top 10 이탈</div>
                    </div>
                  </div>

                  {/* 알림 목록 */}
                  <div className="space-y-3">
                    {rankDropAlerts.alerts.map((alert: any, index: number) => (
                      <div
                        key={`${alert.keyword}-${index}`}
                        className={`bg-card rounded-lg border p-4 ${
                          alert.severity === 'critical'
                            ? 'border-red-500/50 bg-red-500/5'
                            : alert.severity === 'warning'
                            ? 'border-orange-500/50 bg-orange-500/5'
                            : 'border-yellow-500/50 bg-yellow-500/5'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-3">
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                              alert.severity === 'critical'
                                ? 'bg-red-500 text-white'
                                : alert.severity === 'warning'
                                ? 'bg-orange-500 text-white'
                                : 'bg-yellow-500 text-black'
                            }`}>
                              {alert.severity === 'critical' ? '🚨 심각' :
                               alert.severity === 'warning' ? '⚠️ 주의' : '📉 하락'}
                            </span>
                            <span className="font-semibold">{alert.keyword}</span>
                          </div>
                          <Button
                            variant="ghost"
                            size="xs"
                            onClick={() => {
                              setKeywordFilter(alert.keyword)
                              setActiveTab('trends')
                            }}
                          >
                            📈 트렌드 보기
                          </Button>
                        </div>

                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                          <div>
                            <div className="text-xs text-muted-foreground mb-1">이전 순위</div>
                            <div className="text-lg font-bold">{alert.previous_rank}위</div>
                          </div>
                          <div>
                            <div className="text-xs text-muted-foreground mb-1">현재 순위</div>
                            <div className="text-lg font-bold text-red-500">{alert.current_rank}위</div>
                          </div>
                          <div>
                            <div className="text-xs text-muted-foreground mb-1">하락폭</div>
                            <div className="text-lg font-bold text-red-500">-{alert.rank_drop}</div>
                          </div>
                          <div>
                            <div className="text-xs text-muted-foreground mb-1">목표</div>
                            <div className="text-lg font-bold">{alert.target_rank || '-'}위</div>
                          </div>
                        </div>

                        {/* 트렌드 정보 */}
                        {alert.trend && (
                          <div className="mt-3 pt-3 border-t border-border">
                            <div className="flex items-center justify-between text-sm">
                              <span className="text-muted-foreground">7일 트렌드</span>
                              <span className={`font-medium ${
                                alert.trend === 'declining' ? 'text-red-500' :
                                alert.trend === 'improving' ? 'text-green-500' :
                                'text-yellow-500'
                              }`}>
                                {alert.trend === 'declining' ? '📉 지속 하락세' :
                                 alert.trend === 'improving' ? '📈 회복 중' :
                                 '➡️ 변동 중'}
                              </span>
                            </div>
                            {alert.consecutive_drops && (
                              <div className="text-xs text-muted-foreground mt-1">
                                연속 {alert.consecutive_drops}회 하락
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  <p className="text-xs text-muted-foreground">
                    💡 3순위 이상 하락한 키워드만 표시됩니다. 순위 스캔 후 자동 업데이트됩니다.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* 추적 키워드 탭 */}
          {activeTab === 'keywords' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold">🎯 추적 중인 키워드</h2>
                <div className="flex items-center gap-3">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={handleRefreshVolumes}
                    loading={refreshVolumes.isPending}
                    title="검색량이 0인 키워드들의 검색량을 Naver API로 조회합니다"
                  >
                    📊 검색량 새로고침
                  </Button>
                  <span className="text-sm text-muted-foreground">
                    {rankingKeywords?.length || 0}개 키워드 추적 중
                  </span>
                </div>
              </div>
              <RankingKeywordsList
                keywords={rankingKeywords || []}
                onRemove={handleRemoveKeyword}
                onEdit={handleEditKeyword}
                onUpdateTargetRank={handleUpdateTargetRank}
              />
            </div>
          )}

          {/* 경쟁사 활력 탭 */}
          {activeTab === 'competitors' && (
            <div className="space-y-4">
              <h2 className="text-xl font-bold">💪 경쟁사 활력 지표</h2>
              {vitalsLoading ? (
                <SkeletonList items={4} />
              ) : vitalsError ? (
                <ErrorState
                  title="경쟁사 정보 로드 실패"
                  message="경쟁사 활력 데이터를 불러오는데 실패했습니다."
                  onRetry={() => refetchVitals()}
                />
              ) : !competitorVitals || Object.keys(competitorVitals).length === 0 ? (
                <div className="bg-muted/50 rounded-lg p-8 text-center">
                  <p className="text-4xl mb-2">💪</p>
                  <p className="font-medium text-lg mb-1">경쟁사 활력 데이터가 없습니다</p>
                  <p className="text-sm text-muted-foreground mb-4">순위 스캔을 실행하면 경쟁사 리뷰 정보가 수집됩니다.</p>
                  <Button
                    variant="primary"
                    onClick={handleRunScan}
                    loading={runScan.isPending || !!scanningModule}
                  >
                    🔍 순위 스캔 시작
                  </Button>
                </div>
              ) : (
                <>
                  <CompetitorVitals vitals={competitorVitals} />
                  {/* [Phase 6.2] 경쟁사 순위 비교 */}
                  <CompetitorRankingCompare />
                </>
              )}
            </div>
          )}

          {/* [Phase 5.2] 경쟁 인사이트 탭 */}
          {activeTab === 'insights' && (
            <div className="space-y-4">
              <h2 className="text-xl font-bold">📊 경쟁 인사이트</h2>
              <CompetitorInsights />
            </div>
          )}

          {/* [Phase 5.3] Local SEO 대시보드 탭 */}
          {activeTab === 'local-seo' && (
            <LocalSeoDashboard />
          )}
        </div>
      </div>

      {/* 키워드 추가 모달 */}
      {showAddModal && (
        <AddKeywordModal
          onClose={() => setShowAddModal(false)}
          onSuccess={() => {
            setShowAddModal(false)
            queryClient.invalidateQueries({ queryKey: ['ranking-keywords'] })
          }}
        />
      )}

      {/* 키워드 수정 모달 */}
      {editingKeyword && (
        <EditKeywordModal
          keyword={editingKeyword.keyword}
          currentCategory={editingKeyword.category}
          onClose={() => setEditingKeyword(null)}
          onSuccess={() => {
            toast.success('키워드가 수정되었습니다')
            setEditingKeyword(null)
            queryClient.invalidateQueries({ queryKey: ['ranking-keywords'] })
          }}
        />
      )}

      {/* 키워드 삭제 확인 모달 */}
      <ConfirmModal
        isOpen={keywordToDelete !== null}
        onClose={() => setKeywordToDelete(null)}
        onConfirm={confirmRemoveKeyword}
        title="키워드 삭제"
        message={`"${keywordToDelete}" 순위 추적을 중지하시겠습니까? 기존 순위 기록은 유지됩니다.`}
        confirmText="삭제"
        cancelText="취소"
        variant="danger"
        loading={removeKeyword.isPending}
      />

      {/* [Phase D-2] Context Insight Panel */}
      {showInsightPanel && keywordFilter && (
        <ContextInsightPanel
          keyword={keywordFilter}
          onClose={() => setShowInsightPanel(false)}
          context={keywordContext}
          onShowLifecycle={() => setShowLifecycleView(true)}
        />
      )}

      {/* [Phase D-3] Keyword Lifecycle View */}
      {showLifecycleView && keywordFilter && (
        <KeywordLifecycleView
          keyword={keywordFilter}
          onClose={() => setShowLifecycleView(false)}
        />
      )}

      {/* [Phase E-1] Keyword Hub */}
      {showKeywordHub && keywordFilter && (
        <KeywordHub
          keyword={keywordFilter}
          onClose={() => setShowKeywordHub(false)}
        />
      )}
    </div>
    </PageTransition>
  )
}

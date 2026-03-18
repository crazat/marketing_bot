import { useState, useEffect, useMemo, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { pathfinderApi, hudApi } from '@/services/api'
import { exportToCSV, KEYWORD_EXPORT_COLUMNS } from '@/utils/export'
import KeywordTable from '@/components/pathfinder/KeywordTable'
import PathfinderStats from '@/components/pathfinder/PathfinderStats'
import PathfinderControls from '@/components/pathfinder/PathfinderControls'
import KeywordClusters from '@/components/pathfinder/KeywordClusters'
import TopKeiKeywords from '@/components/pathfinder/TopKeiKeywords'
import KeywordAnalysisTab from '@/components/pathfinder/KeywordAnalysisTab'
import KeywordUtilizationTab from '@/components/pathfinder/KeywordUtilizationTab'
import KeywordHistoryTab from '@/components/pathfinder/KeywordHistoryTab'
import LiveLogViewer from '@/components/pathfinder/LiveLogViewer'
import { SkeletonStatsGrid, SkeletonTable } from '@/components/ui/Skeleton'
import EmptyState from '@/components/ui/EmptyState'
import MissionProgress from '@/components/ui/MissionProgress'
import ErrorState from '@/components/ui/ErrorState'
import TabNavigation from '@/components/ui/TabNavigation'
import SearchInput from '@/components/ui/SearchInput'
import { useToast } from '@/components/ui/Toast'
import { DataFreshness } from '@/components/ui'
import { useUrlState } from '@/hooks/useUrlState'
import PageTransition from '@/components/PageTransition'
import { TerminalGuide } from '@/components/ui/TerminalGuide'
import { getPageCommands } from '@/utils/terminalCommands'
import Button, { IconButton } from '@/components/ui/Button'
import { Download, Save, RotateCcw } from 'lucide-react'

// 필터 프리셋 타입
interface FilterPreset {
  id: string
  name: string
  grade: string
  category: string
  source: string
  trend: string
  createdAt: string
}

const PRESETS_STORAGE_KEY = 'pathfinder-filter-presets'

// 프리셋 저장/불러오기 헬퍼
const loadPresets = (): FilterPreset[] => {
  try {
    const saved = localStorage.getItem(PRESETS_STORAGE_KEY)
    return saved ? JSON.parse(saved) : []
  } catch {
    return []
  }
}

const savePresets = (presets: FilterPreset[]) => {
  localStorage.setItem(PRESETS_STORAGE_KEY, JSON.stringify(presets))
}

export default function Pathfinder() {
  // [Phase 5.0] URL 상태 관리
  const [activeTab, setActiveTab] = useUrlState<string>('tab', { defaultValue: 'collection' })
  const [gradeFilter, setGradeFilter] = useUrlState<string>('grade', { defaultValue: '' })
  const [categoryFilter, setCategoryFilter] = useUrlState<string>('category', { defaultValue: '' })
  const [sourceFilter, setSourceFilter] = useUrlState<string>('source', { defaultValue: '' })
  const [trendFilter, setTrendFilter] = useUrlState<string>('trend', { defaultValue: '' })

  // 로컬 상태
  const [selectedMode, setSelectedMode] = useState<'total_war' | 'legion'>('total_war')
  const [scanningModule, setScanningModule] = useState<string | null>(null)
  const [scanningName, setScanningName] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  // 필터 프리셋 상태
  const [presets, setPresets] = useState<FilterPreset[]>(() => loadPresets())
  const [showPresetInput, setShowPresetInput] = useState(false)
  const [presetName, setPresetName] = useState('')

  // [P1-2] 캘린더 아웃라인 상태
  const [expandedOutline, setExpandedOutline] = useState<number | null>(null)
  const [generatedOutlines, setGeneratedOutlines] = useState<Record<number, any>>({})

  // [P2-2] 캘린더 진행 트래킹 (localStorage)
  const CALENDAR_PROGRESS_KEY = 'pathfinder-calendar-progress'
  const [completedWeeks, setCompletedWeeks] = useState<Set<number>>(() => {
    try {
      const saved = localStorage.getItem(CALENDAR_PROGRESS_KEY)
      return saved ? new Set(JSON.parse(saved)) : new Set()
    } catch {
      return new Set()
    }
  })

  const toggleWeekComplete = useCallback((week: number) => {
    setCompletedWeeks(prev => {
      const next = new Set(prev)
      if (next.has(week)) {
        next.delete(week)
      } else {
        next.add(week)
      }
      localStorage.setItem(CALENDAR_PROGRESS_KEY, JSON.stringify([...next]))
      return next
    })
  }, [])

  const queryClient = useQueryClient()
  const toast = useToast()

  // 프리셋 저장
  const handleSavePreset = useCallback(() => {
    if (!presetName.trim()) {
      toast.error('프리셋 이름을 입력하세요')
      return
    }

    const newPreset: FilterPreset = {
      id: Date.now().toString(),
      name: presetName.trim(),
      grade: gradeFilter,
      category: categoryFilter,
      source: sourceFilter,
      trend: trendFilter,
      createdAt: new Date().toISOString()
    }

    const updated = [...presets, newPreset]
    setPresets(updated)
    savePresets(updated)
    setPresetName('')
    setShowPresetInput(false)
    toast.success(`"${newPreset.name}" 프리셋이 저장되었습니다`)
  }, [presetName, gradeFilter, categoryFilter, sourceFilter, trendFilter, presets, toast])

  // 프리셋 적용
  const handleApplyPreset = useCallback((preset: FilterPreset) => {
    setGradeFilter(preset.grade)
    setCategoryFilter(preset.category)
    setSourceFilter(preset.source)
    setTrendFilter(preset.trend)
    toast.success(`"${preset.name}" 프리셋이 적용되었습니다`)
  }, [setGradeFilter, setCategoryFilter, setSourceFilter, setTrendFilter, toast])

  // 프리셋 삭제
  const handleDeletePreset = useCallback((presetId: string) => {
    const updated = presets.filter(p => p.id !== presetId)
    setPresets(updated)
    savePresets(updated)
    toast.info('프리셋이 삭제되었습니다')
  }, [presets, toast])

  // 필터 객체
  const filters = useMemo(() => ({
    grade: gradeFilter,
    category: categoryFilter,
    source: sourceFilter,
    trend_status: trendFilter
  }), [gradeFilter, categoryFilter, sourceFilter, trendFilter])

  // 통계 조회
  const {
    data: stats,
    isLoading: statsLoading,
    isError: statsError,
    dataUpdatedAt: statsUpdatedAt,
    refetch: refetchStats,
    isFetching: statsRefreshing,
  } = useQuery({
    queryKey: ['pathfinder-stats'],
    queryFn: () => pathfinderApi.getStats(true),
    staleTime: 60000, // 1분간 캐시
    retry: 2,
  })

  // 키워드 목록 조회
  const {
    data: keywords,
    isLoading: keywordsLoading,
    isError: keywordsError,
    refetch: refetchKeywords,
    isFetching: keywordsRefreshing,
  } = useQuery({
    queryKey: ['pathfinder-keywords', filters],
    queryFn: () => pathfinderApi.getKeywords({
      grade: filters.grade || undefined,
      category: filters.category || undefined,
      source: filters.source || undefined,
      trend_status: filters.trend_status || undefined,
      limit: 500
    }),
    staleTime: 60000, // [Phase 7] 30초 → 60초
    retry: 2,
  })

  // [Phase 5.0] 키워드 검색 필터링
  const filteredKeywords = useMemo(() => {
    if (!keywords) return []
    if (!searchQuery.trim()) return keywords

    const query = searchQuery.toLowerCase()
    return keywords.filter((kw: any) =>
      kw.keyword.toLowerCase().includes(query) ||
      kw.category?.toLowerCase().includes(query) ||
      kw.source?.toLowerCase().includes(query)
    )
  }, [keywords, searchQuery])

  // 클러스터 조회 (Lazy Loading - 탭 활성화 시에만 로드)
  const { data: clusters, isError: clustersError, refetch: refetchClusters } = useQuery({
    queryKey: ['pathfinder-clusters'],
    queryFn: pathfinderApi.getClusters,
    enabled: activeTab === 'clusters',
    staleTime: 120000, // 2분간 캐시
    retry: 2,
  })

  // 콘텐츠 캘린더 조회
  const { data: contentCalendar, isLoading: calendarLoading, isError: calendarError, refetch: refetchCalendar } = useQuery({
    queryKey: ['content-calendar'],
    queryFn: () => pathfinderApi.getContentCalendar(12),
    enabled: activeTab === 'calendar',
    staleTime: 120000, // 2분간 캐시
    retry: 2,
  })

  // 실행 중인 모듈 조회 (페이지 로드 시 상태 복원)
  const { data: runningModules } = useQuery({
    queryKey: ['running-modules'],
    queryFn: () => hudApi.getRunningModules().catch(() => ({ running: [] })),
    refetchInterval: 30000, // 30초마다 확인 (서버 부하 감소)
    retry: 1,
  })

  // pathfinder 모듈이 실행 중이면 scanningModule 상태 복원
  useEffect(() => {
    if (!scanningModule && runningModules?.running) {
      if (runningModules.running.includes('pathfinder')) {
        setScanningModule('pathfinder')
        setScanningName('Total War')
      } else if (runningModules.running.includes('pathfinder_legion')) {
        setScanningModule('pathfinder_legion')
        setScanningName('LEGION MODE')
      }
    }
  }, [runningModules, scanningModule])

  // Pathfinder 실행 mutation (hudApi 사용)
  const runPathfinder = useMutation({
    mutationFn: (mode: 'total_war' | 'legion') => {
      const moduleName = mode === 'total_war' ? 'pathfinder' : 'pathfinder_legion'
      return hudApi.executeMission(moduleName)
    },
    onSuccess: (_data, mode) => {
      const moduleName = mode === 'total_war' ? 'pathfinder' : 'pathfinder_legion'
      const displayName = mode === 'total_war' ? 'Total War' : 'LEGION MODE'
      toast.success(`${displayName} 실행이 시작되었습니다`)
      setScanningModule(moduleName)
      setScanningName(displayName)
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`실행 실패: ${error.response?.data?.detail || error.message}`)
      setScanningModule(null)
      setScanningName('')
    },
  })

  const handleMissionComplete = () => {
    toast.success('키워드 수집이 완료되었습니다')
    setScanningModule(null)
    setScanningName('')
    queryClient.invalidateQueries({ queryKey: ['pathfinder-stats'] })
    queryClient.invalidateQueries({ queryKey: ['pathfinder-keywords'] })
    queryClient.invalidateQueries({ queryKey: ['pathfinder-clusters'] })
  }

  const handleMissionStop = () => {
    toast.info('키워드 수집이 중지되었습니다')
    setScanningModule(null)
    setScanningName('')
  }

  const handleRunPathfinder = (mode: 'total_war' | 'legion') => {
    runPathfinder.mutate(mode)
  }

  // [Phase 5.0] 필터 초기화
  const handleResetFilters = () => {
    setGradeFilter('')
    setCategoryFilter('')
    setSourceFilter('')
    setTrendFilter('')
    setSearchQuery('')
  }

  // 전체 키워드 일괄 내보내기
  const exportAllKeywords = useMutation({
    mutationFn: () => pathfinderApi.exportAllKeywords({
      grade: gradeFilter || undefined,
      category: categoryFilter || undefined
    }),
    onSuccess: (data) => {
      const timestamp = new Date().toISOString().slice(0, 10)
      const filterSuffix = gradeFilter ? `_${gradeFilter}` : ''
      exportToCSV(data, KEYWORD_EXPORT_COLUMNS, `all_keywords${filterSuffix}_${timestamp}.csv`)
      toast.success(`${data.length}개 키워드를 CSV로 내보냈습니다`)
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`내보내기 실패: ${error.response?.data?.detail || error.message}`)
    }
  })

  const handleExportAll = () => {
    exportAllKeywords.mutate()
  }

  // [P1-2] 아웃라인 생성 mutation
  const generateOutline = useMutation({
    mutationFn: ({ keywords, clusterName, category }: { keywords: string[]; clusterName?: string; category?: string }) =>
      pathfinderApi.generateOutline(keywords, clusterName, category),
    onSuccess: (data) => {
      if (data.success && data.outline) {
        // expandedOutline은 week 번호를 사용
        const weekNum = expandedOutline
        if (weekNum !== null) {
          setGeneratedOutlines(prev => ({ ...prev, [weekNum]: data.outline }))
        }
        toast.success('콘텐츠 아웃라인이 생성되었습니다')
      }
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`아웃라인 생성 실패: ${error.response?.data?.detail || error.message}`)
    }
  })

  const handleGenerateOutline = (week: number, keywords: string[], clusterName: string, category?: string) => {
    setExpandedOutline(week)
    generateOutline.mutate({ keywords, clusterName, category })
  }

  const hasActiveFilters = gradeFilter || categoryFilter || sourceFilter || trendFilter || searchQuery

  const isScanning = scanningModule !== null || runPathfinder.isPending

  return (
    <PageTransition>
    <div className="space-y-6">
      {/* 헤더 */}
      <div>
        <h1 className="text-3xl font-bold mb-2">🎯 Pathfinder V3</h1>
        <p className="text-muted-foreground">
          AI 기반 키워드 발굴 시스템 - SERP 분석 & 등급 기반
        </p>
      </div>

      {/* 실시간 로그 뷰어 */}
      <LiveLogViewer maxLines={300} />

      {/* 실시간 스캔 진행 상황 (기존 MissionProgress - 백업용) */}
      {scanningModule && (
        <MissionProgress
          moduleName={scanningModule}
          missionName={`Pathfinder ${scanningName}`}
          onComplete={handleMissionComplete}
          onStop={handleMissionStop}
        />
      )}

      {/* 통계 */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">키워드 통계</h2>
          <DataFreshness
            lastUpdated={statsUpdatedAt ? new Date(statsUpdatedAt) : null}
            onRefresh={() => {
              refetchStats()
              refetchKeywords()
            }}
            isRefreshing={statsRefreshing || keywordsRefreshing}
            compact
          />
        </div>
        {statsLoading ? (
          <SkeletonStatsGrid cards={6} />
        ) : statsError ? (
          <ErrorState
            title="통계 로드 실패"
            message="통계 데이터를 불러오는데 실패했습니다."
            onRetry={() => refetchStats()}
          />
        ) : (
          <PathfinderStats stats={stats} />
        )}
      </div>

      {/* 탭 네비게이션 */}
      <TabNavigation
        tabs={[
          { id: 'collection', label: '🚀 키워드 수집' },
          { id: 'analysis', label: '📊 키워드 분석' },
          { id: 'utilization', label: '✍️ 키워드 활용' },
          { id: 'history', label: '📜 히스토리' },
          { id: 'clusters', label: '📝 콘텐츠 클러스터' },
          { id: 'calendar', label: '📅 콘텐츠 캘린더' },
        ]}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        ariaLabel="Pathfinder 탭"
      />

      {/* 탭 컨텐츠 */}
      {activeTab === 'collection' && (
        <div className="space-y-6">{renderCollectionTab()}</div>
      )}

      {activeTab === 'analysis' && (
        <KeywordAnalysisTab stats={stats} />
      )}

      {activeTab === 'utilization' && (
        <KeywordUtilizationTab stats={stats} />
      )}

      {activeTab === 'history' && (
        <KeywordHistoryTab stats={stats} />
      )}

      {activeTab === 'clusters' && (
        <div className="space-y-6">{renderClustersTab()}</div>
      )}

      {activeTab === 'calendar' && (
        <div className="space-y-6">{renderCalendarTab()}</div>
      )}
    </div>
    </PageTransition>
  )

  // 키워드 수집 탭 렌더링
  function renderCollectionTab() {
    return (
      <>
        {/* 컨트롤 */}
        <PathfinderControls
          onRun={handleRunPathfinder}
          isRunning={isScanning}
          selectedMode={selectedMode}
          onModeChange={setSelectedMode}
        />

        {/* 터미널 실행 가이드 */}
        <TerminalGuide commands={getPageCommands('pathfinder')} />

        {/* 필터 */}
        <div className="bg-card rounded-lg border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">🔍 필터</h3>
            <div className="flex items-center gap-2">
              {hasActiveFilters && (
                <>
                  <Button
                    variant="ghost"
                    size="xs"
                    onClick={() => setShowPresetInput(true)}
                    icon={<Save size={14} />}
                  >
                    프리셋 저장
                  </Button>
                  <span className="text-border">|</span>
                  <Button
                    variant="ghost"
                    size="xs"
                    onClick={handleResetFilters}
                    icon={<RotateCcw size={14} />}
                  >
                    초기화
                  </Button>
                </>
              )}
            </div>
          </div>

          {/* 프리셋 저장 입력 */}
          {showPresetInput && (
            <div className="mb-4 p-3 bg-primary/5 border border-primary/20 rounded-lg">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={presetName}
                  onChange={(e) => setPresetName(e.target.value)}
                  placeholder="프리셋 이름 입력..."
                  className="flex-1 px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  onKeyDown={(e) => e.key === 'Enter' && handleSavePreset()}
                  autoFocus
                />
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleSavePreset}
                >
                  저장
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => { setShowPresetInput(false); setPresetName('') }}
                >
                  취소
                </Button>
              </div>
            </div>
          )}

          {/* 저장된 프리셋 목록 */}
          {presets.length > 0 && (
            <div className="mb-4">
              <p className="text-xs text-muted-foreground mb-2">저장된 프리셋:</p>
              <div className="flex flex-wrap gap-2">
                {presets.map((preset) => (
                  <div
                    key={preset.id}
                    className="group flex items-center gap-1 px-3 py-1.5 bg-muted rounded-full text-sm hover:bg-accent transition-colors"
                  >
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={() => handleApplyPreset(preset)}
                      title={`등급: ${preset.grade || '전체'}, 카테고리: ${preset.category || '전체'}, 소스: ${preset.source || '전체'}, 트렌드: ${preset.trend || '전체'}`}
                      className="p-0 h-auto hover:text-primary"
                    >
                      {preset.name}
                    </Button>
                    <IconButton
                      icon={<span>✕</span>}
                      onClick={() => handleDeletePreset(preset.id)}
                      size="xs"
                      title="프리셋 삭제"
                      className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive ml-1"
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* [Phase 5.0] 검색 입력 */}
          <div className="mb-4">
            <SearchInput
              value={searchQuery}
              onChange={setSearchQuery}
              placeholder="키워드, 카테고리, 소스 검색..."
              className="max-w-md"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2">등급</label>
              <select
                value={gradeFilter}
                onChange={(e) => setGradeFilter(e.target.value)}
                className="w-full px-3 py-2 bg-background border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">전체</option>
                <option value="S">🔥 S급</option>
                <option value="A">🟢 A급</option>
                <option value="B">🔵 B급</option>
                <option value="C">⚪ C급</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">카테고리</label>
              <select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
                className="w-full px-3 py-2 bg-background border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">전체</option>
                {stats?.categories && Object.keys(stats.categories).map((cat) => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">소스</label>
              <select
                value={sourceFilter}
                onChange={(e) => setSourceFilter(e.target.value)}
                className="w-full px-3 py-2 bg-background border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">전체</option>
                {stats?.sources && Object.keys(stats.sources).map((src) => (
                  <option key={src} value={src}>{src}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">트렌드</label>
              <select
                value={trendFilter}
                onChange={(e) => setTrendFilter(e.target.value)}
                className="w-full px-3 py-2 bg-background border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">전체</option>
                <option value="rising">📈 Rising</option>
                <option value="falling">📉 Falling</option>
                <option value="stable">➡️ Stable</option>
              </select>
            </div>
          </div>

          {/* 필터 결과 요약 */}
          {hasActiveFilters && keywords && (
            <div className="mt-4 text-sm text-muted-foreground">
              {filteredKeywords.length}개 키워드 (전체 {keywords.length}개 중)
            </div>
          )}
        </div>

        {/* [Phase 6.2] KEI 상위 키워드 */}
        <TopKeiKeywords limit={10} minVolume={10} />

        {/* 키워드 테이블 */}
        <div className="bg-card rounded-lg border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">📊 키워드 목록</h3>
            <Button
              variant="success"
              size="sm"
              onClick={handleExportAll}
              loading={exportAllKeywords.isPending}
              disabled={keywordsLoading}
              icon={<Download size={14} />}
              title={hasActiveFilters ? "현재 필터 적용된 전체 키워드 내보내기" : "전체 키워드 내보내기"}
            >
              전체 CSV 내보내기
            </Button>
          </div>
          {keywordsLoading ? (
            <SkeletonTable rows={10} columns={6} />
          ) : keywordsError ? (
            <ErrorState
              title="키워드 로드 실패"
              message="키워드 데이터를 불러오는데 실패했습니다."
              onRetry={() => refetchKeywords()}
            />
          ) : !filteredKeywords || filteredKeywords.length === 0 ? (
            <div className="text-center py-12">
              {searchQuery || hasActiveFilters ? (
                <>
                  <p className="text-4xl mb-4">🔍</p>
                  <p className="text-lg font-medium mb-2">검색 결과가 없습니다</p>
                  <p className="text-sm text-muted-foreground mb-4">
                    다른 검색어나 필터를 시도해보세요.
                  </p>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleResetFilters}
                  >
                    필터 초기화
                  </Button>
                </>
              ) : (
                <>
                  <p className="text-6xl mb-6">🎯</p>
                  <p className="text-2xl font-bold mb-3">키워드가 없습니다</p>

                  <div className="max-w-2xl mx-auto space-y-4">
                    <div className="bg-primary/10 border border-primary/30 rounded-lg p-6">
                      <p className="text-lg font-semibold text-primary mb-2">💡 사용 방법</p>
                      <p className="text-sm text-muted-foreground">
                        위의 <strong>컨트롤 패널</strong>에서 Total War 또는 LEGION 모드를 선택하고 실행하세요.
                        <br />
                        실시간 로그 뷰어에서 진행 상황을 확인할 수 있습니다.
                      </p>
                    </div>

                    <div className="bg-card border border-border rounded-lg p-6 text-left">
                      <p className="text-sm font-semibold mb-3">📊 모드 설명:</p>
                      <div className="space-y-3">
                        <div className="flex items-start gap-3">
                          <span className="text-xl">⚔️</span>
                          <div>
                            <p className="font-medium">Total War 모드</p>
                            <p className="text-xs text-muted-foreground">자동완성 기반 빠른 키워드 수집 (약 5분)</p>
                          </div>
                        </div>
                        <div className="flex items-start gap-3">
                          <span className="text-xl">🎖️</span>
                          <div>
                            <p className="font-medium">LEGION 모드</p>
                            <p className="text-xs text-muted-foreground">6단계 확장으로 고품질 키워드 대량 수집 (약 15-30분)</p>
                          </div>
                        </div>
                      </div>
                    </div>

                    <Button
                      variant="secondary"
                      size="lg"
                      onClick={() => window.location.reload()}
                    >
                      🔄 페이지 새로고침
                    </Button>
                  </div>
                </>
              )}
            </div>
          ) : (
            <KeywordTable keywords={filteredKeywords} />
          )}
        </div>
      </>
    )
  }

  // 콘텐츠 클러스터 탭 렌더링
  function renderClustersTab() {
    return (
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">📝 콘텐츠 클러스터</h3>
        <p className="text-sm text-muted-foreground mb-4">
          관련 키워드를 그룹화하여 한 블로그 포스트로 여러 키워드를 커버할 수 있습니다.
        </p>
        {clustersError ? (
          <ErrorState
            title="클러스터 로드 실패"
            message="클러스터 데이터를 불러오는데 실패했습니다."
            onRetry={() => refetchClusters()}
          />
        ) : !clusters || clusters.length === 0 ? (
          <EmptyState
            type="initial"
            icon="📝"
            title="콘텐츠 클러스터가 없습니다"
            description="키워드를 수집한 후 자동으로 관련 키워드들이 그룹화됩니다."
            suggestion="먼저 '키워드 수집' 탭에서 Pathfinder를 실행해보세요."
            actions={[
              {
                label: '키워드 수집하기',
                onClick: () => setActiveTab('collection'),
                variant: 'primary',
              }
            ]}
          />
        ) : (
          <KeywordClusters clusters={clusters} />
        )}
      </div>
    )
  }

  // 콘텐츠 캘린더 탭 렌더링
  function renderCalendarTab() {
    if (calendarLoading) {
      return <SkeletonTable rows={6} columns={4} />
    }

    if (calendarError) {
      return (
        <ErrorState
          title="캘린더 로드 실패"
          message="콘텐츠 캘린더를 불러오는데 실패했습니다."
          onRetry={() => refetchCalendar()}
        />
      )
    }

    if (!contentCalendar || !contentCalendar.weekly_plan || contentCalendar.weekly_plan.length === 0) {
      return (
        <div className="bg-card rounded-lg border border-border p-6">
          <div className="text-center py-12 text-muted-foreground">
            <p className="text-4xl mb-4">📅</p>
            <p className="text-lg font-medium mb-2">콘텐츠 캘린더를 생성할 수 없습니다</p>
            <p className="text-sm">S급 또는 A급 키워드 클러스터가 필요합니다.</p>
            <p className="text-xs mt-2">먼저 키워드 수집을 실행해주세요.</p>
          </div>
        </div>
      )
    }

    const { summary, weekly_plan } = contentCalendar

    // [P2-2] 진행률 계산
    const totalWeeks = weekly_plan.length
    const completedCount = weekly_plan.filter((w: any) => completedWeeks.has(w.week)).length
    const progressPercent = totalWeeks > 0 ? Math.round((completedCount / totalWeeks) * 100) : 0

    return (
      <div className="space-y-6">
        {/* 진행률 바 */}
        <div className="bg-card rounded-lg border border-border p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">콘텐츠 제작 진행률</span>
            <span className="text-sm text-muted-foreground">
              {completedCount}/{totalWeeks}주 완료 ({progressPercent}%)
            </span>
          </div>
          <div className="h-3 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-green-500 to-emerald-500 transition-all duration-500"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          {completedCount > 0 && (
            <p className="text-xs text-muted-foreground mt-2">
              ✨ {completedCount}주차 콘텐츠 제작 완료!
              {progressPercent === 100 && ' 🎉 모든 콘텐츠 제작이 완료되었습니다!'}
            </p>
          )}
        </div>

        {/* 요약 카드 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-card rounded-lg border border-border p-4">
            <p className="text-sm text-muted-foreground">총 기간</p>
            <p className="text-2xl font-bold">{summary?.total_weeks || 0}주</p>
          </div>
          <div className="bg-card rounded-lg border border-border p-4">
            <p className="text-sm text-muted-foreground">커버 키워드</p>
            <p className="text-2xl font-bold text-primary">{summary?.total_keywords || 0}개</p>
          </div>
          <div className="bg-card rounded-lg border border-border p-4">
            <p className="text-sm text-muted-foreground">예상 트래픽</p>
            <p className="text-2xl font-bold text-green-500">{(summary?.estimated_monthly_traffic || 0).toLocaleString()}</p>
          </div>
          <div className="bg-card rounded-lg border border-border p-4">
            <p className="text-sm text-muted-foreground">클러스터</p>
            <p className="text-2xl font-bold">{summary?.clusters_used || 0}개</p>
          </div>
        </div>

        {/* 주별 계획 */}
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-semibold mb-4">📅 주별 콘텐츠 계획</h3>
          <p className="text-sm text-muted-foreground mb-6">
            S/A 등급 클러스터 기반으로 자동 생성된 12주 콘텐츠 캘린더입니다.
          </p>

          <div className="space-y-4">
            {weekly_plan.map((week: any) => {
              const isCompleted = completedWeeks.has(week.week)

              return (
              <div
                key={week.week}
                className={`border rounded-lg p-4 transition-colors ${
                  isCompleted
                    ? 'border-green-500/50 bg-green-500/5'
                    : 'border-border hover:bg-muted/30'
                }`}
              >
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-3">
                  <div className="flex items-center gap-3">
                    {/* 완료 체크박스 */}
                    <button
                      onClick={() => toggleWeekComplete(week.week)}
                      className={`w-10 h-10 rounded-full flex items-center justify-center font-bold flex-shrink-0 transition-all ${
                        isCompleted
                          ? 'bg-green-500 text-white'
                          : 'bg-primary/20 text-primary hover:bg-primary/30'
                      }`}
                      title={isCompleted ? '완료 취소' : '완료로 표시'}
                    >
                      {isCompleted ? '✓' : week.week}
                    </button>
                    <div className="min-w-0">
                      <p className={`font-semibold truncate ${isCompleted ? 'line-through text-muted-foreground' : ''}`}>
                        {week.cluster_name}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {isCompleted ? '✅ 완료' : (week.grade === 'S' ? '🔥' : '🟢')} {week.grade}급 클러스터
                      </p>
                    </div>
                  </div>
                  <div className="text-left sm:text-right flex-shrink-0 ml-13 sm:ml-0">
                    <p className="text-sm font-medium text-green-500">
                      +{week.estimated_traffic?.toLocaleString() || 0} 예상
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {week.keyword_count}개 키워드 커버
                    </p>
                  </div>
                </div>

                {/* 타겟 키워드 */}
                <div className="mb-3">
                  <p className="text-xs text-muted-foreground mb-2">타겟 키워드:</p>
                  <div className="flex flex-wrap gap-1">
                    {week.keywords?.slice(0, 5).map((kw: string, idx: number) => (
                      <span
                        key={idx}
                        className="px-2 py-0.5 bg-muted rounded text-xs"
                      >
                        {kw}
                      </span>
                    ))}
                    {week.keywords?.length > 5 && (
                      <span className="px-2 py-0.5 text-muted-foreground text-xs">
                        +{week.keywords.length - 5}개 더
                      </span>
                    )}
                  </div>
                </div>

                {/* 추천 콘텐츠 타입 & 아웃라인 생성 버튼 */}
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <p className="text-xs text-muted-foreground">추천 형식:</p>
                    {week.content_types?.map((type: string, idx: number) => (
                      <span
                        key={idx}
                        className="px-2 py-0.5 bg-primary/10 text-primary rounded text-xs"
                      >
                        {type}
                      </span>
                    ))}
                  </div>
                  <Button
                    variant="primary"
                    size="xs"
                    onClick={() => handleGenerateOutline(week.week, week.keywords || [], week.cluster_name || '', week.category)}
                    loading={generateOutline.isPending && expandedOutline === week.week}
                    className="bg-gradient-to-r from-purple-500 to-pink-500"
                  >
                    ✨ 아웃라인 생성
                  </Button>
                </div>

                {/* 생성된 아웃라인 표시 */}
                {generatedOutlines[week.week] && (
                  <div className="mt-4 pt-4 border-t border-border">
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="font-semibold text-sm flex items-center gap-2">
                        📝 생성된 아웃라인
                        <span className="text-xs px-2 py-0.5 bg-muted rounded">
                          {generatedOutlines[week.week].source === 'gemini' ? 'AI 생성' : '템플릿'}
                        </span>
                      </h4>
                      <Button
                        variant="ghost"
                        size="xs"
                        onClick={() => {
                          navigator.clipboard.writeText(JSON.stringify(generatedOutlines[week.week], null, 2))
                          toast.success('아웃라인이 클립보드에 복사되었습니다')
                        }}
                      >
                        📋 복사
                      </Button>
                    </div>

                    <div className="bg-muted/50 rounded-lg p-4 space-y-3">
                      {/* 제목 */}
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">제목</p>
                        <p className="font-medium">{generatedOutlines[week.week].title}</p>
                      </div>

                      {/* 훅 */}
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">도입부 훅</p>
                        <p className="text-sm italic">"{generatedOutlines[week.week].hook}"</p>
                      </div>

                      {/* 섹션 */}
                      <div>
                        <p className="text-xs text-muted-foreground mb-2">섹션 구성</p>
                        <div className="space-y-2">
                          {generatedOutlines[week.week].sections?.map((section: any, sIdx: number) => (
                            <div key={sIdx} className="bg-background/50 rounded p-2">
                              <p className="font-medium text-sm">{sIdx + 1}. {section.heading}</p>
                              <ul className="text-xs text-muted-foreground mt-1 ml-4 list-disc">
                                {section.key_points?.map((point: string, pIdx: number) => (
                                  <li key={pIdx}>{point}</li>
                                ))}
                              </ul>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* CTA */}
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">CTA (행동 유도)</p>
                        <p className="text-sm font-medium text-primary">{generatedOutlines[week.week].cta}</p>
                      </div>

                      {/* 메타 설명 */}
                      {generatedOutlines[week.week].meta_description && (
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">메타 설명</p>
                          <p className="text-xs">{generatedOutlines[week.week].meta_description}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )})}
          </div>
        </div>

        {/* 안내 */}
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
          <p className="text-sm text-blue-400">
            💡 <strong>팁:</strong> 캘린더는 고품질(S/A급) 클러스터를 우선으로 배치합니다.
            각 주마다 하나의 클러스터를 집중 공략하면 SEO 효과가 극대화됩니다.
          </p>
        </div>
      </div>
    )
  }
}

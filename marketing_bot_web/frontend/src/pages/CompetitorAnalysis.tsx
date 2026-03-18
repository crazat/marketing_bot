import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { competitorsApi, instagramApi, hudApi } from '@/services/api'
import PageTransition from '@/components/PageTransition'
import CompetitorList from '@/components/competitors/CompetitorList'
import WeaknessSummary from '@/components/competitors/WeaknessSummary'
import OpportunityKeywords from '@/components/competitors/OpportunityKeywords'
import InstagramAnalysis from '@/components/competitors/InstagramAnalysis'
import ContentGapAnalyzer from '@/components/competitors/ContentGapAnalyzer'
import WeaknessRadar from '@/components/competitors/WeaknessRadar'
import ReviewResponseAssistant from '@/components/reviews/ReviewResponseAssistant'
import { useToast } from '@/components/ui/Toast'
import MissionProgress from '@/components/ui/MissionProgress'
import ErrorState from '@/components/ui/ErrorState'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import { RefreshCw, Copy } from 'lucide-react'
import Button from '@/components/ui/Button'
import { useUrlState } from '@/hooks/useUrlState'
import { TerminalGuide } from '@/components/ui/TerminalGuide'
import { getPageCommands } from '@/utils/terminalCommands'
import { useLoadingState } from '@/hooks/useLoadingState'

export default function CompetitorAnalysis() {
  // [Phase 5.0] URL 상태 관리
  const [activeTab, setActiveTab] = useUrlState<string>('tab', { defaultValue: 'weaknesses' })
  const [scanningModule, setScanningModule] = useState<string | null>(null)
  const [missionName, setMissionName] = useState('')
  const queryClient = useQueryClient()
  const toast = useToast()

  // 경쟁사 목록
  const {
    data: competitors,
    isLoading: competitorsLoading,
    isFetching: competitorsFetching,
    error: competitorsError
  } = useQuery({
    queryKey: ['competitors-list'],
    queryFn: () => competitorsApi.getList().catch(() => []),
    staleTime: 120000, // 2분간 캐시
    retry: 1,
  })

  // [UX 개선] 로딩 상태 통합
  const competitorsLoadingState = useLoadingState({
    isLoading: competitorsLoading,
    isFetching: competitorsFetching,
  })

  // 디버그: 경쟁사 목록 로딩 상태
  if (competitorsError) {
    console.error('Competitors loading error:', competitorsError)
  }

  // 약점 요약
  const { data: weaknessSummary } = useQuery({
    queryKey: ['weakness-summary'],
    queryFn: () => competitorsApi.getWeaknessSummary().catch(() => null),
    staleTime: 120000, // 2분간 캐시
    retry: 1,
  })

  // 약점 목록
  const {
    data: weaknesses,
    isLoading: weaknessesLoading,
    isFetching: weaknessesFetching
  } = useQuery({
    queryKey: ['weaknesses'],
    queryFn: () => competitorsApi.getWeaknesses(30).catch(() => []),
    staleTime: 120000, // 2분간 캐시
    retry: 1,
  })

  // [UX 개선] 로딩 상태 통합
  const weaknessesLoadingState = useLoadingState({
    isLoading: weaknessesLoading,
    isFetching: weaknessesFetching,
  })

  // 기회 키워드
  const { data: opportunityKeywords } = useQuery({
    queryKey: ['opportunity-keywords'],
    queryFn: () => competitorsApi.getOpportunityKeywords('pending').catch(() => []),
    staleTime: 120000, // 2분간 캐시
    retry: 1,
  })

  // Instagram 통계
  const { data: instagramStats } = useQuery({
    queryKey: ['instagram-stats'],
    queryFn: () => instagramApi.getStats(30).catch(() => null),
    staleTime: 300000, // 5분간 캐시
    retry: 1,
  })

  // Instagram 해시태그 분석
  const { data: hashtagAnalysis } = useQuery({
    queryKey: ['hashtag-analysis'],
    queryFn: () => instagramApi.getHashtagAnalysis(30).catch(() => null),
    staleTime: 300000, // 5분간 캐시
    retry: 1,
  })

  // 실행 중인 모듈 조회 (페이지 로드 시 상태 복원)
  const { data: runningModules } = useQuery({
    queryKey: ['running-modules'],
    queryFn: () => hudApi.getRunningModules().catch(() => ({ running: [] })),
    refetchInterval: 60000, // 60초마다 확인 (서버 부하 감소)
    retry: 1,
  })

  // 경쟁사 분석 모듈이 실행 중이면 scanningModule 상태 복원
  useEffect(() => {
    if (!scanningModule && runningModules?.running) {
      const moduleNameMap: Record<string, string> = {
        weakness_analyzer: '경쟁사 리뷰 분석',
        instagram: 'Instagram 스캔',
        place_sniper: '경쟁사 순위 스캔',
      }
      const runningModule = Object.keys(moduleNameMap).find(m => runningModules.running.includes(m))
      if (runningModule) {
        setScanningModule(runningModule)
        setMissionName(moduleNameMap[runningModule])
      }
    }
  }, [runningModules, scanningModule])

  // 스캔 mutation (HUD 모듈 실행)
  const runScan = useMutation({
    mutationFn: (moduleName: string) => hudApi.executeMission(moduleName),
    onSuccess: (_data, moduleName) => {
      const name = scanModules[activeTab]?.name || moduleName
      toast.success(`${name} 스캔이 시작되었습니다`)
      setScanningModule(moduleName)
      setMissionName(name)
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`스캔 실패: ${error.response?.data?.detail || error.message}`)
    },
  })

  // 리뷰 기반 약점 분석 mutation (빠른 분석)
  const analyzeReviews = useMutation({
    mutationFn: () => competitorsApi.analyzeReviews(),
    onSuccess: (data) => {
      toast.success(`${data.weaknesses_found}개 약점 분석 완료`)
      queryClient.invalidateQueries({ queryKey: ['weakness-summary'] })
      queryClient.invalidateQueries({ queryKey: ['weaknesses'] })
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`분석 실패: ${error.response?.data?.detail || error.message}`)
    },
  })

  // [Phase 4.0] 콘텐츠 아웃라인 생성
  const [contentOutlines, setContentOutlines] = useState<any[]>([])
  const generateOutlines = useMutation({
    mutationFn: (weaknessType?: string) => competitorsApi.generateContentOutline(weaknessType),
    onSuccess: (data) => {
      setContentOutlines(data.outlines || [])
      toast.success(`${data.total || 0}개 콘텐츠 아웃라인 생성 완료`)
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`생성 실패: ${error.response?.data?.detail || error.message}`)
    },
  })

  // MissionProgress 완료 콜백
  const handleMissionComplete = () => {
    toast.success('스캔이 완료되었습니다')
    setScanningModule(null)
    setMissionName('')
    // 데이터 새로고침
    queryClient.invalidateQueries({ queryKey: ['competitors-list'] })
    queryClient.invalidateQueries({ queryKey: ['weakness-summary'] })
    queryClient.invalidateQueries({ queryKey: ['weaknesses'] })
    queryClient.invalidateQueries({ queryKey: ['opportunity-keywords'] })
    queryClient.invalidateQueries({ queryKey: ['instagram-stats'] })
    queryClient.invalidateQueries({ queryKey: ['hashtag-analysis'] })
  }

  // MissionProgress 중지 콜백
  const handleMissionStop = () => {
    toast.info('스캔이 중지되었습니다')
    setScanningModule(null)
    setMissionName('')
  }

  const handleRunScan = (moduleName: string) => {
    runScan.mutate(moduleName)
  }

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['competitors-list'] })
    queryClient.invalidateQueries({ queryKey: ['weakness-summary'] })
    queryClient.invalidateQueries({ queryKey: ['weaknesses'] })
    queryClient.invalidateQueries({ queryKey: ['opportunity-keywords'] })
    queryClient.invalidateQueries({ queryKey: ['instagram-stats'] })
    queryClient.invalidateQueries({ queryKey: ['hashtag-analysis'] })
  }

  // 탭별 스캔 모듈 매핑
  const scanModules: Record<string, { module: string; name: string }> = {
    weaknesses: { module: 'weakness_analyzer', name: '경쟁사 리뷰 분석' },
    opportunities: { module: 'weakness_analyzer', name: '기회 키워드 스캔' },
    'content-gap': { module: 'weakness_analyzer', name: '콘텐츠 갭 분석' },
    'weakness-radar': { module: 'weakness_analyzer', name: '약점 레이더 분석' },
    instagram: { module: 'instagram', name: 'Instagram 스캔' },
    'review-response': { module: 'weakness_analyzer', name: '리뷰 응답 도우미' },
    competitors: { module: 'place_sniper', name: '경쟁사 순위 스캔' },
  }

  const isScanning = scanningModule !== null || runScan.isPending || analyzeReviews.isPending

  return (
    <PageTransition>
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold mb-2">💪 경쟁사 분석</h1>
          <p className="text-muted-foreground">
            경쟁사 약점 분석 및 Instagram 모니터링
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={handleRefresh}
            disabled={isScanning}
            icon={<RefreshCw className="w-4 h-4" />}
          >
            새로고침
          </Button>
          {!scanningModule && (
            <Button
              variant="primary"
              onClick={() => {
                if (activeTab === 'weaknesses' || activeTab === 'opportunities') {
                  analyzeReviews.mutate()
                } else {
                  handleRunScan(scanModules[activeTab].module)
                }
              }}
              disabled={isScanning}
              loading={analyzeReviews.isPending}
            >
              🔍 {scanModules[activeTab].name}
            </Button>
          )}
        </div>
      </div>

      {/* 터미널 실행 가이드 */}
      <TerminalGuide commands={getPageCommands('competitors')} />

      {/* 실시간 스캔 진행 상황 - MissionProgress 컴포넌트 사용 */}
      {scanningModule && (
        <MissionProgress
          moduleName={scanningModule}
          missionName={missionName}
          onComplete={handleMissionComplete}
          onStop={handleMissionStop}
        />
      )}

      {/* 탭 */}
      <div className="flex gap-2 border-b border-border overflow-x-auto" role="tablist" aria-label="경쟁사 분석 탭">
        {[
          { id: 'weaknesses', label: '🎯 약점 공략', icon: '🎯' },
          { id: 'opportunities', label: '🔑 기회 키워드', icon: '🔑' },
          { id: 'content-gap', label: '📊 콘텐츠 갭', icon: '📊' },
          { id: 'weakness-radar', label: '📡 약점 레이더', icon: '📡' },
          { id: 'instagram', label: '📸 Instagram', icon: '📸' },
          { id: 'review-response', label: '💬 리뷰 응답', icon: '💬' },
          { id: 'competitors', label: '🏢 경쟁사 관리', icon: '🏢' }
        ].map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`tabpanel-${tab.id}`}
            onClick={() => setActiveTab(tab.id)}
            className={`
              px-4 py-3 font-medium transition-colors relative whitespace-nowrap
              ${activeTab === tab.id
                ? 'text-primary'
                : 'text-muted-foreground hover:text-foreground'
              }
            `}
          >
            {tab.label}
            {activeTab === tab.id && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
            )}
          </button>
        ))}
      </div>

      {/* 탭 컨텐츠 */}
      <div>
        {activeTab === 'weaknesses' && (
          <div className="space-y-6">
            <WeaknessSummary summary={weaknessSummary} />

            {/* [Phase 4.0] 콘텐츠 아웃라인 생성 */}
            <div className="bg-card rounded-lg border border-border p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold">✍️ 콘텐츠 아웃라인 생성</h2>
                <Button
                  variant="primary"
                  onClick={() => generateOutlines.mutate(undefined)}
                  loading={generateOutlines.isPending}
                >
                  🚀 AI 아웃라인 생성
                </Button>
              </div>
              <p className="text-sm text-muted-foreground mb-4">
                경쟁사 약점을 바탕으로 우리 한의원의 강점을 부각시키는 콘텐츠 아웃라인을 자동 생성합니다.
              </p>

              {contentOutlines.length > 0 && (
                <div className="space-y-4 mt-4">
                  {contentOutlines.map((outline, idx) => (
                    <div key={idx} className="border border-border rounded-lg p-4">
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-xs px-2 py-1 bg-primary/10 text-primary rounded-full">
                          {outline.platform} · {outline.weakness_type}
                        </span>
                        <Button
                          variant="ghost"
                          size="xs"
                          onClick={() => {
                            const text = `제목: ${outline.title}\n\n${outline.hook}\n\n${
                              outline.sections?.map((s: any) =>
                                `## ${s.heading}\n${s.key_points?.map((p: string) => `- ${p}`).join('\n')}`
                              ).join('\n\n') || ''
                            }\n\n${outline.cta}\n\n키워드: ${outline.keywords?.join(', ')}`
                            navigator.clipboard.writeText(text)
                            toast.success('아웃라인이 클립보드에 복사되었습니다')
                          }}
                          icon={<Copy className="w-3 h-3" />}
                        >
                          복사
                        </Button>
                      </div>
                      <h3 className="font-bold text-lg mb-2">{outline.title}</h3>
                      <p className="text-sm text-muted-foreground mb-3 italic">"{outline.hook}"</p>
                      <div className="space-y-2">
                        {outline.sections?.map((section: any, sIdx: number) => (
                          <div key={sIdx} className="pl-3 border-l-2 border-primary/30">
                            <div className="font-medium text-sm">{section.heading}</div>
                            <ul className="text-xs text-muted-foreground list-disc list-inside">
                              {section.key_points?.map((point: string, pIdx: number) => (
                                <li key={pIdx}>{point}</li>
                              ))}
                            </ul>
                          </div>
                        ))}
                      </div>
                      <div className="mt-3 pt-3 border-t border-border">
                        <div className="text-sm font-medium text-green-500">{outline.cta}</div>
                        <div className="flex flex-wrap gap-1 mt-2">
                          {outline.keywords?.map((kw: string, kIdx: number) => (
                            <span key={kIdx} className="text-xs px-2 py-0.5 bg-muted rounded">
                              #{kw}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="bg-card rounded-lg border border-border p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold">📋 발견된 약점</h2>
                <span className="text-sm text-muted-foreground">
                  {weaknesses?.length || 0}개 약점
                </span>
              </div>
              {weaknessesLoadingState.isInitialLoad ? (
                <div className="text-center py-8">
                  <LoadingSpinner size="md" text="약점 목록을 불러오는 중..." />
                  {weaknessesLoadingState.isSlowLoading && (
                    <p className="text-xs text-muted-foreground mt-2">
                      데이터 양이 많아 시간이 걸리고 있습니다...
                    </p>
                  )}
                </div>
              ) : !weaknesses || weaknesses.length === 0 ? (
                <div className="text-center py-12">
                  <p className="text-6xl mb-4">🔍</p>
                  <p className="text-xl font-semibold mb-2">발견된 약점이 없습니다</p>
                  <p className="text-muted-foreground mb-6">
                    경쟁사 리뷰를 분석하여 약점과 기회를 찾아보세요.
                  </p>
                  <Button
                    variant="primary"
                    size="lg"
                    onClick={() => analyzeReviews.mutate()}
                    loading={analyzeReviews.isPending}
                  >
                    🔍 약점 분석 시작
                  </Button>
                </div>
              ) : (
                <div className="space-y-4" role="list">
                  {weaknesses.map((weakness: { competitor_name: string; weakness_type: string; description: string; evidence?: string; opportunity_keywords?: string; severity?: string; impact_score?: number }, index: number) => (
                    <div
                      key={`weakness-${weakness.competitor_name}-${index}`}
                      role="listitem"
                      className="p-4 rounded-lg border border-border hover:border-primary/50 transition-colors"
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold">{weakness.competitor_name}</span>
                          {/* [Phase 5.0] 영향도 점수 표시 */}
                          {weakness.impact_score !== undefined && (
                            <div
                              className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                                weakness.impact_score >= 70 ? 'bg-red-500/20 text-red-500' :
                                weakness.impact_score >= 50 ? 'bg-orange-500/20 text-orange-500' :
                                weakness.impact_score >= 30 ? 'bg-yellow-500/20 text-yellow-500' :
                                'bg-gray-500/20 text-gray-500'
                              }`}
                              title={`영향도: ${weakness.impact_score}점 (심각도: ${weakness.severity || 'Medium'})`}
                            >
                              {weakness.impact_score >= 70 ? '🔴' :
                               weakness.impact_score >= 50 ? '🟠' :
                               weakness.impact_score >= 30 ? '🟡' : '⚪'}
                              {weakness.impact_score}점
                            </div>
                          )}
                        </div>
                        <span className="text-xs px-2 py-1 rounded-full bg-muted">
                          {weakness.weakness_type}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground mb-2">
                        {weakness.description}
                      </p>
                      {weakness.evidence && (
                        <div className="text-xs bg-muted/50 p-2 rounded mb-2 border-l-2 border-primary/50">
                          <span className="text-muted-foreground">📝 근거: </span>
                          <span className="italic">"{weakness.evidence}"</span>
                        </div>
                      )}
                      {weakness.opportunity_keywords && (
                        <div className="flex flex-wrap gap-1">
                          {weakness.opportunity_keywords.split(',').map((kw: string, kwIdx: number) => (
                            <span
                              key={`kw-${kw.trim()}-${kwIdx}`}
                              className="text-xs px-2 py-1 rounded-md bg-green-500/10 text-green-500"
                            >
                              <span aria-hidden="true">💡</span> {kw.trim()}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'opportunities' && (
          <div className="space-y-6">
            {!opportunityKeywords || opportunityKeywords.length === 0 ? (
              <div className="bg-card rounded-lg border border-border p-6">
                <div className="text-center py-12">
                  <p className="text-6xl mb-4">🔑</p>
                  <p className="text-xl font-semibold mb-2">기회 키워드가 없습니다</p>
                  <p className="text-muted-foreground mb-6">
                    경쟁사 약점을 분석하여 기회 키워드를 생성하세요.
                  </p>
                  <Button
                    variant="primary"
                    size="lg"
                    onClick={() => analyzeReviews.mutate()}
                    loading={analyzeReviews.isPending}
                  >
                    🔍 기회 키워드 스캔
                  </Button>
                </div>
              </div>
            ) : (
              <OpportunityKeywords keywords={opportunityKeywords} />
            )}
          </div>
        )}

        {activeTab === 'content-gap' && (
          <ContentGapAnalyzer />
        )}

        {activeTab === 'weakness-radar' && (
          <WeaknessRadar />
        )}

        {activeTab === 'instagram' && (
          <div className="space-y-6">
            {(!instagramStats || Object.keys(instagramStats).length === 0) && (!hashtagAnalysis || hashtagAnalysis.length === 0) ? (
              <div className="bg-card rounded-lg border border-border p-6">
                <div className="text-center py-12">
                  <p className="text-6xl mb-4">📸</p>
                  <p className="text-xl font-semibold mb-2">Instagram 데이터가 없습니다</p>
                  <p className="text-muted-foreground mb-6">
                    경쟁사 Instagram 계정을 분석하여 인사이트를 얻으세요.
                  </p>
                  <Button
                    variant="primary"
                    size="lg"
                    onClick={() => handleRunScan('instagram')}
                    loading={isScanning}
                  >
                    🔍 Instagram 스캔
                  </Button>
                </div>
              </div>
            ) : (
              <InstagramAnalysis
                stats={instagramStats}
                hashtagAnalysis={hashtagAnalysis}
              />
            )}
          </div>
        )}

        {activeTab === 'review-response' && (
          <ReviewResponseAssistant />
        )}

        {activeTab === 'competitors' && (
          competitorsLoadingState.isInitialLoad ? (
            <div className="bg-card rounded-lg border border-border p-6">
              <div className="text-center py-8">
                <LoadingSpinner size="lg" text="경쟁사 목록을 불러오는 중..." />
                {competitorsLoadingState.isSlowLoading && (
                  <p className="text-xs text-muted-foreground mt-2">
                    데이터 양이 많아 시간이 걸리고 있습니다...
                  </p>
                )}
              </div>
            </div>
          ) : competitorsError ? (
            <div className="bg-card rounded-lg border border-border p-6">
              <ErrorState
                title="경쟁사 목록 로드 실패"
                message={(competitorsError as Error).message || "경쟁사 목록을 불러오는데 실패했습니다."}
                onRetry={handleRefresh}
              />
            </div>
          ) : (
            <div className="relative">
              {/* [UX 개선] 백그라운드 새로고침 인디케이터 */}
              {competitorsLoadingState.isRefreshing && (
                <div className="absolute top-2 right-2 flex items-center gap-2 text-xs text-muted-foreground bg-card/90 px-2 py-1 rounded-full border border-border">
                  <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-primary" />
                  새로고침 중...
                </div>
              )}
              <CompetitorList competitors={competitors || []} />
            </div>
          )
        )}
      </div>
    </div>
    </PageTransition>
  )
}

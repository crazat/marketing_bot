import { useState, useEffect, useCallback, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { leadsApi, hudApi, exportApi, Lead } from '@/services/api'
import PageTransition from '@/components/PageTransition'
import LeadStats from '@/components/leads/LeadStats'
import LeadTable from '@/components/leads/LeadTable'
import { LeadAttributionStats } from '@/components/leads/LeadAttribution'
import KanbanBoard from '@/components/leads/KanbanBoard'
import ConversionModal from '@/components/leads/ConversionModal'
import ErrorState from '@/components/ui/ErrorState'
import { SkeletonStatsGrid, SkeletonTable } from '@/components/ui/Skeleton'
import MissionProgress from '@/components/ui/MissionProgress'
import TabNavigation from '@/components/ui/TabNavigation'
import { useToast } from '@/components/ui/Toast'
import { useUrlState } from '@/hooks/useUrlState'
import { TerminalGuide } from '@/components/ui/TerminalGuide'
import { getPageCommands } from '@/utils/terminalCommands'
import Button, { IconButton } from '@/components/ui/Button'
import { Download, RefreshCw, Search } from 'lucide-react'
// Lead Manager 뷰 모드 타입 — 카드 뷰 제거 (테이블이 모바일 반응형으로 동작)
type LeadViewMode = 'table' | 'kanban'

export default function LeadManager() {
  // [Phase 5.0] URL 상태 관리
  const [activeTab, setActiveTab] = useUrlState<string>('platform', { defaultValue: 'cafe' })
  const [viewMode, setViewMode] = useUrlState<LeadViewMode>('view', { defaultValue: 'table' })
  const [statusFilter, setStatusFilter] = useUrlState<string>('status', { defaultValue: '' })

  // 레거시 URL(?view=card) 자동 마이그레이션 → table
  useEffect(() => {
    if ((viewMode as string) === 'card') setViewMode('table')
  }, [viewMode, setViewMode])
  // [Phase 4.0] 신뢰도 필터
  const [trustFilter, setTrustFilter] = useUrlState<string>('trust', { defaultValue: '' })
  const [scanningModule, setScanningModule] = useState<string | null>(null)
  const [scanningName, setScanningName] = useState('')
  // [Phase 7.1] 전환 기록 모달 상태
  const [conversionModalOpen, setConversionModalOpen] = useState(false)
  const [conversionLead, setConversionLead] = useState<Lead | null>(null)
  const queryClient = useQueryClient()
  const toast = useToast()

  // [성능 개선] 탭별 쿼리 키 매핑 (선택적 무효화용)
  const tabQueryKeyMap = useMemo(() => ({
    cafe: 'naver-leads',
    naver: 'naver-leads',
    youtube: 'youtube-leads',
    tiktok: 'tiktok-leads',
    instagram: 'instagram-leads',
    carrot: 'carrot-leads',
    influencer: 'influencer-leads',
    duplicates: 'leads-duplicates',
    all: null, // 'all' 탭은 모든 쿼리 무효화
  }), [])

  // [성능 개선] 선택적 쿼리 무효화 함수
  const invalidateCurrentTab = useCallback(() => {
    const queryKey = tabQueryKeyMap[activeTab as keyof typeof tabQueryKeyMap]
    if (queryKey) {
      // 현재 탭에 해당하는 쿼리만 무효화
      queryClient.invalidateQueries({ queryKey: [queryKey] })
    } else {
      // 'all' 탭이면 모든 리드 쿼리 무효화
      queryClient.invalidateQueries({ queryKey: ['naver-leads'] })
      queryClient.invalidateQueries({ queryKey: ['youtube-leads'] })
      queryClient.invalidateQueries({ queryKey: ['tiktok-leads'] })
      queryClient.invalidateQueries({ queryKey: ['instagram-leads'] })
      queryClient.invalidateQueries({ queryKey: ['carrot-leads'] })
      queryClient.invalidateQueries({ queryKey: ['influencer-leads'] })
    }
    // 통계는 항상 새로고침
    queryClient.invalidateQueries({ queryKey: ['leads-stats'] })
  }, [activeTab, tabQueryKeyMap, queryClient])

  // 리드 통계
  const { data: stats, isLoading: statsLoading, isError: statsError, refetch: refetchStats } = useQuery({
    queryKey: ['leads-stats'],
    queryFn: leadsApi.getStats,
    staleTime: 60000, // 1분간 캐시
    retry: 2,
  })

  // [Phase 1.3] 점수 분포 통계
  const { data: scoreStats } = useQuery({
    queryKey: ['leads-score-distribution'],
    queryFn: () => leadsApi.getScoreDistribution().catch(() => null),
    staleTime: 60000, // 1분간 캐시
    retry: 1,
  })

  // 플랫폼별 전환율
  const { data: conversionRates } = useQuery({
    queryKey: ['leads-conversion-rates'],
    queryFn: () => leadsApi.getConversionRates().catch(() => []),
    staleTime: 120000, // 2분간 캐시
    retry: 1,
  })

  // [Phase 4.0] 전환 추적 (ROI 분석)
  const { data: conversionTracking } = useQuery({
    queryKey: ['leads-conversion-tracking'],
    queryFn: () => leadsApi.getConversionTracking().catch(() => null),
    staleTime: 120000, // 2분간 캐시
    retry: 1,
  })

  // [성능 최적화] 활성 탭 또는 칸반 보드에서만 해당 플랫폼 쿼리 활성화
  const isKanban = viewMode === 'kanban'

  // 맘카페(Naver) 리드
  const { data: naverLeads, isLoading: naverLoading, isError: naverError, refetch: refetchNaver } = useQuery({
    queryKey: ['naver-leads', statusFilter],
    queryFn: () => leadsApi.getNaverLeads({
      status: statusFilter || undefined,
      limit: 100
    }),
    staleTime: 60000, // [Phase 7] 30초 → 60초 (API 호출 50% 감소)
    retry: 2,
    enabled: isKanban || activeTab === 'cafe',
  })

  // 당근마켓 리드
  const { data: carrotLeads, isLoading: carrotLoading, isError: carrotError, refetch: refetchCarrot } = useQuery({
    queryKey: ['carrot-leads', statusFilter],
    queryFn: () => leadsApi.getCarrotLeads({
      status: statusFilter || undefined,
      limit: 100
    }),
    staleTime: 60000, // [Phase 7] 30초 → 60초
    retry: 2,
    enabled: isKanban || activeTab === 'carrot',
  })

  // 인플루언서 리드
  const { data: influencerLeads, isLoading: influencerLoading, isError: influencerError, refetch: refetchInfluencer } = useQuery({
    queryKey: ['influencer-leads', statusFilter],
    queryFn: () => leadsApi.getInfluencerLeads({
      status: statusFilter || undefined,
      limit: 100
    }),
    staleTime: 60000, // [Phase 7] 30초 → 60초
    retry: 2,
    enabled: isKanban || activeTab === 'influencer',
  })

  // YouTube 리드
  const { data: youtubeLeads, isLoading: youtubeLoading, isError: youtubeError, refetch: refetchYoutube } = useQuery({
    queryKey: ['youtube-leads', statusFilter],
    queryFn: () => leadsApi.getYoutubeLeads({
      status: statusFilter || undefined,
      limit: 100
    }),
    staleTime: 60000, // [Phase 7] 30초 → 60초
    retry: 2,
    enabled: isKanban || activeTab === 'youtube',
  })

  // TikTok 리드
  const { data: tiktokLeads, isLoading: tiktokLoading, isError: tiktokError, refetch: refetchTiktok } = useQuery({
    queryKey: ['tiktok-leads', statusFilter],
    queryFn: () => leadsApi.getTiktokLeads({
      status: statusFilter || undefined,
      limit: 100
    }),
    staleTime: 60000, // [Phase 7] 30초 → 60초
    retry: 2,
    enabled: isKanban || activeTab === 'tiktok',
  })

  // Instagram 리드
  const { data: instagramLeads, isLoading: instagramLoading, isError: instagramError, refetch: refetchInstagram } = useQuery({
    queryKey: ['instagram-leads', statusFilter],
    queryFn: () => leadsApi.getInstagramLeads({
      status: statusFilter || undefined,
      limit: 100
    }),
    staleTime: 60000, // [Phase 7] 30초 → 60초
    retry: 2,
    enabled: isKanban || activeTab === 'instagram',
  })

  // [Phase 6.1] 중복 리드 감지
  const { data: duplicatesData, isLoading: duplicatesLoading, refetch: refetchDuplicates } = useQuery({
    queryKey: ['leads-duplicates'],
    queryFn: leadsApi.getDuplicates,
    staleTime: 60000, // 1분간 캐시
    retry: 1,
    enabled: activeTab === 'duplicates',
  })

  // 실행 중인 모듈 조회 (페이지 로드 시 상태 복원)
  const { data: runningModules } = useQuery({
    queryKey: ['running-modules'],
    queryFn: () => hudApi.getRunningModules().catch(() => ({ running: [] })),
    refetchInterval: 30000, // 30초마다 확인 (서버 부하 감소)
    retry: 1,
  })

  // 리드 스캔 모듈이 실행 중이면 scanningModule 상태 복원
  useEffect(() => {
    if (!scanningModule && runningModules?.running) {
      const moduleNameMap: Record<string, string> = {
        cafe_swarm: '맘카페 스캔',
        youtube: 'YouTube 스캔',
        tiktok: 'TikTok 스캔',
        carrot_farm: '당근마켓 스캔',
        ambassador: '인플루언서 스캔',
        instagram: 'Instagram 스캔',
      }
      const runningLeadModule = Object.keys(moduleNameMap).find(m => runningModules.running.includes(m))
      if (runningLeadModule) {
        setScanningModule(runningLeadModule)
        setScanningName(moduleNameMap[runningLeadModule])
      }
    }
  }, [runningModules, scanningModule])

  // 스캔 mutation
  const runScan = useMutation({
    mutationFn: (moduleName: string) => hudApi.executeMission(moduleName),
    onSuccess: (_data, moduleName) => {
      const moduleInfo = scanModules[activeTab]
      toast.success(`${moduleInfo?.name || moduleName} 스캔이 시작되었습니다`)
      setScanningModule(moduleName)
      setScanningName(moduleInfo?.name || moduleName)
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`스캔 실패: ${error.response?.data?.detail || error.message}`)
      setScanningModule(null)
      setScanningName('')
    },
  })

  // 리드 업데이트 mutation
  // [Phase 2-1] 선택적 쿼리 무효화로 네트워크 요청 최적화 (7개 → 2개)
  const updateLead = useMutation({
    mutationFn: ({ lead_id, status, notes }: { lead_id: number; status: string; notes?: string; platform?: string }) =>
      leadsApi.updateLead(lead_id, { status, notes }),
    onSuccess: (_data, variables) => {
      toast.success('리드가 업데이트되었습니다')
      // [Phase 2-1] 활성 플랫폼만 무효화 (네트워크 요청 71% 감소)
      const platformKey = variables.platform || activeTab
      const platformQueryMap: Record<string, string> = {
        cafe: 'naver-leads',
        youtube: 'youtube-leads',
        tiktok: 'tiktok-leads',
        instagram: 'instagram-leads',
        carrot: 'carrot-leads',
        influencer: 'influencer-leads',
      }
      const queryKey = platformQueryMap[platformKey]
      if (queryKey) {
        queryClient.invalidateQueries({ queryKey: [queryKey] })
      }
      // 통계는 항상 업데이트
      queryClient.invalidateQueries({ queryKey: ['leads-stats'] })
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`업데이트 실패: ${error.response?.data?.detail || error.message}`)
    },
  })

  // [Phase 7.1] 전환 기록 mutation
  const addConversion = useMutation({
    mutationFn: (data: {
      lead_id: number
      revenue: number
      keyword?: string
      platform?: string
      notes?: string
    }) => leadsApi.addConversion(data),
    onSuccess: () => {
      toast.success('전환이 기록되었습니다')
      queryClient.invalidateQueries({ queryKey: ['leads-conversion-tracking'] })
      queryClient.invalidateQueries({ queryKey: ['leads-conversion-rates'] })
      queryClient.invalidateQueries({ queryKey: ['leads-stats'] })
      setConversionModalOpen(false)
      setConversionLead(null)
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`전환 기록 실패: ${error.response?.data?.detail || error.message}`)
    },
  })

  // [Phase 7.1] 전환 기록 핸들러
  const handleConversionConfirm = (data: {
    lead_id: number
    revenue: number
    keyword?: string
    platform?: string
    notes?: string
  }) => {
    addConversion.mutate(data)
  }

  const handleUpdateLead = (lead_id: number, status: string, notes?: string, platform?: string) => {
    updateLead.mutate({ lead_id, status, notes, platform: platform || activeTab })
  }

  // [Phase 7.1] 전환 기록 모달 표시 핸들러 (LeadTable용)
  const handleConversionWithLead = (lead: { id: number; platform: string; title: string; author?: string }) => {
    // Lead 타입으로 변환 (필수 필드만 사용)
    setConversionLead({
      id: lead.id,
      platform: lead.platform,
      title: lead.title,
      author: lead.author || '',
      source: '',
      content: '',
      url: '',
      status: 'converted',
      detected_at: new Date().toISOString(),
    })
    setConversionModalOpen(true)
  }

  // [Phase 6.1] 중복 리드 병합 mutation
  const mergeDuplicates = useMutation({
    mutationFn: ({ mergeIds, keepId }: { mergeIds: number[]; keepId: number }) =>
      leadsApi.mergeDuplicates(mergeIds, keepId),
    onSuccess: (data) => {
      toast.success(`${data.archived_count}개 중복 리드가 병합되었습니다`)
      queryClient.invalidateQueries({ queryKey: ['leads-duplicates'] })
      queryClient.invalidateQueries({ queryKey: ['leads-stats'] })
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`병합 실패: ${error.response?.data?.detail || error.message}`)
    },
  })

  // [Phase 6.0] 일괄 상태 변경 핸들러
  const handleBulkUpdateStatus = async (leadIds: number[], status: string) => {
    // 순차적으로 업데이트 (Promise.all로 병렬 처리도 가능)
    for (const leadId of leadIds) {
      await leadsApi.updateLead(leadId, { status })
    }
    // 모든 플랫폼별 리드 쿼리 무효화
    queryClient.invalidateQueries({ queryKey: ['naver-leads'] })
    queryClient.invalidateQueries({ queryKey: ['youtube-leads'] })
    queryClient.invalidateQueries({ queryKey: ['tiktok-leads'] })
    queryClient.invalidateQueries({ queryKey: ['instagram-leads'] })
    queryClient.invalidateQueries({ queryKey: ['carrot-leads'] })
    queryClient.invalidateQueries({ queryKey: ['influencer-leads'] })
    queryClient.invalidateQueries({ queryKey: ['leads-stats'] })
  }

  const handleRunScan = (moduleName: string) => {
    runScan.mutate(moduleName)
  }

  const handleMissionComplete = useCallback(() => {
    toast.success('스캔이 완료되었습니다')
    setScanningModule(null)
    setScanningName('')
    // [성능 개선] 현재 탭에 해당하는 쿼리만 새로고침
    invalidateCurrentTab()
  }, [toast, invalidateCurrentTab])

  // [Phase 4.0] 신뢰도 필터 적용 함수 (메모이제이션)
  const filterByTrust = useCallback(<T extends { trust_level?: string }>(leads: T[] | undefined): T[] => {
    if (!leads) return []
    if (!trustFilter) return leads
    return leads.filter(lead => lead.trust_level === trustFilter)
  }, [trustFilter])

  const handleMissionStop = () => {
    toast.info('스캔이 중지되었습니다')
    setScanningModule(null)
    setScanningName('')
  }

  // 탭별 스캔 모듈 매핑
  const scanModules: Record<string, { module: string; name: string }> = {
    cafe: { module: 'cafe_swarm', name: '맘카페 스캔' },
    youtube: { module: 'youtube', name: 'YouTube 스캔' },
    tiktok: { module: 'tiktok', name: 'TikTok 스캔' },
    carrot: { module: 'carrot_farm', name: '당근마켓 스캔' },
    influencer: { module: 'ambassador', name: '인플루언서 스캔' },
    instagram: { module: 'instagram', name: 'Instagram 스캔' },
  }

  const isScanning = scanningModule !== null || runScan.isPending

if (statsLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold mb-2">📋 Lead Manager</h1>
          <p className="text-muted-foreground">여러 플랫폼의 리드를 발굴·관리합니다</p>
        </div>
        <SkeletonStatsGrid cards={6} />
        <div className="bg-card rounded-lg border border-border p-6">
          <SkeletonTable rows={5} columns={6} />
        </div>
      </div>
    )
  }

  if (statsError) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <ErrorState
          title="통계 로드 실패"
          message="리드 통계를 불러오는데 실패했습니다."
          onRetry={() => refetchStats()}
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
          <h1 className="text-3xl font-bold mb-2">📋 Lead Manager</h1>
          <p className="text-muted-foreground">
            여러 플랫폼의 리드를 발굴·관리합니다
          </p>
        </div>
        <div className="flex gap-2 items-center">
          {/* 뷰 모드 토글 */}
          <div className="flex bg-muted rounded-lg p-1">
            <button
              onClick={() => setViewMode('table')}
              className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                viewMode === 'table'
                  ? 'bg-card shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
              aria-pressed={viewMode === 'table'}
              title="테이블 뷰"
            >
              📋 <span className="hidden sm:inline">테이블</span>
            </button>
            <button
              onClick={() => setViewMode('kanban')}
              className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                viewMode === 'kanban'
                  ? 'bg-card shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
              aria-pressed={viewMode === 'kanban'}
              title="칸반 보드"
            >
              📊 <span className="hidden sm:inline">칸반</span>
            </button>
          </div>

          {viewMode === 'table' && (
            <>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-3 py-2 bg-card border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">전체 상태</option>
                <option value="pending">대기 중</option>
                <option value="contacted">연락 완료</option>
                <option value="replied">답변 받음</option>
                <option value="converted">전환 완료</option>
                <option value="rejected">거절됨</option>
              </select>
              {/* [Phase 4.0] 신뢰도 필터 */}
              <select
                value={trustFilter}
                onChange={(e) => setTrustFilter(e.target.value)}
                className="px-3 py-2 bg-card border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">전체 신뢰도</option>
                <option value="trusted">🟢 신뢰</option>
                <option value="review">🟡 확인 필요</option>
                <option value="suspicious">🔴 의심</option>
              </select>
            </>
          )}
          {/* Excel 내보내기 버튼 */}
          <Button
            variant="success"
            onClick={() => {
              exportApi.downloadLeads({
                status: statusFilter || undefined,
                platform: activeTab !== 'all' ? activeTab : undefined
              })
            }}
            icon={<Download size={16} />}
            title="현재 필터 기준으로 리드를 Excel로 내보내기"
          >
            Excel 내보내기
          </Button>
          <Button
            variant="outline"
            onClick={invalidateCurrentTab}
            icon={<RefreshCw size={16} />}
          >
            새로고침
          </Button>
          {isScanning ? (
            <Button
              variant="danger"
              onClick={async () => {
                if (scanningModule) {
                  await hudApi.stopMission(scanningModule)
                  handleMissionStop()
                }
              }}
            >
              ⏹️ 스캔 중지
            </Button>
          ) : (
            <Button
              variant="primary"
              onClick={() => handleRunScan(scanModules[activeTab].module)}
              icon={<Search size={16} />}
            >
              {scanModules[activeTab].name}
            </Button>
          )}
        </div>
      </div>

      {/* 터미널 실행 가이드 */}
      <TerminalGuide commands={getPageCommands('leads')} />

      {/* 실시간 스캔 진행 상황 */}
      {scanningModule && (
        <MissionProgress
          moduleName={scanningModule}
          missionName={scanningName}
          onComplete={handleMissionComplete}
          onStop={handleMissionStop}
        />
      )}

      {/* 탭 네비게이션 */}
      <TabNavigation
        tabs={[
          { id: 'cafe', label: '🏠 맘카페' },
          { id: 'youtube', label: '📺 YouTube' },
          { id: 'tiktok', label: '🎵 TikTok' },
          { id: 'instagram', label: '📸 Instagram' },
          { id: 'carrot', label: '🥕 당근마켓' },
          { id: 'influencer', label: '🤝 인플루언서' },
          { id: 'duplicates', label: `🔄 중복 (${duplicatesData?.total_duplicates || 0})` },
        ]}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        ariaLabel="리드 플랫폼 탭"
      />

      {/* 적용된 필터 칩 표시 */}
      {(statusFilter || trustFilter) && (
        <div className="flex items-center gap-2 flex-wrap" role="status" aria-label="적용된 필터">
          <span className="text-sm text-muted-foreground">필터:</span>
          {statusFilter && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-primary/10 text-primary rounded-full text-sm">
              상태: {statusFilter === 'pending' ? '대기 중' : statusFilter === 'contacted' ? '연락 완료' : statusFilter === 'replied' ? '답변 받음' : statusFilter === 'converted' ? '전환 완료' : '거절됨'}
              <IconButton
                icon={<span>✕</span>}
                onClick={() => setStatusFilter('')}
                size="xs"
                title="상태 필터 제거"
                className="ml-1 hover:text-primary/70"
              />
            </span>
          )}
          {trustFilter && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-primary/10 text-primary rounded-full text-sm">
              신뢰도: {trustFilter === 'trusted' ? '신뢰' : trustFilter === 'review' ? '확인 필요' : '의심'}
              <IconButton
                icon={<span>✕</span>}
                onClick={() => setTrustFilter('')}
                size="xs"
                title="신뢰도 필터 제거"
                className="ml-1 hover:text-primary/70"
              />
            </span>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setStatusFilter('')
              setTrustFilter('')
            }}
          >
            모두 초기화
          </Button>
        </div>
      )}

      {/* 탭 컨텐츠 */}
      {activeTab === 'cafe' && (
        <div className="space-y-6">
          <LeadStats stats={stats ?? null} scoreStats={scoreStats} conversionRates={conversionRates} conversionTracking={conversionTracking} />
          {/* [Phase F-2] 소스 키워드별 리드 통계 */}
          {naverLeads && naverLeads.length > 0 && (
            <LeadAttributionStats leads={naverLeads} />
          )}
          {viewMode === 'kanban' ? (
            naverLoading ? (
              <LoadingState />
            ) : naverError ? (
              <ErrorState
                title="맘카페 리드 로드 실패"
                message="맘카페 리드를 불러오는데 실패했습니다."
                onRetry={() => refetchNaver()}
              />
            ) : !naverLeads || naverLeads.length === 0 ? (
              <EmptyState
                icon="🏠"
                title="맘카페 리드가 없습니다"
                description="맘카페 스캔을 실행하여 리드를 수집하세요."
                onScan={() => handleRunScan('cafe_swarm')}
                isScanning={isScanning}
                secondaryAction={{ label: '📺 YouTube 보기', onClick: () => setActiveTab('youtube') }}
              />
            ) : (
              <KanbanBoard leads={filterByTrust(naverLeads)} onConversionWithLead={handleConversionWithLead} />
            )
          ) : (
            <div className="bg-card rounded-lg border border-border p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold">🏠 맘카페 리드 목록</h2>
                <span className="text-sm text-muted-foreground">
                  {naverLeads?.length || 0}개 리드
                </span>
              </div>
              {naverLoading ? (
                <LoadingState />
              ) : naverError ? (
                <ErrorState
                  title="맘카페 리드 로드 실패"
                  message="맘카페 리드를 불러오는데 실패했습니다."
                  onRetry={() => refetchNaver()}
                />
              ) : !naverLeads || naverLeads.length === 0 ? (
                <EmptyState
                  icon="🏠"
                  title="맘카페 리드가 없습니다"
                  description="맘카페 스캔을 실행하여 리드를 수집하세요."
                  onScan={() => handleRunScan('cafe_swarm')}
                  isScanning={isScanning}
                  secondaryAction={{ label: '📺 YouTube 보기', onClick: () => setActiveTab('youtube') }}
                />
              ) : (
                <LeadTable
                  leads={filterByTrust(naverLeads)}
                  onUpdateStatus={handleUpdateLead}
                  onBulkUpdateStatus={handleBulkUpdateStatus}
                  onConversionWithLead={handleConversionWithLead}
                  viewMode="table"
                />
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === 'youtube' && (
        <div className="space-y-6">
          {viewMode === 'kanban' ? (
            youtubeLoading ? (
              <LoadingState />
            ) : youtubeError ? (
              <ErrorState
                title="YouTube 리드 로드 실패"
                message="YouTube 리드를 불러오는데 실패했습니다."
                onRetry={() => refetchYoutube()}
              />
            ) : !youtubeLeads || youtubeLeads.length === 0 ? (
              <EmptyState
                icon="📺"
                title="YouTube 리드가 없습니다"
                description="YouTube 스캔을 실행하여 관련 영상과 채널을 수집하세요."
                onScan={() => handleRunScan('youtube')}
                isScanning={isScanning}
                secondaryAction={{ label: '🎵 TikTok 보기', onClick: () => setActiveTab('tiktok') }}
              />
            ) : (
              <KanbanBoard leads={filterByTrust(youtubeLeads)} onConversionWithLead={handleConversionWithLead} />
            )
          ) : (
            <div className="bg-card rounded-lg border border-border p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold">📺 YouTube 리드 목록</h2>
                <span className="text-sm text-muted-foreground">
                  {youtubeLeads?.length || 0}개 리드
                </span>
              </div>
              {youtubeLoading ? (
                <LoadingState />
              ) : youtubeError ? (
                <ErrorState
                  title="YouTube 리드 로드 실패"
                  message="YouTube 리드를 불러오는데 실패했습니다."
                  onRetry={() => refetchYoutube()}
                />
              ) : !youtubeLeads || youtubeLeads.length === 0 ? (
                <EmptyState
                  icon="📺"
                  title="YouTube 리드가 없습니다"
                  description="YouTube 스캔을 실행하여 관련 영상과 채널을 수집하세요."
                  onScan={() => handleRunScan('youtube')}
                  isScanning={isScanning}
                  secondaryAction={{ label: '🎵 TikTok 보기', onClick: () => setActiveTab('tiktok') }}
                />
              ) : (
                <LeadTable
                  leads={filterByTrust(youtubeLeads)}
                  onUpdateStatus={handleUpdateLead}
                  onBulkUpdateStatus={handleBulkUpdateStatus}
                  onConversionWithLead={handleConversionWithLead}
                  viewMode="table"
                />
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === 'tiktok' && (
        <div className="space-y-6">
          {viewMode === 'kanban' ? (
            tiktokLoading ? (
              <LoadingState />
            ) : tiktokError ? (
              <ErrorState
                title="TikTok 리드 로드 실패"
                message="TikTok 리드를 불러오는데 실패했습니다."
                onRetry={() => refetchTiktok()}
              />
            ) : !tiktokLeads || tiktokLeads.length === 0 ? (
              <EmptyState
                icon="🎵"
                title="TikTok 리드가 없습니다"
                description="TikTok 스캔을 실행하여 관련 콘텐츠를 수집하세요."
                onScan={() => handleRunScan('tiktok')}
                isScanning={isScanning}
              />
            ) : (
              <KanbanBoard leads={filterByTrust(tiktokLeads)} onConversionWithLead={handleConversionWithLead} />
            )
          ) : (
            <div className="bg-card rounded-lg border border-border p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold">🎵 TikTok 리드 목록</h2>
                <span className="text-sm text-muted-foreground">
                  {tiktokLeads?.length || 0}개 리드
                </span>
              </div>
              {tiktokLoading ? (
                <LoadingState />
              ) : tiktokError ? (
                <ErrorState
                  title="TikTok 리드 로드 실패"
                  message="TikTok 리드를 불러오는데 실패했습니다."
                  onRetry={() => refetchTiktok()}
                />
              ) : !tiktokLeads || tiktokLeads.length === 0 ? (
                <EmptyState
                  icon="🎵"
                  title="TikTok 리드가 없습니다"
                  description="TikTok 스캔을 실행하여 관련 콘텐츠를 수집하세요."
                  onScan={() => handleRunScan('tiktok')}
                  isScanning={isScanning}
                />
              ) : (
                <LeadTable
                  leads={filterByTrust(tiktokLeads)}
                  onUpdateStatus={handleUpdateLead}
                  onBulkUpdateStatus={handleBulkUpdateStatus}
                  onConversionWithLead={handleConversionWithLead}
                  viewMode="table"
                />
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === 'instagram' && (
        <div className="space-y-6">
          {viewMode === 'kanban' ? (
            instagramLoading ? (
              <LoadingState />
            ) : instagramError ? (
              <ErrorState
                title="Instagram 리드 로드 실패"
                message="Instagram 리드를 불러오는데 실패했습니다."
                onRetry={() => refetchInstagram()}
              />
            ) : !instagramLeads || instagramLeads.length === 0 ? (
              <EmptyState
                icon="📸"
                title="Instagram 리드가 없습니다"
                description="Instagram 스캔을 실행하여 관련 콘텐츠와 인플루언서를 수집하세요."
                onScan={() => handleRunScan('instagram')}
                isScanning={isScanning}
              />
            ) : (
              <KanbanBoard leads={filterByTrust(instagramLeads)} onConversionWithLead={handleConversionWithLead} />
            )
          ) : (
            <div className="bg-card rounded-lg border border-border p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold">📸 Instagram 리드 목록</h2>
                <span className="text-sm text-muted-foreground">
                  {instagramLeads?.length || 0}개 리드
                </span>
              </div>
              {instagramLoading ? (
                <LoadingState />
              ) : instagramError ? (
                <ErrorState
                  title="Instagram 리드 로드 실패"
                  message="Instagram 리드를 불러오는데 실패했습니다."
                  onRetry={() => refetchInstagram()}
                />
              ) : !instagramLeads || instagramLeads.length === 0 ? (
                <EmptyState
                  icon="📸"
                  title="Instagram 리드가 없습니다"
                  description="Instagram 스캔을 실행하여 관련 콘텐츠와 인플루언서를 수집하세요."
                  onScan={() => handleRunScan('instagram')}
                  isScanning={isScanning}
                />
              ) : (
                <LeadTable
                  leads={filterByTrust(instagramLeads)}
                  onUpdateStatus={handleUpdateLead}
                  onBulkUpdateStatus={handleBulkUpdateStatus}
                  onConversionWithLead={handleConversionWithLead}
                  viewMode="table"
                />
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === 'carrot' && (
        <div className="space-y-6">
          {viewMode === 'kanban' ? (
            carrotLoading ? (
              <LoadingState />
            ) : carrotError ? (
              <ErrorState
                title="당근마켓 리드 로드 실패"
                message="당근마켓 리드를 불러오는데 실패했습니다."
                onRetry={() => refetchCarrot()}
              />
            ) : !carrotLeads || carrotLeads.length === 0 ? (
              <EmptyState
                icon="🥕"
                title="당근마켓 리드가 없습니다"
                description="당근마켓 스캔을 실행하여 지역 기반 리드를 수집하세요."
                onScan={() => handleRunScan('carrot_farm')}
                isScanning={isScanning}
              />
            ) : (
              <KanbanBoard leads={filterByTrust(carrotLeads)} onConversionWithLead={handleConversionWithLead} />
            )
          ) : (
            <div className="bg-card rounded-lg border border-border p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold">🥕 당근마켓 리드 목록</h2>
                <span className="text-sm text-muted-foreground">
                  {carrotLeads?.length || 0}개 리드
                </span>
              </div>
              {carrotLoading ? (
                <LoadingState />
              ) : carrotError ? (
                <ErrorState
                  title="당근마켓 리드 로드 실패"
                  message="당근마켓 리드를 불러오는데 실패했습니다."
                  onRetry={() => refetchCarrot()}
                />
              ) : !carrotLeads || carrotLeads.length === 0 ? (
                <EmptyState
                  icon="🥕"
                  title="당근마켓 리드가 없습니다"
                  description="당근마켓 스캔을 실행하여 지역 기반 리드를 수집하세요."
                  onScan={() => handleRunScan('carrot_farm')}
                  isScanning={isScanning}
                />
              ) : (
                <LeadTable
                  leads={filterByTrust(carrotLeads)}
                  onUpdateStatus={handleUpdateLead}
                  onBulkUpdateStatus={handleBulkUpdateStatus}
                  onConversionWithLead={handleConversionWithLead}
                  viewMode="table"
                />
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === 'influencer' && (
        <div className="space-y-6">
          {viewMode === 'kanban' ? (
            influencerLoading ? (
              <LoadingState />
            ) : influencerError ? (
              <ErrorState
                title="인플루언서 리드 로드 실패"
                message="인플루언서 리드를 불러오는데 실패했습니다."
                onRetry={() => refetchInfluencer()}
              />
            ) : !influencerLeads || influencerLeads.length === 0 ? (
              <EmptyState
                icon="🤝"
                title="인플루언서 리드가 없습니다"
                description="인플루언서 스캔을 실행하여 협업 후보를 발굴하세요."
                onScan={() => handleRunScan('ambassador')}
                isScanning={isScanning}
              />
            ) : (
              <KanbanBoard leads={filterByTrust(influencerLeads)} onConversionWithLead={handleConversionWithLead} />
            )
          ) : (
            <div className="bg-card rounded-lg border border-border p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold">🤝 인플루언서 리드 목록</h2>
                <span className="text-sm text-muted-foreground">
                  {influencerLeads?.length || 0}개 리드
                </span>
              </div>
              {influencerLoading ? (
                <LoadingState />
              ) : influencerError ? (
                <ErrorState
                  title="인플루언서 리드 로드 실패"
                  message="인플루언서 리드를 불러오는데 실패했습니다."
                  onRetry={() => refetchInfluencer()}
                />
              ) : !influencerLeads || influencerLeads.length === 0 ? (
                <EmptyState
                  icon="🤝"
                  title="인플루언서 리드가 없습니다"
                  description="인플루언서 스캔을 실행하여 협업 후보를 발굴하세요."
                  onScan={() => handleRunScan('ambassador')}
                  isScanning={isScanning}
                />
              ) : (
                <LeadTable
                  leads={filterByTrust(influencerLeads)}
                  onUpdateStatus={handleUpdateLead}
                  onBulkUpdateStatus={handleBulkUpdateStatus}
                  onConversionWithLead={handleConversionWithLead}
                  viewMode="table"
                />
              )}
            </div>
          )}
        </div>
      )}

      {/* [Phase 6.1] 중복 리드 탭 */}
      {activeTab === 'duplicates' && (
        <div className="space-y-6">
          <div className="bg-card rounded-lg border border-border p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold">🔄 중복 리드 관리</h2>
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">
                  {duplicatesData?.total_groups || 0}개 그룹, {duplicatesData?.total_duplicates || 0}개 중복
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => refetchDuplicates()}
                  icon={<RefreshCw size={14} />}
                >
                  새로고침
                </Button>
              </div>
            </div>

            {duplicatesLoading ? (
              <LoadingState />
            ) : !duplicatesData?.duplicate_groups || duplicatesData.duplicate_groups.length === 0 ? (
              <div className="text-center py-12" role="status">
                <p className="text-6xl mb-4">✨</p>
                <p className="text-xl font-semibold mb-2">중복 리드가 없습니다</p>
                <p className="text-muted-foreground">모든 리드가 고유합니다.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {duplicatesData.duplicate_groups.map((group: {
                  url: string
                  count: number
                  leads: Array<{
                    id: number
                    platform: string
                    title: string
                    url: string
                    status: string
                    author: string
                    created_at: string
                    is_original: boolean
                  }>
                }, groupIdx: number) => (
                  <div
                    key={groupIdx}
                    className="border border-border rounded-lg p-4 hover:border-primary/30 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 bg-red-500/10 text-red-500 rounded text-xs font-medium">
                          {group.count}개 중복
                        </span>
                        <a
                          href={group.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm text-muted-foreground hover:text-primary truncate max-w-[400px]"
                        >
                          {group.url}
                        </a>
                      </div>
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => {
                          const originalLead = group.leads.find(l => l.is_original)
                          if (originalLead) {
                            const allIds = group.leads.map(l => l.id)
                            mergeDuplicates.mutate({ mergeIds: allIds, keepId: originalLead.id })
                          }
                        }}
                        loading={mergeDuplicates.isPending}
                      >
                        🔗 자동 병합
                      </Button>
                    </div>

                    <div className="space-y-2">
                      {group.leads.map((lead) => (
                        <div
                          key={lead.id}
                          className={`flex items-center justify-between p-2 rounded ${
                            lead.is_original
                              ? 'bg-green-500/10 border border-green-500/30'
                              : 'bg-muted/50'
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            {lead.is_original && (
                              <span className="px-2 py-0.5 bg-green-500/20 text-green-600 rounded text-xs font-medium">
                                원본
                              </span>
                            )}
                            <span className="text-sm font-medium truncate max-w-[300px]">
                              {lead.title || '제목 없음'}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {lead.platform}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <span>{lead.status}</span>
                            <span>•</span>
                            <span>{new Date(lead.created_at).toLocaleDateString('ko-KR')}</span>
                            {!lead.is_original && (
                              <Button
                                variant="outline"
                                size="xs"
                                onClick={() => {
                                  const allIds = group.leads.map(l => l.id)
                                  mergeDuplicates.mutate({ mergeIds: allIds, keepId: lead.id })
                                }}
                                disabled={mergeDuplicates.isPending}
                              >
                                이것을 원본으로
                              </Button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* [Phase 7.1] 전환 기록 모달 */}
      <ConversionModal
        isOpen={conversionModalOpen}
        onClose={() => {
          setConversionModalOpen(false)
          setConversionLead(null)
        }}
        onConfirm={handleConversionConfirm}
        lead={conversionLead}
        loading={addConversion.isPending}
      />
    </div>
    </PageTransition>
  )
}

// 로딩 상태 컴포넌트
function LoadingState() {
  return (
    <div className="text-center py-8">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-2" />
      <p className="text-sm text-muted-foreground">로딩 중...</p>
    </div>
  )
}

// 빈 상태 컴포넌트
interface EmptyStateProps {
  icon: string
  title: string
  description: string
  onScan: () => void
  isScanning: boolean
  secondaryAction?: {
    label: string
    onClick: () => void
  }
}

function EmptyState({
  icon,
  title,
  description,
  onScan,
  isScanning,
  secondaryAction
}: EmptyStateProps) {
  return (
    <div className="text-center py-12" role="status" aria-label={title}>
      <p className="text-6xl mb-4" aria-hidden="true">{icon}</p>
      <p className="text-xl font-semibold mb-2">{title}</p>
      <p className="text-muted-foreground mb-6">{description}</p>
      <div className="flex items-center justify-center gap-3">
        <Button
          variant="primary"
          size="lg"
          onClick={onScan}
          loading={isScanning}
          icon={<Search size={16} />}
        >
          스캔 시작
        </Button>
        {secondaryAction && (
          <Button
            variant="outline"
            size="lg"
            onClick={secondaryAction.onClick}
          >
            {secondaryAction.label}
          </Button>
        )}
      </div>
    </div>
  )
}

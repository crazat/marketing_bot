import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { viralApi, hudApi } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import ErrorState from '@/components/ui/ErrorState'
import type { FilterState, ScanBatch } from '@/components/viral/FilterBar'
import { HomeView, WorkView, ListView, CompletionView } from '@/components/viral/views'
import ShortcutsOverlay from '@/components/viral/ShortcutsOverlay'
import SkipReasonModal from '@/components/viral/SkipReasonModal'
import BulkConfirmModal, { type BulkAction } from '@/components/ui/BulkConfirmModal'
import { ViralTargetData as ViralTarget } from '@/types/viral'
import { useLoadingState } from '@/hooks/useLoadingState'
import { getToastErrorMessage } from '@/utils/errorMessages'
import { useRecentItems } from '@/hooks/useRecentItems'
import { useResumeState } from '@/hooks/useResumeState'
import { useOfflineQueue } from '@/hooks/useOfflineQueue'
import { invalidateViralAll, invalidateViralAndLeads } from '@/lib/queryInvalidation'
import { useActionJournal } from '@/hooks/useActionJournal'
import { useFatigueDetector } from '@/hooks/useFatigueDetector'

export default function ViralHunter() {
  const [view, setView] = useState<'home' | 'list' | 'work' | 'completion'>('home')
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [categoryTargets, setCategoryTargets] = useState<ViralTarget[]>([])
  const [expandedTargetId, setExpandedTargetId] = useState<string | null>(null)
  const [expandedComments, setExpandedComments] = useState<Record<string, string>>({})
  const [generatingTargetId, setGeneratingTargetId] = useState<string | null>(null)
  const [completionStats, setCompletionStats] = useState({
    approved: 0,
    skipped: 0,
    deleted: 0,
  })
  const [scanningModule, setScanningModule] = useState<string | null>(null)
  // [U3] 단축키 도움말 오버레이
  const [showShortcuts, setShowShortcuts] = useState(false)
  // [F2] 스킵 사유 모달 (target_id 저장)
  const [skipReasonFor, setSkipReasonFor] = useState<string | null>(null)
  const [showScanSettings, setShowScanSettings] = useState(false)
  const [scanSettings, setScanSettings] = useState({
    platforms: ['cafe', 'blog', 'kin', 'place', 'karrot', 'youtube', 'instagram', 'tiktok'] as string[],
    maxResults: 500,
  })

  // [X2] URL 쿼리 → filters 초기값 (lazy init으로 1회만 평가)
  const [searchParams, setSearchParams] = useSearchParams()
  // 필터 상태 — 마운트 시 URL 또는 골든큐 default
  const [filters, setFilters] = useState<FilterState>(() => {
    const platforms = searchParams.get('platforms')
    const hasAnyFilter = ['status', 'sort', 'category', 'comment_status', 'date_filter',
      'search', 'scan_batch', 'platforms', 'min_scan_count',
      'ai_ad_label', 'specialty_match', 'post_region', 'work_scope'].some(k => searchParams.get(k))
    if (!hasAnyFilter) {
      // Default staff queue: latest Legion scan, core clinic categories, pending targets.
      return {
        status: 'pending',
        sort: 'priority',
        work_scope: 'latest_legion',
      }
    }
    return {
      status: searchParams.get('status') ?? 'pending',
      sort: searchParams.get('sort') ?? 'priority',
      category: searchParams.get('category') ?? undefined,
      comment_status: searchParams.get('comment_status') ?? undefined,
      date_filter: searchParams.get('date_filter') ?? undefined,
      search: searchParams.get('search') ?? undefined,
      scan_batch: searchParams.get('scan_batch') ?? undefined,
      platforms: platforms ? platforms.split(',').filter(Boolean) : undefined,
      min_scan_count: searchParams.get('min_scan_count')
        ? Number(searchParams.get('min_scan_count'))
        : undefined,
      ai_ad_label: searchParams.get('ai_ad_label') ?? undefined,
      specialty_match: searchParams.get('specialty_match') ?? undefined,
      post_region: searchParams.get('post_region') ?? undefined,
      work_scope: (searchParams.get('work_scope') as FilterState['work_scope']) ?? 'latest_legion',
    }
  })

  // [X2] filters 변경 시 URL 동기화 — setSearchParams reference 의존성 제거 (무한 루프 방지)
  useEffect(() => {
    const params = new URLSearchParams()
    if (filters.status && filters.status !== 'pending') params.set('status', filters.status)
    if (filters.sort && filters.sort !== 'priority') params.set('sort', filters.sort)
    if (filters.category) params.set('category', filters.category)
    if (filters.comment_status) params.set('comment_status', filters.comment_status)
    if (filters.date_filter) params.set('date_filter', filters.date_filter)
    if (filters.search) params.set('search', filters.search)
    if (filters.scan_batch) params.set('scan_batch', filters.scan_batch)
    if (filters.platforms && filters.platforms.length > 0) {
      params.set('platforms', filters.platforms.join(','))
    }
    if (filters.min_scan_count) params.set('min_scan_count', String(filters.min_scan_count))
    if (filters.ai_ad_label) params.set('ai_ad_label', filters.ai_ad_label)
    if (filters.specialty_match) params.set('specialty_match', filters.specialty_match)
    if (filters.post_region) params.set('post_region', filters.post_region)
    if (filters.work_scope && filters.work_scope !== 'latest_legion') params.set('work_scope', filters.work_scope)
    setSearchParams(params, { replace: true })
  }, [filters])

  // 홈 화면 스캔 배치 필터
  const [homeScanBatch, setHomeScanBatch] = useState<string>('')

  // 대량 액션 상태
  const [selectedTargets, setSelectedTargets] = useState<Set<string>>(new Set())
  const [isProcessingBulk, setIsProcessingBulk] = useState(false)
  const [bulkActionConfirm, setBulkActionConfirm] = useState<{
    action: 'approve' | 'skip' | 'delete'
    count: number
  } | null>(null)

  // 페이지네이션 상태
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)

  // [Phase 6.0] 일괄 검증 상태 + [F5] 진행률
  const [isVerifying, setIsVerifying] = useState(false)
  const [verifyLimit, setVerifyLimit] = useState(50)
  const [verifyProgress, setVerifyProgress] = useState<{
    status: 'queued' | 'running' | 'done' | 'error'
    total: number
    commentable: number
    not_commentable: number
  } | null>(null)
  const [verifyResults, setVerifyResults] = useState<{
    total: number
    commentable: number
    not_commentable: number
  } | null>(null)

  // AI 댓글 일괄 생성 상태
  const [isGeneratingComments, setIsGeneratingComments] = useState(false)
  const [generationProgress, setGenerationProgress] = useState<{
    current: number
    total: number
  } | null>(null)

  // AI 댓글 스타일 상태
  const [selectedCommentStyle, setSelectedCommentStyle] = useState<string>('default')

  // [Phase 8.0] 리드 추적 연결 모달
  const [leadTrackingModal, setLeadTrackingModal] = useState<{
    isOpen: boolean
    targetTitle: string
    leadCreated: boolean
  }>({ isOpen: false, targetTitle: '', leadCreated: false })

  const queryClient = useQueryClient()
  const toast = useToast()
  const { record: recordRecent } = useRecentItems()
  const { initial: resumeInitial, record: recordResume, clear: clearResume } = useResumeState('viral-hunter')
  const [resumeBannerDismissed, setResumeBannerDismissed] = useState(false)
  const { log: logJournal } = useActionJournal()
  const { markAction: markFatigueAction } = useFatigueDetector()

  // [Y5] 오프라인 액션 큐 — mutation 실패 시 또는 오프라인 중 저장
  const dedupeCountRef = useRef(0)
  const { queue: offlineQueue, isOnline, enqueue: enqueueOffline, clearQueue: clearOfflineQueue } = useOfflineQueue(
    async (action) => {
      if (action.kind === 'viral_action') {
        const resp = await viralApi.targetAction(
          action.payload.target_id,
          action.payload.action,
          action.payload.comment,
          action.payload.skip_reason,
          action.payload.skip_note,
          action.id, // [AA4] idempotency key — 큐 entry ID 재사용
        )
        // [DD3] 서버가 중복 감지하면 조용히 카운트만 집계
        if (resp?.deduplicated) {
          dedupeCountRef.current += 1
        }
      }
    },
    {
      onFlushSuccess: (count) => {
        const deduped = dedupeCountRef.current
        dedupeCountRef.current = 0
        if (deduped > 0) {
          toast.success(
            `📡 ${count}건 전송 완료 (이미 처리된 ${deduped}건은 제외)`,
          )
        } else {
          toast.success(`📡 오프라인 중 쌓인 ${count}건을 전송했습니다`)
        }
        invalidateViralAndLeads(queryClient)
      },
      onActionFailed: (action) => {
        toast.error(`❌ 재전송 실패: 타겟 #${action.payload.target_id} ${action.payload.action}`)
      },
    },
  )

  // [X7] view/category/expandedTargetId 변경 시 resume 상태 저장
  useEffect(() => {
    if (view === 'work' && selectedCategory) {
      recordResume({
        view,
        category: selectedCategory,
        expandedTargetId,
        label: `${selectedCategory} 카테고리 작업`,
      })
    }
  }, [view, selectedCategory, expandedTargetId, recordResume])

  // 전체 통계
  const { data: stats, isError: statsError } = useQuery({
    queryKey: ['viral-stats'],
    queryFn: () => viralApi.getStats().catch(() => null),
    staleTime: 60000, // 1분간 캐시
    retry: 2,
  })

  // 스캔 배치 목록
  const { data: scanBatches = [], isError: scanBatchesError } = useQuery<ScanBatch[]>({
    queryKey: ['viral-scan-batches'],
    queryFn: () => viralApi.getScanBatches().catch(() => []),
    staleTime: 60000, // 1분간 캐시
    retry: 2,
  })

  // 실행 중인 모듈 조회 - 적응형 폴링 (스캔 중 5초, 유휴 시 60초)
  const { data: runningModules, isError: runningModulesError } = useQuery({
    queryKey: ['running-modules'],
    queryFn: () => hudApi.getRunningModules().catch(() => ({ running: [] })),
    refetchInterval: (query) => {
      const data = query.state.data as { running?: string[] } | undefined
      const hasRunningScan = data?.running && data.running.length > 0
      return hasRunningScan ? 5000 : 60000
    },
    staleTime: 3000,
    retry: 1,
  })

  // viral_hunter 모듈이 실행 중이면 scanningModule 상태 복원
  useEffect(() => {
    if (runningModules?.running?.includes('viral_hunter') && !scanningModule) {
      setScanningModule('viral_hunter')
    }
  }, [runningModules, scanningModule])

  // [Phase 9.0] 홈 화면용 집계 통계 (DB 직접 집계 - 성능 최적화)
  const { data: homeStats, isError: homeStatsError } = useQuery({
    queryKey: ['viral-home-stats', homeScanBatch],
    queryFn: () => viralApi.getHomeStats(homeScanBatch || undefined).catch(() => ({
      total_count: 0,
      platform_stats: {},
      category_stats: [],
      status_stats: {},
      score_distribution: {}
    })),
    staleTime: 60000, // [Phase 7] 30초 → 60초 (API 호출 감소)
    enabled: view === 'home', // 홈 화면에서만 로드
    retry: 2,
  })

  const { data: qualitySummary } = useQuery({
    queryKey: ['viral-quality-summary'],
    queryFn: () => viralApi.getQualitySummary(14).catch(() => null),
    staleTime: 60000,
    enabled: view === 'home',
    retry: 1,
  })

  const { data: opsStatus } = useQuery({
    queryKey: ['viral-ops-status'],
    queryFn: () => viralApi.getOpsStatus().catch(() => null),
    staleTime: 60000,
    enabled: view === 'home',
    retry: 1,
  })

  // 필터링된 타겟 (list view용) - 서버 페이지네이션
  const effectiveStatus = filters.comment_status || filters.status || 'pending'
  const offset = (currentPage - 1) * pageSize
  const {
    data: filteredTargets,
    isLoading: isLoadingFiltered,
    isFetching: isFetchingFiltered,
    isError: filteredTargetsError
  } = useQuery({
    queryKey: ['viral-filtered-targets', filters, currentPage, pageSize],
    queryFn: () => viralApi.getTargets(
      effectiveStatus,
      undefined,
      pageSize,
      {
        date_filter: filters.date_filter,
        platforms: filters.platforms,
        category: filters.category,
        min_scan_count: filters.min_scan_count,
        search: filters.search,
        sort: filters.sort,
        scan_batch: filters.scan_batch,
        offset,
        ai_ad_label: filters.ai_ad_label,
        min_confidence: filters.min_confidence,
        specialty_match: filters.specialty_match,
        post_region: filters.post_region,
        work_scope: filters.work_scope || 'latest_legion',
      }
    ).catch(() => []),
    enabled: view === 'list',
    staleTime: 60000,
    retry: 1,
    placeholderData: (prev: unknown) => prev,
  })

  // 총 개수 조회 (필터 조건만 변경 시 재조회, 페이지 변경 시 재사용)
  const { data: totalCountData } = useQuery({
    queryKey: ['viral-filtered-targets-count', filters],
    queryFn: () => viralApi.getTargetsCount(
      effectiveStatus,
      undefined,
      {
        date_filter: filters.date_filter,
        platforms: filters.platforms,
        category: filters.category,
        min_scan_count: filters.min_scan_count,
        search: filters.search,
        scan_batch: filters.scan_batch,
        ai_ad_label: filters.ai_ad_label,
        min_confidence: filters.min_confidence,
        specialty_match: filters.specialty_match,
        post_region: filters.post_region,
        work_scope: filters.work_scope || 'latest_legion',
      }
    ).catch(() => ({ total: 0 })),
    enabled: view === 'list',
    staleTime: 60000,
    retry: 1,
  })

  // [UX 개선] 로딩 상태 통합
  const filteredLoadingState = useLoadingState({
    isLoading: isLoadingFiltered,
    isFetching: isFetchingFiltered,
  })

  // 댓글 템플릿 조회
  const { data: templates = [], isError: templatesError } = useQuery<Array<{
    id: number
    name: string
    content: string
    category: string
    use_count: number
  }>>({
    queryKey: ['comment-templates'],
    queryFn: () => viralApi.getTemplates().catch(() => []),
    staleTime: 300000, // 5분간 캐시 (자주 변하지 않음)
    retry: 1,
  })

  // 댓글 스타일 조회
  const { data: commentStylesData, isError: commentStylesError } = useQuery({
    queryKey: ['comment-styles'],
    queryFn: () => viralApi.getCommentStyles().catch(() => ({ success: false, styles: [] })),
    staleTime: 300000, // 5분간 캐시 (자주 변하지 않음)
    retry: 1,
  })
  const commentStyles = commentStylesData?.styles || []

  // 에러 상태 (디버깅용) - 콘솔에서 확인 가능
  const _hasErrors = statsError || scanBatchesError || runningModulesError || homeStatsError || filteredTargetsError || templatesError || commentStylesError
  if (_hasErrors) console.debug('ViralHunter API errors detected')

  // [Phase 9.0] 카테고리 통계 (백엔드 집계)
  const categoryStats = homeStats?.category_stats || []

  // [Phase 9.0] 플랫폼별 통계 (백엔드 집계)
  const platformStats = homeStats?.platform_stats || {}

  // 스캔 mutation (viralApi 사용 - 설정 전달)
  const runScanMutation = useMutation({
    mutationFn: () => viralApi.runScan({
      platforms: scanSettings.platforms,
      max_results: scanSettings.maxResults,
      use_latest_legion: true,
      fresh: true,
    }),
    onSuccess: (data) => {
      toast.success(`바이럴 스캔 시작! (${data.platforms?.length || 0}개 플랫폼, 최대 ${data.max_results === 0 ? '무제한' : data.max_results + '개'})`)
      setScanningModule('viral_hunter')
    },
    onError: (error: Error) => {
      toast.error(getToastErrorMessage(error, '스캔 실패'))
      setScanningModule(null)
    },
  })

  // [Phase 4.0] 댓글 가능 여부 검증 mutation
  const verifyTargetMutation = useMutation({
    mutationFn: (targetId: string) => viralApi.verifyTarget(targetId),
    onSuccess: (data) => {
      if (data.verification?.commentable) {
        toast.success('댓글 작성 가능한 타겟입니다')
      } else {
        toast.warning(`댓글 불가: ${data.verification?.reason || '알 수 없음'}`)
      }
      queryClient.invalidateQueries({ queryKey: ['viral-all-targets'] })
    },
    onError: (error: Error) => {
      toast.error(getToastErrorMessage(error, '검증 실패'))
    },
  })

  const handleVerifyTarget = (targetId: string) => {
    verifyTargetMutation.mutate(targetId)
  }

  // [F5] 일괄 검증 핸들러 — 백그라운드 job + 폴링
  const handleBatchVerify = useCallback(async (category?: string, limit = 20) => {
    setIsVerifying(true)
    setVerifyResults(null)
    setVerifyProgress({ status: 'queued', total: 0, commentable: 0, not_commentable: 0 })
    try {
      const start = await viralApi.verifyBatchStart(category, limit)
      const jobId = start.job_id

      const POLL_INTERVAL = 2000  // 2초
      const MAX_POLLS = 300       // 최대 10분
      let polls = 0

      while (polls < MAX_POLLS) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL))
        polls += 1
        try {
          const status = await viralApi.verifyBatchStatus(jobId)
          setVerifyProgress({
            status: status.status,
            total: status.total,
            commentable: status.commentable,
            not_commentable: status.not_commentable,
          })
          if (status.status === 'done') {
            setVerifyResults({
              total: status.total,
              commentable: status.commentable,
              not_commentable: status.not_commentable,
            })
            toast.success(`검증 완료: ${status.commentable}/${status.total} 댓글 가능`)
            queryClient.invalidateQueries({ queryKey: ['viral-all-targets'] })
            queryClient.invalidateQueries({ queryKey: ['viral-filtered-targets'] })
            break
          }
          if (status.status === 'error') {
            toast.error(`검증 실패: ${status.error ?? '알 수 없는 오류'}`)
            break
          }
        } catch (pollErr) {
          // 일시 네트워크 오류는 계속 폴링
          console.warn('[verify] poll error', pollErr)
        }
      }
      if (polls >= MAX_POLLS) {
        toast.warning('검증이 오래 걸립니다. 완료 시 새로고침하세요.')
      }
    } catch (error: unknown) {
      toast.error(getToastErrorMessage(error, '일괄 검증 시작 실패'))
    } finally {
      setIsVerifying(false)
      setVerifyProgress(null)
    }
  }, [toast, queryClient])

  // [성능 개선] useCallback으로 핸들러 메모이제이션
  const handleMissionComplete = useCallback(() => {
    toast.success('바이럴 타겟 스캔이 완료되었습니다')
    setScanningModule(null)
    queryClient.invalidateQueries({ queryKey: ['viral-all-targets'] })
    queryClient.invalidateQueries({ queryKey: ['viral-stats'] })
  }, [toast, queryClient])

  const handleMissionStop = useCallback(() => {
    toast.info('스캔이 중지되었습니다')
    setScanningModule(null)
  }, [toast])

  // 필터 변경 핸들러
  const handleFilterChange = useCallback((newFilters: FilterState) => {
    setFilters(newFilters)
    setCurrentPage(1) // 필터 변경 시 첫 페이지로
    setSelectedTargets(new Set()) // 필터 변경 시 선택 초기화
  }, [])

  // 필터 초기화 핸들러
  const handleFilterReset = useCallback(() => {
    setFilters({
      status: 'pending',
      sort: 'priority',
      category: undefined,
      comment_status: undefined,
    })
    setCurrentPage(1)
    setSelectedTargets(new Set())
  }, [])

  // [V2] KPI 카드 클릭 → 해당 필터 적용 후 ListView 진입
  const handleKpiNavigate = useCallback(
    (target: 'pending' | 'today_processed' | 'week_processed' | 'hot_pending') => {
      let next: FilterState
      switch (target) {
        case 'pending':
          next = { status: 'pending', sort: 'priority' }
          break
        case 'hot_pending':
          next = { status: 'pending', sort: 'priority', min_scan_count: undefined }
          // HOT LEAD는 priority_score 100+ — 현재 FilterState엔 점수 필터 없으므로 정렬만 priority로
          break
        case 'today_processed':
          // 오늘 승인된 것 중심 (가장 많이 보고 싶은 상태)
          next = { status: 'posted', sort: 'date', date_filter: '오늘' }
          break
        case 'week_processed':
          next = { status: 'posted', sort: 'date', date_filter: '최근 7일' }
          break
      }
      setFilters(next)
      setCurrentPage(1)
      setSelectedTargets(new Set())
      setView('list')
    },
    []
  )

  // 스캔 중지 핸들러
  const stopScan = useCallback(async () => {
    try {
      await hudApi.stopMission('viral_hunter')
      toast.info('스캔 중지 요청됨')
      setScanningModule(null)
    } catch (error: unknown) {
      toast.error(getToastErrorMessage(error, '스캔 중지 실패'))
    }
  }, [toast])

  // AI 댓글 일괄 생성 핸들러
  const handleBulkGenerateComments = async () => {
    if (selectedTargets.size === 0) {
      toast.warning('선택된 타겟이 없습니다')
      return
    }

    setIsGeneratingComments(true)
    setGenerationProgress({ current: 0, total: selectedTargets.size })

    const targetIds = Array.from(selectedTargets)
    let successCount = 0
    let failCount = 0

    try {
      // 배치 API 사용 (5개씩)
      const batchSize = 5
      for (let i = 0; i < targetIds.length; i += batchSize) {
        const batch = targetIds.slice(i, i + batchSize)

        // 각 배치에서 개별 요청 (병렬) — 응답의 comment를 expandedComments에 누적
        const promises = batch.map(async (targetId) => {
          try {
            const result = await viralApi.generateComment(targetId)
            if (result?.comment) {
              setExpandedComments(prev => ({ ...prev, [String(targetId)]: result.comment }))
            }
            successCount++
            return true
          } catch {
            failCount++
            return false
          }
        })

        await Promise.all(promises)

        // 진행률 업데이트
        setGenerationProgress({
          current: Math.min(i + batchSize, targetIds.length),
          total: targetIds.length
        })
      }

      if (successCount > 0) {
        toast.success(`✨ ${successCount}개 타겟에 AI 댓글이 생성되었습니다!`)
        queryClient.invalidateQueries({ queryKey: ['viral-filtered-targets'] })
        queryClient.invalidateQueries({ queryKey: ['viral-all-targets'] })
      }

      if (failCount > 0) {
        toast.warning(`⚠️ ${failCount}개 타겟 댓글 생성 실패`)
      }
    } catch (error: unknown) {
      toast.error(getToastErrorMessage(error, 'AI 댓글 생성 실패'))
    } finally {
      setIsGeneratingComments(false)
      setGenerationProgress(null)
    }
  }

  // [Phase 9.0] 카테고리 선택 핸들러 - API에서 해당 카테고리만 로드 (성능 최적화)
  const handleSelectCategory = async (category: string) => {
    setSelectedCategory(category)
    setExpandedTargetId(null)
    setExpandedComments({})
    setCompletionStats({ approved: 0, skipped: 0, deleted: 0 })
    setView('work')

    try {
      // 해당 카테고리 타겟만 API에서 로드 (최대 500개, 우선순위순)
      const targets = await viralApi.getTargets('pending', category, 500, {
        sort: 'priority',
        scan_batch: homeScanBatch || undefined,
        work_scope: 'latest_legion',
      })
      setCategoryTargets(targets || [])
    } catch (error) {
      console.error('카테고리 타겟 로드 실패:', error)
      toast.error('타겟 로드에 실패했습니다')
      setCategoryTargets([])
    }
  }

  // 타겟 펼치기/접기
  const toggleExpand = (targetId: string) => {
    if (expandedTargetId === targetId) {
      setExpandedTargetId(null)
    } else {
      setExpandedTargetId(targetId)
      // [U5] 최근 본 바이럴 타겟 기록
      const target = categoryTargets.find((t) => t.id === targetId)
      if (target) {
        recordRecent({
          id: String(target.id),
          kind: 'viral_target',
          label: target.title?.slice(0, 50) || '타겟',
          path: `/viral?search=${encodeURIComponent(target.title || '')}`,
        })
      }
    }
  }

  // AI 댓글 생성
  const handleGenerateComment = async (targetId: string, style?: string) => {
    setGeneratingTargetId(targetId)
    try {
      const result = await viralApi.generateComment(targetId, style || selectedCommentStyle)
      if (result.comment) {
        setExpandedComments(prev => ({ ...prev, [targetId]: result.comment }))
        const styleName = commentStyles.find(s => s.id === (style || selectedCommentStyle))?.name || '기본'
        toast.success(`AI 댓글이 생성되었습니다 (${styleName} 스타일)`)
      }
    } catch (error: unknown) {
      toast.error(getToastErrorMessage(error, '댓글 생성 실패'))
    } finally {
      setGeneratingTargetId(null)
    }
  }

  // 타겟 액션 처리 (승인/건너뛰기/삭제) - Optimistic Updates
  const handleTargetAction = async (
    targetId: string,
    action: string,
    skipReason?: string,
    skipNote?: string,
  ) => {
    // [F2] skip 액션이면 사유 모달 먼저 띄움 (reason이 이미 전달되면 바로 진행)
    if (action === 'skip' && !skipReason) {
      setSkipReasonFor(targetId)
      return
    }

    const comment = expandedComments[targetId]

    // 낙관적 업데이트: 즉시 UI 반영
    const previousTargets = [...categoryTargets]
    const previousStats = { ...completionStats }
    const previousComments = { ...expandedComments }

    // UI 즉시 업데이트
    if (action === 'approve') {
      setCompletionStats(prev => ({ ...prev, approved: prev.approved + 1 }))
    } else if (action === 'skip') {
      setCompletionStats(prev => ({ ...prev, skipped: prev.skipped + 1 }))
    } else if (action === 'delete') {
      setCompletionStats(prev => ({ ...prev, deleted: prev.deleted + 1 }))
    }

    // [U2] Inbox Zero 루프: 처리한 타겟 바로 다음 타겟으로 자동 이동
    const remaining = categoryTargets.filter(t => t.id !== targetId)
    setCategoryTargets(remaining)

    // 자동 이동 대상 선정 (현재 위치 기준 다음, 없으면 이전)
    const currentIndex = categoryTargets.findIndex(t => t.id === targetId)
    let nextTargetId: string | null = null
    if (currentIndex >= 0) {
      const next = remaining[currentIndex] ?? remaining[currentIndex - 1] ?? remaining[0] ?? null
      nextTargetId = next?.id ?? null
    }
    setExpandedTargetId(nextTargetId)

    setExpandedComments(prev => {
      const newComments = { ...prev }
      delete newComments[targetId]
      return newComments
    })

    // 모든 타겟 완료 시
    if (categoryTargets.length <= 1) {
      setView('completion')
    }

    try {
      // 실제 API 호출 ([F2] skip 사유 학습 포함)
      const result = await viralApi.targetAction(targetId, action, comment, skipReason, skipNote)

      // [Phase 8.0] 승인 시 리드 추적 모달 표시
      if (action === 'approve') {
        // 타겟 정보 찾기
        const target = categoryTargets.find(t => t.id === targetId)
        setLeadTrackingModal({
          isOpen: true,
          targetTitle: target?.title || '콘텐츠',
          leadCreated: result?.lead_created || false
        })
      } else {
        const messages = {
          skip: '⏭️ 건너뜀',
          delete: '🗑️ 삭제됨',
          reopen: '↩️ 복구됨'
        }
        // [U1] Undo 지원 — skip/delete는 6초 내 되돌리기 가능
        if (action === 'skip' || action === 'delete') {
          toast.action(
            'success',
            messages[action as keyof typeof messages] || '완료',
            {
              label: '되돌리기',
              onClick: async () => {
                try {
                  await viralApi.targetAction(targetId, 'reopen')
                  queryClient.invalidateQueries({ queryKey: ['viral-filtered-targets'] })
                  queryClient.invalidateQueries({ queryKey: ['viral-all-targets'] })
                  queryClient.invalidateQueries({ queryKey: ['viral-stats'] })
                  toast.info('↩️ 복구했습니다')
                } catch (err) {
                  toast.error(getToastErrorMessage(err, '복구 실패'))
                }
              },
            },
          )
        } else {
          toast.success(messages[action as keyof typeof messages] || '완료')
        }
      }

      // [BB1] 저널 기록
      if (action === 'approve' || action === 'skip' || action === 'delete' || action === 'reopen') {
        logJournal(action, selectedCategory ?? undefined)
      }
      // [BB5] 피로 감지
      markFatigueAction()

      // [AA2] 데이터 갱신 — 중앙 헬퍼 사용
      if (action === 'approve') {
        invalidateViralAndLeads(queryClient)
      } else {
        invalidateViralAll(queryClient)
      }
    } catch (error: unknown) {
      // [Y5] 오프라인/네트워크 오류면 큐에 저장, 그 외는 롤백
      const isNetworkError = !navigator.onLine || (error as { code?: string })?.code === 'ERR_NETWORK'
      if (isNetworkError) {
        enqueueOffline({
          target_id: targetId,
          action: action as 'approve' | 'skip' | 'delete',
          comment,
          skip_reason: skipReason,
          skip_note: skipNote,
        })
        toast.warning(`📡 오프라인 감지 — 큐에 저장했습니다. 연결 복구 시 자동 전송`)
        // UI는 낙관적 업데이트 유지 (롤백 X)
      } else {
        // 에러 발생 시 롤백
        setCategoryTargets(previousTargets)
        setCompletionStats(previousStats)
        setExpandedComments(previousComments)
        toast.error(getToastErrorMessage(error, '처리 실패'))
      }
    }
  }

  const isScanning = scanningModule !== null || runScanMutation.isPending

  // 필터링된 타겟 (list view용) - 서버 페이지네이션으로 이미 페이지 분량만 로드됨
  const displayTargets: any[] = view === 'list' && Array.isArray(filteredTargets) ? filteredTargets : []
  const totalItems = totalCountData?.total ?? displayTargets.length
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize))
  const safeCurrentPage = Math.min(currentPage, totalPages)
  const allFilteredTargets: any[] = displayTargets

  // 페이지 변경 핸들러
  const handlePageChange = (page: number) => {
    setCurrentPage(page)
    setSelectedTargets(new Set()) // 페이지 변경 시 선택 초기화
  }

  // 페이지 크기 변경 핸들러
  const handlePageSizeChange = (size: number) => {
    setPageSize(size)
    setCurrentPage(1)
    setSelectedTargets(new Set())
  }

  // 체크박스 핸들러
  const handleToggleSelect = (targetId: string) => {
    setSelectedTargets(prev => {
      const newSet = new Set(prev)
      if (newSet.has(targetId)) {
        newSet.delete(targetId)
      } else {
        newSet.add(targetId)
      }
      return newSet
    })
  }

  const handleToggleSelectAll = () => {
    if (selectedTargets.size === displayTargets.length) {
      setSelectedTargets(new Set())
    } else {
      setSelectedTargets(new Set(displayTargets.map((t: ViralTarget) => t.id)))
    }
  }

  // 대량 액션 핸들러 - 확인 모달 표시
  const handleBulkAction = (action: 'approve' | 'skip' | 'delete') => {
    if (selectedTargets.size === 0) return
    setBulkActionConfirm({ action, count: selectedTargets.size })
  }

  // 대량 액션 실행
  const executeBulkAction = async () => {
    if (!bulkActionConfirm) return

    const { action } = bulkActionConfirm
    const actionNames = {
      approve: '승인',
      skip: '건너뛰기',
      delete: '삭제',
    }

    setBulkActionConfirm(null)
    setIsProcessingBulk(true)
    toast.info(`${selectedTargets.size}개 타겟 처리 시작...`)

    try {
      const targetIds = Array.from(selectedTargets)
      let successCount = 0
      let failCount = 0

      // 배치 처리 (5개씩)
      const batchSize = 5
      for (let i = 0; i < targetIds.length; i += batchSize) {
        const batch = targetIds.slice(i, i + batchSize)
        const promises = batch.map(targetId =>
          viralApi.targetAction(targetId, action)
            .then(() => {
              successCount++
              return true
            })
            .catch(error => {
              failCount++
              console.error(`Failed to ${action} target ${targetId}:`, error)
              return false
            })
        )

        await Promise.all(promises)

        // 중간 진행률 표시
        if (i + batchSize < targetIds.length) {
          const progress = Math.round(((i + batchSize) / targetIds.length) * 100)
          toast.info(`진행 중... ${progress}%`)
        }
      }

      if (successCount > 0) {
        toast.success(`✅ ${successCount}개 타겟 ${actionNames[action]} 완료!`)
        queryClient.invalidateQueries({ queryKey: ['viral-filtered-targets'] })
        queryClient.invalidateQueries({ queryKey: ['viral-all-targets'] })
        queryClient.invalidateQueries({ queryKey: ['viral-stats'] })
      }

      if (failCount > 0) {
        toast.error(`⚠️ ${failCount}개 타겟 ${actionNames[action]} 실패`)
      }

      setSelectedTargets(new Set())
    } catch (error) {
      toast.error(getToastErrorMessage(error, '대량 액션 실패'))
    } finally {
      setIsProcessingBulk(false)
    }
  }

  // [X5] 대량 작업 확인 모달 상태
  const [bulkAllConfirm, setBulkAllConfirm] = useState<BulkAction | null>(null)

  // [F3] 필터 매칭 전체 대량 액션 — 모달 표시만
  const handleBulkActionAll = useCallback((action: 'approve' | 'skip' | 'delete') => {
    const total = totalCountData?.total ?? 0
    if (total === 0) {
      toast.warning('매칭되는 타겟이 없습니다')
      return
    }
    setBulkAllConfirm(action)
  }, [totalCountData, toast])

  // [X5] 실제 실행 — 모달 확인 시
  const executeBulkActionAll = useCallback(async () => {
    if (!bulkAllConfirm) return
    const action = bulkAllConfirm
    const actionNames: Record<string, string> = {
      approve: '승인', skip: '스킵', delete: '삭제',
    }
    setIsProcessingBulk(true)
    try {
      const result = await viralApi.bulkActionByFilter(action, {
        status: filters.status,
        comment_status: filters.comment_status,
        category: filters.category,
        date_filter: filters.date_filter,
        platforms: filters.platforms,
        min_scan_count: filters.min_scan_count,
        search: filters.search,
        scan_batch: filters.scan_batch,
        ai_ad_label: filters.ai_ad_label,
        specialty_match: filters.specialty_match,
        post_region: filters.post_region,
        min_confidence: filters.min_confidence,
      })
      toast.success(`✅ ${result.updated.toLocaleString()}건 ${actionNames[action]} 완료`)
      queryClient.invalidateQueries({ queryKey: ['viral-filtered-targets'] })
      queryClient.invalidateQueries({ queryKey: ['viral-filtered-targets-count'] })
      queryClient.invalidateQueries({ queryKey: ['viral-kpi-stats'] })
      queryClient.invalidateQueries({ queryKey: ['viral-todays-queue'] })
      setBulkAllConfirm(null)
    } catch (err: unknown) {
      toast.error(getToastErrorMessage(err, `일괄 ${actionNames[action]} 실패`))
    } finally {
      setIsProcessingBulk(false)
    }
  }, [bulkAllConfirm, filters, toast, queryClient])

  // [U3] 전역 ? 단축키 (모든 view에서 도움말 토글)
  useEffect(() => {
    const handleGlobalHelp = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) return
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        e.preventDefault()
        setShowShortcuts((prev) => !prev)
      }
    }
    window.addEventListener('keydown', handleGlobalHelp)
    return () => window.removeEventListener('keydown', handleGlobalHelp)
  }, [])

  // 키보드 단축키 (work view) — [U3] J/K/E/S/G + 액션
  useEffect(() => {
    if (view !== 'work') return

    const handleKeyPress = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return

      const key = e.key.toLowerCase()

      // J / K : 다음/이전 타겟 이동 (expanded 유무 무관)
      if (key === 'j' || key === 'k') {
        e.preventDefault()
        if (categoryTargets.length === 0) return
        const currentIdx = expandedTargetId
          ? categoryTargets.findIndex((t) => t.id === expandedTargetId)
          : -1
        const nextIdx =
          key === 'j'
            ? Math.min(categoryTargets.length - 1, currentIdx + 1)
            : Math.max(0, currentIdx - 1)
        setExpandedTargetId(categoryTargets[nextIdx]?.id ?? null)
        return
      }

      if (!expandedTargetId) return

      switch (key) {
        case 'a': // Approve (기존 유지)
        case 'e': // Approve (Gmail 관습)
          e.preventDefault()
          handleTargetAction(expandedTargetId, 'approve')
          break
        case 's': // Quick Skip (사유 없이)
          e.preventDefault()
          if (e.shiftKey) {
            // Shift+S → 사유 선택 모달
            handleTargetAction(expandedTargetId, 'skip')
          } else {
            // S → 즉시 스킵
            handleTargetAction(expandedTargetId, 'skip', 'unspecified')
          }
          break
        case 'd': // Delete
          e.preventDefault()
          handleTargetAction(expandedTargetId, 'delete')
          break
        case 'g': // Generate comment
          e.preventDefault()
          handleGenerateComment(expandedTargetId, selectedCommentStyle)
          break
        case ' ':
        case 'escape':
          e.preventDefault()
          setExpandedTargetId(null)
          break
      }
    }

    window.addEventListener('keydown', handleKeyPress)
    return () => window.removeEventListener('keydown', handleKeyPress)
  }, [view, expandedTargetId, categoryTargets, expandedComments, selectedCommentStyle])

  // 키보드 단축키 (list view)
  useEffect(() => {
    if (view !== 'list') return

    const handleKeyPress = (e: KeyboardEvent) => {
      // 입력 필드에서는 단축키 비활성화
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return
      }

      // Ctrl/Cmd 키와 함께 눌러야 함 (선택 관련)
      if (e.ctrlKey || e.metaKey) {
        switch (e.key.toLowerCase()) {
          case 'a':
            e.preventDefault()
            handleToggleSelectAll()
            break
          case 'd':
            e.preventDefault()
            setSelectedTargets(new Set())
            break
        }
        return
      }

      // 선택된 항목이 있을 때만 작동 (단일 키)
      if (selectedTargets.size === 0) return

      switch (e.key.toLowerCase()) {
        case 'a':
          e.preventDefault()
          handleBulkAction('approve')
          break
        case 's':
          e.preventDefault()
          handleBulkAction('skip')
          break
        case 'd':
          e.preventDefault()
          handleBulkAction('delete')
          break
        case 'escape':
          e.preventDefault()
          setSelectedTargets(new Set())
          break
      }
    }

    window.addEventListener('keydown', handleKeyPress)
    return () => window.removeEventListener('keydown', handleKeyPress)
  }, [view, displayTargets.length, selectedTargets.size])

  // [UX 개선] 주요 데이터 에러 시 ErrorState 표시
  const hasHomeError = statsError && homeStatsError
  const hasListError = filteredTargetsError

  // 홈 화면
  if (view === 'home') {
    // 모든 주요 데이터 로드 실패 시 에러 표시
    if (hasHomeError) {
      return (
        <div className="p-6">
          <ErrorState
            error={statsError || homeStatsError}
            onRetry={() => {
              queryClient.invalidateQueries({ queryKey: ['viral-stats'] })
              queryClient.invalidateQueries({ queryKey: ['viral-home-stats'] })
            }}
            showRetry
            title="데이터 로드 실패"
            message="바이럴 타겟 데이터를 불러오는데 실패했습니다. 네트워크 연결을 확인하고 다시 시도해주세요."
          />
        </div>
      )
    }

    // [Y5] 오프라인 큐 배너 — 쌓인 액션이 있으면 표시
    const showOfflineQueue = offlineQueue.length > 0

    // [X7/DD5] Resume 배너 — 8시간 내 중단된 작업이 있으면 복귀 제안.
    // 단, 최근 2분 이내 기록은 "현재 세션" 자기참조이므로 제외.
    const MIN_AGE_FOR_RESUME_MS = 2 * 60_000
    const showResumeBanner =
      !resumeBannerDismissed &&
      resumeInitial &&
      resumeInitial.view === 'work' &&
      resumeInitial.category &&
      Date.now() - resumeInitial.timestamp > MIN_AGE_FOR_RESUME_MS

    return (
      <>
        {showOfflineQueue && (
          <div
            role="status"
            aria-live="polite"
            className={`mb-4 border p-3 flex items-center justify-between gap-2 text-sm flex-wrap ${
              isOnline
                ? 'border-blue-500/40 bg-blue-500/5 text-blue-700 dark:text-blue-300'
                : 'border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-300'
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="animate-pulse">●</span>
              <span>
                {isOnline
                  ? `재전송 중 — 큐에 ${offlineQueue.length}건 대기`
                  : `오프라인 — ${offlineQueue.length}건이 연결 복구 시 자동 전송됩니다`}
              </span>
            </div>
            {/* [EE7] 영구 실패 정리용 수동 비우기 (2건 이상일 때만) */}
            {offlineQueue.length >= 2 && (
              <button
                onClick={() => {
                  if (window.confirm(`대기 중인 ${offlineQueue.length}건을 삭제할까요? 서버에 전송되지 않습니다.`)) {
                    clearOfflineQueue()
                    toast.info('오프라인 큐를 비웠습니다')
                  }
                }}
                className="text-xs underline hover:opacity-70"
              >
                큐 비우기
              </button>
            )}
          </div>
        )}
        {showResumeBanner && resumeInitial && (
          <div className="mb-6 relative bg-card border border-primary/40 p-5 md:p-6 overflow-hidden">
            <span
              aria-hidden
              className="absolute right-4 top-2 text-[6rem] leading-none font-display text-foreground/[0.04] select-none pointer-events-none"
            >
              續
            </span>
            <div className="relative flex items-start justify-between gap-4 flex-wrap">
              <div>
                <div className="caps text-primary mb-2">이어서 작업하기</div>
                <h3 className="font-display text-lg md:text-xl leading-tight mb-1">
                  {resumeInitial.label ?? '지난번 작업'}에서 이어서 하시겠어요?
                </h3>
                <p className="text-xs text-muted-foreground">
                  {Math.max(1, Math.round((Date.now() - resumeInitial.timestamp) / 60000))}분 전에 중단되었습니다.
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    if (resumeInitial.category) handleSelectCategory(resumeInitial.category)
                    setResumeBannerDismissed(true)
                  }}
                  className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                >
                  이어서 하기
                </button>
                <button
                  onClick={() => {
                    clearResume()
                    setResumeBannerDismissed(true)
                  }}
                  className="px-3 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                >
                  아니오
                </button>
              </div>
            </div>
          </div>
        )}
        <HomeView
          stats={stats || undefined}
          homeStats={homeStats}
          qualitySummary={qualitySummary || undefined}
          opsStatus={opsStatus || undefined}
          scanBatches={scanBatches}
          platformStats={platformStats}
          categoryStats={categoryStats}
          scanningModule={scanningModule}
          isScanning={isScanning}
          showScanSettings={showScanSettings}
          scanSettings={scanSettings}
          homeScanBatch={homeScanBatch}
          isVerifying={isVerifying}
          verifyLimit={verifyLimit}
          verifyResults={verifyResults}
          onMissionComplete={handleMissionComplete}
          onMissionStop={handleMissionStop}
          onSelectCategory={handleSelectCategory}
          onBatchVerify={handleBatchVerify}
          onViewList={() => setView('list')}
          onKpiNavigate={handleKpiNavigate}
          onToggleScanSettings={() => setShowScanSettings(!showScanSettings)}
          onScanSettingsChange={setScanSettings}
          onVerifyLimitChange={setVerifyLimit}
          onHomeScanBatchChange={setHomeScanBatch}
          runScanMutation={runScanMutation}
          stopScan={stopScan}
        />
        <ShortcutsOverlay open={showShortcuts} onClose={() => setShowShortcuts(false)} />
        <SkipReasonModal
          open={!!skipReasonFor}
          onCancel={() => setSkipReasonFor(null)}
          onConfirm={(reason, note) => {
            const tid = skipReasonFor
            setSkipReasonFor(null)
            if (tid) handleTargetAction(tid, 'skip', reason, note)
          }}
        />
      </>
    )
  }

  // 작업 화면 (아코디언 방식)
  if (view === 'work') {
    return (
      <>
        <WorkView
          selectedCategory={selectedCategory}
          categoryTargets={categoryTargets}
          templates={templates}
          completionStats={completionStats}
          expandedTargetId={expandedTargetId}
          expandedComments={expandedComments}
          generatingTargetId={generatingTargetId}
          commentStyles={commentStyles}
          selectedCommentStyle={selectedCommentStyle}
          onGoHome={() => setView('home')}
          onToggleExpand={toggleExpand}
          onSetExpandedTargetId={setExpandedTargetId}
          onSetExpandedComments={setExpandedComments}
          onGenerateComment={handleGenerateComment}
          onSetSelectedCommentStyle={setSelectedCommentStyle}
          onTargetAction={handleTargetAction}
          onVerifyTarget={handleVerifyTarget}
          verifyTargetMutation={verifyTargetMutation}
          toast={toast}
        />
        <ShortcutsOverlay open={showShortcuts} onClose={() => setShowShortcuts(false)} />
        <SkipReasonModal
          open={!!skipReasonFor}
          onCancel={() => setSkipReasonFor(null)}
          onConfirm={(reason, note) => {
            const tid = skipReasonFor
            setSkipReasonFor(null)
            if (tid) handleTargetAction(tid, 'skip', reason, note)
          }}
        />
      </>
    )
  }

  // 전체 목록 화면
  if (view === 'list') {
    // 목록 데이터 로드 실패 시 에러 표시
    if (hasListError) {
      return (
        <div className="p-6">
          <div className="mb-4">
            <button
              onClick={() => setView('home')}
              className="text-sm text-muted-foreground hover:text-foreground flex items-center gap-1"
            >
              ← 홈으로 돌아가기
            </button>
          </div>
          <ErrorState
            error={filteredTargetsError}
            onRetry={() => {
              queryClient.invalidateQueries({ queryKey: ['viral-targets-filtered'] })
            }}
            showRetry
            title="타겟 목록 로드 실패"
            message="바이럴 타겟 목록을 불러오는데 실패했습니다."
          />
        </div>
      )
    }

    return (
      <>
        <ListView
          filters={filters}
          scanBatches={scanBatches}
          displayTargets={displayTargets}
          allTargets={allFilteredTargets}
          selectedTargets={selectedTargets}
          isLoadingFiltered={isLoadingFiltered}
          isRefreshing={filteredLoadingState.isRefreshing}
          currentPage={safeCurrentPage}
          totalPages={totalPages}
          totalItems={totalItems}
          pageSize={pageSize}
          isVerifying={isVerifying}
          verifyProgress={verifyProgress}
          verifyLimit={verifyLimit}
          verifyResults={verifyResults}
          isProcessingBulk={isProcessingBulk}
          isGeneratingComments={isGeneratingComments}
          generationProgress={generationProgress}
          bulkActionConfirm={bulkActionConfirm}
          leadTrackingModal={leadTrackingModal}
          onGoHome={() => setView('home')}
          onFilterChange={handleFilterChange}
          onFilterReset={handleFilterReset}
          onVerifyLimitChange={setVerifyLimit}
          onBatchVerify={handleBatchVerify}
          onToggleSelect={handleToggleSelect}
          onToggleSelectAll={handleToggleSelectAll}
          onBulkAction={handleBulkAction}
          onBulkActionAll={handleBulkActionAll}
          onBulkGenerateComments={handleBulkGenerateComments}
          onClearSelection={() => setSelectedTargets(new Set())}
          onSetExpandedTargetId={setExpandedTargetId}
          onPageChange={handlePageChange}
          onPageSizeChange={handlePageSizeChange}
          onSetBulkActionConfirm={setBulkActionConfirm}
          onExecuteBulkAction={executeBulkAction}
          onSetLeadTrackingModal={setLeadTrackingModal}
          toast={toast}
        />
        <ShortcutsOverlay open={showShortcuts} onClose={() => setShowShortcuts(false)} />
        <SkipReasonModal
          open={!!skipReasonFor}
          onCancel={() => setSkipReasonFor(null)}
          onConfirm={(reason, note) => {
            const tid = skipReasonFor
            setSkipReasonFor(null)
            if (tid) handleTargetAction(tid, 'skip', reason, note)
          }}
        />
        {/* [X5] 대량 작업 미리보기 */}
        <BulkConfirmModal
          open={!!bulkAllConfirm}
          action={bulkAllConfirm ?? 'approve'}
          totalCount={totalCountData?.total ?? 0}
          filterSummary={(() => {
            const s: Array<{ label: string; value: string }> = []
            if (filters.status) s.push({ label: '상태', value: filters.status })
            if (filters.category) s.push({ label: '카테고리', value: filters.category })
            if (filters.comment_status) s.push({ label: '댓글 상태', value: filters.comment_status })
            if (filters.date_filter) s.push({ label: '기간', value: filters.date_filter })
            if (filters.platforms?.length)
              s.push({ label: '플랫폼', value: filters.platforms.join(', ') })
            if (filters.search) s.push({ label: '검색어', value: filters.search })
            if (filters.scan_batch) s.push({ label: '스캔 배치', value: filters.scan_batch })
            if (s.length === 0) s.push({ label: '필터', value: '전체 (필터 없음)' })
            return s
          })()}
          onConfirm={executeBulkActionAll}
          onCancel={() => setBulkAllConfirm(null)}
          isProcessing={isProcessingBulk}
        />
      </>
    )
  }

  // 완료 화면
  if (view === 'completion') {
    return (
      <>
        <CompletionView
          selectedCategory={selectedCategory}
          completionStats={completionStats}
          onGoHome={() => {
            setView('home')
            setSelectedCategory(null)
            setExpandedTargetId(null)
            setExpandedComments({})
            setCategoryTargets([])
            setCompletionStats({ approved: 0, skipped: 0, deleted: 0 })
            queryClient.invalidateQueries({ queryKey: ['viral-all-targets'] })
          }}
        />
        <ShortcutsOverlay open={showShortcuts} onClose={() => setShowShortcuts(false)} />
        <SkipReasonModal
          open={!!skipReasonFor}
          onCancel={() => setSkipReasonFor(null)}
          onConfirm={(reason, note) => {
            const tid = skipReasonFor
            setSkipReasonFor(null)
            if (tid) handleTargetAction(tid, 'skip', reason, note)
          }}
        />
      </>
    )
  }

  return null
}

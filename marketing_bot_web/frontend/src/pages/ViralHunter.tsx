import { useState, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { viralApi, hudApi } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import ErrorState from '@/components/ui/ErrorState'
import type { FilterState, ScanBatch } from '@/components/viral/FilterBar'
import { HomeView, WorkView, ListView, CompletionView } from '@/components/viral/views'
import { ViralTargetData as ViralTarget } from '@/types/viral'
import { useLoadingState } from '@/hooks/useLoadingState'

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
  const [showScanSettings, setShowScanSettings] = useState(false)
  const [scanSettings, setScanSettings] = useState({
    platforms: ['cafe', 'blog', 'kin', 'place', 'karrot', 'youtube', 'instagram', 'tiktok'] as string[],
    maxResults: 500,
  })

  // 필터 상태
  const [filters, setFilters] = useState<FilterState>({
    status: 'pending',
    sort: 'priority',
  })

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

  // [Phase 6.0] 일괄 검증 상태
  const [isVerifying, setIsVerifying] = useState(false)
  const [verifyLimit, setVerifyLimit] = useState(50)  // 기본 50개
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

  // 실행 중인 모듈 조회 (페이지 로드 시 상태 복원)
  const { data: runningModules, isError: runningModulesError } = useQuery({
    queryKey: ['running-modules'],
    queryFn: () => hudApi.getRunningModules().catch(() => ({ running: [] })),
    refetchInterval: 30000, // 30초마다 확인 (서버 부하 감소)
    staleTime: 5000, // 5초간 캐시
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

  // 필터링된 타겟 (list view용)
  // comment_status가 선택되면 해당 값을 status로 사용, 아니면 기본 status 사용
  const effectiveStatus = filters.comment_status || filters.status || 'pending'
  const {
    data: filteredTargets,
    isLoading: isLoadingFiltered,
    isFetching: isFetchingFiltered,
    isError: filteredTargetsError
  } = useQuery({
    queryKey: ['viral-filtered-targets', filters],
    queryFn: () => viralApi.getTargets(
      effectiveStatus,
      undefined,
      1000,
      {
        date_filter: filters.date_filter,
        platforms: filters.platforms,
        category: filters.category,
        min_scan_count: filters.min_scan_count,
        search: filters.search,
        sort: filters.sort,
        scan_batch: filters.scan_batch,
      }
    ).catch(() => ({ targets: [], total: 0 })),
    enabled: view === 'list',
    staleTime: 60000, // [Phase 7] 30초 → 60초
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
    }),
    onSuccess: (data) => {
      toast.success(`바이럴 스캔 시작! (${data.platforms?.length || 0}개 플랫폼, 최대 ${data.max_results === 0 ? '무제한' : data.max_results + '개'})`)
      setScanningModule('viral_hunter')
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`스캔 실패: ${error.response?.data?.detail || error.message}`)
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
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(`검증 실패: ${error.response?.data?.detail || error.message}`)
    },
  })

  const handleVerifyTarget = (targetId: string) => {
    verifyTargetMutation.mutate(targetId)
  }

  // [Phase 6.0] 일괄 검증 핸들러
  const handleBatchVerify = useCallback(async (category?: string, limit = 20) => {
    setIsVerifying(true)
    setVerifyResults(null)
    try {
      const result = await viralApi.verifyBatch(category, limit)
      setVerifyResults({
        total: result.total,
        commentable: result.commentable,
        not_commentable: result.not_commentable
      })
      toast.success(`검증 완료: ${result.commentable}/${result.total} 댓글 가능`)
      queryClient.invalidateQueries({ queryKey: ['viral-all-targets'] })
      queryClient.invalidateQueries({ queryKey: ['viral-filtered-targets'] })
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : '알 수 없는 오류'
      toast.error(`일괄 검증 실패: ${errorMessage}`)
    } finally {
      setIsVerifying(false)
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

  // 스캔 중지 핸들러
  const stopScan = useCallback(async () => {
    try {
      await hudApi.stopMission('viral_hunter')
      toast.info('스캔 중지 요청됨')
      setScanningModule(null)
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : '알 수 없는 오류'
      toast.error(`스캔 중지 실패: ${errorMessage}`)
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

        // 각 배치에서 개별 요청 (병렬)
        const promises = batch.map(async (targetId) => {
          try {
            await viralApi.generateComment(targetId)
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
      const errorMessage = error instanceof Error ? error.message : '알 수 없는 오류'
      toast.error(`AI 댓글 생성 실패: ${errorMessage}`)
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
      const errorMessage = error instanceof Error ? error.message : '알 수 없는 오류'
      toast.error(`댓글 생성 실패: ${errorMessage}`)
    } finally {
      setGeneratingTargetId(null)
    }
  }

  // 타겟 액션 처리 (승인/건너뛰기/삭제) - Optimistic Updates
  const handleTargetAction = async (targetId: string, action: string) => {
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

    setCategoryTargets(prev => prev.filter(t => t.id !== targetId))
    setExpandedTargetId(null)
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
      // 실제 API 호출
      const result = await viralApi.targetAction(targetId, action, comment)

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
          delete: '🗑️ 삭제됨'
        }
        toast.success(messages[action as keyof typeof messages] || '완료')
      }

      // 데이터 갱신
      queryClient.invalidateQueries({ queryKey: ['viral-filtered-targets'] })
      queryClient.invalidateQueries({ queryKey: ['viral-all-targets'] })
      queryClient.invalidateQueries({ queryKey: ['viral-stats'] })
      // 리드 데이터도 갱신 (승인 시)
      if (action === 'approve') {
        queryClient.invalidateQueries({ queryKey: ['leads-stats'] })
        queryClient.invalidateQueries({ queryKey: ['leads-pending-alerts'] })
      }
    } catch (error: unknown) {
      // 에러 발생 시 롤백
      setCategoryTargets(previousTargets)
      setCompletionStats(previousStats)
      setExpandedComments(previousComments)

      const errorMessage = error instanceof Error ? error.message : '알 수 없는 오류'
      toast.error(`❌ 에러: ${errorMessage}`)
    }
  }

  const isScanning = scanningModule !== null || runScanMutation.isPending

  // 필터링된 타겟 (list view용)
  const allFilteredTargets = view === 'list' ? (filteredTargets || []) : []

  // 페이지네이션 계산
  const totalItems = allFilteredTargets.length
  const totalPages = Math.ceil(totalItems / pageSize) || 1
  const safeCurrentPage = Math.min(currentPage, totalPages)

  // 현재 페이지에 표시할 타겟
  const displayTargets = allFilteredTargets.slice(
    (safeCurrentPage - 1) * pageSize,
    safeCurrentPage * pageSize
  )

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
      toast.error(`대량 액션 실패: ${error}`)
    } finally {
      setIsProcessingBulk(false)
    }
  }

  // 키보드 단축키 (work view)
  useEffect(() => {
    if (view !== 'work') return

    const handleKeyPress = (e: KeyboardEvent) => {
      // 입력 필드에서는 단축키 비활성화
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return
      }

      // 펼쳐진 타겟이 있을 때만
      if (!expandedTargetId) return

      switch (e.key.toLowerCase()) {
        case 'a':
          e.preventDefault()
          handleTargetAction(expandedTargetId, 'approve')
          break
        case 's':
          e.preventDefault()
          handleTargetAction(expandedTargetId, 'skip')
          break
        case 'd':
          e.preventDefault()
          handleTargetAction(expandedTargetId, 'delete')
          break
        case ' ':
        case 'space':
          e.preventDefault()
          setExpandedTargetId(null)
          break
        case 'escape':
          e.preventDefault()
          setExpandedTargetId(null)
          break
      }
    }

    window.addEventListener('keydown', handleKeyPress)
    return () => window.removeEventListener('keydown', handleKeyPress)
  }, [view, expandedTargetId, expandedComments])

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

    return (
      <HomeView
        stats={stats || undefined}
        homeStats={homeStats}
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
        onToggleScanSettings={() => setShowScanSettings(!showScanSettings)}
        onScanSettingsChange={setScanSettings}
        onVerifyLimitChange={setVerifyLimit}
        onHomeScanBatchChange={setHomeScanBatch}
        runScanMutation={runScanMutation}
        stopScan={stopScan}
      />
    )
  }

  // 작업 화면 (아코디언 방식)
  if (view === 'work') {
    return (
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
    )
  }

  // 완료 화면
  if (view === 'completion') {
    return (
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
    )
  }

  return null
}

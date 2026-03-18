import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { agentApi } from '@/services/api'
import PageTransition from '@/components/PageTransition'
import UsageStats from '@/components/agent/UsageStats'
import ActionLog from '@/components/agent/ActionLog'
import AutoApprovalRules from '@/components/agent/AutoApprovalRules'
import ErrorState from '@/components/ui/ErrorState'
import { SkeletonStatsGrid, SkeletonTable } from '@/components/ui/Skeleton'
import TabNavigation from '@/components/ui/TabNavigation'
import { ConfirmModal } from '@/components/ui/Modal'
import { useUrlState } from '@/hooks/useUrlState'
import { useToast } from '@/components/ui/Toast'
import { TrendingUp, Clock, Zap, CheckCheck, XCircle, RefreshCw } from 'lucide-react'
import Button from '@/components/ui/Button'

export default function AIAgent() {
  const queryClient = useQueryClient()
  const toast = useToast()
  // [Phase 5.0] URL 상태 관리
  const [activeTab, setActiveTab] = useUrlState<string>('tab', { defaultValue: 'overview' })
  const [statusFilter, setStatusFilter] = useUrlState<string>('status', { defaultValue: '' })
  const [logOffset, setLogOffset] = useState(0)
  // [Phase 6.1] 일괄 처리 확인 모달
  const [batchModal, setBatchModal] = useState<{
    isOpen: boolean
    action: 'approve' | 'reject' | null
  }>({ isOpen: false, action: null })

  // 사용량 통계
  const {
    data: usageStats,
    isLoading: usageLoading,
    isError: usageError,
    refetch: refetchUsage,
  } = useQuery({
    queryKey: ['agent-usage'],
    queryFn: agentApi.getUsageStats,
    staleTime: 60000, // [Phase 7] 30초 → 60초
    refetchInterval: 60000, // 60초마다 갱신
  })

  // 요약 정보
  const { data: summary } = useQuery({
    queryKey: ['agent-summary'],
    queryFn: () => agentApi.getSummary().catch(() => null),
    staleTime: 60000, // [Phase 7] 30초 → 60초
    refetchInterval: 60000, // [Phase 7] 30초 → 60초
    retry: 1,
  })

  // 액션 로그
  const {
    data: actionsData,
    isLoading: actionsLoading,
    isError: actionsError,
    refetch: refetchActions,
  } = useQuery({
    queryKey: ['agent-actions', logOffset, statusFilter],
    queryFn: () => agentApi.getActionsLog({
      limit: 50,
      offset: logOffset,
      status: statusFilter || undefined,
    }),
    staleTime: 60000, // [Phase 7] 30초 → 60초
  })

  // [Phase 4.0] 액션별 승인/거절 비율
  const { data: approvalRates } = useQuery({
    queryKey: ['agent-approval-rates'],
    queryFn: () => agentApi.getApprovalRates().catch(() => []),
    staleTime: 60000, // 1분간 캐시
    refetchInterval: 60000, // 1분마다 갱신
    retry: 1,
  })

  // [Phase 6.1] 일괄 승인 mutation
  const batchApproveMutation = useMutation({
    mutationFn: () => agentApi.batchApprove(),
    onSuccess: (data) => {
      toast.success(data.message || `${data.approved_count}개 액션이 승인되었습니다`)
      queryClient.invalidateQueries({ queryKey: ['agent-actions'] })
      queryClient.invalidateQueries({ queryKey: ['agent-summary'] })
      setBatchModal({ isOpen: false, action: null })
    },
    onError: () => {
      toast.error('일괄 승인 실패')
    },
  })

  // [Phase 6.1] 일괄 거절 mutation
  const batchRejectMutation = useMutation({
    mutationFn: () => agentApi.batchReject(undefined, '일괄 거절됨'),
    onSuccess: (data) => {
      toast.success(data.message || `${data.rejected_count}개 액션이 거절되었습니다`)
      queryClient.invalidateQueries({ queryKey: ['agent-actions'] })
      queryClient.invalidateQueries({ queryKey: ['agent-summary'] })
      setBatchModal({ isOpen: false, action: null })
    },
    onError: () => {
      toast.error('일괄 거절 실패')
    },
  })

  // [Phase 6.1] 일괄 처리 실행
  const handleBatchAction = () => {
    if (batchModal.action === 'approve') {
      batchApproveMutation.mutate()
    } else if (batchModal.action === 'reject') {
      batchRejectMutation.mutate()
    }
  }

  if (usageLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold mb-2">🤖 AI Agent</h1>
          <p className="text-muted-foreground">AI 에이전트 사용량 모니터링 및 액션 관리</p>
        </div>
        <SkeletonStatsGrid cards={4} />
        <SkeletonTable rows={5} columns={5} />
      </div>
    )
  }

  if (usageError) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold mb-2">🤖 AI Agent</h1>
          <p className="text-muted-foreground">AI 에이전트 사용량 모니터링 및 액션 관리</p>
        </div>
        <ErrorState
          title="데이터 로드 실패"
          message="AI Agent 정보를 불러오는데 실패했습니다."
          onRetry={() => refetchUsage()}
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
          <h1 className="text-3xl font-bold mb-2">🤖 AI Agent</h1>
          <p className="text-muted-foreground">
            AI 에이전트 사용량 모니터링 및 액션 관리
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => {
              refetchUsage()
              refetchActions()
            }}
            icon={<RefreshCw className="w-4 h-4" />}
          >
            새로고침
          </Button>
        </div>
      </div>

      {/* 사용량 통계 */}
      {usageStats && <UsageStats stats={usageStats} />}

      {/* [Phase 6.0] 자동 승인 규칙 */}
      <AutoApprovalRules />

      {/* 탭 네비게이션 */}
      <TabNavigation
        tabs={[
          { id: 'overview', label: '📊 개요' },
          { id: 'pending', label: `⏳ 대기 중 (${summary?.actions_summary?.pending || 0})` },
          { id: 'history', label: '📜 전체 기록' },
          { id: 'efficiency', label: '📈 효율성 분석' },
        ]}
        activeTab={activeTab}
        onTabChange={(tab) => {
          setActiveTab(tab)
          setLogOffset(0)
          if (tab === 'pending') {
            setStatusFilter('pending')
          } else if (tab === 'history') {
            setStatusFilter('')
          }
        }}
        ariaLabel="AI Agent 탭"
      />

      {/* 탭 컨텐츠 */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* [Phase 5.0] AI 효율성 분석 */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-card border border-border rounded-lg p-4">
              <div className="flex items-center gap-3 mb-3">
                <div className="p-2 bg-green-100 rounded-lg">
                  <TrendingUp className="w-5 h-5 text-green-600" />
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">승인율</div>
                  <div className="text-2xl font-bold">
                    {summary?.actions_summary ?
                      (() => {
                        const total = (summary.actions_summary.approved || 0) +
                                     (summary.actions_summary.rejected || 0) +
                                     (summary.actions_summary.completed || 0)
                        return total > 0
                          ? Math.round(((summary.actions_summary.approved || 0) + (summary.actions_summary.completed || 0)) / total * 100)
                          : 0
                      })()
                    : 0}%
                  </div>
                </div>
              </div>
              <div className="text-xs text-muted-foreground">
                승인/완료된 액션 비율
              </div>
            </div>

            <div className="bg-card border border-border rounded-lg p-4">
              <div className="flex items-center gap-3 mb-3">
                <div className="p-2 bg-blue-100 rounded-lg">
                  <Clock className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">일일 잔여량</div>
                  <div className="text-2xl font-bold">
                    {usageStats ? Math.max(0, (usageStats.daily_limit || 100) - (usageStats.daily_calls || 0)) : 0}
                  </div>
                </div>
              </div>
              <div className="text-xs text-muted-foreground">
                오늘 사용 가능한 호출 수
              </div>
            </div>

            <div className="bg-card border border-border rounded-lg p-4">
              <div className="flex items-center gap-3 mb-3">
                <div className="p-2 bg-purple-100 rounded-lg">
                  <Zap className="w-5 h-5 text-purple-600" />
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">예상 소진 시간</div>
                  <div className="text-2xl font-bold">
                    {usageStats?.daily_calls && usageStats.daily_calls > 0 ? (
                      (() => {
                        const remaining = Math.max(0, (usageStats.daily_limit || 100) - usageStats.daily_calls)
                        const hoursLeft = Math.floor(remaining / Math.max(1, usageStats.daily_calls / 24))
                        return hoursLeft > 24 ? '충분' : `${hoursLeft}h`
                      })()
                    ) : '충분'}
                  </div>
                </div>
              </div>
              <div className="text-xs text-muted-foreground">
                현재 사용 속도 기준 예측
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 액션 요약 */}
          <div className="bg-card border border-border rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-4">📊 최근 7일 액션 요약</h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-yellow-50 rounded-lg p-4 text-center">
                <div className="text-3xl font-bold text-yellow-600">
                  {summary?.actions_summary?.pending || 0}
                </div>
                <div className="text-sm text-yellow-700 mt-1">대기 중</div>
              </div>
              <div className="bg-blue-50 rounded-lg p-4 text-center">
                <div className="text-3xl font-bold text-blue-600">
                  {summary?.actions_summary?.approved || 0}
                </div>
                <div className="text-sm text-blue-700 mt-1">승인됨</div>
              </div>
              <div className="bg-green-50 rounded-lg p-4 text-center">
                <div className="text-3xl font-bold text-green-600">
                  {summary?.actions_summary?.completed || 0}
                </div>
                <div className="text-sm text-green-700 mt-1">완료</div>
              </div>
              <div className="bg-red-50 rounded-lg p-4 text-center">
                <div className="text-3xl font-bold text-red-600">
                  {summary?.actions_summary?.rejected || 0}
                </div>
                <div className="text-sm text-red-700 mt-1">거절됨</div>
              </div>
            </div>
          </div>

          {/* 최근 액션 */}
          <div className="bg-card border border-border rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-4">🕐 최근 액션</h3>
            {summary?.recent_actions && summary.recent_actions.length > 0 ? (
              <div className="space-y-3">
                {summary.recent_actions.map((action: any) => (
                  <div
                    key={action.id}
                    className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg"
                  >
                    <span className="text-xl">
                      {action.action_type === 'comment' && '💬'}
                      {action.action_type === 'analysis' && '📊'}
                      {action.action_type === 'content' && '✍️'}
                      {action.action_type === 'keyword' && '🔍'}
                      {!['comment', 'analysis', 'content', 'keyword'].includes(action.action_type) && '🤖'}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">
                        {action.action_type}
                        {action.target_type && (
                          <span className="text-muted-foreground ml-1">
                            ({action.target_type})
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {new Date(action.created_at).toLocaleString('ko-KR', {
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </div>
                    </div>
                    <div
                      className={`px-2 py-0.5 rounded-full text-xs ${
                        action.status === 'pending'
                          ? 'bg-yellow-100 text-yellow-700'
                          : action.status === 'approved'
                          ? 'bg-blue-100 text-blue-700'
                          : action.status === 'completed'
                          ? 'bg-green-100 text-green-700'
                          : 'bg-red-100 text-red-700'
                      }`}
                    >
                      {action.status === 'pending' && '대기'}
                      {action.status === 'approved' && '승인'}
                      {action.status === 'completed' && '완료'}
                      {action.status === 'rejected' && '거절'}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <div className="text-4xl mb-2">📭</div>
                <p>최근 액션이 없습니다</p>
              </div>
            )}
          </div>
          </div>
        </div>
      )}

      {/* [Phase 6.1] 일괄 처리 확인 모달 */}
      <ConfirmModal
        isOpen={batchModal.isOpen}
        onClose={() => setBatchModal({ isOpen: false, action: null })}
        onConfirm={handleBatchAction}
        title={batchModal.action === 'approve' ? '일괄 승인' : '일괄 거절'}
        message={`대기 중인 모든 액션(${summary?.actions_summary?.pending || 0}개)을 ${batchModal.action === 'approve' ? '승인' : '거절'}하시겠습니까?`}
        confirmText={batchModal.action === 'approve' ? '모두 승인' : '모두 거절'}
        cancelText="취소"
        variant={batchModal.action === 'reject' ? 'danger' : 'default'}
        loading={batchApproveMutation.isPending || batchRejectMutation.isPending}
      />

      {(activeTab === 'pending' || activeTab === 'history') && (
        <div className="space-y-4">
          {/* [Phase 6.1] 대기 중 탭 - 일괄 처리 버튼 */}
          {activeTab === 'pending' && (summary?.actions_summary?.pending || 0) > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
              <div className="flex items-center gap-2">
                <span className="text-yellow-600 font-medium">
                  {summary?.actions_summary?.pending || 0}개의 액션이 승인 대기 중입니다
                </span>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="success"
                  onClick={() => setBatchModal({ isOpen: true, action: 'approve' })}
                  loading={batchApproveMutation.isPending}
                  icon={<CheckCheck className="w-4 h-4" />}
                >
                  모두 승인
                </Button>
                <Button
                  variant="danger"
                  onClick={() => setBatchModal({ isOpen: true, action: 'reject' })}
                  loading={batchRejectMutation.isPending}
                  icon={<XCircle className="w-4 h-4" />}
                >
                  모두 거절
                </Button>
              </div>
            </div>
          )}

          {/* 필터 */}
          {activeTab === 'history' && (
            <div className="flex gap-2">
              <select
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value)
                  setLogOffset(0)
                }}
                className="px-3 py-2 bg-card border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">전체 상태</option>
                <option value="pending">대기 중</option>
                <option value="approved">승인됨</option>
                <option value="completed">완료</option>
                <option value="rejected">거절됨</option>
              </select>
            </div>
          )}

          {/* 액션 로그 */}
          {actionsLoading ? (
            <SkeletonTable rows={5} columns={5} />
          ) : actionsError ? (
            <ErrorState
              title="액션 로그 로드 실패"
              message="액션 로그를 불러오는데 실패했습니다."
              onRetry={() => refetchActions()}
            />
          ) : (
            <ActionLog
              actions={actionsData?.actions || []}
              total={actionsData?.total || 0}
              pendingCount={actionsData?.pending_count || 0}
              onPageChange={setLogOffset}
              currentOffset={logOffset}
              limit={50}
            />
          )}
        </div>
      )}

      {/* [Phase 5.0] 효율성 분석 탭 */}
      {activeTab === 'efficiency' && (
        <div className="space-y-6">
          {/* 액션 유형별 통계 */}
          <div className="bg-card border border-border rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-4">📊 액션 유형별 성과</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { type: 'comment', label: '댓글 생성', icon: '💬', color: 'blue' },
                { type: 'analysis', label: '콘텐츠 분석', icon: '📊', color: 'green' },
                { type: 'content', label: '콘텐츠 작성', icon: '✍️', color: 'purple' },
                { type: 'keyword', label: '키워드 분석', icon: '🔍', color: 'orange' },
              ].map((item) => {
                const typeActions = summary?.recent_actions?.filter(
                  (a: any) => a.action_type === item.type
                ) || []
                const completedCount = typeActions.filter(
                  (a: any) => a.status === 'completed'
                ).length

                return (
                  <div key={item.type} className="bg-muted/50 rounded-lg p-4 text-center">
                    <div className="text-3xl mb-2">{item.icon}</div>
                    <div className="text-sm font-medium mb-1">{item.label}</div>
                    <div className={`text-2xl font-bold text-${item.color}-500`}>
                      {typeActions.length}
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                      {completedCount}건 완료
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* [Phase 4.0] 액션별 승인/거절 비율 분석 */}
          {approvalRates && approvalRates.by_action_type && Object.keys(approvalRates.by_action_type).length > 0 && (
            <div className="bg-card border border-border rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4">📈 액션별 승인/거절 비율</h3>

              {/* 모바일: 카드형 레이아웃 */}
              <div className="md:hidden space-y-3">
                {Object.entries(approvalRates.by_action_type)
                  .sort(([, a]: [string, any], [, b]: [string, any]) => b.total - a.total)
                  .map(([actionType, data]: [string, any]) => {
                    const actionLabels: Record<string, { label: string; icon: string }> = {
                      comment: { label: '댓글 생성', icon: '💬' },
                      analysis: { label: '콘텐츠 분석', icon: '📊' },
                      content: { label: '콘텐츠 작성', icon: '✍️' },
                      keyword: { label: '키워드 분석', icon: '🔍' },
                      viral: { label: '바이럴 처리', icon: '🎯' },
                      lead: { label: '리드 처리', icon: '👥' },
                    }
                    const info = actionLabels[actionType] || { label: actionType, icon: '🤖' }

                    return (
                      <div key={actionType} className="bg-muted/50 rounded-lg p-4">
                        <div className="flex justify-between items-center mb-3">
                          <div className="flex items-center gap-2">
                            <span className="text-xl">{info.icon}</span>
                            <span className="font-medium">{info.label}</span>
                          </div>
                          <span className={`text-lg font-bold ${
                            data.approval_rate >= 70 ? 'text-green-500' :
                            data.approval_rate >= 40 ? 'text-yellow-500' :
                            'text-red-500'
                          }`}>
                            {data.approval_rate}%
                          </span>
                        </div>
                        <div className="h-2 bg-muted rounded-full overflow-hidden mb-3">
                          <div
                            className={`h-full transition-all ${
                              data.approval_rate >= 70 ? 'bg-green-500' :
                              data.approval_rate >= 40 ? 'bg-yellow-500' :
                              'bg-red-500'
                            }`}
                            style={{ width: `${data.approval_rate}%` }}
                          />
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-center">
                          <div>
                            <div className="text-muted-foreground">전체</div>
                            <div className="font-medium">{data.total}</div>
                          </div>
                          <div>
                            <div className="text-muted-foreground">승인</div>
                            <div className="font-medium text-green-600">{data.approved}</div>
                          </div>
                          <div>
                            <div className="text-muted-foreground">거절</div>
                            <div className="font-medium text-red-500">{data.rejected}</div>
                          </div>
                          <div>
                            <div className="text-muted-foreground">대기</div>
                            <div className="font-medium text-yellow-500">{data.pending}</div>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                {/* 모바일 합계 */}
                <div className="bg-primary/10 border border-primary/20 rounded-lg p-4">
                  <div className="flex justify-between items-center mb-2">
                    <span className="font-semibold">전체 합계</span>
                    <span className={`text-lg font-bold ${
                      approvalRates.overall.approval_rate >= 70 ? 'text-green-500' :
                      approvalRates.overall.approval_rate >= 40 ? 'text-yellow-500' :
                      'text-red-500'
                    }`}>
                      {approvalRates.overall.approval_rate}%
                    </span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-center">
                    <div>
                      <div className="text-muted-foreground">전체</div>
                      <div className="font-medium">{approvalRates.overall.total}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">승인</div>
                      <div className="font-medium text-green-600">{approvalRates.overall.approved}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">거절</div>
                      <div className="font-medium text-red-500">{approvalRates.overall.rejected}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">대기</div>
                      <div className="font-medium text-yellow-500">{approvalRates.overall.pending}</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* 데스크톱: 테이블 레이아웃 */}
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="px-4 py-3 text-left text-sm font-semibold">액션 유형</th>
                      <th className="px-4 py-3 text-center text-sm font-semibold">전체</th>
                      <th className="px-4 py-3 text-center text-sm font-semibold">승인</th>
                      <th className="px-4 py-3 text-center text-sm font-semibold">거절</th>
                      <th className="px-4 py-3 text-center text-sm font-semibold">대기</th>
                      <th className="px-4 py-3 text-center text-sm font-semibold">승인율</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(approvalRates.by_action_type)
                      .sort(([, a]: [string, any], [, b]: [string, any]) => b.total - a.total)
                      .map(([actionType, data]: [string, any]) => {
                        const actionLabels: Record<string, { label: string; icon: string }> = {
                          comment: { label: '댓글 생성', icon: '💬' },
                          analysis: { label: '콘텐츠 분석', icon: '📊' },
                          content: { label: '콘텐츠 작성', icon: '✍️' },
                          keyword: { label: '키워드 분석', icon: '🔍' },
                          viral: { label: '바이럴 처리', icon: '🎯' },
                          lead: { label: '리드 처리', icon: '👥' },
                        }
                        const info = actionLabels[actionType] || { label: actionType, icon: '🤖' }

                        return (
                          <tr key={actionType} className="border-b border-border hover:bg-muted/50">
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-2">
                                <span>{info.icon}</span>
                                <span className="font-medium">{info.label}</span>
                              </div>
                            </td>
                            <td className="px-4 py-3 text-center font-medium">{data.total}</td>
                            <td className="px-4 py-3 text-center">
                              <span className="text-green-600 font-medium">{data.approved}</span>
                            </td>
                            <td className="px-4 py-3 text-center">
                              <span className="text-red-500 font-medium">{data.rejected}</span>
                            </td>
                            <td className="px-4 py-3 text-center">
                              <span className="text-yellow-500 font-medium">{data.pending}</span>
                            </td>
                            <td className="px-4 py-3 text-center">
                              <div className="flex items-center justify-center gap-2">
                                <div className="w-16 h-2 bg-muted rounded-full overflow-hidden">
                                  <div
                                    className={`h-full transition-all ${
                                      data.approval_rate >= 70 ? 'bg-green-500' :
                                      data.approval_rate >= 40 ? 'bg-yellow-500' :
                                      'bg-red-500'
                                    }`}
                                    style={{ width: `${data.approval_rate}%` }}
                                  />
                                </div>
                                <span className={`text-sm font-bold ${
                                  data.approval_rate >= 70 ? 'text-green-500' :
                                  data.approval_rate >= 40 ? 'text-yellow-500' :
                                  'text-red-500'
                                }`}>
                                  {data.approval_rate}%
                                </span>
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    {/* 전체 합계 */}
                    <tr className="bg-muted/50 font-semibold">
                      <td className="px-4 py-3">전체</td>
                      <td className="px-4 py-3 text-center">{approvalRates.overall.total}</td>
                      <td className="px-4 py-3 text-center text-green-600">{approvalRates.overall.approved}</td>
                      <td className="px-4 py-3 text-center text-red-500">{approvalRates.overall.rejected}</td>
                      <td className="px-4 py-3 text-center text-yellow-500">{approvalRates.overall.pending}</td>
                      <td className="px-4 py-3 text-center">
                        <span className={`font-bold ${
                          approvalRates.overall.approval_rate >= 70 ? 'text-green-500' :
                          approvalRates.overall.approval_rate >= 40 ? 'text-yellow-500' :
                          'text-red-500'
                        }`}>
                          {approvalRates.overall.approval_rate}%
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div className="mt-4 text-xs text-muted-foreground">
                * 승인율 = 승인 / (승인 + 거절) × 100 (대기 중 액션 제외)
              </div>
            </div>
          )}

          {/* 시간대별 사용 패턴 */}
          <div className="bg-card border border-border rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-4">⏰ 사용 패턴 분석</h3>
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                <span className="text-sm">오늘 사용량</span>
                <div className="flex items-center gap-2">
                  <div className="w-32 h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary transition-all"
                      style={{
                        width: `${Math.min(100, ((usageStats?.daily_calls || 0) / (usageStats?.daily_limit || 100)) * 100)}%`
                      }}
                    />
                  </div>
                  <span className="text-sm font-medium">
                    {usageStats?.daily_calls || 0}/{usageStats?.daily_limit || 100}
                  </span>
                </div>
              </div>

              <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                <span className="text-sm">쿨다운 상태</span>
                <span className={`text-sm font-medium ${usageStats?.cooldown_remaining ? 'text-yellow-500' : 'text-green-500'}`}>
                  {usageStats?.cooldown_remaining ? `${usageStats.cooldown_remaining}초 남음` : '사용 가능'}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                <span className="text-sm">다음 리셋</span>
                <span className="text-sm font-medium">
                  {(() => {
                    const now = new Date()
                    const midnight = new Date(now)
                    midnight.setHours(24, 0, 0, 0)
                    const hoursLeft = Math.floor((midnight.getTime() - now.getTime()) / (1000 * 60 * 60))
                    const minsLeft = Math.floor(((midnight.getTime() - now.getTime()) % (1000 * 60 * 60)) / (1000 * 60))
                    return `${hoursLeft}시간 ${minsLeft}분 후`
                  })()}
                </span>
              </div>
            </div>
          </div>

          {/* 추천 사항 */}
          <div className="bg-gradient-to-r from-blue-50 to-purple-50 border border-blue-200 rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-4">💡 AI 사용 최적화 팁</h3>
            <ul className="space-y-2 text-sm">
              {usageStats?.daily_calls && usageStats.daily_calls > (usageStats.daily_limit || 100) * 0.8 && (
                <li className="flex items-start gap-2">
                  <span className="text-yellow-500">⚠️</span>
                  <span>일일 한도의 80% 이상을 사용했습니다. 중요한 작업을 우선 처리하세요.</span>
                </li>
              )}
              {summary?.actions_summary?.pending && summary.actions_summary.pending > 5 && (
                <li className="flex items-start gap-2">
                  <span className="text-blue-500">📋</span>
                  <span>{summary.actions_summary.pending}개의 액션이 대기 중입니다. 검토 후 승인해주세요.</span>
                </li>
              )}
              <li className="flex items-start gap-2">
                <span className="text-green-500">✓</span>
                <span>댓글 생성 시 여러 개를 한 번에 요청하면 효율적입니다.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-500">✓</span>
                <span>분석 작업은 오전 시간대에 집중하면 좋습니다.</span>
              </li>
            </ul>
          </div>
        </div>
      )}

      {/* 안내 */}
      <div className="bg-muted/50 border border-border rounded-lg p-4">
        <h4 className="font-semibold mb-2">💡 AI Agent 안내</h4>
        <ul className="text-sm text-muted-foreground space-y-1">
          <li>• AI Agent는 댓글 생성, 콘텐츠 분석 등 자동화 작업을 수행합니다.</li>
          <li>• 일일 사용량 한도가 있으며, 매일 자정에 리셋됩니다.</li>
          <li>• 대기 중인 액션은 승인 후 실행됩니다.</li>
          <li>• 쿨다운 시간 동안 연속 호출이 제한됩니다.</li>
        </ul>
      </div>
    </div>
    </PageTransition>
  )
}

/**
 * [Phase K-1] 키워드 라이프사이클 자동화 컴포넌트
 * 키워드 상태 관리 및 자동 전환
 */

import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  RefreshCw,
  ChevronRight,
  Search,
  Target,
  CheckCircle,
  Archive,
  Eye,
  Play,
  TrendingUp,
  TrendingDown,
} from 'lucide-react'
import { analyticsApi } from '@/services/api'
import { LoadingState, ErrorState } from './shared'
import Button, { IconButton } from '@/components/ui/Button'
import type {
  KeywordLifecycleData,
  KeywordLifecycleItem,
  KeywordTransition,
  LifecycleStatus,
} from '@/types/analytics'

const STATUS_CONFIG: Record<LifecycleStatus, {
  label: string
  icon: React.ReactNode
  color: string
  bgColor: string
  description: string
}> = {
  discovered: {
    label: '발견됨',
    icon: <Search className="w-4 h-4" />,
    color: 'text-blue-500',
    bgColor: 'bg-blue-500/10',
    description: '새로 발견된 키워드',
  },
  tracking: {
    label: '추적 중',
    icon: <Eye className="w-4 h-4" />,
    color: 'text-purple-500',
    bgColor: 'bg-purple-500/10',
    description: '성과 모니터링 중',
  },
  active: {
    label: '활성',
    icon: <Target className="w-4 h-4" />,
    color: 'text-green-500',
    bgColor: 'bg-green-500/10',
    description: '적극 활용 중',
  },
  maintaining: {
    label: '유지',
    icon: <CheckCircle className="w-4 h-4" />,
    color: 'text-yellow-500',
    bgColor: 'bg-yellow-500/10',
    description: '순위 유지 단계',
  },
  archived: {
    label: '보관',
    icon: <Archive className="w-4 h-4" />,
    color: 'text-gray-500',
    bgColor: 'bg-gray-500/10',
    description: '더 이상 사용하지 않음',
  },
}

const STATUS_ORDER: LifecycleStatus[] = ['discovered', 'tracking', 'active', 'maintaining', 'archived']

export default function KeywordLifecycle() {
  const [selectedStatus, setSelectedStatus] = useState<LifecycleStatus | 'all'>('all')
  const queryClient = useQueryClient()

  const { data, isLoading, isError, refetch, isRefetching } = useQuery<KeywordLifecycleData>({
    queryKey: ['keyword-lifecycle', selectedStatus === 'all' ? undefined : selectedStatus],
    queryFn: () => analyticsApi.getKeywordLifecycle(selectedStatus === 'all' ? undefined : selectedStatus),
    staleTime: 300000,
  })

  const updateStatusMutation = useMutation({
    mutationFn: ({ keyword, newStatus, reason }: { keyword: string; newStatus: string; reason?: string }) =>
      analyticsApi.updateKeywordStatus(keyword, newStatus, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['keyword-lifecycle'] })
    },
  })

  const autoTransitionMutation = useMutation({
    mutationFn: analyticsApi.runAutoTransition,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['keyword-lifecycle'] })
    },
  })

  if (isLoading) {
    return <LoadingState message="키워드 라이프사이클 로딩 중..." />
  }

  if (isError || !data) {
    return (
      <ErrorState
        message="키워드 라이프사이클 데이터를 불러오는데 실패했습니다"
        onRetry={() => refetch()}
        isRetrying={isRefetching}
      />
    )
  }

  const { keywords, summary, recent_transitions } = data

  return (
    <div className="bg-card rounded-lg border border-border">
      {/* 헤더 */}
      <div className="p-6 border-b border-border">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold flex items-center gap-2">
              <RefreshCw className="w-5 h-5 text-primary" />
              키워드 라이프사이클
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              키워드의 상태를 추적하고 관리합니다
            </p>
          </div>
          <Button
            variant="primary"
            onClick={() => autoTransitionMutation.mutate()}
            loading={autoTransitionMutation.isPending}
            icon={<Play className="w-4 h-4" />}
          >
            자동 전환 실행
          </Button>
        </div>
      </div>

      {/* 상태별 요약 */}
      <div className="p-6 border-b border-border">
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setSelectedStatus('all')}
            className={`px-4 py-2 rounded-lg text-sm transition-colors ${
              selectedStatus === 'all'
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted hover:bg-muted/70'
            }`}
          >
            전체 ({summary.total})
          </button>
          {STATUS_ORDER.map((status) => {
            const config = STATUS_CONFIG[status]
            const count = summary.by_status[status] || 0
            return (
              <button
                key={status}
                onClick={() => setSelectedStatus(status)}
                className={`px-4 py-2 rounded-lg text-sm transition-colors flex items-center gap-2 ${
                  selectedStatus === status
                    ? `${config.bgColor} ${config.color} border border-current`
                    : 'bg-muted hover:bg-muted/70'
                }`}
              >
                {config.icon}
                {config.label} ({count})
              </button>
            )
          })}
        </div>
      </div>

      {/* 라이프사이클 다이어그램 */}
      <div className="p-6 border-b border-border bg-muted/20">
        <h3 className="text-sm font-semibold text-muted-foreground mb-4">라이프사이클 흐름</h3>
        <div className="flex items-center justify-between overflow-x-auto pb-2">
          {STATUS_ORDER.map((status, idx) => {
            const config = STATUS_CONFIG[status]
            const count = summary.by_status[status] || 0
            return (
              <div key={status} className="flex items-center">
                <div className="text-center min-w-[100px]">
                  <div className={`w-12 h-12 mx-auto rounded-full ${config.bgColor} flex items-center justify-center ${config.color}`}>
                    {config.icon}
                  </div>
                  <div className="mt-2 text-xs font-medium">{config.label}</div>
                  <div className="text-lg font-bold">{count}</div>
                </div>
                {idx < STATUS_ORDER.length - 1 && (
                  <ChevronRight className="w-5 h-5 text-muted-foreground mx-2" />
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* 키워드 목록 */}
      <div className="p-6 border-b border-border">
        <h3 className="text-sm font-semibold text-muted-foreground mb-4">
          키워드 목록 ({keywords.length}개)
        </h3>
        <div className="space-y-2 max-h-[400px] overflow-y-auto">
          {keywords.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              해당 상태의 키워드가 없습니다
            </p>
          ) : (
            keywords.map((kw: KeywordLifecycleItem) => (
              <KeywordItem
                key={kw.keyword}
                keyword={kw}
                onStatusChange={(newStatus, reason) =>
                  updateStatusMutation.mutate({ keyword: kw.keyword, newStatus, reason })
                }
                isUpdating={updateStatusMutation.isPending}
              />
            ))
          )}
        </div>
      </div>

      {/* 최근 전환 이력 */}
      {recent_transitions.length > 0 && (
        <div className="p-6">
          <h3 className="text-sm font-semibold text-muted-foreground mb-3">최근 상태 전환</h3>
          <div className="space-y-2">
            {recent_transitions.slice(0, 5).map((t: KeywordTransition, idx: number) => (
              <div key={idx} className="flex items-center gap-2 text-sm bg-muted/30 rounded p-2">
                <span className="font-medium truncate flex-1">{t.keyword}</span>
                <span className={STATUS_CONFIG[t.from_status]?.color || ''}>
                  {STATUS_CONFIG[t.from_status]?.label || t.from_status}
                </span>
                <ChevronRight className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
                <span className={STATUS_CONFIG[t.to_status]?.color || ''}>
                  {STATUS_CONFIG[t.to_status]?.label || t.to_status}
                </span>
                <span className="text-xs text-muted-foreground">{t.changed_at}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const KeywordItem = React.memo(function KeywordItem({
  keyword,
  onStatusChange,
  isUpdating,
}: {
  keyword: KeywordLifecycleItem
  onStatusChange: (newStatus: string, reason?: string) => void
  isUpdating: boolean
}) {
  const [showActions, setShowActions] = useState(false)
  const config = STATUS_CONFIG[keyword.status as LifecycleStatus] || STATUS_CONFIG.discovered

  const getNextStatus = (current: LifecycleStatus): LifecycleStatus | null => {
    const idx = STATUS_ORDER.indexOf(current)
    if (idx < STATUS_ORDER.length - 1) return STATUS_ORDER[idx + 1]
    return null
  }

  const getPrevStatus = (current: LifecycleStatus): LifecycleStatus | null => {
    const idx = STATUS_ORDER.indexOf(current)
    if (idx > 0) return STATUS_ORDER[idx - 1]
    return null
  }

  const nextStatus = getNextStatus(keyword.status)
  const prevStatus = getPrevStatus(keyword.status)

  return (
    <div
      className={`p-3 rounded-lg border ${showActions ? 'border-primary' : 'border-border'} transition-colors`}
    >
      <div className="flex items-center gap-3">
        {/* 상태 아이콘 */}
        <div className={`w-8 h-8 rounded-full ${config.bgColor} flex items-center justify-center ${config.color}`}>
          {config.icon}
        </div>

        {/* 키워드 정보 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium truncate">{keyword.keyword}</span>
            <span className={`text-xs px-2 py-0.5 rounded ${config.bgColor} ${config.color}`}>
              {config.label}
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1">
            {(keyword.viral_count ?? 0) > 0 && <span>바이럴 {keyword.viral_count}</span>}
            {(keyword.lead_count ?? 0) > 0 && <span>리드 {keyword.lead_count}</span>}
            {(keyword.conversion_count ?? 0) > 0 && (
              <span className="text-green-500">전환 {keyword.conversion_count}</span>
            )}
            {keyword.current_rank && (
              <span className="flex items-center gap-1">
                순위 {keyword.current_rank}위
                {keyword.rank_change != null && keyword.rank_change !== 0 && (
                  keyword.rank_change > 0 ? (
                    <TrendingUp className="w-3 h-3 text-green-500" aria-hidden="true" />
                  ) : (
                    <TrendingDown className="w-3 h-3 text-red-500" aria-hidden="true" />
                  )
                )}
              </span>
            )}
            {keyword.last_activity_at && <span>업데이트: {keyword.last_activity_at}</span>}
          </div>
        </div>

        {/* 액션 버튼 */}
        <IconButton
          icon={<ChevronRight className={`w-4 h-4 transition-transform ${showActions ? 'rotate-90' : ''}`} />}
          onClick={() => setShowActions(!showActions)}
          title={showActions ? '액션 닫기' : '액션 보기'}
        />
      </div>

      {/* 상태 변경 액션 */}
      {showActions && (
        <div className="mt-3 pt-3 border-t border-border flex items-center gap-2">
          {prevStatus && (
            <Button
              variant="secondary"
              size="xs"
              onClick={() => onStatusChange(prevStatus, '수동 전환')}
              disabled={isUpdating}
              icon={<ChevronRight className="w-3 h-3 rotate-180" />}
            >
              {STATUS_CONFIG[prevStatus].label}로 되돌리기
            </Button>
          )}
          {nextStatus && (
            <Button
              variant="outline"
              size="xs"
              onClick={() => onStatusChange(nextStatus, '수동 전환')}
              disabled={isUpdating}
              icon={<ChevronRight className="w-3 h-3" />}
              iconPosition="right"
              className="text-primary"
            >
              {STATUS_CONFIG[nextStatus].label}로 진행
            </Button>
          )}
          {keyword.status !== 'archived' && (
            <Button
              variant="danger"
              size="xs"
              onClick={() => onStatusChange('archived', '수동 보관')}
              disabled={isUpdating}
              icon={<Archive className="w-3 h-3" />}
            >
              보관
            </Button>
          )}
        </div>
      )}
    </div>
  )
})

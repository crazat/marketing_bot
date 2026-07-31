/**
 * 스마트 필터 바 컴포넌트
 * AI 기반 빠른 필터 및 추천 시스템
 */

import { useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { viralApi, type SmartRecommendations } from '@/services/api'
import { Sparkles, ChevronRight, Loader2, Target, AlertCircle } from 'lucide-react'
import type { FilterState } from './FilterBar'

interface SmartFilterBarProps {
  onApplyFilter: (filter: Partial<FilterState>) => void
  onSelectTarget?: (targetId: string) => void
  workScope?: string
}

const platformLabels: Record<string, string> = {
  cafe: '카페',
  blog: '블로그',
  kin: '지식인',
  youtube: 'YouTube',
  instagram: '인스타',
  tiktok: 'TikTok',
  place: '플레이스',
  karrot: '당근'
}

export function SmartFilterBar({ onApplyFilter, onSelectTarget, workScope = 'latest_legion' }: SmartFilterBarProps) {
  const { data, isLoading, isError } = useQuery<SmartRecommendations>({
    queryKey: ['smart-recommendations', workScope],
    queryFn: () => viralApi.getSmartRecommendations(workScope),
    staleTime: 2 * 60 * 1000, // 2분
    refetchInterval: 5 * 60 * 1000, // 5분
  })

  // [Phase 7] useCallback으로 메모이제이션 — Rules of Hooks: early return 위에 정의해야 함
  const buildSmartFilterState = useCallback((filter: Record<string, unknown>): Partial<FilterState> => {
    const filterState: Partial<FilterState> = {
      status: 'pending',
      comment_status: undefined,
      category: undefined,
      platforms: undefined,
      date_filter: undefined,
      min_scan_count: undefined,
      min_score: undefined,
      min_clinic_fit: undefined,
      min_worksite_efficiency: undefined,
      commentable_only: undefined,
      search: undefined,
      scan_batch: undefined,
      ai_ad_label: undefined,
      min_confidence: undefined,
      specialty_match: undefined,
      post_region: undefined,
    }

    if (Array.isArray(filter.platforms)) {
      filterState.platforms = filter.platforms.filter((platform): platform is string => typeof platform === 'string')
    }
    if (filter.min_score) {
      filterState.min_score = Number(filter.min_score)
    }
    if (filter.min_clinic_fit) {
      filterState.min_clinic_fit = Number(filter.min_clinic_fit)
    }
    if (filter.min_worksite_efficiency) {
      filterState.min_worksite_efficiency = Number(filter.min_worksite_efficiency)
    }
    if (filter.commentable_only != null) {
      filterState.commentable_only = Boolean(filter.commentable_only)
    }
    if (filter.date_filter) filterState.date_filter = filter.date_filter as string
    if (filter.min_scan_count) filterState.min_scan_count = filter.min_scan_count as number
    if (filter.sort) filterState.sort = filter.sort as string
    if (filter.status) filterState.status = filter.status as string

    return filterState
  }, [])

  const handleApplyQuickFilter = useCallback((filter: Record<string, unknown>) => {
    onApplyFilter(buildSmartFilterState(filter))
  }, [buildSmartFilterState, onApplyFilter])

  const handleApplyPlatformFilter = useCallback((platform: string) => {
    onApplyFilter(buildSmartFilterState({
      status: 'pending',
      sort: 'priority',
      platforms: [platform],
    }))
  }, [buildSmartFilterState, onApplyFilter])

  if (isLoading) {
    return (
      <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 border border-purple-500/30 rounded-lg p-4">
        <div className="flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin text-purple-500" />
          <span className="text-sm text-muted-foreground">스마트 추천 로딩 중...</span>
        </div>
      </div>
    )
  }

  if (isError || !data) {
    return null
  }

  return (
    <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 border border-purple-500/30 rounded-lg p-4 space-y-4">
      {/* 헤더 */}
      <div className="flex items-center gap-2">
        <Sparkles className="w-5 h-5 text-purple-500" />
        <span className="font-semibold">스마트 추천</span>
      </div>

      {/* 빠른 필터 */}
      {data.quick_filters.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-muted-foreground mb-2">빠른 필터</h4>
          <div className="flex flex-wrap gap-2">
            {data.quick_filters.map((filter) => (
              <button
                key={filter.id}
                onClick={() => handleApplyQuickFilter(filter.filter)}
                className="flex items-center gap-2 px-3 py-2 bg-card hover:bg-muted border border-border rounded-lg transition-colors"
              >
                <span className="text-lg">{filter.icon}</span>
                <div className="text-left">
                  <div className="text-sm font-medium">{filter.name}</div>
                  <div className="text-xs text-muted-foreground">{filter.count}개</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 오늘 집중 타겟 */}
      {data.today_focus.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1">
            <Target className="w-3 h-3" />
            오늘 집중 타겟
          </h4>
          <div className="space-y-1">
            {data.today_focus.slice(0, 3).map((target) => (
              <button
                key={target.id}
                onClick={() => onSelectTarget?.(target.id)}
                className="w-full flex items-center justify-between p-2 bg-card hover:bg-muted rounded-lg text-left transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate">{target.title}</div>
                  <div className="text-xs text-muted-foreground">
                    {platformLabels[target.platform] || target.platform} · {target.priority_score?.toFixed(0)}점
                    {target.scan_count >= 2 && ` · ${target.scan_count}회`}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-bold ${
                    target.priority_score >= 80 ? 'text-red-500' :
                    target.priority_score >= 60 ? 'text-yellow-500' : 'text-blue-500'
                  }`}>
                    {target.priority_score?.toFixed(0)}
                  </span>
                  <ChevronRight className="w-4 h-4 text-muted-foreground" />
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 플랫폼별 우선순위 */}
      {data.platform_priorities.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-muted-foreground mb-2">플랫폼별 기회</h4>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {data.platform_priorities.slice(0, 4).map((p, idx) => (
              <button
                key={p.platform}
                onClick={() => handleApplyPlatformFilter(p.platform)}
                className={`flex-shrink-0 px-3 py-2 rounded-lg border text-center transition-colors ${
                  idx === 0
                    ? 'bg-purple-500/20 border-purple-500/50 hover:bg-purple-500/30'
                    : 'bg-card border-border hover:bg-muted'
                }`}
              >
                <div className="text-sm font-medium">
                  {platformLabels[p.platform] || p.platform}
                </div>
                <div className="text-xs text-muted-foreground">
                  {p.count}개 · {p.avg_score}점
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 인사이트 */}
      {data.insights.length > 0 && (
        <div className="space-y-1">
          {data.insights.slice(0, 2).map((insight, idx) => (
            <div
              key={idx}
              className={`flex items-start gap-2 p-2 rounded text-xs ${
                insight.importance === 'high'
                  ? 'bg-red-500/10 text-red-500'
                  : 'bg-muted text-muted-foreground'
              }`}
            >
              <AlertCircle className="w-3 h-3 flex-shrink-0 mt-0.5" />
              <span>{insight.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

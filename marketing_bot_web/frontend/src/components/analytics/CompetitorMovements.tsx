/**
 * [Phase I-1] 경쟁사 움직임 감지 컴포넌트
 * 경쟁사 순위 변동 및 활동 모니터링
 */

import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Eye,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Users,
  ChevronDown,
  ChevronUp,
  Star,
  Activity,
} from 'lucide-react'
import { analyticsApi } from '@/services/api'
import { LoadingState, ErrorState, SummaryCard } from './shared'
import type {
  CompetitorMovementsData,
  CompetitorAlert,
  CompetitorRankChange,
  NewCompetitor,
  ActivityChange,
} from '@/types/analytics'

interface CompetitorMovementsProps {
  compact?: boolean
  days?: number
}

export default function CompetitorMovements({ compact = false, days = 7 }: CompetitorMovementsProps) {
  const [showAllCompetitors, setShowAllCompetitors] = useState(false)

  const { data, isLoading, isError, refetch, isRefetching } = useQuery<CompetitorMovementsData>({
    queryKey: ['competitor-movements', days],
    queryFn: () => analyticsApi.getCompetitorMovements(days),
    staleTime: 300000,
  })

  if (isLoading) {
    return <LoadingState message="경쟁사 동향 분석 중..." />
  }

  if (isError || !data) {
    return (
      <ErrorState
        message="경쟁사 동향 데이터를 불러오는데 실패했습니다"
        onRetry={() => refetch()}
        isRetrying={isRefetching}
      />
    )
  }

  const { summary, rank_changes, new_competitors, activity_changes, alerts } = data

  // 컴팩트 모드
  if (compact) {
    return (
      <div className="bg-card rounded-lg border border-border p-4">
        <h3 className="font-semibold flex items-center gap-2 mb-3">
          <Eye className="w-4 h-4 text-primary" />
          경쟁사 동향
        </h3>

        {/* 요약 통계 */}
        <div className="grid grid-cols-3 gap-2 mb-3">
          <div className="text-center p-2 bg-muted/50 rounded">
            <div className="text-lg font-bold">{summary.total_competitors}</div>
            <div className="text-xs text-muted-foreground">경쟁사</div>
          </div>
          <div className="text-center p-2 bg-green-500/10 rounded">
            <div className="text-lg font-bold text-green-500">{summary.rank_improved}</div>
            <div className="text-xs text-muted-foreground">순위 상승</div>
          </div>
          <div className="text-center p-2 bg-red-500/10 rounded">
            <div className="text-lg font-bold text-red-500">{summary.rank_dropped}</div>
            <div className="text-xs text-muted-foreground">순위 하락</div>
          </div>
        </div>

        {/* 주요 알림 */}
        {alerts.length > 0 && (
          <div className="space-y-1">
            {alerts.slice(0, 2).map((alert: CompetitorAlert, idx: number) => (
              <div
                key={idx}
                className={`text-xs p-2 rounded flex items-center gap-2 ${
                  alert.severity === 'high'
                    ? 'bg-red-500/10 text-red-600'
                    : alert.severity === 'medium'
                    ? 'bg-yellow-500/10 text-yellow-600'
                    : 'bg-blue-500/10 text-blue-600'
                }`}
              >
                <AlertTriangle className="w-3 h-3" aria-hidden="true" />
                <span className="truncate">{alert.message}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  // 전체 모드
  return (
    <div className="bg-card rounded-lg border border-border">
      {/* 헤더 */}
      <div className="p-6 border-b border-border">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <Eye className="w-5 h-5 text-primary" />
          경쟁사 움직임 감지
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          최근 {days}일간 경쟁사의 순위 변동 및 활동을 추적합니다
        </p>
      </div>

      {/* 요약 대시보드 */}
      <div className="p-6 border-b border-border">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <SummaryCard
            label="총 경쟁사"
            value={summary.total_competitors}
            icon={<Users className="w-4 h-4" />}
          />
          <SummaryCard
            label="순위 상승"
            value={summary.rank_improved}
            icon={<TrendingUp className="w-4 h-4" />}
            color="text-green-500"
          />
          <SummaryCard
            label="순위 하락"
            value={summary.rank_dropped}
            icon={<TrendingDown className="w-4 h-4" />}
            color="text-red-500"
          />
          <SummaryCard
            label="신규 진입"
            value={summary.new_entries}
            icon={<Star className="w-4 h-4" />}
            color="text-yellow-500"
          />
          <SummaryCard
            label="활동 증가"
            value={summary.activity_increased}
            icon={<Activity className="w-4 h-4" />}
            color="text-purple-500"
          />
        </div>
      </div>

      {/* 알림 */}
      {alerts.length > 0 && (
        <div className="p-6 border-b border-border">
          <h3 className="text-sm font-semibold text-muted-foreground mb-3">주요 알림</h3>
          <div className="space-y-2">
            {alerts.map((alert: CompetitorAlert, idx: number) => (
              <div
                key={idx}
                className={`p-3 rounded-lg flex items-start gap-3 ${
                  alert.severity === 'high'
                    ? 'bg-red-500/10 border border-red-500/30'
                    : alert.severity === 'medium'
                    ? 'bg-yellow-500/10 border border-yellow-500/30'
                    : 'bg-blue-500/10 border border-blue-500/30'
                }`}
              >
                <AlertTriangle className={`w-4 h-4 mt-0.5 ${
                  alert.severity === 'high'
                    ? 'text-red-500'
                    : alert.severity === 'medium'
                    ? 'text-yellow-500'
                    : 'text-blue-500'
                }`} aria-hidden="true" />
                <div className="flex-1">
                  <p className="text-sm font-medium">{alert.message}</p>
                  {alert.competitor && (
                    <p className="text-xs text-muted-foreground mt-1">
                      {alert.competitor} - {alert.keyword}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 순위 변동 */}
      {rank_changes.length > 0 && (
        <div className="p-6 border-b border-border">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-muted-foreground">순위 변동</h3>
            {rank_changes.length > 5 && (
              <button
                onClick={() => setShowAllCompetitors(!showAllCompetitors)}
                className="text-xs text-primary hover:underline flex items-center gap-1"
              >
                {showAllCompetitors ? '접기' : `전체 보기 (${rank_changes.length})`}
                {showAllCompetitors ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
            )}
          </div>
          <div className="space-y-2">
            {(showAllCompetitors ? rank_changes : rank_changes.slice(0, 5)).map((change: CompetitorRankChange, idx: number) => (
              <RankChangeItem key={idx} change={change} />
            ))}
          </div>
        </div>
      )}

      {/* 신규 진입 경쟁사 */}
      {new_competitors.length > 0 && (
        <div className="p-6 border-b border-border">
          <h3 className="text-sm font-semibold text-muted-foreground mb-3">
            신규 진입 경쟁사 ({new_competitors.length})
          </h3>
          <div className="flex flex-wrap gap-2">
            {new_competitors.map((comp: NewCompetitor, idx: number) => (
              <div
                key={idx}
                className="px-3 py-2 bg-yellow-500/10 border border-yellow-500/30 rounded-lg"
              >
                <div className="text-sm font-medium">{comp.name}</div>
                <div className="text-xs text-muted-foreground">
                  {comp.keyword} - {comp.rank}위
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 활동 변화 */}
      {activity_changes.length > 0 && (
        <div className="p-6">
          <h3 className="text-sm font-semibold text-muted-foreground mb-3">활동 변화 감지</h3>
          <div className="space-y-2">
            {activity_changes.map((activity: ActivityChange, idx: number) => (
              <div
                key={idx}
                className="flex items-center justify-between p-3 bg-muted/30 rounded-lg"
              >
                <div>
                  <div className="font-medium">{activity.competitor}</div>
                  <div className="text-xs text-muted-foreground">{activity.type}</div>
                </div>
                <div className="text-right">
                  <div className={`text-sm font-medium ${
                    activity.direction === 'increase' ? 'text-green-500' : 'text-red-500'
                  }`}>
                    {activity.direction === 'increase' ? '+' : ''}{activity.change}
                  </div>
                  <div className="text-xs text-muted-foreground">{activity.metric}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 데이터 없음 */}
      {rank_changes.length === 0 && new_competitors.length === 0 && activity_changes.length === 0 && (
        <div className="p-6 text-center text-muted-foreground">
          <Eye className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>최근 {days}일간 특별한 경쟁사 움직임이 감지되지 않았습니다</p>
        </div>
      )}
    </div>
  )
}

const RankChangeItem = React.memo(function RankChangeItem({ change }: { change: CompetitorRankChange }) {
  const isUp = change.direction === 'up'
  const rankDiff = Math.abs(change.previous_rank - change.current_rank)

  return (
    <div className="flex items-center gap-3 p-3 bg-muted/30 rounded-lg">
      {/* 방향 아이콘 */}
      <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
        isUp ? 'bg-green-500/20' : 'bg-red-500/20'
      }`}>
        {isUp ? (
          <TrendingUp className="w-4 h-4 text-green-500" />
        ) : (
          <TrendingDown className="w-4 h-4 text-red-500" />
        )}
      </div>

      {/* 경쟁사 정보 */}
      <div className="flex-1 min-w-0">
        <div className="font-medium truncate">{change.competitor}</div>
        <div className="text-xs text-muted-foreground">{change.keyword}</div>
      </div>

      {/* 순위 변동 */}
      <div className="text-right">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">{change.previous_rank}위</span>
          <span>→</span>
          <span className={isUp ? 'text-green-500 font-medium' : 'text-red-500 font-medium'}>
            {change.current_rank}위
          </span>
        </div>
        <div className={`text-xs ${isUp ? 'text-green-500' : 'text-red-500'}`}>
          {isUp ? '▲' : '▼'} {rankDiff}단계
        </div>
      </div>
    </div>
  )
})

/**
 * [Phase J-2] AI 주간 브리핑 컴포넌트
 * 크로스 모듈 데이터 기반 자동 브리핑
 */

import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  TrendingUp,
  TrendingDown,
  Users,
  DollarSign,
  Target,
  AlertTriangle,
  ChevronRight,
  Calendar,
  RefreshCw,
} from 'lucide-react'
import { analyticsApi } from '@/services/api'
import { LoadingState, ErrorState } from './shared'
import Button, { IconButton } from '@/components/ui/Button'
import type {
  WeeklyBriefingData,
  TopKeyword,
  RankChange,
  RecommendedAction,
} from '@/types/analytics'

interface WeeklyBriefingProps {
  compact?: boolean
}

export default function WeeklyBriefing({ compact = false }: WeeklyBriefingProps) {
  const navigate = useNavigate()

  const { data, isLoading, isError, refetch, isRefetching } = useQuery<WeeklyBriefingData>({
    queryKey: ['weekly-briefing'],
    queryFn: analyticsApi.getWeeklyBriefing,
    staleTime: 300000, // 5분
    refetchInterval: 600000, // 10분
  })

  if (isLoading) {
    return <LoadingState message="브리핑 생성 중..." />
  }

  if (isError || !data) {
    return (
      <ErrorState
        message="브리핑 데이터를 불러오는데 실패했습니다"
        onRetry={() => refetch()}
        isRetrying={isRefetching}
      />
    )
  }

  const { key_metrics, top_performing_keywords, rank_changes, insights, recommended_actions, alerts } = data

  // 컴팩트 모드
  if (compact) {
    return (
      <div className="bg-gradient-to-br from-primary/5 to-primary/10 rounded-lg border border-primary/20 p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold flex items-center gap-2">
            <Calendar className="w-4 h-4 text-primary" aria-hidden="true" />
            이번주 브리핑
          </h3>
          <IconButton
            icon={<RefreshCw className={`w-4 h-4 ${isRefetching ? 'animate-spin' : ''}`} />}
            onClick={() => refetch()}
            disabled={isRefetching}
            title="브리핑 새로고침"
            size="sm"
          />
        </div>

        <div className="grid grid-cols-3 gap-3 mb-3">
          <div className="text-center">
            <div className="text-2xl font-bold">{key_metrics.new_leads.value}</div>
            <div className="text-xs text-muted-foreground">신규 리드</div>
            <ChangeIndicator value={key_metrics.new_leads.change_percent} />
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold">{key_metrics.conversions.value}</div>
            <div className="text-xs text-muted-foreground">전환</div>
            <ChangeIndicator value={key_metrics.conversions.change_percent} />
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold">{(key_metrics.revenue.value / 10000).toFixed(0)}만</div>
            <div className="text-xs text-muted-foreground">매출</div>
            <ChangeIndicator value={key_metrics.revenue.change_percent} />
          </div>
        </div>

        {alerts.pending_hot_leads > 0 && (
          <div className="bg-red-500/10 border border-red-500/30 rounded p-2 text-sm flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-500" aria-hidden="true" />
            <span>Hot 리드 {alerts.pending_hot_leads}건 응답 대기</span>
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
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Calendar className="w-5 h-5 text-primary" aria-hidden="true" />
              주간 마케팅 브리핑
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              {data.period.start} ~ {data.period.end}
            </p>
          </div>
          <IconButton
            icon={<RefreshCw className={`w-5 h-5 ${isRefetching ? 'animate-spin' : ''}`} />}
            onClick={() => refetch()}
            disabled={isRefetching}
            title="브리핑 새로고침"
          />
        </div>
      </div>

      {/* 핵심 지표 */}
      <div className="p-6 border-b border-border">
        <h3 className="text-sm font-semibold text-muted-foreground mb-4">핵심 지표</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricCard
            icon={<Users className="w-5 h-5" />}
            label="신규 리드"
            value={key_metrics.new_leads.value}
            change={key_metrics.new_leads.change_percent}
            subtext={`Hot ${key_metrics.new_leads.hot_count} / Warm ${key_metrics.new_leads.warm_count}`}
          />
          <MetricCard
            icon={<Target className="w-5 h-5" />}
            label="전환"
            value={key_metrics.conversions.value}
            change={key_metrics.conversions.change_percent}
            subtext={`전환율 ${key_metrics.conversions.conversion_rate}%`}
          />
          <MetricCard
            icon={<DollarSign className="w-5 h-5" />}
            label="매출"
            value={`${(key_metrics.revenue.value / 10000).toFixed(0)}만원`}
            change={key_metrics.revenue.change_percent}
          />
          <MetricCard
            icon={<AlertTriangle className="w-5 h-5" />}
            label="대기 중"
            value={alerts.pending_hot_leads}
            variant={alerts.pending_hot_leads > 0 ? 'warning' : 'default'}
            subtext="Hot 리드"
          />
        </div>
      </div>

      {/* 인사이트 & 키워드 */}
      <div className="p-6 border-b border-border grid md:grid-cols-2 gap-6">
        {/* 인사이트 */}
        <div>
          <h3 className="text-sm font-semibold text-muted-foreground mb-3">인사이트</h3>
          <div className="space-y-2">
            {insights.map((insight: string, idx: number) => (
              <div key={idx} className="text-sm bg-muted/50 rounded p-2">
                {insight}
              </div>
            ))}
            {insights.length === 0 && (
              <p className="text-sm text-muted-foreground">특별한 인사이트가 없습니다</p>
            )}
          </div>
        </div>

        {/* 최고 성과 키워드 */}
        <div>
          <h3 className="text-sm font-semibold text-muted-foreground mb-3">최고 성과 키워드</h3>
          <div className="space-y-2">
            {top_performing_keywords.slice(0, 5).map((kw: TopKeyword, idx: number) => (
              <div key={idx} className="flex items-center justify-between text-sm">
                <span className="truncate flex-1">{kw.keyword}</span>
                <span className="text-muted-foreground ml-2">
                  {kw.conversions}건 / {(kw.revenue / 10000).toFixed(0)}만원
                </span>
              </div>
            ))}
            {top_performing_keywords.length === 0 && (
              <p className="text-sm text-muted-foreground">데이터가 없습니다</p>
            )}
          </div>
        </div>
      </div>

      {/* 순위 변동 */}
      {rank_changes.length > 0 && (
        <div className="p-6 border-b border-border">
          <h3 className="text-sm font-semibold text-muted-foreground mb-3">순위 변동</h3>
          <div className="flex flex-wrap gap-2">
            {rank_changes.map((rc: RankChange, idx: number) => (
              <div
                key={idx}
                className={`px-3 py-1.5 rounded-lg text-sm flex items-center gap-1 ${
                  rc.direction === 'up'
                    ? 'bg-green-500/10 text-green-600'
                    : rc.direction === 'down'
                    ? 'bg-red-500/10 text-red-600'
                    : 'bg-muted'
                }`}
              >
                {rc.direction === 'up' ? (
                  <TrendingUp className="w-3 h-3" />
                ) : rc.direction === 'down' ? (
                  <TrendingDown className="w-3 h-3" />
                ) : null}
                <span>{rc.keyword}</span>
                <span className="font-medium">
                  {rc.previous_rank}→{rc.current_rank}위
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 권장 액션 */}
      <div className="p-6">
        <h3 className="text-sm font-semibold text-muted-foreground mb-3">권장 액션</h3>
        <div className="space-y-2">
          {recommended_actions.map((action: RecommendedAction, idx: number) => (
            <Button
              key={idx}
              variant={action.priority === 'high' ? 'danger' : 'ghost'}
              fullWidth
              onClick={() => navigate(action.link)}
              icon={<ChevronRight className="w-4 h-4" />}
              iconPosition="right"
              className={`justify-between ${
                action.priority === 'high'
                  ? 'bg-red-500/10 hover:bg-red-500/20 border border-red-500/30'
                  : 'bg-muted/50 hover:bg-muted'
              }`}
            >
              {action.action}
            </Button>
          ))}
          {recommended_actions.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">
              현재 특별히 권장되는 액션이 없습니다
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

// 변화율 표시
function ChangeIndicator({ value }: { value: number }) {
  if (value === 0) return null

  return (
    <span className={`text-xs ${value > 0 ? 'text-green-500' : 'text-red-500'}`}>
      {value > 0 ? '+' : ''}{value.toFixed(0)}%
    </span>
  )
}

// 메트릭 카드
function MetricCard({
  icon,
  label,
  value,
  change,
  subtext,
  variant = 'default',
}: {
  icon: React.ReactNode
  label: string
  value: string | number
  change?: number
  subtext?: string
  variant?: 'default' | 'warning'
}) {
  return (
    <div className={`p-4 rounded-lg ${
      variant === 'warning' && typeof value === 'number' && value > 0
        ? 'bg-red-500/10 border border-red-500/30'
        : 'bg-muted/50'
    }`}>
      <div className="flex items-center gap-2 text-muted-foreground mb-1">
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold">{value}</span>
        {change !== undefined && <ChangeIndicator value={change} />}
      </div>
      {subtext && <p className="text-xs text-muted-foreground mt-1">{subtext}</p>}
    </div>
  )
}

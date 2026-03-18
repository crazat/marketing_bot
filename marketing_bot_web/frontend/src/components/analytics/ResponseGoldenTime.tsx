/**
 * [Phase H-3] 리드 응답 골든타임 컴포넌트
 * 응답 시간별 전환율 분석
 */

import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Clock,
  AlertTriangle,
  TrendingUp,
  ChevronRight,
} from 'lucide-react'
import { analyticsApi } from '@/services/api'
import { LoadingState, ErrorState } from './shared'
import Button from '@/components/ui/Button'
import type { ResponseGoldenTimeData, TimeBracket } from '@/types/analytics'

interface ResponseGoldenTimeProps {
  compact?: boolean
}

export default function ResponseGoldenTime({ compact = false }: ResponseGoldenTimeProps) {
  const navigate = useNavigate()

  const { data, isLoading, isError, refetch, isRefetching } = useQuery<ResponseGoldenTimeData>({
    queryKey: ['response-golden-time'],
    queryFn: () => analyticsApi.getResponseGoldenTime(90),
    staleTime: 300000,
  })

  if (isLoading) {
    return <LoadingState message="골든타임 분석 중..." />
  }

  if (isError || !data) {
    return (
      <ErrorState
        message="골든타임 데이터를 불러오는데 실패했습니다"
        onRetry={() => refetch()}
        isRetrying={isRefetching}
      />
    )
  }

  const { by_response_time, hot_lead_analysis, alerts, insights } = data

  // 컴팩트 모드
  if (compact) {
    return (
      <div className="bg-card rounded-lg border border-border p-4">
        <h3 className="font-semibold flex items-center gap-2 mb-3">
          <Clock className="w-4 h-4 text-primary" />
          응답 골든타임
        </h3>

        {/* 시간대별 전환율 바 */}
        <div className="space-y-2 mb-3">
          {by_response_time.slice(0, 3).map((bracket: TimeBracket) => (
            <div key={bracket.bracket} className="flex items-center gap-2">
              <span className="text-xs w-20 text-muted-foreground">{bracket.bracket}</span>
              <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full"
                  style={{ width: `${Math.min(bracket.conversion_rate * 3, 100)}%` }}
                />
              </div>
              <span className="text-xs font-medium w-10 text-right">{bracket.conversion_rate}%</span>
            </div>
          ))}
        </div>

        {/* 긴급 알림 */}
        {alerts.urgent_hot_leads > 0 && (
          <Button
            variant="danger"
            fullWidth
            onClick={() => navigate('/leads?grade=hot&status=pending')}
            icon={<ChevronRight className="w-4 h-4" />}
            iconPosition="right"
            className="bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 justify-between"
          >
            <span className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-500" aria-hidden="true" />
              긴급! {alerts.urgent_hot_leads}건 48시간 초과
            </span>
          </Button>
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
          <Clock className="w-5 h-5 text-primary" />
          응답 골든타임 분석
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          빠른 응답이 전환율에 미치는 영향을 분석합니다
        </p>
      </div>

      {/* 핵심 인사이트 */}
      {hot_lead_analysis.within_1hour.conversion_rate > 0 && (
        <div className="p-6 border-b border-border bg-gradient-to-r from-green-500/5 to-transparent">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-green-500/20 flex items-center justify-center">
              <TrendingUp className="w-8 h-8 text-green-500" />
            </div>
            <div>
              <p className="text-lg font-bold">
                1시간 내 응답 시 전환율{' '}
                <span className="text-green-500">{hot_lead_analysis.within_1hour.conversion_rate}%</span>
              </p>
              <p className="text-sm text-muted-foreground">
                48시간 이후 응답 대비{' '}
                {hot_lead_analysis.after_48hours.conversion_rate > 0
                  ? `${(hot_lead_analysis.within_1hour.conversion_rate / hot_lead_analysis.after_48hours.conversion_rate).toFixed(1)}배`
                  : '월등히'}{' '}
                높은 전환율
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 시간대별 전환율 */}
      <div className="p-6 border-b border-border">
        <h3 className="text-sm font-semibold text-muted-foreground mb-4">응답 시간대별 전환율</h3>
        <div className="space-y-3">
          {by_response_time.map((bracket: TimeBracket, idx: number) => {
            const isOptimal = idx === 0
            const isWarning = idx >= 3

            return (
              <div key={bracket.bracket} className="flex items-center gap-4">
                <span className="w-28 text-sm">{bracket.bracket}</span>
                <div className="flex-1 relative">
                  <div className="h-8 bg-muted rounded-lg overflow-hidden">
                    <div
                      className={`h-full rounded-lg flex items-center justify-end pr-2 ${
                        isOptimal ? 'bg-green-500' :
                        isWarning ? 'bg-red-500/70' : 'bg-blue-500/70'
                      }`}
                      style={{ width: `${Math.max(bracket.conversion_rate * 3, 5)}%` }}
                    >
                      {bracket.conversion_rate > 5 && (
                        <span className="text-xs text-white font-medium">
                          {bracket.conversion_rate}%
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="w-24 text-right">
                  <div className="text-sm font-medium">{bracket.total_leads}건</div>
                  <div className="text-xs text-muted-foreground">{bracket.converted} 전환</div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* 알림 */}
      {(alerts.pending_hot_leads > 0 || alerts.urgent_hot_leads > 0) && (
        <div className="p-6 border-b border-border">
          <h3 className="text-sm font-semibold text-muted-foreground mb-3">주의 필요</h3>
          <div className="space-y-2">
            {alerts.urgent_hot_leads > 0 && (
              <Button
                variant="danger"
                fullWidth
                onClick={() => navigate('/leads?grade=hot&status=pending')}
                icon={<ChevronRight className="w-5 h-5" />}
                iconPosition="right"
                className="bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 p-4 justify-between"
              >
                <div className="flex items-center gap-3">
                  <AlertTriangle className="w-5 h-5 text-red-500" aria-hidden="true" />
                  <div className="text-left">
                    <p className="font-medium">긴급: Hot 리드 {alerts.urgent_hot_leads}건 48시간 초과</p>
                    <p className="text-sm text-muted-foreground">즉시 응답이 필요합니다</p>
                  </div>
                </div>
              </Button>
            )}
            {alerts.pending_hot_leads > alerts.urgent_hot_leads && (
              <Button
                variant="ghost"
                fullWidth
                onClick={() => navigate('/leads?grade=hot&status=pending')}
                icon={<ChevronRight className="w-5 h-5" />}
                iconPosition="right"
                className="bg-yellow-500/10 hover:bg-yellow-500/20 border border-yellow-500/30 p-4 justify-between"
              >
                <div className="flex items-center gap-3">
                  <Clock className="w-5 h-5 text-yellow-500" aria-hidden="true" />
                  <div className="text-left">
                    <p className="font-medium">
                      Hot 리드 {alerts.pending_hot_leads - alerts.urgent_hot_leads}건 응답 대기
                    </p>
                    <p className="text-sm text-muted-foreground">골든타임 내 응답을 권장합니다</p>
                  </div>
                </div>
              </Button>
            )}
          </div>
        </div>
      )}

      {/* 인사이트 */}
      {insights.length > 0 && (
        <div className="p-6">
          <h3 className="text-sm font-semibold text-muted-foreground mb-3">인사이트</h3>
          <div className="space-y-2">
            {insights.map((insight: string, idx: number) => (
              <div key={idx} className="text-sm bg-muted/50 rounded p-3">
                {insight}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

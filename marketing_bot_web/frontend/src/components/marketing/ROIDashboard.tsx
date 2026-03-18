/**
 * 통합 ROI 대시보드 컴포넌트
 */

import { useQuery } from '@tanstack/react-query'
import { marketingApi } from '@/services/api'
import { TrendingUp, DollarSign, Target, Users, ArrowRight, Lightbulb, RefreshCw } from 'lucide-react'
import Button, { IconButton } from '@/components/ui/Button'
import type { ROIDashboardData } from '@/types/marketing'

interface ROIDashboardProps {
  days?: number
  compact?: boolean
}

const PLATFORM_LABELS: Record<string, string> = {
  cafe: '카페',
  blog: '블로그',
  kin: '지식인',
  youtube: 'YouTube',
  instagram: '인스타',
  tiktok: 'TikTok',
  place: '플레이스',
  karrot: '당근',
  unknown: '기타',
}

export function ROIDashboard({ days = 30, compact = false }: ROIDashboardProps) {
  const { data, isLoading, error, refetch, isRefetching } = useQuery<ROIDashboardData>({
    queryKey: ['roi-dashboard', days],
    queryFn: () => marketingApi.getROIDashboard(days),
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 animate-pulse">
        <div className="h-6 bg-muted rounded w-1/3 mb-4" />
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-24 bg-muted rounded" />
          ))}
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 text-center">
        <p className="text-muted-foreground">ROI 데이터를 불러올 수 없습니다.</p>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => refetch()}
          className="mt-2"
        >
          다시 시도
        </Button>
      </div>
    )
  }

  const { funnel, by_channel, summary, recommendations } = data

  // 컴팩트 모드 (홈 화면용)
  if (compact) {
    return (
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <DollarSign className="w-5 h-5 text-green-500" />
            ROI 요약
          </h3>
          <span className="text-2xl font-bold text-green-500">{summary.overall_roi}%</span>
        </div>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="text-center p-3 bg-muted/50 rounded-lg">
            <div className="text-xl font-bold">{funnel.conversions}</div>
            <div className="text-xs text-muted-foreground">전환</div>
          </div>
          <div className="text-center p-3 bg-muted/50 rounded-lg">
            <div className="text-xl font-bold">{(summary.total_revenue / 10000).toFixed(0)}만</div>
            <div className="text-xs text-muted-foreground">수익</div>
          </div>
        </div>

        {recommendations.length > 0 && (
          <div className="p-2 bg-blue-500/10 rounded-lg text-xs text-blue-400">
            <Lightbulb className="w-3 h-3 inline mr-1" />
            {recommendations[0].title}
          </div>
        )}
      </div>
    )
  }

  // 전체 모드
  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <DollarSign className="w-6 h-6 text-green-500" />
          통합 ROI 대시보드
        </h2>
        <div className="flex items-center gap-4">
          <span className="text-sm text-muted-foreground">최근 {days}일</span>
          <IconButton
            icon={<RefreshCw className={`w-4 h-4 ${isRefetching ? 'animate-spin' : ''}`} />}
            onClick={() => refetch()}
            disabled={isRefetching}
            title="새로고침"
          />
        </div>
      </div>

      {/* 핵심 지표 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <Target className="w-8 h-8 mx-auto mb-2 text-blue-500" />
          <div className="text-3xl font-bold">{funnel.targets.toLocaleString()}</div>
          <div className="text-sm text-muted-foreground">발견된 타겟</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <Users className="w-8 h-8 mx-auto mb-2 text-purple-500" />
          <div className="text-3xl font-bold">{funnel.leads}</div>
          <div className="text-sm text-muted-foreground">생성된 리드</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <TrendingUp className="w-8 h-8 mx-auto mb-2 text-green-500" />
          <div className="text-3xl font-bold">{funnel.conversions}</div>
          <div className="text-sm text-muted-foreground">전환 성공</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <DollarSign className="w-8 h-8 mx-auto mb-2 text-yellow-500" />
          <div className="text-3xl font-bold">{(summary.total_revenue / 10000).toFixed(0)}만</div>
          <div className="text-sm text-muted-foreground">총 수익</div>
        </div>
      </div>

      {/* 퍼널 분석 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">마케팅 퍼널</h3>
        <div className="flex items-center justify-between">
          <div className="text-center flex-1">
            <div className="text-2xl font-bold">{funnel.targets.toLocaleString()}</div>
            <div className="text-sm text-muted-foreground">타겟</div>
          </div>
          <div className="flex flex-col items-center">
            <ArrowRight className="w-5 h-5 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">{funnel.rates.target_to_comment}%</span>
          </div>
          <div className="text-center flex-1">
            <div className="text-2xl font-bold text-blue-500">{funnel.comments}</div>
            <div className="text-sm text-muted-foreground">댓글</div>
          </div>
          <div className="flex flex-col items-center">
            <ArrowRight className="w-5 h-5 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">{funnel.rates.comment_to_engagement}%</span>
          </div>
          <div className="text-center flex-1">
            <div className="text-2xl font-bold text-purple-500">{funnel.engagements}</div>
            <div className="text-sm text-muted-foreground">반응</div>
          </div>
          <div className="flex flex-col items-center">
            <ArrowRight className="w-5 h-5 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">{funnel.rates.engagement_to_lead}%</span>
          </div>
          <div className="text-center flex-1">
            <div className="text-2xl font-bold text-yellow-500">{funnel.leads}</div>
            <div className="text-sm text-muted-foreground">리드</div>
          </div>
          <div className="flex flex-col items-center">
            <ArrowRight className="w-5 h-5 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">{funnel.rates.lead_to_conversion}%</span>
          </div>
          <div className="text-center flex-1">
            <div className="text-2xl font-bold text-green-500">{funnel.conversions}</div>
            <div className="text-sm text-muted-foreground">전환</div>
          </div>
        </div>

        {/* 퍼널 바 */}
        <div className="mt-4 h-4 bg-muted rounded-full overflow-hidden flex">
          <div
            className="bg-blue-500 h-full transition-all"
            style={{ width: `${funnel.rates.target_to_comment}%` }}
            title="타겟→댓글"
          />
          <div
            className="bg-purple-500 h-full transition-all"
            style={{ width: `${funnel.rates.comment_to_engagement * 0.5}%` }}
            title="댓글→반응"
          />
          <div
            className="bg-yellow-500 h-full transition-all"
            style={{ width: `${funnel.rates.engagement_to_lead * 0.3}%` }}
            title="반응→리드"
          />
          <div
            className="bg-green-500 h-full transition-all"
            style={{ width: `${funnel.rates.lead_to_conversion * 0.2}%` }}
            title="리드→전환"
          />
        </div>
      </div>

      {/* 채널별 ROI */}
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">채널별 ROI</h3>
        <div className="space-y-3">
          {by_channel.map((channel) => (
            <div key={channel.platform} className="flex items-center gap-4">
              <div className="w-20 font-medium">
                {PLATFORM_LABELS[channel.platform] || channel.platform}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <div
                    className="h-6 bg-gradient-to-r from-blue-500 to-green-500 rounded"
                    style={{
                      width: `${Math.min(channel.roi_percentage / 20, 100)}%`,
                      minWidth: '20px'
                    }}
                  />
                  <span className={`font-bold ${channel.roi_percentage > 0 ? 'text-green-500' : 'text-red-500'}`}>
                    {channel.roi_percentage > 0 ? '+' : ''}{channel.roi_percentage}%
                  </span>
                </div>
                <div className="flex gap-4 text-xs text-muted-foreground">
                  <span>댓글 {channel.comments}</span>
                  <span>리드 {channel.leads}</span>
                  <span>전환 {channel.conversions}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* AI 권장사항 */}
      {recommendations.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Lightbulb className="w-5 h-5 text-yellow-500" />
            AI 권장사항
          </h3>
          <div className="space-y-3">
            {recommendations.map((rec, idx) => (
              <div
                key={idx}
                className={`p-4 rounded-lg border ${
                  rec.priority === 'high'
                    ? 'border-red-500/50 bg-red-500/10'
                    : rec.priority === 'medium'
                    ? 'border-yellow-500/50 bg-yellow-500/10'
                    : 'border-blue-500/50 bg-blue-500/10'
                }`}
              >
                <div className="font-medium">{rec.title}</div>
                <div className="text-sm text-muted-foreground mt-1">{rec.description}</div>
                <div className="text-xs text-green-500 mt-2">{rec.expected_impact}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 종합 ROI */}
      <div className="bg-gradient-to-r from-green-500/20 to-blue-500/20 border border-green-500/30 rounded-lg p-6 text-center">
        <div className="text-sm text-muted-foreground mb-1">종합 ROI</div>
        <div className="text-5xl font-bold text-green-400">{summary.overall_roi}%</div>
        <div className="text-sm text-muted-foreground mt-2">
          비용 {(summary.estimated_cost / 10000).toFixed(0)}만원 → 수익 {(summary.total_revenue / 10000).toFixed(0)}만원
        </div>
      </div>
    </div>
  )
}

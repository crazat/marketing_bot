/**
 * [Phase M-2] Before/After 비교 분석 컴포넌트
 * 두 기간의 마케팅 지표 비교
 */

import { useQuery } from '@tanstack/react-query'
import {
  ArrowRight,
  TrendingUp,
  TrendingDown,
  Minus,
  RefreshCw,
  Calendar,
  ChevronUp,
  ChevronDown,
} from 'lucide-react'
import { analyticsApi } from '@/services/api'
import { LoadingState, ErrorState } from './shared'
import type { BeforeAfterComparisonData, MetricChange } from '@/types/analytics'

interface BeforeAfterComparisonProps {
  compact?: boolean
}

export default function BeforeAfterComparison({ compact = false }: BeforeAfterComparisonProps) {
  const { data, isLoading, isError, refetch, isRefetching } = useQuery<BeforeAfterComparisonData>({
    queryKey: ['before-after-comparison'],
    queryFn: () => analyticsApi.getBeforeAfterComparison(),
    staleTime: 300000, // 5분
  })

  if (isLoading) {
    return <LoadingState message="비교 분석 중..." />
  }

  if (isError || !data) {
    return (
      <ErrorState
        message="비교 데이터를 불러오는데 실패했습니다"
        onRetry={() => refetch()}
        isRetrying={isRefetching}
      />
    )
  }

  const { periods, before, after, changes, overall, overall_label, positive_changes, negative_changes, insights } = data

  // 전체 평가 색상
  const overallColors: Record<string, string> = {
    significant_improvement: 'text-green-500 bg-green-500/10',
    improvement: 'text-green-500 bg-green-500/10',
    stable: 'text-blue-500 bg-blue-500/10',
    decline: 'text-red-500 bg-red-500/10',
    significant_decline: 'text-red-500 bg-red-500/10',
  }

  // 컴팩트 모드
  if (compact) {
    return (
      <div className="bg-card rounded-lg border border-border p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold flex items-center gap-2">
            <Calendar className="w-4 h-4 text-primary" aria-hidden="true" />
            Before/After
          </h3>
          <div className={`px-2 py-1 rounded-lg text-sm font-medium ${overallColors[overall]}`}>
            {overall_label}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs text-muted-foreground mb-1">Before</div>
            <div className="text-lg font-bold">{before.leads.total}건</div>
            <div className="text-xs text-muted-foreground">리드</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground mb-1">After</div>
            <div className="text-lg font-bold flex items-center gap-1">
              {after.leads.total}건
              <ChangeIcon change={changes.leads_total} />
            </div>
            <div className="text-xs text-muted-foreground">리드</div>
          </div>
        </div>

        <div className="mt-3 pt-3 border-t border-border text-xs text-muted-foreground">
          개선 {positive_changes}개 / 하락 {negative_changes}개
        </div>
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
              Before/After 비교
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              {periods.before.start} ~ {periods.before.end} vs {periods.after.start} ~ {periods.after.end}
            </p>
          </div>
          <button
            onClick={() => refetch()}
            className="p-2 hover:bg-muted rounded-lg transition-colors"
            disabled={isRefetching}
            aria-label="비교 데이터 새로고침"
          >
            <RefreshCw className={`w-5 h-5 ${isRefetching ? 'animate-spin' : ''}`} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* 종합 평가 */}
      <div className="p-6 border-b border-border">
        <div className={`p-4 rounded-lg ${overallColors[overall]}`}>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-2xl font-bold">{overall_label}</div>
              <div className="text-sm mt-1">
                개선 {positive_changes}개 / 하락 {negative_changes}개 항목
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="text-center">
                <div className="text-sm text-muted-foreground">Before</div>
                <div className="text-lg font-bold">{before.leads.total}</div>
              </div>
              <ArrowRight className="w-5 h-5" aria-hidden="true" />
              <div className="text-center">
                <div className="text-sm text-muted-foreground">After</div>
                <div className="text-lg font-bold">{after.leads.total}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 상세 비교 */}
      <div className="p-6 border-b border-border">
        <h3 className="text-sm font-semibold text-muted-foreground mb-4">상세 비교</h3>
        <div className="space-y-3">
          <ComparisonRow
            label="총 리드"
            before={before.leads.total}
            after={after.leads.total}
            change={changes.leads_total}
            unit="건"
          />
          <ComparisonRow
            label="Hot 리드"
            before={before.leads.hot}
            after={after.leads.hot}
            change={changes.leads_hot}
            unit="건"
          />
          <ComparisonRow
            label="전환"
            before={before.conversions}
            after={after.conversions}
            change={changes.conversions}
            unit="건"
          />
          <ComparisonRow
            label="매출"
            before={before.revenue}
            after={after.revenue}
            change={changes.revenue}
            unit="원"
            formatValue={(v) => `${(v / 10000).toFixed(0)}만`}
          />
          <ComparisonRow
            label="바이럴"
            before={before.virals.total}
            after={after.virals.total}
            change={changes.virals_total}
            unit="건"
          />
          <ComparisonRow
            label="Top 10 키워드"
            before={before.top10_keywords}
            after={after.top10_keywords}
            change={changes.top10_keywords}
            unit="개"
          />
          {before.avg_rank && after.avg_rank && (
            <ComparisonRow
              label="평균 순위"
              before={before.avg_rank}
              after={after.avg_rank}
              change={changes.avg_rank}
              unit="위"
              inverse={true}
            />
          )}
        </div>
      </div>

      {/* 인사이트 */}
      {insights.length > 0 && (
        <div className="p-6">
          <h3 className="text-sm font-semibold text-muted-foreground mb-3">주요 변화</h3>
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

// 변화 아이콘
function ChangeIcon({ change }: { change: MetricChange }) {
  if (change.direction === 'up') {
    return <ChevronUp className="w-4 h-4 text-green-500" aria-hidden="true" />
  }
  if (change.direction === 'down') {
    return <ChevronDown className="w-4 h-4 text-red-500" aria-hidden="true" />
  }
  return <Minus className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
}

// 비교 행
function ComparisonRow({
  label,
  before,
  after,
  change,
  unit,
  formatValue,
  inverse = false,
}: {
  label: string
  before: number
  after: number
  change: MetricChange
  unit: string
  formatValue?: (v: number) => string
  inverse?: boolean
}) {
  const format = formatValue || ((v: number) => v.toLocaleString())

  // 역방향 (순위처럼 낮을수록 좋은 경우)
  const direction = inverse
    ? change.direction === 'up' ? 'down' : change.direction === 'down' ? 'up' : 'stable'
    : change.direction

  return (
    <div className="flex items-center gap-4">
      <div className="w-28 text-sm text-muted-foreground">{label}</div>
      <div className="flex-1 flex items-center gap-3">
        <div className="w-24 text-right text-sm">{format(before)}{unit}</div>
        <ArrowRight className="w-4 h-4 text-muted-foreground flex-shrink-0" aria-hidden="true" />
        <div className="w-24 text-sm font-medium">{format(after)}{unit}</div>
      </div>
      <div className={`flex items-center gap-1 text-sm ${
        direction === 'up' ? 'text-green-500' : direction === 'down' ? 'text-red-500' : 'text-muted-foreground'
      }`}>
        {direction === 'up' && <TrendingUp className="w-4 h-4" aria-hidden="true" />}
        {direction === 'down' && <TrendingDown className="w-4 h-4" aria-hidden="true" />}
        {direction === 'stable' && <Minus className="w-4 h-4" aria-hidden="true" />}
        {change.percent !== null ? (
          <span>{change.percent > 0 ? '+' : ''}{change.percent}%</span>
        ) : (
          <span>{change.value > 0 ? '+' : ''}{change.value}</span>
        )}
      </div>
    </div>
  )
}

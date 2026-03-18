/**
 * Viral Hunter 성과 대시보드
 * 전체 퍼널, 플랫폼별/카테고리별 성과, 추이 분석
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { viralApi, type PerformanceStats, type PerformanceComparison } from '@/services/api'
import {
  BarChart3, TrendingUp, TrendingDown, Target, CheckCircle,
  AlertCircle, RefreshCw, Calendar, Award, Minus
} from 'lucide-react'
import { IconButton } from '@/components/ui/Button'

interface PerformanceDashboardProps {
  compact?: boolean
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

export function PerformanceDashboard({ compact = false }: PerformanceDashboardProps) {
  const [days, setDays] = useState(30)

  const { data: stats, isLoading, isError, refetch, isFetching } = useQuery<PerformanceStats>({
    queryKey: ['performance-stats', days],
    queryFn: () => viralApi.getPerformanceStats(days),
    staleTime: 5 * 60 * 1000,
  })

  const { data: comparison } = useQuery<PerformanceComparison>({
    queryKey: ['performance-comparison'],
    queryFn: viralApi.getPerformanceComparison,
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 animate-pulse">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-6 h-6 bg-muted rounded" />
          <div className="h-6 bg-muted rounded w-40" />
        </div>
        <div className="grid grid-cols-4 gap-4 mb-6">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-24 bg-muted rounded" />
          ))}
        </div>
        <div className="h-48 bg-muted rounded" />
      </div>
    )
  }

  if (isError || !stats) {
    return (
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <AlertCircle className="w-5 h-5" />
          <span>성과 데이터를 불러올 수 없습니다.</span>
        </div>
      </div>
    )
  }

  const { funnel, rates, by_platform, by_category, daily_stats, insights } = stats

  // 컴팩트 모드
  if (compact) {
    return (
      <div className="bg-card border border-border rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-green-500" />
            <span className="font-semibold">성과 요약</span>
          </div>
          <IconButton
            icon={<RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />}
            onClick={() => refetch()}
            disabled={isFetching}
            size="sm"
            title="새로고침"
          />
        </div>

        {/* 핵심 지표 */}
        <div className="grid grid-cols-4 gap-2 mb-3">
          <div className="text-center p-2 bg-muted/50 rounded">
            <div className="text-lg font-bold">{funnel.scanned}</div>
            <div className="text-[10px] text-muted-foreground">스캔</div>
          </div>
          <div className="text-center p-2 bg-blue-500/10 rounded">
            <div className="text-lg font-bold text-blue-500">{funnel.generated}</div>
            <div className="text-[10px] text-muted-foreground">생성</div>
          </div>
          <div className="text-center p-2 bg-yellow-500/10 rounded">
            <div className="text-lg font-bold text-yellow-500">{funnel.approved}</div>
            <div className="text-[10px] text-muted-foreground">승인</div>
          </div>
          <div className="text-center p-2 bg-green-500/10 rounded">
            <div className="text-lg font-bold text-green-500">{funnel.posted}</div>
            <div className="text-[10px] text-muted-foreground">게시</div>
          </div>
        </div>

        {/* 전환율 */}
        <div className="text-center p-2 bg-gradient-to-r from-green-500/10 to-emerald-500/10 rounded">
          <span className="text-sm text-muted-foreground">전체 전환율: </span>
          <span className="text-lg font-bold text-green-500">{rates.overall_conversion}%</span>
        </div>
      </div>
    )
  }

  // 전체 모드
  const maxDailyScanned = Math.max(...daily_stats.map(d => d.scanned), 1)

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      {/* 헤더 */}
      <div className="bg-gradient-to-r from-green-500/10 to-emerald-500/10 border-b border-border p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-6 h-6 text-green-500" />
            <h3 className="text-lg font-semibold">성과 대시보드</h3>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="px-3 py-1 bg-background border border-border rounded text-sm"
            >
              <option value={7}>최근 7일</option>
              <option value={14}>최근 14일</option>
              <option value={30}>최근 30일</option>
              <option value={90}>최근 90일</option>
            </select>
            <IconButton
              icon={<RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />}
              onClick={() => refetch()}
              disabled={isFetching}
              title="새로고침"
            />
          </div>
        </div>
      </div>

      <div className="p-4 space-y-6">
        {/* 인사이트 */}
        {insights.length > 0 && (
          <div className="space-y-2">
            {insights.map((insight, idx) => (
              <div
                key={idx}
                className={`flex items-start gap-2 p-3 rounded-lg ${
                  insight.type === 'success' ? 'bg-green-500/10 border border-green-500/30' :
                  insight.type === 'warning' ? 'bg-yellow-500/10 border border-yellow-500/30' :
                  'bg-muted/50'
                }`}
              >
                {insight.type === 'success' ? (
                  <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                ) : insight.type === 'warning' ? (
                  <AlertCircle className="w-4 h-4 text-yellow-500 flex-shrink-0 mt-0.5" />
                ) : (
                  <Target className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                )}
                <span className="text-sm">{insight.message}</span>
              </div>
            ))}
          </div>
        )}

        {/* 퍼널 시각화 */}
        <div>
          <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Target className="w-4 h-4" />
            전환 퍼널
          </h4>
          <div className="space-y-2">
            <FunnelBar label="스캔" value={funnel.scanned} max={funnel.scanned} color="bg-gray-500" />
            <FunnelBar label="필터" value={funnel.filtered} max={funnel.scanned} color="bg-blue-400" rate={rates.filter_rate} />
            <FunnelBar label="생성" value={funnel.generated} max={funnel.scanned} color="bg-blue-500" rate={rates.generation_rate} />
            <FunnelBar label="승인" value={funnel.approved} max={funnel.scanned} color="bg-yellow-500" rate={rates.approval_rate} />
            <FunnelBar label="게시" value={funnel.posted} max={funnel.scanned} color="bg-green-500" rate={rates.posting_rate} />
          </div>
          <div className="mt-3 p-3 bg-muted/30 rounded-lg text-center">
            <span className="text-muted-foreground">전체 전환율: </span>
            <span className="text-2xl font-bold text-green-500">{rates.overall_conversion}%</span>
            <span className="text-muted-foreground ml-2">
              (스킵률: {rates.skip_rate}%)
            </span>
          </div>
        </div>

        {/* 기간별 비교 */}
        {comparison && (
          <div>
            <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <Calendar className="w-4 h-4" />
              기간별 비교
            </h4>
            <div className="grid grid-cols-2 gap-4">
              {/* 주간 비교 */}
              <div className="p-3 bg-muted/30 rounded-lg">
                <div className="text-xs text-muted-foreground mb-2">이번 주 vs 지난 주</div>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-lg font-bold">{comparison.weekly.this_week.posted}</div>
                    <div className="text-xs text-muted-foreground">게시</div>
                  </div>
                  <ChangeIndicator value={comparison.weekly.change.posted_pct} />
                </div>
              </div>
              {/* 월간 비교 */}
              <div className="p-3 bg-muted/30 rounded-lg">
                <div className="text-xs text-muted-foreground mb-2">이번 달 vs 지난 달</div>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-lg font-bold">{comparison.monthly.this_month.posted}</div>
                    <div className="text-xs text-muted-foreground">게시</div>
                  </div>
                  <ChangeIndicator value={comparison.monthly.change.posted_pct} />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 일별 추이 차트 */}
        {daily_stats.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              일별 추이
            </h4>
            <div className="flex items-end gap-1 h-32">
              {daily_stats.map((day, idx) => {
                const height = (day.scanned / maxDailyScanned) * 100
                const postedHeight = day.scanned > 0 ? (day.posted / day.scanned) * height : 0
                const date = new Date(day.date)
                const dayLabel = date.getDate().toString()

                return (
                  <div
                    key={idx}
                    className="flex-1 flex flex-col items-center gap-1"
                    title={`${day.date}: 스캔 ${day.scanned}, 게시 ${day.posted}`}
                  >
                    <div className="w-full relative" style={{ height: `${Math.max(height, 4)}%` }}>
                      <div
                        className="absolute bottom-0 w-full bg-gray-300 dark:bg-gray-600 rounded-t transition-all"
                        style={{ height: '100%' }}
                      />
                      <div
                        className="absolute bottom-0 w-full bg-green-500 rounded-t transition-all"
                        style={{ height: `${postedHeight}%` }}
                      />
                    </div>
                    <span className="text-[10px] text-muted-foreground">{dayLabel}</span>
                  </div>
                )
              })}
            </div>
            <div className="flex items-center justify-center gap-4 mt-2 text-xs text-muted-foreground">
              <div className="flex items-center gap-1">
                <div className="w-3 h-3 bg-gray-300 dark:bg-gray-600 rounded" />
                <span>스캔</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="w-3 h-3 bg-green-500 rounded" />
                <span>게시</span>
              </div>
            </div>
          </div>
        )}

        {/* 플랫폼별 성과 */}
        {by_platform.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-3">플랫폼별 성과</h4>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left p-2">플랫폼</th>
                    <th className="text-right p-2">스캔</th>
                    <th className="text-right p-2">생성</th>
                    <th className="text-right p-2">게시</th>
                    <th className="text-right p-2">전환율</th>
                  </tr>
                </thead>
                <tbody>
                  {by_platform.map((p, idx) => (
                    <tr key={idx} className="border-b border-border/50">
                      <td className="p-2 font-medium">
                        {platformLabels[p.platform] || p.platform}
                      </td>
                      <td className="text-right p-2 text-muted-foreground">{p.total}</td>
                      <td className="text-right p-2 text-blue-500">{p.generated}</td>
                      <td className="text-right p-2 text-green-500 font-semibold">{p.posted}</td>
                      <td className="text-right p-2">
                        <span className={`px-2 py-0.5 rounded text-xs ${
                          p.posting_rate >= 5 ? 'bg-green-500/20 text-green-500' :
                          p.posting_rate >= 2 ? 'bg-yellow-500/20 text-yellow-500' :
                          'bg-gray-500/20 text-gray-500'
                        }`}>
                          {p.posting_rate}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 카테고리별 성과 */}
        {by_category.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-3">카테고리별 성과</h4>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
              {by_category.slice(0, 5).map((cat, idx) => (
                <div
                  key={idx}
                  className={`p-3 rounded-lg text-center ${
                    idx === 0 ? 'bg-green-500/10 border border-green-500/30' : 'bg-muted/30'
                  }`}
                >
                  <div className="text-sm font-medium truncate">{cat.category}</div>
                  <div className="text-lg font-bold text-green-500">{cat.posted}</div>
                  <div className="text-xs text-muted-foreground">
                    {cat.total}개 중 ({cat.posting_rate}%)
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 베스트 성과 */}
        {stats.top_performers.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <Award className="w-4 h-4 text-yellow-500" />
              베스트 성과 타겟
            </h4>
            <div className="space-y-2">
              {stats.top_performers.slice(0, 5).map((target, idx) => (
                <div
                  key={idx}
                  className="flex items-start gap-3 p-3 bg-muted/30 rounded-lg"
                >
                  <span className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                    idx === 0 ? 'bg-yellow-500 text-white' :
                    idx === 1 ? 'bg-gray-400 text-white' :
                    idx === 2 ? 'bg-orange-600 text-white' :
                    'bg-muted text-muted-foreground'
                  }`}>
                    {idx + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{target.title}</div>
                    <div className="text-xs text-muted-foreground">
                      {platformLabels[target.platform] || target.platform} · {target.category} · {target.priority_score}점
                    </div>
                    {target.comment_preview && (
                      <div className="text-xs text-muted-foreground mt-1 line-clamp-1">
                        "{target.comment_preview}"
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// 퍼널 바 컴포넌트
function FunnelBar({
  label,
  value,
  max,
  color,
  rate
}: {
  label: string
  value: number
  max: number
  color: string
  rate?: number
}) {
  const width = max > 0 ? (value / max) * 100 : 0

  return (
    <div className="flex items-center gap-3">
      <div className="w-12 text-xs text-muted-foreground">{label}</div>
      <div className="flex-1 h-6 bg-muted rounded-full overflow-hidden">
        <div
          className={`h-full ${color} transition-all duration-500`}
          style={{ width: `${width}%` }}
        />
      </div>
      <div className="w-16 text-right text-sm font-medium">{value}</div>
      {rate !== undefined && (
        <div className="w-12 text-right text-xs text-muted-foreground">{rate}%</div>
      )}
    </div>
  )
}

// 변화율 표시 컴포넌트
function ChangeIndicator({ value }: { value: number }) {
  if (value === 0) {
    return (
      <div className="flex items-center gap-1 text-gray-500">
        <Minus className="w-4 h-4" />
        <span className="text-sm">0%</span>
      </div>
    )
  }

  const isPositive = value > 0

  return (
    <div className={`flex items-center gap-1 ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
      {isPositive ? (
        <TrendingUp className="w-4 h-4" />
      ) : (
        <TrendingDown className="w-4 h-4" />
      )}
      <span className="text-sm font-medium">
        {isPositive ? '+' : ''}{value}%
      </span>
    </div>
  )
}

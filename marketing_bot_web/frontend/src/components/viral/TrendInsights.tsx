/**
 * 트렌드 인사이트 컴포넌트
 * 키워드/플랫폼 트렌드 시각화
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { viralApi, type TrendInsights as TrendInsightsType } from '@/services/api'
import {
  TrendingUp, TrendingDown, BarChart3, Sparkles, RefreshCw,
  AlertCircle, Calendar
} from 'lucide-react'
import { IconButton } from '@/components/ui/Button'

interface TrendInsightsProps {
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

export function TrendInsights({ compact = false }: TrendInsightsProps) {
  const [days, setDays] = useState(7)

  const { data, isLoading, isError, refetch, isFetching } = useQuery<TrendInsightsType>({
    queryKey: ['trend-insights', days],
    queryFn: () => viralApi.getTrendInsights(days),
    staleTime: 5 * 60 * 1000, // 5분
  })

  if (isLoading) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 animate-pulse">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-6 h-6 bg-muted rounded" />
          <div className="h-6 bg-muted rounded w-32" />
        </div>
        <div className="space-y-3">
          <div className="h-32 bg-muted rounded" />
          <div className="h-24 bg-muted rounded" />
        </div>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <AlertCircle className="w-5 h-5" />
          <span>트렌드 데이터를 불러올 수 없습니다.</span>
        </div>
      </div>
    )
  }

  // 컴팩트 모드
  if (compact) {
    return (
      <div className="bg-card border border-border rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-blue-500" />
            <span className="font-semibold">트렌드 인사이트</span>
          </div>
          <IconButton
            icon={<RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />}
            onClick={() => refetch()}
            disabled={isFetching}
            size="sm"
            title="새로고침"
          />
        </div>

        {/* 급상승 키워드 */}
        {data.keyword_trends.rising.length > 0 && (
          <div className="mb-3">
            <h4 className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1">
              <TrendingUp className="w-3 h-3 text-green-500" />
              급상승 키워드
            </h4>
            <div className="flex flex-wrap gap-1">
              {data.keyword_trends.rising.slice(0, 3).map((kw, idx) => (
                <span
                  key={idx}
                  className="px-2 py-0.5 bg-green-500/10 text-green-500 rounded text-xs"
                >
                  {kw.keyword} {kw.change === 'new' ? '🆕' : `+${kw.change_rate}%`}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* 인사이트 */}
        {data.insights.length > 0 && (
          <div className="text-xs text-muted-foreground">
            {data.insights[0].message}
          </div>
        )}
      </div>
    )
  }

  // 전체 모드
  const maxDailyCount = data.daily_trends?.length
    ? Math.max(...data.daily_trends.map(d => d.count), 1)
    : 1

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      {/* 헤더 */}
      <div className="bg-gradient-to-r from-blue-500/10 to-cyan-500/10 border-b border-border p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-6 h-6 text-blue-500" />
            <h3 className="text-lg font-semibold">트렌드 인사이트</h3>
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

      <div className="p-4 space-y-5">
        {/* 인사이트 */}
        {data.insights.length > 0 && (
          <div className="space-y-2">
            {data.insights.map((insight, idx) => (
              <div
                key={idx}
                className={`flex items-start gap-2 p-3 rounded-lg ${
                  insight.importance === 'high'
                    ? 'bg-blue-500/10 border border-blue-500/30'
                    : 'bg-muted/50'
                }`}
              >
                <Sparkles className={`w-4 h-4 flex-shrink-0 mt-0.5 ${
                  insight.importance === 'high' ? 'text-blue-500' : 'text-muted-foreground'
                }`} />
                <span className="text-sm">{insight.message}</span>
              </div>
            ))}
          </div>
        )}

        {/* 일별 추이 차트 */}
        {data.daily_trends.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <Calendar className="w-4 h-4" />
              일별 타겟 발견 추이
            </h4>
            <div className="flex items-end gap-1 h-24">
              {data.daily_trends.map((day, idx) => {
                const height = (day.count / maxDailyCount) * 100
                const date = new Date(day.date)
                const dayLabel = date.toLocaleDateString('ko-KR', { weekday: 'short' })

                return (
                  <div
                    key={idx}
                    className="flex-1 flex flex-col items-center gap-1"
                    title={`${day.date}: ${day.count}개 (평균 ${day.avg_score}점)`}
                  >
                    <div
                      className="w-full bg-blue-500 rounded-t transition-all hover:bg-blue-400"
                      style={{ height: `${Math.max(height, 4)}%` }}
                    />
                    <span className="text-[10px] text-muted-foreground">{dayLabel}</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* 급상승/하락 키워드 */}
        <div className="grid grid-cols-2 gap-4">
          {/* 급상승 */}
          <div>
            <h4 className="text-sm font-semibold mb-3 flex items-center gap-2 text-green-500">
              <TrendingUp className="w-4 h-4" />
              급상승 키워드
            </h4>
            {data.keyword_trends.rising.length > 0 ? (
              <div className="space-y-1">
                {data.keyword_trends.rising.slice(0, 5).map((kw, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2 bg-green-500/5 rounded"
                  >
                    <span className="text-sm">{kw.keyword}</span>
                    <span className="text-xs text-green-500 font-medium">
                      {kw.change === 'new' ? '🆕 신규' : `+${kw.change_rate}%`}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-muted-foreground p-2">
                급상승 키워드 없음
              </div>
            )}
          </div>

          {/* 하락 */}
          <div>
            <h4 className="text-sm font-semibold mb-3 flex items-center gap-2 text-red-500">
              <TrendingDown className="w-4 h-4" />
              하락 키워드
            </h4>
            {data.keyword_trends.falling.length > 0 ? (
              <div className="space-y-1">
                {data.keyword_trends.falling.slice(0, 5).map((kw, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2 bg-red-500/5 rounded"
                  >
                    <span className="text-sm">{kw.keyword}</span>
                    <span className="text-xs text-red-500 font-medium">
                      {kw.change_rate}%
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-muted-foreground p-2">
                하락 키워드 없음
              </div>
            )}
          </div>
        </div>

        {/* 플랫폼별 현황 */}
        {data.platform_trends.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-3">플랫폼별 활동</h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {data.platform_trends
                .sort((a, b) => b.total - a.total)
                .slice(0, 8)
                .map((p) => (
                  <div
                    key={p.platform}
                    className="p-3 bg-muted/30 rounded-lg text-center"
                  >
                    <div className="text-lg font-bold">{p.total}</div>
                    <div className="text-xs text-muted-foreground">
                      {platformLabels[p.platform] || p.platform}
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* 카테고리 트렌드 */}
        {data.category_trends.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-3">인기 카테고리</h4>
            <div className="flex flex-wrap gap-2">
              {data.category_trends.slice(0, 6).map((cat, idx) => (
                <span
                  key={idx}
                  className={`px-3 py-1 rounded-full text-sm ${
                    idx === 0
                      ? 'bg-blue-500 text-white'
                      : 'bg-muted text-foreground'
                  }`}
                >
                  {cat.category} ({cat.count})
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * 골든타임 분석 대시보드 컴포넌트
 */

import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { marketingApi } from '@/services/api'
import { Clock, TrendingUp, Calendar, RefreshCw } from 'lucide-react'
import Button, { IconButton } from '@/components/ui/Button'
import type { GoldenTimeStats } from '@/types/marketing'

interface GoldenTimeDashboardProps {
  days?: number
  compact?: boolean
}

const DAY_LABELS = ['일', '월', '화', '수', '목', '금', '토']

const PLATFORM_OPTIONS = [
  { value: '', label: '전체 플랫폼' },
  { value: 'cafe', label: '카페' },
  { value: 'blog', label: '블로그' },
  { value: 'kin', label: '지식인' },
  { value: 'youtube', label: 'YouTube' },
  { value: 'instagram', label: '인스타' },
]

export function GoldenTimeDashboard({ days = 30, compact = false }: GoldenTimeDashboardProps) {
  const [platform, setPlatform] = useState('')

  const { data, isLoading, error, refetch, isRefetching } = useQuery<GoldenTimeStats>({
    queryKey: ['golden-time-stats', platform, days],
    queryFn: () => marketingApi.getGoldenTimeStats({ platform: platform || undefined, days }),
    staleTime: 5 * 60 * 1000,
  })

  // 히트맵 색상 계산
  const getHeatmapColor = (engagement: number, maxEngagement: number) => {
    if (maxEngagement === 0) return 'bg-muted'
    const intensity = engagement / maxEngagement
    if (intensity > 0.8) return 'bg-green-500'
    if (intensity > 0.6) return 'bg-green-400'
    if (intensity > 0.4) return 'bg-yellow-400'
    if (intensity > 0.2) return 'bg-yellow-300'
    if (intensity > 0) return 'bg-gray-300'
    return 'bg-muted'
  }

  // 최대 engagement 계산
  const maxEngagement = useMemo(() => {
    if (!data?.heatmap) return 0
    return Math.max(...data.heatmap.map(h => h.avg_engagement), 1)
  }, [data])

  if (isLoading) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 animate-pulse">
        <div className="h-6 bg-muted rounded w-1/3 mb-4" />
        <div className="h-48 bg-muted rounded" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 text-center">
        <p className="text-muted-foreground">골든타임 데이터를 불러올 수 없습니다.</p>
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

  const { hourly_stats, recommendations, heatmap } = data

  // 컴팩트 모드
  if (compact) {
    const bestHour = recommendations.best_hours[0]
    const bestDay = recommendations.best_days[0]

    return (
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Clock className="w-5 h-5 text-blue-500" />
          골든타임
        </h3>

        <div className="grid grid-cols-2 gap-4">
          <div className="p-3 bg-blue-500/10 rounded-lg text-center">
            <div className="text-2xl font-bold text-blue-400">
              {bestHour ? `${bestHour.hour}시` : '-'}
            </div>
            <div className="text-xs text-muted-foreground">최적 시간</div>
          </div>
          <div className="p-3 bg-green-500/10 rounded-lg text-center">
            <div className="text-2xl font-bold text-green-400">
              {bestDay ? bestDay.day_name : '-'}요일
            </div>
            <div className="text-xs text-muted-foreground">최적 요일</div>
          </div>
        </div>
      </div>
    )
  }

  // 전체 모드
  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <Clock className="w-6 h-6 text-blue-500" />
          골든타임 분석
        </h2>
        <div className="flex items-center gap-4">
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            className="px-3 py-2 bg-muted border border-border rounded-lg text-sm"
          >
            {PLATFORM_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <IconButton
            icon={<RefreshCw className={`w-4 h-4 ${isRefetching ? 'animate-spin' : ''}`} />}
            onClick={() => refetch()}
            disabled={isRefetching}
            title="새로고침"
          />
        </div>
      </div>

      {/* 최적 시간 권장 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-green-500" />
            최적 게시 시간
          </h3>
          <div className="space-y-3">
            {recommendations.best_hours.map((h, idx) => (
              <div key={idx} className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                <div className="flex items-center gap-3">
                  <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                    idx === 0 ? 'bg-yellow-500 text-black' :
                    idx === 1 ? 'bg-gray-400 text-black' :
                    'bg-orange-700 text-white'
                  }`}>
                    {idx + 1}
                  </span>
                  <span className="font-bold text-xl">{h.hour}:00</span>
                </div>
                <div className="text-sm text-muted-foreground">
                  반응률 {(h.engagement_rate * 100).toFixed(1)}%
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-card border border-border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Calendar className="w-5 h-5 text-purple-500" />
            최적 요일
          </h3>
          <div className="space-y-3">
            {recommendations.best_days.map((d, idx) => (
              <div key={idx} className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                <div className="flex items-center gap-3">
                  <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                    idx === 0 ? 'bg-yellow-500 text-black' :
                    idx === 1 ? 'bg-gray-400 text-black' :
                    'bg-orange-700 text-white'
                  }`}>
                    {idx + 1}
                  </span>
                  <span className="font-bold text-xl">{d.day_name}요일</span>
                </div>
                <div className="text-sm text-muted-foreground">
                  반응률 {(d.engagement_rate * 100).toFixed(1)}%
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 히트맵 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">시간대별 반응률 히트맵</h3>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className="p-2 text-left text-sm font-medium text-muted-foreground">시간</th>
                {DAY_LABELS.map((day, idx) => (
                  <th key={idx} className="p-2 text-center text-sm font-medium text-muted-foreground">
                    {day}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 24 }, (_, hour) => (
                <tr key={hour}>
                  <td className="p-1 text-sm text-muted-foreground">{hour}:00</td>
                  {Array.from({ length: 7 }, (_, day) => {
                    const cell = heatmap.find(
                      h => h.hour === hour && h.day_of_week === day
                    )
                    const engagement = cell?.avg_engagement || 0

                    return (
                      <td key={day} className="p-1">
                        <div
                          className={`w-full h-6 rounded ${getHeatmapColor(engagement, maxEngagement)}`}
                          title={`${DAY_LABELS[day]} ${hour}시: 반응 ${engagement.toFixed(1)}`}
                        />
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* 범례 */}
        <div className="flex items-center justify-center gap-4 mt-4 text-xs">
          <span className="text-muted-foreground">낮음</span>
          <div className="flex gap-1">
            <div className="w-4 h-4 bg-muted rounded" />
            <div className="w-4 h-4 bg-gray-300 rounded" />
            <div className="w-4 h-4 bg-yellow-300 rounded" />
            <div className="w-4 h-4 bg-yellow-400 rounded" />
            <div className="w-4 h-4 bg-green-400 rounded" />
            <div className="w-4 h-4 bg-green-500 rounded" />
          </div>
          <span className="text-muted-foreground">높음</span>
        </div>
      </div>

      {/* 시간대별 통계 바 차트 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">시간대별 반응 분포</h3>
        <div className="h-40 flex items-end justify-between gap-1">
          {hourly_stats.map((stat) => {
            const maxEng = Math.max(...hourly_stats.map(s => s.engagement), 1)
            const height = (stat.engagement / maxEng) * 100

            return (
              <div
                key={stat.hour}
                className="flex-1 flex flex-col items-center"
              >
                <div
                  className="w-full bg-blue-500 rounded-t transition-all hover:bg-blue-400"
                  style={{ height: `${height}%`, minHeight: stat.engagement > 0 ? '4px' : '0' }}
                  title={`${stat.hour}시: 반응 ${stat.engagement}`}
                />
                <span className="text-xs text-muted-foreground mt-1">
                  {stat.hour}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

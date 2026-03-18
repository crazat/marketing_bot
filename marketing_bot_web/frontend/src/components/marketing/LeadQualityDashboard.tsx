/**
 * 리드 품질 스코어링 대시보드
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { marketingApi } from '@/services/api'
import { Award, TrendingUp, Users, Target, RefreshCw } from 'lucide-react'
import Button, { IconButton } from '@/components/ui/Button'
import type { LeadQualityStats } from '@/types/marketing'

interface LeadQualityDashboardProps {
  days?: number
  compact?: boolean
}

const DIMENSION_OPTIONS = [
  { value: 'platform', label: '플랫폼별' },
  { value: 'category', label: '카테고리별' },
  { value: 'content_type', label: '콘텐츠 유형별' },
]

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

export function LeadQualityDashboard({ days = 30, compact = false }: LeadQualityDashboardProps) {
  const [dimension, setDimension] = useState<'platform' | 'category' | 'content_type'>('platform')

  const { data, isLoading, error, refetch, isRefetching } = useQuery<LeadQualityStats>({
    queryKey: ['lead-quality-stats', dimension, days],
    queryFn: () => marketingApi.getLeadQualityStats({ dimension, days }),
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 animate-pulse">
        <div className="h-6 bg-muted rounded w-1/3 mb-4" />
        <div className="space-y-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-16 bg-muted rounded" />
          ))}
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 text-center">
        <p className="text-muted-foreground">리드 품질 데이터를 불러올 수 없습니다.</p>
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

  const { stats, summary } = data
  const bestPerforming = summary.best_performing

  // 컴팩트 모드
  if (compact) {
    return (
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Award className="w-5 h-5 text-yellow-500" />
          리드 품질
        </h3>

        {bestPerforming && (
          <div className="p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
            <div className="text-sm text-muted-foreground mb-1">최고 성과</div>
            <div className="text-xl font-bold">
              {dimension === 'platform'
                ? PLATFORM_LABELS[bestPerforming.value] || bestPerforming.value
                : bestPerforming.value}
            </div>
            <div className="text-sm text-green-500 mt-1">
              전환율 {bestPerforming.conversion_rate}%
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-2 mt-4 text-sm">
          <div className="text-center p-2 bg-muted/50 rounded-lg">
            <div className="font-bold">{summary.total_leads}</div>
            <div className="text-xs text-muted-foreground">총 리드</div>
          </div>
          <div className="text-center p-2 bg-muted/50 rounded-lg">
            <div className="font-bold">{summary.total_conversions}</div>
            <div className="text-xs text-muted-foreground">전환</div>
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
          <Award className="w-6 h-6 text-yellow-500" />
          리드 품질 스코어링
        </h2>
        <div className="flex items-center gap-4">
          <select
            value={dimension}
            onChange={(e) => setDimension(e.target.value as any)}
            className="px-3 py-2 bg-muted border border-border rounded-lg text-sm"
          >
            {DIMENSION_OPTIONS.map(opt => (
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

      {/* 요약 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <Target className="w-8 h-8 mx-auto mb-2 text-blue-500" />
          <div className="text-3xl font-bold">{summary.total_targets.toLocaleString()}</div>
          <div className="text-sm text-muted-foreground">총 타겟</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <TrendingUp className="w-8 h-8 mx-auto mb-2 text-purple-500" />
          <div className="text-3xl font-bold">{summary.total_comments}</div>
          <div className="text-sm text-muted-foreground">댓글</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <Users className="w-8 h-8 mx-auto mb-2 text-green-500" />
          <div className="text-3xl font-bold">{summary.total_leads}</div>
          <div className="text-sm text-muted-foreground">리드</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <Award className="w-8 h-8 mx-auto mb-2 text-yellow-500" />
          <div className="text-3xl font-bold">{summary.total_conversions}</div>
          <div className="text-sm text-muted-foreground">전환</div>
        </div>
      </div>

      {/* 상세 통계 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">
          {DIMENSION_OPTIONS.find(d => d.value === dimension)?.label} 리드 품질
        </h3>

        <div className="space-y-4">
          {stats.map((stat, idx) => {
            const displayValue = dimension === 'platform'
              ? PLATFORM_LABELS[stat.value] || stat.value
              : stat.value

            return (
              <div key={idx} className="border border-border rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                      idx === 0 ? 'bg-yellow-500 text-black' :
                      idx === 1 ? 'bg-gray-400 text-black' :
                      idx === 2 ? 'bg-orange-700 text-white' :
                      'bg-muted text-muted-foreground'
                    }`}>
                      {idx + 1}
                    </span>
                    <span className="font-semibold text-lg">{displayValue}</span>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-green-500">
                      {stat.quality_score.toFixed(1)}
                    </div>
                    <div className="text-xs text-muted-foreground">품질 점수</div>
                  </div>
                </div>

                {/* 품질 점수 바 */}
                <div className="h-2 bg-muted rounded-full overflow-hidden mb-3">
                  <div
                    className={`h-full transition-all ${
                      stat.quality_score >= 30 ? 'bg-green-500' :
                      stat.quality_score >= 20 ? 'bg-yellow-500' :
                      stat.quality_score >= 10 ? 'bg-orange-500' :
                      'bg-red-500'
                    }`}
                    style={{ width: `${Math.min(stat.quality_score, 100)}%` }}
                  />
                </div>

                {/* 세부 지표 */}
                <div className="grid grid-cols-4 gap-4 text-center text-sm">
                  <div>
                    <div className="font-medium">{stat.total_targets}</div>
                    <div className="text-xs text-muted-foreground">타겟</div>
                  </div>
                  <div>
                    <div className="font-medium">{stat.total_comments}</div>
                    <div className="text-xs text-muted-foreground">댓글</div>
                  </div>
                  <div>
                    <div className="font-medium">{stat.total_leads}</div>
                    <div className="text-xs text-muted-foreground">리드</div>
                  </div>
                  <div>
                    <div className="font-medium text-green-500">{stat.conversion_rate}%</div>
                    <div className="text-xs text-muted-foreground">전환율</div>
                  </div>
                </div>

                {/* 전환 퍼널 */}
                <div className="flex items-center gap-2 mt-3 text-xs text-muted-foreground">
                  <span>댓글율 {stat.comment_rate}%</span>
                  <span>→</span>
                  <span>리드율 {stat.lead_rate}%</span>
                  <span>→</span>
                  <span className="text-green-500">전환율 {stat.conversion_rate}%</span>
                </div>
              </div>
            )
          })}
        </div>

        {stats.length === 0 && (
          <div className="text-center py-8 text-muted-foreground">
            데이터가 없습니다. 더 많은 타겟을 처리해보세요.
          </div>
        )}
      </div>

      {/* 인사이트 */}
      {bestPerforming && (
        <div className="bg-gradient-to-r from-yellow-500/20 to-green-500/20 border border-yellow-500/30 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-2 flex items-center gap-2">
            <Award className="w-5 h-5 text-yellow-500" />
            AI 인사이트
          </h3>
          <p className="text-muted-foreground">
            <span className="text-foreground font-medium">
              {dimension === 'platform'
                ? PLATFORM_LABELS[bestPerforming.value] || bestPerforming.value
                : bestPerforming.value}
            </span>
            에서 가장 높은 품질 점수({bestPerforming.quality_score.toFixed(1)})를 기록했습니다.
            전환율 {bestPerforming.conversion_rate}%로 리소스를 집중 투입할 것을 권장합니다.
          </p>
        </div>
      )}
    </div>
  )
}

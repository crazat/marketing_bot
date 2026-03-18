/**
 * [Phase F-2] 리드 소스 어트리뷰션
 * 리드가 어디서 왔는지 추적하고 시각화
 */

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Target,
  MessageSquare,
  TrendingUp,
  Link2,
  ExternalLink,
  Loader2,
  BarChart3,
} from 'lucide-react'
import { pathfinderApi, battleApi, viralApi } from '@/services/api'
import Button from '@/components/ui/Button'

interface LeadAttributionProps {
  /** 리드의 소스 키워드 */
  sourceKeyword?: string
  /** 리드 플랫폼 */
  platform?: string
  /** 컴팩트 모드 */
  compact?: boolean
}

export default function LeadAttribution({
  sourceKeyword,
  platform,
  compact = false,
}: LeadAttributionProps) {
  const navigate = useNavigate()

  // 키워드 인사이트 조회
  const { data: keywordInsight, isLoading: keywordLoading } = useQuery({
    queryKey: ['attribution-keyword', sourceKeyword],
    queryFn: async () => {
      if (!sourceKeyword) return null
      const data = await pathfinderApi.getKeywords({ limit: 500 })
      const keywords = data?.keywords || []
      return keywords.find((k: any) =>
        k.keyword.toLowerCase() === sourceKeyword.toLowerCase()
      )
    },
    enabled: !!sourceKeyword,
    staleTime: 60000,
  })

  // 순위 정보 조회
  const { data: rankInfo, isLoading: rankLoading } = useQuery({
    queryKey: ['attribution-rank', sourceKeyword],
    queryFn: async () => {
      if (!sourceKeyword) return null
      const keywords = await battleApi.getRankingKeywords()
      return (keywords || []).find((k: any) =>
        k.keyword.toLowerCase() === sourceKeyword.toLowerCase()
      )
    },
    enabled: !!sourceKeyword,
    staleTime: 60000,
  })

  // 관련 바이럴 조회
  const { data: viralData, isLoading: viralLoading } = useQuery({
    queryKey: ['attribution-viral', sourceKeyword],
    queryFn: async () => {
      if (!sourceKeyword) return { count: 0, items: [] }
      const data = await viralApi.getTargets('', undefined, 50, { search: sourceKeyword })
      const targets = data?.targets || []
      const filtered = targets.filter((t: any) =>
        t.matched_keyword?.toLowerCase().includes(sourceKeyword.toLowerCase())
      )
      return {
        count: filtered.length,
        completed: filtered.filter((t: any) => t.status === 'completed').length,
        items: filtered.slice(0, 3),
      }
    },
    enabled: !!sourceKeyword,
    staleTime: 60000,
  })

  const isLoading = keywordLoading || rankLoading || viralLoading

  if (!sourceKeyword) {
    return (
      <div className="text-sm text-muted-foreground">
        소스 키워드 정보 없음
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="w-4 h-4 animate-spin" />
        어트리뷰션 분석 중...
      </div>
    )
  }

  // 컴팩트 모드
  if (compact) {
    return (
      <div className="flex items-center gap-2 text-xs">
        <Link2 className="w-3 h-3 text-muted-foreground" />
        <span className="text-muted-foreground">소스:</span>
        <Button
          variant="ghost"
          size="xs"
          onClick={() => navigate(`/pathfinder?keyword=${encodeURIComponent(sourceKeyword)}`)}
          className="text-primary font-medium p-0 h-auto"
        >
          {sourceKeyword}
        </Button>
        {keywordInsight?.grade && (
          <span className={`px-1 py-0.5 rounded text-[10px] ${
            keywordInsight.grade === 'S' ? 'bg-red-500/20 text-red-500' :
            keywordInsight.grade === 'A' ? 'bg-green-500/20 text-green-500' :
            'bg-muted text-muted-foreground'
          }`}>
            {keywordInsight.grade}급
          </span>
        )}
        {rankInfo && (
          <span className="text-muted-foreground">
            · {rankInfo.current_rank}위
          </span>
        )}
      </div>
    )
  }

  // 전체 모드
  return (
    <div className="bg-muted/30 rounded-lg p-4 space-y-3">
      <h4 className="text-sm font-medium flex items-center gap-2">
        <Link2 className="w-4 h-4 text-primary" />
        리드 소스 어트리뷰션
      </h4>

      {/* 소스 키워드 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Target className="w-4 h-4 text-blue-500" />
          <span className="text-sm text-muted-foreground">소스 키워드</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate(`/pathfinder?keyword=${encodeURIComponent(sourceKeyword)}`)}
          icon={<ExternalLink className="w-3 h-3" />}
          iconPosition="right"
          className="text-primary font-medium"
        >
          {sourceKeyword}
        </Button>
      </div>

      {/* 키워드 등급 */}
      {keywordInsight && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">키워드 등급</span>
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
            keywordInsight.grade === 'S' ? 'bg-red-500/20 text-red-500' :
            keywordInsight.grade === 'A' ? 'bg-green-500/20 text-green-500' :
            keywordInsight.grade === 'B' ? 'bg-blue-500/20 text-blue-500' :
            'bg-muted text-muted-foreground'
          }`}>
            {keywordInsight.grade}급 · 검색량 {keywordInsight.search_volume?.toLocaleString() || '-'}
          </span>
        </div>
      )}

      {/* 현재 순위 */}
      {rankInfo && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-purple-500" />
            <span className="text-sm text-muted-foreground">현재 순위</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">{rankInfo.current_rank}위</span>
            {rankInfo.rank_change !== 0 && (
              <span className={`text-xs ${
                rankInfo.rank_change > 0 ? 'text-green-500' : 'text-red-500'
              }`}>
                {rankInfo.rank_change > 0 ? '▲' : '▼'}{Math.abs(rankInfo.rank_change)}
              </span>
            )}
          </div>
        </div>
      )}

      {/* 관련 바이럴 */}
      {viralData && viralData.count > 0 && (
        <div className="pt-2 border-t border-border">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-orange-500" />
              <span className="text-sm text-muted-foreground">관련 바이럴</span>
            </div>
            <span className="text-sm">
              {viralData.completed}/{viralData.count}건 완료
            </span>
          </div>
          {viralData.items.length > 0 && (
            <div className="space-y-1">
              {viralData.items.map((v: any) => (
                <div key={v.id} className="text-xs text-muted-foreground truncate">
                  · {v.platform}: {v.title?.slice(0, 30)}...
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 플랫폼 정보 */}
      {platform && (
        <div className="flex items-center justify-between pt-2 border-t border-border">
          <span className="text-sm text-muted-foreground">발견 플랫폼</span>
          <span className="text-sm font-medium">{platform}</span>
        </div>
      )}
    </div>
  )
}

// 리드 목록용 어트리뷰션 통계 컴포넌트
export function LeadAttributionStats({
  leads,
}: {
  leads: any[]
}) {
  const navigate = useNavigate()

  // 소스 키워드별 통계
  const stats = useMemo(() => {
    const keywordMap = new Map<string, { total: number; hot: number; warm: number; cold: number }>()

    leads.forEach((lead) => {
      const keyword = lead.source_keyword || '(알 수 없음)'
      const current = keywordMap.get(keyword) || { total: 0, hot: 0, warm: 0, cold: 0 }

      current.total++
      if (lead.grade === 'hot') current.hot++
      else if (lead.grade === 'warm') current.warm++
      else current.cold++

      keywordMap.set(keyword, current)
    })

    return Array.from(keywordMap.entries())
      .map(([keyword, data]) => ({ keyword, ...data }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 10)
  }, [leads])

  if (stats.length === 0) {
    return null
  }

  return (
    <div className="bg-card rounded-lg border border-border p-4">
      <h3 className="font-semibold mb-4 flex items-center gap-2">
        <BarChart3 className="w-5 h-5 text-primary" />
        소스 키워드별 리드
      </h3>

      <div className="space-y-2">
        {stats.map(({ keyword, total, hot, warm, cold }) => (
          <div key={keyword} className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                if (keyword !== '(알 수 없음)') {
                  navigate(`/leads?keyword=${encodeURIComponent(keyword)}`)
                }
              }}
              disabled={keyword === '(알 수 없음)'}
              className={`flex-1 text-sm truncate text-left justify-start p-0 h-auto ${
                keyword !== '(알 수 없음)'
                  ? 'text-primary hover:underline'
                  : 'text-muted-foreground'
              }`}
            >
              {keyword}
            </Button>

            {/* 등급별 바 */}
            <div className="flex items-center gap-1 w-32">
              {hot > 0 && (
                <div
                  className="h-4 bg-red-500 rounded-l"
                  style={{ width: `${(hot / total) * 100}%` }}
                  title={`Hot ${hot}`}
                />
              )}
              {warm > 0 && (
                <div
                  className="h-4 bg-yellow-500"
                  style={{ width: `${(warm / total) * 100}%` }}
                  title={`Warm ${warm}`}
                />
              )}
              {cold > 0 && (
                <div
                  className="h-4 bg-blue-500 rounded-r"
                  style={{ width: `${(cold / total) * 100}%` }}
                  title={`Cold ${cold}`}
                />
              )}
            </div>

            <span className="text-sm font-medium w-8 text-right">{total}</span>
          </div>
        ))}
      </div>

      {/* 범례 */}
      <div className="flex items-center gap-4 mt-4 pt-3 border-t border-border text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <div className="w-3 h-3 bg-red-500 rounded" /> Hot
        </span>
        <span className="flex items-center gap-1">
          <div className="w-3 h-3 bg-yellow-500 rounded" /> Warm
        </span>
        <span className="flex items-center gap-1">
          <div className="w-3 h-3 bg-blue-500 rounded" /> Cold
        </span>
      </div>
    </div>
  )
}

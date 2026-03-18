import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { hudApi } from '@/services/api'
import Button from '@/components/ui/Button'

interface RankAlertsData {
  critical_drops: Array<{
    keyword: string
    current_rank: number
    previous_rank: number
    rank_change: number
    severity: string
  }>
  warnings: Array<{
    keyword: string
    current_rank: number
    previous_rank: number
    rank_change: number
    severity: string
  }>
  recommendations: Array<{
    priority: string
    message: string
    action: string
    keywords?: string[]
  }>
  summary: {
    total_critical: number
    total_warnings: number
  }
}

export default function RankAlerts() {
  const navigate = useNavigate()

  const { data, isLoading } = useQuery<RankAlertsData>({
    queryKey: ['rank-alerts'],
    queryFn: hudApi.getRankAlerts,
    refetchInterval: 300000,  // 5분마다 갱신
    retry: 1,
  })

  if (isLoading) {
    return null
  }

  if (!data?.summary || (data.summary.total_critical === 0 && data.summary.total_warnings === 0)) {
    return null
  }

  const hasCritical = data.summary.total_critical > 0

  return (
    <div className={`rounded-lg p-4 mb-6 border ${
      hasCritical
        ? 'bg-red-500/10 border-red-500/30'
        : 'bg-yellow-500/10 border-yellow-500/30'
    }`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className={`font-semibold flex items-center gap-2 ${
          hasCritical ? 'text-red-600' : 'text-yellow-600'
        }`}>
          <span className="text-xl">{hasCritical ? '🚨' : '⚠️'}</span>
          순위 변동 알림
        </h3>
        <Button
          variant="ghost"
          size="xs"
          onClick={() => navigate('/battle')}
          className={hasCritical ? 'text-red-600 hover:text-red-700' : 'text-yellow-600 hover:text-yellow-700'}
        >
          순위 현황 →
        </Button>
      </div>

      {/* Critical Drops */}
      {data.critical_drops.length > 0 && (
        <div className="mb-3">
          <p className="text-xs text-red-500 mb-2">
            🔴 5위 이상 하락 ({data.critical_drops.length}개)
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {data.critical_drops.slice(0, 4).map((drop) => (
              <div
                key={drop.keyword}
                className="flex items-center justify-between bg-red-500/20 px-3 py-2 rounded-lg"
              >
                <span className="font-medium text-sm truncate max-w-[60%]">{drop.keyword}</span>
                <div className="text-right">
                  <span className="text-xs text-muted-foreground">
                    {drop.previous_rank}위 → {drop.current_rank}위
                  </span>
                  <span className="ml-2 text-sm font-bold text-red-600">
                    ↓{drop.rank_change}위
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Warnings */}
      {data.warnings.length > 0 && (
        <div className="mb-3">
          <p className="text-xs text-yellow-600 mb-2">
            🟡 3위 이상 하락 ({data.warnings.length}개)
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {data.warnings.slice(0, 4).map((warn) => (
              <div
                key={warn.keyword}
                className="flex items-center justify-between bg-yellow-500/20 px-3 py-2 rounded-lg"
              >
                <span className="font-medium text-sm truncate max-w-[60%]">{warn.keyword}</span>
                <div className="text-right">
                  <span className="text-xs text-muted-foreground">
                    {warn.previous_rank}위 → {warn.current_rank}위
                  </span>
                  <span className="ml-2 text-sm font-bold text-yellow-600">
                    ↓{warn.rank_change}위
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recommendations */}
      {data.recommendations.length > 0 && (
        <div className="pt-2 border-t border-border">
          {data.recommendations.map((rec, idx) => (
            <div key={idx} className="text-sm">
              <p className={`${
                rec.priority === 'critical' ? 'text-red-600' :
                rec.priority === 'warning' ? 'text-yellow-600' :
                'text-green-600'
              }`}>
                {rec.message}
              </p>
              <p className="text-xs text-muted-foreground">{rec.action}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

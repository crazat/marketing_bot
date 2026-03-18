interface UsageStatsProps {
  stats: {
    daily_calls: number
    daily_limit: number
    remaining: number
    usage_percent: number
    total_calls: number
    last_call: string | null
    cooldown_seconds: number
    cooldown_remaining: number
    status: 'available' | 'cooldown' | 'limit_reached'
    enabled: boolean
  }
}

export default function UsageStats({ stats }: UsageStatsProps) {
  const getStatusColor = () => {
    if (!stats.enabled) return 'bg-gray-500'
    switch (stats.status) {
      case 'available':
        return 'bg-green-500'
      case 'cooldown':
        return 'bg-yellow-500'
      case 'limit_reached':
        return 'bg-red-500'
      default:
        return 'bg-gray-500'
    }
  }

  const getStatusText = () => {
    if (!stats.enabled) return '비활성화됨'
    switch (stats.status) {
      case 'available':
        return '사용 가능'
      case 'cooldown':
        return `쿨다운 (${stats.cooldown_remaining}초)`
      case 'limit_reached':
        return '일일 한도 초과'
      default:
        return '알 수 없음'
    }
  }

  const getUsageBarColor = () => {
    if (stats.usage_percent >= 90) return 'bg-red-500'
    if (stats.usage_percent >= 70) return 'bg-yellow-500'
    return 'bg-green-500'
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* 상태 카드 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-muted-foreground">상태</span>
          <div className={`w-3 h-3 rounded-full ${getStatusColor()} animate-pulse`} />
        </div>
        <div className="text-2xl font-bold">{getStatusText()}</div>
        {stats.status === 'cooldown' && (
          <div className="mt-2 text-xs text-muted-foreground">
            쿨다운 시간: {stats.cooldown_seconds}초
          </div>
        )}
      </div>

      {/* 일일 사용량 카드 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-muted-foreground">일일 사용량</span>
          <span className="text-xs text-muted-foreground">
            {stats.daily_calls} / {stats.daily_limit}
          </span>
        </div>
        <div className="text-2xl font-bold">{stats.usage_percent.toFixed(1)}%</div>
        <div className="mt-3 w-full bg-muted rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all ${getUsageBarColor()}`}
            style={{ width: `${Math.min(100, stats.usage_percent)}%` }}
          />
        </div>
      </div>

      {/* 남은 호출 카드 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="text-sm text-muted-foreground mb-2">남은 호출</div>
        <div className="text-4xl font-bold text-primary">
          {stats.remaining}
        </div>
        <div className="text-xs text-muted-foreground mt-2">
          오늘 남은 AI 호출 가능 횟수
        </div>
      </div>

      {/* 누적 사용량 카드 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="text-sm text-muted-foreground mb-2">총 누적 호출</div>
        <div className="text-4xl font-bold">{stats.total_calls.toLocaleString()}</div>
        {stats.last_call && (
          <div className="text-xs text-muted-foreground mt-2">
            마지막: {new Date(stats.last_call).toLocaleString('ko-KR')}
          </div>
        )}
      </div>
    </div>
  )
}

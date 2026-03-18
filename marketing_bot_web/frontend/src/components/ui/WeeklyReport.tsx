import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { hudApi } from '@/services/api'
import Button from '@/components/ui/Button'

interface WeeklyReportData {
  period: {
    start: string
    end: string
    generated_at: string
  }
  summary: {
    total_new_leads: number
    total_converted: number
    total_new_keywords: number
    s_grade_keywords: number
    conversion_rate: number
  }
  // 전주 대비 (선택적)
  previous_week?: {
    total_new_leads: number
    total_converted: number
    total_new_keywords: number
    s_grade_keywords: number
  }
  leads: {
    new_leads: number
    status_breakdown: Record<string, number>
    conversion_rate: number
    converted_count: number
    by_platform: Array<{ platform: string; count: number }>
  }
  keywords: {
    new_keywords: number
    by_grade: Record<string, number>
    top_keywords: Array<{ keyword: string; volume: number; grade: string }>
    s_grade_count: number
  }
  rankings: {
    scan_days: number
    significant_changes: Array<{
      keyword: string
      best_rank: number
      worst_rank: number
      change: number
    }>
  }
  viral: {
    total_targets: number
    comments_posted: number
    targets_skipped: number
    engagement_rate: number
  }
  insights: string[]
  recommendations: Array<{
    priority: string
    action: string
    link: string
  }>
}

export default function WeeklyReport() {
  const navigate = useNavigate()
  const [isExpanded, setIsExpanded] = useState(false)

  const { data, isLoading } = useQuery<WeeklyReportData>({
    queryKey: ['weekly-report'],
    queryFn: hudApi.getWeeklyReport,
    refetchInterval: 3600000,  // 1시간마다 갱신
    retry: 1,
  })

  if (isLoading) {
    return (
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="h-6 w-48 bg-muted rounded animate-pulse mb-4" />
        <div className="h-32 bg-muted rounded animate-pulse" />
      </div>
    )
  }

  if (!data) {
    return (
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold flex items-center gap-2">
            <span>📊</span> 주간 리포트
          </h2>
        </div>
        <div className="text-center py-8">
          <div className="text-4xl mb-4">📈</div>
          <h3 className="text-lg font-semibold mb-2">데이터 수집 중입니다</h3>
          <p className="text-sm text-muted-foreground max-w-md mx-auto">
            주간 리포트는 최소 7일간의 데이터가 필요합니다.
            키워드 스캔, 리드 수집, 바이럴 활동을 진행하면
            자동으로 리포트가 생성됩니다.
          </p>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            <a
              href="/pathfinder"
              className="px-3 py-1.5 text-xs bg-purple-500/10 text-purple-500 rounded-lg hover:bg-purple-500/20"
            >
              🔍 키워드 발굴 시작
            </a>
            <a
              href="/viral"
              className="px-3 py-1.5 text-xs bg-orange-500/10 text-orange-500 rounded-lg hover:bg-orange-500/20"
            >
              🎯 바이럴 수집 시작
            </a>
            <a
              href="/battle"
              className="px-3 py-1.5 text-xs bg-blue-500/10 text-blue-500 rounded-lg hover:bg-blue-500/20"
            >
              📊 순위 추적 시작
            </a>
          </div>
        </div>
      </div>
    )
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('ko-KR', {
      month: 'short',
      day: 'numeric'
    })
  }

  // 전주 대비 변화 계산
  const getChange = (current: number, previous: number | undefined) => {
    if (previous === undefined || previous === 0) return null
    const change = current - previous
    const percentage = Math.round((change / previous) * 100)
    return { change, percentage }
  }

  // 변화 표시 컴포넌트
  const ChangeIndicator = ({ current, previous }: { current: number; previous: number | undefined }) => {
    const changeData = getChange(current, previous)
    if (!changeData) return null

    const { change, percentage } = changeData
    const isPositive = change > 0
    const isNegative = change < 0

    return (
      <div className={`text-[10px] mt-1 ${
        isPositive ? 'text-green-500' : isNegative ? 'text-red-500' : 'text-muted-foreground'
      }`}>
        {isPositive ? '↑' : isNegative ? '↓' : '→'} {Math.abs(percentage)}% vs 전주
      </div>
    )
  }

  return (
    <div className="bg-card rounded-lg border border-border p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <span>📊</span> 주간 리포트
          </h2>
          <p className="text-sm text-muted-foreground">
            {formatDate(data.period.start)} ~ {formatDate(data.period.end)}
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          {isExpanded ? '접기' : '자세히'}
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3 text-center">
          <p className="text-2xl font-bold text-blue-500">{data.summary.total_new_leads}</p>
          <p className="text-xs text-muted-foreground">신규 리드</p>
          <ChangeIndicator
            current={data.summary.total_new_leads}
            previous={data.previous_week?.total_new_leads}
          />
        </div>
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3 text-center">
          <p className="text-2xl font-bold text-green-500">{data.summary.total_converted}</p>
          <p className="text-xs text-muted-foreground">전환 완료</p>
          <ChangeIndicator
            current={data.summary.total_converted}
            previous={data.previous_week?.total_converted}
          />
        </div>
        <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-3 text-center">
          <p className="text-2xl font-bold text-purple-500">{data.summary.total_new_keywords}</p>
          <p className="text-xs text-muted-foreground">신규 키워드</p>
          <ChangeIndicator
            current={data.summary.total_new_keywords}
            previous={data.previous_week?.total_new_keywords}
          />
        </div>
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-center">
          <p className="text-2xl font-bold text-red-500">{data.summary.s_grade_keywords}</p>
          <p className="text-xs text-muted-foreground">S급 키워드</p>
          <ChangeIndicator
            current={data.summary.s_grade_keywords}
            previous={data.previous_week?.s_grade_keywords}
          />
        </div>
      </div>

      {/* Insights */}
      {data.insights.length > 0 && (
        <div className="mb-4">
          <h3 className="text-sm font-medium mb-2">💡 주요 인사이트</h3>
          <ul className="space-y-1 text-sm">
            {data.insights.map((insight, idx) => (
              <li key={idx} className="text-muted-foreground">• {insight}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Recommendations */}
      {data.recommendations.length > 0 && (
        <div className="mb-4">
          <h3 className="text-sm font-medium mb-2">🎯 권장 액션</h3>
          <div className="flex flex-wrap gap-2">
            {data.recommendations.map((rec, idx) => (
              <Button
                key={idx}
                variant={rec.priority === 'high' ? 'danger' : 'ghost'}
                size="xs"
                onClick={() => navigate(rec.link)}
                className={rec.priority === 'high' ? 'bg-red-500/10 hover:bg-red-500/20' : ''}
              >
                {rec.action}
              </Button>
            ))}
          </div>
        </div>
      )}

      {/* Expanded Details */}
      {isExpanded && (
        <div className="mt-6 pt-4 border-t border-border space-y-6">
          {/* Leads by Platform */}
          {data.leads.by_platform.length > 0 && (
            <div>
              <h3 className="text-sm font-medium mb-2">플랫폼별 리드</h3>
              <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
                {data.leads.by_platform.map((p) => (
                  <div key={p.platform} className="bg-muted p-2 rounded text-center">
                    <p className="font-semibold">{p.count}</p>
                    <p className="text-xs text-muted-foreground capitalize">{p.platform}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Top Keywords */}
          {data.keywords.top_keywords.length > 0 && (
            <div>
              <h3 className="text-sm font-medium mb-2">상위 키워드</h3>
              <div className="space-y-2">
                {data.keywords.top_keywords.map((kw) => (
                  <div key={kw.keyword} className="flex items-center justify-between bg-muted p-2 rounded">
                    <span className="font-medium">{kw.keyword}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">{kw.volume?.toLocaleString() || 0}</span>
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        kw.grade === 'S' ? 'bg-red-500 text-white' :
                        kw.grade === 'A' ? 'bg-green-500 text-white' : 'bg-muted'
                      }`}>
                        {kw.grade}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Ranking Changes */}
          {data.rankings.significant_changes.length > 0 && (
            <div>
              <h3 className="text-sm font-medium mb-2">순위 변동</h3>
              <div className="space-y-2">
                {data.rankings.significant_changes.map((r) => (
                  <div key={r.keyword} className="flex items-center justify-between bg-muted p-2 rounded">
                    <span className="font-medium">{r.keyword}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs">{r.best_rank}위 ~ {r.worst_rank}위</span>
                      <span className={`text-xs ${r.change > 0 ? 'text-red-500' : 'text-green-500'}`}>
                        {r.change > 0 ? `+${r.change}` : r.change}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Viral Stats */}
          {data.viral.total_targets > 0 && (
            <div>
              <h3 className="text-sm font-medium mb-2">바이럴 활동</h3>
              <div className="grid grid-cols-3 gap-2">
                <div className="bg-muted p-2 rounded text-center">
                  <p className="font-semibold">{data.viral.total_targets}</p>
                  <p className="text-xs text-muted-foreground">발견 타겟</p>
                </div>
                <div className="bg-muted p-2 rounded text-center">
                  <p className="font-semibold">{data.viral.comments_posted}</p>
                  <p className="text-xs text-muted-foreground">댓글 게시</p>
                </div>
                <div className="bg-muted p-2 rounded text-center">
                  <p className="font-semibold">{data.viral.engagement_rate}%</p>
                  <p className="text-xs text-muted-foreground">참여율</p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

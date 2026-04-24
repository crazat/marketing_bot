/**
 * Performance Monitor Widget
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 4-3-B] 대시보드 성능 모니터링 위젯
 * - 전체 성공률
 * - 정상/주의/문제 작업 수
 * - 문제 작업 목록 (critical/warning)
 * - 권장 조치 사항
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  RefreshCw,
  Zap,
  ChevronDown,
  ChevronUp,
  Play,
} from 'lucide-react'

interface JobSummary {
  name: string
  health: 'healthy' | 'warning' | 'critical' | 'unknown'
  success_rate: number
  total_runs: number
  avg_duration: number
  last_run: string | null
  last_status: string
}

interface Recommendation {
  job_name: string
  current_schedule: string
  recommended_schedule: string
  reason: string
  priority: 'high' | 'medium' | 'low'
  auto_apply: boolean
}

interface SchedulerHealthData {
  summary: {
    total_jobs: number
    total_runs: number
    overall_success_rate: number
    health_counts: {
      healthy: number
      warning: number
      critical: number
      unknown: number
    }
  }
  jobs: JobSummary[]
  recommendations: Recommendation[]
  last_updated: string
}

async function fetchSchedulerHealth(): Promise<SchedulerHealthData> {
  const response = await fetch('/api/scheduler/health')
  if (!response.ok) throw new Error('Failed to fetch scheduler health')
  const json = await response.json()
  return json.data
}

async function applyRecommendations() {
  const response = await fetch('/api/scheduler/apply-recommendations', {
    method: 'POST',
  })
  if (!response.ok) throw new Error('Failed to apply recommendations')
  return response.json()
}

export function PerformanceMonitorWidget() {
  const [isExpanded, setIsExpanded] = useState(false)
  const queryClient = useQueryClient()

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['scheduler-health'],
    queryFn: fetchSchedulerHealth,
    refetchInterval: 60000, // 1분마다 갱신
  })

  const applyMutation = useMutation({
    mutationFn: applyRecommendations,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduler-health'] })
    },
  })

  if (isLoading) {
    return (
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-center gap-2 text-muted-foreground">
          <RefreshCw className="h-4 w-4 animate-spin" />
          <span>스케줄러 상태 로딩 중...</span>
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-center gap-2 text-red-500">
          <AlertTriangle className="h-4 w-4" />
          <span>스케줄러 상태를 불러올 수 없습니다</span>
        </div>
      </div>
    )
  }

  const { summary, jobs, recommendations } = data
  const hasIssues = summary.health_counts.critical > 0 || summary.health_counts.warning > 0
  const problemJobs = jobs.filter(j => j.health === 'critical' || j.health === 'warning')
  const autoApplyCount = recommendations.filter(r => r.auto_apply).length

  // 상태 아이콘
  const getHealthIcon = (health: string) => {
    switch (health) {
      case 'healthy':
        return <CheckCircle2 className="h-4 w-4 text-green-500" />
      case 'warning':
        return <AlertTriangle className="h-4 w-4 text-yellow-500" />
      case 'critical':
        return <AlertTriangle className="h-4 w-4 text-red-500" />
      default:
        return <Clock className="h-4 w-4 text-muted-foreground" />
    }
  }

  // 우선순위 색상
  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high': return 'text-red-500 bg-red-500/10'
      case 'medium': return 'text-yellow-500 bg-yellow-500/10'
      case 'low': return 'text-blue-500 bg-blue-500/10'
      default: return 'text-muted-foreground'
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      {/* 헤더 */}
      <div
        className="flex items-center justify-between p-4 cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${hasIssues ? 'bg-yellow-500/10' : 'bg-green-500/10'}`}>
            <Activity className={`h-5 w-5 ${hasIssues ? 'text-yellow-500' : 'text-green-500'}`} />
          </div>
          <div>
            <h3 className="font-semibold">스케줄러 성능</h3>
            <p className="text-sm text-muted-foreground">
              전체 성공률: {summary.overall_success_rate.toFixed(1)}%
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* 상태 요약 배지 */}
          <div className="hidden sm:flex items-center gap-2">
            <span className="flex items-center gap-1 text-xs bg-green-500/10 text-green-500 px-2 py-1 rounded-full">
              <CheckCircle2 className="h-3 w-3" />
              {summary.health_counts.healthy}
            </span>
            {summary.health_counts.warning > 0 && (
              <span className="flex items-center gap-1 text-xs bg-yellow-500/10 text-yellow-500 px-2 py-1 rounded-full">
                <AlertTriangle className="h-3 w-3" />
                {summary.health_counts.warning}
              </span>
            )}
            {summary.health_counts.critical > 0 && (
              <span className="flex items-center gap-1 text-xs bg-red-500/10 text-red-500 px-2 py-1 rounded-full">
                <AlertTriangle className="h-3 w-3" />
                {summary.health_counts.critical}
              </span>
            )}
          </div>

          {isExpanded ? (
            <ChevronUp className="h-5 w-5 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-5 w-5 text-muted-foreground" />
          )}
        </div>
      </div>

      {/* 확장 콘텐츠 */}
      {isExpanded && (
        <div className="border-t border-border">
          {/* 요약 통계 */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-muted/30">
            <div className="text-center">
              <div className="text-2xl font-bold">{summary.total_jobs}</div>
              <div className="text-xs text-muted-foreground">전체 작업</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold">{summary.total_runs}</div>
              <div className="text-xs text-muted-foreground">총 실행 횟수</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-500">
                {summary.health_counts.healthy}
              </div>
              <div className="text-xs text-muted-foreground">정상</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-yellow-500">
                {summary.health_counts.warning + summary.health_counts.critical}
              </div>
              <div className="text-xs text-muted-foreground">문제</div>
            </div>
          </div>

          {/* 문제 작업 목록 */}
          {problemJobs.length > 0 && (
            <div className="p-4 border-t border-border">
              <h4 className="font-medium mb-3 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-yellow-500" />
                주의 필요 작업
              </h4>
              <div className="space-y-2">
                {problemJobs.slice(0, 5).map((job) => (
                  <div
                    key={job.name}
                    className="flex items-center justify-between p-2 rounded-lg bg-muted/50"
                  >
                    <div className="flex items-center gap-2">
                      {getHealthIcon(job.health)}
                      <span className="text-sm font-medium">{job.name}</span>
                    </div>
                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                      <span>성공률: {job.success_rate.toFixed(1)}%</span>
                      <span>평균: {job.avg_duration.toFixed(1)}초</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 권장 조치 */}
          {recommendations.length > 0 && (
            <div className="p-4 border-t border-border">
              <div className="flex items-center justify-between mb-3">
                <h4 className="font-medium flex items-center gap-2">
                  <Zap className="h-4 w-4 text-blue-500" />
                  권장 조치 ({recommendations.length})
                </h4>
                {autoApplyCount > 0 && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      applyMutation.mutate()
                    }}
                    disabled={applyMutation.isPending}
                    className="flex items-center gap-1 text-xs bg-blue-500 hover:bg-blue-600 text-white px-3 py-1 rounded-full transition-colors disabled:opacity-50"
                  >
                    {applyMutation.isPending ? (
                      <RefreshCw className="h-3 w-3 animate-spin" />
                    ) : (
                      <Play className="h-3 w-3" />
                    )}
                    자동 적용 ({autoApplyCount})
                  </button>
                )}
              </div>

              <div className="space-y-2">
                {recommendations.slice(0, 3).map((rec, index) => (
                  <div
                    key={index}
                    className="p-3 rounded-lg border border-border bg-background"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-sm">{rec.job_name}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${getPriorityColor(rec.priority)}`}>
                        {rec.priority === 'high' ? '높음' : rec.priority === 'medium' ? '중간' : '낮음'}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mb-1">{rec.reason}</p>
                    <p className="text-xs">
                      <span className="text-muted-foreground">권장:</span>{' '}
                      <span className="text-blue-500">{rec.recommended_schedule}</span>
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 새로고침 버튼 */}
          <div className="p-4 border-t border-border flex justify-between items-center text-xs text-muted-foreground">
            <span>
              마지막 업데이트: {data.last_updated ? new Date(data.last_updated).toLocaleTimeString('ko-KR') : '-'}
            </span>
            <button
              onClick={(e) => {
                e.stopPropagation()
                refetch()
              }}
              className="flex items-center gap-1 hover:text-foreground transition-colors"
            >
              <RefreshCw className="h-3 w-3" />
              새로고침
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default PerformanceMonitorWidget

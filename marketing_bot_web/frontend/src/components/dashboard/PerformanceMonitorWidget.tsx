import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, AlertTriangle, CheckCircle2, RefreshCw } from 'lucide-react'

type SchedulerSummary = {
  total_jobs?: number
  running_jobs?: number
  failed_jobs?: number
  overall_success_rate?: number
}

type SchedulerHealthResponse = {
  success?: boolean
  data?: {
    summary?: SchedulerSummary
  }
}

type ApplyRecommendationsResponse = {
  success?: boolean
  message?: string
  data?: {
    applied?: unknown[]
    skipped?: unknown[]
  }
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })

  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`)
  }

  return response.json() as Promise<T>
}

export default function PerformanceMonitorWidget() {
  const queryClient = useQueryClient()

  const { data, isError, isFetching, isLoading, refetch } = useQuery<SchedulerHealthResponse>({
    queryKey: ['performance-monitor', 'scheduler-health'],
    queryFn: () => requestJson<SchedulerHealthResponse>('/api/scheduler/health'),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const applyRecommendations = useMutation<ApplyRecommendationsResponse, Error>({
    mutationFn: () =>
      requestJson<ApplyRecommendationsResponse>('/api/scheduler/apply-recommendations', {
        method: 'POST',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['performance-monitor', 'scheduler-health'] })
    },
  })

  const summary = data?.data?.summary ?? {}
  const totalJobs = summary.total_jobs ?? 0
  const runningJobs = summary.running_jobs ?? 0
  const failedJobs = summary.failed_jobs ?? 0
  const successRate = summary.overall_success_rate ?? 0
  const healthy = Boolean(data?.success) && !isError && failedJobs === 0

  return (
    <section className="border border-border bg-card p-5" aria-label="Performance monitor">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="caps mb-2 flex items-center gap-2 text-muted-foreground">
            <Activity className="h-4 w-4" />
            <span>Scheduler</span>
          </div>
          <h2 className="text-lg font-semibold leading-tight">Performance Monitor</h2>
        </div>

        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
            healthy
              ? 'bg-emerald-500/10 text-emerald-600'
              : 'bg-amber-500/10 text-amber-600'
          }`}
        >
          {healthy ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
          {healthy ? 'Healthy' : 'Check'}
        </span>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="Jobs" value={totalJobs.toLocaleString()} />
        <Metric label="Running" value={runningJobs.toLocaleString()} />
        <Metric label="Failed" value={failedJobs.toLocaleString()} />
        <Metric label="Success" value={`${successRate.toFixed(1)}%`} />
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void refetch()}
          disabled={isFetching}
          className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </button>
        <button
          type="button"
          onClick={() => applyRecommendations.mutate()}
          disabled={applyRecommendations.isPending || isLoading}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          Apply Recommendations
        </button>
      </div>

      {isError ? (
        <p className="mt-3 text-sm text-destructive">Scheduler health is unavailable.</p>
      ) : null}
      {applyRecommendations.isError ? (
        <p className="mt-3 text-sm text-destructive">{applyRecommendations.error.message}</p>
      ) : null}
      {applyRecommendations.data?.success ? (
        <p className="mt-3 text-sm text-muted-foreground">
          Applied {(applyRecommendations.data.data?.applied ?? []).length.toLocaleString()} recommendations.
        </p>
      ) : null}
    </section>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-border bg-background p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-semibold tabular-nums">{value}</div>
    </div>
  )
}

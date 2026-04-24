import { useQuery } from '@tanstack/react-query'
import { TrendingUp, Clock, CheckCircle2, Activity } from 'lucide-react'
import { viralApi } from '@/services/api'
import GlossaryTerm from '@/components/ui/GlossaryTerm'
import RefetchIndicator from '@/components/ui/RefetchIndicator'
import FreshnessBadge from '@/components/ui/FreshnessBadge'

export type KpiNavigateTarget =
  | 'pending'            // 대기 중 (전체)
  | 'today_processed'    // 오늘 처리 (승인/게시/스킵)
  | 'week_processed'     // 최근 7일 처리
  | 'hot_pending'        // HOT LEAD (점수 100+) 대기

interface KpiWidgetProps {
  onNavigate?: (target: KpiNavigateTarget) => void
}

/**
 * [U6/V2] KPI 위젯 — 숫자 클릭 시 해당 필터로 ListView 진입.
 */
export default function KpiWidget({ onNavigate }: KpiWidgetProps = {}) {
  const { data, isLoading, isFetching, dataUpdatedAt } = useQuery({
    queryKey: ['viral-kpi-stats', 14],
    queryFn: () => viralApi.getKpiStats(14),
    staleTime: 120_000,
  })
  const isRefetching = isFetching && !isLoading

  if (isLoading || !data) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 animate-pulse">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 bg-muted/50 rounded-lg" />
        ))}
      </div>
    )
  }

  const { summary, daily } = data

  // 단순 스파크라인용 스케일
  const maxProcessed = Math.max(
    1,
    ...daily.map((d) => d.approved + d.posted + d.skipped)
  )
  const acceptRatePct = Math.round(summary.ai_accept_rate * 100)

  // [BB2/EE5] 전주 대비 비교 — daily를 반으로 나눠 최신 vs 이전. NaN/빈 배열 방어.
  const weekDelta = (() => {
    if (!Array.isArray(daily) || daily.length < 4) return null
    const half = Math.floor(daily.length / 2)
    if (half < 1) return null
    const recent = daily.slice(-half)
    const earlier = daily.slice(0, half)
    const sum = (arr: typeof daily) =>
      arr.reduce((a, d) => {
        const approved = Number(d?.approved) || 0
        const posted = Number(d?.posted) || 0
        const skipped = Number(d?.skipped) || 0
        return a + approved + posted + skipped
      }, 0)
    const recentTotal = sum(recent)
    const earlierTotal = sum(earlier)
    if (!Number.isFinite(recentTotal) || !Number.isFinite(earlierTotal)) return null
    if (earlierTotal === 0) return recentTotal > 0 ? { pct: 100, dir: 'up' as const } : null
    const pct = Math.round(((recentTotal - earlierTotal) / earlierTotal) * 100)
    if (!Number.isFinite(pct)) return null
    return { pct: Math.abs(pct), dir: pct >= 0 ? 'up' as const : 'down' as const }
  })()

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          icon={<Clock className="h-4 w-4" />}
          label="대기 중"
          value={summary.backlog_pending.toLocaleString()}
          subLabel={
            summary.backlog_hot > 0
              ? `🔥 HOT ${summary.backlog_hot.toLocaleString()}건 (클릭)`
              : '전체 보기 (클릭)'
          }
          accent={summary.backlog_hot > 500 ? 'warning' : 'default'}
          onClick={() => onNavigate?.(summary.backlog_hot > 0 ? 'hot_pending' : 'pending')}
        />
        <KpiCard
          icon={<CheckCircle2 className="h-4 w-4" />}
          label="오늘 처리"
          value={summary.today_processed.toLocaleString()}
          subLabel="오늘 목록 열기 (클릭)"
          accent="success"
          onClick={() => onNavigate?.('today_processed')}
        />
        <KpiCard
          icon={<TrendingUp className="h-4 w-4" />}
          label="이번 주 처리"
          value={summary.week_processed.toLocaleString()}
          subLabel={
            weekDelta
              ? `전주 대비 ${weekDelta.dir === 'up' ? '▲' : '▼'}${weekDelta.pct}%`
              : '최근 7일 (클릭)'
          }
          accent={weekDelta?.dir === 'up' ? 'success' : weekDelta?.dir === 'down' ? 'warning' : 'default'}
          onClick={() => onNavigate?.('week_processed')}
        />
        <KpiCard
          icon={<Activity className="h-4 w-4" />}
          label={<GlossaryTerm termKey="ai_accept_rate">AI 적합률</GlossaryTerm>}
          value={`${acceptRatePct}%`}
          subLabel={`${data.range_days}일 기준`}
          accent={acceptRatePct >= 40 ? 'success' : 'warning'}
        />
      </div>

      {/* 간단 스파크라인 */}
      {daily.length > 1 && (
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              일별 처리량 (최근 {data.range_days}일)
              <RefetchIndicator isRefetching={isRefetching} variant="dot" />
            </h4>
            {dataUpdatedAt > 0 && (
              <FreshnessBadge timestamp={dataUpdatedAt} prefix="수집" />
            )}
          </div>
          <div className="flex items-end gap-1 h-20">
            {daily.map((d) => {
              const total = d.approved + d.posted + d.skipped
              const h = Math.max(2, (total / maxProcessed) * 100)
              return (
                <div
                  key={d.day}
                  className="flex-1 flex flex-col items-center gap-0.5"
                  title={`${d.day}: 승인 ${d.approved} · 게시 ${d.posted} · 스킵 ${d.skipped}`}
                >
                  <div
                    className="w-full bg-primary/70 rounded-t"
                    style={{ height: `${h}%` }}
                  />
                </div>
              )
            })}
          </div>
          <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
            <span>{daily[0]?.day.slice(5)}</span>
            <span>{daily[daily.length - 1]?.day.slice(5)}</span>
          </div>
        </div>
      )}
    </div>
  )
}

interface KpiCardProps {
  icon: React.ReactNode
  label: React.ReactNode
  value: string
  subLabel?: string
  accent?: 'default' | 'success' | 'warning'
  onClick?: () => void
}

function KpiCard({ icon, label, value, subLabel, accent = 'default', onClick }: KpiCardProps) {
  const accentColor =
    accent === 'success'
      ? 'text-emerald-600 dark:text-emerald-400'
      : accent === 'warning'
      ? 'text-accent'
      : 'text-primary'
  const interactive = !!onClick
  return (
    <div
      onClick={onClick}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={interactive ? (e) => (e.key === 'Enter' || e.key === ' ') && onClick?.() : undefined}
      className={`group relative bg-card border border-border p-5 ${
        interactive
          ? 'cursor-pointer hover:border-primary/60 hover:shadow-lg hover:shadow-primary/5 transition-all duration-200'
          : ''
      }`}
    >
      {/* [Z3] 상단 caps 라벨 — editorial magazine 스타일 */}
      <div className="flex items-center gap-1.5 caps text-muted-foreground">
        <span className="opacity-60">{icon}</span>
        <span>{label}</span>
      </div>

      {/* [Z3] 대형 monospace 숫자 — Paperlogy display or D2Coding tabular */}
      <div
        className={`font-display tabular-nums mt-3 leading-none ${accentColor}`}
        style={{ fontSize: 'clamp(2.25rem, 4.5vw, 3.25rem)' }}
      >
        {value}
      </div>

      {subLabel && (
        <div className="text-xs text-muted-foreground mt-2 flex items-center gap-1">
          {subLabel}
          {interactive && (
            <span className="opacity-0 group-hover:opacity-100 transition-opacity ml-auto">
              →
            </span>
          )}
        </div>
      )}

      {/* 좌측 accent 선 (호버 시 등장) */}
      {interactive && (
        <span
          aria-hidden
          className="absolute left-0 top-4 bottom-4 w-[2px] bg-primary scale-y-0 group-hover:scale-y-100 transition-transform origin-top"
        />
      )}
    </div>
  )
}

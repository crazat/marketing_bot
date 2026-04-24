import { AlertTriangle, ArrowRight, Zap } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAnomalyDetection } from '@/hooks/useAnomalyDetection'

/**
 * [Z2] 이상치 감지 배너 — Dashboard 최상단
 *
 * 정상 상태에선 렌더링 없음. 이상 감지 시 최대 2건 표시.
 * TodayFocus 위에 배치해 즉시 주의 환기.
 */
export default function AnomalyAlert() {
  const navigate = useNavigate()
  const { anomalies } = useAnomalyDetection()

  if (anomalies.length === 0) return null

  const top = anomalies.slice(0, 2)

  return (
    <section
      aria-label="이상 신호"
      className="space-y-2"
    >
      <div className="caps text-accent flex items-center gap-1.5">
        <Zap className="w-3 h-3" aria-hidden />
        <span>이상 신호 · Anomaly</span>
      </div>
      {top.map((a) => {
        const toneClass =
          a.severity === 'critical'
            ? 'border-red-500/40 bg-red-500/5'
            : a.severity === 'warning'
            ? 'border-amber-500/40 bg-amber-500/5'
            : 'border-blue-500/40 bg-blue-500/5'
        const iconTone =
          a.severity === 'critical'
            ? 'text-red-500'
            : a.severity === 'warning'
            ? 'text-amber-500'
            : 'text-blue-500'
        return (
          <button
            key={a.id}
            onClick={() => a.path && navigate(a.path)}
            className={`group w-full text-left border p-4 flex items-start gap-3 transition-all hover:shadow-md ${toneClass} ${
              a.path ? 'cursor-pointer' : 'cursor-default'
            }`}
          >
            <AlertTriangle className={`w-5 h-5 shrink-0 mt-0.5 ${iconTone}`} aria-hidden />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="font-display text-base leading-tight">{a.title}</h3>
                {a.delta && (
                  <span className={`text-xs font-bold tabular-nums ${iconTone}`}>{a.delta}</span>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-1">{a.detail}</p>
            </div>
            {a.path && (
              <ArrowRight
                className="w-4 h-4 text-muted-foreground shrink-0 mt-1 opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all"
                aria-hidden
              />
            )}
          </button>
        )
      })}
    </section>
  )
}

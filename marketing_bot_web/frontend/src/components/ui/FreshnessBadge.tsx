import { formatRelative } from '@/utils/format'

interface FreshnessBadgeProps {
  /** 데이터 수집/업데이트 시각 */
  timestamp: number | string | Date | null | undefined
  /** 기준 시간 이상이면 경고 색상 (기본 10분) */
  warnAfterMs?: number
  /** 기준 시간 이상이면 에러 색상 (기본 60분) */
  staleAfterMs?: number
  /** prefix 텍스트 */
  prefix?: string
}

/**
 * [Z3] 데이터 신선도 미니 배지
 *
 * "2분 전" 형태. timestamp 기준으로 warn/stale 색상 자동 전환.
 * 위젯 헤더·숫자 옆에 조용히 배치해 "이 값이 언제 것인지" 투명화.
 */
export default function FreshnessBadge({
  timestamp,
  warnAfterMs = 10 * 60_000,
  staleAfterMs = 60 * 60_000,
  prefix,
}: FreshnessBadgeProps) {
  if (!timestamp) return null
  const t = timestamp instanceof Date ? timestamp.getTime() : new Date(timestamp).getTime()
  if (Number.isNaN(t)) return null

  const age = Date.now() - t
  const tone =
    age >= staleAfterMs
      ? 'text-red-500 bg-red-500/10 border-red-500/30'
      : age >= warnAfterMs
      ? 'text-amber-600 bg-amber-500/10 border-amber-500/30'
      : 'text-muted-foreground bg-muted/40 border-border'

  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium border rounded ${tone}`}
      title={new Date(t).toLocaleString('ko-KR')}
    >
      {prefix && <span>{prefix}</span>}
      <span className="tabular-nums">{formatRelative(t)}</span>
    </span>
  )
}

import { Loader2 } from 'lucide-react'

interface RefetchIndicatorProps {
  /** React Query의 isFetching && !isLoading */
  isRefetching: boolean
  /** 크기 — inline(기본)/absolute 오버레이 */
  variant?: 'inline' | 'badge' | 'dot'
  label?: string
}

/**
 * [Z6] Stale-while-revalidate 시각 신호
 *
 * isLoading=false이지만 isFetching=true일 때 표시.
 * 이전 데이터는 그대로 보여주면서 "백그라운드에서 갱신 중"임을 암시.
 */
export default function RefetchIndicator({
  isRefetching,
  variant = 'inline',
  label = '갱신 중',
}: RefetchIndicatorProps) {
  if (!isRefetching) return null

  if (variant === 'dot') {
    return (
      <span
        className="inline-block w-1.5 h-1.5 rounded-full bg-primary animate-pulse align-middle ml-1.5"
        aria-label={label}
        role="status"
      />
    )
  }

  if (variant === 'badge') {
    return (
      <span
        role="status"
        aria-live="polite"
        className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] text-muted-foreground bg-muted/50 rounded-full animate-fade-in"
      >
        <Loader2 className="w-2.5 h-2.5 animate-spin" aria-hidden />
        <span>{label}</span>
      </span>
    )
  }

  // inline — 기본
  return (
    <span
      role="status"
      aria-live="polite"
      className="inline-flex items-center gap-1 text-xs text-muted-foreground animate-fade-in"
    >
      <Loader2 className="w-3 h-3 animate-spin" aria-hidden />
      <span>{label}</span>
    </span>
  )
}

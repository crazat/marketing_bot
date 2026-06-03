/**
 * MetricCard Component
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] 메트릭 카드 - 트렌드 표시 강화
 * - 숫자 트렌드 (이전 값 대비 변화율)
 * - 스파크라인 차트 옵션
 * - 클릭 가능한 카드
 */

import { useMemo, memo, type ReactNode } from 'react'
import SparklineChart from '@/components/ui/SparklineChart'
import CountUp from '@/components/ui/CountUp'

interface MetricCardProps {
  title: string
  value: number
  icon?: ReactNode
  trend?: string
  /** @deprecated RECOVER OS — KPI 값은 항상 text-strong. 색상 무시됨 */
  color?: string
  subtitle?: string
  // [Phase 5.0] 신규 props
  previousValue?: number
  sparklineData?: number[]
  onClick?: () => void
  loading?: boolean
  // [Phase 5.0] 카운트업 애니메이션
  animate?: boolean
  animationDuration?: number
}

// [성능 최적화] React.memo로 불필요한 리렌더링 방지
function MetricCardComponent({
  title,
  value,
  icon,
  trend,
  subtitle,
  previousValue,
  sparklineData,
  onClick,
  loading = false,
  animate = true,
  animationDuration = 800,
}: MetricCardProps) {
  // 트렌드 계산
  const trendInfo = useMemo(() => {
    if (previousValue === undefined || previousValue === null) {
      return null
    }

    const diff = value - previousValue
    const percentChange = previousValue !== 0
      ? ((value - previousValue) / Math.abs(previousValue)) * 100
      : value > 0 ? 100 : 0

    return {
      diff,
      percent: percentChange,
      isPositive: diff > 0,
      isNegative: diff < 0,
    }
  }, [value, previousValue])

  // 로딩 상태
  if (loading) {
    return (
      <div
        className="bg-card rounded-lg border border-border p-6 animate-pulse"
        role="region"
        aria-label={title}
        aria-busy="true"
      >
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="h-4 w-24 bg-muted rounded mb-2" />
            <div className="h-8 w-16 bg-muted rounded mb-2" />
            <div className="h-3 w-20 bg-muted rounded" />
          </div>
          <div className="h-12 w-12 bg-muted rounded-lg" />
        </div>
      </div>
    )
  }

  const isClickable = !!onClick

  return (
    <div
      className={`ros-kpi ${isClickable ? '' : 'cursor-default'}`}
      role={isClickable ? 'button' : 'region'}
      aria-label={title}
      onClick={onClick}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={isClickable ? (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick?.()
        }
      } : undefined}
    >
      {/* 라벨 + 아이콘 */}
      <div className="flex items-start justify-between gap-2.5">
        <p className="text-[12.5px] text-muted-foreground font-medium whitespace-nowrap">{title}</p>
        {icon && <span className="ros-kpi-ico" aria-hidden="true">{icon}</span>}
      </div>

      {/* 값 (Fraunces) + 델타 */}
      <div className="ros-kpi-val">
        <span aria-live="polite">
          {animate ? (
            <CountUp end={value} duration={animationDuration} />
          ) : (
            value.toLocaleString()
          )}
        </span>
        {trendInfo && (
          <span
            className={`ros-kpi-trend ${trendInfo.isPositive ? 'up' : trendInfo.isNegative ? 'down' : ''}`}
            role="status"
            aria-label={`어제 대비 ${trendInfo.isPositive ? '증가' : trendInfo.isNegative ? '감소' : '변동 없음'} ${Math.abs(trendInfo.percent).toFixed(1)}%`}
          >
            {trendInfo.isPositive && <span aria-hidden="true">↑</span>}
            {trendInfo.isNegative && <span aria-hidden="true">↓</span>}
            {Math.abs(trendInfo.percent).toFixed(1)}%
          </span>
        )}
      </div>

      {/* 기존 trend 문자열 (하위 호환) */}
      {trend && !trendInfo && (
        <p className="text-xs text-ok mt-1.5">{trend}</p>
      )}

      {/* 스파크라인 */}
      {sparklineData && sparklineData.length > 1 && (
        <div className="mt-2.5 -mb-0.5">
          <SparklineChart data={sparklineData} width={120} height={26} showArea={true} />
        </div>
      )}

      {/* 서브타이틀 + 클릭 안내 */}
      <div className="flex items-end justify-between gap-2 mt-3">
        {subtitle && <p className="text-[11.5px] text-faint truncate">{subtitle}</p>}
        {isClickable && (
          <span className="text-[11.5px] text-faint inline-flex items-center gap-1 ml-auto whitespace-nowrap">
            자세히 보기 <span aria-hidden="true">→</span>
          </span>
        )}
      </div>
    </div>
  )
}

// memo로 value, title 등이 변경될 때만 리렌더링
const MetricCard = memo(MetricCardComponent)

export default MetricCard

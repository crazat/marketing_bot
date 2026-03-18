/**
 * MetricCard Component
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] 메트릭 카드 - 트렌드 표시 강화
 * - 숫자 트렌드 (이전 값 대비 변화율)
 * - 스파크라인 차트 옵션
 * - 클릭 가능한 카드
 */

import { useMemo, memo } from 'react'
import SparklineChart from '@/components/ui/SparklineChart'
import CountUp from '@/components/ui/CountUp'

interface MetricCardProps {
  title: string
  value: number
  icon: string
  trend?: string
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
  color,
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
      className={`
        bg-card rounded-lg border border-border p-6
        transition-all duration-200
        ${isClickable
          ? 'cursor-pointer hover:border-primary hover:shadow-md active:scale-[0.98]'
          : 'hover:border-primary/50'
        }
      `}
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
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-muted-foreground mb-1">{title}</p>
          <div className="flex items-baseline gap-2">
            <p className={`text-3xl font-bold ${color || ''}`} aria-live="polite">
              {animate ? (
                <CountUp end={value} duration={animationDuration} />
              ) : (
                value.toLocaleString()
              )}
            </p>

            {/* 트렌드 표시 */}
            {trendInfo && (
              <span
                className={`
                  inline-flex items-center gap-0.5 text-sm font-medium
                  ${trendInfo.isPositive ? 'text-green-500' : ''}
                  ${trendInfo.isNegative ? 'text-red-500' : ''}
                  ${!trendInfo.isPositive && !trendInfo.isNegative ? 'text-muted-foreground' : ''}
                `}
                role="status"
                aria-label={`어제 대비 ${trendInfo.isPositive ? '증가' : trendInfo.isNegative ? '감소' : '변동 없음'} ${Math.abs(trendInfo.percent).toFixed(1)}%`}
              >
                {trendInfo.isPositive && <span aria-hidden="true">↑</span>}
                {trendInfo.isNegative && <span aria-hidden="true">↓</span>}
                <span className="sr-only">
                  {trendInfo.isPositive ? '증가' : trendInfo.isNegative ? '감소' : '변동 없음'}
                </span>
                {Math.abs(trendInfo.percent).toFixed(1)}%
              </span>
            )}
          </div>

          {/* 기존 trend 문자열 표시 (하위 호환) */}
          {trend && !trendInfo && (
            <p className="text-sm text-green-500 mt-1">{trend}</p>
          )}

          {/* 스파크라인 차트 */}
          {sparklineData && sparklineData.length > 1 && (
            <div className="mt-2">
              <SparklineChart
                data={sparklineData}
                width={120}
                height={24}
                showArea={true}
              />
            </div>
          )}

          {subtitle && (
            <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
          )}
        </div>

        <div className="text-4xl flex-shrink-0 ml-4" aria-hidden="true">
          {icon}
        </div>
      </div>

      {/* 클릭 가능 표시 */}
      {isClickable && (
        <div className="mt-3 pt-3 border-t border-border">
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <span>자세히 보기</span>
            <span aria-hidden="true">→</span>
          </span>
        </div>
      )}
    </div>
  )
}

// memo로 value, title 등이 변경될 때만 리렌더링
const MetricCard = memo(MetricCardComponent)

export default MetricCard

/**
 * SparklineChart Component
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] 미니 트렌드 차트 (SVG 기반)
 * - 외부 라이브러리 없이 순수 SVG
 * - 선 그래프 + 영역 채우기
 * - 호버 시 값 표시
 */

import { useMemo, useState } from 'react'

interface SparklineChartProps {
  data: number[]
  width?: number
  height?: number
  color?: string
  showDots?: boolean
  showArea?: boolean
  className?: string
}

export default function SparklineChart({
  data,
  width = 100,
  height = 32,
  color = 'currentColor',
  showDots = false,
  showArea = true,
  className = '',
}: SparklineChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)

  // 데이터를 SVG 좌표로 변환
  const { points, areaPath, linePath } = useMemo(() => {
    if (data.length === 0) {
      return { points: [], areaPath: '', linePath: '' }
    }

    const padding = 2
    const chartWidth = width - padding * 2
    const chartHeight = height - padding * 2

    const minVal = Math.min(...data)
    const maxVal = Math.max(...data)
    const range = maxVal - minVal || 1

    const pts = data.map((value, index) => {
      const x = padding + (index / (data.length - 1 || 1)) * chartWidth
      const y = padding + chartHeight - ((value - minVal) / range) * chartHeight
      return { x, y, value }
    })

    // 선 경로
    const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')

    // 영역 경로 (닫힌 형태)
    const area = pts.length > 0
      ? `${line} L ${pts[pts.length - 1].x} ${height - padding} L ${pts[0].x} ${height - padding} Z`
      : ''

    return {
      points: pts,
      linePath: line,
      areaPath: area,
    }
  }, [data, width, height])

  // 트렌드 방향 계산
  const trend = useMemo(() => {
    if (data.length < 2) return 'neutral'
    const first = data[0]
    const last = data[data.length - 1]
    if (last > first) return 'up'
    if (last < first) return 'down'
    return 'neutral'
  }, [data])

  // 색상 결정
  const chartColor = useMemo(() => {
    if (color !== 'currentColor') return color
    switch (trend) {
      case 'up':
        return '#22c55e' // green-500
      case 'down':
        return '#ef4444' // red-500
      default:
        return '#6b7280' // gray-500
    }
  }, [color, trend])

  if (data.length === 0) {
    return (
      <div
        className={`flex items-center justify-center text-xs text-muted-foreground ${className}`}
        style={{ width, height }}
      >
        데이터 없음
      </div>
    )
  }

  return (
    <div className={`relative ${className}`} style={{ width, height }}>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="overflow-visible"
      >
        {/* 영역 채우기 */}
        {showArea && (
          <path
            d={areaPath}
            fill={chartColor}
            fillOpacity={0.1}
          />
        )}

        {/* 선 */}
        <path
          d={linePath}
          fill="none"
          stroke={chartColor}
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* 점 */}
        {showDots && points.map((point, index) => (
          <circle
            key={index}
            cx={point.x}
            cy={point.y}
            r={hoveredIndex === index ? 4 : 2}
            fill={chartColor}
            className="transition-all duration-150"
            onMouseEnter={() => setHoveredIndex(index)}
            onMouseLeave={() => setHoveredIndex(null)}
          />
        ))}

        {/* 마지막 점 강조 */}
        {points.length > 0 && (
          <circle
            cx={points[points.length - 1].x}
            cy={points[points.length - 1].y}
            r={3}
            fill={chartColor}
          />
        )}
      </svg>

      {/* 호버 툴팁 */}
      {hoveredIndex !== null && points[hoveredIndex] && (
        <div
          className="
            absolute -top-8 px-2 py-1
            bg-popover text-popover-foreground
            text-xs rounded shadow-lg border border-border
            pointer-events-none transform -translate-x-1/2
            z-10
          "
          style={{ left: points[hoveredIndex].x }}
        >
          {points[hoveredIndex].value.toLocaleString()}
        </div>
      )}
    </div>
  )
}

/**
 * 간단한 변화율 표시 배지
 */
interface TrendBadgeProps {
  current: number
  previous: number
  format?: 'percent' | 'absolute'
  className?: string
}

export function TrendBadge({
  current,
  previous,
  format = 'percent',
  className = '',
}: TrendBadgeProps) {
  const diff = current - previous
  const percentChange = previous !== 0
    ? ((current - previous) / Math.abs(previous)) * 100
    : 0

  const isPositive = diff > 0
  const isNegative = diff < 0

  const displayValue = format === 'percent'
    ? `${Math.abs(percentChange).toFixed(1)}%`
    : Math.abs(diff).toLocaleString()

  if (diff === 0) {
    return (
      <span className={`text-xs text-muted-foreground ${className}`}>
        -
      </span>
    )
  }

  return (
    <span
      className={`
        inline-flex items-center gap-0.5 text-xs font-medium
        ${isPositive ? 'text-green-500' : ''}
        ${isNegative ? 'text-red-500' : ''}
        ${className}
      `}
    >
      <span aria-hidden="true">{isPositive ? '↑' : '↓'}</span>
      {displayValue}
    </span>
  )
}

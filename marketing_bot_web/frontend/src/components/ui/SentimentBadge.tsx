/**
 * [Phase 6.0] 감성 분석 배지 컴포넌트
 * 리드, 리뷰, 댓글 등에서 감성 상태를 표시
 */

import type { ReactNode } from 'react'
import { Smile, Frown, Meh } from 'lucide-react'

type SentimentType = 'positive' | 'negative' | 'neutral'

interface SentimentBadgeProps {
  sentiment: SentimentType | null | undefined
  showLabel?: boolean
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const sentimentConfig: Record<SentimentType, { bg: string; text: string; icon: ReactNode; label: string }> = {
  positive: { bg: 'bg-ok-tint', text: 'text-ok', icon: <Smile className="w-3.5 h-3.5" strokeWidth={1.8} />, label: '긍정' },
  negative: { bg: 'bg-danger-tint', text: 'text-danger', icon: <Frown className="w-3.5 h-3.5" strokeWidth={1.8} />, label: '부정' },
  neutral: { bg: 'bg-muted', text: 'text-muted-foreground', icon: <Meh className="w-3.5 h-3.5" strokeWidth={1.8} />, label: '중립' },
}

const sizeStyles = {
  sm: 'text-[10px] px-1.5 py-0.5',
  md: 'text-xs px-2 py-1',
  lg: 'text-sm px-3 py-1.5',
}

export default function SentimentBadge({
  sentiment,
  showLabel = true,
  size = 'md',
  className = '',
}: SentimentBadgeProps) {
  if (!sentiment) {
    return <span className="text-xs text-muted-foreground">-</span>
  }

  const config = sentimentConfig[sentiment]

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-medium ${config.bg} ${config.text} ${sizeStyles[size]} ${className}`}
      title={`감성: ${config.label}`}
    >
      <span aria-hidden="true">{config.icon}</span>
      {showLabel && <span>{config.label}</span>}
    </span>
  )
}

// 감성 분석 요약 컴포넌트 (통계용)
interface SentimentSummaryProps {
  positive: number
  negative: number
  neutral: number
  showPercentage?: boolean
}

export function SentimentSummary({ positive, negative, neutral, showPercentage = true }: SentimentSummaryProps) {
  const total = positive + negative + neutral
  if (total === 0) {
    return <span className="text-xs text-muted-foreground">데이터 없음</span>
  }

  const getPercentage = (value: number) => Math.round((value / total) * 100)

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1">
        <Smile className="w-4 h-4 text-ok" strokeWidth={1.8} />
        <span className="text-sm font-medium">{positive}</span>
        {showPercentage && (
          <span className="text-xs text-muted-foreground">({getPercentage(positive)}%)</span>
        )}
      </div>
      <div className="flex items-center gap-1">
        <Frown className="w-4 h-4 text-danger" strokeWidth={1.8} />
        <span className="text-sm font-medium">{negative}</span>
        {showPercentage && (
          <span className="text-xs text-muted-foreground">({getPercentage(negative)}%)</span>
        )}
      </div>
      <div className="flex items-center gap-1">
        <Meh className="w-4 h-4 text-muted-foreground" strokeWidth={1.8} />
        <span className="text-sm font-medium">{neutral}</span>
        {showPercentage && (
          <span className="text-xs text-muted-foreground">({getPercentage(neutral)}%)</span>
        )}
      </div>
    </div>
  )
}

// 감성 분석 진행 바 (비주얼용)
interface SentimentBarProps {
  positive: number
  negative: number
  neutral: number
  height?: number
}

export function SentimentBar({ positive, negative, neutral, height = 8 }: SentimentBarProps) {
  const total = positive + negative + neutral
  if (total === 0) {
    return <div className={`w-full bg-muted rounded-full`} style={{ height }} />
  }

  const positivePercent = (positive / total) * 100
  const negativePercent = (negative / total) * 100
  const neutralPercent = (neutral / total) * 100

  return (
    <div className={`w-full flex rounded-full overflow-hidden`} style={{ height }}>
      {positivePercent > 0 && (
        <div
          className="bg-green-500 transition-all"
          style={{ width: `${positivePercent}%` }}
          title={`긍정: ${positive}건 (${Math.round(positivePercent)}%)`}
        />
      )}
      {neutralPercent > 0 && (
        <div
          className="bg-gray-400 transition-all"
          style={{ width: `${neutralPercent}%` }}
          title={`중립: ${neutral}건 (${Math.round(neutralPercent)}%)`}
        />
      )}
      {negativePercent > 0 && (
        <div
          className="bg-red-500 transition-all"
          style={{ width: `${negativePercent}%` }}
          title={`부정: ${negative}건 (${Math.round(negativePercent)}%)`}
        />
      )}
    </div>
  )
}

/**
 * [Phase 6.0] 감성 분석 배지 컴포넌트
 * 리드, 리뷰, 댓글 등에서 감성 상태를 표시
 */

type SentimentType = 'positive' | 'negative' | 'neutral'

interface SentimentBadgeProps {
  sentiment: SentimentType | null | undefined
  showLabel?: boolean
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const sentimentConfig: Record<SentimentType, { bg: string; text: string; emoji: string; label: string }> = {
  positive: { bg: 'bg-green-500/20', text: 'text-green-500', emoji: '😊', label: '긍정' },
  negative: { bg: 'bg-red-500/20', text: 'text-red-500', emoji: '😟', label: '부정' },
  neutral: { bg: 'bg-gray-500/20', text: 'text-gray-500', emoji: '😐', label: '중립' },
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
      <span aria-hidden="true">{config.emoji}</span>
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
        <span className="text-green-500">😊</span>
        <span className="text-sm font-medium">{positive}</span>
        {showPercentage && (
          <span className="text-xs text-muted-foreground">({getPercentage(positive)}%)</span>
        )}
      </div>
      <div className="flex items-center gap-1">
        <span className="text-red-500">😟</span>
        <span className="text-sm font-medium">{negative}</span>
        {showPercentage && (
          <span className="text-xs text-muted-foreground">({getPercentage(negative)}%)</span>
        )}
      </div>
      <div className="flex items-center gap-1">
        <span className="text-gray-500">😐</span>
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

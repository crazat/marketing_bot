import { RefreshCw, Clock } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { ko } from 'date-fns/locale'

interface DataFreshnessProps {
  /** 마지막 업데이트 시간 (ISO string 또는 Date) */
  lastUpdated?: string | Date | null
  /** 새로고침 함수 */
  onRefresh?: () => void
  /** 로딩 상태 */
  isRefreshing?: boolean
  /** 컴팩트 모드 - 텍스트 숨김 */
  compact?: boolean
  /** 추가 클래스 */
  className?: string
}

/**
 * 데이터 신선도 표시 컴포넌트
 *
 * 마지막 업데이트 시각과 새로고침 버튼을 표시합니다.
 */
export default function DataFreshness({
  lastUpdated,
  onRefresh,
  isRefreshing = false,
  compact = false,
  className = '',
}: DataFreshnessProps) {
  // 시간 포맷팅
  const getTimeAgo = () => {
    if (!lastUpdated) return null

    try {
      const date = typeof lastUpdated === 'string' ? new Date(lastUpdated) : lastUpdated
      return formatDistanceToNow(date, { addSuffix: true, locale: ko })
    } catch {
      return null
    }
  }

  const timeAgo = getTimeAgo()

  return (
    <div className={`flex items-center gap-2 text-sm text-muted-foreground ${className}`}>
      {/* 마지막 업데이트 시각 */}
      {timeAgo && (
        <span className="flex items-center gap-1">
          <Clock className="w-3.5 h-3.5" />
          {!compact && <span>업데이트:</span>}
          <span>{timeAgo}</span>
        </span>
      )}

      {/* 새로고침 버튼 */}
      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="p-1.5 rounded-md hover:bg-muted focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          title="새로고침"
          aria-label="데이터 새로고침"
        >
          <RefreshCw
            className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`}
          />
        </button>
      )}
    </div>
  )
}

/**
 * 섹션 헤더에 통합된 버전
 */
interface SectionHeaderWithRefreshProps {
  title: string
  description?: string
  lastUpdated?: string | Date | null
  onRefresh?: () => void
  isRefreshing?: boolean
  children?: React.ReactNode
}

export function SectionHeaderWithRefresh({
  title,
  description,
  lastUpdated,
  onRefresh,
  isRefreshing = false,
  children,
}: SectionHeaderWithRefreshProps) {
  return (
    <div className="flex items-center justify-between mb-4">
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        {description && (
          <p className="text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      <div className="flex items-center gap-4">
        <DataFreshness
          lastUpdated={lastUpdated}
          onRefresh={onRefresh}
          isRefreshing={isRefreshing}
          compact
        />
        {children}
      </div>
    </div>
  )
}

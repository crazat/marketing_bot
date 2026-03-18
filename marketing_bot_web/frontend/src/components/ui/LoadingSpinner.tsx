/**
 * LoadingSpinner 컴포넌트
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] 로딩 상태 명확화
 * - 기본 스피너
 * - 새로고침 인디케이터
 * - 느린 로딩 메시지
 * - 진행률 표시
 */

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  text?: string
  fullPage?: boolean
  /** 최소 높이 (fullPage일 때) */
  minHeight?: string
}

const sizeClasses = {
  sm: 'h-6 w-6',
  md: 'h-8 w-8',
  lg: 'h-12 w-12',
}

export default function LoadingSpinner({
  size = 'lg',
  text = '로딩 중...',
  fullPage = false,
  minHeight = 'h-96',
}: LoadingSpinnerProps) {
  const spinner = (
    <div
      className="text-center"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div
        className={`animate-spin rounded-full border-b-2 border-primary mx-auto mb-4 ${sizeClasses[size]}`}
        aria-hidden="true"
      />
      {text && (
        <p className="text-muted-foreground">
          <span className="sr-only">현재 상태: </span>
          {text}
        </p>
      )}
    </div>
  )

  if (fullPage) {
    return (
      <div className={`flex items-center justify-center ${minHeight}`}>
        {spinner}
      </div>
    )
  }

  return spinner
}

/**
 * 인라인 스피너 (작은 영역용)
 */
export function InlineSpinner({ size = 'sm' }: { size?: 'sm' | 'md' }) {
  return (
    <span
      className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${
        size === 'sm' ? 'h-4 w-4' : 'h-5 w-5'
      }`}
      role="status"
      aria-label="로딩 중"
    />
  )
}

/**
 * 데이터 새로고침 인디케이터
 * 기존 데이터를 보여주면서 새로고침 중임을 표시
 */
export function RefreshingIndicator({
  message = '데이터를 업데이트하고 있습니다...',
  position = 'top',
}: {
  message?: string
  position?: 'top' | 'bottom' | 'inline'
}) {
  const baseClass = 'flex items-center gap-2 px-3 py-2 text-sm text-blue-600 bg-blue-50 border border-blue-200 rounded-lg'

  if (position === 'inline') {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm text-blue-600">
        <InlineSpinner size="sm" />
        <span>{message}</span>
      </span>
    )
  }

  return (
    <div
      className={`${baseClass} ${position === 'top' ? 'mb-4' : 'mt-4'}`}
      role="status"
      aria-live="polite"
    >
      <InlineSpinner size="sm" />
      <span>{message}</span>
    </div>
  )
}

/**
 * 느린 로딩 메시지
 * 로딩이 오래 걸릴 때 추가 피드백 제공
 */
export function SlowLoadingMessage({
  loadingTime,
  threshold = 5000,
  messages = [
    { time: 5000, text: '잠시만 기다려주세요...' },
    { time: 10000, text: '데이터가 많아 조금 더 걸릴 수 있습니다' },
    { time: 20000, text: '거의 다 됐습니다...' },
    { time: 30000, text: '네트워크가 느릴 수 있습니다. 조금만 더 기다려주세요' },
  ],
}: {
  loadingTime: number
  threshold?: number
  messages?: Array<{ time: number; text: string }>
}) {
  if (loadingTime < threshold) return null

  // 현재 시간에 맞는 메시지 찾기
  const sortedMessages = [...messages].sort((a, b) => b.time - a.time)
  const currentMessage = sortedMessages.find(m => loadingTime >= m.time)

  if (!currentMessage) return null

  return (
    <div
      className="mt-2 text-sm text-muted-foreground animate-fade-in"
      role="status"
      aria-live="polite"
    >
      <span>{currentMessage.text}</span>
      <span className="ml-2 tabular-nums">
        ({Math.round(loadingTime / 1000)}초)
      </span>
    </div>
  )
}

/**
 * 진행률 바
 */
export function ProgressBar({
  progress,
  showPercentage = true,
  color = 'primary',
  size = 'md',
}: {
  progress: number
  showPercentage?: boolean
  color?: 'primary' | 'success' | 'warning' | 'error'
  size?: 'sm' | 'md' | 'lg'
}) {
  const colorClasses = {
    primary: 'bg-primary',
    success: 'bg-green-500',
    warning: 'bg-yellow-500',
    error: 'bg-red-500',
  }

  const sizeHeights = {
    sm: 'h-1',
    md: 'h-2',
    lg: 'h-3',
  }

  const clampedProgress = Math.min(100, Math.max(0, progress))

  return (
    <div className="w-full">
      <div
        className={`w-full bg-muted rounded-full overflow-hidden ${sizeHeights[size]}`}
        role="progressbar"
        aria-valuenow={clampedProgress}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={`h-full ${colorClasses[color]} transition-all duration-300 ease-out`}
          style={{ width: `${clampedProgress}%` }}
        />
      </div>
      {showPercentage && (
        <div className="mt-1 text-xs text-muted-foreground text-right tabular-nums">
          {Math.round(clampedProgress)}%
        </div>
      )}
    </div>
  )
}

/**
 * 스켈레톤과 함께 사용하는 로딩 상태 래퍼
 */
export function LoadingOverlay({
  isLoading,
  children,
  blur = true,
}: {
  isLoading: boolean
  children: React.ReactNode
  blur?: boolean
}) {
  if (!isLoading) return <>{children}</>

  return (
    <div className="relative">
      <div className={blur ? 'opacity-50 blur-[1px]' : 'opacity-50'}>
        {children}
      </div>
      <div className="absolute inset-0 flex items-center justify-center bg-background/50">
        <LoadingSpinner size="md" />
      </div>
    </div>
  )
}

/**
 * 버튼 로딩 상태
 */
export function ButtonLoadingState({
  isLoading,
  loadingText = '처리 중...',
  children,
}: {
  isLoading: boolean
  loadingText?: string
  children: React.ReactNode
}) {
  if (isLoading) {
    return (
      <>
        <InlineSpinner size="sm" />
        <span className="ml-2">{loadingText}</span>
      </>
    )
  }

  return <>{children}</>
}

/**
 * 배치 작업 진행률 표시
 * 여러 항목을 일괄 처리할 때 개별 진행률 표시
 */
export interface BatchItem {
  id: string | number
  label: string
  status: 'pending' | 'processing' | 'completed' | 'error'
  error?: string
}

export function BatchProgressIndicator({
  items,
  title = '일괄 처리 진행 중',
  onCancel,
  showDetails = true,
  maxVisibleItems = 5,
}: {
  items: BatchItem[]
  title?: string
  onCancel?: () => void
  showDetails?: boolean
  maxVisibleItems?: number
}) {
  const completed = items.filter(i => i.status === 'completed').length
  const errors = items.filter(i => i.status === 'error').length
  const total = items.length
  const progress = total > 0 ? (completed / total) * 100 : 0
  const currentItem = items.find(i => i.status === 'processing')

  return (
    <div
      className="bg-card border border-border rounded-lg p-4 shadow-sm"
      role="region"
      aria-label={title}
    >
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <InlineSpinner size="sm" />
          <span className="font-medium">{title}</span>
        </div>
        {onCancel && (
          <button
            onClick={onCancel}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors px-2 py-1 rounded hover:bg-muted"
            aria-label="작업 취소"
          >
            취소
          </button>
        )}
      </div>

      {/* 전체 진행률 */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-sm mb-1">
          <span className="text-muted-foreground">
            {completed}/{total} 완료
            {errors > 0 && (
              <span className="text-red-500 ml-2">({errors}개 실패)</span>
            )}
          </span>
          <span className="font-mono text-muted-foreground">
            {Math.round(progress)}%
          </span>
        </div>
        <ProgressBar
          progress={progress}
          showPercentage={false}
          color={errors > 0 ? 'warning' : 'primary'}
          size="md"
        />
      </div>

      {/* 현재 처리 중인 항목 */}
      {currentItem && (
        <div className="text-sm text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 px-3 py-2 rounded-md mb-3 flex items-center gap-2">
          <InlineSpinner size="sm" />
          <span className="truncate">{currentItem.label}</span>
        </div>
      )}

      {/* 상세 목록 (선택적) */}
      {showDetails && items.length > 0 && (
        <div className="space-y-1 max-h-40 overflow-y-auto">
          {items.slice(0, maxVisibleItems).map((item) => (
            <div
              key={item.id}
              className={`flex items-center gap-2 text-xs py-1 px-2 rounded ${
                item.status === 'completed'
                  ? 'text-green-600 dark:text-green-400'
                  : item.status === 'error'
                  ? 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20'
                  : item.status === 'processing'
                  ? 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/10'
                  : 'text-muted-foreground'
              }`}
            >
              {/* 상태 아이콘 */}
              <span className="flex-shrink-0">
                {item.status === 'completed' && '✓'}
                {item.status === 'error' && '✕'}
                {item.status === 'processing' && <InlineSpinner size="sm" />}
                {item.status === 'pending' && '○'}
              </span>
              {/* 라벨 */}
              <span className="truncate flex-1">{item.label}</span>
              {/* 에러 메시지 */}
              {item.error && (
                <span className="text-red-500 text-[10px] truncate max-w-[100px]" title={item.error}>
                  {item.error}
                </span>
              )}
            </div>
          ))}
          {items.length > maxVisibleItems && (
            <div className="text-xs text-muted-foreground text-center py-1">
              +{items.length - maxVisibleItems}개 더...
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * 간단한 배치 진행률 인라인 표시
 */
export function BatchProgressInline({
  current,
  total,
  label,
}: {
  current: number
  total: number
  label?: string
}) {
  const progress = total > 0 ? (current / total) * 100 : 0

  return (
    <div className="flex items-center gap-3 text-sm">
      <InlineSpinner size="sm" />
      <span className="text-muted-foreground">
        {label && <span className="mr-1">{label}</span>}
        <span className="font-mono">{current}/{total}</span>
      </span>
      <div className="w-24">
        <ProgressBar progress={progress} showPercentage={false} size="sm" />
      </div>
    </div>
  )
}

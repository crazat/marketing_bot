/**
 * ErrorState 컴포넌트
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] 에러 처리 고도화
 * - 에러 타입별 표시
 * - 다양한 액션 지원
 * - 심각도별 스타일
 */

import { useNavigate } from 'react-router-dom'
import {
  type ApiErrorType,
  type ErrorSeverity,
  parseApiError,
} from '@/utils/errorMessages'

interface ErrorAction {
  label: string
  onClick: () => void
  variant?: 'primary' | 'secondary'
}

interface ErrorStateProps {
  /** 에러 객체 (자동 파싱) */
  error?: unknown
  /** 직접 지정하는 에러 타입 */
  type?: ApiErrorType
  /** 에러 제목 (기본값: 에러 타입에 따라 자동) */
  title?: string
  /** 에러 메시지 */
  message?: string
  /** 심각도 (자동 설정 가능) */
  severity?: ErrorSeverity
  /** 재시도 콜백 */
  onRetry?: () => void
  /** 재시도 버튼 표시 여부 */
  showRetry?: boolean
  /** 추가 액션들 */
  actions?: ErrorAction[]
  /** 홈으로 버튼 표시 */
  showHome?: boolean
  /** 새로고침 버튼 표시 */
  showRefresh?: boolean
  /** 컴팩트 모드 */
  compact?: boolean
  /** 추가 클래스 */
  className?: string
}

/**
 * 에러 아이콘 SVG 컴포넌트
 */
export function ErrorIcon({ className = 'w-6 h-6' }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="currentColor"
      viewBox="0 0 20 20"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
        clipRule="evenodd"
      />
    </svg>
  )
}

/**
 * 경고 아이콘 SVG 컴포넌트
 */
export function WarningIcon({ className = 'w-6 h-6' }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="currentColor"
      viewBox="0 0 20 20"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
        clipRule="evenodd"
      />
    </svg>
  )
}

/**
 * 심각도별 스타일
 */
const severityStyles: Record<ErrorSeverity, { container: string; icon: string; button: string }> = {
  critical: {
    container: 'bg-danger-tint border-danger/30',
    icon: 'text-danger',
    button: 'bg-destructive hover:bg-destructive/90 focus:ring-danger',
  },
  error: {
    container: 'bg-danger-tint border-danger/30',
    icon: 'text-danger',
    button: 'bg-destructive hover:bg-destructive/90 focus:ring-danger',
  },
  warning: {
    container: 'bg-warn-tint border-warn/30',
    icon: 'text-warn',
    button: 'bg-warn hover:opacity-90 focus:ring-warn',
  },
  info: {
    container: 'bg-info-tint border-info/30',
    icon: 'text-info',
    button: 'bg-info hover:opacity-90 focus:ring-info',
  },
}

/**
 * 에러 타입별 제목
 */
const errorTitles: Record<ApiErrorType, string> = {
  NETWORK_ERROR: '네트워크 오류',
  TIMEOUT: '요청 시간 초과',
  UNAUTHORIZED: '인증 필요',
  FORBIDDEN: '접근 거부',
  NOT_FOUND: '찾을 수 없음',
  VALIDATION_ERROR: '입력 오류',
  SERVER_ERROR: '서버 오류',
  RATE_LIMIT: '요청 제한',
  DATABASE_ERROR: '데이터베이스 오류',
  UNKNOWN: '오류 발생',
}

export default function ErrorState({
  error,
  type,
  title,
  message,
  severity,
  onRetry,
  showRetry = true,
  actions = [],
  showHome = false,
  showRefresh = false,
  compact = false,
  className = '',
}: ErrorStateProps) {
  const navigate = useNavigate()

  // 에러 파싱
  const parsed = error ? parseApiError(error) : null
  const errorType = type || parsed?.type || 'UNKNOWN'
  const errorMessage = message || parsed?.userMessage || '오류가 발생했습니다.'
  const errorSeverity = severity || parsed?.config.severity || 'error'
  const errorTitle = title || errorTitles[errorType]
  const IconComp = errorSeverity === 'warning' ? WarningIcon : ErrorIcon

  const styles = severityStyles[errorSeverity]

  // 액션 핸들러
  const handleRefresh = () => window.location.reload()
  const handleHome = () => navigate('/')

  // 모든 액션 수집
  const allActions: ErrorAction[] = [...actions]

  if (showRetry && onRetry) {
    allActions.unshift({ label: '다시 시도', onClick: onRetry, variant: 'primary' })
  }
  if (showRefresh) {
    allActions.push({ label: '새로고침', onClick: handleRefresh, variant: 'secondary' })
  }
  if (showHome) {
    allActions.push({ label: '홈으로', onClick: handleHome, variant: 'secondary' })
  }

  if (compact) {
    return (
      <div
        className={`${styles.container} border rounded-lg p-4 ${className}`}
        role="alert"
        aria-live="polite"
      >
        <div className="flex items-start gap-3">
          <span className={`flex-shrink-0 ${styles.icon}`} aria-hidden="true"><IconComp className="w-6 h-6" /></span>
          <div className="flex-1 min-w-0">
            <h4 className={`font-semibold ${styles.icon}`}>{errorTitle}</h4>
            <p className="text-sm text-muted-foreground mt-1">{errorMessage}</p>
          </div>
          {allActions.length > 0 && (
            <button
              onClick={allActions[0].onClick}
              className={`px-3 py-1.5 text-sm text-white rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 ${styles.button}`}
            >
              {allActions[0].label}
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div
      className={`${styles.container} border rounded-lg p-6 text-center ${className}`}
      role="alert"
      aria-live="polite"
    >
      {/* 아이콘 */}
      <div className={`flex justify-center mb-3 ${styles.icon}`}>
        <IconComp className="w-12 h-12" />
      </div>

      {/* 제목 */}
      <h3 className={`text-lg font-semibold ${styles.icon} mb-2`}>
        {errorTitle}
      </h3>

      {/* 메시지 */}
      <p className="text-sm text-muted-foreground mb-4 max-w-md mx-auto">
        {errorMessage}
      </p>

      {/* 액션 버튼들 */}
      {allActions.length > 0 && (
        <div className="flex flex-wrap justify-center gap-2">
          {allActions.map((action, idx) => (
            <button
              key={idx}
              onClick={action.onClick}
              className={`px-4 py-2 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 ${
                action.variant === 'primary' || idx === 0
                  ? `${styles.button} text-white`
                  : 'bg-muted text-foreground hover:bg-muted/80 focus:ring-primary'
              }`}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * 인라인 에러 표시 (작은 영역용)
 */
export function InlineError({
  message,
  severity = 'error',
}: {
  message: string
  severity?: ErrorSeverity
}) {
  const colorClass = severity === 'warning' ? 'text-warn' : 'text-danger'

  return (
    <div className={`flex items-center gap-2 ${colorClass} text-sm`} role="alert">
      <ErrorIcon className="w-4 h-4 flex-shrink-0" />
      <span>{message}</span>
    </div>
  )
}

/**
 * 폼 에러 메시지 (입력 필드 하단용)
 */
export function FormErrorMessage({
  id,
  message,
}: {
  id?: string
  message: string
}) {
  return (
    <div
      id={id}
      className="p-3 bg-danger-tint border border-danger/30 rounded-lg text-danger text-sm flex items-center gap-2"
      role="alert"
    >
      <ErrorIcon className="w-4 h-4 flex-shrink-0" />
      <span>{message}</span>
    </div>
  )
}

/**
 * API 에러를 위한 간편 래퍼
 */
export function ApiErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown
  onRetry?: () => void
  className?: string
}) {
  return (
    <ErrorState
      error={error}
      onRetry={onRetry}
      showRetry={!!onRetry}
      showRefresh
      className={className}
    />
  )
}

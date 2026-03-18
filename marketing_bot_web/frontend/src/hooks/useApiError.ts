/**
 * API 에러 처리 통합 훅
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.1] 에러 처리 표준화
 * - Toast 알림과 에러 파싱 통합
 * - 재시도 로직 내장
 * - 에러 타입별 적절한 대응
 */

import { useCallback } from 'react'
import { useToast } from '@/components/ui/Toast'
import {
  parseApiError,
  getErrorMessage,
  isRetryableError,
  getRetryDelay,
  getMaxRetries,
  type ApiErrorType,
  type ParsedError,
} from '@/utils/errorMessages'

interface UseApiErrorOptions {
  /** 자동으로 Toast 표시 (기본: true) */
  showToast?: boolean
  /** 재시도 활성화 (기본: true) */
  enableRetry?: boolean
  /** 에러 콘솔 로깅 (기본: true) */
  logToConsole?: boolean
  /** 커스텀 에러 메시지 접두사 */
  prefix?: string
}

interface ErrorHandler {
  /** 에러 처리 및 Toast 표시 */
  handleError: (error: unknown, customMessage?: string) => ParsedError
  /** 에러 메시지만 반환 */
  getErrorMessage: (error: unknown) => string
  /** 재시도 가능 여부 확인 */
  isRetryable: (error: unknown) => boolean
  /** 재시도 실행 */
  withRetry: <T>(
    fn: () => Promise<T>,
    options?: { maxRetries?: number; onRetry?: (attempt: number, error: unknown) => void }
  ) => Promise<T>
  /** 에러 타입별 Toast 표시 */
  showError: (error: unknown, customMessage?: string) => void
  /** 특정 에러 타입인지 확인 */
  isErrorType: (error: unknown, type: ApiErrorType) => boolean
}

export function useApiError(options: UseApiErrorOptions = {}): ErrorHandler {
  const {
    showToast = true,
    enableRetry = true,
    logToConsole = true,
    prefix,
  } = options

  const toast = useToast()

  /**
   * 에러 처리 및 Toast 표시
   */
  const handleError = useCallback((error: unknown, customMessage?: string): ParsedError => {
    const parsed = parseApiError(error)

    if (logToConsole) {
      console.error(`[API Error] ${parsed.type}:`, parsed.technicalMessage)
    }

    if (showToast) {
      const message = customMessage || parsed.userMessage
      const finalMessage = prefix ? `${prefix}: ${message}` : message

      // 에러 심각도에 따라 Toast 타입 결정
      if (parsed.config.severity === 'critical' || parsed.config.severity === 'error') {
        toast.error(finalMessage, 5000) // 5초
      } else if (parsed.config.severity === 'warning') {
        toast.warning(finalMessage, 4000)
      } else {
        toast.info(finalMessage, 3000)
      }
    }

    return parsed
  }, [showToast, logToConsole, prefix, toast])

  /**
   * 에러 메시지만 반환
   */
  const getErrorMessageFn = useCallback((error: unknown): string => {
    return getErrorMessage(error)
  }, [])

  /**
   * 재시도 가능 여부 확인
   */
  const isRetryable = useCallback((error: unknown): boolean => {
    return isRetryableError(error)
  }, [])

  /**
   * 재시도 로직 포함 실행
   */
  const withRetry = useCallback(async <T>(
    fn: () => Promise<T>,
    retryOptions?: {
      maxRetries?: number
      onRetry?: (attempt: number, error: unknown) => void
    }
  ): Promise<T> => {
    if (!enableRetry) {
      return fn()
    }

    for (let attempt = 0; ; attempt++) {
      try {
        return await fn()
      } catch (error) {
        const maxRetries = retryOptions?.maxRetries ?? getMaxRetries(error)

        if (attempt >= maxRetries || !isRetryableError(error)) {
          throw error
        }

        retryOptions?.onRetry?.(attempt + 1, error)

        const delay = getRetryDelay(error, attempt)
        await new Promise(resolve => setTimeout(resolve, delay))
      }
    }
  }, [enableRetry])

  /**
   * 에러 타입별 Toast 표시
   */
  const showError = useCallback((error: unknown, customMessage?: string) => {
    handleError(error, customMessage)
  }, [handleError])

  /**
   * 특정 에러 타입인지 확인
   */
  const isErrorType = useCallback((error: unknown, type: ApiErrorType): boolean => {
    const parsed = parseApiError(error)
    return parsed.type === type
  }, [])

  return {
    handleError,
    getErrorMessage: getErrorMessageFn,
    isRetryable,
    withRetry,
    showError,
    isErrorType,
  }
}

/**
 * Mutation 에러 핸들러 생성 헬퍼
 * TanStack Query useMutation의 onError 콜백에 사용
 */
export function createMutationErrorHandler(
  toast: ReturnType<typeof useToast>,
  prefix?: string
) {
  return (error: unknown) => {
    const parsed = parseApiError(error)
    const message = prefix
      ? `${prefix}: ${parsed.userMessage}`
      : parsed.userMessage

    if (parsed.config.severity === 'critical' || parsed.config.severity === 'error') {
      toast.error(message, 5000)
    } else {
      toast.warning(message, 4000)
    }
  }
}

/**
 * 에러 boundary용 fallback 렌더러
 */
export function getErrorFallback(error: unknown): {
  title: string
  message: string
  type: ApiErrorType
} {
  const parsed = parseApiError(error)
  return {
    title: parsed.type === 'NETWORK_ERROR' ? '네트워크 오류' :
           parsed.type === 'SERVER_ERROR' ? '서버 오류' :
           '오류 발생',
    message: parsed.userMessage,
    type: parsed.type,
  }
}

export default useApiError

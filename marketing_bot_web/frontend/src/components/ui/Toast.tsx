/**
 * Toast 컴포넌트
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] Toast 개선
 * - 반응형 위치 (모바일: 상단, 데스크톱: 우측 하단)
 * - 최대 개수 제한
 * - 중복 메시지 방지
 */

import { createContext, useContext, useState, useCallback, useEffect, useRef, ReactNode } from 'react'
import { CheckCircle, XCircle, Info, AlertTriangle, X } from 'lucide-react'

type ToastType = 'success' | 'error' | 'info' | 'warning'

interface Toast {
  id: number
  type: ToastType
  message: string
  duration?: number
}

interface ToastContextType {
  toasts: Toast[]
  showToast: (type: ToastType, message: string, duration?: number) => void
  dismissToast: (id: number) => void
  dismissAll: () => void
}

interface ToastOptions {
  /** 최대 표시 개수 (기본: 5) */
  maxToasts?: number
  /** 중복 메시지 방지 (기본: true) */
  preventDuplicates?: boolean
  /** 기본 표시 시간 (ms) */
  defaultDuration?: number
}

const ToastContext = createContext<ToastContextType | null>(null)

let toastId = 0

export function ToastProvider({
  children,
  maxToasts = 5,
  preventDuplicates = true,
  defaultDuration = 4000,
}: { children: ReactNode } & ToastOptions) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const [isMobile, setIsMobile] = useState(false)
  // [Phase 2] setTimeout 타이머 추적 (cleanup용)
  const timerMapRef = useRef<Map<number, NodeJS.Timeout>>(new Map())

  // 화면 크기 감지
  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 640)
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  // [Phase 2] 컴포넌트 언마운트 시 모든 타이머 정리
  useEffect(() => {
    return () => {
      timerMapRef.current.forEach((timer) => clearTimeout(timer))
      timerMapRef.current.clear()
    }
  }, [])

  const showToast = useCallback((type: ToastType, message: string, duration?: number) => {
    // 중복 방지
    if (preventDuplicates) {
      const isDuplicate = toasts.some(t => t.type === type && t.message === message)
      if (isDuplicate) return
    }

    const id = ++toastId
    const actualDuration = duration ?? defaultDuration

    setToasts((prev) => {
      // 최대 개수 제한
      const newToasts = [...prev, { id, type, message, duration: actualDuration }]
      if (newToasts.length > maxToasts) {
        return newToasts.slice(-maxToasts)
      }
      return newToasts
    })

    if (actualDuration > 0) {
      // [Phase 2] 타이머 추적
      const timer = setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id))
        timerMapRef.current.delete(id)
      }, actualDuration)
      timerMapRef.current.set(id, timer)
    }
  }, [toasts, maxToasts, preventDuplicates, defaultDuration])

  const dismissToast = useCallback((id: number) => {
    // [Phase 2] 해당 타이머 정리
    const timer = timerMapRef.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timerMapRef.current.delete(id)
    }
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const dismissAll = useCallback(() => {
    // [Phase 2] 모든 타이머 정리
    timerMapRef.current.forEach((timer) => clearTimeout(timer))
    timerMapRef.current.clear()
    setToasts([])
  }, [])

  return (
    <ToastContext.Provider value={{ toasts, showToast, dismissToast, dismissAll }}>
      {children}
      <ToastContainer
        toasts={toasts}
        onDismiss={dismissToast}
        isMobile={isMobile}
        maxToasts={isMobile ? 3 : maxToasts}
      />
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }

  return {
    success: (message: string, duration?: number) =>
      context.showToast('success', message, duration),
    error: (message: string, duration?: number) =>
      context.showToast('error', message, duration),
    info: (message: string, duration?: number) =>
      context.showToast('info', message, duration),
    warning: (message: string, duration?: number) =>
      context.showToast('warning', message, duration),
    dismiss: context.dismissToast,
    dismissAll: context.dismissAll,
  }
}

const toastConfig: Record<ToastType, {
  bg: string
  Icon: typeof CheckCircle
  label: string
}> = {
  success: { bg: 'bg-green-500/90', Icon: CheckCircle, label: '성공' },
  error: { bg: 'bg-red-500/90', Icon: XCircle, label: '오류' },
  info: { bg: 'bg-blue-500/90', Icon: Info, label: '정보' },
  warning: { bg: 'bg-yellow-500/90', Icon: AlertTriangle, label: '경고' },
}

function ToastContainer({
  toasts,
  onDismiss,
  isMobile,
  maxToasts,
}: {
  toasts: Toast[]
  onDismiss: (id: number) => void
  isMobile: boolean
  maxToasts: number
}) {
  // 최대 개수만큼만 표시
  const displayToasts = toasts.slice(-maxToasts)

  if (displayToasts.length === 0) return null

  // 반응형 위치 클래스
  const positionClass = isMobile
    ? 'top-4 left-4 right-4'  // 모바일: 상단 전체 너비
    : 'bottom-4 right-4'       // 데스크톱: 우측 하단

  return (
    <div
      className={`fixed ${positionClass} z-50 flex flex-col gap-2`}
      role="region"
      aria-label="알림 메시지"
    >
      {displayToasts.map((toast) => {
        const { bg, Icon, label } = toastConfig[toast.type]
        return (
          <div
            key={toast.id}
            role="alert"
            aria-live={toast.type === 'error' ? 'assertive' : 'polite'}
            className={`
              ${bg}
              text-white px-4 py-3 rounded-lg shadow-lg
              flex items-center gap-3
              ${isMobile ? 'w-full' : 'min-w-[300px] max-w-[400px]'}
              animate-in ${isMobile ? 'slide-in-from-top' : 'slide-in-from-right'} duration-300
              cursor-pointer hover:brightness-110 transition-all
            `}
            onClick={() => onDismiss(toast.id)}
          >
            <Icon className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
            <div className="flex-1 min-w-0">
              <span className="sr-only">{label}: </span>
              <span className="block truncate">{toast.message}</span>
            </div>
            <button
              type="button"
              className="text-white/70 hover:text-white focus:outline-none focus:ring-2 focus:ring-white/50 rounded p-0.5 flex-shrink-0"
              onClick={(e) => {
                e.stopPropagation()
                onDismiss(toast.id)
              }}
              aria-label="알림 닫기"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )
      })}
    </div>
  )
}

/**
 * Promise 기반 Toast (비동기 작업용)
 */
export function usePromiseToast() {
  const toast = useToast()

  const promiseToast = useCallback(async <T,>(
    promise: Promise<T>,
    {
      loading = '처리 중...',
      success = '완료되었습니다',
      error = '오류가 발생했습니다',
    }: {
      loading?: string
      success?: string | ((data: T) => string)
      error?: string | ((err: unknown) => string)
    }
  ): Promise<T> => {
    const loadingId = toastId + 1
    toast.info(loading, 0) // 0 = 자동 dismiss 안함

    try {
      const result = await promise
      toast.dismiss(loadingId)
      const successMessage = typeof success === 'function' ? success(result) : success
      toast.success(successMessage)
      return result
    } catch (err) {
      toast.dismiss(loadingId)
      const errorMessage = typeof error === 'function' ? error(err) : error
      toast.error(errorMessage)
      throw err
    }
  }, [toast])

  return promiseToast
}

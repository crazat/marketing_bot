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

interface ToastAction {
  label: string
  onClick: () => void
}

interface Toast {
  id: number
  type: ToastType
  message: string
  duration?: number
  action?: ToastAction
  count?: number
}

interface ToastContextType {
  toasts: Toast[]
  showToast: (type: ToastType, message: string, duration?: number, action?: ToastAction) => void
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
  // 4000ms → 5500ms: 연속 액션(A/S/D 키로 바이럴 처리 등) 시 마지막 토스트가 너무 빨리 사라지는 문제 완화
  defaultDuration = 5500,
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

  const showToast = useCallback((type: ToastType, message: string, duration?: number, action?: ToastAction) => {
    // 중복 방지 (action 토스트는 예외 — undo는 개별 타겟마다 독립)
    if (preventDuplicates && !action) {
      const isDuplicate = toasts.some(t => t.type === type && t.message === message)
      if (isDuplicate) return
    }

    const id = ++toastId
    const actualDuration = duration ?? defaultDuration

    // [Y7] 토스트 그룹화 — 같은 type의 연속 토스트를 묶어서 표시
    // 예: "⏭️ 건너뜀" 여러 번 → "⏭️ 건너뜀 (3건)"
    setToasts((prev) => {
      const last = prev[prev.length - 1]
      const groupable = !action && last && last.type === type && last.message === message
      if (groupable) {
        // 기존 토스트의 count 증가, 새 토스트 생성 안 함
        const oldTimer = timerMapRef.current.get(last.id)
        if (oldTimer) {
          clearTimeout(oldTimer)
          timerMapRef.current.delete(last.id)
        }
        const updated = prev.slice(0, -1).concat({
          ...last,
          count: (last.count ?? 1) + 1,
        })
        if (actualDuration > 0) {
          const timer = setTimeout(() => {
            setToasts((p) => p.filter((t) => t.id !== last.id))
            timerMapRef.current.delete(last.id)
          }, actualDuration)
          timerMapRef.current.set(last.id, timer)
        }
        return updated
      }

      // 최대 개수 제한
      const newToasts = [...prev, { id, type, message, duration: actualDuration, action, count: 1 }]
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
    // [U1] 액션 가능한 토스트 — Undo 등
    action: (
      type: ToastType,
      message: string,
      action: ToastAction,
      duration = 6000,
    ) => context.showToast(type, message, duration, action),
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

  // [DD1] 반응형 위치 — 모바일 햄버거 헤더(h-16=64px) 아래, 탭바(h-14=56px) 위
  const positionClass = isMobile
    ? 'top-20 left-4 right-4'  // 모바일: 햄버거 헤더 아래
    : 'bottom-4 right-4'        // 데스크톱: 우측 하단

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
              <span className="block truncate">
                {toast.message}
                {toast.count && toast.count > 1 && (
                  <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded-full bg-white/25 text-[11px] font-bold tabular-nums">
                    ×{toast.count}
                  </span>
                )}
              </span>
            </div>
            {toast.action && (
              <button
                type="button"
                className="text-white font-semibold underline underline-offset-2 hover:brightness-125 px-1.5 flex-shrink-0 text-sm"
                onClick={(e) => {
                  e.stopPropagation()
                  toast.action!.onClick()
                  onDismiss(toast.id)
                }}
              >
                {toast.action.label}
              </button>
            )}
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

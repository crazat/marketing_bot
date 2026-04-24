import { useCallback, useEffect, useRef, useState } from 'react'

const STORAGE_KEY = 'marketing-bot-offline-queue-v1'
const MAX_RETRY = 3

export interface QueuedAction {
  id: string
  /** Endpoint kind — 확장 가능 */
  kind: 'viral_action'
  /** 실행 인자 */
  payload: {
    target_id: string | number
    action: 'approve' | 'skip' | 'delete' | 'reopen'
    comment?: string
    skip_reason?: string
    skip_note?: string
  }
  retries: number
  queuedAt: number
}

function loadQueue(): QueuedAction[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveQueue(queue: QueuedAction[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(queue))
  } catch {
    // ignore
  }
}

/**
 * [Y5] 오프라인 액션 큐
 *
 * 오프라인 중 enqueue된 액션을 localStorage에 저장.
 * 온라인 복귀 시 자동으로 flush — 순차 처리 + 실패 재시도.
 *
 * @param executor — 실제 API 호출 함수. 실패 시 throw.
 */
export function useOfflineQueue(
  executor: (action: QueuedAction) => Promise<void>,
  options?: {
    onFlushStart?: (count: number) => void
    onFlushSuccess?: (count: number) => void
    onActionFailed?: (action: QueuedAction, error: unknown) => void
  },
) {
  const [queue, setQueue] = useState<QueuedAction[]>([])
  const [isOnline, setIsOnline] = useState(typeof navigator !== 'undefined' ? navigator.onLine : true)
  const [isFlushing, setIsFlushing] = useState(false)
  // [DD4] StrictMode 이중 마운트/이중 호출 안전 — ref 기반 잠금
  const isFlushingRef = useRef(false)
  const executorRef = useRef(executor)
  const optionsRef = useRef(options)

  useEffect(() => {
    executorRef.current = executor
    optionsRef.current = options
  }, [executor, options])

  useEffect(() => {
    setQueue(loadQueue())
  }, [])

  const enqueue = useCallback(
    (payload: QueuedAction['payload'], kind: QueuedAction['kind'] = 'viral_action') => {
      const action: QueuedAction = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        kind,
        payload,
        retries: 0,
        queuedAt: Date.now(),
      }
      setQueue((prev) => {
        const next = [...prev, action]
        saveQueue(next)
        return next
      })
      return action
    },
    [],
  )

  const flush = useCallback(async () => {
    // [DD4] ref 잠금으로 StrictMode 이중 실행 방지
    if (isFlushingRef.current) return
    const current = loadQueue()
    if (current.length === 0) return

    isFlushingRef.current = true
    setIsFlushing(true)
    optionsRef.current?.onFlushStart?.(current.length)

    const remaining: QueuedAction[] = []
    let successCount = 0

    try {
      for (const action of current) {
        try {
          await executorRef.current(action)
          successCount += 1
        } catch (err) {
          if (action.retries + 1 >= MAX_RETRY) {
            optionsRef.current?.onActionFailed?.(action, err)
          } else {
            remaining.push({ ...action, retries: action.retries + 1 })
          }
        }
      }

      saveQueue(remaining)
      setQueue(remaining)
      if (successCount > 0) {
        optionsRef.current?.onFlushSuccess?.(successCount)
      }
    } finally {
      setIsFlushing(false)
      isFlushingRef.current = false
    }
  }, [])

  // 온라인 상태 감지
  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true)
      void flush()
    }
    const handleOffline = () => setIsOnline(false)

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    // 마운트 시 한 번 시도 (온라인이지만 큐에 잔여가 있을 수 있음)
    if (navigator.onLine && loadQueue().length > 0) {
      void flush()
    }

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [flush])

  // [EE7] 큐 수동 비우기 — 영구 실패 항목 정리
  const clearQueue = useCallback(() => {
    saveQueue([])
    setQueue([])
  }, [])

  const removeItem = useCallback((id: string) => {
    setQueue((prev) => {
      const next = prev.filter((a) => a.id !== id)
      saveQueue(next)
      return next
    })
  }, [])

  return { queue, isOnline, isFlushing, enqueue, flush, clearQueue, removeItem }
}

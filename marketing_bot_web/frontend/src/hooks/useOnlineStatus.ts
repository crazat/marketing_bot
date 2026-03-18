import { useState, useEffect, useCallback, useRef } from 'react'

interface UseOnlineStatusReturn {
  isOnline: boolean
  wasOffline: boolean // 오프라인이었다가 복구됨
  lastOnlineAt: Date | null
}

/**
 * 네트워크 상태 감지 훅
 *
 * @example
 * const { isOnline, wasOffline } = useOnlineStatus()
 *
 * if (!isOnline) {
 *   return <OfflineBanner />
 * }
 */
export function useOnlineStatus(): UseOnlineStatusReturn {
  const [isOnline, setIsOnline] = useState<boolean>(
    typeof navigator !== 'undefined' ? navigator.onLine : true
  )
  const [wasOffline, setWasOffline] = useState(false)
  const [lastOnlineAt, setLastOnlineAt] = useState<Date | null>(null)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)

  const handleOnline = useCallback(() => {
    setIsOnline(true)
    setLastOnlineAt(new Date())
    // 오프라인이었다가 복구되면 wasOffline을 true로 설정
    setWasOffline(true)

    // 기존 타이머 정리
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }

    // 5초 후 wasOffline 초기화
    timeoutRef.current = setTimeout(() => {
      setWasOffline(false)
    }, 5000)
  }, [])

  const handleOffline = useCallback(() => {
    setIsOnline(false)
  }, [])

  useEffect(() => {
    // 초기 상태
    setIsOnline(navigator.onLine)
    if (navigator.onLine) {
      setLastOnlineAt(new Date())
    }

    // 이벤트 리스너 등록
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
      // [성능 최적화] setTimeout cleanup으로 메모리 누수 방지
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [handleOnline, handleOffline])

  return {
    isOnline,
    wasOffline,
    lastOnlineAt,
  }
}

export default useOnlineStatus

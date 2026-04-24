import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useOnlineStatus } from '@/hooks/useOnlineStatus'
import { useNetworkStatus } from '@/hooks/useNetworkStatus'
import { WifiOff, Wifi, RefreshCw, SignalLow } from 'lucide-react'

/**
 * 오프라인 상태 배너
 *
 * 네트워크 연결이 끊어지면 화면 상단에 경고 배너를 표시합니다.
 * 연결이 복구되면 자동으로 데이터를 새로고침하고 성공 메시지를 표시합니다.
 */
export function OfflineBanner() {
  const { isOnline, wasOffline } = useOnlineStatus()
  const { isSlowConnection, effectiveType } = useNetworkStatus()
  const queryClient = useQueryClient()
  const [isRefreshing, setIsRefreshing] = useState(false)
  const hasRefreshedRef = useRef(false)
  const resetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 오프라인 → 온라인 복구 시 자동 새로고침
  useEffect(() => {
    if (isOnline && wasOffline && !hasRefreshedRef.current) {
      hasRefreshedRef.current = true
      setIsRefreshing(true)

      // 모든 활성 쿼리를 새로고침
      queryClient.refetchQueries({
        type: 'active',
        stale: true,
      }).finally(() => {
        setIsRefreshing(false)
        // 5초 후에 다시 새로고침 가능하도록 리셋
        if (resetTimerRef.current) {
          clearTimeout(resetTimerRef.current)
        }
        resetTimerRef.current = setTimeout(() => {
          hasRefreshedRef.current = false
        }, 5000)
      })
    }

    // cleanup: 컴포넌트 언마운트 시 타이머 정리
    return () => {
      if (resetTimerRef.current) {
        clearTimeout(resetTimerRef.current)
      }
    }
  }, [isOnline, wasOffline, queryClient])

  // [CC4] 저속 연결 경고 — 오프라인은 아니지만 2g/slow-2g
  if (isOnline && !wasOffline && !isRefreshing && isSlowConnection) {
    return (
      <div
        className="fixed top-0 left-0 right-0 z-50 bg-amber-500 text-white py-2 px-4 text-center text-sm font-medium flex items-center justify-center gap-2"
        role="status"
        aria-live="polite"
      >
        <SignalLow className="w-4 h-4" />
        <span>저속 연결 감지 ({effectiveType ?? '느린 네트워크'}) — 일부 기능이 느릴 수 있습니다</span>
      </div>
    )
  }

  // 온라인이고 최근 오프라인이 아니었으면 아무것도 표시 안 함
  if (isOnline && !wasOffline && !isRefreshing) {
    return null
  }

  // 오프라인 → 온라인 복구 후 새로고침 중
  if (isOnline && isRefreshing) {
    return (
      <div
        className="fixed top-0 left-0 right-0 z-50 bg-blue-500 text-white py-2 px-4 text-center text-sm font-medium flex items-center justify-center gap-2"
        role="alert"
        aria-live="polite"
      >
        <RefreshCw className="w-4 h-4 animate-spin" />
        <span>데이터를 새로고침하고 있습니다...</span>
      </div>
    )
  }

  // 오프라인 → 온라인 복구 완료
  if (isOnline && wasOffline) {
    return (
      <div
        className="fixed top-0 left-0 right-0 z-50 bg-green-500 text-white py-2 px-4 text-center text-sm font-medium flex items-center justify-center gap-2 animate-pulse"
        role="alert"
        aria-live="polite"
      >
        <Wifi className="w-4 h-4" />
        <span>네트워크 연결이 복구되었습니다. 데이터가 최신 상태입니다.</span>
      </div>
    )
  }

  // 오프라인 상태
  return (
    <div
      className="fixed top-0 left-0 right-0 z-50 bg-red-500 text-white py-2 px-4 text-center text-sm font-medium flex items-center justify-center gap-2"
      role="alert"
      aria-live="assertive"
    >
      <WifiOff className="w-4 h-4" />
      <span>네트워크 연결이 끊어졌습니다. 일부 기능이 제한될 수 있습니다.</span>
    </div>
  )
}

export default OfflineBanner

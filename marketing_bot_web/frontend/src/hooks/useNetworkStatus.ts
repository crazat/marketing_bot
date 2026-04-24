import { useEffect, useState } from 'react'

export interface NetworkStatus {
  online: boolean
  /** Network Information API — 지원 브라우저만 */
  effectiveType?: '2g' | '3g' | '4g' | 'slow-2g' | string
  downlink?: number
  rtt?: number
  /** 저대역 감지 — 2g/slow-2g 또는 RTT 600ms+ */
  isSlowConnection: boolean
}

interface NavigatorWithConnection extends Navigator {
  connection?: {
    effectiveType?: string
    downlink?: number
    rtt?: number
    addEventListener?: (evt: string, cb: () => void) => void
    removeEventListener?: (evt: string, cb: () => void) => void
  }
}

function read(): NetworkStatus {
  if (typeof navigator === 'undefined') {
    return { online: true, isSlowConnection: false }
  }
  const conn = (navigator as NavigatorWithConnection).connection
  const online = navigator.onLine
  const effectiveType = conn?.effectiveType
  const downlink = conn?.downlink
  const rtt = conn?.rtt
  const isSlow =
    effectiveType === '2g' ||
    effectiveType === 'slow-2g' ||
    (typeof rtt === 'number' && rtt >= 600)
  return {
    online,
    effectiveType,
    downlink,
    rtt,
    isSlowConnection: isSlow,
  }
}

/**
 * [AA3] 전역 네트워크 상태 훅
 *
 * - navigator.onLine + Network Information API 통합
 * - 저대역 감지 (2g/slow-2g 또는 RTT 600ms+)
 * - Provider 없이 각 페이지에서 직접 호출
 */
export function useNetworkStatus(): NetworkStatus {
  const [status, setStatus] = useState<NetworkStatus>(() => read())

  useEffect(() => {
    const handler = () => setStatus(read())

    window.addEventListener('online', handler)
    window.addEventListener('offline', handler)

    const conn = (navigator as NavigatorWithConnection).connection
    conn?.addEventListener?.('change', handler)

    return () => {
      window.removeEventListener('online', handler)
      window.removeEventListener('offline', handler)
      conn?.removeEventListener?.('change', handler)
    }
  }, [])

  return status
}

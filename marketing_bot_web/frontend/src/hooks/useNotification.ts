import { useState, useEffect, useCallback } from 'react'

type NotificationPermission = 'default' | 'granted' | 'denied'

interface NotificationOptions {
  body?: string
  icon?: string
  tag?: string
  requireInteraction?: boolean
  silent?: boolean
}

interface UseNotificationReturn {
  permission: NotificationPermission
  isSupported: boolean
  requestPermission: () => Promise<NotificationPermission>
  showNotification: (title: string, options?: NotificationOptions) => void
}

const DEFAULT_ICON = '/favicon.ico'

export function useNotification(): UseNotificationReturn {
  const [permission, setPermission] = useState<NotificationPermission>('default')
  const isSupported = typeof window !== 'undefined' && 'Notification' in window

  useEffect(() => {
    if (isSupported) {
      setPermission(Notification.permission)
    }
  }, [isSupported])

  const requestPermission = useCallback(async (): Promise<NotificationPermission> => {
    if (!isSupported) {
      console.warn('브라우저가 알림을 지원하지 않습니다.')
      return 'denied'
    }

    try {
      const result = await Notification.requestPermission()
      setPermission(result)
      return result
    } catch (error) {
      console.error('알림 권한 요청 실패:', error)
      return 'denied'
    }
  }, [isSupported])

  const showNotification = useCallback(
    (title: string, options?: NotificationOptions) => {
      if (!isSupported) {
        console.warn('브라우저가 알림을 지원하지 않습니다.')
        return
      }

      if (permission !== 'granted') {
        console.warn('알림 권한이 없습니다.')
        return
      }

      // 페이지가 보이는 상태면 알림을 표시하지 않음 (토스트로 충분)
      if (document.visibilityState === 'visible') {
        return
      }

      try {
        const notification = new Notification(title, {
          icon: options?.icon || DEFAULT_ICON,
          body: options?.body,
          tag: options?.tag,
          requireInteraction: options?.requireInteraction ?? false,
          silent: options?.silent ?? false,
        })

        // 알림 클릭 시 해당 탭으로 포커스
        notification.onclick = () => {
          window.focus()
          notification.close()
        }

        // 5초 후 자동 닫기
        setTimeout(() => {
          notification.close()
        }, 5000)
      } catch (error) {
        console.error('알림 표시 실패:', error)
      }
    },
    [isSupported, permission]
  )

  return {
    permission,
    isSupported,
    requestPermission,
    showNotification,
  }
}

// 알림 타입별 헬퍼 함수들
export function createScanCompleteNotification(moduleName: string, resultCount?: number) {
  const body = resultCount !== undefined
    ? `${resultCount}개의 결과를 찾았습니다.`
    : '스캔이 완료되었습니다.'

  return {
    title: `${moduleName} 완료`,
    options: {
      body,
      tag: `scan-${moduleName}`,
      icon: '/favicon.ico',
    },
  }
}

export function createNewLeadNotification(platform: string, count: number) {
  return {
    title: '새로운 리드 발견',
    options: {
      body: `${platform}에서 ${count}개의 새로운 리드를 발견했습니다.`,
      tag: `lead-${platform}`,
      icon: '/favicon.ico',
    },
  }
}

export function createAlertNotification(message: string, severity: 'warning' | 'critical') {
  return {
    title: severity === 'critical' ? '긴급 알림' : '주의 알림',
    options: {
      body: message,
      tag: `alert-${Date.now()}`,
      icon: '/favicon.ico',
      requireInteraction: severity === 'critical',
    },
  }
}

// [Phase 6.0] 핫리드 알림
export function createHotLeadNotification(leadTitle: string, platform: string, score: number) {
  return {
    title: '🔥 Hot Lead 발견!',
    options: {
      body: `[${platform}] ${leadTitle} (점수: ${score}점)`,
      tag: `hot-lead-${Date.now()}`,
      icon: '/favicon.ico',
      requireInteraction: true, // 사용자가 직접 닫아야 함
    },
  }
}

// [Phase 6.0] 순위 변동 알림
export function createRankChangeNotification(keyword: string, oldRank: number, newRank: number) {
  const isImproved = newRank < oldRank
  return {
    title: isImproved ? '📈 순위 상승!' : '📉 순위 하락',
    options: {
      body: `"${keyword}" ${oldRank}위 → ${newRank}위`,
      tag: `rank-${keyword}`,
      icon: '/favicon.ico',
    },
  }
}

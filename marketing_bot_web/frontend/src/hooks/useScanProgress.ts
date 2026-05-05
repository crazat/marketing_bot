/**
 * SSE 기반 실시간 스캔 진행률 훅
 *
 * 사용 예:
 * ```tsx
 * const { progress, status, message, isRunning, connect, disconnect } = useScanProgress('place_sniper');
 *
 * // 스캔 시작 시 연결
 * const handleStartScan = () => {
 *   startScan();
 *   connect();
 * };
 * ```
 */

import { useState, useEffect, useCallback, useRef } from 'react'

export interface ScanProgressData {
  status: 'idle' | 'running' | 'completed' | 'error' | 'timeout'
  progress: number
  message: string
  isRunning: boolean
}

interface UseScanProgressOptions {
  /** 자동 연결 여부 (기본: false) */
  autoConnect?: boolean
  /** 완료 후 자동 연결 해제 여부 (기본: true) */
  autoDisconnectOnComplete?: boolean
  /** 완료 시 콜백 */
  onComplete?: () => void
  /** 에러 시 콜백 */
  onError?: (error: string) => void
}

export function useScanProgress(
  moduleName: string,
  options: UseScanProgressOptions = {}
) {
  const {
    autoConnect = false,
    autoDisconnectOnComplete = true,
    onComplete,
    onError,
  } = options

  const [data, setData] = useState<ScanProgressData>({
    status: 'idle',
    progress: 0,
    message: '대기 중',
    isRunning: false,
  })

  const [isConnected, setIsConnected] = useState(false)
  const eventSourceRef = useRef<EventSource | null>(null)

  const connect = useCallback(() => {
    // 이미 연결된 경우 무시
    if (eventSourceRef.current) {
      return
    }

    const url = `/api/hud/mission/${moduleName}/progress/stream`
    const eventSource = new EventSource(url)

    eventSource.onopen = () => {
      setIsConnected(true)
    }

    eventSource.onmessage = (event) => {
      try {
        const progressData: ScanProgressData = JSON.parse(event.data)
        setData({
          status: progressData.status,
          progress: progressData.progress,
          message: progressData.message,
          isRunning: progressData.isRunning ?? progressData.status === 'running',
        })

        // 완료 시 콜백 실행
        if (progressData.status === 'completed') {
          onComplete?.()
          if (autoDisconnectOnComplete) {
            eventSource.close()
            eventSourceRef.current = null
            setIsConnected(false)
          }
        }

        // 에러 시 콜백 실행
        if (progressData.status === 'error') {
          onError?.(progressData.message)
        }
      } catch (e) {
        console.error('SSE 데이터 파싱 오류:', e)
      }
    }

    eventSource.onerror = () => {
      // 연결 오류 시 재연결 시도하지 않음 (EventSource 기본 동작은 재연결)
      eventSource.close()
      eventSourceRef.current = null
      setIsConnected(false)
      setData((prev) => ({
        ...prev,
        status: 'error',
        message: '연결 오류',
        isRunning: false,
      }))
    }

    eventSourceRef.current = eventSource
  }, [moduleName, autoDisconnectOnComplete, onComplete, onError])

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
      setIsConnected(false)
    }
  }, [])

  // 자동 연결
  useEffect(() => {
    if (autoConnect) {
      connect()
    }

    return () => {
      disconnect()
    }
  }, [autoConnect, connect, disconnect])

  // 모듈명 변경 시 재연결
  useEffect(() => {
    if (isConnected) {
      disconnect()
      connect()
    }
  }, [moduleName])

  return {
    ...data,
    isConnected,
    connect,
    disconnect,
  }
}

/**
 * Polling 방식 스캔 진행률 훅 (SSE 미지원 환경용)
 */
export function useScanProgressPolling(
  moduleName: string,
  options: { interval?: number; enabled?: boolean } = {}
) {
  const { interval = 2000, enabled = false } = options

  const [data, setData] = useState<ScanProgressData>({
    status: 'idle',
    progress: 0,
    message: '대기 중',
    isRunning: false,
  })

  useEffect(() => {
    if (!enabled) return

    const fetchProgress = async () => {
      try {
        const response = await fetch(`/api/hud/mission/${moduleName}/progress`)
        if (response.ok) {
          const progressData = await response.json()
          setData({
            status: progressData.status,
            progress: progressData.progress,
            message: progressData.message,
            isRunning: progressData.is_running ?? progressData.status === 'running',
          })
        }
      } catch (error) {
        console.error('진행률 조회 오류:', error)
      }
    }

    // 즉시 한 번 실행
    fetchProgress()

    // 주기적 polling
    const intervalId = setInterval(fetchProgress, interval)

    return () => clearInterval(intervalId)
  }, [moduleName, interval, enabled])

  return data
}

export default useScanProgress

import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

// 개발 환경에서만 로그 출력
const isDev = import.meta.env.DEV
const devLog = (...args: unknown[]) => isDev && console.log(...args)
const devError = (...args: unknown[]) => isDev && console.error(...args)

interface WebSocketMessage {
  type: string
  data: any
}

// Pathfinder 로그 이벤트 타입
export interface PathfinderLogEvent {
  line: string
  timestamp: string
}

export interface PathfinderStatusEvent {
  status: 'idle' | 'running' | 'completed'
  message: string
  mode?: 'total_war' | 'legion'
  updated_at?: string
}

// 커스텀 이벤트 이름
export const PATHFINDER_LOG_EVENT = 'pathfinder-log'
export const PATHFINDER_STATUS_EVENT = 'pathfinder-status'

export function useWebSocket() {
  const [isConnected, setIsConnected] = useState(false)
  const [isReconnecting, setIsReconnecting] = useState(false)
  const [reconnectAttempt, setReconnectAttempt] = useState(0)
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null)
  const [pathfinderStatus, setPathfinderStatus] = useState<PathfinderStatusEvent>({
    status: 'idle',
    message: '대기 중'
  })
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const queryClient = useQueryClient()
  const maxReconnectAttempts = 10

  const connect = (isManualReconnect = false) => {
    // 수동 재연결 시 시도 횟수 초기화
    if (isManualReconnect) {
      setReconnectAttempt(0)
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws`)

    // [성능 최적화] pingInterval을 외부 변수로 관리하여 onclose에서 정리
    let pingInterval: NodeJS.Timeout | null = null

    ws.onopen = () => {
      devLog('✅ WebSocket 연결됨')
      setIsConnected(true)
      setIsReconnecting(false)
      setReconnectAttempt(0)

      // Ping 전송 (연결 유지)
      pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send('ping')
        }
      }, 30000)
    }

    ws.onmessage = (event) => {
      try {
        if (event.data === 'pong') return

        const message: WebSocketMessage = JSON.parse(event.data)
        setLastMessage(message)

        // 메시지 타입에 따라 자동으로 캐시 무효화
        handleMessage(message)
      } catch (error) {
        devError('WebSocket 메시지 파싱 오류:', error)
      }
    }

    ws.onerror = (error) => {
      devError('WebSocket 오류:', error)
    }

    // [성능 최적화] 단일 onclose 핸들러로 통합
    ws.onclose = () => {
      devLog('❌ WebSocket 연결 종료')
      setIsConnected(false)

      // pingInterval 정리
      if (pingInterval) {
        clearInterval(pingInterval)
        pingInterval = null
      }

      // 최대 재연결 시도 횟수 확인
      setReconnectAttempt(prev => {
        const newAttempt = prev + 1
        if (newAttempt <= maxReconnectAttempts) {
          setIsReconnecting(true)
          // 지수 백오프: 1초, 2초, 4초, 8초... (최대 30초)
          const delay = Math.min(1000 * Math.pow(2, prev), 30000)
          devLog(`🔄 WebSocket 재연결 시도 ${newAttempt}/${maxReconnectAttempts} (${delay/1000}초 후)`)

          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, delay)
        } else {
          setIsReconnecting(false)
          devLog('❌ WebSocket 재연결 실패: 최대 시도 횟수 초과')
        }
        return newAttempt
      })
    }

    wsRef.current = ws
  }

  const handleMessage = (message: WebSocketMessage) => {
    const { type, data } = message

    switch (type) {
      case 'hud_update':
        // HUD 메트릭 업데이트
        queryClient.invalidateQueries({ queryKey: ['hud-metrics'] })
        queryClient.invalidateQueries({ queryKey: ['system-status'] })
        break

      case 'pathfinder_complete':
        // Pathfinder 실행 완료
        queryClient.invalidateQueries({ queryKey: ['pathfinder-stats'] })
        queryClient.invalidateQueries({ queryKey: ['pathfinder-keywords'] })
        queryClient.invalidateQueries({ queryKey: ['pathfinder-clusters'] })
        break

      case 'pathfinder_progress':
        // Pathfinder 진행 상황 업데이트
        // 진행률 표시 등에 사용 가능
        devLog('Pathfinder 진행:', data)
        break

      case 'ranking_update':
        // 순위 업데이트
        queryClient.invalidateQueries({ queryKey: ['ranking-keywords'] })
        queryClient.invalidateQueries({ queryKey: ['ranking-trends'] })
        break

      case 'new_lead':
        // 새 리드 발견
        queryClient.invalidateQueries({ queryKey: ['leads'] })
        queryClient.invalidateQueries({ queryKey: ['leads-stats'] })
        break

      case 'viral_target_update':
        // 바이럴 타겟 업데이트
        queryClient.invalidateQueries({ queryKey: ['viral-targets'] })
        queryClient.invalidateQueries({ queryKey: ['viral-stats'] })
        break

      case 'scheduler_status':
        // 스케줄러 상태 변경
        queryClient.invalidateQueries({ queryKey: ['system-status'] })
        break

      case 'pathfinder_log':
        // Pathfinder 실시간 로그
        {
          const logEvent = new CustomEvent(PATHFINDER_LOG_EVENT, {
            detail: {
              line: data.line,
              timestamp: data.timestamp || new Date().toISOString()
            }
          })
          window.dispatchEvent(logEvent)
        }
        break

      case 'pathfinder_status':
        // Pathfinder 상태 변경 (running/completed/idle)
        setPathfinderStatus(data)
        {
          const statusEvent = new CustomEvent(PATHFINDER_STATUS_EVENT, {
            detail: data
          })
          window.dispatchEvent(statusEvent)
        }

        // 완료 시 쿼리 무효화
        if (data.status === 'completed') {
          queryClient.invalidateQueries({ queryKey: ['pathfinder-stats'] })
          queryClient.invalidateQueries({ queryKey: ['pathfinder-keywords'] })
          queryClient.invalidateQueries({ queryKey: ['pathfinder-clusters'] })
        }
        break

      default:
        devLog('알 수 없는 메시지 타입:', type)
    }
  }

  const disconnect = () => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }

  useEffect(() => {
    connect()

    return () => {
      disconnect()
    }
  }, [])

  return {
    isConnected,
    isReconnecting,
    reconnectAttempt,
    maxReconnectAttempts,
    lastMessage,
    pathfinderStatus,
    disconnect,
    reconnect: () => connect(true)
  }
}

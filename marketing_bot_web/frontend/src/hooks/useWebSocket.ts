import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { resetApiKeyToBundledDefault, withApiKeyQuery } from '@/services/api/base'

const isDev = import.meta.env.DEV
const devLog = (...args: unknown[]) => isDev && console.log(...args)
const devError = (...args: unknown[]) => isDev && console.error(...args)

interface WebSocketMessage {
  type: string
  data: any
}

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

export const PATHFINDER_LOG_EVENT = 'pathfinder-log'
export const PATHFINDER_STATUS_EVENT = 'pathfinder-status'

export function useWebSocket() {
  const [isConnected, setIsConnected] = useState(false)
  const [isReconnecting, setIsReconnecting] = useState(false)
  const [reconnectAttempt, setReconnectAttempt] = useState(0)
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null)
  const [pathfinderStatus, setPathfinderStatus] = useState<PathfinderStatusEvent>({
    status: 'idle',
    message: 'Idle',
  })
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const shouldReconnectRef = useRef(true)
  const isMountedRef = useRef(false)
  const queryClient = useQueryClient()
  const maxReconnectAttempts = 10

  const connect = (isManualReconnect = false) => {
    if (!isMountedRef.current) return

    if (isManualReconnect) {
      setReconnectAttempt(0)
    }
    shouldReconnectRef.current = true

    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(withApiKeyQuery(`${protocol}//${window.location.host}/ws`))
    let pingInterval: NodeJS.Timeout | null = null

    ws.onopen = () => {
      if (!isMountedRef.current) {
        ws.close()
        return
      }
      devLog('WebSocket connected')
      setIsConnected(true)
      setIsReconnecting(false)
      setReconnectAttempt(0)

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
        handleMessage(message)
      } catch (error) {
        devError('WebSocket message parse error:', error)
      }
    }

    ws.onerror = (error) => {
      devError('WebSocket error:', error)
    }

    ws.onclose = (event) => {
      if (wsRef.current === ws) {
        wsRef.current = null
      }
      devLog('WebSocket closed')
      setIsConnected(false)

      if (pingInterval) {
        clearInterval(pingInterval)
        pingInterval = null
      }

      if ((event.code === 1006 || event.code === 1008) && resetApiKeyToBundledDefault()) {
        if (shouldReconnectRef.current && isMountedRef.current) {
          setIsReconnecting(true)
          reconnectTimeoutRef.current = setTimeout(() => {
            if (shouldReconnectRef.current && isMountedRef.current) {
              connect()
            }
          }, 250)
        }
        return
      }

      if (!shouldReconnectRef.current || !isMountedRef.current || event.code === 1008) {
        setIsReconnecting(false)
        return
      }

      setReconnectAttempt((prev) => {
        const newAttempt = prev + 1
        if (newAttempt <= maxReconnectAttempts) {
          setIsReconnecting(true)
          const delay = Math.min(1000 * Math.pow(2, prev), 30000)
          devLog(`WebSocket reconnect ${newAttempt}/${maxReconnectAttempts} in ${delay / 1000}s`)

          reconnectTimeoutRef.current = setTimeout(() => {
            if (shouldReconnectRef.current && isMountedRef.current) {
              connect()
            }
          }, delay)
        } else {
          setIsReconnecting(false)
          devLog('WebSocket reconnect attempts exhausted')
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
        queryClient.invalidateQueries({ queryKey: ['hud-metrics'] })
        queryClient.invalidateQueries({ queryKey: ['system-status'] })
        break

      case 'pathfinder_complete':
        queryClient.invalidateQueries({ queryKey: ['pathfinder-stats'] })
        queryClient.invalidateQueries({ queryKey: ['pathfinder-keywords'] })
        queryClient.invalidateQueries({ queryKey: ['pathfinder-clusters'] })
        break

      case 'pathfinder_progress':
        devLog('Pathfinder progress:', data)
        break

      case 'ranking_update':
      case 'rank_update':
        queryClient.invalidateQueries({ queryKey: ['ranking-keywords'] })
        queryClient.invalidateQueries({ queryKey: ['ranking-trends'] })
        break

      case 'new_lead':
        queryClient.invalidateQueries({ queryKey: ['leads'] })
        queryClient.invalidateQueries({ queryKey: ['leads-stats'] })
        break

      case 'viral_target_update':
        queryClient.invalidateQueries({ queryKey: ['viral-targets'] })
        queryClient.invalidateQueries({ queryKey: ['viral-stats'] })
        break

      case 'scheduler_status':
        queryClient.invalidateQueries({ queryKey: ['system-status'] })
        break

      case 'pathfinder_log': {
        const logEvent = new CustomEvent(PATHFINDER_LOG_EVENT, {
          detail: {
            line: data.line,
            timestamp: data.timestamp || new Date().toISOString(),
          },
        })
        window.dispatchEvent(logEvent)
        break
      }

      case 'pathfinder_status': {
        setPathfinderStatus(data)
        const statusEvent = new CustomEvent(PATHFINDER_STATUS_EVENT, {
          detail: data,
        })
        window.dispatchEvent(statusEvent)

        if (data.status === 'completed') {
          queryClient.invalidateQueries({ queryKey: ['pathfinder-stats'] })
          queryClient.invalidateQueries({ queryKey: ['pathfinder-keywords'] })
          queryClient.invalidateQueries({ queryKey: ['pathfinder-clusters'] })
        }
        break
      }

      default:
        devLog('Unknown WebSocket message type:', type)
    }
  }

  const disconnect = () => {
    shouldReconnectRef.current = false
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }

  useEffect(() => {
    isMountedRef.current = true
    shouldReconnectRef.current = true
    connect()

    return () => {
      isMountedRef.current = false
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
    reconnect: () => connect(true),
  }
}

import { useState } from 'react'
import { useWebSocket } from '@/hooks/useWebSocket'

export default function WebSocketIndicator() {
  const { isConnected, isReconnecting, reconnectAttempt, maxReconnectAttempts, reconnect } = useWebSocket()
  const [isHovered, setIsHovered] = useState(false)

  // 연결됨 + 호버 안함 = 최소화
  const isMinimized = isConnected && !isHovered

  // 상태별 스타일
  const getStatusStyle = () => {
    if (isConnected) {
      return 'bg-green-500/10 border-green-500/30 text-green-500 dark:bg-green-500/20'
    }
    if (isReconnecting) {
      return 'bg-yellow-500/10 border-yellow-500/30 text-yellow-600 dark:bg-yellow-500/20 dark:text-yellow-400'
    }
    return 'bg-red-500/10 border-red-500/30 text-red-500 dark:bg-red-500/20'
  }

  // 상태별 아이콘 색상
  const getIndicatorStyle = () => {
    if (isConnected) return 'bg-green-500 animate-pulse'
    if (isReconnecting) return 'bg-yellow-500 animate-spin'
    return 'bg-red-500'
  }

  // 상태 메시지
  const getStatusMessage = () => {
    if (isConnected) return '실시간 연결됨'
    if (isReconnecting) {
      return `재연결 중... (${reconnectAttempt}/${maxReconnectAttempts})`
    }
    if (reconnectAttempt >= maxReconnectAttempts) {
      return '연결 실패'
    }
    return '연결 끊김'
  }

  return (
    <div
      className={`
        fixed bottom-4 right-4 z-50 transition-all duration-300
        ${isMinimized ? 'opacity-40 scale-90' : 'opacity-100 scale-100'}
        ${!isConnected && !isReconnecting ? 'animate-pulse' : ''}
      `}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div
        className={`
          flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors
          ${getStatusStyle()}
        `}
      >
        <div
          className={`
            w-2 h-2 rounded-full flex-shrink-0
            ${getIndicatorStyle()}
          `}
        />
        <span className="text-xs font-medium whitespace-nowrap">
          {getStatusMessage()}
        </span>
        {!isConnected && !isReconnecting && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              reconnect()
            }}
            className="ml-1 px-2 py-0.5 text-xs bg-red-500 text-white rounded hover:bg-red-600 transition-colors"
          >
            재연결
          </button>
        )}
      </div>
    </div>
  )
}

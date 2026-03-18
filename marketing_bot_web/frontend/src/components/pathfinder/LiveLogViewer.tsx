import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  PATHFINDER_LOG_EVENT,
  PATHFINDER_STATUS_EVENT,
  PathfinderLogEvent,
  PathfinderStatusEvent
} from '@/hooks/useWebSocket'
import Button from '@/components/ui/Button'
import { Trash2 } from 'lucide-react'

interface LiveLogViewerProps {
  maxLines?: number
}

export default function LiveLogViewer({ maxLines = 200 }: LiveLogViewerProps) {
  const [logs, setLogs] = useState<string[]>([])
  const [status, setStatus] = useState<PathfinderStatusEvent>({
    status: 'idle',
    message: '대기 중'
  })
  const [autoScroll, setAutoScroll] = useState(true)
  const logContainerRef = useRef<HTMLDivElement>(null)

  // 초기 상태 및 최근 로그 가져오기
  const { data: initialData, refetch } = useQuery({
    queryKey: ['pathfinder-live-status'],
    queryFn: async () => {
      const res = await fetch('/api/pathfinder/live-status')
      if (!res.ok) throw new Error('Failed to fetch live status')
      return res.json()
    },
    refetchOnWindowFocus: false,
  })

  // 초기 데이터 로드
  useEffect(() => {
    if (initialData) {
      setStatus({
        status: initialData.status || 'idle',
        message: initialData.message || '대기 중',
        mode: initialData.mode,
        updated_at: initialData.updated_at
      })

      if (initialData.recent_logs && initialData.recent_logs.length > 0) {
        setLogs(initialData.recent_logs)
      }
    }
  }, [initialData])

  // 새 로그 라인 추가
  const addLogLine = useCallback((line: string) => {
    setLogs(prev => {
      const newLogs = [...prev, line]
      // 최대 라인 수 유지
      if (newLogs.length > maxLines) {
        return newLogs.slice(-maxLines)
      }
      return newLogs
    })
  }, [maxLines])

  // WebSocket 이벤트 리스너
  useEffect(() => {
    const handleLogEvent = (event: CustomEvent<PathfinderLogEvent>) => {
      addLogLine(event.detail.line)
    }

    const handleStatusEvent = (event: CustomEvent<PathfinderStatusEvent>) => {
      setStatus(event.detail)

      // 완료 시 상태 새로고침
      if (event.detail.status === 'completed') {
        refetch()
      }
    }

    window.addEventListener(PATHFINDER_LOG_EVENT, handleLogEvent as EventListener)
    window.addEventListener(PATHFINDER_STATUS_EVENT, handleStatusEvent as EventListener)

    return () => {
      window.removeEventListener(PATHFINDER_LOG_EVENT, handleLogEvent as EventListener)
      window.removeEventListener(PATHFINDER_STATUS_EVENT, handleStatusEvent as EventListener)
    }
  }, [addLogLine, refetch])

  // 자동 스크롤
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  // 스크롤 위치 감지 (사용자가 위로 스크롤하면 자동 스크롤 비활성화)
  const handleScroll = () => {
    if (logContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50
      setAutoScroll(isAtBottom)
    }
  }

  // 로그 클리어
  const clearLogs = () => {
    setLogs([])
  }

  // 상태 표시 스타일
  const getStatusStyle = () => {
    switch (status.status) {
      case 'running':
        return 'bg-green-500'
      case 'completed':
        return 'bg-blue-500'
      case 'idle':
      default:
        return 'bg-muted-foreground'
    }
  }

  const getStatusText = () => {
    switch (status.status) {
      case 'running':
        return '실행 중'
      case 'completed':
        return '완료됨'
      case 'idle':
      default:
        return '대기 중'
    }
  }

  const getModeText = () => {
    if (!status.mode) return ''
    return status.mode === 'legion' ? 'LEGION MODE' : 'Total War'
  }

  // 로그 라인 스타일링 (중요 키워드 하이라이트)
  const formatLogLine = (line: string, index: number) => {
    let className = 'font-mono text-xs leading-relaxed whitespace-pre-wrap break-all'

    // 에러/경고 하이라이트
    if (line.includes('Error') || line.includes('오류') || line.includes('실패')) {
      className += ' text-red-400'
    } else if (line.includes('Warning') || line.includes('⚠️')) {
      className += ' text-yellow-400'
    } else if (line.includes('✅') || line.includes('완료') || line.includes('성공')) {
      className += ' text-green-400'
    } else if (line.includes('S급') || line.includes('[S]')) {
      className += ' text-orange-400 font-bold'
    } else if (line.includes('A급') || line.includes('[A]')) {
      className += ' text-emerald-400'
    } else if (line.startsWith('===') || line.startsWith('---') || line.startsWith('━')) {
      className += ' text-zinc-500'
    } else if (line.startsWith('[Phase') || line.startsWith('[Round')) {
      className += ' text-cyan-400 font-semibold'
    } else {
      className += ' text-zinc-300'
    }

    return (
      <div key={index} className={className}>
        {line}
      </div>
    )
  }

  return (
    <div className="bg-card rounded-lg border border-border overflow-hidden">
      {/* 헤더 */}
      <div className="flex items-center justify-between px-4 py-3 bg-muted/50 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${getStatusStyle()} ${status.status === 'running' ? 'animate-pulse' : ''}`} />
            <span className="font-semibold">{getStatusText()}</span>
            {getModeText() && (
              <span className="text-sm text-muted-foreground">
                ({getModeText()})
              </span>
            )}
          </div>

          {status.status === 'running' && (
            <div className="flex items-center gap-1 text-green-500">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
              <span className="text-xs">LIVE</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {logs.length}줄
          </span>

          <Button
            variant={autoScroll ? 'primary' : 'secondary'}
            size="xs"
            onClick={() => setAutoScroll(!autoScroll)}
          >
            {autoScroll ? '자동 스크롤 ON' : '자동 스크롤 OFF'}
          </Button>

          <Button
            variant="secondary"
            size="xs"
            onClick={clearLogs}
            icon={<Trash2 size={12} />}
          >
            지우기
          </Button>
        </div>
      </div>

      {/* 로그 컨테이너 */}
      <div
        ref={logContainerRef}
        onScroll={handleScroll}
        className="h-80 overflow-y-auto bg-zinc-900 p-4 scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-zinc-900"
      >
        {logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-zinc-500">
            <span className="text-4xl mb-3">📋</span>
            <p className="text-sm">실시간 로그가 여기에 표시됩니다</p>
            <p className="text-xs mt-1">Pathfinder를 실행하면 진행 상황을 확인할 수 있습니다</p>
          </div>
        ) : (
          <div className="space-y-0.5">
            {logs.map((line, index) => formatLogLine(line, index))}
          </div>
        )}
      </div>

      {/* 푸터 */}
      {status.message && status.message !== '대기 중' && (
        <div className="px-4 py-2 bg-muted/30 border-t border-border">
          <p className="text-xs text-muted-foreground">
            {status.message}
          </p>
        </div>
      )}
    </div>
  )
}

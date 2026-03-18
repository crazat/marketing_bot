import { useState, useEffect, useRef, useCallback } from 'react'
import { hudApi } from '@/services/api'
import { Square, ChevronDown, ChevronRight, Clock, FileText, Wifi, WifiOff } from 'lucide-react'
import { useNotification, createScanCompleteNotification } from '@/hooks/useNotification'

interface MissionStatus {
  status: 'running' | 'completed' | 'not_found'
  logs: string[]
  started_at?: string
  progress?: {
    last_action?: string
    competitor?: string
    progress?: string
    percentage?: number
  }
  total_lines?: number
}

interface SSEProgress {
  status: 'idle' | 'running' | 'completed' | 'error' | 'timeout'
  progress: number
  message: string
  is_running: boolean
}

// 로그 표시 설정
const LOG_LINES_TO_SHOW = 50
const LOG_LINES_TO_FETCH = 60

interface MissionProgressProps {
  moduleName: string | null
  missionName: string
  onComplete?: () => void
  onStop?: () => void
}

export default function MissionProgress({
  moduleName,
  missionName,
  onComplete,
  onStop,
}: MissionProgressProps) {
  const [missionStatus, setMissionStatus] = useState<MissionStatus | null>(null)
  const [sseProgress, setSseProgress] = useState<SSEProgress | null>(null)
  const [elapsedTime, setElapsedTime] = useState(0)
  const [isExpanded, setIsExpanded] = useState(true)
  const [isSSEConnected, setIsSSEConnected] = useState(false)
  const eventSourceRef = useRef<EventSource | null>(null)
  const pollingRef = useRef<NodeJS.Timeout | null>(null)
  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const logPollingRef = useRef<NodeJS.Timeout | null>(null)  // [Phase 2] ref로 변경
  const { showNotification } = useNotification()

  // 경과 시간 포맷팅
  const formatElapsedTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return mins > 0 ? `${mins}분 ${secs}초` : `${secs}초`
  }

  // SSE 연결 해제
  const disconnectSSE = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
      setIsSSEConnected(false)
    }
  }, [])

  // Polling 중지 - [Phase 2] logPollingRef도 함께 정리
  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (logPollingRef.current) {
      clearInterval(logPollingRef.current)
      logPollingRef.current = null
    }
    disconnectSSE()
  }, [disconnectSSE])

  // SSE 연결 시작
  useEffect(() => {
    if (!moduleName) {
      stopPolling()
      return
    }

    // 타이머 시작
    timerRef.current = setInterval(() => {
      setElapsedTime(prev => prev + 1)
    }, 1000)

    // SSE 연결 시도
    const connectSSE = () => {
      const url = `/api/hud/mission/${moduleName}/progress/stream`
      const eventSource = new EventSource(url)

      eventSource.onopen = () => {
        setIsSSEConnected(true)
        // SSE 연결 성공 시 polling 중지
        if (pollingRef.current) {
          clearInterval(pollingRef.current)
          pollingRef.current = null
        }
      }

      eventSource.onmessage = (event) => {
        try {
          const data: SSEProgress = JSON.parse(event.data)
          setSseProgress(data)

          // 완료 시 알림 및 정리
          if (data.status === 'completed') {
            const notification = createScanCompleteNotification(missionName)
            showNotification(notification.title, notification.options)
            stopPolling()
            onComplete?.()
          }
        } catch (e) {
          console.error('SSE 데이터 파싱 오류:', e)
        }
      }

      eventSource.onerror = () => {
        // SSE 실패 시 polling으로 폴백
        eventSource.close()
        setIsSSEConnected(false)
        startPollingFallback()
      }

      eventSourceRef.current = eventSource
    }

    // Polling 폴백 (SSE 실패 시)
    const startPollingFallback = () => {
      if (pollingRef.current) return // 이미 polling 중

      const fetchStatus = async () => {
        try {
          const status = await hudApi.getMissionStatus(moduleName, LOG_LINES_TO_FETCH)
          setMissionStatus(status)

          if (status.status === 'completed' || status.status === 'not_found') {
            stopPolling()
            const notification = createScanCompleteNotification(missionName)
            showNotification(notification.title, notification.options)
            onComplete?.()
          }
        } catch (err) {
          console.error('Mission status polling error:', err)
        }
      }

      fetchStatus()
      pollingRef.current = setInterval(fetchStatus, 2000)
    }

    // 로그 조회 (SSE와 별개로 주기적 조회)
    const fetchLogs = async () => {
      try {
        const status = await hudApi.getMissionStatus(moduleName, LOG_LINES_TO_FETCH)
        setMissionStatus(status)
      } catch (err) {
        console.error('Mission logs fetch error:', err)
      }
    }

    // SSE 연결 시도
    connectSSE()

    // 로그는 3초마다 별도 조회 (SSE로는 진행률만 받음)
    fetchLogs()
    // [Phase 2] ref 사용으로 변경
    logPollingRef.current = setInterval(fetchLogs, 3000)

    return () => {
      stopPolling()
    }
  }, [moduleName, missionName, onComplete, showNotification, stopPolling])

  // 스캔 중지 핸들러
  const handleStop = async () => {
    if (moduleName) {
      try {
        await hudApi.stopMission(moduleName)
        stopPolling()
        onStop?.()
      } catch {
        console.error('Failed to stop mission')
      }
    }
  }

  // 로그 색상 및 스타일 결정
  const getLogStyle = (log: string): { color: string; bold?: boolean } => {
    // 에러
    if (log.includes('ERROR') || log.includes('오류') || log.includes('실패') || log.includes('Exception')) {
      return { color: 'text-red-400', bold: true }
    }
    // 경고
    if (log.includes('WARNING') || log.includes('⚠️') || log.includes('경고')) {
      return { color: 'text-yellow-400' }
    }
    // 완료/성공
    if (log.includes('완료') || log.includes('SUCCESS') || log.includes('성공') || log.includes('✅')) {
      return { color: 'text-green-400', bold: true }
    }
    // S급/A급 키워드 (강조)
    if (log.includes('S급') || log.includes('[S]') || log.includes('🔥')) {
      return { color: 'text-orange-400', bold: true }
    }
    if (log.includes('A급') || log.includes('[A]')) {
      return { color: 'text-emerald-400' }
    }
    // 단계/라운드
    if (log.includes('[Phase') || log.includes('[Round') || log.includes('===')) {
      return { color: 'text-cyan-400', bold: true }
    }
    // 진행 중
    if (log.includes('수집') || log.includes('분석') || log.includes('처리') || log.includes('스캔')) {
      return { color: 'text-yellow-400' }
    }
    // 시작
    if (log.includes('시작') || log.includes('진행') || log.includes('Starting')) {
      return { color: 'text-blue-400' }
    }
    return { color: 'text-muted-foreground' }
  }

  // 진행률 파싱 (SSE 우선, 없으면 로그에서 파싱)
  const getProgressPercentage = (): number | null => {
    // SSE 진행률 우선 사용
    if (sseProgress && sseProgress.progress > 0) {
      return sseProgress.progress
    }
    if (missionStatus?.progress?.percentage) {
      return missionStatus.progress.percentage
    }
    if (missionStatus?.progress?.progress) {
      const match = missionStatus.progress.progress.match(/(\d+)%/)
      if (match) return parseInt(match[1], 10)
    }
    return null
  }

  // SSE 또는 로그에서 현재 상태 메시지 가져오기
  const getCurrentMessage = (): string | null => {
    if (sseProgress?.message && sseProgress.message !== '대기 중') {
      return sseProgress.message
    }
    return missionStatus?.progress?.last_action || null
  }

  const progressPercent = getProgressPercentage()
  const currentMessage = getCurrentMessage()

  if (!moduleName) return null

  return (
    <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg overflow-hidden">
      {/* 헤더 */}
      <div
        className="flex items-center justify-between p-4 cursor-pointer hover:bg-blue-500/5"
        onClick={() => setIsExpanded(!isExpanded)}
        role="button"
        aria-expanded={isExpanded}
      >
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="animate-spin rounded-full h-6 w-6 border-2 border-blue-500/30 border-t-blue-500" />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
            </div>
          </div>
          <div>
            <p className="font-semibold text-blue-500">
              {missionName} 진행 중...
            </p>
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                {formatElapsedTime(elapsedTime)}
              </span>
              {missionStatus?.total_lines && (
                <span className="flex items-center gap-1">
                  <FileText className="w-3.5 h-3.5" />
                  {missionStatus.total_lines}줄
                </span>
              )}
              {progressPercent !== null && (
                <span className="font-medium text-blue-400">
                  {progressPercent}%
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* SSE 연결 상태 표시 */}
          <span
            className={`flex items-center gap-1 text-xs ${isSSEConnected ? 'text-green-400' : 'text-yellow-400'}`}
            title={isSSEConnected ? '실시간 연결됨' : 'Polling 모드'}
          >
            {isSSEConnected ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
          </span>
          {currentMessage && (
            <span className="text-xs px-2 py-1 rounded bg-blue-500/20 text-blue-400 max-w-[250px] truncate hidden md:block">
              {currentMessage}
            </span>
          )}
          <button
            onClick={(e) => {
              e.stopPropagation()
              handleStop()
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500 text-white rounded-md text-sm font-medium hover:bg-red-600 transition-colors"
            aria-label="작업 중지"
          >
            <Square className="w-3.5 h-3.5" />
            중지
          </button>
          {isExpanded ? (
            <ChevronDown className="w-5 h-5 text-muted-foreground" />
          ) : (
            <ChevronRight className="w-5 h-5 text-muted-foreground" />
          )}
        </div>
      </div>

      {/* 진행률 바 (있는 경우) */}
      {progressPercent !== null && (
        <div className="px-4 pb-2">
          <div className="h-2 bg-blue-500/20 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      )}

      {/* 로그 영역 (확장 시) */}
      {isExpanded && missionStatus?.logs && missionStatus.logs.length > 0 && (
        <div className="border-t border-blue-500/20 p-4 bg-zinc-950/50">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              실시간 로그
            </span>
            <span className="text-xs text-muted-foreground">
              최근 {Math.min(missionStatus.logs.length, LOG_LINES_TO_SHOW)}줄
            </span>
          </div>
          <div className="font-mono text-xs space-y-0.5 max-h-80 overflow-y-auto bg-zinc-900 rounded-md p-3">
            {missionStatus.logs.slice(-LOG_LINES_TO_SHOW).map((log, idx) => {
              const style = getLogStyle(log)
              return (
                <div
                  key={idx}
                  className={`py-0.5 ${style.color} ${style.bold ? 'font-semibold' : ''}`}
                >
                  {log}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// useMissionProgress 훅 - 각 페이지에서 사용
export function useMissionProgress() {
  const [scanningModule, setScanningModule] = useState<string | null>(null)
  const [missionName, setMissionName] = useState('')

  const startMission = (moduleName: string, name: string) => {
    setScanningModule(moduleName)
    setMissionName(name)
  }

  const stopMission = () => {
    setScanningModule(null)
    setMissionName('')
  }

  return {
    scanningModule,
    missionName,
    isScanning: scanningModule !== null,
    startMission,
    stopMission,
  }
}

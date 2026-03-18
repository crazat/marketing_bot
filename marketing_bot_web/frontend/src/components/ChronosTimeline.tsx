import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { hudApi } from '@/services/api'
import { useState } from 'react'
import { useToast } from '@/components/ui/Toast'
import MissionProgress from '@/components/ui/MissionProgress'

interface ScheduleItem {
  time: string
  name: string
  icon: string
  cmd: string
  status: 'done' | 'running' | 'upcoming' | 'missed' | 'pending'
  last_run?: string
}

interface SchedulerState {
  schedule: ScheduleItem[]
  current_time: string
  today: string
  running_count: number
}

export default function ChronosTimeline() {
  const queryClient = useQueryClient()
  const [executingModule, setExecutingModule] = useState<string | null>(null)
  const [executingName, setExecutingName] = useState('')
  const toast = useToast()

  const { data: schedulerState, isLoading } = useQuery<SchedulerState>({
    queryKey: ['scheduler-state'],
    queryFn: hudApi.getSchedulerState,
    refetchInterval: 60000, // 60초마다 새로고침
  })

  const executeMission = useMutation({
    mutationFn: (moduleName: string) => hudApi.executeMission(moduleName),
    onSuccess: (data, moduleName) => {
      if (data.success) {
        toast.success(`${moduleName} 실행이 시작되었습니다`)
      } else {
        toast.error(`${moduleName} 실행 실패: ${data.message || '알 수 없는 오류'}`)
        setExecutingModule(null)
        setExecutingName('')
      }
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }, moduleName) => {
      toast.error(`${moduleName} 실행 오류: ${error.response?.data?.detail || error.message}`)
      setExecutingModule(null)
      setExecutingName('')
    },
  })

  const handleExecute = (item: ScheduleItem) => {
    if (item.status === 'running' || executingModule === item.cmd) {
      return
    }
    setExecutingModule(item.cmd)
    setExecutingName(item.name)
    executeMission.mutate(item.cmd)
  }

  const handleMissionComplete = () => {
    setExecutingModule(null)
    setExecutingName('')
    queryClient.invalidateQueries({ queryKey: ['scheduler-state'] })
    queryClient.invalidateQueries({ queryKey: ['hud-metrics'] })
    queryClient.invalidateQueries({ queryKey: ['recent-activities'] })
    toast.success('작업이 완료되었습니다')
  }

  const handleMissionStop = () => {
    setExecutingModule(null)
    setExecutingName('')
    toast.info('작업이 중지되었습니다')
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'done':
        return 'bg-green-500/10 border-green-500/50 text-green-500'
      case 'running':
        return 'bg-blue-500/10 border-blue-500 text-blue-500 ring-2 ring-blue-500/50'
      case 'upcoming':
        return 'bg-yellow-500/10 border-yellow-500/50 text-yellow-500'
      case 'missed':
        return 'bg-red-500/10 border-red-500/50 text-red-500'
      default:
        return 'bg-muted border-border text-muted-foreground'
    }
  }

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'done':
        return '완료'
      case 'running':
        return '실행 중'
      case 'upcoming':
        return '곧 시작'
      case 'missed':
        return '놓침'
      default:
        return '대기'
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-24">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    )
  }

  const schedule = schedulerState?.schedule || []

  return (
    <div className="space-y-4">
      {/* 현재 시간 표시 */}
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          현재 시간: <span className="font-mono font-bold text-foreground">{schedulerState?.current_time || '--:--'}</span>
        </span>
        {schedulerState?.running_count ? (
          <span className="px-2 py-1 bg-blue-500/10 text-blue-500 rounded text-xs">
            {schedulerState.running_count}개 실행 중
          </span>
        ) : null}
      </div>

      {/* 실시간 진행 상황 */}
      {executingModule && (
        <MissionProgress
          moduleName={executingModule}
          missionName={executingName}
          onComplete={handleMissionComplete}
          onStop={handleMissionStop}
        />
      )}

      {/* 타임라인 */}
      <div className="overflow-x-auto">
        <div className="flex gap-3 pb-4 min-w-max">
          {schedule.map((item) => {
            const isExecuting = executingModule === item.cmd
            const isRunning = item.status === 'running' || isExecuting

            return (
              <button
                key={item.time}
                onClick={() => handleExecute(item)}
                disabled={isRunning}
                className={`
                  flex flex-col items-center min-w-[90px] p-3 rounded-lg border-2
                  transition-all duration-300 cursor-pointer
                  hover:scale-105 hover:shadow-lg
                  disabled:cursor-not-allowed disabled:hover:scale-100
                  ${getStatusColor(isRunning ? 'running' : item.status)}
                `}
              >
                {/* 시간 */}
                <div className="text-xs font-mono mb-1">{item.time}</div>

                {/* 아이콘 */}
                <div className={`text-3xl mb-1 ${isRunning ? 'animate-pulse' : ''}`}>
                  {item.icon}
                </div>

                {/* 이름 */}
                <div className="text-xs text-center font-medium leading-tight">
                  {item.name}
                </div>

                {/* 상태 표시 */}
                <div className="mt-2 text-[10px] font-semibold uppercase tracking-wider">
                  {isRunning ? (
                    <span className="flex items-center gap-1">
                      <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
                      실행 중
                    </span>
                  ) : (
                    getStatusLabel(item.status)
                  )}
                </div>

                {/* 실행 중 프로그레스 바 */}
                {isRunning && (
                  <div className="mt-2 w-full h-1 bg-blue-500/30 rounded-full overflow-hidden">
                    <div className="h-full bg-blue-500 rounded-full animate-[progress_2s_ease-in-out_infinite]" />
                  </div>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* 범례 */}
      <div className="flex flex-wrap gap-3 text-xs">
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-green-500/50" />
          <span>완료</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-blue-500 animate-pulse" />
          <span>실행 중</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-yellow-500/50" />
          <span>곧 시작</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-red-500/50" />
          <span>놓침</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-muted" />
          <span>대기</span>
        </div>
      </div>

      {/* 안내 문구 */}
      <p className="text-xs text-muted-foreground">
        클릭하여 수동 실행할 수 있습니다. 스케줄 시간에 자동 실행됩니다.
      </p>
    </div>
  )
}

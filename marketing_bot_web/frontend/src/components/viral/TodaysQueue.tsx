import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Inbox, Flame, Swords, ChevronRight, Clock, Check, X } from 'lucide-react'
import { viralApi } from '@/services/api'
import { useState } from 'react'
import { useToast } from '@/components/ui/Toast'
import SwipeableTargetItem from '@/components/viral/SwipeableTargetItem'

interface TodaysQueueProps {
  onOpenTarget?: (targetId: string) => void
  onOpenCategory?: (category: string) => void
}

const CATEGORY_ICON: Record<string, string> = {
  '경쟁사_역공략': '⚔️',
  '기타': '📌',
}

const PLATFORM_ICON: Record<string, string> = {
  cafe: '☕',
  blog: '📝',
  kin: '❓',
  instagram: '📸',
  youtube: '▶️',
  tiktok: '🎵',
}

export default function TodaysQueue({ onOpenTarget, onOpenCategory }: TodaysQueueProps) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [pendingAction, setPendingAction] = useState<string | null>(null)
  // [V1] 오늘 발견분만 보기 (기본 ON)
  const [todayOnly, setTodayOnly] = useState<boolean>(true)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['viral-todays-queue', todayOnly],
    queryFn: () => viralApi.getTodaysQueue(30, 5, todayOnly),
    staleTime: 60_000,
    refetchInterval: 120_000,
  })

  const doAction = async (targetId: string, action: 'approve' | 'skip') => {
    setPendingAction(targetId)
    try {
      await viralApi.targetAction(targetId, action)
      toast.success(action === 'approve' ? '✅ 승인' : '⏭️ 스킵')
      queryClient.invalidateQueries({ queryKey: ['viral-todays-queue'] })
      queryClient.invalidateQueries({ queryKey: ['viral-kpi-stats'] })
    } catch (err) {
      toast.error(`처리 실패: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setPendingAction(null)
    }
  }

  const handleQuickAction = async (
    e: React.MouseEvent,
    targetId: string,
    action: 'approve' | 'skip'
  ) => {
    e.stopPropagation()
    await doAction(targetId, action)
  }

  if (isLoading) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 animate-pulse">
        <div className="h-5 w-40 bg-muted rounded mb-4" />
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-16 bg-muted/50 rounded" />
          ))}
        </div>
      </div>
    )
  }

  if (isError || !data || data.total === 0) {
    return (
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Inbox className="h-5 w-5" /> 오늘의 작업 큐
          </h2>
          {/* 빈 상태에서도 토글 노출 (전체로 전환 가능) */}
          <button
            onClick={() => setTodayOnly((v) => !v)}
            className={`text-xs px-3 py-1.5 rounded-full border ${
              todayOnly ? 'bg-primary/10 border-primary text-primary font-medium' : 'border-border'
            }`}
          >
            {todayOnly ? '📅 오늘만' : '🗓️ 전체'}
          </button>
        </div>
        <p className="text-sm text-muted-foreground">
          {todayOnly
            ? '오늘 새로 발견된 HOT LEAD가 없습니다. 전체 보기로 전환하거나 새로 스캔하세요.'
            : '대기 중인 HOT LEAD가 없습니다. 새로운 스캔을 실행해 보세요.'}
        </p>
      </div>
    )
  }

  return (
    <div className="bg-card border border-border rounded-lg p-6">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Inbox className="h-5 w-5" />
          오늘의 작업 큐
          <span className="text-sm font-normal text-muted-foreground ml-2">
            · 점수 80+ {todayOnly ? '오늘 ' : '전체 '}상위 {data.total}건
          </span>
        </h2>
        <div className="flex items-center gap-2">
          {/* [V1] 오늘 필터 토글 */}
          <button
            onClick={() => setTodayOnly((v) => !v)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
              todayOnly
                ? 'bg-primary/10 border-primary text-primary font-medium'
                : 'bg-background border-border hover:bg-muted text-muted-foreground'
            }`}
            title="오늘 발견된 타겟만 표시"
          >
            {todayOnly ? '📅 오늘만' : '🗓️ 전체'}
          </button>
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {new Date(data.generated_at).toLocaleTimeString('ko-KR', {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>
      </div>

      <div className="space-y-4">
        {data.groups.map((group) => {
          const isCompetitor = group.category === '경쟁사_역공략'
          const icon = CATEGORY_ICON[group.category] ?? '📌'
          return (
            <div
              key={group.category}
              className={`border rounded-lg p-4 ${isCompetitor ? 'border-orange-400 bg-orange-50/30 dark:bg-orange-950/20' : 'border-border bg-background'}`}
            >
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-medium flex items-center gap-2">
                  <span>{icon}</span>
                  <span>{group.category}</span>
                  {isCompetitor && <Swords className="h-4 w-4 text-orange-500" />}
                  <span className="text-xs text-muted-foreground ml-1">{group.count}건</span>
                </h3>
                <button
                  onClick={() => onOpenCategory?.(group.category)}
                  className="text-xs text-primary hover:underline flex items-center gap-1"
                >
                  전체 보기
                  <ChevronRight className="h-3 w-3" />
                </button>
              </div>

              <ul className="space-y-2">
                {group.items.map((item) => {
                  const isPending = pendingAction === item.id
                  return (
                    <li key={item.id}>
                      <SwipeableTargetItem
                        disabled={isPending}
                        onSwipeRight={() => doAction(item.id, 'approve')}
                        onSwipeLeft={() => doAction(item.id, 'skip')}
                      >
                        <div
                          onClick={() => onOpenTarget?.(item.id)}
                          className="flex items-center gap-3 p-3 sm:p-2 rounded hover:bg-muted/50 cursor-pointer transition-colors select-none"
                        >
                          <span className="text-lg">{PLATFORM_ICON[item.platform] ?? '📌'}</span>
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium truncate">{item.title}</div>
                            <div className="text-xs text-muted-foreground flex items-center gap-2 mt-0.5">
                              <span className="flex items-center gap-0.5">
                                <Flame className="h-3 w-3 text-red-500" />
                                {item.priority_score?.toFixed?.(0) ?? 0}
                              </span>
                              {item.matched_keyword && (
                                <span className="truncate max-w-[14rem]">
                                  · {item.matched_keyword}
                                </span>
                              )}
                            </div>
                          </div>

                          {/* [D4] 빠른 액션 버튼 */}
                          <div className="flex items-center gap-1 shrink-0">
                            <button
                              onClick={(e) => handleQuickAction(e, item.id, 'skip')}
                              disabled={isPending}
                              aria-label="스킵"
                              className="h-10 w-10 rounded-full hover:bg-muted flex items-center justify-center disabled:opacity-40"
                            >
                              <X className="h-4 w-4 text-muted-foreground" />
                            </button>
                            <button
                              onClick={(e) => handleQuickAction(e, item.id, 'approve')}
                              disabled={isPending}
                              aria-label="승인"
                              className="h-10 w-10 rounded-full bg-green-500/10 hover:bg-green-500/20 flex items-center justify-center disabled:opacity-40"
                            >
                              <Check className="h-4 w-4 text-green-600 dark:text-green-400" />
                            </button>
                          </div>
                        </div>
                      </SwipeableTargetItem>
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </div>
    </div>
  )
}

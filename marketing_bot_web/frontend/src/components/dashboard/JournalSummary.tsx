import { useEffect, useState } from 'react'
import { useActionJournal, summarizeToday } from '@/hooks/useActionJournal'
import { formatRelative } from '@/utils/format'
import { BookOpen, Check, SkipForward, Trash2, Sparkles } from 'lucide-react'

/**
 * [BB1] 오늘 한 일 저널 요약
 *
 * 로컬 액션 로그를 기반으로 오늘의 narrative 생성.
 * "14시부터 작업 중 · 승인 12건, 스킵 5건, 다이어트 카테고리 집중"
 */
export default function JournalSummary() {
  const { entries } = useActionJournal()
  // [DD5] 자정 경계 감지 — 다음 자정에 재계산 강제
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const now = new Date()
    const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
    const msUntilMidnight = tomorrow.getTime() - now.getTime()
    const timer = setTimeout(() => setTick((t) => t + 1), msUntilMidnight + 1000)
    return () => clearTimeout(timer)
  }, [tick])
  const summary = summarizeToday(entries)
  void tick // summary 재계산을 위한 의존 표시

  if (summary.totalActions === 0) {
    return (
      <section
        aria-label="오늘 한 일"
        className="bg-card border border-border p-5 md:p-6"
      >
        <div className="caps text-muted-foreground mb-2 flex items-center gap-1.5">
          <BookOpen className="w-3 h-3" aria-hidden />
          <span>오늘 한 일 · Journal</span>
        </div>
        <p className="text-sm text-muted-foreground">
          오늘 아직 기록된 활동이 없습니다. 첫 작업을 시작해 보세요.
        </p>
      </section>
    )
  }

  const { byKind, topContexts, firstAction, lastAction } = summary
  const working = firstAction && lastAction ? lastAction - firstAction : 0

  return (
    <section
      aria-label="오늘 한 일"
      className="bg-card border border-border p-5 md:p-6"
    >
      <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
        <div className="caps text-muted-foreground flex items-center gap-1.5">
          <BookOpen className="w-3 h-3" aria-hidden />
          <span>오늘 한 일 · Journal</span>
        </div>
        {firstAction && (
          <span className="text-xs text-muted-foreground tabular-nums">
            {formatRelative(firstAction)} 시작 · 총 {summary.totalActions}회
          </span>
        )}
      </div>

      {/* 액션 카운트 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <JournalChip Icon={Check} label="승인" value={byKind.approve} tone="text-emerald-600" />
        <JournalChip Icon={SkipForward} label="스킵" value={byKind.skip} tone="text-amber-600" />
        <JournalChip Icon={Trash2} label="삭제" value={byKind.delete} tone="text-red-500" />
        <JournalChip Icon={Sparkles} label="AI 생성" value={byKind.generate} tone="text-purple-600" />
      </div>

      {/* Top 카테고리 */}
      {topContexts.length > 0 && (
        <div>
          <div className="caps text-muted-foreground mb-2">집중 카테고리</div>
          <div className="flex flex-wrap gap-1.5">
            {topContexts.map(([ctx, count]) => (
              <span
                key={ctx}
                className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-muted/40 border border-border rounded"
              >
                <span className="font-medium">{ctx}</span>
                <span className="text-muted-foreground tabular-nums">{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {working > 5 * 60_000 && (
        <p className="text-[11px] text-muted-foreground mt-3 pt-3 border-t border-border">
          작업 세션: {Math.round(working / 60_000)}분 지속 중
        </p>
      )}
    </section>
  )
}

function JournalChip({
  Icon,
  label,
  value,
  tone,
}: {
  Icon: typeof Check
  label: string
  value: number
  tone: string
}) {
  return (
    <div className="bg-muted/30 border border-border p-3">
      <div className={`flex items-center gap-1.5 text-xs mb-1 ${tone}`}>
        <Icon className="w-3.5 h-3.5" aria-hidden />
        <span>{label}</span>
      </div>
      <div className="font-display text-2xl tabular-nums leading-none">{value}</div>
    </div>
  )
}

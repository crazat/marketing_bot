import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'marketing-bot-journal-v1'
const MAX_ENTRIES = 500

export type JournalKind = 'approve' | 'skip' | 'delete' | 'reopen' | 'generate' | 'scan'

export interface JournalEntry {
  id: string
  kind: JournalKind
  context?: string // 카테고리/플랫폼 등
  timestamp: number
}

function load(): JournalEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function save(entries: JournalEntry[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(-MAX_ENTRIES)))
  } catch {
    // ignore
  }
}

/**
 * [BB1] 활동 저널 — 로컬 액션 로그
 *
 * 승인/스킵/삭제/생성 등 주요 액션을 localStorage에 누적.
 * DashboardJournal 위젯에서 오늘/이번주 요약 생성.
 */
export function useActionJournal() {
  const [entries, setEntries] = useState<JournalEntry[]>([])

  useEffect(() => {
    setEntries(load())
  }, [])

  const log = useCallback(
    (kind: JournalKind, context?: string) => {
      const entry: JournalEntry = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        kind,
        context,
        timestamp: Date.now(),
      }
      setEntries((prev) => {
        const next = [...prev, entry].slice(-MAX_ENTRIES)
        save(next)
        return next
      })
    },
    [],
  )

  return { entries, log }
}

/**
 * 저널 요약 계산 (오늘)
 */
export function summarizeToday(entries: JournalEntry[]) {
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const today = entries.filter((e) => e.timestamp >= start)

  const byKind: Record<JournalKind, number> = {
    approve: 0,
    skip: 0,
    delete: 0,
    reopen: 0,
    generate: 0,
    scan: 0,
  }
  const byContext = new Map<string, number>()

  today.forEach((e) => {
    byKind[e.kind] = (byKind[e.kind] ?? 0) + 1
    if (e.context) {
      byContext.set(e.context, (byContext.get(e.context) ?? 0) + 1)
    }
  })

  const topContexts = Array.from(byContext.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)

  const firstAction = today[0]?.timestamp
  const lastAction = today[today.length - 1]?.timestamp

  return {
    totalActions: today.length,
    byKind,
    topContexts,
    firstAction,
    lastAction,
  }
}

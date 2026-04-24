import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'marketing-bot-recent-items-v1'
const MAX_ITEMS = 12

export type RecentKind = 'lead' | 'keyword' | 'viral_target' | 'competitor' | 'page'

export interface RecentItem {
  id: string
  kind: RecentKind
  label: string
  path: string
  timestamp: number
}

function loadItems(): RecentItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (x) =>
        x && typeof x.id === 'string' && typeof x.path === 'string' && typeof x.timestamp === 'number',
    )
  } catch {
    return []
  }
}

function saveItems(items: RecentItem[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
  } catch {
    // ignore quota errors
  }
}

/**
 * 최근 본 리드/키워드/타겟 추적
 *
 * 페이지에서 record() 호출 → localStorage 저장 →
 * Command Palette에서 최근 섹션에 표시.
 */
export function useRecentItems() {
  const [items, setItems] = useState<RecentItem[]>([])

  useEffect(() => {
    setItems(loadItems())
  }, [])

  const record = useCallback((item: Omit<RecentItem, 'timestamp'>) => {
    setItems((prev) => {
      const filtered = prev.filter((x) => !(x.kind === item.kind && x.id === item.id))
      const next = [{ ...item, timestamp: Date.now() }, ...filtered].slice(0, MAX_ITEMS)
      saveItems(next)
      return next
    })
  }, [])

  const clear = useCallback(() => {
    saveItems([])
    setItems([])
  }, [])

  const getByKind = useCallback(
    (kind: RecentKind) => items.filter((x) => x.kind === kind),
    [items],
  )

  return { items, record, clear, getByKind }
}

import { useCallback, useEffect, useState } from 'react'
import { readStorageJson, writeStorageJson } from '@/utils/safeStorage'

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
  const parsed = readStorageJson<unknown[]>(STORAGE_KEY, [], Array.isArray)
  return parsed.filter(
    (x): x is RecentItem =>
      Boolean(x) &&
      typeof x === 'object' &&
      typeof (x as RecentItem).id === 'string' &&
      typeof (x as RecentItem).path === 'string' &&
      typeof (x as RecentItem).timestamp === 'number',
  )
}

function saveItems(items: RecentItem[]) {
  writeStorageJson(STORAGE_KEY, items)
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

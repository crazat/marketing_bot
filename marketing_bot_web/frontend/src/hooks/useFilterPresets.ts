import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'marketing-bot-filter-presets-v1'
const MAX_PRESETS = 8

export interface FilterPreset<T = unknown> {
  id: string
  name: string
  scope: string
  filters: T
  createdAt: number
}

function load<T>(scope: string): FilterPreset<T>[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((p) => p?.scope === scope) as FilterPreset<T>[]
  } catch {
    return []
  }
}

function save<T>(all: FilterPreset<T>[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
  } catch {
    // ignore quota
  }
}

function loadAll(): FilterPreset[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 필터 프리셋 저장/불러오기
 *
 * @param scope — 페이지별 분리 키 (예: 'viral', 'pathfinder')
 */
export function useFilterPresets<T>(scope: string) {
  const [presets, setPresets] = useState<FilterPreset<T>[]>([])

  useEffect(() => {
    setPresets(load<T>(scope))
  }, [scope])

  const savePreset = useCallback(
    (name: string, filters: T) => {
      const all = loadAll() as FilterPreset<T>[]
      const scoped = all.filter((p) => p.scope === scope)
      if (scoped.length >= MAX_PRESETS) {
        // 가장 오래된 것 제거
        scoped.sort((a, b) => a.createdAt - b.createdAt)
        const removeId = scoped[0]?.id
        const filtered = all.filter((p) => p.id !== removeId)
        const next: FilterPreset<T> = {
          id: `${scope}-${Date.now()}`,
          name: name.trim() || '이름 없음',
          scope,
          filters,
          createdAt: Date.now(),
        }
        save([...filtered, next])
        setPresets(filtered.concat(next).filter((p) => p.scope === scope) as FilterPreset<T>[])
        return next
      }
      const next: FilterPreset<T> = {
        id: `${scope}-${Date.now()}`,
        name: name.trim() || '이름 없음',
        scope,
        filters,
        createdAt: Date.now(),
      }
      save([...all, next])
      setPresets([...scoped, next])
      return next
    },
    [scope],
  )

  const removePreset = useCallback(
    (id: string) => {
      const all = loadAll()
      const next = all.filter((p) => p.id !== id)
      save(next)
      setPresets(next.filter((p) => p.scope === scope) as FilterPreset<T>[])
    },
    [scope],
  )

  return { presets, savePreset, removePreset }
}

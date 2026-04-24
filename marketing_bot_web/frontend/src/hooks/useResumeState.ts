import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'marketing-bot-resume-v1'
const RESUME_TTL_MS = 8 * 60 * 60 * 1000 // 8시간

export interface ResumeState {
  scope: string
  view?: string
  category?: string | null
  expandedTargetId?: string | null
  label?: string // 사용자에게 보일 설명 ("청주 다이어트 카테고리 작업 중")
  timestamp: number
}

function load(scope: string): ResumeState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const all = JSON.parse(raw)
    const entry = all?.[scope]
    if (!entry || typeof entry.timestamp !== 'number') return null
    if (Date.now() - entry.timestamp > RESUME_TTL_MS) return null
    return entry as ResumeState
  } catch {
    return null
  }
}

function save(scope: string, state: ResumeState | null) {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const all = raw ? JSON.parse(raw) : {}
    if (state === null) {
      delete all[scope]
    } else {
      all[scope] = state
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
  } catch {
    // ignore
  }
}

/**
 * [X7] 이어 작업하기 — 페이지 scope별로 마지막 상태 저장.
 *
 * - record(): 중요 상태 변경 시마다 호출
 * - resume(): 초기 마운트 시 반환, 8시간 내면 배너 표시
 * - dismiss(): 사용자가 거절 시
 */
export function useResumeState(scope: string) {
  const [initial, setInitial] = useState<ResumeState | null>(null)

  useEffect(() => {
    setInitial(load(scope))
  }, [scope])

  const record = useCallback(
    (state: Omit<ResumeState, 'scope' | 'timestamp'>) => {
      save(scope, { ...state, scope, timestamp: Date.now() })
    },
    [scope],
  )

  const clear = useCallback(() => {
    save(scope, null)
    setInitial(null)
  }, [scope])

  return { initial, record, clear }
}

import { useEffect, useRef } from 'react'
import { useToast } from '@/components/ui/Toast'

const STORAGE_KEY = 'marketing-bot-fatigue-v1'
const SESSION_TTL_MS = 30 * 60_000 // 30분 유휴 시 세션 종료
const DEFAULT_THRESHOLD = { actions: 30, minDurationMs: 15 * 60_000 }

interface FatigueState {
  sessionStart: number
  actionCount: number
  lastAction: number
  warnedAt?: number
}

function load(): FatigueState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as FatigueState) : null
  } catch {
    return null
  }
}

function save(state: FatigueState | null) {
  try {
    if (state === null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // ignore
  }
}

/**
 * [BB5] 세션 피로 감지
 *
 * 연속 작업 중 임계(기본 15분 + 30액션) 초과 시 토스트로 휴식 권유.
 * 한 세션에 1회만. 30분 유휴 시 세션 리셋.
 *
 * 사용:
 *   const { markAction } = useFatigueDetector()
 *   markAction() — 사용자 액션마다 호출
 */
export function useFatigueDetector(threshold = DEFAULT_THRESHOLD) {
  const toast = useToast()
  const stateRef = useRef<FatigueState | null>(null)

  useEffect(() => {
    stateRef.current = load()
  }, [])

  const markAction = () => {
    const now = Date.now()
    const current = stateRef.current
    // 새 세션 시작 or 유휴 후 리셋
    if (!current || now - current.lastAction > SESSION_TTL_MS) {
      const next: FatigueState = {
        sessionStart: now,
        actionCount: 1,
        lastAction: now,
      }
      stateRef.current = next
      save(next)
      return
    }

    const next: FatigueState = {
      ...current,
      actionCount: current.actionCount + 1,
      lastAction: now,
    }

    // 임계 초과 + 아직 경고 안 함
    const duration = now - next.sessionStart
    const shouldWarn =
      !next.warnedAt &&
      next.actionCount >= threshold.actions &&
      duration >= threshold.minDurationMs

    if (shouldWarn) {
      const mins = Math.round(duration / 60_000)
      toast.info(
        `☕ ${mins}분 동안 ${next.actionCount}개 작업 완료 — 잠시 쉬어가세요`,
        8000,
      )
      next.warnedAt = now
    }

    stateRef.current = next
    save(next)
  }

  return { markAction }
}

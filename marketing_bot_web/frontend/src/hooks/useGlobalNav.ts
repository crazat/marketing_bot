import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

const NAV_MAP: Record<string, { path: string; label: string }> = {
  h: { path: '/', label: '대시보드' },
  v: { path: '/viral', label: 'Viral Hunter' },
  l: { path: '/leads', label: 'Lead Manager' },
  p: { path: '/pathfinder', label: 'Pathfinder' },
  b: { path: '/battle', label: 'Battle Intelligence' },
  c: { path: '/competitors', label: '경쟁사 분석' },
  q: { path: '/qa', label: 'Q&A Repository' },
  m: { path: '/marketing', label: 'Marketing Hub' },
  s: { path: '/settings', label: '설정' },
}

const PREFIX_KEY = 'g'
const TIMEOUT_MS = 800

/**
 * [X6] 전역 키보드 네비 — Gmail/GitHub 스타일 prefix 시퀀스.
 *
 * g → (800ms 내) → h/v/l/p/b/c/q/a/s → 해당 페이지로 이동.
 * 힌트는 onPrefixStart 콜백에서 toast로 표시 가능.
 */
export function useGlobalNav(options?: {
  onPrefixStart?: () => void
  onCancel?: () => void
}) {
  const navigate = useNavigate()
  const prefixActiveRef = useRef(false)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // 입력 필드에서는 비활성
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        (e.target as HTMLElement)?.isContentEditable
      ) {
        return
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return

      const key = e.key.toLowerCase()

      // prefix 대기 중 → 대상 키 매칭
      if (prefixActiveRef.current) {
        const target = NAV_MAP[key]
        if (target) {
          e.preventDefault()
          navigate(target.path)
        }
        prefixActiveRef.current = false
        if (timeoutRef.current) clearTimeout(timeoutRef.current)
        options?.onCancel?.()
        return
      }

      // prefix 시작
      if (key === PREFIX_KEY && !e.shiftKey) {
        prefixActiveRef.current = true
        options?.onPrefixStart?.()
        if (timeoutRef.current) clearTimeout(timeoutRef.current)
        timeoutRef.current = setTimeout(() => {
          prefixActiveRef.current = false
          options?.onCancel?.()
        }, TIMEOUT_MS)
      }
    }

    window.addEventListener('keydown', handler)
    return () => {
      window.removeEventListener('keydown', handler)
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [navigate, options])
}

export { NAV_MAP }

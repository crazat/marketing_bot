import { useEffect, useRef } from 'react'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

/**
 * [Y1] Modal focus trap — 모달 내부에서만 Tab 순환.
 * 열릴 때 트리거 복원을 위해 이전 활성 요소 기억.
 *
 * @param active — 모달이 열려있을 때만 true
 * @param containerRef — 모달 컨테이너 ref
 * @param options.autoFocusFirst — 열릴 때 첫 요소로 자동 포커스 (기본 true)
 */
export function useFocusTrap(
  active: boolean,
  containerRef: React.RefObject<HTMLElement | null>,
  options: { autoFocusFirst?: boolean } = {},
) {
  const { autoFocusFirst = true } = options
  const previouslyFocusedRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!active) return

    previouslyFocusedRef.current = document.activeElement as HTMLElement | null

    const container = containerRef.current
    if (!container) return

    const focusables = Array.from(
      container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
    ).filter((el) => !el.hasAttribute('aria-hidden'))

    if (autoFocusFirst && focusables.length > 0) {
      focusables[0].focus()
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return

      const currentFocusables = Array.from(
        container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((el) => !el.hasAttribute('aria-hidden'))

      if (currentFocusables.length === 0) {
        e.preventDefault()
        return
      }

      const first = currentFocusables[0]
      const last = currentFocusables[currentFocusables.length - 1]

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault()
          last.focus()
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }

    container.addEventListener('keydown', handleKeyDown)
    return () => {
      container.removeEventListener('keydown', handleKeyDown)
      // 트리거로 포커스 복원
      const prev = previouslyFocusedRef.current
      if (prev && typeof prev.focus === 'function') {
        prev.focus()
      }
    }
  }, [active, containerRef, autoFocusFirst])
}

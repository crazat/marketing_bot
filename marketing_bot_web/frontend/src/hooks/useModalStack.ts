import { useEffect } from 'react'

/**
 * [DD2] 전역 모달 스택 — LIFO 순서로 활성 모달 추적.
 *
 * 여러 모달이 동시에 열렸을 때:
 * - Escape가 가장 위 모달만 닫음 (하위로 전파 방지)
 * - focus trap은 가장 위 모달에만 활성화되어야 함 (useFocusTrap에서 참조)
 */

type ModalId = string

const stack: ModalId[] = []
const listeners = new Set<() => void>()

function notify() {
  listeners.forEach((l) => l())
}

function push(id: ModalId) {
  if (!stack.includes(id)) {
    stack.push(id)
    notify()
  }
}

function pop(id: ModalId) {
  const idx = stack.indexOf(id)
  if (idx >= 0) {
    stack.splice(idx, 1)
    notify()
  }
}

export function useModalStack(open: boolean, id: ModalId) {
  useEffect(() => {
    if (open) {
      push(id)
      return () => pop(id)
    }
    return undefined
  }, [open, id])
}

/** 현재 가장 위 (최근 열린) 모달 id */
export function getTopModalId(): ModalId | null {
  return stack[stack.length - 1] ?? null
}

/** 이 id가 스택 최상단인가 */
export function isTopModal(id: ModalId): boolean {
  return getTopModalId() === id
}

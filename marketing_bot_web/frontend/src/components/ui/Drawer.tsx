/**
 * [RECOVER OS] Drawer — 우측 슬라이드인 디테일 패널 (440px)
 * 프로스티드 오버레이 + 슬라이드 트랜지션 + Esc/오버레이 닫기 + 포커스 트랩 + 스크롤 락.
 * .ros-drawer / .ros-drawer-ov 클래스(recover-os.css) 사용.
 */
import { useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { useFocusTrap } from '@/hooks/useFocusTrap'

interface DrawerProps {
  isOpen: boolean
  onClose: () => void
  title?: ReactNode
  /** 모노 eyebrow 라벨 */
  eyebrow?: string
  children: ReactNode
  /** 하단 고정 액션 영역 */
  footer?: ReactNode
  /** 패널 너비(px) */
  width?: number
}

let drawerLockCount = 0
let prevBodyOverflow = ''
function lockScroll() {
  if (drawerLockCount === 0) {
    prevBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }
  drawerLockCount += 1
}
function unlockScroll() {
  drawerLockCount = Math.max(0, drawerLockCount - 1)
  if (drawerLockCount === 0) {
    document.body.style.overflow = prevBodyOverflow
    prevBodyOverflow = ''
  }
}

export default function Drawer({ isOpen, onClose, title, eyebrow, children, footer, width = 440 }: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const titleId = useId()
  useFocusTrap(isOpen, panelRef)

  useEffect(() => {
    if (!isOpen) return undefined
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('keydown', onKey)
    lockScroll()
    return () => {
      document.removeEventListener('keydown', onKey)
      unlockScroll()
    }
  }, [isOpen, onClose])

  return createPortal(
    <div
      className={`ros-drawer-ov ${isOpen ? 'on' : ''}`}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
      aria-hidden={!isOpen}
    >
      <div
        ref={panelRef}
        className="ros-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        style={{ width }}
        tabIndex={-1}
      >
        {/* 헤더 */}
        <div className="flex items-start justify-between gap-4 px-[22px] pt-[22px] pb-4 border-b" style={{ borderColor: 'var(--hair)' }}>
          <div className="min-w-0">
            {eyebrow && <div className="eyebrow mb-2">{eyebrow}</div>}
            {title && <h2 id={titleId} className="ros-dr-title">{title}</h2>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-9 h-9 rounded-lg grid place-items-center text-faint hover:text-foreground hover:bg-surface-2 transition-colors flex-shrink-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            aria-label="닫기"
          >
            <X className="w-[18px] h-[18px]" strokeWidth={1.8} />
          </button>
        </div>

        {/* 본문 */}
        <div className="flex-1 overflow-y-auto px-[22px] py-5 flex flex-col gap-[22px]">
          {children}
        </div>

        {/* 푸터 */}
        {footer && (
          <div className="flex items-center gap-2.5 justify-end px-[22px] py-4 border-t" style={{ borderColor: 'var(--hair)' }}>
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}

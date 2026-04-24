import { useRef, useState, ReactNode } from 'react'
import { Check, X } from 'lucide-react'

interface SwipeableTargetItemProps {
  onSwipeRight: () => void  // 승인
  onSwipeLeft: () => void   // 스킵
  children: ReactNode
  disabled?: boolean
  threshold?: number        // 임계값 (px), 기본 100
}

/**
 * [F4] 스와이프 가능한 리스트 아이템.
 * - 좌(←)로 스와이프: 스킵
 * - 우(→)로 스와이프: 승인
 * - Pointer Events로 마우스/터치 모두 지원
 * - 의존성 없음 (react-swipeable 미사용)
 */
export default function SwipeableTargetItem({
  onSwipeRight,
  onSwipeLeft,
  children,
  disabled = false,
  threshold = 100,
}: SwipeableTargetItemProps) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [dragX, setDragX] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const startX = useRef<number | null>(null)
  const startY = useRef<number | null>(null)
  const horizontalConfirmed = useRef(false)

  const reset = () => {
    setDragX(0)
    setIsDragging(false)
    startX.current = null
    startY.current = null
    horizontalConfirmed.current = false
  }

  const onPointerDown = (e: React.PointerEvent) => {
    if (disabled) return
    // 버튼·링크 내부 클릭은 스와이프 차단
    const target = e.target as HTMLElement
    if (target.closest('button, a, input')) return
    startX.current = e.clientX
    startY.current = e.clientY
    setIsDragging(true)
    try {
      ;(e.target as Element).setPointerCapture?.(e.pointerId)
    } catch {
      // 무시
    }
  }

  const onPointerMove = (e: React.PointerEvent) => {
    if (!isDragging || startX.current === null || startY.current === null) return
    const dx = e.clientX - startX.current
    const dy = e.clientY - startY.current
    // 세로 스크롤 우선 판정 (최초 10px)
    if (!horizontalConfirmed.current) {
      if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > 10) {
        // 세로 의도 — 스와이프 취소
        reset()
        return
      }
      if (Math.abs(dx) > 10) {
        horizontalConfirmed.current = true
      } else {
        return
      }
    }
    setDragX(dx)
  }

  const onPointerUp = () => {
    if (!isDragging) return
    if (Math.abs(dragX) >= threshold) {
      if (dragX > 0) onSwipeRight()
      else onSwipeLeft()
    }
    reset()
  }

  const leftOpacity = Math.min(1, -dragX / threshold)  // 스킵 (빨강)
  const rightOpacity = Math.min(1, dragX / threshold)   // 승인 (초록)

  return (
    <div className="relative overflow-hidden rounded" ref={ref}>
      {/* 배경 액션 힌트 */}
      <div
        className="absolute inset-0 flex items-center justify-between px-4 pointer-events-none"
        style={{
          backgroundColor:
            dragX > 0
              ? `rgba(34, 197, 94, ${rightOpacity * 0.2})`
              : dragX < 0
              ? `rgba(239, 68, 68, ${leftOpacity * 0.2})`
              : 'transparent',
        }}
      >
        <div
          className="flex items-center gap-1 text-green-600"
          style={{ opacity: rightOpacity }}
        >
          <Check className="h-5 w-5" />
          <span className="text-sm font-medium">승인</span>
        </div>
        <div className="flex-1" />
        <div
          className="flex items-center gap-1 text-red-600"
          style={{ opacity: leftOpacity }}
        >
          <span className="text-sm font-medium">스킵</span>
          <X className="h-5 w-5" />
        </div>
      </div>

      {/* 실제 컨텐츠 */}
      <div
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={reset}
        onPointerLeave={(e) => {
          if (e.buttons === 0) reset()
        }}
        style={{
          transform: `translateX(${dragX}px)`,
          transition: isDragging ? 'none' : 'transform 0.2s ease-out',
          touchAction: 'pan-y',
        }}
        className="bg-background"
      >
        {children}
      </div>
    </div>
  )
}

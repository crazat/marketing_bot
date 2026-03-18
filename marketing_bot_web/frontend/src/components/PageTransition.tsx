import { ReactNode, useEffect, useState } from 'react'

interface PageTransitionProps {
  children: ReactNode
  className?: string
}

/**
 * 페이지 전환 애니메이션 래퍼 컴포넌트
 *
 * 사용법:
 * <PageTransition>
 *   <YourPageContent />
 * </PageTransition>
 */
export default function PageTransition({ children, className = '' }: PageTransitionProps) {
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    // 마운트 시 약간의 지연 후 애니메이션 시작
    const timer = requestAnimationFrame(() => {
      setIsVisible(true)
    })

    return () => cancelAnimationFrame(timer)
  }, [])

  return (
    <div
      className={`
        transition-all duration-300 ease-out
        ${isVisible
          ? 'opacity-100 translate-y-0'
          : 'opacity-0 translate-y-2'
        }
        ${className}
      `}
    >
      {children}
    </div>
  )
}

/**
 * 섹션별 순차 애니메이션을 위한 래퍼
 * stagger 효과로 자연스러운 진입 애니메이션
 */
interface StaggeredTransitionProps {
  children: ReactNode
  index: number
  baseDelay?: number
  className?: string
}

export function StaggeredTransition({
  children,
  index,
  baseDelay = 50,
  className = ''
}: StaggeredTransitionProps) {
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsVisible(true)
    }, index * baseDelay)

    return () => clearTimeout(timer)
  }, [index, baseDelay])

  return (
    <div
      className={`
        transition-all duration-300 ease-out
        ${isVisible
          ? 'opacity-100 translate-y-0'
          : 'opacity-0 translate-y-3'
        }
        ${className}
      `}
    >
      {children}
    </div>
  )
}

/**
 * 스케일 + 페이드 애니메이션 (모달, 카드용)
 */
interface ScaleTransitionProps {
  children: ReactNode
  show: boolean
  className?: string
}

export function ScaleTransition({ children, show, className = '' }: ScaleTransitionProps) {
  return (
    <div
      className={`
        transition-all duration-200 ease-out
        ${show
          ? 'opacity-100 scale-100'
          : 'opacity-0 scale-95 pointer-events-none'
        }
        ${className}
      `}
    >
      {children}
    </div>
  )
}

/**
 * 슬라이드 애니메이션 (드롭다운, 패널용)
 */
interface SlideTransitionProps {
  children: ReactNode
  show: boolean
  direction?: 'up' | 'down' | 'left' | 'right'
  className?: string
}

export function SlideTransition({
  children,
  show,
  direction = 'down',
  className = ''
}: SlideTransitionProps) {
  const directionClasses = {
    up: show ? 'translate-y-0' : '-translate-y-2',
    down: show ? 'translate-y-0' : 'translate-y-2',
    left: show ? 'translate-x-0' : '-translate-x-2',
    right: show ? 'translate-x-0' : 'translate-x-2',
  }

  return (
    <div
      className={`
        transition-all duration-200 ease-out
        ${show ? 'opacity-100' : 'opacity-0 pointer-events-none'}
        ${directionClasses[direction]}
        ${className}
      `}
    >
      {children}
    </div>
  )
}

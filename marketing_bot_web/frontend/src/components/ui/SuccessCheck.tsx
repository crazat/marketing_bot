import { useEffect, useState } from 'react'

interface SuccessCheckProps {
  /** 애니메이션 시작 여부 */
  show: boolean
  /** 체크마크 크기 (기본 48px) */
  size?: number
  /** 애니메이션 완료 콜백 */
  onComplete?: () => void
  /** 추가 CSS 클래스 */
  className?: string
  /** 성공 메시지 */
  message?: string
}

/**
 * 성공 체크마크 애니메이션 컴포넌트
 *
 * 사용법:
 * <SuccessCheck show={isSuccess} message="저장 완료!" />
 */
export default function SuccessCheck({
  show,
  size = 48,
  onComplete,
  className = '',
  message,
}: SuccessCheckProps) {
  const [isAnimating, setIsAnimating] = useState(false)
  const [showMessage, setShowMessage] = useState(false)

  useEffect(() => {
    if (show) {
      setIsAnimating(true)
      // 메시지는 체크 애니메이션 후 표시
      const messageTimer = setTimeout(() => {
        setShowMessage(true)
      }, 400)

      // 완료 콜백
      const completeTimer = setTimeout(() => {
        onComplete?.()
      }, 1000)

      return () => {
        clearTimeout(messageTimer)
        clearTimeout(completeTimer)
      }
    } else {
      setIsAnimating(false)
      setShowMessage(false)
    }
  }, [show, onComplete])

  if (!show) return null

  const strokeWidth = size / 12

  return (
    <div className={`flex flex-col items-center justify-center gap-3 ${className}`}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 52 52"
        className="success-checkmark"
        style={{
          '--size': `${size}px`,
          '--stroke-width': `${strokeWidth}px`,
        } as React.CSSProperties}
      >
        {/* 배경 원 */}
        <circle
          className={`
            fill-none stroke-green-500
            transition-all duration-500 ease-out
            ${isAnimating ? 'opacity-100' : 'opacity-0'}
          `}
          cx="26"
          cy="26"
          r="24"
          strokeWidth={strokeWidth}
          style={{
            strokeDasharray: 166,
            strokeDashoffset: isAnimating ? 0 : 166,
            transition: 'stroke-dashoffset 0.6s cubic-bezier(0.65, 0, 0.45, 1)',
          }}
        />

        {/* 체크마크 */}
        <path
          className={`
            fill-none stroke-green-500
            ${isAnimating ? 'opacity-100' : 'opacity-0'}
          `}
          d="M14 27l7 7 16-16"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            strokeDasharray: 48,
            strokeDashoffset: isAnimating ? 0 : 48,
            transition: 'stroke-dashoffset 0.3s cubic-bezier(0.65, 0, 0.45, 1) 0.4s',
          }}
        />
      </svg>

      {/* 메시지 */}
      {message && (
        <span
          className={`
            text-sm font-medium text-green-500
            transition-all duration-300
            ${showMessage ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'}
          `}
        >
          {message}
        </span>
      )}
    </div>
  )
}

/**
 * 인라인 성공 체크 (텍스트 옆에 표시되는 작은 체크마크)
 */
export function InlineSuccessCheck({
  show,
  className = '',
}: {
  show: boolean
  className?: string
}) {
  return (
    <span
      className={`
        inline-flex items-center justify-center
        w-5 h-5 rounded-full
        transition-all duration-300 ease-out
        ${show ? 'bg-green-500 scale-100 opacity-100' : 'bg-transparent scale-0 opacity-0'}
        ${className}
      `}
    >
      <svg
        className="w-3 h-3 text-white"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={3}
          d="M5 13l4 4L19 7"
        />
      </svg>
    </span>
  )
}

/**
 * 성공 오버레이 (전체 화면 성공 표시)
 */
export function SuccessOverlay({
  show,
  message = '완료!',
  onComplete,
}: {
  show: boolean
  message?: string
  onComplete?: () => void
}) {
  useEffect(() => {
    if (show) {
      const timer = setTimeout(() => {
        onComplete?.()
      }, 1500)
      return () => clearTimeout(timer)
    }
  }, [show, onComplete])

  if (!show) return null

  return (
    <div
      className={`
        fixed inset-0 z-50
        flex items-center justify-center
        bg-background/80 backdrop-blur-sm
        transition-opacity duration-300
        ${show ? 'opacity-100' : 'opacity-0'}
      `}
    >
      <div className="bg-card rounded-2xl p-8 shadow-xl border border-border">
        <SuccessCheck show={show} size={64} message={message} />
      </div>
    </div>
  )
}

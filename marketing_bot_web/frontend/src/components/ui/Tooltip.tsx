import { useState, useRef, useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

export interface TooltipProps {
  content: ReactNode
  children: ReactNode
  position?: 'top' | 'bottom' | 'left' | 'right'
  delay?: number
  disabled?: boolean
  className?: string
}

export default function Tooltip({
  content,
  children,
  position = 'top',
  delay = 200,
  disabled = false,
  className = '',
}: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false)
  const [coords, setCoords] = useState({ top: 0, left: 0 })
  const triggerRef = useRef<HTMLDivElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)

  const showTooltip = () => {
    if (disabled) return

    timeoutRef.current = setTimeout(() => {
      if (triggerRef.current) {
        const rect = triggerRef.current.getBoundingClientRect()
        const tooltipRect = tooltipRef.current?.getBoundingClientRect()
        const tooltipWidth = tooltipRect?.width || 0
        const tooltipHeight = tooltipRect?.height || 0

        let top = 0
        let left = 0

        switch (position) {
          case 'top':
            top = rect.top - tooltipHeight - 8
            left = rect.left + rect.width / 2 - tooltipWidth / 2
            break
          case 'bottom':
            top = rect.bottom + 8
            left = rect.left + rect.width / 2 - tooltipWidth / 2
            break
          case 'left':
            top = rect.top + rect.height / 2 - tooltipHeight / 2
            left = rect.left - tooltipWidth - 8
            break
          case 'right':
            top = rect.top + rect.height / 2 - tooltipHeight / 2
            left = rect.right + 8
            break
        }

        // 화면 경계 체크
        const padding = 8
        if (left < padding) left = padding
        if (left + tooltipWidth > window.innerWidth - padding) {
          left = window.innerWidth - tooltipWidth - padding
        }
        if (top < padding) top = padding
        if (top + tooltipHeight > window.innerHeight - padding) {
          top = window.innerHeight - tooltipHeight - padding
        }

        setCoords({ top, left })
        setIsVisible(true)
      }
    }, delay)
  }

  const hideTooltip = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }
    setIsVisible(false)
  }

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [])

  const arrowStyles = {
    top: 'bottom-0 left-1/2 -translate-x-1/2 translate-y-full border-t-card border-x-transparent border-b-transparent',
    bottom: 'top-0 left-1/2 -translate-x-1/2 -translate-y-full border-b-card border-x-transparent border-t-transparent',
    left: 'right-0 top-1/2 -translate-y-1/2 translate-x-full border-l-card border-y-transparent border-r-transparent',
    right: 'left-0 top-1/2 -translate-y-1/2 -translate-x-full border-r-card border-y-transparent border-l-transparent',
  }

  return (
    <>
      <div
        ref={triggerRef}
        onMouseEnter={showTooltip}
        onMouseLeave={hideTooltip}
        onFocus={showTooltip}
        onBlur={hideTooltip}
        className="inline-block"
      >
        {children}
      </div>

      {isVisible &&
        createPortal(
          <div
            ref={tooltipRef}
            role="tooltip"
            className={`
              fixed z-[100] px-3 py-2 text-sm
              bg-card text-card-foreground
              border border-border rounded-lg shadow-lg
              animate-fade-in pointer-events-none
              ${className}
            `}
            style={{
              top: coords.top,
              left: coords.left,
            }}
          >
            {content}
            <span
              className={`absolute w-0 h-0 border-4 ${arrowStyles[position]}`}
              aria-hidden="true"
            />
          </div>,
          document.body
        )}
    </>
  )
}

/**
 * 아이콘 정보 툴팁 (도움말)
 */
export function InfoTooltip({
  content,
  position = 'top',
}: {
  content: ReactNode
  position?: TooltipProps['position']
}) {
  return (
    <Tooltip content={content} position={position}>
      <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-muted text-muted-foreground text-xs cursor-help">
        ?
      </span>
    </Tooltip>
  )
}

/**
 * 잘린 텍스트 툴팁
 */
export function TruncatedText({
  text,
  maxLength = 30,
  className = '',
}: {
  text: string
  maxLength?: number
  className?: string
}) {
  const isTruncated = text.length > maxLength
  const displayText = isTruncated ? `${text.slice(0, maxLength)}...` : text

  if (!isTruncated) {
    return <span className={className}>{text}</span>
  }

  return (
    <Tooltip content={text}>
      <span className={`cursor-default ${className}`}>{displayText}</span>
    </Tooltip>
  )
}

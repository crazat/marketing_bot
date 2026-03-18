import { useState, useRef, useEffect, ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'

interface CollapsibleProps {
  /** 헤더 (항상 표시) */
  title: ReactNode
  /** 접힌 상태에서 보여줄 요약 */
  summary?: ReactNode
  /** 펼쳐질 콘텐츠 */
  children: ReactNode
  /** 기본 열림 상태 */
  defaultOpen?: boolean
  /** 제어 모드 - 외부에서 열림 상태 관리 */
  open?: boolean
  /** 열림 상태 변경 콜백 */
  onOpenChange?: (open: boolean) => void
  /** 추가 클래스 */
  className?: string
  /** 헤더 클래스 */
  headerClassName?: string
  /** 콘텐츠 클래스 */
  contentClassName?: string
  /** 아이콘 숨김 */
  hideIcon?: boolean
}

/**
 * 접기/펼치기 컴포넌트
 *
 * 긴 콘텐츠를 접고 펼칠 수 있습니다.
 */
export default function Collapsible({
  title,
  summary,
  children,
  defaultOpen = false,
  open: controlledOpen,
  onOpenChange,
  className = '',
  headerClassName = '',
  contentClassName = '',
  hideIcon = false,
}: CollapsibleProps) {
  // 제어/비제어 모드 처리
  const isControlled = controlledOpen !== undefined
  const [internalOpen, setInternalOpen] = useState(defaultOpen)
  const isOpen = isControlled ? controlledOpen : internalOpen

  const contentRef = useRef<HTMLDivElement>(null)
  const [contentHeight, setContentHeight] = useState<number | undefined>(undefined)

  // 콘텐츠 높이 계산
  useEffect(() => {
    if (contentRef.current) {
      setContentHeight(contentRef.current.scrollHeight)
    }
  }, [children])

  const handleToggle = () => {
    const newOpen = !isOpen
    if (!isControlled) {
      setInternalOpen(newOpen)
    }
    onOpenChange?.(newOpen)
  }

  return (
    <div className={`border border-border rounded-lg overflow-hidden ${className}`}>
      {/* 헤더 */}
      <button
        type="button"
        onClick={handleToggle}
        className={`
          w-full flex items-center justify-between gap-3 px-4 py-3
          bg-card hover:bg-muted/50 transition-colors text-left
          focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary
          ${headerClassName}
        `}
        aria-expanded={isOpen}
      >
        <div className="flex-1 min-w-0">
          {typeof title === 'string' ? (
            <span className="font-medium">{title}</span>
          ) : (
            title
          )}
          {/* 접힌 상태에서 요약 표시 */}
          {!isOpen && summary && (
            <div className="text-sm text-muted-foreground mt-1 truncate">
              {summary}
            </div>
          )}
        </div>

        {!hideIcon && (
          <ChevronDown
            className={`
              w-5 h-5 text-muted-foreground flex-shrink-0
              transition-transform duration-200
              ${isOpen ? 'rotate-180' : ''}
            `}
          />
        )}
      </button>

      {/* 콘텐츠 (애니메이션) */}
      <div
        className="overflow-hidden transition-all duration-200 ease-out"
        style={{
          maxHeight: isOpen ? contentHeight : 0,
          opacity: isOpen ? 1 : 0,
        }}
      >
        <div
          ref={contentRef}
          className={`px-4 py-3 border-t border-border ${contentClassName}`}
        >
          {children}
        </div>
      </div>
    </div>
  )
}

/**
 * 아코디언 그룹 - 하나만 열리도록 관리
 */
interface AccordionProps {
  children: ReactNode
  /** 동시에 여러 개 열림 허용 */
  allowMultiple?: boolean
  /** 기본 열린 인덱스 */
  defaultIndex?: number | number[]
  className?: string
}

interface AccordionItemProps {
  title: ReactNode
  children: ReactNode
  disabled?: boolean
}

export function Accordion({
  children,
  allowMultiple = false,
  defaultIndex,
  className = '',
}: AccordionProps) {
  const [openIndices, setOpenIndices] = useState<number[]>(() => {
    if (defaultIndex === undefined) return []
    return Array.isArray(defaultIndex) ? defaultIndex : [defaultIndex]
  })

  const handleToggle = (index: number) => {
    setOpenIndices(prev => {
      const isOpen = prev.includes(index)
      if (isOpen) {
        return prev.filter(i => i !== index)
      }
      if (allowMultiple) {
        return [...prev, index]
      }
      return [index]
    })
  }

  return (
    <div className={`space-y-2 ${className}`}>
      {Array.isArray(children) ? (
        children.map((child, index) => {
          if (!child || typeof child !== 'object' || !('props' in child)) {
            return child
          }
          const itemProps = child.props as AccordionItemProps
          return (
            <Collapsible
              key={index}
              title={itemProps.title}
              open={openIndices.includes(index)}
              onOpenChange={() => handleToggle(index)}
            >
              {itemProps.children}
            </Collapsible>
          )
        })
      ) : (
        children
      )}
    </div>
  )
}

export function AccordionItem({ title, children }: AccordionItemProps) {
  // 이 컴포넌트는 Accordion에서 props만 읽어서 사용함
  return (
    <Collapsible title={title}>
      {children}
    </Collapsible>
  )
}

/**
 * 간단한 세부정보 토글
 */
export function DetailsToggle({
  label = '더 보기',
  hideLabel = '접기',
  children,
  className = '',
}: {
  label?: string
  hideLabel?: string
  children: ReactNode
  className?: string
}) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="text-sm text-primary hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
      >
        {isOpen ? hideLabel : label}
      </button>
      {isOpen && (
        <div className="mt-2 animate-fade-in">
          {children}
        </div>
      )}
    </div>
  )
}

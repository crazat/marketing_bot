import { HelpCircle } from 'lucide-react'
import type { ReactNode } from 'react'
import Tooltip from './Tooltip'
import { getGlossary } from '@/utils/glossary'

interface GlossaryTermProps {
  /** glossary.ts에 정의된 키 */
  termKey: string
  /** 직접 보이는 label (생략 시 glossary term 사용) */
  children?: ReactNode
  /** 물음표 아이콘 숨김 */
  hideIcon?: boolean
  /** 툴팁 위치 */
  position?: 'top' | 'bottom' | 'left' | 'right'
}

/**
 * 도메인 용어 툴팁 래퍼
 *
 * <GlossaryTerm termKey="priority_score">우선순위</GlossaryTerm>
 *  → "우선순위" 옆에 ? 아이콘, hover 시 정의+상세 표시
 */
export default function GlossaryTerm({
  termKey,
  children,
  hideIcon = false,
  position = 'top',
}: GlossaryTermProps) {
  const entry = getGlossary(termKey)
  if (!entry) {
    return <>{children}</>
  }

  const tooltipContent = (
    <div className="max-w-xs">
      <div className="caps text-primary mb-1">{entry.term}</div>
      <div className="text-sm font-medium mb-1">{entry.short}</div>
      {entry.detail && (
        <div className="text-xs text-muted-foreground leading-relaxed mt-1.5 pt-1.5 border-t border-border/50">
          {entry.detail}
        </div>
      )}
    </div>
  )

  return (
    <Tooltip content={tooltipContent} position={position}>
      <span className="inline-flex items-center gap-1 border-b border-dotted border-muted-foreground/40 cursor-help">
        {children ?? entry.term}
        {!hideIcon && (
          <HelpCircle
            className="h-3 w-3 text-muted-foreground/60"
            aria-hidden
          />
        )}
      </span>
    </Tooltip>
  )
}

/**
 * 테이블/카드 뷰 전환 컴포넌트
 */
import { useState, useEffect } from 'react'
import { LayoutGrid, List } from 'lucide-react'

export type ViewMode = 'table' | 'card'

interface ViewToggleProps {
  value: ViewMode
  onChange: (mode: ViewMode) => void
  className?: string
}

export function ViewToggle({ value, onChange, className = '' }: ViewToggleProps) {
  return (
    <div className={`inline-flex rounded-lg border border-border bg-muted p-0.5 ${className}`}>
      <button
        onClick={() => onChange('table')}
        className={`
          flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors
          ${value === 'table'
            ? 'bg-background text-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground'
          }
        `}
        aria-pressed={value === 'table'}
        title="테이블 뷰"
      >
        <List className="w-4 h-4" />
        <span className="hidden sm:inline">테이블</span>
      </button>
      <button
        onClick={() => onChange('card')}
        className={`
          flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors
          ${value === 'card'
            ? 'bg-background text-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground'
          }
        `}
        aria-pressed={value === 'card'}
        title="카드 뷰"
      >
        <LayoutGrid className="w-4 h-4" />
        <span className="hidden sm:inline">카드</span>
      </button>
    </div>
  )
}

// 모바일 자동 감지 훅
export function useViewMode(defaultMode: ViewMode = 'table'): [ViewMode, (mode: ViewMode) => void] {
  const [mode, setMode] = useState<ViewMode>(() => {
    // 768px 미만은 모바일로 간주하여 카드 뷰 기본
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      return 'card'
    }
    return defaultMode
  })

  useEffect(() => {
    const handleResize = () => {
      // 모바일에서 테이블 뷰 선택 시 유지, 데스크톱에서 카드 뷰 선택 시 유지
      // 자동 전환은 하지 않음 (사용자 선택 존중)
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  return [mode, setMode]
}

export default ViewToggle

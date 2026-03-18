import { useState, useEffect } from 'react'
import { Keyboard, X } from 'lucide-react'

interface Shortcut {
  /** 키 조합 (예: ['Ctrl', 'S'] 또는 ['⌘', 'K']) */
  keys: string[]
  /** 설명 */
  description: string
  /** 카테고리 (선택) */
  category?: string
}

interface KeyboardShortcutsProps {
  /** 단축키 목록 */
  shortcuts: Shortcut[]
  /** 표시 모드 */
  variant?: 'inline' | 'modal' | 'popover'
  /** 추가 클래스 */
  className?: string
}

/**
 * 키보드 단축키 도움말 컴포넌트
 */
export default function KeyboardShortcuts({
  shortcuts,
  variant = 'inline',
  className = '',
}: KeyboardShortcutsProps) {
  const [isOpen, setIsOpen] = useState(false)

  // ? 키로 도움말 토글
  useEffect(() => {
    if (variant !== 'modal') return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '?' && !e.ctrlKey && !e.metaKey) {
        // 입력 필드에서는 무시
        if ((e.target as HTMLElement).tagName === 'INPUT' ||
            (e.target as HTMLElement).tagName === 'TEXTAREA') {
          return
        }
        e.preventDefault()
        setIsOpen(prev => !prev)
      }
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [variant, isOpen])

  // 카테고리별 그룹화
  const groupedShortcuts = shortcuts.reduce((acc, shortcut) => {
    const category = shortcut.category || '일반'
    if (!acc[category]) {
      acc[category] = []
    }
    acc[category].push(shortcut)
    return acc
  }, {} as Record<string, Shortcut[]>)

  const renderShortcutList = () => (
    <div className="space-y-4">
      {Object.entries(groupedShortcuts).map(([category, items]) => (
        <div key={category}>
          {Object.keys(groupedShortcuts).length > 1 && (
            <h4 className="text-sm font-medium text-muted-foreground mb-2">
              {category}
            </h4>
          )}
          <div className="space-y-2">
            {items.map((shortcut, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between gap-4"
              >
                <span className="text-sm">{shortcut.description}</span>
                <KeyCombo keys={shortcut.keys} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )

  // 인라인 모드
  if (variant === 'inline') {
    return (
      <div className={`text-sm text-muted-foreground ${className}`}>
        {renderShortcutList()}
      </div>
    )
  }

  // 팝오버/모달 모드
  return (
    <>
      {/* 트리거 버튼 */}
      <button
        onClick={() => setIsOpen(true)}
        className={`
          inline-flex items-center gap-1.5 px-2 py-1 text-xs
          text-muted-foreground hover:text-foreground
          bg-muted rounded transition-colors
          ${className}
        `}
        title="키보드 단축키 (? 키)"
      >
        <Keyboard className="w-3.5 h-3.5" />
        <span>단축키</span>
      </button>

      {/* 모달 */}
      {isOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setIsOpen(false)}
        >
          <div
            className="bg-card border border-border rounded-lg shadow-lg max-w-md w-full mx-4 animate-slide-up"
            onClick={e => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="shortcuts-title"
          >
            {/* 헤더 */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <h3 id="shortcuts-title" className="font-semibold flex items-center gap-2">
                <Keyboard className="w-5 h-5" />
                키보드 단축키
              </h3>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1 rounded hover:bg-muted transition-colors"
                aria-label="닫기"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* 내용 */}
            <div className="px-4 py-4 max-h-[60vh] overflow-y-auto">
              {renderShortcutList()}
            </div>

            {/* 푸터 */}
            <div className="px-4 py-3 border-t border-border text-xs text-muted-foreground text-center">
              <KeyCombo keys={['?']} /> 를 눌러 이 도움말을 토글할 수 있습니다
            </div>
          </div>
        </div>
      )}
    </>
  )
}

/**
 * 키 조합 표시 컴포넌트
 */
export function KeyCombo({ keys, size = 'sm' }: { keys: string[]; size?: 'xs' | 'sm' | 'md' }) {
  const sizeStyles = {
    xs: 'text-[10px] px-1 py-0.5 min-w-4',
    sm: 'text-xs px-1.5 py-0.5 min-w-5',
    md: 'text-sm px-2 py-1 min-w-6',
  }

  return (
    <div className="flex items-center gap-1">
      {keys.map((key, idx) => (
        <span key={idx}>
          <kbd
            className={`
              inline-flex items-center justify-center
              font-mono font-medium
              bg-muted border border-border rounded
              shadow-sm
              ${sizeStyles[size]}
            `}
          >
            {key}
          </kbd>
          {idx < keys.length - 1 && (
            <span className="mx-0.5 text-muted-foreground">+</span>
          )}
        </span>
      ))}
    </div>
  )
}

/**
 * 단축키 힌트 (인라인)
 */
export function ShortcutHint({
  keys,
  className = '',
}: {
  keys: string[]
  className?: string
}) {
  return (
    <span className={`inline-flex items-center gap-1 ${className}`}>
      {keys.map((key, idx) => (
        <kbd
          key={idx}
          className="text-[10px] px-1 py-0.5 bg-muted border border-border rounded font-mono"
        >
          {key}
        </kbd>
      ))}
    </span>
  )
}

/**
 * Viral Hunter 전용 단축키 설정
 */
export const VIRAL_HUNTER_SHORTCUTS: Shortcut[] = [
  { keys: ['A'], description: '현재 타겟 승인', category: '액션' },
  { keys: ['S'], description: '현재 타겟 스킵', category: '액션' },
  { keys: ['G'], description: 'AI 댓글 생성', category: '액션' },
  { keys: ['C'], description: '댓글 복사', category: '액션' },
  { keys: ['↑'], description: '이전 타겟', category: '탐색' },
  { keys: ['↓'], description: '다음 타겟', category: '탐색' },
  { keys: ['J'], description: '다음 타겟 (vim)', category: '탐색' },
  { keys: ['K'], description: '이전 타겟 (vim)', category: '탐색' },
  { keys: ['Enter'], description: '원문 보기', category: '탐색' },
  { keys: ['?'], description: '단축키 도움말', category: '기타' },
  { keys: ['Esc'], description: '선택 해제', category: '기타' },
]

/**
 * Pathfinder 전용 단축키 설정
 */
export const PATHFINDER_SHORTCUTS: Shortcut[] = [
  { keys: ['R'], description: '데이터 새로고침', category: '일반' },
  { keys: ['F'], description: '필터 열기', category: '일반' },
  { keys: ['1'], description: '수집 탭', category: '탭 전환' },
  { keys: ['2'], description: '분석 탭', category: '탭 전환' },
  { keys: ['3'], description: '활용 탭', category: '탭 전환' },
  { keys: ['4'], description: '히스토리 탭', category: '탭 전환' },
  { keys: ['5'], description: '클러스터 탭', category: '탭 전환' },
]

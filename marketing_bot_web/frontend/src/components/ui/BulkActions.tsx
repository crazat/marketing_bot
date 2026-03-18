import { useState, useRef, useEffect, useCallback } from 'react'
import Button from '@/components/ui/Button'

interface BulkActionsProps {
  selectedCount: number
  actions: Array<{
    label: string
    icon?: string
    variant?: 'default' | 'primary' | 'danger'
    onClick: () => void | Promise<void>
    confirmMessage?: string
  }>
  onSelectAll?: () => void
  onClearSelection?: () => void
  totalCount?: number
}

export default function BulkActions({
  selectedCount,
  actions,
  onSelectAll,
  onClearSelection,
  totalCount,
}: BulkActionsProps) {
  const [isProcessing, setIsProcessing] = useState(false)
  const [confirmAction, setConfirmAction] = useState<typeof actions[0] | null>(null)
  const [focusedIndex, setFocusedIndex] = useState(-1)
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([])

  // Arrow 키로 버튼 간 이동
  const handleKeyDown = useCallback((e: React.KeyboardEvent, index: number) => {
    const actionCount = actions.length
    let newIndex = index

    switch (e.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        e.preventDefault()
        newIndex = (index + 1) % actionCount
        break
      case 'ArrowLeft':
      case 'ArrowUp':
        e.preventDefault()
        newIndex = (index - 1 + actionCount) % actionCount
        break
      case 'Home':
        e.preventDefault()
        newIndex = 0
        break
      case 'End':
        e.preventDefault()
        newIndex = actionCount - 1
        break
      default:
        return
    }

    setFocusedIndex(newIndex)
    buttonRefs.current[newIndex]?.focus()
  }, [actions.length])

  if (selectedCount === 0) {
    return null
  }

  const handleAction = async (action: typeof actions[0]) => {
    if (action.confirmMessage) {
      setConfirmAction(action)
      return
    }

    await executeAction(action)
  }

  const executeAction = async (action: typeof actions[0]) => {
    setIsProcessing(true)
    setConfirmAction(null)
    try {
      await action.onClick()
    } finally {
      setIsProcessing(false)
    }
  }

  return (
    <>
      <div className="sticky top-0 z-10 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-b border-border p-3">
        <div className="flex items-center justify-between gap-4">
          {/* 선택 정보 */}
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium">
              {selectedCount}개 선택됨
              {totalCount && (
                <span className="text-muted-foreground"> / {totalCount}개</span>
              )}
            </span>

            {onSelectAll && totalCount && selectedCount < totalCount && (
              <Button
                variant="ghost"
                size="xs"
                onClick={onSelectAll}
                className="text-primary"
              >
                전체 선택
              </Button>
            )}

            {onClearSelection && (
              <Button
                variant="ghost"
                size="xs"
                onClick={onClearSelection}
              >
                선택 해제
              </Button>
            )}
          </div>

          {/* 액션 버튼들 */}
          <div className="flex items-center gap-2" role="toolbar" aria-label="일괄 작업">
            {actions.map((action, index) => (
              <Button
                key={index}
                ref={(el) => { buttonRefs.current[index] = el }}
                variant={action.variant === 'danger' ? 'danger' : action.variant === 'primary' ? 'primary' : 'secondary'}
                size="xs"
                onClick={() => handleAction(action)}
                onKeyDown={(e) => handleKeyDown(e, index)}
                disabled={isProcessing}
                tabIndex={focusedIndex === -1 || focusedIndex === index ? 0 : -1}
                aria-label={`${action.label} (${selectedCount}개 항목에 적용)`}
              >
                {action.icon && <span className="mr-1" aria-hidden="true">{action.icon}</span>}
                {action.label}
              </Button>
            ))}
          </div>
        </div>

        {/* 처리 중 표시 */}
        {isProcessing && (
          <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
            <span className="animate-spin">⏳</span>
            <span>처리 중...</span>
          </div>
        )}
      </div>

      {/* 확인 다이얼로그 */}
      {confirmAction && (
        <ConfirmDialog
          message={confirmAction.confirmMessage!}
          onConfirm={() => executeAction(confirmAction)}
          onCancel={() => setConfirmAction(null)}
          variant={confirmAction.variant}
        />
      )}
    </>
  )
}

interface ConfirmDialogProps {
  message: string
  onConfirm: () => void
  onCancel: () => void
  variant?: 'default' | 'primary' | 'danger'
}

function ConfirmDialog({
  message,
  onConfirm,
  onCancel,
  variant = 'default',
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const cancelButtonRef = useRef<HTMLButtonElement>(null)

  // 다이얼로그 열릴 때 취소 버튼에 포커스
  useEffect(() => {
    cancelButtonRef.current?.focus()
  }, [])

  // Escape 키로 닫기 및 포커스 트랩
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onCancel()
        return
      }

      // 포커스 트랩: Tab 키가 다이얼로그 내에서만 순환
      if (e.key === 'Tab') {
        const focusableElements = dialogRef.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
        if (!focusableElements || focusableElements.length === 0) return

        const firstElement = focusableElements[0]
        const lastElement = focusableElements[focusableElements.length - 1]

        if (e.shiftKey && document.activeElement === firstElement) {
          e.preventDefault()
          lastElement.focus()
        } else if (!e.shiftKey && document.activeElement === lastElement) {
          e.preventDefault()
          firstElement.focus()
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onCancel])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-message"
      onClick={(e) => {
        // 배경 클릭 시 닫기
        if (e.target === e.currentTarget) onCancel()
      }}
    >
      <div
        ref={dialogRef}
        className="bg-card border border-border rounded-lg p-6 max-w-md mx-4 shadow-lg"
      >
        <p id="confirm-dialog-message" className="text-sm mb-4">{message}</p>
        <div className="flex justify-end gap-2">
          <Button
            ref={cancelButtonRef}
            variant="secondary"
            size="sm"
            onClick={onCancel}
          >
            취소
          </Button>
          <Button
            variant={variant === 'danger' ? 'danger' : 'primary'}
            size="sm"
            onClick={onConfirm}
          >
            확인
          </Button>
        </div>
      </div>
    </div>
  )
}

/**
 * 키워드용 일괄 작업 프리셋
 */
export const KEYWORD_BULK_ACTIONS = (
  onGradeChange: (grade: string) => void,
  onExport: () => void,
  onDelete: () => void
) => [
  {
    label: 'S급으로 변경',
    icon: '🔥',
    onClick: () => onGradeChange('S'),
  },
  {
    label: 'A급으로 변경',
    icon: '🟢',
    onClick: () => onGradeChange('A'),
  },
  {
    label: 'CSV 내보내기',
    icon: '📥',
    onClick: onExport,
  },
  {
    label: '삭제',
    icon: '🗑️',
    variant: 'danger' as const,
    onClick: onDelete,
    confirmMessage: '선택한 키워드를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.',
  },
]

/**
 * 리드용 일괄 작업 프리셋
 */
export const LEAD_BULK_ACTIONS = (
  onStatusChange: (status: string) => void,
  onExport: () => void
) => [
  {
    label: '연락완료로 변경',
    icon: '📞',
    onClick: () => onStatusChange('contacted'),
  },
  {
    label: '전환으로 변경',
    icon: '✅',
    variant: 'primary' as const,
    onClick: () => onStatusChange('converted'),
  },
  {
    label: '거절로 변경',
    icon: '❌',
    onClick: () => onStatusChange('rejected'),
  },
  {
    label: 'CSV 내보내기',
    icon: '📥',
    onClick: onExport,
  },
]

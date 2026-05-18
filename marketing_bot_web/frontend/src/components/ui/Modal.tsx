import { useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import Button, { IconButton } from '@/components/ui/Button'
import { useFocusTrap } from '@/hooks/useFocusTrap'
import { isTopModal, useModalStack } from '@/hooks/useModalStack'

export interface ModalProps {
  isOpen: boolean
  onClose: () => void
  title?: string
  description?: string
  children: ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full'
  closeOnOverlay?: boolean
  closeOnEscape?: boolean
  showCloseButton?: boolean
  footer?: ReactNode
}

let scrollLockCount = 0
let previousBodyOverflow = ''

function lockBodyScroll() {
  if (scrollLockCount === 0) {
    previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }
  scrollLockCount += 1
}

function unlockBodyScroll() {
  scrollLockCount = Math.max(0, scrollLockCount - 1)
  if (scrollLockCount === 0) {
    document.body.style.overflow = previousBodyOverflow
    previousBodyOverflow = ''
  }
}

export default function Modal({
  isOpen,
  onClose,
  title,
  description,
  children,
  size = 'md',
  closeOnOverlay = true,
  closeOnEscape = true,
  showCloseButton = true,
  footer,
}: ModalProps) {
  const modalRef = useRef<HTMLDivElement>(null)
  const modalId = useId()
  const titleId = useId()
  const descriptionId = useId()
  useModalStack(isOpen, modalId)
  useFocusTrap(isOpen, modalRef)

  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && closeOnEscape && isTopModal(modalId)) {
        e.stopPropagation()
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, closeOnEscape, modalId, onClose])

  useEffect(() => {
    if (!isOpen) return undefined

    lockBodyScroll()
    return () => {
      unlockBodyScroll()
    }
  }, [isOpen])

  if (!isOpen) return null

  // [UX 개선] 반응형 모달 크기 - 태블릿에서 너무 크지 않도록 조정
  const sizeClasses = {
    sm: 'max-w-[90vw] sm:max-w-sm',
    md: 'max-w-[95vw] sm:max-w-md md:max-w-lg',
    lg: 'max-w-[95vw] sm:max-w-lg md:max-w-xl',
    xl: 'max-w-[95vw] sm:max-w-xl md:max-w-2xl lg:max-w-3xl',
    full: 'max-w-[95vw] md:max-w-[90vw] h-[90vh]',
  }

  const modalContent = (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? titleId : undefined}
      aria-describedby={description ? descriptionId : undefined}
    >
      {/* 오버레이 */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-fade-in"
        onClick={() => {
          if (closeOnOverlay && isTopModal(modalId)) onClose()
        }}
        aria-hidden="true"
      />

      {/* 모달 콘텐츠 */}
      <div
        ref={modalRef}
        tabIndex={-1}
        className={`
          relative w-full ${sizeClasses[size]}
          bg-card border border-border rounded-xl shadow-2xl
          animate-modal-enter
          max-h-[90vh] overflow-hidden
          ${size === 'full' ? 'flex flex-col' : 'flex flex-col'}
        `}
      >
        {/* 헤더 */}
        {(title || showCloseButton) && (
          <div className="flex items-start justify-between p-4 border-b border-border">
            <div>
              {title && (
                <h2 id={titleId} className="text-lg font-semibold">
                  {title}
                </h2>
              )}
              {description && (
                <p id={descriptionId} className="text-sm text-muted-foreground mt-1">
                  {description}
                </p>
              )}
            </div>
            {showCloseButton && (
              <IconButton
                icon={<X className="w-5 h-5" />}
                onClick={onClose}
                size="sm"
                aria-label="닫기"
              />
            )}
          </div>
        )}

        {/* 본문 */}
        <div className="p-4 flex-1 overflow-auto">
          {children}
        </div>

        {/* 푸터 */}
        {footer && (
          <div className="flex items-center justify-end gap-2 p-4 border-t border-border">
            {footer}
          </div>
        )}
      </div>
    </div>
  )

  return createPortal(modalContent, document.body)
}

/**
 * 확인 다이얼로그
 */
export function ConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  title = '확인',
  message,
  confirmText = '확인',
  cancelText = '취소',
  variant = 'default',
  loading = false,
}: {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  variant?: 'default' | 'danger'
  loading?: boolean
}) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      size="sm"
      closeOnOverlay={!loading}
      closeOnEscape={!loading}
      showCloseButton={!loading}
      footer={
        <>
          <Button
            onClick={onClose}
            variant="outline"
            size="sm"
            disabled={loading}
          >
            {cancelText}
          </Button>
          <Button
            onClick={onConfirm}
            variant={variant === 'danger' ? 'danger' : 'primary'}
            size="sm"
            loading={loading}
          >
            {confirmText}
          </Button>
        </>
      }
    >
      <p className="text-muted-foreground">{message}</p>
    </Modal>
  )
}

/**
 * 알림 모달
 */
export function AlertModal({
  isOpen,
  onClose,
  title,
  message,
  type = 'info',
}: {
  isOpen: boolean
  onClose: () => void
  title: string
  message: string
  type?: 'info' | 'success' | 'warning' | 'error'
}) {
  const icons = {
    info: '💡',
    success: '✅',
    warning: '⚠️',
    error: '❌',
  }

  const colors = {
    info: 'text-blue-500',
    success: 'text-green-500',
    warning: 'text-yellow-500',
    error: 'text-red-500',
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="sm">
      <div className="text-center py-4">
        <div className={`text-5xl mb-4 ${colors[type]}`}>{icons[type]}</div>
        <h3 className="text-lg font-semibold mb-2">{title}</h3>
        <p className="text-muted-foreground">{message}</p>
        <Button onClick={onClose} className="mt-6">
          확인
        </Button>
      </div>
    </Modal>
  )
}

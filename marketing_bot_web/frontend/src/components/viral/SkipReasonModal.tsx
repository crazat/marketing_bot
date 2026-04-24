import { useState, useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import { useFocusTrap } from '@/hooks/useFocusTrap'
import { useModalStack, isTopModal } from '@/hooks/useModalStack'

interface SkipReasonModalProps {
  open: boolean
  onConfirm: (reasonTag: string, note: string) => void
  onCancel: () => void
}

const REASON_TAGS: Array<{ value: string; label: string; description: string }> = [
  { value: 'ad', label: '광고/홍보글', description: '업체 직접 홍보·체험단 등' },
  { value: 'competitor_post', label: '경쟁사 직영 글', description: '경쟁 업체가 직접 작성' },
  { value: 'off_topic', label: '주제 무관', description: '우리 업종/지역과 무관' },
  { value: 'low_quality', label: '저품질/스팸', description: '짧거나 성의 없는 글' },
  { value: 'out_of_region', label: '지역 불일치', description: '타 지역 질문 · 권유 불가' },
  { value: 'already_answered', label: '이미 답변됨', description: '경쟁사 또는 우리가 이미 댓글' },
  { value: 'too_old', label: '오래된 글', description: '노출 가치 낮음' },
  { value: 'other', label: '기타', description: '직접 입력' },
]

export default function SkipReasonModal({ open, onConfirm, onCancel }: SkipReasonModalProps) {
  const [selected, setSelected] = useState<string>('')
  const [note, setNote] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)
  const MODAL_ID = 'skip-reason'
  useModalStack(open, MODAL_ID)
  useFocusTrap(open, containerRef, { autoFocusFirst: false })

  useEffect(() => {
    if (!open) {
      setSelected('')
      setNote('')
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      // [DD2] 최상단 모달만 반응
      if (!isTopModal(MODAL_ID)) return
      if (e.key === 'Escape') onCancel()
      // 숫자 1-8로 사유 빠르게 선택
      const idx = parseInt(e.key, 10)
      if (idx >= 1 && idx <= REASON_TAGS.length) {
        e.preventDefault()
        setSelected(REASON_TAGS[idx - 1].value)
      }
      if (e.key === 'Enter' && selected) {
        e.preventDefault()
        onConfirm(selected, note)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, selected, note, onCancel, onConfirm])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="skip-reason-title"
        className="bg-card border border-border rounded-t-xl sm:rounded-xl p-5 sm:p-6 max-w-lg w-full sm:mx-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 id="skip-reason-title" className="text-base font-semibold">⏭️ 스킵 사유 (선택)</h3>
          <button
            onClick={onCancel}
            className="p-1 rounded hover:bg-muted"
            aria-label="닫기"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="text-xs text-muted-foreground mb-3">
          같은 도메인·작성자가 반복 스킵되면 다음 스캔에서 자동 감점됩니다.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 mb-3">
          {REASON_TAGS.map((tag, idx) => {
            const isSelected = selected === tag.value
            return (
              <button
                key={tag.value}
                onClick={() => setSelected(tag.value)}
                className={`text-left px-3 py-2 rounded border transition-colors ${
                  isSelected
                    ? 'border-primary bg-primary/10'
                    : 'border-border hover:bg-muted/50'
                }`}
              >
                <div className="flex items-center gap-2">
                  <kbd className="text-[10px] font-mono px-1 rounded bg-muted/60">
                    {idx + 1}
                  </kbd>
                  <span className="text-sm font-medium">{tag.label}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5 ml-6">{tag.description}</p>
              </button>
            )
          })}
        </div>

        {selected === 'other' && (
          <input
            autoFocus
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="사유를 직접 입력하세요"
            className="w-full mb-3 px-3 py-2 text-sm border border-border rounded bg-background"
            maxLength={200}
          />
        )}

        <div className="flex justify-end gap-2 mt-3">
          <button
            onClick={onCancel}
            className="px-3 py-2 text-sm rounded border border-border hover:bg-muted"
          >
            취소
          </button>
          <button
            onClick={() => onConfirm(selected || 'unspecified', note)}
            className="px-4 py-2 text-sm font-medium rounded bg-primary text-primary-foreground hover:bg-primary/90"
          >
            사유 없이 스킵
          </button>
          <button
            onClick={() => onConfirm(selected, note)}
            disabled={!selected}
            className="px-4 py-2 text-sm font-medium rounded bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-40"
          >
            스킵 (Enter)
          </button>
        </div>

        <p className="text-[10px] text-muted-foreground text-center mt-3">
          숫자 1-8로 빠르게 선택 · Enter 확정 · Esc 취소
        </p>
      </div>
    </div>
  )
}

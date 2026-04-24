import { useEffect, useRef } from 'react'
import { AlertTriangle, CheckCircle2, Trash2, SkipForward, X } from 'lucide-react'
import { useFocusTrap } from '@/hooks/useFocusTrap'
import { useModalStack, isTopModal } from '@/hooks/useModalStack'

export type BulkAction = 'approve' | 'skip' | 'delete'

interface FilterSummary {
  label: string
  value: string
}

interface BulkConfirmModalProps {
  open: boolean
  action: BulkAction
  totalCount: number
  /** 영향받을 필터 요약 — 주요 필터만 (카테고리, 플랫폼, 상태 등) */
  filterSummary?: FilterSummary[]
  onConfirm: () => void
  onCancel: () => void
  isProcessing?: boolean
}

const ACTION_CONFIG: Record<
  BulkAction,
  { label: string; Icon: typeof CheckCircle2; tone: string; btn: string }
> = {
  approve: {
    label: '승인',
    Icon: CheckCircle2,
    tone: 'text-emerald-600 dark:text-emerald-400',
    btn: 'bg-emerald-600 hover:bg-emerald-700 text-white',
  },
  skip: {
    label: '스킵',
    Icon: SkipForward,
    tone: 'text-amber-600 dark:text-amber-400',
    btn: 'bg-amber-500 hover:bg-amber-600 text-white',
  },
  delete: {
    label: '삭제',
    Icon: Trash2,
    tone: 'text-red-600 dark:text-red-400',
    btn: 'bg-red-600 hover:bg-red-700 text-white',
  },
}

function getRiskLevel(count: number): { level: 'normal' | 'warning' | 'critical'; label: string; color: string } {
  if (count >= 500) return { level: 'critical', label: '치명적 규모', color: 'bg-red-500/10 border-red-500/40 text-red-600' }
  if (count >= 100) return { level: 'warning', label: '대규모 작업', color: 'bg-amber-500/10 border-amber-500/40 text-amber-600' }
  return { level: 'normal', label: '일반 규모', color: 'bg-muted/40 border-border text-muted-foreground' }
}

/**
 * [X5] 대량 작업 미리보기 다이얼로그
 *
 * 영향 범위·위험도·되돌리기 가능 여부를 한눈에 보여주고
 * 사용자가 확신 갖고 진행할 수 있도록 설계.
 */
export default function BulkConfirmModal({
  open,
  action,
  totalCount,
  filterSummary = [],
  onConfirm,
  onCancel,
  isProcessing = false,
}: BulkConfirmModalProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const MODAL_ID = 'bulk-confirm'
  useModalStack(open, MODAL_ID)
  useFocusTrap(open, containerRef)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      // [DD2] 최상단 모달만 Escape에 반응
      if (e.key === 'Escape' && !isProcessing && isTopModal(MODAL_ID)) onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onCancel, isProcessing])

  if (!open) return null

  const config = ACTION_CONFIG[action]
  const risk = getRiskLevel(totalCount)
  const Icon = config.Icon
  const reversible = action !== 'delete'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="bulk-confirm-title"
    >
      <div
        ref={containerRef}
        className="relative bg-card border border-border w-[92vw] max-w-lg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-start justify-between p-5 border-b border-border">
          <div className="flex items-start gap-3">
            <div className={`p-2 rounded ${config.tone} bg-current/10`}>
              <Icon className="w-5 h-5" />
            </div>
            <div>
              <div className="caps text-muted-foreground mb-1">대량 작업 확인</div>
              <h2 id="bulk-confirm-title" className="font-display text-xl leading-tight">
                {totalCount.toLocaleString()}건을 <span className={config.tone}>{config.label}</span>하시겠습니까?
              </h2>
            </div>
          </div>
          <button
            onClick={onCancel}
            className="p-1 hover:bg-muted rounded transition-colors"
            aria-label="닫기"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 위험도 & 세부 */}
        <div className="p-5 space-y-4">
          <div className={`border p-3 flex items-start gap-2 text-sm ${risk.color}`}>
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="flex-1">
              <div className="font-semibold">{risk.label}</div>
              <div className="text-xs mt-0.5 opacity-80">
                {totalCount.toLocaleString()}건에 동시 적용됩니다.
                {!reversible && ' 삭제는 되돌릴 수 없습니다.'}
                {reversible && ' 개별 타겟은 "되돌리기"로 복구 가능합니다.'}
              </div>
            </div>
          </div>

          {/* 필터 요약 */}
          {filterSummary.length > 0 && (
            <div>
              <div className="caps text-muted-foreground mb-2">적용되는 필터</div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
                {filterSummary.map((f) => (
                  <div key={f.label} className="contents">
                    <dt className="text-muted-foreground">{f.label}</dt>
                    <dd className="font-medium text-foreground truncate">{f.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          {/* 치명적 규모 경고 추가 문구 */}
          {risk.level === 'critical' && (
            <div className="text-xs text-red-600 dark:text-red-400 bg-red-500/5 border-l-2 border-red-500 pl-3 py-2">
              500건 이상의 대량 작업입니다. 필터 조건을 먼저 검토하세요.
            </div>
          )}
        </div>

        {/* 액션 */}
        <div className="flex items-center justify-end gap-2 p-4 border-t border-border bg-muted/20">
          <button
            onClick={onCancel}
            disabled={isProcessing}
            className="px-4 py-2 text-sm rounded border border-border hover:bg-muted disabled:opacity-40"
          >
            취소
          </button>
          <button
            onClick={onConfirm}
            disabled={isProcessing}
            className={`px-4 py-2 text-sm font-medium rounded ${config.btn} disabled:opacity-40 flex items-center gap-2`}
          >
            {isProcessing ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                처리 중...
              </>
            ) : (
              <>
                <Icon className="w-4 h-4" />
                {totalCount.toLocaleString()}건 {config.label}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

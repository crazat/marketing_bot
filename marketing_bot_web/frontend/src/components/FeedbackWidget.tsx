import { useEffect, useRef, useState } from 'react'
import { MessageSquarePlus, X, Bug, Lightbulb, Heart } from 'lucide-react'
import { useFocusTrap } from '@/hooks/useFocusTrap'
import { useModalStack, isTopModal } from '@/hooks/useModalStack'
import { useToast } from '@/components/ui/Toast'
import { logger } from '@/utils/logger'

const STORAGE_KEY = 'marketing-bot-feedback-queue-v1'
const MAX_QUEUE = 30

type FeedbackKind = 'bug' | 'idea' | 'praise'

interface FeedbackEntry {
  id: string
  kind: FeedbackKind
  message: string
  path: string
  userAgent: string
  timestamp: number
}

const KIND_CONFIG: Record<FeedbackKind, { Icon: typeof Bug; label: string; tone: string }> = {
  bug: { Icon: Bug, label: '버그 신고', tone: 'text-red-500' },
  idea: { Icon: Lightbulb, label: '개선 제안', tone: 'text-amber-500' },
  praise: { Icon: Heart, label: '칭찬/응원', tone: 'text-emerald-500' },
}

function enqueueFeedback(entry: FeedbackEntry) {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const arr: FeedbackEntry[] = raw ? JSON.parse(raw) : []
    arr.push(entry)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(arr.slice(-MAX_QUEUE)))
  } catch (err) {
    logger.warn('feedback enqueue 실패', err)
  }
}

/**
 * [AA5] 피드백 위젯 — 플로팅 버튼 + 모달
 *
 * 화면 우측 하단 상시 노출 (모바일 탭바 위). 사용자가 버그/제안/칭찬을 빠르게 전달.
 * 백엔드 엔드포인트 없어도 localStorage 큐에 저장 → 추후 관리자가 추출 가능.
 */
export default function FeedbackWidget() {
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<FeedbackKind>('idea')
  const [message, setMessage] = useState('')
  const toast = useToast()
  const containerRef = useRef<HTMLDivElement>(null)
  const MODAL_ID = 'feedback-widget'
  useModalStack(open, MODAL_ID)
  useFocusTrap(open, containerRef)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      // [DD2] 최상단 모달만 Escape 반응
      if (e.key === 'Escape' && isTopModal(MODAL_ID)) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const handleSubmit = () => {
    const trimmed = message.trim()
    if (!trimmed) return
    enqueueFeedback({
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      kind,
      message: trimmed,
      path: window.location.pathname,
      userAgent: navigator.userAgent,
      timestamp: Date.now(),
    })
    toast.success('피드백 감사합니다! 개선에 반영하겠습니다.')
    setMessage('')
    setKind('idea')
    setOpen(false)
  }

  return (
    <>
      {/* 플로팅 버튼 — 모바일 탭바 위 */}
      <button
        onClick={() => setOpen(true)}
        aria-label="피드백 보내기"
        className="fixed bottom-20 md:bottom-6 right-4 md:right-6 z-40 inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium bg-card border border-border shadow-lg hover:border-primary/50 hover:bg-muted/30 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <MessageSquarePlus className="w-3.5 h-3.5" aria-hidden />
        <span>피드백</span>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="feedback-title"
        >
          <div
            ref={containerRef}
            onClick={(e) => e.stopPropagation()}
            className="relative bg-card border border-border w-[92vw] max-w-md p-6 shadow-2xl"
          >
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="caps text-muted-foreground mb-1">Feedback</div>
                <h2 id="feedback-title" className="font-display text-xl leading-tight">
                  의견을 들려주세요
                </h2>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="p-1 hover:bg-muted rounded"
                aria-label="닫기"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* 유형 선택 */}
            <div className="grid grid-cols-3 gap-2 mb-4">
              {(Object.keys(KIND_CONFIG) as FeedbackKind[]).map((k) => {
                const cfg = KIND_CONFIG[k]
                const Icon = cfg.Icon
                const selected = kind === k
                return (
                  <button
                    key={k}
                    onClick={() => setKind(k)}
                    className={`flex flex-col items-center gap-1 px-2 py-3 border transition-all ${
                      selected
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:bg-muted/30'
                    }`}
                  >
                    <Icon className={`w-5 h-5 ${cfg.tone}`} aria-hidden />
                    <span className="text-xs">{cfg.label}</span>
                  </button>
                )
              })}
            </div>

            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder={
                kind === 'bug'
                  ? '어떤 버그를 발견하셨나요? 재현 방법도 함께 알려주세요.'
                  : kind === 'idea'
                  ? '어떤 기능이 있으면 좋을까요?'
                  : '좋아하시는 점을 알려주세요!'
              }
              className="w-full h-24 p-3 text-sm bg-background border border-border focus:outline-none focus:ring-2 focus:ring-primary resize-none"
              maxLength={500}
            />

            <div className="flex items-center justify-between mt-3">
              <span className="text-[11px] text-muted-foreground">
                {message.length}/500 · 현재 페이지 자동 포함
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setOpen(false)}
                  className="px-3 py-1.5 text-xs rounded border border-border hover:bg-muted"
                >
                  취소
                </button>
                <button
                  onClick={handleSubmit}
                  disabled={!message.trim()}
                  className="px-4 py-1.5 text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40"
                >
                  보내기
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

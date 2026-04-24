import { useEffect, useState, useCallback, useRef } from 'react'
import { X, ChevronRight, Keyboard } from 'lucide-react'
import { useFocusTrap } from '@/hooks/useFocusTrap'
import { useModalStack, isTopModal } from '@/hooks/useModalStack'

const STORAGE_KEY = 'marketing-bot-onboarding-v1'

interface Step {
  eyebrow: string
  headline: string
  body: string
  hint?: string
}

const STEPS: Step[] = [
  {
    eyebrow: 'Step 01 · 시작',
    headline: '오늘의 집중부터 보세요',
    body: '대시보드 상단의 "오늘의 집중" 카드는 가장 긴급한 한 가지 행동을 먼저 제시합니다. 아래 상세 분석은 접혀 있으니 필요할 때만 펼쳐 보세요.',
  },
  {
    eyebrow: 'Step 02 · 작업',
    headline: 'Viral Hunter에서 빠르게 처리',
    body: 'HOT LEAD 카테고리 카드를 열면 한 건씩 펼쳐 AI 댓글을 생성·승인·스킵할 수 있습니다. 스킵은 S 키로 즉시, Shift+S 로 사유 선택이 가능합니다.',
    hint: '단축키: A 승인 · S 스킵 · D 삭제 · G 댓글 생성',
  },
  {
    eyebrow: 'Step 03 · 탐색',
    headline: '? 키로 언제든 도움말',
    body: '어떤 페이지에서든 ? 를 누르면 단축키 오버레이가 열립니다. 경로는 페이지 상단 breadcrumb에서 확인하세요.',
    hint: '? 단축키 · Cmd/Ctrl+K 명령 팔레트',
  },
]

export default function OnboardingTour() {
  const [step, setStep] = useState(0)
  const [visible, setVisible] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const MODAL_ID = 'onboarding-tour'
  useModalStack(visible, MODAL_ID)
  useFocusTrap(visible, containerRef)

  useEffect(() => {
    try {
      const seen = localStorage.getItem(STORAGE_KEY)
      if (!seen) setVisible(true)
    } catch {
      // localStorage 접근 실패 시 조용히 무시
    }
  }, [])

  const dismiss = useCallback(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(Date.now()))
    } catch {
      // ignore
    }
    setVisible(false)
  }, [])

  const next = useCallback(() => {
    if (step < STEPS.length - 1) {
      setStep((s) => s + 1)
    } else {
      dismiss()
    }
  }, [step, dismiss])

  useEffect(() => {
    if (!visible) return
    const onKey = (e: KeyboardEvent) => {
      // [DD2] 다른 모달 열려있으면 무시
      if (!isTopModal(MODAL_ID)) return
      if (e.key === 'Escape') dismiss()
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        next()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [visible, dismiss, next])

  if (!visible) return null

  const current = STEPS[step]
  const isLast = step === STEPS.length - 1

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-sm animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label="사용 가이드"
    >
      <div
        ref={containerRef}
        className="relative bg-card border border-border max-w-lg w-[90vw] p-7 md:p-9 shadow-2xl overflow-hidden animate-slide-up"
      >
        <span
          aria-hidden
          className="absolute right-4 top-2 text-[9rem] leading-none font-display text-foreground/[0.04] select-none pointer-events-none"
        >
          案
        </span>
        <button
          onClick={dismiss}
          className="absolute top-3 right-3 p-1.5 rounded hover:bg-muted transition-colors"
          aria-label="닫기"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="relative">
          <div className="caps text-primary mb-4">{current.eyebrow}</div>
          <h2 className="font-display text-2xl md:text-3xl leading-tight tracking-tight mb-3">
            {current.headline}
          </h2>
          <p className="text-sm md:text-base text-muted-foreground leading-relaxed mb-5">
            {current.body}
          </p>
          {current.hint && (
            <div className="flex items-center gap-2 text-xs text-foreground/70 bg-muted/40 border border-border px-3 py-2 mb-5">
              <Keyboard className="h-3.5 w-3.5 shrink-0" />
              <span>{current.hint}</span>
            </div>
          )}

          <div className="flex items-center justify-between mt-6">
            <div className="flex items-center gap-1.5">
              {STEPS.map((_, idx) => (
                <span
                  key={idx}
                  className={`h-1 transition-all ${
                    idx === step
                      ? 'w-8 bg-primary'
                      : idx < step
                      ? 'w-4 bg-primary/40'
                      : 'w-4 bg-border'
                  }`}
                />
              ))}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={dismiss}
                className="text-xs text-muted-foreground hover:text-foreground px-3 py-2 transition-colors"
              >
                건너뛰기
              </button>
              <button
                onClick={next}
                className="inline-flex items-center gap-1.5 bg-primary text-primary-foreground px-4 py-2 font-medium hover:bg-primary/90 transition-colors"
              >
                {isLast ? '시작하기' : '다음'}
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>

          <p className="text-[10px] text-muted-foreground text-center mt-4">
            Enter 다음 · Esc 닫기 · 이 안내는 한 번만 표시됩니다
          </p>
        </div>
      </div>
    </div>
  )
}

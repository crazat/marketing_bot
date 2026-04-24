import { useState } from 'react'
import { Zap, X } from 'lucide-react'
import { usePatternDetector } from '@/hooks/usePatternDetector'

const DISMISS_KEY = 'marketing-bot-pattern-dismissed-v1'

function loadDismissed(): Record<string, number> {
  try {
    const raw = localStorage.getItem(DISMISS_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function saveDismissed(obj: Record<string, number>) {
  try {
    localStorage.setItem(DISMISS_KEY, JSON.stringify(obj))
  } catch {
    // ignore
  }
}

/**
 * [BB4] 패턴 자동화 제안 배너 — Dashboard 또는 ViralHunter 상단
 *
 * 10연속 같은 카테고리 액션 감지 시 한 번만 표시.
 * 사용자가 닫으면 12시간 침묵.
 */
export default function PatternSuggestion() {
  const patterns = usePatternDetector()
  const [dismissed, setDismissed] = useState<Record<string, number>>(() => loadDismissed())

  if (patterns.length === 0) return null

  const visible = patterns.find((p) => {
    const key = `${p.kind}:${p.context}`
    const until = dismissed[key]
    return !until || Date.now() > until
  })
  if (!visible) return null

  const handleDismiss = () => {
    const key = `${visible.kind}:${visible.context}`
    const next = { ...dismissed, [key]: Date.now() + 12 * 3600_000 }
    setDismissed(next)
    saveDismissed(next)
  }

  return (
    <section
      aria-label="패턴 감지"
      className="bg-card border border-primary/30 p-4 flex items-start gap-3"
    >
      <Zap className="w-5 h-5 text-primary shrink-0 mt-0.5" aria-hidden />
      <div className="flex-1 min-w-0">
        <div className="caps text-primary mb-1">패턴 감지 · Coaching</div>
        <h3 className="font-display text-base leading-tight">{visible.message}</h3>
        <p className="text-xs text-muted-foreground mt-1">{visible.suggestion}</p>
      </div>
      <button
        onClick={handleDismiss}
        className="p-1 hover:bg-muted rounded shrink-0"
        aria-label="닫기 — 12시간 침묵"
      >
        <X className="w-4 h-4" />
      </button>
    </section>
  )
}

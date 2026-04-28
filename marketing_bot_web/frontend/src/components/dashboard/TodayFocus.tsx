import type { ReactElement } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Flame, Clock, Activity } from 'lucide-react'
import { viralApi } from '@/services/api'

/**
 * [Z4] Today Focus — Dashboard 최상단 단일 CTA 카드.
 *
 * Hick's law 대응: 여러 위젯에 분산된 "지금 뭐 해야 하지?"를
 * 하나의 큰 카드로 수렴. 가장 긴급한 한 가지 행동을 먼저 제시.
 *
 * 우선순위 로직:
 *  1. 🔥 Tier 1 HOT LEAD (priority_score >= 120) — 즉시 처리
 *  2. 📮 오늘 대기 중 HOT LEAD (100+)
 *  3. ⏰ 24h 초과 리드 (과기)
 *  4. 정상 상태: "오늘 새 스캔을 실행해 보세요"
 */
export default function TodayFocus() {
  const navigate = useNavigate()

  // 긴급 타겟
  const { data: tier1 } = useQuery({
    queryKey: ['today-focus-tier1'],
    queryFn: () =>
      viralApi.getTargetsCount('pending', undefined, {
        min_scan_count: undefined,
      }).catch(() => ({ total: 0 })),
    staleTime: 60_000,
  })

  // 오늘의 HOT LEAD
  const { data: todayQueue } = useQuery({
    queryKey: ['today-focus-queue'],
    queryFn: () => viralApi.getTodaysQueue(10, 3, true).catch(() => null),
    staleTime: 60_000,
  })

  // 렌더링 결정
  const hotCount = todayQueue?.total ?? 0
  const pendingTotal = (tier1 as { total?: number })?.total ?? 0

  // Primary focus 결정
  let focus: {
    tone: 'urgent' | 'warning' | 'calm'
    icon: ReactElement
    eyebrow: string
    headline: string
    body: string
    cta: string
    action: () => void
  }

  if (hotCount >= 1) {
    focus = {
      tone: 'urgent',
      icon: <Flame className="h-5 w-5" />,
      eyebrow: '오늘의 집중',
      headline: `오늘 발견된 HOT LEAD ${hotCount.toLocaleString()}건`,
      body: '점수 80+ 고우선순위 타겟이 대기 중입니다. 바이럴 헌터 홈의 "오늘의 작업 큐"에서 바로 처리하세요.',
      cta: '작업 큐 열기',
      action: () => navigate('/viral-hunter'),
    }
  } else if (pendingTotal >= 10) {
    focus = {
      tone: 'warning',
      icon: <Clock className="h-5 w-5" />,
      eyebrow: '오늘의 집중',
      headline: `대기 중 ${pendingTotal.toLocaleString()}건 리뷰 필요`,
      body: '오늘 새로 발견된 건은 없지만 누적 대기분을 정리할 좋은 시간입니다.',
      cta: '전체 목록 열기',
      action: () => navigate('/viral-hunter'),
    }
  } else {
    focus = {
      tone: 'calm',
      icon: <Activity className="h-5 w-5" />,
      eyebrow: '오늘의 집중',
      headline: '모든 대기 건 정리 완료',
      body: '새로운 스캔을 실행해 오늘의 기회를 찾아보세요.',
      cta: '스캔 실행',
      action: () => navigate('/viral-hunter'),
    }
  }

  const toneClass =
    focus.tone === 'urgent'
      ? 'border-accent/40 bg-gradient-to-br from-accent/10 via-card to-card'
      : focus.tone === 'warning'
      ? 'border-primary/30 bg-gradient-to-br from-primary/5 via-card to-card'
      : 'border-border bg-card'
  const iconTone =
    focus.tone === 'urgent'
      ? 'text-accent'
      : focus.tone === 'warning'
      ? 'text-primary'
      : 'text-muted-foreground'

  return (
    <section
      aria-label="오늘의 집중 작업"
      className={`relative border ${toneClass} p-6 md:p-8 overflow-hidden`}
    >
      {/* 디자인 장식: 한자 이니셜 */}
      <span
        aria-hidden
        className="absolute right-4 top-2 text-[8rem] md:text-[10rem] leading-none font-display text-foreground/[0.03] select-none pointer-events-none"
      >
        集
      </span>

      <div className="relative flex items-start justify-between gap-6 flex-wrap">
        <div className="flex-1 min-w-0 max-w-2xl">
          <div className={`caps flex items-center gap-2 mb-4 ${iconTone}`}>
            <span>{focus.icon}</span>
            <span>{focus.eyebrow}</span>
          </div>

          <h2 className="font-display text-2xl md:text-3xl lg:text-4xl leading-tight tracking-tight mb-3">
            {focus.headline}
          </h2>

          <p className="text-sm md:text-base text-muted-foreground leading-relaxed mb-6">
            {focus.body}
          </p>

          <button
            onClick={focus.action}
            className={`group inline-flex items-center gap-2 px-5 py-2.5 font-medium transition-all ${
              focus.tone === 'urgent'
                ? 'bg-accent text-accent-foreground hover:bg-accent/90'
                : 'bg-primary text-primary-foreground hover:bg-primary/90'
            }`}
          >
            {focus.cta}
            <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
          </button>
        </div>
      </div>
    </section>
  )
}

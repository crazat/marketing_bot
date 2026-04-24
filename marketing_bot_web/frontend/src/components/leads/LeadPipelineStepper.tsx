import { Check, Phone, MessageCircle, TrendingUp, XCircle } from 'lucide-react'

type LeadStatus = 'pending' | 'contacted' | 'replied' | 'converted' | 'rejected'

interface Step {
  key: LeadStatus
  label: string
  Icon: typeof Check
}

const HAPPY_PATH: Step[] = [
  { key: 'pending', label: '대기', Icon: Check },
  { key: 'contacted', label: '컨택', Icon: Phone },
  { key: 'replied', label: '응답', Icon: MessageCircle },
  { key: 'converted', label: '전환', Icon: TrendingUp },
]

function computeProgress(status: LeadStatus): number {
  // rejected는 별도 처리 - 별도 경로
  if (status === 'rejected') return -1
  const idx = HAPPY_PATH.findIndex((s) => s.key === status)
  return idx === -1 ? 0 : idx
}

/**
 * [Y2] 리드 파이프라인 스테퍼 — 4단계 시각화
 *
 * 현재 상태까지의 스텝은 채워진 상태, 이후는 빈 상태.
 * rejected는 별도 빨간 X 표시.
 */
export default function LeadPipelineStepper({ status }: { status: LeadStatus }) {
  const activeIndex = computeProgress(status)
  const isRejected = status === 'rejected'

  if (isRejected) {
    return (
      <div className="flex items-center gap-3 p-3 bg-red-500/5 border border-red-500/30">
        <XCircle className="w-5 h-5 text-red-500" aria-hidden />
        <div>
          <div className="text-sm font-semibold text-red-600 dark:text-red-400">거절됨</div>
          <div className="text-xs text-muted-foreground">이 리드는 전환되지 않았습니다.</div>
        </div>
      </div>
    )
  }

  return (
    <div className="py-2" aria-label={`리드 진행 단계: ${HAPPY_PATH[activeIndex]?.label ?? '알 수 없음'}`}>
      <ol className="flex items-center justify-between relative">
        {/* 연결선 배경 */}
        <div
          aria-hidden
          className="absolute top-4 left-[10%] right-[10%] h-0.5 bg-border"
        />
        {/* 진행된 연결선 */}
        <div
          aria-hidden
          className="absolute top-4 left-[10%] h-0.5 bg-primary transition-all duration-500"
          style={{
            width: activeIndex > 0
              ? `${(activeIndex / (HAPPY_PATH.length - 1)) * 80}%`
              : '0%',
          }}
        />

        {HAPPY_PATH.map((step, idx) => {
          const isDone = idx <= activeIndex
          const isCurrent = idx === activeIndex
          const Icon = step.Icon

          return (
            <li
              key={step.key}
              className="relative z-10 flex flex-col items-center gap-1.5"
              aria-current={isCurrent ? 'step' : undefined}
            >
              <span
                className={`flex items-center justify-center w-8 h-8 rounded-full border-2 transition-all ${
                  isDone
                    ? 'bg-primary border-primary text-primary-foreground'
                    : 'bg-card border-border text-muted-foreground'
                } ${isCurrent ? 'ring-4 ring-primary/20' : ''}`}
              >
                <Icon className="w-4 h-4" aria-hidden />
              </span>
              <span
                className={`text-[11px] font-medium ${
                  isDone ? 'text-foreground' : 'text-muted-foreground'
                }`}
              >
                {step.label}
              </span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

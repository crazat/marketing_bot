import { HelpCircle } from 'lucide-react'
import Tooltip from '@/components/ui/Tooltip'
import type { ViralTargetData } from '@/types/viral'

interface PriorityScoreExplainProps {
  target: ViralTargetData
}

interface Contribution {
  label: string
  points: number
  note: string
  prefix?: string
}

/**
 * [BB3] Priority Score 설명 가능성
 *
 * priority_score가 왜 이 값인지를 사용 가능한 필드로 해석해 보여줌.
 * 백엔드 score_breakdown이 있으면 실제 신호를 우선 사용하고, 없을 때만
 * 프론트 heuristic으로 근사.
 */
function parseScoreBreakdown(target: ViralTargetData): Record<string, number | string | boolean | null> {
  const raw = target.score_breakdown
  if (!raw) return {}
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object' ? parsed : {}
    } catch {
      return {}
    }
  }
  return raw
}

function num(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function compactSignals(value: unknown): string {
  if (!value || typeof value !== 'string') return ''
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 3)
    .join(', ')
}

function computeContributions(target: ViralTargetData): Contribution[] {
  const contributions: Contribution[] = []
  const breakdown = parseScoreBreakdown(target)
  const hasBackendBreakdown = Object.keys(breakdown).length > 0

  if (hasBackendBreakdown) {
    const clinicFit = num(breakdown.clinic_treatment_fit_score)
    const worksite = num(breakdown.worksite_efficiency_score)
    const viralNeed = num(breakdown.viral_need_score)
    const reply = num(breakdown.reply_opportunity_score)
    const timing = num(breakdown.timing_window_score)
    const journey = num(breakdown.journey_fit_score)
    const qualification = num(breakdown.qualification_fit_score)

    if (clinicFit > 0) {
      const signals = compactSignals(breakdown.clinic_treatment_fit_signals)
      contributions.push({
        label: '진료 적합도',
        points: Math.round(clinicFit),
        prefix: '',
        note: signals ? `규림 진료축 매칭: ${signals}` : '청주 규림 진료 포트폴리오와의 적합도',
      })
    }
    if (worksite > 0) {
      const signals = compactSignals(breakdown.worksite_efficiency_signals)
      contributions.push({
        label: '작업 지점 효율',
        points: Math.round(worksite),
        prefix: '',
        note: signals ? `응대 표면 품질: ${signals}` : '댓글/응대하기 좋은 공개 지점인지 평가',
      })
    }
    if (viralNeed > 0) {
      contributions.push({
        label: '바이럴 수요',
        points: Math.round(viralNeed),
        prefix: '',
        note: String(breakdown.viral_need_tier || '질문·추천·비용·방문 의도 평가'),
      })
    }
    if (reply > 0) {
      contributions.push({
        label: '응답 가능성',
        points: Math.round(reply),
        prefix: '',
        note: String(breakdown.reply_opportunity_tier || '답변이 자연스럽고 유용한지 평가'),
      })
    }
    if (timing > 0) {
      contributions.push({
        label: '타이밍',
        points: Math.round(timing),
        prefix: '',
        note: String(breakdown.timing_window_tier || '게시 후 응답 유효 시간대 평가'),
      })
    }
    if (journey > 0 || qualification > 0) {
      contributions.push({
        label: '전환 여정',
        points: Math.round((journey + qualification) / (journey && qualification ? 2 : 1)),
        prefix: '',
        note: `${breakdown.journey_stage || 'unknown'} · ${breakdown.qualification_tier || 'qualification'}`,
      })
    }
    return contributions
  }

  // 기본 매칭 점수
  const kwCount = target.matched_keywords?.length ?? 0
  if (kwCount > 0) {
    const pts = Math.min(kwCount * 10, 40)
    contributions.push({
      label: '키워드 매칭',
      points: pts,
      note: `${kwCount}개 키워드 매칭 (×10점, 최대 40)`,
    })
  }

  // 참여 신호
  const engagement = (target.like_count ?? 0) + (target.comment_count ?? 0) * 2
  if (engagement > 0) {
    const pts = Math.min(Math.round(engagement / 5), 30)
    contributions.push({
      label: '참여 신호',
      points: pts,
      note: `좋아요 ${target.like_count ?? 0} + 댓글 ${target.comment_count ?? 0} × 2`,
    })
  }

  // 신선도
  if (target.discovered_at) {
    const age = Date.now() - new Date(target.discovered_at).getTime()
    const ageHours = age / 3600_000
    let pts = 0
    let note = ''
    if (ageHours < 24) {
      pts = 25
      note = '24시간 이내 (+25)'
    } else if (ageHours < 72) {
      pts = 15
      note = '3일 이내 (+15)'
    } else if (ageHours < 168) {
      pts = 5
      note = '1주일 이내 (+5)'
    } else {
      pts = 0
      note = '1주일 초과 (신선도 가산 없음)'
    }
    if (pts > 0 || ageHours >= 168) {
      contributions.push({ label: '신선도', points: pts, note })
    }
  }

  // 댓글 가능성 보너스
  if (target.is_commentable) {
    contributions.push({
      label: '댓글 가능',
      points: 15,
      note: 'Selenium 검증 완료',
    })
  }

  return contributions
}

export default function PriorityScoreExplain({ target }: PriorityScoreExplainProps) {
  const score = target.priority_score ?? 0
  const contributions = computeContributions(target)
  const hasBackendBreakdown = Object.keys(parseScoreBreakdown(target)).length > 0
  const estimatedSum = contributions.reduce((a, c) => a + c.points, 0)
  const unexplained = hasBackendBreakdown ? 0 : Math.max(0, score - estimatedSum)

  const content = (
    <div className="max-w-sm">
      <div className="caps text-primary mb-1">Priority Score</div>
      <div className="font-display text-2xl tabular-nums leading-none mb-2">
        {score}
      </div>
      <div className="text-[11px] text-muted-foreground mb-2">
        {hasBackendBreakdown ? '백엔드 score_breakdown 기준 핵심 신호' : '추정 기여도 (백엔드 원점수와 다를 수 있음)'}
      </div>
      <dl className="space-y-1">
        {contributions.map((c) => (
          <div key={c.label} className="flex items-baseline justify-between gap-2 text-xs">
            <div>
              <dt className="font-medium inline">{c.label}</dt>
              <span className="text-muted-foreground ml-1">· {c.note}</span>
            </div>
            <dd className="tabular-nums text-primary shrink-0">{c.prefix ?? '+'}{c.points}</dd>
          </div>
        ))}
        {unexplained > 0 && (
          <div className="flex items-baseline justify-between gap-2 text-xs pt-1 border-t border-border/50 mt-1">
            <dt className="text-muted-foreground">기타 가산 (도메인 가중치 등)</dt>
            <dd className="tabular-nums text-muted-foreground">+{unexplained}</dd>
          </div>
        )}
      </dl>
    </div>
  )

  return (
    <Tooltip content={content} position="top">
      <span className="inline-flex items-center gap-1 text-muted-foreground cursor-help">
        <HelpCircle className="w-3 h-3" aria-hidden />
        <span className="text-[10px] caps">점수 설명</span>
      </span>
    </Tooltip>
  )
}

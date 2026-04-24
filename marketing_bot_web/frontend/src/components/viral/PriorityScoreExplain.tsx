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
}

/**
 * [BB3] Priority Score 설명 가능성
 *
 * priority_score가 왜 이 값인지를 사용 가능한 필드로 해석해 보여줌.
 * 백엔드가 breakdown을 제공하지 않아도 프론트에서 heuristic으로 근사.
 */
function computeContributions(target: ViralTargetData): Contribution[] {
  const contributions: Contribution[] = []

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
  const estimatedSum = contributions.reduce((a, c) => a + c.points, 0)
  const unexplained = Math.max(0, score - estimatedSum)

  const content = (
    <div className="max-w-sm">
      <div className="caps text-primary mb-1">Priority Score</div>
      <div className="font-display text-2xl tabular-nums leading-none mb-2">
        {score}
      </div>
      <div className="text-[11px] text-muted-foreground mb-2">
        추정 기여도 (백엔드 원점수와 다를 수 있음)
      </div>
      <dl className="space-y-1">
        {contributions.map((c) => (
          <div key={c.label} className="flex items-baseline justify-between gap-2 text-xs">
            <div>
              <dt className="font-medium inline">{c.label}</dt>
              <span className="text-muted-foreground ml-1">· {c.note}</span>
            </div>
            <dd className="tabular-nums text-primary shrink-0">+{c.points}</dd>
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

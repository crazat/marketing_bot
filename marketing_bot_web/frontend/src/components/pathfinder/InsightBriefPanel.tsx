import { AlertTriangle, Bot, CheckCircle, ClipboardList, FileText, Film, RefreshCw, ShieldAlert, Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'
import Button from '@/components/ui/Button'
import { copyTextToClipboard } from '@/utils/clipboard'

interface InsightBriefPanelProps {
  brief?: any
  isLoading?: boolean
  isError?: boolean
  onRefresh?: () => void
  onRequestCodex?: () => void
  onFeedback?: (feedbackType: 'accepted' | 'needs_review') => void
  onCopy?: (message: string) => void
}

const AGENT_LABELS: Record<string, { label: string; icon: ReactNode }> = {
  blog_agent: { label: 'Blog Agent', icon: <FileText size={16} /> },
  shorts_studio_agent: { label: 'Shorts Studio', icon: <Film size={16} /> },
  viral_hunter_agent: { label: 'Viral Hunter', icon: <Bot size={16} /> },
  ad_agent: { label: 'Ad Agent', icon: <Sparkles size={16} /> },
}

export default function InsightBriefPanel({
  brief,
  isLoading,
  isError,
  onRefresh,
  onRequestCodex,
  onFeedback,
  onCopy,
}: InsightBriefPanelProps) {
  const summary = brief?.summary
  const codex = brief?.codex_synthesis
  const qualityGate = brief?.quality_gate
  const feedbackSummary = brief?.feedback_summary
  const decisionOverview = brief?.decision_overview
  const topInsights: string[] = brief?.top_insights || []
  const actions: any[] = brief?.action_queue || []
  const packets = brief?.agent_handoffs?.packets || {}
  const primaryAction = actions[0]

  const handleCopyHandoff = async () => {
    try {
      await copyTextToClipboard(JSON.stringify(brief?.agent_handoffs || {}, null, 2))
      onCopy?.('에이전트 handoff JSON을 복사했습니다')
    } catch {
      onCopy?.('복사에 실패했습니다')
    }
  }

  if (isLoading) {
    return (
      <div className="bg-card rounded-lg border border-border p-5">
        <div className="h-5 w-48 bg-muted rounded mb-4 animate-pulse" />
        <div className="grid gap-3 md:grid-cols-3">
          {[0, 1, 2].map((item) => (
            <div key={item} className="h-24 bg-muted/70 rounded animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="bg-card rounded-lg border border-border p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold">Insight Brief</h3>
            <p className="text-sm text-muted-foreground mt-1">Pathfinder 브리프를 불러오지 못했습니다.</p>
          </div>
          <Button variant="outline" size="sm" onClick={onRefresh} icon={<RefreshCw size={14} />}>
            새로고침
          </Button>
        </div>
      </div>
    )
  }

  if (!brief || !summary?.agent_ready) {
    return (
      <div className="bg-card rounded-lg border border-border p-5">
        <div className="flex items-start gap-3">
          <ClipboardList className="w-5 h-5 text-muted-foreground mt-0.5" />
          <div>
            <h3 className="text-lg font-semibold">Insight Brief</h3>
            <p className="text-sm text-muted-foreground mt-1">
              최신 Legion 결과가 있으면 사용자 브리프와 에이전트 handoff가 여기에 표시됩니다.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-card rounded-lg border border-border p-5 space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-primary mb-2">
            <Sparkles size={18} />
            <h3 className="text-lg font-semibold">Insight Brief</h3>
          </div>
          <p className="font-medium">{summary.headline}</p>
          <p className="text-sm text-muted-foreground mt-1">{summary.next_best_action}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={onRefresh} icon={<RefreshCw size={14} />}>
            갱신
          </Button>
          <Button variant="outline" size="sm" onClick={onRequestCodex} icon={<Sparkles size={14} />}>
            Codex 해석
          </Button>
          <Button variant="secondary" size="sm" onClick={handleCopyHandoff} icon={<ClipboardList size={14} />}>
            Handoff 복사
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onFeedback?.('accepted')}
            disabled={!primaryAction?.handoff_id}
            icon={<CheckCircle size={14} />}
          >
            승인
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onFeedback?.('needs_review')}
            disabled={!primaryAction?.handoff_id}
            icon={<AlertTriangle size={14} />}
          >
            검토 필요
          </Button>
        </div>
      </div>

      {codex && (
        <div className="rounded-lg border border-primary/25 bg-primary/5 p-4">
          <div className="flex items-center justify-between gap-3 mb-2">
            <p className="text-sm font-semibold flex items-center gap-2">
              <Sparkles size={15} />
              Codex Synthesis
            </p>
            <span className="text-xs px-2 py-1 rounded bg-background/70 text-muted-foreground">
              {codex.status || 'fallback'}
            </span>
          </div>
          <p className="text-sm">{codex.executive_summary}</p>
          {codex.decision && (
            <p className="text-xs text-muted-foreground mt-2">우선 결정: {codex.decision}</p>
          )}
          {Array.isArray(codex.watchouts) && codex.watchouts.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1">
              {codex.watchouts.slice(0, 4).map((item: string, idx: number) => (
                <span key={idx} className="text-xs px-2 py-1 rounded bg-danger/10 text-danger">
                  {item}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="rounded-lg border border-border bg-background/40 p-4 lg:col-span-2">
          <p className="text-sm font-semibold mb-3">핵심 판단</p>
          <ul className="space-y-2 text-sm text-muted-foreground">
            {topInsights.slice(0, 5).map((insight, idx) => (
              <li key={idx} className="flex gap-2">
                <span className="text-primary">{idx + 1}.</span>
                <span>{insight}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-lg border border-border bg-background/40 p-4">
          <p className="text-sm font-semibold mb-3">검토 신호</p>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">고가치 롱테일</span>
              <span>{brief.metrics?.high_value_longtail_count || 0}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">방문 편의 의도</span>
              <span>{brief.metrics?.access_intent_count || 0}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">비용/보험 의도</span>
              <span>{brief.metrics?.payment_intent_count || 0}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground flex items-center gap-1"><ShieldAlert size={13} />가드레일</span>
              <span>{brief.metrics?.risk_count || 0}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">신뢰도</span>
              <span>{brief.metrics?.avg_confidence ?? '-'}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">검토 대기</span>
              <span>{brief.metrics?.human_review_required_count || 0}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">품질 게이트</span>
              <span>{qualityGate?.status || 'unknown'}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">바로 실행</span>
              <span>{decisionOverview?.publishable_count ?? 0}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">운영자 검토</span>
              <span>{decisionOverview?.operator_review_count ?? 0}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">피드백</span>
              <span>{feedbackSummary?.total_events || 0}</span>
            </div>
            {feedbackSummary?.learning_status && (
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">학습 상태</span>
                <span>{feedbackSummary.learning_status}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      <div>
        <p className="text-sm font-semibold mb-3">에이전트 실행 큐</p>
        <div className="grid gap-3 xl:grid-cols-2">
          {actions.slice(0, 4).map((action, idx) => (
            <div key={`${action.owner}-${action.keyword}-${idx}`} className="rounded-lg border border-border bg-background/40 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{action.keyword}</p>
                  <p className="text-xs text-muted-foreground mt-1">{action.angle}</p>
                  <p className="text-xs text-muted-foreground mt-2">
                    {action.handoff_id} · {action.confidence_band || 'unknown'} {action.confidence ?? ''}
                    {action.decision_packet?.state ? ` · ${action.decision_packet.state}` : ''}
                    {action.data_quality?.status ? ` · data ${action.data_quality.status}` : ''}
                    {action.human_review?.required ? ' · human review' : ''}
                    {action.feedback_snapshot?.learning_status && action.feedback_snapshot.learning_status !== 'unseen'
                      ? ` · ${action.feedback_snapshot.learning_status}`
                      : ''}
                  </p>
                  {action.measurement_plan?.primary_metric && (
                    <p className="text-xs text-muted-foreground mt-1">
                      측정: {action.measurement_plan.primary_metric}
                    </p>
                  )}
                </div>
                <span className="text-xs px-2 py-1 rounded bg-primary/10 text-primary whitespace-nowrap">
                  {action.owner}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {Object.entries(packets).map(([agent, packet]: [string, any]) => {
          const meta = AGENT_LABELS[agent] || { label: agent, icon: <Bot size={16} /> }
          return (
            <div key={agent} className="rounded-lg border border-border bg-background/40 p-4">
              <div className="flex items-center gap-2 mb-2 text-sm font-semibold">
                {meta.icon}
                <span>{meta.label}</span>
              </div>
              <p className="text-xs text-muted-foreground">{packet?.tasks?.length || 0}개 작업 준비됨</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

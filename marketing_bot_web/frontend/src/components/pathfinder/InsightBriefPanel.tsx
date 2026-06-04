import { AlertTriangle, Ban, Bot, CheckCircle, ClipboardList, FileText, Film, ListChecks, MapPin, RefreshCw, ShieldAlert, Sparkles, Target, TrendingDown, TrendingUp } from 'lucide-react'
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
  onTrackPlaceCandidates?: (keywords: string[]) => void
  isTrackingCandidates?: boolean
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
  onTrackPlaceCandidates,
  isTrackingCandidates,
  onCopy,
}: InsightBriefPanelProps) {
  const summary = brief?.summary
  const codex = brief?.codex_synthesis
  const qualityGate = brief?.quality_gate
  const feedbackSummary = brief?.feedback_summary
  const decisionOverview = brief?.decision_overview
  const placeTracking = brief?.place_tracking
  const placeRankLift = brief?.place_rank_lift
  const placeValueLoop = brief?.place_value_loop
  const topInsights: string[] = brief?.top_insights || []
  const actions: any[] = brief?.action_queue || []
  const packets = brief?.agent_handoffs?.packets || {}
  const primaryAction = actions[0]

  const topPlaceTrackingCandidateKeywords: string[] =
    placeRankLift?.tracking_expansion?.candidate_keywords
      ?.slice(0, 5)
      .map((item: any) => item.keyword)
      .filter(Boolean) || []

  const formatPlaceTrend = (trend?: string, delta?: number | null) => {
    if (trend === 'improved') return `상승 +${delta ?? 0}`
    if (trend === 'declined') return `하락 ${delta ?? 0}`
    if (trend === 'stable') return '유지'
    if (trend === 'new') return '신규 추적'
    if (trend === 'not_in_results' || trend === 'no_results' || trend === 'not_found') return '미노출'
    if (trend === 'error') return '오류'
    return trend || '미추적'
  }

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

      {placeTracking && (
        <div className="rounded-lg border border-border bg-background/40 p-4">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="text-sm font-semibold flex items-center gap-2">
                <MapPin size={15} />
                플레이스 추적 전달
              </p>
              <p className="text-sm text-muted-foreground mt-1">{placeTracking.headline}</p>
            </div>
            {placeTracking.latest_checked_at && (
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                최신 {placeTracking.latest_checked_at}
              </span>
            )}
          </div>
          <div className="grid gap-3 mt-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded border border-border bg-card/60 p-3">
              <p className="text-xs text-muted-foreground">연결된 카드</p>
              <p className="text-xl font-semibold mt-1">{placeTracking.tracked_count || 0}</p>
            </div>
            <div className="rounded border border-border bg-card/60 p-3">
              <p className="text-xs text-muted-foreground">노출 / Top3</p>
              <p className="text-xl font-semibold mt-1">
                {placeTracking.visible_count || 0} / {placeTracking.top3_count || 0}
              </p>
            </div>
            <div className="rounded border border-border bg-card/60 p-3">
              <p className="text-xs text-muted-foreground">하락</p>
              <p className="text-xl font-semibold mt-1 text-danger">{placeTracking.declining_count || 0}</p>
            </div>
            <div className="rounded border border-border bg-card/60 p-3">
              <p className="text-xs text-muted-foreground">경쟁사 선점</p>
              <p className="text-xl font-semibold mt-1 text-warn">{placeTracking.competitor_gap_count || 0}</p>
            </div>
          </div>
          {Array.isArray(placeTracking.cards) && placeTracking.cards.length > 0 && (
            <div className="mt-4 grid gap-2 lg:grid-cols-2">
              {placeTracking.cards.slice(0, 4).map((item: any) => (
                <div key={`${item.handoff_id}-${item.keyword}`} className="rounded border border-border bg-card/50 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{item.keyword}</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        {item.device_type || 'unknown'} · {formatPlaceTrend(item.trend, item.rank_delta)}
                        {item.best_competitor?.target_name
                          ? ` · 경쟁 ${item.best_competitor.target_name} ${item.best_competitor.rank}위`
                          : ''}
                      </p>
                    </div>
                    <span className="text-sm font-semibold whitespace-nowrap">
                      {item.status === 'found' && item.current_rank ? `${item.current_rank}위` : item.status || '-'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {placeRankLift && (
        <div className="rounded-lg border border-border bg-background/40 p-4">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="text-sm font-semibold flex items-center gap-2">
                <ListChecks size={15} />
                플레이스 순위 리프트 플랜
              </p>
              <p className="text-sm text-muted-foreground mt-1">{placeRankLift.headline}</p>
            </div>
            <span className="text-xs px-2 py-1 rounded bg-primary/10 text-primary whitespace-nowrap">
              액션 {placeRankLift.priority_action_count || placeRankLift.priority_actions?.length || 0}개
            </span>
          </div>

          <div className="grid gap-3 mt-4 sm:grid-cols-2 lg:grid-cols-5">
            <div className="rounded border border-border bg-card/60 p-3">
              <p className="text-xs text-muted-foreground">추적 소스</p>
              <p className="text-sm font-semibold mt-1 break-words">{placeRankLift.source || 'none'}</p>
            </div>
            <div className="rounded border border-border bg-card/60 p-3">
              <p className="text-xs text-muted-foreground">연결 키워드</p>
              <p className="text-xl font-semibold mt-1">{placeRankLift.tracked_count || 0}</p>
            </div>
            <div className="rounded border border-border bg-card/60 p-3">
              <p className="text-xs text-muted-foreground">재검토</p>
              <p className="text-sm font-semibold mt-1">
                {placeRankLift.measurement_contract?.review_after_days || 14}일
              </p>
            </div>
            <div className="rounded border border-border bg-card/60 p-3">
              <p className="text-xs text-muted-foreground">차단 수단</p>
              <p className="text-xl font-semibold mt-1 text-danger">
                {placeRankLift.prohibited_tactics?.length || 0}
              </p>
            </div>
            <div className="rounded border border-border bg-card/60 p-3">
              <p className="text-xs text-muted-foreground">공식 근거</p>
              <p className="text-xl font-semibold mt-1">{placeRankLift.source_refs?.length || 0}</p>
            </div>
          </div>

          {placeRankLift.tracking_expansion && (
            <div className="mt-4 rounded border border-border bg-card/50 p-3">
              <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                <div>
                  <p className="text-sm font-semibold">추적 키워드 확장</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {placeRankLift.tracking_expansion.next_step}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-primary whitespace-nowrap">
                    커버리지 {Math.round((placeRankLift.tracking_expansion.coverage_rate || 0) * 100)}%
                  </span>
                  {topPlaceTrackingCandidateKeywords.length > 0 && (
                    <Button
                      variant="outline"
                      size="xs"
                      onClick={() => onTrackPlaceCandidates?.(topPlaceTrackingCandidateKeywords)}
                      disabled={!onTrackPlaceCandidates || isTrackingCandidates}
                      icon={<Target size={13} />}
                    >
                      추적 시작
                    </Button>
                  )}
                </div>
              </div>
              <div className="grid gap-2 mt-3 sm:grid-cols-3">
                <div className="rounded bg-background/70 px-3 py-2">
                  <p className="text-xs text-muted-foreground">미추적 카드</p>
                  <p className="text-sm font-semibold mt-1">{placeRankLift.tracking_expansion.uncovered_card_count || 0}</p>
                </div>
                <div className="rounded bg-background/70 px-3 py-2">
                  <p className="text-xs text-muted-foreground">후보</p>
                  <p className="text-sm font-semibold mt-1">{placeRankLift.tracking_expansion.candidate_count || 0}</p>
                </div>
                <div className="rounded bg-background/70 px-3 py-2">
                  <p className="text-xs text-muted-foreground">기존 추적</p>
                  <p className="text-sm font-semibold mt-1">{placeRankLift.tracking_expansion.tracked_keyword_count || 0}</p>
                </div>
              </div>
              {Array.isArray(placeRankLift.tracking_expansion.candidate_keywords) && placeRankLift.tracking_expansion.candidate_keywords.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {placeRankLift.tracking_expansion.candidate_keywords.slice(0, 6).map((item: any) => (
                    <span key={item.candidate_id || item.keyword} className="text-xs px-2 py-1 rounded bg-primary/10 text-primary">
                      {item.keyword}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {placeRankLift.diagnostic_scores && (
            <div className="mt-4 rounded border border-border bg-card/50 p-3">
              <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                <div>
                  <p className="text-sm font-semibold">진단 점수</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {placeRankLift.diagnostic_scores.interpretation}
                  </p>
                </div>
                <span className="text-sm font-semibold text-primary whitespace-nowrap">
                  종합 {placeRankLift.diagnostic_scores.overall_score ?? 0}
                </span>
              </div>
              <div className="grid gap-2 mt-3 sm:grid-cols-2 lg:grid-cols-5">
                {[
                  ['노출', placeRankLift.diagnostic_scores.visibility_score],
                  ['순위품질', placeRankLift.diagnostic_scores.rank_quality_score],
                  ['변동안정', placeRankLift.diagnostic_scores.volatility_score],
                  ['경쟁압력', placeRankLift.diagnostic_scores.competitor_pressure_score],
                  ['실행준비', placeRankLift.diagnostic_scores.execution_readiness_score],
                ].map(([label, score]) => (
                  <div key={String(label)} className="rounded bg-background/70 px-3 py-2">
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="text-sm font-semibold mt-1">{score ?? 0}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {Array.isArray(placeRankLift.profile_audit_checklist) && placeRankLift.profile_audit_checklist.length > 0 && (
            <div className="mt-4 rounded border border-border bg-card/50 p-3">
              <p className="text-sm font-semibold">스마트플레이스 프로필 감사</p>
              <div className="mt-3 grid gap-2 lg:grid-cols-2">
                {placeRankLift.profile_audit_checklist.slice(0, 4).map((item: any) => (
                  <div key={`${item.field}-${item.rank_signal}`} className="rounded bg-background/70 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium">{item.field}</p>
                        <p className="text-xs text-muted-foreground mt-1">{item.why}</p>
                      </div>
                      <span className="text-xs px-2 py-1 rounded bg-primary/10 text-primary whitespace-nowrap">
                        {item.status || item.priority}
                      </span>
                    </div>
                    {Array.isArray(item.checks) && item.checks.length > 0 && (
                      <p className="text-xs text-muted-foreground mt-2">{item.checks[0]}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {Array.isArray(placeRankLift.priority_actions) && placeRankLift.priority_actions.length > 0 && (
            <div className="mt-4 grid gap-3 xl:grid-cols-2">
              {placeRankLift.priority_actions.slice(0, 4).map((item: any) => (
                <div key={item.action_id || `${item.lever}-${item.keyword}`} className="rounded border border-border bg-card/50 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold">{item.title}</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        {item.keyword || '공통 운영'} · {item.lever} · {item.cadence || 'weekly'}
                      </p>
                    </div>
                    <span className="text-xs px-2 py-1 rounded bg-primary/10 text-primary whitespace-nowrap">
                      {item.priority || 'medium'}
                    </span>
                  </div>
                  {item.why && <p className="text-sm text-muted-foreground mt-3">{item.why}</p>}
                  {Array.isArray(item.tasks) && item.tasks.length > 0 && (
                    <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
                      {item.tasks.slice(0, 3).map((task: string, idx: number) => (
                        <li key={idx} className="flex gap-2">
                          <span className="text-primary">{idx + 1}.</span>
                          <span>{task}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {item.measurement && (
                    <p className="text-xs text-muted-foreground mt-3">
                      측정: {item.measurement}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}

          {Array.isArray(placeRankLift.experiment_queue) && placeRankLift.experiment_queue.length > 0 && (
            <div className="mt-4 rounded border border-border bg-card/50 p-3">
              <p className="text-sm font-semibold">14일 실험 큐</p>
              <div className="mt-3 grid gap-2 lg:grid-cols-2">
                {placeRankLift.experiment_queue.slice(0, 2).map((item: any) => (
                  <div key={item.experiment_id} className="rounded bg-background/70 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{item.keyword}</p>
                        <p className="text-xs text-muted-foreground mt-1">{item.intervention}</p>
                      </div>
                      <span className="text-xs px-2 py-1 rounded bg-primary/10 text-primary whitespace-nowrap">
                        {item.lever}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-3">{item.hypothesis}</p>
                    <p className="text-xs text-muted-foreground mt-2">성공: {item.success_metric}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {Array.isArray(placeRankLift.prohibited_tactics) && placeRankLift.prohibited_tactics.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1">
              {placeRankLift.prohibited_tactics.slice(0, 5).map((item: string, idx: number) => (
                <span key={idx} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-danger/10 text-danger">
                  <Ban size={12} />
                  {item}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {placeValueLoop && (
        <div className="rounded-lg border border-border bg-background/40 p-4">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="text-sm font-semibold flex items-center gap-2">
                <Sparkles size={15} />
                SmartPlace 부가가치 루프
              </p>
              <p className="text-sm text-muted-foreground mt-1">{placeValueLoop.headline}</p>
            </div>
            <span className="text-xs px-2 py-1 rounded bg-primary/10 text-primary whitespace-nowrap">
              준비도 {placeValueLoop.pathfinder_to_place?.ai_longtail_readiness?.score ?? 0}
            </span>
          </div>

          {Array.isArray(placeValueLoop.pathfinder_to_place?.representative_keyword_candidates) &&
            placeValueLoop.pathfinder_to_place.representative_keyword_candidates.length > 0 && (
              <div className="mt-4 rounded border border-border bg-card/50 p-3">
                <p className="text-sm font-semibold">대표키워드 후보</p>
                <p className="text-xs text-muted-foreground mt-1">
                  최대 5개까지 실제 서비스명 중심으로 검토하고 홍보성·주관적 표현은 제외합니다.
                </p>
                <div className="mt-3 flex flex-wrap gap-1">
                  {placeValueLoop.pathfinder_to_place.representative_keyword_candidates.slice(0, 5).map((item: any) => (
                    <span key={`${item.source}-${item.keyword}`} className="text-xs px-2 py-1 rounded bg-primary/10 text-primary">
                      {item.keyword}
                    </span>
                  ))}
                </div>
              </div>
            )}

          {Array.isArray(placeValueLoop.pathfinder_to_place?.smartplace_updates) &&
            placeValueLoop.pathfinder_to_place.smartplace_updates.length > 0 && (
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                {placeValueLoop.pathfinder_to_place.smartplace_updates.slice(0, 4).map((item: any) => (
                  <div key={item.field} className="rounded border border-border bg-card/50 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold">{item.field}</p>
                        <p className="text-xs text-muted-foreground mt-1">{item.action}</p>
                      </div>
                      <span className="text-xs px-2 py-1 rounded bg-primary/10 text-primary whitespace-nowrap">
                        {item.priority || 'medium'}
                      </span>
                    </div>
                    {Array.isArray(item.payload) && item.payload.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1">
                        {item.payload.slice(0, 5).map((payload: string, idx: number) => (
                          <span key={idx} className="text-xs px-2 py-1 rounded bg-background/80 text-muted-foreground">
                            {payload}
                          </span>
                        ))}
                      </div>
                    )}
                    {item.measurement && (
                      <p className="text-xs text-muted-foreground mt-3">측정: {item.measurement}</p>
                    )}
                  </div>
                ))}
              </div>
            )}

          {Array.isArray(placeValueLoop.place_to_pathfinder?.import_signals) &&
            placeValueLoop.place_to_pathfinder.import_signals.length > 0 && (
              <div className="mt-4 rounded border border-border bg-card/50 p-3">
                <p className="text-sm font-semibold">플레이스 → Pathfinder 역방향 신호</p>
                <div className="mt-3 grid gap-2 lg:grid-cols-2">
                  {placeValueLoop.place_to_pathfinder.import_signals.slice(0, 4).map((item: any) => (
                    <div key={item.source} className="rounded bg-background/70 p-3">
                      <p className="text-sm font-medium">{item.source}</p>
                      <p className="text-xs text-muted-foreground mt-1">{item.pathfinder_update}</p>
                      <p className="text-xs text-muted-foreground mt-2">{item.owner} · {item.cadence}</p>
                    </div>
                  ))}
                </div>
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
              <span className="text-muted-foreground">플레이스 연결</span>
              <span>{brief.metrics?.place_tracked_count || 0}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">플레이스 Top3</span>
              <span>{brief.metrics?.place_top3_count || 0}</span>
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
                  {action.place_rank?.tracked && (
                    <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                      {action.place_rank.trend === 'declined' ? (
                        <TrendingDown size={12} className="text-danger" />
                      ) : (
                        <TrendingUp size={12} className="text-ok" />
                      )}
                      플레이스 {action.place_rank.current?.rank ? `${action.place_rank.current.rank}위` : action.place_rank.current?.status}
                      {action.place_rank.current?.device_type ? ` · ${action.place_rank.current.device_type}` : ''}
                      {action.place_rank.competitor_gap > 0 ? ` · 경쟁사 +${action.place_rank.competitor_gap}` : ''}
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

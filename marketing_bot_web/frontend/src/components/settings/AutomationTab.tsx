/**
 * 자동화 설정 탭 컴포넌트
 * 리드 분류, 바이럴 추천, 경쟁사 모니터링 자동화 관리
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { automationApi } from '@/services/api'
import type {
  AutomationStatus,
  PriorityLead,
  CompetitorThreat,
  KeywordOpportunity,
} from '@/services/api/automation'
import Button, { IconButton } from '@/components/ui/Button'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/utils/errorMessages'
import {
  Bot,
  RefreshCw,
  Play,
  Users,
  Target,
  Shield,
  TrendingUp,
  Zap,
} from 'lucide-react'

export default function AutomationTab() {
  const queryClient = useQueryClient()
  const toast = useToast()

  // 자동화 상태 조회
  const { data: automationStatus, isLoading: automationLoading, refetch: refetchAutomation } = useQuery<AutomationStatus | null>({
    queryKey: ['automation-status'],
    queryFn: () => automationApi.getStatus().catch(() => null),
    retry: 1,
  })

  // 우선순위 리드 큐
  const { data: priorityQueue } = useQuery<{ queue: PriorityLead[]; total: number }>({
    queryKey: ['automation-priority-queue'],
    queryFn: () => automationApi.getPriorityQueue(10).catch(() => ({ queue: [], total: 0 })),
    retry: 1,
  })

  // 경쟁사 위협
  const { data: competitorThreats } = useQuery<{ threats: CompetitorThreat[]; total: number; critical_count: number }>({
    queryKey: ['automation-competitor-threats'],
    queryFn: () => automationApi.getCompetitorThreats().catch(() => ({ threats: [], total: 0, critical_count: 0 })),
    retry: 1,
  })

  // 키워드 기회
  const { data: keywordOpportunities } = useQuery<{ opportunities: KeywordOpportunity[]; total: number }>({
    queryKey: ['automation-keyword-opportunities'],
    queryFn: () => automationApi.getKeywordOpportunities().catch(() => ({ opportunities: [], total: 0 })),
    retry: 1,
  })

  // 일일 자동화 실행 mutation
  const runAutomationMutation = useMutation({
    mutationFn: () => automationApi.runDailyAutomation(),
    onSuccess: (data) => {
      toast.success(`자동화 완료: 리드 ${data.leads_processed}개 처리, Hot Lead ${data.hot_leads_found}개 발견`)
      queryClient.invalidateQueries({ queryKey: ['automation-status'] })
      queryClient.invalidateQueries({ queryKey: ['automation-priority-queue'] })
      queryClient.invalidateQueries({ queryKey: ['automation-competitor-threats'] })
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })

  // 리드 분류 실행 mutation
  const classifyLeadsMutation = useMutation({
    mutationFn: () => automationApi.classifyLeads(),
    onSuccess: (data) => {
      toast.success(`리드 ${data.total_processed}개 분류 완료, Hot Lead ${data.hot_leads.length}개 발견`)
      queryClient.invalidateQueries({ queryKey: ['automation-status'] })
      queryClient.invalidateQueries({ queryKey: ['automation-priority-queue'] })
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })

  return (
    <div className="space-y-6">
      {/* 자동화 상태 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Bot className="w-5 h-5 text-purple-500" />
            자동화 상태
          </h3>
          <p className="text-sm text-muted-foreground mt-1">
            리드 분류, 바이럴 추천, 경쟁사 모니터링을 자동으로 수행합니다.
          </p>
        </div>
        <div className="flex gap-2">
          <IconButton
            icon={<RefreshCw className="w-4 h-4" />}
            onClick={() => refetchAutomation()}
            size="sm"
            title="새로고침"
          />
          <Button
            variant="primary"
            onClick={() => runAutomationMutation.mutate()}
            loading={runAutomationMutation.isPending}
            icon={<Play className="w-4 h-4" />}
          >
            일일 자동화 실행
          </Button>
        </div>
      </div>

      {/* 자동화 모듈 상태 카드 */}
      {automationLoading ? (
        <div className="text-center py-8 text-muted-foreground">로딩 중...</div>
      ) : automationStatus ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* 리드 분류 */}
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              <Users className="w-5 h-5 text-blue-500" />
              <span className="font-medium">리드 분류</span>
              <span className={`ml-auto px-2 py-0.5 text-xs rounded-full ${
                automationStatus.lead_classification.enabled
                  ? 'bg-green-500/10 text-green-600'
                  : 'bg-gray-500/10 text-gray-600'
              }`}>
                {automationStatus.lead_classification.enabled ? '활성' : '비활성'}
              </span>
            </div>
            <div className="text-2xl font-bold">{automationStatus.lead_classification.pending_leads}</div>
            <div className="text-xs text-muted-foreground">대기중 리드</div>
            {automationStatus.lead_classification.last_run && (
              <div className="text-xs text-muted-foreground mt-2">
                마지막 실행: {new Date(automationStatus.lead_classification.last_run).toLocaleString('ko-KR')}
              </div>
            )}
            <Button
              variant="secondary"
              size="sm"
              onClick={() => classifyLeadsMutation.mutate()}
              loading={classifyLeadsMutation.isPending}
              icon={<Zap className="w-3 h-3" />}
              fullWidth
              className="mt-3"
            >
              지금 분류
            </Button>
          </div>

          {/* 바이럴 추천 */}
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              <Target className="w-5 h-5 text-green-500" />
              <span className="font-medium">바이럴 추천</span>
              <span className={`ml-auto px-2 py-0.5 text-xs rounded-full ${
                automationStatus.viral_recommendation.enabled
                  ? 'bg-green-500/10 text-green-600'
                  : 'bg-gray-500/10 text-gray-600'
              }`}>
                {automationStatus.viral_recommendation.enabled ? '활성' : '비활성'}
              </span>
            </div>
            <div className="text-2xl font-bold">{automationStatus.viral_recommendation.pending_targets}</div>
            <div className="text-xs text-muted-foreground">대기중 타겟</div>
          </div>

          {/* 경쟁사 모니터링 */}
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              <Shield className="w-5 h-5 text-orange-500" />
              <span className="font-medium">경쟁사 모니터링</span>
              <span className={`ml-auto px-2 py-0.5 text-xs rounded-full ${
                automationStatus.competitor_monitoring.enabled
                  ? 'bg-green-500/10 text-green-600'
                  : 'bg-gray-500/10 text-gray-600'
              }`}>
                {automationStatus.competitor_monitoring.enabled ? '활성' : '비활성'}
              </span>
            </div>
            <div className="text-2xl font-bold text-orange-600">
              {automationStatus.competitor_monitoring.active_threats}
            </div>
            <div className="text-xs text-muted-foreground">활성 위협</div>
          </div>

          {/* 일일 브리핑 */}
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              <TrendingUp className="w-5 h-5 text-purple-500" />
              <span className="font-medium">일일 브리핑</span>
              <span className={`ml-auto px-2 py-0.5 text-xs rounded-full ${
                automationStatus.daily_briefing.enabled
                  ? 'bg-green-500/10 text-green-600'
                  : 'bg-gray-500/10 text-gray-600'
              }`}>
                {automationStatus.daily_briefing.enabled ? '활성' : '비활성'}
              </span>
            </div>
            {automationStatus.daily_briefing.last_generated ? (
              <>
                <div className="text-sm font-medium">생성됨</div>
                <div className="text-xs text-muted-foreground">
                  {new Date(automationStatus.daily_briefing.last_generated).toLocaleString('ko-KR')}
                </div>
              </>
            ) : (
              <div className="text-sm text-muted-foreground">생성된 브리핑 없음</div>
            )}
          </div>
        </div>
      ) : (
        <div className="text-center py-8 text-red-500">자동화 상태를 불러올 수 없습니다.</div>
      )}

      {/* 우선순위 리드 큐 */}
      {priorityQueue && priorityQueue.queue.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-6">
          <h4 className="text-md font-semibold mb-4 flex items-center gap-2">
            <Users className="w-4 h-4 text-blue-500" />
            우선순위 리드 ({priorityQueue.total}개)
          </h4>
          <div className="space-y-2">
            {priorityQueue.queue.map((lead) => (
              <div key={lead.id} className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                <div className={`px-2 py-1 rounded text-xs font-bold ${
                  lead.score >= 80 ? 'bg-red-500/20 text-red-600' :
                  lead.score >= 60 ? 'bg-orange-500/20 text-orange-600' :
                  'bg-yellow-500/20 text-yellow-600'
                }`}>
                  {lead.score}점
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">{lead.title}</div>
                  <div className="text-xs text-muted-foreground">{lead.priority_reason}</div>
                </div>
                <div className="text-xs text-muted-foreground">
                  {lead.platform} · {lead.days_since_created}일 전
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 경쟁사 위협 */}
      {competitorThreats && competitorThreats.threats.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-6">
          <h4 className="text-md font-semibold mb-4 flex items-center gap-2">
            <Shield className="w-4 h-4 text-orange-500" />
            경쟁사 위협 ({competitorThreats.critical_count}개 심각)
          </h4>
          <div className="space-y-2">
            {competitorThreats.threats.map((threat, idx) => (
              <div key={idx} className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                <div className={`px-2 py-1 rounded text-xs font-bold ${
                  threat.threat_level === 'critical' ? 'bg-red-500/20 text-red-600' :
                  threat.threat_level === 'high' ? 'bg-orange-500/20 text-orange-600' :
                  threat.threat_level === 'medium' ? 'bg-yellow-500/20 text-yellow-600' :
                  'bg-gray-500/20 text-gray-600'
                }`}>
                  {threat.threat_level.toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium">{threat.competitor_name}</div>
                  <div className="text-xs text-muted-foreground">
                    키워드: {threat.keyword} (그들: {threat.their_rank}위 vs 우리: {threat.our_rank}위)
                  </div>
                </div>
                <div className="text-xs text-muted-foreground max-w-xs truncate">
                  {threat.suggested_response}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 키워드 기회 */}
      {keywordOpportunities && keywordOpportunities.opportunities.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-6">
          <h4 className="text-md font-semibold mb-4 flex items-center gap-2">
            <Target className="w-4 h-4 text-green-500" />
            키워드 기회 ({keywordOpportunities.total}개)
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {keywordOpportunities.opportunities.map((opp, idx) => (
              <div key={idx} className={`p-3 rounded-lg border ${
                opp.priority === 'high' ? 'bg-green-500/10 border-green-500/30' :
                opp.priority === 'medium' ? 'bg-blue-500/10 border-blue-500/30' :
                'bg-gray-500/10 border-gray-500/30'
              }`}>
                <div className="font-medium">{opp.keyword}</div>
                <div className="text-xs text-muted-foreground mt-1">
                  {opp.opportunity_type === 'rank_defense' ? '순위 방어' :
                   opp.opportunity_type === 'momentum' ? '상승 모멘텀' : '새 기회'}
                  {opp.current_rank && ` · 현재 ${opp.current_rank}위`}
                </div>
                <div className="text-xs mt-2">{opp.suggested_action}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * [Phase F-1] 자동 워크플로우 규칙 엔진
 * 조건 기반 자동 작업 트리거 및 알림 생성
 */

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { battleApi, viralApi, leadsApi, pathfinderApi } from '@/services/api'

// 워크플로우 규칙 타입
export interface WorkflowRule {
  id: string
  name: string
  description: string
  enabled: boolean
  trigger: WorkflowTrigger
  conditions: WorkflowCondition[]
  actions: WorkflowAction[]
}

export interface WorkflowTrigger {
  type: 'keyword_discovered' | 'rank_drop' | 'hot_lead' | 'lead_timeout' | 'competitor_activity' | 'viral_success'
  threshold?: number
}

export interface WorkflowCondition {
  field: string
  operator: 'eq' | 'gt' | 'lt' | 'gte' | 'lte' | 'contains' | 'not_contains'
  value: any
}

export interface WorkflowAction {
  type: 'navigate' | 'notification' | 'auto_add' | 'escalate'
  label: string
  target?: string
  params?: Record<string, any>
}

// 트리거된 워크플로우 결과
export interface TriggeredWorkflow {
  rule: WorkflowRule
  triggeredAt: Date
  data: any
  suggestedActions: {
    label: string
    action: () => void
    priority: 'critical' | 'high' | 'medium' | 'low'
  }[]
}

// 기본 워크플로우 규칙
const DEFAULT_RULES: WorkflowRule[] = [
  {
    id: 'rule-a-grade-keyword',
    name: 'A급 키워드 발굴 시 추적 제안',
    description: 'A급 이상 키워드가 발굴되면 순위 추적 시작을 제안합니다',
    enabled: true,
    trigger: { type: 'keyword_discovered' },
    conditions: [
      { field: 'grade', operator: 'eq', value: 'A' },
      { field: 'is_tracking', operator: 'eq', value: false },
    ],
    actions: [
      { type: 'notification', label: 'A급 키워드 발굴!' },
      { type: 'navigate', label: '추적 시작', target: '/battle?tab=keywords' },
    ],
  },
  {
    id: 'rule-s-grade-keyword',
    name: 'S급 키워드 발굴 시 즉시 알림',
    description: 'S급 키워드가 발굴되면 즉시 알림을 보냅니다',
    enabled: true,
    trigger: { type: 'keyword_discovered' },
    conditions: [
      { field: 'grade', operator: 'eq', value: 'S' },
    ],
    actions: [
      { type: 'notification', label: 'S급 키워드 발굴!' },
      { type: 'navigate', label: '상세 보기', target: '/pathfinder' },
    ],
  },
  {
    id: 'rule-rank-drop-critical',
    name: '순위 급락 경보',
    description: '순위가 5위 이상 하락하면 긴급 경보를 발생시킵니다',
    enabled: true,
    trigger: { type: 'rank_drop', threshold: 5 },
    conditions: [],
    actions: [
      { type: 'escalate', label: '긴급 대응 필요' },
      { type: 'navigate', label: '대응하기', target: '/battle?tab=alerts' },
    ],
  },
  {
    id: 'rule-hot-lead-urgent',
    name: 'Hot 리드 48시간 미응답 에스컬레이션',
    description: 'Hot 리드가 48시간 이상 미응답이면 에스컬레이션합니다',
    enabled: true,
    trigger: { type: 'lead_timeout', threshold: 48 },
    conditions: [
      { field: 'grade', operator: 'eq', value: 'hot' },
      { field: 'status', operator: 'eq', value: 'new' },
    ],
    actions: [
      { type: 'escalate', label: 'Hot 리드 긴급!' },
      { type: 'navigate', label: '지금 응답', target: '/leads?grade=hot&status=new' },
    ],
  },
  {
    id: 'rule-hot-lead-new',
    name: 'Hot 리드 발생 알림',
    description: '새로운 Hot 리드가 발생하면 알림을 보냅니다',
    enabled: true,
    trigger: { type: 'hot_lead' },
    conditions: [
      { field: 'grade', operator: 'eq', value: 'hot' },
      { field: 'status', operator: 'eq', value: 'new' },
    ],
    actions: [
      { type: 'notification', label: 'Hot 리드 발생!' },
      { type: 'navigate', label: '확인하기', target: '/leads?grade=hot' },
    ],
  },
  {
    id: 'rule-pending-viral',
    name: '미처리 바이럴 누적 알림',
    description: '미처리 바이럴이 20건 이상 쌓이면 알림을 보냅니다',
    enabled: true,
    trigger: { type: 'viral_success', threshold: 20 },
    conditions: [
      { field: 'pending_count', operator: 'gte', value: 20 },
    ],
    actions: [
      { type: 'notification', label: '바이럴 처리 필요' },
      { type: 'navigate', label: '처리하기', target: '/viral?status=pending' },
    ],
  },
]

export function useWorkflowRules() {
  // 순위 하락 데이터 (에러 시 빈 객체로 폴백)
  const { data: rankAlerts, isError: rankAlertsError } = useQuery({
    queryKey: ['workflow-rank-alerts'],
    queryFn: () => battleApi.getRankDropAlerts(3, true).catch(() => ({ alerts: [], critical_count: 0 })),
    staleTime: 60000,
    refetchInterval: 60000,
    retry: 1,
  })

  // 리드 데이터
  const { data: leadsData, isError: leadsError } = useQuery({
    queryKey: ['workflow-leads'],
    queryFn: async () => {
      const [naver, youtube] = await Promise.all([
        leadsApi.getNaverLeads({ limit: 100 }).catch(() => []),
        leadsApi.getYoutubeLeads({ limit: 100 }).catch(() => []),
      ])
      return [...(naver || []), ...(youtube || [])]
    },
    staleTime: 60000,
    refetchInterval: 60000,
    retry: 1,
  })

  // 바이럴 데이터 (에러 시 빈 배열로 폴백)
  const { data: viralData, isError: viralError } = useQuery({
    queryKey: ['workflow-viral'],
    queryFn: () => viralApi.getTargets('pending', undefined, 100).catch(() => []),
    staleTime: 60000,
    refetchInterval: 120000,
    retry: 1,
  })

  // 키워드 인사이트 (최근 발굴)
  const { data: keywordData, isError: keywordsError } = useQuery({
    queryKey: ['workflow-keywords'],
    queryFn: async () => {
      try {
        const data = await pathfinderApi.getKeywords({ limit: 50 })
        return data?.keywords || []
      } catch {
        return []
      }
    },
    staleTime: 60000,
    refetchInterval: 120000,
    retry: 1,
  })

  // 순위 추적 키워드 (에러 시 빈 배열로 폴백)
  const { data: trackingKeywords, isError: trackingError } = useQuery({
    queryKey: ['workflow-tracking'],
    queryFn: () => battleApi.getRankingKeywords().catch(() => []),
    staleTime: 60000,
    retry: 1,
  })

  // 에러 상태 (디버깅용)
  const hasErrors = rankAlertsError || leadsError || viralError || keywordsError || trackingError

  // 워크플로우 규칙 평가
  const triggeredWorkflows = useMemo(() => {
    const triggered: TriggeredWorkflow[] = []
    const trackingSet = new Set((trackingKeywords || []).map((k: any) => k.keyword))

    DEFAULT_RULES.forEach((rule) => {
      if (!rule.enabled) return

      switch (rule.trigger.type) {
        case 'keyword_discovered': {
          // A급/S급 키워드 중 순위 추적 미등록 건
          const matchingKeywords = (keywordData || []).filter((kw: any) => {
            const gradeMatch = rule.conditions.find(c => c.field === 'grade')
            const trackingMatch = rule.conditions.find(c => c.field === 'is_tracking')

            if (gradeMatch && kw.grade !== gradeMatch.value) return false
            if (trackingMatch && trackingMatch.value === false && trackingSet.has(kw.keyword)) return false

            return true
          })

          if (matchingKeywords.length > 0) {
            triggered.push({
              rule,
              triggeredAt: new Date(),
              data: { keywords: matchingKeywords, count: matchingKeywords.length },
              suggestedActions: [
                {
                  label: `${rule.conditions.find(c => c.field === 'grade')?.value || ''}급 키워드 ${matchingKeywords.length}건 추적 시작`,
                  action: () => window.location.href = '/battle?tab=keywords',
                  priority: rule.id.includes('s-grade') ? 'critical' : 'high',
                },
              ],
            })
          }
          break
        }

        case 'rank_drop': {
          const threshold = rule.trigger.threshold || 5
          const criticalDrops = (rankAlerts?.alerts || []).filter(
            (a: any) => a.rank_drop >= threshold
          )

          if (criticalDrops.length > 0) {
            triggered.push({
              rule,
              triggeredAt: new Date(),
              data: { alerts: criticalDrops, count: criticalDrops.length },
              suggestedActions: criticalDrops.map((alert: any) => ({
                label: `"${alert.keyword}" ${alert.rank_drop}위 하락 대응`,
                action: () => window.location.href = `/battle?keyword=${encodeURIComponent(alert.keyword)}&tab=trends`,
                priority: 'critical' as const,
              })),
            })
          }
          break
        }

        case 'hot_lead': {
          const hotLeads = (leadsData || []).filter((l: any) =>
            l.grade === 'hot' && l.status === 'new'
          )

          if (hotLeads.length > 0) {
            triggered.push({
              rule,
              triggeredAt: new Date(),
              data: { leads: hotLeads, count: hotLeads.length },
              suggestedActions: [
                {
                  label: `Hot 리드 ${hotLeads.length}건 응답`,
                  action: () => window.location.href = '/leads?grade=hot&status=new',
                  priority: 'high',
                },
              ],
            })
          }
          break
        }

        case 'lead_timeout': {
          const threshold = rule.trigger.threshold || 48
          const urgentLeads = (leadsData || []).filter((l: any) => {
            if (l.grade !== 'hot' || l.status !== 'new') return false
            const created = new Date(l.collected_at || l.created_at)
            const hoursSince = (Date.now() - created.getTime()) / (1000 * 60 * 60)
            return hoursSince >= threshold
          })

          if (urgentLeads.length > 0) {
            triggered.push({
              rule,
              triggeredAt: new Date(),
              data: { leads: urgentLeads, count: urgentLeads.length },
              suggestedActions: [
                {
                  label: `긴급! ${urgentLeads.length}건 ${threshold}시간 초과`,
                  action: () => window.location.href = '/leads?grade=hot&status=new',
                  priority: 'critical',
                },
              ],
            })
          }
          break
        }

        case 'viral_success': {
          const threshold = rule.trigger.threshold || 20
          const pendingCount = viralData?.targets?.length || 0

          if (pendingCount >= threshold) {
            triggered.push({
              rule,
              triggeredAt: new Date(),
              data: { pendingCount },
              suggestedActions: [
                {
                  label: `미처리 바이럴 ${pendingCount}건 처리`,
                  action: () => window.location.href = '/viral?status=pending',
                  priority: 'medium',
                },
              ],
            })
          }
          break
        }
      }
    })

    // 우선순위순 정렬
    const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 }
    return triggered.sort((a, b) => {
      const aPriority = a.suggestedActions[0]?.priority || 'low'
      const bPriority = b.suggestedActions[0]?.priority || 'low'
      return priorityOrder[aPriority] - priorityOrder[bPriority]
    })
  }, [rankAlerts, leadsData, viralData, keywordData, trackingKeywords])

  // 통계 요약
  const summary = useMemo(() => ({
    total: triggeredWorkflows.length,
    critical: triggeredWorkflows.filter(w =>
      w.suggestedActions.some(a => a.priority === 'critical')
    ).length,
    high: triggeredWorkflows.filter(w =>
      w.suggestedActions.some(a => a.priority === 'high')
    ).length,
  }), [triggeredWorkflows])

  return {
    rules: DEFAULT_RULES,
    triggeredWorkflows,
    summary,
    hasErrors,
  }
}

export default useWorkflowRules

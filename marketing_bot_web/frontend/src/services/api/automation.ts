/**
 * Automation API - 자동화 확장 (Phase C)
 */
import { api } from './base'

// 타입 정의
export interface LeadClassificationResult {
  total_processed: number
  hot_leads: Array<{
    id: number
    title: string
    platform: string
    score: number
    reason: string
  }>
  warm_leads: Array<{
    id: number
    title: string
    platform: string
    score: number
  }>
  notifications_created: number
}

export interface PriorityLead {
  id: number
  title: string
  platform: string
  score: number
  priority_reason: string
  days_since_created: number
  matched_keyword?: string
}

export interface RecommendedTarget {
  id: number
  title: string
  platform: string
  url: string
  reason: string
  priority_score: number
  matched_keyword?: string
}

export interface KeywordOpportunity {
  keyword: string
  opportunity_type: 'rank_defense' | 'momentum' | 'new_opportunity'
  current_rank?: number
  suggested_action: string
  priority: 'high' | 'medium' | 'low'
}

export interface CompetitorThreat {
  competitor_name: string
  keyword: string
  their_rank: number
  our_rank: number
  rank_change: number
  threat_level: 'critical' | 'high' | 'medium' | 'low'
  suggested_response: string
}

export interface DailyBriefing {
  date: string
  rank_summary: {
    improved: number
    declined: number
    stable: number
  }
  lead_summary: {
    new_leads: number
    hot_leads: number
    pending_followup: number
  }
  competitor_summary: {
    threats_detected: number
    critical_count: number
  }
  recommended_actions: Array<{
    action: string
    priority: string
    reason: string
  }>
}

export interface AutomationStatus {
  lead_classification: {
    enabled: boolean
    last_run: string | null
    pending_leads: number
  }
  viral_recommendation: {
    enabled: boolean
    pending_targets: number
  }
  competitor_monitoring: {
    enabled: boolean
    active_threats: number
  }
  daily_briefing: {
    enabled: boolean
    last_generated: string | null
  }
}

export interface DailyAutomationResult {
  leads_processed: number
  hot_leads_found: number
  threats_detected: number
  briefing_generated: boolean
  errors: string[]
}

export const automationApi = {
  // 리드 자동 분류 실행
  classifyLeads: async (): Promise<LeadClassificationResult> => {
    const response = await api.post('/automation/leads/classify')
    return response.data?.data || response.data
  },

  // 우선순위 리드 큐 조회
  getPriorityQueue: async (limit: number = 20): Promise<{
    queue: PriorityLead[]
    total: number
  }> => {
    const response = await api.get('/automation/leads/priority-queue', {
      params: { limit }
    })
    return response.data?.data || response.data
  },

  // 추천 바이럴 타겟 조회
  getRecommendedTargets: async (limit: number = 10): Promise<{
    targets: RecommendedTarget[]
    total: number
  }> => {
    const response = await api.get('/automation/viral/recommended-targets', {
      params: { limit }
    })
    return response.data?.data || response.data
  },

  // 키워드 기회 분석
  getKeywordOpportunities: async (): Promise<{
    opportunities: KeywordOpportunity[]
    total: number
  }> => {
    const response = await api.get('/automation/viral/keyword-opportunities')
    return response.data?.data || response.data
  },

  // 경쟁사 위협 분석
  getCompetitorThreats: async (): Promise<{
    threats: CompetitorThreat[]
    total: number
    critical_count: number
  }> => {
    const response = await api.get('/automation/competitors/threats')
    return response.data?.data || response.data
  },

  // 일일 브리핑 생성
  generateBriefing: async (): Promise<DailyBriefing> => {
    const response = await api.post('/automation/briefing/generate')
    return response.data?.data || response.data
  },

  // 최신 브리핑 조회
  getLatestBriefing: async (): Promise<DailyBriefing | { message: string }> => {
    const response = await api.get('/automation/briefing/latest')
    return response.data?.data || response.data
  },

  // 일일 자동화 전체 실행
  runDailyAutomation: async (): Promise<DailyAutomationResult> => {
    const response = await api.post('/automation/run-daily')
    return response.data?.data || response.data
  },

  // 자동화 상태 조회
  getStatus: async (): Promise<AutomationStatus> => {
    const response = await api.get('/automation/status')
    return response.data?.data || response.data
  },
}

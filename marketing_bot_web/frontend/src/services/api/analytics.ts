/**
 * Analytics & Marketing APIs - 분석 및 마케팅 강화
 */

import { api } from './base'

// ============================================
// Analytics API
// ============================================
export const analyticsApi = {
  // 전환 어트리뷰션 체인
  getAttributionChain: async (days = 30) => {
    const response = await api.get('/analytics/attribution-chain', { params: { days } })
    return response.data
  },

  // 리드 응답 골든타임
  getResponseGoldenTime: async (days = 90) => {
    const response = await api.get('/analytics/response-golden-time', { params: { days } })
    return response.data
  },

  // 응답 시간 기록
  recordResponse: async (leadId: number, responseContent?: string) => {
    const response = await api.post('/analytics/record-response', {
      lead_id: leadId,
      response_content: responseContent,
    })
    return response.data
  },

  // 경쟁사 움직임 감지
  getCompetitorMovements: async (days = 7) => {
    const response = await api.get('/analytics/competitor-movements', { params: { days } })
    return response.data
  },

  // AI 주간 브리핑
  getWeeklyBriefing: async () => {
    const response = await api.get('/analytics/weekly-briefing')
    return response.data
  },

  // 키워드 라이프사이클
  getKeywordLifecycle: async (status?: string) => {
    const response = await api.get('/analytics/keyword-lifecycle', {
      params: status ? { status } : {},
    })
    return response.data
  },

  // 키워드 상태 변경
  updateKeywordStatus: async (keyword: string, newStatus: string, reason?: string) => {
    const response = await api.post('/analytics/keyword-lifecycle/update-status', {
      keyword,
      new_status: newStatus,
      reason,
    })
    return response.data
  },

  // 키워드 자동 상태 전환
  runAutoTransition: async () => {
    const response = await api.post('/analytics/keyword-lifecycle/auto-transition')
    return response.data
  },

  // 채널별 ROI
  getChannelROI: async (days = 30) => {
    const response = await api.get('/analytics/channel-roi', { params: { days } })
    return response.data
  },

  // 마케팅 건강 점수
  getMarketingHealthScore: async (days = 30) => {
    const response = await api.get('/analytics/marketing-health-score', { params: { days } })
    return response.data
  },

  // Before/After 비교
  getBeforeAfterComparison: async (params?: {
    before_start?: string
    before_end?: string
    after_start?: string
    after_end?: string
  }) => {
    const response = await api.get('/analytics/before-after-comparison', { params })
    return response.data
  },

  // 유입 경로 기록
  recordReferralSource: async (data: {
    conversion_id?: number
    lead_id?: number
    source: string
    source_detail?: string
  }) => {
    const response = await api.post('/analytics/record-referral-source', data)
    return response.data
  },

  // 유입 경로 통계
  getReferralSources: async (days = 90) => {
    const response = await api.get('/analytics/referral-sources', { params: { days } })
    return response.data
  },
}

// ============================================
// Marketing Enhancement API
// ============================================
export const marketingApi = {
  // 골든타임 분석
  getGoldenTimeStats: async (params?: { platform?: string; category?: string; days?: number }) => {
    const response = await api.get('/marketing/golden-time/stats', { params })
    return response.data
  },

  // 리드 품질 스코어링
  getLeadQualityStats: async (params?: { dimension?: string; days?: number }) => {
    const response = await api.get('/marketing/lead-quality/stats', { params })
    return response.data
  },

  // 콘텐츠 성과 분석
  getContentPerformanceStats: async (days = 30) => {
    const response = await api.get('/marketing/content-performance/stats', { params: { days } })
    return response.data
  },

  // 캠페인 관리
  getCampaigns: async (status?: string) => {
    const response = await api.get('/marketing/campaigns', { params: status ? { status } : {} })
    return response.data?.campaigns || []
  },

  createCampaign: async (data: {
    name: string
    description?: string
    start_date?: string
    end_date?: string
    target_categories?: string[]
    target_platforms?: string[]
    daily_target?: number
    total_target?: number
    budget?: number
    template_ids?: number[]
  }) => {
    const response = await api.post('/marketing/campaigns', data)
    return response.data
  },

  updateCampaignStatus: async (campaignId: number, status: string) => {
    const response = await api.put(`/marketing/campaigns/${campaignId}/status`, null, {
      params: { status }
    })
    return response.data
  },

  // 통합 ROI 대시보드
  getROIDashboard: async (days = 30) => {
    const response = await api.get('/marketing/roi/dashboard', { params: { days } })
    return response.data
  },

  // 스마트 알림 규칙
  getAlertRules: async () => {
    const response = await api.get('/marketing/alerts/rules')
    return response.data?.rules || []
  },

  createAlertRule: async (data: {
    name: string
    description?: string
    rule_type: string
    condition_json: string
    action_type?: string
    action_params?: string
    priority?: string
  }) => {
    const response = await api.post('/marketing/alerts/rules', data)
    return response.data
  },

  getAlertLogs: async (limit = 50) => {
    const response = await api.get('/marketing/alerts/logs', { params: { limit } })
    return response.data?.logs || []
  },

  updateAlertRule: async (id: number, data: { is_active?: boolean }) => {
    const response = await api.patch(`/marketing/alerts/rules/${id}`, data)
    return response.data
  },

  deleteAlertRule: async (id: number) => {
    const response = await api.delete(`/marketing/alerts/rules/${id}`)
    return response.data
  },

  // 경쟁사 바이럴 레이더
  getCompetitorRadarStats: async (days = 30) => {
    const response = await api.get('/marketing/competitor-radar/stats', { params: { days } })
    return response.data
  },

  // A/B 테스트
  getABTests: async () => {
    const response = await api.get('/marketing/ab-tests')
    return response.data?.experiments || []
  },

  createABTest: async (data: {
    name: string
    description?: string
    experiment_type?: string
    target_category?: string
    target_platform?: string
    sample_size_target?: number
    variants?: Array<{
      name: string
      description?: string
      content_template?: string
    }>
  }) => {
    const response = await api.post('/marketing/ab-tests', data)
    return response.data
  },

  updateABTestStatus: async (experimentId: number, status: string) => {
    const response = await api.put(`/marketing/ab-tests/${experimentId}/status`, null, {
      params: { status }
    })
    return response.data
  },
}

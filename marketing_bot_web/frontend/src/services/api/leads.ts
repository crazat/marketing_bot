/**
 * Leads API - 리드 관리 관련
 */

import { api, extractResponseData, LeadStats, ContactHistoryResponse, AddContactHistoryResponse, UpdateContactResponse } from './base'

export const leadsApi = {
  getStats: async (): Promise<LeadStats> => {
    const response = await api.get('/leads/stats')
    return extractResponseData<LeadStats>(response.data, { total: 0, by_platform: {}, by_status: {} })
  },

  getConversionRates: async () => {
    const response = await api.get('/leads/conversion-rates')
    return response.data
  },

  getLeads: async (params: {
    platform?: string
    status?: string
    category?: string
    limit?: number
    offset?: number
  }) => {
    const response = await api.get('/leads/list', { params })
    return response.data
  },

  getCarrotLeads: async (params: { status?: string; limit?: number }) => {
    const response = await api.get('/leads/carrot', { params })
    return response.data
  },

  getInfluencerLeads: async (params: { status?: string; limit?: number }) => {
    const response = await api.get('/leads/influencer', { params })
    return response.data
  },

  getYoutubeLeads: async (params: { status?: string; limit?: number }) => {
    const response = await api.get('/leads/youtube', { params })
    return response.data
  },

  getTiktokLeads: async (params: { status?: string; limit?: number }) => {
    const response = await api.get('/leads/tiktok', { params })
    return response.data
  },

  getNaverLeads: async (params: { status?: string; limit?: number }) => {
    const response = await api.get('/leads/naver', { params })
    return response.data
  },

  getInstagramLeads: async (params: { status?: string; limit?: number }) => {
    const response = await api.get('/leads/instagram', { params })
    return response.data
  },

  updateLead: async (lead_id: number, data: {
    status: string
    notes?: string
    follow_up_date?: string | null
    contact_info?: string
    expected_revenue?: number
    actual_revenue?: number
    source_keyword?: string
    source_content?: string
  }) => {
    const response = await api.patch(`/leads/${lead_id}`, data)
    return response.data
  },

  getCategories: async () => {
    const response = await api.get('/leads/categories')
    return response.data
  },

  getScoreDistribution: async () => {
    const response = await api.get('/leads/score-distribution')
    return response.data
  },

  getQualityStats: async () => {
    const response = await api.get('/leads/quality-stats')
    return response.data
  },

  getHotLeads: async (limit = 5) => {
    const response = await api.get('/leads/list', {
      params: { grade: 'hot', limit, offset: 0 },
    })
    return response.data
  },

  getConversionTracking: async () => {
    const response = await api.get('/leads/conversion-tracking')
    return response.data
  },

  getConversionTrends: async (days: number = 30) => {
    const response = await api.get('/leads/conversion-trends', { params: { days } })
    return response.data
  },

  getPendingAlerts: async () => {
    const response = await api.get('/leads/pending-alerts')
    return response.data
  },

  suggestResponse: async (platform: string, templateType = 'first_contact', leadId?: number) => {
    const response = await api.get('/leads/suggest-response', {
      params: { platform, template_type: templateType, lead_id: leadId }
    })
    return response.data
  },

  createResponseTemplate: async (data: {
    platform: string
    template_type?: string
    title: string
    content: string
  }) => {
    const response = await api.post('/leads/response-templates', data)
    return response.data
  },

  useResponseTemplate: async (templateId: number) => {
    const response = await api.post(`/leads/response-templates/${templateId}/use`)
    return response.data
  },

  getBottleneckAnalysis: async () => {
    const response = await api.get('/leads/bottleneck-analysis')
    return response.data
  },

  getRoiAnalysis: async () => {
    const response = await api.get('/leads/roi-analysis')
    return response.data
  },

  getGoalForecast: async (params: {
    goal_type?: string
    target_value?: number
    days_history?: number
  }) => {
    const response = await api.get('/leads/goal-forecast', { params })
    return response.data
  },

  getDuplicates: async () => {
    const response = await api.get('/leads/duplicates')
    return response.data?.data || response.data
  },

  mergeDuplicates: async (mergeIds: number[], keepId: number) => {
    const response = await api.post('/leads/merge-duplicates', {
      merge_ids: mergeIds,
      keep_id: keepId
    })
    return response.data
  },

  getContactHistory: async (leadId: number): Promise<ContactHistoryResponse> => {
    const response = await api.get<ContactHistoryResponse>(`/leads/${leadId}/contact-history`)
    return response.data
  },

  addContactHistory: async (data: {
    lead_id: number
    contact_type?: 'comment' | 'dm' | 'email' | 'call'
    content: string
    platform?: string
    template_id?: number
    notes?: string
  }): Promise<AddContactHistoryResponse> => {
    const response = await api.post<AddContactHistoryResponse>('/leads/contact-history', data)
    return response.data
  },

  updateContactResponse: async (historyId: number, response: string, status?: string): Promise<UpdateContactResponse> => {
    const res = await api.put<UpdateContactResponse>(`/leads/contact-history/${historyId}/response`, null, {
      params: { response, status: status || 'replied' }
    })
    return res.data
  },

  addConversion: async (data: {
    lead_id: number
    revenue: number
    keyword?: string
    platform?: string
    notes?: string
  }) => {
    const response = await api.post('/leads/conversions', data)
    return response.data
  },

  getLeadConversions: async (leadId: number) => {
    const response = await api.get(`/leads/${leadId}/conversions`)
    return response.data
  },

  getRoiDetail: async (params?: { days?: number }) => {
    const response = await api.get('/leads/roi-analysis', { params })
    return response.data
  },

  // Unified Contacts API
  getUnifiedContacts: async (params?: {
    search?: string
    platform?: string
    limit?: number
    offset?: number
  }) => {
    const response = await api.get('/leads/unified-contacts', { params })
    return response.data?.data || response.data
  },

  createUnifiedContact: async (data: {
    display_name: string
    primary_platform?: string
    email?: string
    phone?: string
    notes?: string
    tags?: string[]
  }) => {
    const response = await api.post('/leads/unified-contacts', data)
    return response.data
  },

  getUnifiedContactDetail: async (contactId: number) => {
    const response = await api.get(`/leads/unified-contacts/${contactId}`)
    return response.data?.data || response.data
  },

  updateUnifiedContact: async (contactId: number, data: {
    display_name?: string
    primary_platform?: string
    email?: string
    phone?: string
    notes?: string
    tags?: string[]
  }) => {
    const response = await api.put(`/leads/unified-contacts/${contactId}`, data)
    return response.data
  },

  linkLeadToUnifiedContact: async (contactId: number, mentionId: number) => {
    const response = await api.post(`/leads/unified-contacts/${contactId}/link`, {
      mention_id: mentionId
    })
    return response.data
  },

  unlinkLeadFromUnifiedContact: async (contactId: number, mentionId: number) => {
    const response = await api.post(`/leads/unified-contacts/${contactId}/unlink`, {
      mention_id: mentionId
    })
    return response.data
  },

  deleteUnifiedContact: async (contactId: number) => {
    const response = await api.delete(`/leads/unified-contacts/${contactId}`)
    return response.data
  },
}

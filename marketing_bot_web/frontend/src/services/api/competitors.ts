/**
 * Competitors API - 경쟁사 분석 관련
 */

import { api } from './base'

export const competitorsApi = {
  getList: async () => {
    const response = await api.get('/competitors/list')
    return response.data
  },

  addCompetitor: async (name: string, place_id?: string, category = '한의원', priority = 'Medium') => {
    const response = await api.post('/competitors/add', {
      name,
      place_id,
      category,
      priority,
    })
    return response.data
  },

  updateCompetitor: async (id: number, data: { name?: string; category?: string; priority?: string; keywords?: string[] }) => {
    const response = await api.put(`/competitors/${id}`, data)
    return response.data
  },

  deleteCompetitor: async (id: number) => {
    const response = await api.delete(`/competitors/${id}`)
    return response.data
  },

  getWeaknesses: async (days = 30) => {
    const response = await api.get('/competitors/weaknesses', { params: { days } })
    return response.data
  },

  getWeaknessSummary: async () => {
    const response = await api.get('/competitors/weaknesses/summary')
    return response.data
  },

  getOpportunityKeywords: async (status = 'pending') => {
    const response = await api.get('/competitors/opportunity-keywords', {
      params: { status },
    })
    return response.data
  },

  markOpportunityUsed: async (keyword: string) => {
    const response = await api.patch(`/competitors/opportunity-keywords/${keyword}/mark-used`)
    return response.data
  },

  analyzeReviews: async () => {
    const response = await api.post('/competitors/analyze-reviews', null, {
      timeout: 180000
    })
    return response.data
  },

  generateContentOutline: async (weaknessType?: string) => {
    const response = await api.post('/competitors/generate-content-outline', null, {
      params: weaknessType ? { weakness_type: weaknessType } : {}
    })
    return response.data
  },

  getContentGap: async () => {
    const response = await api.get('/competitors/content-gap')
    return response.data
  },

  getWeaknessRadar: async () => {
    const response = await api.get('/competitors/weakness-radar')
    return response.data
  },

  getMonitoringDashboard: async () => {
    const response = await api.get('/competitors/monitoring-dashboard')
    return response.data
  },
}

// Instagram API
export const instagramApi = {
  getStats: async (days = 30) => {
    const response = await api.get('/instagram/stats', { params: { days } })
    return response.data
  },

  getHashtagAnalysis: async (days = 30) => {
    const response = await api.get('/instagram/hashtag-analysis', { params: { days } })
    return response.data
  },

  getContentAnalysis: async (days = 30) => {
    const response = await api.get('/instagram/content-analysis', { params: { days } })
    return response.data
  },

  addAccount: async (username: string, category = '한의원') => {
    const response = await api.post('/instagram/accounts', { username, category })
    return response.data
  },

  getAccounts: async () => {
    const response = await api.get('/instagram/accounts')
    return response.data
  },

  getPosts: async (params?: { days?: number; account?: string; limit?: number }) => {
    const response = await api.get('/instagram/posts', { params })
    return response.data
  },

  analyzeContent: async (params?: { account?: string; analysis_type?: string }) => {
    const response = await api.post('/instagram/analysis', params || {})
    return response.data
  },

  getTokenStatus: async () => {
    const response = await api.get('/instagram/token-status')
    return response.data
  },
}

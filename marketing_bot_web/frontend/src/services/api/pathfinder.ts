/**
 * Pathfinder API - 키워드 발굴 관련
 */

import { api } from './base'

export const pathfinderApi = {
  getStats: async (applyFilter = true, days?: number) => {
    const response = await api.get('/pathfinder/stats', {
      params: { apply_filter: applyFilter, days },
    })
    return response.data
  },

  getKeywords: async (params: {
    grade?: string
    category?: string
    source?: string
    trend_status?: string
    /** [Q12] N일 이상 갱신 안 된 stale 키워드 숨김. 0=무제한, 기본 60일 */
    max_age_days?: number
    /** [Q12] search_volume<50 저신뢰 키워드 포함 (기본 false) */
    include_low_volume?: boolean
    /** 최신 완료 Legion run + document_count>0 키워드만 조회 */
    latest_verified_only?: boolean
    /** 실제 유입 핵심군만 조회 */
    business_core_only?: boolean
    limit?: number
    offset?: number
  }) => {
    const response = await api.get('/pathfinder/keywords', { params })
    return response.data
  },

  runPathfinder: async (mode: 'total_war' | 'legion', target = 500, save_db = true) => {
    const response = await api.post('/pathfinder/run', {
      mode,
      target,
      save_db,
    })
    return response.data
  },

  getClusters: async () => {
    const response = await api.get('/pathfinder/clusters')
    return response.data
  },

  exportAllKeywords: async (params?: {
    grade?: string
    category?: string
    latest_verified_only?: boolean
    business_core_only?: boolean
  }) => {
    const response = await api.get('/pathfinder/keywords/export-all', { params })
    return response.data
  },

  getContentCalendar: async (weeks: number = 12) => {
    const response = await api.get('/pathfinder/content-calendar', { params: { weeks } })
    return response.data
  },

  generateOutline: async (keywords: string[], clusterName?: string, category?: string) => {
    const response = await api.post('/pathfinder/generate-outline', {
      keywords,
      cluster_name: clusterName,
      category
    })
    return response.data
  },

  updateKeyword: async (keyword: string, data: {
    grade?: string
    category?: string
    memo?: string
    user_tags?: string[]
  }) => {
    const response = await api.patch(`/pathfinder/keywords/${encodeURIComponent(keyword)}`, data)
    return response.data
  },

  getScanHistory: async (params?: { limit?: number; offset?: number; scan_type?: string }) => {
    const response = await api.get('/pathfinder/scan-history', { params })
    return response.data
  },

  getScanRunDetail: async (runId: number) => {
    const response = await api.get(`/pathfinder/scan-history/${runId}`)
    return response.data
  },

  getScanStatus: async () => {
    const response = await api.get('/pathfinder/scan-status')
    return response.data
  },

  getTopKeiKeywords: async (limit = 20, minVolume = 10) => {
    const response = await api.get('/pathfinder/keywords/top-kei', {
      params: { limit, min_volume: minVolume }
    })
    return response.data
  },

  recalculateKei: async () => {
    const response = await api.post('/pathfinder/keywords/recalculate-kei')
    return response.data
  },

  getInsightBrief: async (limit = 12, useCodex = false) => {
    const response = await api.get('/pathfinder/insight-brief', {
      params: { limit, use_codex: useCodex }
    })
    return response.data
  },

  getAgentHandoff: async (agent: 'all' | 'blog' | 'shorts' | 'viral' | 'ads' = 'all', limit = 8) => {
    const response = await api.get('/pathfinder/agent-handoff', {
      params: { agent, limit }
    })
    return response.data
  },

  submitInsightFeedback: async (payload: {
    handoff_id: string
    keyword?: string
    agent?: string
    feedback_type: 'accepted' | 'rejected' | 'needs_review' | 'sent_to_agent' | 'completed' | 'failed'
    note?: string
    metadata?: Record<string, unknown>
  }) => {
    const response = await api.post('/pathfinder/insight-feedback', payload)
    return response.data
  },
}

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

  exportAllKeywords: async (params?: { grade?: string; category?: string }) => {
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
}

/**
 * Battle Intelligence API - 순위 추적 관련
 */

import { api, RankDropAlertsResponse, GenerateRankAlertsResponse } from './base'

export const battleApi = {
  getRankingKeywords: async () => {
    const response = await api.get('/battle/ranking-keywords')
    return response.data
  },

  getRankingTrends: async (days = 14, keyword_filter?: string) => {
    const response = await api.get('/battle/ranking-trends', {
      params: { days, keyword_filter },
    })
    return response.data
  },

  addRankingKeyword: async (keyword: string, target_rank = 10, category = '기타') => {
    const response = await api.post('/battle/ranking-keywords', {
      keyword,
      target_rank,
      category,
    })
    return response.data
  },

  removeRankingKeyword: async (keyword: string) => {
    const response = await api.delete(`/battle/ranking-keywords/${keyword}`)
    return response.data
  },

  updateRankingKeyword: async (oldKeyword: string, newKeyword: string, category?: string) => {
    const response = await api.put(`/battle/ranking-keywords/${encodeURIComponent(oldKeyword)}`, {
      new_keyword: newKeyword,
      category,
    })
    return response.data
  },

  refreshKeywordVolumes: async () => {
    const response = await api.post('/battle/ranking-keywords/refresh-volumes')
    return response.data
  },

  getCompetitorVitals: async () => {
    const response = await api.get('/battle/competitor-vitals')
    return response.data
  },

  updateTargetRank: async (keyword: string, targetRank: number) => {
    const response = await api.put(
      `/battle/ranking-keywords/${encodeURIComponent(keyword)}/target-rank`,
      { keyword, target_rank: targetRank }
    )
    return response.data
  },

  getRankingForecast: async (days = 14, forecastDays = 7) => {
    const response = await api.get('/battle/ranking-forecast', {
      params: { days, forecast_days: forecastDays }
    })
    return response.data
  },

  getForecastAccuracy: async (backtestDays = 7, analysisDays = 14) => {
    const response = await api.get('/battle/forecast-accuracy', {
      params: { backtest_days: backtestDays, analysis_days: analysisDays }
    })
    return response.data
  },

  getRankDropAlerts: async (minDrop = 3, includeTrends = true): Promise<RankDropAlertsResponse> => {
    const response = await api.get<RankDropAlertsResponse>('/battle/rank-drop-alerts', {
      params: { min_drop: minDrop, include_trends: includeTrends }
    })
    return response.data
  },

  generateRankAlerts: async (minDrop = 3): Promise<GenerateRankAlertsResponse> => {
    const response = await api.post<GenerateRankAlertsResponse>('/battle/generate-rank-alerts', null, {
      params: { min_drop: minDrop }
    })
    return response.data
  },

  addCompetitorRanking: async (data: {
    competitor_name: string
    keyword: string
    rank: number
    note?: string
  }) => {
    const response = await api.post('/battle/competitor-rankings', data)
    return response.data
  },

  getCompetitorRankings: async (params?: {
    competitor_name?: string
    keyword?: string
    limit?: number
  }) => {
    const response = await api.get('/battle/competitor-rankings', { params })
    return response.data
  },

  compareRankingsWithCompetitors: async (keyword?: string) => {
    const response = await api.get('/battle/competitor-rankings/compare', {
      params: keyword ? { keyword } : undefined
    })
    return response.data
  },
}

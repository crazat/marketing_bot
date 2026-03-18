/**
 * HUD (Heads-Up Display) API - 대시보드 관련
 */

import { api, AiBriefingData } from './base'

export const hudApi = {
  getMetrics: async () => {
    const response = await api.get('/hud/metrics')
    return response.data
  },

  getSystemStatus: async () => {
    const response = await api.get('/hud/system-status')
    return response.data
  },

  getBriefing: async () => {
    const response = await api.get('/hud/briefing')
    return response.data
  },

  getAiBriefing: async (): Promise<AiBriefingData> => {
    const response = await api.get('/hud/ai-briefing')
    return response.data
  },

  getSentinelAlerts: async () => {
    const response = await api.get('/hud/sentinel-alerts')
    return response.data
  },

  executeMission: async (moduleName: string) => {
    const response = await api.post(`/hud/mission/${moduleName}`)
    return response.data
  },

  stopMission: async (moduleName: string) => {
    const response = await api.post(`/hud/mission/${moduleName}/stop`)
    return response.data
  },

  getMissionStatus: async (moduleName: string, lines = 20) => {
    const response = await api.get(`/hud/mission/${moduleName}/status`, {
      params: { lines }
    })
    return response.data
  },

  getSchedulerState: async () => {
    const response = await api.get('/hud/scheduler-state')
    return response.data
  },

  getRunningModules: async () => {
    const response = await api.get('/hud/running-modules')
    return response.data
  },

  getRecentActivities: async () => {
    const response = await api.get('/hud/recent-activities')
    return response.data
  },

  getMetricsTrend: async (days = 7) => {
    const response = await api.get('/hud/metrics-trend', { params: { days } })
    return response.data
  },

  getGoals: async () => {
    const response = await api.get('/hud/goals')
    return response.data
  },

  createGoal: async (data: { type: string; target_value: number; period?: string; title?: string }) => {
    const response = await api.post('/hud/goals', data)
    return response.data
  },

  deleteGoal: async (goalId: number) => {
    const response = await api.delete(`/hud/goals/${goalId}`)
    return response.data
  },

  getWeeklyReport: async () => {
    const response = await api.get('/hud/weekly-report')
    return response.data
  },

  getOverdueLeads: async () => {
    const response = await api.get('/hud/overdue-leads')
    return response.data
  },

  getRankAlerts: async () => {
    const response = await api.get('/hud/rank-alerts')
    return response.data
  },

  getRecommendedKeywords: async (limit: number = 10) => {
    const response = await api.get('/hud/recommended-keywords', { params: { limit } })
    return response.data
  },

  getSuggestedActions: async () => {
    const response = await api.get('/hud/suggested-actions')
    return response.data
  },

  getKeiAlerts: async (days: number = 7) => {
    const response = await api.get('/hud/kei-alerts', { params: { days } })
    return response.data
  },

  getAutoApprovalAlerts: async (days: number = 7) => {
    const response = await api.get('/hud/auto-approval-alerts', { params: { days } })
    return response.data
  },
}

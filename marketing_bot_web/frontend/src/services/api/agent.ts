/**
 * AI Agent API - AI 에이전트 관련
 */

import { api, BatchActionResponse } from './base'

export const agentApi = {
  getUsageStats: async () => {
    const response = await api.get('/agent/usage-stats')
    return response.data
  },

  getActionsLog: async (params: {
    limit?: number
    offset?: number
    status?: string
    action_type?: string
  } = {}) => {
    const response = await api.get('/agent/actions-log', { params })
    return response.data
  },

  approveAction: async (actionId: number, notes?: string) => {
    const response = await api.post(`/agent/approve/${actionId}`, { notes })
    return response.data
  },

  rejectAction: async (actionId: number, notes?: string) => {
    const response = await api.post(`/agent/reject/${actionId}`, { notes })
    return response.data
  },

  getSummary: async () => {
    const response = await api.get('/agent/summary')
    return response.data
  },

  batchApprove: async (actionType?: string): Promise<BatchActionResponse> => {
    const response = await api.post<BatchActionResponse>('/agent/batch-approve', null, {
      params: actionType ? { action_type: actionType } : undefined
    })
    return response.data
  },

  batchReject: async (actionType?: string, reason?: string): Promise<BatchActionResponse> => {
    const response = await api.post<BatchActionResponse>('/agent/batch-reject', null, {
      params: {
        ...(actionType ? { action_type: actionType } : {}),
        ...(reason ? { reason } : {})
      }
    })
    return response.data
  },

  getApprovalRates: async () => {
    const response = await api.get('/agent/approval-rates')
    return response.data
  },

  getRules: async () => {
    const response = await api.get('/agent/rules')
    return response.data
  },

  createRule: async (data: {
    name: string
    description?: string
    condition_type: string
    condition_value: string
    action?: string
    priority?: number
    is_active?: boolean
  }) => {
    const response = await api.post('/agent/rules', data)
    return response.data
  },

  updateRule: async (ruleId: number, data: {
    name?: string
    description?: string
    condition_type?: string
    condition_value?: string
    action?: string
    priority?: number
    is_active?: boolean
  }) => {
    const response = await api.put(`/agent/rules/${ruleId}`, data)
    return response.data
  },

  deleteRule: async (ruleId: number) => {
    const response = await api.delete(`/agent/rules/${ruleId}`)
    return response.data
  },

  applyRules: async () => {
    const response = await api.post('/agent/rules/apply')
    return response.data
  },
}

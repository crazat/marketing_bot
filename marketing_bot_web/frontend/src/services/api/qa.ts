/**
 * Q&A Repository API - Q&A 패턴 및 응답 관리
 */

import { api } from './base'

export const qaApi = {
  getList: async (params: { category?: string; limit?: number; offset?: number } = {}) => {
    const response = await api.get('/qa/list', { params })
    return response.data
  },

  create: async (data: {
    question_pattern: string
    question_category?: string
    standard_answer: string
    variations?: string[]
  }) => {
    const response = await api.post('/qa/create', data)
    return response.data
  },

  update: async (id: number, data: {
    question_pattern?: string
    question_category?: string
    standard_answer?: string
    variations?: string[]
  }) => {
    const response = await api.put(`/qa/${id}`, data)
    return response.data
  },

  delete: async (id: number) => {
    const response = await api.delete(`/qa/${id}`)
    return response.data
  },

  match: async (text: string, limit = 3) => {
    const response = await api.get('/qa/match', { params: { text, limit } })
    return response.data
  },

  getStats: async () => {
    const response = await api.get('/qa/stats')
    return response.data
  },
}

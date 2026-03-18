/**
 * Review Response Assistant API - 리뷰 응답 관리
 */

import { api } from './base'

export const reviewsApi = {
  getTemplates: async () => {
    const response = await api.get('/reviews/templates')
    return response.data
  },

  createTemplate: async (data: {
    sentiment: string
    template_name: string
    content: string
    variables?: string[]
  }) => {
    const response = await api.post('/reviews/templates', data)
    return response.data
  },

  useTemplate: async (templateId: number) => {
    const response = await api.post(`/reviews/templates/${templateId}/use`)
    return response.data
  },

  deleteTemplate: async (templateId: number) => {
    const response = await api.delete(`/reviews/templates/${templateId}`)
    return response.data
  },

  generateResponse: async (data: {
    review_content: string
    reviewer_name?: string
    rating?: number
    sentiment?: string
    tone?: string
    include_promotion?: boolean
  }) => {
    const response = await api.post('/reviews/generate-response', data)
    return response.data
  },

  getHistory: async (limit = 20) => {
    const response = await api.get('/reviews/history', { params: { limit } })
    return response.data
  },

  getStats: async () => {
    const response = await api.get('/reviews/stats')
    return response.data
  },

  classifyReview: async (data: {
    review_content: string
    rating?: number
  }) => {
    const response = await api.post('/reviews/classify', data)
    return response.data
  },
}

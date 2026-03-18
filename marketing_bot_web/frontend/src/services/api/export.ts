/**
 * Data Export API - 데이터 내보내기 관련
 */

import { api } from './base'

export const exportApi = {
  getSummary: async () => {
    const response = await api.get('/export/summary')
    return response.data
  },

  downloadLeads: (params?: { status?: string; platform?: string; days?: number }) => {
    const queryString = new URLSearchParams(
      Object.entries(params || {}).filter(([, v]) => v !== undefined) as [string, string][]
    ).toString()
    const url = `/api/export/leads${queryString ? '?' + queryString : ''}`
    window.open(url, '_blank')
  },

  downloadKeywords: (params?: { grade?: string; category?: string; days?: number }) => {
    const queryString = new URLSearchParams(
      Object.entries(params || {}).filter(([, v]) => v !== undefined) as [string, string][]
    ).toString()
    const url = `/api/export/keywords${queryString ? '?' + queryString : ''}`
    window.open(url, '_blank')
  },

  downloadRankHistory: (params?: { keyword?: string; days?: number }) => {
    const queryString = new URLSearchParams(
      Object.entries(params || {}).filter(([, v]) => v !== undefined) as [string, string][]
    ).toString()
    const url = `/api/export/rank-history${queryString ? '?' + queryString : ''}`
    window.open(url, '_blank')
  },

  downloadViralTargets: (params?: { status?: string; days?: number }) => {
    const queryString = new URLSearchParams(
      Object.entries(params || {}).filter(([, v]) => v !== undefined) as [string, string][]
    ).toString()
    const url = `/api/export/viral-targets${queryString ? '?' + queryString : ''}`
    window.open(url, '_blank')
  },
}

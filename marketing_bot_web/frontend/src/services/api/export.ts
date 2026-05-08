/**
 * Data Export API - 데이터 내보내기 관련
 */

import { api } from './base'

function compactParams(params?: object): Record<string, string | number | boolean> {
  return Object.fromEntries(
    Object.entries(params || {}).filter(([, value]) => value !== undefined && value !== null),
  ) as Record<string, string | number | boolean>
}

function filenameFromDisposition(disposition: unknown, fallback: string): string {
  if (typeof disposition !== 'string') return fallback
  const match = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(disposition)
  const filename = match?.[1] || match?.[2]
  return filename ? decodeURIComponent(filename) : fallback
}

async function downloadCsv(path: string, params: object | undefined, fallbackName: string) {
  const response = await api.get(path, {
    params: compactParams(params),
    responseType: 'blob',
  })

  const rawContentType = response.headers['content-type']
  const contentType = typeof rawContentType === 'string' ? rawContentType : 'text/csv;charset=utf-8'
  const blob = new Blob([response.data], { type: contentType })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filenameFromDisposition(response.headers['content-disposition'], fallbackName)
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => window.URL.revokeObjectURL(url), 1000)
}

export const exportApi = {
  getSummary: async () => {
    const response = await api.get('/export/summary')
    return response.data
  },

  downloadLeads: async (params?: { status?: string; platform?: string; days?: number }) => {
    await downloadCsv('/export/leads', params, 'leads_export.csv')
  },

  downloadKeywords: async (params?: { grade?: string; category?: string; days?: number }) => {
    await downloadCsv('/export/keywords', params, 'keywords_export.csv')
  },

  downloadRankHistory: async (params?: { keyword?: string; days?: number }) => {
    await downloadCsv('/export/rank-history', params, 'rank_history_export.csv')
  },

  downloadViralTargets: async (params?: { status?: string; days?: number }) => {
    await downloadCsv('/export/viral-targets', params, 'viral_targets_export.csv')
  },
}

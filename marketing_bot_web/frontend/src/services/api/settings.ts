/**
 * Settings APIs - 설정 관련 (Preferences, Notifications, Config)
 */

import { api, extractResponseData, KeywordsData, KeywordMutationResponse, KeywordsBackupsResponse } from './base'

// ============================================
// User Preferences API
// ============================================
export interface WidgetConfig {
  enabled: boolean
  order: number
  title: string
}

export interface DashboardWidgets {
  [key: string]: WidgetConfig
}

export const preferencesApi = {
  getDashboard: async () => {
    const response = await api.get('/preferences/dashboard')
    return extractResponseData(response.data, { widgets: {}, available_widgets: [] })
  },

  updateDashboard: async (widgets: Record<string, { enabled: boolean; order?: number }>) => {
    const response = await api.put('/preferences/dashboard', { widgets })
    return extractResponseData(response.data, null)
  },

  resetDashboard: async () => {
    const response = await api.post('/preferences/dashboard/reset')
    return extractResponseData(response.data, null)
  },

  toggleWidget: async (widgetId: string, enabled: boolean) => {
    const response = await api.put(`/preferences/dashboard/widget/${widgetId}`, null, {
      params: { enabled }
    })
    return extractResponseData(response.data, null)
  },

  reorderWidgets: async (widgetOrder: string[]) => {
    const response = await api.put('/preferences/dashboard/reorder', widgetOrder)
    return response.data
  },

  getAll: async () => {
    const response = await api.get('/preferences/all')
    return response.data
  },
}

// ============================================
// Notifications API
// ============================================
export interface Notification {
  id: number
  type: 'rank_change' | 'new_lead' | 'competitor' | 'system' | 'keyword' | 'viral'
  priority: 'critical' | 'high' | 'medium' | 'low'
  title: string
  message: string
  link?: string
  metadata?: Record<string, unknown>
  is_read: number
  created_at: string
}

// 외부 알림 설정 타입
export interface ExternalNotificationSettings {
  id: number
  telegram_enabled: boolean
  telegram_bot_token_masked?: string
  telegram_chat_id?: string
  kakao_enabled: boolean
  kakao_access_token_masked?: string
  rank_drop_threshold: number
  new_lead_min_score: number
  competitor_activity_alert: boolean
  system_error_alert: boolean
  alert_quiet_start: string
  alert_quiet_end: string
  created_at: string
  updated_at: string
}

export interface NotificationSettingsUpdate {
  telegram_enabled?: boolean
  telegram_bot_token?: string
  telegram_chat_id?: string
  kakao_enabled?: boolean
  kakao_access_token?: string
  rank_drop_threshold?: number
  new_lead_min_score?: number
  competitor_activity_alert?: boolean
  system_error_alert?: boolean
  alert_quiet_start?: string
  alert_quiet_end?: string
}

export interface NotificationHistory {
  id: number
  notification_type: string
  channel: string
  title: string
  message: string
  status: 'sent' | 'failed'
  error_message?: string
  sent_at: string
}

export const notificationsApi = {
  getList: async (params?: { unread_only?: boolean; notification_type?: string; limit?: number }) => {
    const response = await api.get('/notifications/list', { params })
    return extractResponseData(response.data, { notifications: [], unread_count: 0, total: 0 })
  },

  markAsRead: async (id: number) => {
    const response = await api.put(`/notifications/${id}/read`)
    return extractResponseData(response.data, null)
  },

  markAllAsRead: async () => {
    const response = await api.put('/notifications/read-all')
    return extractResponseData(response.data, null)
  },

  delete: async (id: number) => {
    const response = await api.delete(`/notifications/${id}`)
    return extractResponseData(response.data, null)
  },

  clearOld: async (days = 30) => {
    const response = await api.delete('/notifications/clear-old', { params: { days } })
    return response.data
  },

  autoGenerate: async () => {
    const response = await api.get('/notifications/auto-generate')
    return response.data
  },

  // [Marketing Enhancement 2.0] 외부 알림 설정
  getSettings: async (): Promise<ExternalNotificationSettings> => {
    const response = await api.get('/notifications/settings')
    return extractResponseData(response.data, {} as ExternalNotificationSettings)
  },

  updateSettings: async (settings: NotificationSettingsUpdate): Promise<{ message: string }> => {
    const response = await api.put('/notifications/settings', settings)
    return extractResponseData(response.data, { message: '' })
  },

  testTelegram: async (message?: string): Promise<{ message: string; message_id?: number }> => {
    const response = await api.post('/notifications/test-telegram', { message })
    return extractResponseData(response.data, { message: '' })
  },

  testKakao: async (message?: string): Promise<{ message: string }> => {
    const response = await api.post('/notifications/test-kakao', { message })
    return extractResponseData(response.data, { message: '' })
  },

  getHistory: async (params?: { channel?: string; notification_type?: string; limit?: number }): Promise<{
    history: NotificationHistory[]
    total: number
    stats: { sent: number; failed: number }
  }> => {
    const response = await api.get('/notifications/history', { params })
    return extractResponseData(response.data, { history: [], total: 0, stats: { sent: 0, failed: 0 } })
  },

  triggerCheck: async (): Promise<{ message: string; results: { rank_drops: number; new_leads: number; competitor_activity: number } }> => {
    const response = await api.post('/notifications/trigger-check')
    return extractResponseData(response.data, { message: '', results: { rank_drops: 0, new_leads: 0, competitor_activity: 0 } })
  },
}

// ============================================
// Config API - keywords.json 웹 편집
// ============================================
export const configApi = {
  getKeywords: async (): Promise<KeywordsData> => {
    const response = await api.get<KeywordsData>('/config/keywords')
    return response.data
  },

  updateKeywords: async (data: { naver_place: string[]; blog_seo: string[] }): Promise<KeywordMutationResponse> => {
    const response = await api.put<KeywordMutationResponse>('/config/keywords', data)
    return response.data
  },

  addKeyword: async (keyword: string, category: 'naver_place' | 'blog_seo'): Promise<KeywordMutationResponse> => {
    const response = await api.post<KeywordMutationResponse>('/config/keywords/add', {
      keyword,
      category
    })
    return response.data
  },

  deleteKeyword: async (keyword: string, category: 'naver_place' | 'blog_seo'): Promise<KeywordMutationResponse> => {
    const response = await api.post<KeywordMutationResponse>('/config/keywords/delete', {
      keyword,
      category
    })
    return response.data
  },

  moveKeyword: async (keyword: string, fromCategory: 'naver_place' | 'blog_seo', toCategory: 'naver_place' | 'blog_seo'): Promise<KeywordMutationResponse> => {
    const response = await api.post<KeywordMutationResponse>('/config/keywords/move', {
      keyword,
      from_category: fromCategory,
      to_category: toCategory
    })
    return response.data
  },

  getKeywordsBackups: async (): Promise<KeywordsBackupsResponse> => {
    const response = await api.get<KeywordsBackupsResponse>('/config/keywords/backups')
    return response.data
  },

  restoreKeywordsBackup: async (filename: string): Promise<KeywordMutationResponse> => {
    const response = await api.post<KeywordMutationResponse>(`/config/keywords/restore/${filename}`)
    return response.data
  },

  getBusinessProfile: async () => {
    const response = await api.get('/config/business-profile')
    return response.data
  },

  getCategories: async () => {
    const response = await api.get('/config/categories')
    return response.data
  },

  getBranding: async () => {
    const response = await api.get('/config/branding')
    return response.data
  },

  // [Phase 4] 설정 파일 뷰어
  viewConfigFile: async (file: 'keywords' | 'config' | 'schedule') => {
    const response = await api.get('/config/view', { params: { file } })
    return response.data
  },
}

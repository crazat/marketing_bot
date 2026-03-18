/**
 * Viral Hunter API - 바이럴 타겟 관련
 */

import { api, ViralStats } from './base'

// 댓글 스타일 타입
export interface CommentStyle {
  id: string
  name: string
  icon: string
  description: string
}

// Decision Intelligence 타입들
export interface TrendInsights {
  period_days: number
  daily_trends: { date: string; count: number; avg_score: number }[]
  keyword_trends: {
    rising: { keyword: string; recent_count: number; older_count: number; change?: string; change_rate?: number }[]
    falling: { keyword: string; recent_count: number; older_count: number; change_rate: number }[]
  }
  platform_trends: { platform: string; data: { date: string; count: number }[]; total: number }[]
  category_trends: { category: string; count: number }[]
  insights: { type: string; message: string; importance: 'high' | 'medium' | 'low' }[]
}

export interface PerformanceStats {
  period_days: number
  funnel: {
    scanned: number; filtered: number; generated: number
    approved: number; posted: number; skipped: number; avg_priority_score: number
  }
  rates: {
    filter_rate: number; generation_rate: number; approval_rate: number
    posting_rate: number; overall_conversion: number; skip_rate: number
  }
  by_platform: {
    platform: string; total: number; generated: number; approved: number
    posted: number; avg_score: number; approval_rate: number; posting_rate: number
  }[]
  by_category: { category: string; total: number; posted: number; avg_score: number; posting_rate: number }[]
  daily_stats: { date: string; scanned: number; generated: number; posted: number; avg_score: number }[]
  top_performers: {
    id: string; title: string; platform: string; category: string
    priority_score: number; comment_preview: string; discovered_at: string
  }[]
  recent_posted: {
    id: string; title: string; platform: string; category: string
    priority_score: number; discovered_at: string
  }[]
  insights: { type: string; message: string; importance: 'high' | 'medium' | 'low' }[]
}

export interface PerformanceComparison {
  weekly: {
    this_week: { scanned: number; posted: number; rate: number }
    last_week: { scanned: number; posted: number; rate: number }
    change: { scanned: number; scanned_pct: number; posted: number; posted_pct: number }
  }
  monthly: {
    this_month: { scanned: number; posted: number; rate: number }
    last_month: { scanned: number; posted: number; rate: number }
    change: { scanned: number; scanned_pct: number; posted: number; posted_pct: number }
  }
}

export interface SmartRecommendations {
  quick_filters: {
    id: string; name: string; icon: string; description: string
    count: number; filter: Record<string, unknown>
  }[]
  today_focus: {
    id: string; title: string; platform: string
    priority_score: number; matched_keywords: string[]; scan_count: number
  }[]
  platform_priorities: { platform: string; count: number; avg_score: number }[]
  insights: { type: string; message: string; importance: 'high' | 'medium' | 'low' }[]
}

export interface TargetContext {
  target_id: string
  title: string
  platform: string
  similar_targets: {
    id: string; title: string; platform: string
    priority_score: number; comment_status: string; discovered_at: string
  }[]
  keyword_analysis: { keyword: string; grade: string; search_volume: number; kei_score: number }[]
  competitor_mentions: { competitor_id: number; competitor_name: string; context: string }[]
  target_history: { scan_count: number; first_seen: string; last_seen: string; current_score: number } | null
  insights: { type: string; message: string; importance: 'high' | 'medium' | 'low' }[]
}

// [Phase 9.0] 홈 화면 집계 통계 타입
export interface HomeStats {
  total_count: number
  platform_stats: Record<string, { count: number; avgScore: number; maxScore: number }>
  category_stats: Array<{
    category: string
    count: number
    avgScore: number
    maxScore: number
    priority: number
  }>
  status_stats: Record<string, number>  // 댓글 상태별 개수
  score_distribution: Record<string, number>  // 점수 분포
}

export const viralApi = {
  getStats: async (): Promise<ViralStats> => {
    const response = await api.get('/viral/stats')
    return response.data
  },

  // [Phase 9.0] 홈 화면용 집계 통계 (DB 직접 집계 - 성능 최적화)
  getHomeStats: async (scanBatch?: string): Promise<HomeStats> => {
    const params: Record<string, string> = {}
    if (scanBatch) params.scan_batch = scanBatch
    const response = await api.get('/viral/home-stats', { params })
    return response.data
  },

  getScanBatches: async () => {
    const response = await api.get('/viral/scan-batches')
    return response.data
  },

  getTargets: async (
    status = 'pending',
    category?: string,
    limit = 50,
    filters?: {
      date_filter?: string
      platforms?: string[]
      category?: string
      comment_status?: string
      min_scan_count?: number
      search?: string
      sort?: string
      scan_batch?: string
    }
  ) => {
    const params: Record<string, any> = { status, limit }

    if (category) params.category = category
    if (filters?.category) params.category = filters.category
    if (filters?.date_filter) params.date_filter = filters.date_filter
    if (filters?.platforms && filters.platforms.length > 0) {
      params.platforms = filters.platforms.join(',')
    }
    if (filters?.comment_status) params.comment_status = filters.comment_status
    if (filters?.min_scan_count) params.min_scan_count = filters.min_scan_count
    if (filters?.search) params.search = filters.search
    if (filters?.sort) params.sort = filters.sort
    if (filters?.scan_batch) params.scan_batch = filters.scan_batch

    const response = await api.get('/viral/targets', { params })
    return response.data
  },

  getCategories: async () => {
    const response = await api.get('/viral/categories')
    return response.data
  },

  generateComment: async (target_id: string | number, style: string = 'default') => {
    const response = await api.post('/viral/generate-comment', { target_id, style })
    return response.data
  },

  getCommentStyles: async (): Promise<{ success: boolean; styles: CommentStyle[] }> => {
    const response = await api.get('/viral/comment-styles')
    return response.data
  },

  generateCommentsBatch: async (data: {
    target_ids?: (string | number)[]
    category?: string
    batch_size?: number
    prioritize_by?: 'priority_score' | 'freshness' | 'engagement'
  }) => {
    const response = await api.post('/viral/generate-comments-batch', data)
    return response.data
  },

  targetAction: async (target_id: string | number, action: string, comment?: string) => {
    const response = await api.post('/viral/action', { target_id, action, comment })
    return response.data
  },

  runScan: async (config?: { platforms?: string[]; max_results?: number }) => {
    const response = await api.post('/viral/scan', config || {})
    return response.data
  },

  getTemplates: async () => {
    const response = await api.get('/viral/templates')
    return response.data
  },

  createTemplate: async (data: { name: string; content: string; category?: string }) => {
    const response = await api.post('/viral/templates', data)
    return response.data
  },

  useTemplate: async (templateId: number) => {
    const response = await api.patch(`/viral/templates/${templateId}/use`)
    return response.data
  },

  deleteTemplate: async (templateId: number) => {
    const response = await api.delete(`/viral/templates/${templateId}`)
    return response.data
  },

  recommendTemplate: async (data: {
    priority_rank: number
    engagement_signal: string
    category?: string
    content_preview?: string
  }) => {
    const response = await api.post('/viral/templates/recommend', data)
    return response.data
  },

  generateUtm: async (data: {
    url: string
    campaign?: string
    content?: string
    term?: string
    source?: string
    medium?: string
  }) => {
    const response = await api.post('/viral/generate-utm', data)
    return response.data
  },

  verifyTarget: async (target_id: string | number) => {
    const response = await api.post('/viral/verify-target', { target_id })
    return response.data
  },

  verifyBatch: async (category?: string, limit = 10) => {
    const params: Record<string, any> = { limit }
    if (category) params.category = category
    const response = await api.post('/viral/verify-batch', null, { params })
    return response.data
  },

  postComment: async (data: {
    target_id: number
    template_id?: number
    content: string
    platform: string
    url: string
    posted_at?: string
  }) => {
    const response = await api.post('/viral/comments/post', data)
    return response.data
  },

  updateCommentEngagement: async (commentId: number, data: {
    likes?: number
    replies?: number
    clicks?: number
    led_to_contact?: boolean
    led_to_conversion?: boolean
  }) => {
    const response = await api.put(`/viral/comments/${commentId}/engagement`, data)
    return response.data
  },

  getCommentPerformance: async (days = 30) => {
    const response = await api.get('/viral/comments/performance', { params: { days } })
    return response.data
  },

  getPostedComments: async (params?: { platform?: string; limit?: number; offset?: number }) => {
    const response = await api.get('/viral/comments/list', { params })
    return response.data
  },

  getTargetContext: async (targetId: string): Promise<TargetContext> => {
    const response = await api.get(`/viral/target/${targetId}/context`)
    return response.data
  },

  getSmartRecommendations: async (): Promise<SmartRecommendations> => {
    const response = await api.get('/viral/smart-recommendations')
    return response.data
  },

  getTrendInsights: async (days = 7): Promise<TrendInsights> => {
    const response = await api.get('/viral/trend-insights', { params: { days } })
    return response.data
  },

  getPerformanceStats: async (days = 30): Promise<PerformanceStats> => {
    const response = await api.get('/viral/performance-stats', { params: { days } })
    return response.data
  },

  getPerformanceComparison: async (): Promise<PerformanceComparison> => {
    const response = await api.get('/viral/performance-comparison')
    return response.data
  },
}

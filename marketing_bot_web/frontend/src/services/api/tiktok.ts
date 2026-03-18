/**
 * TikTok API 클라이언트
 */
import { api, extractResponseData } from './base'

// TikTok 타입 정의
export interface TikTokVideo {
  id: number
  video_id: string
  author_username: string
  author_nickname: string
  description: string
  hashtags: string[]
  views: number
  likes: number
  comments: number
  shares: number
  music_title: string
  music_author: string
  duration: number
  video_url: string
  thumbnail_url: string
  scraped_at: string
  matched_keyword: string | null
  engagement_rate: number
}

export interface TikTokTrend {
  id: number
  trend_type: 'hashtag' | 'music' | 'effect'
  name: string
  view_count: number
  video_count: number
  growth_rate: number
  first_seen: string
  last_updated: string
  is_hot: boolean
}

export interface TikTokAccount {
  username: string
  nickname: string
  follower_count: number
  following_count: number
  total_likes: number
  video_count: number
  bio: string
  is_competitor: boolean
  last_scanned: string
}

export interface TikTokAnalytics {
  total_views: number
  total_likes: number
  total_comments: number
  total_shares: number
  avg_engagement_rate: number
  top_performing_video: TikTokVideo | null
  growth_trend: 'up' | 'down' | 'stable'
  daily_stats: Array<{
    date: string
    views: number
    engagement: number
  }>
  // 확장 속성
  overall?: {
    total_views: number
    total_likes: number
    avg_engagement: number
    top_engagement: number
  }
  top_accounts?: Array<{
    author_username: string
    video_count: number
    total_views: number
  }>
  top_hashtags?: Array<{
    hashtag: string
    video_count: number
  }>
}

export interface TikTokStatus {
  enabled: boolean
  last_scan: string | null
  total_videos: number
  total_trends: number
  tracked_accounts: number
  api_status: 'ok' | 'error' | 'not_configured'
  message: string
  // 확장 속성
  status?: 'active' | 'pending'
  videos?: {
    total_videos: number
    unique_accounts: number
    competitor_videos: number
  }
  trends?: {
    total_trends: number
    rising_trends: number
  }
}

export interface TikTokScanOptions {
  hashtags?: string[]
  accounts?: string[]
  limit?: number
  scan_trending?: boolean
}

export const tiktokApi = {
  // 상태 조회
  getStatus: async (): Promise<TikTokStatus> => {
    const response = await api.get('/tiktok/status')
    return extractResponseData(response)
  },

  // 비디오 목록 조회
  getVideos: async (params?: {
    limit?: number
    offset?: number
    hashtag?: string
    sort_by?: 'views' | 'likes' | 'engagement' | 'recent'
    days?: number
  }): Promise<{ videos: TikTokVideo[]; total: number; stats?: { total: number } }> => {
    const response = await api.get('/tiktok/videos', { params })
    return extractResponseData(response)
  },

  // 트렌드 조회
  getTrends: async (params?: {
    trend_type?: 'hashtag' | 'music' | 'effect'
    limit?: number
    hot_only?: boolean
    days?: number
  }): Promise<{ trends: TikTokTrend[]; total: number }> => {
    const response = await api.get('/tiktok/trends', { params })
    return extractResponseData(response)
  },

  // 스캔 시작
  startScan: async (options?: TikTokScanOptions): Promise<{
    message: string
    scan_id: string
    estimated_time: number
  }> => {
    const response = await api.post('/tiktok/scan', options)
    return extractResponseData(response)
  },

  // 계정 목록 조회
  getAccounts: async (): Promise<{ accounts: TikTokAccount[]; total: number }> => {
    const response = await api.get('/tiktok/accounts')
    return extractResponseData(response)
  },

  // 계정 추가
  addAccount: async (params: string | { username: string; is_competitor?: boolean }): Promise<{
    message: string
    account: TikTokAccount
  }> => {
    const data = typeof params === 'string'
      ? { username: params, is_competitor: false }
      : { username: params.username, is_competitor: params.is_competitor ?? false }
    const response = await api.post('/tiktok/accounts', data)
    return extractResponseData(response)
  },

  // 계정 삭제
  deleteAccount: async (username: string): Promise<{ message: string }> => {
    const response = await api.delete(`/tiktok/accounts/${username}`)
    return extractResponseData(response)
  },

  // 분석 데이터 조회
  getAnalytics: async (params?: {
    days?: number
    account?: string
  }): Promise<TikTokAnalytics> => {
    const response = await api.get('/tiktok/analytics', { params })
    return extractResponseData(response)
  },

  // 해시태그 분석
  analyzeHashtag: async (hashtag: string): Promise<{
    hashtag: string
    total_views: number
    video_count: number
    avg_engagement: number
    trending: boolean
    related_hashtags: string[]
  }> => {
    const response = await api.get(`/tiktok/hashtag/${hashtag}`)
    return extractResponseData(response)
  },
}

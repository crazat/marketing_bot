// Keyword Types
export interface Keyword {
  keyword: string
  search_volume: number
  competition?: number
  difficulty?: number
  opportunity?: number
  grade: 'S' | 'A' | 'B' | 'C'
  category?: string
  source?: string
  kei?: number
  trend_status?: 'rising' | 'falling' | 'stable' | 'unknown'
  trend_slope?: number
  search_intent?: 'transactional' | 'commercial' | 'informational' | 'navigational' | 'unknown'
  created_at?: string
  updated_at?: string
}

export interface KeywordCluster {
  cluster_name: string
  keywords: string[]
  keyword_count: number
  total_volume: number
  avg_difficulty?: number
  representative_keyword?: string
}

// Pathfinder Stats
export interface CategoryStats {
  total: number
  s_grade: number
  a_grade: number
}

export interface PathfinderStats {
  total: number
  s_grade: number
  a_grade: number
  b_grade: number
  c_grade: number
  categories: Record<string, CategoryStats>
  sources: Record<string, number>
  trends: {
    rising: number
    falling: number
    stable: number
  }
  recent_keywords?: Keyword[]
}

// Pathfinder Scan Run (History)
export interface ScanRun {
  id: number
  scan_type: string
  mode: string
  target_count: number
  started_at: string
  completed_at: string | null
  status: string
  total_keywords: number
  new_keywords: number
  s_grade_count: number
  a_grade_count: number
  b_grade_count: number
  c_grade_count: number
  error_message: string | null
  top_keywords_json: string
  execution_time_seconds: number
  topKeywords?: Keyword[]
}

// Date Statistics (for Keyword History)
export interface DateStat {
  date: string
  total: number
  sCount: number
  aCount: number
  totalVolume: number
  sources: Record<string, number>
  categories: Record<string, number>
  keywords: Keyword[]
}

// Battle Intelligence Types
export interface RankingKeyword {
  keyword: string
  current_rank: number
  target_rank: number
  rank_change: number
  category?: string
  search_volume?: number
  last_checked?: string
  status?: 'scanned' | 'pending'
}

export interface RankHistory {
  rank: number
  date: string
}

export interface RankingTrends {
  keywords: Record<string, RankHistory[]>
  summary: {
    improving: number
    declining: number
    stable: number
    total: number
  }
}

export interface CompetitorVitals {
  competitors: CompetitorVital[]
  summary: {
    total_competitors: number
    most_active: string
    avg_posts_30d: number
  }
}

export interface CompetitorVital {
  name: string
  blog_posts_30d: number
  cafe_posts_30d: number
  total_posts_30d: number
  category: string
  priority: string
}

// Lead Types
export type Platform = 'naver' | 'youtube' | 'tiktok' | 'instagram' | 'carrot' | 'influencer'
export type LeadStatus = 'new' | 'contacted' | 'responded' | 'converted' | 'ignored'

export interface Lead {
  id: number
  platform: Platform
  name: string
  category?: string
  followers?: number
  engagement_rate?: number
  contact_info?: string
  status: LeadStatus
  notes?: string
  source_url?: string
  created_at: string
  updated_at?: string
}

export interface LeadStats {
  total: number
  by_platform: Record<Platform, number>
  by_status: Record<LeadStatus, number>
  recent_count: number
}

export interface LeadFilters {
  status?: LeadStatus | ''
  category?: string
  search?: string
}

// Viral Types
export interface ViralTarget {
  id: number
  platform: Platform
  target_name: string
  target_url: string
  category: string
  priority: 'high' | 'medium' | 'low'
  status: 'active' | 'paused' | 'completed'
  last_scanned?: string
  comment_count?: number
  keywords?: string[]
}

export interface ViralStats {
  total_targets: number
  total_comments: number
  by_platform: Record<Platform, number>
  by_status: Record<string, number>
}

export interface ViralCategory {
  name: string
  count: number
  platforms: Platform[]
}

// Competitor Types
export interface Competitor {
  id?: number
  name: string
  category: string
  priority: 'High' | 'Medium' | 'Low'
  naver_place_id?: string
  blog_id?: string
  instagram_handle?: string
  keywords?: string[]
  notes?: string
}

export type SeverityLevel = 'Critical' | 'High' | 'Medium' | 'Low'

export type WeaknessType =
  | 'service' | 'price' | 'facility' | 'wait_time' | 'effect'
  | '서비스' | '가격' | '시설' | '대기시간' | '효과' | '기타' | 'other'

export interface CompetitorWeakness {
  id: number
  competitor_name: string
  weakness_type: WeaknessType
  description: string
  severity?: SeverityLevel
  evidence?: string
  source_url?: string
  review_source?: string  // 하위 호환
  created_at: string
  impact_score?: number  // 0-100
}

export interface WeaknessSummary {
  total: number
  by_type: Record<string, number>
  by_competitor: Record<string, number>
}

export interface OpportunityKeyword {
  id: number
  keyword: string
  source_weakness: string
  competitor_name: string
  status: 'pending' | 'used' | 'rejected'
  created_at: string
}

export interface InstagramStats {
  total_accounts: number
  total_posts: number
  avg_engagement: number
  top_hashtags: string[]
}

export interface HashtagAnalysis {
  hashtag: string
  count: number
  avg_engagement: number
  category?: string
}

// WebSocket Types
export interface WebSocketMessage {
  type: string
  data: unknown
  timestamp?: string
}

// UI Types
export interface SelectOption {
  value: string
  label: string
}

// API Response Types
export interface ApiResponse<T> {
  status: 'success' | 'error'
  data?: T
  message?: string
  detail?: string
}

// Grade Icons/Colors Maps
export const GRADE_ICONS: Record<string, string> = {
  S: '🔥',
  A: '🟢',
  B: '🔵',
  C: '⚪'
}

export const GRADE_COLORS: Record<string, string> = {
  S: 'text-red-500',
  A: 'text-green-500',
  B: 'text-blue-500',
  C: 'text-muted-foreground'
}

export const TREND_ICONS: Record<string, string> = {
  rising: '📈',
  falling: '📉',
  stable: '➡️',
  unknown: '❓'
}

export const PLATFORM_ICONS: Record<Platform, string> = {
  naver: '🟢',
  youtube: '📺',
  tiktok: '🎵',
  instagram: '📸',
  carrot: '🥕',
  influencer: '⭐'
}

export const STATUS_COLORS: Record<LeadStatus, string> = {
  new: 'bg-blue-500/20 text-blue-500',
  contacted: 'bg-yellow-500/20 text-yellow-500',
  responded: 'bg-green-500/20 text-green-500',
  converted: 'bg-purple-500/20 text-purple-500',
  ignored: 'bg-muted text-muted-foreground'
}

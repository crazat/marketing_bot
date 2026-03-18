/**
 * API 기본 설정 - axios 인스턴스, 타입 정의, 헬퍼 함수
 */

import axios, { AxiosError } from 'axios'
import { parseApiError } from '@/utils/errorMessages'

// 개발 환경에서만 로그 출력
const isDev = import.meta.env.DEV
export const devLog = (...args: unknown[]) => isDev && console.log(...args)
export const devError = (...args: unknown[]) => isDev && console.error(...args)

// ============================================
// TypeScript 인터페이스 정의
// ============================================

export interface KeywordHighlight {
  keyword: string
  volume: number
  grade: string
}

export interface BriefingData {
  date: string | null
  summary: string
  keyword_highlights: {
    new_keywords: number
    new_s_grade: number
    top_keywords: KeywordHighlight[]
  }
  lead_summary: {
    new_leads: number
  }
  recommended_actions: {
    type: string
    priority: 'high' | 'medium' | 'low'
    action: string
  }[]
  recent_insights: {
    type: string
    title: string
    content: string
    created_at: string
  }[]
  urgent_actions?: {
    title: string
    action: string
    action_link?: string
    priority: 'critical' | 'high' | 'medium' | 'low'
    metric?: string | number
  }[]
}

export interface AiBriefingData {
  executive_summary: string
  key_insights: {
    category: 'keywords' | 'leads' | 'competition' | 'trends' | string
    title: string
    description: string
    importance: 'high' | 'medium' | 'low'
  }[]
  recommended_actions: {
    priority: number
    action: string
    reason: string
    link?: string
  }[]
  market_signals: {
    signal: string
    trend: 'up' | 'down' | 'stable'
    impact: string
  }[]
  risk_alerts: {
    level: 'warning' | 'critical'
    message: string
  }[]
  data_context: {
    keywords_count: number
    viral_targets_count: number
    leads_count: number
  }
  generated_at: string
  source: 'ai' | 'default'
}

export interface SentinelAlert {
  message: string
  severity: 'critical' | 'warning' | 'info'
  details?: {
    platform: string
    detected_at: string
    text: string
  }[]
}

export interface SentinelAlertsData {
  status: 'normal' | 'warning' | 'critical'
  alert_count: number
  alerts: SentinelAlert[]
}

export interface Activity {
  icon: string
  label: string
  relative_time: string
}

// AI Insights 관련 타입
export interface RankAlert {
  keyword: string
  previous_rank: number
  current_rank: number
  change: number
  severity?: 'critical' | 'warning' | 'info'
}

export interface TimingRecommendation {
  action: string
  optimal_time: string
  reason: string
  priority?: 'high' | 'medium' | 'low'
}

export interface AiInsights {
  rank_alerts: RankAlert[]
  timing_recommendations: TimingRecommendation[]
  rising_keywords: number
  falling_keywords: number
}

export interface HudMetrics {
  total_keywords: number
  s_grade_keywords: number
  a_grade_keywords: number
  total_leads: number
  pending_leads?: number
  viral_targets?: number
  viral_total?: number
  viral_completed?: number
  viral_completion_rate?: number
  ranking_keywords?: number
  ai_insights?: AiInsights
}

export interface SystemStatus {
  scheduler_status: string
  last_pathfinder_run: string | null
  last_rank_check: string | null
}

export interface Keyword {
  id: number
  keyword: string
  search_volume: number
  grade: string
  category: string
  source: string
  trend_status: string
  created_at: string
}

export interface Lead {
  id: number
  platform: string
  source: string
  title: string
  content: string
  url: string
  author: string
  status: string
  detected_at: string
  score?: number
  notes?: string
  follow_up_date?: string
  trust_score?: number
  trust_level?: 'trusted' | 'review' | 'suspicious'
  trust_reasons?: string[]
  extracted_contacts?: {
    phone: string[]
    email: string[]
    kakao: string[]
    instagram: string[]
    has_contact: boolean
    summary: string
  }
  opportunity_bonus?: number
  engagement_signal?: 'seeking_info' | 'ready_to_act' | 'passive'
  priority_rank?: number
  multi_dimensional?: {
    conversion_probability: number
    urgency_score: number
    revenue_potential: 'premium' | 'high' | 'medium' | 'low'
    fit_score: number
    priority_rank: number
  }
}

export interface LeadStats {
  total: number
  by_platform: Record<string, number>
  by_status: {
    hot?: number
    new?: number
    contacted?: number
    qualified?: number
    converted?: number
    lost?: number
  }
}

// Viral 상태 타입
export type ViralCommentStatus = 'pending' | 'generated' | 'approved' | 'posted' | 'skipped'

export interface ViralTarget {
  id: string | number
  platform: string
  title: string
  url: string
  author: string
  content: string
  category: string
  status: string
  comment_status?: ViralCommentStatus
  generated_comment?: string
  like_count?: number
  comment_count?: number
  view_count?: number
  posted_at?: string
  priority_score?: number
  is_commentable?: boolean
  last_scanned_at?: string
}

export interface ViralStats {
  total_targets: number
  pending: number
  generated: number
  approved: number
  posted: number
  skipped: number
  new_today?: number
}

export interface RankDropAlert {
  keyword: string
  previous_rank: number
  current_rank: number
  rank_drop: number
  target_rank?: number
  severity: 'critical' | 'warning' | 'notice'
  trend?: 'declining' | 'stable' | 'improving'
  consecutive_drops?: number
}

export interface RankDropAlertsResponse {
  alerts: RankDropAlert[]
  summary: {
    total_alerts: number
    critical_drops: number
    avg_drop: number
    keywords_outside_top10: number
  }
}

export interface GenerateRankAlertsResponse {
  success: boolean
  created_count: number
  skipped_count: number
  alerts: Array<{
    keyword: string
    drop: number
    priority: string
    title: string
  }>
  message: string
}

export interface KeywordsData {
  naver_place: string[]
  blog_seo: string[]
  total_count?: number
}

export interface KeywordMutationResponse {
  success: boolean
  message: string
  keyword?: string
  category?: string
}

export interface BatchActionResponse {
  success: boolean
  message: string
  count: number
  action_type?: string
  approved_count?: number
  rejected_count?: number
}

export interface ContactHistory {
  id: number
  lead_id: number
  contact_type: 'comment' | 'dm' | 'email' | 'call'
  content: string
  platform?: string
  response?: string
  status?: string
  created_at: string
}

export interface ContactHistoryResponse {
  history: ContactHistory[]
  total: number
  lead_id: number
}

export interface AddContactHistoryResponse {
  success: boolean
  message: string
  id: number
}

export interface UpdateContactResponse {
  success: boolean
  message: string
}

export interface KeywordsBackup {
  filename: string
  created_at: string
  size_bytes: number
}

export interface KeywordsBackupsResponse {
  backups: KeywordsBackup[]
  total: number
}

export interface QAItem {
  id: number
  question_pattern: string
  question_category: string
  standard_answer: string
  variations: string[]
  use_count: number
  created_at: string
  updated_at: string
  match_score?: number
}

export interface QAListResponse {
  items: QAItem[]
  total: number
  categories: string[]
  limit: number
  offset: number
}

// ============================================
// Analytics 타입 정의
// ============================================

// Weekly Briefing
export interface WeeklyBriefingData {
  generated_at: string
  period: { start: string; end: string }
  key_metrics: {
    new_leads: { value: number; change_percent: number; hot_count: number; warm_count: number }
    conversions: { value: number; change_percent: number; conversion_rate: number }
    revenue: { value: number; change_percent: number }
  }
  top_performing_keywords: { keyword: string; conversions: number; revenue: number }[]
  rank_changes: {
    keyword: string
    current_rank: number
    previous_rank: number
    change: number
    direction: 'up' | 'down' | 'stable'
  }[]
  alerts: { pending_hot_leads: number; competitor_in_top3: number }
  insights: string[]
  recommended_actions: { priority: 'high' | 'medium' | 'low'; action: string; link?: string }[]
}

// Marketing Health Score
export interface MarketingHealthScoreData {
  period_days: number
  calculated_at: string
  total_score: number
  grade: 'A' | 'B' | 'C' | 'D'
  grade_label: string
  grade_color: 'green' | 'blue' | 'yellow' | 'red'
  scores: { ranking: number; viral: number; leads: number; competition: number }
  weights: { ranking: number; viral: number; leads: number; competition: number }
  details: Record<string, unknown>
  recommendations: { area: string; priority: 'high' | 'medium' | 'low'; message: string }[]
}

// Before/After Comparison
export interface BeforeAfterComparisonData {
  periods: {
    before: { start: string; end: string }
    after: { start: string; end: string }
  }
  before: {
    leads: { total: number; hot: number; converted: number }
    virals: { total: number; completed: number }
    avg_rank: number | null
    top10_keywords: number
    conversions: number
    revenue: number
  }
  after: {
    leads: { total: number; hot: number; converted: number }
    virals: { total: number; completed: number }
    avg_rank: number | null
    top10_keywords: number
    conversions: number
    revenue: number
  }
  changes: Record<string, { value: number; percent: number | null; direction: 'up' | 'down' | 'stable' }>
  overall: 'significant_improvement' | 'improvement' | 'stable' | 'decline' | 'significant_decline'
  overall_label: string
  positive_changes: number
  negative_changes: number
  insights: string[]
}

export interface ApiError {
  message: string
  detail?: string
  status?: number
}

// ============================================
// Axios 인스턴스 및 인터셉터
// ============================================

export const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// [성능 최적화] 장시간 작업용 API 인스턴스 (스캔, 분석 등)
export const longRunningApi = axios.create({
  baseURL: '/api',
  timeout: 300000, // 5분
})

// longRunningApi에도 동일한 인터셉터 적용
longRunningApi.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string; message?: string }>) => {
    const parsedError = parseApiError(error)

    const apiError: ApiError = {
      message: parsedError.userMessage,
      detail: parsedError.technicalMessage,
      status: parsedError.statusCode,
    }

    devError('[Long Running API Error]', {
      userMessage: parsedError.userMessage,
      technicalMessage: parsedError.technicalMessage,
      statusCode: parsedError.statusCode,
    })
    return Promise.reject(apiError)
  }
)

/**
 * [성능 최적화] AbortController 지원 API 요청 래퍼
 * 컴포넌트 언마운트 시 요청 취소 가능
 *
 * @example
 * const controller = new AbortController()
 * const data = await apiRequest('/path', { signal: controller.signal })
 * // 취소: controller.abort()
 */
export async function apiRequest<T>(
  url: string,
  options: {
    method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
    data?: unknown
    signal?: AbortSignal
    timeout?: number
  } = {}
): Promise<T> {
  const { method = 'GET', data, signal, timeout = 30000 } = options

  const response = await api.request<T>({
    url,
    method,
    data,
    signal,
    timeout,
  })

  return response.data
}

// ============================================
// 응답 표준화 헬퍼 함수
// ============================================

/**
 * 백엔드 응답에서 실제 데이터 추출
 */
export function extractResponseData<T>(responseData: unknown, fallback?: T): T {
  if (responseData === null || responseData === undefined) {
    return fallback as T
  }

  const data = responseData as Record<string, unknown>

  // success_response 래핑: { status: "success", data: {...} }
  if (data.status === 'success' && 'data' in data) {
    return (data.data as T) ?? (fallback as T)
  }

  // success 플래그 래핑: { success: true, data: {...} }
  if (data.success === true && 'data' in data) {
    return (data.data as T) ?? (fallback as T)
  }

  // 직접 반환된 경우
  return responseData as T
}

// 응답 인터셉터 - 에러 처리
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string; message?: string }>) => {
    const parsedError = parseApiError(error)

    const apiError: ApiError = {
      message: parsedError.userMessage,
      detail: parsedError.technicalMessage,
      status: parsedError.statusCode,
    }

    devError('[API Error]', {
      userMessage: parsedError.userMessage,
      technicalMessage: parsedError.technicalMessage,
      statusCode: parsedError.statusCode,
    })
    return Promise.reject(apiError)
  }
)

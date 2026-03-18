/**
 * Data Intelligence API - Phase 9 정보 수집 고도화
 */
import { api, extractResponseData } from './base'

// ============================================
// 타입 정의
// ============================================

export interface SmartPlaceStat {
  id: number
  date: string
  impressions: number
  clicks: number
  calls: number
  directions: number
  saves: number
  shares: number
  reviews_count: number
  avg_rating: number
  top_search_keywords: string[]
}

export interface SmartPlaceStatsResponse {
  stats: SmartPlaceStat[]
  summary: {
    total_impressions: number
    total_clicks: number
    total_calls: number
    total_directions: number
    total_saves: number
    avg_conversion_rate: number
    avg_engagement_rate: number
  }
}

export interface ReviewIntelligence {
  id: number
  competitor_name: string
  platform: string
  date: string
  total_reviews: number
  new_reviews_count: number
  avg_rating: number
  rating_distribution: Record<string, number>
  photo_review_ratio: number
  response_rate: number
  avg_response_time_hours: number
  sentiment_positive: number
  sentiment_negative: number
  sentiment_neutral: number
  top_keywords: string[]
  suspicious_review_count: number
}

export interface ReviewIntelSummary {
  total_competitors: number
  avg_response_rate: number
  avg_rating: number
  total_suspicious_reviews: number
  competitors: Array<{
    name: string
    avg_rating: number
    response_rate: number
    review_velocity: number
  }>
}

export interface BlogRankRecord {
  id: number
  keyword: string
  blog_url: string
  blog_title: string
  rank: number
  section: string
  total_results: number
  scanned_date: string
}

export interface HiraClinic {
  id: number
  ykiho: string
  name: string
  category: string
  address: string
  phone: string
  sido: string
  sigungu: string
  specialty: string[]
  doctor_count: number
  is_competitor: number
}

export interface MedicalReview {
  id: number
  platform: string
  clinic_name: string
  reviewer: string
  rating: number
  content: string
  treatment_type: string
  review_date: string
  is_our_clinic: number
  sentiment: string
}

export interface CompetitorChange {
  id: number
  competitor_name: string
  change_type: string
  source_url: string
  field_changed: string
  old_value: string
  new_value: string
  severity: string
  detected_at: string
  acknowledged: number
}

export interface KakaoRankRecord {
  id: number
  keyword: string
  rank: number
  status: string
  total_results: number
  place_name: string
  scanned_date: string
}

export interface CallTrackingRecord {
  date: string
  total_calls: number
  naver_search_calls: number
  direct_calls: number
  reservations: number
  reservation_rate: number
}

export interface CallTrackingResponse {
  records: CallTrackingRecord[]
  summary: {
    total_calls: number
    avg_daily_calls: number
    total_reservations: number
    avg_reservation_rate: number
  }
}

export interface GeoGridPoint {
  grid_lat: number
  grid_lng: number
  grid_label: string
  rank: number
  status: string
  place_name: string
}

export interface GeoGridResult {
  keyword: string
  scan_session_id: string
  scanned_date: string
  points: GeoGridPoint[]
  arp: number
}

export interface NaverAdKeyword {
  keyword: string
  monthly_search_pc: number
  monthly_search_mobile: number
  monthly_click_pc: number
  monthly_click_mobile: number
  monthly_ctr_pc: number
  monthly_ctr_mobile: number
  competition_level: string
  avg_ad_count: number
  related_keywords: string[]
  collected_date: string
}

export interface CommunityMention {
  id: number
  platform: string
  community_name: string
  title: string
  content_preview: string
  author: string
  url: string
  keyword_matched: string
  mention_type: string
  sentiment: string
  engagement_count: number
  comment_count: number
  is_lead_candidate: number
  discovered_at: string
}

export interface IntelligenceDashboard {
  smartplace_latest: SmartPlaceStat | null
  review_alerts: Array<{
    competitor_name: string
    alert_type: string
    detail: string
  }>
  competitor_changes_count: number
  blog_rank_summary: {
    ranked: number
    not_ranked: number
  }
  kakao_rank_summary: {
    ranked: number
    not_ranked: number
  }
  call_trend: CallTrackingRecord[]
  new_community_leads: number
}

// ============================================
// API 클라이언트
// ============================================

export const dataIntelligenceApi = {
  // SmartPlace 통계
  getSmartPlaceStats: async (days = 30): Promise<SmartPlaceStatsResponse> => {
    const response = await api.get('/data-intelligence/smartplace/stats', { params: { days } })
    return extractResponseData(response)
  },

  getSmartPlaceTrend: async (metric: string, days = 90) => {
    const response = await api.get(`/data-intelligence/smartplace/trend/${metric}`, { params: { days } })
    return extractResponseData(response)
  },

  // 리뷰 인텔리전스
  getReviewIntelligence: async (days = 30, competitor?: string): Promise<ReviewIntelligence[]> => {
    const response = await api.get('/data-intelligence/reviews/intelligence', {
      params: { days, ...(competitor && { competitor }) }
    })
    return extractResponseData(response)
  },

  getReviewIntelSummary: async (): Promise<ReviewIntelSummary> => {
    const response = await api.get('/data-intelligence/reviews/intelligence/summary')
    return extractResponseData(response)
  },

  // 블로그 순위
  getBlogRankings: async (days = 30, keyword?: string): Promise<BlogRankRecord[]> => {
    const response = await api.get('/data-intelligence/blog/rankings', {
      params: { days, ...(keyword && { keyword }) }
    })
    return extractResponseData(response)
  },

  // HIRA 의료기관
  getHiraClinics: async (sigungu = '청주', category = '한의원'): Promise<HiraClinic[]> => {
    const response = await api.get('/data-intelligence/hira/clinics', {
      params: { sigungu, category }
    })
    return extractResponseData(response)
  },

  // 의료 플랫폼 리뷰
  getMedicalReviews: async (days = 30, platform?: string, clinicName?: string): Promise<MedicalReview[]> => {
    const response = await api.get('/data-intelligence/medical-reviews', {
      params: { days, ...(platform && { platform }), ...(clinicName && { clinic_name: clinicName }) }
    })
    return extractResponseData(response)
  },

  // 경쟁사 변경 감지
  getCompetitorChanges: async (days = 30, severity?: string): Promise<CompetitorChange[]> => {
    const response = await api.get('/data-intelligence/competitor-changes', {
      params: { days, ...(severity && { severity }) }
    })
    return extractResponseData(response)
  },

  // 카카오맵 순위
  getKakaoRankings: async (days = 30, keyword?: string): Promise<KakaoRankRecord[]> => {
    const response = await api.get('/data-intelligence/kakao/rankings', {
      params: { days, ...(keyword && { keyword }) }
    })
    return extractResponseData(response)
  },

  // 전화 추적
  getCallTracking: async (days = 30): Promise<CallTrackingResponse> => {
    const response = await api.get('/data-intelligence/call-tracking', { params: { days } })
    return extractResponseData(response)
  },

  // 상권 데이터
  getCommercialData: async () => {
    const response = await api.get('/data-intelligence/commercial/data')
    return extractResponseData(response)
  },

  // 지오그리드
  getGeoGridLatest: async (keyword?: string): Promise<GeoGridResult> => {
    const response = await api.get('/data-intelligence/geo-grid/latest', {
      params: { ...(keyword && { keyword }) }
    })
    return extractResponseData(response)
  },

  getGeoGridSessions: async () => {
    const response = await api.get('/data-intelligence/geo-grid/sessions')
    return extractResponseData(response)
  },

  // 네이버 광고 키워드
  getNaverAdKeywords: async (days = 30, keyword?: string): Promise<NaverAdKeyword[]> => {
    const response = await api.get('/data-intelligence/naver-ads/keywords', {
      params: { days, ...(keyword && { keyword }) }
    })
    return extractResponseData(response)
  },

  // 커뮤니티 멘션
  getCommunityMentions: async (days = 30, platform?: string, isLead?: boolean): Promise<CommunityMention[]> => {
    const response = await api.get('/data-intelligence/community/mentions', {
      params: { days, ...(platform && { platform }), ...(isLead !== undefined && { is_lead: isLead }) }
    })
    return extractResponseData(response)
  },

  // 통합 대시보드
  getDashboard: async (): Promise<IntelligenceDashboard> => {
    const response = await api.get('/data-intelligence/dashboard')
    return extractResponseData(response)
  },
}

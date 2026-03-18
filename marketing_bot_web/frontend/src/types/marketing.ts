/**
 * Marketing Enhancement 타입 정의
 */

// ============================================
// 1. 골든타임 분석
// ============================================

export interface GoldenTimeHeatmapData {
  hour: number
  day_of_week: number
  total_comments: number
  total_likes: number
  total_replies: number
  avg_engagement: number
  conversions: number
}

export interface HourlyStats {
  hour: number
  comments: number
  engagement: number
  conversions: number
}

export interface DailyStats {
  day: number
  day_name: string
  comments: number
  engagement: number
  conversions: number
}

export interface GoldenTimeRecommendation {
  best_hours: Array<{ hour: number; engagement_rate: number }>
  best_days: Array<{ day: number; day_name: string; engagement_rate: number }>
}

export interface GoldenTimeStats {
  period_days: number
  platform?: string
  category?: string
  heatmap: GoldenTimeHeatmapData[]
  hourly_stats: HourlyStats[]
  daily_stats: DailyStats[]
  recommendations: GoldenTimeRecommendation
}

// ============================================
// 2. 리드 품질 스코어링
// ============================================

export interface LeadQualityStat {
  dimension: string
  value: string
  total_targets: number
  total_comments: number
  total_leads: number
  total_conversions: number
  comment_rate: number
  lead_rate: number
  conversion_rate: number
  quality_score: number
}

export interface LeadQualityStats {
  period_days: number
  dimension: string
  stats: LeadQualityStat[]
  summary: {
    total_targets: number
    total_comments: number
    total_leads: number
    total_conversions: number
    best_performing: LeadQualityStat | null
  }
}

// ============================================
// 3. 콘텐츠 성과 분석
// ============================================

export interface ContentPerformanceMatrix {
  content_type: string
  platform: string
  targets: number
  comments: number
  conversions: number
  conversion_rate: number
}

export interface ContentTypeStats {
  content_type: string
  targets: number
  comments: number
  conversions: number
  conversion_rate: number
}

export interface ContentPerformanceStats {
  period_days: number
  matrix: ContentPerformanceMatrix[]
  by_content_type: ContentTypeStats[]
  by_platform: Array<{
    platform: string
    targets: number
    comments: number
    conversions: number
    conversion_rate: number
  }>
}

// ============================================
// 4. 캠페인 관리
// ============================================

export interface CampaignKPISummary {
  processed: number
  comments: number
  leads: number
  conversions: number
  revenue: number
}

export interface Campaign {
  id: number
  name: string
  description?: string
  status: 'draft' | 'active' | 'paused' | 'completed'
  start_date?: string
  end_date?: string
  target_categories: string[]
  target_platforms: string[]
  daily_target: number
  total_target: number
  budget: number
  template_ids: number[]
  priority: number
  created_at: string
  updated_at: string
  kpi_summary: CampaignKPISummary
  progress_percent: number
}

export interface CampaignListResponse {
  campaigns: Campaign[]
  total: number
}

// ============================================
// 5. 통합 ROI 대시보드
// ============================================

export interface FunnelData {
  targets: number
  comments: number
  engagements: number
  leads: number
  conversions: number
  revenue: number
  rates: {
    target_to_comment: number
    comment_to_engagement: number
    engagement_to_lead: number
    lead_to_conversion: number
  }
}

export interface ChannelROIStat {
  platform: string
  comments: number
  engagements: number
  leads: number
  conversions: number
  estimated_revenue: number
  estimated_cost: number
  roi_percentage: number
}

export interface ROIRecommendation {
  type: string
  priority: string
  title: string
  description: string
  expected_impact: string
}

export interface ROIDashboardData {
  period_days: number
  funnel: FunnelData
  by_channel: ChannelROIStat[]
  summary: {
    total_revenue: number
    estimated_cost: number
    overall_roi: number
  }
  recommendations: ROIRecommendation[]
}

// ============================================
// 6. 스마트 알림
// ============================================

export interface AlertRule {
  id: number
  name: string
  description?: string
  rule_type: string
  condition_json: string
  action_type: string
  action_params: string
  priority: string
  is_active: number
  cooldown_minutes: number
  last_triggered_at?: string
  trigger_count: number
  created_at: string
  updated_at: string
}

export interface AlertLog {
  id: number
  rule_id?: number
  rule_name?: string
  alert_type: string
  title: string
  message?: string
  priority: string
  channel: string
  status: string
  sent_at?: string
  read_at?: string
  created_at: string
}

// ============================================
// 7. 경쟁사 바이럴 레이더
// ============================================

export interface CompetitorRadarStat {
  competitor_name: string
  total_mentions: number
  positive: number
  negative: number
  neutral: number
  weaknesses: number
  avg_counter_score: number
}

export interface CounterAttackOpportunity {
  id: number
  source_mention_id?: number
  competitor_name: string
  opportunity_type: string
  opportunity_score: number
  our_strength?: string
  suggested_response?: string
  status: string
  created_at: string
}

export interface CompetitorRadarStats {
  period_days: number
  competitors: CompetitorRadarStat[]
  opportunities: CounterAttackOpportunity[]
  summary: {
    total_competitors: number
    total_mentions: number
    total_weaknesses: number
    pending_opportunities: number
  }
}

// ============================================
// 8. A/B 테스트
// ============================================

export interface ABVariant {
  id: number
  experiment_id: number
  name: string
  description?: string
  content_template?: string
  weight: number
  is_control: number
  impressions: number
  engagements: number
  conversions: number
  engagement_rate: number
  conversion_rate: number
  created_at: string
}

export interface ABExperiment {
  id: number
  name: string
  description?: string
  status: 'draft' | 'running' | 'paused' | 'completed'
  experiment_type: string
  target_category?: string
  target_platform?: string
  sample_size_target: number
  confidence_level: number
  start_date?: string
  end_date?: string
  winner_variant_id?: number
  created_at: string
  updated_at: string
  variants: ABVariant[]
  total_impressions: number
  progress_percent: number
}

export interface ABTestListResponse {
  experiments: ABExperiment[]
  total: number
}

// ============================================
// 콘텐츠 유형 상수
// ============================================

export const CONTENT_TYPES = {
  question: { label: '질문형', icon: '❓', description: '추천해주세요, 어디가 좋을까요?' },
  concern: { label: '고민형', icon: '😔', description: '고민이에요, 아파요' },
  review: { label: '후기형', icon: '📝', description: '다녀왔는데, 후기 공유' },
  info: { label: '정보형', icon: '📖', description: '알려드립니다, 효과가 있어요' },
  unknown: { label: '미분류', icon: '❔', description: '분류되지 않음' },
} as const

export const DAY_NAMES = ['일', '월', '화', '수', '목', '금', '토'] as const

export const CAMPAIGN_STATUS = {
  draft: { label: '초안', color: 'gray' },
  active: { label: '활성', color: 'green' },
  paused: { label: '일시중지', color: 'yellow' },
  completed: { label: '완료', color: 'blue' },
} as const

export const AB_TEST_STATUS = {
  draft: { label: '초안', color: 'gray' },
  running: { label: '실행 중', color: 'green' },
  paused: { label: '일시중지', color: 'yellow' },
  completed: { label: '완료', color: 'blue' },
} as const

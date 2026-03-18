/**
 * Analytics 관련 타입 정의
 */

// 공통 타입
export interface TimePeriod {
  start: string
  end: string
}

// WeeklyBriefing 타입
export interface KeyMetric {
  value: number
  change_percent: number
  hot_count?: number
  warm_count?: number
  conversion_rate?: number
}

export interface TopKeyword {
  keyword: string
  conversions: number
  revenue: number
}

export interface RankChange {
  keyword: string
  direction: 'up' | 'down' | 'stable'
  previous_rank: number
  current_rank: number
  change: number
}

export interface RecommendedAction {
  action: string
  link: string
  priority: 'high' | 'medium' | 'low'
}

export interface WeeklyBriefingData {
  generated_at: string
  period: TimePeriod
  key_metrics: {
    new_leads: KeyMetric
    conversions: KeyMetric
    revenue: KeyMetric
  }
  top_performing_keywords: TopKeyword[]
  rank_changes: RankChange[]
  insights: string[]
  recommended_actions: RecommendedAction[]
  alerts: {
    pending_hot_leads: number
    competitor_in_top3: number
  }
}

// ChannelROI 타입
export interface PlatformROI {
  platform: string
  viral_count: number
  lead_count: number
  converted: number
  conversion_rate: number
  revenue: number
  revenue_per_lead: number
  revenue_per_viral: number
}

export interface KeywordROI {
  keyword: string
  viral_count: number
  lead_count: number
  conversions: number
  revenue: number
  conversion_rate: number
  avg_days_to_conversion: number
  revenue_per_viral: number
}

export interface ChannelROIData {
  period_days: number
  overview: {
    total_virals: number
    total_leads: number
    total_conversions: number
    total_revenue: number
    overall_conversion_rate: number
    revenue_per_conversion: number
  }
  by_platform: PlatformROI[]
  by_keyword: KeywordROI[]
  insights: string[]
}

// AttributionChain 타입
export interface KeywordAttribution {
  keyword: string
  viral_count: number
  lead_count: number
  conversions: number
  revenue: number
  conversion_rate: number
  avg_days_to_conversion: number
  revenue_per_viral: number
}

export interface TopPath {
  keyword: string
  platform: string
  conversions: number
  revenue: number
  avg_days_to_conversion: number
}

export interface AttributionChainData {
  period_days: number
  summary: {
    total_keywords: number
    total_virals: number
    total_leads: number
    total_conversions: number
    total_revenue: number
    conversion_rate: number
  }
  top_paths: TopPath[]
  keyword_attribution: KeywordAttribution[]
  insights: string[]
}

// CompetitorMovements 타입
export interface CompetitorAlert {
  type: string
  message: string
  severity: 'high' | 'medium' | 'low'
  competitor?: string
  keyword?: string
}

export interface CompetitorRankChange {
  competitor: string
  keyword: string
  direction: 'up' | 'down'
  previous_rank: number
  current_rank: number
}

export interface NewCompetitor {
  name: string
  keyword: string
  rank: number
}

export interface ActivityChange {
  competitor: string
  type: string
  direction: 'increase' | 'decrease'
  change: string
  metric: string
  recent_reviews?: number
  previous_reviews?: number
  increase_percent?: number
}

export interface CompetitorMovementsData {
  period_days: number
  movements: ActivityChange[]
  rank_changes: CompetitorRankChange[]
  new_competitors: NewCompetitor[]
  activity_changes: ActivityChange[]
  alerts: CompetitorAlert[]
  opportunities: Array<{ competitor: string; last_activity: string; message: string }>
  summary: {
    total_competitors: number
    rank_improved: number
    rank_dropped: number
    new_entries: number
    activity_increased: number
    total_movements: number
    high_severity: number
    medium_severity: number
    opportunities_count: number
  }
}

// ResponseGoldenTime 타입
export interface TimeBracket {
  bracket: string
  min_hours: number
  max_hours: number | null
  total_leads: number
  converted: number
  conversion_rate: number
}

export interface ResponseGoldenTimeData {
  period_days: number
  by_response_time: TimeBracket[]
  hot_lead_analysis: {
    within_1hour: { total: number; converted: number; conversion_rate: number }
    after_48hours: { total: number; converted: number; conversion_rate: number }
  }
  alerts: {
    pending_hot_leads: number
    urgent_hot_leads: number
  }
  insights: string[]
}

// KeywordLifecycle 타입
export type LifecycleStatus = 'discovered' | 'tracking' | 'active' | 'maintaining' | 'archived'

export interface KeywordLifecycleItem {
  keyword: string
  status: LifecycleStatus
  grade: string
  total_leads: number
  total_conversions: number
  total_revenue: number
  current_rank: number | null
  best_rank: number | null
  weeks_in_top10: number
  discovered_at: string
  tracking_started_at: string | null
  active_started_at: string | null
  last_viral_at: string | null
  last_lead_at: string | null
  last_conversion_at: string | null
  updated_at: string
  viral_count?: number
  lead_count?: number
  conversion_count?: number
  rank_change?: number
  last_activity_at?: string
}

export interface KeywordTransition {
  keyword: string
  from_status: LifecycleStatus
  to_status: LifecycleStatus
  changed_at: string
  reason?: string
}

export interface KeywordLifecycleData {
  keywords: KeywordLifecycleItem[]
  by_status: Record<LifecycleStatus, number>
  summary: {
    total: number
    by_status: Record<LifecycleStatus, number>
  }
  recent_transitions: KeywordTransition[]
  total: number
}

// MarketingHealthScore 타입
export interface HealthScoreDetails {
  avg_rank_score?: number
  top10_keywords?: number
  total_keywords?: number
  top10_ratio?: number
  current_period?: number
  previous_period?: number
  completed?: number
  completion_rate?: number
  growth_rate?: number
  total?: number
  hot?: number
  warm?: number
  converted?: number
  conversion_rate?: number
  wins?: number
  ties?: number
  losses?: number
  win_rate?: number
  message?: string
}

export interface HealthScoreRecommendation {
  area: string
  priority: 'high' | 'medium' | 'low'
  message: string
}

export interface MarketingHealthScoreData {
  period_days: number
  calculated_at: string
  total_score: number
  grade: string
  grade_label: string
  grade_color: string
  scores: {
    ranking: number
    viral: number
    leads: number
    competition: number
  }
  weights: {
    ranking: number
    viral: number
    leads: number
    competition: number
  }
  details: {
    ranking: HealthScoreDetails
    viral: HealthScoreDetails
    leads: HealthScoreDetails
    competition: HealthScoreDetails
  }
  recommendations: HealthScoreRecommendation[]
}

// BeforeAfterComparison 타입
export interface PeriodMetrics {
  leads: {
    total: number
    hot: number
    converted: number
  }
  virals: {
    total: number
    completed: number
  }
  avg_rank: number | null
  top10_keywords: number
  conversions: number
  revenue: number
}

export interface MetricChange {
  value: number
  percent: number | null
  direction: 'up' | 'down' | 'stable'
}

export interface BeforeAfterComparisonData {
  periods: {
    before: { start: string; end: string }
    after: { start: string; end: string }
  }
  before: PeriodMetrics
  after: PeriodMetrics
  changes: {
    leads_total: MetricChange
    leads_hot: MetricChange
    leads_converted: MetricChange
    virals_total: MetricChange
    virals_completed: MetricChange
    avg_rank: MetricChange
    top10_keywords: MetricChange
    conversions: MetricChange
    revenue: MetricChange
  }
  overall: string
  overall_label: string
  positive_changes: number
  negative_changes: number
  insights: string[]
}

// ReferralSources 타입
export interface ReferralSourceItem {
  source: string
  count: number
  percentage: number
  details: string[]
}

export interface ReferralSourcesData {
  period_days: number
  by_source: ReferralSourceItem[]
  total: number
  insights: string[]
  suggested_sources: string[]
  message?: string
}

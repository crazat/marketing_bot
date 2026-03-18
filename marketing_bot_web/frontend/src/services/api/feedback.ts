/**
 * Feedback API - 피드백 루프 (Phase D)
 */
import { api } from './base'

// 타입 정의
export interface ConversionAnalysis {
  platform_conversion_rates: Record<string, {
    rate: number
    total: number
    converted: number
  }>
  score_conversion_rates: Record<string, number>
  avg_conversion_time_hours: number
  total_conversions: number
  recommended_adjustments: Array<{
    factor: string
    current_weight: number
    suggested_weight: number
    reason: string
  }>
}

export interface WeightAdjustment {
  factor: string
  current_weight: number
  suggested_weight: number
  reason: string
}

export interface PredictionAccuracyResult {
  overall_accuracy: number
  verified_predictions: number
  accurate_predictions: number
  accuracy_by_confidence: Record<string, number>
  accuracy_by_trend: Record<string, number>
  recommendations: string[]
}

export interface KeywordROI {
  keyword: string
  leads_generated: number
  conversions: number
  conversion_rate: number
  roi_score: number
  trend: 'improving' | 'declining' | 'stable'
}

export interface ROIAnalysis {
  keywords: KeywordROI[]
  top_performers: KeywordROI[]
  underperformers: Array<{
    keyword: string
    leads_generated: number
    days_without_conversion: number
  }>
  summary: {
    total_keywords: number
    total_leads: number
    total_conversions: number
    avg_conversion_rate: number
  }
}

export interface ROITrend {
  date: string
  conversion_rate: number
  leads: number
  conversions: number
}

export interface PerformanceReport {
  period: string
  generated_at: string
  highlights: Array<{
    type: 'success' | 'warning' | 'info'
    message: string
    metric?: number
  }>
  metrics: {
    total_leads: number
    total_conversions: number
    conversion_rate: number
    avg_response_time_hours: number
    top_keyword: string
    top_platform: string
  }
  comparisons: {
    leads_change: number
    conversion_change: number
  }
  recommendations: string[]
}

export interface FeedbackCycleResult {
  conversion_analysis: {
    total_conversions: number
    adjustments_count: number
  }
  prediction_accuracy: {
    overall: number
    verified: number
  }
  roi_analysis: {
    keywords_analyzed: number
    top_performers: number
  }
  weekly_report: {
    generated: boolean
    highlights_count: number
  }
  errors: string[]
}

export interface FeedbackSummary {
  last_conversion_analysis: string | null
  last_accuracy_check: string | null
  last_roi_calculation: string | null
  last_weekly_report: string | null
  overall_accuracy: number | null
  total_conversions_30d: number
}

export const feedbackApi = {
  // 전환 특성 분석
  analyzeConversions: async (): Promise<ConversionAnalysis> => {
    const response = await api.post('/feedback/conversion-analysis')
    return response.data?.data || response.data
  },

  // 가중치 조정 제안 조회
  getWeightAdjustments: async (): Promise<{
    adjustments: WeightAdjustment[]
    total: number
  }> => {
    const response = await api.get('/feedback/weight-adjustments')
    return response.data?.data || response.data
  },

  // 예측 정확도 검증 실행
  validatePredictions: async (): Promise<PredictionAccuracyResult> => {
    const response = await api.post('/feedback/validate-predictions')
    return response.data?.data || response.data
  },

  // 예측 정확도 조회
  getPredictionAccuracy: async (): Promise<{
    overall_accuracy: number
    verified_count: number
    accurate_count: number
    by_confidence: Record<string, number>
    recommendations: string[]
  }> => {
    const response = await api.get('/feedback/prediction-accuracy')
    return response.data?.data || response.data
  },

  // ROI 분석
  getROI: async (periodDays: number = 30): Promise<ROIAnalysis> => {
    const response = await api.get('/feedback/roi', {
      params: { period_days: periodDays }
    })
    return response.data?.data || response.data
  },

  // 상위 성과 키워드 조회
  getTopPerformers: async (limit: number = 10): Promise<{
    top_performers: KeywordROI[]
    summary: ROIAnalysis['summary']
  }> => {
    const response = await api.get('/feedback/roi/top-performers', {
      params: { limit }
    })
    return response.data?.data || response.data
  },

  // 저성과 키워드 조회
  getUnderperformers: async (): Promise<{
    underperformers: ROIAnalysis['underperformers']
    total: number
  }> => {
    const response = await api.get('/feedback/roi/underperformers')
    return response.data?.data || response.data
  },

  // ROI 트렌드 조회
  getROITrends: async (keyword?: string): Promise<{
    trends: ROITrend[]
    keyword?: string
  }> => {
    const response = await api.get('/feedback/roi/trends', {
      params: keyword ? { keyword } : {}
    })
    return response.data?.data || response.data
  },

  // 주간 리포트 생성
  generateWeeklyReport: async (): Promise<PerformanceReport> => {
    const response = await api.post('/feedback/reports/weekly')
    return response.data?.data || response.data
  },

  // 월간 리포트 생성
  generateMonthlyReport: async (): Promise<PerformanceReport> => {
    const response = await api.post('/feedback/reports/monthly')
    return response.data?.data || response.data
  },

  // 최신 리포트 조회
  getLatestReport: async (reportType: 'weekly' | 'monthly' = 'weekly'): Promise<PerformanceReport | { message: string }> => {
    const response = await api.get('/feedback/reports/latest', {
      params: { report_type: reportType }
    })
    return response.data?.data || response.data
  },

  // 전체 피드백 사이클 실행
  runFeedbackCycle: async (): Promise<FeedbackCycleResult> => {
    const response = await api.post('/feedback/run-cycle')
    return response.data?.data || response.data
  },

  // 피드백 시스템 요약 조회
  getSummary: async (): Promise<FeedbackSummary> => {
    const response = await api.get('/feedback/summary')
    return response.data?.data || response.data
  },
}

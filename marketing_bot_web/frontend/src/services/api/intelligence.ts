/**
 * Intelligence API - AI 기반 지능화 (Phase B)
 */
import { api, extractResponseData } from './base'

// 타입 정의
export interface DashboardInsights {
  platform_conversion_rates: Record<string, number>
  high_performing_keywords: Array<{
    keyword: string
    conversion_rate: number
    leads: number
  }>
  rank_warnings: Array<{
    keyword: string
    current_rank: number
    trend: string
    warning_level: string
  }>
  timing_recommendations: Array<{
    platform: string
    recommended_action: string
    confidence: number
  }>
}

export interface ConversionPatterns {
  patterns: {
    platform_patterns: Record<string, number>
    keyword_patterns: Record<string, number>
    time_patterns: Record<string, number>
    score_patterns: Record<string, number>
  }
  pattern_types: string[]
  total_patterns: number
}

export interface CommentEffectiveness {
  length_analysis: {
    optimal_length: number
    length_distribution: Record<string, number>
  }
  style_analysis: {
    best_styles: string[]
    style_effectiveness: Record<string, number>
  }
  recommendations: string[]
}

export interface RankPrediction {
  keyword: string
  current_rank: number
  predicted_rank: number
  trend: 'rising' | 'falling' | 'stable'
  confidence: number
  factors: string[]
}

export interface RankPredictions {
  predictions: RankPrediction[]
  days_ahead: number
  total_keywords: number
  rising_count: number
  falling_count: number
  stable_count: number
}

export interface PredictionAccuracy {
  overall_accuracy: number
  verified_predictions: number
  accurate_predictions: number
  by_confidence: Record<string, number>
  by_trend: Record<string, number>
}

export interface TimingAnalysis {
  platform_timing: Record<string, {
    best_hours: number[]
    best_days: string[]
    avg_engagement: number
  }>
  recommendations: Array<{
    platform: string
    action: string
    timing: string
    confidence: number
  }>
}

export interface TimingRecommendation {
  platform: string
  action: string
  reason: string
}

export interface AnalysisSummary {
  conversion_patterns: {
    platform_count: number
    keyword_count: number
    total_leads: number
    total_conversions: number
  }
  comment_effectiveness: {
    length_analysis: boolean
    style_analysis: boolean
    recommendations_count: number
  }
  rank_predictions: {
    keywords_predicted: number
    rising_count: number
    falling_count: number
  }
  timing_analysis: {
    recommendations_count: number
  }
  errors: string[]
}

export const intelligenceApi = {
  // 대시보드 인사이트 조회
  getInsights: async (): Promise<DashboardInsights> => {
    const response = await api.get('/intelligence/insights')
    return extractResponseData(response)
  },

  // 전체 AI 분석 실행
  runFullAnalysis: async (): Promise<AnalysisSummary> => {
    const response = await api.post('/intelligence/analyze')
    return extractResponseData(response)
  },

  // 전환 패턴 조회
  getConversionPatterns: async (): Promise<ConversionPatterns> => {
    const response = await api.get('/intelligence/conversion-patterns')
    return extractResponseData(response)
  },

  // 전환 패턴 학습 실행
  learnConversionPatterns: async (): Promise<{ message: string }> => {
    const response = await api.post('/intelligence/conversion-patterns/learn')
    return extractResponseData(response)
  },

  // 전환 확률 예측
  predictConversion: async (data: {
    platform?: string
    keyword?: string
    score?: number
  }): Promise<{
    probability: number
    factors: Array<{ factor: string; impact: number }>
  }> => {
    const response = await api.post('/intelligence/conversion-patterns/predict', data)
    return extractResponseData(response)
  },

  // 댓글 효과 분석 조회
  getCommentEffectiveness: async (): Promise<CommentEffectiveness> => {
    const response = await api.get('/intelligence/comment-effectiveness')
    return extractResponseData(response)
  },

  // 댓글 효과 분석 실행
  analyzeCommentEffectiveness: async (): Promise<CommentEffectiveness> => {
    const response = await api.post('/intelligence/comment-effectiveness/analyze')
    return extractResponseData(response)
  },

  // 순위 예측 조회
  getRankPredictions: async (daysAhead: number = 7): Promise<RankPredictions> => {
    const response = await api.get('/intelligence/rank-predictions', {
      params: { days_ahead: daysAhead }
    })
    return extractResponseData(response)
  },

  // 예측 정확도 조회
  getPredictionAccuracy: async (): Promise<PredictionAccuracy> => {
    const response = await api.get('/intelligence/rank-predictions/accuracy')
    return extractResponseData(response)
  },

  // 타이밍 분석 조회
  getTimingAnalysis: async (): Promise<TimingAnalysis> => {
    const response = await api.get('/intelligence/timing')
    return extractResponseData(response)
  },

  // 현재 시점 타이밍 추천
  getCurrentTimingRecommendations: async (): Promise<{
    recommendations: TimingRecommendation[]
    has_recommendations: boolean
  }> => {
    const response = await api.get('/intelligence/timing/now')
    return extractResponseData(response)
  },

  // 타이밍 분석 실행
  analyzeTimng: async (): Promise<TimingAnalysis> => {
    const response = await api.post('/intelligence/timing/analyze')
    return extractResponseData(response)
  },
}

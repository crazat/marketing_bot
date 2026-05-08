/**
 * API 紐⑤뱢 ?듯빀 ?대낫?닿린
 *
 * ?섏쐞 ?명솚?깆쓣 ?꾪빐 紐⑤뱺 API? ??낆쓣 ?ш린???щ궡蹂대궡湲고빀?덈떎.
 * ??肄붾뱶?먯꽌??媛쒕퀎 紐⑤뱢?먯꽌 吏곸젒 import?섎뒗 寃껋쓣 沅뚯옣?⑸땲??
 *
 * @example
 * // ?덇굅??諛⑹떇 (?섏쐞 ?명솚)
 * import { hudApi, viralApi, LeadStats } from '@/services/api'
 *
 * // 沅뚯옣 諛⑹떇
 * import { hudApi } from '@/services/api/hud'
 * import { viralApi } from '@/services/api/viral'
 * import type { LeadStats } from '@/services/api/base'
 */

// Base - axios instance, types, helpers
export {
  api,
  getApiAuthHeaders,
  getConfiguredApiKey,
  setConfiguredApiKey,
  withApiKeyQuery,
  extractResponseData,
  devLog,
  devError,
  // Types
  type KeywordHighlight,
  type BriefingData,
  type AiBriefingData,
  type SentinelAlert,
  type SentinelAlertsData,
  type Activity,
  type HudMetrics,
  type SystemStatus,
  type Keyword,
  type Lead,
  type LeadStats,
  type ViralTarget,
  type ViralStats,
  type RankDropAlert,
  type RankDropAlertsResponse,
  type GenerateRankAlertsResponse,
  type KeywordsData,
  type KeywordMutationResponse,
  type BatchActionResponse,
  type ContactHistory,
  type ContactHistoryResponse,
  type AddContactHistoryResponse,
  type UpdateContactResponse,
  type KeywordsBackup,
  type KeywordsBackupsResponse,
  type QAItem,
  type QAListResponse,
  type ApiError,
} from './base'

import { withApiKeyQuery } from './base'

// HUD API
export { hudApi } from './hud'

// Pathfinder API
export { pathfinderApi } from './pathfinder'

// Battle Intelligence API
export { battleApi } from './battle'

// Leads API
export { leadsApi } from './leads'

// Viral Hunter API
export {
  viralApi,
  type TrendInsights,
  type PerformanceStats,
  type PerformanceComparison,
  type SmartRecommendations,
  type TargetContext,
} from './viral'

// Competitors & Instagram API
export { competitorsApi, instagramApi } from './competitors'

// Backup API
export { backupApi } from './backup'

// Agent API
export { agentApi } from './agent'

// Q&A API
export { qaApi } from './qa'

// Settings APIs (Preferences, Notifications, Config)
export {
  preferencesApi,
  notificationsApi,
  configApi,
  type WidgetConfig,
  type DashboardWidgets,
  type Notification,
} from './settings'

// Export API
export { exportApi } from './export'

// Reviews API
export { reviewsApi } from './reviews'

// Analytics & Marketing APIs
export { analyticsApi, marketingApi } from './analytics'

// TikTok API
export {
  tiktokApi,
  type TikTokVideo,
  type TikTokTrend,
  type TikTokAccount,
  type TikTokAnalytics,
  type TikTokStatus,
  type TikTokScanOptions,
} from './tiktok'

// Intelligence API (Phase B - AI 吏?ν솕)
export {
  intelligenceApi,
  type DashboardInsights,
  type ConversionPatterns,
  type CommentEffectiveness,
  type RankPrediction,
  type RankPredictions,
  type TimingAnalysis,
  type TimingRecommendation,
  type AnalysisSummary,
} from './intelligence'

// Automation API (Phase C - ?먮룞???뺤옣)
export {
  automationApi,
  type LeadClassificationResult,
  type PriorityLead,
  type RecommendedTarget,
  type KeywordOpportunity,
  type CompetitorThreat,
  type DailyBriefing,
  type AutomationStatus,
  type DailyAutomationResult,
} from './automation'

// Feedback API (Phase D - ?쇰뱶諛?猷⑦봽)
export {
  feedbackApi,
  type ConversionAnalysis,
  type WeightAdjustment,
  type PredictionAccuracyResult,
  type KeywordROI,
  type ROIAnalysis,
  type ROITrend,
  type PerformanceReport,
  type FeedbackCycleResult,
  type FeedbackSummary,
} from './feedback'

// Migration API
export {
  migrationApi,
  type MigrationInfo,
  type MigrationStatus,
  type MigrationRunResult,
  type MigrationHistory,
} from './migration'

// WebSocket connection
export const createWebSocket = (onMessage: (data: unknown) => void) => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(withApiKeyQuery(`${protocol}//${window.location.host}/ws`))

  const isDev = import.meta.env.DEV
  const devLog = (...args: unknown[]) => isDev && console.log(...args)
  const devError = (...args: unknown[]) => isDev && console.error(...args)

  ws.onopen = () => {
    devLog('WebSocket connected')
    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping')
      }
    }, 30000)

    ws.onclose = () => {
      clearInterval(pingInterval)
    }
  }

  ws.onmessage = (event) => {
    try {
      if (event.data === 'pong') return
      const data = JSON.parse(event.data)
      onMessage(data)
    } catch (error) {
      devError('WebSocket message parse error:', error)
    }
  }

  ws.onerror = (error) => {
    devError('WebSocket error:', error)
  }

  return ws
}

// Query Config (React Query ?ㅼ젙 ?꾨━??
export {
  QUERY_CONFIGS,
  DOMAIN_CONFIGS,
  TIME,
  getQueryConfig,
  conditionalRefetchInterval,
  useVisibilityBasedRefetch,
} from './queryConfig'

// Data Intelligence API (Phase 9 - ?뺣낫 ?섏쭛 怨좊룄??
export {
  dataIntelligenceApi,
  type SmartPlaceStat,
  type SmartPlaceStatsResponse,
  type ReviewIntelligence,
  type ReviewIntelSummary,
  type BlogRankRecord,
  type HiraClinic,
  type MedicalReview,
  type CompetitorChange,
  type KakaoRankRecord,
  type CallTrackingRecord,
  type CallTrackingResponse,
  type GeoGridPoint,
  type GeoGridResult,
  type NaverAdKeyword,
  type CommunityMention,
  type IntelligenceDashboard,
} from './dataIntelligence'

// 湲곕낯 export
export { api as default } from './base'

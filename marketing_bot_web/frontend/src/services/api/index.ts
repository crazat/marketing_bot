/**
 * API 모듈 통합 내보내기
 *
 * 하위 호환성을 위해 모든 API와 타입을 여기서 재내보내기합니다.
 * 새 코드에서는 개별 모듈에서 직접 import하는 것을 권장합니다.
 *
 * @example
 * // 레거시 방식 (하위 호환)
 * import { hudApi, viralApi, LeadStats } from '@/services/api'
 *
 * // 권장 방식
 * import { hudApi } from '@/services/api/hud'
 * import { viralApi } from '@/services/api/viral'
 * import type { LeadStats } from '@/services/api/base'
 */

// Base - axios instance, types, helpers
export {
  api,
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

// Intelligence API (Phase B - AI 지능화)
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

// Automation API (Phase C - 자동화 확장)
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

// Feedback API (Phase D - 피드백 루프)
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

// WebSocket 연결
export const createWebSocket = (onMessage: (data: unknown) => void) => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${protocol}//${window.location.host}/ws`)

  const isDev = import.meta.env.DEV
  const devLog = (...args: unknown[]) => isDev && console.log(...args)
  const devError = (...args: unknown[]) => isDev && console.error(...args)

  ws.onopen = () => {
    devLog('WebSocket 연결됨')
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
      const data = JSON.parse(event.data)
      onMessage(data)
    } catch (error) {
      devError('WebSocket 메시지 파싱 오류:', error)
    }
  }

  ws.onerror = (error) => {
    devError('WebSocket 오류:', error)
  }

  return ws
}

// Query Config (React Query 설정 프리셋)
export {
  QUERY_CONFIGS,
  DOMAIN_CONFIGS,
  TIME,
  getQueryConfig,
  conditionalRefetchInterval,
  useVisibilityBasedRefetch,
} from './queryConfig'

// Data Intelligence API (Phase 9 - 정보 수집 고도화)
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

// 기본 export
export { api as default } from './base'

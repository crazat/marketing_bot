/**
 * 유틸리티 모듈 인덱스
 */

// 리드 점수 관련
export {
  calculateLeadScore,
  sortLeadsByScore,
  getLeadGradeStats,
  getPlatformAverageScores,
  type Lead,
  type LeadScore,
} from './leadScoring'

// 콘텐츠 제안 관련
export {
  generateSuggestion,
  generateClusterSuggestion,
  generateSuggestions,
  generateWeeklyCalendar,
  getContentTypeStats,
  type Keyword,
  type ContentSuggestion,
} from './contentSuggestions'

// 마케팅 분석 관련
export {
  calculateConversionRate,
  calculateKeywordEfficiency,
  calculateLeadQualityScore,
  analyzeROI,
  analyzePlatformPerformance,
  analyzeTrends,
  summarizeByCategory,
  generateDashboardSummary,
  type CampaignMetrics,
  type ROIAnalysis,
  type PlatformPerformance,
  type TrendAnalysis,
} from './marketingAnalytics'

// 일괄 작업 관련
export {
  bulkUpdateKeywordGrades,
  bulkUpdateLeadStatus,
  bulkCategorizeKeywords,
  deduplicateKeywords,
  filterKeywords,
  filterLeads,
  createSelectionManager,
  prepareBulkExport,
  type BulkOperationResult,
  type KeywordBulkUpdate,
  type LeadBulkUpdate,
} from './bulkOperations'

// 내보내기 관련
export {
  exportToCSV,
  exportToJSON,
  KEYWORD_EXPORT_COLUMNS,
  LEAD_EXPORT_COLUMNS,
} from './export'

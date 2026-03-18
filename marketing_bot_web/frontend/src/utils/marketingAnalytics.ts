/**
 * 마케팅 분석 유틸리티
 * ROI, 전환율, 성과 지표를 계산합니다.
 */

export interface CampaignMetrics {
  totalKeywords: number
  sGradeKeywords: number
  aGradeKeywords: number
  totalLeads: number
  convertedLeads: number
  totalSearchVolume: number
  averageDifficulty: number
  averageOpportunity: number
}

export interface ROIAnalysis {
  conversionRate: number
  leadQualityScore: number
  keywordEfficiency: number
  overallScore: number
  grade: 'excellent' | 'good' | 'average' | 'needs-improvement'
  insights: string[]
  recommendations: string[]
}

export interface PlatformPerformance {
  platform: string
  leads: number
  converted: number
  conversionRate: number
  averageScore: number
  trend: 'up' | 'down' | 'stable'
}

export interface TrendAnalysis {
  period: string
  keywords: number
  leads: number
  conversions: number
  growth: number
}

/**
 * 전환율 계산
 */
export function calculateConversionRate(
  totalLeads: number,
  convertedLeads: number
): number {
  if (totalLeads === 0) return 0
  return Math.round((convertedLeads / totalLeads) * 100 * 10) / 10
}

/**
 * 키워드 효율성 점수 계산
 * S/A급 키워드 비율 기반
 */
export function calculateKeywordEfficiency(metrics: CampaignMetrics): number {
  if (metrics.totalKeywords === 0) return 0

  const saRatio = (metrics.sGradeKeywords + metrics.aGradeKeywords) / metrics.totalKeywords
  const volumeBonus = Math.min(Math.log10(metrics.totalSearchVolume + 1) * 5, 20)
  const difficultyBonus = Math.max(0, (50 - metrics.averageDifficulty) / 2)

  return Math.round(saRatio * 60 + volumeBonus + difficultyBonus)
}

/**
 * 리드 품질 점수 계산
 */
export function calculateLeadQualityScore(metrics: CampaignMetrics): number {
  if (metrics.totalLeads === 0) return 0

  const conversionRate = calculateConversionRate(
    metrics.totalLeads,
    metrics.convertedLeads
  )

  // 기본 점수: 전환율 기반
  let score = conversionRate * 2

  // 리드 수 보너스
  if (metrics.totalLeads > 100) score += 10
  if (metrics.totalLeads > 500) score += 10

  return Math.min(Math.round(score), 100)
}

/**
 * 종합 ROI 분석
 */
export function analyzeROI(metrics: CampaignMetrics): ROIAnalysis {
  const conversionRate = calculateConversionRate(
    metrics.totalLeads,
    metrics.convertedLeads
  )
  const keywordEfficiency = calculateKeywordEfficiency(metrics)
  const leadQualityScore = calculateLeadQualityScore(metrics)

  // 종합 점수 계산
  const overallScore = Math.round(
    keywordEfficiency * 0.4 +
    leadQualityScore * 0.4 +
    conversionRate * 0.2
  )

  // 등급 결정
  let grade: ROIAnalysis['grade']
  if (overallScore >= 80) grade = 'excellent'
  else if (overallScore >= 60) grade = 'good'
  else if (overallScore >= 40) grade = 'average'
  else grade = 'needs-improvement'

  // 인사이트 생성
  const insights: string[] = []

  if (metrics.sGradeKeywords > metrics.totalKeywords * 0.2) {
    insights.push(`S급 키워드가 ${Math.round(metrics.sGradeKeywords / metrics.totalKeywords * 100)}%로 높은 편입니다.`)
  }

  if (conversionRate > 5) {
    insights.push(`전환율 ${conversionRate}%는 업계 평균 대비 우수합니다.`)
  } else if (conversionRate < 2) {
    insights.push(`전환율 ${conversionRate}%는 개선이 필요합니다.`)
  }

  if (metrics.averageDifficulty < 40) {
    insights.push('키워드 난이도가 낮아 랭킹 진입이 용이합니다.')
  }

  if (metrics.averageOpportunity > 60) {
    insights.push(`평균 기회점수 ${Math.round(metrics.averageOpportunity)}점으로 성장 잠재력이 높습니다.`)
  }

  // 추천 사항 생성
  const recommendations: string[] = []

  if (metrics.sGradeKeywords < 100) {
    recommendations.push('LEGION MODE를 실행하여 더 많은 S급 키워드를 발굴하세요.')
  }

  if (conversionRate < 3) {
    recommendations.push('리드 품질 점수가 높은 리드에 먼저 연락하세요.')
    recommendations.push('리드 응답 시간을 단축하여 전환율을 높이세요.')
  }

  if (metrics.totalLeads < 50) {
    recommendations.push('리드 스캔을 더 자주 실행하여 기회를 놓치지 마세요.')
  }

  if (metrics.averageDifficulty > 60) {
    recommendations.push('난이도가 낮은 롱테일 키워드에 집중하세요.')
  }

  return {
    conversionRate,
    leadQualityScore,
    keywordEfficiency,
    overallScore,
    grade,
    insights,
    recommendations,
  }
}

/**
 * 플랫폼별 성과 분석
 */
export function analyzePlatformPerformance(
  platformData: Array<{
    platform: string
    leads: number
    converted: number
    previousLeads?: number
  }>
): PlatformPerformance[] {
  return platformData.map(data => {
    const conversionRate = calculateConversionRate(data.leads, data.converted)

    // 트렌드 결정
    let trend: 'up' | 'down' | 'stable' = 'stable'
    if (data.previousLeads !== undefined) {
      const growth = ((data.leads - data.previousLeads) / (data.previousLeads || 1)) * 100
      if (growth > 10) trend = 'up'
      else if (growth < -10) trend = 'down'
    }

    // 평균 점수 계산 (간단한 휴리스틱)
    const averageScore = Math.round(conversionRate * 10 + data.leads * 0.1)

    return {
      platform: data.platform,
      leads: data.leads,
      converted: data.converted,
      conversionRate,
      averageScore: Math.min(averageScore, 100),
      trend,
    }
  }).sort((a, b) => b.averageScore - a.averageScore)
}

/**
 * 기간별 트렌드 분석
 */
export function analyzeTrends(
  periodData: Array<{
    period: string
    keywords: number
    leads: number
    conversions: number
  }>
): TrendAnalysis[] {
  return periodData.map((data, index) => {
    let growth = 0
    if (index > 0) {
      const prev = periodData[index - 1]
      growth = Math.round(
        ((data.conversions - prev.conversions) / (prev.conversions || 1)) * 100
      )
    }

    return {
      ...data,
      growth,
    }
  })
}

/**
 * 카테고리별 성과 요약
 */
export function summarizeByCategory(
  keywords: Array<{
    category: string
    search_volume: number
    grade: string
  }>
): Array<{
  category: string
  count: number
  totalVolume: number
  sGrade: number
  aGrade: number
  effectiveness: number
}> {
  const categoryMap = new Map<string, {
    count: number
    totalVolume: number
    sGrade: number
    aGrade: number
  }>()

  keywords.forEach(kw => {
    const existing = categoryMap.get(kw.category) || {
      count: 0,
      totalVolume: 0,
      sGrade: 0,
      aGrade: 0,
    }

    existing.count++
    existing.totalVolume += kw.search_volume
    if (kw.grade === 'S') existing.sGrade++
    if (kw.grade === 'A') existing.aGrade++

    categoryMap.set(kw.category, existing)
  })

  return Array.from(categoryMap.entries())
    .map(([category, data]) => ({
      category,
      ...data,
      effectiveness: Math.round(
        ((data.sGrade + data.aGrade) / data.count) * 100
      ),
    }))
    .sort((a, b) => b.effectiveness - a.effectiveness)
}

/**
 * 성과 대시보드용 요약 데이터
 */
export function generateDashboardSummary(metrics: CampaignMetrics): {
  kpis: Array<{ label: string; value: string | number; change?: number; status: 'good' | 'warning' | 'critical' }>
  charts: {
    gradeDistribution: Array<{ name: string; value: number }>
    conversionFunnel: Array<{ stage: string; count: number }>
  }
} {
  const roi = analyzeROI(metrics)

  return {
    kpis: [
      {
        label: '총 키워드',
        value: metrics.totalKeywords.toLocaleString(),
        status: metrics.totalKeywords > 1000 ? 'good' : metrics.totalKeywords > 500 ? 'warning' : 'critical',
      },
      {
        label: 'S/A급 비율',
        value: `${Math.round((metrics.sGradeKeywords + metrics.aGradeKeywords) / metrics.totalKeywords * 100)}%`,
        status: roi.keywordEfficiency > 60 ? 'good' : roi.keywordEfficiency > 40 ? 'warning' : 'critical',
      },
      {
        label: '전환율',
        value: `${roi.conversionRate}%`,
        status: roi.conversionRate > 5 ? 'good' : roi.conversionRate > 2 ? 'warning' : 'critical',
      },
      {
        label: '종합 점수',
        value: roi.overallScore,
        status: roi.grade === 'excellent' || roi.grade === 'good' ? 'good' : roi.grade === 'average' ? 'warning' : 'critical',
      },
    ],
    charts: {
      gradeDistribution: [
        { name: 'S급', value: metrics.sGradeKeywords },
        { name: 'A급', value: metrics.aGradeKeywords },
        { name: 'B급', value: Math.round(metrics.totalKeywords * 0.3) },
        { name: 'C급', value: metrics.totalKeywords - metrics.sGradeKeywords - metrics.aGradeKeywords - Math.round(metrics.totalKeywords * 0.3) },
      ],
      conversionFunnel: [
        { stage: '총 리드', count: metrics.totalLeads },
        { stage: '연락 완료', count: Math.round(metrics.totalLeads * 0.6) },
        { stage: '관심 표명', count: Math.round(metrics.totalLeads * 0.3) },
        { stage: '전환', count: metrics.convertedLeads },
      ],
    },
  }
}

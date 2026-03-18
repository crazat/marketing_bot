import { useQuery } from '@tanstack/react-query'
import { leadsApi } from '@/services/api'

interface RoiData {
  overall_roi: {
    total_leads: number
    total_converted: number
    conversion_rate: number
    total_expected_revenue: number
    total_actual_revenue: number
    avg_revenue_per_conversion: number
    message?: string
  }
  by_platform: Array<{
    platform: string
    total_leads: number
    converted: number
    conversion_rate: number
    expected_revenue: number
    actual_revenue: number
    avg_revenue_per_lead: number
    avg_revenue_per_conversion: number
  }>
  by_keyword: Array<{
    keyword: string
    total_leads: number
    converted: number
    conversion_rate: number
    expected_revenue: number
    actual_revenue: number
    avg_revenue_per_lead: number
  }>
  insights: string[]
}

interface BottleneckData {
  stage_durations: Record<string, number | null>
  bottleneck: string | null
  max_duration_hours: number
  sample_size: number
  recommendations: string[]
  stage_labels: Record<string, string>
}

export default function RoiAnalysis() {
  const { data: roiData, isLoading: roiLoading } = useQuery<RoiData>({
    queryKey: ['roi-analysis'],
    queryFn: leadsApi.getRoiAnalysis,
    refetchInterval: 300000,
    retry: 1,
  })

  const { data: bottleneckData, isLoading: bottleneckLoading } = useQuery<BottleneckData>({
    queryKey: ['bottleneck-analysis'],
    queryFn: leadsApi.getBottleneckAnalysis,
    refetchInterval: 300000,
    retry: 1,
  })

  const platformIcons: Record<string, string> = {
    youtube: '📺',
    tiktok: '🎵',
    instagram: '📸',
    naver: '🟢',
    carrot: '🥕',
    cafe: '☕',
    other: '📱',
  }

  const formatCurrency = (value: number) => {
    if (value >= 10000) {
      return `${(value / 10000).toFixed(0)}만원`
    }
    return `${value.toLocaleString()}원`
  }

  if (roiLoading && bottleneckLoading) {
    return (
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="h-6 w-48 bg-muted rounded animate-pulse mb-4" />
        <div className="space-y-3">
          <div className="h-20 bg-muted rounded animate-pulse" />
          <div className="h-20 bg-muted rounded animate-pulse" />
        </div>
      </div>
    )
  }

  const hasRoiData = roiData && !roiData.overall_roi.message && roiData.overall_roi.total_actual_revenue > 0
  const hasBottleneckData = bottleneckData && bottleneckData.bottleneck

  if (!hasRoiData && !hasBottleneckData) {
    return (
      <div className="bg-card rounded-lg border border-border p-6">
        <h2 className="text-xl font-bold mb-4">📊 ROI 분석</h2>
        <div className="text-center py-8 text-muted-foreground">
          <p className="mb-2">아직 분석할 데이터가 충분하지 않습니다</p>
          <p className="text-sm">리드에 예상 매출/실제 매출을 입력하면 ROI 분석이 가능합니다</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-card rounded-lg border border-border p-6">
      <h2 className="text-xl font-bold mb-4">📊 마케팅 ROI 분석</h2>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ROI 요약 카드 */}
        {hasRoiData && (
          <div className="space-y-4">
            {/* 전체 ROI */}
            <div className="bg-gradient-to-br from-green-500/10 to-emerald-500/10 border border-green-500/30 rounded-lg p-4">
              <h3 className="font-semibold text-green-600 mb-3 flex items-center gap-2">
                💰 전체 매출 현황
              </h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-muted-foreground">총 매출</p>
                  <p className="text-2xl font-bold text-green-600">
                    {formatCurrency(roiData.overall_roi.total_actual_revenue)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">전환당 평균</p>
                  <p className="text-2xl font-bold">
                    {formatCurrency(roiData.overall_roi.avg_revenue_per_conversion)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">총 전환</p>
                  <p className="text-lg font-semibold">
                    {roiData.overall_roi.total_converted}건
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">전환율</p>
                  <p className="text-lg font-semibold">
                    {roiData.overall_roi.conversion_rate}%
                  </p>
                </div>
              </div>
            </div>

            {/* 플랫폼별 ROI */}
            {roiData.by_platform.length > 0 && (
              <div>
                <h4 className="text-sm font-medium mb-2">플랫폼별 성과</h4>
                <div className="space-y-2">
                  {roiData.by_platform.slice(0, 5).map((platform) => (
                    <div
                      key={platform.platform}
                      className="flex items-center justify-between p-2 bg-muted/50 rounded-lg"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{platformIcons[platform.platform] || '📱'}</span>
                        <span className="font-medium capitalize">{platform.platform}</span>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold">{formatCurrency(platform.actual_revenue)}</p>
                        <p className="text-xs text-muted-foreground">
                          {platform.converted}건 / {platform.conversion_rate}%
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 인사이트 */}
            {roiData.insights.length > 0 && (
              <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3">
                <h4 className="text-sm font-medium text-blue-600 mb-2">💡 인사이트</h4>
                <ul className="space-y-1 text-sm">
                  {roiData.insights.map((insight, idx) => (
                    <li key={idx}>{insight}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* 병목 분석 */}
        {hasBottleneckData && (
          <div className="space-y-4">
            <div className="bg-gradient-to-br from-yellow-500/10 to-orange-500/10 border border-yellow-500/30 rounded-lg p-4">
              <h3 className="font-semibold text-yellow-600 mb-3 flex items-center gap-2">
                ⏱️ 파이프라인 분석
              </h3>

              {/* 단계별 소요 시간 */}
              <div className="space-y-3">
                {Object.entries(bottleneckData.stage_durations).map(([stage, duration]) => {
                  if (duration === null) return null
                  const isBottleneck = stage === bottleneckData.bottleneck
                  const label = bottleneckData.stage_labels[stage] || stage

                  return (
                    <div key={stage}>
                      <div className="flex items-center justify-between mb-1">
                        <span className={`text-sm ${isBottleneck ? 'font-semibold text-yellow-600' : ''}`}>
                          {isBottleneck ? '⚠️ ' : ''}{label}
                        </span>
                        <span className={`text-sm ${isBottleneck ? 'font-bold text-yellow-600' : 'text-muted-foreground'}`}>
                          {duration < 1 ? `${Math.round(duration * 60)}분` : `${duration}시간`}
                        </span>
                      </div>
                      <div className="h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className={`h-full transition-all ${
                            isBottleneck ? 'bg-yellow-500' : 'bg-primary/60'
                          }`}
                          style={{
                            width: `${Math.min(100, (duration / bottleneckData.max_duration_hours) * 100)}%`
                          }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>

              <p className="text-xs text-muted-foreground mt-3">
                분석 대상: {bottleneckData.sample_size}건
              </p>
            </div>

            {/* 권장 사항 */}
            {bottleneckData.recommendations.length > 0 && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
                <h4 className="text-sm font-medium text-red-600 mb-2">🎯 개선 권장</h4>
                <ul className="space-y-1 text-sm">
                  {bottleneckData.recommendations.map((rec, idx) => (
                    <li key={idx}>• {rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

import { useQuery } from '@tanstack/react-query'
import { leadsApi } from '@/services/api'
import MetricCard from '../MetricCard'

// [Phase 4.0] 품질 통계 타입
interface QualityStatsData {
  trust_distribution: {
    trusted: number
    review: number
    suspicious: number
  }
  contact_rate: number
  total_leads: number
  quality_score: number
}

interface ConversionRateData {
  total: number
  contacted: number
  replied: number
  converted: number
  contact_rate: number
  reply_rate: number
  conversion_rate: number
}

// [Phase 4.0] 전환 추적 데이터 타입
interface ConversionTrackingData {
  overview: {
    total_conversions: number
    total_revenue: number
    avg_revenue_per_conversion: number
  }
  by_keyword: {
    keyword: string
    conversions: number
    revenue: number
    avg_revenue: number
    total_leads: number
    conversion_rate: number
  }[]
  by_platform: {
    platform: string
    conversions: number
    revenue: number
    avg_revenue: number
  }[]
}

interface LeadStats {
  total: number
  by_platform: Record<string, number>
  by_status: Record<string, number>
}

interface LeadStatsProps {
  stats: LeadStats | null
  scoreStats?: {
    by_grade?: { hot: number; warm: number; cool: number; cold: number }
    average_score?: number
    total_scored?: number
  }
  conversionRates?: {
    total: ConversionRateData
    by_platform: Record<string, ConversionRateData>
  }
  conversionTracking?: ConversionTrackingData
}

const platformIcons: Record<string, string> = {
  youtube: '📺',
  tiktok: '🎵',
  naver: '🟢',
  instagram: '📸',
  carrot: '🥕',
  influencer: '⭐',
  cafe: '☕',
  blog: '📝',
  other: '📁',
}

const platformLabels: Record<string, string> = {
  youtube: 'YouTube',
  tiktok: 'TikTok',
  naver: 'Naver',
  instagram: 'Instagram',
  carrot: '당근마켓',
  influencer: '인플루언서',
  cafe: '맘카페',
  blog: '블로그',
  other: '기타',
}

export default function LeadStats({ stats, scoreStats, conversionRates, conversionTracking }: LeadStatsProps) {
  // [P2-1] 전환 트렌드 조회
  const { data: conversionTrends } = useQuery({
    queryKey: ['leads-conversion-trends'],
    queryFn: () => leadsApi.getConversionTrends(30),
    retry: 1,
  })

  // [Phase 4.0] 품질 통계 조회
  const { data: qualityStats } = useQuery<QualityStatsData>({
    queryKey: ['leads-quality-stats'],
    queryFn: () => leadsApi.getQualityStats(),
    retry: 1,
  })

  if (!stats) return null

  // [Phase 5.0] 전환 퍼널 데이터 계산
  const funnelData = [
    { stage: '발견', value: stats.total || 0, color: 'bg-blue-500', icon: '🔍' },
    { stage: '연락', value: stats.by_status?.contacted || 0, color: 'bg-purple-500', icon: '📞' },
    { stage: '응답', value: stats.by_status?.replied || 0, color: 'bg-yellow-500', icon: '💬' },
    { stage: '전환', value: stats.by_status?.converted || 0, color: 'bg-green-500', icon: '✅' },
  ]

  const maxValue = funnelData[0].value || 1

  return (
    <div className="space-y-4">
      {/* [Phase 5.0] 전환 퍼널 차트 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">📊 전환 퍼널</h3>
        <div className="space-y-3">
          {funnelData.map((item, index) => {
            const percentage = maxValue > 0 ? (item.value / maxValue) * 100 : 0
            const conversionRate = index > 0 && funnelData[index - 1].value > 0
              ? ((item.value / funnelData[index - 1].value) * 100).toFixed(1)
              : null

            return (
              <div key={item.stage} className="flex items-center gap-4">
                <div className="w-20 flex items-center gap-2">
                  <span aria-hidden="true">{item.icon}</span>
                  <span className="text-sm font-medium">{item.stage}</span>
                </div>
                <div className="flex-1 h-8 bg-muted rounded-lg overflow-hidden relative">
                  <div
                    className={`h-full ${item.color} transition-all duration-500`}
                    style={{ width: `${Math.max(percentage, 2)}%` }}
                  />
                  <div className="absolute inset-0 flex items-center px-3">
                    <span className="text-sm font-bold text-foreground">
                      {item.value.toLocaleString()}
                    </span>
                  </div>
                </div>
                <div className="w-16 text-right">
                  {conversionRate !== null ? (
                    <span className="text-xs text-muted-foreground">
                      {conversionRate}%
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">-</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
        {/* 전체 전환율 */}
        {funnelData[0].value > 0 && (
          <div className="mt-4 pt-4 border-t border-border">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">전체 전환율</span>
              <span className="font-bold text-green-500">
                {((funnelData[3].value / funnelData[0].value) * 100).toFixed(1)}%
              </span>
            </div>
          </div>
        )}
      </div>

      {/* [Phase 4.0] 리드 품질 통계 */}
      {qualityStats && qualityStats.total_leads > 0 && (
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-semibold mb-4">🎯 리드 품질 분석</h3>

          {/* 품질 점수 메인 */}
          <div className="flex items-center justify-center mb-6">
            <div className="relative">
              <div className={`w-24 h-24 rounded-full flex items-center justify-center text-3xl font-bold border-4 ${
                qualityStats.quality_score >= 70 ? 'border-green-500 text-green-500' :
                qualityStats.quality_score >= 50 ? 'border-yellow-500 text-yellow-500' :
                'border-red-500 text-red-500'
              }`}>
                {qualityStats.quality_score}
              </div>
              <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 bg-card px-2 text-xs text-muted-foreground">
                품질점수
              </div>
            </div>
          </div>

          {/* 신뢰도 분포 */}
          <div className="mb-4">
            <h4 className="text-sm font-medium mb-3 text-muted-foreground">신뢰도 분포</h4>
            <div className="space-y-2">
              {/* 신뢰 */}
              <div className="flex items-center gap-3">
                <div className="w-16 flex items-center gap-1.5 text-sm">
                  <span className="text-blue-500">🛡️</span>
                  <span>신뢰</span>
                </div>
                <div className="flex-1 h-6 bg-muted rounded-md overflow-hidden relative">
                  <div
                    className="h-full bg-blue-500 transition-all"
                    style={{
                      width: `${qualityStats.total_leads > 0
                        ? (qualityStats.trust_distribution.trusted / qualityStats.total_leads) * 100
                        : 0}%`
                    }}
                  />
                  <span className="absolute inset-0 flex items-center px-2 text-xs font-medium">
                    {qualityStats.trust_distribution.trusted}개
                  </span>
                </div>
                <div className="w-12 text-right text-xs text-muted-foreground">
                  {qualityStats.total_leads > 0
                    ? ((qualityStats.trust_distribution.trusted / qualityStats.total_leads) * 100).toFixed(0)
                    : 0}%
                </div>
              </div>

              {/* 확인 필요 */}
              <div className="flex items-center gap-3">
                <div className="w-16 flex items-center gap-1.5 text-sm">
                  <span className="text-amber-500">⚠️</span>
                  <span>확인</span>
                </div>
                <div className="flex-1 h-6 bg-muted rounded-md overflow-hidden relative">
                  <div
                    className="h-full bg-amber-500 transition-all"
                    style={{
                      width: `${qualityStats.total_leads > 0
                        ? (qualityStats.trust_distribution.review / qualityStats.total_leads) * 100
                        : 0}%`
                    }}
                  />
                  <span className="absolute inset-0 flex items-center px-2 text-xs font-medium">
                    {qualityStats.trust_distribution.review}개
                  </span>
                </div>
                <div className="w-12 text-right text-xs text-muted-foreground">
                  {qualityStats.total_leads > 0
                    ? ((qualityStats.trust_distribution.review / qualityStats.total_leads) * 100).toFixed(0)
                    : 0}%
                </div>
              </div>

              {/* 의심 */}
              <div className="flex items-center gap-3">
                <div className="w-16 flex items-center gap-1.5 text-sm">
                  <span className="text-red-500">🚫</span>
                  <span>의심</span>
                </div>
                <div className="flex-1 h-6 bg-muted rounded-md overflow-hidden relative">
                  <div
                    className="h-full bg-red-500 transition-all"
                    style={{
                      width: `${qualityStats.total_leads > 0
                        ? (qualityStats.trust_distribution.suspicious / qualityStats.total_leads) * 100
                        : 0}%`
                    }}
                  />
                  <span className="absolute inset-0 flex items-center px-2 text-xs font-medium">
                    {qualityStats.trust_distribution.suspicious}개
                  </span>
                </div>
                <div className="w-12 text-right text-xs text-muted-foreground">
                  {qualityStats.total_leads > 0
                    ? ((qualityStats.trust_distribution.suspicious / qualityStats.total_leads) * 100).toFixed(0)
                    : 0}%
                </div>
              </div>
            </div>
          </div>

          {/* 연락처 보유율 */}
          <div className="pt-4 border-t border-border">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-purple-500">📞</span>
                <span className="text-sm font-medium">연락처 보유율</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-24 h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-purple-500 transition-all"
                    style={{ width: `${qualityStats.contact_rate}%` }}
                  />
                </div>
                <span className={`text-sm font-bold ${
                  qualityStats.contact_rate >= 30 ? 'text-green-500' :
                  qualityStats.contact_rate >= 15 ? 'text-yellow-500' :
                  'text-gray-500'
                }`}>
                  {qualityStats.contact_rate.toFixed(1)}%
                </span>
              </div>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              전체 {qualityStats.total_leads}개 리드 중 연락처 정보 보유
            </p>
          </div>
        </div>
      )}

      {/* [P2-1] 전환 트렌드 차트 */}
      {conversionTrends && conversionTrends.daily_trends?.length > 0 && (
        <div className="bg-card rounded-lg border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">📈 전환 트렌드 (최근 14일)</h3>
            <div className="text-sm text-muted-foreground">
              기간 전환율: <span className="font-bold text-green-500">{conversionTrends.summary?.overall_conversion_rate || 0}%</span>
            </div>
          </div>

          {/* 일별 바 차트 */}
          <div className="space-y-2">
            {conversionTrends.daily_trends.slice(0, 14).reverse().map((day: any) => {
              const maxLeads = Math.max(...conversionTrends.daily_trends.map((d: any) => d.total_leads || 1))
              const barWidth = (day.total_leads / maxLeads) * 100

              return (
                <div key={day.date} className="flex items-center gap-3">
                  <div className="w-16 text-xs text-muted-foreground">
                    {new Date(day.date).toLocaleDateString('ko-KR', { month: 'numeric', day: 'numeric' })}
                  </div>
                  <div className="flex-1 h-6 bg-muted rounded-md overflow-hidden relative">
                    {/* 전체 리드 바 */}
                    <div
                      className="absolute inset-y-0 left-0 bg-blue-500/30 transition-all"
                      style={{ width: `${barWidth}%` }}
                    />
                    {/* 전환된 리드 바 (오버레이) */}
                    <div
                      className="absolute inset-y-0 left-0 bg-green-500 transition-all"
                      style={{ width: `${day.total_leads > 0 ? (day.converted / day.total_leads) * barWidth : 0}%` }}
                    />
                    <div className="absolute inset-0 flex items-center px-2">
                      <span className="text-xs font-medium">
                        {day.converted > 0 && <span className="text-green-600">{day.converted}건 전환</span>}
                      </span>
                    </div>
                  </div>
                  <div className="w-12 text-right text-xs">
                    <span className="text-muted-foreground">{day.total_leads}</span>
                  </div>
                </div>
              )
            })}
          </div>

          {/* 범례 */}
          <div className="flex items-center gap-4 mt-4 pt-4 border-t border-border text-xs text-muted-foreground">
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-blue-500/30 rounded" />
              <span>전체 리드</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-green-500 rounded" />
              <span>전환 완료</span>
            </div>
          </div>

          {/* 주별 요약 */}
          {conversionTrends.weekly_trends?.length > 0 && (
            <div className="mt-4 pt-4 border-t border-border">
              <p className="text-sm font-medium mb-3">주별 요약</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {conversionTrends.weekly_trends.slice(0, 4).map((week: any) => (
                  <div key={week.week} className="bg-muted/50 rounded-lg p-3 text-center">
                    <div className="text-xs text-muted-foreground mb-1">{week.week}</div>
                    <div className="text-lg font-bold">{week.converted}</div>
                    <div className="text-xs text-green-500">{week.conversion_rate}%</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* [Phase 4.0] ROI 기반 전환 추적 */}
      {conversionTracking?.overview && conversionTracking.overview.total_conversions > 0 && (
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-semibold mb-4">💰 ROI 기반 전환 분석</h3>

          {/* 전체 요약 */}
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="bg-green-500/10 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-green-500">
                {conversionTracking.overview.total_conversions}
              </div>
              <div className="text-xs text-muted-foreground">총 전환</div>
            </div>
            <div className="bg-blue-500/10 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-blue-500">
                ₩{conversionTracking.overview.total_revenue.toLocaleString()}
              </div>
              <div className="text-xs text-muted-foreground">총 매출</div>
            </div>
            <div className="bg-purple-500/10 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-purple-500">
                ₩{conversionTracking.overview.avg_revenue_per_conversion.toLocaleString()}
              </div>
              <div className="text-xs text-muted-foreground">전환당 평균</div>
            </div>
          </div>

          {/* 키워드별 ROI (상위 5개) */}
          {conversionTracking.by_keyword.length > 0 && (
            <div className="mb-4">
              <h4 className="text-sm font-semibold mb-3 text-muted-foreground">
                키워드별 ROI (Top 5)
              </h4>
              <div className="space-y-2">
                {conversionTracking.by_keyword.slice(0, 5).map((kw) => (
                  <div
                    key={kw.keyword}
                    className="flex items-center justify-between p-3 bg-muted/50 rounded-lg"
                  >
                    <div className="flex-1">
                      <div className="font-medium text-sm">{kw.keyword}</div>
                      <div className="text-xs text-muted-foreground">
                        리드 {kw.total_leads}개 → 전환 {kw.conversions}개 ({kw.conversion_rate}%)
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-bold text-green-500">
                        ₩{kw.revenue.toLocaleString()}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        평균 ₩{kw.avg_revenue.toLocaleString()}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 플랫폼별 매출 */}
          {conversionTracking.by_platform.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold mb-3 text-muted-foreground">
                플랫폼별 매출
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {conversionTracking.by_platform.map((p) => (
                  <div key={p.platform} className="bg-muted/50 rounded-lg p-3 text-center">
                    <div className="text-xl mb-1">{platformIcons[p.platform] || '📁'}</div>
                    <div className="font-bold text-sm">₩{p.revenue.toLocaleString()}</div>
                    <div className="text-xs text-muted-foreground">
                      {platformLabels[p.platform] || p.platform} ({p.conversions}건)
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* [Phase 1.3] 점수 분포 */}
      {scoreStats && (
        <div>
          <h3 className="text-sm font-semibold mb-3 text-muted-foreground">
            리드 점수 분포 (평균: {scoreStats.average_score || 0}점)
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard
              title="Hot Lead"
              value={scoreStats.by_grade?.hot || 0}
              icon="🔴"
              color="text-red-500"
              subtitle="즉시 연락"
            />
            <MetricCard
              title="Warm Lead"
              value={scoreStats.by_grade?.warm || 0}
              icon="🟡"
              color="text-yellow-500"
              subtitle="1일 내"
            />
            <MetricCard
              title="Cool Lead"
              value={scoreStats.by_grade?.cool || 0}
              icon="🟢"
              color="text-green-500"
              subtitle="주간 리뷰"
            />
            <MetricCard
              title="Cold Lead"
              value={scoreStats.by_grade?.cold || 0}
              icon="⚪"
              color="text-gray-500"
              subtitle="자동 보관"
            />
          </div>
        </div>
      )}

      {/* 플랫폼별 통계 */}
      <div>
        <h3 className="text-sm font-semibold mb-3 text-muted-foreground">플랫폼별</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricCard
            title="전체"
            value={stats.total || 0}
            icon="📊"
          />
          <MetricCard
            title="YouTube"
            value={stats.by_platform?.youtube || 0}
            icon="📺"
            color="text-red-500"
          />
          <MetricCard
            title="TikTok"
            value={stats.by_platform?.tiktok || 0}
            icon="🎵"
            color="text-pink-500"
          />
          <MetricCard
            title="Naver"
            value={stats.by_platform?.naver || 0}
            icon="🟢"
            color="text-green-500"
          />
        </div>
      </div>

      {/* 상태별 통계 */}
      <div>
        <h3 className="text-sm font-semibold mb-3 text-muted-foreground">상태별</h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <MetricCard
            title="대기"
            value={stats.by_status?.pending || 0}
            icon="⏳"
            color="text-yellow-500"
          />
          <MetricCard
            title="연락함"
            value={stats.by_status?.contacted || 0}
            icon="📞"
            color="text-blue-500"
          />
          <MetricCard
            title="답변받음"
            value={stats.by_status?.replied || 0}
            icon="💬"
            color="text-purple-500"
          />
          <MetricCard
            title="전환완료"
            value={stats.by_status?.converted || 0}
            icon="✅"
            color="text-green-500"
          />
          <MetricCard
            title="거절됨"
            value={stats.by_status?.rejected || 0}
            icon="❌"
            color="text-red-500"
          />
        </div>
      </div>

      {/* 플랫폼별 전환율 대시보드 */}
      {conversionRates && Object.keys(conversionRates.by_platform).length > 0 && (
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-semibold mb-4">📈 플랫폼별 전환율</h3>

          {/* 모바일: 카드형 레이아웃 */}
          <div className="md:hidden space-y-3">
            {Object.entries(conversionRates.by_platform)
              .sort(([, a], [, b]) => b.conversion_rate - a.conversion_rate)
              .map(([platform, data]) => (
                <div key={platform} className="bg-muted/50 rounded-lg p-4">
                  <div className="flex justify-between items-center mb-3">
                    <div className="flex items-center gap-2">
                      <span className="text-xl">{platformIcons[platform] || '📁'}</span>
                      <span className="font-medium">{platformLabels[platform] || platform}</span>
                    </div>
                    <span className={`text-lg font-bold ${
                      data.conversion_rate >= 10 ? 'text-green-500' :
                      data.conversion_rate >= 5 ? 'text-yellow-500' :
                      'text-gray-500'
                    }`}>
                      {data.conversion_rate}%
                    </span>
                  </div>
                  <div className="h-2 bg-muted rounded-full overflow-hidden mb-3">
                    <div
                      className={`h-full transition-all ${
                        data.conversion_rate >= 10 ? 'bg-green-500' :
                        data.conversion_rate >= 5 ? 'bg-yellow-500' :
                        'bg-gray-400'
                      }`}
                      style={{ width: `${Math.min(data.conversion_rate * 5, 100)}%` }}
                    />
                  </div>
                  <div className="grid grid-cols-4 gap-2 text-xs text-center">
                    <div>
                      <div className="text-muted-foreground">리드</div>
                      <div className="font-medium">{data.total}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">연락</div>
                      <div className="font-medium">{data.contact_rate}%</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">응답</div>
                      <div className="font-medium">{data.reply_rate}%</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">전환</div>
                      <div className="font-bold text-green-500">{data.converted}</div>
                    </div>
                  </div>
                </div>
              ))}
            {/* 모바일 합계 */}
            <div className="bg-primary/10 border border-primary/20 rounded-lg p-4">
              <div className="flex justify-between items-center mb-2">
                <span className="font-semibold">전체 합계</span>
                <span className="text-lg font-bold text-green-500">
                  {conversionRates.total.conversion_rate}%
                </span>
              </div>
              <div className="grid grid-cols-4 gap-2 text-xs text-center">
                <div>
                  <div className="text-muted-foreground">리드</div>
                  <div className="font-medium">{conversionRates.total.total}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">연락</div>
                  <div className="font-medium">{conversionRates.total.contact_rate}%</div>
                </div>
                <div>
                  <div className="text-muted-foreground">응답</div>
                  <div className="font-medium">{conversionRates.total.reply_rate}%</div>
                </div>
                <div>
                  <div className="text-muted-foreground">전환</div>
                  <div className="font-bold text-green-500">{conversionRates.total.converted}</div>
                </div>
              </div>
            </div>
          </div>

          {/* 데스크톱: 테이블 레이아웃 */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-4 py-3 text-left text-sm font-semibold">플랫폼</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">총 리드</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">연락률</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">응답률</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">전환율</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">전환 수</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(conversionRates.by_platform)
                  .sort(([, a], [, b]) => b.conversion_rate - a.conversion_rate)
                  .map(([platform, data]) => (
                    <tr key={platform} className="border-b border-border hover:bg-muted/50">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span>{platformIcons[platform] || '📁'}</span>
                          <span className="font-medium">{platformLabels[platform] || platform}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-center font-medium">
                        {data.total.toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${
                          data.contact_rate >= 50 ? 'bg-green-500/20 text-green-500' :
                          data.contact_rate >= 25 ? 'bg-yellow-500/20 text-yellow-500' :
                          'bg-gray-500/20 text-gray-500'
                        }`}>
                          {data.contact_rate}%
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${
                          data.reply_rate >= 50 ? 'bg-green-500/20 text-green-500' :
                          data.reply_rate >= 25 ? 'bg-yellow-500/20 text-yellow-500' :
                          'bg-gray-500/20 text-gray-500'
                        }`}>
                          {data.reply_rate}%
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`px-2 py-1 rounded text-xs font-bold ${
                          data.conversion_rate >= 10 ? 'bg-green-500/20 text-green-500' :
                          data.conversion_rate >= 5 ? 'bg-yellow-500/20 text-yellow-500' :
                          'bg-gray-500/20 text-gray-500'
                        }`}>
                          {data.conversion_rate}%
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center font-bold text-green-500">
                        {data.converted}
                      </td>
                    </tr>
                  ))}
                {/* 합계 행 */}
                <tr className="bg-muted/50 font-semibold">
                  <td className="px-4 py-3">합계</td>
                  <td className="px-4 py-3 text-center">
                    {conversionRates.total.total.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="px-2 py-1 rounded text-xs font-medium bg-blue-500/20 text-blue-500">
                      {conversionRates.total.contact_rate}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="px-2 py-1 rounded text-xs font-medium bg-purple-500/20 text-purple-500">
                      {conversionRates.total.reply_rate}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="px-2 py-1 rounded text-xs font-bold bg-green-500/20 text-green-500">
                      {conversionRates.total.conversion_rate}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center font-bold text-green-500">
                    {conversionRates.total.converted}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

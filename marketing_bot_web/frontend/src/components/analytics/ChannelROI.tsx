/**
 * [Phase L-1] 채널별 ROI 대시보드 컴포넌트
 * 플랫폼별/키워드별 투입 대비 수익 분석
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart3,
  TrendingUp,
  DollarSign,
  Target,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { analyticsApi } from '@/services/api'
import { LoadingState, ErrorState, SummaryCard, getPlatformLabel } from './shared'
import type { ChannelROIData, PlatformROI, KeywordROI } from '@/types/analytics'

interface ChannelROIProps {
  defaultDays?: number
}

export default function ChannelROI({ defaultDays = 30 }: ChannelROIProps) {
  const [days, setDays] = useState(defaultDays)
  const [showAllKeywords, setShowAllKeywords] = useState(false)

  const { data, isLoading, isError, refetch, isRefetching } = useQuery<ChannelROIData>({
    queryKey: ['channel-roi', days],
    queryFn: () => analyticsApi.getChannelROI(days),
    staleTime: 300000,
  })

  if (isLoading) {
    return <LoadingState message="ROI 데이터 로딩 중..." />
  }

  if (isError || !data) {
    return (
      <ErrorState
        message="ROI 데이터를 불러오는데 실패했습니다"
        onRetry={() => refetch()}
        isRetrying={isRefetching}
      />
    )
  }

  const { overview, by_platform, by_keyword, insights } = data

  return (
    <div className="bg-card rounded-lg border border-border">
      {/* 헤더 */}
      <div className="p-6 border-b border-border">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-primary" />
            채널별 ROI 분석
          </h2>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="px-3 py-1.5 bg-muted border border-border rounded-lg text-sm"
            aria-label="분석 기간 선택"
          >
            <option value={7}>최근 7일</option>
            <option value={30}>최근 30일</option>
            <option value={90}>최근 90일</option>
          </select>
        </div>
      </div>

      {/* 전체 요약 */}
      <div className="p-6 border-b border-border">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <SummaryCard
            label="바이럴"
            value={overview.total_virals}
            icon={<Target className="w-4 h-4" />}
          />
          <SummaryCard
            label="리드"
            value={overview.total_leads}
            icon={<TrendingUp className="w-4 h-4" />}
          />
          <SummaryCard
            label="전환"
            value={overview.total_conversions}
            icon={<Target className="w-4 h-4" />}
          />
          <SummaryCard
            label="매출"
            value={`${(overview.total_revenue / 10000).toFixed(0)}만`}
            icon={<DollarSign className="w-4 h-4" />}
          />
          <SummaryCard
            label="전환율"
            value={`${overview.overall_conversion_rate}%`}
            highlight
          />
        </div>
      </div>

      {/* 플랫폼별 ROI */}
      <div className="p-6 border-b border-border">
        <h3 className="text-sm font-semibold text-muted-foreground mb-4">플랫폼별 성과</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 px-3">플랫폼</th>
                <th className="text-right py-2 px-3">바이럴</th>
                <th className="text-right py-2 px-3">리드</th>
                <th className="text-right py-2 px-3">전환</th>
                <th className="text-right py-2 px-3">전환율</th>
                <th className="text-right py-2 px-3">매출</th>
                <th className="text-right py-2 px-3">리드당 매출</th>
              </tr>
            </thead>
            <tbody>
              {by_platform.map((p: PlatformROI) => (
                <tr key={p.platform} className="border-b border-border/50 hover:bg-muted/30">
                  <td className="py-2 px-3 font-medium">{getPlatformLabel(p.platform)}</td>
                  <td className="text-right py-2 px-3">{p.viral_count}</td>
                  <td className="text-right py-2 px-3">{p.lead_count}</td>
                  <td className="text-right py-2 px-3">{p.converted}</td>
                  <td className="text-right py-2 px-3">
                    <span className={p.conversion_rate >= 10 ? 'text-green-500 font-medium' : ''}>
                      {p.conversion_rate}%
                    </span>
                  </td>
                  <td className="text-right py-2 px-3">{(p.revenue / 10000).toFixed(0)}만</td>
                  <td className="text-right py-2 px-3 text-muted-foreground">
                    {p.revenue_per_lead.toLocaleString()}원
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 키워드별 ROI */}
      <div className="p-6 border-b border-border">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-muted-foreground">키워드별 성과</h3>
          {by_keyword.length > 5 && (
            <button
              onClick={() => setShowAllKeywords(!showAllKeywords)}
              className="text-xs text-primary hover:underline flex items-center gap-1"
              aria-expanded={showAllKeywords}
              aria-label={showAllKeywords ? '키워드 목록 접기' : '전체 키워드 보기'}
            >
              {showAllKeywords ? '접기' : `전체 보기 (${by_keyword.length})`}
              {showAllKeywords ? <ChevronUp className="w-3 h-3" aria-hidden="true" /> : <ChevronDown className="w-3 h-3" aria-hidden="true" />}
            </button>
          )}
        </div>
        <div className="space-y-2">
          {(showAllKeywords ? by_keyword : by_keyword.slice(0, 5)).map((k: KeywordROI, idx: number) => (
            <div
              key={k.keyword}
              className="flex items-center gap-3 p-3 bg-muted/30 rounded-lg"
            >
              <span className="w-6 h-6 rounded-full bg-primary/10 text-primary text-xs flex items-center justify-center font-medium">
                {idx + 1}
              </span>
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{k.keyword}</div>
                <div className="text-xs text-muted-foreground">
                  바이럴 {k.viral_count} → 리드 {k.lead_count} → 전환 {k.conversions}
                </div>
              </div>
              <div className="text-right">
                <div className="font-bold">{(k.revenue / 10000).toFixed(0)}만원</div>
                <div className="text-xs text-muted-foreground">
                  전환율 {k.conversion_rate}%
                </div>
              </div>
              {/* ROI 바 */}
              <div className="w-20 h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    k.conversion_rate >= 15 ? 'bg-green-500' :
                    k.conversion_rate >= 10 ? 'bg-blue-500' :
                    k.conversion_rate >= 5 ? 'bg-yellow-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${Math.min(k.conversion_rate * 5, 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 인사이트 */}
      {insights.length > 0 && (
        <div className="p-6">
          <h3 className="text-sm font-semibold text-muted-foreground mb-3">인사이트</h3>
          <div className="space-y-2">
            {insights.map((insight: string, idx: number) => (
              <div key={idx} className="text-sm bg-primary/5 border border-primary/20 rounded p-3">
                {insight}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

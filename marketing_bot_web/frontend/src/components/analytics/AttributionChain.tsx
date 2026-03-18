/**
 * [Phase G-1] 전환 어트리뷰션 체인 컴포넌트
 * 키워드 → 바이럴 → 리드 → 전환 경로 시각화
 */

import React from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Link2,
  ChevronRight,
  Search,
  FileText,
  Users,
  CheckCircle,
} from 'lucide-react'
import { analyticsApi } from '@/services/api'
import { LoadingState, ErrorState, getPlatformLabel } from './shared'
import type { AttributionChainData, TopPath, KeywordAttribution } from '@/types/analytics'

interface AttributionChainProps {
  compact?: boolean
  days?: number
}

export default function AttributionChain({ compact = false, days = 30 }: AttributionChainProps) {
  const { data, isLoading, isError, refetch, isRefetching } = useQuery<AttributionChainData>({
    queryKey: ['attribution-chain', days],
    queryFn: () => analyticsApi.getAttributionChain(days),
    staleTime: 300000,
  })

  if (isLoading) {
    return <LoadingState message="어트리뷰션 데이터 로딩 중..." />
  }

  if (isError || !data) {
    return (
      <ErrorState
        message="어트리뷰션 데이터를 불러오는데 실패했습니다"
        onRetry={() => refetch()}
        isRetrying={isRefetching}
      />
    )
  }

  const { summary, top_paths, keyword_attribution, insights } = data

  // 컴팩트 모드
  if (compact) {
    return (
      <div className="bg-card rounded-lg border border-border p-4">
        <h3 className="font-semibold flex items-center gap-2 mb-3">
          <Link2 className="w-4 h-4 text-primary" />
          전환 경로
        </h3>

        {/* 퍼널 요약 */}
        <div className="flex items-center justify-between text-sm mb-3">
          <div className="flex items-center gap-1">
            <Search className="w-3 h-3 text-muted-foreground" />
            <span>{summary.total_keywords}</span>
          </div>
          <ChevronRight className="w-3 h-3 text-muted-foreground" />
          <div className="flex items-center gap-1">
            <FileText className="w-3 h-3 text-muted-foreground" />
            <span>{summary.total_virals}</span>
          </div>
          <ChevronRight className="w-3 h-3 text-muted-foreground" />
          <div className="flex items-center gap-1">
            <Users className="w-3 h-3 text-muted-foreground" />
            <span>{summary.total_leads}</span>
          </div>
          <ChevronRight className="w-3 h-3 text-muted-foreground" />
          <div className="flex items-center gap-1">
            <CheckCircle className="w-3 h-3 text-green-500" />
            <span className="text-green-500 font-medium">{summary.total_conversions}</span>
          </div>
        </div>

        {/* 상위 경로 */}
        <div className="space-y-1">
          {top_paths.slice(0, 2).map((path: TopPath, idx: number) => (
            <div key={idx} className="text-xs bg-muted/50 rounded p-2 truncate">
              {path.keyword} → {path.platform} → 전환 {path.conversions}건
            </div>
          ))}
        </div>
      </div>
    )
  }

  // 전체 모드
  return (
    <div className="bg-card rounded-lg border border-border">
      {/* 헤더 */}
      <div className="p-6 border-b border-border">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <Link2 className="w-5 h-5 text-primary" />
          전환 어트리뷰션 체인
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          키워드에서 전환까지의 경로를 추적합니다
        </p>
      </div>

      {/* 전체 퍼널 */}
      <div className="p-6 border-b border-border">
        <h3 className="text-sm font-semibold text-muted-foreground mb-4">전환 퍼널</h3>
        <div className="flex items-center justify-between">
          <FunnelStep
            icon={<Search className="w-5 h-5" />}
            label="키워드"
            value={summary.total_keywords}
            color="text-blue-500"
          />
          <FunnelArrow rate={summary.total_virals > 0 ? (summary.total_virals / summary.total_keywords * 100).toFixed(0) : '0'} />
          <FunnelStep
            icon={<FileText className="w-5 h-5" />}
            label="바이럴"
            value={summary.total_virals}
            color="text-purple-500"
          />
          <FunnelArrow rate={summary.total_leads > 0 ? (summary.total_leads / summary.total_virals * 100).toFixed(0) : '0'} />
          <FunnelStep
            icon={<Users className="w-5 h-5" />}
            label="리드"
            value={summary.total_leads}
            color="text-orange-500"
          />
          <FunnelArrow rate={summary.conversion_rate.toFixed(1)} />
          <FunnelStep
            icon={<CheckCircle className="w-5 h-5" />}
            label="전환"
            value={summary.total_conversions}
            color="text-green-500"
            highlight
          />
        </div>
        <div className="mt-4 text-center">
          <span className="text-sm text-muted-foreground">총 매출: </span>
          <span className="text-lg font-bold text-primary">
            {(summary.total_revenue / 10000).toFixed(0)}만원
          </span>
        </div>
      </div>

      {/* 상위 전환 경로 */}
      <div className="p-6 border-b border-border">
        <h3 className="text-sm font-semibold text-muted-foreground mb-4">상위 전환 경로</h3>
        <div className="space-y-3">
          {top_paths.map((path: TopPath, idx: number) => (
            <div
              key={idx}
              className="flex items-center gap-3 p-3 bg-muted/30 rounded-lg"
            >
              <span className="w-6 h-6 rounded-full bg-primary/10 text-primary text-xs flex items-center justify-center font-medium">
                {idx + 1}
              </span>
              <div className="flex-1 flex items-center gap-2 text-sm overflow-hidden">
                <span className="font-medium truncate max-w-[120px]">{path.keyword}</span>
                <ChevronRight className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                <span className="text-muted-foreground">{getPlatformLabel(path.platform)}</span>
                <ChevronRight className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                <span className="text-green-500 font-medium">전환 {path.conversions}건</span>
              </div>
              <div className="text-right flex-shrink-0">
                <div className="font-bold">{(path.revenue / 10000).toFixed(0)}만</div>
                <div className="text-xs text-muted-foreground">
                  평균 {path.avg_days_to_conversion.toFixed(1)}일
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 키워드별 어트리뷰션 */}
      <div className="p-6 border-b border-border">
        <h3 className="text-sm font-semibold text-muted-foreground mb-4">키워드별 기여도</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 px-3">키워드</th>
                <th className="text-right py-2 px-3">바이럴</th>
                <th className="text-right py-2 px-3">리드</th>
                <th className="text-right py-2 px-3">전환</th>
                <th className="text-right py-2 px-3">전환율</th>
                <th className="text-right py-2 px-3">매출</th>
              </tr>
            </thead>
            <tbody>
              {keyword_attribution.slice(0, 10).map((kw: KeywordAttribution) => (
                <tr key={kw.keyword} className="border-b border-border/50 hover:bg-muted/30">
                  <td className="py-2 px-3 font-medium truncate max-w-[150px]">{kw.keyword}</td>
                  <td className="text-right py-2 px-3">{kw.viral_count}</td>
                  <td className="text-right py-2 px-3">{kw.lead_count}</td>
                  <td className="text-right py-2 px-3">{kw.conversions}</td>
                  <td className="text-right py-2 px-3">
                    <span className={kw.conversion_rate >= 10 ? 'text-green-500 font-medium' : ''}>
                      {kw.conversion_rate}%
                    </span>
                  </td>
                  <td className="text-right py-2 px-3 font-medium">
                    {(kw.revenue / 10000).toFixed(0)}만
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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

const FunnelStep = React.memo(function FunnelStep({
  icon,
  label,
  value,
  color,
  highlight,
}: {
  icon: React.ReactNode
  label: string
  value: number
  color: string
  highlight?: boolean
}) {
  return (
    <div className={`text-center ${highlight ? 'scale-110' : ''}`}>
      <div className={`w-12 h-12 mx-auto rounded-full flex items-center justify-center ${
        highlight ? 'bg-green-500/20' : 'bg-muted'
      } ${color}`}>
        {icon}
      </div>
      <div className="mt-2 text-xs text-muted-foreground">{label}</div>
      <div className={`text-lg font-bold ${highlight ? 'text-green-500' : ''}`}>{value}</div>
    </div>
  )
})

const FunnelArrow = React.memo(function FunnelArrow({ rate }: { rate: string }) {
  return (
    <div className="flex flex-col items-center">
      <ChevronRight className="w-6 h-6 text-muted-foreground" aria-hidden="true" />
      <span className="text-xs text-muted-foreground">{rate}%</span>
    </div>
  )
})

/**
 * 경쟁사 바이럴 레이더 컴포넌트
 */

import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { marketingApi } from '@/services/api'
import { Radar, Target, TrendingDown, AlertTriangle, Swords, RefreshCw, ArrowRight } from 'lucide-react'
import Button, { IconButton } from '@/components/ui/Button'
import type { CompetitorRadarStats } from '@/types/marketing'

interface CompetitorRadarProps {
  days?: number
  compact?: boolean
}

export function CompetitorRadar({ days = 30, compact = false }: CompetitorRadarProps) {
  const { data, isLoading, error, refetch, isRefetching } = useQuery<CompetitorRadarStats>({
    queryKey: ['competitor-radar', days],
    queryFn: () => marketingApi.getCompetitorRadarStats(days),
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 animate-pulse">
        <div className="h-6 bg-muted rounded w-1/3 mb-4" />
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-20 bg-muted rounded" />
          ))}
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 text-center">
        <p className="text-muted-foreground">경쟁사 레이더 데이터를 불러올 수 없습니다.</p>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => refetch()}
          className="mt-2"
        >
          다시 시도
        </Button>
      </div>
    )
  }

  const { competitors, opportunities, summary } = data

  // 컴팩트 모드
  if (compact) {
    return (
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Radar className="w-5 h-5 text-red-500" />
          경쟁사 레이더
        </h3>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="text-center p-3 bg-muted/50 rounded-lg">
            <div className="text-2xl font-bold">{summary.total_mentions}</div>
            <div className="text-xs text-muted-foreground">총 언급</div>
          </div>
          <div className="text-center p-3 bg-red-500/10 rounded-lg">
            <div className="text-2xl font-bold text-red-500">{summary.pending_opportunities}</div>
            <div className="text-xs text-muted-foreground">역공략 기회</div>
          </div>
        </div>

        {opportunities.length > 0 && (
          <div className="p-2 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-xs">
            <Swords className="w-3 h-3 inline mr-1 text-yellow-500" />
            {opportunities[0].competitor_name}에 대한 역공략 기회 발견
          </div>
        )}
      </div>
    )
  }

  // 전체 모드
  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <Radar className="w-6 h-6 text-red-500" />
          경쟁사 바이럴 레이더
        </h2>
        <div className="flex items-center gap-4">
          <span className="text-sm text-muted-foreground">최근 {days}일</span>
          <IconButton
            icon={<RefreshCw className={`w-4 h-4 ${isRefetching ? 'animate-spin' : ''}`} />}
            onClick={() => refetch()}
            disabled={isRefetching}
            title="새로고침"
          />
        </div>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <Target className="w-8 h-8 mx-auto mb-2 text-blue-500" />
          <div className="text-3xl font-bold">{summary.total_competitors}</div>
          <div className="text-sm text-muted-foreground">모니터링 경쟁사</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <Radar className="w-8 h-8 mx-auto mb-2 text-purple-500" />
          <div className="text-3xl font-bold">{summary.total_mentions}</div>
          <div className="text-sm text-muted-foreground">총 언급 수</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <TrendingDown className="w-8 h-8 mx-auto mb-2 text-red-500" />
          <div className="text-3xl font-bold">{summary.total_weaknesses}</div>
          <div className="text-sm text-muted-foreground">발견된 약점</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <Swords className="w-8 h-8 mx-auto mb-2 text-yellow-500" />
          <div className="text-3xl font-bold">{summary.pending_opportunities}</div>
          <div className="text-sm text-muted-foreground">역공략 기회</div>
        </div>
      </div>

      {/* 경쟁사별 통계 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">경쟁사별 온라인 활동</h3>

        {competitors.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Radar className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>아직 모니터링 중인 경쟁사가 없습니다.</p>
            <p className="text-sm mt-1">경쟁사 분석 페이지에서 경쟁사를 등록해주세요.</p>
            <Link
              to="/competitors"
              className="inline-flex items-center gap-2 mt-4 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
            >
              경쟁사 등록하기
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            {competitors.map((comp) => (
              <div key={comp.competitor_name} className="border border-border rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="font-semibold text-lg">{comp.competitor_name}</h4>
                  <span className="text-sm text-muted-foreground">
                    총 {comp.total_mentions}건
                  </span>
                </div>

                {/* 감정 분석 바 */}
                <div className="h-4 bg-muted rounded-full overflow-hidden flex mb-3">
                  {comp.positive > 0 && (
                    <div
                      className="bg-green-500 h-full"
                      style={{ width: `${(comp.positive / comp.total_mentions) * 100}%` }}
                      title={`긍정 ${comp.positive}건`}
                    />
                  )}
                  {comp.neutral > 0 && (
                    <div
                      className="bg-gray-400 h-full"
                      style={{ width: `${(comp.neutral / comp.total_mentions) * 100}%` }}
                      title={`중립 ${comp.neutral}건`}
                    />
                  )}
                  {comp.negative > 0 && (
                    <div
                      className="bg-red-500 h-full"
                      style={{ width: `${(comp.negative / comp.total_mentions) * 100}%` }}
                      title={`부정 ${comp.negative}건`}
                    />
                  )}
                </div>

                <div className="flex items-center justify-between text-sm">
                  <div className="flex gap-4">
                    <span className="text-green-500">긍정 {comp.positive}</span>
                    <span className="text-gray-400">중립 {comp.neutral}</span>
                    <span className="text-red-500">부정 {comp.negative}</span>
                  </div>
                  {comp.weaknesses > 0 && (
                    <span className="text-yellow-500 flex items-center gap-1">
                      <AlertTriangle className="w-4 h-4" />
                      약점 {comp.weaknesses}건
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 역공략 기회 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Swords className="w-5 h-5 text-yellow-500" />
          역공략 기회
        </h3>

        {opportunities.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p>현재 발견된 역공략 기회가 없습니다.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {opportunities.map((opp) => (
              <div
                key={opp.id}
                className="p-4 border border-yellow-500/30 bg-yellow-500/5 rounded-lg"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium">{opp.competitor_name}</span>
                      <span className="text-xs px-2 py-0.5 bg-yellow-500/20 text-yellow-500 rounded">
                        {opp.opportunity_type}
                      </span>
                    </div>
                    {opp.our_strength && (
                      <p className="text-sm text-muted-foreground">
                        우리 강점: {opp.our_strength}
                      </p>
                    )}
                    {opp.suggested_response && (
                      <p className="text-sm text-green-500 mt-1">
                        제안: {opp.suggested_response}
                      </p>
                    )}
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-yellow-500">
                      {opp.opportunity_score.toFixed(0)}
                    </div>
                    <div className="text-xs text-muted-foreground">기회 점수</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

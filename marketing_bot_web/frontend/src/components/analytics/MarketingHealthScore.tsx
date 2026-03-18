/**
 * [Phase M-1] 마케팅 건강 점수 컴포넌트
 * 활동 기반 종합 마케팅 성과 점수
 */

import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  TrendingUp,
  MessageCircle,
  Users,
  Swords,
  AlertCircle,
  RefreshCw,
  ChevronRight,
} from 'lucide-react'
import { analyticsApi } from '@/services/api'
import { LoadingState, ErrorState } from './shared'
import type { MarketingHealthScoreData, HealthScoreRecommendation, HealthScoreDetails } from '@/types/analytics'

interface MarketingHealthScoreProps {
  compact?: boolean
  days?: number
}

export default function MarketingHealthScore({ compact = false, days = 30 }: MarketingHealthScoreProps) {
  const { data, isLoading, isError, refetch, isRefetching } = useQuery<MarketingHealthScoreData>({
    queryKey: ['marketing-health-score', days],
    queryFn: () => analyticsApi.getMarketingHealthScore(days),
    staleTime: 300000, // 5분
    refetchInterval: 600000, // 10분
  })

  if (isLoading) {
    return <LoadingState message="건강 점수 계산 중..." />
  }

  if (isError || !data) {
    return (
      <ErrorState
        message="건강 점수를 불러오는데 실패했습니다"
        onRetry={() => refetch()}
        isRetrying={isRefetching}
      />
    )
  }

  const { total_score, grade, grade_label, scores, details, recommendations } = data

  // 등급별 색상
  const gradeColors: Record<string, string> = {
    A: 'text-green-500 bg-green-500/10 border-green-500/30',
    B: 'text-blue-500 bg-blue-500/10 border-blue-500/30',
    C: 'text-yellow-500 bg-yellow-500/10 border-yellow-500/30',
    D: 'text-red-500 bg-red-500/10 border-red-500/30',
  }

  const gradeColor = gradeColors[grade] || gradeColors.D

  // 컴팩트 모드
  if (compact) {
    return (
      <div className="bg-card rounded-lg border border-border p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" aria-hidden="true" />
            마케팅 건강
          </h3>
          <div className={`px-2 py-1 rounded-lg text-sm font-bold border ${gradeColor}`}>
            {grade} ({total_score.toFixed(0)}점)
          </div>
        </div>

        <div className="grid grid-cols-4 gap-2">
          <ScoreBar label="순위" value={scores.ranking} icon={<TrendingUp className="w-3 h-3" />} />
          <ScoreBar label="바이럴" value={scores.viral} icon={<MessageCircle className="w-3 h-3" />} />
          <ScoreBar label="리드" value={scores.leads} icon={<Users className="w-3 h-3" />} />
          <ScoreBar label="경쟁" value={scores.competition} icon={<Swords className="w-3 h-3" />} />
        </div>

        {recommendations.length > 0 && (
          <div className="mt-3 pt-3 border-t border-border">
            <div className="text-xs text-muted-foreground flex items-center gap-1">
              <AlertCircle className="w-3 h-3" aria-hidden="true" />
              {recommendations[0].message}
            </div>
          </div>
        )}
      </div>
    )
  }

  // 전체 모드
  return (
    <div className="bg-card rounded-lg border border-border">
      {/* 헤더 */}
      <div className="p-6 border-b border-border">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Activity className="w-5 h-5 text-primary" aria-hidden="true" />
              마케팅 건강 점수
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              최근 {days}일 기준
            </p>
          </div>
          <button
            onClick={() => refetch()}
            className="p-2 hover:bg-muted rounded-lg transition-colors"
            disabled={isRefetching}
            aria-label="건강 점수 새로고침"
          >
            <RefreshCw className={`w-5 h-5 ${isRefetching ? 'animate-spin' : ''}`} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* 종합 점수 */}
      <div className="p-6 border-b border-border">
        <div className="flex items-center gap-6">
          {/* 큰 점수 표시 */}
          <div className={`w-32 h-32 rounded-full flex flex-col items-center justify-center border-4 ${gradeColor}`}>
            <span className="text-4xl font-bold">{total_score.toFixed(0)}</span>
            <span className="text-sm">/ 100</span>
          </div>

          <div className="flex-1">
            <div className={`inline-block px-4 py-2 rounded-lg text-lg font-bold border ${gradeColor}`}>
              {grade}등급 - {grade_label}
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              {grade === 'A' && '마케팅 활동이 매우 건강한 상태입니다. 현재 전략을 유지하세요.'}
              {grade === 'B' && '마케팅 활동이 양호합니다. 조금 더 개선하면 A등급을 받을 수 있습니다.'}
              {grade === 'C' && '일부 영역에서 개선이 필요합니다. 아래 권장 사항을 확인하세요.'}
              {grade === 'D' && '마케팅 활동 강화가 필요합니다. 우선순위에 따라 개선하세요.'}
            </p>
          </div>
        </div>
      </div>

      {/* 세부 점수 */}
      <div className="p-6 border-b border-border">
        <h3 className="text-sm font-semibold text-muted-foreground mb-4">세부 점수</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <ScoreCard
            icon={<TrendingUp className="w-5 h-5" />}
            label="순위 점수"
            value={scores.ranking}
            weight={30}
            details={details.ranking}
          />
          <ScoreCard
            icon={<MessageCircle className="w-5 h-5" />}
            label="바이럴 활동"
            value={scores.viral}
            weight={25}
            details={details.viral}
          />
          <ScoreCard
            icon={<Users className="w-5 h-5" />}
            label="리드 생성"
            value={scores.leads}
            weight={25}
            details={details.leads}
          />
          <ScoreCard
            icon={<Swords className="w-5 h-5" />}
            label="경쟁 우위"
            value={scores.competition}
            weight={20}
            details={details.competition}
          />
        </div>
      </div>

      {/* 개선 권장사항 */}
      {recommendations.length > 0 && (
        <div className="p-6">
          <h3 className="text-sm font-semibold text-muted-foreground mb-3">개선 권장사항</h3>
          <div className="space-y-2">
            {recommendations.map((rec: HealthScoreRecommendation, idx: number) => (
              <div
                key={idx}
                className={`p-3 rounded-lg flex items-center gap-3 ${
                  rec.priority === 'high'
                    ? 'bg-red-500/10 border border-red-500/30'
                    : 'bg-muted/50'
                }`}
              >
                <AlertCircle className={`w-4 h-4 flex-shrink-0 ${
                  rec.priority === 'high' ? 'text-red-500' : 'text-muted-foreground'
                }`} aria-hidden="true" />
                <span className="text-sm flex-1">{rec.message}</span>
                <ChevronRight className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// 점수 막대 (컴팩트용)
function ScoreBar({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) {
  const color = value >= 70 ? 'bg-green-500' : value >= 40 ? 'bg-yellow-500' : 'bg-red-500'

  return (
    <div className="text-center">
      <div className="flex items-center justify-center gap-1 text-xs text-muted-foreground mb-1">
        <span aria-hidden="true">{icon}</span>
        {label}
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${value}%` }} />
      </div>
      <div className="text-xs mt-1 font-medium">{value.toFixed(0)}</div>
    </div>
  )
}

// 점수 카드 (전체 모드용)
function ScoreCard({
  icon,
  label,
  value,
  weight,
  details,
}: {
  icon: React.ReactNode
  label: string
  value: number
  weight: number
  details: HealthScoreDetails
}) {
  const color = value >= 70 ? 'text-green-500' : value >= 40 ? 'text-yellow-500' : 'text-red-500'
  const bgColor = value >= 70 ? 'bg-green-500' : value >= 40 ? 'bg-yellow-500' : 'bg-red-500'

  return (
    <div className="p-4 rounded-lg bg-muted/50">
      <div className="flex items-center gap-2 text-muted-foreground mb-2">
        <span aria-hidden="true">{icon}</span>
        <span className="text-xs">{label}</span>
        <span className="text-xs ml-auto">({weight}%)</span>
      </div>
      <div className={`text-2xl font-bold ${color}`}>{value.toFixed(0)}</div>
      <div className="h-2 bg-muted rounded-full overflow-hidden mt-2">
        <div className={`h-full ${bgColor}`} style={{ width: `${value}%` }} />
      </div>
      {/* 세부 정보 */}
      <div className="mt-2 text-xs text-muted-foreground">
        {details.message ? (
          <span>{String(details.message)}</span>
        ) : (
          <>
            {details.top10_keywords !== undefined && (
              <span>Top10: {String(details.top10_keywords)}개</span>
            )}
            {details.completion_rate !== undefined && (
              <span>완료율: {String(details.completion_rate)}%</span>
            )}
            {details.conversion_rate !== undefined && (
              <span>전환율: {String(details.conversion_rate)}%</span>
            )}
            {details.win_rate !== undefined && (
              <span>승률: {String(details.win_rate)}%</span>
            )}
          </>
        )}
      </div>
    </div>
  )
}

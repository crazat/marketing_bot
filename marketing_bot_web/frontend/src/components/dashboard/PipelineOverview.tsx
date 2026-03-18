/**
 * [Phase 8.0] 마케팅 파이프라인 개요 컴포넌트
 * 5단계 파이프라인: 발견 → 추적 → 콘텐츠 → 유입 → 전환
 * Dashboard 상단에 항상 표시되어 전체 마케팅 흐름을 한눈에 파악
 */

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { pathfinderApi, battleApi, viralApi, leadsApi } from '@/services/api'
import {
  Search,
  TrendingUp,
  MessageSquare,
  Users,
  CheckCircle,
  ChevronRight,
  Sparkles
} from 'lucide-react'

interface PipelineStage {
  id: string
  label: string
  shortLabel: string
  value: number
  subValue?: string
  icon: React.ReactNode
  color: string
  bgColor: string
  borderColor: string
  path: string
  tooltip: string
}

export default function PipelineOverview() {
  const navigate = useNavigate()

  // 키워드 통계
  const { data: keywordStats } = useQuery({
    queryKey: ['pathfinder-stats-pipeline'],
    queryFn: () => pathfinderApi.getStats(),
    staleTime: 60000,
  })

  // 순위 키워드 통계
  const { data: rankingKeywords } = useQuery({
    queryKey: ['ranking-keywords-pipeline'],
    queryFn: battleApi.getRankingKeywords,
    staleTime: 60000,
  })

  // 바이럴 통계
  const { data: viralStats } = useQuery({
    queryKey: ['viral-stats-pipeline'],
    queryFn: viralApi.getStats,
    staleTime: 60000,
  })

  // 리드 통계
  const { data: leadStats } = useQuery({
    queryKey: ['lead-stats-pipeline'],
    queryFn: leadsApi.getStats,
    staleTime: 60000,
  })

  // 전환 추적 통계
  const { data: conversionStats } = useQuery({
    queryKey: ['conversion-tracking-pipeline'],
    queryFn: leadsApi.getConversionTracking,
    staleTime: 60000,
  })

  // [성능 최적화] useMemo로 계산 결과 캐싱
  const pipelineStats = useMemo(() => ({
    sGradeKeywords: keywordStats?.by_grade?.S || 0,
    aGradeKeywords: keywordStats?.by_grade?.A || 0,
    newKeywords: (keywordStats?.by_grade?.S || 0) + (keywordStats?.by_grade?.A || 0),
    trackingCount: rankingKeywords?.length || 0,
    rankUpCount: rankingKeywords?.filter((k: any) => k.rank_change > 0).length || 0,
    pendingViral: viralStats?.pending || 0,
    newViral: viralStats?.new_today || 0,
    hotLeads: leadStats?.by_status?.hot || 0,
    activeLeads: (leadStats?.by_status?.new || 0) + (leadStats?.by_status?.contacted || 0),
    thisMonthConversions: conversionStats?.this_month?.count || 0,
    thisMonthRevenue: conversionStats?.this_month?.revenue || 0,
  }), [keywordStats, rankingKeywords, viralStats, leadStats, conversionStats])

  const {
    sGradeKeywords,
    newKeywords,
    trackingCount,
    rankUpCount,
    pendingViral,
    newViral,
    hotLeads,
    activeLeads,
    thisMonthConversions,
    thisMonthRevenue,
  } = pipelineStats

  const pipelineStages: PipelineStage[] = [
    {
      id: 'discovery',
      label: '발견',
      shortLabel: 'Discovery',
      value: newKeywords,
      subValue: `S급 ${sGradeKeywords}개`,
      icon: <Search className="w-5 h-5" />,
      color: 'text-blue-500',
      bgColor: 'bg-blue-500/10',
      borderColor: 'border-blue-500/30',
      path: '/pathfinder',
      tooltip: 'Pathfinder에서 발굴된 S/A급 키워드',
    },
    {
      id: 'tracking',
      label: '추적',
      shortLabel: 'Tracking',
      value: trackingCount,
      subValue: rankUpCount > 0 ? `${rankUpCount}개 상승` : undefined,
      icon: <TrendingUp className="w-5 h-5" />,
      color: 'text-purple-500',
      bgColor: 'bg-purple-500/10',
      borderColor: 'border-purple-500/30',
      path: '/battle',
      tooltip: 'Battle Intelligence에서 순위 추적 중인 키워드',
    },
    {
      id: 'content',
      label: '콘텐츠',
      shortLabel: 'Content',
      value: pendingViral,
      subValue: newViral > 0 ? `+${newViral} 오늘` : undefined,
      icon: <MessageSquare className="w-5 h-5" />,
      color: 'text-orange-500',
      bgColor: 'bg-orange-500/10',
      borderColor: 'border-orange-500/30',
      path: '/viral',
      tooltip: 'Viral Hunter에서 대기 중인 타겟',
    },
    {
      id: 'acquisition',
      label: '유입',
      shortLabel: 'Acquisition',
      value: activeLeads,
      subValue: hotLeads > 0 ? `HOT ${hotLeads}개` : undefined,
      icon: <Users className="w-5 h-5" />,
      color: 'text-cyan-500',
      bgColor: 'bg-cyan-500/10',
      borderColor: 'border-cyan-500/30',
      path: '/leads',
      tooltip: '활성 리드 (신규 + 컨택중)',
    },
    {
      id: 'conversion',
      label: '전환',
      shortLabel: 'Conversion',
      value: thisMonthConversions,
      subValue: thisMonthRevenue > 0 ? `${(thisMonthRevenue / 10000).toFixed(0)}만원` : undefined,
      icon: <CheckCircle className="w-5 h-5" />,
      color: 'text-green-500',
      bgColor: 'bg-green-500/10',
      borderColor: 'border-green-500/30',
      path: '/leads?status=converted',
      tooltip: '이번 달 전환 및 매출',
    },
  ]

  // 다음 추천 액션 결정
  const getNextAction = () => {
    if (sGradeKeywords > 0 && trackingCount < 10) {
      return {
        message: `S급 키워드 ${sGradeKeywords}개 순위 추적 등록 권장`,
        link: '/pathfinder?grade=S',
        type: 'keyword'
      }
    }
    if (pendingViral > 10) {
      return {
        message: `대기 중인 바이럴 타겟 ${pendingViral}개 - 댓글 작성 필요`,
        link: '/viral',
        type: 'viral'
      }
    }
    if (hotLeads > 0) {
      return {
        message: `HOT 리드 ${hotLeads}개 응답 대기 중`,
        link: '/leads?grade=hot',
        type: 'lead'
      }
    }
    return null
  }

  const nextAction = getNextAction()

  return (
    <div className="bg-card rounded-lg border border-border p-4 md:p-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-bold">마케팅 파이프라인</h2>
        </div>
        <span className="text-xs text-muted-foreground hidden md:block">
          클릭하여 상세 페이지로 이동
        </span>
      </div>

      {/* 파이프라인 스테이지 */}
      <div className="flex items-stretch gap-1 md:gap-2 overflow-x-auto pb-2">
        {pipelineStages.map((stage, index) => (
          <div key={stage.id} className="flex items-center flex-1 min-w-0">
            {/* 스테이지 카드 */}
            <button
              onClick={() => navigate(stage.path)}
              className={`
                flex-1 min-w-[80px] md:min-w-[120px] p-3 md:p-4 rounded-lg border transition-all
                hover:shadow-md hover:scale-[1.02] cursor-pointer
                ${stage.bgColor} ${stage.borderColor}
              `}
              title={stage.tooltip}
            >
              {/* 아이콘 + 라벨 */}
              <div className={`flex items-center gap-1 md:gap-2 mb-2 ${stage.color}`}>
                {stage.icon}
                <span className="text-xs md:text-sm font-medium truncate">
                  {stage.label}
                </span>
              </div>

              {/* 메인 값 */}
              <div className="text-xl md:text-2xl font-bold">
                {stage.value.toLocaleString()}
              </div>

              {/* 서브 값 */}
              {stage.subValue && (
                <div className={`text-xs mt-1 ${stage.color} opacity-80`}>
                  {stage.subValue}
                </div>
              )}
            </button>

            {/* 화살표 */}
            {index < pipelineStages.length - 1 && (
              <div className="px-1 md:px-2 flex-shrink-0">
                <ChevronRight className="w-4 h-4 md:w-5 md:h-5 text-muted-foreground" />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* 다음 액션 제안 */}
      {nextAction && (
        <div
          onClick={() => navigate(nextAction.link)}
          className="mt-4 p-3 bg-primary/10 border border-primary/30 rounded-lg cursor-pointer hover:bg-primary/20 transition-colors"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-lg">
                {nextAction.type === 'keyword' && '🎯'}
                {nextAction.type === 'viral' && '💬'}
                {nextAction.type === 'lead' && '🔥'}
              </span>
              <span className="text-sm font-medium text-primary">
                다음 액션: {nextAction.message}
              </span>
            </div>
            <ChevronRight className="w-4 h-4 text-primary" />
          </div>
        </div>
      )}
    </div>
  )
}

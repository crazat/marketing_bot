/**
 * [Phase 6.0] 통합 마케팅 퍼널 컴포넌트
 * 키워드 → 순위 → 리드 → 전환 흐름을 시각화
 */

import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { pathfinderApi, battleApi, leadsApi } from '@/services/api'
import { ArrowRight, TrendingUp, Target, Users, CheckCircle } from 'lucide-react'

interface FunnelStage {
  id: string
  label: string
  value: number
  icon: React.ReactNode
  color: string
  bgColor: string
  path: string
}

export default function MarketingFunnel() {
  const navigate = useNavigate()

  // 키워드 통계
  const { data: keywordStats } = useQuery({
    queryKey: ['pathfinder-stats'],
    queryFn: () => pathfinderApi.getStats(),
  })

  // 순위 키워드 통계
  const { data: rankingKeywords } = useQuery({
    queryKey: ['ranking-keywords'],
    queryFn: battleApi.getRankingKeywords,
  })

  // 리드 통계
  const { data: leadStats } = useQuery({
    queryKey: ['lead-stats'],
    queryFn: leadsApi.getStats,
  })

  // 퍼널 데이터 계산
  const totalKeywords = keywordStats?.total || 0
  const sGradeKeywords = keywordStats?.by_grade?.S || 0
  const rankedKeywords = rankingKeywords?.filter((k: any) => k.current_rank && k.current_rank <= 10).length || 0
  const totalLeads = leadStats?.total || 0
  const convertedLeads = leadStats?.by_status?.converted || 0

  const funnelStages: FunnelStage[] = [
    {
      id: 'keywords',
      label: '발굴 키워드',
      value: totalKeywords,
      icon: <Target className="w-5 h-5" />,
      color: 'text-blue-500',
      bgColor: 'bg-blue-500',
      path: '/pathfinder',
    },
    {
      id: 'ranked',
      label: 'TOP 10 진입',
      value: rankedKeywords,
      icon: <TrendingUp className="w-5 h-5" />,
      color: 'text-purple-500',
      bgColor: 'bg-purple-500',
      path: '/battle',
    },
    {
      id: 'leads',
      label: '리드 확보',
      value: totalLeads,
      icon: <Users className="w-5 h-5" />,
      color: 'text-orange-500',
      bgColor: 'bg-orange-500',
      path: '/leads',
    },
    {
      id: 'converted',
      label: '전환 완료',
      value: convertedLeads,
      icon: <CheckCircle className="w-5 h-5" />,
      color: 'text-green-500',
      bgColor: 'bg-green-500',
      path: '/leads?status=converted',
    },
  ]

  // 전환율 계산
  const getConversionRate = (current: number, previous: number) => {
    if (previous === 0) return null
    return Math.round((current / previous) * 100)
  }

  const conversionRates = [
    getConversionRate(rankedKeywords, totalKeywords),
    getConversionRate(totalLeads, rankedKeywords),
    getConversionRate(convertedLeads, totalLeads),
  ]

  // 전체 전환율
  const overallRate = totalKeywords > 0 ? Math.round((convertedLeads / totalKeywords) * 100 * 100) / 100 : 0

  return (
    <div className="bg-card rounded-lg border border-border p-6">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold">📊 마케팅 퍼널</h3>
        <div className="text-xs text-muted-foreground">
          클릭하여 상세 페이지로 이동
        </div>
      </div>

      {/* 퍼널 시각화 */}
      <div className="flex items-center justify-between gap-2">
        {funnelStages.map((stage, index) => (
          <div key={stage.id} className="flex items-center flex-1">
            {/* 스테이지 카드 */}
            <div
              onClick={() => navigate(stage.path)}
              className="flex-1 p-4 bg-muted/50 rounded-lg hover:bg-muted cursor-pointer transition-colors group"
            >
              <div className={`flex items-center gap-2 mb-2 ${stage.color}`}>
                {stage.icon}
                <span className="text-sm font-medium">{stage.label}</span>
              </div>
              <div className="text-3xl font-bold">{stage.value.toLocaleString()}</div>

              {/* 전환율 표시 */}
              {index > 0 && conversionRates[index - 1] !== null && (
                <div className="mt-2 text-xs text-muted-foreground">
                  전환율: <span className={`font-medium ${conversionRates[index - 1]! >= 50 ? 'text-green-500' : conversionRates[index - 1]! >= 20 ? 'text-yellow-500' : 'text-red-500'}`}>
                    {conversionRates[index - 1]}%
                  </span>
                </div>
              )}
            </div>

            {/* 화살표 */}
            {index < funnelStages.length - 1 && (
              <div className="px-2 flex-shrink-0">
                <ArrowRight className="w-5 h-5 text-muted-foreground" />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* 퍼널 시각화 (깔때기 모양) */}
      <div className="mt-6 flex flex-col items-center gap-1">
        {funnelStages.map((stage, index) => {
          // 각 단계별 너비 계산 (점점 좁아지는 깔때기)
          const widthPercent = 100 - (index * 18) // 100% → 82% → 64% → 46%
          const prevValue = index > 0 ? funnelStages[index - 1].value : null

          return (
            <div key={stage.id} className="w-full flex flex-col items-center">
              {/* 전환율 화살표 (첫 단계 제외) */}
              {index > 0 && (
                <div className="flex items-center gap-2 py-1 text-xs text-muted-foreground">
                  <div className="w-0 h-0 border-l-4 border-r-4 border-t-6 border-l-transparent border-r-transparent border-t-muted-foreground/50" />
                  {conversionRates[index - 1] !== null && (
                    <span className={`font-semibold ${
                      conversionRates[index - 1]! >= 50 ? 'text-green-500' :
                      conversionRates[index - 1]! >= 20 ? 'text-yellow-500' : 'text-red-500'
                    }`}>
                      {conversionRates[index - 1]}% 전환
                    </span>
                  )}
                  <div className="w-0 h-0 border-l-4 border-r-4 border-t-6 border-l-transparent border-r-transparent border-t-muted-foreground/50" />
                </div>
              )}

              {/* 퍼널 단계 */}
              <div
                onClick={() => navigate(stage.path)}
                className={`
                  relative flex items-center justify-between px-4 py-3
                  ${stage.bgColor}/20 hover:${stage.bgColor}/30
                  border-2 ${stage.color.replace('text-', 'border-')}
                  cursor-pointer transition-all duration-300 group
                  hover:scale-[1.02] hover:shadow-md
                `}
                style={{
                  width: `${widthPercent}%`,
                  clipPath: index < funnelStages.length - 1
                    ? 'polygon(0 0, 100% 0, 96% 100%, 4% 100%)'
                    : 'polygon(4% 0, 96% 0, 100% 100%, 0 100%)',
                  borderRadius: index === 0 ? '8px 8px 0 0' : index === funnelStages.length - 1 ? '0 0 8px 8px' : '0',
                }}
              >
                {/* 아이콘 + 라벨 */}
                <div className={`flex items-center gap-2 ${stage.color}`}>
                  {stage.icon}
                  <span className="font-medium">{stage.label}</span>
                </div>

                {/* 숫자 */}
                <div className="flex items-center gap-3">
                  <span className="text-2xl font-bold">{stage.value.toLocaleString()}</span>
                  {prevValue !== null && prevValue > 0 && (
                    <span className="text-xs text-muted-foreground">
                      ({Math.round((stage.value / prevValue) * 100)}%)
                    </span>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* 전체 전환율 요약 */}
      <div className="mt-4 flex justify-center">
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-500/10 via-purple-500/10 to-green-500/10 rounded-full border border-border">
          <span className="text-sm text-muted-foreground">전체 전환율</span>
          <span className="text-lg font-bold text-green-500">{overallRate}%</span>
          <span className="text-xs text-muted-foreground">({totalKeywords} → {convertedLeads})</span>
        </div>
      </div>

      {/* 인사이트 */}
      {totalKeywords > 0 && (
        <div className="mt-4 p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
          <div className="text-sm">
            {rankedKeywords === 0 ? (
              <span className="text-yellow-500">💡 순위권 진입 키워드가 없습니다. Battle Intelligence에서 순위를 확인하세요.</span>
            ) : convertedLeads === 0 ? (
              <span className="text-yellow-500">💡 아직 전환된 리드가 없습니다. 리드 관리에서 상태를 업데이트하세요.</span>
            ) : (
              <span className="text-green-500">✅ 마케팅 퍼널이 정상 작동 중입니다. {sGradeKeywords}개의 S급 키워드가 있습니다.</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

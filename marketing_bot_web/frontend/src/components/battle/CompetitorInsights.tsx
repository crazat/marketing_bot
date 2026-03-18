import { useQuery } from '@tanstack/react-query'
import { competitorsApi } from '@/services/api'
import { Link } from 'react-router-dom'
import { AlertTriangle, Target, Radar, TrendingUp, ArrowRight, Lightbulb } from 'lucide-react'

export default function CompetitorInsights() {
  // Content Gap 분석 데이터
  const { data: contentGap, isLoading: gapLoading } = useQuery({
    queryKey: ['content-gap-summary'],
    queryFn: competitorsApi.getContentGap,
    retry: 1,
  })

  // Weakness Radar 데이터
  const { data: weaknessRadar, isLoading: radarLoading } = useQuery({
    queryKey: ['weakness-radar-summary'],
    queryFn: competitorsApi.getWeaknessRadar,
    retry: 1,
  })

  const isLoading = gapLoading || radarLoading

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        <span className="ml-3 text-muted-foreground">경쟁 인사이트 분석 중...</span>
      </div>
    )
  }

  const hasData = contentGap || weaknessRadar

  if (!hasData) {
    return (
      <div className="text-center py-12">
        <AlertTriangle className="w-12 h-12 text-yellow-500 mx-auto mb-4" />
        <p className="text-lg font-medium mb-2">경쟁 인사이트 데이터 없음</p>
        <p className="text-sm text-muted-foreground mb-4">
          경쟁사 분석 페이지에서 리뷰 분석을 먼저 실행해주세요.
        </p>
        <Link
          to="/competitors"
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90"
        >
          경쟁사 분석으로 이동
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 요약 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <Target className="w-4 h-4 text-red-500" />
            <span className="text-sm text-muted-foreground">콘텐츠 갭</span>
          </div>
          <div className="text-2xl font-bold text-red-500">
            {contentGap?.summary?.total_gaps || 0}
          </div>
          <div className="text-xs text-muted-foreground">경쟁사만 보유한 키워드</div>
        </div>
        <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-green-500" />
            <span className="text-sm text-muted-foreground">우리 강점</span>
          </div>
          <div className="text-2xl font-bold text-green-500">
            {contentGap?.summary?.total_strengths || 0}
          </div>
          <div className="text-xs text-muted-foreground">우리만 보유한 키워드</div>
        </div>
        <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <Radar className="w-4 h-4 text-purple-500" />
            <span className="text-sm text-muted-foreground">발견된 약점</span>
          </div>
          <div className="text-2xl font-bold text-purple-500">
            {weaknessRadar?.summary?.total_weaknesses_found || 0}
          </div>
          <div className="text-xs text-muted-foreground">경쟁사 부정 리뷰 분석</div>
        </div>
        <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <Lightbulb className="w-4 h-4 text-yellow-500" />
            <span className="text-sm text-muted-foreground">기회</span>
          </div>
          <div className="text-2xl font-bold text-yellow-500">
            {weaknessRadar?.opportunities?.length || 0}
          </div>
          <div className="text-xs text-muted-foreground">차별화 기회</div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* 콘텐츠 갭 요약 */}
        <div className="bg-card rounded-lg border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold flex items-center gap-2">
              <Target className="w-5 h-5 text-red-500" />
              콘텐츠 갭 TOP 5
            </h3>
            <Link
              to="/competitors?tab=content-gap"
              className="text-xs text-primary hover:underline flex items-center gap-1"
            >
              자세히 보기
              <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          {contentGap?.gap_keywords?.length > 0 ? (
            <div className="space-y-2">
              {contentGap.gap_keywords.slice(0, 5).map((gap: any, idx: number) => (
                <div
                  key={idx}
                  className="flex items-center justify-between p-3 bg-red-500/5 rounded-lg border border-red-500/20"
                >
                  <span className="font-medium">{gap.keyword}</span>
                  <span className="text-sm text-red-500">
                    {gap.competitor_count || gap.mention_count}개 경쟁사
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-6 text-muted-foreground">
              <p>콘텐츠 갭이 없습니다</p>
              <p className="text-sm">경쟁사 대비 키워드 커버리지가 우수합니다</p>
            </div>
          )}
        </div>

        {/* 약점 레이더 요약 */}
        <div className="bg-card rounded-lg border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold flex items-center gap-2">
              <Radar className="w-5 h-5 text-purple-500" />
              경쟁사 약점 TOP 5
            </h3>
            <Link
              to="/competitors?tab=weakness-radar"
              className="text-xs text-primary hover:underline flex items-center gap-1"
            >
              자세히 보기
              <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          {weaknessRadar?.weakness_frequency?.length > 0 ? (
            <div className="space-y-2">
              {weaknessRadar.weakness_frequency.slice(0, 5).map((weakness: any, idx: number) => (
                <div
                  key={idx}
                  className="flex items-center justify-between p-3 rounded-lg"
                  style={{ backgroundColor: `${weakness.color}10`, borderColor: `${weakness.color}30`, borderWidth: 1 }}
                >
                  <div className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: weakness.color }}
                    />
                    <span className="font-medium">{weakness.label}</span>
                  </div>
                  <span className="text-sm" style={{ color: weakness.color }}>
                    {weakness.count}건
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-6 text-muted-foreground">
              <p>분석된 약점이 없습니다</p>
              <p className="text-sm">경쟁사 리뷰 분석을 실행해주세요</p>
            </div>
          )}
        </div>
      </div>

      {/* 추천 액션 */}
      {contentGap?.recommendations?.length > 0 && (
        <div className="bg-gradient-to-r from-yellow-500/10 to-orange-500/10 rounded-lg border border-yellow-500/30 p-6">
          <h3 className="text-lg font-bold flex items-center gap-2 mb-4">
            <Lightbulb className="w-5 h-5 text-yellow-500" />
            추천 액션
          </h3>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {contentGap.recommendations.slice(0, 3).map((rec: any, idx: number) => (
              <div
                key={idx}
                className="bg-card rounded-lg p-4 border border-border"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-sm">{rec.keyword}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    rec.priority === 'high' ? 'bg-red-500/20 text-red-500' :
                    rec.priority === 'medium' ? 'bg-yellow-500/20 text-yellow-500' :
                    'bg-blue-500/20 text-blue-500'
                  }`}>
                    {rec.priority === 'high' ? '긴급' : rec.priority === 'medium' ? '권장' : '참고'}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  {rec.reason || rec.suggested_content}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 상세 분석 링크 */}
      <div className="flex justify-center">
        <Link
          to="/competitors"
          className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
        >
          경쟁사 분석 상세 보기
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </div>
  )
}

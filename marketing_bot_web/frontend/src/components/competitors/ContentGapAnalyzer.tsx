import { useQuery } from '@tanstack/react-query'
import { competitorsApi } from '@/services/api'
import { AlertTriangle, Target, TrendingUp, Lightbulb, RefreshCw } from 'lucide-react'

interface ContentGapData {
  gap_keywords: {
    keyword: string
    competitor_count: number
    competitors: string[]
  }[]
  our_strengths: {
    keyword: string
    grade: string
    search_volume: number
  }[]
  shared_keywords: {
    keyword: string
    our_grade: string
    competitor_count: number
  }[]
  recommendations: {
    priority: 'high' | 'medium' | 'low'
    keyword: string
    reason: string
    suggested_content_type: string
  }[]
  summary: {
    total_gap_keywords: number
    total_our_strengths: number
    total_shared: number
    coverage_score: number
  }
}

export default function ContentGapAnalyzer() {
  const { data, isLoading, error, refetch, isRefetching } = useQuery<ContentGapData>({
    queryKey: ['content-gap-analysis'],
    queryFn: competitorsApi.getContentGap,
  })

  if (isLoading) {
    return (
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          <span className="ml-3 text-muted-foreground">콘텐츠 갭 분석 중...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex flex-col items-center justify-center py-12">
          <AlertTriangle className="w-12 h-12 text-yellow-500 mb-4" />
          <p className="text-lg font-medium mb-2">분석 데이터를 불러올 수 없습니다</p>
          <p className="text-sm text-muted-foreground mb-4">
            키워드 또는 경쟁사 데이터가 부족할 수 있습니다.
          </p>
          <button
            onClick={() => refetch()}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90"
          >
            다시 시도
          </button>
        </div>
      </div>
    )
  }

  if (!data) return null

  const { gap_keywords, our_strengths, shared_keywords, recommendations, summary } = data

  const priorityColors = {
    high: 'bg-red-500/10 text-red-500 border-red-500/30',
    medium: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/30',
    low: 'bg-blue-500/10 text-blue-500 border-blue-500/30',
  }

  const gradeColors: Record<string, string> = {
    S: 'bg-purple-500/20 text-purple-500',
    A: 'bg-blue-500/20 text-blue-500',
    B: 'bg-green-500/20 text-green-500',
    C: 'bg-yellow-500/20 text-yellow-500',
    D: 'bg-gray-500/20 text-gray-500',
  }

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <Target className="w-5 h-5 text-primary" />
            콘텐츠 갭 분석
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            경쟁사 대비 우리가 놓치고 있는 키워드와 콘텐츠 기회를 분석합니다.
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isRefetching}
          className="flex items-center gap-2 px-3 py-2 bg-muted rounded-lg hover:bg-muted/80 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${isRefetching ? 'animate-spin' : ''}`} />
          새로고침
        </button>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-card rounded-lg border border-border p-4">
          <div className="text-2xl font-bold text-red-500">{summary?.total_gap_keywords || 0}</div>
          <div className="text-sm text-muted-foreground">갭 키워드</div>
          <div className="text-xs text-muted-foreground mt-1">경쟁사만 보유</div>
        </div>
        <div className="bg-card rounded-lg border border-border p-4">
          <div className="text-2xl font-bold text-green-500">{summary?.total_our_strengths || 0}</div>
          <div className="text-sm text-muted-foreground">우리만의 강점</div>
          <div className="text-xs text-muted-foreground mt-1">우리만 보유</div>
        </div>
        <div className="bg-card rounded-lg border border-border p-4">
          <div className="text-2xl font-bold text-blue-500">{summary?.total_shared || 0}</div>
          <div className="text-sm text-muted-foreground">공통 키워드</div>
          <div className="text-xs text-muted-foreground mt-1">양측 모두 보유</div>
        </div>
        <div className="bg-card rounded-lg border border-border p-4">
          <div className="text-2xl font-bold text-primary">
            {summary?.coverage_score?.toFixed(0) || 0}%
          </div>
          <div className="text-sm text-muted-foreground">커버리지</div>
          <div className="text-xs text-muted-foreground mt-1">키워드 확보율</div>
        </div>
      </div>

      {/* 추천 콘텐츠 */}
      {recommendations && recommendations.length > 0 && (
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-bold flex items-center gap-2 mb-4">
            <Lightbulb className="w-5 h-5 text-yellow-500" />
            콘텐츠 제작 추천
          </h3>
          <div className="space-y-3">
            {recommendations.slice(0, 5).map((rec, idx) => (
              <div
                key={idx}
                className={`p-4 rounded-lg border ${priorityColors[rec.priority]}`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold">{rec.keyword}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${priorityColors[rec.priority]}`}>
                        {rec.priority === 'high' ? '긴급' : rec.priority === 'medium' ? '권장' : '참고'}
                      </span>
                    </div>
                    <p className="text-sm opacity-80">{rec.reason}</p>
                  </div>
                  <span className="text-xs px-2 py-1 bg-background/50 rounded">
                    {rec.suggested_content_type}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 갭 키워드 목록 */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* 갭 키워드 */}
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-bold flex items-center gap-2 mb-4">
            <AlertTriangle className="w-5 h-5 text-red-500" />
            갭 키워드
            <span className="text-sm font-normal text-muted-foreground ml-auto">
              경쟁사는 있지만 우리는 없는 키워드
            </span>
          </h3>
          {gap_keywords && gap_keywords.length > 0 ? (
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {gap_keywords.map((item, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between p-3 rounded-lg bg-red-500/5 border border-red-500/20 hover:bg-red-500/10 transition-colors"
                >
                  <div>
                    <span className="font-medium">{item.keyword}</span>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {item.competitors.slice(0, 3).join(', ')}
                      {item.competitors.length > 3 && ` 외 ${item.competitors.length - 3}곳`}
                    </div>
                  </div>
                  <span className="text-sm text-red-500 font-medium">
                    {item.competitor_count}개 경쟁사
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <p>갭 키워드가 없습니다</p>
              <p className="text-sm">경쟁사 대비 키워드 커버리지가 우수합니다!</p>
            </div>
          )}
        </div>

        {/* 우리만의 강점 */}
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-bold flex items-center gap-2 mb-4">
            <TrendingUp className="w-5 h-5 text-green-500" />
            우리만의 강점
            <span className="text-sm font-normal text-muted-foreground ml-auto">
              우리만 보유한 S/A등급 키워드
            </span>
          </h3>
          {our_strengths && our_strengths.length > 0 ? (
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {our_strengths.map((item, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between p-3 rounded-lg bg-green-500/5 border border-green-500/20 hover:bg-green-500/10 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${gradeColors[item.grade] || gradeColors['D']}`}>
                      {item.grade}
                    </span>
                    <span className="font-medium">{item.keyword}</span>
                  </div>
                  <span className="text-sm text-muted-foreground">
                    {item.search_volume?.toLocaleString() || 0} 검색량
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <p>분석된 강점 키워드가 없습니다</p>
              <p className="text-sm">S/A등급 키워드를 더 확보해보세요</p>
            </div>
          )}
        </div>
      </div>

      {/* 공통 키워드 */}
      {shared_keywords && shared_keywords.length > 0 && (
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-bold mb-4">
            공통 키워드
            <span className="text-sm font-normal text-muted-foreground ml-2">
              우리와 경쟁사 모두 보유
            </span>
          </h3>
          <div className="flex flex-wrap gap-2">
            {shared_keywords.slice(0, 20).map((item, idx) => (
              <span
                key={idx}
                className={`px-3 py-1.5 rounded-full text-sm border ${gradeColors[item.our_grade] || 'bg-muted'}`}
              >
                {item.keyword}
                <span className="ml-1 opacity-60">({item.competitor_count})</span>
              </span>
            ))}
            {shared_keywords.length > 20 && (
              <span className="px-3 py-1.5 rounded-full text-sm bg-muted text-muted-foreground">
                +{shared_keywords.length - 20}개 더보기
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

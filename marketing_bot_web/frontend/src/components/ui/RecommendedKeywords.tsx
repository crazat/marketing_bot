import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { hudApi } from '@/services/api'

interface RecommendedKeyword {
  keyword: string
  grade: string
  search_volume: number
  trend_status: string
  category: string
  kei: number
  recommendation_reason: string
  priority: number
}

interface RecommendedKeywordsData {
  status: string
  date: string
  keywords: RecommendedKeyword[]
  count: number
  summary: {
    total_s_grade: number
    total_a_grade: number
    rising_count: number
  }
  tips: string[]
}

export default function RecommendedKeywords() {
  const navigate = useNavigate()

  const { data, isLoading } = useQuery<RecommendedKeywordsData>({
    queryKey: ['recommended-keywords'],
    queryFn: () => hudApi.getRecommendedKeywords(),
    refetchInterval: 600000, // 10분마다 갱신
    retry: 1,
  })

  if (isLoading) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 animate-pulse">
        <div className="h-6 bg-muted rounded w-1/3 mb-4" />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-12 bg-muted rounded" />
          ))}
        </div>
      </div>
    )
  }

  if (!data || data.keywords.length === 0) {
    return (
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <span className="text-xl">🎯</span>
          오늘의 추천 키워드
        </h3>
        <div className="text-center py-6 text-muted-foreground">
          <p className="text-4xl mb-2">📭</p>
          <p>아직 추천할 키워드가 없습니다</p>
          <button
            onClick={() => navigate('/pathfinder')}
            className="mt-3 text-sm text-primary hover:underline"
          >
            키워드 발굴하러 가기 →
          </button>
        </div>
      </div>
    )
  }

  const getGradeBadge = (grade: string) => {
    const styles: Record<string, string> = {
      'S': 'bg-red-500 text-white',
      'A': 'bg-orange-500 text-white',
      'B': 'bg-blue-500 text-white',
      'C': 'bg-gray-500 text-white',
    }
    return styles[grade] || styles['C']
  }

  const getTrendIcon = (status: string) => {
    switch (status) {
      case 'rising': return '📈'
      case 'falling': return '📉'
      case 'stable': return '➡️'
      default: return ''
    }
  }

  return (
    <div className="bg-card border border-border rounded-lg p-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <span className="text-xl">🎯</span>
          오늘의 추천 키워드
        </h3>
        <button
          onClick={() => navigate('/pathfinder')}
          className="text-sm text-primary hover:underline"
        >
          전체 보기 →
        </button>
      </div>

      {/* 요약 통계 */}
      <div className="flex items-center gap-4 mb-4 text-sm">
        <span className="text-muted-foreground">
          S급 <span className="font-bold text-red-500">{data.summary.total_s_grade}</span>개
        </span>
        <span className="text-muted-foreground">
          A급 <span className="font-bold text-orange-500">{data.summary.total_a_grade}</span>개
        </span>
        <span className="text-muted-foreground">
          상승 <span className="font-bold text-green-500">{data.summary.rising_count}</span>개
        </span>
      </div>

      {/* 키워드 목록 */}
      <div className="space-y-2">
        {data.keywords.slice(0, 5).map((kw, idx) => (
          <div
            key={kw.keyword}
            className="flex items-center justify-between p-3 bg-muted/50 rounded-lg hover:bg-muted transition-colors cursor-pointer"
            onClick={() => navigate(`/pathfinder?search=${encodeURIComponent(kw.keyword)}`)}
          >
            <div className="flex items-center gap-3 min-w-0">
              <span className="text-lg font-bold text-muted-foreground w-6">
                {idx + 1}
              </span>
              <span className={`px-2 py-0.5 text-xs font-bold rounded ${getGradeBadge(kw.grade)}`}>
                {kw.grade}
              </span>
              <div className="min-w-0">
                <div className="font-medium truncate">
                  {kw.keyword}
                </div>
                <div className="text-xs text-muted-foreground truncate">
                  {kw.recommendation_reason}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3 text-right flex-shrink-0">
              <div>
                <div className="text-sm font-semibold">
                  {kw.search_volume?.toLocaleString() || 0}
                </div>
                <div className="text-xs text-muted-foreground">검색량</div>
              </div>
              {kw.trend_status && (
                <span className="text-xl" title={`트렌드: ${kw.trend_status}`}>
                  {getTrendIcon(kw.trend_status)}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 팁 */}
      {data.tips && data.tips.length > 0 && (
        <div className="mt-4 pt-4 border-t border-border">
          <p className="text-xs text-muted-foreground">
            💡 {data.tips[Math.floor(Math.random() * data.tips.length)]}
          </p>
        </div>
      )}
    </div>
  )
}

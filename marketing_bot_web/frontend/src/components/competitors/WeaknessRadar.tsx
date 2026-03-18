import { useQuery } from '@tanstack/react-query'
import { competitorsApi } from '@/services/api'
import { AlertTriangle, Radar, TrendingUp, Lightbulb, Building2, RefreshCw } from 'lucide-react'

interface WeaknessCategory {
  category: string
  label: string
  count: number
  color: string
  our_strength: string
  top_competitors: { name: string; count: number }[]
}

interface CompetitorBreakdown {
  competitor: string
  total_weaknesses: number
  main_weakness: {
    category: string
    label: string
    count: number
  }
  breakdown: Record<string, number>
}

interface Opportunity {
  weakness_category: string
  weakness_label: string
  frequency: number
  affected_competitors: number
  our_differentiation: string
  priority: 'high' | 'medium' | 'low'
}

interface ContentIdea {
  title: string
  angle: string
  platforms: string[]
  keywords: string[]
  hook: string
}

interface WeaknessRadarData {
  weakness_frequency: WeaknessCategory[]
  competitor_breakdown: CompetitorBreakdown[]
  opportunities: Opportunity[]
  content_ideas: ContentIdea[]
  summary: {
    total_reviews_analyzed: number
    total_weaknesses_found: number
    competitors_analyzed: number
    top_opportunity: Opportunity | null
  }
}

export default function WeaknessRadar() {
  const { data, isLoading, error, refetch, isRefetching } = useQuery<WeaknessRadarData>({
    queryKey: ['weakness-radar'],
    queryFn: competitorsApi.getWeaknessRadar,
  })

  if (isLoading) {
    return (
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          <span className="ml-3 text-muted-foreground">약점 레이더 분석 중...</span>
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
            경쟁사 리뷰 데이터가 부족할 수 있습니다.
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

  const { weakness_frequency, competitor_breakdown, opportunities, content_ideas, summary } = data
  const maxCount = Math.max(...weakness_frequency.map(w => w.count), 1)

  const priorityColors = {
    high: 'bg-red-500/10 text-red-500 border-red-500/30',
    medium: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/30',
    low: 'bg-blue-500/10 text-blue-500 border-blue-500/30',
  }

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <Radar className="w-5 h-5 text-primary" />
            약점 레이더
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            경쟁사 부정 리뷰에서 반복되는 약점을 분석하여 기회를 발굴합니다.
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
          <div className="text-2xl font-bold text-primary">{summary?.total_reviews_analyzed || 0}</div>
          <div className="text-sm text-muted-foreground">분석된 리뷰</div>
        </div>
        <div className="bg-card rounded-lg border border-border p-4">
          <div className="text-2xl font-bold text-red-500">{summary?.total_weaknesses_found || 0}</div>
          <div className="text-sm text-muted-foreground">발견된 약점</div>
        </div>
        <div className="bg-card rounded-lg border border-border p-4">
          <div className="text-2xl font-bold text-blue-500">{summary?.competitors_analyzed || 0}</div>
          <div className="text-sm text-muted-foreground">분석된 경쟁사</div>
        </div>
        <div className="bg-card rounded-lg border border-border p-4">
          <div className="text-2xl font-bold text-green-500">{opportunities?.length || 0}</div>
          <div className="text-sm text-muted-foreground">발굴된 기회</div>
        </div>
      </div>

      {/* 약점 빈도 시각화 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-bold flex items-center gap-2 mb-4">
          <AlertTriangle className="w-5 h-5 text-red-500" />
          카테고리별 약점 빈도
        </h3>
        {weakness_frequency && weakness_frequency.length > 0 ? (
          <div className="space-y-4">
            {weakness_frequency.map((weakness) => (
              <div key={weakness.category} className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: weakness.color }}
                    />
                    <span className="font-medium">{weakness.label}</span>
                    <span className="text-sm text-muted-foreground">
                      ({weakness.count}건)
                    </span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {weakness.top_competitors.slice(0, 2).map(c => c.name).join(', ')}
                  </div>
                </div>
                <div className="relative h-6 bg-muted rounded-full overflow-hidden">
                  <div
                    className="absolute inset-y-0 left-0 rounded-full transition-all duration-500"
                    style={{
                      width: `${(weakness.count / maxCount) * 100}%`,
                      backgroundColor: weakness.color,
                    }}
                  />
                  <div className="absolute inset-0 flex items-center px-3">
                    <span className="text-xs font-medium text-white drop-shadow">
                      {weakness.our_strength}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            분석된 약점이 없습니다
          </div>
        )}
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* 기회 발굴 */}
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-bold flex items-center gap-2 mb-4">
            <TrendingUp className="w-5 h-5 text-green-500" />
            차별화 기회
          </h3>
          {opportunities && opportunities.length > 0 ? (
            <div className="space-y-3">
              {opportunities.map((opp, idx) => (
                <div
                  key={idx}
                  className={`p-4 rounded-lg border ${priorityColors[opp.priority]}`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold">{opp.weakness_label}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${priorityColors[opp.priority]}`}>
                      {opp.priority === 'high' ? '높음' : opp.priority === 'medium' ? '보통' : '낮음'}
                    </span>
                  </div>
                  <p className="text-sm opacity-80 mb-2">
                    {opp.affected_competitors}개 경쟁사에서 {opp.frequency}건 발견
                  </p>
                  <div className="text-sm font-medium text-green-600 dark:text-green-400">
                    우리 강점: {opp.our_differentiation}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              발굴된 기회가 없습니다
            </div>
          )}
        </div>

        {/* 경쟁사별 약점 */}
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-bold flex items-center gap-2 mb-4">
            <Building2 className="w-5 h-5 text-blue-500" />
            경쟁사별 주요 약점
          </h3>
          {competitor_breakdown && competitor_breakdown.length > 0 ? (
            <div className="space-y-3 max-h-80 overflow-y-auto">
              {competitor_breakdown.map((comp, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-lg bg-muted/50 border border-border hover:bg-muted transition-colors"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium">{comp.competitor}</span>
                    <span className="text-sm text-red-500 font-medium">
                      {comp.total_weaknesses}건
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <span>주요 약점:</span>
                    <span className="px-2 py-0.5 bg-red-500/10 text-red-500 rounded">
                      {comp.main_weakness.label} ({comp.main_weakness.count})
                    </span>
                  </div>
                  {Object.keys(comp.breakdown).length > 1 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {Object.entries(comp.breakdown)
                        .filter(([label]) => label !== comp.main_weakness.label)
                        .slice(0, 3)
                        .map(([label, count]) => (
                          <span
                            key={label}
                            className="text-xs px-2 py-0.5 bg-muted rounded"
                          >
                            {label}: {count}
                          </span>
                        ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              분석된 경쟁사가 없습니다
            </div>
          )}
        </div>
      </div>

      {/* 콘텐츠 아이디어 */}
      {content_ideas && content_ideas.length > 0 && (
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-bold flex items-center gap-2 mb-4">
            <Lightbulb className="w-5 h-5 text-yellow-500" />
            콘텐츠 아이디어
          </h3>
          <div className="grid md:grid-cols-3 gap-4">
            {content_ideas.map((idea, idx) => (
              <div
                key={idx}
                className="p-4 rounded-lg border border-yellow-500/30 bg-yellow-500/5"
              >
                <h4 className="font-medium text-sm mb-2">{idea.title}</h4>
                <p className="text-xs text-muted-foreground mb-3 italic">
                  "{idea.hook}"
                </p>
                <div className="flex flex-wrap gap-1 mb-2">
                  {idea.platforms.map((platform) => (
                    <span
                      key={platform}
                      className="text-xs px-2 py-0.5 bg-primary/10 text-primary rounded"
                    >
                      {platform}
                    </span>
                  ))}
                </div>
                <div className="flex flex-wrap gap-1">
                  {idea.keywords.slice(0, 3).map((kw) => (
                    <span
                      key={kw}
                      className="text-xs px-2 py-0.5 bg-muted rounded"
                    >
                      #{kw}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

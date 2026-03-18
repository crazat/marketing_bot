import { useQuery } from '@tanstack/react-query'
import { battleApi, hudApi } from '@/services/api'
import {
  MapPin,
  Star,
  MessageSquare,
  TrendingUp,
  TrendingDown,
  CheckCircle,
  AlertTriangle,
  Image,
  Phone,
  Clock,
  RefreshCw
} from 'lucide-react'
import ErrorState from '@/components/ui/ErrorState'

type TrendType = 'up' | 'down' | 'stable'

export default function LocalSeoDashboard() {
  // 순위 키워드 데이터
  const { data: rankingKeywords, isLoading: keywordsLoading, isError: keywordsError, refetch } = useQuery({
    queryKey: ['ranking-keywords-seo'],
    queryFn: battleApi.getRankingKeywords,
    retry: 2,
  })

  // 시스템 상태 (마지막 스캔 시간 등)
  const { data: systemStatus } = useQuery({
    queryKey: ['system-status-seo'],
    queryFn: hudApi.getSystemStatus,
  })

  // 데이터 가공
  const processedData = (() => {
    if (!rankingKeywords) return null

    const keywords = rankingKeywords as any[]

    // 평균 순위 계산
    const rankedKeywords = keywords.filter(k => k.current_rank && k.current_rank <= 100)
    const avgRank = rankedKeywords.length > 0
      ? Math.round(rankedKeywords.reduce((sum, k) => sum + k.current_rank, 0) / rankedKeywords.length)
      : 0

    // 상위 키워드 (순위 있는 것만)
    const topKeywords = rankedKeywords
      .sort((a, b) => a.current_rank - b.current_rank)
      .slice(0, 5)
      .map(k => ({ keyword: k.keyword, rank: k.current_rank }))

    // 트렌드 분석
    const improvingCount = keywords.filter(k => k.rank_change > 0).length
    const decliningCount = keywords.filter(k => k.rank_change < 0).length
    const trend: TrendType = improvingCount > decliningCount ? 'up' : decliningCount > improvingCount ? 'down' : 'stable'

    // Top 10 진입 키워드
    const top10Count = rankedKeywords.filter(k => k.current_rank <= 10).length

    // 순위권 밖 키워드
    const outOfRankCount = keywords.filter(k => !k.current_rank || k.current_rank > 100).length

    return {
      avgRank,
      topKeywords,
      trend,
      totalKeywords: keywords.length,
      rankedCount: rankedKeywords.length,
      top10Count,
      outOfRankCount,
      improvingCount,
      decliningCount,
    }
  })()

  // 최적화 팁 생성
  const optimizationTips = (() => {
    const tips = []

    if (processedData) {
      // 순위 관련 팁
      if (processedData.avgRank > 20) {
        tips.push({
          category: '순위',
          status: 'warning' as const,
          message: `평균 순위 ${processedData.avgRank}위 - 개선 필요`,
          action: '키워드별 콘텐츠 최적화 권장',
          icon: TrendingDown,
        })
      } else if (processedData.avgRank > 0) {
        tips.push({
          category: '순위',
          status: 'good' as const,
          message: `평균 순위 ${processedData.avgRank}위 - 양호`,
          action: '현재 수준 유지',
          icon: TrendingUp,
        })
      }

      // 순위권 밖 키워드
      if (processedData.outOfRankCount > 0) {
        tips.push({
          category: '미노출 키워드',
          status: processedData.outOfRankCount > 5 ? 'critical' as const : 'warning' as const,
          message: `${processedData.outOfRankCount}개 키워드가 100위 밖`,
          action: '해당 키워드 콘텐츠 강화 필요',
          icon: AlertTriangle,
        })
      }

      // Top 10 키워드
      if (processedData.top10Count >= 5) {
        tips.push({
          category: 'Top 10',
          status: 'good' as const,
          message: `${processedData.top10Count}개 키워드 Top 10 진입`,
          action: '1위 달성 목표 설정 권장',
          icon: Star,
        })
      }
    }

    // 기본 팁
    tips.push({
      category: '리뷰 관리',
      status: 'warning' as const,
      message: '신규 리뷰에 24시간 내 응답 권장',
      action: '리뷰 응답 도우미 활용',
      icon: MessageSquare,
    })

    tips.push({
      category: '사진',
      status: 'warning' as const,
      message: '플레이스 사진 10장 이상 권장',
      action: '최근 시설/치료 사진 업로드',
      icon: Image,
    })

    tips.push({
      category: '영업시간',
      status: 'good' as const,
      message: '정확한 영업시간 설정 필수',
      action: '휴무일, 점심시간 명시',
      icon: Clock,
    })

    return tips
  })()

  const trendIcons = {
    up: <TrendingUp className="w-4 h-4 text-green-500" />,
    down: <TrendingDown className="w-4 h-4 text-red-500" />,
    stable: <CheckCircle className="w-4 h-4 text-blue-500" />,
  }

  const statusColors = {
    good: 'bg-green-500/10 border-green-500/30 text-green-500',
    warning: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-500',
    critical: 'bg-red-500/10 border-red-500/30 text-red-500',
  }

  if (keywordsLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="w-6 h-6 animate-spin text-primary" />
        <span className="ml-2 text-muted-foreground">Local SEO 데이터 로딩 중...</span>
      </div>
    )
  }

  if (keywordsError) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold flex items-center gap-2">
              <MapPin className="w-5 h-5 text-primary" />
              Local SEO 대시보드
            </h2>
          </div>
        </div>
        <ErrorState
          title="데이터 로드 실패"
          message="Local SEO 데이터를 불러오는데 실패했습니다."
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <MapPin className="w-5 h-5 text-primary" />
            Local SEO 대시보드
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            지역 검색 노출 현황 및 최적화 가이드
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 px-3 py-2 bg-muted rounded-lg hover:bg-muted/80"
        >
          <RefreshCw className="w-4 h-4" />
          새로고침
        </button>
      </div>

      {/* 플랫폼별 현황 */}
      <div className="grid md:grid-cols-3 gap-4">
        {/* 네이버 플레이스 */}
        <div className="bg-card rounded-lg border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-10 h-10 bg-green-500/20 rounded-lg flex items-center justify-center">
                <span className="text-lg">N</span>
              </div>
              <span className="font-bold">네이버 플레이스</span>
            </div>
            {processedData && trendIcons[processedData.trend]}
          </div>
          {processedData ? (
            <>
              <div className="text-3xl font-bold mb-2">
                평균 {processedData.avgRank || '-'}위
              </div>
              <div className="text-sm text-muted-foreground mb-4">
                {processedData.rankedCount}개 키워드 추적 중
              </div>
              <div className="space-y-2">
                {processedData.topKeywords.slice(0, 3).map((kw, idx) => (
                  <div key={idx} className="flex justify-between text-sm">
                    <span className="truncate">{kw.keyword}</span>
                    <span className="font-medium">{kw.rank}위</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="text-center text-muted-foreground py-4">
              데이터 없음
            </div>
          )}
        </div>

      </div>

      {/* 통계 카드 */}
      {processedData && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-card rounded-lg border border-border p-4">
            <div className="flex items-center gap-2 mb-2">
              <Star className="w-4 h-4 text-yellow-500" />
              <span className="text-sm text-muted-foreground">Top 10 키워드</span>
            </div>
            <div className="text-2xl font-bold text-yellow-500">{processedData.top10Count}</div>
          </div>
          <div className="bg-card rounded-lg border border-border p-4">
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp className="w-4 h-4 text-green-500" />
              <span className="text-sm text-muted-foreground">순위 상승</span>
            </div>
            <div className="text-2xl font-bold text-green-500">{processedData.improvingCount}</div>
          </div>
          <div className="bg-card rounded-lg border border-border p-4">
            <div className="flex items-center gap-2 mb-2">
              <TrendingDown className="w-4 h-4 text-red-500" />
              <span className="text-sm text-muted-foreground">순위 하락</span>
            </div>
            <div className="text-2xl font-bold text-red-500">{processedData.decliningCount}</div>
          </div>
          <div className="bg-card rounded-lg border border-border p-4">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-4 h-4 text-orange-500" />
              <span className="text-sm text-muted-foreground">순위권 밖</span>
            </div>
            <div className="text-2xl font-bold text-orange-500">{processedData.outOfRankCount}</div>
          </div>
        </div>
      )}

      {/* NAP 일관성 체크 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="font-bold mb-4 flex items-center gap-2">
          <Phone className="w-5 h-5" />
          NAP 일관성 체크리스트
        </h3>
        <p className="text-sm text-muted-foreground mb-4">
          Name(이름), Address(주소), Phone(전화번호)가 모든 플랫폼에서 동일해야 합니다.
        </p>
        <div className="grid md:grid-cols-3 gap-4">
          <div className="flex items-center gap-3 p-3 bg-green-500/10 rounded-lg">
            <CheckCircle className="w-5 h-5 text-green-500" />
            <div>
              <div className="font-medium">이름 (Name)</div>
              <div className="text-sm text-muted-foreground">규림한의원</div>
            </div>
          </div>
          <div className="flex items-center gap-3 p-3 bg-green-500/10 rounded-lg">
            <CheckCircle className="w-5 h-5 text-green-500" />
            <div>
              <div className="font-medium">주소 (Address)</div>
              <div className="text-sm text-muted-foreground">청주시 흥덕구 ...</div>
            </div>
          </div>
          <div className="flex items-center gap-3 p-3 bg-green-500/10 rounded-lg">
            <CheckCircle className="w-5 h-5 text-green-500" />
            <div>
              <div className="font-medium">전화번호 (Phone)</div>
              <div className="text-sm text-muted-foreground">043-XXX-XXXX</div>
            </div>
          </div>
        </div>
      </div>

      {/* 최적화 팁 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="font-bold mb-4">최적화 체크리스트</h3>
        <div className="space-y-3">
          {optimizationTips.map((tip, idx) => (
            <div
              key={idx}
              className={`flex items-start gap-3 p-4 rounded-lg border ${statusColors[tip.status]}`}
            >
              <tip.icon className="w-5 h-5 mt-0.5" />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{tip.category}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    tip.status === 'good' ? 'bg-green-500/20' :
                    tip.status === 'warning' ? 'bg-yellow-500/20' :
                    'bg-red-500/20'
                  }`}>
                    {tip.status === 'good' ? '양호' : tip.status === 'warning' ? '주의' : '개선 필요'}
                  </span>
                </div>
                <p className="text-sm opacity-80 mt-1">{tip.message}</p>
                <p className="text-sm opacity-60 mt-1">추천: {tip.action}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 마지막 스캔 시간 */}
      {systemStatus?.last_rank_check && (
        <div className="text-center text-sm text-muted-foreground">
          마지막 순위 스캔: {new Date(systemStatus.last_rank_check).toLocaleString('ko-KR')}
        </div>
      )}
    </div>
  )
}

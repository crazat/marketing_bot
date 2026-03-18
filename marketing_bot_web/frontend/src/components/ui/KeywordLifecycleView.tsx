/**
 * [Phase D-3] Keyword Lifecycle View
 * 키워드의 전체 여정을 타임라인 형태로 시각화
 * 발굴 → 추적 → 바이럴 → 순위 변화 → 리드 발생
 */

import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  X,
  Search,
  Target,
  MessageSquare,
  TrendingUp,
  TrendingDown,
  Users,
  Calendar,
  CheckCircle2,
  Clock,
  Loader2,
  ExternalLink,
  ChevronRight,
} from 'lucide-react'
import { pathfinderApi, battleApi, viralApi, leadsApi } from '@/services/api'
import Button, { IconButton } from '@/components/ui/Button'

interface KeywordLifecycleViewProps {
  /** 조회할 키워드 */
  keyword: string
  /** 닫기 콜백 */
  onClose: () => void
}

interface TimelineEvent {
  id: string
  type: 'discovery' | 'tracking' | 'viral' | 'rank_change' | 'lead'
  date: string
  title: string
  description: string
  icon: React.ReactNode
  color: string
  link?: string
  metadata?: Record<string, any>
}

export default function KeywordLifecycleView({
  keyword,
  onClose,
}: KeywordLifecycleViewProps) {
  const navigate = useNavigate()

  // 키워드 인사이트 (발굴 정보)
  const { data: insightData, isLoading: insightLoading } = useQuery({
    queryKey: ['lifecycle-insight', keyword],
    queryFn: async () => {
      const data = await pathfinderApi.getKeywords({ limit: 500 })
      const keywords = data?.keywords || []
      return keywords.find((k: any) => k.keyword === keyword)
    },
    enabled: keyword.length > 0,
    staleTime: 60000,
  })

  // 순위 히스토리
  const { data: rankHistory, isLoading: rankLoading } = useQuery({
    queryKey: ['lifecycle-rank', keyword],
    queryFn: () => battleApi.getRankingTrends(30, keyword),
    enabled: keyword.length > 0,
    staleTime: 60000,
  })

  // 바이럴 콘텐츠
  const { data: viralData, isLoading: viralLoading } = useQuery({
    queryKey: ['lifecycle-viral', keyword],
    queryFn: async () => {
      const data = await viralApi.getTargets('', undefined, 100, { search: keyword })
      const targets = data?.targets || []
      return targets.filter((t: any) =>
        t.title?.toLowerCase().includes(keyword.toLowerCase()) ||
        t.matched_keyword?.toLowerCase().includes(keyword.toLowerCase())
      )
    },
    enabled: keyword.length > 0,
    staleTime: 60000,
  })

  // 리드 데이터
  const { data: leadsData, isLoading: leadsLoading } = useQuery({
    queryKey: ['lifecycle-leads', keyword],
    queryFn: async () => {
      const [naver, youtube] = await Promise.all([
        leadsApi.getNaverLeads({ limit: 100 }).catch(() => []),
        leadsApi.getYoutubeLeads({ limit: 100 }).catch(() => []),
      ])
      const allLeads = [...(naver || []), ...(youtube || [])]
      return allLeads.filter((l: any) =>
        l.title?.toLowerCase().includes(keyword.toLowerCase()) ||
        l.matched_keywords?.some((k: string) => k.toLowerCase().includes(keyword.toLowerCase())) ||
        l.source_keyword?.toLowerCase().includes(keyword.toLowerCase())
      )
    },
    enabled: keyword.length > 0,
    staleTime: 60000,
  })

  const isLoading = insightLoading || rankLoading || viralLoading || leadsLoading

  // 타임라인 이벤트 생성
  const buildTimeline = (): TimelineEvent[] => {
    const events: TimelineEvent[] = []

    // 1. 발굴 이벤트
    if (insightData) {
      events.push({
        id: 'discovery',
        type: 'discovery',
        date: insightData.discovered_at || insightData.created_at || '알 수 없음',
        title: '키워드 발굴',
        description: `${insightData.source || 'Pathfinder'}에서 발굴됨 · 등급: ${insightData.grade || 'N/A'}`,
        icon: <Search className="w-4 h-4" />,
        color: 'blue',
        link: `/pathfinder?keyword=${encodeURIComponent(keyword)}`,
        metadata: {
          grade: insightData.grade,
          searchVolume: insightData.search_volume,
          source: insightData.source,
        },
      })
    }

    // 2. 추적 시작 이벤트 (rank_history의 첫 기록)
    const trends = rankHistory?.trends || []
    if (trends.length > 0) {
      const firstEntry = trends[trends.length - 1] // 가장 오래된 기록
      events.push({
        id: 'tracking-start',
        type: 'tracking',
        date: firstEntry.date || '알 수 없음',
        title: '순위 추적 시작',
        description: `초기 순위: ${firstEntry.rank || '순위권 외'}위`,
        icon: <Target className="w-4 h-4" />,
        color: 'purple',
        link: `/battle?keyword=${encodeURIComponent(keyword)}&tab=trends`,
        metadata: {
          initialRank: firstEntry.rank,
        },
      })
    }

    // 3. 바이럴 콘텐츠 이벤트
    const viralTargets = viralData || []
    viralTargets.forEach((target: any, idx: number) => {
      if (idx < 5) { // 최대 5개만 표시
        events.push({
          id: `viral-${target.id}`,
          type: 'viral',
          date: target.discovered_at || target.created_at || '알 수 없음',
          title: '바이럴 콘텐츠 발견',
          description: `${target.platform}: ${target.title?.slice(0, 40)}...`,
          icon: <MessageSquare className="w-4 h-4" />,
          color: 'orange',
          link: `/viral?search=${encodeURIComponent(keyword)}`,
          metadata: {
            platform: target.platform,
            status: target.status,
          },
        })
      }
    })

    // 4. 주요 순위 변화 이벤트 (5위 이상 변동)
    trends.forEach((entry: any, idx: number) => {
      if (idx > 0 && idx < trends.length - 1) {
        const prevEntry = trends[idx + 1]
        const rankChange = (prevEntry?.rank || 100) - (entry?.rank || 100)
        if (Math.abs(rankChange) >= 5) {
          events.push({
            id: `rank-${idx}`,
            type: 'rank_change',
            date: entry.date || '알 수 없음',
            title: rankChange > 0 ? '순위 급상승' : '순위 급하락',
            description: `${prevEntry?.rank || '?'}위 → ${entry?.rank || '?'}위 (${rankChange > 0 ? '+' : ''}${rankChange})`,
            icon: rankChange > 0 ?
              <TrendingUp className="w-4 h-4" /> :
              <TrendingDown className="w-4 h-4" />,
            color: rankChange > 0 ? 'green' : 'red',
            link: `/battle?keyword=${encodeURIComponent(keyword)}&tab=trends`,
            metadata: {
              fromRank: prevEntry?.rank,
              toRank: entry?.rank,
              change: rankChange,
            },
          })
        }
      }
    })

    // 5. 리드 발생 이벤트
    const leads = leadsData || []
    leads.forEach((lead: any, idx: number) => {
      if (idx < 3) { // 최대 3개만 표시
        events.push({
          id: `lead-${lead.id}`,
          type: 'lead',
          date: lead.collected_at || lead.created_at || '알 수 없음',
          title: `리드 발생 (${lead.platform})`,
          description: `${lead.grade === 'hot' ? '🔥 Hot' : lead.grade === 'warm' ? '🌡 Warm' : '❄️ Cold'} - ${lead.title?.slice(0, 30)}...`,
          icon: <Users className="w-4 h-4" />,
          color: lead.grade === 'hot' ? 'red' : lead.grade === 'warm' ? 'yellow' : 'gray',
          link: `/leads?keyword=${encodeURIComponent(keyword)}`,
          metadata: {
            platform: lead.platform,
            grade: lead.grade,
            status: lead.status,
          },
        })
      }
    })

    // 날짜순 정렬 (최신 → 과거)
    return events.sort((a, b) => {
      const dateA = new Date(a.date).getTime()
      const dateB = new Date(b.date).getTime()
      if (isNaN(dateA)) return 1
      if (isNaN(dateB)) return -1
      return dateB - dateA
    })
  }

  const timeline = buildTimeline()

  // 통계 요약
  const stats = {
    totalViral: viralData?.length || 0,
    totalLeads: leadsData?.length || 0,
    hotLeads: leadsData?.filter((l: any) => l.grade === 'hot').length || 0,
    currentRank: rankHistory?.trends?.[0]?.rank,
    rankTrend: rankHistory?.trends?.length > 1 ?
      (rankHistory.trends[1]?.rank || 100) - (rankHistory.trends[0]?.rank || 100) : 0,
  }

  const getColorClasses = (color: string) => {
    const colors: Record<string, { bg: string; border: string; text: string }> = {
      blue: { bg: 'bg-blue-500/20', border: 'border-blue-500', text: 'text-blue-500' },
      purple: { bg: 'bg-purple-500/20', border: 'border-purple-500', text: 'text-purple-500' },
      orange: { bg: 'bg-orange-500/20', border: 'border-orange-500', text: 'text-orange-500' },
      green: { bg: 'bg-green-500/20', border: 'border-green-500', text: 'text-green-500' },
      red: { bg: 'bg-red-500/20', border: 'border-red-500', text: 'text-red-500' },
      yellow: { bg: 'bg-yellow-500/20', border: 'border-yellow-500', text: 'text-yellow-500' },
      gray: { bg: 'bg-gray-500/20', border: 'border-gray-500', text: 'text-gray-500' },
    }
    return colors[color] || colors.gray
  }

  const formatDate = (dateStr: string) => {
    if (dateStr === '알 수 없음') return dateStr
    try {
      const date = new Date(dateStr)
      if (isNaN(date.getTime())) return dateStr
      return date.toLocaleDateString('ko-KR', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    } catch {
      return dateStr
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-card rounded-xl border border-border shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* 헤더 */}
        <div className="p-4 border-b border-border flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold flex items-center gap-2">
              <Calendar className="w-5 h-5 text-primary" />
              키워드 라이프사이클
            </h2>
            <p className="text-sm text-muted-foreground truncate mt-1">
              {keyword}
            </p>
          </div>
          <IconButton
            icon={<X className="w-5 h-5" />}
            onClick={onClose}
            title="닫기"
          />
        </div>

        {/* 통계 요약 */}
        <div className="p-4 border-b border-border bg-muted/30">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {/* 현재 순위 */}
            <div className="bg-card rounded-lg p-3 text-center border border-border">
              <div className={`text-2xl font-bold ${
                stats.currentRank ? (
                  stats.rankTrend > 0 ? 'text-green-500' :
                  stats.rankTrend < 0 ? 'text-red-500' : ''
                ) : 'text-muted-foreground'
              }`}>
                {stats.currentRank ? `${stats.currentRank}위` : '-'}
              </div>
              <div className="text-xs text-muted-foreground">현재 순위</div>
              {stats.rankTrend !== 0 && (
                <div className={`text-xs ${stats.rankTrend > 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {stats.rankTrend > 0 ? '▲' : '▼'} {Math.abs(stats.rankTrend)}
                </div>
              )}
            </div>

            {/* 바이럴 수 */}
            <div className="bg-card rounded-lg p-3 text-center border border-border">
              <div className="text-2xl font-bold text-orange-500">{stats.totalViral}</div>
              <div className="text-xs text-muted-foreground">바이럴 콘텐츠</div>
            </div>

            {/* 총 리드 */}
            <div className="bg-card rounded-lg p-3 text-center border border-border">
              <div className="text-2xl font-bold text-blue-500">{stats.totalLeads}</div>
              <div className="text-xs text-muted-foreground">발굴 리드</div>
            </div>

            {/* Hot 리드 */}
            <div className="bg-card rounded-lg p-3 text-center border border-border">
              <div className="text-2xl font-bold text-red-500">{stats.hotLeads}</div>
              <div className="text-xs text-muted-foreground">Hot 리드</div>
            </div>
          </div>
        </div>

        {/* 타임라인 */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-primary mb-3" />
              <p className="text-sm text-muted-foreground">라이프사이클 데이터 로딩 중...</p>
            </div>
          ) : timeline.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12">
              <Clock className="w-12 h-12 text-muted-foreground/50 mb-3" />
              <p className="font-medium mb-1">타임라인 데이터 없음</p>
              <p className="text-sm text-muted-foreground text-center">
                이 키워드에 대한 활동 기록이 아직 없습니다.<br />
                Pathfinder에서 키워드를 발굴하거나<br />
                Battle Intelligence에서 추적을 시작하세요.
              </p>
            </div>
          ) : (
            <div className="relative">
              {/* 타임라인 선 */}
              <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-border" />

              {/* 이벤트 목록 */}
              <div className="space-y-4">
                {timeline.map((event) => {
                  const colors = getColorClasses(event.color)
                  return (
                    <div key={event.id} className="relative flex gap-4">
                      {/* 아이콘 */}
                      <div className={`w-12 h-12 rounded-full flex items-center justify-center z-10 ${colors.bg} ${colors.text} border-2 ${colors.border}`}>
                        {event.icon}
                      </div>

                      {/* 컨텐츠 */}
                      <div className="flex-1 pb-4">
                        <div className="flex items-start justify-between">
                          <div>
                            <h4 className="font-medium">{event.title}</h4>
                            <p className="text-sm text-muted-foreground">{event.description}</p>
                          </div>
                          <span className="text-xs text-muted-foreground whitespace-nowrap ml-2">
                            {formatDate(event.date)}
                          </span>
                        </div>

                        {/* 링크 버튼 */}
                        {event.link && (
                          <Button
                            variant="ghost"
                            size="xs"
                            onClick={() => {
                              navigate(event.link!)
                              onClose()
                            }}
                            icon={<ChevronRight className="w-3 h-3" />}
                            iconPosition="right"
                            className="mt-2 text-primary p-0 h-auto"
                          >
                            상세 보기
                          </Button>
                        )}
                      </div>
                    </div>
                  )
                })}

                {/* 타임라인 끝 마커 */}
                <div className="relative flex items-center gap-4">
                  <div className="w-12 h-12 rounded-full flex items-center justify-center z-10 bg-muted border-2 border-border">
                    <CheckCircle2 className="w-4 h-4 text-muted-foreground" />
                  </div>
                  <div className="text-sm text-muted-foreground">
                    총 {timeline.length}개의 이벤트가 기록되었습니다
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 푸터 */}
        <div className="p-4 border-t border-border bg-muted/30">
          <div className="flex justify-between items-center">
            <span className="text-xs text-muted-foreground">
              최근 30일간의 활동 기록
            </span>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                navigate(`/pathfinder?keyword=${encodeURIComponent(keyword)}`)
                onClose()
              }}
              icon={<ExternalLink className="w-3 h-3" />}
              iconPosition="right"
            >
              Pathfinder에서 보기
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

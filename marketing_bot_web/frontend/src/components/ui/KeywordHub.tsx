/**
 * [Phase E-1] Keyword Hub
 * 키워드 중심의 모든 관련 데이터를 한눈에 볼 수 있는 통합 허브
 */

import { useState, useMemo } from 'react'
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
  Lightbulb,
  ExternalLink,
  Loader2,
  BarChart3,
  Zap,
  AlertTriangle,
  CheckCircle2,
  ArrowRight,
} from 'lucide-react'
import { pathfinderApi, battleApi, viralApi, leadsApi, qaApi, competitorsApi } from '@/services/api'
import Button, { IconButton } from '@/components/ui/Button'

interface KeywordHubProps {
  keyword: string
  onClose: () => void
}

type TabType = 'overview' | 'ranking' | 'viral' | 'leads' | 'actions'

export default function KeywordHub({ keyword, onClose }: KeywordHubProps) {
  const [activeTab, setActiveTab] = useState<TabType>('overview')
  const navigate = useNavigate()

  // 키워드 인사이트 (발굴 정보)
  const { data: insightData, isLoading: insightLoading } = useQuery({
    queryKey: ['hub-insight', keyword],
    queryFn: async () => {
      const data = await pathfinderApi.getKeywords({ limit: 500 })
      const keywords = data?.keywords || []
      return keywords.find((k: any) => k.keyword === keyword)
    },
    enabled: keyword.length > 0,
    staleTime: 60000,
  })

  // 순위 데이터
  const { data: rankData, isLoading: rankLoading } = useQuery({
    queryKey: ['hub-rank', keyword],
    queryFn: async () => {
      const [keywords, trends] = await Promise.all([
        battleApi.getRankingKeywords(),
        battleApi.getRankingTrends(30, keyword),
      ])
      const keywordInfo = keywords?.find((k: any) => k.keyword === keyword)
      return {
        info: keywordInfo,
        trends: trends?.trends || [],
        isTracking: !!keywordInfo,
      }
    },
    enabled: keyword.length > 0,
    staleTime: 60000,
  })

  // 바이럴 데이터
  const { data: viralData, isLoading: viralLoading } = useQuery({
    queryKey: ['hub-viral', keyword],
    queryFn: async () => {
      const data = await viralApi.getTargets('', undefined, 100, { search: keyword })
      const targets = data?.targets || []
      const filtered = targets.filter((t: any) =>
        t.title?.toLowerCase().includes(keyword.toLowerCase()) ||
        t.matched_keyword?.toLowerCase().includes(keyword.toLowerCase())
      )
      return {
        targets: filtered,
        total: filtered.length,
        byStatus: {
          pending: filtered.filter((t: any) => t.status === 'pending').length,
          completed: filtered.filter((t: any) => t.status === 'completed').length,
          skipped: filtered.filter((t: any) => t.status === 'skipped').length,
        },
        byPlatform: filtered.reduce((acc: Record<string, number>, t: any) => {
          acc[t.platform] = (acc[t.platform] || 0) + 1
          return acc
        }, {}),
      }
    },
    enabled: keyword.length > 0,
    staleTime: 60000,
  })

  // 리드 데이터
  const { data: leadsData, isLoading: leadsLoading } = useQuery({
    queryKey: ['hub-leads', keyword],
    queryFn: async () => {
      const [naver, youtube] = await Promise.all([
        leadsApi.getNaverLeads({ limit: 100 }).catch(() => []),
        leadsApi.getYoutubeLeads({ limit: 100 }).catch(() => []),
      ])
      const allLeads = [...(naver || []), ...(youtube || [])]
      const filtered = allLeads.filter((l: any) =>
        l.title?.toLowerCase().includes(keyword.toLowerCase()) ||
        l.matched_keywords?.some((k: string) => k.toLowerCase().includes(keyword.toLowerCase())) ||
        l.source_keyword?.toLowerCase().includes(keyword.toLowerCase())
      )
      return {
        leads: filtered,
        total: filtered.length,
        byGrade: {
          hot: filtered.filter((l: any) => l.grade === 'hot').length,
          warm: filtered.filter((l: any) => l.grade === 'warm').length,
          cold: filtered.filter((l: any) => l.grade === 'cold').length,
        },
        byStatus: {
          new: filtered.filter((l: any) => l.status === 'new').length,
          contacted: filtered.filter((l: any) => l.status === 'contacted').length,
          converted: filtered.filter((l: any) => l.status === 'converted').length,
        },
      }
    },
    enabled: keyword.length > 0,
    staleTime: 60000,
  })

  // Q&A 매칭
  const { data: qaData } = useQuery({
    queryKey: ['hub-qa', keyword],
    queryFn: () => qaApi.match(keyword, 5),
    enabled: keyword.length > 2,
    staleTime: 60000,
  })

  // 경쟁사 약점
  const { data: weaknessData } = useQuery({
    queryKey: ['hub-weakness', keyword],
    queryFn: async () => {
      const data = await competitorsApi.getWeaknesses(50)
      return (data || []).filter((w: any) =>
        w.opportunity_keywords?.toLowerCase().includes(keyword.toLowerCase()) ||
        w.description?.toLowerCase().includes(keyword.toLowerCase())
      )
    },
    enabled: keyword.length > 0,
    staleTime: 60000,
  })

  const isLoading = insightLoading || rankLoading || viralLoading || leadsLoading

  // 스마트 액션 생성
  const smartActions = useMemo(() => {
    const actions: Array<{
      id: string
      priority: 'critical' | 'high' | 'medium' | 'low'
      icon: React.ReactNode
      title: string
      description: string
      action: () => void
      actionLabel: string
    }> = []

    // Hot 리드 미응답
    const hotLeadsNew = leadsData?.leads?.filter(
      (l: any) => l.grade === 'hot' && l.status === 'new'
    ).length || 0
    if (hotLeadsNew > 0) {
      actions.push({
        id: 'hot-leads',
        priority: 'critical',
        icon: <Users className="w-4 h-4" />,
        title: `Hot 리드 ${hotLeadsNew}건 미응답`,
        description: '즉시 응답하여 전환율을 높이세요',
        action: () => navigate(`/leads?keyword=${encodeURIComponent(keyword)}&grade=hot`),
        actionLabel: '지금 응답',
      })
    }

    // 순위 하락
    const trends = rankData?.trends
    if (trends && trends.length >= 2) {
      const recent = trends[0]?.rank
      const prev = trends[1]?.rank
      if (recent && prev && recent > prev + 3) {
        actions.push({
          id: 'rank-drop',
          priority: 'high',
          icon: <TrendingDown className="w-4 h-4" />,
          title: `순위 ${prev - recent}위 하락`,
          description: `${prev}위 → ${recent}위. 바이럴 콘텐츠 강화 필요`,
          action: () => navigate(`/viral?keyword=${encodeURIComponent(keyword)}`),
          actionLabel: '바이럴 강화',
        })
      }
    }

    // 미처리 바이럴
    const pendingViral = viralData?.byStatus?.pending || 0
    if (pendingViral > 0) {
      actions.push({
        id: 'pending-viral',
        priority: 'medium',
        icon: <MessageSquare className="w-4 h-4" />,
        title: `미처리 바이럴 ${pendingViral}건`,
        description: '댓글 작성하여 노출을 높이세요',
        action: () => navigate(`/viral?keyword=${encodeURIComponent(keyword)}&status=pending`),
        actionLabel: '처리하기',
      })
    }

    // 순위 미추적
    if (!rankData?.isTracking && insightData) {
      actions.push({
        id: 'not-tracking',
        priority: 'medium',
        icon: <Target className="w-4 h-4" />,
        title: '순위 추적 미등록',
        description: '키워드 순위를 추적하여 성과를 측정하세요',
        action: () => navigate('/battle?tab=keywords'),
        actionLabel: '추적 시작',
      })
    }

    // 경쟁사 약점 활용
    const weaknessCount = weaknessData?.length || 0
    if (weaknessCount > 0) {
      actions.push({
        id: 'weakness',
        priority: 'low',
        icon: <Zap className="w-4 h-4" />,
        title: `경쟁사 약점 ${weaknessCount}건 발견`,
        description: '약점을 공략하는 콘텐츠를 제작하세요',
        action: () => navigate('/competitors?tab=weaknesses'),
        actionLabel: '약점 공략',
      })
    }

    // 우선순위순 정렬
    const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 }
    return actions.sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority])
  }, [rankData, viralData, leadsData, weaknessData, insightData, keyword, navigate])

  // 전체 통계
  const stats = {
    grade: insightData?.grade || '-',
    searchVolume: insightData?.search_volume || 0,
    currentRank: rankData?.info?.current_rank,
    rankChange: rankData?.info?.rank_change || 0,
    viralTotal: viralData?.total || 0,
    viralPending: viralData?.byStatus?.pending || 0,
    leadsTotal: leadsData?.total || 0,
    leadsHot: leadsData?.byGrade?.hot || 0,
    qaMatches: qaData?.matches?.length || 0,
    weaknesses: weaknessData?.length || 0,
  }

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'critical': return 'bg-red-500/20 border-red-500/50 text-red-500'
      case 'high': return 'bg-orange-500/20 border-orange-500/50 text-orange-500'
      case 'medium': return 'bg-yellow-500/20 border-yellow-500/50 text-yellow-500'
      default: return 'bg-blue-500/20 border-blue-500/50 text-blue-500'
    }
  }

  const tabs = [
    { id: 'overview' as const, label: '개요', icon: <BarChart3 className="w-4 h-4" /> },
    { id: 'ranking' as const, label: '순위', icon: <TrendingUp className="w-4 h-4" /> },
    { id: 'viral' as const, label: '바이럴', icon: <MessageSquare className="w-4 h-4" /> },
    { id: 'leads' as const, label: '리드', icon: <Users className="w-4 h-4" /> },
    { id: 'actions' as const, label: '액션', icon: <Lightbulb className="w-4 h-4" />, badge: smartActions.length },
  ]

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-card rounded-xl border border-border shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* 헤더 */}
        <div className="p-4 border-b border-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <Search className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h2 className="text-lg font-bold">Keyword Hub</h2>
                <p className="text-sm text-muted-foreground truncate max-w-md">{keyword}</p>
              </div>
            </div>
            <IconButton
              icon={<X className="w-5 h-5" />}
              onClick={onClose}
              title="닫기"
            />
          </div>

          {/* 탭 네비게이션 */}
          <div className="flex gap-1 mt-4 overflow-x-auto">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                  activeTab === tab.id
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted text-muted-foreground'
                }`}
              >
                {tab.icon}
                {tab.label}
                {tab.badge !== undefined && tab.badge > 0 && (
                  <span className={`px-1.5 py-0.5 rounded-full text-xs ${
                    activeTab === tab.id ? 'bg-primary-foreground/20' : 'bg-primary/20 text-primary'
                  }`}>
                    {tab.badge}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* 콘텐츠 */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-primary mb-3" />
              <p className="text-sm text-muted-foreground">데이터 로딩 중...</p>
            </div>
          ) : (
            <>
              {/* 개요 탭 */}
              {activeTab === 'overview' && (
                <div className="space-y-6">
                  {/* 핵심 지표 */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <StatCard
                      label="키워드 등급"
                      value={stats.grade}
                      color={stats.grade === 'A' ? 'text-green-500' : stats.grade === 'B' ? 'text-blue-500' : 'text-muted-foreground'}
                    />
                    <StatCard
                      label="현재 순위"
                      value={stats.currentRank ? `${stats.currentRank}위` : '미추적'}
                      subValue={stats.rankChange !== 0 ? `${stats.rankChange > 0 ? '▲' : '▼'}${Math.abs(stats.rankChange)}` : undefined}
                      color={stats.rankChange > 0 ? 'text-green-500' : stats.rankChange < 0 ? 'text-red-500' : ''}
                    />
                    <StatCard
                      label="바이럴"
                      value={`${stats.viralTotal}건`}
                      subValue={stats.viralPending > 0 ? `미처리 ${stats.viralPending}` : undefined}
                    />
                    <StatCard
                      label="리드"
                      value={`${stats.leadsTotal}건`}
                      subValue={stats.leadsHot > 0 ? `Hot ${stats.leadsHot}` : undefined}
                      color={stats.leadsHot > 0 ? 'text-red-500' : ''}
                    />
                  </div>

                  {/* 상세 정보 */}
                  <div className="grid md:grid-cols-2 gap-4">
                    {/* 발굴 정보 */}
                    <div className="bg-muted/30 rounded-lg p-4">
                      <h4 className="font-medium mb-3 flex items-center gap-2">
                        <Search className="w-4 h-4 text-primary" />
                        발굴 정보
                      </h4>
                      {insightData ? (
                        <div className="space-y-2 text-sm">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">등급</span>
                            <span className="font-medium">{insightData.grade || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">검색량</span>
                            <span className="font-medium">{insightData.search_volume?.toLocaleString() || '-'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">카테고리</span>
                            <span className="font-medium">{insightData.category || '-'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">발굴 소스</span>
                            <span className="font-medium">{insightData.source || 'Pathfinder'}</span>
                          </div>
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">발굴 정보 없음</p>
                      )}
                    </div>

                    {/* 순위 추적 */}
                    <div className="bg-muted/30 rounded-lg p-4">
                      <h4 className="font-medium mb-3 flex items-center gap-2">
                        <Target className="w-4 h-4 text-purple-500" />
                        순위 추적
                      </h4>
                      {rankData?.isTracking ? (
                        <div className="space-y-2 text-sm">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">현재 순위</span>
                            <span className="font-medium">{rankData.info?.current_rank || '-'}위</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">목표 순위</span>
                            <span className="font-medium">{rankData.info?.target_rank || '-'}위</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">변화</span>
                            <span className={`font-medium ${
                              rankData.info?.rank_change > 0 ? 'text-green-500' :
                              rankData.info?.rank_change < 0 ? 'text-red-500' : ''
                            }`}>
                              {rankData.info?.rank_change > 0 ? '+' : ''}{rankData.info?.rank_change || 0}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">데이터 포인트</span>
                            <span className="font-medium">{rankData.trends?.length || 0}개</span>
                          </div>
                        </div>
                      ) : (
                        <div className="text-center py-4">
                          <p className="text-sm text-muted-foreground mb-2">순위 추적 미등록</p>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => navigate('/battle?tab=keywords')}
                          >
                            추적 시작하기
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* 긴급 액션 */}
                  {smartActions.filter(a => a.priority === 'critical' || a.priority === 'high').length > 0 && (
                    <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-4">
                      <h4 className="font-medium mb-3 flex items-center gap-2 text-red-500">
                        <AlertTriangle className="w-4 h-4" />
                        긴급 대응 필요
                      </h4>
                      <div className="space-y-2">
                        {smartActions
                          .filter(a => a.priority === 'critical' || a.priority === 'high')
                          .slice(0, 2)
                          .map((action) => (
                            <div key={action.id} className="flex items-center justify-between bg-card rounded-lg p-3">
                              <div className="flex items-center gap-2">
                                <span className={getPriorityColor(action.priority) + ' p-1.5 rounded'}>
                                  {action.icon}
                                </span>
                                <div>
                                  <p className="text-sm font-medium">{action.title}</p>
                                  <p className="text-xs text-muted-foreground">{action.description}</p>
                                </div>
                              </div>
                              <Button
                                variant="primary"
                                size="xs"
                                onClick={action.action}
                              >
                                {action.actionLabel}
                              </Button>
                            </div>
                          ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* 순위 탭 */}
              {activeTab === 'ranking' && (
                <div className="space-y-4">
                  {rankData?.isTracking ? (
                    <>
                      {/* 순위 트렌드 미니 차트 (텍스트 기반) */}
                      <div className="bg-muted/30 rounded-lg p-4">
                        <h4 className="font-medium mb-3">최근 30일 순위 변화</h4>
                        <div className="space-y-1">
                          {rankData.trends?.slice(0, 10).map((t: any, idx: number) => (
                            <div key={idx} className="flex items-center gap-2 text-sm">
                              <span className="text-muted-foreground w-20">{t.date}</span>
                              <div className="flex-1 h-4 bg-muted rounded-full overflow-hidden">
                                <div
                                  className={`h-full ${t.rank <= 10 ? 'bg-green-500' : t.rank <= 20 ? 'bg-yellow-500' : 'bg-red-500'}`}
                                  style={{ width: `${Math.max(5, 100 - t.rank * 2)}%` }}
                                />
                              </div>
                              <span className="font-medium w-12 text-right">{t.rank}위</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      <Button
                        variant="outline"
                        fullWidth
                        onClick={() => navigate(`/battle?keyword=${encodeURIComponent(keyword)}&tab=trends`)}
                        icon={<ExternalLink className="w-4 h-4" />}
                        iconPosition="right"
                      >
                        Battle Intelligence에서 상세 보기
                      </Button>
                    </>
                  ) : (
                    <div className="text-center py-12">
                      <Target className="w-12 h-12 mx-auto mb-3 text-muted-foreground/50" />
                      <p className="font-medium mb-1">순위 추적 미등록</p>
                      <p className="text-sm text-muted-foreground mb-4">
                        이 키워드의 순위를 추적하여 성과를 측정하세요
                      </p>
                      <Button
                        variant="primary"
                        onClick={() => navigate('/battle?tab=keywords')}
                      >
                        추적 시작
                      </Button>
                    </div>
                  )}
                </div>
              )}

              {/* 바이럴 탭 */}
              {activeTab === 'viral' && (
                <div className="space-y-4">
                  {viralData && viralData.total > 0 ? (
                    <>
                      {/* 플랫폼별 현황 */}
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {Object.entries(viralData.byPlatform).map(([platform, count]) => (
                          <div key={platform} className="bg-muted/30 rounded-lg p-3 text-center">
                            <div className="text-lg font-bold">{count as number}</div>
                            <div className="text-xs text-muted-foreground">{platform}</div>
                          </div>
                        ))}
                      </div>

                      {/* 상태별 현황 */}
                      <div className="flex gap-4 p-3 bg-muted/30 rounded-lg">
                        <div className="flex-1 text-center">
                          <div className="text-lg font-bold text-yellow-500">{viralData.byStatus.pending}</div>
                          <div className="text-xs text-muted-foreground">미처리</div>
                        </div>
                        <div className="flex-1 text-center">
                          <div className="text-lg font-bold text-green-500">{viralData.byStatus.completed}</div>
                          <div className="text-xs text-muted-foreground">완료</div>
                        </div>
                        <div className="flex-1 text-center">
                          <div className="text-lg font-bold text-gray-500">{viralData.byStatus.skipped}</div>
                          <div className="text-xs text-muted-foreground">스킵</div>
                        </div>
                      </div>

                      {/* 최근 바이럴 목록 */}
                      <div className="space-y-2">
                        {viralData.targets.slice(0, 5).map((target: any) => (
                          <div key={target.id} className="flex items-center gap-3 p-3 bg-muted/30 rounded-lg">
                            <span className={`px-2 py-0.5 text-xs rounded ${
                              target.status === 'pending' ? 'bg-yellow-500/20 text-yellow-500' :
                              target.status === 'completed' ? 'bg-green-500/20 text-green-500' :
                              'bg-gray-500/20 text-gray-500'
                            }`}>
                              {target.status}
                            </span>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium truncate">{target.title}</p>
                              <p className="text-xs text-muted-foreground">{target.platform}</p>
                            </div>
                          </div>
                        ))}
                      </div>

                      <Button
                        variant="outline"
                        fullWidth
                        onClick={() => navigate(`/viral?keyword=${encodeURIComponent(keyword)}`)}
                        icon={<ExternalLink className="w-4 h-4" />}
                        iconPosition="right"
                      >
                        Viral Hunter에서 상세 보기
                      </Button>
                    </>
                  ) : (
                    <div className="text-center py-12">
                      <MessageSquare className="w-12 h-12 mx-auto mb-3 text-muted-foreground/50" />
                      <p className="font-medium mb-1">관련 바이럴 없음</p>
                      <p className="text-sm text-muted-foreground mb-4">
                        이 키워드와 관련된 바이럴 콘텐츠가 없습니다
                      </p>
                      <Button
                        variant="primary"
                        onClick={() => navigate('/viral')}
                      >
                        바이럴 수집
                      </Button>
                    </div>
                  )}
                </div>
              )}

              {/* 리드 탭 */}
              {activeTab === 'leads' && (
                <div className="space-y-4">
                  {leadsData && leadsData.total > 0 ? (
                    <>
                      {/* 등급별 현황 */}
                      <div className="grid grid-cols-3 gap-3">
                        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-center">
                          <div className="text-2xl font-bold text-red-500">{leadsData.byGrade.hot}</div>
                          <div className="text-xs text-muted-foreground">Hot</div>
                        </div>
                        <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3 text-center">
                          <div className="text-2xl font-bold text-yellow-500">{leadsData.byGrade.warm}</div>
                          <div className="text-xs text-muted-foreground">Warm</div>
                        </div>
                        <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3 text-center">
                          <div className="text-2xl font-bold text-blue-500">{leadsData.byGrade.cold}</div>
                          <div className="text-xs text-muted-foreground">Cold</div>
                        </div>
                      </div>

                      {/* 최근 리드 목록 */}
                      <div className="space-y-2">
                        {leadsData.leads.slice(0, 5).map((lead: any) => (
                          <div key={lead.id} className="flex items-center gap-3 p-3 bg-muted/30 rounded-lg">
                            <span className={`text-lg ${
                              lead.grade === 'hot' ? '' : lead.grade === 'warm' ? '' : ''
                            }`}>
                              {lead.grade === 'hot' ? '🔥' : lead.grade === 'warm' ? '🌡️' : '❄️'}
                            </span>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium truncate">{lead.title}</p>
                              <p className="text-xs text-muted-foreground">{lead.platform} · {lead.status}</p>
                            </div>
                          </div>
                        ))}
                      </div>

                      <Button
                        variant="outline"
                        fullWidth
                        onClick={() => navigate(`/leads?keyword=${encodeURIComponent(keyword)}`)}
                        icon={<ExternalLink className="w-4 h-4" />}
                        iconPosition="right"
                      >
                        Lead Manager에서 상세 보기
                      </Button>
                    </>
                  ) : (
                    <div className="text-center py-12">
                      <Users className="w-12 h-12 mx-auto mb-3 text-muted-foreground/50" />
                      <p className="font-medium mb-1">관련 리드 없음</p>
                      <p className="text-sm text-muted-foreground">
                        이 키워드와 관련된 리드가 없습니다
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* 액션 탭 */}
              {activeTab === 'actions' && (
                <div className="space-y-4">
                  {smartActions.length > 0 ? (
                    <>
                      <p className="text-sm text-muted-foreground">
                        현재 상황을 분석하여 추천하는 다음 행동입니다
                      </p>
                      <div className="space-y-3">
                        {smartActions.map((action) => (
                          <div
                            key={action.id}
                            className={`rounded-lg border p-4 ${getPriorityColor(action.priority).replace('text-', 'border-').split(' ')[1]} bg-card`}
                          >
                            <div className="flex items-start justify-between">
                              <div className="flex items-start gap-3">
                                <span className={`p-2 rounded-lg ${getPriorityColor(action.priority)}`}>
                                  {action.icon}
                                </span>
                                <div>
                                  <div className="flex items-center gap-2">
                                    <span className={`text-xs px-1.5 py-0.5 rounded ${getPriorityColor(action.priority)}`}>
                                      {action.priority === 'critical' ? '긴급' :
                                       action.priority === 'high' ? '높음' :
                                       action.priority === 'medium' ? '중간' : '낮음'}
                                    </span>
                                    <h4 className="font-medium">{action.title}</h4>
                                  </div>
                                  <p className="text-sm text-muted-foreground mt-1">{action.description}</p>
                                </div>
                              </div>
                              <Button
                                variant="primary"
                                size="sm"
                                onClick={action.action}
                                icon={<ArrowRight className="w-3 h-3" />}
                                iconPosition="right"
                              >
                                {action.actionLabel}
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="text-center py-12">
                      <CheckCircle2 className="w-12 h-12 mx-auto mb-3 text-green-500" />
                      <p className="font-medium mb-1">모든 상황 양호</p>
                      <p className="text-sm text-muted-foreground">
                        현재 추천할 액션이 없습니다
                      </p>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* 푸터 */}
        <div className="p-4 border-t border-border bg-muted/30">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              Q&A 매칭 {stats.qaMatches}건 · 경쟁사 약점 {stats.weaknesses}건
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
              Pathfinder에서 분석
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

// 통계 카드 컴포넌트
function StatCard({
  label,
  value,
  subValue,
  color = '',
}: {
  label: string
  value: string
  subValue?: string
  color?: string
}) {
  return (
    <div className="bg-muted/30 rounded-lg p-3 text-center">
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
      {subValue && (
        <div className={`text-xs mt-1 ${color}`}>{subValue}</div>
      )}
    </div>
  )
}

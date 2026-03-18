/**
 * [Phase D-2] Context Insight Panel
 * 선택한 키워드와 관련된 다양한 데이터를 사이드 패널로 표시
 */

import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  X,
  TrendingUp,
  MessageSquare,
  Users,
  MessageCircle,
  Target,
  Lightbulb,
  ExternalLink,
  Loader2,
  ChevronRight,
} from 'lucide-react'
import { viralApi, leadsApi, qaApi, competitorsApi, battleApi } from '@/services/api'
import Button, { IconButton } from '@/components/ui/Button'

interface ContextInsightPanelProps {
  /** 선택된 키워드 */
  keyword: string
  /** 패널 닫기 콜백 */
  onClose: () => void
  /** 추가 컨텍스트 정보 */
  context?: {
    currentRank?: number
    targetRank?: number
    trend?: 'up' | 'down' | 'stable'
  }
  /** 라이프사이클 뷰 열기 콜백 (선택) */
  onShowLifecycle?: () => void
}

export default function ContextInsightPanel({
  keyword,
  onClose,
  context,
  onShowLifecycle,
}: ContextInsightPanelProps) {
  const navigate = useNavigate()

  // 관련 바이럴 타겟 조회 (키워드 매칭)
  const { data: viralData, isLoading: viralLoading } = useQuery({
    queryKey: ['context-viral', keyword],
    queryFn: async () => {
      // viralApi.getTargets(status, category, limit, filters)
      const data = await viralApi.getTargets('', undefined, 100, { search: keyword })
      // 키워드가 포함된 타겟 필터링
      const targets = data?.targets || []
      return targets.filter((t: any) =>
        t.title?.toLowerCase().includes(keyword.toLowerCase()) ||
        t.matched_keyword?.toLowerCase().includes(keyword.toLowerCase())
      ).slice(0, 5)
    },
    enabled: keyword.length > 0,
    staleTime: 60000,
  })

  // 관련 리드 조회
  const { data: leadsData, isLoading: leadsLoading } = useQuery({
    queryKey: ['context-leads', keyword],
    queryFn: async () => {
      // 여러 플랫폼에서 키워드 관련 리드 검색
      const [naver, youtube] = await Promise.all([
        leadsApi.getNaverLeads({ limit: 50 }).catch(() => []),
        leadsApi.getYoutubeLeads({ limit: 50 }).catch(() => []),
      ])
      const allLeads = [...(naver || []), ...(youtube || [])]
      // 키워드 관련 필터링
      return allLeads.filter((l: any) =>
        l.title?.toLowerCase().includes(keyword.toLowerCase()) ||
        l.matched_keywords?.some((k: string) => k.toLowerCase().includes(keyword.toLowerCase())) ||
        l.source_keyword?.toLowerCase().includes(keyword.toLowerCase())
      ).slice(0, 5)
    },
    enabled: keyword.length > 0,
    staleTime: 60000,
  })

  // Q&A 매칭
  const { data: qaData, isLoading: qaLoading } = useQuery({
    queryKey: ['context-qa', keyword],
    queryFn: () => qaApi.match(keyword, 3),
    enabled: keyword.length > 2,
    staleTime: 60000,
  })

  // 경쟁사 약점 (키워드 관련)
  const { data: weaknessData, isLoading: weaknessLoading } = useQuery({
    queryKey: ['context-weakness', keyword],
    queryFn: async () => {
      const data = await competitorsApi.getWeaknesses(50)
      // 키워드 관련 약점 필터링
      return (data || []).filter((w: any) =>
        w.opportunity_keywords?.toLowerCase().includes(keyword.toLowerCase()) ||
        w.description?.toLowerCase().includes(keyword.toLowerCase())
      ).slice(0, 3)
    },
    enabled: keyword.length > 0,
    staleTime: 60000,
  })

  // 순위 히스토리 (ContextInsightPanel에 이미 context prop으로 전달됨)
  // 추가 데이터 필요 시 활용 가능
  useQuery({
    queryKey: ['context-rank-history', keyword],
    queryFn: () => battleApi.getRankingTrends(7, keyword),
    enabled: keyword.length > 0,
    staleTime: 60000,
  })

  const viralCount = viralData?.length || 0
  const leadsCount = leadsData?.length || 0
  const qaCount = qaData?.matches?.length || 0
  const weaknessCount = weaknessData?.length || 0

  // Hot 리드 수
  const hotLeads = leadsData?.filter((l: any) => l.grade === 'hot').length || 0

  // 추천 액션 생성
  const getRecommendedActions = () => {
    const actions: { icon: React.ReactNode; text: string; priority: 'high' | 'medium' | 'low'; action: () => void }[] = []

    // Hot 리드가 있으면 최우선
    if (hotLeads > 0) {
      actions.push({
        icon: <Users className="w-4 h-4 text-red-500" />,
        text: `Hot 리드 ${hotLeads}건 즉시 응답 필요`,
        priority: 'high',
        action: () => navigate(`/leads?keyword=${encodeURIComponent(keyword)}`),
      })
    }

    // 순위 하락 시 바이럴 콘텐츠 제작 권장
    if (context?.trend === 'down') {
      actions.push({
        icon: <MessageSquare className="w-4 h-4 text-orange-500" />,
        text: '순위 하락 중 - 바이럴 콘텐츠 강화 필요',
        priority: 'high',
        action: () => navigate(`/viral?keyword=${encodeURIComponent(keyword)}`),
      })
    }

    // 미처리 바이럴 타겟
    const pendingViral = viralData?.filter((v: any) => v.status === 'pending').length || 0
    if (pendingViral > 0) {
      actions.push({
        icon: <MessageSquare className="w-4 h-4 text-blue-500" />,
        text: `미처리 바이럴 ${pendingViral}건 검토 필요`,
        priority: 'medium',
        action: () => navigate(`/viral?keyword=${encodeURIComponent(keyword)}`),
      })
    }

    // 경쟁사 약점 발견
    if (weaknessCount > 0) {
      actions.push({
        icon: <Target className="w-4 h-4 text-purple-500" />,
        text: `경쟁사 약점 ${weaknessCount}건 - 공략 콘텐츠 제작 가능`,
        priority: 'medium',
        action: () => navigate('/competitors?tab=weaknesses'),
      })
    }

    return actions.sort((a, b) => {
      const priorityOrder = { high: 0, medium: 1, low: 2 }
      return priorityOrder[a.priority] - priorityOrder[b.priority]
    })
  }

  const recommendedActions = getRecommendedActions()

  return (
    <div className="fixed right-0 top-0 h-full w-80 bg-card border-l border-border shadow-xl z-40 overflow-y-auto">
      {/* 헤더 */}
      <div className="sticky top-0 bg-card border-b border-border p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-sm text-muted-foreground">키워드 인사이트</h3>
            <p className="font-bold truncate" title={keyword}>{keyword}</p>
          </div>
          <IconButton
            icon={<X className="w-5 h-5" />}
            onClick={onClose}
            title="닫기"
          />
        </div>

        {/* 현재 상태 요약 */}
        {context && (
          <div className="flex items-center gap-3 mt-3 p-2 bg-muted/50 rounded-lg">
            {context.currentRank && (
              <div className="text-center">
                <div className="text-lg font-bold">{context.currentRank}위</div>
                <div className="text-[10px] text-muted-foreground">현재 순위</div>
              </div>
            )}
            {context.trend && (
              <div className={`px-2 py-1 rounded text-xs font-medium ${
                context.trend === 'up' ? 'bg-green-500/20 text-green-500' :
                context.trend === 'down' ? 'bg-red-500/20 text-red-500' :
                'bg-gray-500/20 text-gray-500'
              }`}>
                {context.trend === 'up' ? '📈 상승' : context.trend === 'down' ? '📉 하락' : '➖ 유지'}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 추천 액션 */}
      {recommendedActions.length > 0 && (
        <div className="p-4 border-b border-border">
          <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Lightbulb className="w-4 h-4 text-yellow-500" />
            추천 액션
          </h4>
          <div className="space-y-2">
            {recommendedActions.slice(0, 3).map((action, idx) => (
              <Button
                key={idx}
                variant={action.priority === 'high' ? 'danger' : 'ghost'}
                fullWidth
                onClick={action.action}
                icon={<ChevronRight className="w-4 h-4 text-muted-foreground" />}
                iconPosition="right"
                className={`p-2 justify-start text-left ${
                  action.priority === 'high'
                    ? 'bg-red-500/10 hover:bg-red-500/20 border border-red-500/30'
                    : 'bg-muted/50 hover:bg-muted'
                }`}
              >
                <span className="flex items-center gap-2 flex-1">
                  {action.icon}
                  <span className="text-xs">{action.text}</span>
                </span>
              </Button>
            ))}
          </div>
        </div>
      )}

      {/* 관련 데이터 섹션 */}
      <div className="p-4 space-y-4">
        {/* 바이럴 타겟 */}
        <InsightSection
          title="관련 바이럴"
          icon={<MessageSquare className="w-4 h-4 text-orange-500" />}
          count={viralCount}
          isLoading={viralLoading}
          onViewAll={() => navigate(`/viral?keyword=${encodeURIComponent(keyword)}`)}
        >
          {viralData?.map((target: any, idx: number) => (
            <div key={idx} className="text-xs p-2 bg-muted/50 rounded">
              <div className="font-medium truncate">{target.title}</div>
              <div className="text-muted-foreground">{target.platform} · {target.status}</div>
            </div>
          ))}
        </InsightSection>

        {/* 관련 리드 */}
        <InsightSection
          title="관련 리드"
          icon={<Users className="w-4 h-4 text-green-500" />}
          count={leadsCount}
          badge={hotLeads > 0 ? `${hotLeads} Hot` : undefined}
          isLoading={leadsLoading}
          onViewAll={() => navigate(`/leads?keyword=${encodeURIComponent(keyword)}`)}
        >
          {leadsData?.map((lead: any, idx: number) => (
            <div key={idx} className="text-xs p-2 bg-muted/50 rounded">
              <div className="flex items-center gap-2">
                {lead.grade === 'hot' && <span className="text-red-500">🔥</span>}
                <span className="font-medium truncate">{lead.title}</span>
              </div>
              <div className="text-muted-foreground">{lead.platform} · {lead.status}</div>
            </div>
          ))}
        </InsightSection>

        {/* Q&A 매칭 */}
        <InsightSection
          title="매칭 Q&A"
          icon={<MessageCircle className="w-4 h-4 text-blue-500" />}
          count={qaCount}
          isLoading={qaLoading}
          onViewAll={() => navigate('/qa')}
        >
          {qaData?.matches?.map((qa: any, idx: number) => (
            <div key={idx} className="text-xs p-2 bg-muted/50 rounded">
              <div className="font-medium truncate">{qa.question_pattern}</div>
              <div className="text-muted-foreground">점수: {qa.match_score}</div>
            </div>
          ))}
        </InsightSection>

        {/* 경쟁사 약점 */}
        <InsightSection
          title="경쟁사 약점"
          icon={<Target className="w-4 h-4 text-purple-500" />}
          count={weaknessCount}
          isLoading={weaknessLoading}
          onViewAll={() => navigate('/competitors?tab=weaknesses')}
        >
          {weaknessData?.map((weakness: any, idx: number) => (
            <div key={idx} className="text-xs p-2 bg-muted/50 rounded">
              <div className="font-medium">{weakness.competitor_name}</div>
              <div className="text-muted-foreground truncate">{weakness.description}</div>
            </div>
          ))}
        </InsightSection>
      </div>

      {/* 푸터 */}
      <div className="sticky bottom-0 bg-card border-t border-border p-4 space-y-2">
        {/* 라이프사이클 버튼 */}
        {onShowLifecycle && (
          <Button
            fullWidth
            onClick={() => {
              onClose()
              onShowLifecycle()
            }}
            className="bg-gradient-to-r from-cyan-500 to-teal-500 text-white hover:opacity-90"
          >
            📅 키워드 라이프사이클
          </Button>
        )}
        <Button
          variant="primary"
          fullWidth
          onClick={() => navigate(`/pathfinder?keyword=${encodeURIComponent(keyword)}`)}
          icon={<TrendingUp className="w-4 h-4" />}
        >
          키워드 상세 분석
          <ExternalLink className="w-3 h-3 ml-1" />
        </Button>
      </div>
    </div>
  )
}

// 인사이트 섹션 컴포넌트
function InsightSection({
  title,
  icon,
  count,
  badge,
  isLoading,
  onViewAll,
  children,
}: {
  title: string
  icon: React.ReactNode
  count: number
  badge?: string
  isLoading: boolean
  onViewAll: () => void
  children: React.ReactNode
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-sm font-medium">{title}</span>
          <span className="text-xs px-1.5 py-0.5 bg-muted rounded-full">
            {count}
          </span>
          {badge && (
            <span className="text-xs px-1.5 py-0.5 bg-red-500/20 text-red-500 rounded-full">
              {badge}
            </span>
          )}
        </div>
        <Button
          variant="ghost"
          size="xs"
          onClick={onViewAll}
          className="text-primary"
        >
          전체 보기
        </Button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-4">
          <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
        </div>
      ) : count === 0 ? (
        <div className="text-xs text-muted-foreground text-center py-2">
          관련 데이터 없음
        </div>
      ) : (
        <div className="space-y-1">{children}</div>
      )}
    </div>
  )
}

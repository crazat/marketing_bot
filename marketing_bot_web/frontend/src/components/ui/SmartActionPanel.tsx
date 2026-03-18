/**
 * [Phase E-2] Smart Action Panel
 * 전체 시스템 상황을 분석하여 구체적인 다음 행동 추천
 */

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  TrendingDown,
  Users,
  MessageSquare,
  Zap,
  Clock,
  CheckCircle2,
  ArrowRight,
  Loader2,
  Lightbulb,
  Bell,
} from 'lucide-react'
import { battleApi, viralApi, leadsApi, competitorsApi } from '@/services/api'
import Button from '@/components/ui/Button'

interface SmartAction {
  id: string
  category: 'urgent' | 'opportunity' | 'maintenance'
  priority: 'critical' | 'high' | 'medium' | 'low'
  icon: React.ReactNode
  title: string
  description: string
  context?: string
  action: () => void
  actionLabel: string
  timestamp?: string
}

interface SmartActionPanelProps {
  /** 최대 표시할 액션 수 */
  maxItems?: number
  /** 컴팩트 모드 (Dashboard 위젯용) */
  compact?: boolean
  /** 특정 카테고리만 표시 */
  filterCategory?: 'urgent' | 'opportunity' | 'maintenance'
}

export default function SmartActionPanel({
  maxItems = 10,
  compact = false,
  filterCategory,
}: SmartActionPanelProps) {
  const navigate = useNavigate()

  // 순위 하락 알림
  const { data: rankAlerts, isLoading: alertsLoading } = useQuery({
    queryKey: ['smart-rank-alerts'],
    queryFn: () => battleApi.getRankDropAlerts(3, true),
    staleTime: 60000,
  })

  // 바이럴 현황
  const { data: viralData, isLoading: viralLoading } = useQuery({
    queryKey: ['smart-viral'],
    queryFn: () => viralApi.getTargets('pending', undefined, 100),
    staleTime: 60000,
  })

  // 리드 현황 (여러 플랫폼)
  const { data: leadsData, isLoading: leadsLoading } = useQuery({
    queryKey: ['smart-leads'],
    queryFn: async () => {
      const [naver, youtube] = await Promise.all([
        leadsApi.getNaverLeads({ limit: 100, status: 'new' }).catch(() => []),
        leadsApi.getYoutubeLeads({ limit: 100, status: 'new' }).catch(() => []),
      ])
      return [...(naver || []), ...(youtube || [])]
    },
    staleTime: 60000,
  })

  // 경쟁사 약점
  const { data: weaknessData, isLoading: weaknessLoading } = useQuery({
    queryKey: ['smart-weaknesses'],
    queryFn: () => competitorsApi.getWeaknesses(20),
    staleTime: 300000,
  })

  const isLoading = alertsLoading || viralLoading || leadsLoading || weaknessLoading

  // 스마트 액션 생성
  const smartActions = useMemo(() => {
    const actions: SmartAction[] = []

    // 1. 순위 하락 알림 (긴급)
    const alerts = rankAlerts?.alerts || []
    alerts.forEach((alert: any) => {
      const severity = alert.severity || (alert.rank_drop >= 5 ? 'critical' : 'warning')
      actions.push({
        id: `rank-${alert.keyword}`,
        category: 'urgent',
        priority: severity === 'critical' ? 'critical' : 'high',
        icon: <TrendingDown className="w-4 h-4" />,
        title: `"${alert.keyword}" 순위 ${alert.rank_drop}위 하락`,
        description: `${alert.previous_rank}위 → ${alert.current_rank}위`,
        context: alert.trend === 'declining' ? '지속 하락 추세' : undefined,
        action: () => navigate(`/battle?keyword=${encodeURIComponent(alert.keyword)}&tab=trends`),
        actionLabel: '대응하기',
      })
    })

    // 2. Hot 리드 미응답 (긴급)
    const hotLeads = (leadsData || []).filter((l: any) => l.grade === 'hot' && l.status === 'new')
    if (hotLeads.length > 0) {
      // 48시간 이상 지난 Hot 리드는 critical
      const urgentHot = hotLeads.filter((l: any) => {
        const created = new Date(l.collected_at || l.created_at)
        const hoursSince = (Date.now() - created.getTime()) / (1000 * 60 * 60)
        return hoursSince > 48
      })

      if (urgentHot.length > 0) {
        actions.push({
          id: 'urgent-hot-leads',
          category: 'urgent',
          priority: 'critical',
          icon: <Users className="w-4 h-4" />,
          title: `Hot 리드 ${urgentHot.length}건 48시간 초과`,
          description: '즉시 응답하지 않으면 전환 기회를 놓칠 수 있습니다',
          action: () => navigate('/leads?grade=hot&status=new'),
          actionLabel: '지금 응답',
        })
      } else if (hotLeads.length > 0) {
        actions.push({
          id: 'hot-leads',
          category: 'urgent',
          priority: 'high',
          icon: <Users className="w-4 h-4" />,
          title: `Hot 리드 ${hotLeads.length}건 미응답`,
          description: '빠른 응답으로 전환율을 높이세요',
          action: () => navigate('/leads?grade=hot&status=new'),
          actionLabel: '응답하기',
        })
      }
    }

    // 3. Warm 리드 (기회)
    const warmLeads = (leadsData || []).filter((l: any) => l.grade === 'warm' && l.status === 'new')
    if (warmLeads.length >= 5) {
      actions.push({
        id: 'warm-leads',
        category: 'opportunity',
        priority: 'medium',
        icon: <Users className="w-4 h-4" />,
        title: `Warm 리드 ${warmLeads.length}건 대기 중`,
        description: '잠재 고객에게 먼저 다가가세요',
        action: () => navigate('/leads?grade=warm&status=new'),
        actionLabel: '확인하기',
      })
    }

    // 4. 미처리 바이럴 (유지보수)
    const pendingViral = viralData?.targets?.length || 0
    if (pendingViral > 0) {
      actions.push({
        id: 'pending-viral',
        category: 'maintenance',
        priority: pendingViral >= 20 ? 'high' : 'medium',
        icon: <MessageSquare className="w-4 h-4" />,
        title: `미처리 바이럴 ${pendingViral}건`,
        description: '댓글 작성하여 브랜드 노출을 높이세요',
        action: () => navigate('/viral?status=pending'),
        actionLabel: '처리하기',
      })
    }

    // 5. 경쟁사 약점 기회 (기회)
    const recentWeaknesses = (weaknessData || []).filter((w: any) => {
      const created = new Date(w.created_at)
      const daysSince = (Date.now() - created.getTime()) / (1000 * 60 * 60 * 24)
      return daysSince <= 7
    })
    if (recentWeaknesses.length > 0) {
      actions.push({
        id: 'competitor-weakness',
        category: 'opportunity',
        priority: 'medium',
        icon: <Zap className="w-4 h-4" />,
        title: `경쟁사 약점 ${recentWeaknesses.length}건 발견`,
        description: '약점을 공략하는 콘텐츠로 경쟁 우위 확보',
        context: '최근 7일 내 발견',
        action: () => navigate('/competitors?tab=weaknesses'),
        actionLabel: '공략하기',
      })
    }

    // 6. 순위 추적 키워드 없음 (유지보수)
    if (!alertsLoading && (!rankAlerts?.alerts || rankAlerts.alerts.length === 0)) {
      // 하락 알림이 없으면 순위가 안정적이거나 추적 키워드가 없음
      // 추가 확인 필요시 별도 API 호출
    }

    // 우선순위순 정렬
    const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 }
    const categoryOrder = { urgent: 0, opportunity: 1, maintenance: 2 }

    return actions
      .filter(a => !filterCategory || a.category === filterCategory)
      .sort((a, b) => {
        if (a.category !== b.category) {
          return categoryOrder[a.category] - categoryOrder[b.category]
        }
        return priorityOrder[a.priority] - priorityOrder[b.priority]
      })
      .slice(0, maxItems)
  }, [rankAlerts, viralData, leadsData, weaknessData, alertsLoading, filterCategory, maxItems, navigate])

  const getPriorityStyles = (priority: string) => {
    switch (priority) {
      case 'critical':
        return {
          badge: 'bg-red-500 text-white',
          border: 'border-red-500/50',
          bg: 'bg-red-500/5',
          icon: 'bg-red-500/20 text-red-500',
        }
      case 'high':
        return {
          badge: 'bg-orange-500 text-white',
          border: 'border-orange-500/50',
          bg: 'bg-orange-500/5',
          icon: 'bg-orange-500/20 text-orange-500',
        }
      case 'medium':
        return {
          badge: 'bg-yellow-500 text-black',
          border: 'border-yellow-500/50',
          bg: 'bg-yellow-500/5',
          icon: 'bg-yellow-500/20 text-yellow-500',
        }
      default:
        return {
          badge: 'bg-blue-500 text-white',
          border: 'border-blue-500/50',
          bg: 'bg-blue-500/5',
          icon: 'bg-blue-500/20 text-blue-500',
        }
    }
  }

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'urgent':
        return <AlertTriangle className="w-4 h-4" />
      case 'opportunity':
        return <Lightbulb className="w-4 h-4" />
      case 'maintenance':
        return <Clock className="w-4 h-4" />
      default:
        return <Bell className="w-4 h-4" />
    }
  }

  const getCategoryLabel = (category: string) => {
    switch (category) {
      case 'urgent':
        return '긴급 대응'
      case 'opportunity':
        return '기회'
      case 'maintenance':
        return '유지보수'
      default:
        return '기타'
    }
  }

  // 카테고리별 그룹핑
  const groupedActions = useMemo(() => {
    const groups: Record<string, SmartAction[]> = {
      urgent: [],
      opportunity: [],
      maintenance: [],
    }
    smartActions.forEach((action) => {
      groups[action.category].push(action)
    })
    return groups
  }, [smartActions])

  if (isLoading) {
    return (
      <div className={`rounded-lg border border-border p-4 ${compact ? '' : 'bg-card'}`}>
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-primary mr-2" />
          <span className="text-sm text-muted-foreground">상황 분석 중...</span>
        </div>
      </div>
    )
  }

  if (smartActions.length === 0) {
    return (
      <div className={`rounded-lg border border-border p-4 ${compact ? '' : 'bg-card'}`}>
        <div className="flex flex-col items-center justify-center py-8">
          <CheckCircle2 className="w-10 h-10 text-green-500 mb-3" />
          <p className="font-medium">모든 상황 양호</p>
          <p className="text-sm text-muted-foreground">현재 추천할 액션이 없습니다</p>
        </div>
      </div>
    )
  }

  // 컴팩트 모드 (Dashboard 위젯)
  if (compact) {
    return (
      <div className="space-y-2">
        {smartActions.slice(0, 5).map((action) => {
          const styles = getPriorityStyles(action.priority)
          return (
            <div
              key={action.id}
              className={`flex items-center gap-3 p-3 rounded-lg border ${styles.border} ${styles.bg}`}
            >
              <span className={`p-1.5 rounded ${styles.icon}`}>
                {action.icon}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{action.title}</p>
                <p className="text-xs text-muted-foreground truncate">{action.description}</p>
              </div>
              <Button
                variant="primary"
                size="xs"
                onClick={action.action}
              >
                {action.actionLabel}
              </Button>
            </div>
          )
        })}
        {smartActions.length > 5 && (
          <Button
            variant="ghost"
            fullWidth
            onClick={() => navigate('/dashboard#actions')}
            className="text-primary"
          >
            +{smartActions.length - 5}개 더 보기
          </Button>
        )}
      </div>
    )
  }

  // 전체 모드
  return (
    <div className="space-y-6">
      {Object.entries(groupedActions).map(([category, actions]) => {
        if (actions.length === 0) return null

        return (
          <div key={category}>
            <h3 className="flex items-center gap-2 text-sm font-semibold mb-3">
              {getCategoryIcon(category)}
              {getCategoryLabel(category)}
              <span className="px-1.5 py-0.5 text-xs bg-muted rounded-full">
                {actions.length}
              </span>
            </h3>

            <div className="space-y-3">
              {actions.map((action) => {
                const styles = getPriorityStyles(action.priority)
                return (
                  <div
                    key={action.id}
                    className={`rounded-lg border p-4 ${styles.border} ${styles.bg}`}
                  >
                    <div className="flex items-start gap-3">
                      <span className={`p-2 rounded-lg ${styles.icon}`}>
                        {action.icon}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`px-1.5 py-0.5 text-[10px] rounded ${styles.badge}`}>
                            {action.priority === 'critical' ? '긴급' :
                             action.priority === 'high' ? '높음' :
                             action.priority === 'medium' ? '중간' : '낮음'}
                          </span>
                          <h4 className="font-medium">{action.title}</h4>
                        </div>
                        <p className="text-sm text-muted-foreground">{action.description}</p>
                        {action.context && (
                          <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {action.context}
                          </p>
                        )}
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
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

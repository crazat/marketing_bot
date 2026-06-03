import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { AlertCircle, Zap, ClipboardList, Pin, User, FileText, Flame, BarChart3, Sparkles, Target, CheckCircle } from 'lucide-react'
import { hudApi } from '@/services/api'
import Button from '@/components/ui/Button'

interface Action {
  id: string
  priority: 'critical' | 'high' | 'medium' | 'low'
  category: string
  title: string
  description: string
  action_link: string
  impact: string
  effort: string
}

interface QuickWin {
  action: string
  time_estimate: string
  link: string
}

interface SuggestedActionsData {
  actions: Action[]
  quick_wins: QuickWin[]
  focus_areas: Array<{
    area: string
    reason: string
    potential: string
  }>
  summary: {
    total_actions: number
    critical_count: number
    high_count: number
  }
}

const priorityStyles = {
  critical: { bg: 'bg-danger-tint', border: 'border-danger/30', text: 'text-danger', badge: 'bg-danger text-white', icon: <AlertCircle className="w-4 h-4" strokeWidth={1.8} /> },
  high: { bg: 'bg-clay-tint', border: 'border-clay/30', text: 'text-clay', badge: 'bg-clay text-white', icon: <Zap className="w-4 h-4" strokeWidth={1.8} /> },
  medium: { bg: 'bg-warn-tint', border: 'border-warn/30', text: 'text-warn', badge: 'bg-warn text-white', icon: <ClipboardList className="w-4 h-4" strokeWidth={1.8} /> },
  low: { bg: 'bg-muted', border: 'border-border', text: 'text-muted-foreground', badge: 'bg-muted text-foreground', icon: <Pin className="w-4 h-4" strokeWidth={1.8} /> },
}

const SA_CAT = 'w-4 h-4'
const categoryIcons: Record<string, ReactNode> = {
  leads: <User className={SA_CAT} strokeWidth={1.7} />,
  content: <FileText className={SA_CAT} strokeWidth={1.7} />,
  viral: <Flame className={SA_CAT} strokeWidth={1.7} />,
  ranking: <BarChart3 className={SA_CAT} strokeWidth={1.7} />,
  default: <Sparkles className={SA_CAT} strokeWidth={1.7} />,
}

export default function SuggestedActions() {
  const navigate = useNavigate()

  const { data, isLoading } = useQuery<SuggestedActionsData>({
    queryKey: ['suggested-actions'],
    queryFn: hudApi.getSuggestedActions,
    refetchInterval: 300000,  // 5분마다 갱신
    retry: 1,
  })

  if (isLoading) {
    return (
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="h-6 w-48 bg-muted rounded animate-pulse mb-4" />
        <div className="space-y-3">
          <div className="h-16 bg-muted rounded animate-pulse" />
          <div className="h-16 bg-muted rounded animate-pulse" />
        </div>
      </div>
    )
  }

  if (!data || data.actions.length === 0) {
    return (
      <div className="bg-card rounded-lg border border-border p-6">
        <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
          <Target className="w-4 h-4 text-sage inline" strokeWidth={1.8} /> AI 추천 액션
        </h2>
        <div className="text-center py-6 text-muted-foreground">
          <div className="flex justify-center mb-2 text-ok"><CheckCircle className="w-9 h-9" strokeWidth={1.6} /></div>
          <p>모든 작업이 완료되었습니다!</p>
          <p className="text-sm mt-1">새로운 리드나 키워드가 발견되면 알려드릴게요.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-card rounded-lg border border-border p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <Target className="w-4 h-4 text-sage inline" strokeWidth={1.8} /> AI 추천 액션
        </h2>
        {data.summary?.critical_count > 0 && (
          <span className="px-2 py-1 text-xs bg-red-500 text-white rounded-full">
            긴급 {data.summary.critical_count}
          </span>
        )}
      </div>

      {/* Quick Wins */}
      {data.quick_wins?.length > 0 && (
        <div className="mb-6">
          <h3 className="text-sm font-medium text-muted-foreground mb-2">
            빠른 실행 (Quick Wins)
          </h3>
          <div className="flex flex-wrap gap-2">
            {data.quick_wins.map((win, idx) => (
              <Button
                key={idx}
                variant="ghost"
                size="sm"
                onClick={() => navigate(win.link)}
                className="bg-primary/10 text-primary hover:bg-primary/20"
              >
                <span>{win.action}</span>
                <span className="text-xs text-muted-foreground ml-2">~{win.time_estimate}</span>
              </Button>
            ))}
          </div>
        </div>
      )}

      {/* Main Actions */}
      <div className="space-y-3">
        {data.actions.slice(0, 5).map((action) => {
          const style = priorityStyles[action.priority]
          const categoryIcon = categoryIcons[action.category] || categoryIcons.default

          return (
            <div
              key={action.id}
              onClick={() => navigate(action.action_link)}
              className={`p-4 rounded-lg border cursor-pointer transition-all hover:shadow-md ${style.bg} ${style.border}`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-lg">{style.icon}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${style.badge}`}>
                      {action.priority.toUpperCase()}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-muted">
                      {categoryIcon} {action.category}
                    </span>
                  </div>
                  <h4 className={`font-semibold ${style.text}`}>{action.title}</h4>
                  <p className="text-sm text-muted-foreground mt-1">{action.description}</p>
                </div>
                <div className="text-right text-xs text-muted-foreground ml-4">
                  <div>영향: {action.impact === 'high' ? '높음' : action.impact === 'medium' ? '중간' : '낮음'}</div>
                  <div>노력: {action.effort === 'high' ? '많음' : action.effort === 'medium' ? '보통' : '적음'}</div>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Focus Areas */}
      {data.focus_areas?.length > 0 && (
        <div className="mt-6 pt-4 border-t border-border">
          <h3 className="text-sm font-medium text-muted-foreground mb-2">
            집중 영역
          </h3>
          <div className="flex flex-wrap gap-2">
            {data.focus_areas.map((area, idx) => (
              <div
                key={idx}
                className="px-3 py-2 bg-muted rounded-lg text-sm"
                title={area.reason}
              >
                <span className="font-medium">{area.area}</span>
                <span className="text-muted-foreground ml-2">잠재력: {area.potential}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

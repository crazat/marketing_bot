/**
 * AI 브리핑 컴포넌트
 * Gemini AI 기반 일일 인사이트 브리핑
 */

import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { hudApi, type AiBriefingData } from '@/services/api'
import {
  Brain, TrendingUp, TrendingDown, Minus, AlertTriangle,
  ChevronRight, Sparkles, RefreshCw, Target, Lightbulb,
  BarChart3, Zap
} from 'lucide-react'
import Button, { IconButton } from '@/components/ui/Button'

interface AiBriefingProps {
  compact?: boolean
}

const categoryIcons: Record<string, React.ReactNode> = {
  keywords: <Target className="w-4 h-4" />,
  leads: <Zap className="w-4 h-4" />,
  competition: <BarChart3 className="w-4 h-4" />,
  trends: <TrendingUp className="w-4 h-4" />,
}

const categoryColors: Record<string, string> = {
  keywords: 'bg-blue-500/10 text-blue-500 border-blue-500/30',
  leads: 'bg-green-500/10 text-green-500 border-green-500/30',
  competition: 'bg-orange-500/10 text-orange-500 border-orange-500/30',
  trends: 'bg-purple-500/10 text-purple-500 border-purple-500/30',
}

const importanceStyles: Record<string, string> = {
  high: 'border-l-4 border-l-red-500',
  medium: 'border-l-4 border-l-yellow-500',
  low: 'border-l-4 border-l-gray-400',
}

export default function AiBriefing({ compact = false }: AiBriefingProps) {
  const navigate = useNavigate()

  const {
    data: briefing,
    isLoading,
    isError,
    refetch,
    isFetching
  } = useQuery<AiBriefingData>({
    queryKey: ['ai-briefing'],
    queryFn: hudApi.getAiBriefing,
    staleTime: 5 * 60 * 1000, // 5분
    refetchInterval: 10 * 60 * 1000, // 10분마다 자동 갱신
    retry: 1,
  })

  if (isLoading) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 animate-pulse">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-6 h-6 bg-muted rounded" />
          <div className="h-6 bg-muted rounded w-32" />
        </div>
        <div className="space-y-3">
          <div className="h-20 bg-muted rounded" />
          <div className="h-16 bg-muted rounded" />
          <div className="h-16 bg-muted rounded" />
        </div>
      </div>
    )
  }

  if (isError || !briefing) {
    return (
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <AlertTriangle className="w-5 h-5" />
          <span>AI 브리핑을 불러올 수 없습니다.</span>
        </div>
      </div>
    )
  }

  const formatTime = (isoString: string) => {
    const date = new Date(isoString)
    return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
  }

  // 컴팩트 모드 (대시보드 미니 위젯)
  if (compact) {
    return (
      <div className="bg-gradient-to-br from-violet-500/10 to-purple-600/10 border border-violet-500/30 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Brain className="w-5 h-5 text-violet-500" />
            <span className="font-semibold">AI 인사이트</span>
            {briefing.source === 'ai' && (
              <Sparkles className="w-4 h-4 text-violet-400" />
            )}
          </div>
          <IconButton
            icon={<RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />}
            onClick={() => refetch()}
            disabled={isFetching}
            size="sm"
            title="새로고침"
          />
        </div>

        <p className="text-sm text-muted-foreground mb-3 line-clamp-2">
          {briefing.executive_summary}
        </p>

        {briefing.key_insights.length > 0 && (
          <div className="space-y-2">
            {briefing.key_insights.slice(0, 2).map((insight, idx) => (
              <div
                key={idx}
                className={`flex items-center gap-2 text-xs p-2 rounded ${
                  categoryColors[insight.category] || 'bg-muted'
                }`}
              >
                {categoryIcons[insight.category] || <Lightbulb className="w-4 h-4" />}
                <span className="font-medium">{insight.title}</span>
              </div>
            ))}
          </div>
        )}

        {briefing.recommended_actions.length > 0 && (
          <Button
            variant="ghost"
            size="xs"
            fullWidth
            onClick={() => {
              const firstAction = briefing.recommended_actions[0]
              if (firstAction.link) navigate(firstAction.link)
            }}
            icon={<ChevronRight className="w-4 h-4" />}
            iconPosition="right"
            className="mt-3 text-violet-500 hover:text-violet-400"
          >
            {briefing.recommended_actions[0].action}
          </Button>
        )}
      </div>
    )
  }

  // 전체 모드
  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      {/* 헤더 */}
      <div className="bg-gradient-to-r from-violet-500/10 to-purple-600/10 border-b border-border p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Brain className="w-6 h-6 text-violet-500" />
            <h3 className="text-lg font-semibold">AI 일일 브리핑</h3>
            {briefing.source === 'ai' && (
              <span className="flex items-center gap-1 text-xs px-2 py-0.5 bg-violet-500/20 text-violet-400 rounded-full">
                <Sparkles className="w-3 h-3" />
                Gemini
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground">
              {formatTime(briefing.generated_at)}
            </span>
            <IconButton
              icon={<RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />}
              onClick={() => refetch()}
              disabled={isFetching}
              title="새로고침"
            />
          </div>
        </div>
      </div>

      <div className="p-4 space-y-5">
        {/* 핵심 요약 */}
        <div className="p-4 bg-muted/50 rounded-lg">
          <p className="text-sm leading-relaxed">{briefing.executive_summary}</p>
        </div>

        {/* 리스크 알림 */}
        {briefing.risk_alerts.length > 0 && (
          <div className="space-y-2">
            {briefing.risk_alerts.map((alert, idx) => (
              <div
                key={idx}
                className={`flex items-center gap-2 p-3 rounded-lg ${
                  alert.level === 'critical'
                    ? 'bg-red-500/10 border border-red-500/30 text-red-500'
                    : 'bg-yellow-500/10 border border-yellow-500/30 text-yellow-500'
                }`}
              >
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span className="text-sm">{alert.message}</span>
              </div>
            ))}
          </div>
        )}

        {/* 주요 인사이트 */}
        {briefing.key_insights.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <Lightbulb className="w-4 h-4 text-yellow-500" />
              주요 인사이트
            </h4>
            <div className="grid gap-2">
              {briefing.key_insights.map((insight, idx) => (
                <div
                  key={idx}
                  className={`p-3 bg-muted/30 rounded-lg ${importanceStyles[insight.importance]}`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`px-2 py-0.5 text-xs rounded border ${
                      categoryColors[insight.category] || 'bg-muted border-border'
                    }`}>
                      {insight.category === 'keywords' && '키워드'}
                      {insight.category === 'leads' && '리드'}
                      {insight.category === 'competition' && '경쟁'}
                      {insight.category === 'trends' && '트렌드'}
                      {!['keywords', 'leads', 'competition', 'trends'].includes(insight.category) && insight.category}
                    </span>
                    <span className="font-medium text-sm">{insight.title}</span>
                  </div>
                  <p className="text-xs text-muted-foreground pl-1">{insight.description}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 시장 신호 */}
        {briefing.market_signals.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-blue-500" />
              시장 신호
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              {briefing.market_signals.map((signal, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between p-3 bg-muted/30 rounded-lg"
                >
                  <span className="text-sm">{signal.signal}</span>
                  <div className="flex items-center gap-1">
                    {signal.trend === 'up' && <TrendingUp className="w-4 h-4 text-green-500" />}
                    {signal.trend === 'down' && <TrendingDown className="w-4 h-4 text-red-500" />}
                    {signal.trend === 'stable' && <Minus className="w-4 h-4 text-gray-400" />}
                    <span className={`text-xs ${
                      signal.impact === '긍정적' ? 'text-green-500' :
                      signal.impact === '부정적' ? 'text-red-500' : 'text-gray-400'
                    }`}>
                      {signal.impact}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 권장 액션 */}
        {briefing.recommended_actions.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <Zap className="w-4 h-4 text-orange-500" />
              권장 액션
            </h4>
            <div className="space-y-2">
              {briefing.recommended_actions.map((action, idx) => (
                <Button
                  key={idx}
                  variant="ghost"
                  fullWidth
                  onClick={() => action.link && navigate(action.link)}
                  icon={action.link ? <ChevronRight className="w-4 h-4 text-muted-foreground" /> : undefined}
                  iconPosition="right"
                  className="p-3 bg-muted/30 hover:bg-muted/50 justify-between h-auto"
                >
                  <div className="flex items-center gap-3 text-left">
                    <span className="flex items-center justify-center w-6 h-6 rounded-full bg-primary text-primary-foreground text-xs font-bold">
                      {action.priority}
                    </span>
                    <div>
                      <div className="text-sm font-medium">{action.action}</div>
                      <div className="text-xs text-muted-foreground">{action.reason}</div>
                    </div>
                  </div>
                </Button>
              ))}
            </div>
          </div>
        )}

        {/* 데이터 컨텍스트 */}
        {briefing.data_context && (
          <div className="grid grid-cols-3 gap-2 pt-3 border-t border-border">
            <div className="text-center p-2">
              <div className="text-lg font-bold">{briefing.data_context.keywords_count}</div>
              <div className="text-xs text-muted-foreground">키워드</div>
            </div>
            <div className="text-center p-2">
              <div className="text-lg font-bold">{briefing.data_context.viral_targets_count}</div>
              <div className="text-xs text-muted-foreground">대기 타겟</div>
            </div>
            <div className="text-center p-2">
              <div className="text-lg font-bold">{briefing.data_context.leads_count}</div>
              <div className="text-xs text-muted-foreground">신규 리드</div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

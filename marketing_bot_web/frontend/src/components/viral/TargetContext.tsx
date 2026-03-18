/**
 * 타겟 컨텍스트 컴포넌트
 * 의사결정에 필요한 심층 정보 제공
 */

import { useQuery } from '@tanstack/react-query'
import { viralApi, type TargetContext as TargetContextType } from '@/services/api'
import {
  Users, Tag, Building2, History, Lightbulb, TrendingUp,
  AlertCircle, ChevronRight, Loader2
} from 'lucide-react'

interface TargetContextProps {
  targetId: string
  onSelectTarget?: (targetId: string) => void
}

const gradeColors: Record<string, string> = {
  S: 'text-red-500 bg-red-500/10',
  A: 'text-orange-500 bg-orange-500/10',
  B: 'text-yellow-500 bg-yellow-500/10',
  C: 'text-blue-500 bg-blue-500/10',
  D: 'text-gray-500 bg-gray-500/10',
}

const importanceColors: Record<string, string> = {
  high: 'border-l-red-500',
  medium: 'border-l-yellow-500',
  low: 'border-l-blue-500',
}

export function TargetContext({ targetId, onSelectTarget }: TargetContextProps) {
  const { data: context, isLoading, isError } = useQuery<TargetContextType>({
    queryKey: ['target-context', targetId],
    queryFn: () => viralApi.getTargetContext(targetId),
    enabled: !!targetId,
    staleTime: 2 * 60 * 1000, // 2분
  })

  if (isLoading) {
    return (
      <div className="p-4 bg-muted/30 rounded-lg flex items-center justify-center gap-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-sm text-muted-foreground">컨텍스트 정보 로딩 중...</span>
      </div>
    )
  }

  if (isError || !context) {
    return (
      <div className="p-4 bg-muted/30 rounded-lg flex items-center gap-2 text-muted-foreground">
        <AlertCircle className="w-4 h-4" />
        <span className="text-sm">컨텍스트 정보를 불러올 수 없습니다.</span>
      </div>
    )
  }

  const hasContent =
    context.insights.length > 0 ||
    context.similar_targets.length > 0 ||
    context.keyword_analysis.length > 0 ||
    context.competitor_mentions.length > 0

  if (!hasContent) {
    return (
      <div className="p-4 bg-muted/30 rounded-lg text-center text-muted-foreground">
        <Lightbulb className="w-6 h-6 mx-auto mb-2 opacity-50" />
        <span className="text-sm">추가 컨텍스트 정보 없음</span>
      </div>
    )
  }

  return (
    <div className="space-y-4 p-4 bg-gradient-to-br from-blue-500/5 to-purple-500/5 rounded-lg border border-border">
      <div className="flex items-center gap-2">
        <Lightbulb className="w-5 h-5 text-yellow-500" />
        <h4 className="font-semibold">컨텍스트 인사이트</h4>
      </div>

      {/* 인사이트 목록 */}
      {context.insights.length > 0 && (
        <div className="space-y-2">
          {context.insights.map((insight, idx) => (
            <div
              key={idx}
              className={`flex items-center gap-2 p-2 bg-card rounded border-l-4 ${
                importanceColors[insight.importance] || 'border-l-gray-400'
              }`}
            >
              {insight.type === 'similar' && <Users className="w-4 h-4 text-blue-500" />}
              {insight.type === 'keyword' && <Tag className="w-4 h-4 text-green-500" />}
              {insight.type === 'competitor' && <Building2 className="w-4 h-4 text-orange-500" />}
              {insight.type === 'recurring' && <History className="w-4 h-4 text-purple-500" />}
              {insight.type === 'platform' && <TrendingUp className="w-4 h-4 text-cyan-500" />}
              <span className="text-sm">{insight.message}</span>
            </div>
          ))}
        </div>
      )}

      {/* 키워드 분석 */}
      {context.keyword_analysis.length > 0 && (
        <div>
          <h5 className="text-sm font-medium mb-2 flex items-center gap-2">
            <Tag className="w-4 h-4" />
            매칭 키워드 분석
          </h5>
          <div className="flex flex-wrap gap-2">
            {context.keyword_analysis.map((kw, idx) => (
              <div
                key={idx}
                className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${
                  gradeColors[kw.grade] || 'bg-muted'
                }`}
              >
                <span className="font-bold">{kw.grade}</span>
                <span>{kw.keyword}</span>
                {kw.search_volume && (
                  <span className="text-muted-foreground">
                    ({kw.search_volume.toLocaleString()})
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 경쟁사 언급 */}
      {context.competitor_mentions.length > 0 && (
        <div>
          <h5 className="text-sm font-medium mb-2 flex items-center gap-2">
            <Building2 className="w-4 h-4 text-orange-500" />
            경쟁사 언급 발견
          </h5>
          <div className="flex flex-wrap gap-2">
            {context.competitor_mentions.map((comp, idx) => (
              <span
                key={idx}
                className="px-2 py-1 bg-orange-500/10 text-orange-500 rounded text-xs border border-orange-500/30"
              >
                {comp.competitor_name}
              </span>
            ))}
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            경쟁사 언급 콘텐츠는 역공략 기회가 높습니다
          </p>
        </div>
      )}

      {/* 유사 타겟 */}
      {context.similar_targets.length > 0 && (
        <div>
          <h5 className="text-sm font-medium mb-2 flex items-center gap-2">
            <Users className="w-4 h-4 text-blue-500" />
            유사 타겟 ({context.similar_targets.length})
          </h5>
          <div className="space-y-1">
            {context.similar_targets.slice(0, 3).map((target) => (
              <button
                key={target.id}
                onClick={() => onSelectTarget?.(target.id)}
                className="w-full flex items-center justify-between p-2 bg-card hover:bg-muted/50 rounded text-left transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate">{target.title}</div>
                  <div className="text-xs text-muted-foreground">
                    {target.platform} · {target.priority_score?.toFixed(0)}점
                  </div>
                </div>
                <ChevronRight className="w-4 h-4 text-muted-foreground flex-shrink-0" />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 타겟 히스토리 */}
      {context.target_history && context.target_history.scan_count > 1 && (
        <div className="flex items-center gap-2 p-2 bg-purple-500/10 rounded text-sm">
          <History className="w-4 h-4 text-purple-500" />
          <span>
            이 타겟은 <strong>{context.target_history.scan_count}회</strong> 재발견됨
            {context.target_history.first_seen && (
              <span className="text-muted-foreground">
                {' '}(최초 발견: {new Date(context.target_history.first_seen).toLocaleDateString('ko-KR')})
              </span>
            )}
          </span>
        </div>
      )}
    </div>
  )
}

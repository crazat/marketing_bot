/**
 * AI 인사이트 컴포넌트 (Phase B - Intelligence API)
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Brain,
  TrendingUp,
  TrendingDown,
  Minus,
  Lightbulb,
  MessageSquare,
  Clock,
  Target,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Sparkles,
  AlertTriangle,
  CheckCircle,
} from 'lucide-react'
import { intelligenceApi } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import Button from '@/components/ui/Button'

export default function AIInsights() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [expandedSection, setExpandedSection] = useState<string | null>('insights')

  // 대시보드 인사이트 조회
  const { data: insights, isLoading: insightsLoading } = useQuery({
    queryKey: ['ai-insights'],
    queryFn: intelligenceApi.getInsights,
    retry: 1,
    refetchInterval: 60000,
  })

  // 순위 예측 조회
  const { data: rankPredictions, isLoading: predictionsLoading } = useQuery({
    queryKey: ['rank-predictions'],
    queryFn: () => intelligenceApi.getRankPredictions(7),
    retry: 1,
  })

  // 댓글 효과 분석 조회
  const { data: commentEffectiveness, isLoading: commentLoading } = useQuery({
    queryKey: ['comment-effectiveness'],
    queryFn: intelligenceApi.getCommentEffectiveness,
    retry: 1,
  })

  // 타이밍 추천 조회
  const { data: timingRecs } = useQuery({
    queryKey: ['timing-recommendations'],
    queryFn: intelligenceApi.getCurrentTimingRecommendations,
    retry: 1,
    refetchInterval: 300000, // 5분마다
  })

  // 전체 분석 실행
  const runAnalysisMutation = useMutation({
    mutationFn: intelligenceApi.runFullAnalysis,
    onSuccess: () => {
      toast.success('AI 분석이 완료되었습니다.')
      queryClient.invalidateQueries({ queryKey: ['ai-insights'] })
      queryClient.invalidateQueries({ queryKey: ['rank-predictions'] })
      queryClient.invalidateQueries({ queryKey: ['comment-effectiveness'] })
    },
    onError: () => {
      toast.error('분석 중 오류가 발생했습니다.')
    },
  })

  const toggleSection = (section: string) => {
    setExpandedSection(expandedSection === section ? null : section)
  }

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'rising':
        return <TrendingUp className="w-4 h-4 text-green-500" />
      case 'falling':
        return <TrendingDown className="w-4 h-4 text-red-500" />
      default:
        return <Minus className="w-4 h-4 text-gray-500" />
    }
  }

  const getTrendColor = (trend: string) => {
    switch (trend) {
      case 'rising':
        return 'text-green-500 bg-green-500/10'
      case 'falling':
        return 'text-red-500 bg-red-500/10'
      default:
        return 'text-gray-500 bg-gray-500/10'
    }
  }

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-purple-500/10 rounded-lg">
            <Brain className="w-6 h-6 text-purple-500" />
          </div>
          <div>
            <h2 className="text-xl font-bold">AI 인사이트</h2>
            <p className="text-sm text-muted-foreground">
              AI가 분석한 마케팅 인사이트와 예측
            </p>
          </div>
        </div>
        <Button
          variant="primary"
          onClick={() => runAnalysisMutation.mutate()}
          loading={runAnalysisMutation.isPending}
          icon={<Sparkles className="w-4 h-4" />}
          className="bg-purple-600 hover:bg-purple-700"
        >
          전체 분석 실행
        </Button>
      </div>

      {/* 현재 시점 추천 액션 */}
      {timingRecs?.has_recommendations && (
        <div className="bg-gradient-to-r from-purple-500/10 to-blue-500/10 border border-purple-500/20 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <Clock className="w-5 h-5 text-purple-500" />
            <h3 className="font-semibold">지금 추천하는 액션</h3>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {timingRecs.recommendations.map((rec, idx) => (
              <div key={idx} className="bg-background/50 rounded-lg p-3">
                <div className="font-medium text-sm">{rec.platform}</div>
                <div className="text-muted-foreground text-sm">{rec.action}</div>
                <div className="text-xs text-purple-500 mt-1">{rec.reason}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 인사이트 섹션 */}
      <div className="bg-card border border-border rounded-lg">
        <button
          onClick={() => toggleSection('insights')}
          className="w-full px-4 py-3 flex items-center justify-between hover:bg-muted/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Lightbulb className="w-5 h-5 text-yellow-500" />
            <span className="font-semibold">핵심 인사이트</span>
          </div>
          {expandedSection === 'insights' ? (
            <ChevronUp className="w-5 h-5" />
          ) : (
            <ChevronDown className="w-5 h-5" />
          )}
        </button>

        {expandedSection === 'insights' && (
          <div className="px-4 pb-4 space-y-4">
            {insightsLoading ? (
              <div className="animate-pulse space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-16 bg-muted rounded-lg" />
                ))}
              </div>
            ) : insights ? (
              <>
                {/* 플랫폼별 전환율 */}
                {insights.platform_conversion_rates && Object.keys(insights.platform_conversion_rates).length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-2">플랫폼별 전환율</h4>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      {Object.entries(insights.platform_conversion_rates).map(([platform, rate]) => (
                        <div key={platform} className="bg-muted/50 rounded-lg p-3 text-center">
                          <div className="text-xs text-muted-foreground">{platform}</div>
                          <div className="text-lg font-bold text-primary">{(Number(rate) * 100).toFixed(1)}%</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 고성과 키워드 */}
                {insights.high_performing_keywords && insights.high_performing_keywords.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-2">고성과 키워드</h4>
                    <div className="space-y-2">
                      {insights.high_performing_keywords.slice(0, 5).map((kw, idx) => (
                        <div key={idx} className="flex items-center justify-between bg-green-500/5 border border-green-500/20 rounded-lg p-3">
                          <div className="flex items-center gap-2">
                            <CheckCircle className="w-4 h-4 text-green-500" />
                            <span className="font-medium">{kw.keyword}</span>
                          </div>
                          <div className="text-sm">
                            <span className="text-green-500 font-medium">{(kw.conversion_rate * 100).toFixed(1)}%</span>
                            <span className="text-muted-foreground ml-2">({kw.leads} 리드)</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 순위 경고 */}
                {insights.rank_warnings && insights.rank_warnings.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-2">순위 주의 키워드</h4>
                    <div className="space-y-2">
                      {insights.rank_warnings.slice(0, 5).map((warning, idx) => (
                        <div key={idx} className={`flex items-center justify-between rounded-lg p-3 ${
                          warning.warning_level === 'critical'
                            ? 'bg-red-500/5 border border-red-500/20'
                            : 'bg-yellow-500/5 border border-yellow-500/20'
                        }`}>
                          <div className="flex items-center gap-2">
                            <AlertTriangle className={`w-4 h-4 ${
                              warning.warning_level === 'critical' ? 'text-red-500' : 'text-yellow-500'
                            }`} />
                            <span className="font-medium">{warning.keyword}</span>
                          </div>
                          <div className="flex items-center gap-2 text-sm">
                            <span>{warning.current_rank}위</span>
                            {getTrendIcon(warning.trend)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Brain className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>인사이트 데이터가 없습니다.</p>
                <p className="text-sm">전체 분석을 실행해보세요.</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 순위 예측 섹션 */}
      <div className="bg-card border border-border rounded-lg">
        <button
          onClick={() => toggleSection('predictions')}
          className="w-full px-4 py-3 flex items-center justify-between hover:bg-muted/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Target className="w-5 h-5 text-blue-500" />
            <span className="font-semibold">7일 순위 예측</span>
            {rankPredictions && (
              <div className="flex items-center gap-2 text-sm">
                <span className="px-2 py-0.5 bg-green-500/10 text-green-500 rounded">
                  상승 {rankPredictions.rising_count}
                </span>
                <span className="px-2 py-0.5 bg-red-500/10 text-red-500 rounded">
                  하락 {rankPredictions.falling_count}
                </span>
              </div>
            )}
          </div>
          {expandedSection === 'predictions' ? (
            <ChevronUp className="w-5 h-5" />
          ) : (
            <ChevronDown className="w-5 h-5" />
          )}
        </button>

        {expandedSection === 'predictions' && (
          <div className="px-4 pb-4">
            {predictionsLoading ? (
              <div className="animate-pulse space-y-2">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="h-12 bg-muted rounded-lg" />
                ))}
              </div>
            ) : rankPredictions?.predictions && rankPredictions.predictions.length > 0 ? (
              <div className="space-y-2">
                {rankPredictions.predictions.slice(0, 10).map((pred, idx) => (
                  <div key={idx} className={`flex items-center justify-between rounded-lg p-3 ${getTrendColor(pred.trend)}`}>
                    <div className="flex items-center gap-3">
                      {getTrendIcon(pred.trend)}
                      <span className="font-medium">{pred.keyword}</span>
                    </div>
                    <div className="flex items-center gap-4 text-sm">
                      <div className="flex items-center gap-2">
                        <span className="text-muted-foreground">{pred.current_rank}위</span>
                        <ArrowRight className="w-4 h-4" />
                        <span className="font-medium">{pred.predicted_rank}위</span>
                      </div>
                      <div className="text-xs px-2 py-0.5 bg-background/50 rounded">
                        신뢰도 {(pred.confidence * 100).toFixed(0)}%
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Target className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>예측 데이터가 없습니다.</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 댓글 효과 분석 섹션 */}
      <div className="bg-card border border-border rounded-lg">
        <button
          onClick={() => toggleSection('comments')}
          className="w-full px-4 py-3 flex items-center justify-between hover:bg-muted/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-green-500" />
            <span className="font-semibold">댓글 효과 분석</span>
          </div>
          {expandedSection === 'comments' ? (
            <ChevronUp className="w-5 h-5" />
          ) : (
            <ChevronDown className="w-5 h-5" />
          )}
        </button>

        {expandedSection === 'comments' && (
          <div className="px-4 pb-4">
            {commentLoading ? (
              <div className="animate-pulse space-y-3">
                <div className="h-24 bg-muted rounded-lg" />
                <div className="h-24 bg-muted rounded-lg" />
              </div>
            ) : commentEffectiveness ? (
              <div className="space-y-4">
                {/* 길이 분석 */}
                {commentEffectiveness.length_analysis && (
                  <div className="bg-muted/30 rounded-lg p-4">
                    <h4 className="text-sm font-medium mb-2">최적 댓글 길이</h4>
                    <div className="text-2xl font-bold text-primary">
                      {commentEffectiveness.length_analysis.optimal_length || '-'}자
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                      가장 높은 전환율을 보이는 평균 길이
                    </p>
                  </div>
                )}

                {/* 스타일 분석 */}
                {commentEffectiveness.style_analysis?.best_styles && (
                  <div className="bg-muted/30 rounded-lg p-4">
                    <h4 className="text-sm font-medium mb-2">효과적인 스타일</h4>
                    <div className="flex flex-wrap gap-2">
                      {commentEffectiveness.style_analysis.best_styles.map((style, idx) => (
                        <span key={idx} className="px-3 py-1 bg-green-500/10 text-green-500 rounded-full text-sm">
                          {style}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* 추천 사항 */}
                {commentEffectiveness.recommendations && commentEffectiveness.recommendations.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium mb-2">AI 추천</h4>
                    <ul className="space-y-2">
                      {commentEffectiveness.recommendations.map((rec, idx) => (
                        <li key={idx} className="flex items-start gap-2 text-sm">
                          <Lightbulb className="w-4 h-4 text-yellow-500 mt-0.5 flex-shrink-0" />
                          <span>{rec}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <MessageSquare className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>댓글 효과 데이터가 없습니다.</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * 성과 분석 컴포넌트 (Phase D - Feedback API)
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  LineChart,
  TrendingUp,
  FileText,
  Award,
  AlertTriangle,
  Target,
  BarChart2,
  ChevronDown,
  ChevronUp,
  Play,
  CheckCircle,
  XCircle,
  Percent,
} from 'lucide-react'
import { feedbackApi } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import Button from '@/components/ui/Button'

export default function PerformanceFeedback() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [expandedSection, setExpandedSection] = useState<string | null>('summary')
  const [reportType, setReportType] = useState<'weekly' | 'monthly'>('weekly')

  // 피드백 요약 조회
  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['feedback-summary'],
    queryFn: feedbackApi.getSummary,
    retry: 1,
  })

  // ROI 분석 조회
  const { data: roiData, isLoading: roiLoading } = useQuery({
    queryKey: ['roi-analysis'],
    queryFn: () => feedbackApi.getROI(30),
    retry: 1,
  })

  // 예측 정확도 조회
  const { data: accuracyData, isLoading: accuracyLoading } = useQuery({
    queryKey: ['prediction-accuracy'],
    queryFn: feedbackApi.getPredictionAccuracy,
    retry: 1,
  })

  // 최신 리포트 조회
  const { data: latestReport, isLoading: reportLoading } = useQuery({
    queryKey: ['latest-report', reportType],
    queryFn: () => feedbackApi.getLatestReport(reportType),
    retry: 1,
  })

  // 피드백 사이클 실행
  const runCycleMutation = useMutation({
    mutationFn: feedbackApi.runFeedbackCycle,
    onSuccess: () => {
      toast.success('피드백 분석이 완료되었습니다.')
      queryClient.invalidateQueries({ queryKey: ['feedback-summary'] })
      queryClient.invalidateQueries({ queryKey: ['roi-analysis'] })
      queryClient.invalidateQueries({ queryKey: ['prediction-accuracy'] })
    },
    onError: () => {
      toast.error('분석 중 오류가 발생했습니다.')
    },
  })

  // 주간 리포트 생성
  const generateWeeklyMutation = useMutation({
    mutationFn: feedbackApi.generateWeeklyReport,
    onSuccess: () => {
      toast.success('주간 리포트가 생성되었습니다.')
      queryClient.invalidateQueries({ queryKey: ['latest-report'] })
    },
    onError: () => {
      toast.error('리포트 생성 중 오류가 발생했습니다.')
    },
  })

  const toggleSection = (section: string) => {
    setExpandedSection(expandedSection === section ? null : section)
  }

  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return '-'
    try {
      return new Date(dateStr).toLocaleDateString('ko-KR', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return dateStr
    }
  }

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/10 rounded-lg">
            <LineChart className="w-6 h-6 text-blue-500" />
          </div>
          <div>
            <h2 className="text-xl font-bold">성과 분석</h2>
            <p className="text-sm text-muted-foreground">
              ROI 추적, 예측 정확도, 성과 리포트
            </p>
          </div>
        </div>
        <Button
          variant="primary"
          onClick={() => runCycleMutation.mutate()}
          loading={runCycleMutation.isPending}
          icon={<Play className="w-4 h-4" />}
          className="bg-blue-600 hover:bg-blue-700"
        >
          전체 분석 실행
        </Button>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center gap-2 text-muted-foreground text-sm mb-1">
            <CheckCircle className="w-4 h-4 text-green-500" />
            <span>30일 전환</span>
          </div>
          <div className="text-2xl font-bold">
            {summaryLoading ? '-' : summary?.total_conversions_30d || 0}
          </div>
        </div>

        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center gap-2 text-muted-foreground text-sm mb-1">
            <Percent className="w-4 h-4 text-blue-500" />
            <span>예측 정확도</span>
          </div>
          <div className="text-2xl font-bold">
            {summaryLoading ? '-' : summary?.overall_accuracy ? `${(summary.overall_accuracy * 100).toFixed(1)}%` : '-'}
          </div>
        </div>

        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center gap-2 text-muted-foreground text-sm mb-1">
            <FileText className="w-4 h-4 text-purple-500" />
            <span>마지막 리포트</span>
          </div>
          <div className="text-sm font-medium truncate">
            {summaryLoading ? '-' : formatDate(summary?.last_weekly_report)}
          </div>
        </div>

        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center gap-2 text-muted-foreground text-sm mb-1">
            <Target className="w-4 h-4 text-orange-500" />
            <span>마지막 ROI 분석</span>
          </div>
          <div className="text-sm font-medium truncate">
            {summaryLoading ? '-' : formatDate(summary?.last_roi_calculation)}
          </div>
        </div>
      </div>

      {/* ROI 분석 섹션 */}
      <div className="bg-card border border-border rounded-lg">
        <button
          onClick={() => toggleSection('roi')}
          className="w-full px-4 py-3 flex items-center justify-between hover:bg-muted/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <BarChart2 className="w-5 h-5 text-green-500" />
            <span className="font-semibold">키워드 ROI 분석</span>
            {roiData?.summary && (
              <span className="text-sm text-muted-foreground">
                (평균 전환율 {(roiData.summary.avg_conversion_rate * 100).toFixed(1)}%)
              </span>
            )}
          </div>
          {expandedSection === 'roi' ? (
            <ChevronUp className="w-5 h-5" />
          ) : (
            <ChevronDown className="w-5 h-5" />
          )}
        </button>

        {expandedSection === 'roi' && (
          <div className="px-4 pb-4 space-y-4">
            {roiLoading ? (
              <div className="animate-pulse space-y-2">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="h-12 bg-muted rounded-lg" />
                ))}
              </div>
            ) : roiData ? (
              <>
                {/* 상위 성과 키워드 */}
                {roiData.top_performers && roiData.top_performers.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
                      <Award className="w-4 h-4 text-yellow-500" />
                      상위 성과 키워드
                    </h4>
                    <div className="space-y-2">
                      {roiData.top_performers.slice(0, 5).map((kw, idx) => (
                        <div key={idx} className="flex items-center justify-between bg-green-500/5 border border-green-500/20 rounded-lg p-3">
                          <div className="flex items-center gap-3">
                            <span className={`w-6 h-6 flex items-center justify-center rounded-full text-xs font-bold ${
                              idx === 0 ? 'bg-yellow-500 text-white' :
                              idx === 1 ? 'bg-gray-400 text-white' :
                              idx === 2 ? 'bg-orange-600 text-white' :
                              'bg-muted text-muted-foreground'
                            }`}>
                              {idx + 1}
                            </span>
                            <span className="font-medium">{kw.keyword}</span>
                          </div>
                          <div className="flex items-center gap-4 text-sm">
                            <div>
                              <span className="text-muted-foreground">리드 </span>
                              <span className="font-medium">{kw.leads_generated}</span>
                            </div>
                            <div>
                              <span className="text-muted-foreground">전환 </span>
                              <span className="font-medium text-green-500">{kw.conversions}</span>
                            </div>
                            <div className="px-2 py-0.5 bg-green-500/10 text-green-500 rounded">
                              {(kw.conversion_rate * 100).toFixed(1)}%
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 저성과 키워드 */}
                {roiData.underperformers && roiData.underperformers.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-orange-500" />
                      개선 필요 키워드
                    </h4>
                    <div className="space-y-2">
                      {roiData.underperformers.slice(0, 5).map((kw, idx) => (
                        <div key={idx} className="flex items-center justify-between bg-orange-500/5 border border-orange-500/20 rounded-lg p-3">
                          <div className="flex items-center gap-2">
                            <XCircle className="w-4 h-4 text-orange-500" />
                            <span className="font-medium">{kw.keyword}</span>
                          </div>
                          <div className="text-sm text-muted-foreground">
                            {kw.leads_generated} 리드, {kw.days_without_conversion}일 전환 없음
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <BarChart2 className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>ROI 데이터가 없습니다.</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 예측 정확도 섹션 */}
      <div className="bg-card border border-border rounded-lg">
        <button
          onClick={() => toggleSection('accuracy')}
          className="w-full px-4 py-3 flex items-center justify-between hover:bg-muted/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Target className="w-5 h-5 text-blue-500" />
            <span className="font-semibold">예측 정확도</span>
            {accuracyData && (
              <span className={`px-2 py-0.5 rounded text-sm ${
                accuracyData.overall_accuracy >= 0.7 ? 'bg-green-500/10 text-green-500' :
                accuracyData.overall_accuracy >= 0.5 ? 'bg-yellow-500/10 text-yellow-500' :
                'bg-red-500/10 text-red-500'
              }`}>
                {(accuracyData.overall_accuracy * 100).toFixed(1)}%
              </span>
            )}
          </div>
          {expandedSection === 'accuracy' ? (
            <ChevronUp className="w-5 h-5" />
          ) : (
            <ChevronDown className="w-5 h-5" />
          )}
        </button>

        {expandedSection === 'accuracy' && (
          <div className="px-4 pb-4">
            {accuracyLoading ? (
              <div className="animate-pulse space-y-3">
                <div className="h-24 bg-muted rounded-lg" />
              </div>
            ) : accuracyData ? (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-muted/30 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-primary">
                      {accuracyData.verified_count || 0}
                    </div>
                    <div className="text-sm text-muted-foreground">검증된 예측</div>
                  </div>
                  <div className="bg-muted/30 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-green-500">
                      {accuracyData.accurate_count || 0}
                    </div>
                    <div className="text-sm text-muted-foreground">정확한 예측</div>
                  </div>
                  <div className="bg-muted/30 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold">
                      {(accuracyData.overall_accuracy * 100).toFixed(1)}%
                    </div>
                    <div className="text-sm text-muted-foreground">전체 정확도</div>
                  </div>
                </div>

                {/* 신뢰도별 정확도 */}
                {accuracyData.by_confidence && Object.keys(accuracyData.by_confidence).length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-2">신뢰도별 정확도</h4>
                    <div className="grid grid-cols-3 gap-2">
                      {Object.entries(accuracyData.by_confidence).map(([level, accuracy]) => (
                        <div key={level} className="bg-muted/50 rounded-lg p-3 text-center">
                          <div className="text-xs text-muted-foreground mb-1">{level}</div>
                          <div className="font-bold">{(Number(accuracy) * 100).toFixed(1)}%</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 추천 사항 */}
                {accuracyData.recommendations && accuracyData.recommendations.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-2">개선 추천</h4>
                    <ul className="space-y-2">
                      {accuracyData.recommendations.map((rec, idx) => (
                        <li key={idx} className="flex items-start gap-2 text-sm bg-blue-500/5 border border-blue-500/20 rounded-lg p-3">
                          <CheckCircle className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
                          <span>{rec}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Target className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>정확도 데이터가 없습니다.</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 성과 리포트 섹션 */}
      <div className="bg-card border border-border rounded-lg">
        <div className="px-4 py-3 flex items-center justify-between border-b border-border">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-purple-500" />
            <span className="font-semibold">성과 리포트</span>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={reportType}
              onChange={(e) => setReportType(e.target.value as 'weekly' | 'monthly')}
              className="px-3 py-1.5 bg-muted border border-border rounded-lg text-sm"
            >
              <option value="weekly">주간</option>
              <option value="monthly">월간</option>
            </select>
            <Button
              variant="primary"
              size="sm"
              onClick={() => generateWeeklyMutation.mutate()}
              loading={generateWeeklyMutation.isPending}
              icon={<FileText className="w-3 h-3" />}
              className="bg-purple-600 hover:bg-purple-700"
            >
              생성
            </Button>
          </div>
        </div>

        <div className="p-4">
          {reportLoading ? (
            <div className="animate-pulse space-y-3">
              <div className="h-32 bg-muted rounded-lg" />
            </div>
          ) : latestReport && 'highlights' in latestReport ? (
            <div className="space-y-4">
              {/* 리포트 헤더 */}
              <div className="flex items-center justify-between">
                <div className="text-sm text-muted-foreground">
                  {latestReport.period} | 생성: {formatDate(latestReport.generated_at)}
                </div>
              </div>

              {/* 주요 지표 */}
              {latestReport.metrics && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="bg-muted/30 rounded-lg p-3 text-center">
                    <div className="text-xl font-bold">{latestReport.metrics.total_leads}</div>
                    <div className="text-xs text-muted-foreground">총 리드</div>
                  </div>
                  <div className="bg-muted/30 rounded-lg p-3 text-center">
                    <div className="text-xl font-bold text-green-500">{latestReport.metrics.total_conversions}</div>
                    <div className="text-xs text-muted-foreground">전환</div>
                  </div>
                  <div className="bg-muted/30 rounded-lg p-3 text-center">
                    <div className="text-xl font-bold">{(latestReport.metrics.conversion_rate * 100).toFixed(1)}%</div>
                    <div className="text-xs text-muted-foreground">전환율</div>
                  </div>
                  <div className="bg-muted/30 rounded-lg p-3 text-center">
                    <div className="text-xl font-bold">{latestReport.metrics.avg_response_time_hours?.toFixed(1)}h</div>
                    <div className="text-xs text-muted-foreground">평균 응답</div>
                  </div>
                </div>
              )}

              {/* 하이라이트 */}
              {latestReport.highlights && latestReport.highlights.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground mb-2">주요 하이라이트</h4>
                  <div className="space-y-2">
                    {latestReport.highlights.map((highlight, idx) => (
                      <div key={idx} className={`flex items-start gap-2 text-sm rounded-lg p-3 ${
                        highlight.type === 'success' ? 'bg-green-500/5 border border-green-500/20' :
                        highlight.type === 'warning' ? 'bg-yellow-500/5 border border-yellow-500/20' :
                        'bg-blue-500/5 border border-blue-500/20'
                      }`}>
                        {highlight.type === 'success' ? (
                          <TrendingUp className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                        ) : highlight.type === 'warning' ? (
                          <AlertTriangle className="w-4 h-4 text-yellow-500 mt-0.5 flex-shrink-0" />
                        ) : (
                          <CheckCircle className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
                        )}
                        <span>{highlight.message}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 추천 사항 */}
              {latestReport.recommendations && latestReport.recommendations.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground mb-2">다음 주 추천</h4>
                  <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground">
                    {latestReport.recommendations.map((rec, idx) => (
                      <li key={idx}>{rec}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>{reportType === 'weekly' ? '주간' : '월간'} 리포트가 아직 생성되지 않았습니다.</p>
              <p className="text-sm">위 버튼을 클릭하여 리포트를 생성하세요.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

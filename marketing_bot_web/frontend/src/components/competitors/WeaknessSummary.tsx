import { useState, useMemo } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { FileText, ExternalLink } from 'lucide-react'
import MetricCard from '../MetricCard'
import { SentimentBar, SentimentSummary } from '@/components/ui/SentimentBadge'
import { useToast } from '@/components/ui/Toast'
import { competitorsApi } from '@/services/api'
import Button, { IconButton } from '@/components/ui/Button'

// 약점 유형별 실행 전략
const WEAKNESS_STRATEGIES: Record<string, { icon: string; title: string; strategies: { text: string; action: string }[] }> = {
  service: {
    icon: '🔧',
    title: '서비스 품질',
    strategies: [
      { text: '친절한 상담 과정 강조', action: '블로그/후기에서 친절 키워드 사용' },
      { text: '치료 과정 상세 설명', action: '유튜브 치료 과정 영상 제작' },
      { text: '예약 편의성 개선', action: '온라인 예약 시스템 홍보' },
      { text: '사후 관리 프로그램 부각', action: '재방문 프로모션 SNS 홍보' },
    ]
  },
  price: {
    icon: '💰',
    title: '가격',
    strategies: [
      { text: '가격 대비 가치 강조', action: '효과 비교 콘텐츠 제작' },
      { text: '투명한 가격 정보 제공', action: '블로그에 가격표 게시' },
      { text: '분할 결제/프로모션 안내', action: 'SNS 할인 이벤트 진행' },
      { text: '무료 상담 제공', action: '맘카페에 무료상담 홍보' },
    ]
  },
  facility: {
    icon: '🏢',
    title: '시설',
    strategies: [
      { text: '청결한 시설 이미지 부각', action: '시설 사진 업데이트' },
      { text: '최신 장비 보유 강조', action: '장비 소개 블로그 포스팅' },
      { text: '편안한 분위기 연출', action: '인테리어 사진 SNS 업로드' },
      { text: '주차 편의성 안내', action: '네이버 플레이스 정보 업데이트' },
    ]
  },
  wait_time: {
    icon: '⏱️',
    title: '대기시간',
    strategies: [
      { text: '예약제 운영 강조', action: '온라인 예약 시스템 홍보' },
      { text: '대기시간 단축 노력 홍보', action: '신속 진료 키워드 사용' },
      { text: '예약 시간 엄수 강조', action: '후기에서 대기없음 언급' },
      { text: '편안한 대기 공간 소개', action: '대기실 사진 업로드' },
    ]
  },
  effect: {
    icon: '✨',
    title: '효과',
    strategies: [
      { text: '실제 치료 사례 공유', action: 'Before/After 콘텐츠 제작' },
      { text: '객관적 데이터 제시', action: '치료 성공률 통계 공개' },
      { text: '환자 후기 적극 활용', action: '영상 후기 촬영' },
      { text: '전문성 강조', action: '의료진 경력 홍보' },
    ]
  }
}

interface WeaknessSummaryProps {
  summary: any
}

export default function WeaknessSummary({ summary }: WeaknessSummaryProps) {
  const [checkedItems, setCheckedItems] = useState<Set<string>>(new Set())
  const [generatedOutline, setGeneratedOutline] = useState<{
    type: string
    outline: any
  } | null>(null)
  const toast = useToast()
  const navigate = useNavigate()

  // [Phase 8.0] 콘텐츠 아웃라인 생성 mutation
  const generateOutlineMutation = useMutation({
    mutationFn: (weaknessType: string) => competitorsApi.generateContentOutline(weaknessType),
    onSuccess: (data, weaknessType) => {
      setGeneratedOutline({ type: weaknessType, outline: data })
      toast.success('콘텐츠 아웃라인이 생성되었습니다!')
    },
    onError: (error: any) => {
      toast.error('아웃라인 생성 실패: ' + (error?.message || '알 수 없는 오류'))
    },
  })

  // 전체 체크리스트 항목 수 계산
  const totalChecklistItems = useMemo(() => {
    if (!summary?.by_type) return 0
    return Object.entries(summary.by_type)
      .filter(([type, count]) => (count as number) > 0 && WEAKNESS_STRATEGIES[type])
      .reduce((total, [type]) => total + (WEAKNESS_STRATEGIES[type]?.strategies.length || 0), 0)
  }, [summary?.by_type])

  if (!summary) return null

  // [Phase 6.0] 감성 분석 데이터 추출
  const sentimentData = {
    positive: summary.sentiment?.positive || 0,
    negative: summary.sentiment?.negative || 0,
    neutral: summary.sentiment?.neutral || 0,
  }
  const hasSentimentData = sentimentData.positive + sentimentData.negative + sentimentData.neutral > 0

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <MetricCard
          title="총 약점"
          value={summary.total || 0}
          icon="🎯"
        />
        <MetricCard
          title="서비스 품질"
          value={summary.by_type?.service || 0}
          icon="🔧"
          color="text-red-500"
        />
        <MetricCard
          title="가격"
          value={summary.by_type?.price || 0}
          icon="💰"
          color="text-yellow-500"
        />
        <MetricCard
          title="시설"
          value={summary.by_type?.facility || 0}
          icon="🏢"
          color="text-blue-500"
        />
      </div>

      {/* [Phase 6.0] 경쟁사 리뷰 감성 분석 */}
      {hasSentimentData && (
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-semibold mb-4">😊 리뷰 감성 분석</h3>
          <div className="space-y-3">
            <SentimentBar {...sentimentData} height={12} />
            <SentimentSummary {...sentimentData} />
          </div>
        </div>
      )}

      {summary.by_competitor && (
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-semibold mb-4">경쟁사별 약점 수</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {Object.entries(summary.by_competitor).map(([name, count]: [string, any]) => (
              <div key={name} className="p-3 rounded-lg bg-muted">
                <div className="text-sm text-muted-foreground mb-1">{name}</div>
                <div className="text-2xl font-bold">{count}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 약점별 실행 전략 체크리스트 */}
      {summary.by_type && Object.keys(summary.by_type).some(k => (summary.by_type[k] || 0) > 0) && (
        <div className="bg-card rounded-lg border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">📋 약점 공략 전략 체크리스트</h3>
            <div className="flex items-center gap-3">
              <div className="w-24 h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 transition-all"
                  style={{ width: `${totalChecklistItems > 0 ? (checkedItems.size / totalChecklistItems) * 100 : 0}%` }}
                />
              </div>
              <div className="text-sm text-muted-foreground whitespace-nowrap">
                {checkedItems.size}/{totalChecklistItems} 완료
              </div>
            </div>
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            경쟁사의 약점을 우리의 강점으로 부각시키는 마케팅 전략입니다.
          </p>
          <div className="space-y-6">
            {Object.entries(summary.by_type || {})
              .filter(([, count]) => (count as number) > 0)
              .map(([type, count]) => {
                const strategy = WEAKNESS_STRATEGIES[type]
                if (!strategy) return null

                return (
                  <div key={type} className="border border-border rounded-lg p-4">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <span className="text-xl">{strategy.icon}</span>
                        <span className="font-semibold">{strategy.title}</span>
                        <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-500">
                          {count as number}건 발견
                        </span>
                      </div>
                      {/* [Phase 8.0] 콘텐츠 아웃라인 생성 버튼 */}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => generateOutlineMutation.mutate(type)}
                        loading={generateOutlineMutation.isPending && generateOutlineMutation.variables === type}
                        icon={<FileText className="w-4 h-4" />}
                        className="text-primary"
                      >
                        콘텐츠 아웃라인 생성
                      </Button>
                    </div>
                    <div className="space-y-2">
                      {strategy.strategies.map((item, idx) => {
                        const itemKey = `${type}-${idx}`
                        const isChecked = checkedItems.has(itemKey)

                        return (
                          <div
                            key={idx}
                            className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                              isChecked ? 'bg-green-500/10' : 'bg-muted/50 hover:bg-muted'
                            }`}
                            onClick={() => {
                              setCheckedItems(prev => {
                                const next = new Set(prev)
                                if (next.has(itemKey)) {
                                  next.delete(itemKey)
                                } else {
                                  next.add(itemKey)
                                }
                                return next
                              })
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => {}}
                              className="mt-1 w-4 h-4 text-green-500 rounded focus:ring-2 focus:ring-green-500 cursor-pointer"
                            />
                            <div className="flex-1">
                              <div className={`font-medium text-sm ${isChecked ? 'line-through text-muted-foreground' : ''}`}>
                                {item.text}
                              </div>
                              <div className="text-xs text-muted-foreground mt-1">
                                💡 {item.action}
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
          </div>
        </div>
      )}

      {/* [Phase 8.0] 생성된 콘텐츠 아웃라인 표시 */}
      {generatedOutline && (
        <div className="bg-card rounded-lg border border-primary/30 p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-primary" />
              <h3 className="text-lg font-semibold">
                AI 생성 콘텐츠 아웃라인
              </h3>
              <span className="text-xs px-2 py-0.5 rounded-full bg-primary/20 text-primary">
                {WEAKNESS_STRATEGIES[generatedOutline.type]?.title || generatedOutline.type} 공략
              </span>
            </div>
            <IconButton
              icon={<span>✕</span>}
              onClick={() => setGeneratedOutline(null)}
              title="닫기"
            />
          </div>

          {/* 아웃라인 내용 */}
          <div className="space-y-4">
            {generatedOutline.outline?.title && (
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-1">제목</h4>
                <p className="text-lg font-semibold">{generatedOutline.outline.title}</p>
              </div>
            )}

            {generatedOutline.outline?.hook && (
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-1">도입부 훅</h4>
                <p className="text-sm bg-muted/50 p-3 rounded-lg">{generatedOutline.outline.hook}</p>
              </div>
            )}

            {generatedOutline.outline?.sections && (
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2">본문 구성</h4>
                <div className="space-y-2">
                  {generatedOutline.outline.sections.map((section: any, idx: number) => (
                    <div key={idx} className="p-3 bg-muted/30 rounded-lg border border-border">
                      <div className="font-medium text-sm">{idx + 1}. {section.heading || section}</div>
                      {section.points && (
                        <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                          {section.points.map((point: string, pidx: number) => (
                            <li key={pidx}>• {point}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {generatedOutline.outline?.keywords && (
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2">추천 키워드</h4>
                <div className="flex flex-wrap gap-2">
                  {generatedOutline.outline.keywords.map((kw: string, idx: number) => (
                    <span key={idx} className="text-xs px-2 py-1 bg-primary/10 text-primary rounded-full">
                      {kw}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {generatedOutline.outline?.cta && (
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-1">CTA (Call to Action)</h4>
                <p className="text-sm bg-green-500/10 text-green-600 p-3 rounded-lg">{generatedOutline.outline.cta}</p>
              </div>
            )}
          </div>

          {/* 액션 버튼 */}
          <div className="flex gap-3 mt-6 pt-4 border-t border-border">
            <Button
              variant="secondary"
              fullWidth
              onClick={() => {
                // 클립보드에 복사
                const outlineText = JSON.stringify(generatedOutline.outline, null, 2)
                navigator.clipboard.writeText(outlineText)
                toast.success('아웃라인이 클립보드에 복사되었습니다')
              }}
            >
              📋 복사하기
            </Button>
            <Button
              variant="primary"
              fullWidth
              onClick={() => navigate('/pathfinder?tab=content')}
              icon={<ExternalLink className="w-4 h-4" />}
            >
              콘텐츠 캘린더에 추가
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

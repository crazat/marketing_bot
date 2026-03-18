import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { competitorsApi } from '@/services/api'
import { Sparkles, Copy, X } from 'lucide-react'
import { useToast } from '@/components/ui/Toast'
import Button, { IconButton } from '@/components/ui/Button'

interface OpportunityKeywordsProps {
  keywords: any[]
}

// [Phase 6.0] 콘텐츠 아이디어 생성 (로컬 생성)
const generateContentIdeas = (keyword: string, weaknessType: string): string[] => {
  const templates: Record<string, string[]> = {
    service: [
      `${keyword} 전문가가 알려주는 맞춤 관리법`,
      `${keyword} 실제 후기로 보는 효과`,
      `${keyword} 선택 시 꼭 확인해야 할 3가지`,
    ],
    price: [
      `${keyword} 합리적인 가격으로 만나는 방법`,
      `${keyword} 가성비 좋은 곳 추천`,
      `${keyword} 비용 완벽 가이드`,
    ],
    facility: [
      `${keyword} 최신 시설에서 받는 프리미엄 케어`,
      `청결하고 쾌적한 ${keyword} 전문점`,
      `${keyword} 환경이 중요한 이유`,
    ],
    time: [
      `${keyword} 빠른 예약, 대기 없이 바로!`,
      `바쁜 현대인을 위한 ${keyword} 빠른 상담`,
      `${keyword} 시간 절약하는 스마트한 방법`,
    ],
    effect: [
      `${keyword} 확실한 효과를 보장하는 곳`,
      `${keyword} 전후 비교 사진으로 보는 변화`,
      `${keyword} 효과 극대화하는 관리 팁`,
    ],
  }

  const defaultTemplates = [
    `${keyword} 완벽 가이드`,
    `${keyword} 전문가 추천`,
    `${keyword} 후회 없는 선택법`,
  ]

  return templates[weaknessType] || defaultTemplates
}

export default function OpportunityKeywords({ keywords }: OpportunityKeywordsProps) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [selectedKeyword, setSelectedKeyword] = useState<any>(null)
  const [contentIdeas, setContentIdeas] = useState<string[]>([])

  const markUsed = useMutation({
    mutationFn: (keyword: string) => competitorsApi.markOpportunityUsed(keyword),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['opportunity-keywords'] })
    },
  })

  const handleGenerateIdeas = (kw: any) => {
    const ideas = generateContentIdeas(kw.keyword, kw.weakness_type)
    setContentIdeas(ideas)
    setSelectedKeyword(kw)
  }

  const handleCopyIdea = (idea: string) => {
    navigator.clipboard.writeText(idea)
    toast.success('클립보드에 복사되었습니다')
  }

  if (!keywords || keywords.length === 0) {
    return (
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-4xl mb-4">🔑</p>
          <p>기회 키워드가 없습니다.</p>
          <p className="text-sm mt-2">경쟁사 약점 분석을 먼저 실행하세요.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-card rounded-lg border border-border p-6">
      <h2 className="text-xl font-bold mb-4">🔑 기회 키워드</h2>
      <p className="text-sm text-muted-foreground mb-6">
        경쟁사 약점을 기반으로 생성된 공략 키워드입니다.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {keywords.map((kw: any, index: number) => (
          <div
            key={index}
            className="p-4 rounded-lg border border-border hover:border-green-500/50 transition-colors"
          >
            <div className="flex items-start justify-between mb-3">
              <h4 className="font-semibold text-green-500">💡 {kw.keyword}</h4>
              <div className="flex gap-1">
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={() => handleGenerateIdeas(kw)}
                  icon={<Sparkles className="w-3 h-3" />}
                  className="text-purple-500 hover:bg-purple-500/20"
                  title="콘텐츠 아이디어 생성"
                >
                  아이디어
                </Button>
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={() => markUsed.mutate(kw.keyword)}
                  className="text-green-500 hover:bg-green-500/20"
                >
                  ✓ 사용
                </Button>
              </div>
            </div>

            <div className="space-y-2 text-sm">
              <div>
                <span className="text-muted-foreground">약점 유형: </span>
                <span className="font-medium">{kw.weakness_type}</span>
              </div>
              <div>
                <span className="text-muted-foreground">우선순위: </span>
                <span className="font-bold text-primary">{kw.priority}</span>
              </div>
              {kw.content_direction && (
                <div className="mt-3 p-3 rounded-lg bg-muted">
                  <div className="text-xs font-semibold mb-1">콘텐츠 방향</div>
                  <p className="text-xs text-muted-foreground">
                    {kw.content_direction}
                  </p>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* [Phase 6.0] 콘텐츠 아이디어 모달 */}
      {selectedKeyword && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-card rounded-lg border border-border p-6 max-w-lg w-full mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-purple-500" />
                콘텐츠 아이디어
              </h3>
              <IconButton
                icon={<X className="w-5 h-5" />}
                onClick={() => setSelectedKeyword(null)}
                title="닫기"
              />
            </div>

            <div className="mb-4 p-3 bg-muted rounded-lg">
              <div className="text-sm text-muted-foreground">키워드</div>
              <div className="font-semibold text-green-500">{selectedKeyword.keyword}</div>
            </div>

            <div className="space-y-3">
              {contentIdeas.map((idea, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-3 bg-muted/50 rounded-lg hover:bg-muted transition-colors"
                >
                  <span className="text-sm flex-1">{idea}</span>
                  <IconButton
                    icon={<Copy className="w-4 h-4" />}
                    onClick={() => handleCopyIdea(idea)}
                    title="복사"
                    className="ml-2"
                  />
                </div>
              ))}
            </div>

            <div className="mt-4 pt-4 border-t border-border">
              <p className="text-xs text-muted-foreground">
                💡 이 아이디어를 기반으로 블로그 포스트나 SNS 콘텐츠를 작성해보세요.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

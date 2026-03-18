/**
 * [Phase D-1] Q&A 매칭 패널
 * 리드 메시지 기반으로 관련 Q&A를 자동 추천
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MessageCircle, Copy, ChevronDown, ChevronUp, Loader2, Search } from 'lucide-react'
import { qaApi, configApi } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import Button from '@/components/ui/Button'

interface QAMatch {
  id: number
  question_pattern: string
  question_category: string
  standard_answer: string
  variations: string[]
  match_score: number
  use_count: number
}

interface QAMatchPanelProps {
  /** 리드의 제목 또는 내용 (매칭에 사용) */
  leadText: string
  /** 리드 플랫폼 */
  platform?: string
  /** 응답 선택 시 콜백 */
  onSelectResponse?: (response: string) => void
  /** 초기 펼침 상태 */
  defaultExpanded?: boolean
}

// 카테고리 정보
const CATEGORY_INFO: Record<string, { label: string; icon: string }> = {
  general: { label: '일반', icon: '💬' },
  price: { label: '가격/비용', icon: '💰' },
  treatment: { label: '치료/시술', icon: '💉' },
  reservation: { label: '예약/상담', icon: '📅' },
  location: { label: '위치/주차', icon: '📍' },
  review: { label: '후기/효과', icon: '⭐' },
}

export default function QAMatchPanel({
  leadText,
  platform,
  onSelectResponse,
  defaultExpanded = false,
}: QAMatchPanelProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)
  const [selectedQA, setSelectedQA] = useState<QAMatch | null>(null)

  // [Phase 7.0] 브랜딩 정보 가져오기
  const { data: branding } = useQuery({
    queryKey: ['branding'],
    queryFn: configApi.getBranding,
    staleTime: 1000 * 60 * 60, // 1시간 캐시
    retry: 1,
  })
  const [customQuery, setCustomQuery] = useState('')
  const toast = useToast()

  // 매칭 쿼리 텍스트 (커스텀 입력 또는 리드 텍스트)
  const queryText = customQuery.trim() || leadText

  // Q&A 매칭 조회
  const { data: matchData, isLoading, refetch } = useQuery({
    queryKey: ['qa-match', queryText],
    queryFn: () => qaApi.match(queryText, 5),
    enabled: isExpanded && queryText.length > 2,
    staleTime: 60000, // [Phase 7] 30초 → 60초
  })

  const matches: QAMatch[] = matchData?.matches || []

  // 응답 복사
  const handleCopyResponse = (response: string) => {
    navigator.clipboard.writeText(response)
    toast.success('응답이 클립보드에 복사되었습니다')

    // 콜백이 있으면 호출
    if (onSelectResponse) {
      onSelectResponse(response)
    }
  }

  // 플랫폼별 응답 포맷팅 (선택적)
  const formatResponseForPlatform = (response: string): string => {
    if (!platform) return response

    // [Phase 7.0] business_profile.json에서 서명 가져오기
    const signatures = branding?.signatures || {}
    const suffix = signatures[platform] || ''

    return response + suffix
  }

  // 카테고리 라벨 가져오기
  const getCategoryInfo = (category: string) => {
    return CATEGORY_INFO[category] || { label: category, icon: '💬' }
  }

  return (
    <div className="border border-primary/30 rounded-lg overflow-hidden">
      {/* 헤더 */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-4 py-3 bg-primary/5 hover:bg-primary/10 transition-colors"
      >
        <div className="flex items-center gap-2">
          <MessageCircle className="w-4 h-4 text-primary" />
          <span className="font-medium text-sm">Q&A 자동 매칭</span>
          {matches.length > 0 && (
            <span className="px-2 py-0.5 text-xs bg-primary/20 text-primary rounded-full">
              {matches.length}개 매칭
            </span>
          )}
        </div>
        {isExpanded ? (
          <ChevronUp className="w-4 h-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="w-4 h-4 text-muted-foreground" />
        )}
      </button>

      {/* 본문 */}
      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* 검색 입력 */}
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="text"
                value={customQuery}
                onChange={(e) => setCustomQuery(e.target.value)}
                placeholder={leadText.slice(0, 50) + '...'}
                className="w-full pl-9 pr-3 py-2 text-sm bg-muted/50 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => refetch()}
              loading={isLoading}
              className="bg-primary/10 text-primary hover:bg-primary/20"
            >
              검색
            </Button>
          </div>

          {/* 매칭 결과 */}
          {isLoading ? (
            <div className="flex items-center justify-center py-6">
              <Loader2 className="w-5 h-5 animate-spin text-primary mr-2" />
              <span className="text-sm text-muted-foreground">Q&A 검색 중...</span>
            </div>
          ) : matches.length === 0 ? (
            <div className="text-center py-6">
              <MessageCircle className="w-8 h-8 mx-auto mb-2 text-muted-foreground/50" />
              <p className="text-sm text-muted-foreground">
                {queryText.length > 2
                  ? '매칭되는 Q&A가 없습니다'
                  : '검색어를 입력하세요 (3자 이상)'}
              </p>
              <a
                href="/qa"
                className="text-xs text-primary hover:underline mt-2 inline-block"
              >
                Q&A Repository에서 추가하기
              </a>
            </div>
          ) : (
            <div className="space-y-3">
              {matches.map((qa, idx) => {
                const isSelected = selectedQA?.id === qa.id
                const categoryInfo = getCategoryInfo(qa.question_category)

                return (
                  <div
                    key={qa.id}
                    className={`border rounded-lg transition-all ${
                      isSelected
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:border-primary/50'
                    }`}
                  >
                    {/* Q&A 헤더 */}
                    <div
                      className="flex items-center justify-between p-3 cursor-pointer"
                      onClick={() => setSelectedQA(isSelected ? null : qa)}
                    >
                      <div className="flex items-center gap-2 flex-1 min-w-0">
                        <span className="text-xs font-medium text-primary">
                          #{idx + 1}
                        </span>
                        <span className="text-xs px-2 py-0.5 rounded-full bg-muted">
                          {categoryInfo.icon} {categoryInfo.label}
                        </span>
                        <span className="text-sm font-medium truncate">
                          {qa.question_pattern}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 ml-2">
                        <span className="text-xs text-muted-foreground">
                          점수: {qa.match_score}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          사용: {qa.use_count}회
                        </span>
                      </div>
                    </div>

                    {/* 확장된 응답 */}
                    {isSelected && (
                      <div className="px-3 pb-3 space-y-3">
                        <div className="bg-muted/50 rounded-lg p-3">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-xs font-medium text-muted-foreground">
                              표준 응답
                            </span>
                            <Button
                              variant="primary"
                              size="xs"
                              onClick={(e) => {
                                e.stopPropagation()
                                handleCopyResponse(
                                  formatResponseForPlatform(qa.standard_answer)
                                )
                              }}
                              icon={<Copy className="w-3 h-3" />}
                            >
                              복사하여 사용
                            </Button>
                          </div>
                          <p className="text-sm whitespace-pre-wrap">
                            {qa.standard_answer}
                          </p>
                        </div>

                        {/* 변형 패턴 */}
                        {qa.variations && qa.variations.length > 0 && (
                          <div>
                            <span className="text-xs text-muted-foreground">
                              유사 질문 패턴:
                            </span>
                            <div className="flex flex-wrap gap-1 mt-1">
                              {qa.variations.map((v, vIdx) => (
                                <span
                                  key={vIdx}
                                  className="text-xs px-2 py-0.5 bg-muted rounded"
                                >
                                  {v}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* 플랫폼 맞춤 응답 미리보기 */}
                        {platform && (
                          <div className="pt-2 border-t border-border">
                            <span className="text-xs text-muted-foreground">
                              {platform} 플랫폼용 응답 미리보기:
                            </span>
                            <div className="mt-1 p-2 bg-green-500/5 border border-green-500/20 rounded text-xs">
                              {formatResponseForPlatform(qa.standard_answer)}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* 안내 문구 */}
          <div className="text-xs text-muted-foreground text-center pt-2 border-t border-border">
            리드 내용을 분석하여 Q&A Repository에서 가장 적합한 응답을 추천합니다
          </div>
        </div>
      )}
    </div>
  )
}

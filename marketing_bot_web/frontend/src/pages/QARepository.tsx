/**
 * [Phase 8.0] Q&A Repository 페이지
 * 자주 묻는 질문 패턴 및 표준 응답 관리
 */

import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  MessageCircle,
  Plus,
  Search,
  Edit2,
  Trash2,
  Copy,
  TestTube,
  Loader2,
  ChevronDown,
  ChevronUp,
  Tag,
  BarChart3,
  X,
} from 'lucide-react'
import { useToast } from '@/components/ui/Toast'
import MetricCard from '@/components/MetricCard'
import { ConfirmModal } from '@/components/ui/Modal'
import { qaApi } from '@/services/api'
import Button, { IconButton } from '@/components/ui/Button'

interface QAItem {
  id: number
  question_pattern: string
  question_category: string
  standard_answer: string
  variations: string[]
  use_count: number
  created_at: string
  updated_at: string
}

interface QAFormData {
  question_pattern: string
  question_category: string
  standard_answer: string
  variations: string[]
}

// 카테고리 옵션
const CATEGORY_OPTIONS = [
  { value: 'general', label: '일반', icon: '💬' },
  { value: 'price', label: '가격/비용', icon: '💰' },
  { value: 'treatment', label: '치료/시술', icon: '💉' },
  { value: 'reservation', label: '예약/상담', icon: '📅' },
  { value: 'location', label: '위치/주차', icon: '📍' },
  { value: 'review', label: '후기/효과', icon: '⭐' },
]

export default function QARepository() {
  const [selectedCategory, setSelectedCategory] = useState<string>('')
  const [searchQuery, setSearchQuery] = useState('')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<QAItem | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<QAItem | null>(null)
  const [expandedItems, setExpandedItems] = useState<Set<number>>(new Set())

  // 매칭 테스트 상태
  const [testMode, setTestMode] = useState(false)
  const [testQuery, setTestQuery] = useState('')
  const [testResults, setTestResults] = useState<any[] | null>(null)

  const toast = useToast()
  const queryClient = useQueryClient()

  // Q&A 목록 조회
  const { data: qaData, isLoading: isLoadingList } = useQuery({
    queryKey: ['qa-list', selectedCategory],
    queryFn: () => qaApi.getList({ category: selectedCategory || undefined, limit: 100 }).catch(() => ({ qa_list: [], total: 0 })),
    staleTime: 60000, // 1분간 캐시
    retry: 1,
  })

  // Q&A 통계 조회
  const { data: stats } = useQuery({
    queryKey: ['qa-stats'],
    queryFn: () => qaApi.getStats().catch(() => null),
    staleTime: 60000, // 1분간 캐시
    retry: 1,
  })

  // Q&A 생성 mutation
  const createMutation = useMutation({
    mutationFn: (data: QAFormData) => qaApi.create(data),
    onSuccess: () => {
      toast.success('Q&A가 등록되었습니다')
      queryClient.invalidateQueries({ queryKey: ['qa-list'] })
      queryClient.invalidateQueries({ queryKey: ['qa-stats'] })
      setIsModalOpen(false)
      setEditingItem(null)
    },
    onError: (error: any) => {
      toast.error('등록 실패: ' + (error?.message || '알 수 없는 오류'))
    },
  })

  // Q&A 수정 mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<QAFormData> }) =>
      qaApi.update(id, data),
    onSuccess: () => {
      toast.success('Q&A가 수정되었습니다')
      queryClient.invalidateQueries({ queryKey: ['qa-list'] })
      queryClient.invalidateQueries({ queryKey: ['qa-stats'] })
      setIsModalOpen(false)
      setEditingItem(null)
    },
    onError: (error: any) => {
      toast.error('수정 실패: ' + (error?.message || '알 수 없는 오류'))
    },
  })

  // Q&A 삭제 mutation
  const deleteMutation = useMutation({
    mutationFn: (id: number) => qaApi.delete(id),
    onSuccess: () => {
      toast.success('Q&A가 삭제되었습니다')
      queryClient.invalidateQueries({ queryKey: ['qa-list'] })
      queryClient.invalidateQueries({ queryKey: ['qa-stats'] })
      setDeleteTarget(null)
    },
    onError: (error: any) => {
      toast.error('삭제 실패: ' + (error?.message || '알 수 없는 오류'))
    },
  })

  // 매칭 테스트 mutation
  const matchMutation = useMutation({
    mutationFn: (text: string) => qaApi.match(text, 5),
    onSuccess: (data) => {
      setTestResults(data.matches || [])
      if (data.matches?.length === 0) {
        toast.info('매칭되는 Q&A가 없습니다')
      }
    },
    onError: (error: any) => {
      toast.error('매칭 실패: ' + (error?.message || '알 수 없는 오류'))
    },
  })

  // 필터링된 목록
  const filteredItems = useMemo(() => {
    if (!qaData?.items) return []
    if (!searchQuery) return qaData.items

    const query = searchQuery.toLowerCase()
    return qaData.items.filter((item: QAItem) =>
      item.question_pattern.toLowerCase().includes(query) ||
      item.standard_answer.toLowerCase().includes(query) ||
      item.variations?.some((v: string) => v.toLowerCase().includes(query))
    )
  }, [qaData?.items, searchQuery])

  // 아이템 확장/축소 토글
  const toggleExpand = (id: number) => {
    setExpandedItems(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  // 응답 복사
  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text)
    toast.success('클립보드에 복사되었습니다')
  }

  // 카테고리 라벨 가져오기
  const getCategoryInfo = (value: string) => {
    return CATEGORY_OPTIONS.find(c => c.value === value) || { label: value, icon: '💬' }
  }

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <MessageCircle className="w-7 h-7 text-primary" />
            Q&A Repository
          </h1>
          <p className="text-muted-foreground mt-1">
            자주 묻는 질문 패턴과 표준 응답을 관리합니다
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={testMode ? 'primary' : 'secondary'}
            onClick={() => setTestMode(!testMode)}
            icon={<TestTube className="w-4 h-4" />}
          >
            매칭 테스트
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              setEditingItem(null)
              setIsModalOpen(true)
            }}
            icon={<Plus className="w-4 h-4" />}
          >
            새 Q&A 등록
          </Button>
        </div>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          title="총 Q&A"
          value={stats?.total || 0}
          icon="📚"
        />
        <MetricCard
          title="총 사용 횟수"
          value={stats?.total_uses || 0}
          icon="📊"
        />
        <MetricCard
          title="카테고리"
          value={Object.keys(stats?.by_category || {}).length}
          icon="🏷️"
        />
        <MetricCard
          title="최다 사용"
          value={stats?.top_used?.[0]?.use_count || 0}
          icon="🔥"
          subtitle={stats?.top_used?.[0]?.question_pattern?.slice(0, 15) + '...'}
        />
      </div>

      {/* 매칭 테스트 패널 */}
      {testMode && (
        <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-4">
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <TestTube className="w-5 h-5 text-purple-500" />
            질문 매칭 테스트
          </h3>
          <div className="flex gap-2 mb-4">
            <input
              type="text"
              value={testQuery}
              onChange={(e) => setTestQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && testQuery.trim()) {
                  matchMutation.mutate(testQuery)
                }
              }}
              placeholder="테스트할 질문을 입력하세요 (예: 가격이 얼마인가요?)"
              className="flex-1 px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <Button
              variant="primary"
              onClick={() => testQuery.trim() && matchMutation.mutate(testQuery)}
              disabled={!testQuery.trim()}
              loading={matchMutation.isPending}
            >
              테스트
            </Button>
          </div>

          {testResults && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                {testResults.length}개의 매칭 결과
              </p>
              {testResults.map((result, idx) => (
                <div
                  key={result.id}
                  className="p-3 bg-background rounded-lg border border-border"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium">
                      #{idx + 1} 매칭 점수: {result.match_score}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-500">
                      {getCategoryInfo(result.question_category).icon} {getCategoryInfo(result.question_category).label}
                    </span>
                  </div>
                  <p className="text-sm mb-1">
                    <strong>패턴:</strong> {result.question_pattern}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    <strong>응답:</strong> {result.standard_answer.slice(0, 100)}...
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 필터 및 검색 */}
      <div className="flex flex-col md:flex-row gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="질문 패턴 또는 응답 검색..."
            className="w-full pl-10 pr-4 py-2 bg-card border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <div className="flex items-center gap-2">
          <Tag className="w-5 h-5 text-muted-foreground" />
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="px-4 py-2 bg-card border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">전체 카테고리</option>
            {CATEGORY_OPTIONS.map((cat) => (
              <option key={cat.value} value={cat.value}>
                {cat.icon} {cat.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Q&A 목록 */}
      <div className="bg-card rounded-lg border border-border">
        {isLoadingList ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <MessageCircle className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>등록된 Q&A가 없습니다</p>
            <Button
              variant="ghost"
              onClick={() => setIsModalOpen(true)}
              className="mt-3"
            >
              첫 Q&A를 등록해보세요
            </Button>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {filteredItems.map((item: QAItem) => {
              const isExpanded = expandedItems.has(item.id)
              const categoryInfo = getCategoryInfo(item.question_category)

              return (
                <div key={item.id} className="p-4">
                  <div
                    className="flex items-start justify-between cursor-pointer"
                    onClick={() => toggleExpand(item.id)}
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                          {categoryInfo.icon} {categoryInfo.label}
                        </span>
                        <span className="text-xs text-muted-foreground flex items-center gap-1">
                          <BarChart3 className="w-3 h-3" />
                          {item.use_count}회 사용
                        </span>
                      </div>
                      <h3 className="font-medium">{item.question_pattern}</h3>
                      {!isExpanded && (
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-1">
                          {item.standard_answer}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      <IconButton
                        icon={<Copy className="w-4 h-4" />}
                        onClick={(e) => {
                          e.stopPropagation()
                          handleCopy(item.standard_answer)
                        }}
                        size="sm"
                        title="응답 복사"
                      />
                      <IconButton
                        icon={<Edit2 className="w-4 h-4 text-blue-500" />}
                        onClick={(e) => {
                          e.stopPropagation()
                          setEditingItem(item)
                          setIsModalOpen(true)
                        }}
                        size="sm"
                        title="수정"
                      />
                      <IconButton
                        icon={<Trash2 className="w-4 h-4 text-red-500" />}
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeleteTarget(item)
                        }}
                        size="sm"
                        title="삭제"
                      />
                      {isExpanded ? (
                        <ChevronUp className="w-5 h-5 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="w-5 h-5 text-muted-foreground" />
                      )}
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="mt-4 pl-4 border-l-2 border-primary/30">
                      <div className="mb-3">
                        <h4 className="text-sm font-medium text-muted-foreground mb-1">표준 응답</h4>
                        <p className="text-sm whitespace-pre-wrap bg-muted/50 p-3 rounded-lg">
                          {item.standard_answer}
                        </p>
                      </div>
                      {item.variations && item.variations.length > 0 && (
                        <div>
                          <h4 className="text-sm font-medium text-muted-foreground mb-1">
                            변형 패턴 ({item.variations.length}개)
                          </h4>
                          <div className="flex flex-wrap gap-2">
                            {item.variations.map((v, idx) => (
                              <span
                                key={idx}
                                className="text-xs px-2 py-1 bg-muted rounded-full"
                              >
                                {v}
                              </span>
                            ))}
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
      </div>

      {/* Q&A 등록/수정 모달 */}
      {isModalOpen && (
        <QAFormModal
          item={editingItem}
          onClose={() => {
            setIsModalOpen(false)
            setEditingItem(null)
          }}
          onSubmit={(data) => {
            if (editingItem) {
              updateMutation.mutate({ id: editingItem.id, data })
            } else {
              createMutation.mutate(data)
            }
          }}
          isLoading={createMutation.isPending || updateMutation.isPending}
        />
      )}

      {/* 삭제 확인 모달 */}
      <ConfirmModal
        isOpen={!!deleteTarget}
        title="Q&A 삭제"
        message={`"${deleteTarget?.question_pattern}" Q&A를 삭제하시겠습니까?`}
        confirmText="삭제"
        variant="danger"
        loading={deleteMutation.isPending}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  )
}

// Q&A 등록/수정 모달 컴포넌트
function QAFormModal({
  item,
  onClose,
  onSubmit,
  isLoading,
}: {
  item: QAItem | null
  onClose: () => void
  onSubmit: (data: QAFormData) => void
  isLoading: boolean
}) {
  const [formData, setFormData] = useState<QAFormData>({
    question_pattern: item?.question_pattern || '',
    question_category: item?.question_category || 'general',
    standard_answer: item?.standard_answer || '',
    variations: item?.variations || [],
  })
  const [newVariation, setNewVariation] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.question_pattern.trim() || !formData.standard_answer.trim()) {
      return
    }
    onSubmit(formData)
  }

  const addVariation = () => {
    if (newVariation.trim() && !formData.variations.includes(newVariation.trim())) {
      setFormData({
        ...formData,
        variations: [...formData.variations, newVariation.trim()],
      })
      setNewVariation('')
    }
  }

  const removeVariation = (idx: number) => {
    setFormData({
      ...formData,
      variations: formData.variations.filter((_, i) => i !== idx),
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-card rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto m-4">
        <div className="sticky top-0 bg-card border-b border-border px-6 py-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">
            {item ? 'Q&A 수정' : '새 Q&A 등록'}
          </h2>
          <IconButton
            icon={<X className="w-5 h-5" />}
            onClick={onClose}
            size="sm"
            title="닫기"
          />
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* 카테고리 */}
          <div>
            <label className="block text-sm font-medium mb-1">카테고리</label>
            <select
              value={formData.question_category}
              onChange={(e) =>
                setFormData({ ...formData, question_category: e.target.value })
              }
              className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {CATEGORY_OPTIONS.map((cat) => (
                <option key={cat.value} value={cat.value}>
                  {cat.icon} {cat.label}
                </option>
              ))}
            </select>
          </div>

          {/* 질문 패턴 */}
          <div>
            <label className="block text-sm font-medium mb-1">
              질문 패턴 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={formData.question_pattern}
              onChange={(e) =>
                setFormData({ ...formData, question_pattern: e.target.value })
              }
              placeholder="예: 가격이 얼마인가요?"
              className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              required
            />
            <p className="text-xs text-muted-foreground mt-1">
              정규식 패턴도 사용 가능합니다 (예: 가격.*얼마)
            </p>
          </div>

          {/* 표준 응답 */}
          <div>
            <label className="block text-sm font-medium mb-1">
              표준 응답 <span className="text-red-500">*</span>
            </label>
            <textarea
              value={formData.standard_answer}
              onChange={(e) =>
                setFormData({ ...formData, standard_answer: e.target.value })
              }
              placeholder="질문에 대한 표준 응답을 입력하세요..."
              rows={5}
              className="w-full px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none"
              required
            />
          </div>

          {/* 변형 패턴 */}
          <div>
            <label className="block text-sm font-medium mb-1">변형 패턴</label>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={newVariation}
                onChange={(e) => setNewVariation(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addVariation()
                  }
                }}
                placeholder="변형 패턴 추가 (Enter로 추가)"
                className="flex-1 px-4 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <IconButton
                icon={<Plus className="w-5 h-5" />}
                onClick={addVariation}
                size="md"
                title="변형 패턴 추가"
              />
            </div>
            {formData.variations.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {formData.variations.map((v, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center gap-1 text-sm px-2 py-1 bg-muted rounded-full"
                  >
                    {v}
                    <IconButton
                      icon={<X className="w-3 h-3" />}
                      onClick={() => removeVariation(idx)}
                      size="xs"
                      title="삭제"
                    />
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* 액션 버튼 */}
          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
            >
              취소
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={!formData.question_pattern.trim() || !formData.standard_answer.trim()}
              loading={isLoading}
            >
              {item ? '수정' : '등록'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}

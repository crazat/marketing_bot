/**
 * Q&A Repository 탭 컴포넌트
 * 질문 패턴 및 표준 응답 관리
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { qaApi } from '@/services/api'
import Button, { IconButton } from '@/components/ui/Button'
import { ConfirmModal } from '@/components/ui/Modal'
import { getErrorMessage } from '@/utils/errorMessages'
import {
  Plus,
  Pencil,
  Trash2,
  MessageSquare,
} from 'lucide-react'

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

interface QAStats {
  total: number
  total_uses: number
  by_category: Record<string, number>
  top_used: Array<{ id: number; use_count: number }>
}

interface QAListResponse {
  items: QAItem[]
  total: number
}

interface QATabProps {
  onMessage: (message: { type: 'success' | 'error'; text: string }) => void
}

export default function QATab({ onMessage }: QATabProps) {
  const queryClient = useQueryClient()

  // Q&A 관련 상태
  const [qaEditMode, setQaEditMode] = useState<'create' | 'edit' | null>(null)
  const [qaEditItem, setQaEditItem] = useState<QAItem | null>(null)
  const [qaDeleteId, setQaDeleteId] = useState<number | null>(null)
  const [qaForm, setQaForm] = useState({
    question_pattern: '',
    question_category: 'general',
    standard_answer: '',
    variations: ''
  })

  // Q&A 목록 조회
  const { data: qaData, isLoading: qaLoading } = useQuery<QAListResponse>({
    queryKey: ['qa-list'],
    queryFn: () => qaApi.getList({ limit: 100 }).catch(() => ({ items: [], total: 0 })),
    retry: 1,
  })

  // Q&A 통계 조회
  const { data: qaStats } = useQuery<QAStats>({
    queryKey: ['qa-stats'],
    queryFn: () => qaApi.getStats().catch(() => null),
    retry: 1,
  })

  // Q&A 생성
  const createQaMutation = useMutation({
    mutationFn: qaApi.create,
    onSuccess: () => {
      onMessage({ type: 'success', text: 'Q&A가 등록되었습니다.' })
      queryClient.invalidateQueries({ queryKey: ['qa-list'] })
      queryClient.invalidateQueries({ queryKey: ['qa-stats'] })
      resetQaForm()
    },
    onError: (error: unknown) => {
      onMessage({ type: 'error', text: getErrorMessage(error) })
    },
  })

  // Q&A 수정
  const updateQaMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Parameters<typeof qaApi.update>[1] }) =>
      qaApi.update(id, data),
    onSuccess: () => {
      onMessage({ type: 'success', text: 'Q&A가 수정되었습니다.' })
      queryClient.invalidateQueries({ queryKey: ['qa-list'] })
      resetQaForm()
    },
    onError: (error: unknown) => {
      onMessage({ type: 'error', text: getErrorMessage(error) })
    },
  })

  // Q&A 삭제
  const deleteQaMutation = useMutation({
    mutationFn: qaApi.delete,
    onSuccess: () => {
      onMessage({ type: 'success', text: 'Q&A가 삭제되었습니다.' })
      queryClient.invalidateQueries({ queryKey: ['qa-list'] })
      queryClient.invalidateQueries({ queryKey: ['qa-stats'] })
      setQaDeleteId(null)
    },
    onError: (error: unknown) => {
      onMessage({ type: 'error', text: getErrorMessage(error) })
    },
  })

  // Q&A 폼 초기화
  const resetQaForm = () => {
    setQaEditMode(null)
    setQaEditItem(null)
    setQaForm({
      question_pattern: '',
      question_category: 'general',
      standard_answer: '',
      variations: ''
    })
  }

  // Q&A 편집 시작
  const startEditQa = (item: QAItem) => {
    setQaEditMode('edit')
    setQaEditItem(item)
    setQaForm({
      question_pattern: item.question_pattern,
      question_category: item.question_category,
      standard_answer: item.standard_answer,
      variations: item.variations.join('\n')
    })
  }

  // Q&A 저장
  const handleSaveQa = () => {
    const variations = qaForm.variations.split('\n').filter(v => v.trim())
    if (qaEditMode === 'create') {
      createQaMutation.mutate({
        question_pattern: qaForm.question_pattern,
        question_category: qaForm.question_category,
        standard_answer: qaForm.standard_answer,
        variations
      })
    } else if (qaEditMode === 'edit' && qaEditItem) {
      updateQaMutation.mutate({
        id: qaEditItem.id,
        data: {
          question_pattern: qaForm.question_pattern,
          question_category: qaForm.question_category,
          standard_answer: qaForm.standard_answer,
          variations
        }
      })
    }
  }

  return (
    <>
      {/* Q&A 통계 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">💬 Q&A Repository</h3>
          <Button
            variant="primary"
            onClick={() => {
              resetQaForm()
              setQaEditMode('create')
            }}
            icon={<Plus className="w-4 h-4" />}
          >
            새 Q&A 추가
          </Button>
        </div>

        {/* 통계 카드 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="p-4 bg-muted/50 rounded-lg text-center">
            <div className="text-2xl font-bold text-primary">{qaStats?.total || 0}</div>
            <div className="text-sm text-muted-foreground">총 Q&A</div>
          </div>
          <div className="p-4 bg-muted/50 rounded-lg text-center">
            <div className="text-2xl font-bold text-green-500">{qaStats?.total_uses || 0}</div>
            <div className="text-sm text-muted-foreground">총 사용 횟수</div>
          </div>
          <div className="p-4 bg-muted/50 rounded-lg text-center">
            <div className="text-2xl font-bold text-blue-500">
              {Object.keys(qaStats?.by_category || {}).length}
            </div>
            <div className="text-sm text-muted-foreground">카테고리</div>
          </div>
          <div className="p-4 bg-muted/50 rounded-lg text-center">
            <div className="text-2xl font-bold text-purple-500">
              {qaStats?.top_used?.[0]?.use_count || 0}
            </div>
            <div className="text-sm text-muted-foreground">최다 사용</div>
          </div>
        </div>

        {/* Q&A 폼 (생성/수정) */}
        {qaEditMode && (
          <div className="mb-6 p-4 bg-muted/30 rounded-lg border border-border">
            <h4 className="font-medium mb-4">
              {qaEditMode === 'create' ? '➕ 새 Q&A 등록' : '✏️ Q&A 수정'}
            </h4>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">질문 패턴 (정규식 가능)</label>
                <input
                  type="text"
                  value={qaForm.question_pattern}
                  onChange={(e) => setQaForm(prev => ({ ...prev, question_pattern: e.target.value }))}
                  placeholder="예: 가격|비용|얼마"
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">카테고리</label>
                <select
                  value={qaForm.question_category}
                  onChange={(e) => setQaForm(prev => ({ ...prev, question_category: e.target.value }))}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="general">일반</option>
                  <option value="price">가격/비용</option>
                  <option value="service">서비스</option>
                  <option value="location">위치/접근성</option>
                  <option value="reservation">예약</option>
                  <option value="effect">효과/후기</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">표준 응답</label>
                <textarea
                  value={qaForm.standard_answer}
                  onChange={(e) => setQaForm(prev => ({ ...prev, standard_answer: e.target.value }))}
                  placeholder="질문에 대한 표준 응답을 입력하세요..."
                  rows={4}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">변형 키워드 (줄바꿈으로 구분)</label>
                <textarea
                  value={qaForm.variations}
                  onChange={(e) => setQaForm(prev => ({ ...prev, variations: e.target.value }))}
                  placeholder="추가 매칭 키워드를 줄바꿈으로 구분하여 입력..."
                  rows={3}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none"
                />
              </div>
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  onClick={handleSaveQa}
                  disabled={!qaForm.question_pattern || !qaForm.standard_answer}
                  loading={createQaMutation.isPending || updateQaMutation.isPending}
                >
                  저장
                </Button>
                <Button
                  variant="secondary"
                  onClick={resetQaForm}
                >
                  취소
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Q&A 목록 */}
        {qaLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-24 bg-muted rounded-lg animate-pulse" />
            ))}
          </div>
        ) : !qaData?.items || qaData.items.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <MessageSquare className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p className="font-medium mb-2">등록된 Q&A가 없습니다</p>
            <p className="text-sm">위 버튼을 클릭하여 첫 Q&A를 등록하세요.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {qaData.items.map((item: QAItem) => (
              <div
                key={item.id}
                className="p-4 bg-muted/30 rounded-lg border border-border hover:border-primary/50 transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="px-2 py-0.5 bg-primary/10 text-primary rounded text-xs font-medium">
                        {item.question_category}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        사용 {item.use_count}회
                      </span>
                    </div>
                    <div className="font-medium mb-1 truncate" title={item.question_pattern}>
                      📝 {item.question_pattern}
                    </div>
                    <div className="text-sm text-muted-foreground line-clamp-2">
                      {item.standard_answer}
                    </div>
                    {item.variations.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {item.variations.slice(0, 3).map((v, i) => (
                          <span key={i} className="px-2 py-0.5 bg-muted rounded text-xs">
                            {v}
                          </span>
                        ))}
                        {item.variations.length > 3 && (
                          <span className="px-2 py-0.5 text-muted-foreground text-xs">
                            +{item.variations.length - 3}개
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <IconButton
                      icon={<Pencil className="w-4 h-4" />}
                      onClick={() => startEditQa(item)}
                      size="sm"
                      title="수정"
                    />
                    <IconButton
                      icon={<Trash2 className="w-4 h-4" />}
                      onClick={() => setQaDeleteId(item.id)}
                      size="sm"
                      title="삭제"
                      className="hover:bg-red-500/10 text-red-500"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Q&A 삭제 확인 모달 */}
      <ConfirmModal
        isOpen={qaDeleteId !== null}
        onClose={() => setQaDeleteId(null)}
        onConfirm={() => qaDeleteId && deleteQaMutation.mutate(qaDeleteId)}
        title="Q&A 삭제"
        message="이 Q&A를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다."
        confirmText="삭제"
        cancelText="취소"
        variant="danger"
        loading={deleteQaMutation.isPending}
      />
    </>
  )
}

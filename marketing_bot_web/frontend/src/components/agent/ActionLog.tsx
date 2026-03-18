import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { agentApi } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/utils/errorMessages'
import Button from '@/components/ui/Button'

// JSON 데이터 타입 (input_data, output_data용)
type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }
type JsonData = Record<string, JsonValue> | null

interface Action {
  id: number
  action_type: string
  target_type: string | null
  target_id: string | null
  input_data: JsonData
  output_data: JsonData
  status: 'pending' | 'approved' | 'rejected' | 'completed'
  created_at: string
  approved_at: string | null
  completed_at: string | null
  error_message: string | null
  tokens_used: number
}

interface ActionLogProps {
  actions: Action[]
  total: number
  pendingCount: number
  onPageChange?: (offset: number) => void
  currentOffset?: number
  limit?: number
}

const ACTION_TYPE_LABELS: Record<string, { label: string; icon: string }> = {
  comment: { label: '댓글 생성', icon: '💬' },
  analysis: { label: '분석', icon: '📊' },
  content: { label: '콘텐츠 생성', icon: '✍️' },
  keyword: { label: '키워드 분석', icon: '🔍' },
  weakness: { label: '약점 분석', icon: '💪' },
  default: { label: '기타', icon: '🤖' },
}

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  pending: { bg: 'bg-yellow-100 dark:bg-yellow-900/30', text: 'text-yellow-700 dark:text-yellow-400', label: '대기 중' },
  approved: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-400', label: '승인됨' },
  rejected: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-700 dark:text-red-400', label: '거절됨' },
  completed: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-400', label: '완료' },
}

// 데이터 뷰어 컴포넌트 - JSON을 읽기 쉽게 표시
function DataViewer({ data }: { data: JsonData }) {
  const [isRawView, setIsRawView] = useState(false)

  // 객체가 아니거나 비어있으면 간단히 표시
  if (!data || typeof data !== 'object') {
    return (
      <div className="text-xs bg-muted p-2 rounded">
        {String(data)}
      </div>
    )
  }

  const entries = Object.entries(data)
  if (entries.length === 0) {
    return (
      <div className="text-xs text-muted-foreground bg-muted p-2 rounded">
        (빈 데이터)
      </div>
    )
  }

  // 키 레이블 매핑
  const keyLabels: Record<string, string> = {
    keyword: '키워드',
    keywords: '키워드 목록',
    content: '내용',
    comment: '댓글',
    target_id: '대상 ID',
    target_url: '대상 URL',
    platform: '플랫폼',
    category: '카테고리',
    result: '결과',
    message: '메시지',
    score: '점수',
    count: '개수',
    success: '성공 여부',
    error: '오류',
  }

  const formatValue = (value: JsonValue): string => {
    if (value === null || value === undefined) return '-'
    if (typeof value === 'boolean') return value ? '✓ 예' : '✗ 아니오'
    if (Array.isArray(value)) {
      if (value.length === 0) return '(없음)'
      if (value.length <= 3) return value.map(v => String(v)).join(', ')
      return `${value.slice(0, 3).map(v => String(v)).join(', ')} 외 ${value.length - 3}개`
    }
    if (typeof value === 'object') return JSON.stringify(value)
    return String(value)
  }

  return (
    <div className="text-xs bg-muted rounded overflow-hidden">
      {/* 뷰 전환 버튼 */}
      <div className="flex justify-end p-1 border-b border-border/50">
        <Button
          variant="ghost"
          size="xs"
          onClick={() => setIsRawView(!isRawView)}
          className="text-[10px]"
        >
          {isRawView ? '📋 정리된 보기' : '{ } JSON 보기'}
        </Button>
      </div>

      {isRawView ? (
        <pre className="p-2 overflow-x-auto max-h-48">
          {JSON.stringify(data, null, 2)}
        </pre>
      ) : (
        <div className="p-2 space-y-1 max-h-48 overflow-y-auto">
          {entries.map(([key, value]) => (
            <div key={key} className="flex gap-2">
              <span className="text-muted-foreground min-w-[80px] flex-shrink-0">
                {keyLabels[key] || key}:
              </span>
              <span className="break-all">{formatValue(value)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ActionLog({
  actions,
  total,
  pendingCount,
  onPageChange,
  currentOffset = 0,
  limit = 50,
}: ActionLogProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const queryClient = useQueryClient()
  const toast = useToast()

  const approveMutation = useMutation({
    mutationFn: (actionId: number) => agentApi.approveAction(actionId),
    onSuccess: () => {
      toast.success('액션이 승인되었습니다')
      queryClient.invalidateQueries({ queryKey: ['agent-actions'] })
      queryClient.invalidateQueries({ queryKey: ['agent-summary'] })
    },
    onError: (error: unknown) => {
      toast.error(`승인 실패: ${getErrorMessage(error)}`)
    },
  })

  const rejectMutation = useMutation({
    mutationFn: (actionId: number) => agentApi.rejectAction(actionId),
    onSuccess: () => {
      toast.success('액션이 거절되었습니다')
      queryClient.invalidateQueries({ queryKey: ['agent-actions'] })
      queryClient.invalidateQueries({ queryKey: ['agent-summary'] })
    },
    onError: (error: unknown) => {
      toast.error(`거절 실패: ${getErrorMessage(error)}`)
    },
  })

  const getActionTypeInfo = (type: string) => {
    return ACTION_TYPE_LABELS[type] || ACTION_TYPE_LABELS.default
  }

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleString('ko-KR', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return dateStr
    }
  }

  const totalPages = Math.ceil(total / limit)
  const currentPage = Math.floor(currentOffset / limit) + 1

  if (actions.length === 0) {
    return (
      <div className="bg-card border border-border rounded-lg p-12 text-center">
        <div className="text-6xl mb-4">🤖</div>
        <h3 className="text-xl font-semibold mb-2">액션 로그가 없습니다</h3>
        <p className="text-muted-foreground">
          AI Agent가 수행한 액션이 이곳에 표시됩니다.
        </p>
      </div>
    )
  }

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      {/* 헤더 */}
      <div className="p-4 border-b border-border flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">액션 로그</h3>
          <p className="text-sm text-muted-foreground">
            총 {total}개 액션 {pendingCount > 0 && `(${pendingCount}개 대기 중)`}
          </p>
        </div>
        {pendingCount > 0 && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 rounded-full text-sm font-medium">
            <span className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse" />
            {pendingCount}개 승인 대기
          </div>
        )}
      </div>

      {/* 액션 목록 */}
      <div className="divide-y divide-border">
        {actions.map((action) => {
          const typeInfo = getActionTypeInfo(action.action_type)
          const statusStyle = STATUS_STYLES[action.status] || STATUS_STYLES.pending
          const isExpanded = expandedId === action.id

          return (
            <div
              key={action.id}
              className={`p-4 hover:bg-muted/50 transition-colors ${
                action.status === 'pending' ? 'bg-yellow-50/50 dark:bg-yellow-900/10' : ''
              }`}
            >
              {/* 메인 행 */}
              <div
                className="flex items-center gap-4 cursor-pointer"
                onClick={() => setExpandedId(isExpanded ? null : action.id)}
              >
                <span className="text-2xl">{typeInfo.icon}</span>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium">{typeInfo.label}</span>
                    {action.target_type && (
                      <span className="text-xs text-muted-foreground">
                        ({action.target_type})
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {formatDate(action.created_at)}
                    {action.tokens_used > 0 && (
                      <span className="ml-2">
                        | {action.tokens_used.toLocaleString()} 토큰
                      </span>
                    )}
                  </div>
                </div>

                {/* 상태 배지 */}
                <div
                  className={`px-2 py-1 rounded-full text-xs font-medium ${statusStyle.bg} ${statusStyle.text}`}
                >
                  {statusStyle.label}
                </div>

                {/* 액션 버튼 (pending 상태일 때만) */}
                {action.status === 'pending' && (
                  <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                    <Button
                      variant="success"
                      size="xs"
                      onClick={() => approveMutation.mutate(action.id)}
                      loading={approveMutation.isPending}
                    >
                      승인
                    </Button>
                    <Button
                      variant="danger"
                      size="xs"
                      onClick={() => rejectMutation.mutate(action.id)}
                      loading={rejectMutation.isPending}
                    >
                      거절
                    </Button>
                  </div>
                )}

                <span className="text-muted-foreground">
                  {isExpanded ? '▲' : '▼'}
                </span>
              </div>

              {/* 펼쳐진 상세 정보 */}
              {isExpanded && (
                <div className="mt-4 pl-12 space-y-3">
                  {action.input_data && (
                    <div>
                      <div className="text-xs font-medium text-muted-foreground mb-1">
                        📥 입력 데이터
                      </div>
                      <DataViewer data={action.input_data} />
                    </div>
                  )}

                  {action.output_data && (
                    <div>
                      <div className="text-xs font-medium text-muted-foreground mb-1">
                        📤 출력 데이터
                      </div>
                      <DataViewer data={action.output_data} />
                    </div>
                  )}

                  {action.error_message && (
                    <div>
                      <div className="text-xs font-medium text-red-500 dark:text-red-400 mb-1">
                        ⚠️ 오류 메시지
                      </div>
                      <div className="text-xs text-red-500 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-2 rounded">
                        {action.error_message}
                      </div>
                    </div>
                  )}

                  <div className="flex gap-4 text-xs text-muted-foreground">
                    {action.approved_at && (
                      <span>승인: {formatDate(action.approved_at)}</span>
                    )}
                    {action.completed_at && (
                      <span>완료: {formatDate(action.completed_at)}</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* 페이지네이션 */}
      {totalPages > 1 && onPageChange && (
        <div className="p-4 border-t border-border flex items-center justify-between">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(Math.max(0, currentOffset - limit))}
            disabled={currentOffset === 0}
          >
            이전
          </Button>

          <span className="text-sm text-muted-foreground">
            {currentPage} / {totalPages} 페이지
          </span>

          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(currentOffset + limit)}
            disabled={currentOffset + limit >= total}
          >
            다음
          </Button>
        </div>
      )}
    </div>
  )
}

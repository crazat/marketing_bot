import { useState, useMemo, useCallback, useRef } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Lead, leadsApi } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import KanbanColumn from './KanbanColumn'

// 키보드 네비게이션을 위한 포커스 상태
interface FocusState {
  columnIndex: number
  leadIndex: number
}

interface KanbanBoardProps {
  leads: Lead[]
  // [Phase 7.1] 전환 기록 모달용 콜백
  onConversionWithLead?: (lead: { id: number; platform: string; title: string; author?: string }) => void
}

// 칸반 컬럼 정의
const KANBAN_COLUMNS = [
  { id: 'pending', title: '대기 중', icon: '⏳', color: 'border-b-yellow-500' },
  { id: 'contacted', title: '연락 완료', icon: '📞', color: 'border-b-blue-500' },
  { id: 'replied', title: '답변 받음', icon: '💬', color: 'border-b-purple-500' },
  { id: 'converted', title: '전환 완료', icon: '✅', color: 'border-b-green-500' },
  { id: 'rejected', title: '거절됨', icon: '❌', color: 'border-b-red-500' },
]

// 상태 매핑 (DB 상태 → 칸반 컬럼)
const STATUS_MAP: Record<string, string> = {
  'New': 'pending',
  'new': 'pending',
  'pending': 'pending',
  'contacted': 'contacted',
  'Contacted': 'contacted',
  'replied': 'replied',
  'Replied': 'replied',
  'converted': 'converted',
  'Converted': 'converted',
  'rejected': 'rejected',
  'Rejected': 'rejected',
  'closed': 'rejected',
  'Closed': 'rejected',
}

export default function KanbanBoard({ leads, onConversionWithLead }: KanbanBoardProps) {
  const [draggedLead, setDraggedLead] = useState<Lead | null>(null)
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null)
  const [focusState, setFocusState] = useState<FocusState | null>(null)
  const boardRef = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()
  const toast = useToast()

  // 상태 라벨 매핑
  const STATUS_LABELS: Record<string, string> = {
    pending: '대기 중',
    contacted: '연락 완료',
    replied: '답변 받음',
    converted: '전환 완료',
    rejected: '거절됨',
  }

  // 리드 상태 업데이트 mutation
  // [Phase 2 최적화] 해당 플랫폼만 무효화하여 불필요한 API 호출 제거
  const updateLeadMutation = useMutation({
    mutationFn: ({ lead_id, status }: { lead_id: number; status: string; title?: string; platform?: string }) =>
      leadsApi.updateLead(lead_id, { status }),
    onSuccess: (_, variables) => {
      const statusLabel = STATUS_LABELS[variables.status] || variables.status
      const titlePreview = variables.title
        ? (variables.title.length > 20 ? variables.title.slice(0, 20) + '...' : variables.title)
        : '리드'
      toast.success(`"${titlePreview}" → ${statusLabel}`)

      // [Phase 2 최적화] 해당 플랫폼만 무효화 (7개 → 1개 API 호출)
      if (variables.platform) {
        const platformKey = `${variables.platform.toLowerCase()}-leads`
        queryClient.invalidateQueries({ queryKey: [platformKey] })
      } else {
        // 플랫폼 정보가 없는 경우에만 전체 무효화 (fallback)
        queryClient.invalidateQueries({ queryKey: ['naver-leads'] })
        queryClient.invalidateQueries({ queryKey: ['youtube-leads'] })
        queryClient.invalidateQueries({ queryKey: ['tiktok-leads'] })
        queryClient.invalidateQueries({ queryKey: ['instagram-leads'] })
        queryClient.invalidateQueries({ queryKey: ['carrot-leads'] })
        queryClient.invalidateQueries({ queryKey: ['influencer-leads'] })
      }
      // 통계는 항상 업데이트
      queryClient.invalidateQueries({ queryKey: ['leads-stats'] })
    },
    onError: (error: any) => {
      toast.error(`상태 업데이트 실패: ${error.message || '알 수 없는 오류'}`)
    },
  })

  // 컬럼별로 리드 분류
  const leadsByColumn = useMemo(() => {
    const grouped: Record<string, Lead[]> = {}

    // 빈 컬럼 초기화
    KANBAN_COLUMNS.forEach(col => {
      grouped[col.id] = []
    })

    // 리드 분류
    leads.forEach(lead => {
      const status = lead.status || 'pending'
      const columnId = STATUS_MAP[status] || 'pending'
      grouped[columnId].push(lead)
    })

    return grouped
  }, [leads])

  // 드래그 시작
  const handleDragStart = (e: React.DragEvent, lead: Lead) => {
    setDraggedLead(lead)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', lead.id.toString())
  }

  // 컬럼에 드래그 오버
  const handleColumnDragOver = (e: React.DragEvent, columnId: string) => {
    e.preventDefault()
    setDragOverColumn(columnId)
  }

  // 드래그 종료
  const handleDragEnd = () => {
    setDraggedLead(null)
    setDragOverColumn(null)
  }

  // 드롭
  const handleDrop = (e: React.DragEvent, newStatus: string) => {
    e.preventDefault()
    setDragOverColumn(null)

    if (!draggedLead) return

    // 같은 컬럼에 드롭하면 무시
    const currentStatus = STATUS_MAP[draggedLead.status || 'pending'] || 'pending'
    if (currentStatus === newStatus) {
      setDraggedLead(null)
      return
    }

    // 상태 업데이트
    updateLeadMutation.mutate({
      lead_id: draggedLead.id,
      status: newStatus,
      title: draggedLead.title,
      platform: draggedLead.platform,  // [Phase 2] 플랫폼 정보 전달
    })

    // [Phase 7.1] 전환 완료 시 전환 기록 모달 표시
    if (newStatus === 'converted' && onConversionWithLead) {
      onConversionWithLead({
        id: draggedLead.id,
        platform: draggedLead.platform,
        title: draggedLead.title,
        author: draggedLead.author,
      })
    }

    setDraggedLead(null)
  }

  // 리드 클릭 (URL 열기)
  const handleLeadClick = (lead: Lead) => {
    if (lead.url) {
      window.open(lead.url, '_blank', 'noopener,noreferrer')
    }
  }

  // 상태 변경 (터치 디바이스용)
  const handleStatusChange = (lead: Lead, newStatus: string) => {
    const currentStatus = STATUS_MAP[lead.status || 'pending'] || 'pending'
    if (currentStatus === newStatus) return

    updateLeadMutation.mutate({
      lead_id: lead.id,
      status: newStatus,
      title: lead.title,
      platform: lead.platform,  // [Phase 2] 플랫폼 정보 전달
    })

    // [Phase 7.1] 전환 완료 시 전환 기록 모달 표시
    if (newStatus === 'converted' && onConversionWithLead) {
      onConversionWithLead({
        id: lead.id,
        platform: lead.platform,
        title: lead.title,
        author: lead.author,
      })
    }
  }

  // [Phase 4-1] 키보드 네비게이션
  const handleKeyboardNavigation = useCallback((e: React.KeyboardEvent) => {
    if (!focusState) {
      // 첫 포커스 시 첫 번째 컬럼의 첫 번째 리드로 이동
      if (['ArrowDown', 'ArrowRight', 'Enter', ' '].includes(e.key)) {
        e.preventDefault()
        setFocusState({ columnIndex: 0, leadIndex: 0 })
      }
      return
    }

    const { columnIndex, leadIndex } = focusState
    const currentColumnLeads = leadsByColumn[KANBAN_COLUMNS[columnIndex].id] || []

    switch (e.key) {
      case 'ArrowRight': {
        // 다음 컬럼으로 이동
        e.preventDefault()
        const nextColumnIndex = (columnIndex + 1) % KANBAN_COLUMNS.length
        const nextColumnLeads = leadsByColumn[KANBAN_COLUMNS[nextColumnIndex].id] || []
        setFocusState({
          columnIndex: nextColumnIndex,
          leadIndex: Math.min(leadIndex, Math.max(0, nextColumnLeads.length - 1)),
        })
        break
      }
      case 'ArrowLeft': {
        // 이전 컬럼으로 이동
        e.preventDefault()
        const prevColumnIndex = (columnIndex - 1 + KANBAN_COLUMNS.length) % KANBAN_COLUMNS.length
        const prevColumnLeads = leadsByColumn[KANBAN_COLUMNS[prevColumnIndex].id] || []
        setFocusState({
          columnIndex: prevColumnIndex,
          leadIndex: Math.min(leadIndex, Math.max(0, prevColumnLeads.length - 1)),
        })
        break
      }
      case 'ArrowDown':
        // 다음 리드로 이동
        e.preventDefault()
        if (leadIndex < currentColumnLeads.length - 1) {
          setFocusState({ columnIndex, leadIndex: leadIndex + 1 })
        }
        break
      case 'ArrowUp':
        // 이전 리드로 이동
        e.preventDefault()
        if (leadIndex > 0) {
          setFocusState({ columnIndex, leadIndex: leadIndex - 1 })
        }
        break
      case 'Enter': {
        // 리드 상세 보기 (URL 열기)
        e.preventDefault()
        const lead = currentColumnLeads[leadIndex]
        if (lead?.url) {
          window.open(lead.url, '_blank', 'noopener,noreferrer')
        }
        break
      }
      case ' ': {
        // 리드를 다음 상태로 이동 (Space)
        e.preventDefault()
        const lead = currentColumnLeads[leadIndex]
        if (lead) {
          const nextColumnIndex = (columnIndex + 1) % KANBAN_COLUMNS.length
          const newStatus = KANBAN_COLUMNS[nextColumnIndex].id
          handleStatusChange(lead, newStatus)
        }
        break
      }
      case 'Escape':
        // 포커스 해제
        setFocusState(null)
        boardRef.current?.blur()
        break
      case 'Home':
        // 첫 번째 리드로 이동
        e.preventDefault()
        setFocusState({ columnIndex, leadIndex: 0 })
        break
      case 'End':
        // 마지막 리드로 이동
        e.preventDefault()
        setFocusState({ columnIndex, leadIndex: Math.max(0, currentColumnLeads.length - 1) })
        break
    }
  }, [focusState, leadsByColumn, handleStatusChange])

  // 리드 포커스 설정
  const handleLeadFocus = useCallback((columnIndex: number, leadIndex: number) => {
    setFocusState({ columnIndex, leadIndex })
  }, [])

  return (
    <div
      ref={boardRef}
      className="space-y-4"
      onDragEnd={handleDragEnd}
      onKeyDown={handleKeyboardNavigation}
      tabIndex={0}
      role="application"
      aria-label="리드 칸반 보드. 화살표 키로 탐색, Enter로 상세 보기, Space로 다음 상태로 이동"
      aria-roledescription="칸반 보드"
    >
      {/* 안내 */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          <span className="hidden md:inline">💡 카드를 드래그하거나 키보드(←→↑↓)로 탐색하세요</span>
          <span className="md:hidden">💡 카드의 "이동" 버튼으로 상태를 변경하세요</span>
        </p>
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span>총 {leads.length}개 리드</span>
          {updateLeadMutation.isPending && (
            <span className="flex items-center gap-1 text-primary">
              <span className="animate-spin">⚙️</span>
              업데이트 중...
            </span>
          )}
        </div>
      </div>

      {/* 칸반 보드 - 모바일 가로 스크롤 */}
      <div className="relative">
        {/* 모바일 스크롤 힌트 */}
        <div className="md:hidden absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-background to-transparent pointer-events-none z-10" />

        <div className="flex gap-4 overflow-x-auto pb-4 md:grid md:grid-cols-2 lg:grid-cols-5 md:overflow-visible scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent">
          {KANBAN_COLUMNS.map((column, colIndex) => (
            <div key={column.id} className="flex-shrink-0 w-72 md:w-auto">
              <KanbanColumn
                id={column.id}
                title={column.title}
                icon={column.icon}
                color={column.color}
                leads={leadsByColumn[column.id] || []}
                onDragStart={handleDragStart}
                onDragOver={(e) => handleColumnDragOver(e, column.id)}
                onDrop={handleDrop}
                onLeadClick={handleLeadClick}
                onStatusChange={handleStatusChange}
                isDragOver={dragOverColumn === column.id}
                focusedLeadIndex={focusState?.columnIndex === colIndex ? focusState.leadIndex : -1}
                onLeadFocus={(leadIndex) => handleLeadFocus(colIndex, leadIndex)}
              />
            </div>
          ))}
        </div>
      </div>

      {/* 모바일 스크롤 안내 */}
      <p className="md:hidden text-xs text-muted-foreground text-center">
        👆 좌우로 스와이프하여 다른 컬럼을 확인하세요
      </p>

      {/* 상태 설명 */}
      <div className="bg-muted/50 rounded-lg p-4">
        <h4 className="font-semibold mb-2">📋 상태 설명</h4>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-sm">
          <div className="flex items-center gap-2">
            <span>⏳</span>
            <span><strong>대기 중</strong>: 신규 발견</span>
          </div>
          <div className="flex items-center gap-2">
            <span>📞</span>
            <span><strong>연락 완료</strong>: 첫 연락</span>
          </div>
          <div className="flex items-center gap-2">
            <span>💬</span>
            <span><strong>답변 받음</strong>: 응답 수신</span>
          </div>
          <div className="flex items-center gap-2">
            <span>✅</span>
            <span><strong>전환 완료</strong>: 목표 달성</span>
          </div>
          <div className="flex items-center gap-2">
            <span>❌</span>
            <span><strong>거절됨</strong>: 진행 불가</span>
          </div>
        </div>
      </div>
    </div>
  )
}

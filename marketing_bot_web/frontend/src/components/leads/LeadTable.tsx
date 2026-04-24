import { useState, Fragment, memo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { leadsApi } from '@/services/api'
import EmptyState from '@/components/ui/EmptyState'
import Pagination from '@/components/ui/Pagination'
import SentimentBadge from '@/components/ui/SentimentBadge'
import LeadNoteEditor from '@/components/leads/LeadNoteEditor'
import QAMatchPanel from '@/components/leads/QAMatchPanel'
import LeadAttribution from '@/components/leads/LeadAttribution'
import LeadPipelineStepper from '@/components/leads/LeadPipelineStepper'
import { safeUrl } from '@/utils/safeUrl'
import { ConfirmModal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { ResultsAnnouncer } from '@/components/ui/LiveRegion'
import { exportToCSV, LEAD_EXPORT_COLUMNS } from '@/utils/export'
import Button, { IconButton } from '@/components/ui/Button'
import { Download, Phone, MessageCircle, CheckCircle, XCircle, Shield, Contact, Ban, Copy } from 'lucide-react'

type LeadPlatform = 'youtube' | 'tiktok' | 'naver' | 'instagram' | 'carrot' | 'influencer'
type LeadStatus = 'pending' | 'contacted' | 'replied' | 'converted' | 'rejected'

interface LeadData {
  id: number
  platform: LeadPlatform
  title: string
  url?: string
  category?: string
  status: LeadStatus
  created_at?: string
  content_preview?: string
  summary?: string
  matched_keywords?: string[]
  notes?: string
  follow_up_date?: string | null
  contact_info?: string
  // [Phase 1.3] 리드 스코어링
  score?: number
  grade?: 'hot' | 'warm' | 'cool' | 'cold'
  score_breakdown?: {
    source?: number
    relevance?: number
    freshness?: number
    engagement?: number
  }
  // [Phase 6.0] 감성 분석
  sentiment?: 'positive' | 'negative' | 'neutral'
  // [Phase 4.0] ROI 분석 필드
  expected_revenue?: number
  actual_revenue?: number
  source_keyword?: string
  source_content?: string
  stage_timestamps?: string
  // [Phase 4.0] 신뢰도 점수
  trust_score?: number
  trust_level?: 'trusted' | 'review' | 'suspicious'
  trust_reasons?: string[]
  // [Phase 4.0] 연락처 추출
  extracted_contacts?: {
    phone: string[]
    email: string[]
    kakao: string[]
    instagram: string[]
    has_contact: boolean
    summary: string
  }
}

// [Phase 1.3] 등급별 스타일
const gradeStyles: Record<string, { bg: string; text: string; emoji: string; label: string }> = {
  hot: { bg: 'bg-red-500/20', text: 'text-red-400', emoji: '🔴', label: 'Hot' },
  warm: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', emoji: '🟡', label: 'Warm' },
  cool: { bg: 'bg-green-500/20', text: 'text-green-400', emoji: '🟢', label: 'Cool' },
  cold: { bg: 'bg-gray-500/20', text: 'text-gray-400', emoji: '⚪', label: 'Cold' },
}


// [Phase 7.1] 전환 모달용 최소 리드 정보
interface ConversionLeadInfo {
  id: number
  platform: string
  title: string
  author?: string
}

type ViewMode = 'table' | 'card'

interface LeadTableProps {
  leads: LeadData[]
  onUpdateStatus: (lead_id: number, status: LeadStatus, notes?: string) => void
  onBulkUpdateStatus?: (lead_ids: number[], status: LeadStatus) => void
  // [Phase 7.1] 전환 기록 모달용 - 필수 리드 정보만 전달
  onConversionWithLead?: (lead: ConversionLeadInfo) => void
  initialPageSize?: number
  showExport?: boolean
  viewMode?: ViewMode // 모바일 카드 뷰 지원
}

const platformIcons: Record<string, string> = {
  youtube: '📺',
  tiktok: '🎵',
  naver: '🟢',
  instagram: '📸',
  carrot: '🥕',
  influencer: '⭐'
}

const statusColors: Record<LeadStatus, string> = {
  pending: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/30',
  contacted: 'bg-blue-500/10 text-blue-500 border-blue-500/30',
  replied: 'bg-purple-500/10 text-purple-500 border-purple-500/30',
  converted: 'bg-green-500/10 text-green-500 border-green-500/30',
  rejected: 'bg-red-500/10 text-red-500 border-red-500/30'
}

// [성능 최적화] React.memo로 불필요한 리렌더링 방지
function LeadTableComponent({ leads, onUpdateStatus, onBulkUpdateStatus, onConversionWithLead, initialPageSize = 25, showExport = true, viewMode = 'table' }: LeadTableProps) {
  const [expandedLead, setExpandedLead] = useState<number | null>(null)
  // [Phase 6.0] 일괄 선택 상태
  const [selectedLeads, setSelectedLeads] = useState<Set<number>>(new Set())
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(initialPageSize)
  // [Phase 4.0] 템플릿 표시 상태
  const [showTemplates, setShowTemplates] = useState<number | null>(null)
  // [Phase 6.1] 컨택 히스토리 표시 상태
  const [showContactHistory, setShowContactHistory] = useState<number | null>(null)
  const [newContactContent, setNewContactContent] = useState('')
  const [newContactType, setNewContactType] = useState<'comment' | 'dm' | 'email' | 'call'>('comment')
  const queryClient = useQueryClient()
  // [Phase 5.0] 일괄 처리 확인 모달
  const [bulkConfirmModal, setBulkConfirmModal] = useState<{
    isOpen: boolean
    status: LeadStatus | null
    count: number
  }>({ isOpen: false, status: null, count: 0 })
  const toast = useToast()

  // [Phase 4.0] 현재 확장된 리드의 플랫폼으로 템플릿 조회
  const expandedLeadData = leads.find(l => l.id === expandedLead)
  const { data: templateData } = useQuery({
    queryKey: ['response-templates', expandedLeadData?.platform, expandedLead],
    queryFn: () => leadsApi.suggestResponse(
      expandedLeadData?.platform || 'naver',
      'first_contact',
      expandedLead || undefined
    ),
    enabled: !!expandedLead && showTemplates === expandedLead,
  })

  // [Phase 6.1] 컨택 히스토리 조회
  const { data: contactHistoryData, isLoading: contactHistoryLoading } = useQuery({
    queryKey: ['contact-history', showContactHistory],
    queryFn: () => leadsApi.getContactHistory(showContactHistory!),
    enabled: !!showContactHistory,
  })

  // [Phase 6.1] 컨택 추가 mutation
  const addContactMutation = useMutation({
    mutationFn: (data: { lead_id: number; contact_type?: 'comment' | 'dm' | 'email' | 'call'; content: string; platform?: string }) =>
      leadsApi.addContactHistory(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contact-history', showContactHistory] })
      setNewContactContent('')
      toast.success('컨택 기록이 추가되었습니다')
    },
    onError: () => {
      toast.error('컨택 기록 추가 실패')
    },
  })

  // [Phase 6.1] 응답 업데이트 mutation
  const updateResponseMutation = useMutation({
    mutationFn: ({ historyId, response, status }: { historyId: number; response: string; status?: string }) =>
      leadsApi.updateContactResponse(historyId, response, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contact-history', showContactHistory] })
      toast.success('응답이 기록되었습니다')
    },
  })

  const handleExport = () => {
    const timestamp = new Date().toISOString().slice(0, 10)
    exportToCSV(leads, LEAD_EXPORT_COLUMNS, `leads_${timestamp}.csv`)
    toast.success(`${leads.length}개 리드를 CSV로 내보냈습니다`)
  }

  if (!leads || leads.length === 0) {
    return (
      <EmptyState
        icon="📋"
        title="리드가 없습니다"
        description="바이럴 스캔을 실행하여 새로운 리드를 발굴하세요."
      />
    )
  }

  // 페이지네이션 계산
  const totalPages = Math.ceil(leads.length / pageSize)
  const startIndex = (currentPage - 1) * pageSize
  const endIndex = startIndex + pageSize
  const paginatedLeads = leads.slice(startIndex, endIndex)

  const handlePageSizeChange = (size: number) => {
    setPageSize(size)
    setCurrentPage(1)
    setExpandedLead(null) // 확장된 리드 닫기
  }

  const handlePageChange = (page: number) => {
    setCurrentPage(page)
    setExpandedLead(null) // 페이지 변경 시 확장된 리드 닫기
  }

  // [Phase 6.0] 일괄 선택 핸들러
  const handleSelectAll = () => {
    if (selectedLeads.size === paginatedLeads.length) {
      setSelectedLeads(new Set())
    } else {
      setSelectedLeads(new Set(paginatedLeads.map((l) => l.id)))
    }
  }

  const handleSelectLead = (leadId: number, e: React.MouseEvent) => {
    e.stopPropagation()
    const newSelected = new Set(selectedLeads)
    if (newSelected.has(leadId)) {
      newSelected.delete(leadId)
    } else {
      newSelected.add(leadId)
    }
    setSelectedLeads(newSelected)
  }

  // [Phase 5.0] 일괄 상태 변경 요청 (확인 모달 표시)
  const handleBulkAction = (status: LeadStatus) => {
    if (selectedLeads.size > 0) {
      setBulkConfirmModal({
        isOpen: true,
        status,
        count: selectedLeads.size
      })
    }
  }

  // [Phase 5.0] 일괄 상태 변경 확정
  const confirmBulkAction = () => {
    if (onBulkUpdateStatus && bulkConfirmModal.status && selectedLeads.size > 0) {
      onBulkUpdateStatus(Array.from(selectedLeads), bulkConfirmModal.status)
      setSelectedLeads(new Set())
      toast.success(`${bulkConfirmModal.count}개 리드 상태가 변경되었습니다`)
    }
    setBulkConfirmModal({ isOpen: false, status: null, count: 0 })
  }

  // [Phase 5.0] 신뢰도 낮은(의심) 리드 선택
  const handleSelectSuspicious = () => {
    const suspiciousLeads = paginatedLeads.filter(l => l.trust_level === 'suspicious')
    setSelectedLeads(new Set(suspiciousLeads.map(l => l.id)))
    if (suspiciousLeads.length > 0) {
      toast.info(`의심 리드 ${suspiciousLeads.length}개를 선택했습니다`)
    } else {
      toast.info('의심 리드가 없습니다')
    }
  }

  // [Phase 5.0] 연락처 있는 리드 선택
  const handleSelectWithContacts = () => {
    const leadsWithContacts = paginatedLeads.filter(l => l.extracted_contacts?.has_contact)
    setSelectedLeads(new Set(leadsWithContacts.map(l => l.id)))
    if (leadsWithContacts.length > 0) {
      toast.info(`연락처 보유 리드 ${leadsWithContacts.length}개를 선택했습니다`)
    } else {
      toast.info('연락처 보유 리드가 없습니다')
    }
  }

  // [Phase 5.0] 신뢰 리드만 선택
  const handleSelectTrusted = () => {
    const trustedLeads = paginatedLeads.filter(l => l.trust_level === 'trusted')
    setSelectedLeads(new Set(trustedLeads.map(l => l.id)))
    if (trustedLeads.length > 0) {
      toast.info(`신뢰 리드 ${trustedLeads.length}개를 선택했습니다`)
    } else {
      toast.info('신뢰 리드가 없습니다')
    }
  }

  // [Phase 5.0] 상태 라벨 맵
  const statusLabels: Record<LeadStatus, string> = {
    pending: '대기 중',
    contacted: '연락 완료',
    replied: '답변 받음',
    converted: '전환 완료',
    rejected: '거절됨'
  }

  return (
    <div className="space-y-4">
      {/* 스크린 리더용 결과 알림 */}
      <ResultsAnnouncer
        count={leads.length}
        itemName="리드"
      />

      {/* [Phase 5.0] 일괄 처리 확인 모달 */}
      <ConfirmModal
        isOpen={bulkConfirmModal.isOpen}
        onClose={() => setBulkConfirmModal({ isOpen: false, status: null, count: 0 })}
        onConfirm={confirmBulkAction}
        title="일괄 상태 변경"
        message={`선택된 ${bulkConfirmModal.count}개 리드를 "${bulkConfirmModal.status ? statusLabels[bulkConfirmModal.status] : ''}" 상태로 변경하시겠습니까?`}
        confirmText="변경"
        cancelText="취소"
        variant={bulkConfirmModal.status === 'rejected' ? 'danger' : 'default'}
      />

      {/* [Phase 5.0] 스마트 선택 버튼들 */}
      {onBulkUpdateStatus && (
        <div className="flex flex-wrap items-center gap-2 p-3 bg-muted/50 border border-border rounded-lg">
          <span className="text-sm text-muted-foreground mr-2">빠른 선택:</span>
          <Button
            variant="outline"
            size="xs"
            onClick={handleSelectTrusted}
            icon={<Shield className="w-3 h-3" />}
            title="신뢰도 높은 리드만 선택"
            className="border-blue-500/30 text-blue-600 hover:bg-blue-500/20"
          >
            신뢰 리드
          </Button>
          <Button
            variant="outline"
            size="xs"
            onClick={handleSelectWithContacts}
            icon={<Contact className="w-3 h-3" />}
            title="연락처가 추출된 리드만 선택"
            className="border-purple-500/30 text-purple-600 hover:bg-purple-500/20"
          >
            연락처 있음
          </Button>
          <Button
            variant="outline"
            size="xs"
            onClick={handleSelectSuspicious}
            icon={<Ban className="w-3 h-3" />}
            title="신뢰도 낮은 리드만 선택 (일괄 거절용)"
            className="border-red-500/30 text-red-600 hover:bg-red-500/20"
          >
            의심 리드
          </Button>
          {selectedLeads.size > 0 && (
            <span className="ml-auto text-sm font-medium text-primary">
              {selectedLeads.size}개 선택됨
            </span>
          )}
        </div>
      )}

      {/* [Phase 6.0] 일괄 액션 바 */}
      {selectedLeads.size > 0 && onBulkUpdateStatus && (
        <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-primary/10 border border-primary/30 rounded-lg">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">
              {selectedLeads.size}개 선택됨
            </span>
            <span className="text-xs text-muted-foreground">
              | 상태 일괄 변경:
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              size="xs"
              onClick={() => handleBulkAction('contacted')}
              icon={<Phone className="w-3 h-3" />}
              className="bg-blue-500 hover:bg-blue-600"
            >
              연락함
            </Button>
            <Button
              size="xs"
              onClick={() => handleBulkAction('replied')}
              icon={<MessageCircle className="w-3 h-3" />}
              className="bg-purple-500 hover:bg-purple-600"
            >
              답변받음
            </Button>
            <Button
              variant="success"
              size="xs"
              onClick={() => handleBulkAction('converted')}
              icon={<CheckCircle className="w-3 h-3" />}
            >
              전환
            </Button>
            <Button
              variant="danger"
              size="xs"
              onClick={() => handleBulkAction('rejected')}
              icon={<XCircle className="w-3 h-3" />}
            >
              거절
            </Button>
            <div className="border-l border-border pl-2">
              <Button
                variant="ghost"
                size="xs"
                onClick={() => setSelectedLeads(new Set())}
              >
                선택 해제
              </Button>
            </div>
          </div>
        </div>
      )}

      {showExport && leads.length > 0 && (
        <div className="flex justify-end">
          <Button
            variant="outline"
            size="sm"
            onClick={handleExport}
            icon={<Download className="w-4 h-4" />}
          >
            CSV 내보내기 ({leads.length}개)
          </Button>
        </div>
      )}

    {/* 카드 뷰 (모바일 친화적) */}
    {viewMode === 'card' ? (
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {paginatedLeads.map((lead) => (
          <div
            key={lead.id}
            className={`
              bg-card border border-border rounded-lg p-4 space-y-3
              cursor-pointer transition-all hover:shadow-md hover:border-primary/50
              ${selectedLeads.has(lead.id) ? 'ring-2 ring-primary' : ''}
            `}
            onClick={() => setExpandedLead(expandedLead === lead.id ? null : lead.id)}
          >
            {/* 헤더 */}
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                {onBulkUpdateStatus && (
                  <input
                    type="checkbox"
                    checked={selectedLeads.has(lead.id)}
                    onClick={(e) => handleSelectLead(lead.id, e as unknown as React.MouseEvent)}
                    className="w-4 h-4 rounded border-border"
                  />
                )}
                <span className="text-lg">{platformIcons[lead.platform] || '📄'}</span>
                <span className={`px-2 py-0.5 text-xs rounded-full border ${statusColors[lead.status]}`}>
                  {statusLabels[lead.status]}
                </span>
              </div>
              {lead.grade && (
                <span className={`px-2 py-0.5 text-xs rounded-full ${gradeStyles[lead.grade].bg} ${gradeStyles[lead.grade].text}`}>
                  {gradeStyles[lead.grade].emoji} {lead.score}점
                </span>
              )}
            </div>

            {/* 제목 */}
            <h3 className="font-medium text-sm line-clamp-2">{lead.title}</h3>

            {/* 메타 정보 */}
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              {lead.category && (
                <span className="px-2 py-0.5 bg-muted rounded">{lead.category}</span>
              )}
              {lead.created_at && (
                <span>{new Date(lead.created_at).toLocaleDateString('ko-KR')}</span>
              )}
              {lead.sentiment && <SentimentBadge sentiment={lead.sentiment} size="sm" />}
            </div>

            {/* 액션 버튼 (확장 시) */}
            {expandedLead === lead.id && (
              <div className="pt-3 border-t border-border space-y-3">
                {lead.content_preview && (
                  <p className="text-xs text-muted-foreground line-clamp-3">{lead.content_preview}</p>
                )}
                <div className="flex flex-wrap gap-2">
                  {lead.status !== 'contacted' && (
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={(e) => { e.stopPropagation(); onUpdateStatus(lead.id, 'contacted'); }}
                      className="px-2 py-1 bg-blue-500/10 text-blue-600 hover:bg-blue-500/20"
                    >
                      📞 연락함
                    </Button>
                  )}
                  {lead.status !== 'converted' && (
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={(e) => { e.stopPropagation(); onUpdateStatus(lead.id, 'converted'); }}
                      className="px-2 py-1 bg-green-500/10 text-green-600 hover:bg-green-500/20"
                    >
                      ✅ 전환
                    </Button>
                  )}
                  {lead.url && (
                    <a
                      href={safeUrl(lead.url)}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="px-2 py-1 text-xs bg-muted rounded hover:bg-accent"
                    >
                      🔗 원본
                    </a>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    ) : (
    /* 테이블 뷰 (데스크톱) */
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border">
            {onBulkUpdateStatus && (
              <th className="px-4 py-3 text-left">
                <input
                  type="checkbox"
                  checked={selectedLeads.size === paginatedLeads.length && paginatedLeads.length > 0}
                  onChange={handleSelectAll}
                  className="w-4 h-4 rounded border-border"
                  aria-label="전체 선택"
                />
              </th>
            )}
            <th className="px-4 py-3 text-left text-sm font-semibold">플랫폼</th>
            <th className="px-4 py-3 text-left text-sm font-semibold">점수</th>
            {/* 감성 컬럼 제거 — 점수(grade)에 이미 반영됨, 상세는 확장 행에서 표시 */}
            <th className="px-4 py-3 text-left text-sm font-semibold">신뢰도</th>
            <th className="px-4 py-3 text-left text-sm font-semibold">제목</th>
            <th className="px-4 py-3 text-left text-sm font-semibold">카테고리</th>
            <th className="px-4 py-3 text-left text-sm font-semibold">상태</th>
            {/* 발견일은 xl 이상에서만 표시 — 중소 화면에선 확장 행에서 확인 */}
            <th className="hidden xl:table-cell px-4 py-3 text-left text-sm font-semibold">발견일</th>
            <th className="px-4 py-3 text-left text-sm font-semibold">노트</th>
            <th className="px-4 py-3 text-left text-sm font-semibold">액션</th>
          </tr>
        </thead>
        <tbody>
          {paginatedLeads.map((lead) => (
            <Fragment key={lead.id}>
              <tr
                className={`
                  border-b border-border cursor-pointer
                  transition-all duration-200 ease-out
                  hover:bg-accent/50 hover:shadow-sm
                  hover:border-l-2 hover:border-l-primary
                  ${selectedLeads.has(lead.id) ? 'bg-primary/5 border-l-2 border-l-primary' : ''}
                `}
                onClick={() => setExpandedLead(expandedLead === lead.id ? null : lead.id)}
              >
                {onBulkUpdateStatus && (
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selectedLeads.has(lead.id)}
                      onChange={() => {}}
                      onClick={(e) => handleSelectLead(lead.id, e)}
                      className="w-4 h-4 rounded border-border"
                      aria-label={`${lead.title} 선택`}
                    />
                  </td>
                )}
                <td className="px-4 py-3">
                  <span className="text-2xl">{platformIcons[lead.platform]}</span>
                </td>
                {/* [Phase 1.3] 점수 표시 */}
                <td className="px-4 py-3">
                  {lead.score !== undefined ? (
                    <div className="flex flex-col items-center gap-1">
                      <span className={`text-xs px-2 py-1 rounded-full font-bold ${gradeStyles[lead.grade || 'cold'].bg} ${gradeStyles[lead.grade || 'cold'].text}`}>
                        {gradeStyles[lead.grade || 'cold'].emoji} {lead.score}
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        {gradeStyles[lead.grade || 'cold'].label}
                      </span>
                    </div>
                  ) : (
                    <span className="text-xs text-muted-foreground">-</span>
                  )}
                </td>
                {/* [Phase 4.0] 신뢰도 배지 */}
                <td className="px-4 py-3">
                  {lead.trust_level ? (
                    <div className="flex flex-col items-center gap-1">
                      <span
                        className={`text-xs px-2 py-1 rounded-full font-medium ${
                          lead.trust_level === 'trusted'
                            ? 'bg-blue-500/20 text-blue-400'
                            : lead.trust_level === 'review'
                            ? 'bg-amber-500/20 text-amber-400'
                            : 'bg-red-500/20 text-red-400'
                        }`}
                        title={lead.trust_reasons?.join(', ') || '신뢰도 평가'}
                      >
                        {lead.trust_level === 'trusted' ? '🟢' : lead.trust_level === 'review' ? '🟡' : '🔴'} {lead.trust_score}
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        {lead.trust_level === 'trusted' ? '신뢰' : lead.trust_level === 'review' ? '확인' : '의심'}
                      </span>
                    </div>
                  ) : (
                    <span className="text-xs text-muted-foreground">-</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="max-w-md">
                    <div className="font-medium truncate">{lead.title}</div>
                    {lead.url && (
                      <a
                        href={safeUrl(lead.url)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-500 hover:underline"
                        onClick={(e) => e.stopPropagation()}
                      >
                        링크 열기 ↗
                      </a>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className="text-xs px-2 py-1 rounded-full bg-muted">
                    {lead.category || '-'}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-1 rounded-full border ${statusColors[lead.status]}`}>
                    {lead.status}
                  </span>
                </td>
                <td className="hidden xl:table-cell px-4 py-3 text-sm text-muted-foreground">
                  {lead.created_at ? new Date(lead.created_at).toLocaleDateString() : '-'}
                </td>
                <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                  <LeadNoteEditor
                    leadId={lead.id}
                    currentStatus={lead.status}
                    notes={lead.notes || ''}
                    followUpDate={lead.follow_up_date}
                    contactInfo={lead.contact_info || ''}
                    expectedRevenue={lead.expected_revenue}
                    actualRevenue={lead.actual_revenue}
                    sourceKeyword={lead.source_keyword}
                    sourceContent={lead.source_content}
                  />
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                    <IconButton
                      icon={<Phone className="w-4 h-4" />}
                      onClick={() => onUpdateStatus(lead.id, 'contacted')}
                      size="sm"
                      className="text-blue-500 bg-blue-500/10 hover:bg-blue-500/20"
                      title="연락함으로 표시"
                      aria-label="연락함으로 표시"
                    />
                    <IconButton
                      icon={<CheckCircle className="w-4 h-4" />}
                      onClick={() => {
                        onUpdateStatus(lead.id, 'converted')
                        // [Phase 7.1] 전환 기록 모달 표시
                        if (onConversionWithLead) {
                          onConversionWithLead({
                            id: lead.id,
                            platform: lead.platform,
                            title: lead.title,
                            author: undefined, // LeadData에 author 필드 없음
                          })
                        }
                      }}
                      size="sm"
                      className="text-green-500 bg-green-500/10 hover:bg-green-500/20"
                      title="전환완료로 표시"
                      aria-label="전환완료로 표시"
                    />
                    <IconButton
                      icon={<XCircle className="w-4 h-4" />}
                      onClick={() => onUpdateStatus(lead.id, 'rejected')}
                      size="sm"
                      className="text-red-500 bg-red-500/10 hover:bg-red-500/20"
                      title="거절됨으로 표시"
                      aria-label="거절됨으로 표시"
                    />
                  </div>
                </td>
              </tr>
              {expandedLead === lead.id && (
                <tr className="bg-muted/30">
                  <td colSpan={onBulkUpdateStatus ? 10 : 9} className="px-4 py-4">
                    <div className="space-y-3">
                      {/* [Y2] 파이프라인 스테퍼 */}
                      <div className="bg-card border border-border p-3">
                        <div className="caps text-muted-foreground mb-2">진행 단계</div>
                        <LeadPipelineStepper status={lead.status} />
                      </div>
                      {/* [Phase 1.3] 점수 분석 */}
                      {lead.score_breakdown && (
                        <div>
                          <div className="text-sm font-semibold mb-2">점수 분석</div>
                          <div className="grid grid-cols-4 gap-2">
                            <div className="bg-card p-2 rounded border border-border">
                              <div className="text-[10px] text-muted-foreground">소스 신뢰도</div>
                              <div className="text-lg font-bold">{lead.score_breakdown.source || 0}<span className="text-xs text-muted-foreground">/30</span></div>
                            </div>
                            <div className="bg-card p-2 rounded border border-border">
                              <div className="text-[10px] text-muted-foreground">콘텐츠 관련성</div>
                              <div className="text-lg font-bold">{lead.score_breakdown.relevance || 0}<span className="text-xs text-muted-foreground">/30</span></div>
                            </div>
                            <div className="bg-card p-2 rounded border border-border">
                              <div className="text-[10px] text-muted-foreground">시간 신선도</div>
                              <div className="text-lg font-bold">{lead.score_breakdown.freshness || 0}<span className="text-xs text-muted-foreground">/20</span></div>
                            </div>
                            <div className="bg-card p-2 rounded border border-border">
                              <div className="text-[10px] text-muted-foreground">참여도</div>
                              <div className="text-lg font-bold">{lead.score_breakdown.engagement || 0}<span className="text-xs text-muted-foreground">/20</span></div>
                            </div>
                          </div>
                        </div>
                      )}
                      <div>
                        <div className="text-sm font-semibold mb-1">콘텐츠 미리보기</div>
                        <p className="text-sm text-muted-foreground">
                          {lead.content_preview || lead.summary || '내용 없음'}
                        </p>
                      </div>
                      {lead.matched_keywords && lead.matched_keywords.length > 0 && (
                        <div>
                          <div className="text-sm font-semibold mb-1">매칭 키워드</div>
                          <div className="flex flex-wrap gap-1">
                            {lead.matched_keywords.map((kw: string, i: number) => (
                              <span
                                key={i}
                                className="text-xs px-2 py-1 rounded-md bg-primary/10 text-primary"
                              >
                                {kw}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* [Phase F-2] 리드 소스 어트리뷰션 */}
                      {lead.source_keyword && (
                        <div className="pt-3 border-t border-border">
                          <LeadAttribution
                            sourceKeyword={lead.source_keyword}
                            platform={lead.platform}
                          />
                        </div>
                      )}

                      {lead.notes && (
                        <div>
                          <div className="text-sm font-semibold mb-1">메모</div>
                          <p className="text-sm text-muted-foreground">{lead.notes}</p>
                        </div>
                      )}
                      {/* [Phase 4.0] 추출된 연락처 */}
                      {lead.extracted_contacts?.has_contact && (
                        <div>
                          <div className="text-sm font-semibold mb-2 flex items-center gap-2">
                            📞 추출된 연락처
                            <span className="text-xs text-muted-foreground font-normal">
                              ({lead.extracted_contacts.summary})
                            </span>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {(lead.extracted_contacts.phone ?? []).map((phone, i) => (
                              <span key={`phone-${i}`} className="text-xs px-2 py-1 rounded-full bg-blue-500/10 text-blue-500">
                                📱 {phone}
                              </span>
                            ))}
                            {(lead.extracted_contacts.email ?? []).map((email, i) => (
                              <span key={`email-${i}`} className="text-xs px-2 py-1 rounded-full bg-green-500/10 text-green-500">
                                ✉️ {email}
                              </span>
                            ))}
                            {(lead.extracted_contacts.kakao ?? []).map((kakao, i) => (
                              <span key={`kakao-${i}`} className="text-xs px-2 py-1 rounded-full bg-yellow-500/10 text-yellow-500">
                                💬 {kakao}
                              </span>
                            ))}
                            {(lead.extracted_contacts.instagram ?? []).map((insta, i) => (
                              <span key={`insta-${i}`} className="text-xs px-2 py-1 rounded-full bg-pink-500/10 text-pink-500">
                                📷 @{insta}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* [Phase D-1] Q&A 자동 매칭 */}
                      <div className="pt-3 border-t border-border">
                        <QAMatchPanel
                          leadText={lead.content_preview || lead.title || ''}
                          platform={lead.platform}
                          onSelectResponse={() => {
                            toast.success('응답을 복사했습니다. 컨택 기록에 붙여넣기하세요.')
                          }}
                        />
                      </div>

                      {/* [Phase 4.0] 응답 템플릿 */}
                      <div className="pt-3 border-t border-border">
                        {showTemplates !== lead.id ? (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation()
                              setShowTemplates(lead.id)
                            }}
                            icon={<MessageCircle className="w-4 h-4" />}
                          >
                            응답 템플릿 보기
                          </Button>
                        ) : (
                          <div className="space-y-3">
                            <div className="flex items-center justify-between">
                              <div className="text-sm font-semibold">응답 템플릿</div>
                              <Button
                                variant="ghost"
                                size="xs"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  setShowTemplates(null)
                                }}
                              >
                                닫기
                              </Button>
                            </div>
                            {templateData?.templates?.length > 0 ? (
                              <div className="space-y-2">
                                {templateData.templates.map((tpl: any, idx: number) => (
                                  <div
                                    key={tpl.id || idx}
                                    className="bg-card border border-border rounded-lg p-3"
                                  >
                                    <div className="flex items-center justify-between mb-2">
                                      <span className="text-sm font-medium">{tpl.title}</span>
                                      <Button
                                        variant="primary"
                                        size="xs"
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          navigator.clipboard.writeText(tpl.content)
                                          toast.success('템플릿이 클립보드에 복사되었습니다')
                                          if (tpl.id) {
                                            leadsApi.useResponseTemplate(tpl.id)
                                          }
                                        }}
                                        icon={<Copy className="w-3 h-3" />}
                                      >
                                        복사
                                      </Button>
                                    </div>
                                    <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-sans">
                                      {tpl.content}
                                    </pre>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="text-sm text-muted-foreground">템플릿을 불러오는 중...</p>
                            )}
                          </div>
                        )}
                      </div>

                      {/* [Phase 6.1] 컨택 히스토리 */}
                      <div className="pt-3 border-t border-border">
                        {showContactHistory !== lead.id ? (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation()
                              setShowContactHistory(lead.id)
                            }}
                            className="text-purple-500 border-purple-500/30 hover:bg-purple-500/10"
                          >
                            📝 컨택 히스토리
                          </Button>
                        ) : (
                          <div className="space-y-3">
                            <div className="flex items-center justify-between">
                              <div className="text-sm font-semibold">컨택 히스토리</div>
                              <Button
                                variant="ghost"
                                size="xs"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  setShowContactHistory(null)
                                }}
                              >
                                닫기
                              </Button>
                            </div>

                            {/* 새 컨택 추가 폼 */}
                            <div className="bg-card border border-border rounded-lg p-3 space-y-2">
                              <div className="flex gap-2">
                                <select
                                  value={newContactType}
                                  onChange={(e) => setNewContactType(e.target.value as 'comment' | 'dm' | 'email' | 'call')}
                                  onClick={(e) => e.stopPropagation()}
                                  className="text-xs px-2 py-1.5 bg-muted border border-border rounded"
                                >
                                  <option value="comment">💬 댓글</option>
                                  <option value="dm">📩 DM</option>
                                  <option value="email">✉️ 이메일</option>
                                  <option value="call">📞 전화</option>
                                </select>
                                <input
                                  type="text"
                                  value={newContactContent}
                                  onChange={(e) => setNewContactContent(e.target.value)}
                                  onClick={(e) => e.stopPropagation()}
                                  placeholder="컨택 내용 입력..."
                                  className="flex-1 text-xs px-2 py-1.5 bg-muted border border-border rounded focus:outline-none focus:ring-2 focus:ring-primary"
                                />
                                <Button
                                  variant="primary"
                                  size="xs"
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    if (newContactContent.trim()) {
                                      addContactMutation.mutate({
                                        lead_id: lead.id,
                                        contact_type: newContactType,
                                        content: newContactContent,
                                        platform: lead.platform,
                                      })
                                    }
                                  }}
                                  disabled={!newContactContent.trim()}
                                  loading={addContactMutation.isPending}
                                  className="bg-purple-500 hover:bg-purple-600"
                                >
                                  추가
                                </Button>
                              </div>
                            </div>

                            {/* 히스토리 목록 */}
                            {contactHistoryLoading ? (
                              <p className="text-sm text-muted-foreground">불러오는 중...</p>
                            ) : (contactHistoryData?.history?.length ?? 0) > 0 ? (
                              <div className="space-y-2 max-h-60 overflow-y-auto">
                                {contactHistoryData?.history?.map((item: any) => (
                                  <div
                                    key={item.id}
                                    className={`bg-card border rounded-lg p-3 ${
                                      item.status === 'replied'
                                        ? 'border-green-500/30'
                                        : item.status === 'no_response'
                                        ? 'border-red-500/30'
                                        : 'border-border'
                                    }`}
                                  >
                                    <div className="flex items-center justify-between mb-1">
                                      <div className="flex items-center gap-2">
                                        <span className="text-sm">
                                          {item.contact_type === 'comment' ? '💬' :
                                           item.contact_type === 'dm' ? '📩' :
                                           item.contact_type === 'email' ? '✉️' : '📞'}
                                        </span>
                                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                                          item.status === 'replied'
                                            ? 'bg-green-500/10 text-green-500'
                                            : item.status === 'no_response'
                                            ? 'bg-red-500/10 text-red-500'
                                            : 'bg-blue-500/10 text-blue-500'
                                        }`}>
                                          {item.status === 'replied' ? '응답받음' :
                                           item.status === 'no_response' ? '무응답' : '발송완료'}
                                        </span>
                                      </div>
                                      <span className="text-[10px] text-muted-foreground">
                                        {new Date(item.created_at).toLocaleString('ko-KR')}
                                      </span>
                                    </div>
                                    <p className="text-xs text-muted-foreground mb-2">{item.content}</p>
                                    {item.response && (
                                      <div className="bg-green-500/5 border border-green-500/20 rounded p-2 mt-2">
                                        <div className="text-[10px] text-green-500 mb-1">응답 내용:</div>
                                        <p className="text-xs">{item.response}</p>
                                      </div>
                                    )}
                                    {item.status === 'sent' && (
                                      <div className="flex gap-1 mt-2">
                                        <Button
                                          variant="success"
                                          size="xs"
                                          onClick={(e) => {
                                            e.stopPropagation()
                                            const response = prompt('응답 내용을 입력하세요:')
                                            if (response) {
                                              updateResponseMutation.mutate({
                                                historyId: item.id,
                                                response,
                                                status: 'replied',
                                              })
                                            }
                                          }}
                                        >
                                          응답 기록
                                        </Button>
                                        <Button
                                          variant="danger"
                                          size="xs"
                                          onClick={(e) => {
                                            e.stopPropagation()
                                            updateResponseMutation.mutate({
                                              historyId: item.id,
                                              response: '',
                                              status: 'no_response',
                                            })
                                          }}
                                        >
                                          무응답 처리
                                        </Button>
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="text-sm text-muted-foreground text-center py-4">
                                아직 컨택 기록이 없습니다
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
    )}

      {/* 페이지네이션 */}
      {leads.length > pageSize && (
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          onPageChange={handlePageChange}
          pageSize={pageSize}
          pageSizeOptions={[25, 50, 100]}
          onPageSizeChange={handlePageSizeChange}
          totalItems={leads.length}
        />
      )}
    </div>
  )
}

// [성능 최적화] memo로 leads, viewMode가 변경될 때만 리렌더링
const LeadTable = memo(LeadTableComponent, (prevProps, nextProps) => {
  return (
    prevProps.leads === nextProps.leads &&
    prevProps.viewMode === nextProps.viewMode &&
    prevProps.initialPageSize === nextProps.initialPageSize
  )
})

export default LeadTable

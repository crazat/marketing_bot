import { useState, useRef, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { leadsApi } from '@/services/api'
import { useToast } from '@/components/ui/Toast'
import Button, { IconButton } from '@/components/ui/Button'
import { X } from 'lucide-react'

interface LeadNoteEditorProps {
  leadId: number
  currentStatus: string
  notes: string
  followUpDate?: string | null
  contactInfo: string
  expectedRevenue?: number
  actualRevenue?: number
  sourceKeyword?: string
  sourceContent?: string
  onSuccess?: () => void
}

export default function LeadNoteEditor({
  leadId,
  currentStatus,
  notes: initialNotes,
  followUpDate: initialFollowUpDate,
  contactInfo: initialContactInfo,
  expectedRevenue: initialExpectedRevenue = 0,
  actualRevenue: initialActualRevenue = 0,
  sourceKeyword: initialSourceKeyword = '',
  sourceContent: initialSourceContent = '',
  onSuccess
}: LeadNoteEditorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [notes, setNotes] = useState(initialNotes || '')
  const [followUpDate, setFollowUpDate] = useState(initialFollowUpDate || '')
  const [contactInfo, setContactInfo] = useState(initialContactInfo || '')
  const [expectedRevenue, setExpectedRevenue] = useState(initialExpectedRevenue)
  const [actualRevenue, setActualRevenue] = useState(initialActualRevenue)
  const [sourceKeyword, setSourceKeyword] = useState(initialSourceKeyword)
  const [sourceContent, setSourceContent] = useState(initialSourceContent)
  const popoverRef = useRef<HTMLDivElement>(null)
  const toast = useToast()
  const queryClient = useQueryClient()

  // 외부 클릭 감지
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  const updateMutation = useMutation({
    mutationFn: () => leadsApi.updateLead(leadId, {
      status: currentStatus,
      notes,
      follow_up_date: followUpDate || null,
      contact_info: contactInfo,
      expected_revenue: expectedRevenue || undefined,
      actual_revenue: actualRevenue || undefined,
      source_keyword: sourceKeyword || undefined,
      source_content: sourceContent || undefined
    }),
    onSuccess: () => {
      toast.success('저장되었습니다')
      queryClient.invalidateQueries({ queryKey: ['leads'] })
      setIsOpen(false)
      onSuccess?.()
    },
    onError: () => {
      toast.error('저장 실패')
    }
  })

  const hasNotes = initialNotes && initialNotes.length > 0
  const hasFollowUp = initialFollowUpDate && initialFollowUpDate.length > 0

  // 팔로업 날짜가 오늘 이전인지 확인
  const isOverdue = hasFollowUp && new Date(initialFollowUpDate) < new Date(new Date().toDateString())

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`p-1.5 rounded hover:bg-muted transition-colors flex items-center gap-1 ${
          hasNotes ? 'text-primary' : 'text-muted-foreground'
        } ${isOverdue ? 'text-red-500' : ''}`}
        title={hasNotes ? notes : '노트 추가'}
      >
        {hasNotes ? '📝' : '➕'}
        {hasFollowUp && (
          <span className={`text-xs ${isOverdue ? 'text-red-500' : 'text-muted-foreground'}`}>
            {isOverdue ? '⚠️' : '📅'}
          </span>
        )}
      </button>

      {/* 팔로업 날짜 미리보기 */}
      {hasFollowUp && !isOpen && (
        <div className={`text-xs mt-1 ${isOverdue ? 'text-red-500 font-medium' : 'text-muted-foreground'}`}>
          {isOverdue ? '⚠️ ' : ''}
          {new Date(initialFollowUpDate).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' })}
        </div>
      )}

      {/* 편집 팝오버 */}
      {isOpen && (
        <div
          ref={popoverRef}
          className="absolute right-0 top-full mt-2 w-80 bg-card border border-border rounded-lg shadow-lg z-50 p-4"
        >
          <h4 className="font-semibold mb-3 text-sm">📝 리드 노트</h4>

          {/* 상담 노트 */}
          <div className="mb-4">
            <label className="text-xs text-muted-foreground mb-1 block">상담 메모</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="상담 내용, 관심사, 특이사항..."
              className="w-full h-24 px-3 py-2 text-sm bg-background border border-border rounded-lg resize-none focus:ring-2 focus:ring-primary focus:border-transparent"
            />
          </div>

          {/* 연락처 정보 */}
          <div className="mb-4">
            <label className="text-xs text-muted-foreground mb-1 block">연락처</label>
            <input
              type="text"
              value={contactInfo}
              onChange={(e) => setContactInfo(e.target.value)}
              placeholder="전화번호, 이메일 등..."
              className="w-full px-3 py-2 text-sm bg-background border border-border rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
            />
          </div>

          {/* 팔로업 날짜 */}
          <div className="mb-4">
            <label className="text-xs text-muted-foreground mb-1 block">팔로업 예정일</label>
            <div className="flex gap-2">
              <input
                type="date"
                value={followUpDate}
                onChange={(e) => setFollowUpDate(e.target.value)}
                className="flex-1 px-3 py-2 text-sm bg-background border border-border rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
              />
              {followUpDate && (
                <IconButton
                  icon={<X className="w-4 h-4" />}
                  onClick={() => setFollowUpDate('')}
                  size="sm"
                  title="날짜 삭제"
                />
              )}
            </div>
            {/* 빠른 선택 버튼 */}
            <div className="flex gap-2 mt-2">
              {[
                { label: '내일', days: 1 },
                { label: '3일 후', days: 3 },
                { label: '1주 후', days: 7 },
              ].map(({ label, days }) => (
                <Button
                  key={days}
                  variant="ghost"
                  size="xs"
                  onClick={() => {
                    const date = new Date()
                    date.setDate(date.getDate() + days)
                    setFollowUpDate(date.toISOString().split('T')[0])
                  }}
                  className="px-2 py-1 bg-muted text-muted-foreground hover:bg-muted/80"
                >
                  {label}
                </Button>
              ))}
            </div>
          </div>

          {/* [Phase 4.0] 매출 정보 */}
          <div className="mb-4 p-3 bg-muted/50 rounded-lg">
            <label className="text-xs text-muted-foreground mb-2 block font-medium">💰 매출 정보 (ROI 분석용)</label>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">예상 매출</label>
                <input
                  type="number"
                  value={expectedRevenue || ''}
                  onChange={(e) => setExpectedRevenue(parseInt(e.target.value) || 0)}
                  placeholder="₩0"
                  className="w-full px-3 py-2 text-sm bg-background border border-border rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">실제 매출</label>
                <input
                  type="number"
                  value={actualRevenue || ''}
                  onChange={(e) => setActualRevenue(parseInt(e.target.value) || 0)}
                  placeholder="₩0"
                  className="w-full px-3 py-2 text-sm bg-background border border-border rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                />
              </div>
            </div>
          </div>

          {/* [Phase 4.0] 출처 추적 */}
          <div className="mb-4">
            <label className="text-xs text-muted-foreground mb-2 block font-medium">🔗 출처 추적</label>
            <input
              type="text"
              value={sourceKeyword}
              onChange={(e) => setSourceKeyword(e.target.value)}
              placeholder="출처 키워드 (예: 청주 한의원)"
              className="w-full px-3 py-2 text-sm bg-background border border-border rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent mb-2"
            />
            <input
              type="text"
              value={sourceContent}
              onChange={(e) => setSourceContent(e.target.value)}
              placeholder="출처 URL (블로그, 영상 등)"
              className="w-full px-3 py-2 text-sm bg-background border border-border rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
            />
          </div>

          {/* 저장 버튼 */}
          <div className="flex justify-end gap-2">
            <Button
              onClick={() => setIsOpen(false)}
              variant="ghost"
              size="sm"
            >
              취소
            </Button>
            <Button
              onClick={() => updateMutation.mutate()}
              loading={updateMutation.isPending}
              size="sm"
            >
              저장
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

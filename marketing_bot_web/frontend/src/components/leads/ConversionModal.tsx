import { useState, useMemo } from 'react'
import Modal from '@/components/ui/Modal'
import Button from '@/components/ui/Button'
import { Lead } from '@/services/api'

interface ConversionModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: (data: {
    lead_id: number
    revenue: number
    keyword?: string
    platform?: string
    notes?: string
  }) => void
  lead: Lead | null
  loading?: boolean
}

// [UX 개선] 폼 유효성 검사 추가
interface FormErrors {
  revenue?: string
  keyword?: string
}

export default function ConversionModal({
  isOpen,
  onClose,
  onConfirm,
  lead,
  loading = false,
}: ConversionModalProps) {
  const [revenue, setRevenue] = useState<string>('')
  const [keyword, setKeyword] = useState<string>('')
  const [notes, setNotes] = useState<string>('')
  const [touched, setTouched] = useState<{ revenue: boolean; keyword: boolean }>({
    revenue: false,
    keyword: false,
  })

  // [UX 개선] 유효성 검사 로직
  const errors = useMemo<FormErrors>(() => {
    const errs: FormErrors = {}

    // 매출액 검증
    if (!revenue.trim()) {
      errs.revenue = '매출액을 입력해주세요'
    } else {
      const numRevenue = parseFloat(revenue)
      if (isNaN(numRevenue)) {
        errs.revenue = '유효한 숫자를 입력해주세요'
      } else if (numRevenue < 0) {
        errs.revenue = '매출액은 0 이상이어야 합니다'
      } else if (numRevenue > 100000000) {
        errs.revenue = '매출액이 너무 큽니다 (1억 이하)'
      }
    }

    // 키워드 검증 (선택 사항이지만 입력 시 검증)
    if (keyword && keyword.length > 50) {
      errs.keyword = '키워드는 50자 이하로 입력해주세요'
    }

    return errs
  }, [revenue, keyword])

  const isValid = Object.keys(errors).length === 0 && revenue.trim() !== ''

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!lead) return

    // 모든 필드 touched 처리
    setTouched({ revenue: true, keyword: true })

    if (!isValid) return

    onConfirm({
      lead_id: lead.id,
      revenue: parseFloat(revenue) || 0,
      keyword: keyword || undefined,
      platform: lead.platform || undefined,
      notes: notes || undefined,
    })
  }

  const handleClose = () => {
    setRevenue('')
    setKeyword('')
    setNotes('')
    setTouched({ revenue: false, keyword: false })
    onClose()
  }

  if (!lead) return null

  // 입력이 시작됐으면 실수로 ESC 눌러도 닫히지 않도록 보호 (매출액 등 입력값 손실 방지)
  const isDirty = revenue.trim() !== '' || keyword.trim() !== '' || notes.trim() !== ''

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="전환 기록"
      description="이 리드의 전환 정보를 기록합니다. 매출 데이터는 ROI 분석에 활용됩니다."
      size="md"
      closeOnEscape={!isDirty}
      closeOnOverlay={!isDirty}
      footer={
        <>
          <Button
            type="button"
            onClick={handleClose}
            variant="outline"
            size="sm"
            disabled={loading}
          >
            취소
          </Button>
          <Button
            type="submit"
            form="conversion-form"
            variant="success"
            size="sm"
            loading={loading}
            disabled={!isValid}
          >
            전환 기록
          </Button>
        </>
      }
    >
      <form id="conversion-form" onSubmit={handleSubmit} className="space-y-4">
        {/* 리드 정보 요약 */}
        <div className="bg-muted/50 rounded-lg p-3">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">플랫폼:</span>
            <span className="font-medium">{lead.platform || '기타'}</span>
          </div>
          <div className="text-sm mt-1 truncate" title={lead.title}>
            <span className="text-muted-foreground">제목:</span>{' '}
            <span>{lead.title || '제목 없음'}</span>
          </div>
          {lead.author && (
            <div className="text-sm mt-1">
              <span className="text-muted-foreground">작성자:</span>{' '}
              <span>{lead.author}</span>
            </div>
          )}
        </div>

        {/* 매출액 입력 */}
        <div>
          <label htmlFor="revenue" className="block text-sm font-medium mb-1.5">
            매출액 <span className="text-destructive">*</span>
          </label>
          <div className="relative">
            <input
              id="revenue"
              type="number"
              value={revenue}
              onChange={(e) => setRevenue(e.target.value)}
              onBlur={() => setTouched(prev => ({ ...prev, revenue: true }))}
              placeholder="예: 300000"
              min="0"
              max="100000000"
              step="1000"
              className={`w-full px-3 py-2 pr-12 bg-card border rounded-lg focus:outline-none focus:ring-2 transition-colors ${
                touched.revenue && errors.revenue
                  ? 'border-red-500 focus:border-red-500 focus:ring-red-500/30'
                  : 'border-border focus:border-primary focus:ring-primary'
              }`}
              required
              aria-invalid={touched.revenue && !!errors.revenue}
              aria-describedby={touched.revenue && errors.revenue ? 'revenue-error' : 'revenue-help'}
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">
              원
            </span>
          </div>
          {touched.revenue && errors.revenue ? (
            <p id="revenue-error" className="text-xs text-red-500 mt-1 flex items-center gap-1" role="alert">
              <svg className="w-3.5 h-3.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              {errors.revenue}
            </p>
          ) : (
            <p id="revenue-help" className="text-xs text-muted-foreground mt-1">
              이 리드를 통해 발생한 매출을 입력하세요
            </p>
          )}
        </div>

        {/* 연관 키워드 */}
        <div>
          <label htmlFor="keyword" className="block text-sm font-medium mb-1.5">
            연관 키워드 (선택)
          </label>
          <input
            id="keyword"
            type="text"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onBlur={() => setTouched(prev => ({ ...prev, keyword: true }))}
            placeholder="예: 청주 한의원"
            maxLength={50}
            className={`w-full px-3 py-2 bg-card border rounded-lg focus:outline-none focus:ring-2 transition-colors ${
              touched.keyword && errors.keyword
                ? 'border-red-500 focus:border-red-500 focus:ring-red-500/30'
                : 'border-border focus:border-primary focus:ring-primary'
            }`}
            aria-invalid={touched.keyword && !!errors.keyword}
            aria-describedby={touched.keyword && errors.keyword ? 'keyword-error' : 'keyword-help'}
          />
          {touched.keyword && errors.keyword ? (
            <p id="keyword-error" className="text-xs text-red-500 mt-1 flex items-center gap-1" role="alert">
              <svg className="w-3.5 h-3.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              {errors.keyword}
            </p>
          ) : (
            <p id="keyword-help" className="text-xs text-muted-foreground mt-1">
              이 전환과 연관된 키워드를 입력하면 키워드별 ROI를 분석할 수 있습니다
            </p>
          )}
        </div>

        {/* 메모 */}
        <div>
          <label htmlFor="notes" className="block text-sm font-medium mb-1.5">
            메모 (선택)
          </label>
          <textarea
            id="notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="전환 관련 추가 정보를 기록하세요"
            rows={3}
            className="w-full px-3 py-2 bg-card border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary resize-none"
          />
        </div>

        {/* 도움말 */}
        <div className="flex items-start gap-2 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm">
          <span className="text-lg">💡</span>
          <div className="text-blue-700 dark:text-blue-300">
            <p className="font-medium">전환 기록의 활용</p>
            <ul className="mt-1 text-xs space-y-0.5 text-blue-600 dark:text-blue-400">
              <li>• 플랫폼별 전환율 및 ROI 분석</li>
              <li>• 키워드별 매출 기여도 파악</li>
              <li>• 마케팅 전략 최적화에 활용</li>
            </ul>
          </div>
        </div>
      </form>
    </Modal>
  )
}

import { useState, useEffect, useRef, memo } from 'react'
import { Lead } from '@/services/api'
import Button from '@/components/ui/Button'
import {
  PLATFORM_ICONS,
  getScoreBadgeStyle,
  getTrustBadgeStyle,
  getTrustLabel,
  getEngagementSignalStyle,
  getEngagementSignalLabel,
  getPriorityStyle,
  getPriorityLabel,
  getRevenuePotentialStyle,
  getRevenuePotentialLabel,
} from '@/constants/styles'

interface LeadCardProps {
  lead: Lead
  onDragStart: (e: React.DragEvent, lead: Lead) => void
  onClick?: (lead: Lead) => void
  onStatusChange?: (lead: Lead, newStatus: string) => void
  showStatusButtons?: boolean
  /** 키보드 네비게이션: 포커스 상태 */
  isFocused?: boolean
  /** 키보드 네비게이션: 포커스 콜백 */
  onFocus?: () => void
}

const STATUS_OPTIONS = [
  { id: 'pending', label: '대기 중', icon: '⏳' },
  { id: 'contacted', label: '연락 완료', icon: '📞' },
  { id: 'replied', label: '답변 받음', icon: '💬' },
  { id: 'converted', label: '전환 완료', icon: '✅' },
  { id: 'rejected', label: '거절됨', icon: '❌' },
]

// [성능 최적화] React.memo로 불필요한 리렌더링 방지
function LeadCardComponent({
  lead,
  onDragStart,
  onClick,
  onStatusChange,
  showStatusButtons = true,
  isFocused = false,
  onFocus,
}: LeadCardProps) {
  const [showStatusMenu, setShowStatusMenu] = useState(false)
  const cardRef = useRef<HTMLDivElement>(null)
  const platformIcon = PLATFORM_ICONS[lead.platform?.toLowerCase()] || '📌'

  // 포커스 상태 시 스크롤 및 포커스 적용
  useEffect(() => {
    if (isFocused && cardRef.current) {
      cardRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      cardRef.current.focus()
    }
  }, [isFocused])

  const handleStatusChange = (newStatus: string) => {
    if (onStatusChange) {
      onStatusChange(lead, newStatus)
    }
    setShowStatusMenu(false)
  }

  const formatDate = (dateStr: string) => {
    if (!dateStr) return '-'
    try {
      const date = new Date(dateStr)
      const now = new Date()
      const diffMs = now.getTime() - date.getTime()
      const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
      const diffDays = Math.floor(diffHours / 24)

      if (diffHours < 1) return '방금 전'
      if (diffHours < 24) return `${diffHours}시간 전`
      if (diffDays < 7) return `${diffDays}일 전`
      return date.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' })
    } catch {
      return dateStr
    }
  }

  return (
    <div
      ref={cardRef}
      draggable
      onDragStart={(e) => onDragStart(e, lead)}
      onClick={() => onClick?.(lead)}
      onFocus={onFocus}
      tabIndex={isFocused ? 0 : -1}
      role="option"
      aria-selected={isFocused}
      aria-label={`${lead.platform || '기타'} 리드: ${lead.title || '제목 없음'}${lead.score ? `, 점수 ${lead.score}점` : ''}`}
      className={`bg-card border rounded-lg p-3 shadow-sm hover:shadow-md transition-all cursor-grab active:cursor-grabbing hover:border-primary/50 outline-none ${
        isFocused
          ? 'border-primary ring-2 ring-primary/50'
          : 'border-border'
      }`}
    >
      {/* 헤더 */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-lg flex-shrink-0">{platformIcon}</span>
          <span className="text-xs text-muted-foreground truncate">
            {lead.platform || '기타'}
          </span>
          {lead.score !== undefined && lead.score > 0 && (
            <span
              className={`px-1.5 py-0.5 rounded text-xs font-medium ${getScoreBadgeStyle(lead.score)}`}
              title={`리드 점수: ${lead.score}점 (${lead.score >= 80 ? '우수 - 즉시 연락 권장' : lead.score >= 60 ? '양호 - 검토 후 연락' : '보통 - 추가 확인 필요'})`}
            >
              {lead.score}점
            </span>
          )}
          {/* [Phase 4.0] 신뢰도 배지 */}
          {lead.trust_level && (
            <span
              className={`px-1.5 py-0.5 rounded text-xs font-medium ${getTrustBadgeStyle(lead.trust_level)}`}
              title={lead.trust_reasons?.join(', ') || '신뢰도 평가'}
            >
              {getTrustLabel(lead.trust_level)}
            </span>
          )}
          {/* [Phase 4.0] 연락처 추출 배지 */}
          {lead.extracted_contacts?.has_contact && (
            <span
              className="px-1.5 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400"
              title={lead.extracted_contacts.summary}
            >
              📞 연락처
            </span>
          )}
          {/* [Phase 5.0] 기회 배지 - opportunity_bonus > 10 */}
          {lead.opportunity_bonus !== undefined && lead.opportunity_bonus > 10 && (
            <span
              className="px-1.5 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
              title={`🎯 높은 기회 점수 (${lead.opportunity_bonus}점): 최근 게시물, 낮은 경쟁, 질문형 콘텐츠로 전환 가능성이 높습니다.`}
            >
              🎯 기회
            </span>
          )}
          {/* [Phase 5.0] 참여 신호 배지 */}
          {lead.engagement_signal && lead.engagement_signal !== 'passive' && (
            <span
              className={`px-1.5 py-0.5 rounded text-xs font-medium ${getEngagementSignalStyle(lead.engagement_signal)}`}
              title={lead.engagement_signal === 'ready_to_act'
                ? '⚡ 즉시대응: 예약, 비교, 결정 관련 언급으로 구매/전환 준비가 된 상태입니다.'
                : '🔍 정보탐색: 정보를 찾고 있는 단계로, 상세한 안내가 효과적입니다.'}
            >
              {lead.engagement_signal === 'ready_to_act' ? '⚡' : '🔍'} {getEngagementSignalLabel(lead.engagement_signal)}
            </span>
          )}
          {/* [Phase 5.1] 우선순위 배지 */}
          {lead.priority_rank && lead.priority_rank <= 3 && (
            <span
              className={`px-1.5 py-0.5 rounded text-xs font-bold ${getPriorityStyle(lead.priority_rank)}`}
              title={(() => {
                const priority = getPriorityLabel(lead.priority_rank)
                const md = lead.multi_dimensional
                if (!md) return priority.desc
                return `${priority.desc}\n전환확률: ${(md.conversion_probability * 100).toFixed(1)}%\n긴급도: ${md.urgency_score}점\n매칭도: ${md.fit_score}점`
              })()}
            >
              {getPriorityLabel(lead.priority_rank).icon} {getPriorityLabel(lead.priority_rank).label}
            </span>
          )}
          {/* [Phase 5.1] 수익 잠재력 배지 */}
          {lead.multi_dimensional?.revenue_potential && getRevenuePotentialLabel(lead.multi_dimensional.revenue_potential) && (
            <span
              className={`px-1.5 py-0.5 rounded text-xs font-medium ${getRevenuePotentialStyle(lead.multi_dimensional.revenue_potential)}`}
              title={`수익 잠재력: ${getRevenuePotentialLabel(lead.multi_dimensional.revenue_potential)?.label}`}
            >
              {getRevenuePotentialLabel(lead.multi_dimensional.revenue_potential)?.icon}
            </span>
          )}
        </div>
        <span className="text-xs text-muted-foreground flex-shrink-0">
          {formatDate(lead.detected_at)}
        </span>
      </div>

      {/* 제목 */}
      <h4 className="font-medium text-sm mb-1 line-clamp-2" title={lead.title}>
        {lead.title || '제목 없음'}
      </h4>

      {/* 내용 미리보기 */}
      {lead.content && (
        <p className="text-xs text-muted-foreground line-clamp-2 mb-2" title={lead.content}>
          {lead.content}
        </p>
      )}

      {/* 하단 정보 */}
      <div className="flex items-center justify-between text-xs">
        {lead.author && (
          <span className="text-muted-foreground truncate max-w-[60%]" title={lead.author}>
            👤 {lead.author}
          </span>
        )}
        <div className="flex items-center gap-2">
          {lead.url && (
            <a
              href={lead.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-primary hover:underline flex-shrink-0"
            >
              🔗 링크
            </a>
          )}
          {/* 터치 디바이스용 상태 변경 버튼 */}
          {showStatusButtons && onStatusChange && (
            <div className="relative">
              <Button
                variant="ghost"
                size="xs"
                onClick={(e) => {
                  e.stopPropagation()
                  setShowStatusMenu(!showStatusMenu)
                }}
                className="md:hidden"
                aria-label="상태 변경"
              >
                📋 이동
              </Button>
              {/* 상태 선택 메뉴 */}
              {showStatusMenu && (
                <div
                  className="absolute right-0 bottom-full mb-1 bg-card border border-border rounded-lg shadow-lg z-20 min-w-[120px]"
                  onClick={(e) => e.stopPropagation()}
                >
                  {STATUS_OPTIONS.map((status) => (
                    <button
                      key={status.id}
                      onClick={() => handleStatusChange(status.id)}
                      disabled={lead.status === status.id}
                      className={`w-full px-3 py-2 text-left text-xs hover:bg-muted transition-colors first:rounded-t-lg last:rounded-b-lg flex items-center gap-2 ${
                        lead.status === status.id ? 'bg-primary/10 text-primary' : ''
                      }`}
                    >
                      <span>{status.icon}</span>
                      <span>{status.label}</span>
                      {lead.status === status.id && <span className="ml-auto">✓</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      {/* 클릭 외부 시 메뉴 닫기 */}
      {showStatusMenu && (
        <div
          className="fixed inset-0 z-10"
          onClick={(e) => {
            e.stopPropagation()
            setShowStatusMenu(false)
          }}
        />
      )}
    </div>
  )
}

// memo로 lead.id, isFocused가 변경될 때만 리렌더링
const LeadCard = memo(LeadCardComponent, (prevProps, nextProps) => {
  return (
    prevProps.lead.id === nextProps.lead.id &&
    prevProps.lead.status === nextProps.lead.status &&
    prevProps.isFocused === nextProps.isFocused
  )
})

export default LeadCard

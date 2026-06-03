/**
 * [RECOVER OS] 리드 디테일 드로어
 * 카드 클릭 → 우측 패널: 온도/점수 · 상담 메모 · 4단계 진행 타임라인 · 매칭 Q&A · 지금 연락
 */
import { Lead } from '@/services/api'
import Drawer from '@/components/ui/Drawer'
import Button from '@/components/ui/Button'
import QAMatchPanel from '@/components/leads/QAMatchPanel'
import { platformIcon } from '@/lib/entityIcons'
import { Phone, ExternalLink, Check } from 'lucide-react'
import { safeUrl } from '@/utils/safeUrl'

interface LeadDetailDrawerProps {
  lead: Lead | null
  onClose: () => void
  /** 상태 변경 (대기/연락/응답/전환/거절) */
  onStatusChange?: (lead: Lead, status: string) => void
}

const STATUS_FLOW = [
  { id: 'pending', label: '대기 중', sub: '신규 발견' },
  { id: 'contacted', label: '연락 완료', sub: '첫 연락' },
  { id: 'replied', label: '답변 받음', sub: '응답 수신' },
  { id: 'converted', label: '전환 완료', sub: '목표 달성' },
]

export default function LeadDetailDrawer({ lead, onClose, onStatusChange }: LeadDetailDrawerProps) {
  const L = lead as any
  const grade: string = (L?.grade || 'cold').toLowerCase()
  const temp = grade === 'hot' ? { cls: 'hot', label: 'HOT' } : grade === 'warm' ? { cls: 'warm', label: 'WARM' } : { cls: 'cold', label: 'COLD' }
  const status: string = L?.status || 'pending'
  const currentIndex = STATUS_FLOW.findIndex((s) => s.id === status)
  const leadText: string = [L?.title, L?.content].filter(Boolean).join(' ').trim()
  const url = L?.url ? safeUrl(L.url) : null

  const detectedAt = L?.detected_at
    ? new Date(L.detected_at).toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : null

  const handleContact = () => {
    if (lead && onStatusChange && status === 'pending') onStatusChange(lead, 'contacted')
    if (url) window.open(url, '_blank', 'noopener,noreferrer')
  }

  return (
    <Drawer
      isOpen={!!lead}
      onClose={onClose}
      eyebrow={lead ? `LEAD · ${L?.platform || ''}` : undefined}
      title={lead ? L?.title || '리드 상세' : undefined}
      footer={
        lead ? (
          <>
            {url && (
              <Button variant="outline" size="sm" icon={<ExternalLink className="w-4 h-4" />} onClick={() => window.open(url, '_blank', 'noopener,noreferrer')}>
                원문 열기
              </Button>
            )}
            <Button variant="primary" size="sm" icon={<Phone className="w-4 h-4" />} onClick={handleContact}>
              지금 연락
            </Button>
          </>
        ) : undefined
      }
    >
      {lead && (
        <>
          {/* 온도 · 점수 */}
          <div className="ros-dr-row">
            <span className={`ros-temp ${temp.cls}`}>{temp.label}</span>
            <span className="text-faint inline-flex items-center gap-1.5">
              <span className="text-sage">{platformIcon(L?.platform, 'w-4 h-4')}</span>
              {L?.author || '익명'}
            </span>
            {typeof L?.score === 'number' && (
              <span className="ml-auto inline-flex items-baseline gap-1.5">
                <span className="num text-2xl text-strong">{L.score}</span>
                <span className="mono-label text-[10px] text-faint">SCORE</span>
              </span>
            )}
          </div>

          {/* 상담 메모 */}
          {L?.notes ? (
            <div className="ros-dr-sec">
              <div className="ros-dr-k">상담 메모</div>
              <p className="ros-dr-p whitespace-pre-wrap">{L.notes}</p>
            </div>
          ) : L?.content ? (
            <div className="ros-dr-sec">
              <div className="ros-dr-k">원문 내용</div>
              <p className="ros-dr-p whitespace-pre-wrap line-clamp-6">{L.content}</p>
            </div>
          ) : null}

          {/* 진행 타임라인 */}
          <div className="ros-dr-sec">
            <div className="ros-dr-k">진행 단계</div>
            <div className="flex flex-col">
              {STATUS_FLOW.map((step, i) => {
                const done = i <= currentIndex
                const isCurrent = i === currentIndex
                const dotColor = isCurrent ? 'var(--clay)' : done ? 'var(--ok)' : 'var(--text-faint)'
                return (
                  <button
                    key={step.id}
                    type="button"
                    className={`ros-dr-step ${done ? 'done' : ''} text-left w-full hover:opacity-90`}
                    onClick={() => onStatusChange?.(lead, step.id)}
                    title={`${step.label}(으)로 변경`}
                  >
                    <span className="ros-dr-dot" style={{ background: dotColor }} />
                    <span>
                      <span className="ros-dr-st">{step.label}</span>
                      <span className="ros-dr-ss block">{step.sub}</span>
                    </span>
                    {done && <Check className="ml-auto w-4 h-4 text-ok flex-shrink-0" strokeWidth={2} />}
                  </button>
                )
              })}
            </div>
          </div>

          {/* 매칭 Q&A */}
          {leadText && (
            <div className="ros-dr-sec">
              <div className="ros-dr-k">매칭 Q&amp;A</div>
              <QAMatchPanel leadText={leadText} platform={L?.platform} defaultExpanded />
            </div>
          )}

          {/* 메타 */}
          <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-[11.5px] text-faint mono-label">
            {L?.source_keyword && <span>KEYWORD · {L.source_keyword}</span>}
            {detectedAt && <span>FOUND · {detectedAt}</span>}
          </div>
        </>
      )}
    </Drawer>
  )
}

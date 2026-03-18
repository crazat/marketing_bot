import { Lead } from '@/services/api'
import LeadCard from './LeadCard'

interface KanbanColumnProps {
  id: string
  title: string
  icon: string
  color: string
  leads: Lead[]
  onDragStart: (e: React.DragEvent, lead: Lead) => void
  onDragOver: (e: React.DragEvent) => void
  onDrop: (e: React.DragEvent, status: string) => void
  onLeadClick?: (lead: Lead) => void
  onStatusChange?: (lead: Lead, newStatus: string) => void
  isDragOver?: boolean
  /** 키보드 네비게이션: 현재 포커스된 리드 인덱스 */
  focusedLeadIndex?: number
  /** 키보드 네비게이션: 리드 포커스 콜백 */
  onLeadFocus?: (leadIndex: number) => void
}

export default function KanbanColumn({
  id,
  title,
  icon,
  color,
  leads,
  onDragStart,
  onDragOver,
  onDrop,
  onLeadClick,
  onStatusChange,
  isDragOver = false,
  focusedLeadIndex = -1,
  onLeadFocus,
}: KanbanColumnProps) {
  return (
    <div
      className={`flex flex-col bg-muted/30 rounded-lg min-h-[500px] transition-colors ${
        isDragOver ? 'ring-2 ring-primary bg-primary/5' : ''
      }`}
      onDragOver={onDragOver}
      onDrop={(e) => onDrop(e, id)}
      role="listbox"
      aria-label={`${title} 상태 리드 목록 (${leads.length}개)`}
    >
      {/* 컬럼 헤더 */}
      <div className={`px-4 py-3 border-b-2 ${color} rounded-t-lg`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-lg">{icon}</span>
            <h3 className="font-semibold">{title}</h3>
          </div>
          <span className="px-2 py-0.5 bg-background rounded-full text-sm font-medium">
            {leads.length}
          </span>
        </div>
      </div>

      {/* 카드 목록 */}
      <div className="flex-1 p-3 space-y-3 overflow-y-auto max-h-[calc(100vh-300px)]">
        {leads.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center text-muted-foreground">
            <div className="text-3xl mb-2 opacity-50">{icon}</div>
            <p className="text-sm">리드가 없습니다</p>
            <p className="text-xs mt-1">카드를 여기로 드래그하세요</p>
          </div>
        ) : (
          leads.map((lead, index) => (
            <LeadCard
              key={lead.id}
              lead={lead}
              onDragStart={onDragStart}
              onClick={onLeadClick}
              onStatusChange={onStatusChange}
              isFocused={index === focusedLeadIndex}
              onFocus={() => onLeadFocus?.(index)}
            />
          ))
        )}
      </div>
    </div>
  )
}

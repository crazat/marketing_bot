import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { hudApi } from '@/services/api'
import Button from '@/components/ui/Button'

interface OverdueLeadsData {
  overdue_followups: Array<{
    id: number
    title: string
    platform: string
    follow_up_date: string
    status: string
    days_overdue: number
  }>
  stale_leads: Array<{
    id: number
    title: string
    platform: string
    created_at: string
    status: string
  }>
  no_response_leads: Array<{
    id: number
    title: string
    platform: string
    last_contact: string
    status: string
  }>
  summary: {
    total_overdue: number
    total_stale: number
    total_no_response: number
    total_action_needed: number
  }
}

const platformIcons: Record<string, string> = {
  youtube: '📺',
  tiktok: '🎵',
  instagram: '📸',
  naver: '🟢',
  carrot: '🥕',
  cafe: '☕',
}

export default function LeadReminders() {
  const navigate = useNavigate()

  const { data, isLoading } = useQuery<OverdueLeadsData>({
    queryKey: ['overdue-leads'],
    queryFn: hudApi.getOverdueLeads,
    refetchInterval: 300000,  // 5분마다 갱신
    retry: 1,
  })

  if (isLoading) {
    return null
  }

  if (!data || data.summary.total_action_needed === 0) {
    return null
  }

  const totalAlerts = data.summary.total_action_needed

  return (
    <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-yellow-600 flex items-center gap-2">
          <span className="text-xl">⏰</span>
          리드 리마인더
          <span className="px-2 py-0.5 text-xs bg-yellow-500 text-black rounded-full">
            {totalAlerts}
          </span>
        </h3>
        <Button
          variant="ghost"
          size="xs"
          onClick={() => navigate('/leads')}
          className="text-yellow-600"
        >
          전체 보기 →
        </Button>
      </div>

      <div className="space-y-3">
        {/* 팔로업 기한 초과 */}
        {data.overdue_followups.length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground mb-1">
              📅 팔로업 기한 초과 ({data.overdue_followups.length}건)
            </p>
            <div className="flex flex-wrap gap-2">
              {data.overdue_followups.slice(0, 3).map((lead) => (
                <Button
                  key={lead.id}
                  variant="ghost"
                  size="xs"
                  onClick={() => navigate(`/leads?id=${lead.id}`)}
                  className="px-3 py-1.5 bg-red-500/20 text-red-600 hover:bg-red-500/30 flex items-center gap-1"
                >
                  <span>{platformIcons[lead.platform] || '📱'}</span>
                  <span className="max-w-[120px] truncate">{lead.title}</span>
                  <span className="text-red-400">D+{lead.days_overdue}</span>
                </Button>
              ))}
              {data.overdue_followups.length > 3 && (
                <span className="text-xs text-muted-foreground self-center">
                  +{data.overdue_followups.length - 3}개
                </span>
              )}
            </div>
          </div>
        )}

        {/* 오래된 pending 리드 */}
        {data.stale_leads.length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground mb-1">
              ⚠️ 대기 중 3일 이상 ({data.stale_leads.length}건)
            </p>
            <div className="flex flex-wrap gap-2">
              {data.stale_leads.slice(0, 3).map((lead) => (
                <Button
                  key={lead.id}
                  variant="ghost"
                  size="xs"
                  onClick={() => navigate(`/leads?id=${lead.id}`)}
                  className="px-3 py-1.5 bg-yellow-500/20 text-yellow-600 hover:bg-yellow-500/30 flex items-center gap-1"
                >
                  <span>{platformIcons[lead.platform] || '📱'}</span>
                  <span className="max-w-[120px] truncate">{lead.title}</span>
                </Button>
              ))}
              {data.stale_leads.length > 3 && (
                <span className="text-xs text-muted-foreground self-center">
                  +{data.stale_leads.length - 3}개
                </span>
              )}
            </div>
          </div>
        )}

        {/* 응답 없는 리드 */}
        {data.no_response_leads.length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground mb-1">
              📭 연락 후 응답 없음 ({data.no_response_leads.length}건)
            </p>
            <div className="flex flex-wrap gap-2">
              {data.no_response_leads.slice(0, 3).map((lead) => (
                <Button
                  key={lead.id}
                  variant="ghost"
                  size="xs"
                  onClick={() => navigate(`/leads?id=${lead.id}`)}
                  className="px-3 py-1.5 bg-orange-500/20 text-orange-600 hover:bg-orange-500/30 flex items-center gap-1"
                >
                  <span>{platformIcons[lead.platform] || '📱'}</span>
                  <span className="max-w-[120px] truncate">{lead.title}</span>
                </Button>
              ))}
              {data.no_response_leads.length > 3 && (
                <span className="text-xs text-muted-foreground self-center">
                  +{data.no_response_leads.length - 3}개
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

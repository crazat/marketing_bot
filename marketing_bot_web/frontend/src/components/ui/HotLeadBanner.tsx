/**
 * [Phase 6.0] 핫리드 배너 컴포넌트
 * 대시보드 상단에 Hot Lead(80점+)를 눈에 띄게 표시
 */

import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { leadsApi } from '@/services/api'
import { Flame, ArrowRight, X } from 'lucide-react'
import { useState, useEffect } from 'react'
import { useNotification, createHotLeadNotification } from '@/hooks/useNotification'
import Button, { IconButton } from '@/components/ui/Button'

interface HotLead {
  id: number
  title: string
  platform: string
  score: number
  grade: string
  created_at: string
  url?: string
}

export default function HotLeadBanner() {
  const navigate = useNavigate()
  const [dismissed, setDismissed] = useState(false)
  const [notifiedLeads, setNotifiedLeads] = useState<Set<number>>(new Set())
  const { permission, showNotification } = useNotification()

  const { data: hotLeadsData } = useQuery({
    queryKey: ['hot-leads'],
    queryFn: () => leadsApi.getHotLeads(5),
    refetchInterval: 60000, // 1분마다 갱신
  })

  const hotLeads: HotLead[] = hotLeadsData?.leads || []

  // 새로운 핫리드 발견 시 알림
  useEffect(() => {
    if (permission === 'granted' && hotLeads.length > 0) {
      hotLeads.forEach((lead) => {
        if (!notifiedLeads.has(lead.id)) {
          const notif = createHotLeadNotification(lead.title, lead.platform, lead.score)
          showNotification(notif.title, notif.options)
          setNotifiedLeads((prev) => new Set(prev).add(lead.id))
        }
      })
    }
  }, [hotLeads, permission, showNotification, notifiedLeads])

  if (dismissed || !hotLeads || hotLeads.length === 0) {
    return null
  }

  const platformIcons: Record<string, string> = {
    youtube: '📺',
    tiktok: '🎵',
    naver: '🟢',
    instagram: '📸',
    carrot: '🥕',
    influencer: '⭐',
  }

  return (
    <div className="relative bg-gradient-to-r from-red-500/20 via-orange-500/20 to-yellow-500/20 border border-red-500/30 rounded-lg p-4 mb-6 animate-pulse-slow">
      <IconButton
        icon={<X className="w-4 h-4 text-muted-foreground" />}
        onClick={() => setDismissed(true)}
        className="absolute top-2 right-2 hover:bg-red-500/20"
        size="xs"
        aria-label="배너 닫기"
      />

      <div className="flex items-center gap-3 mb-3">
        <div className="flex items-center justify-center w-10 h-10 bg-red-500/20 rounded-full">
          <Flame className="w-6 h-6 text-red-500" />
        </div>
        <div>
          <h3 className="font-bold text-lg flex items-center gap-2">
            <span className="text-red-500">Hot Lead</span>
            <span className="text-xs px-2 py-0.5 bg-red-500 text-white rounded-full">
              {hotLeads.length}건
            </span>
          </h3>
          <p className="text-sm text-muted-foreground">
            즉시 연락이 필요한 고품질 리드입니다
          </p>
        </div>
      </div>

      <div className="space-y-2">
        {hotLeads.slice(0, 3).map((lead) => (
          <div
            key={lead.id}
            className="flex items-center justify-between gap-2 p-3 bg-card/50 rounded-lg hover:bg-card transition-colors cursor-pointer"
            onClick={() => navigate(`/leads?status=pending`)}
          >
            <div className="flex items-center gap-2 md:gap-3 min-w-0 flex-1">
              <span className="text-lg md:text-xl flex-shrink-0">{platformIcons[lead.platform] || '📋'}</span>
              <div className="min-w-0">
                <div className="font-medium text-sm truncate">
                  {lead.title}
                </div>
                <div className="text-xs text-muted-foreground">
                  {new Date(lead.created_at).toLocaleDateString('ko-KR')}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span className="text-base md:text-lg font-bold text-red-500">{lead.score}점</span>
              <ArrowRight className="w-4 h-4 text-muted-foreground hidden sm:block" />
            </div>
          </div>
        ))}
      </div>

      {hotLeads.length > 3 && (
        <Button
          onClick={() => navigate('/leads?grade=hot')}
          variant="ghost"
          size="sm"
          fullWidth
          className="mt-3 text-red-500 hover:bg-red-500/10"
        >
          +{hotLeads.length - 3}건 더 보기
        </Button>
      )}
    </div>
  )
}

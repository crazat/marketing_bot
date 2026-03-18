import { useQuery } from '@tanstack/react-query'
import { leadsApi } from '@/services/api'

export type LeadPlatform = 'cafe' | 'youtube' | 'tiktok' | 'instagram' | 'carrot' | 'influencer'

interface LeadQueryOptions {
  status?: string
  limit?: number
  enabled?: boolean
}

const apiMethodMap = {
  cafe: leadsApi.getNaverLeads,
  youtube: leadsApi.getYoutubeLeads,
  tiktok: leadsApi.getTiktokLeads,
  instagram: leadsApi.getInstagramLeads,
  carrot: leadsApi.getCarrotLeads,
  influencer: leadsApi.getInfluencerLeads,
} as const

/**
 * 플랫폼별 리드 조회 훅
 *
 * @example
 * const { data, isLoading, isError, refetch } = useLeadsByPlatform('youtube')
 */
export function useLeadsByPlatform(
  platform: LeadPlatform,
  options: LeadQueryOptions = {}
) {
  const { status, limit = 100, enabled = true } = options

  return useQuery({
    queryKey: [`${platform}-leads`, status] as const,
    queryFn: () => apiMethodMap[platform]({
      status: status || undefined,
      limit
    }),
    enabled,
  })
}

/**
 * 리드 통계 조회 훅
 */
export function useLeadStats() {
  return useQuery({
    queryKey: ['leads-stats'],
    queryFn: leadsApi.getStats,
  })
}

/**
 * 모든 플랫폼 쿼리 키 반환
 */
export function getAllLeadQueryKeys() {
  return [
    'naver-leads',
    'youtube-leads',
    'tiktok-leads',
    'instagram-leads',
    'carrot-leads',
    'influencer-leads',
    'leads-stats',
  ] as const
}

/**
 * 플랫폼 정보 맵
 */
export const PLATFORM_INFO: Record<LeadPlatform, { icon: string; name: string; scanModule: string }> = {
  cafe: { icon: '🏠', name: '맘카페', scanModule: 'cafe_swarm' },
  youtube: { icon: '📺', name: 'YouTube', scanModule: 'youtube' },
  tiktok: { icon: '🎵', name: 'TikTok', scanModule: 'tiktok' },
  instagram: { icon: '📸', name: 'Instagram', scanModule: 'instagram' },
  carrot: { icon: '🥕', name: '당근마켓', scanModule: 'carrot_farm' },
  influencer: { icon: '🤝', name: '인플루언서', scanModule: 'ambassador' },
}

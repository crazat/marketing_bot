/**
 * usePrefetch Hook
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [성능 최적화] 페이지 전환 전 데이터 프리페칭
 * - 사이드바 메뉴 hover 시 해당 페이지 데이터 미리 로드
 * - 페이지 전환 시 즉시 데이터 표시 가능
 */

import { useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  pathfinderApi,
  battleApi,
  viralApi,
  leadsApi,
  competitorsApi,
} from '@/services/api'

// 페이지별 프리페칭 설정
const prefetchConfig: Record<string, () => Promise<void>[]> = {
  '/': () => [
    // Dashboard
  ],
  '/pathfinder': () => [
    pathfinderApi.getKeywords({ limit: 50, offset: 0 }),
    pathfinderApi.getStats(),
  ],
  '/battle': () => [
    battleApi.getRankingKeywords(),
    battleApi.getRankingTrends(),
  ],
  '/viral': () => [
    viralApi.getStats(),
    viralApi.getScanBatches(),
  ],
  '/leads': () => [
    leadsApi.getLeads({ platform: 'naver' }),
    leadsApi.getPendingAlerts(),
  ],
  '/competitors': () => [
    competitorsApi.getWeaknesses(),
    competitorsApi.getList(),
  ],
}

/**
 * 페이지 데이터 프리페칭 훅
 */
export function usePrefetch() {
  const queryClient = useQueryClient()

  const prefetchPage = useCallback(
    async (path: string) => {
      const config = prefetchConfig[path]
      if (!config) return

      try {
        // 각 API에 대해 프리페칭 실행
        const promises = config()

        // 프리페칭은 조용히 실패해도 됨 (사용자 경험에 영향 없음)
        await Promise.allSettled(
          promises.map((promise) => {
            // queryKey를 동적으로 생성하기 어려우므로
            // 간단히 staleTime 내에 있으면 캐시 사용
            return promise.catch(() => {
              // 프리페칭 실패는 무시
            })
          })
        )
      } catch {
        // 프리페칭 오류 무시
      }
    },
    [queryClient]
  )

  // 특정 쿼리 프리페칭
  const prefetchQuery = useCallback(
    async <T>(
      queryKey: string[],
      queryFn: () => Promise<T>,
      staleTime: number = 60000
    ) => {
      try {
        await queryClient.prefetchQuery({
          queryKey,
          queryFn,
          staleTime,
        })
      } catch {
        // 프리페칭 오류 무시
      }
    },
    [queryClient]
  )

  return {
    prefetchPage,
    prefetchQuery,
  }
}

/**
 * 사이드바 링크용 프리페칭 핸들러
 */
export function useSidebarPrefetch() {
  const { prefetchPage } = usePrefetch()
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)

  const handleMouseEnter = useCallback(
    (path: string) => {
      // 100ms 딜레이로 불필요한 프리페칭 방지 (빠른 마우스 이동 시)
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
      timeoutRef.current = setTimeout(() => {
        prefetchPage(path)
      }, 100)
    },
    [prefetchPage]
  )

  const handleMouseLeave = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
  }, [])

  return { handleMouseEnter, handleMouseLeave }
}

export default usePrefetch

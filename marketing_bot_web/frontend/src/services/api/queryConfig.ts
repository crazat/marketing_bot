/**
 * React Query 설정 프리셋
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [UX 개선] 데이터 유형별 최적화된 쿼리 설정
 * - 실시간 데이터: 짧은 staleTime, 자동 새로고침
 * - 준실시간 데이터: 중간 staleTime
 * - 정적 데이터: 긴 staleTime, 포커스 시 새로고침 안 함
 *
 * 사용법:
 *   import { QUERY_CONFIGS } from '@/services/api/queryConfig'
 *
 *   useQuery({
 *     queryKey: ['metrics'],
 *     queryFn: fetchMetrics,
 *     ...QUERY_CONFIGS.realtime,
 *   })
 */

import { UseQueryOptions } from '@tanstack/react-query'

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 시간 상수
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export const TIME = {
  SECONDS_10: 10 * 1000,
  SECONDS_30: 30 * 1000,
  MINUTE_1: 60 * 1000,
  MINUTE_2: 2 * 60 * 1000,
  MINUTE_5: 5 * 60 * 1000,
  MINUTE_10: 10 * 60 * 1000,
  MINUTE_30: 30 * 60 * 1000,
  HOUR_1: 60 * 60 * 1000,
} as const

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 쿼리 프리셋 타입
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

type QueryPreset = Pick<
  UseQueryOptions,
  'staleTime' | 'gcTime' | 'refetchInterval' | 'refetchOnWindowFocus' | 'refetchOnReconnect'
>

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 쿼리 설정 프리셋
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export const QUERY_CONFIGS = {
  /**
   * 실시간 데이터 (대시보드 메트릭, 알림 등)
   * - [Phase 7] 30초 → 60초 후 stale (API 호출 50% 감소)
   * - 2분마다 자동 새로고침
   * - [Phase 2 최적화] 포커스 시 새로고침 비활성화 (불필요한 API 호출 감소)
   * - 백그라운드 탭에서는 자동 새로고침 중지
   */
  realtime: {
    staleTime: TIME.MINUTE_1, // [Phase 7] 30초 → 60초
    gcTime: TIME.MINUTE_5,
    refetchInterval: TIME.MINUTE_2, // [Phase 7] 1분 → 2분
    refetchOnWindowFocus: false,  // [Phase 2] 포커스 시 새로고침 비활성화
    refetchOnReconnect: true,
  } satisfies QueryPreset,

  /**
   * 준실시간 데이터 (순위, 리드 목록 등)
   * - 2분 후 stale
   * - 5분마다 자동 새로고침
   * - [Phase 2 최적화] 포커스 시 새로고침 비활성화
   */
  semiRealtime: {
    staleTime: TIME.MINUTE_2,
    gcTime: TIME.MINUTE_10,
    refetchInterval: TIME.MINUTE_5,
    refetchOnWindowFocus: false,  // [Phase 2] 포커스 시 새로고침 비활성화
    refetchOnReconnect: true,
  } satisfies QueryPreset,

  /**
   * 일반 데이터 (키워드 목록, 경쟁사 분석 등)
   * - 5분 후 stale
   * - 자동 새로고침 없음
   * - [Phase 2 최적화] 포커스 시 새로고침 비활성화
   */
  standard: {
    staleTime: TIME.MINUTE_5,
    gcTime: TIME.MINUTE_30,
    refetchOnWindowFocus: false,  // [Phase 2] 포커스 시 새로고침 비활성화
    refetchOnReconnect: true,
  } satisfies QueryPreset,

  /**
   * 정적 데이터 (설정, 옵션 목록 등)
   * - 30분 후 stale
   * - 자동 새로고침 없음
   * - 포커스 시에도 새로고침 안 함
   */
  static: {
    staleTime: TIME.MINUTE_30,
    gcTime: TIME.HOUR_1,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  } satisfies QueryPreset,

  /**
   * 무기한 캐시 (거의 변하지 않는 데이터)
   * - 1시간 후 stale
   * - 새로고침 없음
   */
  permanent: {
    staleTime: TIME.HOUR_1,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  } satisfies QueryPreset,

  /**
   * 한 번만 조회 (초기 로드 후 변경 없음)
   * - 무기한 fresh
   * - 수동으로만 새로고침
   */
  once: {
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  } satisfies QueryPreset,
} as const

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 도메인별 권장 설정
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export const DOMAIN_CONFIGS = {
  // 대시보드 HUD
  'hud.metrics': QUERY_CONFIGS.realtime,
  'hud.briefing': QUERY_CONFIGS.semiRealtime,
  'hud.scanner-status': QUERY_CONFIGS.realtime,

  // 알림
  'notifications.list': QUERY_CONFIGS.realtime,
  'notifications.unread-count': QUERY_CONFIGS.realtime,

  // 키워드
  'pathfinder.keywords': QUERY_CONFIGS.standard,
  'pathfinder.history': QUERY_CONFIGS.standard,
  'pathfinder.clusters': QUERY_CONFIGS.standard,

  // 순위
  'battle.rankings': QUERY_CONFIGS.semiRealtime,
  'battle.trends': QUERY_CONFIGS.semiRealtime,
  'battle.decline-streaks': QUERY_CONFIGS.semiRealtime,

  // 바이럴
  'viral.targets': QUERY_CONFIGS.standard,
  'viral.category-stats': QUERY_CONFIGS.semiRealtime,

  // 리드
  'leads.list': QUERY_CONFIGS.semiRealtime,
  'leads.priority-queue': QUERY_CONFIGS.realtime,

  // 경쟁사
  'competitors.list': QUERY_CONFIGS.standard,
  'competitors.analysis': QUERY_CONFIGS.standard,
  'competitors.weaknesses': QUERY_CONFIGS.standard,

  // 설정
  'settings.config': QUERY_CONFIGS.static,
  'settings.keywords': QUERY_CONFIGS.static,
  'qa.repository': QUERY_CONFIGS.static,

  // 분석
  'analytics.metrics': QUERY_CONFIGS.semiRealtime,
  'analytics.roi': QUERY_CONFIGS.standard,
} as const

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 유틸리티 함수
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

/**
 * 도메인 키로 쿼리 설정 가져오기
 */
export function getQueryConfig(domainKey: keyof typeof DOMAIN_CONFIGS): QueryPreset {
  return DOMAIN_CONFIGS[domainKey]
}

/**
 * 조건부 새로고침 간격 설정
 * - 탭이 활성화 상태일 때만 새로고침
 */
export function conditionalRefetchInterval(interval: number, enabled: boolean = true): number | false {
  return enabled ? interval : false
}

/**
 * 페이지 가시성 기반 새로고침 설정
 */
export function useVisibilityBasedRefetch(baseInterval: number) {
  const isVisible = typeof document !== 'undefined' && document.visibilityState === 'visible'
  return conditionalRefetchInterval(baseInterval, isVisible)
}

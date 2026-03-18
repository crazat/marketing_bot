/**
 * React Query 키 팩토리
 *
 * 일관된 쿼리 키 관리를 위한 중앙 집중식 팩토리
 *
 * @example
 * // 사용법
 * useQuery({ queryKey: queryKeys.pathfinder.keywords(filters) })
 * queryClient.invalidateQueries({ queryKey: queryKeys.pathfinder.all })
 */

export const queryKeys = {
  // === HUD ===
  hud: {
    all: ['hud'] as const,
    metrics: () => [...queryKeys.hud.all, 'metrics'] as const,
    status: () => [...queryKeys.hud.all, 'status'] as const,
    briefing: () => [...queryKeys.hud.all, 'briefing'] as const,
    scheduler: () => [...queryKeys.hud.all, 'scheduler'] as const,
  },

  // === Pathfinder ===
  pathfinder: {
    all: ['pathfinder'] as const,
    stats: () => [...queryKeys.pathfinder.all, 'stats'] as const,
    keywords: (filters?: Record<string, string>) =>
      filters
        ? ([...queryKeys.pathfinder.all, 'keywords', filters] as const)
        : ([...queryKeys.pathfinder.all, 'keywords'] as const),
    clusters: () => [...queryKeys.pathfinder.all, 'clusters'] as const,
  },

  // === Leads ===
  leads: {
    all: ['leads'] as const,
    stats: () => [...queryKeys.leads.all, 'stats'] as const,
    byPlatform: (platform: string, status?: string) =>
      status
        ? ([`${platform}-leads`, status] as const)
        : ([`${platform}-leads`] as const),
  },

  // === Battle Intelligence ===
  battle: {
    all: ['battle'] as const,
    rankingKeywords: () => [...queryKeys.battle.all, 'ranking-keywords'] as const,
    trends: (days: number) => [...queryKeys.battle.all, 'trends', days] as const,
    competitorVitals: () => [...queryKeys.battle.all, 'competitor-vitals'] as const,
  },

  // === Viral Hunter ===
  viral: {
    all: ['viral'] as const,
    targets: (filters?: Record<string, string>) =>
      filters
        ? ([...queryKeys.viral.all, 'targets', filters] as const)
        : ([...queryKeys.viral.all, 'targets'] as const),
    stats: () => [...queryKeys.viral.all, 'stats'] as const,
    categories: () => [...queryKeys.viral.all, 'categories'] as const,
    comments: (targetId: string) => [...queryKeys.viral.all, 'comments', targetId] as const,
  },

  // === Competitors ===
  competitors: {
    all: ['competitors'] as const,
    list: () => [...queryKeys.competitors.all, 'list'] as const,
    weaknesses: (days?: number) =>
      days
        ? ([...queryKeys.competitors.all, 'weaknesses', days] as const)
        : ([...queryKeys.competitors.all, 'weaknesses'] as const),
    weaknessSummary: () => [...queryKeys.competitors.all, 'weakness-summary'] as const,
    opportunities: (status?: string) =>
      status
        ? ([...queryKeys.competitors.all, 'opportunities', status] as const)
        : ([...queryKeys.competitors.all, 'opportunities'] as const),
    instagram: {
      stats: () => [...queryKeys.competitors.all, 'instagram', 'stats'] as const,
      hashtags: () => [...queryKeys.competitors.all, 'instagram', 'hashtags'] as const,
    },
  },
} as const

// 타입 추출 헬퍼
export type QueryKeys = typeof queryKeys

import type { QueryClient } from '@tanstack/react-query'

/**
 * [AA2/DD6] Query 무효화 중앙 헬퍼
 *
 * 도메인 단위 단일 호출 → 관련된 모든 쿼리를 일괄 갱신.
 * 개별 호출 지점마다 invalidateQueries를 나열해 빠뜨리는 것을 방지.
 *
 * [DD6] 250ms 디바운스 — 연속 대량 작업 시 refetch 폭발 방지.
 * 같은 도메인의 invalidate를 모아 한 번만 실행.
 */

const DEBOUNCE_MS = 250
const pending = new Map<string, ReturnType<typeof setTimeout>>()

function scheduleInvalidate(key: string, fn: () => void) {
  const existing = pending.get(key)
  if (existing) clearTimeout(existing)
  const timer = setTimeout(() => {
    pending.delete(key)
    fn()
  }, DEBOUNCE_MS)
  pending.set(key, timer)
}

/** 바이럴 타겟 액션 후 호출 — 대기/처리/KPI/큐 모두 갱신 (디바운스) */
export function invalidateViralAll(qc: QueryClient): void {
  scheduleInvalidate('viral', () => {
    qc.invalidateQueries({ queryKey: ['viral-filtered-targets'] })
    qc.invalidateQueries({ queryKey: ['viral-filtered-targets-count'] })
    qc.invalidateQueries({ queryKey: ['viral-all-targets'] })
    qc.invalidateQueries({ queryKey: ['viral-stats'] })
    qc.invalidateQueries({ queryKey: ['viral-kpi-stats'] })
    qc.invalidateQueries({ queryKey: ['viral-todays-queue'] })
    qc.invalidateQueries({ queryKey: ['today-focus-queue'] })
    qc.invalidateQueries({ queryKey: ['today-focus-tier1'] })
  })
}

/** 바이럴 승인으로 인해 리드 생성된 경우 — 리드 관련 쿼리도 갱신 */
export function invalidateViralAndLeads(qc: QueryClient): void {
  invalidateViralAll(qc)
  scheduleInvalidate('viral-leads', () => {
    qc.invalidateQueries({ queryKey: ['leads-stats'] })
    qc.invalidateQueries({ queryKey: ['leads-pending-alerts'] })
    qc.invalidateQueries({ queryKey: ['leads'] })
  })
}

/** 리드 상태 변경 후 */
export function invalidateLeadAll(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['leads'] })
  qc.invalidateQueries({ queryKey: ['leads-stats'] })
  qc.invalidateQueries({ queryKey: ['leads-pending-alerts'] })
  qc.invalidateQueries({ queryKey: ['lead-detail'] })
  qc.invalidateQueries({ queryKey: ['attribution-keyword'] })
  qc.invalidateQueries({ queryKey: ['attribution-rank'] })
  qc.invalidateQueries({ queryKey: ['attribution-viral'] })
}

/** 키워드(Pathfinder) 변경 후 */
export function invalidateKeywordAll(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['keywords'] })
  qc.invalidateQueries({ queryKey: ['pathfinder-stats'] })
  qc.invalidateQueries({ queryKey: ['top-kei-keywords'] })
  qc.invalidateQueries({ queryKey: ['recommended-keywords'] })
}

/** HUD / 대시보드 메트릭 갱신 */
export function invalidateDashboard(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['hud-metrics'] })
  qc.invalidateQueries({ queryKey: ['daily-briefing'] })
  qc.invalidateQueries({ queryKey: ['sentinel-alerts'] })
  qc.invalidateQueries({ queryKey: ['system-status'] })
}

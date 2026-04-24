import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { viralApi } from '@/services/api'

export interface Anomaly {
  id: string
  severity: 'critical' | 'warning' | 'info'
  title: string
  detail: string
  /** 이동 경로 */
  path?: string
  /** 값 변화 (배수 또는 ±) */
  delta?: string
}

/**
 * [Z2] 이상치 감지 — Viral KPI 기반 간단 룰.
 *
 * 프론트엔드에서 감지 가능한 것:
 *  - 오늘 대기 HOT LEAD가 14일 평균의 2배 이상
 *  - 대기 backlog 누적 (300+)
 *  - AI 적합률 급락 (30% 미만)
 */
export function useAnomalyDetection(): { anomalies: Anomaly[]; isLoading: boolean } {
  const { data, isLoading } = useQuery({
    queryKey: ['viral-kpi-stats', 14],
    queryFn: () => viralApi.getKpiStats(14),
    staleTime: 120_000,
  })

  const anomalies = useMemo<Anomaly[]>(() => {
    if (!data) return []
    const list: Anomaly[] = []

    // [EE5] 모든 값 방어적 파싱
    const hot = Number(data.summary?.backlog_hot) || 0
    const backlog = Number(data.summary?.backlog_pending) || 0
    const rate = Number(data.summary?.ai_accept_rate) || 0
    const daily = Array.isArray(data.daily) ? data.daily : []

    // 평균 일 처리량
    const totalProcessed = daily.reduce(
      (acc, d) => acc + (Number(d?.approved) || 0) + (Number(d?.posted) || 0) + (Number(d?.skipped) || 0),
      0,
    )
    const avgDaily = daily.length > 0 ? totalProcessed / daily.length : 0
    if (!Number.isFinite(avgDaily)) return []

    // 1. HOT LEAD 급증 — 대기 HOT이 일평균 처리량의 2배 이상
    if (hot > 0 && avgDaily > 0 && hot >= avgDaily * 2) {
      list.push({
        id: 'hot-surge',
        severity: 'critical',
        title: `HOT LEAD ${hot.toLocaleString()}건 대기 — 평균 대비 급증`,
        detail: `최근 ${daily.length}일 평균 처리량 ${Math.round(avgDaily)}건보다 ${Math.round((hot / avgDaily) * 10) / 10}배. 즉시 처리 권장.`,
        path: '/viral',
        delta: `×${Math.round((hot / avgDaily) * 10) / 10}`,
      })
    }

    // 2. 대기 누적 경고
    if (backlog >= 500) {
      list.push({
        id: 'backlog-heavy',
        severity: 'warning',
        title: `대기 ${backlog.toLocaleString()}건 누적`,
        detail: '일괄 처리로 정리하거나 필터 프리셋으로 우선순위 정리가 필요합니다.',
        path: '/viral',
      })
    }

    // 3. AI 적합률 급락
    if (rate > 0 && rate < 0.3) {
      list.push({
        id: 'ai-rate-drop',
        severity: 'warning',
        title: `AI 적합률 ${Math.round(rate * 100)}% — 기준 미달`,
        detail: '댓글 스타일을 재검토하거나 더 구체적 스타일로 재생성을 고려하세요.',
        path: '/viral',
      })
    }

    return list
  }, [data])

  return { anomalies, isLoading }
}

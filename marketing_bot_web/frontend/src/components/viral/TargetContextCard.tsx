import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Info } from 'lucide-react'
import { viralApi } from '@/services/api'

interface TargetContextCardProps {
  targetId: string | null
  compact?: boolean
}

interface TargetContextData {
  target_id: string
  domain: string
  domain_recent_approved_7d: number
  author_recent_approved_7d: number
  scan_count: number
  badges: Array<{ type: string; label: string; color: string }>
  warnings: string[]
}

/**
 * [U4] 컨텍스트 카드 — 타겟 승인 전 필요한 맥락 정보:
 * - 경쟁사 배지, Tier 배지
 * - 동일 도메인·작성자에 대한 최근 댓글 이력 (과노출 경고)
 * - 재발견 횟수
 */
export default function TargetContextCard({ targetId, compact = false }: TargetContextCardProps) {
  const { data, isLoading } = useQuery<TargetContextData | null>({
    queryKey: ['viral-target-context', targetId],
    queryFn: () => (targetId ? viralApi.getTargetWarnings(targetId) : Promise.resolve(null)),
    enabled: !!targetId,
    staleTime: 120_000,
    retry: 1,
  })

  if (!targetId || isLoading || !data) return null

  const hasContent =
    data.badges.length > 0 ||
    data.warnings.length > 0 ||
    data.scan_count > 1

  if (!hasContent) return null

  return (
    <div className={`border border-border rounded-lg ${compact ? 'p-3' : 'p-4'} bg-muted/20 space-y-2`}>
      {/* 배지 */}
      {data.badges.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {data.badges.map((b, i) => (
            <span
              key={i}
              className="text-xs px-2 py-0.5 rounded-full bg-background border border-border font-medium"
            >
              {b.label}
            </span>
          ))}
        </div>
      )}

      {/* 경고 */}
      {data.warnings.length > 0 && (
        <div className="space-y-1">
          {data.warnings.map((w, i) => (
            <div
              key={i}
              className="flex items-start gap-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/40 rounded px-2 py-1.5"
            >
              <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {/* 기본 정보 */}
      {(data.domain || data.scan_count > 0) && (
        <div className="flex items-center gap-3 text-xs text-muted-foreground pt-1">
          {data.domain && (
            <span className="flex items-center gap-1">
              <Info className="h-3 w-3" />
              {data.domain}
            </span>
          )}
          {data.scan_count > 1 && (
            <span>재발견 {data.scan_count}회</span>
          )}
        </div>
      )}
    </div>
  )
}

import { cn } from '@/lib/utils'

interface SkeletonProps {
  className?: string
  style?: React.CSSProperties
}

// 기본 스켈레톤 박스
export function Skeleton({ className, style }: SkeletonProps) {
  return (
    <div
      className={cn(
        'animate-pulse rounded-md bg-muted',
        className
      )}
      style={style}
      aria-hidden="true"
    />
  )
}

// 텍스트 스켈레톤
export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn('space-y-2', className)} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className={cn(
            'h-4',
            i === lines - 1 ? 'w-3/4' : 'w-full'
          )}
        />
      ))}
    </div>
  )
}

// 메트릭 카드 스켈레톤
export function SkeletonMetricCard() {
  return (
    <div className="bg-card rounded-lg border border-border p-6" aria-hidden="true">
      <div className="flex items-start justify-between">
        <div className="space-y-2 flex-1">
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-8 w-24" />
        </div>
        <Skeleton className="h-10 w-10 rounded-full" />
      </div>
    </div>
  )
}

// 브리핑 카드 스켈레톤
export function SkeletonBriefingCard() {
  return (
    <div className="bg-card rounded-lg border border-border p-6 space-y-4" aria-hidden="true">
      <Skeleton className="h-6 w-32" />
      <div className="bg-muted/50 rounded-lg p-4 space-y-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-muted p-3 rounded space-y-2">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-6 w-12" />
        </div>
        <div className="bg-muted p-3 rounded space-y-2">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-6 w-12" />
        </div>
      </div>
      <div className="space-y-2">
        <Skeleton className="h-4 w-28" />
        {[1, 2, 3].map((i) => (
          <div key={i} className="p-2 bg-muted/50 rounded flex items-center justify-between">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-16" />
          </div>
        ))}
      </div>
    </div>
  )
}

// 알림 카드 스켈레톤
export function SkeletonAlertCard() {
  return (
    <div className="bg-card rounded-lg border border-border p-6 space-y-4" aria-hidden="true">
      <Skeleton className="h-6 w-36" />
      <div className="bg-muted/50 rounded-lg p-4 text-center space-y-2">
        <Skeleton className="h-8 w-8 rounded-full mx-auto" />
        <Skeleton className="h-4 w-32 mx-auto" />
      </div>
    </div>
  )
}

// 테이블 행 스켈레톤
export function SkeletonTableRow({ columns = 5 }: { columns?: number }) {
  return (
    <tr aria-hidden="true">
      {Array.from({ length: columns }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <Skeleton className="h-4 w-full" />
        </td>
      ))}
    </tr>
  )
}

// 테이블 스켈레톤
export function SkeletonTable({ rows = 5, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div className="overflow-x-auto" aria-hidden="true">
      <table className="w-full">
        <thead className="bg-muted border-b border-border">
          <tr>
            {Array.from({ length: columns }).map((_, i) => (
              <th key={i} className="px-4 py-3 text-left">
                <Skeleton className="h-4 w-20" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {Array.from({ length: rows }).map((_, i) => (
            <SkeletonTableRow key={i} columns={columns} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

// 리스트 아이템 스켈레톤
export function SkeletonListItem() {
  return (
    <div className="p-4 rounded-lg border border-border space-y-2" aria-hidden="true">
      <div className="flex items-center justify-between">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-5 w-16 rounded-full" />
      </div>
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  )
}

// 리스트 스켈레톤
export function SkeletonList({ items = 3 }: { items?: number }) {
  return (
    <div className="space-y-4" aria-hidden="true">
      {Array.from({ length: items }).map((_, i) => (
        <SkeletonListItem key={i} />
      ))}
    </div>
  )
}

// 통계 카드 그리드 스켈레톤
export function SkeletonStatsGrid({ cards = 4 }: { cards?: number }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4" aria-hidden="true">
      {Array.from({ length: cards }).map((_, i) => (
        <SkeletonMetricCard key={i} />
      ))}
    </div>
  )
}

// 차트 스켈레톤
export function SkeletonChart({ height = 'h-64' }: { height?: string }) {
  return (
    <div className={cn('bg-card rounded-lg border border-border p-6', height)} aria-hidden="true">
      <div className="flex items-center justify-between mb-4">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-8 w-24" />
      </div>
      <div className="flex items-end justify-between h-3/4 gap-2">
        {Array.from({ length: 12 }).map((_, i) => (
          <Skeleton
            key={i}
            className="flex-1"
            style={{ height: `${Math.random() * 60 + 20}%` }}
          />
        ))}
      </div>
    </div>
  )
}

// 활동 로그 스켈레톤
export function SkeletonActivityLog({ items = 5 }: { items?: number }) {
  return (
    <div className="space-y-3" aria-hidden="true">
      {Array.from({ length: items }).map((_, i) => (
        <div key={i} className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Skeleton className="h-5 w-5 rounded" />
            <Skeleton className="h-4 w-32" />
          </div>
          <Skeleton className="h-3 w-16" />
        </div>
      ))}
    </div>
  )
}

// 타임라인 스켈레톤
export function SkeletonTimeline({ items = 6 }: { items?: number }) {
  return (
    <div className="space-y-4" aria-hidden="true">
      {Array.from({ length: items }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 p-3 rounded-lg border border-border">
          <Skeleton className="h-10 w-10 rounded-full flex-shrink-0" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-3 w-40" />
          </div>
          <Skeleton className="h-8 w-20 rounded" />
        </div>
      ))}
    </div>
  )
}

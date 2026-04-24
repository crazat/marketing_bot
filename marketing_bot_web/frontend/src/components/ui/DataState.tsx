import type { ReactNode } from 'react'
import { Loader2, Search, Inbox, AlertTriangle, Filter } from 'lucide-react'

type StateKind = 'loading' | 'empty' | 'filtered-empty' | 'error'

interface DataStateProps {
  kind: StateKind
  /** 커스텀 제목 — 미제공 시 기본값 */
  title?: string
  /** 설명 */
  description?: string
  /** 액션 버튼 라벨 + 핸들러 */
  actionLabel?: string
  onAction?: () => void
  /** 에러 객체 (kind=error일 때) */
  error?: Error | null
  /** 추가 하단 영역 */
  children?: ReactNode
}

const DEFAULTS: Record<
  StateKind,
  { Icon: typeof Loader2; title: string; description: string; tone: string }
> = {
  loading: {
    Icon: Loader2,
    title: '불러오는 중',
    description: '잠시만 기다려 주세요.',
    tone: 'text-muted-foreground',
  },
  empty: {
    Icon: Inbox,
    title: '아직 데이터가 없습니다',
    description: '스캔을 실행해 정보를 수집해 보세요.',
    tone: 'text-muted-foreground',
  },
  'filtered-empty': {
    Icon: Filter,
    title: '조건에 맞는 결과가 없습니다',
    description: '필터를 조정하거나 초기화해 보세요.',
    tone: 'text-amber-600 dark:text-amber-400',
  },
  error: {
    Icon: AlertTriangle,
    title: '데이터를 불러오지 못했습니다',
    description: '네트워크 연결을 확인하고 다시 시도해 주세요.',
    tone: 'text-red-600 dark:text-red-400',
  },
}

/**
 * [AA6] 데이터 상태 UI — loading / empty / filtered-empty / error 4가지
 *
 * 각각 아이콘·문구·권장 액션이 달라 사용자가 상태를 혼동하지 않도록.
 */
export default function DataState({
  kind,
  title,
  description,
  actionLabel,
  onAction,
  error,
  children,
}: DataStateProps) {
  const d = DEFAULTS[kind]
  const Icon = d.Icon
  const isLoading = kind === 'loading'
  const finalDescription = description ?? (kind === 'error' && error?.message ? error.message : d.description)

  return (
    <div
      role={kind === 'error' ? 'alert' : 'status'}
      aria-live={kind === 'loading' ? 'polite' : 'off'}
      aria-busy={isLoading}
      className="bg-card border border-border p-8 md:p-10 text-center flex flex-col items-center gap-3"
    >
      <div className={`${d.tone} ${isLoading ? 'animate-pulse' : ''}`}>
        <Icon className={`w-10 h-10 ${isLoading ? 'animate-spin' : ''}`} aria-hidden />
      </div>
      <div className="caps text-muted-foreground">
        {kind === 'loading' && 'Loading'}
        {kind === 'empty' && 'Empty'}
        {kind === 'filtered-empty' && 'No match'}
        {kind === 'error' && 'Error'}
      </div>
      <h3 className="font-display text-lg md:text-xl leading-tight">
        {title ?? d.title}
      </h3>
      <p className="text-sm text-muted-foreground max-w-md">{finalDescription}</p>
      {actionLabel && onAction && !isLoading && (
        <button
          onClick={onAction}
          className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          {kind === 'filtered-empty' && <Search className="w-3.5 h-3.5" aria-hidden />}
          {actionLabel}
        </button>
      )}
      {children}
    </div>
  )
}

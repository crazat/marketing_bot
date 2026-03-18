/**
 * EmptyState 컴포넌트
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] EmptyState 개선
 * - 상황별 분류 (initial, no-results, filtered, error)
 * - 다양한 액션 지원
 * - 팁/제안 표시
 */

import { ReactNode } from 'react'
import Button from '@/components/ui/Button'

// 빈 상태 타입
export type EmptyStateType = 'initial' | 'no-results' | 'filtered' | 'error' | 'custom'

// 액션 타입
interface EmptyStateAction {
  label: string
  onClick: () => void
  variant?: 'primary' | 'secondary' | 'ghost'
  disabled?: boolean
  icon?: ReactNode
}

interface EmptyStateProps {
  /** 빈 상태 타입 (기본 스타일 적용) */
  type?: EmptyStateType
  /** 아이콘 - emoji 문자열 또는 Lucide 아이콘 컴포넌트 */
  icon?: ReactNode
  /** 제목 */
  title: string
  /** 설명 (선택) */
  description?: string
  /** 액션 버튼들 (최대 3개 권장) */
  actions?: EmptyStateAction[]
  /** 주요 액션 버튼 (legacy 지원) */
  action?: {
    label: string
    onClick: () => void
    disabled?: boolean
  }
  /** 보조 액션 버튼 (legacy 지원) */
  secondaryAction?: {
    label: string
    onClick: () => void
  }
  /** 추가 콘텐츠 */
  children?: ReactNode
  /** 컴팩트 모드 - 패딩 축소 */
  compact?: boolean
  /** 팁/제안 메시지 */
  suggestion?: string
  /** 추가 클래스 */
  className?: string
}

// 타입별 기본 설정
const typeDefaults: Record<EmptyStateType, { icon: string; title: string; description: string }> = {
  initial: {
    icon: '🚀',
    title: '시작해보세요',
    description: '첫 번째 항목을 추가하여 시작하세요.',
  },
  'no-results': {
    icon: '🔍',
    title: '검색 결과가 없습니다',
    description: '다른 검색어로 시도해보세요.',
  },
  filtered: {
    icon: '🔎',
    title: '필터 결과가 없습니다',
    description: '현재 필터 조건에 맞는 항목이 없습니다.',
  },
  error: {
    icon: '⚠️',
    title: '오류가 발생했습니다',
    description: '데이터를 불러오는 중 문제가 발생했습니다.',
  },
  custom: {
    icon: '📭',
    title: '데이터가 없습니다',
    description: '',
  },
}

export default function EmptyState({
  type = 'custom',
  icon,
  title,
  description,
  actions,
  action,
  secondaryAction,
  children,
  compact = false,
  suggestion,
  className = '',
}: EmptyStateProps) {
  const defaults = typeDefaults[type]

  // 실제 표시할 값 결정
  const displayIcon = icon ?? defaults.icon
  const displayTitle = title || defaults.title
  const displayDescription = description ?? defaults.description

  // 아이콘이 문자열(emoji)인지 ReactNode인지 판단
  const isEmojiIcon = typeof displayIcon === 'string'

  // actions 배열이 없으면 legacy props에서 생성
  const allActions: EmptyStateAction[] = actions ?? [
    ...(action ? [{ ...action, variant: 'primary' as const }] : []),
    ...(secondaryAction ? [{ ...secondaryAction, variant: 'secondary' as const }] : []),
  ]

  // variant 매핑 (legacy props 호환)
  const variantMap: Record<'primary' | 'secondary' | 'ghost', 'primary' | 'outline' | 'ghost'> = {
    primary: 'primary',
    secondary: 'outline',
    ghost: 'ghost',
  }

  return (
    <div
      className={`flex flex-col items-center justify-center text-center ${compact ? 'py-6' : 'py-12'} ${className}`}
      role="status"
      aria-label={displayTitle}
    >
      {/* 아이콘 */}
      <div className={`mb-4 ${isEmojiIcon ? 'text-5xl md:text-6xl' : 'text-muted-foreground'}`}>
        {isEmojiIcon ? (
          <span role="img" aria-hidden="true">{displayIcon}</span>
        ) : (
          displayIcon
        )}
      </div>

      {/* 제목 */}
      <h3 className="text-lg md:text-xl font-semibold mb-2">{displayTitle}</h3>

      {/* 설명 */}
      {displayDescription && (
        <p className="text-sm md:text-base text-muted-foreground mb-4 max-w-md px-4">
          {displayDescription}
        </p>
      )}

      {/* 팁/제안 */}
      {suggestion && (
        <div className="mb-4 px-4 py-2 bg-muted/50 rounded-lg text-sm text-muted-foreground max-w-md">
          <span aria-hidden="true">💡 </span>
          {suggestion}
        </div>
      )}

      {/* 액션 버튼들 */}
      {allActions.length > 0 && (
        <div className="flex flex-wrap items-center justify-center gap-2 mt-2">
          {allActions.map((actionItem, idx) => (
            <Button
              key={idx}
              onClick={actionItem.onClick}
              disabled={actionItem.disabled}
              variant={variantMap[actionItem.variant || (idx === 0 ? 'primary' : 'secondary')]}
              icon={actionItem.icon}
            >
              {actionItem.label}
            </Button>
          ))}
        </div>
      )}

      {/* 추가 콘텐츠 */}
      {children}
    </div>
  )
}

/**
 * 검색 결과 없음 전용 컴포넌트
 */
export function NoSearchResults({
  query,
  onClearSearch,
  suggestions,
}: {
  query: string
  onClearSearch?: () => void
  suggestions?: string[]
}) {
  return (
    <EmptyState
      type="no-results"
      title={`"${query}"에 대한 결과가 없습니다`}
      description="검색어를 확인하거나 다른 키워드로 시도해보세요."
      actions={onClearSearch ? [{ label: '검색어 지우기', onClick: onClearSearch }] : []}
      suggestion={suggestions?.length ? `다음 검색어를 시도해보세요: ${suggestions.join(', ')}` : undefined}
    />
  )
}

/**
 * 필터 결과 없음 전용 컴포넌트
 */
export function NoFilterResults({
  onClearFilters,
  filterCount,
}: {
  onClearFilters: () => void
  filterCount?: number
}) {
  return (
    <EmptyState
      type="filtered"
      title="필터 조건에 맞는 항목이 없습니다"
      description={filterCount ? `${filterCount}개의 필터가 적용되어 있습니다.` : '필터 조건을 변경해보세요.'}
      actions={[
        { label: '필터 초기화', onClick: onClearFilters, variant: 'primary' },
      ]}
    />
  )
}

/**
 * 첫 시작 전용 컴포넌트
 */
export function FirstTimeState({
  itemName,
  onStart,
  description,
}: {
  itemName: string
  onStart: () => void
  description?: string
}) {
  return (
    <EmptyState
      type="initial"
      title={`첫 ${itemName}을(를) 추가해보세요`}
      description={description || `아직 ${itemName}이(가) 없습니다. 시작하려면 아래 버튼을 클릭하세요.`}
      actions={[
        { label: `${itemName} 추가`, onClick: onStart, variant: 'primary', icon: '➕' },
      ]}
    />
  )
}

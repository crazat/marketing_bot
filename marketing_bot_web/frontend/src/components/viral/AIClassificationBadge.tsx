/**
 * AI 분류 배지 — 자연_질문 / 광고 / 광고성_후기톤 / 기타_노이즈 + 신뢰도 + specialty_match
 *
 * 직원이 한눈에 "이 글이 진짜 작업할 가치가 있는지" 판단할 수 있도록.
 */

interface Props {
  label?: string | null
  confidence?: number | null
  specialtyMatch?: string | null  // 'high' | 'medium' | 'low'
  reason?: string | null
  size?: 'xs' | 'sm' | 'md'
}

const LABEL_INFO: Record<string, { icon: string; bg: string; label: string }> = {
  '자연_질문': {
    icon: '✓',
    bg: 'bg-green-100 text-green-700 border-green-300 dark:bg-green-900/30 dark:text-green-400 dark:border-green-700',
    label: '자연 질문',
  },
  '광고': {
    icon: '⚠',
    bg: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-900/30 dark:text-red-400 dark:border-red-700',
    label: '광고',
  },
  '광고성_후기톤': {
    icon: '?',
    bg: 'bg-yellow-100 text-yellow-700 border-yellow-300 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-700',
    label: '광고 의심',
  },
  '기타_노이즈': {
    icon: '·',
    bg: 'bg-gray-100 text-gray-600 border-gray-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-600',
    label: '노이즈',
  },
}

const SPECIALTY_INFO: Record<string, { icon: string; bg: string; label: string }> = {
  high: {
    icon: '🎯',
    bg: 'bg-orange-100 text-orange-700 border-orange-300 dark:bg-orange-900/30 dark:text-orange-400 dark:border-orange-700',
    label: '특화 매칭',
  },
  medium: {
    icon: '○',
    bg: 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-900/20 dark:text-sky-400 dark:border-sky-800',
    label: '관련',
  },
  low: {
    icon: '·',
    bg: 'bg-gray-50 text-gray-500 border-gray-200 dark:bg-gray-900/30 dark:text-gray-500 dark:border-gray-700',
    label: '낮음',
  },
}

export function AIClassificationBadge({ label, confidence, specialtyMatch, reason, size = 'sm' }: Props) {
  if (!label && !specialtyMatch) return null

  const sizeClass =
    size === 'xs' ? 'text-[10px] px-1 py-0' : size === 'md' ? 'text-sm px-2 py-1' : 'text-xs px-1.5 py-0.5'

  const labelInfo = label ? LABEL_INFO[label] : null
  const specialtyInfo = specialtyMatch ? SPECIALTY_INFO[specialtyMatch] : null

  // 신뢰도 표시 (0.0 ~ 1.0 → 백분율)
  const confPct = confidence != null ? Math.round(confidence * 100) : null

  // 가장 강한 신호를 첫 배지로
  const tooltip = reason ? `사유: ${reason}` : undefined

  return (
    <span className="inline-flex items-center gap-1" title={tooltip}>
      {specialtyInfo && (
        <span
          className={`inline-flex items-center gap-0.5 rounded border font-medium ${sizeClass} ${specialtyInfo.bg}`}
          title="미용 특화 매칭"
        >
          <span>{specialtyInfo.icon}</span>
          <span>{specialtyInfo.label}</span>
        </span>
      )}
      {labelInfo && (
        <span
          className={`inline-flex items-center gap-0.5 rounded border font-medium ${sizeClass} ${labelInfo.bg}`}
          title={`AI: ${labelInfo.label}${confPct != null ? ` (${confPct}%)` : ''}${reason ? ` — ${reason}` : ''}`}
        >
          <span>{labelInfo.icon}</span>
          <span>{labelInfo.label}</span>
          {confPct != null && (
            <span className="opacity-70 ml-0.5">{confPct}%</span>
          )}
        </span>
      )}
    </span>
  )
}

/**
 * 미니 변형 — 테이블 셀 등 좁은 공간용.
 * specialty_match 우선, 없으면 label만.
 */
export function AIClassificationMini({ label, confidence, specialtyMatch }: Pick<Props, 'label' | 'confidence' | 'specialtyMatch'>) {
  if (specialtyMatch === 'high') {
    return (
      <span className="inline-flex items-center gap-0.5 rounded border border-orange-300 bg-orange-100 text-orange-700 px-1 py-0 text-[10px] font-medium dark:bg-orange-900/30 dark:text-orange-400 dark:border-orange-700">
        🎯 특화 {confidence != null ? `${Math.round(confidence * 100)}%` : ''}
      </span>
    )
  }
  if (specialtyMatch === 'medium') {
    return (
      <span className="inline-flex items-center gap-0.5 rounded border border-sky-200 bg-sky-50 text-sky-700 px-1 py-0 text-[10px] font-medium dark:bg-sky-900/20 dark:text-sky-400">
        관련
      </span>
    )
  }
  if (label === '자연_질문') {
    return (
      <span className="inline-flex items-center gap-0.5 rounded border border-green-300 bg-green-100 text-green-700 px-1 py-0 text-[10px] font-medium dark:bg-green-900/30 dark:text-green-400">
        ✓ 자연
      </span>
    )
  }
  return null
}

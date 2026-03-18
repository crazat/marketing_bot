/**
 * StatusBadge 컴포넌트
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] 접근성(a11y) 개선
 * - 색상 + 텍스트 라벨 함께 표시
 * - 스크린 리더 지원
 * - 다양한 상태 타입 지원
 */

// StatusBadge - 상태별 배지 컴포넌트

// 상태 타입
export type StatusType =
  | 'success' | 'error' | 'warning' | 'info' | 'pending' | 'processing'
  | 'hot' | 'warm' | 'cold' | 'dead'
  | 'scanned' | 'not_found' | 'rising' | 'falling' | 'stable'

// 배지 크기
export type BadgeSize = 'xs' | 'sm' | 'md' | 'lg'

interface StatusBadgeProps {
  /** 상태 타입 */
  status: StatusType | string
  /** 커스텀 라벨 (미지정 시 상태 이름 사용) */
  label?: string
  /** 아이콘 표시 */
  showIcon?: boolean
  /** 텍스트 라벨 표시 */
  showLabel?: boolean
  /** 배지 크기 */
  size?: BadgeSize
  /** 추가 클래스 */
  className?: string
}

// 상태별 설정
const statusConfig: Record<string, {
  label: string
  icon: string
  bgColor: string
  textColor: string
  borderColor: string
}> = {
  // 일반 상태
  success: { label: '성공', icon: '✅', bgColor: 'bg-green-500/20', textColor: 'text-green-600', borderColor: 'border-green-500/30' },
  error: { label: '오류', icon: '❌', bgColor: 'bg-red-500/20', textColor: 'text-red-600', borderColor: 'border-red-500/30' },
  warning: { label: '경고', icon: '⚠️', bgColor: 'bg-yellow-500/20', textColor: 'text-yellow-600', borderColor: 'border-yellow-500/30' },
  info: { label: '정보', icon: 'ℹ️', bgColor: 'bg-blue-500/20', textColor: 'text-blue-600', borderColor: 'border-blue-500/30' },
  pending: { label: '대기', icon: '⏳', bgColor: 'bg-gray-500/20', textColor: 'text-gray-600', borderColor: 'border-gray-500/30' },
  processing: { label: '처리중', icon: '🔄', bgColor: 'bg-blue-500/20', textColor: 'text-blue-600', borderColor: 'border-blue-500/30' },

  // 리드 상태
  hot: { label: 'Hot', icon: '🔴', bgColor: 'bg-red-500/20', textColor: 'text-red-600', borderColor: 'border-red-500/30' },
  warm: { label: 'Warm', icon: '🟡', bgColor: 'bg-yellow-500/20', textColor: 'text-yellow-600', borderColor: 'border-yellow-500/30' },
  cold: { label: 'Cold', icon: '🔵', bgColor: 'bg-blue-500/20', textColor: 'text-blue-600', borderColor: 'border-blue-500/30' },
  dead: { label: 'Dead', icon: '⚪', bgColor: 'bg-gray-500/20', textColor: 'text-gray-600', borderColor: 'border-gray-500/30' },

  // 순위 상태
  scanned: { label: '확인됨', icon: '✅', bgColor: 'bg-green-500/20', textColor: 'text-green-600', borderColor: 'border-green-500/30' },
  not_found: { label: '순위권 밖', icon: '🔍', bgColor: 'bg-orange-500/20', textColor: 'text-orange-600', borderColor: 'border-orange-500/30' },
  not_in_results: { label: '순위권 밖', icon: '🔍', bgColor: 'bg-orange-500/20', textColor: 'text-orange-600', borderColor: 'border-orange-500/30' },
  found: { label: '발견', icon: '✅', bgColor: 'bg-green-500/20', textColor: 'text-green-600', borderColor: 'border-green-500/30' },
  no_results: { label: '결과없음', icon: '❓', bgColor: 'bg-gray-500/20', textColor: 'text-gray-600', borderColor: 'border-gray-500/30' },

  // 트렌드 상태
  rising: { label: '상승', icon: '📈', bgColor: 'bg-green-500/20', textColor: 'text-green-600', borderColor: 'border-green-500/30' },
  falling: { label: '하락', icon: '📉', bgColor: 'bg-red-500/20', textColor: 'text-red-600', borderColor: 'border-red-500/30' },
  stable: { label: '안정', icon: '➡️', bgColor: 'bg-gray-500/20', textColor: 'text-gray-600', borderColor: 'border-gray-500/30' },

  // 바이럴 상태
  generated: { label: '생성됨', icon: '✨', bgColor: 'bg-blue-500/20', textColor: 'text-blue-600', borderColor: 'border-blue-500/30' },
  approved: { label: '승인됨', icon: '👍', bgColor: 'bg-green-500/20', textColor: 'text-green-600', borderColor: 'border-green-500/30' },
  posted: { label: '게시됨', icon: '📤', bgColor: 'bg-purple-500/20', textColor: 'text-purple-600', borderColor: 'border-purple-500/30' },
  skipped: { label: '건너뜀', icon: '⏭️', bgColor: 'bg-gray-500/20', textColor: 'text-gray-600', borderColor: 'border-gray-500/30' },
  failed: { label: '실패', icon: '❌', bgColor: 'bg-red-500/20', textColor: 'text-red-600', borderColor: 'border-red-500/30' },

  // 기타
  new: { label: '신규', icon: '🆕', bgColor: 'bg-purple-500/20', textColor: 'text-purple-600', borderColor: 'border-purple-500/30' },
  contacted: { label: '연락됨', icon: '📞', bgColor: 'bg-blue-500/20', textColor: 'text-blue-600', borderColor: 'border-blue-500/30' },
  converted: { label: '전환됨', icon: '🎉', bgColor: 'bg-green-500/20', textColor: 'text-green-600', borderColor: 'border-green-500/30' },
}

// 크기별 스타일
const sizeStyles: Record<BadgeSize, string> = {
  xs: 'px-1.5 py-0.5 text-[10px] gap-0.5',
  sm: 'px-2 py-0.5 text-xs gap-1',
  md: 'px-2.5 py-1 text-sm gap-1.5',
  lg: 'px-3 py-1.5 text-base gap-2',
}

// 기본 설정 (알 수 없는 상태용)
const defaultConfig = {
  label: '알 수 없음',
  icon: '❓',
  bgColor: 'bg-gray-500/20',
  textColor: 'text-gray-600',
  borderColor: 'border-gray-500/30',
}

export default function StatusBadge({
  status,
  label,
  showIcon = true,
  showLabel = true,
  size = 'sm',
  className = '',
}: StatusBadgeProps) {
  const config = statusConfig[status] || defaultConfig
  const displayLabel = label || config.label

  return (
    <span
      className={`
        inline-flex items-center font-medium rounded-full border
        ${config.bgColor} ${config.textColor} ${config.borderColor}
        ${sizeStyles[size]}
        ${className}
      `}
      role="status"
    >
      {showIcon && (
        <span aria-hidden="true">{config.icon}</span>
      )}
      {showLabel && (
        <span>{displayLabel}</span>
      )}
      {/* 스크린 리더용 전체 텍스트 */}
      {showIcon && !showLabel && (
        <span className="sr-only">{displayLabel}</span>
      )}
    </span>
  )
}

/**
 * 등급 배지 (S, A, B, C, D)
 */
export function GradeBadge({
  grade,
  size = 'sm',
  showLabel = false,
  className = '',
}: {
  grade: string
  size?: BadgeSize
  showLabel?: boolean
  className?: string
}) {
  const gradeConfig: Record<string, { bgColor: string; textColor: string; label: string }> = {
    S: { bgColor: 'bg-red-500', textColor: 'text-white', label: 'S등급 (최고)' },
    A: { bgColor: 'bg-orange-500', textColor: 'text-white', label: 'A등급 (우수)' },
    B: { bgColor: 'bg-blue-500', textColor: 'text-white', label: 'B등급 (양호)' },
    C: { bgColor: 'bg-gray-500', textColor: 'text-white', label: 'C등급 (보통)' },
    D: { bgColor: 'bg-gray-400', textColor: 'text-white', label: 'D등급 (낮음)' },
  }

  const config = gradeConfig[grade.toUpperCase()] || gradeConfig.C

  return (
    <span
      className={`
        inline-flex items-center justify-center font-bold rounded
        ${config.bgColor} ${config.textColor}
        ${size === 'xs' ? 'w-4 h-4 text-[10px]' : ''}
        ${size === 'sm' ? 'w-5 h-5 text-xs' : ''}
        ${size === 'md' ? 'w-6 h-6 text-sm' : ''}
        ${size === 'lg' ? 'w-8 h-8 text-base' : ''}
        ${className}
      `}
      role="status"
      aria-label={config.label}
    >
      {grade.toUpperCase()}
      {showLabel && <span className="ml-1 font-normal">등급</span>}
    </span>
  )
}

/**
 * 신뢰도 배지
 */
export function TrustBadge({
  score,
  size = 'sm',
  className = '',
}: {
  score: number
  size?: BadgeSize
  className?: string
}) {
  const getConfig = (score: number) => {
    if (score >= 80) return { label: '높음', bgColor: 'bg-green-500/20', textColor: 'text-green-600' }
    if (score >= 60) return { label: '중간', bgColor: 'bg-yellow-500/20', textColor: 'text-yellow-600' }
    if (score >= 40) return { label: '낮음', bgColor: 'bg-orange-500/20', textColor: 'text-orange-600' }
    return { label: '매우 낮음', bgColor: 'bg-red-500/20', textColor: 'text-red-600' }
  }

  const config = getConfig(score)

  return (
    <span
      className={`
        inline-flex items-center font-medium rounded-full
        ${config.bgColor} ${config.textColor}
        ${sizeStyles[size]}
        ${className}
      `}
      role="status"
      aria-label={`신뢰도 ${score}점 (${config.label})`}
    >
      <span aria-hidden="true">🛡️</span>
      <span>{score}</span>
      <span className="sr-only">점 ({config.label})</span>
    </span>
  )
}

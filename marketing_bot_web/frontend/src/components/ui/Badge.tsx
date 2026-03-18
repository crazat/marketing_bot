import { type HTMLAttributes } from 'react'

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'primary' | 'secondary' | 'success' | 'warning' | 'danger' | 'outline'
  size?: 'sm' | 'md' | 'lg'
  dot?: boolean
  removable?: boolean
  onRemove?: () => void
}

export default function Badge({
  variant = 'default',
  size = 'md',
  dot = false,
  removable = false,
  onRemove,
  className = '',
  children,
  ...props
}: BadgeProps) {
  const baseStyles = `
    inline-flex items-center font-medium rounded-full
    transition-colors duration-200
  `

  const variantStyles = {
    default: 'bg-muted text-muted-foreground',
    primary: 'bg-primary/20 text-primary border border-primary/30',
    secondary: 'bg-secondary text-secondary-foreground',
    success: 'bg-green-500/20 text-green-500 border border-green-500/30',
    warning: 'bg-yellow-500/20 text-yellow-500 border border-yellow-500/30',
    danger: 'bg-red-500/20 text-red-500 border border-red-500/30',
    outline: 'border border-border text-foreground bg-transparent',
  }

  const sizeStyles = {
    sm: 'text-xs px-2 py-0.5 gap-1',
    md: 'text-xs px-2.5 py-1 gap-1.5',
    lg: 'text-sm px-3 py-1.5 gap-2',
  }

  const dotSizeStyles = {
    sm: 'w-1.5 h-1.5',
    md: 'w-2 h-2',
    lg: 'w-2.5 h-2.5',
  }

  const dotColors = {
    default: 'bg-muted-foreground',
    primary: 'bg-primary',
    secondary: 'bg-secondary-foreground',
    success: 'bg-green-500',
    warning: 'bg-yellow-500',
    danger: 'bg-red-500',
    outline: 'bg-foreground',
  }

  return (
    <span
      className={`
        ${baseStyles}
        ${variantStyles[variant]}
        ${sizeStyles[size]}
        ${className}
      `}
      {...props}
    >
      {dot && (
        <span
          className={`rounded-full ${dotSizeStyles[size]} ${dotColors[variant]}`}
          aria-hidden="true"
        />
      )}
      {children}
      {removable && onRemove && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}
          className="ml-1 hover:bg-black/10 rounded-full p-0.5 transition-colors"
          aria-label="제거"
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </span>
  )
}

/**
 * 상태 뱃지 (온라인/오프라인 등)
 */
export function StatusBadge({
  status,
  label,
  showDot = true,
}: {
  status: 'online' | 'offline' | 'busy' | 'away'
  label?: string
  showDot?: boolean
}) {
  const statusConfig = {
    online: { color: 'bg-green-500', text: '온라인', variant: 'success' as const },
    offline: { color: 'bg-gray-500', text: '오프라인', variant: 'default' as const },
    busy: { color: 'bg-red-500', text: '바쁨', variant: 'danger' as const },
    away: { color: 'bg-yellow-500', text: '자리비움', variant: 'warning' as const },
  }

  const config = statusConfig[status]

  return (
    <Badge variant={config.variant} dot={showDot} size="sm">
      {label || config.text}
    </Badge>
  )
}

/**
 * 카운트 뱃지 (알림 수 등)
 */
export function CountBadge({
  count,
  max = 99,
  variant = 'danger',
  className = '',
}: {
  count: number
  max?: number
  variant?: BadgeProps['variant']
  className?: string
}) {
  if (count <= 0) return null

  const displayCount = count > max ? `${max}+` : count.toString()

  return (
    <Badge
      variant={variant}
      size="sm"
      className={`min-w-5 justify-center ${className}`}
    >
      {displayCount}
    </Badge>
  )
}

/**
 * 등급 뱃지 (S/A/B/C)
 */
export function GradeBadge({
  grade,
  size = 'md',
}: {
  grade: 'S' | 'A' | 'B' | 'C' | string
  size?: BadgeProps['size']
}) {
  const gradeConfig: Record<string, { variant: BadgeProps['variant']; icon: string }> = {
    S: { variant: 'danger', icon: '🔥' },
    A: { variant: 'success', icon: '🟢' },
    B: { variant: 'primary', icon: '🔵' },
    C: { variant: 'default', icon: '⚪' },
  }

  const config = gradeConfig[grade] || gradeConfig.C

  return (
    <Badge variant={config.variant} size={size}>
      <span>{config.icon}</span>
      <span>{grade}급</span>
    </Badge>
  )
}

/**
 * 트렌드 뱃지 (상승/하락/안정)
 */
export function TrendBadge({
  trend,
  size = 'sm',
}: {
  trend: 'up' | 'down' | 'stable' | 'rising' | 'falling'
  size?: BadgeProps['size']
}) {
  const trendConfig = {
    up: { variant: 'success' as const, icon: '↑', label: '상승' },
    rising: { variant: 'success' as const, icon: '📈', label: '상승' },
    down: { variant: 'danger' as const, icon: '↓', label: '하락' },
    falling: { variant: 'danger' as const, icon: '📉', label: '하락' },
    stable: { variant: 'default' as const, icon: '→', label: '안정' },
  }

  const config = trendConfig[trend]

  return (
    <Badge variant={config.variant} size={size}>
      <span>{config.icon}</span>
      <span>{config.label}</span>
    </Badge>
  )
}

/**
 * 플랫폼 뱃지
 */
export function PlatformBadge({
  platform,
  size = 'sm',
}: {
  platform: string
  size?: BadgeProps['size']
}) {
  const platformConfig: Record<string, { icon: string; color: string }> = {
    cafe: { icon: '🏠', color: 'bg-green-500/20 text-green-500' },
    youtube: { icon: '📺', color: 'bg-red-500/20 text-red-500' },
    instagram: { icon: '📸', color: 'bg-pink-500/20 text-pink-500' },
    tiktok: { icon: '🎵', color: 'bg-purple-500/20 text-purple-500' },
    carrot: { icon: '🥕', color: 'bg-orange-500/20 text-orange-500' },
    influencer: { icon: '🤝', color: 'bg-blue-500/20 text-blue-500' },
  }

  const config = platformConfig[platform.toLowerCase()] || { icon: '📱', color: 'bg-muted text-muted-foreground' }

  const sizeStyles = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-xs px-2.5 py-1',
    lg: 'text-sm px-3 py-1.5',
  }

  return (
    <span className={`inline-flex items-center gap-1 rounded-full font-medium ${config.color} ${sizeStyles[size]}`}>
      <span>{config.icon}</span>
      <span>{platform}</span>
    </span>
  )
}

import { forwardRef, type HTMLAttributes } from 'react'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'elevated' | 'outlined' | 'ghost'
  interactive?: boolean
  selected?: boolean
  status?: 'default' | 'success' | 'warning' | 'error' | 'info'
  padding?: 'none' | 'sm' | 'md' | 'lg'
}

const Card = forwardRef<HTMLDivElement, CardProps>(
  (
    {
      variant = 'default',
      interactive = false,
      selected = false,
      status = 'default',
      padding = 'md',
      className = '',
      children,
      ...props
    },
    ref
  ) => {
    const baseStyles = `
      rounded-lg transition-all duration-200 ease-out
    `

    const variantStyles = {
      default: 'bg-card border border-border',
      elevated: 'bg-card border border-border shadow-lg',
      outlined: 'bg-transparent border-2 border-border',
      ghost: 'bg-transparent',
    }

    const interactiveStyles = interactive
      ? `
          cursor-pointer
          hover:border-primary/50 hover:shadow-md hover:-translate-y-0.5
          active:translate-y-0 active:shadow-sm
        `
      : ''

    const selectedStyles = selected
      ? 'border-primary bg-primary/5 ring-2 ring-primary/20'
      : ''

    const statusStyles = {
      default: '',
      success: 'border-l-4 border-l-green-500',
      warning: 'border-l-4 border-l-yellow-500',
      error: 'border-l-4 border-l-red-500',
      info: 'border-l-4 border-l-blue-500',
    }

    const paddingStyles = {
      none: '',
      sm: 'p-3',
      md: 'p-4',
      lg: 'p-6',
    }

    return (
      <div
        ref={ref}
        className={`
          ${baseStyles}
          ${variantStyles[variant]}
          ${interactiveStyles}
          ${selectedStyles}
          ${statusStyles[status]}
          ${paddingStyles[padding]}
          ${className}
        `}
        {...props}
      >
        {children}
      </div>
    )
  }
)

Card.displayName = 'Card'

export default Card

/**
 * 카드 헤더
 */
export function CardHeader({
  title,
  subtitle,
  action,
  icon,
  className = '',
}: {
  title: string
  subtitle?: string
  action?: React.ReactNode
  icon?: React.ReactNode
  className?: string
}) {
  return (
    <div className={`flex items-start justify-between gap-4 ${className}`}>
      <div className="flex items-start gap-3">
        {icon && (
          <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
            {icon}
          </div>
        )}
        <div>
          <h3 className="font-semibold text-foreground">{title}</h3>
          {subtitle && (
            <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>
          )}
        </div>
      </div>
      {action && <div className="flex-shrink-0">{action}</div>}
    </div>
  )
}

/**
 * 카드 콘텐츠
 */
export function CardContent({
  children,
  className = '',
}: {
  children: React.ReactNode
  className?: string
}) {
  return <div className={`mt-4 ${className}`}>{children}</div>
}

/**
 * 카드 푸터
 */
export function CardFooter({
  children,
  className = '',
  bordered = false,
}: {
  children: React.ReactNode
  className?: string
  bordered?: boolean
}) {
  return (
    <div
      className={`
        mt-4 flex items-center justify-end gap-2
        ${bordered ? 'pt-4 border-t border-border' : ''}
        ${className}
      `}
    >
      {children}
    </div>
  )
}

/**
 * 메트릭 카드 (대시보드용)
 */
export function MetricCard({
  title,
  value,
  change,
  changeType = 'neutral',
  icon,
  trend,
  className = '',
}: {
  title: string
  value: string | number
  change?: string | number
  changeType?: 'positive' | 'negative' | 'neutral'
  icon?: React.ReactNode
  trend?: 'up' | 'down' | 'stable'
  className?: string
}) {
  const changeColors = {
    positive: 'text-green-500',
    negative: 'text-red-500',
    neutral: 'text-muted-foreground',
  }

  const trendIcons = {
    up: '↑',
    down: '↓',
    stable: '→',
  }

  return (
    <Card
      className={`group hover:border-primary/30 transition-all duration-300 ${className}`}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className="text-2xl font-bold mt-1 group-hover:text-primary transition-colors">
            {value}
          </p>
          {change !== undefined && (
            <p className={`text-xs mt-1 flex items-center gap-1 ${changeColors[changeType]}`}>
              {trend && <span>{trendIcons[trend]}</span>}
              <span>{change}</span>
            </p>
          )}
        </div>
        {icon && (
          <div className="w-10 h-10 rounded-lg bg-muted flex items-center justify-center text-xl group-hover:bg-primary/10 group-hover:scale-110 transition-all">
            {icon}
          </div>
        )}
      </div>
    </Card>
  )
}

/**
 * 스탯 카드 그리드
 */
export function StatsGrid({
  children,
  columns = 4,
  className = '',
}: {
  children: React.ReactNode
  columns?: 2 | 3 | 4 | 5
  className?: string
}) {
  const colClasses = {
    2: 'grid-cols-1 sm:grid-cols-2',
    3: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
    4: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4',
    5: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-5',
  }

  return (
    <div className={`grid gap-4 ${colClasses[columns]} ${className}`}>
      {children}
    </div>
  )
}

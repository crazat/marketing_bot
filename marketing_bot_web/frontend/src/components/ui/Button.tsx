import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { Check, X } from 'lucide-react'

export type ButtonStatus = 'idle' | 'loading' | 'success' | 'error'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger' | 'success'
  size?: 'xs' | 'sm' | 'md' | 'lg'
  loading?: boolean
  /** 버튼 상태 (idle, loading, success, error) */
  status?: ButtonStatus
  /** 성공 시 표시할 텍스트 */
  successText?: string
  /** 에러 시 표시할 텍스트 */
  errorText?: string
  icon?: React.ReactNode
  iconPosition?: 'left' | 'right'
  fullWidth?: boolean
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'primary',
      size = 'md',
      loading = false,
      status = 'idle',
      successText = '완료!',
      errorText = '실패',
      icon,
      iconPosition = 'left',
      fullWidth = false,
      disabled,
      className = '',
      children,
      ...props
    },
    ref
  ) => {
    // loading prop이 true면 status를 loading으로 처리 (하위 호환성)
    const effectiveStatus: ButtonStatus = loading ? 'loading' : status

    const baseStyles = `
      inline-flex items-center justify-center font-medium
      rounded-lg transition-all duration-200 ease-out
      focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary
      disabled:opacity-50 disabled:cursor-not-allowed
      active:scale-[0.98]
    `

    const variantStyles = {
      primary: `
        bg-primary text-primary-foreground
        hover:bg-primary/90 hover:shadow-lg hover:shadow-primary/25
      `,
      secondary: `
        bg-secondary text-secondary-foreground
        hover:bg-secondary/80
      `,
      outline: `
        border-2 border-border bg-transparent text-foreground
        hover:bg-muted hover:border-primary/50
      `,
      ghost: `
        bg-transparent text-foreground
        hover:bg-muted
      `,
      danger: `
        bg-destructive text-destructive-foreground
        hover:bg-destructive/90 hover:shadow-lg hover:shadow-destructive/25
      `,
      success: `
        bg-green-600 text-white
        hover:bg-green-700 hover:shadow-lg hover:shadow-green-600/25
      `,
    }

    // 상태별 스타일 오버라이드
    const statusStyles = {
      idle: '',
      loading: '',
      success: 'bg-green-600 hover:bg-green-600 text-white',
      error: 'bg-red-500 hover:bg-red-500 text-white animate-shake',
    }

    const sizeStyles = {
      xs: 'text-xs px-2 py-1 gap-1',
      sm: 'text-sm px-3 py-1.5 gap-1.5',
      md: 'text-sm px-4 py-2 gap-2',
      lg: 'text-base px-6 py-3 gap-2',
    }

    const iconSizeStyles = {
      xs: 'w-3 h-3',
      sm: 'w-4 h-4',
      md: 'w-4 h-4',
      lg: 'w-5 h-5',
    }

    // 상태별 컨텐츠 렌더링
    const renderContent = () => {
      switch (effectiveStatus) {
        case 'loading':
          return (
            <>
              <LoadingSpinner className={iconSizeStyles[size]} />
              <span>처리 중...</span>
            </>
          )
        case 'success':
          return (
            <>
              <Check className={iconSizeStyles[size]} />
              <span>{successText}</span>
            </>
          )
        case 'error':
          return (
            <>
              <X className={iconSizeStyles[size]} />
              <span>{errorText}</span>
            </>
          )
        default:
          return (
            <>
              {icon && iconPosition === 'left' && (
                <span className={iconSizeStyles[size]}>{icon}</span>
              )}
              {children}
              {icon && iconPosition === 'right' && (
                <span className={iconSizeStyles[size]}>{icon}</span>
              )}
            </>
          )
      }
    }

    return (
      <button
        ref={ref}
        disabled={disabled || effectiveStatus === 'loading'}
        className={`
          ${baseStyles}
          ${effectiveStatus === 'idle' ? variantStyles[variant] : ''}
          ${statusStyles[effectiveStatus]}
          ${sizeStyles[size]}
          ${fullWidth ? 'w-full' : ''}
          ${className}
        `}
        {...props}
      >
        {renderContent()}
      </button>
    )
  }
)

Button.displayName = 'Button'

export default Button

function LoadingSpinner({ className = '' }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className}`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  )
}

/**
 * 아이콘 버튼 (정사각형)
 */
export function IconButton({
  icon,
  size = 'md',
  variant = 'ghost',
  className = '',
  ...props
}: Omit<ButtonProps, 'children'> & { icon: React.ReactNode }) {
  const sizeStyles = {
    xs: 'w-6 h-6',
    sm: 'w-8 h-8',
    md: 'w-10 h-10',
    lg: 'w-12 h-12',
  }

  return (
    <Button
      variant={variant}
      size={size}
      className={`${sizeStyles[size]} p-0 ${className}`}
      {...props}
    >
      {icon}
    </Button>
  )
}

/**
 * 버튼 그룹
 */
export function ButtonGroup({
  children,
  className = '',
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={`inline-flex rounded-lg overflow-hidden divide-x divide-border ${className}`}
      role="group"
    >
      {children}
    </div>
  )
}

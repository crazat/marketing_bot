import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from 'react'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
  icon?: React.ReactNode
  iconPosition?: 'left' | 'right'
  fullWidth?: boolean
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      error,
      hint,
      icon,
      iconPosition = 'left',
      fullWidth = true,
      className = '',
      id,
      ...props
    },
    ref
  ) => {
    const inputId = id || `input-${Math.random().toString(36).substr(2, 9)}`

    const baseInputStyles = `
      w-full px-3 py-2 text-sm
      bg-background border rounded-lg
      placeholder:text-muted-foreground
      transition-all duration-200
      focus:outline-none focus:ring-2 focus:ring-offset-0
    `

    const stateStyles = error
      ? 'border-destructive focus:ring-destructive/30 bg-destructive/5'
      : 'border-border focus:ring-primary/30 focus:border-primary'

    const disabledStyles = props.disabled
      ? 'bg-muted cursor-not-allowed opacity-60'
      : ''

    const iconPaddingStyles = icon
      ? iconPosition === 'left'
        ? 'pl-10'
        : 'pr-10'
      : ''

    return (
      <div className={`${fullWidth ? 'w-full' : ''} ${className}`}>
        {label && (
          <label
            htmlFor={inputId}
            className="block text-sm font-medium mb-1.5"
          >
            {label}
            {props.required && <span className="text-destructive ml-1">*</span>}
          </label>
        )}

        <div className="relative">
          {icon && (
            <div
              className={`
                absolute top-1/2 -translate-y-1/2 text-muted-foreground
                ${iconPosition === 'left' ? 'left-3' : 'right-3'}
              `}
            >
              {icon}
            </div>
          )}

          <input
            ref={ref}
            id={inputId}
            aria-invalid={error ? 'true' : 'false'}
            aria-describedby={
              error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined
            }
            className={`
              ${baseInputStyles}
              ${stateStyles}
              ${disabledStyles}
              ${iconPaddingStyles}
            `}
            {...props}
          />
        </div>

        {error && (
          <p
            id={`${inputId}-error`}
            className="mt-1.5 text-sm text-destructive flex items-center gap-1"
            role="alert"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            {error}
          </p>
        )}

        {hint && !error && (
          <p
            id={`${inputId}-hint`}
            className="mt-1.5 text-xs text-muted-foreground"
          >
            {hint}
          </p>
        )}
      </div>
    )
  }
)

Input.displayName = 'Input'

export default Input

/**
 * 텍스트에어리어 컴포넌트
 */
export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  error?: string
  hint?: string
  fullWidth?: boolean
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  (
    {
      label,
      error,
      hint,
      fullWidth = true,
      className = '',
      id,
      ...props
    },
    ref
  ) => {
    const textareaId = id || `textarea-${Math.random().toString(36).substr(2, 9)}`

    const baseStyles = `
      w-full px-3 py-2 text-sm
      bg-background border rounded-lg
      placeholder:text-muted-foreground
      transition-all duration-200
      focus:outline-none focus:ring-2 focus:ring-offset-0
      resize-none
    `

    const stateStyles = error
      ? 'border-destructive focus:ring-destructive/30 bg-destructive/5'
      : 'border-border focus:ring-primary/30 focus:border-primary'

    const disabledStyles = props.disabled
      ? 'bg-muted cursor-not-allowed opacity-60'
      : ''

    return (
      <div className={`${fullWidth ? 'w-full' : ''} ${className}`}>
        {label && (
          <label
            htmlFor={textareaId}
            className="block text-sm font-medium mb-1.5"
          >
            {label}
            {props.required && <span className="text-destructive ml-1">*</span>}
          </label>
        )}

        <textarea
          ref={ref}
          id={textareaId}
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={
            error ? `${textareaId}-error` : hint ? `${textareaId}-hint` : undefined
          }
          className={`${baseStyles} ${stateStyles} ${disabledStyles}`}
          {...props}
        />

        {error && (
          <p
            id={`${textareaId}-error`}
            className="mt-1.5 text-sm text-destructive flex items-center gap-1"
            role="alert"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            {error}
          </p>
        )}

        {hint && !error && (
          <p
            id={`${textareaId}-hint`}
            className="mt-1.5 text-xs text-muted-foreground"
          >
            {hint}
          </p>
        )}
      </div>
    )
  }
)

Textarea.displayName = 'Textarea'

/**
 * 검색 입력 컴포넌트
 */
export function SearchInput({
  value,
  onChange,
  onClear,
  placeholder = '검색...',
  className = '',
  ...props
}: Omit<InputProps, 'icon' | 'iconPosition'> & {
  onClear?: () => void
}) {
  return (
    <div className={`relative ${className}`}>
      <Input
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        icon={
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        }
        iconPosition="left"
        {...props}
      />
      {value && onClear && (
        <button
          type="button"
          onClick={onClear}
          className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-muted focus:outline-none focus:ring-2 focus:ring-primary transition-colors text-muted-foreground hover:text-foreground"
          aria-label="검색어 지우기"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  )
}

/**
 * 셀렉트 컴포넌트
 */
export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  hint?: string
  options: Array<{ value: string; label: string; disabled?: boolean }>
  placeholder?: string
  fullWidth?: boolean
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  (
    {
      label,
      error,
      hint,
      options,
      placeholder,
      fullWidth = true,
      className = '',
      id,
      ...props
    },
    ref
  ) => {
    const selectId = id || `select-${Math.random().toString(36).substr(2, 9)}`

    const baseStyles = `
      w-full px-3 py-2 text-sm
      bg-background border rounded-lg
      transition-all duration-200
      focus:outline-none focus:ring-2 focus:ring-offset-0
      appearance-none cursor-pointer
    `

    const stateStyles = error
      ? 'border-destructive focus:ring-destructive/30 bg-destructive/5'
      : 'border-border focus:ring-primary/30 focus:border-primary'

    const disabledStyles = props.disabled
      ? 'bg-muted cursor-not-allowed opacity-60'
      : ''

    return (
      <div className={`${fullWidth ? 'w-full' : ''} ${className}`}>
        {label && (
          <label
            htmlFor={selectId}
            className="block text-sm font-medium mb-1.5"
          >
            {label}
            {props.required && <span className="text-destructive ml-1">*</span>}
          </label>
        )}

        <div className="relative">
          <select
            ref={ref}
            id={selectId}
            aria-invalid={error ? 'true' : 'false'}
            aria-describedby={
              error ? `${selectId}-error` : hint ? `${selectId}-hint` : undefined
            }
            className={`${baseStyles} ${stateStyles} ${disabledStyles} pr-10`}
            {...props}
          >
            {placeholder && (
              <option value="" disabled>
                {placeholder}
              </option>
            )}
            {options.map(option => (
              <option
                key={option.value}
                value={option.value}
                disabled={option.disabled}
              >
                {option.label}
              </option>
            ))}
          </select>

          <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </div>

        {error && (
          <p id={`${selectId}-error`} className="mt-1.5 text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        {hint && !error && (
          <p id={`${selectId}-hint`} className="mt-1.5 text-xs text-muted-foreground">
            {hint}
          </p>
        )}
      </div>
    )
  }
)

Select.displayName = 'Select'

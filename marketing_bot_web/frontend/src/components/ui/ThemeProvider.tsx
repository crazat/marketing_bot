import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

type Theme = 'dark' | 'light' | 'system'

interface ThemeContextType {
  theme: Theme
  resolvedTheme: 'dark' | 'light'
  setTheme: (theme: Theme) => void
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined)

const STORAGE_KEY = 'marketing-bot-theme'

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(STORAGE_KEY) as Theme | null
      return stored || 'system'
    }
    return 'system'
  })

  const [resolvedTheme, setResolvedTheme] = useState<'dark' | 'light'>('dark')

  useEffect(() => {
    const root = document.documentElement

    // 시스템 테마 감지
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

    const updateTheme = () => {
      let effectiveTheme: 'dark' | 'light'

      if (theme === 'system') {
        effectiveTheme = mediaQuery.matches ? 'dark' : 'light'
      } else {
        effectiveTheme = theme
      }

      setResolvedTheme(effectiveTheme)

      // HTML data attribute 업데이트
      root.setAttribute('data-theme', effectiveTheme)

      // 기존 클래스 제거 후 추가
      root.classList.remove('dark', 'light')
      root.classList.add(effectiveTheme)
    }

    updateTheme()

    // 시스템 테마 변경 감지
    mediaQuery.addEventListener('change', updateTheme)

    return () => mediaQuery.removeEventListener('change', updateTheme)
  }, [theme])

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme)
    localStorage.setItem(STORAGE_KEY, newTheme)
  }

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}

/**
 * 테마 토글 버튼
 */
export function ThemeToggle({ className = '' }: { className?: string }) {
  const { theme, setTheme } = useTheme()

  const cycleTheme = () => {
    const themeOrder: Theme[] = ['light', 'dark', 'system']
    const currentIndex = themeOrder.indexOf(theme)
    const nextIndex = (currentIndex + 1) % themeOrder.length
    setTheme(themeOrder[nextIndex])
  }

  const icons = {
    light: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
      </svg>
    ),
    dark: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
      </svg>
    ),
    system: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
  }

  const labels = {
    light: '라이트 모드',
    dark: '다크 모드',
    system: '시스템 설정',
  }

  return (
    <button
      onClick={cycleTheme}
      className={`
        p-2 rounded-lg
        bg-muted hover:bg-muted/80
        transition-all duration-200
        focus:outline-none focus-visible:ring-2 focus-visible:ring-primary
        ${className}
      `}
      title={labels[theme]}
      aria-label={`현재: ${labels[theme]}. 클릭하여 변경`}
    >
      <div className="relative">
        {icons[theme]}
        {theme === 'system' && (
          <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-primary" />
        )}
      </div>
    </button>
  )
}

/**
 * 테마 선택 드롭다운
 */
export function ThemeSelector({ className = '' }: { className?: string }) {
  const { theme, setTheme } = useTheme()

  const options: { value: Theme; label: string; icon: string }[] = [
    { value: 'light', label: '라이트', icon: '☀️' },
    { value: 'dark', label: '다크', icon: '🌙' },
    { value: 'system', label: '시스템', icon: '💻' },
  ]

  return (
    <div
      className={`flex rounded-lg border border-border overflow-hidden ${className}`}
      role="group"
      aria-label="테마 선택"
    >
      {options.map(option => (
        <button
          key={option.value}
          onClick={() => setTheme(option.value)}
          className={`
            px-3 py-2 text-sm transition-colors
            focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-inset
            ${theme === option.value
              ? 'bg-primary text-primary-foreground'
              : 'bg-background hover:bg-muted'
            }
          `}
          aria-pressed={theme === option.value}
        >
          <span className="mr-1" aria-hidden="true">{option.icon}</span>
          {option.label}
        </button>
      ))}
    </div>
  )
}

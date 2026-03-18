/**
 * useResponsiveView Hook
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] 반응형 디자인 개선
 * - 화면 크기별 뷰 모드 자동 감지
 * - 모바일/태블릿/데스크톱 구분
 * - 테이블 ↔ 카드 뷰 전환 지원
 */

import { useState, useEffect, useCallback } from 'react'

// Tailwind 기본 브레이크포인트
export const breakpoints = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  '2xl': 1536,
} as const

export type Breakpoint = keyof typeof breakpoints

export type DeviceType = 'mobile' | 'tablet' | 'desktop'

export interface ResponsiveState {
  /** 현재 화면 너비 */
  width: number
  /** 현재 화면 높이 */
  height: number
  /** 모바일 여부 (< 768px) */
  isMobile: boolean
  /** 태블릿 여부 (768px ~ 1024px) */
  isTablet: boolean
  /** 데스크톱 여부 (>= 1024px) */
  isDesktop: boolean
  /** 디바이스 타입 */
  deviceType: DeviceType
  /** 터치 디바이스 여부 */
  isTouchDevice: boolean
  /** 특정 브레이크포인트 이상인지 */
  isAbove: (bp: Breakpoint) => boolean
  /** 특정 브레이크포인트 이하인지 */
  isBelow: (bp: Breakpoint) => boolean
}

/**
 * 반응형 뷰 상태를 관리하는 훅
 */
export function useResponsiveView(): ResponsiveState {
  const [state, setState] = useState<Omit<ResponsiveState, 'isAbove' | 'isBelow'>>(() => {
    const width = typeof window !== 'undefined' ? window.innerWidth : 1024
    const height = typeof window !== 'undefined' ? window.innerHeight : 768

    return {
      width,
      height,
      isMobile: width < breakpoints.md,
      isTablet: width >= breakpoints.md && width < breakpoints.lg,
      isDesktop: width >= breakpoints.lg,
      deviceType: width < breakpoints.md ? 'mobile' : width < breakpoints.lg ? 'tablet' : 'desktop',
      isTouchDevice: typeof window !== 'undefined' && ('ontouchstart' in window || navigator.maxTouchPoints > 0),
    }
  })

  useEffect(() => {
    const handleResize = () => {
      const width = window.innerWidth
      const height = window.innerHeight

      setState({
        width,
        height,
        isMobile: width < breakpoints.md,
        isTablet: width >= breakpoints.md && width < breakpoints.lg,
        isDesktop: width >= breakpoints.lg,
        deviceType: width < breakpoints.md ? 'mobile' : width < breakpoints.lg ? 'tablet' : 'desktop',
        isTouchDevice: 'ontouchstart' in window || navigator.maxTouchPoints > 0,
      })
    }

    // 초기 실행
    handleResize()

    // 리사이즈 이벤트 리스너 (debounce)
    let timeoutId: ReturnType<typeof setTimeout>
    const debouncedResize = () => {
      clearTimeout(timeoutId)
      timeoutId = setTimeout(handleResize, 100)
    }

    window.addEventListener('resize', debouncedResize)
    return () => {
      window.removeEventListener('resize', debouncedResize)
      clearTimeout(timeoutId)
    }
  }, [])

  const isAbove = useCallback((bp: Breakpoint) => state.width >= breakpoints[bp], [state.width])
  const isBelow = useCallback((bp: Breakpoint) => state.width < breakpoints[bp], [state.width])

  return { ...state, isAbove, isBelow }
}

/**
 * 미디어 쿼리 매칭 훅
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    const mediaQuery = window.matchMedia(query)
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches)

    // 초기값 설정
    setMatches(mediaQuery.matches)

    // 이벤트 리스너 등록
    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', handler)
      return () => mediaQuery.removeEventListener('change', handler)
    } else {
      // 구형 브라우저 지원
      mediaQuery.addListener(handler)
      return () => mediaQuery.removeListener(handler)
    }
  }, [query])

  return matches
}

/**
 * 다크 모드 감지 훅
 */
export function useDarkMode(): boolean {
  return useMediaQuery('(prefers-color-scheme: dark)')
}

/**
 * 모션 감소 선호 감지 훅 (접근성)
 */
export function useReducedMotion(): boolean {
  return useMediaQuery('(prefers-reduced-motion: reduce)')
}

/**
 * 뷰 모드 전환 훅
 * 모바일에서는 카드 뷰, 데스크톱에서는 테이블 뷰를 기본으로 사용
 */
export type ViewMode = 'table' | 'card' | 'list' | 'grid'

export function useViewMode(defaultMode?: ViewMode): [ViewMode, (mode: ViewMode) => void] {
  const { isMobile } = useResponsiveView()

  const [mode, setMode] = useState<ViewMode>(() => {
    if (defaultMode) return defaultMode
    return isMobile ? 'card' : 'table'
  })

  // 화면 크기 변경 시 자동 전환 (사용자가 수동 변경 전까지만)
  const [userChanged, setUserChanged] = useState(false)

  useEffect(() => {
    if (!userChanged) {
      setMode(isMobile ? 'card' : 'table')
    }
  }, [isMobile, userChanged])

  const handleSetMode = useCallback((newMode: ViewMode) => {
    setMode(newMode)
    setUserChanged(true)
  }, [])

  return [mode, handleSetMode]
}

export default useResponsiveView

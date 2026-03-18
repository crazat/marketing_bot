/**
 * Design Tokens
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] 스타일 일관성 통합
 * - 색상, 반경, 패딩, 그림자 통합 정의
 * - Tailwind CSS 클래스 기반
 */

// ============================================
// 색상 토큰
// ============================================
export const colors = {
  // 상태 색상
  success: {
    bg: 'bg-green-500/20',
    border: 'border-green-500/30',
    text: 'text-green-600',
    solid: 'bg-green-600 text-white',
  },
  error: {
    bg: 'bg-red-500/20',
    border: 'border-red-500/30',
    text: 'text-red-600',
    solid: 'bg-red-600 text-white',
  },
  warning: {
    bg: 'bg-yellow-500/20',
    border: 'border-yellow-500/30',
    text: 'text-yellow-600',
    solid: 'bg-yellow-600 text-white',
  },
  info: {
    bg: 'bg-blue-500/20',
    border: 'border-blue-500/30',
    text: 'text-blue-600',
    solid: 'bg-blue-600 text-white',
  },

  // 등급 색상
  grade: {
    S: 'bg-red-500 text-white',
    A: 'bg-orange-500 text-white',
    B: 'bg-blue-500 text-white',
    C: 'bg-gray-500 text-white',
    D: 'bg-gray-400 text-white',
  },

  // 리드 온도 색상
  lead: {
    hot: 'bg-red-500/20 text-red-600 border-red-500/30',
    warm: 'bg-yellow-500/20 text-yellow-600 border-yellow-500/30',
    cold: 'bg-blue-500/20 text-blue-600 border-blue-500/30',
    dead: 'bg-gray-500/20 text-gray-600 border-gray-500/30',
  },

  // 트렌드 색상
  trend: {
    rising: 'text-green-500',
    falling: 'text-red-500',
    stable: 'text-gray-500',
  },
} as const

// ============================================
// 반경 토큰
// ============================================
export const radius = {
  none: 'rounded-none',
  sm: 'rounded',
  md: 'rounded-md',
  lg: 'rounded-lg',
  xl: 'rounded-xl',
  '2xl': 'rounded-2xl',
  full: 'rounded-full',
} as const

// ============================================
// 패딩 토큰
// ============================================
export const padding = {
  xs: 'px-2 py-1',
  sm: 'px-3 py-1.5',
  md: 'px-4 py-2',
  lg: 'px-6 py-3',
  xl: 'px-8 py-4',
} as const

// ============================================
// 그림자 토큰
// ============================================
export const shadow = {
  none: 'shadow-none',
  sm: 'shadow-sm',
  md: 'shadow-md',
  lg: 'shadow-lg',
  xl: 'shadow-xl',
  '2xl': 'shadow-2xl',
} as const

// ============================================
// 간격 토큰
// ============================================
export const spacing = {
  xs: 'gap-1',
  sm: 'gap-2',
  md: 'gap-3',
  lg: 'gap-4',
  xl: 'gap-6',
  '2xl': 'gap-8',
} as const

// ============================================
// 텍스트 크기 토큰
// ============================================
export const fontSize = {
  xs: 'text-xs',
  sm: 'text-sm',
  base: 'text-base',
  lg: 'text-lg',
  xl: 'text-xl',
  '2xl': 'text-2xl',
  '3xl': 'text-3xl',
} as const

// ============================================
// 폰트 굵기 토큰
// ============================================
export const fontWeight = {
  normal: 'font-normal',
  medium: 'font-medium',
  semibold: 'font-semibold',
  bold: 'font-bold',
} as const

// ============================================
// 트랜지션 토큰
// ============================================
export const transition = {
  none: '',
  fast: 'transition-all duration-150',
  normal: 'transition-all duration-200',
  slow: 'transition-all duration-300',
  colors: 'transition-colors duration-200',
  transform: 'transition-transform duration-200',
  opacity: 'transition-opacity duration-200',
} as const

// ============================================
// 포커스 토큰 (접근성)
// ============================================
export const focus = {
  default: 'focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-2',
  visible: 'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2',
  error: 'focus:outline-none focus:ring-2 focus:ring-red-500/50 focus:ring-offset-2',
  none: 'focus:outline-none',
} as const

// ============================================
// 반응형 그리드 토큰
// ============================================
export const grid = {
  '1-col': 'grid-cols-1',
  '2-col': 'grid-cols-1 sm:grid-cols-2',
  '3-col': 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
  '4-col': 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4',
  '5-col': 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5',
  '6-col': 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6',
} as const

// ============================================
// 카드 스타일 토큰
// ============================================
export const card = {
  base: 'bg-card border border-border rounded-lg',
  hover: 'bg-card border border-border rounded-lg hover:border-primary/50 transition-colors',
  interactive: 'bg-card border border-border rounded-lg hover:border-primary/50 hover:shadow-md transition-all cursor-pointer',
  elevated: 'bg-card border border-border rounded-lg shadow-md',
} as const

// ============================================
// 버튼 스타일 토큰
// ============================================
export const button = {
  base: `${padding.md} ${radius.lg} ${transition.colors} ${focus.visible}`,

  primary: 'bg-primary text-primary-foreground hover:bg-primary/90',
  secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
  outline: 'border border-border bg-transparent hover:bg-accent hover:text-accent-foreground',
  ghost: 'bg-transparent hover:bg-accent hover:text-accent-foreground',
  danger: 'bg-red-500 text-white hover:bg-red-600',
  success: 'bg-green-500 text-white hover:bg-green-600',

  disabled: 'opacity-50 cursor-not-allowed',

  size: {
    xs: 'px-2 py-1 text-xs',
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-sm',
    lg: 'px-6 py-3 text-base',
  },
} as const

// ============================================
// 입력 필드 스타일 토큰
// ============================================
export const input = {
  base: `w-full ${padding.md} bg-background border border-border ${radius.lg} ${transition.colors} ${focus.default}`,
  error: 'border-red-500 focus:border-red-500 focus:ring-red-500/30',
  disabled: 'opacity-50 cursor-not-allowed bg-muted',
} as const

// ============================================
// 배지 스타일 토큰
// ============================================
export const badge = {
  base: `inline-flex items-center ${radius.full} ${fontWeight.medium}`,

  size: {
    xs: 'px-1.5 py-0.5 text-[10px] gap-0.5',
    sm: 'px-2 py-0.5 text-xs gap-1',
    md: 'px-2.5 py-1 text-sm gap-1.5',
    lg: 'px-3 py-1.5 text-base gap-2',
  },
} as const

// ============================================
// 유틸리티 함수
// ============================================

/**
 * 여러 클래스를 조합하는 함수
 */
export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ')
}

/**
 * 조건부 클래스 적용
 */
export function conditionalClass(condition: boolean, trueClass: string, falseClass?: string): string {
  return condition ? trueClass : (falseClass || '')
}

// 기본 내보내기
const designTokens = {
  colors,
  radius,
  padding,
  shadow,
  spacing,
  fontSize,
  fontWeight,
  transition,
  focus,
  grid,
  card,
  button,
  input,
  badge,
  cn,
  conditionalClass,
}

export default designTokens

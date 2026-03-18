/**
 * 공용 스타일 상수 및 함수
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * 여러 컴포넌트에서 공통으로 사용되는 스타일 함수들을 모아둔 파일
 * - 중복 코드 제거
 * - 일관된 UI 스타일 유지
 */

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 플랫폼 아이콘
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export const PLATFORM_ICONS: Record<string, string> = {
  naver: '🟢',
  cafe: '☕',
  blog: '📝',
  facebook: '📘',
  instagram: '📸',
  carrot: '🥕',
  influencer: '🤝',
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 점수 배지 스타일
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export const getScoreBadgeStyle = (score: number): string => {
  if (score >= 80) {
    return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
  } else if (score >= 60) {
    return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
  }
  return 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 신뢰도 점수 스타일
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export const getTrustBadgeStyle = (trustLevel: string): string => {
  switch (trustLevel) {
    case 'trusted':
      return 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
    case 'review':
      return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
    case 'suspicious':
      return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
    default:
      return 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
  }
}

export const getTrustLabel = (trustLevel: string): string => {
  switch (trustLevel) {
    case 'trusted':
      return '신뢰'
    case 'review':
      return '확인'
    case 'suspicious':
      return '의심'
    default:
      return ''
  }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Engagement Signal 스타일
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export const getEngagementSignalStyle = (signal: string): string => {
  switch (signal) {
    case 'ready_to_act':
      return 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
    case 'seeking_info':
      return 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400'
    default:
      return ''
  }
}

export const getEngagementSignalLabel = (signal: string): string => {
  switch (signal) {
    case 'ready_to_act':
      return '즉시대응'
    case 'seeking_info':
      return '정보탐색'
    default:
      return ''
  }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 우선순위 스타일
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export const getPriorityStyle = (rank: number): string => {
  switch (rank) {
    case 1:
      return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 ring-1 ring-red-500/30'
    case 2:
      return 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
    case 3:
      return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
    case 4:
      return 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
    default:
      return 'bg-gray-50 text-gray-500 dark:bg-gray-900 dark:text-gray-500'
  }
}

interface PriorityLabel {
  icon: string
  label: string
  desc: string
}

export const getPriorityLabel = (rank: number): PriorityLabel => {
  switch (rank) {
    case 1:
      return { icon: '🔥', label: 'P1', desc: '최우선 - 즉시 대응' }
    case 2:
      return { icon: '⚡', label: 'P2', desc: '높음 - 당일 대응' }
    case 3:
      return { icon: '📌', label: 'P3', desc: '중간 - 2-3일 내' }
    case 4:
      return { icon: '📋', label: 'P4', desc: '낮음 - 주간 리뷰' }
    default:
      return { icon: '📦', label: 'P5', desc: '보류 - 자동 보관' }
  }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 수익 잠재력 스타일
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export const getRevenuePotentialStyle = (potential: string): string => {
  switch (potential) {
    case 'premium':
      return 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400'
    case 'high':
      return 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400'
    case 'medium':
      return 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400'
    default:
      return ''
  }
}

interface RevenuePotentialLabel {
  icon: string
  label: string
}

export const getRevenuePotentialLabel = (potential: string): RevenuePotentialLabel | null => {
  switch (potential) {
    case 'premium':
      return { icon: '💎', label: '프리미엄' }
    case 'high':
      return { icon: '💰', label: '고가치' }
    case 'medium':
      return { icon: '💵', label: '중가치' }
    default:
      return null
  }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 상태 스타일
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  pending: { bg: 'bg-yellow-100 dark:bg-yellow-900/30', text: 'text-yellow-700 dark:text-yellow-400', label: '대기 중' },
  approved: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-400', label: '승인됨' },
  rejected: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-700 dark:text-red-400', label: '거절됨' },
  completed: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-400', label: '완료' },
  new: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-400', label: '신규' },
  contacted: { bg: 'bg-yellow-100 dark:bg-yellow-900/30', text: 'text-yellow-700 dark:text-yellow-400', label: '연락됨' },
  qualified: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-400', label: '적합' },
  converted: { bg: 'bg-purple-100 dark:bg-purple-900/30', text: 'text-purple-700 dark:text-purple-400', label: '전환됨' },
  archived: { bg: 'bg-gray-100 dark:bg-gray-800', text: 'text-gray-600 dark:text-gray-400', label: '보관됨' },
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 등급 스타일
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export const getGradeStyle = (grade: string): string => {
  switch (grade) {
    case 'S':
      return 'bg-purple-500/20 text-purple-500 border-purple-500/30'
    case 'A':
      return 'bg-green-500/20 text-green-500 border-green-500/30'
    case 'B':
      return 'bg-blue-500/20 text-blue-500 border-blue-500/30'
    case 'C':
      return 'bg-yellow-500/20 text-yellow-500 border-yellow-500/30'
    default:
      return 'bg-gray-500/20 text-gray-500 border-gray-500/30'
  }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 트렌드 스타일
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export const getTrendStyle = (trend: 'improving' | 'declining' | 'stable' | string): string => {
  switch (trend) {
    case 'improving':
      return 'text-green-500'
    case 'declining':
      return 'text-red-500'
    case 'stable':
      return 'text-blue-500'
    default:
      return 'text-gray-500'
  }
}

export const getTrendIcon = (trend: 'improving' | 'declining' | 'stable' | string): string => {
  switch (trend) {
    case 'improving':
      return '📈'
    case 'declining':
      return '📉'
    case 'stable':
      return '➡️'
    default:
      return '❓'
  }
}

/* ════════════════════════════════════════════════════════════════════════
   [RECOVER OS] 통합 데이터-비주얼 팔레트 — Recharts 공용
   Recharts 는 SVG color 문자열로 CSS 변수(var(--d1) 등)를 그대로 받습니다.
   따라서 모든 차트 색이 다크/라이트 테마에 자동 반응합니다.
   raw hex 금지 — 반드시 이 토큰들을 사용.
   ════════════════════════════════════════════════════════════════════════ */

// 정렬된 조화 팔레트 (sage·clay·mist·brass·deepsage·mauve·teal·sand)
export const D = [
  'var(--d1)', 'var(--d2)', 'var(--d3)', 'var(--d4)',
  'var(--d5)', 'var(--d6)', 'var(--d7)', 'var(--d8)',
] as const

export const dColor = (i: number): string => D[i % D.length]

// 핵심 시리즈 색
export const SERIES = {
  primary: 'var(--sage)',
  secondary: 'var(--clay)',
  tertiary: 'var(--mist)',
} as const

// 플랫폼 → 팔레트 매핑
export const PLATFORM_COLOR: Record<string, string> = {
  cafe: 'var(--d1)',
  blog: 'var(--d3)',
  kin: 'var(--d4)',
  youtube: 'var(--d2)',
  instagram: 'var(--d6)',
  tiktok: 'var(--d7)',
  place: 'var(--d7)',
  karrot: 'var(--d8)',
  other: 'var(--d8)',
}

// 카테고리 → 팔레트 매핑
export const CATEGORY_COLOR: Record<string, string> = {
  '다이어트': 'var(--d2)',
  '비대칭/교정': 'var(--d1)',
  '피부': 'var(--d4)',
  '교통사고': 'var(--d7)',
  '통증/디스크': 'var(--d3)',
  '두통/어지럼': 'var(--d6)',
  '소화기': 'var(--d5)',
  '호흡기': 'var(--d8)',
  '기타': 'var(--d8)',
}

// 작업 상태 → 시맨틱 색
export const STATUS_COLOR: Record<string, string> = {
  pending: 'var(--warn)',
  generated: 'var(--mist)',
  approved: 'var(--ok)',
  posted: 'var(--sage)',
  skipped: 'var(--text-faint)',
}

// 점수 구간 → 시맨틱 색 (히스토그램/리드 스코어)
export const scoreColor = (min: number): string =>
  min >= 81 ? 'var(--danger)' : min >= 61 ? 'var(--warn)' : min >= 41 ? 'var(--ok)' : 'var(--text-faint)'

// Recharts 공용 스타일 토큰
export const CHART_TOOLTIP_STYLE = {
  backgroundColor: 'var(--surface-3)',
  border: '1px solid var(--hair-strong)',
  borderRadius: '9px',
  boxShadow: 'var(--shadow-pop)',
  color: 'var(--text-strong)',
  fontSize: '12px',
} as const

export const CHART_AXIS_TICK = { fontSize: 11, fill: 'var(--text-faint)' } as const
export const CHART_AXIS_LINE = { stroke: 'var(--hair)' } as const
export const CHART_GRID_STROKE = 'var(--hair)'

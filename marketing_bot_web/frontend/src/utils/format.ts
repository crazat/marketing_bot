/**
 * [Z5] 숫자·단위 포맷 유틸 — 앱 전체 일관성
 *
 * 원칙:
 *  - 숫자는 한국 로케일 (천 단위 쉼표)
 *  - 1000+ 은 기본적으로 compact로 (1.2K, 3.4M)
 *  - 퍼센트는 소수점 0자리 기본
 */

const nfFull = new Intl.NumberFormat('ko-KR')
const nfCompact = new Intl.NumberFormat('ko-KR', {
  notation: 'compact',
  maximumFractionDigits: 1,
})

/** 1234 → "1,234" */
export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '-'
  return nfFull.format(n)
}

/** 1234 → "1.2천", 12345 → "1.2만" 등 — ko 기본. */
export function formatCompact(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '-'
  if (Math.abs(n) < 1000) return nfFull.format(n)
  return nfCompact.format(n)
}

/** 0.4567 → "46%" (0자리), 0.4567, 1 → "45.7%" */
export function formatPercent(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '-'
  return `${(n * 100).toFixed(digits)}%`
}

/** 상대 시간: "5분 전", "3시간 전", "2일 전", "오래 전" */
export function formatRelative(input: number | string | Date): string {
  const t = input instanceof Date ? input.getTime() : new Date(input).getTime()
  if (Number.isNaN(t)) return '-'
  const diff = Date.now() - t
  const sec = Math.round(diff / 1000)
  if (sec < 30) return '방금'
  if (sec < 60) return `${sec}초 전`
  const min = Math.round(sec / 60)
  if (min < 60) return `${min}분 전`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr}시간 전`
  const day = Math.round(hr / 24)
  if (day < 7) return `${day}일 전`
  if (day < 30) return `${Math.round(day / 7)}주 전`
  if (day < 365) return `${Math.round(day / 30)}개월 전`
  return `${Math.round(day / 365)}년 전`
}

/** 밀리초 duration → "1분 23초", "2시간 5분" */
export function formatDuration(ms: number): string {
  if (ms < 0 || Number.isNaN(ms)) return '-'
  const sec = Math.round(ms / 1000)
  if (sec < 60) return `${sec}초`
  const min = Math.floor(sec / 60)
  const remSec = sec % 60
  if (min < 60) {
    return remSec > 0 ? `${min}분 ${remSec}초` : `${min}분`
  }
  const hr = Math.floor(min / 60)
  const remMin = min % 60
  return remMin > 0 ? `${hr}시간 ${remMin}분` : `${hr}시간`
}

/** 순위 차이를 화살표 포맷. +3 → "▲3", -2 → "▼2", 0 → "－" */
export function formatRankDelta(delta: number | null | undefined): string {
  if (delta === null || delta === undefined || delta === 0) return '－'
  if (delta > 0) return `▲${delta}`
  return `▼${Math.abs(delta)}`
}

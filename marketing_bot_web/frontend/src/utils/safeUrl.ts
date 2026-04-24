/**
 * [EE2] URL 스킴 검증 — javascript:, data:, vbscript: 등 차단
 *
 * 외부 스크래퍼 데이터에서 온 URL을 <a href>에 렌더하기 전 안전성 확인.
 * 허용 스킴: http, https, mailto, tel
 */

const SAFE_SCHEMES = /^(https?:|mailto:|tel:|\/|#|\?)/i

export function safeUrl(url: string | null | undefined): string {
  if (!url) return '#'
  const trimmed = String(url).trim()
  if (!trimmed) return '#'
  // 상대 경로 또는 허용 스킴만 통과
  if (SAFE_SCHEMES.test(trimmed)) return trimmed
  // 스킴 없이 시작하면 http:// 기본 주입 (ex. "example.com")
  if (/^[a-z0-9.-]+(\/|$)/i.test(trimmed) && !trimmed.includes(':')) {
    return `https://${trimmed}`
  }
  // 그 외 (javascript:, data: 등) 차단
  return '#'
}

export function isSafeUrl(url: string | null | undefined): boolean {
  if (!url) return false
  return safeUrl(url) !== '#'
}

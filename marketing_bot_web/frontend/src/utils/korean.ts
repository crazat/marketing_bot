/**
 * [Z7] 한국어 조사 자동 선택
 *
 * 한글 마지막 글자의 받침 유무에 따라 조사 선택.
 * 영문/숫자 혼합 시 음독 기준.
 */

const JOSA_PAIRS: Record<string, [string, string]> = {
  '은/는': ['은', '는'],
  '이/가': ['이', '가'],
  '을/를': ['을', '를'],
  '와/과': ['과', '와'],
  '으로/로': ['으로', '로'],
  '아/야': ['아', '야'],
}

// 영문/숫자 말미에 받침이 있는 음독 사전 (간단 버전)
const END_WITH_JONGSUNG = new Set([
  // 받침 있음 (종성 존재)
  'ㄱ', 'ㄴ', 'ㄷ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅅ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ',
])

// 숫자·영문의 경우 음독 기준
const DIGIT_JONGSUNG: Record<string, boolean> = {
  '0': true,  // 영 — 받침 있음 (ㅇ)
  '1': true,  // 일 — ㄹ
  '2': false, // 이 — 없음
  '3': true,  // 삼 — ㅁ
  '4': false, // 사 — 없음
  '5': true,  // 오 → ㅇ (음독)
  '6': true,  // 육 — ㄱ
  '7': true,  // 칠 — ㄹ
  '8': true,  // 팔 — ㄹ
  '9': true,  // 구 → ㅇ
}

const ALPHA_JONGSUNG: Record<string, boolean> = {
  l: true, m: true, n: true, r: true, L: true, M: true, N: true, R: true,
  // 그 외 알파벳은 받침 없음 가정 (대략)
}

/**
 * 문자열 끝 글자에 받침이 있는지 판별
 */
export function hasJongsung(str: string): boolean {
  if (!str) return false
  const lastChar = str.trim().slice(-1)
  if (!lastChar) return false

  // 한글 음절 범위
  const code = lastChar.charCodeAt(0)
  if (code >= 0xac00 && code <= 0xd7a3) {
    const jongsung = (code - 0xac00) % 28
    return jongsung !== 0
  }

  // 한글 자음 (단독)
  if (END_WITH_JONGSUNG.has(lastChar)) return true

  // 숫자
  if (DIGIT_JONGSUNG[lastChar] !== undefined) return DIGIT_JONGSUNG[lastChar]

  // 영문
  if (ALPHA_JONGSUNG[lastChar] !== undefined) return ALPHA_JONGSUNG[lastChar]

  // 기본: 받침 없음 가정
  return false
}

/**
 * 조사 자동 선택
 *
 * @example
 * josa("청주 한의원", "은/는") // "은"
 * josa("카페", "은/는")       // "는"
 * josa("서울", "이/가")       // "이"
 * // 편의: 전체 문자열 반환
 * josaWith("청주 한의원", "은/는") // "청주 한의원은"
 */
export function josa(word: string, pair: keyof typeof JOSA_PAIRS): string {
  const [withJong, withoutJong] = JOSA_PAIRS[pair]
  return hasJongsung(word) ? withJong : withoutJong
}

/**
 * 단어 + 조사를 바로 조합한 문자열 반환
 */
export function josaWith(word: string, pair: keyof typeof JOSA_PAIRS): string {
  return `${word}${josa(word, pair)}`
}

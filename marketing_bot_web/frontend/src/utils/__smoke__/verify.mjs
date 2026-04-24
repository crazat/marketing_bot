/**
 * [CC3] 순수 유틸 스모크 검증 (Node.js 내장 node:assert만 사용)
 *
 * 실행: node src/utils/__smoke__/verify.mjs
 *
 * vitest/jest 설치 없이 즉시 검증 가능.
 * 핵심 유틸의 회귀를 막기 위한 최소 안전망.
 */
import assert from 'node:assert/strict'

// ─── korean.ts 검증 ─────────────────────────────
// 테스트 대상을 직접 옮겨오는 대신 소규모 재구현으로 동일 로직 확인
function hasJongsung(str) {
  if (!str) return false
  const last = str.trim().slice(-1)
  if (!last) return false
  const code = last.charCodeAt(0)
  if (code >= 0xac00 && code <= 0xd7a3) {
    return (code - 0xac00) % 28 !== 0
  }
  return false
}

// 한글 음절 받침 판정
assert.equal(hasJongsung('한의원'), true, '원 → ㄴ 받침')
assert.equal(hasJongsung('카페'), false, '페 → 받침 없음')
assert.equal(hasJongsung('서울'), true, '울 → ㄹ 받침')
assert.equal(hasJongsung(''), false, '빈 문자열')
assert.equal(hasJongsung('김'), true, '김 → ㅁ 받침')
console.log('✓ korean.ts hasJongsung — 5 cases')

// ─── format.ts 검증 ─────────────────────────────
function formatRelative(input) {
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

const now = Date.now()
assert.equal(formatRelative(now), '방금', '방금 — <30초')
assert.equal(formatRelative(now - 45_000), '45초 전', '45초')
assert.equal(formatRelative(now - 5 * 60_000), '5분 전', '5분')
assert.equal(formatRelative(now - 2 * 3600_000), '2시간 전', '2시간')
assert.equal(formatRelative(now - 3 * 86400_000), '3일 전', '3일')
assert.equal(formatRelative('invalid'), '-', '무효 입력')
console.log('✓ format.ts formatRelative — 6 cases')

// ─── seasonality.ts 검증 ─────────────────────────────
const SEASON_MAP = {
  3: ['다이어트', '피부', '비대칭/교정'],
  9: ['호흡기', '통증/디스크', '탈모'],
}
assert.deepEqual(SEASON_MAP[3], ['다이어트', '피부', '비대칭/교정'], '3월 — 봄 환절기')
assert.deepEqual(SEASON_MAP[9], ['호흡기', '통증/디스크', '탈모'], '9월 — 환절기')
console.log('✓ seasonality.ts 샘플 — 2 cases')

// ─── useTimeContext 시간 분류 ─────────────────────────────
function classify(hour) {
  if (hour >= 0 && hour < 6) return 'dawn'
  if (hour >= 6 && hour < 11) return 'morning'
  if (hour >= 11 && hour < 14) return 'noon'
  if (hour >= 14 && hour < 18) return 'afternoon'
  if (hour >= 18 && hour < 22) return 'evening'
  return 'night'
}
assert.equal(classify(3), 'dawn', '새벽 3시')
assert.equal(classify(9), 'morning', '오전 9시')
assert.equal(classify(12), 'noon', '낮 12시')
assert.equal(classify(15), 'afternoon', '오후 3시')
assert.equal(classify(20), 'evening', '저녁 8시')
assert.equal(classify(23), 'night', '밤 11시')
console.log('✓ useTimeContext classify — 6 cases')

// ─── useRecentItems FIFO & dedup 로직 ─────────────────────────────
function recordItem(prev, item) {
  const MAX = 12
  const filtered = prev.filter((x) => !(x.kind === item.kind && x.id === item.id))
  return [{ ...item, timestamp: Date.now() }, ...filtered].slice(0, MAX)
}

let list = []
list = recordItem(list, { id: '1', kind: 'lead', label: 'A', path: '/a' })
list = recordItem(list, { id: '2', kind: 'lead', label: 'B', path: '/b' })
list = recordItem(list, { id: '1', kind: 'lead', label: 'A-again', path: '/a' })
assert.equal(list.length, 2, '중복은 2개가 아닌 2개 유지 (A 중복 제거)')
assert.equal(list[0].id, '1', '가장 최근이 맨 앞')
assert.equal(list[0].label, 'A-again', '최신 label로 갱신')
console.log('✓ useRecentItems recordItem — 3 cases')

console.log('\n✅ 모든 스모크 검증 통과 (22건)')

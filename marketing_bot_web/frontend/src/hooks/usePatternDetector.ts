import { useMemo } from 'react'
import { useActionJournal } from '@/hooks/useActionJournal'

const PATTERN_THRESHOLD = 10 // 같은 context 10연속

export interface Pattern {
  kind: 'streak-approve' | 'streak-skip'
  context: string
  count: number
  message: string
  suggestion: string
}

/**
 * [BB4] 액션 패턴 감지
 *
 * 최근 10연속 같은 context + 같은 action = 자동화 기회
 * 예) "다이어트 카테고리 10연속 승인 → 자동 승인 규칙?"
 */
export function usePatternDetector(): Pattern[] {
  const { entries } = useActionJournal()

  return useMemo(() => {
    if (entries.length < PATTERN_THRESHOLD) return []
    const recent = entries.slice(-PATTERN_THRESHOLD * 2) // 최근 20개까지만 스캔
    const patterns: Pattern[] = []

    // 끝에서부터 역순으로 같은 (kind + context) 연속 횟수
    const last = recent[recent.length - 1]
    if (!last || (last.kind !== 'approve' && last.kind !== 'skip')) return []
    if (!last.context) return []

    let streak = 0
    for (let i = recent.length - 1; i >= 0; i--) {
      const e = recent[i]
      if (e.kind === last.kind && e.context === last.context) {
        streak += 1
      } else {
        break
      }
    }

    if (streak >= PATTERN_THRESHOLD) {
      if (last.kind === 'approve') {
        patterns.push({
          kind: 'streak-approve',
          context: last.context,
          count: streak,
          message: `"${last.context}" 카테고리 ${streak}연속 승인 감지`,
          suggestion: '자동 승인 규칙을 만들어 반복 작업을 줄일 수 있습니다.',
        })
      } else {
        patterns.push({
          kind: 'streak-skip',
          context: last.context,
          count: streak,
          message: `"${last.context}" 카테고리 ${streak}연속 스킵 감지`,
          suggestion: '이 카테고리를 필터에서 제외하면 노이즈를 줄일 수 있습니다.',
        })
      }
    }

    return patterns
  }, [entries])
}

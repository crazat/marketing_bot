import { useEffect, useState } from 'react'
import { josaWith } from '@/utils/korean'

export type TimeOfDay = 'dawn' | 'morning' | 'noon' | 'afternoon' | 'evening' | 'night'

export interface TimeContext {
  timeOfDay: TimeOfDay
  hour: number
  /** 맥락에 맞는 인사말 */
  greeting: string
  /** 시간대별 제안 서브 카피 */
  suggestion: string
  /** 요일 한글 (일/월/화...) */
  dayOfWeekKr: string
  /** 주중/주말 */
  isWeekend: boolean
}

function classify(hour: number): TimeOfDay {
  if (hour >= 0 && hour < 6) return 'dawn'
  if (hour >= 6 && hour < 11) return 'morning'
  if (hour >= 11 && hour < 14) return 'noon'
  if (hour >= 14 && hour < 18) return 'afternoon'
  if (hour >= 18 && hour < 22) return 'evening'
  return 'night'
}

const GREETINGS: Record<TimeOfDay, string> = {
  dawn: '새벽 근무 중이시군요',
  morning: '좋은 아침입니다',
  noon: '점심 시간 전후의 정리 시간',
  afternoon: '오후 집중 작업 시간',
  evening: '하루를 마무리할 시간',
  night: '늦은 시간까지 수고가 많으세요',
}

const SUGGESTIONS: Record<TimeOfDay, string> = {
  dawn: '밤사이 쌓인 데이터를 훑어볼 좋은 시간입니다.',
  morning: '오늘의 집중 작업부터 시작해보세요.',
  noon: '오전 처리분을 점검하고 오후 계획을 세울 때입니다.',
  afternoon: 'HOT LEAD 응답률이 가장 높은 시간대입니다.',
  evening: '오늘 처리분을 정리하고 내일 작업을 예약해보세요.',
  night: '긴급 건만 처리하고 휴식을 권장합니다.',
}

const DAY_OF_WEEK = ['일', '월', '화', '수', '목', '금', '토']

function compute(date: Date): TimeContext {
  const hour = date.getHours()
  const tod = classify(hour)
  const day = date.getDay()
  return {
    timeOfDay: tod,
    hour,
    greeting: GREETINGS[tod],
    suggestion: SUGGESTIONS[tod],
    dayOfWeekKr: DAY_OF_WEEK[day],
    isWeekend: day === 0 || day === 6,
  }
}

/**
 * [Z1/EE6] 시간 맥락 훅 — 분 단위로 갱신.
 *
 * 최적화: 시/요일/timeOfDay 변경이 없으면 setState 스킵.
 * Dashboard 렌더는 시간 블록이 바뀔 때만 발생.
 */
export function useTimeContext(): TimeContext {
  const [ctx, setCtx] = useState<TimeContext>(() => compute(new Date()))

  useEffect(() => {
    const tick = () => {
      const next = compute(new Date())
      setCtx((prev) => {
        // [EE6] 값 비교 — 의미 있는 변경만 리렌더 트리거
        if (
          prev.timeOfDay === next.timeOfDay &&
          prev.hour === next.hour &&
          prev.dayOfWeekKr === next.dayOfWeekKr &&
          prev.isWeekend === next.isWeekend
        ) {
          return prev
        }
        return next
      })
    }
    // 다음 시 경계까지 대기 후 시 단위 간격으로만 체크 (분 해상도 불필요)
    const now = new Date()
    const msUntilNextHour =
      (60 - now.getMinutes()) * 60_000 - now.getSeconds() * 1000 - now.getMilliseconds()
    let interval: number | undefined
    const timeout = window.setTimeout(() => {
      tick()
      interval = window.setInterval(tick, 60 * 60_000) // 시 단위
    }, Math.max(1000, msUntilNextHour))
    return () => {
      clearTimeout(timeout)
      if (interval !== undefined) clearInterval(interval)
    }
  }, [])

  return ctx
}

/**
 * 사용자 이름 + 시간 맥락 인사말 조합.
 *
 * @example greetWithName("원장님", ctx) → "원장님, 좋은 아침입니다"
 * @example greetWithName("크라자트", ctx) → "크라자트, 오후 집중 작업 시간"
 */
export function greetWithName(name: string, ctx: TimeContext): string {
  if (!name) return ctx.greeting
  // 이름 뒤에 쉼표 + 인사
  return `${josaWith(name, '이/가') || name}, ${ctx.greeting}`.replace(/이$|가$/, '')
  // 조사는 이름 뒤에 자연스럽지 않으므로 일단 제거 처리
}

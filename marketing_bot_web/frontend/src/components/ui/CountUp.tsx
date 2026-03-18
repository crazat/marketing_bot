import { useEffect, useState, useRef } from 'react'

interface CountUpProps {
  end: number
  start?: number
  duration?: number
  decimals?: number
  prefix?: string
  suffix?: string
  separator?: string
  className?: string
  onComplete?: () => void
}

/**
 * 숫자 카운트업 애니메이션 컴포넌트
 *
 * 사용법:
 * <CountUp end={1234} duration={1000} />
 * <CountUp end={99.9} decimals={1} suffix="%" />
 */
export default function CountUp({
  end,
  start = 0,
  duration = 800,
  decimals = 0,
  prefix = '',
  suffix = '',
  separator = ',',
  className = '',
  onComplete,
}: CountUpProps) {
  const [count, setCount] = useState(start)
  const countRef = useRef(start)
  const startTimeRef = useRef<number | null>(null)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    // 값이 변경되면 새로운 애니메이션 시작
    countRef.current = count
    startTimeRef.current = null

    const animate = (timestamp: number) => {
      if (startTimeRef.current === null) {
        startTimeRef.current = timestamp
      }

      const progress = Math.min((timestamp - startTimeRef.current) / duration, 1)

      // easeOutExpo 이징 함수 적용
      const easeOutExpo = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress)

      const current = start + (end - start) * easeOutExpo
      setCount(current)

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate)
      } else {
        setCount(end)
        onComplete?.()
      }
    }

    rafRef.current = requestAnimationFrame(animate)

    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
      }
    }
  }, [end, start, duration, onComplete])

  // 숫자 포맷팅
  const formatNumber = (num: number): string => {
    const fixed = num.toFixed(decimals)
    const [intPart, decPart] = fixed.split('.')

    // 천 단위 구분자 추가
    const formatted = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, separator)

    return decPart ? `${formatted}.${decPart}` : formatted
  }

  return (
    <span className={className}>
      {prefix}{formatNumber(count)}{suffix}
    </span>
  )
}

/**
 * 퍼센트 카운트업 (0~100%)
 */
export function PercentCountUp({
  value,
  duration = 800,
  className = '',
}: {
  value: number
  duration?: number
  className?: string
}) {
  return (
    <CountUp
      end={value}
      duration={duration}
      decimals={1}
      suffix="%"
      className={className}
    />
  )
}

/**
 * 정수 카운트업 (천 단위 구분)
 */
export function IntegerCountUp({
  value,
  duration = 800,
  className = '',
  prefix = '',
  suffix = '',
}: {
  value: number
  duration?: number
  className?: string
  prefix?: string
  suffix?: string
}) {
  return (
    <CountUp
      end={value}
      duration={duration}
      decimals={0}
      prefix={prefix}
      suffix={suffix}
      className={className}
    />
  )
}

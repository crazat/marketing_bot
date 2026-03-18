/**
 * useLoadingState Hook
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] 로딩 상태 명확화
 * - 다양한 로딩 상태 분류
 * - 로딩 시간 추적
 * - 새로고침 인디케이터 지원
 */

import { useState, useEffect, useCallback, useRef } from 'react'

// 로딩 상태 타입
export interface LoadingState {
  /** 첫 로드 중 */
  isInitialLoad: boolean
  /** 데이터 새로고침 중 (기존 데이터 유지) */
  isRefreshing: boolean
  /** 더 많은 데이터 로드 중 */
  isLoadingMore: boolean
  /** 페이지 전환 중 */
  isPaginating: boolean
  /** 어떤 형태로든 로딩 중 */
  isAnyLoading: boolean
  /** 로딩 경과 시간 (ms) */
  loadingTime: number
  /** 느린 로딩 여부 (5초 이상) */
  isSlowLoading: boolean
}

interface UseLoadingStateOptions {
  /** TanStack Query의 isLoading */
  isLoading?: boolean
  /** TanStack Query의 isFetching */
  isFetching?: boolean
  /** TanStack Query의 isPreviousData / isPlaceholderData */
  isPlaceholderData?: boolean
  /** 느린 로딩 기준 시간 (ms) */
  slowThreshold?: number
}

/**
 * 로딩 상태를 분류하고 추적하는 훅
 */
export function useLoadingState({
  isLoading = false,
  isFetching = false,
  isPlaceholderData = false,
  slowThreshold = 5000,
}: UseLoadingStateOptions = {}): LoadingState {
  const [loadingTime, setLoadingTime] = useState(0)
  const startTimeRef = useRef<number | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // 로딩 시간 추적
  useEffect(() => {
    if (isLoading || isFetching) {
      if (!startTimeRef.current) {
        startTimeRef.current = Date.now()
      }

      intervalRef.current = setInterval(() => {
        if (startTimeRef.current) {
          setLoadingTime(Date.now() - startTimeRef.current)
        }
      }, 100)

      return () => {
        if (intervalRef.current) {
          clearInterval(intervalRef.current)
        }
      }
    } else {
      startTimeRef.current = null
      setLoadingTime(0)
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [isLoading, isFetching])

  return {
    isInitialLoad: isLoading && !isPlaceholderData,
    isRefreshing: isFetching && !isLoading,
    isLoadingMore: isFetching && isPlaceholderData,
    isPaginating: isFetching && isPlaceholderData,
    isAnyLoading: isLoading || isFetching,
    loadingTime,
    isSlowLoading: loadingTime > slowThreshold,
  }
}

/**
 * 로딩 시간만 추적하는 간단한 훅
 */
export function useLoadingTime(isLoading: boolean): number {
  const [time, setTime] = useState(0)
  const startTimeRef = useRef<number | null>(null)

  useEffect(() => {
    if (isLoading) {
      startTimeRef.current = Date.now()
      const interval = setInterval(() => {
        if (startTimeRef.current) {
          setTime(Date.now() - startTimeRef.current)
        }
      }, 100)
      return () => clearInterval(interval)
    } else {
      startTimeRef.current = null
      setTime(0)
    }
  }, [isLoading])

  return time
}

/**
 * 지연된 로딩 상태 (깜빡임 방지)
 * 로딩이 특정 시간 이상 지속될 때만 표시
 */
export function useDelayedLoading(isLoading: boolean, delay: number = 200): boolean {
  const [showLoading, setShowLoading] = useState(false)

  useEffect(() => {
    if (isLoading) {
      const timer = setTimeout(() => setShowLoading(true), delay)
      return () => clearTimeout(timer)
    } else {
      setShowLoading(false)
    }
  }, [isLoading, delay])

  return showLoading
}

/**
 * 최소 로딩 시간 보장 (UX 개선)
 * 로딩이 너무 빨리 끝나면 깜빡이는 느낌을 방지
 */
export function useMinimumLoading(isLoading: boolean, minTime: number = 500): boolean {
  const [showLoading, setShowLoading] = useState(isLoading)
  const startTimeRef = useRef<number | null>(null)

  useEffect(() => {
    if (isLoading) {
      startTimeRef.current = Date.now()
      setShowLoading(true)
    } else if (startTimeRef.current) {
      const elapsed = Date.now() - startTimeRef.current
      const remaining = Math.max(0, minTime - elapsed)

      if (remaining > 0) {
        const timer = setTimeout(() => setShowLoading(false), remaining)
        return () => clearTimeout(timer)
      } else {
        setShowLoading(false)
      }
    }
  }, [isLoading, minTime])

  return showLoading
}

/**
 * 로딩 진행률 시뮬레이션 (실제 진행률을 알 수 없을 때)
 */
export function useSimulatedProgress(isLoading: boolean): number {
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    if (isLoading) {
      setProgress(0)
      const interval = setInterval(() => {
        setProgress(prev => {
          // 점점 느려지는 진행률 (99%에서 멈춤)
          if (prev >= 99) return prev
          const increment = Math.max(0.5, (100 - prev) * 0.1)
          return Math.min(99, prev + increment)
        })
      }, 100)
      return () => clearInterval(interval)
    } else {
      // 로딩 완료 시 100%로 점프 후 리셋
      setProgress(100)
      const timer = setTimeout(() => setProgress(0), 200)
      return () => clearTimeout(timer)
    }
  }, [isLoading])

  return progress
}

/**
 * 데이터 새로고침 상태 추적
 */
export interface RefreshState {
  isRefreshing: boolean
  lastRefreshTime: Date | null
  refresh: () => void
  timeSinceRefresh: number | null
}

export function useRefreshState(
  refetchFn: () => void,
  isFetching: boolean
): RefreshState {
  const [lastRefreshTime, setLastRefreshTime] = useState<Date | null>(null)
  const [timeSinceRefresh, setTimeSinceRefresh] = useState<number | null>(null)

  const refresh = useCallback(() => {
    refetchFn()
    setLastRefreshTime(new Date())
  }, [refetchFn])

  // 마지막 새로고침 이후 경과 시간 계산
  useEffect(() => {
    if (!lastRefreshTime) return

    const updateTime = () => {
      setTimeSinceRefresh(Date.now() - lastRefreshTime.getTime())
    }

    updateTime()
    const interval = setInterval(updateTime, 1000)
    return () => clearInterval(interval)
  }, [lastRefreshTime])

  return {
    isRefreshing: isFetching,
    lastRefreshTime,
    refresh,
    timeSinceRefresh,
  }
}

export default useLoadingState

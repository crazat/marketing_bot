/**
 * useUrlState Hook
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] URL 쿼리 파라미터로 상태 저장
 * - 필터, 탭, 페이지네이션 상태 유지
 * - 새로고침/공유 시 상태 복원
 * - 브라우저 뒤로가기 지원
 */

import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

type ParamValue = string | number | boolean | null | undefined

interface UseUrlStateOptions<T> {
  defaultValue: T
  serialize?: (value: T) => string
  deserialize?: (value: string) => T
}

/**
 * URL 파라미터로 상태를 관리하는 훅
 * @param key - URL 파라미터 키
 * @param options - 기본값 및 직렬화 옵션
 */
export function useUrlState<T extends ParamValue>(
  key: string,
  options: UseUrlStateOptions<T>
): [T, (value: T) => void] {
  const [searchParams, setSearchParams] = useSearchParams()

  const { defaultValue, serialize, deserialize } = options

  // URL에서 값 읽기
  const value = useMemo(() => {
    const param = searchParams.get(key)
    if (param === null) return defaultValue

    if (deserialize) {
      return deserialize(param)
    }

    // 기본 역직렬화
    if (typeof defaultValue === 'number') {
      const num = Number(param)
      return (isNaN(num) ? defaultValue : num) as T
    }
    if (typeof defaultValue === 'boolean') {
      return (param === 'true') as T
    }
    return param as T
  }, [searchParams, key, defaultValue, deserialize])

  // URL에 값 쓰기
  const setValue = useCallback(
    (newValue: T) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)

          if (newValue === null || newValue === undefined || newValue === defaultValue) {
            next.delete(key)
          } else {
            const serialized = serialize
              ? serialize(newValue)
              : String(newValue)
            next.set(key, serialized)
          }

          return next
        },
        { replace: true }
      )
    },
    [key, defaultValue, serialize, setSearchParams]
  )

  return [value, setValue]
}

/**
 * 여러 URL 파라미터를 한 번에 관리하는 훅
 * @param config - 파라미터 설정 객체
 */
export function useUrlStates<T extends Record<string, ParamValue>>(
  config: { [K in keyof T]: UseUrlStateOptions<T[K]> }
): [T, (updates: Partial<T>) => void] {
  const [searchParams, setSearchParams] = useSearchParams()

  // 모든 값 읽기
  const values = useMemo(() => {
    const result: Partial<T> = {}

    for (const key in config) {
      const { defaultValue, deserialize } = config[key]
      const param = searchParams.get(key)

      if (param === null) {
        result[key] = defaultValue
      } else if (deserialize) {
        result[key] = deserialize(param)
      } else if (typeof defaultValue === 'number') {
        const num = Number(param)
        result[key] = (isNaN(num) ? defaultValue : num) as T[typeof key]
      } else if (typeof defaultValue === 'boolean') {
        result[key] = (param === 'true') as T[typeof key]
      } else {
        result[key] = param as T[typeof key]
      }
    }

    return result as T
  }, [searchParams, config])

  // 여러 값 한 번에 업데이트
  const setValues = useCallback(
    (updates: Partial<T>) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)

          for (const key in updates) {
            const newValue = updates[key]
            const { defaultValue, serialize } = config[key]

            if (newValue === null || newValue === undefined || newValue === defaultValue) {
              next.delete(key)
            } else {
              const serialized = serialize
                ? serialize(newValue as T[typeof key])
                : String(newValue)
              next.set(key, serialized)
            }
          }

          return next
        },
        { replace: true }
      )
    },
    [config, setSearchParams]
  )

  return [values, setValues]
}

export default useUrlState

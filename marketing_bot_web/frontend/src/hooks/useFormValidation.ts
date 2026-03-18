/**
 * useFormValidation Hook
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] 폼 검증 시스템 통합
 * - 필드별 검증 규칙 정의
 * - 실시간 검증 및 에러 메시지
 * - 터치 상태 추적
 * - 폼 리셋 및 전체 검증
 */

import { useState, useCallback, useMemo } from 'react'

// 검증 규칙 타입
export interface ValidationRule<T = string> {
  required?: boolean | string
  minLength?: { value: number; message: string }
  maxLength?: { value: number; message: string }
  min?: { value: number; message: string }
  max?: { value: number; message: string }
  pattern?: { value: RegExp; message: string }
  custom?: (value: T, allValues: Record<string, unknown>) => string | null
}

// 스키마 타입
export type ValidationSchema<T extends Record<string, any>> = {
  [K in keyof T]?: ValidationRule<T[K]>
}

// 에러 상태 타입
export type FormErrors<T> = {
  [K in keyof T]?: string
}

// 터치 상태 타입
export type FormTouched<T> = {
  [K in keyof T]?: boolean
}

// 훅 반환 타입
export interface UseFormValidationReturn<T extends Record<string, any>> {
  values: T
  errors: FormErrors<T>
  touched: FormTouched<T>
  isValid: boolean
  isDirty: boolean
  setValue: <K extends keyof T>(field: K, value: T[K]) => void
  setValues: (values: Partial<T>) => void
  setError: <K extends keyof T>(field: K, error: string) => void
  clearError: <K extends keyof T>(field: K) => void
  handleChange: (field: keyof T) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => void
  handleBlur: (field: keyof T) => () => void
  validateField: <K extends keyof T>(field: K, value?: T[K]) => string | null
  validateAll: () => boolean
  reset: (newInitialValues?: Partial<T>) => void
  getFieldProps: (field: keyof T) => {
    value: T[keyof T]
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => void
    onBlur: () => void
    error?: string
    'aria-invalid'?: boolean
  }
}

/**
 * 폼 검증을 관리하는 훅
 * @param schema - 필드별 검증 규칙
 * @param initialValues - 초기 값 (선택)
 */
export function useFormValidation<T extends Record<string, any>>(
  schema: ValidationSchema<T>,
  initialValues?: Partial<T>
): UseFormValidationReturn<T> {
  // 초기값 생성
  const defaultValues = useMemo(() => {
    const values: Partial<T> = {}
    for (const key in schema) {
      values[key as keyof T] = (initialValues?.[key] ?? '') as T[keyof T]
    }
    return values as T
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const [values, setValuesState] = useState<T>(defaultValues)
  const [errors, setErrors] = useState<FormErrors<T>>({})
  const [touched, setTouched] = useState<FormTouched<T>>({})
  const [isDirty, setIsDirty] = useState(false)

  // 단일 필드 검증
  const validateField = useCallback(<K extends keyof T>(
    field: K,
    value?: T[K]
  ): string | null => {
    const rules = schema[field]
    if (!rules) return null

    const fieldValue = value ?? values[field]

    // required 검증
    if (rules.required) {
      const isEmpty = fieldValue === undefined ||
                      fieldValue === null ||
                      fieldValue === '' ||
                      (Array.isArray(fieldValue) && fieldValue.length === 0)

      if (isEmpty) {
        return typeof rules.required === 'string'
          ? rules.required
          : '필수 입력 항목입니다'
      }
    }

    // 값이 없으면 나머지 검증 스킵
    if (fieldValue === undefined || fieldValue === null || fieldValue === '') {
      return null
    }

    const stringValue = String(fieldValue)

    // minLength 검증
    if (rules.minLength && stringValue.length < rules.minLength.value) {
      return rules.minLength.message
    }

    // maxLength 검증
    if (rules.maxLength && stringValue.length > rules.maxLength.value) {
      return rules.maxLength.message
    }

    // min 검증 (숫자)
    if (rules.min && typeof fieldValue === 'number' && fieldValue < rules.min.value) {
      return rules.min.message
    }

    // max 검증 (숫자)
    if (rules.max && typeof fieldValue === 'number' && fieldValue > rules.max.value) {
      return rules.max.message
    }

    // pattern 검증
    if (rules.pattern && !rules.pattern.value.test(stringValue)) {
      return rules.pattern.message
    }

    // custom 검증
    if (rules.custom) {
      return rules.custom(fieldValue, values as Record<string, unknown>)
    }

    return null
  }, [schema, values])

  // 값 설정
  const setValue = useCallback(<K extends keyof T>(field: K, value: T[K]) => {
    setValuesState(prev => ({ ...prev, [field]: value }))
    setIsDirty(true)

    // 터치된 필드면 즉시 검증
    if (touched[field]) {
      const error = validateField(field, value)
      setErrors(prev => ({
        ...prev,
        [field]: error || undefined
      }))
    }
  }, [touched, validateField])

  // 여러 값 설정
  const setValues = useCallback((newValues: Partial<T>) => {
    setValuesState(prev => ({ ...prev, ...newValues }))
    setIsDirty(true)
  }, [])

  // 에러 직접 설정
  const setError = useCallback(<K extends keyof T>(field: K, error: string) => {
    setErrors(prev => ({ ...prev, [field]: error }))
  }, [])

  // 에러 지우기
  const clearError = useCallback(<K extends keyof T>(field: K) => {
    setErrors(prev => {
      const next = { ...prev }
      delete next[field]
      return next
    })
  }, [])

  // 변경 핸들러 생성
  const handleChange = useCallback((field: keyof T) => {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      const target = e.target
      let value: unknown

      if (target.type === 'checkbox') {
        value = (target as HTMLInputElement).checked
      } else if (target.type === 'number') {
        value = target.value === '' ? '' : Number(target.value)
      } else {
        value = target.value
      }

      setValue(field, value as T[keyof T])
    }
  }, [setValue])

  // blur 핸들러 생성
  const handleBlur = useCallback((field: keyof T) => {
    return () => {
      setTouched(prev => ({ ...prev, [field]: true }))
      const error = validateField(field)
      setErrors(prev => ({
        ...prev,
        [field]: error || undefined
      }))
    }
  }, [validateField])

  // 전체 검증
  const validateAll = useCallback((): boolean => {
    const newErrors: FormErrors<T> = {}
    const newTouched: FormTouched<T> = {}
    let isValid = true

    for (const field in schema) {
      newTouched[field as keyof T] = true
      const error = validateField(field as keyof T)
      if (error) {
        newErrors[field as keyof T] = error
        isValid = false
      }
    }

    setTouched(newTouched)
    setErrors(newErrors)
    return isValid
  }, [schema, validateField])

  // 폼 리셋
  const reset = useCallback((newInitialValues?: Partial<T>) => {
    const resetValues = newInitialValues
      ? { ...defaultValues, ...newInitialValues }
      : defaultValues

    setValuesState(resetValues)
    setErrors({})
    setTouched({})
    setIsDirty(false)
  }, [defaultValues])

  // 필드 props 생성 (편의 함수)
  const getFieldProps = useCallback((field: keyof T) => {
    const error = touched[field] ? errors[field] : undefined
    return {
      value: values[field],
      onChange: handleChange(field),
      onBlur: handleBlur(field),
      error,
      'aria-invalid': error ? true : undefined
    }
  }, [values, errors, touched, handleChange, handleBlur])

  // 유효성 상태 계산
  const isValid = useMemo(() => {
    return Object.keys(errors).length === 0
  }, [errors])

  return {
    values,
    errors,
    touched,
    isValid,
    isDirty,
    setValue,
    setValues,
    setError,
    clearError,
    handleChange,
    handleBlur,
    validateField,
    validateAll,
    reset,
    getFieldProps
  }
}

export default useFormValidation

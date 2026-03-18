/**
 * SearchInput Component
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] 테이블/리스트 검색용 입력 컴포넌트
 * - 디바운스 적용
 * - 검색어 초기화 버튼
 * - 아이콘 포함
 */

import { useState, useEffect, useCallback } from 'react'

interface SearchInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  debounceMs?: number
  className?: string
}

export default function SearchInput({
  value,
  onChange,
  placeholder = '검색...',
  debounceMs = 300,
  className = '',
}: SearchInputProps) {
  const [localValue, setLocalValue] = useState(value)

  // 외부 value 변경 시 동기화
  useEffect(() => {
    setLocalValue(value)
  }, [value])

  // 디바운스 처리
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localValue !== value) {
        onChange(localValue)
      }
    }, debounceMs)

    return () => clearTimeout(timer)
  }, [localValue, debounceMs, onChange, value])

  const handleClear = useCallback(() => {
    setLocalValue('')
    onChange('')
  }, [onChange])

  return (
    <div className={`relative ${className}`}>
      {/* 검색 아이콘 */}
      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none">
        🔍
      </span>

      {/* 검색 입력 */}
      <input
        type="text"
        value={localValue}
        onChange={(e) => setLocalValue(e.target.value)}
        placeholder={placeholder}
        className="
          w-full pl-10 pr-10 py-2
          bg-background border border-border rounded-lg
          text-sm placeholder:text-muted-foreground
          focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent
          transition-colors
        "
        aria-label={placeholder}
      />

      {/* 초기화 버튼 */}
      {localValue && (
        <button
          type="button"
          onClick={handleClear}
          className="
            absolute right-3 top-1/2 -translate-y-1/2
            text-muted-foreground hover:text-foreground
            transition-colors p-1
          "
          aria-label="검색어 지우기"
        >
          ✕
        </button>
      )}
    </div>
  )
}

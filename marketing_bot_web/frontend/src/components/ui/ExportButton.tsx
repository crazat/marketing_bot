/**
 * ExportButton Component
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] 데이터 내보내기 버튼
 * - CSV 내보내기
 * - 커스텀 컬럼 매핑 지원
 * - 파일명 커스터마이징
 */

import { useCallback, useState } from 'react'

interface ExportColumn<T> {
  key: keyof T | string
  header: string
  formatter?: (value: any, row: T) => string
}

interface ExportButtonProps<T> {
  data: T[]
  columns: ExportColumn<T>[]
  filename?: string
  label?: string
  disabled?: boolean
  className?: string
}

export default function ExportButton<T extends Record<string, any>>({
  data,
  columns,
  filename = 'export',
  label = 'CSV 내보내기',
  disabled = false,
  className = '',
}: ExportButtonProps<T>) {
  const [isExporting, setIsExporting] = useState(false)

  const handleExport = useCallback(() => {
    if (data.length === 0 || disabled) return

    setIsExporting(true)

    try {
      // 헤더 행
      const headers = columns.map((col) => `"${col.header}"`)

      // 데이터 행
      const rows = data.map((row) => {
        return columns.map((col) => {
          const key = col.key as string
          const value = key.includes('.')
            ? key.split('.').reduce((obj, k) => obj?.[k], row as any)
            : row[key]

          let formattedValue = col.formatter
            ? col.formatter(value, row)
            : String(value ?? '')

          // CSV 이스케이프 처리
          formattedValue = formattedValue.replace(/"/g, '""')
          return `"${formattedValue}"`
        })
      })

      // CSV 문자열 생성
      const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n')

      // BOM 추가 (한글 깨짐 방지)
      const bom = '\uFEFF'
      const blob = new Blob([bom + csvContent], { type: 'text/csv;charset=utf-8;' })

      // 다운로드
      const link = document.createElement('a')
      const url = URL.createObjectURL(blob)
      const dateStr = new Date().toISOString().split('T')[0]

      link.setAttribute('href', url)
      link.setAttribute('download', `${filename}_${dateStr}.csv`)
      link.style.visibility = 'hidden'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    } catch (error) {
      console.error('CSV 내보내기 오류:', error)
    } finally {
      setIsExporting(false)
    }
  }, [data, columns, filename, disabled])

  return (
    <button
      type="button"
      onClick={handleExport}
      disabled={disabled || isExporting || data.length === 0}
      className={`
        inline-flex items-center gap-2 px-4 py-2
        bg-primary text-primary-foreground rounded-lg
        text-sm font-medium
        hover:bg-primary/90
        disabled:opacity-50 disabled:cursor-not-allowed
        focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2
        transition-colors
        ${className}
      `}
      aria-label={label}
    >
      {isExporting ? (
        <>
          <span className="animate-spin">⏳</span>
          내보내는 중...
        </>
      ) : (
        <>
          <span aria-hidden="true">📥</span>
          {label}
          {data.length > 0 && (
            <span className="text-xs opacity-75">({data.length}건)</span>
          )}
        </>
      )}
    </button>
  )
}

import { useState, useCallback } from 'react'
import Button from '@/components/ui/Button'

export interface FilterOption {
  value: string
  label: string
  count?: number
}

export interface FilterConfig {
  key: string
  label: string
  type: 'select' | 'multiselect' | 'range' | 'search' | 'date-range'
  options?: FilterOption[]
  placeholder?: string
  min?: number
  max?: number
}

export interface FilterValues {
  [key: string]: string | string[] | number | [number, number] | [Date, Date] | undefined
}

interface AdvancedFilterProps {
  filters: FilterConfig[]
  values: FilterValues
  onChange: (values: FilterValues) => void
  onReset?: () => void
  className?: string
}

export default function AdvancedFilter({
  filters,
  values,
  onChange,
  onReset,
  className = '',
}: AdvancedFilterProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const handleChange = useCallback(
    (key: string, value: FilterValues[string]) => {
      onChange({ ...values, [key]: value })
    },
    [values, onChange]
  )

  const activeFilterCount = Object.values(values).filter(
    v => v !== undefined && v !== '' && (Array.isArray(v) ? v.length > 0 : true)
  ).length

  return (
    <div className={`bg-card border border-border rounded-lg ${className}`}>
      {/* 헤더 */}
      <div className="flex items-center justify-between p-3 border-b border-border">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-2 text-sm font-medium hover:text-primary focus:outline-none focus:ring-2 focus:ring-primary rounded-lg px-2 py-1 -mx-2 -my-1 transition-colors"
          aria-expanded={isExpanded}
          aria-controls="filter-content"
        >
          <span>필터</span>
          {activeFilterCount > 0 && (
            <span className="px-2 py-0.5 bg-primary text-primary-foreground rounded-full text-xs">
              {activeFilterCount}
            </span>
          )}
          <span className="text-muted-foreground" aria-hidden="true">
            {isExpanded ? '▲' : '▼'}
          </span>
        </button>

        {activeFilterCount > 0 && onReset && (
          <Button
            variant="ghost"
            size="xs"
            onClick={onReset}
          >
            초기화
          </Button>
        )}
      </div>

      {/* 필터 내용 */}
      {isExpanded && (
        <div id="filter-content" className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filters.map(filter => (
            <FilterField
              key={filter.key}
              config={filter}
              value={values[filter.key]}
              onChange={value => handleChange(filter.key, value)}
            />
          ))}
        </div>
      )}

      {/* 빠른 필터 (접힌 상태에서도 표시) */}
      {!isExpanded && activeFilterCount > 0 && (
        <div className="px-3 py-2 flex flex-wrap gap-2">
          {Object.entries(values).map(([key, value]) => {
            if (!value || (Array.isArray(value) && value.length === 0)) return null
            const filter = filters.find(f => f.key === key)
            if (!filter) return null

            return (
              <FilterTag
                key={key}
                label={filter.label}
                value={formatFilterValue(value, filter)}
                onRemove={() => handleChange(key, undefined)}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

interface FilterFieldProps {
  config: FilterConfig
  value: FilterValues[string]
  onChange: (value: FilterValues[string]) => void
}

function FilterField({ config, value, onChange }: FilterFieldProps) {
  switch (config.type) {
    case 'select':
      return (
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{config.label}</label>
          <select
            value={(value as string) || ''}
            onChange={e => onChange(e.target.value || undefined)}
            className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">{config.placeholder || '전체'}</option>
            {config.options?.map(opt => (
              <option key={opt.value} value={opt.value}>
                {opt.label} {opt.count !== undefined && `(${opt.count})`}
              </option>
            ))}
          </select>
        </div>
      )

    case 'multiselect':
      return (
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{config.label}</label>
          <div className="flex flex-wrap gap-1">
            {config.options?.map(opt => {
              const isSelected = Array.isArray(value) && (value as string[]).includes(opt.value)
              return (
                <button
                  key={opt.value}
                  onClick={() => {
                    const currentValue = (value as string[]) || []
                    const newValue = isSelected
                      ? currentValue.filter(v => v !== opt.value)
                      : [...currentValue, opt.value]
                    onChange(newValue.length > 0 ? newValue : undefined)
                  }}
                  className={`px-2 py-1 text-xs rounded-md border transition-colors ${
                    isSelected
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-background border-border hover:border-primary'
                  }`}
                >
                  {opt.label}
                </button>
              )
            })}
          </div>
        </div>
      )

    case 'range':
      return (
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{config.label}</label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              placeholder="최소"
              min={config.min}
              max={config.max}
              value={Array.isArray(value) ? (value as [number, number])[0] || '' : ''}
              onChange={e => {
                const min = e.target.value ? Number(e.target.value) : undefined
                const currentMax = Array.isArray(value) ? (value as [number, number])[1] : undefined
                if (min === undefined && currentMax === undefined) {
                  onChange(undefined)
                } else {
                  onChange([min ?? 0, currentMax ?? config.max ?? 999999])
                }
              }}
              className="w-full px-2 py-1 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <span className="text-muted-foreground">~</span>
            <input
              type="number"
              placeholder="최대"
              min={config.min}
              max={config.max}
              value={Array.isArray(value) ? (value as [number, number])[1] || '' : ''}
              onChange={e => {
                const max = e.target.value ? Number(e.target.value) : undefined
                const currentMin = Array.isArray(value) ? (value as [number, number])[0] : undefined
                if (max === undefined && currentMin === undefined) {
                  onChange(undefined)
                } else {
                  onChange([currentMin ?? config.min ?? 0, max ?? 999999])
                }
              }}
              className="w-full px-2 py-1 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
        </div>
      )

    case 'search':
      return (
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{config.label}</label>
          <input
            type="text"
            placeholder={config.placeholder || '검색...'}
            value={(value as string) || ''}
            onChange={e => onChange(e.target.value || undefined)}
            className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
      )

    case 'date-range':
      return (
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{config.label}</label>
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={
                Array.isArray(value) && value[0] instanceof Date
                  ? (value as [Date, Date])[0].toISOString().split('T')[0]
                  : ''
              }
              onChange={e => {
                const from = e.target.value ? new Date(e.target.value) : undefined
                const currentTo = Array.isArray(value) ? (value as [Date, Date])[1] : undefined
                if (!from && !currentTo) {
                  onChange(undefined)
                } else {
                  onChange([from ?? new Date(), currentTo ?? new Date()])
                }
              }}
              className="w-full px-2 py-1 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <span className="text-muted-foreground">~</span>
            <input
              type="date"
              value={
                Array.isArray(value) && value[1] instanceof Date
                  ? (value as [Date, Date])[1].toISOString().split('T')[0]
                  : ''
              }
              onChange={e => {
                const to = e.target.value ? new Date(e.target.value) : undefined
                const currentFrom = Array.isArray(value) ? (value as [Date, Date])[0] : undefined
                if (!to && !currentFrom) {
                  onChange(undefined)
                } else {
                  onChange([currentFrom ?? new Date(), to ?? new Date()])
                }
              }}
              className="w-full px-2 py-1 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
        </div>
      )

    default:
      return null
  }
}

interface FilterTagProps {
  label: string
  value: string
  onRemove: () => void
}

function FilterTag({ label, value, onRemove }: FilterTagProps) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-1 bg-muted rounded-md text-xs">
      <span className="text-muted-foreground">{label}:</span>
      <span>{value}</span>
      <button
        onClick={onRemove}
        className="ml-1 hover:text-destructive transition-colors"
        aria-label={`${label} 필터 제거`}
      >
        ×
      </button>
    </span>
  )
}

function formatFilterValue(value: FilterValues[string], config: FilterConfig): string {
  if (Array.isArray(value)) {
    if (config.type === 'multiselect') {
      return (value as string[])
        .map(v => config.options?.find(o => o.value === v)?.label || v)
        .join(', ')
    }
    if (config.type === 'range') {
      const [min, max] = value as [number, number]
      return `${min.toLocaleString()} ~ ${max.toLocaleString()}`
    }
    if (config.type === 'date-range') {
      const [from, to] = value as [Date, Date]
      return `${from.toLocaleDateString()} ~ ${to.toLocaleDateString()}`
    }
  }

  if (config.type === 'select' && config.options) {
    return config.options.find(o => o.value === value)?.label || String(value)
  }

  return String(value)
}

/**
 * 필터 프리셋 정의
 */
export const KEYWORD_FILTER_CONFIGS: FilterConfig[] = [
  {
    key: 'grade',
    label: '등급',
    type: 'multiselect',
    options: [
      { value: 'S', label: 'S급' },
      { value: 'A', label: 'A급' },
      { value: 'B', label: 'B급' },
      { value: 'C', label: 'C급' },
    ],
  },
  {
    key: 'category',
    label: '카테고리',
    type: 'select',
    options: [
      { value: '다이어트', label: '다이어트' },
      { value: '피부', label: '피부' },
      { value: '교통사고', label: '교통사고' },
      { value: '체형교정', label: '체형교정' },
      { value: '탈모', label: '탈모' },
      { value: '통증', label: '통증' },
    ],
  },
  {
    key: 'searchVolume',
    label: '검색량',
    type: 'range',
    min: 0,
    max: 100000,
  },
  {
    key: 'trendStatus',
    label: '트렌드',
    type: 'multiselect',
    options: [
      { value: 'rising', label: '상승' },
      { value: 'stable', label: '안정' },
      { value: 'falling', label: '하락' },
    ],
  },
  {
    key: 'searchText',
    label: '키워드 검색',
    type: 'search',
    placeholder: '키워드 입력...',
  },
]

export const LEAD_FILTER_CONFIGS: FilterConfig[] = [
  {
    key: 'platform',
    label: '플랫폼',
    type: 'multiselect',
    options: [
      { value: 'cafe', label: '맘카페' },
      { value: 'youtube', label: 'YouTube' },
      { value: 'instagram', label: 'Instagram' },
      { value: 'tiktok', label: 'TikTok' },
      { value: 'carrot', label: '당근마켓' },
    ],
  },
  {
    key: 'status',
    label: '상태',
    type: 'multiselect',
    options: [
      { value: 'pending', label: '대기' },
      { value: 'contacted', label: '연락완료' },
      { value: 'replied', label: '답변받음' },
      { value: 'converted', label: '전환' },
      { value: 'rejected', label: '거절' },
    ],
  },
  {
    key: 'dateRange',
    label: '발견일',
    type: 'date-range',
  },
  {
    key: 'searchText',
    label: '내용 검색',
    type: 'search',
    placeholder: '제목 또는 내용...',
  },
]

import { ReactNode } from 'react'

/**
 * 반응형 데이터 뷰 컴포넌트
 *
 * 데스크톱에서는 테이블 형식으로, 모바일에서는 카드 형식으로 데이터를 표시합니다.
 */

export interface Column<T> {
  /** 컬럼 키 */
  key: keyof T | string
  /** 컬럼 헤더 */
  header: string
  /** 셀 렌더링 함수 */
  render?: (item: T) => ReactNode
  /** 모바일에서 숨김 */
  hideOnMobile?: boolean
  /** 항상 표시 (모바일 카드에서 우선 표시) */
  alwaysShow?: boolean
  /** 컬럼 너비 클래스 */
  width?: string
  /** 정렬 */
  align?: 'left' | 'center' | 'right'
}

interface ResponsiveDataViewProps<T> {
  /** 데이터 배열 */
  data: T[]
  /** 컬럼 정의 */
  columns: Column<T>[]
  /** 행 키 생성 함수 */
  getRowKey: (item: T) => string | number
  /** 행 클릭 핸들러 */
  onRowClick?: (item: T) => void
  /** 선택된 행 키 배열 */
  selectedKeys?: (string | number)[]
  /** 행 선택 핸들러 */
  onRowSelect?: (key: string | number, selected: boolean) => void
  /** 전체 선택 핸들러 */
  onSelectAll?: (selected: boolean) => void
  /** 로딩 상태 */
  isLoading?: boolean
  /** 빈 상태 메시지 */
  emptyMessage?: string
  /** 카드 렌더링 커스터마이징 */
  renderCard?: (item: T) => ReactNode
  /** 테이블 스타일 클래스 */
  className?: string
}

export default function ResponsiveDataView<T>({
  data,
  columns,
  getRowKey,
  onRowClick,
  selectedKeys = [],
  onRowSelect,
  onSelectAll,
  isLoading,
  emptyMessage = '데이터가 없습니다.',
  renderCard,
  className = '',
}: ResponsiveDataViewProps<T>) {
  const hasSelection = !!onRowSelect
  const allSelected = data.length > 0 && selectedKeys.length === data.length

  // 모바일 카드에 표시할 주요 컬럼 (alwaysShow 또는 hideOnMobile이 아닌 것)
  const mobileColumns = columns.filter(col => col.alwaysShow || !col.hideOnMobile)

  // 셀 값 가져오기
  const getCellValue = (item: T, column: Column<T>): ReactNode => {
    if (column.render) {
      return column.render(item)
    }
    const value = item[column.key as keyof T]
    return value as ReactNode
  }

  // 정렬 클래스
  const getAlignClass = (align?: 'left' | 'center' | 'right') => {
    switch (align) {
      case 'center': return 'text-center'
      case 'right': return 'text-right'
      default: return 'text-left'
    }
  }

  if (isLoading) {
    return (
      <div className="animate-pulse space-y-3">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-16 bg-muted rounded-lg" />
        ))}
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p>{emptyMessage}</p>
      </div>
    )
  }

  return (
    <div className={className}>
      {/* 데스크톱: 테이블 */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              {hasSelection && (
                <th className="py-3 px-4 w-10">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={(e) => onSelectAll?.(e.target.checked)}
                    className="rounded border-border text-primary focus:ring-primary"
                    aria-label="전체 선택"
                  />
                </th>
              )}
              {columns.map(column => (
                <th
                  key={String(column.key)}
                  className={`py-3 px-4 text-sm font-semibold ${getAlignClass(column.align)} ${column.width || ''}`}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map(item => {
              const key = getRowKey(item)
              const isSelected = selectedKeys.includes(key)

              return (
                <tr
                  key={key}
                  onClick={() => onRowClick?.(item)}
                  className={`
                    border-b border-border transition-colors
                    ${onRowClick ? 'cursor-pointer hover:bg-muted/50' : ''}
                    ${isSelected ? 'bg-primary/10' : ''}
                  `}
                >
                  {hasSelection && (
                    <td className="py-3 px-4">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={(e) => {
                          e.stopPropagation()
                          onRowSelect?.(key, e.target.checked)
                        }}
                        onClick={(e) => e.stopPropagation()}
                        className="rounded border-border text-primary focus:ring-primary"
                        aria-label={`행 ${key} 선택`}
                      />
                    </td>
                  )}
                  {columns.map(column => (
                    <td
                      key={String(column.key)}
                      className={`py-3 px-4 text-sm ${getAlignClass(column.align)}`}
                    >
                      {getCellValue(item, column)}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* 모바일: 카드 */}
      <div className="md:hidden space-y-3">
        {data.map(item => {
          const key = getRowKey(item)
          const isSelected = selectedKeys.includes(key)

          // 커스텀 카드 렌더링
          if (renderCard) {
            return (
              <div
                key={key}
                onClick={() => onRowClick?.(item)}
                className={onRowClick ? 'cursor-pointer' : ''}
              >
                {renderCard(item)}
              </div>
            )
          }

          // 기본 카드 렌더링
          return (
            <div
              key={key}
              onClick={() => onRowClick?.(item)}
              className={`
                bg-card border border-border rounded-lg p-4 transition-colors
                ${onRowClick ? 'cursor-pointer hover:border-primary/50' : ''}
                ${isSelected ? 'border-primary bg-primary/5' : ''}
              `}
            >
              {/* 선택 체크박스 */}
              {hasSelection && (
                <div className="flex items-center justify-end mb-2">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={(e) => {
                      e.stopPropagation()
                      onRowSelect?.(key, e.target.checked)
                    }}
                    onClick={(e) => e.stopPropagation()}
                    className="rounded border-border text-primary focus:ring-primary"
                    aria-label={`행 ${key} 선택`}
                  />
                </div>
              )}

              {/* 카드 내용 */}
              <div className="space-y-2">
                {mobileColumns.map((column, idx) => (
                  <div
                    key={String(column.key)}
                    className={idx === 0 ? 'font-medium' : 'text-sm'}
                  >
                    {idx > 0 && (
                      <span className="text-muted-foreground mr-2">
                        {column.header}:
                      </span>
                    )}
                    {getCellValue(item, column)}
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/**
 * 간단한 모바일 카드 리스트 컴포넌트
 */
interface MobileCardListProps<T> {
  data: T[]
  getKey: (item: T) => string | number
  renderCard: (item: T) => ReactNode
  emptyMessage?: string
}

export function MobileCardList<T>({
  data,
  getKey,
  renderCard,
  emptyMessage = '데이터가 없습니다.',
}: MobileCardListProps<T>) {
  if (data.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p>{emptyMessage}</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {data.map(item => (
        <div key={getKey(item)}>
          {renderCard(item)}
        </div>
      ))}
    </div>
  )
}

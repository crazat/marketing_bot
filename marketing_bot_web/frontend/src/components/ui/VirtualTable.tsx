import { useRef, useState, useCallback } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'

interface Column<T> {
  key: string
  header: string
  width?: string
  align?: 'left' | 'center' | 'right'
  render: (item: T, index: number) => React.ReactNode
}

interface VirtualTableProps<T> {
  data: T[]
  columns: Column<T>[]
  rowHeight?: number
  maxHeight?: number
  className?: string
  onRowClick?: (item: T, index: number) => void
  emptyMessage?: string
  /** [Phase 4-3-A] 테이블 라벨 (스크린 리더용) */
  ariaLabel?: string
  /** [Phase 4-3-A] 현재 선택된 행 인덱스 (외부에서 제어) */
  selectedIndex?: number
  /** [Phase 4-3-A] 행 선택 시 콜백 */
  onSelectedIndexChange?: (index: number) => void
}

export function VirtualTable<T>({
  data,
  columns,
  rowHeight = 48,
  maxHeight = 600,
  className = '',
  onRowClick,
  emptyMessage = '데이터가 없습니다.',
  ariaLabel = '데이터 테이블',
  selectedIndex: externalSelectedIndex,
  onSelectedIndexChange,
}: VirtualTableProps<T>) {
  const parentRef = useRef<HTMLDivElement>(null)
  const [internalFocusedIndex, setInternalFocusedIndex] = useState<number>(-1)

  // 외부 제어와 내부 상태 병합
  const focusedIndex = externalSelectedIndex ?? internalFocusedIndex

  const setFocusedIndex = useCallback((index: number) => {
    setInternalFocusedIndex(index)
    onSelectedIndexChange?.(index)
  }, [onSelectedIndexChange])

  const virtualizer = useVirtualizer({
    count: data.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 10,
  })

  const items = virtualizer.getVirtualItems()

  // 정렬 클래스
  const alignClass = (align?: 'left' | 'center' | 'right') => {
    switch (align) {
      case 'center': return 'text-center'
      case 'right': return 'text-right'
      default: return 'text-left'
    }
  }

  // [Phase 4-3-A] 키보드 네비게이션 핸들러
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (data.length === 0) return

    let newIndex = focusedIndex

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        newIndex = Math.min(focusedIndex + 1, data.length - 1)
        break

      case 'ArrowUp':
        e.preventDefault()
        newIndex = Math.max(focusedIndex - 1, 0)
        break

      case 'Home':
        e.preventDefault()
        newIndex = 0
        break

      case 'End':
        e.preventDefault()
        newIndex = data.length - 1
        break

      case 'PageDown':
        e.preventDefault()
        // 대략 10개 행씩 이동
        newIndex = Math.min(focusedIndex + 10, data.length - 1)
        break

      case 'PageUp':
        e.preventDefault()
        newIndex = Math.max(focusedIndex - 10, 0)
        break

      case 'Enter':
      case ' ':
        e.preventDefault()
        if (focusedIndex >= 0 && focusedIndex < data.length) {
          onRowClick?.(data[focusedIndex], focusedIndex)
        }
        return

      default:
        return
    }

    if (newIndex !== focusedIndex) {
      setFocusedIndex(newIndex)
      // 스크롤 위치 조정
      virtualizer.scrollToIndex(newIndex, { align: 'auto' })
    }
  }, [data, focusedIndex, onRowClick, setFocusedIndex, virtualizer])

  // 포커스 시 첫 행 선택
  const handleFocus = useCallback(() => {
    if (focusedIndex < 0 && data.length > 0) {
      setFocusedIndex(0)
    }
  }, [data.length, focusedIndex, setFocusedIndex])

  // 선택된 행 ID
  const getRowId = (index: number) => `virtual-table-row-${index}`

  if (data.length === 0) {
    return (
      <div
        className="text-center py-12 text-muted-foreground"
        role="status"
        aria-label="데이터 없음"
      >
        <p className="text-4xl mb-4">📭</p>
        <p>{emptyMessage}</p>
      </div>
    )
  }

  return (
    <div
      className={`border border-border rounded-lg overflow-hidden ${className}`}
      role="grid"
      aria-label={ariaLabel}
      aria-rowcount={data.length}
      aria-colcount={columns.length}
    >
      {/* 헤더 (고정) */}
      <div
        className="bg-muted border-b border-border sticky top-0 z-10"
        role="row"
        aria-rowindex={1}
      >
        <div className="flex">
          {columns.map((col, colIndex) => (
            <div
              key={col.key}
              role="columnheader"
              aria-colindex={colIndex + 1}
              className={`px-4 py-3 text-sm font-semibold ${alignClass(col.align)}`}
              style={{ width: col.width || 'auto', flex: col.width ? 'none' : 1 }}
            >
              {col.header}
            </div>
          ))}
        </div>
      </div>

      {/* 가상 스크롤 영역 */}
      <div
        ref={parentRef}
        className="overflow-auto focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        style={{ height: Math.min(maxHeight, data.length * rowHeight + 20) }}
        tabIndex={0}
        onKeyDown={handleKeyDown}
        onFocus={handleFocus}
        aria-activedescendant={focusedIndex >= 0 ? getRowId(focusedIndex) : undefined}
      >
        <div
          style={{
            height: `${virtualizer.getTotalSize()}px`,
            width: '100%',
            position: 'relative',
          }}
        >
          {items.map((virtualRow) => {
            const item = data[virtualRow.index]
            const isFocused = virtualRow.index === focusedIndex

            return (
              <div
                key={virtualRow.key}
                id={getRowId(virtualRow.index)}
                role="row"
                aria-rowindex={virtualRow.index + 2}
                aria-selected={isFocused}
                className={`absolute left-0 w-full flex border-b border-border transition-colors ${
                  onRowClick ? 'cursor-pointer' : ''
                } ${isFocused ? 'bg-accent ring-2 ring-ring ring-inset' : 'hover:bg-muted/50'}`}
                style={{
                  height: `${virtualRow.size}px`,
                  transform: `translateY(${virtualRow.start}px)`,
                }}
                onClick={() => {
                  setFocusedIndex(virtualRow.index)
                  onRowClick?.(item, virtualRow.index)
                }}
              >
                {columns.map((col, colIndex) => (
                  <div
                    key={col.key}
                    role="gridcell"
                    aria-colindex={colIndex + 1}
                    className={`px-4 py-3 text-sm flex items-center ${alignClass(col.align)}`}
                    style={{ width: col.width || 'auto', flex: col.width ? 'none' : 1 }}
                  >
                    {col.render(item, virtualRow.index)}
                  </div>
                ))}
              </div>
            )
          })}
        </div>
      </div>

      {/* 푸터 정보 */}
      <div
        className="bg-muted/50 border-t border-border px-4 py-2 text-xs text-muted-foreground"
        role="status"
        aria-live="polite"
      >
        총 {data.length.toLocaleString()}개 항목
        {focusedIndex >= 0 && (
          <span className="ml-2">
            | 선택: {focusedIndex + 1}번째 행
          </span>
        )}
        <span className="ml-2 hidden sm:inline">
          | 키보드: ↑↓ 이동, Enter 선택, Home/End 처음/끝
        </span>
      </div>
    </div>
  )
}

/**
 * 간단한 가상 리스트 컴포넌트
 */
interface VirtualListProps<T> {
  data: T[]
  renderItem: (item: T, index: number) => React.ReactNode
  itemHeight?: number
  maxHeight?: number
  className?: string
  ariaLabel?: string
}

export function VirtualList<T>({
  data,
  renderItem,
  itemHeight = 60,
  maxHeight = 500,
  className = '',
  ariaLabel = '리스트',
}: VirtualListProps<T>) {
  const parentRef = useRef<HTMLDivElement>(null)
  const [focusedIndex, setFocusedIndex] = useState<number>(-1)

  const virtualizer = useVirtualizer({
    count: data.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => itemHeight,
    overscan: 5,
  })

  const items = virtualizer.getVirtualItems()

  // 키보드 네비게이션
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (data.length === 0) return

    let newIndex = focusedIndex

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        newIndex = Math.min(focusedIndex + 1, data.length - 1)
        break
      case 'ArrowUp':
        e.preventDefault()
        newIndex = Math.max(focusedIndex - 1, 0)
        break
      case 'Home':
        e.preventDefault()
        newIndex = 0
        break
      case 'End':
        e.preventDefault()
        newIndex = data.length - 1
        break
      default:
        return
    }

    if (newIndex !== focusedIndex) {
      setFocusedIndex(newIndex)
      virtualizer.scrollToIndex(newIndex, { align: 'auto' })
    }
  }, [data.length, focusedIndex, virtualizer])

  const handleFocus = useCallback(() => {
    if (focusedIndex < 0 && data.length > 0) {
      setFocusedIndex(0)
    }
  }, [data.length, focusedIndex])

  if (data.length === 0) {
    return null
  }

  return (
    <div
      ref={parentRef}
      className={`overflow-auto focus:outline-none focus-visible:ring-2 focus-visible:ring-ring ${className}`}
      style={{ maxHeight }}
      tabIndex={0}
      role="listbox"
      aria-label={ariaLabel}
      aria-activedescendant={focusedIndex >= 0 ? `virtual-list-item-${focusedIndex}` : undefined}
      onKeyDown={handleKeyDown}
      onFocus={handleFocus}
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: '100%',
          position: 'relative',
        }}
      >
        {items.map((virtualRow) => (
          <div
            key={virtualRow.key}
            id={`virtual-list-item-${virtualRow.index}`}
            role="option"
            aria-selected={virtualRow.index === focusedIndex}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: `${virtualRow.size}px`,
              transform: `translateY(${virtualRow.start}px)`,
            }}
            className={virtualRow.index === focusedIndex ? 'ring-2 ring-ring ring-inset' : ''}
            onClick={() => setFocusedIndex(virtualRow.index)}
          >
            {renderItem(data[virtualRow.index], virtualRow.index)}
          </div>
        ))}
      </div>
    </div>
  )
}

export default VirtualTable

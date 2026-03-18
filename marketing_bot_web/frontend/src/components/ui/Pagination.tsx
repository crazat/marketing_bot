import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react'
import { IconButton } from '@/components/ui/Button'

export interface PaginationProps {
  currentPage: number
  totalPages: number
  onPageChange: (page: number) => void
  /** 페이지당 항목 수 */
  pageSize?: number
  /** 페이지당 항목 수 옵션 */
  pageSizeOptions?: number[]
  /** 페이지당 항목 수 변경 핸들러 */
  onPageSizeChange?: (size: number) => void
  /** 총 항목 수 (표시용) */
  totalItems?: number
  /** 표시할 페이지 버튼 수 */
  siblingCount?: number
  /** 간소화 모드 */
  compact?: boolean
  className?: string
}

export default function Pagination({
  currentPage,
  totalPages,
  onPageChange,
  pageSize,
  pageSizeOptions = [25, 50, 100],
  onPageSizeChange,
  totalItems,
  siblingCount = 1,
  compact = false,
  className = '',
}: PaginationProps) {
  // 페이지 범위 계산
  const getPageRange = () => {
    const range: (number | 'ellipsis')[] = []

    // 총 페이지가 7개 이하면 모두 표시
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) {
        range.push(i)
      }
      return range
    }

    // 항상 첫 페이지 포함
    range.push(1)

    // 왼쪽 생략 기호
    const leftSiblingIndex = Math.max(currentPage - siblingCount, 2)
    const shouldShowLeftEllipsis = leftSiblingIndex > 2

    if (shouldShowLeftEllipsis) {
      range.push('ellipsis')
    } else {
      // 2페이지 추가
      if (totalPages > 1) range.push(2)
    }

    // 중간 페이지들
    const start = shouldShowLeftEllipsis ? leftSiblingIndex : 3
    const rightSiblingIndex = Math.min(currentPage + siblingCount, totalPages - 1)
    const shouldShowRightEllipsis = rightSiblingIndex < totalPages - 1
    const end = shouldShowRightEllipsis ? rightSiblingIndex : totalPages - 1

    for (let i = start; i <= end; i++) {
      if (!range.includes(i)) {
        range.push(i)
      }
    }

    // 오른쪽 생략 기호
    if (shouldShowRightEllipsis) {
      range.push('ellipsis')
    }

    // 마지막 페이지 포함
    if (totalPages > 1 && !range.includes(totalPages)) {
      range.push(totalPages)
    }

    return range
  }

  const pageRange = getPageRange()

  // 현재 표시 범위 계산
  const startItem = totalItems ? (currentPage - 1) * (pageSize || 25) + 1 : 0
  const endItem = totalItems ? Math.min(currentPage * (pageSize || 25), totalItems) : 0

  if (totalPages <= 1 && !onPageSizeChange) {
    return null
  }

  return (
    <nav
      className={`flex flex-col sm:flex-row items-center justify-between gap-4 ${className}`}
      aria-label="페이지 네비게이션"
      role="navigation"
    >
      {/* 항목 정보 */}
      {totalItems !== undefined && !compact && (
        <div className="text-sm text-muted-foreground">
          {totalItems > 0 ? (
            <>
              <span className="font-medium">{startItem.toLocaleString()}</span>
              {' - '}
              <span className="font-medium">{endItem.toLocaleString()}</span>
              {' / '}
              <span className="font-medium">{totalItems.toLocaleString()}</span>
              <span className="ml-1">개</span>
            </>
          ) : (
            <span>항목 없음</span>
          )}
        </div>
      )}

      {/* 페이지네이션 컨트롤 */}
      <div className="flex items-center gap-1">
        {/* 첫 페이지 */}
        {!compact && (
          <IconButton
            icon={<ChevronsLeft className="w-4 h-4" />}
            onClick={() => onPageChange(1)}
            disabled={currentPage === 1}
            title="첫 페이지로 이동"
            aria-label="첫 페이지로 이동"
          />
        )}

        {/* 이전 페이지 */}
        <IconButton
          icon={<ChevronLeft className="w-4 h-4" />}
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage === 1}
          title="이전 페이지로 이동"
          aria-label="이전 페이지로 이동"
        />

        {/* 페이지 번호 */}
        {!compact && (
          <div className="flex items-center gap-1 mx-1">
            {pageRange.map((page, index) => {
              if (page === 'ellipsis') {
                return (
                  <span
                    key={`ellipsis-${index}`}
                    className="px-2 py-1 text-muted-foreground"
                  >
                    ...
                  </span>
                )
              }

              const isCurrentPage = page === currentPage
              return (
                <button
                  key={page}
                  onClick={() => onPageChange(page)}
                  className={`
                    min-w-[36px] px-3 py-1.5 rounded-lg text-sm font-medium transition-colors
                    focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2
                    ${isCurrentPage
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                    }
                  `}
                  aria-current={isCurrentPage ? 'page' : undefined}
                  aria-label={`${page} 페이지로 이동${isCurrentPage ? ' (현재 페이지)' : ''}`}
                >
                  {page}
                </button>
              )
            })}
          </div>
        )}

        {/* 간소화 모드에서 페이지 표시 */}
        {compact && (
          <span className="px-3 py-1.5 text-sm text-muted-foreground">
            {currentPage} / {totalPages}
          </span>
        )}

        {/* 다음 페이지 */}
        <IconButton
          icon={<ChevronRight className="w-4 h-4" />}
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage === totalPages}
          title="다음 페이지로 이동"
          aria-label="다음 페이지로 이동"
        />

        {/* 마지막 페이지 */}
        {!compact && (
          <IconButton
            icon={<ChevronsRight className="w-4 h-4" />}
            onClick={() => onPageChange(totalPages)}
            disabled={currentPage === totalPages}
            title="마지막 페이지로 이동"
            aria-label="마지막 페이지로 이동"
          />
        )}
      </div>

      {/* 페이지당 항목 수 선택 */}
      {onPageSizeChange && pageSize && (
        <div className="flex items-center gap-2">
          <label htmlFor="page-size" className="text-sm text-muted-foreground whitespace-nowrap">
            페이지당
          </label>
          <select
            id="page-size"
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="px-2 py-1.5 text-sm bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size}개
              </option>
            ))}
          </select>
        </div>
      )}
    </nav>
  )
}

/**
 * 페이지네이션 상태 관리 훅
 */
export function usePagination<T>(
  items: T[],
  initialPageSize = 25
) {
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(initialPageSize)

  const totalPages = Math.ceil(items.length / pageSize)
  const totalItems = items.length

  // 페이지 변경 시 범위 검증
  const handlePageChange = (page: number) => {
    const validPage = Math.max(1, Math.min(page, totalPages))
    setCurrentPage(validPage)
  }

  // 페이지 사이즈 변경 시 첫 페이지로
  const handlePageSizeChange = (size: number) => {
    setPageSize(size)
    setCurrentPage(1)
  }

  // 현재 페이지 데이터
  const paginatedItems = items.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  )

  // items가 변경되면 페이지 범위 재검증
  const safeCurrentPage = Math.min(currentPage, totalPages || 1)
  if (safeCurrentPage !== currentPage && totalPages > 0) {
    setCurrentPage(safeCurrentPage)
  }

  return {
    currentPage: safeCurrentPage,
    pageSize,
    totalPages,
    totalItems,
    paginatedItems,
    onPageChange: handlePageChange,
    onPageSizeChange: handlePageSizeChange,
  }
}

// useState import 추가
import { useState } from 'react'

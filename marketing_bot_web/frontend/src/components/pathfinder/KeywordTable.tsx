import { useState, useMemo, useCallback, memo } from 'react'
import { exportToCSV, KEYWORD_EXPORT_COLUMNS } from '@/utils/export'
import Pagination from '@/components/ui/Pagination'
import KeywordPopover from '@/components/ui/KeywordPopover'
import KeywordMemoEditor from '@/components/pathfinder/KeywordMemoEditor'
import { useToast } from '@/components/ui/Toast'
import Button from '@/components/ui/Button'
import { Download, X } from 'lucide-react'

interface KeywordData {
  keyword: string
  search_volume?: number
  difficulty: number
  opportunity: number
  grade: 'S' | 'A' | 'B' | 'C'
  trend_status?: 'rising' | 'falling' | 'stable' | 'unknown'
  category?: string
  source?: string
  current_rank?: number | null
  rank_status?: string
  memo?: string
  user_tags?: string[]
  likelihood_score?: number
}

interface KeywordTableProps {
  keywords: KeywordData[]
  showExport?: boolean
  /** 초기 페이지 크기 */
  initialPageSize?: number
  /** 선택/정렬 기능 활성화 */
  enableSelection?: boolean
  /** 일괄 작업 콜백 */
  onBulkAction?: (action: 'export' | 'delete', keywords: KeywordData[]) => void
}

type SortColumn = 'grade' | 'keyword' | 'search_volume' | 'difficulty' | 'opportunity' | 'trend_status' | 'category' | 'source' | 'current_rank' | 'likelihood_score'
type SortDirection = 'asc' | 'desc'

const gradeOrder: Record<string, number> = { S: 4, A: 3, B: 2, C: 1 }
const trendOrder: Record<string, number> = { rising: 3, stable: 2, falling: 1, unknown: 0 }

const gradeColors: Record<string, string> = {
  S: 'text-red-500',
  A: 'text-green-500',
  B: 'text-blue-500',
  C: 'text-muted-foreground'
}

const gradeEmojis: Record<string, string> = {
  S: '🔥',
  A: '🟢',
  B: '🔵',
  C: '⚪'
}

const trendEmojis: Record<string, string> = {
  rising: '📈',
  falling: '📉',
  stable: '➡️',
  unknown: '❓'
}

// [성능 최적화] React.memo로 불필요한 리렌더링 방지
function KeywordTableComponent({
  keywords,
  showExport = true,
  initialPageSize = 25,
  enableSelection = true,
  onBulkAction
}: KeywordTableProps) {
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(initialPageSize)
  const [sortColumn, setSortColumn] = useState<SortColumn | null>(null)
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [selectedKeywords, setSelectedKeywords] = useState<Set<string>>(new Set())
  const toast = useToast()

  // 정렬된 키워드 목록
  const sortedKeywords = useMemo(() => {
    if (!sortColumn) return keywords

    return [...keywords].sort((a, b) => {
      let aVal: any, bVal: any

      switch (sortColumn) {
        case 'grade':
          aVal = gradeOrder[a.grade] || 0
          bVal = gradeOrder[b.grade] || 0
          break
        case 'trend_status':
          aVal = trendOrder[a.trend_status || 'unknown'] || 0
          bVal = trendOrder[b.trend_status || 'unknown'] || 0
          break
        case 'search_volume':
        case 'difficulty':
        case 'opportunity':
        case 'likelihood_score':
          aVal = a[sortColumn] ?? 0
          bVal = b[sortColumn] ?? 0
          break
        case 'current_rank':
          // null/undefined는 마지막으로 (999999)
          aVal = a.current_rank ?? 999999
          bVal = b.current_rank ?? 999999
          break
        default:
          aVal = (a[sortColumn] || '').toString().toLowerCase()
          bVal = (b[sortColumn] || '').toString().toLowerCase()
      }

      if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1
      if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1
      return 0
    })
  }, [keywords, sortColumn, sortDirection])

  // 컬럼 헤더 클릭 핸들러
  const handleSort = useCallback((column: SortColumn) => {
    if (sortColumn === column) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortColumn(column)
      setSortDirection('desc')
    }
  }, [sortColumn])

  // 전체 선택/해제
  const handleSelectAll = useCallback(() => {
    if (selectedKeywords.size === sortedKeywords.length) {
      setSelectedKeywords(new Set())
    } else {
      setSelectedKeywords(new Set(sortedKeywords.map(k => k.keyword)))
    }
  }, [sortedKeywords, selectedKeywords.size])

  // 개별 선택
  const handleSelectOne = useCallback((keyword: string) => {
    setSelectedKeywords(prev => {
      const next = new Set(prev)
      if (next.has(keyword)) {
        next.delete(keyword)
      } else {
        next.add(keyword)
      }
      return next
    })
  }, [])

  // 선택된 키워드 가져오기
  const getSelectedKeywordData = useCallback(() => {
    return keywords.filter(k => selectedKeywords.has(k.keyword))
  }, [keywords, selectedKeywords])

  // 선택 항목 내보내기
  const handleExportSelected = useCallback(() => {
    const selected = getSelectedKeywordData()
    if (selected.length === 0) {
      toast.error('선택된 키워드가 없습니다')
      return
    }
    const timestamp = new Date().toISOString().slice(0, 10)
    exportToCSV(selected, KEYWORD_EXPORT_COLUMNS, `keywords_selected_${timestamp}.csv`)
    toast.success(`${selected.length}개 키워드를 CSV로 내보냈습니다`)
    if (onBulkAction) onBulkAction('export', selected)
  }, [getSelectedKeywordData, toast, onBulkAction])

  const handleExport = () => {
    const timestamp = new Date().toISOString().slice(0, 10)
    exportToCSV(keywords, KEYWORD_EXPORT_COLUMNS, `keywords_${timestamp}.csv`)
    toast.success(`${keywords.length}개 키워드를 CSV로 내보냈습니다`)
  }

  // 정렬 아이콘
  const SortIcon = ({ column }: { column: SortColumn }) => {
    if (sortColumn !== column) {
      return <span className="text-muted-foreground/50 ml-1">⇅</span>
    }
    return <span className="ml-1">{sortDirection === 'asc' ? '↑' : '↓'}</span>
  }

  // 정렬 가능한 헤더
  const SortableHeader = ({ column, children, className = '' }: { column: SortColumn; children: React.ReactNode; className?: string }) => (
    <th
      className={`px-3 py-3 text-left text-sm font-semibold cursor-pointer hover:bg-accent/50 transition-colors select-none whitespace-nowrap ${className}`}
      onClick={() => handleSort(column)}
      role="columnheader"
      aria-sort={sortColumn === column ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <span className="flex items-center">
        {children}
        <SortIcon column={column} />
      </span>
    </th>
  )

  if (!keywords || keywords.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p className="text-4xl mb-4">🔍</p>
        <p>키워드가 없습니다.</p>
        <p className="text-sm mt-2">Pathfinder를 실행하여 키워드를 발굴하세요.</p>
      </div>
    )
  }

  // 페이지네이션 계산
  const totalPages = Math.ceil(sortedKeywords.length / pageSize)
  const startIndex = (currentPage - 1) * pageSize
  const endIndex = startIndex + pageSize
  const paginatedKeywords = sortedKeywords.slice(startIndex, endIndex)

  // 현재 페이지의 모든 항목이 선택되었는지 확인
  const isAllCurrentPageSelected = paginatedKeywords.length > 0 &&
    paginatedKeywords.every(k => selectedKeywords.has(k.keyword))
  const isSomeSelected = selectedKeywords.size > 0

  // 페이지 사이즈 변경 시 첫 페이지로
  const handlePageSizeChange = (size: number) => {
    setPageSize(size)
    setCurrentPage(1)
  }

  return (
    <div className="space-y-4">
      {/* 상단 액션 바 */}
      <div className="flex justify-between items-center">
        {/* 일괄 작업 바 (선택 시 표시) */}
        {enableSelection && isSomeSelected ? (
          <div className="flex items-center gap-3 px-4 py-2 bg-primary/10 border border-primary/20 rounded-lg">
            <span className="text-sm font-medium text-primary">
              {selectedKeywords.size}개 선택됨
            </span>
            <div className="h-4 w-px bg-border" />
            <Button
              variant="outline"
              size="sm"
              onClick={handleExportSelected}
              icon={<Download size={14} />}
            >
              선택 내보내기
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedKeywords(new Set())}
              icon={<X size={14} />}
            >
              선택 해제
            </Button>
          </div>
        ) : (
          <div />
        )}

        {showExport && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleExport}
            icon={<Download size={14} />}
          >
            CSV 내보내기 ({keywords.length}개)
          </Button>
        )}
      </div>

      {/* 순위 색상 범례 */}
      <div className="flex flex-wrap gap-4 text-xs text-muted-foreground px-2 py-2 bg-muted/30 rounded-lg">
        <span className="font-medium">순위 범례:</span>
        <span><span className="text-yellow-500 font-bold">●</span> 1-3위 (최상위)</span>
        <span><span className="text-green-500 font-bold">●</span> 4-10위 (상위)</span>
        <span><span className="text-blue-500 font-bold">●</span> 11-20위 (중상위)</span>
        <span><span className="text-muted-foreground font-bold">●</span> 21-50위</span>
        <span><span className="text-orange-500 font-bold">●</span> 50위+ (하위)</span>
      </div>

      {/* 달성 가능성 점수 범례 */}
      <div className="flex flex-wrap gap-4 text-xs text-muted-foreground px-2 py-2 bg-muted/30 rounded-lg">
        <span className="font-medium">달성 가능성:</span>
        <span><span className="text-green-500 font-bold">●</span> 70점+ (높음)</span>
        <span><span className="text-yellow-500 font-bold">●</span> 50-69점 (보통)</span>
        <span><span className="text-orange-500 font-bold">●</span> 30-49점 (낮음)</span>
        <span><span className="text-red-500 font-bold">●</span> 30점 미만 (어려움)</span>
      </div>

      <div className="overflow-x-auto" role="region" aria-label="키워드 테이블">
        <table className="w-full table-auto text-sm" role="table">
        <thead>
          <tr className="border-b border-border">
            {enableSelection && (
              <th className="px-2 py-3 w-10">
                <input
                  type="checkbox"
                  checked={isAllCurrentPageSelected}
                  onChange={handleSelectAll}
                  className="w-4 h-4 rounded border-border cursor-pointer focus:ring-2 focus:ring-primary"
                  aria-label="전체 선택"
                />
              </th>
            )}
            <SortableHeader column="grade" className="w-16">등급</SortableHeader>
            <SortableHeader column="keyword" className="min-w-[180px]">키워드</SortableHeader>
            <SortableHeader column="current_rank" className="w-24">순위</SortableHeader>
            <SortableHeader column="likelihood_score" className="w-28">달성가능</SortableHeader>
            <SortableHeader column="search_volume" className="w-20">검색량</SortableHeader>
            <SortableHeader column="difficulty" className="w-24">난이도</SortableHeader>
            <SortableHeader column="opportunity" className="w-20">기회</SortableHeader>
            <SortableHeader column="trend_status" className="w-16">트렌드</SortableHeader>
            <SortableHeader column="category" className="w-24">카테고리</SortableHeader>
            <SortableHeader column="source" className="w-20">소스</SortableHeader>
            <th className="px-3 py-3 text-left text-sm font-medium text-muted-foreground whitespace-nowrap w-20">메모</th>
          </tr>
        </thead>
        <tbody>
          {paginatedKeywords.map((kw, index) => {
            const isSelected = selectedKeywords.has(kw.keyword)
            return (
            <tr
              key={`${kw.keyword}-${index}`}
              className={`
                border-b border-border
                transition-all duration-200 ease-out
                hover:bg-accent/50 hover:shadow-sm
                hover:border-l-2 hover:border-l-primary
                ${isSelected ? 'bg-primary/5 border-l-2 border-l-primary' : ''}
              `}
            >
              {enableSelection && (
                <td className="px-2 py-2 w-10">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => handleSelectOne(kw.keyword)}
                    className="w-4 h-4 rounded border-border cursor-pointer focus:ring-2 focus:ring-primary"
                    aria-label={`${kw.keyword} 선택`}
                  />
                </td>
              )}
              <td className="px-3 py-2 whitespace-nowrap">
                <span className={`font-bold ${gradeColors[kw.grade as keyof typeof gradeColors]}`}>
                  {gradeEmojis[kw.grade as keyof typeof gradeEmojis]} {kw.grade}
                </span>
              </td>
              <td className="px-3 py-2 font-medium min-w-[180px] whitespace-nowrap">
                <KeywordPopover
                  keyword={kw.keyword}
                  grade={kw.grade}
                  searchVolume={kw.search_volume}
                >
                  <span className="hover:text-primary hover:underline transition-colors">
                    {kw.keyword}
                  </span>
                </KeywordPopover>
              </td>
              <td className="px-3 py-2 whitespace-nowrap text-center">
                {kw.current_rank ? (
                  <span className={`font-bold ${
                    kw.current_rank <= 3 ? 'text-yellow-500' :
                    kw.current_rank <= 10 ? 'text-green-500' :
                    kw.current_rank <= 20 ? 'text-blue-500' :
                    kw.current_rank <= 50 ? 'text-muted-foreground' :
                    'text-orange-500'
                  }`}>
                    #{kw.current_rank}
                  </span>
                ) : (
                  <span className="text-muted-foreground/50 text-sm">-</span>
                )}
              </td>
              <td className="px-3 py-2 whitespace-nowrap">
                {kw.likelihood_score !== undefined ? (
                  <div className="flex items-center gap-1">
                    <div className="w-10 h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className={`h-full ${
                          kw.likelihood_score >= 70 ? 'bg-green-500' :
                          kw.likelihood_score >= 50 ? 'bg-yellow-500' :
                          kw.likelihood_score >= 30 ? 'bg-orange-500' :
                          'bg-red-500'
                        }`}
                        style={{ width: `${kw.likelihood_score}%` }}
                      />
                    </div>
                    <span className={`text-xs font-medium ${
                      kw.likelihood_score >= 70 ? 'text-green-500' :
                      kw.likelihood_score >= 50 ? 'text-yellow-500' :
                      kw.likelihood_score >= 30 ? 'text-orange-500' :
                      'text-red-500'
                    }`}>
                      {kw.likelihood_score}
                    </span>
                  </div>
                ) : (
                  <span className="text-muted-foreground/50 text-sm">-</span>
                )}
              </td>
              <td className="px-3 py-2 whitespace-nowrap text-sm">
                {kw.search_volume ? kw.search_volume.toLocaleString() : '-'}
              </td>
              <td className="px-3 py-2 whitespace-nowrap">
                <div className="flex items-center gap-1">
                  <div className="w-12 h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full ${
                        kw.difficulty <= 30 ? 'bg-green-500' :
                        kw.difficulty <= 50 ? 'bg-yellow-500' :
                        kw.difficulty <= 70 ? 'bg-orange-500' :
                        'bg-red-500'
                      }`}
                      style={{ width: `${kw.difficulty}%` }}
                    />
                  </div>
                  <span className="text-xs">{kw.difficulty}</span>
                </div>
              </td>
              <td className="px-3 py-2 whitespace-nowrap">
                <div className="flex items-center gap-1">
                  <div className="w-10 h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-green-500"
                      style={{ width: `${kw.opportunity}%` }}
                    />
                  </div>
                  <span className="text-xs">{kw.opportunity}</span>
                </div>
              </td>
              <td className="px-3 py-2 text-center">
                <span className="text-base">
                  {trendEmojis[kw.trend_status as keyof typeof trendEmojis]}
                </span>
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                {kw.category || '-'}
              </td>
              <td className="px-3 py-2">
                <span className="text-xs px-1.5 py-0.5 rounded bg-muted whitespace-nowrap">
                  {kw.source}
                </span>
              </td>
              <td className="px-3 py-2">
                <KeywordMemoEditor
                  keyword={kw.keyword}
                  memo={kw.memo || ''}
                  userTags={kw.user_tags || []}
                />
              </td>
            </tr>
          )})}
        </tbody>
      </table>
      </div>

      {/* 페이지네이션 */}
      {keywords.length > pageSize && (
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          onPageChange={setCurrentPage}
          pageSize={pageSize}
          pageSizeOptions={[25, 50, 100]}
          onPageSizeChange={handlePageSizeChange}
          totalItems={keywords.length}
        />
      )}
    </div>
  )
}

// [성능 최적화] memo로 keywords가 변경될 때만 리렌더링
const KeywordTable = memo(KeywordTableComponent, (prevProps, nextProps) => {
  return (
    prevProps.keywords === nextProps.keywords &&
    prevProps.showExport === nextProps.showExport &&
    prevProps.initialPageSize === nextProps.initialPageSize &&
    prevProps.enableSelection === nextProps.enableSelection
  )
})

export default KeywordTable

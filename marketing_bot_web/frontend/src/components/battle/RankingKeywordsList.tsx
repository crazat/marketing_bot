import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, X, Download, MessageSquare, Check, Edit2, Trash2 } from 'lucide-react'
import EmptyState from '@/components/ui/EmptyState'
import Pagination from '@/components/ui/Pagination'
import { useToast } from '@/components/ui/Toast'
import { ResultsAnnouncer } from '@/components/ui/LiveRegion'
import { ConfirmModal } from '@/components/ui/Modal'
import { exportToCSV, RANKING_KEYWORD_EXPORT_COLUMNS } from '@/utils/export'
import Button, { IconButton } from '@/components/ui/Button'

interface RankingKeyword {
  keyword: string
  current_rank: number
  target_rank: number
  rank_change: number
  search_volume?: number
  category: string
  status: string
  decline_streak?: number
  decline_amount?: number
  is_declining?: boolean
}

interface RankingKeywordsListProps {
  keywords: RankingKeyword[]
  onRemove: (keyword: string) => void
  onEdit?: (keyword: string, category: string) => void
  onAdd?: () => void
  onUpdateTargetRank?: (keyword: string, targetRank: number) => void
}

export default function RankingKeywordsList({ keywords, onRemove, onEdit, onAdd, onUpdateTargetRank }: RankingKeywordsListProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [editingTargetKeyword, setEditingTargetKeyword] = useState<string | null>(null)
  const [editingTargetValue, setEditingTargetValue] = useState<number>(10)
  const [statusFilter, setStatusFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [keywordToDelete, setKeywordToDelete] = useState<string | null>(null)
  const toast = useToast()
  const navigate = useNavigate()

  // [Phase 8.0] 바이럴 콘텐츠 찾기
  const handleFindViral = (keyword: string) => {
    navigate(`/viral?keyword=${encodeURIComponent(keyword)}`)
  }

  // 카테고리 목록 추출
  const categories = useMemo(() => {
    const cats = new Set(keywords.map(k => k.category).filter(Boolean))
    return Array.from(cats).sort()
  }, [keywords])

  // 하락 추세 키워드 수 계산
  const decliningCount = useMemo(() => {
    return keywords.filter(kw => kw.is_declining).length
  }, [keywords])

  // 필터링된 키워드
  const filteredKeywords = useMemo(() => {
    return keywords.filter(kw => {
      // 검색어 필터
      if (searchQuery && !kw.keyword.toLowerCase().includes(searchQuery.toLowerCase())) {
        return false
      }
      // 상태 필터
      if (statusFilter) {
        if (statusFilter === 'declining') {
          // 하락 추세 필터
          if (!kw.is_declining) return false
        } else if (kw.status !== statusFilter) {
          return false
        }
      }
      // 카테고리 필터
      if (categoryFilter && kw.category !== categoryFilter) {
        return false
      }
      return true
    })
  }, [keywords, searchQuery, statusFilter, categoryFilter])

  // 페이지네이션 계산
  const totalPages = Math.ceil(filteredKeywords.length / pageSize)
  const paginatedKeywords = filteredKeywords.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  )

  // 필터 변경 시 첫 페이지로
  const handleFilterChange = () => {
    setCurrentPage(1)
  }

  const handleClearFilters = () => {
    setSearchQuery('')
    setStatusFilter('')
    setCategoryFilter('')
    setCurrentPage(1)
  }

  const hasActiveFilters = searchQuery || statusFilter || categoryFilter

  const handleExport = () => {
    const timestamp = new Date().toISOString().slice(0, 10)
    const dataToExport = hasActiveFilters ? filteredKeywords : keywords
    exportToCSV(dataToExport, RANKING_KEYWORD_EXPORT_COLUMNS, `ranking_keywords_${timestamp}.csv`)
    toast.success(`${dataToExport.length}개 키워드를 CSV로 내보냈습니다`)
  }

  if (!keywords || keywords.length === 0) {
    return (
      <EmptyState
        icon="🎯"
        title="추적 중인 키워드가 없습니다"
        description="새로운 키워드를 추가하여 네이버 플레이스 순위를 추적하세요."
        action={onAdd ? { label: '키워드 추가', onClick: onAdd } : undefined}
      />
    )
  }

  // 상태별 스타일 및 텍스트
  const getStatusInfo = (status: string) => {
    switch (status) {
      case 'scanned':
        return { label: '추적 중', bgClass: 'bg-green-500/20', textClass: 'text-green-500' }
      case 'not_found':
        return { label: '순위권 밖', bgClass: 'bg-orange-500/20', textClass: 'text-orange-500' }
      case 'error':
        return { label: '스캔 오류', bgClass: 'bg-red-500/20', textClass: 'text-red-500' }
      case 'pending':
      default:
        return { label: '대기 중', bgClass: 'bg-yellow-500/20', textClass: 'text-yellow-500' }
    }
  }

  return (
    <div className="space-y-4">
      {/* 스크린 리더용 결과 알림 */}
      <ResultsAnnouncer
        count={filteredKeywords.length}
        itemName="키워드"
      />

      {/* 검색 및 필터 */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* 검색창 */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="키워드 검색..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
              handleFilterChange()
            }}
            className="w-full pl-10 pr-10 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
          {searchQuery && (
            <IconButton
              icon={<X className="w-4 h-4" />}
              onClick={() => {
                setSearchQuery('')
                handleFilterChange()
              }}
              size="sm"
              className="absolute right-3 top-1/2 -translate-y-1/2"
              title="검색어 지우기"
            />
          )}
        </div>

        {/* 상태 필터 */}
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value)
            handleFilterChange()
          }}
          className="px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <option value="">모든 상태</option>
          <option value="scanned">추적 중</option>
          <option value="declining">⚠️ 하락 추세</option>
          <option value="pending">대기 중</option>
          <option value="not_found">순위권 밖</option>
          <option value="error">오류</option>
        </select>

        {/* 카테고리 필터 */}
        {categories.length > 0 && (
          <select
            value={categoryFilter}
            onChange={(e) => {
              setCategoryFilter(e.target.value)
              handleFilterChange()
            }}
            className="px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">모든 카테고리</option>
            {categories.map(cat => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </select>
        )}

        {/* 필터 초기화 */}
        {hasActiveFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleClearFilters}
          >
            필터 초기화
          </Button>
        )}

        {/* CSV 내보내기 */}
        <Button
          variant="outline"
          size="sm"
          onClick={handleExport}
          icon={<Download className="w-4 h-4" />}
          title={hasActiveFilters ? `필터된 ${filteredKeywords.length}개 내보내기` : `전체 ${keywords.length}개 내보내기`}
        >
          <span className="hidden sm:inline">
            CSV ({hasActiveFilters ? filteredKeywords.length : keywords.length}개)
          </span>
        </Button>
      </div>

      {/* 결과 요약 */}
      {hasActiveFilters && (
        <div className="text-sm text-muted-foreground">
          {filteredKeywords.length}개 결과 (전체 {keywords.length}개 중)
        </div>
      )}

      {/* 필터 결과가 없을 때 */}
      {filteredKeywords.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-4xl mb-4">🔍</p>
          <p>검색 결과가 없습니다.</p>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleClearFilters}
            className="mt-4"
          >
            필터 초기화
          </Button>
        </div>
      ) : (
      <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border">
            <th className="px-4 py-3 text-left text-sm font-semibold">키워드</th>
            <th className="px-4 py-3 text-left text-sm font-semibold">현재 순위</th>
            <th className="px-4 py-3 text-left text-sm font-semibold">목표 순위</th>
            <th className="px-4 py-3 text-left text-sm font-semibold">변화</th>
            <th className="px-4 py-3 text-left text-sm font-semibold">검색량</th>
            <th className="px-4 py-3 text-left text-sm font-semibold">카테고리</th>
            <th className="px-4 py-3 text-left text-sm font-semibold">상태</th>
            <th className="px-4 py-3 text-left text-sm font-semibold">액션</th>
          </tr>
        </thead>
        <tbody>
          {paginatedKeywords.map((kw, index) => {
            const rankDiff = kw.rank_change || 0
            const isImproving = rankDiff > 0
            const isDeclining = rankDiff < 0
            const statusInfo = getStatusInfo(kw.status)
            const hasRank = kw.status === 'scanned' && kw.current_rank > 0

            return (
              <tr
                key={kw.keyword ?? `row-${index}`}
                className={`
                  border-b border-border
                  transition-all duration-200 ease-out
                  hover:bg-accent/50 hover:shadow-sm
                  hover:border-l-2 hover:border-l-primary
                  ${kw.status === 'pending' ? 'bg-yellow-500/5' :
                    kw.status === 'not_found' ? 'bg-orange-500/5' :
                    kw.status === 'error' ? 'bg-red-500/5' : ''}
                `}
              >
                <td className="px-4 py-3 font-medium">
                  <div className="flex items-center gap-2">
                    <span>{kw.keyword}</span>
                    {kw.is_declining && (
                      <span
                        className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-red-500/20 text-red-500 animate-pulse"
                        title={`${kw.decline_streak}일 연속 하락 (총 ${kw.decline_amount}순위 하락)`}
                      >
                        ⚠️ {kw.decline_streak}일↘
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">
                  {hasRank ? (
                    <span className={`
                      text-2xl font-bold
                      ${kw.current_rank <= 3 ? 'text-yellow-500' :
                        kw.current_rank <= 10 ? 'text-green-500' :
                        kw.current_rank <= 20 ? 'text-blue-500' :
                        'text-muted-foreground'
                      }
                    `}>
                      #{kw.current_rank}
                    </span>
                  ) : kw.status === 'not_found' ? (
                    <span className="text-sm text-orange-500 font-medium">
                      100위 밖
                    </span>
                  ) : kw.status === 'error' ? (
                    <span className="text-sm text-red-500 font-medium">
                      오류
                    </span>
                  ) : (
                    <span className="text-sm text-yellow-500 font-medium">
                      스캔 대기
                    </span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      {/* 목표 순위 수정 UI */}
                      {editingTargetKeyword === kw.keyword ? (
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            min={1}
                            max={100}
                            value={editingTargetValue}
                            onChange={(e) => setEditingTargetValue(Math.max(1, Math.min(100, parseInt(e.target.value) || 1)))}
                            className="w-14 px-2 py-1 text-sm border border-border rounded bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                onUpdateTargetRank?.(kw.keyword, editingTargetValue)
                                setEditingTargetKeyword(null)
                                toast.success(`"${kw.keyword}" 목표 순위가 ${editingTargetValue}위로 설정되었습니다`)
                              } else if (e.key === 'Escape') {
                                setEditingTargetKeyword(null)
                              }
                            }}
                          />
                          <IconButton
                            icon={<Check className="w-4 h-4" />}
                            onClick={() => {
                              onUpdateTargetRank?.(kw.keyword, editingTargetValue)
                              setEditingTargetKeyword(null)
                              toast.success(`"${kw.keyword}" 목표 순위가 ${editingTargetValue}위로 설정되었습니다`)
                            }}
                            size="sm"
                            className="text-green-500 hover:bg-green-500/10"
                            title="저장"
                          />
                          <IconButton
                            icon={<X className="w-4 h-4" />}
                            onClick={() => setEditingTargetKeyword(null)}
                            size="sm"
                            className="text-red-500 hover:bg-red-500/10"
                            title="취소"
                          />
                        </div>
                      ) : (
                        <button
                          onClick={() => {
                            setEditingTargetKeyword(kw.keyword)
                            setEditingTargetValue(kw.target_rank)
                          }}
                          className="text-muted-foreground hover:text-foreground hover:bg-muted px-1.5 py-0.5 rounded transition-colors"
                          title="클릭하여 목표 순위 수정"
                        >
                          #{kw.target_rank}
                        </button>
                      )}
                      {/* 목표 달성 여부 표시 */}
                      {editingTargetKeyword !== kw.keyword && hasRank && (
                        kw.current_rank <= kw.target_rank ? (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-green-500/20 text-green-500" title="목표 달성!">
                            ✓ 달성
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground" title={`목표까지 ${kw.current_rank - kw.target_rank}순위 남음`}>
                            (-{kw.current_rank - kw.target_rank})
                          </span>
                        )
                      )}
                    </div>
                    {/* [Phase 8.0] 목표 달성 게이지 */}
                    {hasRank && kw.current_rank > kw.target_rank && (
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden max-w-[80px]">
                          {(() => {
                            // 목표 대비 진행률 계산 (100위 기준에서 목표까지의 진행률)
                            const maxRank = 100
                            const progress = Math.max(0, Math.min(100,
                              ((maxRank - kw.current_rank) / (maxRank - kw.target_rank)) * 100
                            ))
                            return (
                              <div
                                className={`h-full transition-all ${
                                  progress >= 80 ? 'bg-green-500' :
                                  progress >= 50 ? 'bg-yellow-500' :
                                  progress >= 25 ? 'bg-orange-500' :
                                  'bg-red-500'
                                }`}
                                style={{ width: `${progress}%` }}
                                title={`목표 달성률: ${progress.toFixed(0)}%`}
                              />
                            )
                          })()}
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {(() => {
                            const maxRank = 100
                            const progress = Math.max(0, Math.min(100,
                              ((maxRank - kw.current_rank) / (maxRank - kw.target_rank)) * 100
                            ))
                            return `${progress.toFixed(0)}%`
                          })()}
                        </span>
                      </div>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">
                  {hasRank && rankDiff !== 0 ? (
                    <span className={`
                      flex items-center gap-1 text-sm font-medium
                      ${isImproving ? 'text-green-500' : isDeclining ? 'text-red-500' : ''}
                    `}>
                      {isImproving ? '↗️' : isDeclining ? '↘️' : ''}
                      {Math.abs(rankDiff)}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">-</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {kw.search_volume?.toLocaleString() || '-'}
                </td>
                <td className="px-4 py-3">
                  <span className="text-xs px-2 py-1 rounded-full bg-muted">
                    {kw.category}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-1 rounded-full ${statusInfo.bgClass} ${statusInfo.textClass}`}>
                    {statusInfo.label}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1">
                    {/* [Phase 8.0] 바이럴 찾기 버튼 - 하락 추세에 강조 */}
                    <IconButton
                      icon={<MessageSquare className="w-4 h-4" />}
                      onClick={() => handleFindViral(kw.keyword)}
                      size="sm"
                      className={
                        kw.is_declining || isDeclining
                          ? 'text-orange-500 bg-orange-500/20 hover:bg-orange-500/30 animate-pulse'
                          : 'text-orange-500 hover:text-orange-700 hover:bg-orange-500/10'
                      }
                      title={kw.is_declining ? '바이럴 대응 필요!' : '관련 바이럴 콘텐츠 찾기'}
                      aria-label={`${kw.keyword} 바이럴 콘텐츠 찾기`}
                    />
                    {onEdit && (
                      <IconButton
                        icon={<Edit2 className="w-4 h-4" />}
                        onClick={() => onEdit(kw.keyword, kw.category)}
                        size="sm"
                        className="text-blue-500 hover:text-blue-700 hover:bg-blue-500/10"
                        title="키워드 수정"
                        aria-label={`${kw.keyword} 키워드 수정`}
                      />
                    )}
                    <IconButton
                      icon={<Trash2 className="w-4 h-4" />}
                      onClick={() => setKeywordToDelete(kw.keyword)}
                      size="sm"
                      className="text-red-500 hover:text-red-700 hover:bg-red-500/10"
                      title="키워드 삭제"
                      aria-label={`${kw.keyword} 키워드 삭제`}
                    />
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {/* 상태별 안내 메시지 */}
      {decliningCount > 0 && !statusFilter && (
        <div className="mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
          <p className="text-sm text-red-500 flex items-center flex-wrap gap-2">
            <span className="font-medium">🚨 주의:</span> {decliningCount}개 키워드가 연속 하락 추세입니다.
            <Button
              variant="ghost"
              size="xs"
              onClick={() => setStatusFilter('declining')}
              className="text-red-500 hover:text-red-600"
            >
              하락 추세 키워드만 보기
            </Button>
          </p>
          <p className="text-xs text-red-400 mt-2 flex items-center flex-wrap gap-1">
            💡 <span className="font-medium">팁:</span> 하락 추세 키워드에 대해 바이럴 댓글 활동을 강화하면 순위 회복에 도움이 됩니다.
            <Button
              variant="ghost"
              size="xs"
              onClick={() => navigate('/viral')}
              className="text-red-400 hover:text-red-500"
            >
              Viral Hunter로 이동
            </Button>
          </p>
        </div>
      )}

      {paginatedKeywords.some(kw => kw.status === 'pending') && (
        <div className="mt-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
          <p className="text-sm text-yellow-500">
            <span className="font-medium">💡 팁:</span> "대기 중" 키워드는 순위 스캔을 실행하면 순위가 업데이트됩니다.
          </p>
        </div>
      )}

      {paginatedKeywords.some(kw => kw.status === 'not_found') && (
        <div className="mt-4 p-3 bg-orange-500/10 border border-orange-500/30 rounded-lg">
          <p className="text-sm text-orange-500">
            <span className="font-medium">⚠️ 참고:</span> "순위권 밖" 키워드는 네이버 플레이스 검색 결과 상위 100위 안에 우리 업체가 없는 키워드입니다.
          </p>
        </div>
      )}

      {/* 페이지네이션 */}
      {filteredKeywords.length > pageSize && (
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          onPageChange={setCurrentPage}
          pageSize={pageSize}
          pageSizeOptions={[25, 50, 100]}
          onPageSizeChange={(size) => {
            setPageSize(size)
            setCurrentPage(1)
          }}
          totalItems={filteredKeywords.length}
        />
      )}
    </div>
      )}

      {/* 키워드 삭제 확인 모달 */}
      <ConfirmModal
        isOpen={keywordToDelete !== null}
        onClose={() => setKeywordToDelete(null)}
        onConfirm={() => {
          if (keywordToDelete) {
            onRemove(keywordToDelete)
            toast.success(`"${keywordToDelete}" 키워드가 삭제되었습니다`)
            setKeywordToDelete(null)
          }
        }}
        title="키워드 삭제"
        message={`"${keywordToDelete}" 키워드를 삭제하시겠습니까?\n\n⚠️ 이 키워드의 모든 순위 기록이 함께 삭제됩니다. 삭제된 데이터는 복구할 수 없습니다.`}
        confirmText="삭제"
        variant="danger"
      />
    </div>
  )
}

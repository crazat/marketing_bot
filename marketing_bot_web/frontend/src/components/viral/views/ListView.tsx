/**
 * Viral Hunter - 전체 목록 화면
 * 테이블 형식 전체 관리, 대량 처리
 * [성능 개선] @tanstack/react-virtual로 가상화 적용
 */

import { useRef, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useVirtualizer } from '@tanstack/react-virtual'
import Button from '@/components/ui/Button'
import Modal, { ConfirmModal } from '@/components/ui/Modal'
import { safeUrl } from '@/utils/safeUrl'
import Pagination from '@/components/ui/Pagination'
import { FilterBar, FilterState, ScanBatch } from '@/components/viral/FilterBar'
import { SmartFilterBar } from '@/components/viral/SmartFilterBar'
import { BulkActionBar } from '@/components/viral/BulkActionBar'
import { PlatformBadge } from '@/components/viral/PlatformBadge'
import { CategoryBadge } from '@/components/viral/CategoryBadge'
import { EngagementMetrics } from '@/components/viral/EngagementMetrics'
import { ScanCountBadge } from '@/components/viral/ScanCountBadge'
import { AIClassificationMini } from '@/components/viral/AIClassificationBadge'
import { TargetSkeleton } from '@/components/viral/TargetSkeleton'
import { EmptyState } from '@/components/viral/EmptyState'
import { ViralTargetData, autoCategorize } from '@/types/viral'
import { formatRelativeTime, formatDateTime } from '@/utils/dateFormat'
import { viralApi, exportApi } from '@/services/api'

interface LeadTrackingModalState {
  isOpen: boolean
  targetTitle: string
  leadCreated: boolean
}

interface ListViewProps {
  // 데이터
  filters: FilterState
  scanBatches: ScanBatch[]
  displayTargets: ViralTargetData[]
  allTargets?: ViralTargetData[]
  selectedTargets: Set<string>
  isLoadingFiltered: boolean
  isRefreshing?: boolean  // [UX 개선] 백그라운드 새로고침 상태

  // 페이지네이션
  currentPage: number
  totalPages: number
  totalItems: number
  pageSize: number

  // 검증
  isVerifying: boolean
  verifyProgress?: {
    status: 'queued' | 'running' | 'done' | 'error'
    total: number
    commentable: number
    not_commentable: number
  } | null
  verifyLimit: number
  verifyResults: {
    total: number
    commentable: number
    not_commentable: number
  } | null

  // 대량 처리
  isProcessingBulk: boolean
  isGeneratingComments: boolean
  generationProgress: { current: number; total: number } | null
  bulkActionConfirm: { action: 'approve' | 'skip' | 'delete'; count: number } | null

  // 리드 추적 모달
  leadTrackingModal: LeadTrackingModalState

  // 핸들러
  onGoHome: () => void
  onFilterChange: (filters: FilterState) => void
  onFilterReset: () => void
  onVerifyLimitChange: (limit: number) => void
  onBatchVerify: (category: string | undefined, limit: number) => void
  onToggleSelect: (targetId: string) => void
  onToggleSelectAll: () => void
  onBulkAction: (action: 'approve' | 'skip' | 'delete') => void
  onBulkActionAll: (action: 'approve' | 'skip' | 'delete') => void  // [F3] 필터 매칭 전체
  onBulkGenerateComments: () => void
  onClearSelection: () => void
  onSetExpandedTargetId: (targetId: string | null) => void
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
  onSetBulkActionConfirm: (confirm: { action: 'approve' | 'skip' | 'delete'; count: number } | null) => void
  onExecuteBulkAction: () => void
  onSetLeadTrackingModal: (fn: (prev: LeadTrackingModalState) => LeadTrackingModalState) => void
  toast: {
    success: (msg: string) => void
    error: (msg: string) => void
    warning: (msg: string) => void
  }
}

export function ListView({
  filters,
  scanBatches,
  displayTargets,
  allTargets: _allTargets,
  selectedTargets,
  isLoadingFiltered,
  isRefreshing = false,
  currentPage,
  totalPages,
  totalItems,
  pageSize,
  isVerifying,
  verifyProgress,
  verifyLimit,
  verifyResults,
  isProcessingBulk,
  isGeneratingComments,
  generationProgress,
  bulkActionConfirm,
  leadTrackingModal,
  onGoHome,
  onFilterChange,
  onFilterReset,
  onVerifyLimitChange,
  onBatchVerify,
  onToggleSelect,
  onToggleSelectAll,
  onBulkAction,
  onBulkActionAll,
  onBulkGenerateComments,
  onClearSelection,
  onSetExpandedTargetId,
  onPageChange,
  onPageSizeChange,
  onSetBulkActionConfirm,
  onExecuteBulkAction,
  onSetLeadTrackingModal,
  toast,
}: ListViewProps) {
  const navigate = useNavigate()
  const isAllSelected = displayTargets.length > 0 && selectedTargets.size === displayTargets.length

  // [성능 개선] 가상화를 위한 스크롤 컨테이너 참조
  const tableContainerRef = useRef<HTMLDivElement>(null)

  // 생성된 댓글 미리보기 모달
  const [commentPreview, setCommentPreview] = useState<{
    targetId: string
    targetTitle: string
    comment: string
  } | null>(null)

  // 행 높이 추정치 (실제 콘텐츠에 따라 동적)
  const ROW_HEIGHT = 120

  // 가상화 설정
  const rowVirtualizer = useVirtualizer({
    count: displayTargets.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 5, // 화면 위아래로 5개 항목 추가 렌더링
  })

  // 카테고리 계산을 메모이제이션하여 불필요한 재계산 방지
  const getCategoryMemo = useMemo(() => {
    const cache = new Map<string, string>()
    return (target: ViralTargetData) => {
      const cacheKey = `${target.id}-${target.title}`
      if (!cache.has(cacheKey)) {
        const keywords = Array.isArray(target.matched_keywords) ? target.matched_keywords : []
        cache.set(cacheKey, autoCategorize(target.title || '', keywords))
      }
      return cache.get(cacheKey)!
    }
  }, [displayTargets])

  return (
    <div className="space-y-0">
      {/* 헤더 */}
      <div className="flex items-center gap-4 p-6 bg-card border-b border-border">
        <Button onClick={onGoHome} variant="outline">
          ← 홈으로
        </Button>
        <div>
          <h1 className="text-3xl font-bold">📋 일괄 작업 모드</h1>
          <p className="text-xs text-muted-foreground mt-1">
            여러 카테고리를 가로질러 필터링 · 일괄 승인/스킵/삭제 — 카테고리별 개별 작업은 홈에서 카테고리 선택
          </p>
        </div>
        <div className="ml-auto flex items-center gap-4">
          <Button
            onClick={() => {
              exportApi.downloadViralTargets({
                status: filters.status !== 'all' ? filters.status : undefined,
              })
            }}
            variant="success"
            size="sm"
            title="바이럴 타겟을 Excel로 내보내기"
          >
            📥 Excel 내보내기
          </Button>
          <div className="text-xs text-muted-foreground">
            단축키:{' '}
            <kbd className="px-1 py-0.5 bg-muted border border-border rounded">Ctrl+A</kbd> 전체 선택,{' '}
            <kbd className="px-1 py-0.5 bg-muted border border-border rounded">A</kbd> 승인,{' '}
            <kbd className="px-1 py-0.5 bg-muted border border-border rounded">S</kbd> 건너뛰기,{' '}
            <kbd className="px-1 py-0.5 bg-muted border border-border rounded">D</kbd> 삭제,{' '}
            <kbd className="px-1 py-0.5 bg-muted border border-border rounded">Esc</kbd> 해제
          </div>
          <div className="text-sm text-muted-foreground flex items-center gap-2">
            {isLoadingFiltered ? '로딩 중...' : `${displayTargets.length}개 타겟`}
            {/* [UX 개선] 백그라운드 새로고침 인디케이터 */}
            {isRefreshing && !isLoadingFiltered && (
              <span className="flex items-center gap-1 text-xs text-blue-500">
                <span className="animate-spin rounded-full h-3 w-3 border-b-2 border-blue-500" />
                새로고침...
              </span>
            )}
            {selectedTargets.size > 0 && (
              <span className="ml-2 text-blue-600 font-semibold">({selectedTargets.size}개 선택)</span>
            )}
          </div>
        </div>
      </div>

      {/* 스마트 필터 */}
      <SmartFilterBar
        onApplyFilter={(filter) => onFilterChange({ ...filters, ...filter })}
        onSelectTarget={(targetId) => onSetExpandedTargetId(targetId)}
      />

      {/* 필터 바 */}
      <FilterBar
        filters={filters}
        onFilterChange={onFilterChange}
        onReset={onFilterReset}
        scanBatches={scanBatches}
      />

      {/* 일괄 검증 + 대량 액션 바 */}
      <div className="flex items-center gap-4 p-4 bg-muted/30 border border-border rounded-lg">
        <div className="flex items-center gap-2">
          <select
            value={verifyLimit}
            onChange={(e) => onVerifyLimitChange(Number(e.target.value))}
            className="px-2 py-1.5 bg-background border border-border rounded text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            disabled={isVerifying}
          >
            <option value={20}>20개</option>
            <option value={50}>50개</option>
            <option value={100}>100개</option>
            <option value={0}>전체</option>
          </select>
          <Button
            onClick={() => onBatchVerify(undefined, verifyLimit)}
            loading={isVerifying}
            className="bg-blue-500 hover:bg-blue-600"
          >
            🔍 일괄 검증
          </Button>
        </div>
        {/* [F5][U4] 검증 진행 상태 — 단계별 구체 메시지 */}
        {isVerifying && verifyProgress && (() => {
          const processed = verifyProgress.commentable + verifyProgress.not_commentable
          const ratio = verifyProgress.total > 0 ? processed / verifyProgress.total : 0
          const statusMsg =
            verifyProgress.status === 'queued'
              ? '큐 대기 중 — 백엔드 워커 할당 중'
              : ratio < 0.25
              ? 'Selenium 브라우저 시작 중…'
              : ratio < 0.7
              ? '댓글창 접근 가능 여부 확인 중…'
              : ratio < 1
              ? '마지막 타겟 검증 중…'
              : '결과 집계 중…'
          return (
            <div className="flex flex-col gap-1 text-sm text-blue-600 dark:text-blue-400">
              <div className="flex items-center gap-2">
                <span className="animate-pulse">●</span>
                <span>{statusMsg}</span>
                {verifyProgress.total > 0 && (
                  <span className="text-xs text-muted-foreground tabular-nums ml-1">
                    · {processed}/{verifyProgress.total} (✓{verifyProgress.commentable} ✗{verifyProgress.not_commentable})
                  </span>
                )}
              </div>
              {verifyProgress.total > 0 && (
                <div className="w-48 h-1 bg-muted overflow-hidden">
                  <div
                    className="h-full bg-blue-500 transition-all duration-500"
                    style={{ width: `${ratio * 100}%` }}
                  />
                </div>
              )}
            </div>
          )
        })()}
        {verifyResults && !isVerifying && (
          <div className="flex items-center gap-3 text-sm">
            <span className="text-muted-foreground">결과:</span>
            <span className="text-green-500 font-medium">✓ {verifyResults.commentable}</span>
            <span className="text-red-500 font-medium">✗ {verifyResults.not_commentable}</span>
          </div>
        )}
        <div className="flex-1" />
        <BulkActionBar
          selectedCount={selectedTargets.size}
          totalCount={displayTargets.length}
          onApprove={() => onBulkAction('approve')}
          onSkip={() => onBulkAction('skip')}
          onDelete={() => onBulkAction('delete')}
          onGenerateComments={onBulkGenerateComments}
          onClearSelection={onClearSelection}
          isProcessing={isProcessingBulk}
          isGenerating={isGeneratingComments}
          generationProgress={generationProgress || undefined}
        />
      </div>

      {/* [F3] 필터 매칭 전체 대량 액션 바 (현재 페이지를 넘는 경우) */}
      {totalItems > displayTargets.length && (
        <div className="flex flex-wrap items-center gap-2 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/40 rounded-lg px-3 py-2 text-sm">
          <span className="text-amber-800 dark:text-amber-300">
            ⚠️ 필터 매칭 <strong>{totalItems.toLocaleString()}건</strong> 전체 일괄 처리
          </span>
          <span className="text-xs text-amber-700 dark:text-amber-400">
            (현재 페이지 {displayTargets.length}건 외 {(totalItems - displayTargets.length).toLocaleString()}건 포함)
          </span>
          <div className="flex-1" />
          <button
            onClick={() => onBulkActionAll('approve')}
            disabled={isProcessingBulk}
            className="px-3 py-1 rounded bg-green-500/90 text-white hover:bg-green-500 disabled:opacity-40 text-xs"
          >
            전체 승인
          </button>
          <button
            onClick={() => onBulkActionAll('skip')}
            disabled={isProcessingBulk}
            className="px-3 py-1 rounded bg-amber-500/90 text-white hover:bg-amber-500 disabled:opacity-40 text-xs"
          >
            전체 스킵
          </button>
          <button
            onClick={() => onBulkActionAll('delete')}
            disabled={isProcessingBulk}
            className="px-3 py-1 rounded bg-red-500/90 text-white hover:bg-red-500 disabled:opacity-40 text-xs"
          >
            전체 삭제
          </button>
        </div>
      )}

      {/* 타겟 목록 테이블 */}
      <div className="bg-card border-t-0 rounded-b-lg overflow-hidden">
        {isLoadingFiltered ? (
          <div className="p-6">
            <TargetSkeleton count={5} />
          </div>
        ) : displayTargets.length === 0 ? (
          <div className="p-6">
            <EmptyState
              type={filters.search || filters.platforms?.length || filters.min_scan_count ? 'no-results' : 'no-targets'}
              onAction={() => {
                if (filters.search || filters.platforms?.length || filters.min_scan_count) {
                  onFilterReset()
                } else {
                  onGoHome()
                }
              }}
            />
          </div>
        ) : (
          /* [성능 개선] 가상화된 테이블 - 화면에 보이는 행만 렌더링 */
          <div
            ref={tableContainerRef}
            className="overflow-auto max-h-[calc(100vh-400px)] min-h-[400px]"
          >
            <table className="w-full">
              <thead className="bg-muted border-b border-border sticky top-0 z-10">
                <tr>
                  <th className="px-4 py-3 w-12">
                    <input
                      type="checkbox"
                      checked={isAllSelected}
                      onChange={onToggleSelectAll}
                      className="w-4 h-4 text-primary rounded focus:ring-2 focus:ring-primary cursor-pointer"
                    />
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">플랫폼</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">제목/내용</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">카테고리</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold" title="AI가 분류한 글 성격 + 미용 특화 매칭">AI 판정</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">참여도</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">우선순위</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">재발견</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">게시 상태</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">발견 시간</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold">액션</th>
                </tr>
              </thead>
              <tbody
                className="relative"
                style={{ height: `${rowVirtualizer.getTotalSize()}px` }}
              >
                {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                  const target = displayTargets[virtualRow.index]
                  const category = getCategoryMemo(target)
                  const isSelected = selectedTargets.has(target.id)
                  const keywords = Array.isArray(target.matched_keywords) ? target.matched_keywords : []

                  return (
                    <tr
                      key={target.id || virtualRow.index}
                      data-index={virtualRow.index}
                      ref={rowVirtualizer.measureElement}
                      className={`absolute w-full hover:bg-muted/50 transition-colors border-b border-border ${isSelected ? 'bg-primary/10' : ''}`}
                      style={{
                        transform: `translateY(${virtualRow.start}px)`,
                      }}
                    >
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => onToggleSelect(target.id)}
                          className="w-4 h-4 text-primary rounded focus:ring-2 focus:ring-primary cursor-pointer"
                        />
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <PlatformBadge platform={target.platform} size="sm" />
                      </td>
                      <td className="px-4 py-3 text-sm max-w-md">
                        <div className="font-medium truncate mb-1" title={target.title}>
                          {target.title || '제목 없음'}
                        </div>
                        {target.content_preview && (
                          <div className="text-xs text-muted-foreground truncate mb-1" title={target.content_preview}>
                            {target.content_preview}
                          </div>
                        )}
                        <a
                          href={safeUrl(target.url)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-primary hover:underline truncate block"
                          title={target.url}
                        >
                          {target.url}
                        </a>
                        {keywords.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1">
                            {keywords.slice(0, 3).map((kw, i) => (
                              <span
                                key={i}
                                className="inline-block px-1.5 py-0.5 bg-muted text-muted-foreground rounded text-xs"
                              >
                                {kw}
                              </span>
                            ))}
                            {keywords.length > 3 && (
                              <span className="text-xs text-muted-foreground">+{keywords.length - 3}</span>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <CategoryBadge category={category} size="sm" />
                      </td>
                      <td className="px-4 py-3 text-sm text-center">
                        <div className="flex flex-col items-center gap-0.5">
                          <AIClassificationMini
                            label={target.ai_ad_label}
                            confidence={target.ai_ad_confidence}
                            specialtyMatch={target.specialty_match}
                          />
                          {target.ai_ad_confidence != null && target.ai_ad_label === '자연_질문' && (
                            <span
                              className="text-[10px] text-muted-foreground"
                              title={target.ai_ad_reason || ''}
                            >
                              {Math.round(target.ai_ad_confidence * 100)}%
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm text-center">
                        <EngagementMetrics
                          likes={target.like_count}
                          comments={target.comment_count}
                          views={target.view_count}
                          size="sm"
                        />
                      </td>
                      <td className="px-4 py-3 text-sm text-center">
                        <div className="font-bold text-foreground">{target.priority_score?.toFixed(0) || 0}</div>
                        <div className="text-xs text-muted-foreground">점</div>
                      </td>
                      <td className="px-4 py-3 text-sm text-center">
                        <ScanCountBadge scanCount={target.scan_count || 1} lastScannedAt={target.last_scanned_at} />
                      </td>
                      <td className="px-4 py-3 text-sm text-center">
                        {(() => {
                          const status = target.comment_status || 'pending'
                          const statusConfig: Record<string, { label: string; bgClass: string; textClass: string }> = {
                            pending: { label: '대기', bgClass: 'bg-gray-500/20', textClass: 'text-gray-500' },
                            generated: { label: '생성됨', bgClass: 'bg-blue-500/20', textClass: 'text-blue-500' },
                            approved: { label: '승인됨', bgClass: 'bg-yellow-500/20', textClass: 'text-yellow-500' },
                            posted: { label: '게시됨', bgClass: 'bg-green-500/20', textClass: 'text-green-500' },
                            skipped: { label: '건너뜀', bgClass: 'bg-orange-500/20', textClass: 'text-orange-500' },
                            failed: { label: '실패', bgClass: 'bg-red-500/20', textClass: 'text-red-500' },
                          }
                          const config = statusConfig[status] || statusConfig['pending']
                          return (
                            <span
                              className={`inline-block px-2 py-1 rounded text-xs font-medium ${config.bgClass} ${config.textClass}`}
                              role="status"
                              aria-label={`게시 상태: ${config.label}`}
                            >
                              {config.label}
                            </span>
                          )
                        })()}
                      </td>
                      <td className="px-4 py-3 text-sm text-center">
                        <div className="text-foreground font-medium" title={formatDateTime(target.discovered_at || '')}>
                          {formatRelativeTime(target.discovered_at || '')}
                        </div>
                        {target.discovered_at && (
                          <div className="text-xs text-muted-foreground">
                            {formatDateTime(target.discovered_at).split(' ')[0]}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Button
                          variant="primary"
                          size="xs"
                          onClick={async (e) => {
                            e.preventDefault()
                            try {
                              const result = await viralApi.generateComment(target.id)
                              if (result.comment) {
                                setCommentPreview({
                                  targetId: String(target.id),
                                  targetTitle: target.title || '제목 없음',
                                  comment: result.comment,
                                })
                                toast.success('AI 댓글 생성 완료')
                              } else {
                                toast.warning('댓글이 생성되지 않았습니다')
                              }
                            } catch (error: unknown) {
                              const apiError = error as Error & { response?: { data?: { detail?: string } } }
                              const errorMsg = apiError.response?.data?.detail || apiError.message || '알 수 없는 오류'
                              toast.error(`댓글 생성 실패: ${errorMsg}`)
                            }
                          }}
                        >
                          🤖 댓글 생성
                        </Button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* 페이지네이션 */}
        {totalItems > 0 && (
          <div className="border-t border-border px-4">
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              totalItems={totalItems}
              pageSize={pageSize}
              pageSizeOptions={[20, 50, 100, 200]}
              onPageChange={onPageChange}
              onPageSizeChange={onPageSizeChange}
            />
          </div>
        )}
      </div>

      {/* 통계 요약 (총 타겟은 전체, 우선순위 breakdown은 현재 페이지) */}
      {totalItems > 0 && (
        <div className="bg-card border border-border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">📊 통계 요약</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <div className="text-3xl font-bold">{totalItems.toLocaleString()}</div>
              <div className="text-sm text-muted-foreground">총 타겟</div>
            </div>
            <div>
              <div className="text-3xl font-bold text-red-500">
                {displayTargets.filter((t) => (t.priority_score || 0) >= 80).length}
              </div>
              <div className="text-sm text-muted-foreground">고우선순위 (이 페이지)</div>
            </div>
            <div>
              <div className="text-3xl font-bold text-yellow-500">
                {displayTargets.filter((t) => (t.priority_score || 0) >= 50 && (t.priority_score || 0) < 80).length}
              </div>
              <div className="text-sm text-muted-foreground">중우선순위 (이 페이지)</div>
            </div>
          </div>
        </div>
      )}

      {/* 대량 액션 확인 모달 */}
      <ConfirmModal
        isOpen={bulkActionConfirm !== null}
        onClose={() => onSetBulkActionConfirm(null)}
        onConfirm={onExecuteBulkAction}
        title="대량 작업 확인"
        message={`선택한 ${bulkActionConfirm?.count || 0}개 타겟을 ${
          bulkActionConfirm?.action === 'approve' ? '승인' : bulkActionConfirm?.action === 'skip' ? '건너뛰기' : '삭제'
        }하시겠습니까?`}
        confirmText="확인"
        cancelText="취소"
        variant={bulkActionConfirm?.action === 'delete' ? 'danger' : 'default'}
        loading={isProcessingBulk}
      />

      {/* 리드 추적 연결 모달 */}
      {leadTrackingModal.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => onSetLeadTrackingModal((prev) => ({ ...prev, isOpen: false }))}
          />
          <div className="relative bg-card border border-border rounded-xl shadow-2xl p-6 max-w-md w-full mx-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="text-center mb-6">
              <div className="text-5xl mb-4">{leadTrackingModal.leadCreated ? '🎉' : '✅'}</div>
              <h3 className="text-xl font-bold mb-2">
                {leadTrackingModal.leadCreated ? '리드 자동 생성 완료!' : '댓글 승인 완료!'}
              </h3>
              <p className="text-sm text-muted-foreground">"{leadTrackingModal.targetTitle.slice(0, 30)}..."</p>
            </div>

            {leadTrackingModal.leadCreated ? (
              <div className="space-y-3">
                <div className="p-3 bg-green-500/10 border border-green-500/20 rounded-lg text-sm text-green-600">
                  이 콘텐츠의 작성자가 잠재 고객으로 Lead Manager에 등록되었습니다.
                </div>
                <Button
                  onClick={() => {
                    onSetLeadTrackingModal((prev) => ({ ...prev, isOpen: false }))
                    navigate('/leads')
                  }}
                  fullWidth
                  size="lg"
                >
                  📋 Lead Manager에서 확인하기
                </Button>
                <Button
                  onClick={() => onSetLeadTrackingModal((prev) => ({ ...prev, isOpen: false }))}
                  variant="secondary"
                  fullWidth
                  size="lg"
                >
                  계속 작업하기
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg text-sm text-blue-600">
                  댓글이 승인되었습니다. 이 타겟은 승인 목록에서 관리됩니다.
                </div>
                <Button
                  onClick={() => onSetLeadTrackingModal((prev) => ({ ...prev, isOpen: false }))}
                  fullWidth
                  size="lg"
                >
                  확인
                </Button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 생성된 AI 댓글 미리보기 모달 — ListView에는 댓글 컬럼이 없어 별도 표시 */}
      <Modal
        isOpen={commentPreview !== null}
        onClose={() => setCommentPreview(null)}
        title="🤖 AI 댓글 생성 완료"
        description={commentPreview ? `타겟: ${commentPreview.targetTitle.slice(0, 60)}${commentPreview.targetTitle.length > 60 ? '...' : ''}` : undefined}
        size="lg"
        footer={
          commentPreview ? (
            <div className="flex gap-2 justify-end">
              <Button
                variant="secondary"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(commentPreview.comment)
                    toast.success('댓글이 클립보드에 복사되었습니다')
                  } catch {
                    toast.error('클립보드 복사 실패')
                  }
                }}
              >
                📋 복사
              </Button>
              <Button onClick={() => setCommentPreview(null)}>닫기</Button>
            </div>
          ) : null
        }
      >
        {commentPreview && (
          <div className="space-y-3">
            <textarea
              readOnly
              value={commentPreview.comment}
              className="w-full min-h-[160px] p-3 bg-muted/30 border border-border rounded-lg text-sm font-mono whitespace-pre-wrap resize-y"
            />
            <p className="text-xs text-muted-foreground">
              💡 댓글은 DB에 저장되었습니다. 게시 상태가 "생성됨"으로 변경되며, 홈의 카테고리 화면 또는 필터(comment_status=generated)에서 다시 확인·승인할 수 있습니다.
            </p>
          </div>
        )}
      </Modal>
    </div>
  )
}

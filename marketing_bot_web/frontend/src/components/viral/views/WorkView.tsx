/**
 * Viral Hunter - 작업 화면 (아코디언 방식)
 * 개별 타겟 상세보기 및 액션 처리
 */

import { useEffect, useRef } from 'react'
import { UseMutationResult } from '@tanstack/react-query'
import { CheckCircle2, ExternalLink, MessageSquarePlus, SkipForward, Trash2, Copy, Search, ThumbsUp, MessageSquareWarning } from 'lucide-react'
import Button from '@/components/ui/Button'
import { PlatformBadge } from '@/components/viral/PlatformBadge'
import { ScanCountBadge } from '@/components/viral/ScanCountBadge'
import { EngagementMetrics } from '@/components/viral/EngagementMetrics'
import { AIClassificationBadge } from '@/components/viral/AIClassificationBadge'
import { EmptyState } from '@/components/viral/EmptyState'
import { CommentPreview } from '@/components/viral/CommentPreview'
import { TargetContext } from '@/components/viral/TargetContext'
import TargetContextCard from '@/components/viral/TargetContextCard'
import PriorityScoreExplain from '@/components/viral/PriorityScoreExplain'
import TargetNote from '@/components/viral/TargetNote'
import { safeUrl } from '@/utils/safeUrl'
import { ViralTargetData } from '@/types/viral'
import { formatRelativeTime, formatDateTime } from '@/utils/dateFormat'
import { viralApi } from '@/services/api'

interface Template {
  id: number
  name: string
  content: string
}

interface CompletionStats {
  approved: number
  skipped: number
  deleted: number
}

interface CommentStyle {
  id: string
  name: string
  icon: string
  description: string
}

interface WorkViewProps {
  // 데이터
  selectedCategory: string | null
  categoryTargets: ViralTargetData[]
  templates: Template[]
  completionStats: CompletionStats
  expandedTargetId: string | null
  expandedComments: Record<string, string>
  generatingTargetId: string | null
  commentStyles: CommentStyle[]
  selectedCommentStyle: string

  // 핸들러
  onGoHome: () => void
  onToggleExpand: (targetId: string) => void
  onSetExpandedTargetId: (targetId: string | null) => void
  onSetExpandedComments: (fn: (prev: Record<string, string>) => Record<string, string>) => void
  onGenerateComment: (targetId: string, style?: string) => void
  onSetSelectedCommentStyle: (style: string) => void
  onTargetAction: (targetId: string, action: string, skipReason?: string) => void
  onVerifyTarget: (targetId: string) => void
  verifyTargetMutation: UseMutationResult<unknown, Error, string, unknown>
  toast: {
    success: (msg: string) => void
    error: (msg: string) => void
    warning: (msg: string) => void
  }
}

const platformIcons: Record<string, string> = {
  cafe: '☕ 네이버 카페',
  blog: '📝 블로그',
  kin: '❓ 지식iN',
  youtube: '📺 유튜브',
  instagram: '📸 인스타그램',
  tiktok: '🎵 틱톡',
  place: '📍 플레이스',
  karrot: '🥕 당근',
}

function getWorkLabel(target?: ViralTargetData | null) {
  if (!target) return '대기'
  if ((target.priority_score || 0) >= 90) return '최우선'
  if ((target.priority_score || 0) >= 70) return '우선'
  return '일반'
}

export function WorkView({
  selectedCategory,
  categoryTargets,
  templates,
  completionStats,
  expandedTargetId,
  expandedComments,
  generatingTargetId,
  commentStyles,
  selectedCommentStyle,
  onGoHome,
  onToggleExpand,
  onSetExpandedTargetId,
  onSetExpandedComments,
  onGenerateComment,
  onSetSelectedCommentStyle,
  onTargetAction,
  onVerifyTarget,
  verifyTargetMutation,
  toast,
}: WorkViewProps) {
  // 자동 다음 타겟 이동 후 해당 아코디언이 뷰포트 밖에 있으면 스크롤해서 보이게 함
  const accordionRefs = useRef<Map<string, HTMLDivElement>>(new Map())
  useEffect(() => {
    if (!expandedTargetId) return
    const el = accordionRefs.current.get(expandedTargetId)
    if (!el) return
    const rect = el.getBoundingClientRect()
    const outOfView = rect.top < 80 || rect.bottom > window.innerHeight - 40
    if (outOfView) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [expandedTargetId])

  const activeTarget = categoryTargets.find((target) => target.id === expandedTargetId) || categoryTargets[0] || null
  const activeComment = activeTarget
    ? (expandedComments[activeTarget.id] ?? activeTarget.generated_comment ?? '')
    : ''
  const activeIndex = activeTarget
    ? categoryTargets.findIndex((target) => target.id === activeTarget.id)
    : -1

  const submitFeedback = async (rating: 'good' | 'needs_edit' | 'bad', reason?: string) => {
    if (!activeTarget) return
    try {
      await viralApi.recordTargetFeedback(activeTarget.id, rating, reason)
      toast.success(rating === 'good' ? '좋은 댓글로 기록했습니다' : '수정 필요 의견을 기록했습니다')
    } catch {
      toast.error('품질 피드백 저장에 실패했습니다')
    }
  }

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <Button onClick={onGoHome} variant="outline">
            ← 홈으로
          </Button>
          <h1 className="text-3xl font-bold">🎯 {selectedCategory} ({categoryTargets.length}개)</h1>
        </div>
        <div className="text-xs text-muted-foreground">
          단축키:{' '}
          <kbd className="px-1 py-0.5 bg-muted border border-border rounded">A</kbd> 승인,{' '}
          <kbd className="px-1 py-0.5 bg-muted border border-border rounded">S</kbd> 건너뛰기,{' '}
          <kbd className="px-1 py-0.5 bg-muted border border-border rounded">D</kbd> 삭제,{' '}
          <kbd className="px-1 py-0.5 bg-muted border border-border rounded">Esc</kbd> 접기
        </div>
      </div>

      {/* 직원 작업 패널 */}
      {activeTarget && (
        <div className="sticky top-3 z-20 bg-card/95 backdrop-blur border border-border rounded-lg shadow-sm p-4">
          <div className="flex flex-col lg:flex-row lg:items-center gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-semibold px-2 py-1 rounded bg-primary/10 text-primary">
                  {activeIndex + 1}/{categoryTargets.length}
                </span>
                <span className="text-xs font-semibold px-2 py-1 rounded bg-muted text-muted-foreground">
                  {getWorkLabel(activeTarget)} · {activeTarget.priority_score?.toFixed(0) || 0}점
                </span>
                <PlatformBadge platform={activeTarget.platform} size="sm" />
              </div>
              <button
                type="button"
                onClick={() => onSetExpandedTargetId(activeTarget.id)}
                className="block text-left font-semibold truncate max-w-full hover:text-primary"
                title={activeTarget.title || ''}
              >
                {activeTarget.title || '제목 없음'}
              </button>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {(activeTarget.matched_keywords || []).slice(0, 4).map((kw) => (
                  <span key={kw} className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">
                    {kw}
                  </span>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 sm:flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => window.open(safeUrl(activeTarget.url), '_blank', 'noopener,noreferrer')}
              >
                <ExternalLink className="w-4 h-4" />
                원문
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => onVerifyTarget(activeTarget.id)}
                loading={verifyTargetMutation.isPending}
              >
                <Search className="w-4 h-4" />
                확인
              </Button>
              <Button
                size="sm"
                variant={activeComment ? 'outline' : 'primary'}
                onClick={() => onGenerateComment(activeTarget.id, selectedCommentStyle)}
                loading={generatingTargetId === activeTarget.id}
              >
                <MessageSquarePlus className="w-4 h-4" />
                댓글
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={!activeComment}
                onClick={async () => {
                  if (!activeComment) return
                  await navigator.clipboard.writeText(activeComment)
                  toast.success('댓글을 복사했습니다')
                }}
              >
                <Copy className="w-4 h-4" />
                복사
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={!activeComment}
                onClick={() => submitFeedback('good')}
                title="좋은 댓글 초안으로 기록"
              >
                <ThumbsUp className="w-4 h-4" />
                좋음
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={!activeComment}
                onClick={() => submitFeedback('needs_edit', 'staff_marked_needs_edit')}
                title="수정이 필요한 댓글 초안으로 기록"
              >
                <MessageSquareWarning className="w-4 h-4" />
                수정필요
              </Button>
              <Button
                size="sm"
                variant="success"
                disabled={!activeComment}
                onClick={() => onTargetAction(activeTarget.id, 'approve')}
              >
                <CheckCircle2 className="w-4 h-4" />
                승인
              </Button>
              <Button
                size="sm"
                onClick={() => onTargetAction(activeTarget.id, 'skip', 'unspecified')}
                className="bg-yellow-500 hover:bg-yellow-600"
              >
                <SkipForward className="w-4 h-4" />
                건너뜀
              </Button>
              <Button
                size="sm"
                variant="danger"
                onClick={() => onTargetAction(activeTarget.id, 'delete')}
              >
                <Trash2 className="w-4 h-4" />
                삭제
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* 통계 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold">{categoryTargets.length}</div>
          <div className="text-xs text-muted-foreground">남은 타겟</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-green-500">{completionStats.approved}</div>
          <div className="text-xs text-muted-foreground">✅ 승인</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-yellow-500">{completionStats.skipped}</div>
          <div className="text-xs text-muted-foreground">⏭️ 건너뜀</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-red-500">{completionStats.deleted}</div>
          <div className="text-xs text-muted-foreground">🗑️ 삭제</div>
        </div>
      </div>

      {/* 타겟 목록 (아코디언) */}
      <div className="space-y-2">
        {categoryTargets.length === 0 ? (
          <EmptyState type="all-done" onAction={onGoHome} />
        ) : (
          categoryTargets.map((target, index) => {
            const isExpanded = expandedTargetId === target.id
            // expandedComments에 없으면 DB에 저장된 generated_comment 폴백
            // (이전 세션/배치 생성분도 재진입 시 표시되도록)
            const comment = expandedComments[target.id] ?? target.generated_comment ?? ''
            const isGenerating = generatingTargetId === target.id

            return (
              <div
                key={target.id || index}
                ref={(el) => {
                  if (el) accordionRefs.current.set(target.id, el)
                  else accordionRefs.current.delete(target.id)
                }}
                className={`bg-card border rounded-lg overflow-hidden transition-all ${
                  isExpanded ? 'border-primary' : 'border-border'
                }`}
              >
                {/* 헤더 (클릭하면 펼침) */}
                <div
                  onClick={() => onToggleExpand(target.id)}
                  className="flex items-center gap-4 p-4 cursor-pointer hover:bg-muted/50"
                >
                  <span className="text-xl">{isExpanded ? '▼' : '▶'}</span>
                  <PlatformBadge platform={target.platform} size="sm" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-semibold truncate">{target.title || '제목 없음'}</span>
                      {target.scan_count && target.scan_count >= 2 && (
                        <ScanCountBadge scanCount={target.scan_count} lastScannedAt={target.last_scanned_at} />
                      )}
                      {target.is_commentable !== undefined && (
                        <span
                          className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                            target.is_commentable
                              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                              : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                          }`}
                          title={target.is_commentable ? '댓글 작성 가능' : '댓글 불가'}
                        >
                          {target.is_commentable ? '✓ 댓글 가능' : '✗ 댓글 불가'}
                        </span>
                      )}
                      {/* [2026-04-27] AI 분류 배지 — 한눈에 작업 가치 판단 */}
                      <AIClassificationBadge
                        label={target.ai_ad_label}
                        confidence={target.ai_ad_confidence}
                        specialtyMatch={target.specialty_match}
                        reason={target.ai_ad_reason}
                        size="xs"
                      />
                    </div>
                    <div className="flex items-center gap-3 text-xs">
                      <span className="text-muted-foreground">
                        {Array.isArray(target.matched_keywords) && target.matched_keywords.length > 0
                          ? target.matched_keywords.slice(0, 3).join(', ')
                          : '키워드 없음'}
                      </span>
                      <EngagementMetrics
                        likes={target.like_count}
                        comments={target.comment_count}
                        views={target.view_count}
                        size="sm"
                      />
                      {target.discovered_at && (
                        <span className="text-muted-foreground" title={formatDateTime(target.discovered_at)}>
                          {formatRelativeTime(target.discovered_at)}
                        </span>
                      )}
                    </div>
                  </div>
                  <div
                    className={`font-bold text-lg ${
                      (target.priority_score || 0) >= 80
                        ? 'text-red-500'
                        : (target.priority_score || 0) >= 50
                          ? 'text-yellow-500'
                          : 'text-blue-500'
                    }`}
                  >
                    {target.priority_score?.toFixed(0) || 0}점
                  </div>
                  {/* 퀵 액션 버튼 */}
                  <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                    <Button
                      size="xs"
                      onClick={() => onVerifyTarget(target.id)}
                      loading={verifyTargetMutation.isPending}
                      className="bg-blue-500 hover:bg-blue-600 text-white"
                      title="댓글 가능 여부 확인"
                    >
                      🔍
                    </Button>
                    <Button
                      size="xs"
                      onClick={(e) => onTargetAction(target.id, 'skip', e.shiftKey ? undefined : 'unspecified')}
                      className="bg-yellow-500 hover:bg-yellow-600 text-white"
                      title="건너뛰기 (Shift+클릭: 사유 선택)"
                    >
                      ⏭️
                    </Button>
                    <Button
                      size="xs"
                      variant="danger"
                      onClick={() => onTargetAction(target.id, 'delete')}
                      title="삭제"
                    >
                      🗑️
                    </Button>
                  </div>
                </div>

                {/* 펼쳐진 상세 내용 */}
                {isExpanded && (
                  <div className="border-t border-border p-4 sm:p-6 bg-muted/30">
                    {/* [U4] 컨텍스트 카드 — 과노출 경고 + 경쟁사 배지 */}
                    <div className="mb-4">
                      <TargetContextCard targetId={target.id} />
                    </div>
                    {/* 기본 정보 */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6 mb-6">
                      <div className="space-y-3">
                        <div>
                          <span className="text-muted-foreground text-sm">📍 플랫폼:</span>{' '}
                          <span className="font-semibold">{platformIcons[target.platform] || '📌 기타'}</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground text-sm">🔗 URL:</span>{' '}
                          <a
                            href={safeUrl(target.url)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-500 hover:underline text-sm break-all"
                          >
                            {target.url}
                          </a>
                        </div>
                        {target.matched_keywords && target.matched_keywords.length > 0 && (
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="text-muted-foreground text-sm">🏷️ 매칭 키워드:</span>
                            {target.matched_keywords.slice(0, 10).map((kw: string) => (
                              <a
                                key={kw}
                                href={`/pathfinder?keyword=${encodeURIComponent(kw)}`}
                                className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary hover:bg-primary/20 border border-primary/20 transition-colors"
                                title={`Pathfinder에서 "${kw}" 상세 보기`}
                              >
                                {kw}
                              </a>
                            ))}
                          </div>
                        )}
                      </div>
                      <div>
                        <div className="text-right">
                          {(target.priority_score || 0) >= 90 ? (
                            <div className="text-red-500">
                              <div className="text-2xl">⭐⭐⭐⭐⭐</div>
                              <div className="text-lg font-bold">{target.priority_score?.toFixed(0)}점 - 최우선</div>
                            </div>
                          ) : (target.priority_score || 0) >= 70 ? (
                            <div className="text-yellow-500">
                              <div className="text-2xl">⭐⭐⭐⭐</div>
                              <div className="text-lg font-bold">{target.priority_score?.toFixed(0)}점 - 우선</div>
                            </div>
                          ) : (
                            <div className="text-blue-500">
                              <div className="text-2xl">⭐⭐⭐</div>
                              <div className="text-lg font-bold">{target.priority_score?.toFixed(0)}점 - 일반</div>
                            </div>
                          )}
                          {/* [BB3] 점수 설명 */}
                          <div className="mt-1 flex justify-end">
                            <PriorityScoreExplain target={target} />
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* 내용 미리보기 */}
                    {target.content_preview && (
                      <details className="mb-6">
                        <summary className="cursor-pointer text-sm font-semibold text-muted-foreground mb-2">
                          📄 내용 미리보기
                        </summary>
                        <div className="bg-background rounded-lg p-4 text-sm border border-border">
                          {target.content_preview.substring(0, 800)}
                        </div>
                      </details>
                    )}

                    {/* 컨텍스트 인사이트 */}
                    <details className="mb-6" open>
                      <summary className="cursor-pointer text-sm font-semibold text-muted-foreground mb-2">
                        💡 컨텍스트 인사이트
                      </summary>
                      <TargetContext
                        targetId={target.id}
                        onSelectTarget={(id) => onSetExpandedTargetId(id)}
                      />
                    </details>

                    {/* AI 댓글 섹션 */}
                    <div className="mb-4">
                      {!comment ? (
                        <div className="bg-card border border-border rounded-lg p-6">
                          {/* 스타일 선택 */}
                          {commentStyles.length > 0 && (
                            <div className="mb-4">
                              <p className="text-sm text-muted-foreground mb-2">댓글 스타일 선택:</p>
                              <div className="flex flex-wrap gap-2">
                                {commentStyles.map((style) => (
                                  <button
                                    key={style.id}
                                    onClick={() => onSetSelectedCommentStyle(style.id)}
                                    className={`px-3 py-2 rounded-lg text-sm transition-all flex items-center gap-1.5 ${
                                      selectedCommentStyle === style.id
                                        ? 'bg-primary text-primary-foreground ring-2 ring-primary ring-offset-2'
                                        : 'bg-muted hover:bg-muted/80 text-foreground'
                                    }`}
                                    title={style.description}
                                  >
                                    <span>{style.icon}</span>
                                    <span>{style.name}</span>
                                  </button>
                                ))}
                              </div>
                              {selectedCommentStyle && selectedCommentStyle !== 'default' && (
                                <p className="text-xs text-muted-foreground mt-2">
                                  {commentStyles.find(s => s.id === selectedCommentStyle)?.description}
                                </p>
                              )}
                            </div>
                          )}

                          <div className="text-center mb-4">
                            <div className="text-4xl mb-3">
                              {commentStyles.find(s => s.id === selectedCommentStyle)?.icon || '🤖'}
                            </div>
                            <p className="text-muted-foreground mb-4">
                              {selectedCommentStyle !== 'default'
                                ? `"${commentStyles.find(s => s.id === selectedCommentStyle)?.name}" 스타일로 댓글을 생성합니다`
                                : 'AI가 자연스러운 댓글을 생성합니다'}
                            </p>
                            <Button
                              variant="primary"
                              size="lg"
                              onClick={() => onGenerateComment(target.id, selectedCommentStyle)}
                              loading={isGenerating}
                              className="group relative"
                            >
                              <span>{commentStyles.find(s => s.id === selectedCommentStyle)?.icon || '🤖'} AI 댓글 생성하기</span>
                              <kbd className="ml-2 hidden group-hover:inline-flex items-center h-5 px-1.5 text-[10px] font-mono rounded bg-black/20 text-white/90">G</kbd>
                            </Button>
                          </div>

                          {/* 템플릿 선택 */}
                          {templates.length > 0 && (
                            <div className="border-t border-border pt-4 mt-4">
                              <p className="text-sm text-muted-foreground mb-2">또는 템플릿 사용:</p>
                              <div className="flex flex-wrap gap-2">
                                {templates.slice(0, 5).map((template) => (
                                  <Button
                                    key={template.id}
                                    variant="secondary"
                                    size="sm"
                                    onClick={async () => {
                                      onSetExpandedComments((prev) => ({
                                        ...prev,
                                        [target.id]: template.content,
                                      }))
                                      await viralApi.useTemplate(template.id)
                                      toast.success(`"${template.name}" 템플릿 적용`)
                                    }}
                                    title={template.content}
                                  >
                                    📝 {template.name}
                                  </Button>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ) : (
                        <CommentPreview
                          comment={comment}
                          onChange={(newComment) =>
                            onSetExpandedComments((prev) => ({ ...prev, [target.id]: newComment }))
                          }
                          onRegenerate={() => {
                            onSetExpandedComments((prev) => {
                              const newComments = { ...prev }
                              delete newComments[target.id]
                              return newComments
                            })
                            onGenerateComment(target.id, selectedCommentStyle)
                          }}
                          isGenerating={isGenerating}
                          targetTitle={target.title}
                          matchedKeywords={Array.isArray(target.matched_keywords) ? target.matched_keywords : []}
                        />
                      )}
                    </div>

                    {/* [BB7] 타겟 개인 메모 */}
                    <div className="mb-4">
                      <TargetNote targetId={target.id} />
                    </div>

                    {/* 액션 버튼 */}
                    <div className="flex gap-3">
                      <Button
                        onClick={() => onTargetAction(target.id, 'approve')}
                        disabled={!comment}
                        variant="success"
                        size="lg"
                        fullWidth
                        className="group relative"
                      >
                        <span>✅ 승인 (댓글 저장)</span>
                        <kbd className="ml-2 hidden group-hover:inline-flex items-center h-5 px-1.5 text-[10px] font-mono rounded bg-black/20 text-white/90">A</kbd>
                      </Button>
                      <Button
                        onClick={(e) => onTargetAction(target.id, 'skip', (e as React.MouseEvent).shiftKey ? undefined : 'unspecified')}
                        size="lg"
                        fullWidth
                        className="bg-yellow-500 hover:bg-yellow-600 group relative"
                        title="Shift+클릭: 사유 선택"
                      >
                        <span>⏭️ 건너뛰기</span>
                        <kbd className="ml-2 hidden group-hover:inline-flex items-center h-5 px-1.5 text-[10px] font-mono rounded bg-black/20 text-white/90">S</kbd>
                      </Button>
                      <Button
                        onClick={() => onTargetAction(target.id, 'delete')}
                        variant="danger"
                        size="lg"
                        fullWidth
                        className="group relative"
                      >
                        <span>🗑️ 삭제</span>
                        <kbd className="ml-2 hidden group-hover:inline-flex items-center h-5 px-1.5 text-[10px] font-mono rounded bg-black/20 text-white/90">D</kbd>
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>

      {/* 하단 안내 */}
      {categoryTargets.length > 0 && (
        <div className="text-center text-sm text-muted-foreground">
          💡 제목을 클릭하면 상세 정보가 펼쳐집니다. 목록에서 바로 ⏭️ 건너뛰기, 🗑️ 삭제도 가능합니다.
        </div>
      )}
    </div>
  )
}

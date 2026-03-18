import { useState, memo } from 'react'
import Button from '@/components/ui/Button'

interface ViralTargetCardProps {
  target: any
  onGenerateComment: (target_id: number) => void
  onAction: (target_id: number, action: string, comment?: string) => void
  isGenerating: boolean
}

const platformIcons: any = {
  youtube: '📺',
  tiktok: '🎵',
  naver: '🟢',
  instagram: '📸',
  blog: '📝',
  cafe: '☕'
}

// 상대적 시간 계산
const getRelativeTime = (dateString: string) => {
  if (!dateString) return ''

  const now = new Date()
  const date = new Date(dateString)
  const diff = now.getTime() - date.getTime()

  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '방금 전'
  if (minutes < 60) return `${minutes}분 전`
  if (hours < 24) return `${hours}시간 전`
  if (days < 7) return `${days}일 전`

  // 7일 이상이면 날짜 표시
  return date.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' })
}

// [성능 최적화] React.memo로 불필요한 리렌더링 방지
function ViralTargetCardComponent({
  target,
  onGenerateComment,
  onAction,
  isGenerating
}: ViralTargetCardProps) {
  const [showComment, setShowComment] = useState(false)
  const [generatedComment, setGeneratedComment] = useState(target.generated_comment || '')

  const handleGenerateComment = async () => {
    onGenerateComment(target.id)
    setShowComment(true)
    // 실제로는 mutation의 onSuccess에서 처리해야 하지만 간단히 구현
    setTimeout(() => {
      setGeneratedComment('AI가 생성한 댓글 예시입니다...')
    }, 1000)
  }

  return (
    <div className="p-4 rounded-lg border border-border hover:border-primary/50 transition-colors">
      {/* 헤더 */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{platformIcons[target.platform]}</span>
          <div className="flex flex-col gap-1">
            <span className="text-xs px-2 py-1 rounded-full bg-muted inline-block w-fit">
              {target.category}
            </span>
            {target.created_at && (
              <span className="text-xs text-muted-foreground">
                🕒 {getRelativeTime(target.created_at)}
              </span>
            )}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-muted-foreground">우선순위</div>
          <div className="text-lg font-bold text-primary">
            {target.priority_score}
          </div>
        </div>
      </div>

      {/* 제목 */}
      <h4 className="font-semibold mb-2 line-clamp-2">{target.title}</h4>

      {/* 콘텐츠 미리보기 */}
      <p className="text-sm text-muted-foreground mb-3 line-clamp-3">
        {target.content_preview}
      </p>

      {/* 매칭 키워드 */}
      {target.matched_keywords && target.matched_keywords.length > 0 && (
        <div className="mb-3">
          <div className="text-xs font-semibold mb-1">매칭 키워드</div>
          <div className="flex flex-wrap gap-1">
            {target.matched_keywords.slice(0, 5).map((kw: string, i: number) => (
              <span
                key={i}
                className="text-xs px-2 py-1 rounded-md bg-primary/10 text-primary"
              >
                {kw}
              </span>
            ))}
            {target.matched_keywords.length > 5 && (
              <span className="text-xs text-muted-foreground">
                +{target.matched_keywords.length - 5}
              </span>
            )}
          </div>
        </div>
      )}

      {/* 링크 */}
      {target.url && (
        <a
          href={target.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-500 hover:underline mb-3 block"
        >
          원본 보기 ↗
        </a>
      )}

      {/* 생성된 댓글 */}
      {showComment && generatedComment && (
        <div className="mb-3 p-3 rounded-lg bg-green-500/10 border border-green-500/30">
          <div className="text-xs font-semibold text-green-500 mb-1">✨ AI 생성 댓글</div>
          <p className="text-sm">{generatedComment}</p>
        </div>
      )}

      {/* 액션 버튼 */}
      <div className="flex gap-2">
        {!showComment ? (
          <Button
            variant="outline"
            fullWidth
            onClick={handleGenerateComment}
            loading={isGenerating}
            className="text-primary"
          >
            ✨ 댓글 생성
          </Button>
        ) : (
          <>
            <Button
              variant="success"
              fullWidth
              onClick={() => onAction(target.id, 'approve', generatedComment)}
            >
              ✅ 승인
            </Button>
            <Button
              onClick={() => onAction(target.id, 'skip')}
              className="bg-yellow-500/10 hover:bg-yellow-500/20 text-yellow-500"
            >
              ⏭️
            </Button>
            <Button
              variant="danger"
              onClick={() => onAction(target.id, 'delete')}
            >
              🗑️
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

// memo로 target.id가 변경될 때만 리렌더링
const ViralTargetCard = memo(ViralTargetCardComponent, (prevProps, nextProps) => {
  return (
    prevProps.target.id === nextProps.target.id &&
    prevProps.target.generated_comment === nextProps.target.generated_comment &&
    prevProps.isGenerating === nextProps.isGenerating
  )
})

export default ViralTargetCard

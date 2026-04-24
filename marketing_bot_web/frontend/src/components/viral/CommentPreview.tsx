import { useState } from 'react'
import { Sparkles, Copy, Check } from 'lucide-react'

interface CommentPreviewProps {
  comment: string
  onChange: (comment: string) => void
  onRegenerate: () => void
  isGenerating: boolean
  targetTitle?: string
  matchedKeywords?: string[]
}

export function CommentPreview({
  comment,
  onChange,
  onRegenerate,
  isGenerating,
  targetTitle,
  matchedKeywords = [],
}: CommentPreviewProps) {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(comment)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      // clipboard 실패 시 무시
    }
  }
  // 댓글 품질 분석
  const analyzeQuality = () => {
    const length = comment.length
    const hasKeywords = matchedKeywords.some(kw =>
      comment.toLowerCase().includes(kw.toLowerCase())
    )
    const hasQuestion = comment.includes('?')
    const hasCTA = /연락|문의|방문|상담|예약|확인/.test(comment)

    let score = 0
    const checks = []

    // 길이 체크 (50-300자 권장)
    if (length >= 50 && length <= 300) {
      score += 25
      checks.push({ label: '적절한 길이', passed: true })
    } else if (length > 0) {
      checks.push({
        label: length < 50 ? '너무 짧음' : '너무 김',
        passed: false
      })
    }

    // 키워드 포함 여부
    if (hasKeywords) {
      score += 25
      checks.push({ label: '키워드 포함', passed: true })
    } else if (matchedKeywords.length > 0) {
      checks.push({ label: '키워드 미포함', passed: false })
    }

    // 질문 포함 여부 (자연스러움)
    if (hasQuestion) {
      score += 25
      checks.push({ label: '자연스러운 질문', passed: true })
    }

    // CTA 포함 여부
    if (hasCTA) {
      score += 25
      checks.push({ label: '행동 유도', passed: true })
    }

    return { score, checks, length }
  }

  const quality = comment ? analyzeQuality() : null

  const getScoreColor = (score: number) => {
    if (score >= 75) return 'text-green-500'
    if (score >= 50) return 'text-yellow-500'
    return 'text-red-500'
  }

  const getScoreLabel = (score: number) => {
    if (score >= 75) return '우수'
    if (score >= 50) return '보통'
    return '개선 필요'
  }

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      {/* 헤더 */}
      <div className="px-4 py-3 border-b border-border flex items-center justify-between gap-2 bg-muted/30 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-lg">💬</span>
          <span className="font-semibold">생성된 댓글</span>
          {/* [Z4] AI 생성 명시 배지 */}
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium bg-purple-500/10 text-purple-700 dark:text-purple-300 border border-purple-500/20 rounded">
            <Sparkles className="w-2.5 h-2.5" aria-hidden />
            AI 생성 · 편집 가능
          </span>
        </div>
        <div className="flex items-center gap-2">
          {quality && (
            <>
              <span className="text-sm text-muted-foreground">품질:</span>
              <span className={`font-bold ${getScoreColor(quality.score)}`}>
                {quality.score}점 ({getScoreLabel(quality.score)})
              </span>
            </>
          )}
          {/* [Z4] 복사 버튼 */}
          <button
            onClick={handleCopy}
            disabled={!comment}
            className="inline-flex items-center gap-1 px-2 py-1 text-xs border border-border hover:bg-muted rounded transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-40"
            aria-label="댓글 복사"
          >
            {copied ? (
              <>
                <Check className="w-3 h-3 text-emerald-500" aria-hidden />
                <span className="text-emerald-600">복사됨</span>
              </>
            ) : (
              <>
                <Copy className="w-3 h-3" aria-hidden />
                <span>복사</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* 타겟 정보 */}
      {targetTitle && (
        <div className="px-4 py-2 bg-blue-50 dark:bg-blue-900/30 border-b border-blue-100 dark:border-blue-800">
          <div className="text-sm text-blue-700 dark:text-blue-300 truncate">
            <span className="font-medium">대상:</span> {targetTitle}
          </div>
        </div>
      )}

      {/* 댓글 편집 영역 */}
      <div className="p-4">
        <textarea
          value={comment}
          onChange={(e) => onChange(e.target.value)}
          placeholder="AI가 생성한 댓글이 여기에 표시됩니다..."
          className="w-full h-32 p-3 bg-background border border-border rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-primary text-sm"
        />

        {/* 글자 수 표시 */}
        <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {comment.length}자
            {comment.length > 0 && (
              <span className={comment.length < 50 ? 'text-red-500' : comment.length > 300 ? 'text-yellow-500' : 'text-green-500'}>
                {comment.length < 50 ? ' (50자 이상 권장)' : comment.length > 300 ? ' (300자 이하 권장)' : ' ✓'}
              </span>
            )}
          </span>
          <button
            onClick={onRegenerate}
            disabled={isGenerating}
            className="flex items-center gap-1 px-2 py-1 bg-muted hover:bg-accent rounded text-xs transition-colors disabled:opacity-50"
          >
            {isGenerating ? (
              <>
                <span className="animate-spin">🔄</span>
                <span>생성 중...</span>
              </>
            ) : (
              <>
                <span>🔄</span>
                <span>재생성</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* 품질 체크 리스트 */}
      {quality && quality.checks.length > 0 && (
        <div className="px-4 pb-4">
          <div className="flex flex-wrap gap-2">
            {quality.checks.map((check, index) => (
              <span
                key={index}
                className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs ${
                  check.passed
                    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                    : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                }`}
              >
                {check.passed ? '✓' : '✗'} {check.label}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 키워드 참고 */}
      {matchedKeywords.length > 0 && (
        <div className="px-4 pb-4">
          <div className="text-xs text-muted-foreground mb-1">포함 권장 키워드:</div>
          <div className="flex flex-wrap gap-1">
            {matchedKeywords.slice(0, 5).map((kw, index) => (
              <span
                key={index}
                className={`px-2 py-0.5 rounded text-xs ${
                  comment.toLowerCase().includes(kw.toLowerCase())
                    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                    : 'bg-muted text-muted-foreground'
                }`}
              >
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

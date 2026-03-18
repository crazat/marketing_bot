import { useQuery } from '@tanstack/react-query'
import { viralApi } from '@/services/api'
import { TrendingUp, MessageSquare, MousePointer, Users, ArrowRight, ThumbsUp, Reply } from 'lucide-react'

interface PerformanceData {
  total_comments: number
  period_days: number
  by_platform: Array<{
    platform: string
    count: number
    total_likes: number
    total_replies: number
    total_clicks: number
    contacts: number
    conversions: number
  }>
  by_template: Array<{
    template_name: string
    category: string
    use_count: number
    avg_likes: number
    avg_replies: number
    conversions: number
  }>
  engagement_summary: {
    total_likes: number
    total_replies: number
    total_clicks: number
    avg_likes_per_comment: number
    avg_replies_per_comment: number
  }
  conversion_funnel: {
    posted: number
    engaged: number
    contacted: number
    converted: number
    engagement_rate: number
    contact_rate: number
    conversion_rate: number
  }
  recent_comments: Array<{
    id: number
    content: string
    platform: string
    url: string
    likes: number
    replies: number
    clicks: number
    led_to_contact: boolean
    led_to_conversion: boolean
    posted_at: string
    template_name: string | null
  }>
}

interface CommentPerformanceProps {
  days?: number
  compact?: boolean
}

const platformLabels: Record<string, string> = {
  cafe: '카페',
  blog: '블로그',
  kin: '지식인',
  youtube: 'YouTube',
  instagram: '인스타',
  tiktok: 'TikTok',
  place: '플레이스',
  karrot: '당근',
}

export function CommentPerformance({ days = 30, compact = false }: CommentPerformanceProps) {
  const { data, isLoading, error } = useQuery<PerformanceData>({
    queryKey: ['comment-performance', days],
    queryFn: () => viralApi.getCommentPerformance(days),
    retry: 1,
    staleTime: 5 * 60 * 1000, // 5분 캐시
  })

  if (isLoading) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 animate-pulse">
        <div className="h-6 bg-muted rounded w-1/3 mb-4"></div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-20 bg-muted rounded"></div>
          ))}
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="bg-card border border-border rounded-lg p-6">
        <p className="text-sm text-muted-foreground">댓글 성과 데이터를 불러올 수 없습니다.</p>
      </div>
    )
  }

  // 데이터가 없는 경우
  if (data.total_comments === 0) {
    return (
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-2 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-primary" />
          댓글 성과 분석
        </h3>
        <p className="text-sm text-muted-foreground">
          아직 게시된 댓글이 없습니다. 타겟을 승인하고 댓글을 게시해보세요!
        </p>
      </div>
    )
  }

  const { engagement_summary, conversion_funnel, by_platform, by_template, recent_comments } = data

  // 간결 모드 (홈 화면용)
  if (compact) {
    return (
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-primary" />
          댓글 성과 (최근 {days}일)
        </h3>

        {/* 핵심 지표 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="text-center p-3 bg-muted/50 rounded-lg">
            <div className="text-2xl font-bold text-foreground">{data.total_comments}</div>
            <div className="text-xs text-muted-foreground">게시된 댓글</div>
          </div>
          <div className="text-center p-3 bg-muted/50 rounded-lg">
            <div className="text-2xl font-bold text-blue-500">{engagement_summary.total_likes}</div>
            <div className="text-xs text-muted-foreground">받은 좋아요</div>
          </div>
          <div className="text-center p-3 bg-muted/50 rounded-lg">
            <div className="text-2xl font-bold text-green-500">{conversion_funnel.contacted}</div>
            <div className="text-xs text-muted-foreground">연락 유도</div>
          </div>
          <div className="text-center p-3 bg-muted/50 rounded-lg">
            <div className="text-2xl font-bold text-purple-500">{conversion_funnel.converted}</div>
            <div className="text-xs text-muted-foreground">전환 성공</div>
          </div>
        </div>

        {/* 전환율 표시 */}
        <div className="flex items-center justify-between text-sm p-2 bg-gradient-to-r from-blue-500/10 to-green-500/10 rounded-lg">
          <span className="text-muted-foreground">전환율</span>
          <span className="font-bold text-green-500">{conversion_funnel.conversion_rate}%</span>
        </div>
      </div>
    )
  }

  // 전체 모드
  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <TrendingUp className="w-6 h-6 text-primary" />
          댓글 성과 분석
        </h2>
        <span className="text-sm text-muted-foreground">최근 {days}일</span>
      </div>

      {/* 핵심 지표 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <MessageSquare className="w-8 h-8 mx-auto mb-2 text-blue-500" />
          <div className="text-3xl font-bold">{data.total_comments}</div>
          <div className="text-sm text-muted-foreground">게시된 댓글</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <ThumbsUp className="w-8 h-8 mx-auto mb-2 text-yellow-500" />
          <div className="text-3xl font-bold">{engagement_summary.total_likes}</div>
          <div className="text-sm text-muted-foreground">총 좋아요</div>
          <div className="text-xs text-muted-foreground mt-1">
            평균 {engagement_summary.avg_likes_per_comment}/댓글
          </div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <Reply className="w-8 h-8 mx-auto mb-2 text-green-500" />
          <div className="text-3xl font-bold">{engagement_summary.total_replies}</div>
          <div className="text-sm text-muted-foreground">총 답글</div>
          <div className="text-xs text-muted-foreground mt-1">
            평균 {engagement_summary.avg_replies_per_comment}/댓글
          </div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <MousePointer className="w-8 h-8 mx-auto mb-2 text-purple-500" />
          <div className="text-3xl font-bold">{engagement_summary.total_clicks}</div>
          <div className="text-sm text-muted-foreground">링크 클릭</div>
        </div>
      </div>

      {/* 전환 퍼널 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Users className="w-5 h-5" />
          전환 퍼널
        </h3>
        <div className="flex items-center justify-between">
          {/* 게시됨 */}
          <div className="text-center flex-1">
            <div className="text-2xl font-bold">{conversion_funnel.posted}</div>
            <div className="text-sm text-muted-foreground">게시됨</div>
          </div>
          <ArrowRight className="w-5 h-5 text-muted-foreground" />
          {/* 참여 */}
          <div className="text-center flex-1">
            <div className="text-2xl font-bold text-blue-500">{conversion_funnel.engaged}</div>
            <div className="text-sm text-muted-foreground">참여 발생</div>
            <div className="text-xs text-blue-500">{conversion_funnel.engagement_rate}%</div>
          </div>
          <ArrowRight className="w-5 h-5 text-muted-foreground" />
          {/* 연락 */}
          <div className="text-center flex-1">
            <div className="text-2xl font-bold text-yellow-500">{conversion_funnel.contacted}</div>
            <div className="text-sm text-muted-foreground">연락 유도</div>
            <div className="text-xs text-yellow-500">{conversion_funnel.contact_rate}%</div>
          </div>
          <ArrowRight className="w-5 h-5 text-muted-foreground" />
          {/* 전환 */}
          <div className="text-center flex-1">
            <div className="text-2xl font-bold text-green-500">{conversion_funnel.converted}</div>
            <div className="text-sm text-muted-foreground">전환 성공</div>
            <div className="text-xs text-green-500">{conversion_funnel.conversion_rate}%</div>
          </div>
        </div>

        {/* 퍼널 바 */}
        <div className="mt-4 h-3 bg-muted rounded-full overflow-hidden flex">
          <div
            className="bg-blue-500 h-full"
            style={{ width: `${(conversion_funnel.engaged / conversion_funnel.posted) * 100 || 0}%` }}
          />
          <div
            className="bg-yellow-500 h-full"
            style={{ width: `${(conversion_funnel.contacted / conversion_funnel.posted) * 100 || 0}%` }}
          />
          <div
            className="bg-green-500 h-full"
            style={{ width: `${(conversion_funnel.converted / conversion_funnel.posted) * 100 || 0}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* 플랫폼별 성과 */}
        <div className="bg-card border border-border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">플랫폼별 성과</h3>
          {by_platform.length === 0 ? (
            <p className="text-sm text-muted-foreground">데이터 없음</p>
          ) : (
            <div className="space-y-3">
              {by_platform.map((p) => (
                <div key={p.platform} className="flex items-center justify-between p-2 bg-muted/30 rounded-lg">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{platformLabels[p.platform] || p.platform}</span>
                    <span className="text-xs text-muted-foreground">{p.count}개</span>
                  </div>
                  <div className="flex items-center gap-3 text-sm">
                    <span className="text-blue-500" title="좋아요">👍 {p.total_likes}</span>
                    <span className="text-green-500" title="답글">💬 {p.total_replies}</span>
                    <span className="text-purple-500" title="전환">{p.conversions > 0 ? `✅ ${p.conversions}` : ''}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 템플릿별 성과 */}
        <div className="bg-card border border-border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">템플릿별 성과</h3>
          {by_template.length === 0 ? (
            <p className="text-sm text-muted-foreground">템플릿 사용 기록 없음</p>
          ) : (
            <div className="space-y-3">
              {by_template.slice(0, 5).map((t, idx) => (
                <div key={idx} className="flex items-center justify-between p-2 bg-muted/30 rounded-lg">
                  <div>
                    <span className="font-medium text-sm">{t.template_name}</span>
                    <span className="text-xs text-muted-foreground ml-2">{t.category}</span>
                  </div>
                  <div className="flex items-center gap-3 text-sm">
                    <span className="text-muted-foreground">{t.use_count}회</span>
                    <span className="text-blue-500">👍 {t.avg_likes}</span>
                    {t.conversions > 0 && <span className="text-green-500">✅ {t.conversions}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 최근 댓글 */}
      {recent_comments.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">최근 게시된 댓글</h3>
          <div className="space-y-3 max-h-80 overflow-y-auto">
            {recent_comments.slice(0, 10).map((comment) => (
              <div key={comment.id} className="p-3 bg-muted/30 rounded-lg">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm line-clamp-2">{comment.content}</p>
                    <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
                      <span>{platformLabels[comment.platform] || comment.platform}</span>
                      <span>•</span>
                      <span>{new Date(comment.posted_at).toLocaleDateString('ko-KR')}</span>
                      {comment.template_name && (
                        <>
                          <span>•</span>
                          <span className="text-primary">{comment.template_name}</span>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 text-sm shrink-0">
                    {comment.likes > 0 && <span className="text-blue-500">👍 {comment.likes}</span>}
                    {comment.replies > 0 && <span className="text-green-500">💬 {comment.replies}</span>}
                    {comment.led_to_conversion && <span className="text-green-600 font-bold">✅</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

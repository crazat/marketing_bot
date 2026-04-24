interface InstagramAnalysisProps {
  stats: any
  hashtagAnalysis: any[]
}

export default function InstagramAnalysis({ stats, hashtagAnalysis }: InstagramAnalysisProps) {
  return (
    <div className="space-y-6">
      {/* 통계 */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-card rounded-lg border border-border p-6">
            <div className="text-sm text-muted-foreground mb-1">총 포스트</div>
            <div className="text-3xl font-bold">{stats.total_posts || 0}</div>
          </div>
          <div className="bg-card rounded-lg border border-border p-6">
            <div className="text-sm text-muted-foreground mb-1">평균 좋아요</div>
            <div className="text-3xl font-bold">{stats.avg_likes?.toFixed(0) || 0}</div>
          </div>
          <div className="bg-card rounded-lg border border-border p-6">
            <div className="text-sm text-muted-foreground mb-1">평균 댓글</div>
            <div className="text-3xl font-bold">{stats.avg_comments?.toFixed(0) || 0}</div>
          </div>
          <div className="bg-card rounded-lg border border-border p-6">
            <div className="text-sm text-muted-foreground mb-1">참여율</div>
            <div className="text-3xl font-bold">
              {stats.engagement_rate?.toFixed(2) || 0}%
            </div>
          </div>
        </div>
      )}

      {/* 해시태그 분석 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">🏷️ 인기 해시태그</h3>
        {!hashtagAnalysis || hashtagAnalysis.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p>해시태그 데이터가 없습니다.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {hashtagAnalysis.slice(0, 12).map((tag: any, index: number) => (
              <div
                key={tag.hashtag ?? tag.name ?? `tag-${index}`}
                className="p-3 rounded-lg border border-border hover:border-primary/50 transition-colors"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium">#{tag.hashtag}</span>
                  <span className="text-xs px-2 py-1 rounded-full bg-muted">
                    {tag.usage_count}회
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary"
                      style={{
                        width: `${Math.min(100, (tag.usage_count / (hashtagAnalysis[0]?.usage_count || 1)) * 100)}%`
                      }}
                    />
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {tag.avg_engagement?.toFixed(1)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

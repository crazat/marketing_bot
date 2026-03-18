import { Heart, MessageCircle, Eye } from 'lucide-react';

interface EngagementMetricsProps {
  likes?: number;
  comments?: number;
  views?: number;
  size?: 'sm' | 'md';
}

export function EngagementMetrics({ likes, comments, views, size = 'sm' }: EngagementMetricsProps) {
  const hasAnyMetric = likes !== undefined || comments !== undefined || views !== undefined;

  if (!hasAnyMetric) {
    return <span className="text-xs text-muted-foreground">-</span>;
  }

  const iconSize = size === 'sm' ? 'w-3 h-3' : 'w-4 h-4';
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm';

  const formatNumber = (num: number) => {
    if (num >= 1000) {
      return `${(num / 1000).toFixed(1)}k`;
    }
    return num.toString();
  };

  return (
    <div className="inline-flex items-center gap-3">
      {likes !== undefined && likes > 0 && (
        <div className="inline-flex items-center gap-1 text-red-500" title={`좋아요 ${likes}개`}>
          <Heart className={iconSize} />
          <span className={`${textSize} font-medium`}>{formatNumber(likes)}</span>
        </div>
      )}

      {comments !== undefined && comments > 0 && (
        <div className="inline-flex items-center gap-1 text-blue-500" title={`댓글 ${comments}개`}>
          <MessageCircle className={iconSize} />
          <span className={`${textSize} font-medium`}>{formatNumber(comments)}</span>
        </div>
      )}

      {views !== undefined && views > 0 && (
        <div className="inline-flex items-center gap-1 text-muted-foreground" title={`조회수 ${views}회`}>
          <Eye className={iconSize} />
          <span className={`${textSize} font-medium`}>{formatNumber(views)}</span>
        </div>
      )}
    </div>
  );
}

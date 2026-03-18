
export function TargetSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, index) => (
        <div
          key={index}
          className="bg-card border border-border rounded-lg p-4 animate-pulse"
        >
          <div className="flex items-center gap-4">
            {/* 체크박스 */}
            <div className="w-4 h-4 bg-muted rounded"></div>

            {/* 플랫폼 배지 */}
            <div className="w-16 h-6 bg-muted rounded"></div>

            {/* 제목/내용 */}
            <div className="flex-1 space-y-2">
              <div className="h-4 bg-muted rounded w-3/4"></div>
              <div className="h-3 bg-muted/50 rounded w-1/2"></div>
            </div>

            {/* 카테고리 */}
            <div className="w-20 h-6 bg-muted rounded"></div>

            {/* 참여도 */}
            <div className="w-24 h-6 bg-muted rounded"></div>

            {/* 우선순위 */}
            <div className="w-12 h-8 bg-muted rounded"></div>

            {/* 재발견 */}
            <div className="w-16 h-6 bg-muted rounded"></div>

            {/* 시간 */}
            <div className="w-20 h-6 bg-muted rounded"></div>

            {/* 액션 */}
            <div className="w-24 h-8 bg-muted rounded"></div>
          </div>
        </div>
      ))}
    </div>
  );
}

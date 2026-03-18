interface CompetitorVitalsProps {
  vitals: any
}

export default function CompetitorVitals({ vitals }: CompetitorVitalsProps) {
  if (!vitals || !vitals.competitors || vitals.competitors.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p className="text-4xl mb-4">💪</p>
        <p className="text-lg font-semibold mb-2">경쟁사 활력 데이터가 없습니다</p>
        <p className="text-sm">경쟁사 리뷰 스크래핑을 먼저 실행하세요.</p>
      </div>
    )
  }

  const competitors = vitals.competitors
  const summary = vitals.summary

  return (
    <div className="space-y-6">
      {/* 요약 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="p-4 rounded-lg bg-muted">
          <div className="text-sm text-muted-foreground mb-1">총 경쟁사</div>
          <div className="text-2xl font-bold">{summary?.total_competitors || 0}</div>
        </div>
        <div className="p-4 rounded-lg bg-muted">
          <div className="text-sm text-muted-foreground mb-1">최다 리뷰</div>
          <div className="text-lg font-bold truncate">{summary?.most_active || '-'}</div>
        </div>
        <div className="p-4 rounded-lg bg-muted">
          <div className="text-sm text-muted-foreground mb-1">평균 리뷰 (30일)</div>
          <div className="text-2xl font-bold">
            {summary?.avg_reviews_30d?.toFixed(1) || 0}
          </div>
        </div>
        <div className="p-4 rounded-lg bg-muted">
          <div className="text-sm text-muted-foreground mb-1">총 리뷰 (30일)</div>
          <div className="text-2xl font-bold text-primary">
            {summary?.total_reviews_30d || 0}
          </div>
        </div>
      </div>

      {/* 경쟁사별 활동량 */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3 text-left text-sm font-semibold">경쟁사</th>
              <th className="px-4 py-3 text-center text-sm font-semibold">전체 리뷰</th>
              <th className="px-4 py-3 text-center text-sm font-semibold">30일</th>
              <th className="px-4 py-3 text-center text-sm font-semibold">7일</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">활동도</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">최근 스크래핑</th>
            </tr>
          </thead>
          <tbody>
            {competitors.map((comp: any, index: number) => (
              <tr
                key={index}
                className="border-b border-border hover:bg-accent/50 transition-colors"
              >
                <td className="px-4 py-3 font-medium">{comp.name}</td>
                <td className="px-4 py-3 text-center">{comp.total_reviews}</td>
                <td className="px-4 py-3 text-center font-bold text-primary">{comp.reviews_30d}</td>
                <td className="px-4 py-3 text-center">{comp.reviews_7d}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 max-w-[120px] h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className={`h-full ${
                          comp.reviews_30d >= 50 ? 'bg-red-500' :
                          comp.reviews_30d >= 30 ? 'bg-yellow-500' :
                          'bg-green-500'
                        }`}
                        style={{
                          width: `${Math.min(100, (comp.reviews_30d / 100) * 100)}%`
                        }}
                      />
                    </div>
                    <span className="text-sm whitespace-nowrap">
                      {comp.trend === 'active' ? '🔥 활발' :
                       comp.trend === 'moderate' ? '📊 보통' :
                       '💤 낮음'}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 text-sm text-muted-foreground">
                  {comp.last_scraped ? new Date(comp.last_scraped).toLocaleDateString('ko-KR') : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

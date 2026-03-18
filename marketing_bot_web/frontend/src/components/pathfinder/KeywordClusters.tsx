import Button from '@/components/ui/Button'
import { FileText } from 'lucide-react'

interface KeywordClustersProps {
  clusters: any[]
}

export default function KeywordClusters({ clusters }: KeywordClustersProps) {
  if (!clusters || clusters.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <p>클러스터가 없습니다.</p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {clusters.slice(0, 12).map((cluster, index) => {
        // 백엔드 필드명과 호환
        const name = cluster.cluster_name || cluster.core_word || '클러스터'
        const keywords = cluster.keywords || []
        const keywordCount = cluster.keyword_count || keywords.length || 0
        const totalVolume = cluster.total_search_volume || cluster.total_volume || 0
        const avgQuality = cluster.avg_quality || 0
        const sCount = cluster.s_count || 0
        const aCount = cluster.a_count || 0

        return (
          <div
            key={index}
            className="p-4 rounded-lg border border-border hover:border-primary/50 transition-colors"
          >
            <div className="flex items-start justify-between mb-3">
              <h4 className="font-semibold text-lg">
                {name}
              </h4>
              <span className="text-xs px-2 py-1 rounded-full bg-primary/10 text-primary font-medium">
                {keywordCount}개
              </span>
            </div>

            <div className="space-y-2 mb-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">총 검색량</span>
                <span className="font-medium">
                  {totalVolume.toLocaleString()}
                </span>
              </div>
              {(sCount > 0 || aCount > 0) && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">S/A급</span>
                  <span className="font-medium">
                    🔥 {sCount} / 🟢 {aCount}
                  </span>
                </div>
              )}
              {avgQuality > 0 && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">평균 품질</span>
                  <span className="font-medium">
                    {avgQuality.toFixed(1)}/4.0
                  </span>
                </div>
              )}
            </div>

            <div className="pt-3 border-t border-border">
              <p className="text-xs text-muted-foreground mb-2">포함 키워드 (최대 5개)</p>
              <div className="flex flex-wrap gap-1">
                {keywords.slice(0, 5).map((kw: string, i: number) => (
                  <span
                    key={i}
                    className="text-xs px-2 py-1 rounded-md bg-muted"
                  >
                    {kw}
                  </span>
                ))}
                {keywords.length > 5 && (
                  <span className="text-xs px-2 py-1 text-muted-foreground">
                    +{keywords.length - 5}개
                  </span>
                )}
              </div>
            </div>

            <div className="mt-3">
              <Button
                variant="outline"
                size="sm"
                fullWidth
                icon={<FileText size={14} />}
              >
                콘텐츠 생성
              </Button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

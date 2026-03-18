import MetricCard from '../MetricCard'

interface PathfinderStatsData {
  total: number
  s_grade: number
  a_grade: number
  b_grade: number
  c_grade: number
  categories?: Record<string, number>
  sources?: Record<string, number>
}

interface PathfinderStatsProps {
  stats: PathfinderStatsData | null | undefined
}

export default function PathfinderStats({ stats }: PathfinderStatsProps) {
  if (!stats) return null

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
      <MetricCard
        title="총 키워드"
        value={stats.total || 0}
        icon="🎯"
      />
      <MetricCard
        title="S급 키워드"
        value={stats.s_grade || 0}
        icon="🔥"
        color="text-red-500"
        trend={`${((stats.s_grade / stats.total) * 100).toFixed(1)}%`}
      />
      <MetricCard
        title="A급 키워드"
        value={stats.a_grade || 0}
        icon="🟢"
        color="text-green-500"
        trend={`${((stats.a_grade / stats.total) * 100).toFixed(1)}%`}
      />
      <MetricCard
        title="B급 키워드"
        value={stats.b_grade || 0}
        icon="🔵"
        color="text-blue-500"
      />
      <MetricCard
        title="C급 키워드"
        value={stats.c_grade || 0}
        icon="⚪"
        color="text-muted-foreground"
      />
    </div>
  )
}

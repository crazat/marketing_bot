import MetricCard from '../MetricCard'
import { Target, Flame, Sparkles, Star, Circle } from 'lucide-react'

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

const PI = 'w-[18px] h-[18px]'

export default function PathfinderStats({ stats }: PathfinderStatsProps) {
  if (!stats) return null

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
      <MetricCard title="총 키워드" value={stats.total || 0} icon={<Target className={PI} strokeWidth={1.8} />} />
      <MetricCard
        title="S급 키워드"
        value={stats.s_grade || 0}
        icon={<Flame className={PI} strokeWidth={1.8} />}
        trend={`${((stats.s_grade / stats.total) * 100).toFixed(1)}%`}
      />
      <MetricCard
        title="A급 키워드"
        value={stats.a_grade || 0}
        icon={<Sparkles className={PI} strokeWidth={1.8} />}
        trend={`${((stats.a_grade / stats.total) * 100).toFixed(1)}%`}
      />
      <MetricCard title="B급 키워드" value={stats.b_grade || 0} icon={<Star className={PI} strokeWidth={1.8} />} />
      <MetricCard title="C급 키워드" value={stats.c_grade || 0} icon={<Circle className={PI} strokeWidth={1.8} />} />
    </div>
  )
}

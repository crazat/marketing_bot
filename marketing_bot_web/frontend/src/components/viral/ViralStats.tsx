import MetricCard from '../MetricCard'

interface ViralStatsProps {
  stats: any
}

export default function ViralStats({ stats }: ViralStatsProps) {
  if (!stats) return null

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
      <MetricCard
        title="총 타겟"
        value={stats.total_targets || 0}
        icon="🎯"
      />
      <MetricCard
        title="대기 중"
        value={stats.pending || 0}
        icon="⏳"
        color="text-yellow-500"
      />
      <MetricCard
        title="승인됨"
        value={stats.approved || 0}
        icon="✅"
        color="text-green-500"
      />
      <MetricCard
        title="게시됨"
        value={stats.posted || 0}
        icon="🚀"
        color="text-blue-500"
      />
    </div>
  )
}

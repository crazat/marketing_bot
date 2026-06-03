import MetricCard from '../MetricCard'
import { Target, Clock, CheckCircle, Rocket } from 'lucide-react'

interface ViralStatsProps {
  stats: any
}

const SI = 'w-[18px] h-[18px]'

export default function ViralStats({ stats }: ViralStatsProps) {
  if (!stats) return null

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
      <MetricCard title="총 타겟" value={stats.total_targets || 0} icon={<Target className={SI} strokeWidth={1.8} />} />
      <MetricCard title="대기 중" value={stats.pending || 0} icon={<Clock className={SI} strokeWidth={1.8} />} />
      <MetricCard title="승인됨" value={stats.approved || 0} icon={<CheckCircle className={SI} strokeWidth={1.8} />} />
      <MetricCard title="게시됨" value={stats.posted || 0} icon={<Rocket className={SI} strokeWidth={1.8} />} />
    </div>
  )
}

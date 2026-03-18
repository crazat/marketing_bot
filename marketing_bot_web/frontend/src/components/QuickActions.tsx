import { useNavigate } from 'react-router-dom'
import Button from '@/components/ui/Button'

const actions = [
  { name: '키워드 발굴', href: '/pathfinder', icon: '🎯', color: 'bg-blue-500/10 hover:bg-blue-500/20 border-blue-500/30' },
  { name: '순위 체크', href: '/battle', icon: '⚔️', color: 'bg-red-500/10 hover:bg-red-500/20 border-red-500/30' },
  { name: '리드 관리', href: '/leads', icon: '📋', color: 'bg-green-500/10 hover:bg-green-500/20 border-green-500/30' },
  { name: 'Viral Hunter', href: '/viral', icon: '🔥', color: 'bg-purple-500/10 hover:bg-purple-500/20 border-purple-500/30' },
]

export default function QuickActions() {
  const navigate = useNavigate()

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {actions.map((action) => (
        <Button
          key={action.name}
          variant="ghost"
          onClick={() => navigate(action.href)}
          className={`p-6 h-auto flex-col border ${action.color}`}
        >
          <div className="text-4xl mb-2">{action.icon}</div>
          <div className="font-semibold">{action.name}</div>
        </Button>
      ))}
    </div>
  )
}

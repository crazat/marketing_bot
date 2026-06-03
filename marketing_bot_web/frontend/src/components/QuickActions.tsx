import { useNavigate } from 'react-router-dom'
import { Target, Swords, ClipboardList, Flame } from 'lucide-react'
import Button from '@/components/ui/Button'

const actions = [
  { name: '키워드 발굴', href: '/pathfinder', icon: <Target className="w-6 h-6" strokeWidth={1.6} />, color: 'bg-sage-tint hover:bg-surface-hover border-hair' },
  { name: '순위 체크', href: '/battle', icon: <Swords className="w-6 h-6" strokeWidth={1.6} />, color: 'bg-clay-tint hover:bg-surface-hover border-hair' },
  { name: '리드 관리', href: '/leads', icon: <ClipboardList className="w-6 h-6" strokeWidth={1.6} />, color: 'bg-mist-tint hover:bg-surface-hover border-hair' },
  { name: 'Viral Hunter', href: '/viral', icon: <Flame className="w-6 h-6" strokeWidth={1.6} />, color: 'bg-clay-tint hover:bg-surface-hover border-hair' },
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

import { NavLink } from 'react-router-dom'
import { BarChart3, Flame, ClipboardList, Target, Settings } from 'lucide-react'

interface TabDef {
  to: string
  label: string
  Icon: typeof BarChart3
  exact?: boolean
}

const TABS: TabDef[] = [
  { to: '/', label: '홈', Icon: BarChart3, exact: true },
  { to: '/viral', label: 'Viral', Icon: Flame },
  { to: '/leads', label: 'Leads', Icon: ClipboardList },
  { to: '/pathfinder', label: 'Paths', Icon: Target },
  { to: '/settings', label: '설정', Icon: Settings },
]

/**
 * [X4] 모바일 하단 탭바 — md 이하에서만 표시.
 *
 * 엄지 도달 영역에 주요 5개 페이지를 배치해 햄버거 메뉴 의존도를 낮춤.
 * 사이드바는 전체 네비, 탭바는 빈번 사용 5개만.
 */
export default function MobileTabBar() {
  return (
    <nav
      aria-label="주요 페이지 탭"
      className="md:hidden fixed bottom-0 left-0 right-0 z-30 bg-card/95 backdrop-blur-md border-t border-border"
    >
      <ul className="flex items-stretch justify-around h-14 safe-area-inset-bottom">
        {TABS.map(({ to, label, Icon, exact }) => (
          <li key={to} className="flex-1">
            <NavLink
              to={to}
              end={exact ?? false}
              className={({ isActive }) =>
                `flex flex-col items-center justify-center h-full gap-0.5 transition-colors ${
                  isActive
                    ? 'text-primary'
                    : 'text-muted-foreground hover:text-foreground'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className="w-5 h-5" />
                  <span className="text-[10px] font-medium">{label}</span>
                  {isActive && (
                    <span
                      aria-hidden
                      className="absolute top-0 h-0.5 w-8 bg-primary"
                    />
                  )}
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}

interface Tab {
  id: string
  label: string
  icon?: string
  /** 탭 라벨 옆에 표시할 카운트 배지 (0이면 숨김) */
  badge?: number
}

interface TabNavigationProps {
  tabs: Tab[]
  activeTab: string
  onTabChange: (tabId: string) => void
  ariaLabel?: string
}

export default function TabNavigation({
  tabs,
  activeTab,
  onTabChange,
  ariaLabel = '탭 네비게이션'
}: TabNavigationProps) {
  return (
    <div className="ros-tabbar" role="tablist" aria-label={ariaLabel}>
      {tabs.map((tab) => (
        <button
          type="button"
          key={tab.id}
          role="tab"
          aria-selected={activeTab === tab.id}
          aria-controls={`tabpanel-${tab.id}`}
          id={`tab-${tab.id}`}
          onClick={() => onTabChange(tab.id)}
          className={`ros-tab ${activeTab === tab.id ? 'on' : ''} focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary`}
        >
          {tab.label}
          {typeof tab.badge === 'number' && tab.badge > 0 && (
            <span className="ros-tab-badge">{tab.badge}</span>
          )}
        </button>
      ))}
    </div>
  )
}

// TabPanel 컴포넌트 - 접근성을 위해 추가
interface TabPanelProps {
  id: string
  activeTab: string
  children: React.ReactNode
}

export function TabPanel({ id, activeTab, children }: TabPanelProps) {
  if (activeTab !== id) return null

  return (
    <div
      role="tabpanel"
      id={`tabpanel-${id}`}
      aria-labelledby={`tab-${id}`}
    >
      {children}
    </div>
  )
}

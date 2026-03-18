interface Tab {
  id: string
  label: string
  icon?: string
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
    <div
      className="
        flex gap-1 sm:gap-2 border-b border-border overflow-x-auto
        scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent
        -mx-2 px-2 sm:mx-0 sm:px-0
      "
      role="tablist"
      aria-label={ariaLabel}
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={activeTab === tab.id}
          aria-controls={`tabpanel-${tab.id}`}
          id={`tab-${tab.id}`}
          onClick={() => onTabChange(tab.id)}
          className={`
            px-2.5 sm:px-4 py-2.5 sm:py-3 text-sm sm:text-base font-medium transition-colors relative whitespace-nowrap
            focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary
            flex-shrink-0
            ${activeTab === tab.id
              ? 'text-primary'
              : 'text-muted-foreground hover:text-foreground'
            }
          `}
        >
          {tab.label}
          {activeTab === tab.id && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
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

import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom'
import { useState, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSidebarPrefetch } from '@/hooks/usePrefetch'
import { Menu, X, AlertTriangle, Users, Clock, ChevronDown, ChevronRight, BarChart3, Megaphone, Briefcase, Wrench, Settings, Target, Swords, Flame, Music, ClipboardList, Coins, MessageSquare, Bot, LineChart, Eye } from 'lucide-react'
import { ThemeToggle } from '@/components/ui/ThemeProvider'
import useKeyboardShortcuts from '@/hooks/useKeyboardShortcuts'
import KeyboardShortcutsHelp from '@/components/ui/KeyboardShortcutsHelp'
import CommandPalette from '@/components/ui/CommandPalette'
import KeywordHub from '@/components/ui/KeywordHub'
import WebSocketIndicator from '@/components/WebSocketIndicator'
import BackToTop from '@/components/ui/BackToTop'
import { NotificationBell } from '@/components/NotificationCenter'
import { DashboardSettingsButton } from '@/components/DashboardSettings'
import { OfflineBanner } from '@/components/ui/OfflineBanner'
import { leadsApi, configApi } from '@/services/api'
import Button, { IconButton } from '@/components/ui/Button'

// 그룹화된 네비게이션 구조
interface NavItem {
  name: string
  href: string
  icon: React.ReactNode
}

interface NavGroup {
  id: string
  name: string
  icon: React.ReactNode
  items: NavItem[]
  defaultOpen?: boolean
}

const navigationGroups: NavGroup[] = [
  {
    id: 'home',
    name: '홈',
    icon: <BarChart3 className="w-4 h-4" />,
    items: [
      { name: '대시보드', href: '/', icon: <BarChart3 className="w-4 h-4" /> },
    ],
    defaultOpen: true,
  },
  {
    id: 'analysis',
    name: '분석 도구',
    icon: <LineChart className="w-4 h-4" />,
    items: [
      { name: 'Pathfinder', href: '/pathfinder', icon: <Target className="w-4 h-4 text-blue-500" /> },
      { name: 'Battle Intelligence', href: '/battle', icon: <Swords className="w-4 h-4 text-red-500" /> },
      { name: '경쟁사 분석', href: '/competitors', icon: <Eye className="w-4 h-4 text-purple-500" /> },
      { name: '마케팅 분석', href: '/analytics', icon: <LineChart className="w-4 h-4 text-green-500" /> },
    ],
    defaultOpen: true,
  },
  {
    id: 'content',
    name: '콘텐츠 수집',
    icon: <Megaphone className="w-4 h-4" />,
    items: [
      { name: 'Viral Hunter', href: '/viral', icon: <Flame className="w-4 h-4 text-orange-500" /> },
      { name: 'TikTok', href: '/tiktok', icon: <Music className="w-4 h-4 text-pink-500" /> },
    ],
  },
  {
    id: 'sales',
    name: '영업 관리',
    icon: <Briefcase className="w-4 h-4" />,
    items: [
      { name: 'Lead Manager', href: '/leads', icon: <ClipboardList className="w-4 h-4 text-blue-500" /> },
      { name: 'Marketing Hub', href: '/marketing', icon: <Coins className="w-4 h-4 text-yellow-500" /> },
    ],
  },
  {
    id: 'tools',
    name: '도구',
    icon: <Wrench className="w-4 h-4" />,
    items: [
      { name: 'Q&A Repository', href: '/qa', icon: <MessageSquare className="w-4 h-4 text-cyan-500" /> },
      { name: 'AI Agent', href: '/agent', icon: <Bot className="w-4 h-4 text-purple-500" /> },
    ],
  },
  {
    id: 'settings',
    name: '설정',
    icon: <Settings className="w-4 h-4" />,
    items: [
      { name: '설정', href: '/settings', icon: <Settings className="w-4 h-4 text-gray-500" /> },
    ],
  },
]

// 핫리드 알림 배너 컴포넌트
function HotLeadBanner({
  pendingAlerts,
  onDismiss
}: {
  pendingAlerts: { hot_leads: Array<{ id: number; title: string; score: number; platform: string }>; overdue_leads: Array<{ id: number; title: string; hours_pending: number }>; total_alerts: number } | undefined
  onDismiss: () => void
}) {
  const navigate = useNavigate()

  if (!pendingAlerts || pendingAlerts.total_alerts === 0) return null

  const { hot_leads, overdue_leads, total_alerts } = pendingAlerts
  const topHotLead = hot_leads[0]
  const topOverdue = overdue_leads[0]

  return (
    <div className="bg-gradient-to-r from-red-500/90 to-orange-500/90 text-white px-4 py-2 flex items-center justify-between gap-4 shadow-lg">
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <div className="p-1.5 bg-white/20 rounded-full">
          <AlertTriangle className="w-4 h-4" />
        </div>
        <div className="flex items-center gap-4 flex-1 min-w-0 overflow-hidden">
          {topHotLead && (
            <div className="flex items-center gap-2 text-sm">
              <Users className="w-4 h-4 flex-shrink-0" />
              <span className="truncate">
                <strong>Hot Lead:</strong> {topHotLead.title.slice(0, 30)}... ({topHotLead.score}점)
              </span>
            </div>
          )}
          {topOverdue && !topHotLead && (
            <div className="flex items-center gap-2 text-sm">
              <Clock className="w-4 h-4 flex-shrink-0" />
              <span className="truncate">
                <strong>긴급:</strong> {Math.round(topOverdue.hours_pending)}시간 대기 중
              </span>
            </div>
          )}
          {total_alerts > 1 && (
            <span className="text-xs bg-white/20 px-2 py-0.5 rounded-full flex-shrink-0">
              +{total_alerts - 1}개 더
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/leads?tab=pending')}
          className="bg-white/20 hover:bg-white/30 text-white"
        >
          확인하기
        </Button>
        <IconButton
          icon={<X className="w-4 h-4" />}
          onClick={onDismiss}
          size="sm"
          title="알림 닫기"
          className="hover:bg-white/20 text-white"
        />
      </div>
    </div>
  )
}

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)
  // [Phase E-3] KeywordHub 상태
  const [keywordHubOpen, setKeywordHubOpen] = useState(false)
  const [keywordHubKeyword, setKeywordHubKeyword] = useState('')
  // 핫리드 배너 숨김 상태 (세션 동안 유지)
  const [bannerDismissed, setBannerDismissed] = useState(false)
  // 메뉴 그룹 접힘 상태
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => {
    const defaultOpen = navigationGroups.filter(g => g.defaultOpen).map(g => g.id)
    return new Set(defaultOpen)
  })
  const location = useLocation()
  // [성능 최적화] 프리페칭
  const { handleMouseEnter, handleMouseLeave } = useSidebarPrefetch()

  const toggleGroup = (groupId: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev)
      if (next.has(groupId)) {
        next.delete(groupId)
      } else {
        next.add(groupId)
      }
      return next
    })
  }

  // 현재 페이지가 속한 그룹 자동 확장
  useEffect(() => {
    const currentGroup = navigationGroups.find(g =>
      g.items.some(item => item.href === location.pathname)
    )
    if (currentGroup && !expandedGroups.has(currentGroup.id)) {
      setExpandedGroups(prev => new Set([...prev, currentGroup.id]))
    }
  }, [location.pathname])

  // [Phase 1.5] 키보드 단축키
  const { showHelp, setShowHelp, shortcuts } = useKeyboardShortcuts()

  // [Phase 4.0] Hot Lead 긴급 알림 조회 (사이드바 배지용)
  const { data: pendingAlerts } = useQuery({
    queryKey: ['leads-pending-alerts'],
    queryFn: leadsApi.getPendingAlerts,
    refetchInterval: 60000,
    retry: 1,
  })
  const alertCount = pendingAlerts?.total_alerts || 0

  // [Phase 7.0] 브랜딩 정보 조회
  const { data: branding } = useQuery({
    queryKey: ['branding'],
    queryFn: configApi.getBranding,
    staleTime: 1000 * 60 * 60, // 1시간 캐시
    retry: 1,
  })
  const brandTagline = branding?.tagline || '마케팅 OS'

  // [Phase 3.3] Command Palette 단축키 (Ctrl+K)
  const handleCommandPaletteShortcut = useCallback((e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault()
      setCommandPaletteOpen(prev => !prev)
    }
  }, [])

  useEffect(() => {
    window.addEventListener('keydown', handleCommandPaletteShortcut)
    return () => window.removeEventListener('keydown', handleCommandPaletteShortcut)
  }, [handleCommandPaletteShortcut])

  return (
    <div className="min-h-screen bg-background">
      {/* 오프라인 상태 배너 */}
      <OfflineBanner />

      {/* Skip Link - 키보드 사용자를 위한 바로가기 */}
      <a
        href="#main-content"
        className="
          sr-only focus:not-sr-only
          focus:absolute focus:top-4 focus:left-4 focus:z-[100]
          bg-primary text-primary-foreground
          px-4 py-2 rounded-lg font-medium
          focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2
        "
      >
        본문으로 건너뛰기
      </a>
      {/* 모바일 사이드바 토글 - md에서는 축소 사이드바가 보이므로 숨김 */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-50 bg-card border-b border-border p-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold">Marketing Bot</h1>
          <div className="flex items-center gap-2">
            <NotificationBell />
            <DashboardSettingsButton />
            <ThemeToggle />
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-2 rounded-md hover:bg-accent focus:outline-none focus:ring-2 focus:ring-primary"
              aria-label={sidebarOpen ? '메뉴 닫기' : '메뉴 열기'}
              aria-expanded={sidebarOpen}
              aria-controls="sidebar"
            >
              <Menu className="w-6 h-6" />
            </button>
          </div>
        </div>
      </div>

      <div>
        {/* 사이드바 - md: 축소(아이콘만), lg: 전체 */}
        <aside
          id="sidebar"
          className={`
            fixed inset-y-0 left-0 z-40 bg-card border-r border-border
            transform transition-all duration-300 ease-in-out
            w-64 md:w-16 lg:w-64
            md:translate-x-0
            ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
          `}
          aria-label="사이드바"
        >
          <div className="flex flex-col h-full">
            {/* 로고 - md: 아이콘만, lg: 전체 */}
            <div className="px-3 lg:px-6 py-4 lg:py-6 border-b border-border">
              <h1 className="text-2xl font-bold">
                <span className="lg:hidden text-center block">🧠</span>
                <span className="hidden lg:inline">🧠 Marketing Bot</span>
              </h1>
              <p className="hidden lg:block text-sm text-muted-foreground mt-1">
                {brandTagline}
              </p>
            </div>

            {/* 네비게이션 - md: 아이콘만, lg: 전체 그룹화 */}
            <nav
              className="flex-1 px-2 lg:px-4 py-4 space-y-1 overflow-y-auto"
              aria-label="메인 네비게이션"
            >
              {navigationGroups.map((group) => {
                const isExpanded = expandedGroups.has(group.id)
                const hasActiveItem = group.items.some(item => item.href === location.pathname)
                const isSingleItem = group.items.length === 1

                // 단일 항목 그룹은 바로 링크로 표시
                if (isSingleItem) {
                  const item = group.items[0]
                  const isActive = location.pathname === item.href
                  return (
                    <Link
                      key={group.id}
                      to={item.href}
                      onClick={() => setSidebarOpen(false)}
                      onMouseEnter={() => handleMouseEnter(item.href)}
                      onMouseLeave={handleMouseLeave}
                      aria-current={isActive ? 'page' : undefined}
                      title={item.name}
                      className={`
                        flex items-center justify-center lg:justify-start gap-3 px-3 py-2.5 rounded-lg
                        transition-all duration-200 ease-out
                        focus:outline-none focus:ring-2 focus:ring-primary focus:ring-inset
                        ${isActive
                          ? 'bg-primary text-primary-foreground shadow-md'
                          : 'hover:bg-accent'
                        }
                      `}
                    >
                      <span aria-hidden="true">{item.icon}</span>
                      <span className="hidden lg:inline font-medium">{item.name}</span>
                    </Link>
                  )
                }

                return (
                  <div key={group.id} className="space-y-0.5">
                    {/* 그룹 헤더 - md에서는 숨김 */}
                    <button
                      onClick={() => toggleGroup(group.id)}
                      className={`
                        hidden lg:flex w-full items-center gap-2 px-3 py-2 rounded-lg text-sm
                        transition-colors hover:bg-accent
                        ${hasActiveItem ? 'text-primary font-medium' : 'text-muted-foreground'}
                      `}
                      aria-expanded={isExpanded}
                    >
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 flex-shrink-0" />
                      ) : (
                        <ChevronRight className="w-4 h-4 flex-shrink-0" />
                      )}
                      <span className="flex-1 text-left">{group.name}</span>
                      <span className="text-xs text-muted-foreground">{group.items.length}</span>
                    </button>

                    {/* 그룹 아이템 - md: 항상 표시(아이콘만), lg: 확장시 표시 */}
                    <div className={`lg:ml-4 space-y-0.5 ${isExpanded ? 'lg:block' : 'lg:hidden'} block`}>
                      {group.items.map((item) => {
                        const isActive = location.pathname === item.href
                        const showBadge = item.href === '/leads' && alertCount > 0

                        return (
                          <Link
                            key={item.name}
                            to={item.href}
                            onClick={() => setSidebarOpen(false)}
                            onMouseEnter={() => handleMouseEnter(item.href)}
                            onMouseLeave={handleMouseLeave}
                            aria-current={isActive ? 'page' : undefined}
                            title={item.name}
                            className={`
                              flex items-center justify-center lg:justify-start gap-2.5 px-3 py-2 rounded-lg text-sm
                              transition-all duration-200 ease-out
                              focus:outline-none focus:ring-2 focus:ring-primary focus:ring-inset
                              ${isActive
                                ? 'bg-primary text-primary-foreground shadow-sm'
                                : 'hover:bg-accent lg:hover:translate-x-0.5'
                              }
                            `}
                          >
                            <span aria-hidden="true" className="relative">
                              {item.icon}
                              {/* md에서 배지 표시 (아이콘 우상단) */}
                              {showBadge && (
                                <span
                                  className="lg:hidden absolute -top-1 -right-1 w-2 h-2 bg-red-500 rounded-full animate-pulse"
                                  aria-label={`${alertCount}개의 긴급 리드`}
                                />
                              )}
                            </span>
                            <span className="hidden lg:inline flex-1">{item.name}</span>
                            {/* lg에서 배지 표시 (텍스트 옆) */}
                            {showBadge && (
                              <span
                                className="hidden lg:inline px-1.5 py-0.5 text-xs font-bold bg-red-500 text-white rounded-full animate-pulse"
                                aria-label={`${alertCount}개의 긴급 리드`}
                              >
                                {alertCount}
                              </span>
                            )}
                          </Link>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </nav>

            {/* 푸터 - md: 아이콘만, lg: 전체 */}
            <div className="px-2 lg:px-6 py-4 border-t border-border">
              <div className="flex flex-col lg:flex-row items-center justify-center lg:justify-between gap-2 lg:gap-0 mb-3">
                <span className="hidden lg:inline text-xs text-muted-foreground">빠른 설정</span>
                <div className="flex items-center gap-1">
                  <NotificationBell />
                  <DashboardSettingsButton />
                  <ThemeToggle />
                </div>
              </div>
              <button
                onClick={() => setCommandPaletteOpen(true)}
                className="hidden lg:flex w-full text-xs text-muted-foreground hover:text-foreground transition-colors mb-2 items-center gap-1 px-2 py-1.5 bg-muted/50 rounded-lg hover:bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                aria-label="명령 팔레트 열기 (Ctrl+K)"
              >
                <kbd className="px-1.5 py-0.5 bg-background rounded text-[10px] font-mono" aria-hidden="true">Ctrl</kbd>
                <kbd className="px-1.5 py-0.5 bg-background rounded text-[10px] font-mono" aria-hidden="true">K</kbd>
                <span className="ml-1">명령 팔레트</span>
              </button>
              <button
                onClick={() => setShowHelp(true)}
                className="hidden lg:flex text-xs text-muted-foreground hover:text-foreground transition-colors mb-2 items-center gap-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
                aria-label="키보드 단축키 도움말 열기"
              >
                <kbd className="px-1 py-0.5 bg-muted rounded text-[10px] font-mono" aria-hidden="true">?</kbd>
                단축키 도움말
              </button>
              <p className="hidden lg:block text-xs text-muted-foreground">
                Version 2.0.0
              </p>
            </div>
          </div>
        </aside>

        {/* 메인 컨텐츠 - 사이드바 너비만큼 왼쪽 마진 (md: 축소, lg: 전체) */}
        <main
          id="main-content"
          className="min-h-screen pt-16 md:pt-0 md:ml-16 lg:ml-64"
          role="main"
          tabIndex={-1}
        >
          {/* 핫리드 알림 배너 */}
          {!bannerDismissed && location.pathname !== '/leads' && (
            <HotLeadBanner
              pendingAlerts={pendingAlerts}
              onDismiss={() => setBannerDismissed(true)}
            />
          )}
          <div className="max-w-7xl mx-auto p-6">
            <Outlet />
          </div>
        </main>
      </div>

      {/* 모바일 사이드바 오버레이 - md 이상에서는 숨김 (축소 사이드바가 보임) */}
      <div
        className={`
          fixed inset-0 bg-black/50 z-30 md:hidden
          transition-opacity duration-300
          ${sidebarOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'}
        `}
        onClick={() => setSidebarOpen(false)}
        aria-hidden="true"
      />

      {/* [Phase 1.5] 키보드 단축키 도움말 */}
      <KeyboardShortcutsHelp
        isOpen={showHelp}
        onClose={() => setShowHelp(false)}
        shortcuts={shortcuts}
      />

      {/* [Phase 3.3] Command Palette */}
      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        onOpenKeywordHub={(keyword) => {
          setKeywordHubKeyword(keyword)
          setKeywordHubOpen(true)
        }}
      />

      {/* [Phase E-3] Keyword Hub (from Command Palette) */}
      {keywordHubOpen && keywordHubKeyword && (
        <KeywordHub
          keyword={keywordHubKeyword}
          onClose={() => {
            setKeywordHubOpen(false)
            setKeywordHubKeyword('')
          }}
        />
      )}

      {/* [Phase 4.0] WebSocket 연결 상태 표시 */}
      <WebSocketIndicator />

      {/* Back to Top 버튼 */}
      <BackToTop />
    </div>
  )
}

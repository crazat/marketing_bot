import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom'
import { useState, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSidebarPrefetch } from '@/hooks/usePrefetch'
import { Menu, X, AlertTriangle, Users, Clock, BarChart3, Megaphone, Briefcase, Wrench, Settings, Target, Swords, Flame, Music, ClipboardList, Coins, MessageSquare, Bot, LineChart, Eye, Sun, Moon, Search } from 'lucide-react'
import { ThemeToggle, useTheme } from '@/components/ui/ThemeProvider'
import useKeyboardShortcuts from '@/hooks/useKeyboardShortcuts'
import { useGlobalNav } from '@/hooks/useGlobalNav'
import KeyboardShortcutsHelp from '@/components/ui/KeyboardShortcutsHelp'
import CommandPalette from '@/components/ui/CommandPalette'
import KeywordHub from '@/components/ui/KeywordHub'
import WebSocketIndicator from '@/components/WebSocketIndicator'
import BackToTop from '@/components/ui/BackToTop'
import { NotificationBell } from '@/components/NotificationCenter'
import Breadcrumb from '@/components/Breadcrumb'
import OnboardingTour from '@/components/OnboardingTour'
import { useToast } from '@/components/ui/Toast'
import MobileTabBar from '@/components/MobileTabBar'
import FeedbackWidget from '@/components/FeedbackWidget'
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

// [RECOVER OS] 모노톤 라인 아이콘 — 색상은 nav 상태(text-muted/sage)에서 상속, 1.7 stroke
const ICON = 'w-[17px] h-[17px]'
const navigationGroups: NavGroup[] = [
  {
    id: 'home',
    name: '홈',
    icon: <BarChart3 className={ICON} strokeWidth={1.7} />,
    items: [
      { name: '대시보드', href: '/', icon: <BarChart3 className={ICON} strokeWidth={1.7} /> },
    ],
    defaultOpen: true,
  },
  {
    id: 'analysis',
    name: '분석 도구',
    icon: <LineChart className={ICON} strokeWidth={1.7} />,
    items: [
      { name: 'Pathfinder', href: '/pathfinder', icon: <Target className={ICON} strokeWidth={1.7} /> },
      { name: 'Battle Intelligence', href: '/battle', icon: <Swords className={ICON} strokeWidth={1.7} /> },
      { name: '경쟁사 분석', href: '/competitors', icon: <Eye className={ICON} strokeWidth={1.7} /> },
    ],
    defaultOpen: true,
  },
  {
    id: 'content',
    name: '콘텐츠 수집',
    icon: <Megaphone className={ICON} strokeWidth={1.7} />,
    items: [
      { name: 'Viral Hunter', href: '/viral', icon: <Flame className={ICON} strokeWidth={1.7} /> },
      { name: 'TikTok', href: '/tiktok', icon: <Music className={ICON} strokeWidth={1.7} /> },
    ],
  },
  {
    id: 'sales',
    name: '영업 관리',
    icon: <Briefcase className={ICON} strokeWidth={1.7} />,
    items: [
      { name: 'Lead Manager', href: '/leads', icon: <ClipboardList className={ICON} strokeWidth={1.7} /> },
      { name: 'Marketing Hub', href: '/marketing', icon: <Coins className={ICON} strokeWidth={1.7} /> },
    ],
  },
  {
    id: 'tools',
    name: '도구',
    icon: <Wrench className={ICON} strokeWidth={1.7} />,
    items: [
      { name: 'Q&A Repository', href: '/qa', icon: <MessageSquare className={ICON} strokeWidth={1.7} /> },
      { name: 'AI Agent', href: '/agent', icon: <Bot className={ICON} strokeWidth={1.7} /> },
    ],
  },
  {
    id: 'settings',
    name: '설정',
    icon: <Settings className={ICON} strokeWidth={1.7} />,
    items: [
      { name: '설정', href: '/settings', icon: <Settings className={ICON} strokeWidth={1.7} /> },
    ],
  },
]

// [RECOVER OS] 토픽바 테마 스위치 (sun/moon 세그먼트)
function ThemeSwitch() {
  const { resolvedTheme, setTheme } = useTheme()
  return (
    <div className="ros-theme-switch" role="group" aria-label="테마 전환">
      <button
        type="button"
        className={resolvedTheme === 'light' ? 'on' : ''}
        onClick={() => setTheme('light')}
        title="라이트 모드"
        aria-label="라이트 모드"
        aria-pressed={resolvedTheme === 'light'}
      >
        <Sun className="w-[15px] h-[15px]" strokeWidth={1.8} />
      </button>
      <button
        type="button"
        className={resolvedTheme === 'dark' ? 'on' : ''}
        onClick={() => setTheme('dark')}
        title="다크 모드"
        aria-label="다크 모드"
        aria-pressed={resolvedTheme === 'dark'}
      >
        <Moon className="w-[15px] h-[15px]" strokeWidth={1.8} />
      </button>
    </div>
  )
}

// [RECOVER OS] 라이브 날짜 칩 — "6월 3일 화 · 09:12"
function formatDateChip(d: Date): string {
  const wd = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()]
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${wd} · ${hh}:${mm}`
}

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
    <div className="bg-gradient-to-r from-red-500/90 to-orange-500/90 text-white px-4 py-2 flex flex-col gap-2 shadow-lg sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <div className="p-1.5 bg-white/20 rounded-full">
          <AlertTriangle className="w-4 h-4" />
        </div>
        <div className="flex items-center gap-3 flex-1 min-w-0 overflow-hidden">
          {topHotLead && (
            <div className="flex items-center gap-2 text-sm">
              <Users className="w-4 h-4 flex-shrink-0" />
              <span className="truncate">
                <strong>Hot Lead:</strong> {topHotLead.title.slice(0, 30)}{topHotLead.title.length > 30 ? '...' : ''} ({topHotLead.score}점)
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
      <div className="flex items-center justify-end gap-2 flex-shrink-0">
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
  const location = useLocation()
  // [성능 최적화] 프리페칭
  const { handleMouseEnter, handleMouseLeave } = useSidebarPrefetch()

  // [RECOVER OS] 토픽바 라이브 날짜 — 1분마다 갱신
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30000)
    return () => clearInterval(t)
  }, [])

  // [Phase 1.5] 키보드 단축키
  const { showHelp, setShowHelp, shortcuts } = useKeyboardShortcuts()

  // [X6] 전역 g-prefix 네비
  const [navHint, setNavHint] = useState<string | null>(null)
  useGlobalNav({
    onPrefixStart: () =>
      setNavHint('다음 키: H 홈 · V Viral · L Leads · P Pathfinder · B Battle · C 경쟁사 · Q Q&A · M Marketing · S 설정'),
    onCancel: () => setNavHint(null),
  })

  // [EE3] 인증 실패 이벤트 수신 → 사용자 안내 토스트
  const authToast = useToast()
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { status: number } | undefined
      const status = detail?.status ?? 0
      if (status === 401) {
        authToast.error('인증이 만료되었습니다. API 키를 확인하거나 다시 로그인하세요.', 10000)
      } else if (status === 403) {
        authToast.error('이 작업에 대한 권한이 없습니다.', 8000)
      }
    }
    window.addEventListener('api:auth-failure', handler)
    return () => window.removeEventListener('api:auth-failure', handler)
  }, [authToast])

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

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSidebarOpen(false)
    }

    if (!sidebarOpen) return
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', handleEscape)

    return () => {
      document.body.style.overflow = ''
      window.removeEventListener('keydown', handleEscape)
    }
  }, [sidebarOpen])

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
          <Link to="/" className="text-xl font-bold truncate" onClick={() => setSidebarOpen(false)}>
            Marketing Bot
          </Link>
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
              {sidebarOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>
        </div>
      </div>

      <div>
        {/* 사이드바 - md: 축소(아이콘만), lg: 전체 */}
        <aside
          id="sidebar"
          className={`
            fixed inset-y-0 left-0 z-[60] md:z-40 bg-card border-r border-border
            transform transition-all duration-300 ease-in-out
            w-64 md:w-16 lg:w-64
            md:translate-x-0
            ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
          `}
          aria-label="주 메뉴"
        >
          <div className="flex flex-col h-full">
            {/* 브랜드 — md: 마크만, lg: 전체 */}
            <div className="px-3 lg:px-5 py-[18px] border-b" style={{ borderColor: 'var(--hair)' }}>
              <div className="flex items-center justify-between gap-2">
                <Link
                  to="/"
                  onClick={() => setSidebarOpen(false)}
                  className="flex items-center gap-[11px] min-w-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-lg"
                  aria-label="대시보드로 이동"
                >
                  <span className="ros-brand-mark" aria-hidden="true">M</span>
                  <span className="min-w-0 block md:hidden lg:block">
                    <span className="block font-display text-[17px] leading-none text-strong" style={{ fontWeight: 480, letterSpacing: '-0.01em' }}>
                      Marketing Bot
                    </span>
                    <span className="block mono-label text-[10.5px] mt-[5px] text-faint truncate">{brandTagline}</span>
                  </span>
                </Link>
                <IconButton
                  icon={<X className="w-4 h-4" />}
                  onClick={() => setSidebarOpen(false)}
                  size="sm"
                  title="메뉴 닫기"
                  className="md:hidden"
                />
              </div>
            </div>

            {/* 네비게이션 - md: 아이콘만, lg: 그룹 라벨 + 전체 (RECOVER OS sage-rail) */}
            <nav
              className="flex-1 px-3 py-3.5 overflow-y-auto"
              aria-label="메인 네비게이션"
            >
              {navigationGroups.map((group) => (
                <div key={group.id} className="mb-1">
                  <div className="ros-nav-group-label block md:hidden lg:block">{group.name}</div>
                  <div className="space-y-px">
                    {group.items.map((item) => {
                      const isActive = location.pathname === item.href
                      const showCount = item.href === '/leads' && alertCount > 0
                      const isViral = item.href === '/viral'

                      return (
                        <Link
                          key={item.name}
                          to={item.href}
                          onClick={() => setSidebarOpen(false)}
                          onMouseEnter={() => handleMouseEnter(item.href)}
                          onMouseLeave={handleMouseLeave}
                          aria-current={isActive ? 'page' : undefined}
                          title={item.name}
                          className={`ros-nav-item justify-center lg:justify-start focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-inset ${isActive ? 'active' : ''}`}
                        >
                          <span aria-hidden="true" className="relative inline-flex">
                            {item.icon}
                            {showCount && (
                              <span
                                className="lg:hidden absolute -top-1 -right-1 w-2 h-2 rounded-full animate-pulse"
                                style={{ background: 'var(--danger)' }}
                                aria-label={`${alertCount}개의 긴급 리드`}
                              />
                            )}
                          </span>
                          <span className="label block md:hidden lg:block">{item.name}</span>
                          {showCount && (
                            <span className="ros-nav-badge hidden lg:inline-flex" aria-label={`${alertCount}개의 긴급 리드`}>
                              {alertCount}
                            </span>
                          )}
                          {isViral && <span className="ros-nav-dot hidden lg:block" aria-hidden="true" />}
                        </Link>
                      )
                    })}
                  </div>
                </div>
              ))}
            </nav>

            {/* 푸터 — 라이브 상태 블록 + 유틸 + 버전 */}
            <div className="px-3 py-3 border-t flex flex-col gap-2" style={{ borderColor: 'var(--hair)' }}>
              <div className="ros-sb-status block md:hidden lg:flex">
                <span className="ros-sb-dot" aria-hidden="true" />
                <div className="min-w-0">
                  <div className="text-[11.5px] font-semibold text-strong whitespace-nowrap">스케줄러 running</div>
                  <div className="text-[10px] text-faint truncate">실시간 동기화 · Sentinel 정상</div>
                </div>
              </div>
              <div className="flex items-center justify-center lg:justify-between gap-1">
                <button
                  onClick={() => setCommandPaletteOpen(true)}
                  className="ros-cmdk hidden lg:flex flex-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  aria-label="명령 팔레트 열기 (Ctrl+K)"
                >
                  <Search className="w-[15px] h-[15px] flex-shrink-0" strokeWidth={1.8} />
                  <span className="truncate text-left">검색 · 명령 팔레트</span>
                  <span className="ml-auto flex gap-1" aria-hidden="true">
                    <span className="ros-kbd">Ctrl</span><span className="ros-kbd">K</span>
                  </span>
                </button>
                <div className="flex items-center gap-1">
                  <NotificationBell />
                  <DashboardSettingsButton />
                  <ThemeToggle />
                </div>
              </div>
              <button
                onClick={() => setShowHelp(true)}
                className="hidden lg:flex text-[11px] text-faint hover:text-foreground transition-colors items-center gap-1.5 px-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
                aria-label="키보드 단축키 도움말 열기"
              >
                <kbd className="ros-kbd" aria-hidden="true">?</kbd>
                단축키 도움말
              </button>
              <p className="hidden lg:block text-[11px] text-faint px-1">Version 2.0.0 · Recover Edition</p>
            </div>
          </div>
        </aside>

        {/* 메인 컨텐츠 - 사이드바 너비만큼 왼쪽 마진 (md: 축소, lg: 전체) */}
        <main
          id="main-content"
          className="min-h-screen pt-16 md:pt-0 md:ml-16 lg:ml-64 pb-16 md:pb-0"
          role="main"
          tabIndex={-1}
        >
          {/* [RECOVER OS] 데스크톱 토픽바 — breadcrumb · 명령 팔레트 · 날짜칩 · 테마 스위치 (모바일은 상단 바 사용) */}
          <header
            className="hidden md:flex sticky top-0 z-20 items-center gap-4 px-4 lg:px-7 py-3 border-b"
            style={{
              borderColor: 'var(--hair)',
              background: 'color-mix(in oklab, var(--bg-grain) 78%, transparent)',
              backdropFilter: 'blur(14px) saturate(1.1)',
            }}
          >
            <div className="min-w-0 flex-shrink-0">
              <Breadcrumb />
            </div>
            <button
              onClick={() => setCommandPaletteOpen(true)}
              className="ros-cmdk ml-1 flex-1 max-w-[420px] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              aria-label="명령 팔레트 (Ctrl+K)"
            >
              <Search className="w-[15px] h-[15px] flex-shrink-0" strokeWidth={1.8} />
              <span className="truncate text-left">키워드 · 리드 · 타겟 · 페이지 검색…</span>
              <span className="ml-auto flex gap-1" aria-hidden="true">
                <span className="ros-kbd">Ctrl</span><span className="ros-kbd">K</span>
              </span>
            </button>
            <div className="ml-auto flex items-center gap-1.5">
              <div className="ros-date-chip hidden lg:inline-flex">
                <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: 'var(--clay)' }} aria-hidden="true" />
                {formatDateChip(now)}
              </div>
              <ThemeSwitch />
              <NotificationBell />
            </div>
          </header>

          {/* 핫리드 알림 배너 */}
          {!bannerDismissed && location.pathname !== '/leads' && (
            <HotLeadBanner
              pendingAlerts={pendingAlerts}
              onDismiss={() => setBannerDismissed(true)}
            />
          )}
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-7 py-6">
            <Outlet />
          </div>
        </main>
      </div>

      {/* 모바일 사이드바 오버레이 - md 이상에서는 숨김 (축소 사이드바가 보임) */}
      <div
        className={`
          fixed inset-0 bg-black/50 z-[55] md:hidden
          transition-opacity duration-300
          ${sidebarOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'}
        `}
        onClick={() => setSidebarOpen(false)}
        aria-hidden="true"
      />

      {/* [X6] g-prefix 힌트 */}
      {navHint && (
        <div
          role="status"
          aria-live="polite"
          className="fixed top-4 left-1/2 -translate-x-1/2 z-[70] bg-card border border-primary/40 shadow-lg px-4 py-2 rounded animate-slide-down"
        >
          <div className="flex items-center gap-2 text-xs">
            <kbd className="px-1.5 py-0.5 font-mono text-[10px] bg-primary/20 text-primary rounded">g</kbd>
            <span className="text-muted-foreground">{navHint}</span>
          </div>
        </div>
      )}

      {/* [AA5] 피드백 플로팅 버튼 + 모달 */}
      <FeedbackWidget />

      {/* [X4] 모바일 하단 탭바 — 사이드바 열려있을 땐 숨김 (시각 간섭 방지) */}
      {!sidebarOpen && <MobileTabBar />}

      {/* [Z9] 첫 방문 온보딩 (localStorage 1회) */}
      <OnboardingTour />

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

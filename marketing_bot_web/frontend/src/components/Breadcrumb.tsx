import { Link, useLocation } from 'react-router-dom'
import { Home, ChevronRight } from 'lucide-react'

const ROUTE_LABELS: Record<string, string> = {
  '': '대시보드',
  pathfinder: 'Pathfinder',
  battle: 'Battle Intelligence',
  competitors: '경쟁사 분석',
  analytics: '마케팅 분석',
  viral: 'Viral Hunter',
  tiktok: 'TikTok',
  leads: 'Lead Manager',
  marketing: 'Marketing Hub',
  qa: 'Q&A Repository',
  agent: 'AI Agent',
  settings: '설정',
  notifications: '알림',
  'data-intelligence': 'Data Intelligence',
  ads: '광고 관리',
  aeo: 'AEO',
}

function labelFor(segment: string): string {
  return ROUTE_LABELS[segment] ?? decodeURIComponent(segment)
}

export default function Breadcrumb() {
  const location = useLocation()
  const segments = location.pathname.split('/').filter(Boolean)

  // 홈에서는 숨김
  if (segments.length === 0) return null

  const crumbs = segments.map((seg, idx) => ({
    label: labelFor(seg),
    href: '/' + segments.slice(0, idx + 1).join('/'),
    isLast: idx === segments.length - 1,
  }))

  return (
    <nav
      aria-label="페이지 경로"
      className="flex items-center gap-1.5 text-xs text-muted-foreground mb-6 flex-wrap"
    >
      <Link
        to="/"
        className="flex items-center gap-1 hover:text-foreground transition-colors"
        aria-label="대시보드로 이동"
      >
        <Home className="h-3.5 w-3.5" />
        <span className="caps">Home</span>
      </Link>
      {crumbs.map((crumb) => (
        <span key={crumb.href} className="flex items-center gap-1.5">
          <ChevronRight className="h-3 w-3 opacity-40" aria-hidden />
          {crumb.isLast ? (
            <span className="font-medium text-foreground" aria-current="page">
              {crumb.label}
            </span>
          ) : (
            <Link
              to={crumb.href}
              className="hover:text-foreground transition-colors"
            >
              {crumb.label}
            </Link>
          )}
        </span>
      ))}
    </nav>
  )
}

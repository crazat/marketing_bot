/**
 * Analytics 페이지 — 리다이렉트 셔임 (레거시 URL 호환)
 *
 * [A안] Marketing Hub로 기능 통합됨에 따라 Analytics 페이지는 폐지.
 * 기존 북마크 `/analytics?tab=xxx`는 자동으로 `/marketing?tab=xxx`로 리다이렉트.
 */

import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

// Analytics 구 탭 ID → Marketing Hub 탭 ID
const TAB_MIGRATION_MAP: Record<string, string> = {
  'overview': 'overview',
  'ai-insights': 'growth',       // AI 인사이트 → 성장 탭 내부 섹션
  'performance': 'performance',
  'attribution': 'attribution',
  'golden-time': 'performance',  // 응답 골든타임 → 성과 탭
  'competitor': 'monitoring',     // 경쟁사 동향 → 모니터링 탭
  'lifecycle': 'attribution',     // 키워드 라이프사이클 → 어트리뷰션 탭
  'roi': 'roi',
}

export default function Analytics() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  useEffect(() => {
    const oldTab = searchParams.get('tab')
    const newTab = oldTab ? TAB_MIGRATION_MAP[oldTab] ?? 'overview' : 'overview'
    navigate(`/marketing?tab=${newTab}`, { replace: true })
  }, [navigate, searchParams])

  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <div className="text-center">
        <p className="text-muted-foreground">Marketing Hub로 이동 중...</p>
      </div>
    </div>
  )
}

import { lazy, Suspense, ReactNode } from 'react'
import { Routes, Route, useNavigate } from 'react-router-dom'
import Layout from './components/Layout'
import WebSocketIndicator from './components/WebSocketIndicator'
import ErrorBoundary from './components/ui/ErrorBoundary'
import LoadingSpinner from './components/ui/LoadingSpinner'

// 페이지 Lazy Loading - 초기 번들 크기 감소
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Pathfinder = lazy(() => import('./pages/Pathfinder'))
const BattleIntelligence = lazy(() => import('./pages/BattleIntelligence'))
const LeadManager = lazy(() => import('./pages/LeadManager'))
const ViralHunter = lazy(() => import('./pages/ViralHunter'))
const CompetitorAnalysis = lazy(() => import('./pages/CompetitorAnalysis'))
const AIAgent = lazy(() => import('./pages/AIAgent'))
const QARepository = lazy(() => import('./pages/QARepository'))
const Analytics = lazy(() => import('./pages/Analytics'))
const MarketingHub = lazy(() => import('./pages/MarketingHub'))
const Settings = lazy(() => import('./pages/Settings'))
const TikTok = lazy(() => import('./pages/TikTok'))
const NotFound = lazy(() => import('./pages/NotFound'))

// 페이지 로딩 중 표시할 Fallback 컴포넌트
function PageLoadingFallback() {
  return (
    <div className="flex items-center justify-center min-h-[400px]">
      <LoadingSpinner size="lg" text="페이지 로딩 중..." />
    </div>
  )
}

// 페이지 레벨 에러 Fallback 컴포넌트
function PageErrorFallback({ pageName }: { pageName: string }) {
  const navigate = useNavigate()

  return (
    <div className="flex items-center justify-center min-h-[400px] p-4">
      <div className="max-w-md w-full bg-card rounded-lg border border-destructive/50 p-6 text-center">
        <div className="text-5xl mb-4">⚠️</div>
        <h2 className="text-xl font-bold mb-2">{pageName} 페이지 오류</h2>
        <p className="text-muted-foreground mb-4">
          이 페이지에서 오류가 발생했습니다. 다른 페이지는 정상적으로 이용 가능합니다.
        </p>
        <div className="flex gap-3 justify-center">
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
          >
            페이지 새로고침
          </button>
          <button
            onClick={() => navigate('/')}
            className="px-4 py-2 bg-card border border-border rounded-lg hover:bg-accent transition-colors"
          >
            대시보드로 이동
          </button>
        </div>
      </div>
    </div>
  )
}

// 페이지 래퍼 - ErrorBoundary + Suspense 조합
function PageWrapper({ children, pageName }: { children: ReactNode; pageName: string }) {
  return (
    <ErrorBoundary fallback={<PageErrorFallback pageName={pageName} />}>
      <Suspense fallback={<PageLoadingFallback />}>
        {children}
      </Suspense>
    </ErrorBoundary>
  )
}

function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route
            index
            element={
              <PageWrapper pageName="대시보드">
                <Dashboard />
              </PageWrapper>
            }
          />
          <Route
            path="pathfinder"
            element={
              <PageWrapper pageName="Pathfinder">
                <Pathfinder />
              </PageWrapper>
            }
          />
          <Route
            path="battle"
            element={
              <PageWrapper pageName="Battle Intelligence">
                <BattleIntelligence />
              </PageWrapper>
            }
          />
          <Route
            path="leads"
            element={
              <PageWrapper pageName="Lead Manager">
                <LeadManager />
              </PageWrapper>
            }
          />
          <Route
            path="viral"
            element={
              <PageWrapper pageName="Viral Hunter">
                <ViralHunter />
              </PageWrapper>
            }
          />
          <Route
            path="competitors"
            element={
              <PageWrapper pageName="Competitor Analysis">
                <CompetitorAnalysis />
              </PageWrapper>
            }
          />
          <Route
            path="agent"
            element={
              <PageWrapper pageName="AI Agent">
                <AIAgent />
              </PageWrapper>
            }
          />
          <Route
            path="qa"
            element={
              <PageWrapper pageName="Q&A Repository">
                <QARepository />
              </PageWrapper>
            }
          />
          <Route
            path="analytics"
            element={
              <PageWrapper pageName="Analytics">
                <Analytics />
              </PageWrapper>
            }
          />
          <Route
            path="marketing"
            element={
              <PageWrapper pageName="Marketing Hub">
                <MarketingHub />
              </PageWrapper>
            }
          />
          <Route
            path="settings"
            element={
              <PageWrapper pageName="Settings">
                <Settings />
              </PageWrapper>
            }
          />
          <Route
            path="tiktok"
            element={
              <PageWrapper pageName="TikTok">
                <TikTok />
              </PageWrapper>
            }
          />
          {/* [M6] 404 Not Found */}
          <Route
            path="*"
            element={
              <PageWrapper pageName="NotFound">
                <NotFound />
              </PageWrapper>
            }
          />
        </Route>
      </Routes>
      <WebSocketIndicator />
    </ErrorBoundary>
  )
}

export default App

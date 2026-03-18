/**
 * [Phase G-L] 마케팅 분석 통합 페이지
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart3,
  Link2,
  Clock,
  Eye,
  Calendar,
  RefreshCw,
  DollarSign,
  TrendingUp,
  Target,
  Users,
  Zap,
  Brain,
  LineChart,
} from 'lucide-react'
import {
  AttributionChain,
  ChannelROI,
  CompetitorMovements,
  KeywordLifecycle,
  ResponseGoldenTime,
  WeeklyBriefing,
} from '@/components/analytics'
import AIInsights from '@/components/analytics/AIInsights'
import PerformanceFeedback from '@/components/analytics/PerformanceFeedback'
import { hudApi } from '@/services/api'

type TabId = 'overview' | 'ai-insights' | 'performance' | 'attribution' | 'golden-time' | 'competitor' | 'lifecycle' | 'roi'

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: 'overview', label: '개요', icon: <Calendar className="w-4 h-4" /> },
  { id: 'ai-insights', label: 'AI 인사이트', icon: <Brain className="w-4 h-4" /> },
  { id: 'performance', label: '성과 분석', icon: <LineChart className="w-4 h-4" /> },
  { id: 'attribution', label: '전환 어트리뷰션', icon: <Link2 className="w-4 h-4" /> },
  { id: 'golden-time', label: '응답 골든타임', icon: <Clock className="w-4 h-4" /> },
  { id: 'competitor', label: '경쟁사 동향', icon: <Eye className="w-4 h-4" /> },
  { id: 'lifecycle', label: '키워드 라이프사이클', icon: <RefreshCw className="w-4 h-4" /> },
  { id: 'roi', label: '채널별 ROI', icon: <DollarSign className="w-4 h-4" /> },
]

export default function Analytics() {
  const [activeTab, setActiveTab] = useState<TabId>('overview')

  return (
    <div className="space-y-6">
      {/* 페이지 헤더 */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <BarChart3 className="w-6 h-6 text-primary" />
          마케팅 분석
        </h1>
        <p className="text-muted-foreground mt-1">
          마케팅 활동의 성과를 다각도로 분석합니다
        </p>
      </div>

      {/* 탭 네비게이션 */}
      <div className="flex flex-wrap gap-2 border-b border-border pb-2">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 rounded-lg text-sm flex items-center gap-2 transition-colors ${
              activeTab === tab.id
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted hover:bg-muted/70'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* 탭 콘텐츠 */}
      <div>
        {activeTab === 'overview' && <OverviewTab />}
        {activeTab === 'ai-insights' && <AIInsights />}
        {activeTab === 'performance' && <PerformanceFeedback />}
        {activeTab === 'attribution' && <AttributionChain />}
        {activeTab === 'golden-time' && <ResponseGoldenTime />}
        {activeTab === 'competitor' && <CompetitorMovements />}
        {activeTab === 'lifecycle' && <KeywordLifecycle />}
        {activeTab === 'roi' && <ChannelROI />}
      </div>
    </div>
  )
}

function OverviewTab() {
  // [Phase 4] HUD 메트릭 데이터 조회
  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ['hud-metrics'],
    queryFn: () => hudApi.getMetrics(),
    staleTime: 60000, // [Phase 7] 30초 → 60초
    refetchInterval: 60000, // [Phase 7] 30초 → 60초
    retry: 1,
  })

  return (
    <div className="space-y-6">
      {/* [Phase 4] 핵심 메트릭 카드 */}
      {!metricsLoading && metrics && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="flex items-center gap-2 text-muted-foreground text-sm mb-1">
              <Target className="w-4 h-4" />
              <span>전체 키워드</span>
            </div>
            <div className="text-2xl font-bold">{metrics.total_keywords || 0}</div>
          </div>

          <div className="bg-card border border-border rounded-lg p-4">
            <div className="flex items-center gap-2 text-muted-foreground text-sm mb-1">
              <TrendingUp className="w-4 h-4" />
              <span>순위 추적</span>
            </div>
            <div className="text-2xl font-bold">{metrics.ranking_keywords_count || 0}</div>
          </div>

          <div className="bg-card border border-border rounded-lg p-4">
            <div className="flex items-center gap-2 text-muted-foreground text-sm mb-1">
              <Users className="w-4 h-4" />
              <span>신규 리드</span>
            </div>
            <div className="text-2xl font-bold">{metrics.leads_new || 0}</div>
          </div>

          <div className="bg-card border border-border rounded-lg p-4">
            <div className="flex items-center gap-2 text-muted-foreground text-sm mb-1">
              <Zap className="w-4 h-4" />
              <span>바이럴 타겟</span>
            </div>
            <div className="text-2xl font-bold">{metrics.viral_total || 0}</div>
          </div>
        </div>
      )}

      {/* 주간 브리핑 */}
      <WeeklyBriefing />

      {/* 2열 그리드 */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* 전환 경로 요약 */}
        <AttributionChain compact />

        {/* 응답 골든타임 요약 */}
        <ResponseGoldenTime compact />
      </div>

      {/* 경쟁사 동향 요약 */}
      <CompetitorMovements compact />

      {/* ROI 요약 */}
      <ChannelROI defaultDays={7} />
    </div>
  )
}

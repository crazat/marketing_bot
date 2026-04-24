/**
 * Marketing Hub - 마케팅 강화 통합 페이지
 *
 * [A안 적용] Analytics 페이지 흡수 — 사이드바에서 별도 분리되어 있던 "마케팅 분석"과 통합.
 *
 * 탭 구조 (6개):
 *   - overview: 개요 (ROI·골든타임·알림 compact 3개)
 *   - roi: ROI (ROIDashboard + 채널별 ChannelROI)
 *   - performance: 성과 (골든타임 + 리드 품질 + 응답 골든타임 + 성과 피드백)
 *   - growth: 성장 (캠페인 + A/B 테스트 + AI 인사이트)
 *   - monitoring: 모니터링 (경쟁사 레이더 + 경쟁사 동향 + 스마트 알림)
 *   - attribution: 어트리뷰션 (전환 경로 + 키워드 라이프사이클 + 주간 브리핑)
 */

import { useState, useEffect } from 'react'
import { BarChart3 } from 'lucide-react'
import { useUrlState } from '@/hooks/useUrlState'
import TabNavigation from '@/components/ui/TabNavigation'

// 기존 Marketing Hub 컴포넌트
import { ROIDashboard } from '@/components/marketing/ROIDashboard'
import { GoldenTimeDashboard } from '@/components/marketing/GoldenTimeDashboard'
import { LeadQualityDashboard } from '@/components/marketing/LeadQualityDashboard'
import { CampaignManager } from '@/components/marketing/CampaignManager'
import { ABTestManager } from '@/components/marketing/ABTestManager'
import { CompetitorRadar } from '@/components/marketing/CompetitorRadar'
import { SmartAlerts } from '@/components/marketing/SmartAlerts'

// Analytics 페이지에서 흡수한 컴포넌트
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

// 레거시 탭 ID → 새 탭 ID (북마크 호환)
// Marketing Hub 자체의 구 ID + 흡수된 Analytics의 구 ID 모두 처리
const LEGACY_TAB_MAP: Record<string, string> = {
  // MarketingHub 구 ID (2차 라운드에서 통합된 것들)
  'golden-time': 'performance',
  'lead-quality': 'performance',
  'campaigns': 'growth',
  'ab-tests': 'growth',
  'competitor-radar': 'monitoring',
  'alerts': 'monitoring',
  // Analytics 흡수에 따른 매핑
  'ai-insights': 'growth',
  'competitor': 'monitoring',
  'lifecycle': 'attribution',
  // 'overview', 'roi', 'performance', 'attribution'은 변경 없음 (같은 ID 재사용)
}

export default function MarketingHub() {
  const [activeTab, setActiveTab] = useUrlState<string>('tab', { defaultValue: 'overview' })
  const [days, setDays] = useState(30)

  // 레거시 탭 ID 자동 리다이렉트 (?tab=golden-time → performance 등)
  useEffect(() => {
    const mapped = LEGACY_TAB_MAP[activeTab]
    if (mapped) setActiveTab(mapped)
  }, [activeTab, setActiveTab])

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* 헤더 */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <BarChart3 className="w-8 h-8 text-primary" />
            Marketing Hub
          </h1>
          <p className="text-muted-foreground mt-1">
            마케팅 성과 분석 및 최적화
          </p>
        </div>

        <select
          value={days}
          onChange={(e) => setDays(parseInt(e.target.value))}
          className="px-4 py-2 bg-muted border border-border rounded-lg"
          aria-label="분석 기간 선택"
        >
          <option value="7">최근 7일</option>
          <option value="14">최근 14일</option>
          <option value="30">최근 30일</option>
          <option value="60">최근 60일</option>
          <option value="90">최근 90일</option>
        </select>
      </div>

      {/* 탭 네비게이션 — 6개 (Analytics 흡수 후) */}
      <TabNavigation
        tabs={[
          { id: 'overview', label: '📊 개요' },
          { id: 'roi', label: '💰 ROI' },
          { id: 'performance', label: '⏰ 성과' },
          { id: 'growth', label: '🚀 성장' },
          { id: 'monitoring', label: '🎯 모니터링' },
          { id: 'attribution', label: '🔗 어트리뷰션' },
        ]}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        ariaLabel="Marketing Hub 탭"
      />

      {/* 탭 컨텐츠 */}
      <div className="mt-6">
        {activeTab === 'overview' && <OverviewTab days={days} />}
        {activeTab === 'roi' && <RoiTab days={days} />}
        {activeTab === 'performance' && <PerformanceTab days={days} />}
        {activeTab === 'growth' && <GrowthTab />}
        {activeTab === 'monitoring' && <MonitoringTab days={days} />}
        {activeTab === 'attribution' && <AttributionTab days={days} />}
      </div>
    </div>
  )
}

// 개요 탭 — compact 3개 (ROI · 골든타임 · 알림)
function OverviewTab({ days }: { days: number }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ROIDashboard days={days} compact />
        <GoldenTimeDashboard days={days} compact />
      </div>
      <SmartAlerts compact />
      <p className="text-xs text-muted-foreground text-center py-2">
        💡 자세한 분석은 상단 탭에서 확인하세요
      </p>
    </div>
  )
}

// ROI 탭 — 종합 ROI + 채널별 ROI
function RoiTab({ days }: { days: number }) {
  return (
    <div className="space-y-8">
      <ROIDashboard days={days} />
      <div className="border-t border-border pt-8">
        <h3 className="text-lg font-semibold mb-4">📊 채널별 ROI 분석</h3>
        <ChannelROI defaultDays={days} />
      </div>
    </div>
  )
}

// 성과 탭 — 골든타임 + 리드 품질 + 응답 골든타임 + 성과 피드백
function PerformanceTab({ days }: { days: number }) {
  return (
    <div className="space-y-8">
      <GoldenTimeDashboard days={days} />
      <div className="border-t border-border pt-8">
        <LeadQualityDashboard days={days} />
      </div>
      <div className="border-t border-border pt-8">
        <h3 className="text-lg font-semibold mb-4">⏱️ 응답 골든타임 (리드 전환율)</h3>
        <ResponseGoldenTime />
      </div>
      <div className="border-t border-border pt-8">
        <h3 className="text-lg font-semibold mb-4">📝 성과 피드백 리포트</h3>
        <PerformanceFeedback />
      </div>
    </div>
  )
}

// 성장 탭 — 캠페인 + A/B 테스트 + AI 인사이트
function GrowthTab() {
  return (
    <div className="space-y-8">
      <CampaignManager />
      <div className="border-t border-border pt-8">
        <ABTestManager />
      </div>
      <div className="border-t border-border pt-8">
        <h3 className="text-lg font-semibold mb-4">🧠 AI 인사이트 & 예측</h3>
        <AIInsights />
      </div>
    </div>
  )
}

// 모니터링 탭 — 경쟁사 레이더 + 경쟁사 동향 + 스마트 알림
function MonitoringTab({ days }: { days: number }) {
  return (
    <div className="space-y-8">
      <CompetitorRadar days={days} />
      <div className="border-t border-border pt-8">
        <h3 className="text-lg font-semibold mb-4">📈 경쟁사 동향 타임라인</h3>
        <CompetitorMovements days={days} />
      </div>
      <div className="border-t border-border pt-8">
        <SmartAlerts />
      </div>
    </div>
  )
}

// 어트리뷰션 탭 — 전환 경로 + 키워드 라이프사이클 + 주간 브리핑
function AttributionTab({ days }: { days: number }) {
  return (
    <div className="space-y-8">
      <AttributionChain days={days} />
      <div className="border-t border-border pt-8">
        <h3 className="text-lg font-semibold mb-4">🔄 키워드 라이프사이클</h3>
        <KeywordLifecycle />
      </div>
      <div className="border-t border-border pt-8">
        <h3 className="text-lg font-semibold mb-4">📅 주간 브리핑</h3>
        <WeeklyBriefing />
      </div>
    </div>
  )
}

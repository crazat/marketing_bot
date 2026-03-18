/**
 * Marketing Hub - 마케팅 강화 통합 페이지
 */

import { useState } from 'react'
import {
  LayoutDashboard, Clock, Award, Megaphone, FlaskConical,
  Radar, Bell, DollarSign, BarChart3
} from 'lucide-react'
import { ROIDashboard } from '@/components/marketing/ROIDashboard'
import { GoldenTimeDashboard } from '@/components/marketing/GoldenTimeDashboard'
import { LeadQualityDashboard } from '@/components/marketing/LeadQualityDashboard'
import { CampaignManager } from '@/components/marketing/CampaignManager'
import { ABTestManager } from '@/components/marketing/ABTestManager'
import { CompetitorRadar } from '@/components/marketing/CompetitorRadar'
import { SmartAlerts } from '@/components/marketing/SmartAlerts'

type TabType = 'overview' | 'roi' | 'golden-time' | 'lead-quality' | 'campaigns' | 'ab-tests' | 'competitor-radar' | 'alerts'

const TABS = [
  { id: 'overview' as const, label: '개요', icon: LayoutDashboard },
  { id: 'roi' as const, label: 'ROI 대시보드', icon: DollarSign },
  { id: 'golden-time' as const, label: '골든타임', icon: Clock },
  { id: 'lead-quality' as const, label: '리드 품질', icon: Award },
  { id: 'campaigns' as const, label: '캠페인', icon: Megaphone },
  { id: 'ab-tests' as const, label: 'A/B 테스트', icon: FlaskConical },
  { id: 'competitor-radar' as const, label: '경쟁사 레이더', icon: Radar },
  { id: 'alerts' as const, label: '스마트 알림', icon: Bell },
]

export default function MarketingHub() {
  const [activeTab, setActiveTab] = useState<TabType>('overview')
  const [days, setDays] = useState(30)

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-6">
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
        >
          <option value="7">최근 7일</option>
          <option value="14">최근 14일</option>
          <option value="30">최근 30일</option>
          <option value="60">최근 60일</option>
          <option value="90">최근 90일</option>
        </select>
      </div>

      {/* 탭 네비게이션 */}
      <div className="flex gap-1 mb-6 overflow-x-auto pb-2">
        {TABS.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg whitespace-nowrap transition-colors ${
                activeTab === tab.id
                  ? 'bg-primary text-primary-foreground'
                  : 'hover:bg-muted text-muted-foreground'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* 탭 컨텐츠 */}
      <div>
        {activeTab === 'overview' && <OverviewTab days={days} />}
        {activeTab === 'roi' && <ROIDashboard days={days} />}
        {activeTab === 'golden-time' && <GoldenTimeDashboard days={days} />}
        {activeTab === 'lead-quality' && <LeadQualityDashboard days={days} />}
        {activeTab === 'campaigns' && <CampaignManager />}
        {activeTab === 'ab-tests' && <ABTestManager />}
        {activeTab === 'competitor-radar' && <CompetitorRadar days={days} />}
        {activeTab === 'alerts' && <SmartAlerts />}
      </div>
    </div>
  )
}

// 개요 탭 - 핵심 지표 요약
function OverviewTab({ days }: { days: number }) {
  return (
    <div className="space-y-6">
      {/* 상단 핵심 대시보드 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ROIDashboard days={days} compact />
        <GoldenTimeDashboard days={days} compact />
      </div>

      {/* 중간 대시보드 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <LeadQualityDashboard days={days} compact />
        <CompetitorRadar days={days} compact />
      </div>

      {/* 하단 대시보드 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SmartAlerts compact />
        <RecentActivityCard />
      </div>
    </div>
  )
}

// 최근 활동 카드
function RecentActivityCard() {
  return (
    <div className="bg-card border border-border rounded-lg p-6">
      <h3 className="text-lg font-semibold mb-4">최근 마케팅 활동</h3>

      <div className="text-center py-8 text-muted-foreground">
        <BarChart3 className="w-12 h-12 mx-auto mb-4 opacity-50" />
        <p>아직 기록된 활동이 없습니다.</p>
        <p className="text-sm mt-1">캠페인을 시작하거나 타겟을 처리해보세요.</p>
      </div>
    </div>
  )
}


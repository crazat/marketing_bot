/**
 * Settings 페이지
 * 시스템 상태, 백업 및 설정 관리
 */

import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { configApi } from '@/services/api'
import PageTransition from '@/components/PageTransition'
import { useUrlState } from '@/hooks/useUrlState'
import TabNavigation from '@/components/ui/TabNavigation'
import GoalManager from '@/components/ui/GoalManager'
import ConfigFileViewer from '@/components/settings/ConfigFileViewer'

// 분리된 탭 컴포넌트들
import BackupTab from '@/components/settings/BackupTab'
import SystemTab from '@/components/settings/SystemTab'
import AutomationTab from '@/components/settings/AutomationTab'
import KeywordsTab from '@/components/settings/KeywordsTab'
import QATab from '@/components/settings/QATab'
import NotificationsTab from '@/components/settings/NotificationsTab'
import ExternalNotificationsTab from '@/components/settings/ExternalNotificationsTab'
import IntegrationsTab from '@/components/settings/IntegrationsTab'

export default function Settings() {
  const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // URL 상태 관리
  const [activeTab, setActiveTab] = useUrlState<string>('tab', { defaultValue: 'backup' })

  // 키워드 카운트 조회 (탭 레이블용)
  const { data: keywordsData } = useQuery({
    queryKey: ['keywords-config'],
    queryFn: () => configApi.getKeywords().catch(() => ({ naver_place: [], blog_seo: [], total_count: 0 })),
    staleTime: 60000, // 1분간 캐시
    enabled: true,
    retry: 1,
  })

  // 메시지 핸들러
  const handleMessage = useCallback((message: { type: 'success' | 'error'; text: string }) => {
    setActionMessage(message)
    setTimeout(() => setActionMessage(null), message.type === 'success' ? 3000 : 5000)
  }, [])

  return (
    <PageTransition>
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold mb-2">⚙️ 시스템 설정</h1>
          <p className="text-muted-foreground">
            시스템 상태, 백업 및 설정 관리
          </p>
        </div>

        {/* 알림 메시지 */}
        {actionMessage && (
          <div className={`p-4 rounded-lg border ${
            actionMessage.type === 'success'
              ? 'bg-green-500/10 border-green-500/30 text-green-500'
              : 'bg-red-500/10 border-red-500/30 text-red-500'
          }`}>
            {actionMessage.text}
          </div>
        )}

        {/* 탭 네비게이션 */}
        <TabNavigation
          tabs={[
            { id: 'backup', label: '💾 백업' },
            { id: 'system', label: '📊 시스템' },
            { id: 'automation', label: '🤖 자동화' },
            { id: 'goals', label: '🎯 목표' },
            { id: 'keywords', label: `🔑 키워드 (${keywordsData?.total_count || 0})` },
            { id: 'qa', label: '💬 Q&A' },
            { id: 'notifications', label: '🔔 알림' },
            { id: 'external-notifications', label: '📲 외부 알림' },
            { id: 'integrations', label: '🔗 연동 상태' },
            { id: 'config', label: '⚙️ 설정' },
          ]}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          ariaLabel="설정 탭"
        />

        {/* 백업 탭 */}
        {activeTab === 'backup' && (
          <BackupTab onMessage={handleMessage} />
        )}

        {/* 시스템 탭 */}
        {activeTab === 'system' && (
          <SystemTab />
        )}

        {/* 자동화 탭 */}
        {activeTab === 'automation' && (
          <AutomationTab />
        )}

        {/* 목표 탭 */}
        {activeTab === 'goals' && (
          <GoalManager />
        )}

        {/* 키워드 탭 */}
        {activeTab === 'keywords' && (
          <KeywordsTab />
        )}

        {/* Q&A 탭 */}
        {activeTab === 'qa' && (
          <QATab onMessage={handleMessage} />
        )}

        {/* 알림 탭 */}
        {activeTab === 'notifications' && (
          <NotificationsTab />
        )}

        {/* 외부 알림 탭 */}
        {activeTab === 'external-notifications' && (
          <ExternalNotificationsTab />
        )}

        {/* 연동 상태 탭 */}
        {activeTab === 'integrations' && (
          <IntegrationsTab />
        )}

        {/* 설정 탭 */}
        {activeTab === 'config' && (
          <>
            {/* 설정 파일 경로 안내 */}
            <div className="bg-card rounded-lg border border-border p-6">
              <h3 className="text-lg font-semibold mb-4">📁 설정 파일 경로</h3>
              <div className="space-y-4">
                <div className="p-4 bg-muted/50 rounded-lg">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-lg">🔑</span>
                    <span className="font-medium">API 키 설정</span>
                  </div>
                  <code className="text-sm text-muted-foreground block bg-background p-2 rounded">
                    config/config.json
                  </code>
                  <p className="text-xs text-muted-foreground mt-2">
                    Gemini API 키, Naver API 키 등을 설정합니다.
                  </p>
                </div>

                <div className="p-4 bg-muted/50 rounded-lg">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-lg">🎯</span>
                    <span className="font-medium">키워드 설정</span>
                  </div>
                  <code className="text-sm text-muted-foreground block bg-background p-2 rounded">
                    config/keywords.json
                  </code>
                  <p className="text-xs text-muted-foreground mt-2">
                    Pathfinder 시드 키워드, 순위 추적 키워드를 설정합니다.
                  </p>
                </div>

                <div className="p-4 bg-muted/50 rounded-lg">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-lg">🏢</span>
                    <span className="font-medium">업체 정보</span>
                  </div>
                  <code className="text-sm text-muted-foreground block bg-background p-2 rounded">
                    config/business_profile.json
                  </code>
                  <p className="text-xs text-muted-foreground mt-2">
                    업체명, 네이버 플레이스 ID 등을 설정합니다.
                  </p>
                </div>

                <div className="p-4 bg-muted/50 rounded-lg">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-lg">📅</span>
                    <span className="font-medium">스케줄 설정</span>
                  </div>
                  <code className="text-sm text-muted-foreground block bg-background p-2 rounded">
                    config/schedule.json
                  </code>
                  <p className="text-xs text-muted-foreground mt-2">
                    Chronos Timeline 스케줄 및 자동 실행 설정을 관리합니다.
                  </p>
                </div>
              </div>
            </div>

            {/* 설정 파일 뷰어 */}
            <ConfigFileViewer />

            {/* 도움말 */}
            <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4">
              <p className="text-sm text-yellow-600 dark:text-yellow-400">
                <span className="font-medium">💡 팁:</span> 설정 파일을 수정한 후에는 웹 서버를 재시작해야 변경사항이 적용됩니다.
              </p>
            </div>
          </>
        )}
      </div>
    </PageTransition>
  )
}

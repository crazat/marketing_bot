import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { preferencesApi, DashboardWidgets } from '@/services/api'
import Button, { IconButton } from '@/components/ui/Button'
import { X, Settings } from 'lucide-react'

interface DashboardSettingsProps {
  isOpen: boolean
  onClose: () => void
}

const widgetIcons: Record<string, string> = {
  metrics_overview: '📊',
  daily_briefing: '📋',
  sentinel_alerts: '🛡️',
  chronos_timeline: '⏰',
  rank_alerts: '📈',
  pending_actions: '⏳',
  recent_activities: '📝',
  suggested_actions: '💡',
}

export default function DashboardSettings({ isOpen, onClose }: DashboardSettingsProps) {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-preferences'],
    queryFn: preferencesApi.getDashboard,
    enabled: isOpen,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ widgetId, enabled }: { widgetId: string; enabled: boolean }) =>
      preferencesApi.toggleWidget(widgetId, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard-preferences'] })
    },
  })

  const resetMutation = useMutation({
    mutationFn: preferencesApi.resetDashboard,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard-preferences'] })
    },
  })

  if (!isOpen) return null

  const widgets: DashboardWidgets = data?.widgets || {}

  // 순서대로 정렬
  const sortedWidgets = Object.entries(widgets)
    .sort(([, a], [, b]) => (a.order || 0) - (b.order || 0))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />
      <div
        className="relative bg-card border border-border rounded-lg shadow-xl w-full max-w-lg mx-4 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <span>⚙️</span>
            대시보드 설정
          </h2>
          <IconButton
            icon={<X className="w-5 h-5" />}
            onClick={onClose}
            size="sm"
            title="닫기"
          />
        </div>

        {/* Content */}
        <div className="p-4 max-h-[60vh] overflow-y-auto">
          <p className="text-sm text-muted-foreground mb-4">
            대시보드에 표시할 위젯을 선택하세요.
          </p>

          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full" />
            </div>
          ) : (
            <div className="space-y-2">
              {sortedWidgets.map(([widgetId, config]) => (
                <label
                  key={widgetId}
                  className={`flex items-center gap-3 p-3 rounded-lg border transition-colors cursor-pointer ${
                    config.enabled
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-muted-foreground/30'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={config.enabled}
                    onChange={(e) => {
                      toggleMutation.mutate({
                        widgetId,
                        enabled: e.target.checked,
                      })
                    }}
                    className="w-4 h-4 rounded border-border text-primary focus:ring-primary"
                  />
                  <span className="text-xl">{widgetIcons[widgetId] || '📌'}</span>
                  <span className="flex-1 font-medium">{config.title}</span>
                  {toggleMutation.isPending && toggleMutation.variables?.widgetId === widgetId && (
                    <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                  )}
                </label>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-border bg-muted/30">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => resetMutation.mutate()}
            loading={resetMutation.isPending}
          >
            기본값으로 초기화
          </Button>
          <Button
            variant="primary"
            onClick={onClose}
          >
            완료
          </Button>
        </div>
      </div>
    </div>
  )
}

// 설정 버튼 컴포넌트
export function DashboardSettingsButton() {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <>
      <IconButton
        icon={<Settings className="w-5 h-5" />}
        onClick={() => setIsOpen(true)}
        size="sm"
        title="대시보드 설정"
      />
      <DashboardSettings isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </>
  )
}

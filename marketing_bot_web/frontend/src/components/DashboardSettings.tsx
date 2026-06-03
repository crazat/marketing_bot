import { useState, type ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { preferencesApi, DashboardWidgets } from '@/services/api'
import Button, { IconButton } from '@/components/ui/Button'
import Modal from '@/components/ui/Modal'
import { Settings, BarChart3, ClipboardList, Shield, Clock, TrendingUp, Hourglass, FileText, Lightbulb } from 'lucide-react'

interface DashboardSettingsProps {
  isOpen: boolean
  onClose: () => void
}

const DW_I = 'w-[18px] h-[18px]'
const widgetIcons: Record<string, ReactNode> = {
  metrics_overview: <BarChart3 className={DW_I} strokeWidth={1.7} />,
  daily_briefing: <ClipboardList className={DW_I} strokeWidth={1.7} />,
  sentinel_alerts: <Shield className={DW_I} strokeWidth={1.7} />,
  chronos_timeline: <Clock className={DW_I} strokeWidth={1.7} />,
  rank_alerts: <TrendingUp className={DW_I} strokeWidth={1.7} />,
  pending_actions: <Hourglass className={DW_I} strokeWidth={1.7} />,
  recent_activities: <FileText className={DW_I} strokeWidth={1.7} />,
  suggested_actions: <Lightbulb className={DW_I} strokeWidth={1.7} />,
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

  const widgets: DashboardWidgets = data?.widgets || {}

  // 순서대로 정렬
  const sortedWidgets = Object.entries(widgets)
    .sort(([, a], [, b]) => (a.order || 0) - (b.order || 0))

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="대시보드 설정"
      size="lg"
      footer={
        <div className="flex w-full items-center justify-between gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => resetMutation.mutate()}
            loading={resetMutation.isPending}
          >
            기본값으로 초기화
          </Button>
          <Button variant="primary" onClick={onClose}>
            완료
          </Button>
        </div>
      }
    >
      <div className="max-h-[60vh] overflow-y-auto">
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
                <span className="text-sage">{widgetIcons[widgetId] || <Settings className={DW_I} strokeWidth={1.7} />}</span>
                <span className="flex-1 font-medium">{config.title}</span>
                {toggleMutation.isPending && toggleMutation.variables?.widgetId === widgetId && (
                  <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                )}
              </label>
            ))}
          </div>
        )}
      </div>
    </Modal>
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

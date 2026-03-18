/**
 * 외부 알림 설정 탭 컴포넌트
 * 텔레그램/카카오톡 알림 설정 및 발송 이력 관리
 */

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notificationsApi } from '@/services/api'
import type { NotificationSettingsUpdate, NotificationHistory } from '@/services/api/settings'
import Button, { IconButton } from '@/components/ui/Button'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/utils/errorMessages'
import {
  Send,
  RefreshCw,
  AlertTriangle,
  Clock,
  Bell,
  CheckCircle,
  XCircle,
} from 'lucide-react'

interface NotificationSettings {
  telegram_enabled?: boolean
  telegram_bot_token_masked?: string
  telegram_chat_id?: string
  kakao_enabled?: boolean
  kakao_access_token_masked?: string
  rank_drop_threshold?: number
  new_lead_min_score?: number
  competitor_activity_alert?: boolean
  system_error_alert?: boolean
  alert_quiet_start?: string
  alert_quiet_end?: string
}

export default function ExternalNotificationsTab() {
  const queryClient = useQueryClient()
  const toast = useToast()

  // 외부 알림 설정 조회
  const { data: externalNotifSettings, isLoading: externalNotifLoading, refetch: refetchExternalNotif } = useQuery<NotificationSettings | null>({
    queryKey: ['external-notification-settings'],
    queryFn: () => notificationsApi.getSettings().catch(() => null),
    retry: 1,
  })

  // 알림 발송 이력 조회
  const { data: notifHistory, isLoading: notifHistoryLoading } = useQuery({
    queryKey: ['notification-history'],
    queryFn: () => notificationsApi.getHistory({ limit: 20 }).catch(() => ({ history: [] as NotificationHistory[], total: 0, stats: { sent: 0, failed: 0 } })),
    retry: 1,
  })

  // 폼 상태
  const [extNotifForm, setExtNotifForm] = useState({
    telegram_enabled: false,
    telegram_bot_token: '',
    telegram_chat_id: '',
    kakao_enabled: false,
    kakao_access_token: '',
    rank_drop_threshold: 5,
    new_lead_min_score: 70,
    competitor_activity_alert: true,
    system_error_alert: true,
    alert_quiet_start: '22:00',
    alert_quiet_end: '08:00',
  })
  const [extNotifFormDirty, setExtNotifFormDirty] = useState(false)

  // 설정 로드 시 폼 초기화
  useEffect(() => {
    if (externalNotifSettings && !extNotifFormDirty) {
      setExtNotifForm({
        telegram_enabled: externalNotifSettings.telegram_enabled || false,
        telegram_bot_token: '',
        telegram_chat_id: externalNotifSettings.telegram_chat_id || '',
        kakao_enabled: externalNotifSettings.kakao_enabled || false,
        kakao_access_token: '',
        rank_drop_threshold: externalNotifSettings.rank_drop_threshold || 5,
        new_lead_min_score: externalNotifSettings.new_lead_min_score || 70,
        competitor_activity_alert: externalNotifSettings.competitor_activity_alert ?? true,
        system_error_alert: externalNotifSettings.system_error_alert ?? true,
        alert_quiet_start: externalNotifSettings.alert_quiet_start || '22:00',
        alert_quiet_end: externalNotifSettings.alert_quiet_end || '08:00',
      })
    }
  }, [externalNotifSettings, extNotifFormDirty])

  // 설정 업데이트 mutation
  const updateExtNotifMutation = useMutation({
    mutationFn: (settings: NotificationSettingsUpdate) => notificationsApi.updateSettings(settings),
    onSuccess: (data) => {
      toast.success(data.message || '알림 설정이 업데이트되었습니다.')
      setExtNotifFormDirty(false)
      queryClient.invalidateQueries({ queryKey: ['external-notification-settings'] })
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })

  // 텔레그램 테스트 mutation
  const testTelegramMutation = useMutation({
    mutationFn: () => notificationsApi.testTelegram(),
    onSuccess: (data) => {
      toast.success(data.message)
      queryClient.invalidateQueries({ queryKey: ['notification-history'] })
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })

  // 카카오톡 테스트 mutation
  const testKakaoMutation = useMutation({
    mutationFn: () => notificationsApi.testKakao(),
    onSuccess: (data) => {
      toast.success(data.message)
      queryClient.invalidateQueries({ queryKey: ['notification-history'] })
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })

  // 알림 트리거 체크 mutation
  const triggerCheckMutation = useMutation({
    mutationFn: () => notificationsApi.triggerCheck(),
    onSuccess: (data) => {
      const { results } = data
      const total = results.rank_drops + results.new_leads + results.competitor_activity
      toast.success(total > 0 ? `${total}개 알림이 발송되었습니다.` : '발송할 알림이 없습니다.')
      queryClient.invalidateQueries({ queryKey: ['notification-history'] })
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error))
    },
  })

  // 폼 취소
  const handleCancel = () => {
    setExtNotifFormDirty(false)
    setExtNotifForm({
      telegram_enabled: externalNotifSettings?.telegram_enabled || false,
      telegram_bot_token: '',
      telegram_chat_id: externalNotifSettings?.telegram_chat_id || '',
      kakao_enabled: externalNotifSettings?.kakao_enabled || false,
      kakao_access_token: '',
      rank_drop_threshold: externalNotifSettings?.rank_drop_threshold || 5,
      new_lead_min_score: externalNotifSettings?.new_lead_min_score || 70,
      competitor_activity_alert: externalNotifSettings?.competitor_activity_alert ?? true,
      system_error_alert: externalNotifSettings?.system_error_alert ?? true,
      alert_quiet_start: externalNotifSettings?.alert_quiet_start || '22:00',
      alert_quiet_end: externalNotifSettings?.alert_quiet_end || '08:00',
    })
  }

  // 폼 저장
  const handleSave = () => {
    const updates: NotificationSettingsUpdate = {}
    if (extNotifForm.telegram_enabled !== externalNotifSettings?.telegram_enabled) {
      updates.telegram_enabled = extNotifForm.telegram_enabled
    }
    if (extNotifForm.telegram_bot_token) {
      updates.telegram_bot_token = extNotifForm.telegram_bot_token
    }
    if (extNotifForm.telegram_chat_id !== externalNotifSettings?.telegram_chat_id) {
      updates.telegram_chat_id = extNotifForm.telegram_chat_id
    }
    if (extNotifForm.kakao_enabled !== externalNotifSettings?.kakao_enabled) {
      updates.kakao_enabled = extNotifForm.kakao_enabled
    }
    if (extNotifForm.kakao_access_token) {
      updates.kakao_access_token = extNotifForm.kakao_access_token
    }
    if (extNotifForm.rank_drop_threshold !== externalNotifSettings?.rank_drop_threshold) {
      updates.rank_drop_threshold = extNotifForm.rank_drop_threshold
    }
    if (extNotifForm.new_lead_min_score !== externalNotifSettings?.new_lead_min_score) {
      updates.new_lead_min_score = extNotifForm.new_lead_min_score
    }
    if (extNotifForm.competitor_activity_alert !== externalNotifSettings?.competitor_activity_alert) {
      updates.competitor_activity_alert = extNotifForm.competitor_activity_alert
    }
    if (extNotifForm.system_error_alert !== externalNotifSettings?.system_error_alert) {
      updates.system_error_alert = extNotifForm.system_error_alert
    }
    if (extNotifForm.alert_quiet_start !== externalNotifSettings?.alert_quiet_start) {
      updates.alert_quiet_start = extNotifForm.alert_quiet_start
    }
    if (extNotifForm.alert_quiet_end !== externalNotifSettings?.alert_quiet_end) {
      updates.alert_quiet_end = extNotifForm.alert_quiet_end
    }

    if (Object.keys(updates).length > 0) {
      updateExtNotifMutation.mutate(updates)
    } else {
      setExtNotifFormDirty(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* 텔레그램/카카오톡 설정 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Send className="w-5 h-5 text-primary" />
            외부 알림 설정
          </h3>
          <IconButton
            icon={<RefreshCw className="w-4 h-4" />}
            onClick={() => refetchExternalNotif()}
            size="sm"
            title="새로고침"
          />
        </div>

        {externalNotifLoading ? (
          <div className="space-y-4 animate-pulse">
            <div className="h-32 bg-muted rounded-lg" />
            <div className="h-32 bg-muted rounded-lg" />
          </div>
        ) : (
          <div className="space-y-6">
            {/* 텔레그램 설정 */}
            <div className="p-4 bg-blue-500/5 border border-blue-500/20 rounded-lg">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">📬</span>
                  <div>
                    <h4 className="font-medium">텔레그램 알림</h4>
                    <p className="text-xs text-muted-foreground">
                      {externalNotifSettings?.telegram_bot_token_masked
                        ? `토큰: ${externalNotifSettings.telegram_bot_token_masked}`
                        : '토큰 미설정'}
                    </p>
                  </div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={extNotifFormDirty ? extNotifForm.telegram_enabled : (externalNotifSettings?.telegram_enabled || false)}
                    onChange={(e) => {
                      setExtNotifForm(prev => ({ ...prev, telegram_enabled: e.target.checked }))
                      setExtNotifFormDirty(true)
                    }}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-muted rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-500"></div>
                </label>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Bot Token</label>
                  <input
                    type="password"
                    value={extNotifForm.telegram_bot_token}
                    onChange={(e) => {
                      setExtNotifForm(prev => ({ ...prev, telegram_bot_token: e.target.value }))
                      setExtNotifFormDirty(true)
                    }}
                    placeholder="새 토큰 입력 (변경 시에만)"
                    className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Chat ID</label>
                  <input
                    type="text"
                    value={extNotifFormDirty ? extNotifForm.telegram_chat_id : (externalNotifSettings?.telegram_chat_id || '')}
                    onChange={(e) => {
                      setExtNotifForm(prev => ({ ...prev, telegram_chat_id: e.target.value }))
                      setExtNotifFormDirty(true)
                    }}
                    placeholder="예: 123456789"
                    className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
              </div>

              <Button
                variant="primary"
                onClick={() => testTelegramMutation.mutate()}
                disabled={!externalNotifSettings?.telegram_enabled}
                loading={testTelegramMutation.isPending}
                icon={<Send className="w-4 h-4" />}
              >
                테스트 발송
              </Button>
            </div>

            {/* 카카오톡 설정 */}
            <div className="p-4 bg-yellow-500/5 border border-yellow-500/20 rounded-lg">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">💬</span>
                  <div>
                    <h4 className="font-medium">카카오톡 알림</h4>
                    <p className="text-xs text-muted-foreground">
                      {externalNotifSettings?.kakao_access_token_masked
                        ? `토큰: ${externalNotifSettings.kakao_access_token_masked}`
                        : '토큰 미설정'}
                    </p>
                  </div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={extNotifFormDirty ? extNotifForm.kakao_enabled : (externalNotifSettings?.kakao_enabled || false)}
                    onChange={(e) => {
                      setExtNotifForm(prev => ({ ...prev, kakao_enabled: e.target.checked }))
                      setExtNotifFormDirty(true)
                    }}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-muted rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-yellow-500"></div>
                </label>
              </div>

              <div className="mb-4">
                <label className="block text-sm font-medium mb-1">Access Token</label>
                <input
                  type="password"
                  value={extNotifForm.kakao_access_token}
                  onChange={(e) => {
                    setExtNotifForm(prev => ({ ...prev, kakao_access_token: e.target.value }))
                    setExtNotifFormDirty(true)
                  }}
                  placeholder="새 토큰 입력 (변경 시에만)"
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              <Button
                variant="primary"
                onClick={() => testKakaoMutation.mutate()}
                disabled={!externalNotifSettings?.kakao_enabled}
                loading={testKakaoMutation.isPending}
                icon={<Send className="w-4 h-4" />}
                className="bg-yellow-500 hover:bg-yellow-600"
              >
                테스트 발송
              </Button>
            </div>

            {/* 알림 임계값 설정 */}
            <div className="p-4 bg-muted/30 border border-border rounded-lg">
              <h4 className="font-medium mb-4 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-orange-500" />
                알림 조건 설정
              </h4>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">
                    순위 급락 알림 임계값
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min={1}
                      max={50}
                      value={extNotifFormDirty ? extNotifForm.rank_drop_threshold : (externalNotifSettings?.rank_drop_threshold || 5)}
                      onChange={(e) => {
                        setExtNotifForm(prev => ({ ...prev, rank_drop_threshold: parseInt(e.target.value) || 5 }))
                        setExtNotifFormDirty(true)
                      }}
                      className="w-20 px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    />
                    <span className="text-sm text-muted-foreground">위 이상 하락 시 알림</span>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1">
                    신규 Hot Lead 최소 점수
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={extNotifFormDirty ? extNotifForm.new_lead_min_score : (externalNotifSettings?.new_lead_min_score || 70)}
                      onChange={(e) => {
                        setExtNotifForm(prev => ({ ...prev, new_lead_min_score: parseInt(e.target.value) || 70 }))
                        setExtNotifFormDirty(true)
                      }}
                      className="w-20 px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    />
                    <span className="text-sm text-muted-foreground">점 이상 리드 발견 시 알림</span>
                  </div>
                </div>

                <div className="flex items-center justify-between p-3 bg-background rounded-lg">
                  <span className="text-sm">경쟁사 활동 감지 알림</span>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={extNotifFormDirty ? extNotifForm.competitor_activity_alert : (externalNotifSettings?.competitor_activity_alert ?? true)}
                      onChange={(e) => {
                        setExtNotifForm(prev => ({ ...prev, competitor_activity_alert: e.target.checked }))
                        setExtNotifFormDirty(true)
                      }}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-muted rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary"></div>
                  </label>
                </div>

                <div className="flex items-center justify-between p-3 bg-background rounded-lg">
                  <span className="text-sm">시스템 오류 알림</span>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={extNotifFormDirty ? extNotifForm.system_error_alert : (externalNotifSettings?.system_error_alert ?? true)}
                      onChange={(e) => {
                        setExtNotifForm(prev => ({ ...prev, system_error_alert: e.target.checked }))
                        setExtNotifFormDirty(true)
                      }}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-muted rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary"></div>
                  </label>
                </div>
              </div>
            </div>

            {/* 방해 금지 시간 */}
            <div className="p-4 bg-muted/30 border border-border rounded-lg">
              <h4 className="font-medium mb-4 flex items-center gap-2">
                <Clock className="w-4 h-4 text-purple-500" />
                방해 금지 시간
              </h4>
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <input
                    type="time"
                    value={extNotifFormDirty ? extNotifForm.alert_quiet_start : (externalNotifSettings?.alert_quiet_start || '22:00')}
                    onChange={(e) => {
                      setExtNotifForm(prev => ({ ...prev, alert_quiet_start: e.target.value }))
                      setExtNotifFormDirty(true)
                    }}
                    className="px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                  <span className="text-muted-foreground">~</span>
                  <input
                    type="time"
                    value={extNotifFormDirty ? extNotifForm.alert_quiet_end : (externalNotifSettings?.alert_quiet_end || '08:00')}
                    onChange={(e) => {
                      setExtNotifForm(prev => ({ ...prev, alert_quiet_end: e.target.value }))
                      setExtNotifFormDirty(true)
                    }}
                    className="px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
                <span className="text-sm text-muted-foreground">이 시간에는 알림이 발송되지 않습니다</span>
              </div>
            </div>

            {/* 저장 버튼 */}
            {extNotifFormDirty && (
              <div className="flex justify-end gap-3">
                <Button variant="secondary" onClick={handleCancel}>
                  취소
                </Button>
                <Button
                  variant="primary"
                  onClick={handleSave}
                  loading={updateExtNotifMutation.isPending}
                >
                  설정 저장
                </Button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 수동 알림 트리거 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold">수동 알림 체크</h3>
            <p className="text-sm text-muted-foreground">
              순위 급락, 신규 Hot Lead, 경쟁사 활동을 확인하고 알림을 발송합니다
            </p>
          </div>
          <Button
            variant="success"
            onClick={() => triggerCheckMutation.mutate()}
            loading={triggerCheckMutation.isPending}
            icon={<Bell className="w-4 h-4" />}
          >
            지금 확인
          </Button>
        </div>
      </div>

      {/* 알림 발송 이력 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">알림 발송 이력</h3>
          {notifHistory?.stats && (
            <div className="flex items-center gap-4 text-sm">
              <span className="flex items-center gap-1 text-green-500">
                <CheckCircle className="w-4 h-4" />
                성공 {notifHistory.stats.sent}
              </span>
              <span className="flex items-center gap-1 text-red-500">
                <XCircle className="w-4 h-4" />
                실패 {notifHistory.stats.failed}
              </span>
            </div>
          )}
        </div>

        {notifHistoryLoading ? (
          <div className="space-y-2 animate-pulse">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 bg-muted rounded-lg" />
            ))}
          </div>
        ) : !notifHistory?.history || notifHistory.history.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Bell className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>발송된 알림이 없습니다</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {notifHistory.history.map((item) => (
              <div
                key={item.id}
                className={`flex items-center justify-between p-3 rounded-lg border ${
                  item.status === 'sent'
                    ? 'bg-green-500/5 border-green-500/20'
                    : 'bg-red-500/5 border-red-500/20'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className="text-lg">
                    {item.channel === 'telegram' ? '📬' : '💬'}
                  </span>
                  <div>
                    <div className="font-medium text-sm">{item.title}</div>
                    <div className="text-xs text-muted-foreground line-clamp-1">
                      {item.message}
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <div className={`text-xs font-medium ${
                    item.status === 'sent' ? 'text-green-500' : 'text-red-500'
                  }`}>
                    {item.status === 'sent' ? '발송 완료' : '실패'}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {new Date(item.sent_at).toLocaleString('ko-KR', {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 설정 안내 */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
        <h4 className="font-medium text-blue-500 mb-2">설정 안내</h4>
        <div className="text-sm text-muted-foreground space-y-2">
          <p>
            <span className="font-medium">텔레그램:</span> @BotFather에서 봇을 생성하고 토큰을 받으세요.
            Chat ID는 @userinfobot에 메시지를 보내면 확인할 수 있습니다.
          </p>
          <p>
            <span className="font-medium">카카오톡:</span> Kakao Developers에서 앱을 등록하고
            카카오 로그인 후 Access Token을 발급받으세요.
          </p>
        </div>
      </div>
    </div>
  )
}

/**
 * 브라우저 알림 설정 탭 컴포넌트
 * 브라우저 알림 권한 및 테스트
 */

import { useNotification } from '@/hooks/useNotification'
import Button from '@/components/ui/Button'
import { Bell, BellOff, BellRing } from 'lucide-react'

export default function NotificationsTab() {
  const { permission, isSupported, requestPermission, showNotification } = useNotification()

  return (
    <div className="bg-card rounded-lg border border-border p-6">
      <h3 className="text-lg font-semibold mb-4">🔔 알림 설정</h3>
      {!isSupported ? (
        <div className="p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
          <p className="text-sm text-yellow-600 dark:text-yellow-400">
            이 브라우저는 알림 기능을 지원하지 않습니다.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className={`p-4 rounded-lg border ${
            permission === 'granted'
              ? 'bg-green-500/10 border-green-500/30'
              : permission === 'denied'
              ? 'bg-red-500/10 border-red-500/30'
              : 'bg-yellow-500/10 border-yellow-500/30'
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {permission === 'granted' ? (
                  <BellRing className="w-5 h-5 text-green-500" />
                ) : permission === 'denied' ? (
                  <BellOff className="w-5 h-5 text-red-500" />
                ) : (
                  <Bell className="w-5 h-5 text-yellow-500" />
                )}
                <div>
                  <div className="font-medium">
                    {permission === 'granted'
                      ? '알림 활성화됨'
                      : permission === 'denied'
                      ? '알림 차단됨'
                      : '알림 권한 필요'}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {permission === 'granted'
                      ? '스캔 완료 시 브라우저 알림을 받습니다.'
                      : permission === 'denied'
                      ? '브라우저 설정에서 알림을 허용해주세요.'
                      : '알림을 허용하면 백그라운드에서도 작업 완료 알림을 받을 수 있습니다.'}
                  </div>
                </div>
              </div>
              {permission !== 'granted' && permission !== 'denied' && (
                <Button
                  variant="primary"
                  onClick={requestPermission}
                >
                  알림 허용
                </Button>
              )}
              {permission === 'granted' && (
                <Button
                  variant="secondary"
                  onClick={() => showNotification('테스트 알림', { body: '알림이 정상적으로 작동합니다!' })}
                >
                  테스트
                </Button>
              )}
            </div>
          </div>

          <div className="text-sm text-muted-foreground">
            <p className="font-medium mb-2">알림이 표시되는 경우:</p>
            <ul className="list-disc list-inside space-y-1">
              <li>스캔 작업이 완료되었을 때 (다른 탭에 있는 경우)</li>
              <li>새로운 리드가 발견되었을 때</li>
              <li>중요한 순위 변동이 감지되었을 때</li>
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}

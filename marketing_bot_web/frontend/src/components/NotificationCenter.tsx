import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notificationsApi, Notification } from '@/services/api'
import Button, { IconButton } from '@/components/ui/Button'
import { X, Bell, BarChart3, Target, Building2, Settings, KeyRound, Flame } from 'lucide-react'
import type { ReactNode } from 'react'

interface NotificationCenterProps {
  isOpen: boolean
  onClose: () => void
}

const priorityStyles: Record<string, string> = {
  critical: 'border-l-4 border-red-500 bg-red-50 dark:bg-red-900/20',
  high: 'border-l-4 border-orange-500 bg-orange-50 dark:bg-orange-900/20',
  medium: 'border-l-4 border-blue-500 bg-blue-50 dark:bg-blue-900/20',
  low: 'border-l-4 border-gray-300 bg-gray-50 dark:bg-gray-800/50',
}

const NC_I = 'w-4 h-4'
const typeIcons: Record<string, ReactNode> = {
  rank_change: <BarChart3 className={NC_I} strokeWidth={1.7} />,
  new_lead: <Target className={NC_I} strokeWidth={1.7} />,
  competitor: <Building2 className={NC_I} strokeWidth={1.7} />,
  system: <Settings className={NC_I} strokeWidth={1.7} />,
  keyword: <KeyRound className={NC_I} strokeWidth={1.7} />,
  viral: <Flame className={NC_I} strokeWidth={1.7} />,
}

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return '방금 전'
  if (diffMins < 60) return `${diffMins}분 전`
  if (diffHours < 24) return `${diffHours}시간 전`
  if (diffDays < 7) return `${diffDays}일 전`
  return date.toLocaleDateString('ko-KR')
}

export default function NotificationCenter({ isOpen, onClose }: NotificationCenterProps) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const { data, isLoading, error } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => notificationsApi.getList({ limit: 30 }),
    enabled: isOpen,
    refetchInterval: isOpen ? 30000 : false, // 열려있을 때만 30초마다 갱신
  })

  const markAsReadMutation = useMutation({
    mutationFn: notificationsApi.markAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  const markAllAsReadMutation = useMutation({
    mutationFn: notificationsApi.markAllAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: notificationsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const notifications: Notification[] = data?.notifications || []
  const unreadCount = data?.unread_count || 0

  const handleNotificationClick = (notification: Notification) => {
    if (!notification.is_read) {
      markAsReadMutation.mutate(notification.id)
    }
    if (notification.link) {
      if (notification.link.startsWith('/')) {
        navigate(notification.link)
      } else {
        window.location.href = notification.link
      }
    }
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50" onClick={onClose}>
      <div className="absolute inset-0 bg-black/20" />
      <div
        className="absolute right-4 top-16 w-[calc(100vw-2rem)] max-w-sm sm:w-96 max-h-[70vh] bg-card border border-border rounded-lg shadow-xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border bg-muted/50">
          <div className="flex items-center gap-2">
            <span className="text-lg font-semibold">알림</span>
            {unreadCount > 0 && (
              <span className="px-2 py-0.5 text-xs font-medium bg-primary text-primary-foreground rounded-full">
                {unreadCount}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {unreadCount > 0 && (
              <Button
                variant="ghost"
                size="xs"
                onClick={() => markAllAsReadMutation.mutate()}
                loading={markAllAsReadMutation.isPending}
              >
                모두 읽음
              </Button>
            )}
            <IconButton
              icon={<X className="w-5 h-5" />}
              onClick={onClose}
              size="sm"
              title="닫기"
            />
          </div>
        </div>

        {/* Content */}
        <div className="overflow-y-auto max-h-[calc(70vh-60px)]">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full" />
            </div>
          ) : error ? (
            <div className="p-4 text-center text-red-500">
              알림을 불러오는데 실패했습니다
            </div>
          ) : notifications.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              <div className="flex justify-center mb-2 text-faint"><Bell className="w-9 h-9" strokeWidth={1.5} /></div>
              <p>새 알림이 없습니다</p>
            </div>
          ) : (
            <div className="divide-y divide-border">
              {notifications.map((notification) => (
                <div
                  key={notification.id}
                  className={`p-4 cursor-pointer hover:bg-muted/50 transition-colors ${
                    priorityStyles[notification.priority]
                  } ${!notification.is_read ? 'bg-primary/5' : ''}`}
                  onClick={() => handleNotificationClick(notification)}
                >
                  <div className="flex items-start gap-3">
                    <span className="text-xl flex-shrink-0">
                      <span className="text-sage">{typeIcons[notification.type] || <Bell className={NC_I} strokeWidth={1.7} />}</span>
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h4 className={`text-sm font-medium truncate ${
                          !notification.is_read ? 'text-foreground' : 'text-muted-foreground'
                        }`}>
                          {notification.title}
                        </h4>
                        {!notification.is_read && (
                          <span className="w-2 h-2 bg-primary rounded-full flex-shrink-0" />
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                        {notification.message}
                      </p>
                      <div className="flex items-center justify-between mt-2">
                        <span className="text-xs text-muted-foreground">
                          {formatRelativeTime(notification.created_at)}
                        </span>
                        <Button
                          variant="ghost"
                          size="xs"
                          onClick={(e) => {
                            e.stopPropagation()
                            deleteMutation.mutate(notification.id)
                          }}
                          className="text-muted-foreground hover:text-red-500"
                        >
                          삭제
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// 알림 벨 버튼 컴포넌트
export function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false)

  const { data } = useQuery({
    queryKey: ['notifications-count'],
    queryFn: () => notificationsApi.getList({ unread_only: true, limit: 1 }),
    refetchInterval: 60000, // 1분마다 갱신
  })

  const unreadCount = data?.unread_count || 0

  return (
    <>
      <div className="relative">
        <IconButton
          icon={<Bell className="w-5 h-5" />}
          onClick={() => setIsOpen(true)}
          size="sm"
          title="알림"
        />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 flex items-center justify-center text-xs font-bold bg-red-500 text-white rounded-full">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </div>
      <NotificationCenter isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </>
  )
}

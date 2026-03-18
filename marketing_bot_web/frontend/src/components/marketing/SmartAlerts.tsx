/**
 * 스마트 알림 및 자동화 컴포넌트
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { marketingApi } from '@/services/api'
import {
  Bell, Plus, Trash2, ToggleLeft, ToggleRight,
  AlertTriangle, TrendingUp, Target, Clock, RefreshCw
} from 'lucide-react'
import type { AlertRule, AlertLog } from '@/types/marketing'
import Button, { IconButton } from '@/components/ui/Button'

interface SmartAlertsProps {
  compact?: boolean
}

const RULE_TYPES = [
  { value: 'lead_score', label: '리드 점수', icon: TrendingUp },
  { value: 'conversion_rate', label: '전환율', icon: AlertTriangle },
  { value: 'competitor', label: '경쟁사 언급', icon: Target },
  { value: 'golden_time', label: '골든타임', icon: Clock },
]

const ACTION_TYPES = [
  { value: 'email', label: '이메일' },
  { value: 'slack', label: 'Slack' },
  { value: 'webhook', label: 'Webhook' },
  { value: 'in_app', label: '앱 내 알림' },
]

// condition_json에서 threshold 추출
function parseThreshold(conditionJson: string): number | null {
  try {
    const parsed = JSON.parse(conditionJson)
    return parsed.threshold ?? null
  } catch {
    return null
  }
}

export function SmartAlerts({ compact = false }: SmartAlertsProps) {
  const [showCreateModal, setShowCreateModal] = useState(false)
  const queryClient = useQueryClient()

  const { data: rules, isLoading: rulesLoading, refetch, isRefetching } = useQuery<AlertRule[]>({
    queryKey: ['alert-rules'],
    queryFn: () => marketingApi.getAlertRules(),
    staleTime: 5 * 60 * 1000,
  })

  const { data: logs } = useQuery<AlertLog[]>({
    queryKey: ['alert-logs'],
    queryFn: () => marketingApi.getAlertLogs(50),
    staleTime: 60 * 1000,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      marketingApi.updateAlertRule(id, { is_active: active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-rules'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => marketingApi.deleteAlertRule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-rules'] })
    },
  })

  if (rulesLoading) {
    return (
      <div className="bg-card border border-border rounded-lg p-6 animate-pulse">
        <div className="h-6 bg-muted rounded w-1/3 mb-4" />
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-16 bg-muted rounded" />
          ))}
        </div>
      </div>
    )
  }

  const activeRules = rules?.filter(r => r.is_active === 1) || []
  const recentLogs = logs?.slice(0, 5) || []
  const unreadCount = logs?.filter(l => !l.read_at).length || 0

  // 컴팩트 모드
  if (compact) {
    return (
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Bell className="w-5 h-5 text-yellow-500" />
          스마트 알림
          {unreadCount > 0 && (
            <span className="px-2 py-0.5 bg-red-500 text-white text-xs rounded-full">
              {unreadCount}
            </span>
          )}
        </h3>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="text-center p-3 bg-muted/50 rounded-lg">
            <div className="text-2xl font-bold">{rules?.length || 0}</div>
            <div className="text-xs text-muted-foreground">전체 규칙</div>
          </div>
          <div className="text-center p-3 bg-green-500/10 rounded-lg">
            <div className="text-2xl font-bold text-green-500">{activeRules.length}</div>
            <div className="text-xs text-muted-foreground">활성 규칙</div>
          </div>
        </div>

        {recentLogs.length > 0 && (
          <div className="space-y-2">
            {recentLogs.slice(0, 2).map((log) => (
              <div
                key={log.id}
                className={`p-2 rounded-lg text-xs ${
                  log.read_at ? 'bg-muted/30' : 'bg-yellow-500/10 border border-yellow-500/30'
                }`}
              >
                <div className="font-medium truncate">{log.title}</div>
                <div className="text-muted-foreground">
                  {new Date(log.sent_at || log.created_at).toLocaleString('ko-KR')}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  // 전체 모드
  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <Bell className="w-6 h-6 text-yellow-500" />
          스마트 알림
          {unreadCount > 0 && (
            <span className="px-2 py-0.5 bg-red-500 text-white text-sm rounded-full">
              {unreadCount}
            </span>
          )}
        </h2>
        <div className="flex items-center gap-2">
          <IconButton
            icon={<RefreshCw className={`w-4 h-4 ${isRefetching ? 'animate-spin' : ''}`} />}
            onClick={() => refetch()}
            disabled={isRefetching}
            title="새로고침"
          />
          <Button
            variant="primary"
            onClick={() => setShowCreateModal(true)}
            icon={<Plus className="w-4 h-4" />}
          >
            규칙 추가
          </Button>
        </div>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <Bell className="w-8 h-8 mx-auto mb-2 text-blue-500" />
          <div className="text-3xl font-bold">{rules?.length || 0}</div>
          <div className="text-sm text-muted-foreground">전체 규칙</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <ToggleRight className="w-8 h-8 mx-auto mb-2 text-green-500" />
          <div className="text-3xl font-bold">{activeRules.length}</div>
          <div className="text-sm text-muted-foreground">활성 규칙</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <AlertTriangle className="w-8 h-8 mx-auto mb-2 text-yellow-500" />
          <div className="text-3xl font-bold">{unreadCount}</div>
          <div className="text-sm text-muted-foreground">미확인 알림</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4 text-center">
          <Clock className="w-8 h-8 mx-auto mb-2 text-purple-500" />
          <div className="text-3xl font-bold">{logs?.length || 0}</div>
          <div className="text-sm text-muted-foreground">총 알림 수</div>
        </div>
      </div>

      {/* 알림 규칙 목록 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">알림 규칙</h3>

        {!rules || rules.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Bell className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>설정된 알림 규칙이 없습니다.</p>
            <p className="text-sm mt-1">새 규칙을 추가하여 중요한 이벤트를 놓치지 마세요.</p>
            <Button
              variant="primary"
              className="mt-4"
              onClick={() => setShowCreateModal(true)}
              icon={<Plus className="w-4 h-4" />}
            >
              첫 규칙 추가
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {rules.map((rule) => {
              const ruleType = RULE_TYPES.find(c => c.value === rule.rule_type)
              const RuleIcon = ruleType?.icon || Bell
              const isActive = rule.is_active === 1
              const threshold = parseThreshold(rule.condition_json)

              return (
                <div
                  key={rule.id}
                  className={`p-4 border rounded-lg transition-colors ${
                    isActive
                      ? 'border-green-500/30 bg-green-500/5'
                      : 'border-border bg-muted/30'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <RuleIcon className={`w-5 h-5 ${
                        isActive ? 'text-green-500' : 'text-muted-foreground'
                      }`} />
                      <div>
                        <div className="font-medium">{rule.name}</div>
                        <div className="text-sm text-muted-foreground">
                          {ruleType?.label || rule.rule_type}
                          {threshold !== null && ` (임계값: ${threshold})`}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-xs px-2 py-1 bg-muted rounded">
                        {ACTION_TYPES.find(c => c.value === rule.action_type)?.label || rule.action_type}
                      </span>
                      <IconButton
                        icon={isActive ? (
                          <ToggleRight className="w-6 h-6 text-green-500" />
                        ) : (
                          <ToggleLeft className="w-6 h-6 text-muted-foreground" />
                        )}
                        onClick={() => toggleMutation.mutate({
                          id: rule.id,
                          active: !isActive
                        })}
                        title={isActive ? '비활성화' : '활성화'}
                      />
                      <IconButton
                        icon={<Trash2 className="w-4 h-4" />}
                        onClick={() => {
                          if (confirm('이 규칙을 삭제하시겠습니까?')) {
                            deleteMutation.mutate(rule.id)
                          }
                        }}
                        className="text-red-500 hover:bg-red-500/10"
                        title="삭제"
                      />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* 최근 알림 로그 */}
      <div className="bg-card border border-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">최근 알림</h3>

        {recentLogs.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p>최근 알림이 없습니다.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {recentLogs.map((log) => (
              <div
                key={log.id}
                className={`p-3 rounded-lg ${
                  log.read_at
                    ? 'bg-muted/30'
                    : 'bg-yellow-500/10 border border-yellow-500/30'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="font-medium">{log.title}</div>
                    {log.message && (
                      <div className="text-sm text-muted-foreground mt-1">
                        {log.message}
                      </div>
                    )}
                    {log.rule_name && (
                      <div className="text-sm text-muted-foreground mt-1">
                        규칙: {log.rule_name}
                      </div>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {new Date(log.sent_at || log.created_at).toLocaleString('ko-KR')}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 규칙 생성 모달 */}
      {showCreateModal && (
        <CreateRuleModal onClose={() => setShowCreateModal(false)} />
      )}
    </div>
  )
}

// 규칙 생성 모달
function CreateRuleModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [formData, setFormData] = useState({
    name: '',
    rule_type: 'lead_score',
    threshold: 80,
    action_type: 'in_app',
  })

  const createMutation = useMutation({
    mutationFn: (data: typeof formData) =>
      marketingApi.createAlertRule({
        name: data.name,
        rule_type: data.rule_type,
        condition_json: JSON.stringify({ threshold: data.threshold }),
        action_type: data.action_type,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-rules'] })
      onClose()
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.name.trim()) return
    createMutation.mutate(formData)
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card border border-border rounded-lg p-6 w-full max-w-md">
        <h3 className="text-xl font-bold mb-4">새 알림 규칙</h3>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">규칙 이름</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 bg-muted border border-border rounded-lg"
              placeholder="예: 고품질 리드 알림"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">규칙 유형</label>
            <select
              value={formData.rule_type}
              onChange={(e) => setFormData({ ...formData, rule_type: e.target.value })}
              className="w-full px-3 py-2 bg-muted border border-border rounded-lg"
            >
              {RULE_TYPES.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">임계값</label>
            <input
              type="number"
              value={formData.threshold}
              onChange={(e) => setFormData({ ...formData, threshold: parseInt(e.target.value) })}
              className="w-full px-3 py-2 bg-muted border border-border rounded-lg"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">알림 채널</label>
            <select
              value={formData.action_type}
              onChange={(e) => setFormData({ ...formData, action_type: e.target.value })}
              className="w-full px-3 py-2 bg-muted border border-border rounded-lg"
            >
              {ACTION_TYPES.map((action) => (
                <option key={action.value} value={action.value}>
                  {action.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex gap-2 pt-4">
            <Button
              variant="secondary"
              fullWidth
              type="button"
              onClick={onClose}
            >
              취소
            </Button>
            <Button
              variant="primary"
              fullWidth
              type="submit"
              loading={createMutation.isPending}
            >
              규칙 생성
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}

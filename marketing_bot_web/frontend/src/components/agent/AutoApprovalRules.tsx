/**
 * [Phase 6.2] AI 자동 승인 규칙 컴포넌트
 * 백엔드 API와 연동하여 자동 승인 규칙을 관리
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { agentApi } from '@/services/api'
import { Settings, Zap, Shield, Clock, Tag, Plus, Trash2, Edit2, Play, X, AlertCircle } from 'lucide-react'
import { useToast } from '@/components/ui/Toast'
import Button, { IconButton } from '@/components/ui/Button'

interface AutoApprovalRule {
  id: number
  name: string
  description: string | null
  condition_type: string
  condition_value: string
  action: string
  priority: number
  is_active: boolean
  created_at: string
}

interface RuleFormData {
  name: string
  description: string
  condition_type: string
  condition_value: string
  action: string
  priority: number
  is_active: boolean
}

const CONDITION_TYPES = [
  { value: 'action_type', label: '액션 유형', description: '특정 액션 유형만 처리 (comment, analysis, content, keyword)' },
  { value: 'score_threshold', label: '점수 임계값', description: '지정 점수 이상인 액션만 처리 (예: 80)' },
  { value: 'trust_level', label: '신뢰 수준', description: '특정 신뢰 수준 이상 (high, medium, low)' },
  { value: 'platform', label: '플랫폼', description: '특정 플랫폼만 처리 (cafe, blog, kin 등)' },
  { value: 'engagement_signal', label: '참여 신호', description: '참여 신호 유형 (seeking_info, ready_to_act, passive)' },
]

const ACTION_TYPES = [
  { value: 'approve', label: '자동 승인', color: 'text-green-500' },
  { value: 'skip', label: '건너뛰기', color: 'text-yellow-500' },
  { value: 'flag', label: '검토 필요 표시', color: 'text-red-500' },
]

const getConditionIcon = (type: string) => {
  switch (type) {
    case 'score_threshold':
      return <Zap className="w-4 h-4 text-yellow-500" />
    case 'action_type':
      return <Tag className="w-4 h-4 text-purple-500" />
    case 'trust_level':
      return <Shield className="w-4 h-4 text-green-500" />
    case 'platform':
      return <Clock className="w-4 h-4 text-blue-500" />
    default:
      return <Settings className="w-4 h-4 text-gray-500" />
  }
}

export default function AutoApprovalRules() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [isExpanded, setIsExpanded] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [editingRule, setEditingRule] = useState<AutoApprovalRule | null>(null)
  const [formData, setFormData] = useState<RuleFormData>({
    name: '',
    description: '',
    condition_type: 'score_threshold',
    condition_value: '80',
    action: 'approve',
    priority: 0,
    is_active: true,
  })

  // 규칙 목록 조회
  const { data, isLoading, error } = useQuery({
    queryKey: ['agent-rules'],
    queryFn: agentApi.getRules,
    staleTime: 60000,
  })

  // 규칙 생성
  const createMutation = useMutation({
    mutationFn: agentApi.createRule,
    onSuccess: () => {
      toast.success('규칙이 생성되었습니다')
      queryClient.invalidateQueries({ queryKey: ['agent-rules'] })
      resetForm()
    },
    onError: () => toast.error('규칙 생성 실패'),
  })

  // 규칙 수정
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<RuleFormData> }) =>
      agentApi.updateRule(id, data),
    onSuccess: () => {
      toast.success('규칙이 수정되었습니다')
      queryClient.invalidateQueries({ queryKey: ['agent-rules'] })
      resetForm()
    },
    onError: () => toast.error('규칙 수정 실패'),
  })

  // 규칙 삭제
  const deleteMutation = useMutation({
    mutationFn: agentApi.deleteRule,
    onSuccess: () => {
      toast.success('규칙이 삭제되었습니다')
      queryClient.invalidateQueries({ queryKey: ['agent-rules'] })
    },
    onError: () => toast.error('규칙 삭제 실패'),
  })

  // 규칙 적용
  const applyMutation = useMutation({
    mutationFn: agentApi.applyRules,
    onSuccess: (data) => {
      toast.success(`${data.applied_count || 0}개 액션에 규칙이 적용되었습니다`)
      queryClient.invalidateQueries({ queryKey: ['agent-actions'] })
      queryClient.invalidateQueries({ queryKey: ['agent-summary'] })
    },
    onError: () => toast.error('규칙 적용 실패'),
  })

  // 활성화/비활성화 토글
  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      agentApi.updateRule(id, { is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agent-rules'] })
    },
  })

  const resetForm = () => {
    setShowForm(false)
    setEditingRule(null)
    setFormData({
      name: '',
      description: '',
      condition_type: 'score_threshold',
      condition_value: '80',
      action: 'approve',
      priority: 0,
      is_active: true,
    })
  }

  const handleEdit = (rule: AutoApprovalRule) => {
    setEditingRule(rule)
    setFormData({
      name: rule.name,
      description: rule.description || '',
      condition_type: rule.condition_type,
      condition_value: rule.condition_value,
      action: rule.action,
      priority: rule.priority,
      is_active: rule.is_active,
    })
    setShowForm(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (editingRule) {
      updateMutation.mutate({ id: editingRule.id, data: formData })
    } else {
      createMutation.mutate(formData)
    }
  }

  const rules: AutoApprovalRule[] = data?.rules || []
  const activeCount = rules.filter((r) => r.is_active).length

  return (
    <div className="bg-card rounded-lg border border-border">
      {/* 헤더 */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-muted/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <Settings className="w-5 h-5 text-muted-foreground" />
          <div className="text-left">
            <div className="font-medium">자동 승인 규칙</div>
            <div className="text-sm text-muted-foreground">
              {isLoading ? '로딩 중...' :
               error ? '로드 실패' :
               activeCount > 0 ? `${activeCount}/${rules.length}개 규칙 활성화됨` :
               rules.length > 0 ? '모든 규칙 비활성화' : '규칙 없음'}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {activeCount > 0 && (
            <span className="px-2 py-1 bg-green-500/20 text-green-500 text-xs rounded-full">
              활성
            </span>
          )}
          <svg
            className={`w-5 h-5 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {/* 규칙 목록 */}
      {isExpanded && (
        <div className="border-t border-border p-4 space-y-4">
          {/* 에러 상태 */}
          {error && (
            <div className="flex items-center gap-2 p-3 bg-red-500/10 text-red-500 rounded-lg">
              <AlertCircle className="w-5 h-5" />
              <span>규칙을 불러올 수 없습니다</span>
            </div>
          )}

          {/* 액션 버튼 */}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                resetForm()
                setShowForm(true)
              }}
              icon={<Plus className="w-4 h-4" />}
            >
              새 규칙
            </Button>
            {rules.length > 0 && activeCount > 0 && (
              <Button
                variant="success"
                size="sm"
                onClick={() => applyMutation.mutate()}
                loading={applyMutation.isPending}
                icon={<Play className="w-4 h-4" />}
              >
                규칙 적용
              </Button>
            )}
          </div>

          {/* 규칙 추가/수정 폼 */}
          {showForm && (
            <form onSubmit={handleSubmit} className="bg-muted/30 rounded-lg p-4 space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="font-medium">{editingRule ? '규칙 수정' : '새 규칙 추가'}</h4>
                <IconButton
                  icon={<X className="w-4 h-4" />}
                  onClick={resetForm}
                  size="sm"
                  title="닫기"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">규칙 이름</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    required
                    className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder="예: 고점수 댓글 자동 승인"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1">조건 유형</label>
                  <select
                    value={formData.condition_type}
                    onChange={(e) => setFormData({ ...formData, condition_type: e.target.value })}
                    className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    {CONDITION_TYPES.map((ct) => (
                      <option key={ct.value} value={ct.value}>{ct.label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1">조건 값</label>
                  <input
                    type="text"
                    value={formData.condition_value}
                    onChange={(e) => setFormData({ ...formData, condition_value: e.target.value })}
                    required
                    className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder={
                      formData.condition_type === 'score_threshold' ? '80' :
                      formData.condition_type === 'action_type' ? 'comment' :
                      formData.condition_type === 'trust_level' ? 'high' :
                      formData.condition_type === 'platform' ? 'cafe' : '값 입력'
                    }
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1">동작</label>
                  <select
                    value={formData.action}
                    onChange={(e) => setFormData({ ...formData, action: e.target.value })}
                    className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    {ACTION_TYPES.map((at) => (
                      <option key={at.value} value={at.value}>{at.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">설명 (선택)</label>
                <input
                  type="text"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="규칙에 대한 설명"
                />
              </div>

              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    className="w-4 h-4"
                  />
                  <span className="text-sm">활성화</span>
                </label>
              </div>

              <div className="flex justify-end gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  type="button"
                  onClick={resetForm}
                >
                  취소
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  type="submit"
                  loading={createMutation.isPending || updateMutation.isPending}
                >
                  저장
                </Button>
              </div>
            </form>
          )}

          {/* 규칙 목록 */}
          {!isLoading && rules.length > 0 && (
            <div className="space-y-2">
              {rules.map((rule) => (
                <div
                  key={rule.id}
                  className={`flex items-center justify-between p-3 rounded-lg transition-colors ${
                    rule.is_active ? 'bg-green-500/10' : 'bg-muted/30'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    {getConditionIcon(rule.condition_type)}
                    <div>
                      <div className="font-medium text-sm flex items-center gap-2">
                        {rule.name}
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          rule.action === 'approve' ? 'bg-green-500/20 text-green-500' :
                          rule.action === 'skip' ? 'bg-yellow-500/20 text-yellow-500' :
                          'bg-red-500/20 text-red-500'
                        }`}>
                          {ACTION_TYPES.find(a => a.value === rule.action)?.label || rule.action}
                        </span>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {CONDITION_TYPES.find(c => c.value === rule.condition_type)?.label}: {rule.condition_value}
                        {rule.description && ` - ${rule.description}`}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <IconButton
                      icon={<Edit2 className="w-4 h-4" />}
                      onClick={() => handleEdit(rule)}
                      size="sm"
                      title="수정"
                    />
                    <IconButton
                      icon={<Trash2 className="w-4 h-4" />}
                      onClick={() => {
                        if (confirm('이 규칙을 삭제하시겠습니까?')) {
                          deleteMutation.mutate(rule.id)
                        }
                      }}
                      size="sm"
                      title="삭제"
                      className="hover:bg-red-500/20 text-red-500"
                    />
                    <button
                      onClick={() => toggleMutation.mutate({ id: rule.id, is_active: !rule.is_active })}
                      className={`relative w-10 h-5 rounded-full transition-colors ${
                        rule.is_active ? 'bg-green-500' : 'bg-muted'
                      }`}
                      role="switch"
                      aria-checked={rule.is_active}
                      aria-label={`${rule.name} ${rule.is_active ? '비활성화' : '활성화'}`}
                    >
                      <span
                        className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform ${
                          rule.is_active ? 'translate-x-5' : ''
                        }`}
                      />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 빈 상태 */}
          {!isLoading && rules.length === 0 && !showForm && (
            <div className="text-center py-6 text-muted-foreground">
              <Settings className="w-10 h-10 mx-auto mb-2 opacity-50" />
              <p>등록된 자동 승인 규칙이 없습니다</p>
              <p className="text-xs mt-1">새 규칙을 추가하여 AI 액션을 자동으로 처리하세요</p>
            </div>
          )}

          <div className="pt-3 border-t border-border">
            <p className="text-xs text-muted-foreground">
              <strong>조건 유형 설명:</strong><br />
              {CONDITION_TYPES.map((ct) => (
                <span key={ct.value} className="block mt-1">
                  • <strong>{ct.label}</strong>: {ct.description}
                </span>
              ))}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { hudApi } from '@/services/api'
import { Target, Plus, Trash2, TrendingUp, AlertCircle } from 'lucide-react'
import Button, { IconButton } from '@/components/ui/Button'

interface Goal {
  id: number
  type: string
  target_value: number
  current_value: number
  period: string
  title: string
  progress: number
  created_at: string
}

// [Phase 6.1] 목표값 검증 상수
const VALIDATION_RULES = {
  MIN_TARGET: 1,
  MAX_TARGET: 10000,
  MAX_TITLE_LENGTH: 50,
}

const GOAL_TYPES = [
  { id: 'leads', label: '리드 수', icon: '👥', unit: '명', suggestedRange: { min: 10, max: 500 } },
  { id: 'conversions', label: '전환 수', icon: '✅', unit: '건', suggestedRange: { min: 1, max: 100 } },
  { id: 'keywords', label: '키워드 수', icon: '🎯', unit: '개', suggestedRange: { min: 10, max: 1000 } },
  { id: 'rank_top10', label: 'TOP 10 키워드', icon: '🏆', unit: '개', suggestedRange: { min: 1, max: 50 } },
]

export default function GoalManager() {
  const queryClient = useQueryClient()
  const [showAddForm, setShowAddForm] = useState(false)
  const [newGoal, setNewGoal] = useState({
    type: 'leads',
    target_value: 100,
    period: 'monthly',
    title: ''
  })
  // [Phase 6.1] 검증 오류 상태
  const [validationErrors, setValidationErrors] = useState<{
    target_value?: string
    title?: string
  }>({})

  // 목표 목록 조회
  const { data: goalsData, isLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: hudApi.getGoals,
    retry: 1,
  })

  // 목표 생성
  const createGoalMutation = useMutation({
    mutationFn: hudApi.createGoal,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] })
      setShowAddForm(false)
      setNewGoal({ type: 'leads', target_value: 100, period: 'monthly', title: '' })
    },
  })

  // 목표 삭제
  const deleteGoalMutation = useMutation({
    mutationFn: hudApi.deleteGoal,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] })
    },
  })

  const goals: Goal[] = goalsData?.goals || []

  // [Phase 6.1] 목표값 검증 함수
  const validateTargetValue = useCallback((value: number, _type?: string): string | undefined => {
    if (isNaN(value) || value === null || value === undefined) {
      return '유효한 숫자를 입력하세요'
    }
    if (value < VALIDATION_RULES.MIN_TARGET) {
      return `목표값은 최소 ${VALIDATION_RULES.MIN_TARGET} 이상이어야 합니다`
    }
    if (value > VALIDATION_RULES.MAX_TARGET) {
      return `목표값은 최대 ${VALIDATION_RULES.MAX_TARGET.toLocaleString()} 이하여야 합니다`
    }
    if (!Number.isInteger(value)) {
      return '정수만 입력 가능합니다'
    }
    return undefined
  }, [])

  // [Phase 6.1] 제목 검증 함수
  const validateTitle = useCallback((title: string): string | undefined => {
    if (title.length > VALIDATION_RULES.MAX_TITLE_LENGTH) {
      return `제목은 최대 ${VALIDATION_RULES.MAX_TITLE_LENGTH}자까지 입력 가능합니다`
    }
    return undefined
  }, [])

  // [Phase 6.1] 목표값 변경 핸들러 (실시간 검증)
  const handleTargetValueChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const rawValue = e.target.value
    // 빈 값 허용 (입력 중일 수 있음)
    if (rawValue === '') {
      setNewGoal(prev => ({ ...prev, target_value: 0 }))
      setValidationErrors(prev => ({ ...prev, target_value: '목표값을 입력하세요' }))
      return
    }

    const value = parseInt(rawValue, 10)
    setNewGoal(prev => ({ ...prev, target_value: isNaN(value) ? 0 : value }))

    const error = validateTargetValue(value)
    setValidationErrors(prev => ({ ...prev, target_value: error }))
  }

  // [Phase 6.1] 제목 변경 핸들러
  const handleTitleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const title = e.target.value
    setNewGoal(prev => ({ ...prev, title }))

    const error = validateTitle(title)
    setValidationErrors(prev => ({ ...prev, title: error }))
  }

  // [Phase 6.1] 폼 유효성 검사
  const isFormValid = () => {
    const targetError = validateTargetValue(newGoal.target_value)
    const titleError = validateTitle(newGoal.title)
    return !targetError && !titleError
  }

  // [Phase 6.1] 현재 타입의 권장 범위 가져오기
  const getCurrentSuggestedRange = () => {
    const goalType = GOAL_TYPES.find(g => g.id === newGoal.type)
    return goalType?.suggestedRange || { min: 10, max: 500 }
  }

  const handleAddGoal = () => {
    // 최종 검증
    if (!isFormValid()) {
      return
    }

    const goalType = GOAL_TYPES.find(g => g.id === newGoal.type)
    createGoalMutation.mutate({
      type: newGoal.type,
      target_value: newGoal.target_value,
      period: newGoal.period,
      title: newGoal.title || `${goalType?.label || newGoal.type} 목표`
    })
  }

  // [Phase 6.1] 폼 초기화
  const resetForm = () => {
    setShowAddForm(false)
    setNewGoal({ type: 'leads', target_value: 100, period: 'monthly', title: '' })
    setValidationErrors({})
  }

  const getGoalTypeInfo = (type: string) => {
    return GOAL_TYPES.find(g => g.id === type) || { id: type, label: type, icon: '📊', unit: '' }
  }

  const getProgressColor = (progress: number) => {
    if (progress >= 100) return 'bg-green-500'
    if (progress >= 75) return 'bg-blue-500'
    if (progress >= 50) return 'bg-yellow-500'
    return 'bg-red-500'
  }

  if (isLoading) {
    return (
      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Target className="w-5 h-5 text-primary" />
            <h3 className="text-lg font-semibold">목표 관리</h3>
          </div>
        </div>
        <div className="space-y-3">
          {[1, 2].map(i => (
            <div key={i} className="h-16 bg-muted rounded-lg animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="bg-card rounded-lg border border-border p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Target className="w-5 h-5 text-primary" />
          <h3 className="text-lg font-semibold">목표 관리</h3>
        </div>
        <Button
          variant="primary"
          size="sm"
          onClick={() => setShowAddForm(!showAddForm)}
          icon={<Plus className="w-4 h-4" />}
        >
          목표 추가
        </Button>
      </div>

      {/* 목표 추가 폼 */}
      {showAddForm && (
        <div className="mb-4 p-4 bg-muted/30 rounded-lg border border-border">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <div>
              <label className="block text-xs font-medium mb-1">유형</label>
              <select
                value={newGoal.type}
                onChange={(e) => {
                  setNewGoal(prev => ({ ...prev, type: e.target.value }))
                  // 타입 변경 시 검증 재실행
                  setValidationErrors(prev => ({
                    ...prev,
                    target_value: validateTargetValue(newGoal.target_value)
                  }))
                }}
                className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                {GOAL_TYPES.map(type => (
                  <option key={type.id} value={type.id}>
                    {type.icon} {type.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium mb-1">목표값</label>
              <input
                type="number"
                value={newGoal.target_value || ''}
                onChange={handleTargetValueChange}
                className={`w-full px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 ${
                  validationErrors.target_value
                    ? 'border-red-500 focus:ring-red-500'
                    : 'border-border focus:ring-primary'
                }`}
                min={VALIDATION_RULES.MIN_TARGET}
                max={VALIDATION_RULES.MAX_TARGET}
                aria-invalid={!!validationErrors.target_value}
                aria-describedby={validationErrors.target_value ? 'target-error' : undefined}
              />
              {/* [Phase 6.1] 검증 오류 메시지 */}
              {validationErrors.target_value && (
                <div id="target-error" className="flex items-center gap-1 mt-1 text-xs text-red-500" role="alert">
                  <AlertCircle className="w-3 h-3" />
                  {validationErrors.target_value}
                </div>
              )}
              {/* [Phase 6.1] 권장 범위 힌트 */}
              {!validationErrors.target_value && (
                <div className="mt-1 text-xs text-muted-foreground">
                  권장: {getCurrentSuggestedRange().min}~{getCurrentSuggestedRange().max}
                </div>
              )}
            </div>
            <div>
              <label className="block text-xs font-medium mb-1">기간</label>
              <select
                value={newGoal.period}
                onChange={(e) => setNewGoal(prev => ({ ...prev, period: e.target.value }))}
                className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="weekly">주간</option>
                <option value="monthly">월간</option>
                <option value="quarterly">분기</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium mb-1">
                제목 (선택)
                <span className="text-muted-foreground font-normal ml-1">
                  {newGoal.title.length}/{VALIDATION_RULES.MAX_TITLE_LENGTH}
                </span>
              </label>
              <input
                type="text"
                value={newGoal.title}
                onChange={handleTitleChange}
                placeholder="목표 제목..."
                maxLength={VALIDATION_RULES.MAX_TITLE_LENGTH}
                className={`w-full px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 ${
                  validationErrors.title
                    ? 'border-red-500 focus:ring-red-500'
                    : 'border-border focus:ring-primary'
                }`}
                aria-invalid={!!validationErrors.title}
              />
              {validationErrors.title && (
                <div className="flex items-center gap-1 mt-1 text-xs text-red-500" role="alert">
                  <AlertCircle className="w-3 h-3" />
                  {validationErrors.title}
                </div>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              variant="primary"
              onClick={handleAddGoal}
              disabled={!isFormValid()}
              loading={createGoalMutation.isPending}
            >
              저장
            </Button>
            <Button variant="secondary" onClick={resetForm}>
              취소
            </Button>
          </div>
        </div>
      )}

      {/* 목표 목록 */}
      {goals.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          <TrendingUp className="w-10 h-10 mx-auto mb-3 opacity-50" />
          <p className="text-sm">설정된 목표가 없습니다.</p>
          <p className="text-xs mt-1">위 버튼을 클릭하여 첫 목표를 설정하세요.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {goals.map((goal) => {
            const typeInfo = getGoalTypeInfo(goal.type)
            const progress = Math.min(100, goal.progress || 0)

            return (
              <div
                key={goal.id}
                className="p-3 bg-muted/30 rounded-lg border border-border hover:border-primary/30 transition-colors"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{typeInfo.icon}</span>
                    <span className="font-medium text-sm">{goal.title || typeInfo.label}</span>
                    <span className="px-2 py-0.5 bg-muted rounded text-xs text-muted-foreground">
                      {goal.period === 'weekly' ? '주간' : goal.period === 'monthly' ? '월간' : '분기'}
                    </span>
                  </div>
                  <IconButton
                    icon={<Trash2 className="w-4 h-4" />}
                    onClick={() => deleteGoalMutation.mutate(goal.id)}
                    disabled={deleteGoalMutation.isPending}
                    className="text-red-500 hover:bg-red-500/10"
                    title="삭제"
                  />
                </div>

                {/* 진행률 바 */}
                <div className="mb-2">
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full ${getProgressColor(progress)} transition-all duration-500`}
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>

                {/* 수치 */}
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">
                    현재: <span className="font-semibold text-foreground">{goal.current_value?.toLocaleString() || 0}{typeInfo.unit}</span>
                  </span>
                  <span className="text-muted-foreground">
                    목표: <span className="font-semibold text-foreground">{goal.target_value?.toLocaleString()}{typeInfo.unit}</span>
                  </span>
                  <span className={`font-bold ${progress >= 100 ? 'text-green-500' : progress >= 75 ? 'text-blue-500' : 'text-muted-foreground'}`}>
                    {progress.toFixed(0)}%
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

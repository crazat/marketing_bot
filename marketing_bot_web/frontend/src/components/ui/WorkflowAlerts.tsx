/**
 * [Phase F-1] 워크플로우 알림 컴포넌트
 * 자동 트리거된 워크플로우 규칙 결과를 표시
 */

import { useState } from 'react'
import {
  Bell,
  AlertTriangle,
  Zap,
  ChevronRight,
  X,
  Settings,
  CheckCircle2,
} from 'lucide-react'
import useWorkflowRules, { TriggeredWorkflow } from '@/hooks/useWorkflowRules'
import Button, { IconButton } from '@/components/ui/Button'

interface WorkflowAlertsProps {
  /** 컴팩트 모드 (배너용) */
  compact?: boolean
  /** 최대 표시 수 */
  maxItems?: number
  /** 닫기 가능 여부 */
  dismissible?: boolean
}

export default function WorkflowAlerts({
  compact = false,
  maxItems = 5,
  dismissible = true,
}: WorkflowAlertsProps) {
  const { triggeredWorkflows, summary } = useWorkflowRules()
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const [expanded, setExpanded] = useState(false)

  // 닫지 않은 워크플로우만 표시
  const visibleWorkflows = triggeredWorkflows.filter(
    (w) => !dismissed.has(w.rule.id)
  )

  const handleDismiss = (ruleId: string) => {
    setDismissed((prev) => new Set([...prev, ruleId]))
  }

  if (visibleWorkflows.length === 0) {
    if (compact) return null
    return (
      <div className="bg-green-500/5 border border-green-500/20 rounded-lg p-4">
        <div className="flex items-center gap-3">
          <CheckCircle2 className="w-5 h-5 text-green-500" />
          <div>
            <p className="font-medium text-green-700 dark:text-green-400">모든 상황 양호</p>
            <p className="text-sm text-muted-foreground">
              현재 트리거된 워크플로우가 없습니다
            </p>
          </div>
        </div>
      </div>
    )
  }

  const getPriorityStyles = (priority: string) => {
    switch (priority) {
      case 'critical':
        return {
          bg: 'bg-red-500/10',
          border: 'border-red-500/30',
          icon: 'text-red-500',
          badge: 'bg-red-500 text-white',
        }
      case 'high':
        return {
          bg: 'bg-orange-500/10',
          border: 'border-orange-500/30',
          icon: 'text-orange-500',
          badge: 'bg-orange-500 text-white',
        }
      case 'medium':
        return {
          bg: 'bg-yellow-500/10',
          border: 'border-yellow-500/30',
          icon: 'text-yellow-500',
          badge: 'bg-yellow-500 text-black',
        }
      default:
        return {
          bg: 'bg-blue-500/10',
          border: 'border-blue-500/30',
          icon: 'text-blue-500',
          badge: 'bg-blue-500 text-white',
        }
    }
  }

  // 컴팩트 모드 (배너)
  if (compact) {
    const topWorkflow = visibleWorkflows[0]
    const topAction = topWorkflow?.suggestedActions[0]
    if (!topWorkflow || !topAction) return null

    const styles = getPriorityStyles(topAction.priority)

    return (
      <div className={`${styles.bg} border ${styles.border} rounded-lg p-3`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-1.5 rounded-lg ${styles.bg}`}>
              {topAction.priority === 'critical' ? (
                <AlertTriangle className={`w-4 h-4 ${styles.icon}`} />
              ) : (
                <Zap className={`w-4 h-4 ${styles.icon}`} />
              )}
            </div>
            <div>
              <p className="text-sm font-medium">{topWorkflow.rule.name}</p>
              <p className="text-xs text-muted-foreground">
                {topAction.label}
                {visibleWorkflows.length > 1 && ` 외 ${visibleWorkflows.length - 1}건`}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="xs"
              onClick={topAction.action}
            >
              실행
            </Button>
            {dismissible && (
              <IconButton
                icon={<X className="w-4 h-4" />}
                onClick={() => handleDismiss(topWorkflow.rule.id)}
                size="sm"
                title="닫기"
              />
            )}
          </div>
        </div>
      </div>
    )
  }

  // 전체 모드
  const displayWorkflows = expanded
    ? visibleWorkflows
    : visibleWorkflows.slice(0, maxItems)

  return (
    <div className="space-y-4">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bell className="w-5 h-5 text-primary" />
          <h3 className="font-semibold">자동 워크플로우 알림</h3>
          {summary.critical > 0 && (
            <span className="px-2 py-0.5 text-xs bg-red-500 text-white rounded-full animate-pulse">
              긴급 {summary.critical}
            </span>
          )}
          {summary.high > 0 && (
            <span className="px-2 py-0.5 text-xs bg-orange-500 text-white rounded-full">
              높음 {summary.high}
            </span>
          )}
        </div>
        <IconButton
          icon={<Settings className="w-4 h-4" />}
          title="워크플로우 설정"
        />
      </div>

      {/* 워크플로우 목록 */}
      <div className="space-y-3">
        {displayWorkflows.map((workflow) => (
          <WorkflowCard
            key={workflow.rule.id}
            workflow={workflow}
            onDismiss={dismissible ? () => handleDismiss(workflow.rule.id) : undefined}
          />
        ))}
      </div>

      {/* 더보기 */}
      {visibleWorkflows.length > maxItems && (
        <Button
          variant="ghost"
          fullWidth
          onClick={() => setExpanded(!expanded)}
          className="text-primary"
        >
          {expanded ? '접기' : `+${visibleWorkflows.length - maxItems}개 더 보기`}
        </Button>
      )}
    </div>
  )
}

// 개별 워크플로우 카드
function WorkflowCard({
  workflow,
  onDismiss,
}: {
  workflow: TriggeredWorkflow
  onDismiss?: () => void
}) {
  const topAction = workflow.suggestedActions[0]
  const priority = topAction?.priority || 'medium'

  const styles = {
    critical: {
      bg: 'bg-red-500/5',
      border: 'border-red-500/30',
      icon: 'bg-red-500/20 text-red-500',
      badge: 'bg-red-500 text-white',
    },
    high: {
      bg: 'bg-orange-500/5',
      border: 'border-orange-500/30',
      icon: 'bg-orange-500/20 text-orange-500',
      badge: 'bg-orange-500 text-white',
    },
    medium: {
      bg: 'bg-yellow-500/5',
      border: 'border-yellow-500/30',
      icon: 'bg-yellow-500/20 text-yellow-500',
      badge: 'bg-yellow-500 text-black',
    },
    low: {
      bg: 'bg-blue-500/5',
      border: 'border-blue-500/30',
      icon: 'bg-blue-500/20 text-blue-500',
      badge: 'bg-blue-500 text-white',
    },
  }[priority]

  return (
    <div className={`rounded-lg border p-4 ${styles.bg} ${styles.border}`}>
      <div className="flex items-start gap-3">
        {/* 아이콘 */}
        <div className={`p-2 rounded-lg ${styles.icon}`}>
          {priority === 'critical' ? (
            <AlertTriangle className="w-4 h-4" />
          ) : (
            <Zap className="w-4 h-4" />
          )}
        </div>

        {/* 내용 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`px-1.5 py-0.5 text-[10px] rounded ${styles.badge}`}>
              {priority === 'critical' ? '긴급' :
               priority === 'high' ? '높음' :
               priority === 'medium' ? '중간' : '낮음'}
            </span>
            <h4 className="font-medium text-sm">{workflow.rule.name}</h4>
          </div>
          <p className="text-sm text-muted-foreground mb-3">
            {workflow.rule.description}
          </p>

          {/* 액션 버튼들 */}
          <div className="flex flex-wrap gap-2">
            {workflow.suggestedActions.map((action, idx) => (
              <Button
                key={idx}
                variant={idx === 0 ? 'primary' : 'secondary'}
                size="xs"
                onClick={action.action}
                icon={<ChevronRight className="w-3 h-3" />}
                iconPosition="right"
              >
                {action.label}
              </Button>
            ))}
          </div>
        </div>

        {/* 닫기 버튼 */}
        {onDismiss && (
          <IconButton
            icon={<X className="w-4 h-4" />}
            onClick={onDismiss}
            size="sm"
            title="닫기"
          />
        )}
      </div>
    </div>
  )
}

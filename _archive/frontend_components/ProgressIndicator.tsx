/**
 * ProgressIndicator 컴포넌트
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [UX 개선] 긴 작업 시 진행률 피드백 제공
 * - 모달 오버레이 형태
 * - 진행률 바 또는 인디터미네이트 스피너
 * - 현재 작업 메시지
 * - 취소 가능 옵션
 */

import { X } from 'lucide-react'
import { ProgressBar, InlineSpinner } from './LoadingSpinner'

interface ProgressIndicatorProps {
  /** 표시 여부 */
  isVisible: boolean
  /** 진행률 (0-100, undefined면 인디터미네이트) */
  progress?: number
  /** 메인 메시지 */
  message?: string
  /** 서브 메시지 (현재 처리 중인 항목 등) */
  subMessage?: string
  /** 취소 가능 여부 */
  cancellable?: boolean
  /** 취소 핸들러 */
  onCancel?: () => void
  /** 취소 버튼 텍스트 */
  cancelText?: string
}

export function ProgressIndicator({
  isVisible,
  progress,
  message = '처리 중...',
  subMessage,
  cancellable = false,
  onCancel,
  cancelText = '취소',
}: ProgressIndicatorProps) {
  if (!isVisible) return null

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="progress-title"
      aria-describedby="progress-description"
    >
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-sm w-full mx-4 shadow-xl">
        <div className="text-center">
          {/* 메인 메시지 */}
          <h3
            id="progress-title"
            className="text-lg font-medium mb-4 text-gray-900 dark:text-gray-100"
          >
            {message}
          </h3>

          {/* 진행률 바 또는 스피너 */}
          {progress !== undefined ? (
            <div className="mb-4">
              <ProgressBar
                progress={progress}
                showPercentage={true}
                color="primary"
                size="md"
              />
            </div>
          ) : (
            <div className="flex justify-center mb-4">
              <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          )}

          {/* 서브 메시지 */}
          {subMessage && (
            <p
              id="progress-description"
              className="text-sm text-gray-600 dark:text-gray-400 mb-4"
            >
              {subMessage}
            </p>
          )}

          {/* 취소 버튼 */}
          {cancellable && onCancel && (
            <button
              onClick={onCancel}
              className="mt-2 px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors"
            >
              {cancelText}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

/**
 * 단계별 진행률 표시
 */
interface Step {
  id: string
  label: string
  status: 'pending' | 'in_progress' | 'completed' | 'error'
}

interface StepProgressIndicatorProps {
  isVisible: boolean
  steps: Step[]
  title?: string
  onCancel?: () => void
}

export function StepProgressIndicator({
  isVisible,
  steps,
  title = '작업 진행 중',
  onCancel,
}: StepProgressIndicatorProps) {
  if (!isVisible) return null

  const completedCount = steps.filter(s => s.status === 'completed').length
  const progress = (completedCount / steps.length) * 100

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
        {/* 헤더 */}
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
            {title}
          </h3>
          {onCancel && (
            <button
              onClick={onCancel}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              aria-label="취소"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* 전체 진행률 */}
        <div className="mb-6">
          <ProgressBar progress={progress} showPercentage={true} size="sm" />
        </div>

        {/* 단계 목록 */}
        <ul className="space-y-3">
          {steps.map((step) => (
            <li key={step.id} className="flex items-center gap-3">
              {/* 상태 아이콘 */}
              <div className="flex-shrink-0">
                {step.status === 'completed' && (
                  <div className="w-5 h-5 rounded-full bg-green-500 flex items-center justify-center">
                    <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                )}
                {step.status === 'in_progress' && (
                  <InlineSpinner size="sm" />
                )}
                {step.status === 'pending' && (
                  <div className="w-5 h-5 rounded-full border-2 border-gray-300 dark:border-gray-600" />
                )}
                {step.status === 'error' && (
                  <div className="w-5 h-5 rounded-full bg-red-500 flex items-center justify-center">
                    <X className="w-3 h-3 text-white" />
                  </div>
                )}
              </div>

              {/* 라벨 */}
              <span
                className={`text-sm ${
                  step.status === 'completed'
                    ? 'text-green-600 dark:text-green-400'
                    : step.status === 'in_progress'
                    ? 'text-primary font-medium'
                    : step.status === 'error'
                    ? 'text-red-600 dark:text-red-400'
                    : 'text-gray-500 dark:text-gray-400'
                }`}
              >
                {step.label}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export default ProgressIndicator

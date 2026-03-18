/**
 * Analytics 공유 컴포넌트 및 유틸리티
 */

import React from 'react'
import { Loader2, AlertTriangle, RefreshCw } from 'lucide-react'

// 플랫폼 라벨 변환 유틸리티
export function getPlatformLabel(platform: string): string {
  const labels: Record<string, string> = {
    naver: '네이버',
    naver_cafe: '네이버 카페',
    youtube: 'YouTube',
    youtube_comment: 'YouTube 댓글',
    tiktok: 'TikTok',
    tiktok_cc_hashtag: 'TikTok',
    instagram: 'Instagram',
    cafe: '맘카페',
    blog: '블로그',
    carrot: '당근마켓',
    unknown: '기타',
  }
  return labels[platform] || platform
}

// 로딩 상태 컴포넌트
interface LoadingStateProps {
  message?: string
}

export const LoadingState = React.memo(function LoadingState({
  message = '데이터 로딩 중...'
}: LoadingStateProps) {
  return (
    <div className="bg-card rounded-lg border border-border p-6">
      <div
        className="flex items-center justify-center py-8"
        role="status"
        aria-live="polite"
      >
        <Loader2 className="w-6 h-6 animate-spin text-primary" aria-hidden="true" />
        <span className="ml-2 text-muted-foreground">{message}</span>
      </div>
    </div>
  )
})

// 에러 상태 컴포넌트
interface ErrorStateProps {
  message?: string
  onRetry?: () => void
  isRetrying?: boolean
}

export const ErrorState = React.memo(function ErrorState({
  message = '데이터를 불러오는데 실패했습니다',
  onRetry,
  isRetrying = false,
}: ErrorStateProps) {
  return (
    <div className="bg-card rounded-lg border border-red-500/30 p-6">
      <div className="text-center" role="alert">
        <AlertTriangle className="w-8 h-8 text-red-500 mx-auto mb-2" aria-hidden="true" />
        <p className="text-red-500 font-medium">{message}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            disabled={isRetrying}
            className="mt-3 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2 mx-auto"
            aria-label="다시 시도"
          >
            <RefreshCw className={`w-4 h-4 ${isRetrying ? 'animate-spin' : ''}`} aria-hidden="true" />
            다시 시도
          </button>
        )}
      </div>
    </div>
  )
})

// 변화율 표시 컴포넌트
interface ChangeIndicatorProps {
  value: number
  showPlus?: boolean
}

export const ChangeIndicator = React.memo(function ChangeIndicator({
  value,
  showPlus = true,
}: ChangeIndicatorProps) {
  if (value === 0) return null

  const label = value > 0 ? `${Math.abs(value).toFixed(0)}% 증가` : `${Math.abs(value).toFixed(0)}% 감소`

  return (
    <span
      className={`text-xs ${value > 0 ? 'text-green-500' : 'text-red-500'}`}
      aria-label={label}
    >
      {value > 0 && showPlus ? '+' : ''}{value.toFixed(0)}%
    </span>
  )
})

// 요약 카드 컴포넌트
interface SummaryCardProps {
  label: string
  value: string | number
  icon?: React.ReactNode
  highlight?: boolean
  change?: number
  color?: string
}

export const SummaryCard = React.memo(function SummaryCard({
  label,
  value,
  icon,
  highlight,
  change,
  color = '',
}: SummaryCardProps) {
  return (
    <div className={`p-3 rounded-lg ${highlight ? 'bg-primary/10 border border-primary/30' : 'bg-muted/50'}`}>
      <div className="flex items-center gap-1 text-muted-foreground mb-1">
        {icon && <span aria-hidden="true">{icon}</span>}
        <span className="text-xs">{label}</span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className={`text-xl font-bold ${highlight ? 'text-primary' : ''} ${color}`}>
          {value}
        </span>
        {change !== undefined && <ChangeIndicator value={change} />}
      </div>
    </div>
  )
})

// 빈 데이터 상태 컴포넌트
interface EmptyStateProps {
  icon?: React.ReactNode
  message: string
}

export const EmptyState = React.memo(function EmptyState({
  icon,
  message,
}: EmptyStateProps) {
  return (
    <div className="p-6 text-center text-muted-foreground">
      {icon && <div className="w-8 h-8 mx-auto mb-2 opacity-50" aria-hidden="true">{icon}</div>}
      <p>{message}</p>
    </div>
  )
})

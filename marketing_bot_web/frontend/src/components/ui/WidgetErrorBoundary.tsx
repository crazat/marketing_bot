import { Component, ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props {
  children: ReactNode
  widgetName: string
  /** 선택적 커스텀 fallback */
  fallback?: (error: Error, retry: () => void) => ReactNode
  /** 높이 안정화용 최소 높이 */
  minHeight?: string
}

interface State {
  hasError: boolean
  error: Error | null
  resetKey: number
}

/**
 * [Y4] 위젯별 에러 경계 — 페이지가 아닌 개별 위젯 단위 fallback.
 *
 * 한 위젯이 실패해도 나머지 대시보드는 정상 작동.
 * fallback UI는 Seoul Medical Editorial 톤과 재시도 버튼 포함.
 */
export default class WidgetErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null, resetKey: 0 }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error): void {
    console.error(`[WidgetErrorBoundary:${this.props.widgetName}]`, error)
  }

  handleRetry = (): void => {
    this.setState((prev) => ({
      hasError: false,
      error: null,
      resetKey: prev.resetKey + 1,
    }))
  }

  render(): ReactNode {
    if (this.state.hasError && this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback(this.state.error, this.handleRetry)
      }

      return (
        <div
          role="alert"
          className="bg-card border border-destructive/30 p-5 flex flex-col justify-center"
          style={{ minHeight: this.props.minHeight ?? '160px' }}
        >
          <div className="flex items-start gap-3 mb-3">
            <AlertTriangle
              className="w-5 h-5 text-destructive shrink-0 mt-0.5"
              aria-hidden
            />
            <div className="flex-1 min-w-0">
              <div className="caps text-destructive mb-1">위젯 오류</div>
              <h4 className="font-display text-base leading-tight mb-1">
                "{this.props.widgetName}" 로딩 실패
              </h4>
              <p className="text-xs text-muted-foreground line-clamp-2">
                {this.state.error.message || '알 수 없는 오류가 발생했습니다.'}
              </p>
            </div>
          </div>
          <button
            onClick={this.handleRetry}
            className="self-start inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-muted hover:bg-muted/70 border border-border transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            이 위젯만 재시도
          </button>
        </div>
      )
    }

    return <div key={this.state.resetKey}>{this.props.children}</div>
  }
}

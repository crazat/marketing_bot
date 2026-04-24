import { logger } from '@/utils/logger'

/**
 * [AA1] 전역 에러 추적 설치
 *
 * - window.onerror: 동기 런타임 에러
 * - unhandledrejection: Promise reject 누락
 *
 * 실제 수집 서비스(Sentry 등) 없이도 logger.error 경로로 큐에 누적.
 * 추후 엔드포인트 추가 시 logger에서 flush만 구현.
 */
export function installErrorTracking(): void {
  if (typeof window === 'undefined') return

  window.addEventListener('error', (event) => {
    // 리소스 로드 에러(이미지 404 등) 제외
    if (!(event.target instanceof HTMLElement)) {
      logger.error('window.error', {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        error: event.error,
      })
    }
  })

  window.addEventListener('unhandledrejection', (event) => {
    logger.error('unhandledrejection', {
      reason: event.reason instanceof Error
        ? { name: event.reason.name, message: event.reason.message, stack: event.reason.stack }
        : event.reason,
    })
  })
}

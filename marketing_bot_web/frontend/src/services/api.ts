/**
 * API 클라이언트 - 하위 호환성을 위한 재내보내기
 *
 * 이 파일은 @/services/api/index.ts에서 모든 API와 타입을 재내보내기합니다.
 * 새 코드에서는 개별 모듈에서 직접 import하는 것을 권장합니다.
 *
 * @example
 * // 레거시 방식 (하위 호환)
 * import { hudApi, viralApi, LeadStats } from '@/services/api'
 *
 * // 권장 방식
 * import { hudApi } from '@/services/api/hud'
 * import { viralApi } from '@/services/api/viral'
 * import type { LeadStats } from '@/services/api/base'
 */

// 모든 API와 타입을 재내보내기
export * from './api/index'

// 기본 export
export { default } from './api/index'

/**
 * 에러 메시지 변환 유틸리티
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * [Phase 5.0] 에러 처리 고도화
 * - 에러 타입 분류
 * - 사용자 친화적 메시지 변환
 * - 에러별 액션 정의
 * - 재시도 가능 여부 판단
 */

// 에러 타입 정의
export type ApiErrorType =
  | 'NETWORK_ERROR'
  | 'TIMEOUT'
  | 'UNAUTHORIZED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'VALIDATION_ERROR'
  | 'SERVER_ERROR'
  | 'RATE_LIMIT'
  | 'DATABASE_ERROR'
  | 'UNKNOWN'

// 에러 심각도
export type ErrorSeverity = 'critical' | 'error' | 'warning' | 'info'

// 에러 설정 타입
export interface ErrorConfig {
  type: ApiErrorType
  message: string
  severity: ErrorSeverity
  retryable: boolean
  retryDelay?: number // ms
  maxRetries?: number
  actions: Array<{
    label: string
    action: 'retry' | 'refresh' | 'navigate' | 'dismiss'
    target?: string // navigate 시 경로
  }>
}

// 에러 타입별 설정
export const ERROR_CONFIGS: Record<ApiErrorType, Omit<ErrorConfig, 'type'>> = {
  NETWORK_ERROR: {
    message: '네트워크 연결을 확인해주세요',
    severity: 'error',
    retryable: true,
    retryDelay: 3000,
    maxRetries: 3,
    actions: [
      { label: '다시 시도', action: 'retry' },
      { label: '새로고침', action: 'refresh' },
    ],
  },
  TIMEOUT: {
    message: '요청 시간이 초과되었습니다',
    severity: 'warning',
    retryable: true,
    retryDelay: 2000,
    maxRetries: 2,
    actions: [{ label: '다시 시도', action: 'retry' }],
  },
  UNAUTHORIZED: {
    message: '인증이 필요합니다',
    severity: 'warning',
    retryable: false,
    actions: [
      { label: '새로고침', action: 'refresh' },
    ],
  },
  FORBIDDEN: {
    message: '접근 권한이 없습니다',
    severity: 'error',
    retryable: false,
    actions: [
      { label: '홈으로', action: 'navigate', target: '/' },
    ],
  },
  NOT_FOUND: {
    message: '요청한 데이터를 찾을 수 없습니다',
    severity: 'warning',
    retryable: false,
    actions: [
      { label: '새로고침', action: 'refresh' },
      { label: '홈으로', action: 'navigate', target: '/' },
    ],
  },
  VALIDATION_ERROR: {
    message: '입력 내용을 확인해주세요',
    severity: 'warning',
    retryable: false,
    actions: [{ label: '확인', action: 'dismiss' }],
  },
  SERVER_ERROR: {
    message: '서버에서 오류가 발생했습니다',
    severity: 'critical',
    retryable: true,
    retryDelay: 5000,
    maxRetries: 2,
    actions: [
      { label: '다시 시도', action: 'retry' },
      { label: '홈으로', action: 'navigate', target: '/' },
    ],
  },
  RATE_LIMIT: {
    message: '요청이 너무 많습니다. 잠시 후 다시 시도해주세요',
    severity: 'warning',
    retryable: true,
    retryDelay: 10000,
    maxRetries: 1,
    actions: [{ label: '확인', action: 'dismiss' }],
  },
  DATABASE_ERROR: {
    message: '데이터베이스 오류가 발생했습니다',
    severity: 'error',
    retryable: true,
    retryDelay: 3000,
    maxRetries: 2,
    actions: [{ label: '다시 시도', action: 'retry' }],
  },
  UNKNOWN: {
    message: '알 수 없는 오류가 발생했습니다',
    severity: 'error',
    retryable: true,
    retryDelay: 2000,
    maxRetries: 1,
    actions: [
      { label: '다시 시도', action: 'retry' },
      { label: '새로고침', action: 'refresh' },
    ],
  },
}

// 일반적인 에러 메시지 매핑
const ERROR_MESSAGES: Record<string, string> = {
  // 네트워크 에러
  'Network Error': '서버에 연결할 수 없습니다. 인터넷 연결을 확인해주세요.',
  'timeout': '요청 시간이 초과되었습니다. 다시 시도해주세요.',
  'ECONNABORTED': '요청 시간이 초과되었습니다. 다시 시도해주세요.',
  'ECONNREFUSED': '서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.',

  // HTTP 상태 코드 에러
  '400': '잘못된 요청입니다. 입력 내용을 확인해주세요.',
  '401': '인증이 필요합니다. 다시 로그인해주세요.',
  '403': '접근 권한이 없습니다.',
  '404': '요청한 리소스를 찾을 수 없습니다.',
  '500': '서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.',
  '502': '서버가 일시적으로 응답하지 않습니다. 잠시 후 다시 시도해주세요.',
  '503': '서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해주세요.',

  // 일반 에러
  'Unknown Error': '알 수 없는 오류가 발생했습니다.',
  'Failed to fetch': '서버에 연결할 수 없습니다.',
}

// 특정 API 에러 메시지 패턴 매핑
const ERROR_PATTERNS: Array<{ pattern: RegExp; message: string; type: ApiErrorType }> = [
  // 데이터베이스 에러
  { pattern: /database.*locked/i, message: '데이터베이스가 일시적으로 사용 중입니다.', type: 'DATABASE_ERROR' },
  { pattern: /sqlite.*locked/i, message: 'DB가 잠시 사용 중입니다. 잠시 후 다시 시도해주세요.', type: 'DATABASE_ERROR' },
  { pattern: /no such table/i, message: '필요한 테이블이 없습니다. 서버를 재시작해주세요.', type: 'DATABASE_ERROR' },
  { pattern: /no such column/i, message: '데이터 구조가 변경되었습니다. 서버를 재시작해주세요.', type: 'DATABASE_ERROR' },

  // 네트워크 에러
  { pattern: /connection.*refused/i, message: '서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.', type: 'NETWORK_ERROR' },
  { pattern: /network/i, message: '네트워크 오류가 발생했습니다. 인터넷 연결을 확인해주세요.', type: 'NETWORK_ERROR' },

  // 타임아웃
  { pattern: /timeout/i, message: '요청 시간이 초과되었습니다. 다시 시도해주세요.', type: 'TIMEOUT' },

  // 권한 에러
  { pattern: /not found/i, message: '요청한 데이터를 찾을 수 없습니다.', type: 'NOT_FOUND' },
  { pattern: /permission denied/i, message: '권한이 없습니다.', type: 'FORBIDDEN' },
  { pattern: /rate limit/i, message: '요청이 너무 많습니다. 1분 후 다시 시도해주세요.', type: 'RATE_LIMIT' },
  { pattern: /invalid.*token/i, message: '인증이 만료되었습니다.', type: 'UNAUTHORIZED' },

  // 마케팅 봇 도메인 특화 에러
  { pattern: /키워드.*찾을 수 없/i, message: '해당 키워드를 찾을 수 없습니다.', type: 'NOT_FOUND' },
  { pattern: /리드.*찾을 수 없/i, message: '해당 리드를 찾을 수 없습니다.', type: 'NOT_FOUND' },
  { pattern: /Q&A.*찾을 수 없/i, message: 'Q&A 항목을 찾을 수 없습니다.', type: 'NOT_FOUND' },
  { pattern: /경쟁사.*찾을 수 없/i, message: '경쟁사 정보를 찾을 수 없습니다.', type: 'NOT_FOUND' },
  { pattern: /스캔.*실행 중/i, message: '스캔이 이미 실행 중입니다. 완료 후 다시 시도해주세요.', type: 'VALIDATION_ERROR' },
  { pattern: /Gemini.*API/i, message: 'AI 서비스에 일시적인 문제가 있습니다. 잠시 후 다시 시도해주세요.', type: 'SERVER_ERROR' },
  { pattern: /Naver.*API/i, message: '네이버 API에 일시적인 문제가 있습니다.', type: 'SERVER_ERROR' },
  { pattern: /중복.*키워드/i, message: '이미 등록된 키워드입니다.', type: 'VALIDATION_ERROR' },
  { pattern: /필수.*입력/i, message: '필수 항목을 모두 입력해주세요.', type: 'VALIDATION_ERROR' },
  { pattern: /잘못된.*형식/i, message: '입력 형식이 올바르지 않습니다.', type: 'VALIDATION_ERROR' },
  { pattern: /AI.*응답.*실패/i, message: 'AI 응답 생성에 실패했습니다. 다시 시도해주세요.', type: 'SERVER_ERROR' },
  { pattern: /검색량.*조회.*실패/i, message: '검색량 조회에 실패했습니다. 잠시 후 다시 시도해주세요.', type: 'SERVER_ERROR' },

  // [안정성 개선] 백엔드 에러 코드 매핑
  { pattern: /DB_CONNECTION_FAILED/i, message: '데이터베이스 연결에 실패했습니다. 서버를 재시작해주세요.', type: 'DATABASE_ERROR' },
  { pattern: /DB_QUERY_FAILED/i, message: '데이터 조회 중 오류가 발생했습니다.', type: 'DATABASE_ERROR' },
  { pattern: /NAVER_API_LIMIT/i, message: 'Naver API 호출 한도를 초과했습니다. 1시간 후 다시 시도해주세요.', type: 'RATE_LIMIT' },
  { pattern: /NAVER_API_ERROR/i, message: 'Naver 서비스가 일시적으로 불안정합니다.', type: 'SERVER_ERROR' },
  { pattern: /SCRAPER_BLOCKED/i, message: '스크래핑이 일시 차단되었습니다. 2-4시간 후 자동 해제됩니다.', type: 'RATE_LIMIT' },
  { pattern: /GEMINI_API_ERROR/i, message: 'AI 서비스가 일시적으로 불안정합니다.', type: 'SERVER_ERROR' },
  { pattern: /RATE_LIMIT_EXCEEDED/i, message: '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.', type: 'RATE_LIMIT' },
]

// HTTP 상태 코드 → 에러 타입 매핑
const STATUS_TO_TYPE: Record<number, ApiErrorType> = {
  400: 'VALIDATION_ERROR',
  401: 'UNAUTHORIZED',
  403: 'FORBIDDEN',
  404: 'NOT_FOUND',
  408: 'TIMEOUT',
  429: 'RATE_LIMIT',
  500: 'SERVER_ERROR',
  502: 'SERVER_ERROR',
  503: 'SERVER_ERROR',
  504: 'TIMEOUT',
}

export interface ParsedError {
  type: ApiErrorType
  userMessage: string
  technicalMessage: string
  statusCode?: number
  config: ErrorConfig
}

/**
 * 에러 타입 판별
 */
export function getErrorType(error: unknown): ApiErrorType {
  if (!error) return 'UNKNOWN'

  // Axios 에러 또는 일반 에러 객체
  const err = error as Record<string, unknown>

  // 네트워크 에러 체크
  if (err.code === 'ERR_NETWORK' || err.message === 'Network Error') {
    return 'NETWORK_ERROR'
  }

  // 타임아웃 체크
  if (err.code === 'ECONNABORTED' || err.code === 'ETIMEDOUT') {
    return 'TIMEOUT'
  }

  // HTTP 상태 코드로 판별
  const status = (err.response as Record<string, unknown>)?.status as number | undefined
  if (status && STATUS_TO_TYPE[status]) {
    return STATUS_TO_TYPE[status]
  }

  // 에러 메시지 패턴으로 판별
  const message = String(err.message || '')
  for (const { pattern, type } of ERROR_PATTERNS) {
    if (pattern.test(message)) {
      return type
    }
  }

  // 서버 에러 상세 메시지 패턴
  const detail = (err.response as Record<string, Record<string, unknown>>)?.data?.detail
  if (typeof detail === 'string') {
    for (const { pattern, type } of ERROR_PATTERNS) {
      if (pattern.test(detail)) {
        return type
      }
    }
  }

  return 'UNKNOWN'
}

/**
 * API 에러를 사용자 친화적인 메시지로 변환
 */
export function parseApiError(error: unknown): ParsedError {
  let technicalMessage = ''
  let statusCode: number | undefined

  // Error 객체에서 정보 추출
  if (error instanceof Error) {
    technicalMessage = error.message
  } else if (typeof error === 'string') {
    technicalMessage = error
  } else if (error && typeof error === 'object') {
    const err = error as Record<string, unknown>

    // Axios 에러 구조
    const response = err.response as Record<string, unknown> | undefined
    const data = response?.data as Record<string, unknown> | undefined

    if (data?.detail) {
      technicalMessage = String(data.detail)
      statusCode = response?.status as number | undefined
    } else if (data?.message) {
      technicalMessage = String(data.message)
      statusCode = response?.status as number | undefined
    } else if (err.message) {
      technicalMessage = String(err.message)
      statusCode = (err.status as number | undefined) || (response?.status as number | undefined)
    }

    // 에러 코드
    if (err.code) {
      const codeMessage = ERROR_MESSAGES[err.code as string]
      if (codeMessage) {
        technicalMessage = technicalMessage || String(err.code)
      }
    }
  }

  // 에러 타입 판별
  const type = getErrorType(error)
  const baseConfig = ERROR_CONFIGS[type]

  // 상태 코드로 메시지 매핑
  let userMessage = baseConfig.message
  if (statusCode && ERROR_MESSAGES[statusCode.toString()]) {
    userMessage = ERROR_MESSAGES[statusCode.toString()]
  }

  // 패턴 매칭으로 더 구체적인 메시지 찾기
  for (const { pattern, message } of ERROR_PATTERNS) {
    if (pattern.test(technicalMessage)) {
      userMessage = message
      break
    }
  }

  // 서버에서 받은 detail 메시지가 있으면 사용
  if (technicalMessage && !userMessage.includes(technicalMessage)) {
    // 기술적 메시지가 사용자에게 보여도 괜찮은지 판단
    const isTechnical = /error|exception|stack|trace|undefined|null/i.test(technicalMessage)
    if (!isTechnical && technicalMessage.length < 100) {
      userMessage = technicalMessage
    }
  }

  return {
    type,
    userMessage,
    technicalMessage: technicalMessage || 'Unknown error',
    statusCode,
    config: { type, ...baseConfig },
  }
}

/**
 * 에러 메시지만 반환 (간단한 사용)
 */
export function getErrorMessage(error: unknown): string {
  return parseApiError(error).userMessage
}

/**
 * Toast용 에러 메시지 (더 간결)
 */
export function getToastErrorMessage(error: unknown, prefix?: string): string {
  const { userMessage } = parseApiError(error)

  // 메시지가 너무 길면 자르기
  const maxLength = 50
  const truncatedMessage = userMessage.length > maxLength
    ? userMessage.substring(0, maxLength) + '...'
    : userMessage

  return prefix ? `${prefix}: ${truncatedMessage}` : truncatedMessage
}

/**
 * 재시도 가능 여부 확인
 */
export function isRetryableError(error: unknown): boolean {
  const { config } = parseApiError(error)
  return config.retryable
}

/**
 * 재시도 지연 시간 반환 (exponential backoff)
 */
export function getRetryDelay(error: unknown, attemptIndex: number): number {
  const { config } = parseApiError(error)
  const baseDelay = config.retryDelay || 2000
  // Exponential backoff with jitter
  const exponentialDelay = baseDelay * Math.pow(2, attemptIndex)
  const jitter = Math.random() * 1000
  return Math.min(exponentialDelay + jitter, 30000) // max 30초
}

/**
 * 최대 재시도 횟수 반환
 */
export function getMaxRetries(error: unknown): number {
  const { config } = parseApiError(error)
  return config.maxRetries || 1
}

/**
 * TanStack Query용 retry 함수
 */
export function queryRetryFn(failureCount: number, error: unknown): boolean {
  if (!isRetryableError(error)) return false
  return failureCount < getMaxRetries(error)
}

/**
 * TanStack Query용 retryDelay 함수
 */
export function queryRetryDelayFn(attemptIndex: number, error: unknown): number {
  return getRetryDelay(error, attemptIndex)
}

/**
 * 에러 심각도에 따른 색상 반환
 */
export function getErrorSeverityColor(severity: ErrorSeverity): string {
  const colors: Record<ErrorSeverity, string> = {
    critical: 'text-red-600 bg-red-50 border-red-200',
    error: 'text-red-500 bg-red-50/50 border-red-200/50',
    warning: 'text-yellow-600 bg-yellow-50 border-yellow-200',
    info: 'text-blue-600 bg-blue-50 border-blue-200',
  }
  return colors[severity]
}

/**
 * 에러 타입에 따른 아이콘 반환
 */
export function getErrorIcon(type: ApiErrorType): string {
  const icons: Record<ApiErrorType, string> = {
    NETWORK_ERROR: '🌐',
    TIMEOUT: '⏱️',
    UNAUTHORIZED: '🔒',
    FORBIDDEN: '⛔',
    NOT_FOUND: '🔍',
    VALIDATION_ERROR: '⚠️',
    SERVER_ERROR: '🔧',
    RATE_LIMIT: '🚦',
    DATABASE_ERROR: '💾',
    UNKNOWN: '❓',
  }
  return icons[type]
}

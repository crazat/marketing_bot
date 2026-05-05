/**
 * [AA7] 프로덕션 로그 가드
 *
 * 개발 환경에서만 console에 출력.
 * 프로덕션은 에러 로깅 시스템 (AA1)으로 전송.
 *
 * 사용:
 *  logger.debug('detail')      — 개발에만
 *  logger.info('status')       — 개발에만
 *  logger.warn('concern')      — 개발 + 프로덕션 (경미)
 *  logger.error('fatal', err)  — 모든 환경 + 에러 큐 전송
 */

const isDev = import.meta.env.DEV

type LogLevel = 'debug' | 'info' | 'warn' | 'error'

interface LogEntry {
  level: LogLevel
  message: string
  args: unknown[]
  timestamp: number
  url: string
  userAgent: string
}

// [AA1과 연동] 에러 큐 — LocalStorage에 저장, 주기 전송
const ERROR_QUEUE_KEY = 'marketing-bot-error-queue-v1'
const MAX_QUEUE_SIZE = 50

function enqueueError(entry: LogEntry) {
  try {
    const raw = localStorage.getItem(ERROR_QUEUE_KEY)
    const arr: LogEntry[] = raw ? JSON.parse(raw) : []
    arr.push(entry)
    // 최신 N개만 유지
    const trimmed = arr.slice(-MAX_QUEUE_SIZE)
    localStorage.setItem(ERROR_QUEUE_KEY, JSON.stringify(trimmed))
  } catch {
    // localStorage 불가 시 무시
  }
}

function format(level: LogLevel, message: string, args: unknown[]): LogEntry {
  return {
    level,
    message,
    args: args.map((a) => {
      if (a instanceof Error) {
        return { name: a.name, message: a.message, stack: a.stack }
      }
      return a
    }),
    timestamp: Date.now(),
    url: typeof window !== 'undefined' ? window.location.href : '',
    userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : '',
  }
}

export const logger = {
  debug(message: string, ...args: unknown[]) {
    if (isDev) {
      console.debug(`[debug]`, message, ...args)
    }
  },
  info(message: string, ...args: unknown[]) {
    if (isDev) {
      console.info(`[info]`, message, ...args)
    }
  },
  warn(message: string, ...args: unknown[]) {
    // 경고는 모든 환경 출력
    console.warn(`[warn]`, message, ...args)
    if (!isDev) {
      enqueueError(format('warn', message, args))
    }
  },
  error(message: string, ...args: unknown[]) {
    // 에러는 모든 환경 출력 + 큐
    // eslint-disable-next-line no-console
    console.error(`[error]`, message, ...args)
    enqueueError(format('error', message, args))
  },
}

export function readErrorQueue(): LogEntry[] {
  try {
    const raw = localStorage.getItem(ERROR_QUEUE_KEY)
    return raw ? (JSON.parse(raw) as LogEntry[]) : []
  } catch {
    return []
  }
}

export function clearErrorQueue(): void {
  try {
    localStorage.removeItem(ERROR_QUEUE_KEY)
  } catch {
    // ignore
  }
}

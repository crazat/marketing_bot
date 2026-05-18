import { readStorageJson, removeStorageItem, writeStorageJson } from './safeStorage'

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

const ERROR_QUEUE_KEY = 'marketing-bot-error-queue-v1'
const MAX_QUEUE_SIZE = 50

function enqueueError(entry: LogEntry) {
  const arr = readStorageJson<LogEntry[]>(ERROR_QUEUE_KEY, [], Array.isArray)
  arr.push(entry)
  writeStorageJson(ERROR_QUEUE_KEY, arr.slice(-MAX_QUEUE_SIZE))
}

function format(level: LogLevel, message: string, args: unknown[]): LogEntry {
  return {
    level,
    message,
    args: args.map((arg) => {
      if (arg instanceof Error) {
        return { name: arg.name, message: arg.message, stack: arg.stack }
      }
      return arg
    }),
    timestamp: Date.now(),
    url: typeof window !== 'undefined' ? window.location.href : '',
    userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : '',
  }
}

export const logger = {
  debug(message: string, ...args: unknown[]) {
    if (isDev) {
      console.debug('[debug]', message, ...args)
    }
  },
  info(message: string, ...args: unknown[]) {
    if (isDev) {
      console.info('[info]', message, ...args)
    }
  },
  warn(message: string, ...args: unknown[]) {
    console.warn('[warn]', message, ...args)
    if (!isDev) {
      enqueueError(format('warn', message, args))
    }
  },
  error(message: string, ...args: unknown[]) {
    console.error('[error]', message, ...args)
    enqueueError(format('error', message, args))
  },
}

export function readErrorQueue(): LogEntry[] {
  return readStorageJson<LogEntry[]>(ERROR_QUEUE_KEY, [], Array.isArray)
}

export function clearErrorQueue(): void {
  removeStorageItem(ERROR_QUEUE_KEY)
}

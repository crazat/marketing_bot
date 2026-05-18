export function safeJsonParse<T>(
  raw: string | null | undefined,
  fallback: T,
  validator?: (value: unknown) => boolean,
): T {
  if (!raw) return fallback

  try {
    const parsed = JSON.parse(raw) as unknown
    if (validator && !validator(parsed)) return fallback
    return parsed as T
  } catch {
    return fallback
  }
}

export function readStorageItem(key: string): string | null {
  if (typeof window === 'undefined') return null

  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeStorageItem(key: string, value: string): boolean {
  if (typeof window === 'undefined') return false

  try {
    window.localStorage.setItem(key, value)
    return true
  } catch {
    return false
  }
}

export function removeStorageItem(key: string): boolean {
  if (typeof window === 'undefined') return false

  try {
    window.localStorage.removeItem(key)
    return true
  } catch {
    return false
  }
}

export function readStorageJson<T>(
  key: string,
  fallback: T,
  validator?: (value: unknown) => boolean,
): T {
  return safeJsonParse(readStorageItem(key), fallback, validator)
}

export function writeStorageJson(key: string, value: unknown): boolean {
  try {
    return writeStorageItem(key, JSON.stringify(value))
  } catch {
    return false
  }
}

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'

type AriaLive = 'polite' | 'assertive' | 'off'

interface Announcement {
  message: string
  politeness: AriaLive
}

interface LiveRegionContextType {
  announce: (message: string, politeness?: AriaLive) => void
}

const LiveRegionContext = createContext<LiveRegionContextType | null>(null)

/**
 * 스크린 리더에게 동적 콘텐츠 변경을 알려주는 Provider
 */
export function LiveRegionProvider({ children }: { children: ReactNode }) {
  const [announcements, setAnnouncements] = useState<Announcement[]>([])

  const announce = useCallback((message: string, politeness: AriaLive = 'polite') => {
    const announcement: Announcement = { message, politeness }
    setAnnouncements((prev) => [...prev, announcement])

    // 일정 시간 후 메시지 제거
    setTimeout(() => {
      setAnnouncements((prev) => prev.filter((a) => a !== announcement))
    }, 1000)
  }, [])

  return (
    <LiveRegionContext.Provider value={{ announce }}>
      {children}
      {/* Polite announcements */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {announcements
          .filter((a) => a.politeness === 'polite')
          .map((a, i) => (
            <span key={i}>{a.message}</span>
          ))}
      </div>
      {/* Assertive announcements */}
      <div
        role="alert"
        aria-live="assertive"
        aria-atomic="true"
        className="sr-only"
      >
        {announcements
          .filter((a) => a.politeness === 'assertive')
          .map((a, i) => (
            <span key={i}>{a.message}</span>
          ))}
      </div>
    </LiveRegionContext.Provider>
  )
}

/**
 * 스크린 리더에 메시지를 알려주는 훅
 */
export function useLiveRegion() {
  const context = useContext(LiveRegionContext)
  if (!context) {
    // Provider가 없는 경우 no-op 반환
    return {
      announce: () => {},
      announcePolite: () => {},
      announceAssertive: () => {},
    }
  }

  return {
    announce: context.announce,
    announcePolite: (message: string) => context.announce(message, 'polite'),
    announceAssertive: (message: string) => context.announce(message, 'assertive'),
  }
}

/**
 * 시각적으로 숨기고 스크린 리더만 읽을 수 있는 컴포넌트
 */
export function VisuallyHidden({ children }: { children: ReactNode }) {
  return (
    <span className="sr-only">
      {children}
    </span>
  )
}

/**
 * 로딩 상태를 스크린 리더에 알려주는 컴포넌트
 */
export function LoadingAnnouncer({
  isLoading,
  loadingMessage = '로딩 중입니다',
  loadedMessage = '로딩이 완료되었습니다',
}: {
  isLoading: boolean
  loadingMessage?: string
  loadedMessage?: string
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy={isLoading}
      className="sr-only"
    >
      {isLoading ? loadingMessage : loadedMessage}
    </div>
  )
}

/**
 * 결과 개수를 스크린 리더에 알려주는 컴포넌트
 */
export function ResultsAnnouncer({
  count,
  itemName = '항목',
  isLoading = false,
}: {
  count: number
  itemName?: string
  isLoading?: boolean
}) {
  if (isLoading) {
    return (
      <div role="status" aria-live="polite" className="sr-only">
        {itemName} 검색 중입니다
      </div>
    )
  }

  return (
    <div role="status" aria-live="polite" className="sr-only">
      {count === 0
        ? `${itemName}이(가) 없습니다`
        : `${count}개의 ${itemName}이(가) 있습니다`}
    </div>
  )
}

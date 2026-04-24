import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@/components/ui/ThemeProvider'
import { ToastProvider } from '@/components/ui/Toast'
import { LiveRegionProvider } from '@/components/ui/LiveRegion'
import { queryRetryFn, queryRetryDelayFn } from '@/utils/errorMessages'
import { installErrorTracking } from '@/lib/errorTracking'
import App from './App'
import './index.css'

// [AA1] 전역 에러 추적 설치 — React 렌더 전 실행
installErrorTracking()

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      // 표준 재시도 로직 적용 (에러 타입별 자동 판단)
      retry: queryRetryFn,
      retryDelay: queryRetryDelayFn,
      // [성능 최적화] 기본 staleTime 1분, 개별 쿼리에서 오버라이드 가능
      staleTime: 60 * 1000, // 1분
      // [EE4] 캐시 보존 — unmount 후 5분까지 유지. 페이지 재진입 시 즉시 복원.
      gcTime: 5 * 60 * 1000, // 5분
      // [EE4] React Query가 AbortController를 자동 생성 → 언마운트 시 진행 중 fetch 취소
      // (axios 어댑터도 signal 전파 지원)
    },
    mutations: {
      // 뮤테이션도 재시도 가능한 에러에 대해 1회 재시도
      retry: (failureCount, error) => {
        return queryRetryFn(failureCount, error) && failureCount < 1
      },
      retryDelay: queryRetryDelayFn,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <ToastProvider>
        <LiveRegionProvider>
          <QueryClientProvider client={queryClient}>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </QueryClientProvider>
        </LiveRegionProvider>
      </ToastProvider>
    </ThemeProvider>
  </React.StrictMode>,
)

// [F1] 서비스 워커 등록 (production 빌드에서만)
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js', { scope: '/' })
      .then((reg) => {
        reg.addEventListener('updatefound', () => {
          const installing = reg.installing
          if (!installing) return
          installing.addEventListener('statechange', () => {
            if (installing.state === 'installed' && navigator.serviceWorker.controller) {
              installing.postMessage({ type: 'SKIP_WAITING' })
            }
          })
        })
      })
      .catch((err) => console.warn('[SW] registration failed', err))
  })
}

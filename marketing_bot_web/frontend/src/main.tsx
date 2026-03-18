import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@/components/ui/ThemeProvider'
import { ToastProvider } from '@/components/ui/Toast'
import { LiveRegionProvider } from '@/components/ui/LiveRegion'
import { queryRetryFn, queryRetryDelayFn } from '@/utils/errorMessages'
import App from './App'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      // 표준 재시도 로직 적용 (에러 타입별 자동 판단)
      retry: queryRetryFn,
      retryDelay: queryRetryDelayFn,
      // [성능 최적화] 기본 staleTime 1분, 개별 쿼리에서 오버라이드 가능
      staleTime: 60 * 1000, // 1분
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

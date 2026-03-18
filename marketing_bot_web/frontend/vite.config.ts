import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import path from 'path'
import compression from 'vite-plugin-compression'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // [성능 최적화] Gzip 압축 - 번들 크기 60-70% 감소
    compression({
      algorithm: 'gzip',
      ext: '.gz',
      threshold: 1024, // 1KB 이상 파일만 압축
      deleteOriginFile: false, // 원본 파일 유지 (폴백용)
    }),
    // [성능 최적화] Brotli 압축 - Gzip보다 15-25% 더 작음
    compression({
      algorithm: 'brotliCompress',
      ext: '.br',
      threshold: 1024,
      deleteOriginFile: false,
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: true,  // 네트워크에 노출 (0.0.0.0)
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    // 프로덕션 빌드 최적화
    target: 'esnext',
    minify: 'esbuild',  // esbuild 사용 (Vite 내장)
    sourcemap: false,   // [성능 최적화] 프로덕션에서 소스맵 제거
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          // [성능 최적화] 더 세밀한 코드 스플리팅
          if (id.includes('node_modules')) {
            // React 핵심
            if (id.includes('react') || id.includes('react-dom') || id.includes('react-router')) {
              return 'react-vendor'
            }
            // 데이터 페칭
            if (id.includes('@tanstack')) {
              return 'query-vendor'
            }
            // 차트
            if (id.includes('recharts') || id.includes('d3')) {
              return 'chart-vendor'
            }
            // 유틸리티
            if (id.includes('date-fns') || id.includes('lodash') || id.includes('axios')) {
              return 'utils-vendor'
            }
            // 아이콘
            if (id.includes('lucide')) {
              return 'icons-vendor'
            }
            // 기타 node_modules
            return 'vendor'
          }
        },
      },
    },
    // chunk 크기 경고 임계값 증가
    chunkSizeWarningLimit: 1000,
    // CSS 코드 분할
    cssCodeSplit: true,
  },
  optimizeDeps: {
    include: ['react', 'react-dom', 'react-router-dom', '@tanstack/react-query'],
  },
})

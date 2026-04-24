/**
 * Marketing Bot Service Worker
 * - 정적 에셋 캐싱 (cache-first)
 * - API 요청은 네트워크 우선, 실패 시 캐시 (GET만)
 * - 새 버전 배포 시 자동 skipWaiting + clientsClaim
 */

const CACHE_VERSION = 'mb-v1'
const STATIC_CACHE = `${CACHE_VERSION}-static`
const API_CACHE = `${CACHE_VERSION}-api`

const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/vite.svg',
  '/manifest.webmanifest',
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) => cache.addAll(STATIC_ASSETS).catch(() => {}))
      .then(() => self.skipWaiting())
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => !k.startsWith(CACHE_VERSION))
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event

  // 비-GET, chrome-extension 등은 우회
  if (request.method !== 'GET' || !request.url.startsWith('http')) return

  const url = new URL(request.url)

  // API 요청: 네트워크 우선, 실패 시 캐시 (단, 민감 엔드포인트는 캐시 금지)
  if (url.pathname.startsWith('/api/')) {
    if (
      url.pathname.includes('/generate-comment') ||
      url.pathname.includes('/action') ||
      url.pathname.includes('/verify-batch/start') ||
      url.pathname.includes('/scan')
    ) {
      return // 네트워크만 사용
    }

    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone()
          caches.open(API_CACHE).then((c) => c.put(request, copy).catch(() => {}))
          return res
        })
        .catch(() => caches.match(request))
    )
    return
  }

  // 정적 에셋: 캐시 우선, 없으면 네트워크
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached
      return fetch(request)
        .then((res) => {
          if (res && res.status === 200 && res.type === 'basic') {
            const copy = res.clone()
            caches.open(STATIC_CACHE).then((c) => c.put(request, copy).catch(() => {}))
          }
          return res
        })
        .catch(() => caches.match('/index.html'))
    })
  )
})

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting()
  }
})

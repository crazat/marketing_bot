/**
 * Marketing Bot Service Worker
 * - Cache static assets with a cache-first strategy.
 * - Never cache API responses; protected API GETs may contain sensitive data.
 * - Activate new deployments immediately.
 */

const CACHE_VERSION = 'mb-v3'
const STATIC_CACHE = `${CACHE_VERSION}-static`

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
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => !key.startsWith(CACHE_VERSION))
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event

  if (request.method !== 'GET' || !request.url.startsWith('http')) return

  const url = new URL(request.url)

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request))
    return
  }

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200 && response.type === 'basic') {
            const copy = response.clone()
            caches.open(STATIC_CACHE).then((cache) => cache.put('/index.html', copy).catch(() => {}))
          }
          return response
        })
        .catch(() => caches.match('/index.html')),
    )
    return
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached
      return fetch(request)
        .then((response) => {
          if (response && response.status === 200 && response.type === 'basic') {
            const copy = response.clone()
            caches.open(STATIC_CACHE).then((cache) => cache.put(request, copy).catch(() => {}))
          }
          return response
        })
        .catch(() => cached || Response.error())
    }),
  )
})

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting()
  }
})

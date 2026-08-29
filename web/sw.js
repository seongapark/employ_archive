const CACHE = 'forecast-v1';

const SHELL_ASSETS = [
  './',
  './index.html',
  './css/styles.css',
  './js/app.js',
  './js/data.js',
  './js/screens/home.js',
  './js/screens/org.js',
  './js/screens/compare.js',
  './js/screens/timeline.js',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names.filter((name) => name !== CACHE).map((name) => caches.delete(name))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  if (url.pathname.includes('/data/')) {
    // 데이터: network-first, 실패 시 캐시(오프라인 시 마지막 수신본 표시)
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // 앱 셸: cache-first
  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request))
  );
});

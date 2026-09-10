const CACHE = 'ask-v1';

const SHELL_ASSETS = [
  './',
  './index.html',
  './core/tokens.css',
  './core/base.css',
  './css/ask.css',
  './js/ask.js',
  './js/lookup.js',
  './js/badge.js',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
];

// ── 캐시 전략: network-first, 앱 셸만 (WHY) ─────────────────────────────
// domains/forecast/app/sw.js 와 같은 전략이다. 항상 최신 코드를 먼저 받고
// (버전 상수를 수동으로 올릴 필요가 없다), 오프라인일 때만 캐시로 폴백한다.
//
// `/api/` 는 절대 캐시하지 않는다 — 질의응답은 항상 최신 근거로 답해야 하고,
// 오래된 카드를 오프라인에서 재생하면 "왜 못 주는지" 가 그날의 사실과 달라진다.
// Worker 는 GitHub Pages 와 다른 오리진(*.workers.dev)이므로 sameOrigin 가드가
// 이미 걸러내지만, 의도를 코드로도 남겨 둔다.
// ─────────────────────────────────────────────────────────────────────

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      cache.addAll(SHELL_ASSETS.map((u) => new Request(u, { cache: 'reload' })))
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((name) => name !== CACHE).map((name) => caches.delete(name)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;               // 질의(POST /api/ask)는 손대지 않는다
  if (new URL(request.url).pathname.includes('/api/')) return; // 명시적으로도 캐시하지 않는다

  event.respondWith(
    fetch(request, { cache: 'no-cache' })
      .then((response) => {
        const sameOrigin = new URL(request.url).origin === self.location.origin;
        if (response.ok && sameOrigin) {
          const copy = response.clone();
          event.waitUntil(caches.open(CACHE).then((cache) => cache.put(request, copy)));
        }
        return response;
      })
      .catch(() => caches.match(request))
  );
});

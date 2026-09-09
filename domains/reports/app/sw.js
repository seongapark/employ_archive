const CACHE = 'reports-v1';

const SHELL_ASSETS = [
  './',
  './index.html',
  './core/tokens.css',
  './core/base.css',
  './core/shell.js',
  './css/app.css',
  './js/app.js',
  './js/data.js',
  './js/ui.js',
  './js/search.js',
  './js/screens/home.js',
  './js/screens/topics.js',
  './js/screens/orgs.js',
  './js/screens/report.js',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
];

// ── 캐시 전략: network-first ────────────────────────────────────────────
// cache-first 로 두면 CACHE 상수를 수동으로 올리지 않는 한 배포해도 사용자에게
// 새 코드가 영원히 안 간다. 게다가 ES 모듈 그래프가 신구 버전으로 섞이면
// import 오류로 빈 화면이 된다. 이 파일을 cache-first 로 "최적화"하지 말 것 —
// 다른 도메인 앱에서 실제로 그 사고가 났다.
// ───────────────────────────────────────────────────────────────────────

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
      Promise.all(names.filter((n) => n !== CACHE).map((n) => caches.delete(n)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
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

const CACHE = 'forecast-v1';

const SHELL_ASSETS = [
  './',
  './index.html',
  './core/tokens.css',
  './core/base.css',
  './core/shell.js',
  './css/app.css',
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

// ── 캐시 전략: network-first (WHY) ──────────────────────────────────────
// 과거에는 앱 셸을 cache-first로 서빙했다. 이 방식은 두 가지 실패를 낳았다.
// 1) CACHE 상수를 수동으로 올리지 않으면 코드가 바뀌어도 사용자에게 절대
//    전달되지 않는다 — 배포해도 앱이 영구히 예전 버전에 머무른다.
// 2) precache/fetch가 브라우저 HTTP 캐시를 그대로 거치기 때문에, 캐시를
//    새로 채우는 순간에도 일부 파일만 예전 버전으로 섞여 들어올 수 있다.
//    ES 모듈 그래프의 import/export가 신구 버전 파일로 뒤섞이면 import
//    오류로 앱이 빈 화면이 되는 사고가 로컬에서 재현되었고, GitHub Pages의
//    max-age=600 캐시 헤더 아래서도 같은 문제가 발생할 수 있다.
// 그래서 shell/data 구분 없이 모든 GET 요청을 network-first로 통일했다.
// 온라인이면 항상 최신 코드를 받고(버전 상수를 올릴 필요가 없다),
// 오프라인일 때만 마지막으로 저장된 캐시로 폴백한다.
// 이 파일을 다시 cache-first로 "최적화"하지 말 것 — 위 두 결함이 재발한다.
// ─────────────────────────────────────────────────────────────────────

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      // HTTP 캐시를 우회해 항상 origin에서 신선한 파일을 받는다.
      // (브라우저 HTTP 캐시를 거치면 신구 버전이 섞여 들어올 수 있다.)
      cache.addAll(SHELL_ASSETS.map((u) => new Request(u, { cache: 'reload' })))
    )
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

  // network-first with revalidation: 항상 최신본을 먼저 시도하고,
  // 성공하면 캐시를 갱신한 뒤 그대로 반환한다. 네트워크 실패(오프라인) 시에만
  // 마지막으로 저장된 캐시로 폴백한다. 캐시도 없으면 그대로 실패시킨다.
  event.respondWith(
    fetch(request, { cache: 'no-cache' })
      .then((response) => {
        // 캐시에는 우리 오리진의 정상 응답(2xx 상태 코드가 있는 것)만 저장한다.
        // - 실패 응답(404 등)을 캐시하면 다음 오프라인 접속 때 그 실패가 그대로 재생된다.
        // - 크로스오리진/opaque 응답(Google Fonts 등)은 상태를 읽을 수 없고 용량만 차지한다.
        // - 206(Range 응답)은 cache.put이 던지므로 반드시 걸러야 한다.
        const sameOrigin = new URL(request.url).origin === self.location.origin;
        if (response.ok && sameOrigin) {
          const copy = response.clone();
          // 응답은 즉시 반환하고, 캐시 저장은 waitUntil로 SW가 살아있는 동안 완료시킨다.
          event.waitUntil(caches.open(CACHE).then((cache) => cache.put(request, copy)));
        }
        return response;
      })
      .catch(() => caches.match(request))
  );
});

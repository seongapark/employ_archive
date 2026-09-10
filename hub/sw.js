// 허브의 서비스워커. **앞서 이 자리에 있던 '구 서비스워커 폐기용' 을 대체한다.**
//
// 지난 사정: 리팩터 전 배포본은 이 URL(/employ_archive/sw.js)에 전망 앱의
// 서비스워커를 스코프 '/' 로 등록해 두었다. 그 등록이 남아 있으면 허브와 모든
// 도메인 요청을 계속 가로채고 옛 앱 셸을 오프라인 캐시로 물고 있는다. 그래서
// 한동안 이 파일은 자기를 해제하고 캐시를 비우기만 했다.
//
// **그 일을 이 파일이 그대로 물려받는다.** 브라우저는 기존 등록이 있으면 이 URL 의
// 업데이트를 확인하므로, **옛 등록은 이 스크립트로 갈아탄다** — 옛 워커가 요청을
// 가로채는 일은 그 순간 끝난다. 그게 폐기의 핵심이고, 남은 옛 캐시는 아무도
// 열지 않는 죽은 바이트라 그대로 둔다.
// **이 파일을 지우지 말 것** — 지우면 404 가 되어 옛 등록이 그대로 살아남는다.
//
// **남의 캐시를 지우지 않는다.** 처음엔 activate 에서 자기 것 말고 전부 지웠는데,
// 브라우저로 확인해 보니 도메인 앱들의 캐시(ask-v1 등)까지 매번 날아갔다 —
// 허브를 한 번 열 때마다 다섯 앱의 오프라인 지원이 사라진다. 우리 것(hub-) 중
// 옛 버전만 지운다.

const CACHE = 'hub-v1';

const SHELL_ASSETS = [
  './',
  './index.html',
  './core/tokens.css',
  './core/base.css',
  './css/hub.css',
  './js/hub.js',
  './js/state.js',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
];

// **허브 것만 가로챈다.** 이 워커의 스코프는 사이트 전체(/employ_archive/)라
// 도메인 앱 요청까지 지나간다. 도메인마다 자기 워커가 있고 그쪽 스코프가 더
// 좁아 우선하지만, 여기서 남의 파일까지 캐시하면 옛 사고가 되풀이된다 —
// 허브 자신의 경로만 다룬다.
const 허브것 = (path) => {
  const rel = path.replace(/^.*\/employ_archive/, '');
  if (rel === '' || rel === '/' || rel === '/index.html') return true;
  return /^\/(css|js|core|icons)\//.test(rel) || rel === '/manifest.webmanifest';
};

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      cache.addAll(SHELL_ASSETS.map((u) => new Request(u, { cache: 'reload' })))
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    // **우리 것 중 옛 버전만** 지운다. 도메인 앱 캐시는 그 앱 워커의 것이다.
    const names = await caches.keys();
    await Promise.all(names
      .filter((n) => n.startsWith('hub-') && n !== CACHE)
      .map((n) => caches.delete(n)));
    await self.clients.claim();
  })());
});

// network-first. 항상 최신 코드를 먼저 받고(버전 상수를 손으로 올릴 일이 없다),
// 오프라인일 때만 캐시로 떨어진다. 도메인 앱들과 같은 전략이다.
self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;   // 워커 API 등 남의 오리진은 손대지 않는다
  if (!허브것(url.pathname)) return;                  // 도메인 앱은 자기 워커에 맡긴다

  event.respondWith(
    fetch(request, { cache: 'no-cache' })
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          event.waitUntil(caches.open(CACHE).then((cache) => cache.put(request, copy)));
        }
        return response;
      })
      .catch(() => caches.match(request))
  );
});

// 관리자 화면 전용 워커. **오프라인이 목적이 아니다 — 신선도가 목적이다.**
//
// 왜 있나: GitHub Pages 가 HTML 과 JS 에 똑같이 `Cache-Control: max-age=600` 을
// 붙이고, 둘은 **따로따로** 만료된다. 그래서 배포 직후 10분 동안 "새 HTML + 옛 JS"
// 같은 어중간한 상태가 나온다. 실제로 새로 넣은 탭바가 HTML 에는 있는데 옛 JS 가
// 숨긴 채로 둬서 화면이 안 바뀐 것처럼 보인 적이 있다(2026-09-12, 그날만 세 번).
//
// 다른 앱 다섯은 각자 워커가 network-first 라 이 문제를 안 겪는다. 허브 워커는
// 스코프가 `/employ_archive/` 로 넓지만 `허브것()` 이 `/admin/` 을 일부러 안 잡아
// 통과시킨다 — 그래서 이 화면만 사이트에서 유일하게 보호가 없었다.
//
// **캐시를 하나도 만들지 않는다.** 늘 네트워크로 가서 재검증만 한다. 관리자 화면은
// 오프라인에서 볼 물건이 아니므로 저장할 이유가 없고, 저장하지 않으면 캐시 이름을
// 관리할 일도 없다 — 이 저장소는 워커가 **남의 앱 캐시를 지워** 다섯 앱의 오프라인이
// 매번 날아간 사고를 겪었다. 지울 캐시가 아예 없으면 그 사고가 재현될 수 없다.

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;                  // 집계 요청(POST)은 손대지 않는다
  if (new URL(request.url).origin !== self.location.origin) return;  // 워커 API 는 남의 오리진이다
  // `no-cache` 는 "캐시를 쓰지 마라"가 아니라 "쓰기 전에 서버에 물어라"다 —
  // 바뀐 게 없으면 304 라 비용도 거의 없고, 바뀌었으면 즉시 새것이 온다.
  event.respondWith(fetch(request, { cache: 'no-cache' }));
});

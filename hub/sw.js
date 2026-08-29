// 구 서비스워커 폐기용.
//
// 리팩터 전 배포본은 이 URL(/employ_archive/sw.js)에 전망 앱의 서비스워커를
// 스코프 '/'로 등록해 두었다. 그 등록이 남아 있으면 허브와 모든 도메인 요청을
// 계속 가로채고 옛 앱 셸을 오프라인 캐시로 물고 있는다.
//
// 브라우저는 기존 등록이 있으면 다음 방문 때 이 URL의 업데이트를 확인하므로,
// 자기를 해제하고 캐시를 비우는 이 파일을 올려두면 옛 등록이 스스로 정리된다.
// 각 도메인 앱은 자기 폴더 아래 자기 서비스워커를 따로 갖는다.
//
// 이 파일은 지우지 말 것 — 지우면 404가 되어 옛 등록이 그대로 살아남는다.

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.map((name) => caches.delete(name)));
    await self.registration.unregister();
    const clients = await self.clients.matchAll({ type: 'window' });
    for (const client of clients) client.navigate(client.url);
  })());
});

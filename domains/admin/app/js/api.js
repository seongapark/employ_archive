// 워커와 말하는 곳. 배포 뒤 아래 주소를 실제 workers.dev 주소로 바꾼다
// (domains/admin/DEPLOY.md). core/track.js 의 ENDPOINT 도 같이 바꿔야 한다.
export const API = 'https://employ-archive-metrics.seongapark92.workers.dev/api/stats';

import { 도메인목록 } from './model.js';

// 도메인 현황이 읽는 last_run.json 은 워커가 아니라 **같은 사이트의 상대
// 경로**다 — admin 은 /employ_archive/admin/ 에서 돌고 데이터는
// /employ_archive/<도메인>/data/ 에 있다(tools/build.py 가 그렇게 조립한다).
// 절대경로를 박으면 배포 경로 접두사가 바뀔 때마다 깨진다.
//
// 하나가 404 여도(그 도메인 배포가 아직 안 끝났거나, 자동 수집이 한 번도
// 안 돈 경우) 나머지는 보여야 한다 — Promise.all 에 실패를 흘리지 않고
// 도메인별로 각자 잡는다.
export async function 현황불러오기({ fetch, 목록 = 도메인목록 } = {}) {
  const f = fetch || globalThis.fetch.bind(globalThis);
  const 결과 = {};
  await Promise.all(목록.map(async (키) => {
    try {
      const res = await f(`../${키}/data/last_run.json`);
      결과[키] = res.ok ? await res.json() : null;
    } catch {
      결과[키] = null;
    }
  }));
  return 결과;
}

const 키 = 'ea:token';
const 제외키 = 'ea:off';

// 배포가 안 끝난 것과 네트워크가 죽은 것은 다른 사실이다 — 앞은 사람이 할 일이
// 남은 것이고 뒤는 잠시 뒤 다시다. 뭉개면 배포 미완료를 장애로 읽는다.
export const 미배포 = (url = API) => url.includes('REPLACE-AFTER-DEPLOY');

export const 토큰읽기 = (store) => store.getItem(키);
export const 토큰쓰기 = (store, v) => store.setItem(키, v);
export const 토큰지우기 = (store) => store.removeItem(키);

export const 제외상태 = (store) => store.getItem(제외키) === '1';
export const 제외설정 = (store, on) =>
  (on ? store.setItem(제외키, '1') : store.removeItem(제외키));

export async function 불러오기(days, { fetch, store, url = API } = {}) {
  const token = 토큰읽기(store);
  if (!token) return { 상태: '인증', 통계: null };
  if (미배포(url)) return { 상태: '미배포', 통계: null };
  try {
    const res = await fetch(`${url}?days=${days}`,
      { headers: { authorization: `Bearer ${token}` } });
    if (res.status === 401) {
      토큰지우기(store);
      return { 상태: '인증', 통계: null };
    }
    if (!res.ok) return { 상태: '연결실패', 통계: null };
    return { 상태: 'ok', 통계: await res.json() };
  } catch {
    return { 상태: '연결실패', 통계: null };
  }
}

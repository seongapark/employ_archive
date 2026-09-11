// 워커와 말하는 곳. 배포 뒤 아래 주소를 실제 workers.dev 주소로 바꾼다
// (domains/admin/DEPLOY.md). core/track.js 의 ENDPOINT 도 같이 바꿔야 한다.
export const API = 'https://REPLACE-AFTER-DEPLOY.workers.dev/api/stats';

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

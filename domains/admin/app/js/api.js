// 워커와 말하는 곳. 배포 뒤 아래 주소를 실제 workers.dev 주소로 바꾼다
// (domains/admin/DEPLOY.md). core/track.js 의 ENDPOINT 도 같이 바꿔야 한다.
export const API = 'https://employ-archive-metrics.seongapark92.workers.dev/api/stats';

const 키 = 'ea:token';
const 등록키 = 'ea:owner';

// 배포가 안 끝난 것과 네트워크가 죽은 것은 다른 사실이다 — 앞은 사람이 할 일이
// 남은 것이고 뒤는 잠시 뒤 다시다. 뭉개면 배포 미완료를 장애로 읽는다.
export const 미배포 = (url = API) => url.includes('REPLACE-AFTER-DEPLOY');

export const 토큰읽기 = (store) => store.getItem(키);
export const 토큰쓰기 = (store, v) => store.setItem(키, v);
export const 토큰지우기 = (store) => store.removeItem(키);

// stats 와 다른 경로일 뿐 같은 워커다. 주소를 또 하나 따로 적으면 배포 때
// 한쪽만 고치는 사고가 난다(이 저장소가 DEPLOY.md 에서 이미 겪었다) — 그래서
// API 상수에서 경로만 바꿔 쓴다.
const OWNER = API.replace('/api/stats', '/api/owner');

export const 등록됐나 = (store) => store.getItem(등록키) === '1';

// 도구 영역이 보여줄 문장을 정한다. `ea:owner` 표식이 있으면 이미 등록을
// 마친 것이고, `ea:v` 가 없으면 이 브라우저가 도메인 앱을 한 번도 안 열어
// 애초에 뺄 방문자가 없다는 뜻이다. 둘 다 아니면(v 는 있는데 아직 못
// 등록했다 — 첫 시도 전이거나 지난 시도가 실패했다) 화면이 그 사실을 따로
// 말해야 한다(그렇지 않으면 두 서로 다른 사실이 같은 문장으로 뭉개진다).
export function 주인상태(store) {
  if (등록됐나(store)) return '등록됨';
  return store.getItem('ea:v') ? '보류' : '없음';
}

// 이 브라우저의 방문자 id 를 주인으로 등록한다. **한 번만 보낸다** — 표식이
// 있으면 조회할 때마다 D1 에 쓰지 않도록 곧장 돌아간다. 등록이 실패해도
// 던지지 않는다 — "통계 기능이 화면을 못 건드린다"는 이 프로젝트의 불변식이
// 관리자 화면에도 그대로 적용된다.
export async function 주인등록(store, { fetch, url = OWNER } = {}) {
  if (등록됐나(store)) return;
  const v = store.getItem('ea:v');
  if (!v) return;
  const token = 토큰읽기(store);
  if (!token) return;
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      body: JSON.stringify({ v }),
    });
    if (res.ok) store.setItem(등록키, '1');
  } catch {
    // 네트워크가 죽어도 화면은 그대로 그려진다 — 다음 조회 때 다시 시도한다.
  }
}

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

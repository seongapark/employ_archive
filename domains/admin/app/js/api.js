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

// 도구 영역이 보여줄 문장을 정한다. 두 가지뿐이다 — 등록을 마쳤거나, 아직
// 못 했거나. `ea:v` 가 없어서 못 하는 경우는 없앴다: 등록할 때 없으면 만든다.
export function 주인상태(store) {
  return 등록됐나(store) ? '등록됨' : '보류';
}

// 이 브라우저가 사이트를 한 번도 안 열었으면 `ea:v` 가 없다 — 관리자 화면에는
// 비콘이 안 붙어 있기 때문이다. 그때 **여기서 만들어 둔다.**
//
// 안 만들고 그냥 돌아가면 구멍이 생긴다: 관리자 화면만 먼저 연 기기(예: 노트북)는
// 등록될 것이 없어 지나가고, **나중에 그 기기로 사이트를 둘러보는 순간** 비콘이
// 새 id 를 만들어 남처럼 세어진다. 그 뒤로는 관리자 화면을 다시 열기 전까지
// 계속 세어진다 — 사용자가 "옵션이 아니라 기본으로" 빼 달라고 한 것과 어긋난다.
//
// 여기서 미리 만들어 두면 비콘이 나중에 `아이디()` 로 **같은 값을 그대로 쓰므로**,
// 그 기기의 첫 방문부터 이미 제외 목록에 있다.
function 방문자아이디(store) {
  try {
    let v = store.getItem('ea:v');
    if (!v) {
      v = crypto.randomUUID();
      store.setItem('ea:v', v);
    }
    return v;
  } catch {
    return null;   // 저장소가 막힌 브라우저 — 등록할 수도, 셀 수도 없다
  }
}

// 이 브라우저의 방문자 id 를 주인으로 등록한다. **한 번만 보낸다** — 표식이
// 있으면 조회할 때마다 D1 에 쓰지 않도록 곧장 돌아간다. 등록이 실패해도
// 던지지 않는다 — "통계 기능이 화면을 못 건드린다"는 이 프로젝트의 불변식이
// 관리자 화면에도 그대로 적용된다.
export async function 주인등록(store, { fetch, url = OWNER } = {}) {
  if (등록됐나(store)) return;
  const v = 방문자아이디(store);
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

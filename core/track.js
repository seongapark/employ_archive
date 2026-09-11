// 방문 비콘. 여섯 앱(허브 + 도메인 다섯)이 이 파일 하나를 공유한다 —
// tools/build.py 가 core/ 를 각 앱 폴더로 복사하기 때문이다.
//
// **불변식 하나: 통계가 화면을 못 건드린다.** 모든 경로가 try/catch 안에서 끝나고,
// 실패해도 다시 시도하지 않는다. 저장소가 막힌 브라우저에서도 던지지 않는다.

export const ENDPOINT = 'https://REPLACE-AFTER-DEPLOY.workers.dev/api/hit';

// 숫자를 품은 세그먼트는 값으로 본다. 라우트 이름(overview, industry, sex)에는
// 숫자가 없고 값(산업코드, 연도, 보고서 id)에는 있다 — 이 비대칭이 근거다.
// 언젠가 `/top10` 같은 라우트 이름이 생기면 예외 한 줄을 더한다.
export function 경로정규화(hash) {
  const segs = String(hash ?? '').replace(/^#/, '').split('/').filter(Boolean).slice(0, 4);
  if (!segs.length) return '/';
  return `/${segs.map((s) => (/\d/.test(s) ? ':id' : s)).join('/')}`;
}

// 호스트만 남긴다. 검색어(쿼리)는 안 가져간다 — 우리가 쓸 데도 없으면서 남의 것이다.
// 같은 사이트면 null 이다: 내부 이동은 유입이 아니다.
export function 유입호스트(referrer, here) {
  try {
    if (!referrer) return null;
    const u = new URL(referrer);
    if (u.host === here) return null;
    return u.host.replace(/^www\./, '');
  } catch {
    return null;
  }
}

export function 보낼까(win) {
  try {
    if (win.localStorage.getItem('ea:off') === '1') return false;
  } catch {
    // 저장소가 막혀 있으면 제외 스위치도 없는 것이다 — 막지 않는다.
  }
  const h = win.location.hostname;
  return h !== 'localhost' && h !== '127.0.0.1' && h !== '';
}

// 저장소가 막힌 브라우저에서도 ID 는 있어야 한다. 모듈 수명 동안만 사는 값으로
// 떨어지고, 그 방문은 늘 신규로 잡힌다(설계 §11).
const 메모리 = {};
function 아이디(store, key) {
  try {
    let v = store.getItem(key);
    if (!v) {
      v = crypto.randomUUID();
      store.setItem(key, v);
    }
    return v;
  } catch {
    메모리[key] = 메모리[key] ?? crypto.randomUUID();
    return 메모리[key];
  }
}

export function 페이로드(win, 도메인) {
  return {
    d: 도메인,
    p: 경로정규화(win.location.hash),
    r: 유입호스트(win.document.referrer, win.location.host),
    v: 아이디(win.localStorage, 'ea:v'),
    s: 아이디(win.sessionStorage, 'ea:s'),
    m: win.matchMedia?.('(display-mode: standalone)')?.matches ? 'standalone' : 'browser',
  };
}

// ── 부팅 ────────────────────────────────────────────────────────────────
// **모듈 스크립트에서 `document.currentScript` 는 null 이다.** 그걸로 읽으면 도메인이
// 전부 undefined 가 되고, 비콘은 실패해도 조용하니 몇 주 뒤에야 눈치챈다.
// 반드시 선택자로 찾는다.
//
// `typeof document` 가드가 있어야 node --test 가 이 파일을 import 할 수 있다.
if (typeof document !== 'undefined') {
  const 도메인 = document.querySelector('script[data-track-domain]')?.dataset.trackDomain;
  let 직전 = null;

  const 보내기 = () => {
    // 정체를 모르는 줄을 쌓느니 안 쌓는다.
    if (!도메인 || !보낼까(window)) return;
    const p = 페이로드(window, 도메인);
    if (p.p === 직전) return;   // 뒤로가기 연타·라우터 재진입
    직전 = p.p;
    try {
      const body = JSON.stringify(p);
      // 문자열로 보내면 text/plain 이라 preflight 가 안 붙는다. Blob 에
      // application/json 을 씌우면 왕복이 하나 는다.
      if (navigator.sendBeacon) navigator.sendBeacon(ENDPOINT, body);
      else fetch(ENDPOINT, { method: 'POST', body, keepalive: true, mode: 'no-cors' });
    } catch {
      /* 통계가 화면을 못 건드린다 */
    }
  };

  보내기();
  window.addEventListener('hashchange', 보내기);
}

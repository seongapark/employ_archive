// 방문 비콘. 여섯 앱(허브 + 도메인 다섯)이 이 파일 하나를 공유한다 —
// tools/build.py 가 core/ 를 각 앱 폴더로 복사하기 때문이다.
//
// **불변식 하나: 통계가 화면을 못 건드린다.** 모든 경로가 try/catch 안에서 끝나고,
// 실패해도 다시 시도하지 않는다. 저장소가 막힌 브라우저에서도 던지지 않는다.

export const ENDPOINT = 'https://employ-archive-metrics.seongapark92.workers.dev/api/hit';

// 숫자를 품은 세그먼트는 값으로 본다. 라우트 이름(overview, industry, sex)에는
// 숫자가 없고 값(산업코드, 연도, 보고서 id)에는 있다 — 이 비대칭이 근거다.
// 언젠가 `/top10` 같은 라우트 이름이 생기면 예외 한 줄을 더한다.
//
// `key=value` 모양의 세그먼트(질의응답의 `#/q=검색어`)는 따로 다룬다. 값에 숫자가
// 섞여 있는지는 우연이라 방어선이 못 된다 — 영문 검색어는 숫자가 없어 그대로
// 새어 나간다. 그래서 `=` 가 있으면 무조건 키만 남기고 값은 버린다: "검색
// 화면이 쓰였다"는 남기되 "무엇을 검색했는지"는 안 남긴다(design §4.3).
const 세그먼트접기 = (s) => {
  const eq = s.indexOf('=');
  if (eq >= 0) return `${s.slice(0, eq)}=:id`;
  return /\d/.test(s) ? ':id' : s;
};

export function 경로정규화(hash) {
  const segs = String(hash ?? '').replace(/^#/, '').split('/').filter(Boolean).slice(0, 4);
  if (!segs.length) return '/';
  return `/${segs.map(세그먼트접기).join('/')}`;
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

// `?.` 는 matchMedia 가 '없는' 경우만 막지 '호출이 던지는' 경우는 못 막는다
// (예: 일부 임베디드 웹뷰). 저장소·유입호스트와 같은 급으로 여기도 자체
// try/catch 로 막아 둔다 — 페이로드() 를 어디서 부르든 던지지 않아야 한다.
function 표시모드(win) {
  try {
    return win.matchMedia?.('(display-mode: standalone)')?.matches ? 'standalone' : 'browser';
  } catch {
    return 'browser';
  }
}

export function 페이로드(win, 도메인) {
  return {
    d: 도메인,
    p: 경로정규화(win.location.hash),
    r: 유입호스트(win.document.referrer, win.location.host),
    v: 아이디(win.localStorage, 'ea:v'),
    s: 아이디(win.sessionStorage, 'ea:s'),
    m: 표시모드(win),
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

  // 페이로드() 호출까지 통째로 try 안에 둔다 — matchMedia 처럼 없는 경우가
  // 아니라 '호출 자체가 던지는' API 가 하나라도 있으면(옵셔널 체이닝 `?.` 은
  // 이걸 못 막는다) 이 함수 전체가 이 파일의 불변식을 어기게 된다.
  const 보내기 = () => {
    try {
      // 정체를 모르는 줄을 쌓느니 안 쌓는다.
      if (!도메인 || !보낼까(window)) return;
      const p = 페이로드(window, 도메인);
      if (p.p === 직전) return;   // 뒤로가기 연타·라우터 재진입
      직전 = p.p;
      const body = JSON.stringify(p);
      // 문자열로 보내면 text/plain 이라 preflight 가 안 붙는다. Blob 에
      // application/json 을 씌우면 왕복이 하나 는다.
      if (navigator.sendBeacon) navigator.sendBeacon(ENDPOINT, body);
      else fetch(ENDPOINT, { method: 'POST', body, keepalive: true, mode: 'no-cors' });
    } catch {
      /* 통계가 화면을 못 건드린다 */
    }
  };

  // 리스너를 최초 전송보다 먼저 등록한다 — 최초 보내기() 가 (위 try 로 막아도
  // 혹시 모를 다른 이유로) 실행을 끝까지 못 마치면 그 아래 줄이 영영 실행되지
  // 않아 세션 내내 비콘이 통째로 죽는다. 등록을 먼저 해 두면 첫 전송이
  // 어떻게 되든 이후 화면 전환은 계속 잡힌다 — 예외를 막는 방어와 예외가
  // 있어도 기능이 남게 하는 방어, 둘 다 있어야 한다.
  window.addEventListener('hashchange', 보내기);
  보내기();
}

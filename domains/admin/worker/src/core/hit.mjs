// 들어온 비콘 한 건을 `hit` 표 한 줄로 바꾸는 순수 함수들. D1 도 Request 도 모른다.
//
// 원칙 하나: **클라이언트가 보낸 값을 그대로 믿지 않는다.** 도메인은 화이트리스트로
// 막고, 표시모드는 아는 값이 아니면 접고, 기기·유입종류·국가는 서버가 직접 채운다.

export const DOMAINS = ['hub', 'employment', 'press', 'forecast', 'reports', 'ask'];

const BOT = /bot|crawl|spider|slurp|headless|preview|monitor|curl|wget|python-requests|facebookexternalhit|lighthouse|pagespeed/i;

// 비콘이라 JS 를 안 돌리는 크롤러는 애초에 안 들어온다. 이건 그 위의 두 번째 겹이고,
// **자칭 봇만** 거른다 — UA 를 감추면 못 거른다(설계 §11).
export const isBot = (ua) => !ua || BOT.test(String(ua));

// 워커는 UTC 로 돈다. 저장 시점에 KST 로 접어 둬야 (1) 집계가 day 인덱스를 타고
// (2) "오늘" 이 한국 오늘이 된다. 설계 §5.4.
export const kstDay = (nowMs) =>
  new Date(nowMs + 9 * 60 * 60 * 1000).toISOString().slice(0, 10);

// `(^|\.)이름\.` 로 맞춘다. `이름` 으로 시작만 해도 맞히면 googleblog.com 이
// 검색 유입이 된다 — 점을 요구하면 라벨 경계가 지켜진다.
const SEARCH = /(^|\.)(google|naver|daum|bing|duckduckgo|yahoo|ecosia|zum)\./;
const SOCIAL = /(^|\.)(x|twitter|facebook|instagram|threads|linkedin|reddit|youtube|kakao)\./;

export function refKind(host) {
  if (!host) return 'direct';
  const h = String(host);
  if (h === 't.co') return 'social';        // 라벨이 둘뿐이라 위 규칙에 안 걸린다
  if (SEARCH.test(h)) return 'search';
  if (SOCIAL.test(h)) return 'social';
  return 'link';
}

// Android 태블릿은 UA 에 `Mobile` 이 없다 — 그 하나로 폰과 갈린다.
export function deviceOf(ua) {
  const s = String(ua ?? '');
  if (/iPad|Tablet|PlayBook|Silk|Android(?!.*Mobile)/i.test(s)) return 'tablet';
  if (/Mobi|Android|iPhone|iPod|Windows Phone/i.test(s)) return 'mobile';
  return 'desktop';
}

// index.mjs 의 /api/owner 도 방문자 id 검증에 이 규칙을 그대로 쓴다 — 비콘의
// visitor 검증과 다른 모양을 허용하면 owner.visitor 가 hit.visitor 와 안 맞는
// 값을 받아들일 수 있다.
export const 문자열 = (v, max) =>
  (typeof v === 'string' && v.length > 0 && v.length <= max ? v : null);

export function 정규화(body, { ua, country, nowMs }) {
  const domain = 문자열(body?.d, 20);
  if (!DOMAINS.includes(domain)) return null;

  const visitor = 문자열(body?.v, 64);
  const session = 문자열(body?.s, 64);
  if (!visitor || !session) return null;

  const ref = 문자열(body?.r, 120);
  return {
    ts: new Date(nowMs).toISOString().slice(0, 19) + 'Z',
    day: kstDay(nowMs),
    domain,
    path: 문자열(body?.p, 120) ?? '/',
    visitor,
    session,
    ref,
    ref_kind: refKind(ref),
    mode: body?.m === 'standalone' ? 'standalone' : 'browser',
    device: deviceOf(ua),
    country: 문자열(country, 2),
  };
}

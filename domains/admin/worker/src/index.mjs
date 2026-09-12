import { d1 } from './core/db.mjs';
import { isBot, 정규화, kstDay, 문자열 } from './core/hit.mjs';
import { 기록 } from './core/write.mjs';
import { 통계 } from './core/stats.mjs';

const cors = (env) => ({
  'access-control-allow-origin': env.ALLOWED_ORIGIN,
  'access-control-allow-headers': 'content-type, authorization',
  'access-control-allow-methods': 'GET, POST, OPTIONS',
});

const json = (body, env, status = 200) =>
  new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json; charset=utf-8', ...cors(env) } });

// 비콘은 **항상 204** 다. 저장했는지 거부했는지 알려주지 않는다 — 클라이언트가
// 재시도할 일이 없고, 어디서 걸렸는지 알려 주면 우회하는 법을 같이 알려 주는 셈이다.
const 조용히 = (env) => new Response(null, { status: 204, headers: cors(env) });

async function 수집(request, env) {
  if (request.headers.get('origin') !== env.ALLOWED_ORIGIN) return 조용히(env);
  const ua = request.headers.get('user-agent');
  if (isBot(ua)) return 조용히(env);

  // sendBeacon 은 문자열을 text/plain 으로 보낸다(preflight 를 피하려고 일부러
  // 그렇게 보낸다) — request.json() 이 아니라 text() 로 받아 우리가 파싱한다.
  let body = null;
  try { body = JSON.parse(await request.text()); } catch { return 조용히(env); }

  const row = 정규화(body, {
    ua, country: request.cf?.country ?? null, nowMs: Date.now() });
  if (!row) return 조용히(env);

  // 통계가 죽어도 방문자에게는 조용하다(응답은 그대로 204) — 하지만 우리에게까지
  // 조용하면 "왜 0 이지"를 진단할 수단이 없다. wrangler tail 에 한 줄 남겨 둔다.
  try { await 기록(d1(env.DB), row); } catch (e) { console.error('기록 실패', e); }
  return 조용히(env);
}

// 길이를 먼저 맞추고 전 바이트를 XOR 로 훑는다. `a === b` 는 앞에서 갈리면 일찍
// 끝나 비교 시간이 답을 흘린다. 개인 사이트라 현실적 위협은 작지만, 잠금이
// 여기 하나뿐이라 싸게 막을 수 있는 것은 막는다.
function 같은토큰(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

// /api/stats 와 /api/owner 가 같은 인증을 쓴다 — 복사해 두면 한쪽만 고치다 잠금이
// 어긋나는 사고가 난다. `env.METRICS_TOKEN` 이 비어 있으면(secret 을 안 넣은 배포)
// 무슨 토큰을 보내도 거부한다 — 아래 index.test.mjs 가 이 가드를 지킨다.
function 인증됨(request, env) {
  const auth = request.headers.get('authorization') ?? '';
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : null;
  return Boolean(env.METRICS_TOKEN) && 같은토큰(token, env.METRICS_TOKEN);
}

// 허용 목록으로 접는다 — 음수나 NaN 이 그대로 들어가면 창 계산이 뒤집힌다.
//
// **숫자 모양인지 먼저 본다.** `Number(null)` 도 `Number('')` 도 0 인데 0 은
// 허용 목록의 유효값(전 기간)이라, 그냥 Number() 로 접으면 days 를 아예 안 보낸
// 요청과 `?days=` 빈 값이 전 기간으로 잘못 해석된다.
const 허용일수 = new Set([0, 7, 30, 90]);
const 일수읽기 = (v) => {
  if (typeof v !== 'string' || !/^\d+$/.test(v)) return 30;
  const n = Number(v);
  return 허용일수.has(n) ? n : 30;
};

async function 집계(request, env, url) {
  if (!인증됨(request, env)) return json({ 오류: '인증' }, env, 401);
  try {
    return json(await 통계(d1(env.DB), 일수읽기(url.searchParams.get('days')),
      kstDay(Date.now())), env);
  } catch {
    return json({ 오류: '집계 실패' }, env, 500);
  }
}

// 주인(관리자 비밀번호로 들어온 기기) 등록. /api/stats 와 같은 Bearer 인증을
// 요구한다 — 아무나 자기 기기를 주인으로 올려 통계를 가릴 수 있으면 이 기능
// 자체가 구멍이 된다.
//
// 방문자 id 검증은 hit.mjs 의 비콘 규칙과 같은 문자열(1~64자) 규칙을 그대로
// 쓴다 — 다른 모양을 허용하면 owner.visitor 가 hit.visitor 와 안 맞는 값을
// 받아들일 수 있다. 인증까지 통과한 뒤의 실수라 401 처럼 정체를 숨길 이유가
// 없으므로 400 으로 사유를 그대로 알린다.
async function 주인등록(request, env) {
  if (!인증됨(request, env)) return json({ 오류: '인증' }, env, 401);
  let body = null;
  try { body = JSON.parse(await request.text()); } catch { return json({ 오류: '잘못된 요청' }, env, 400); }
  const visitor = 문자열(body?.v, 64);
  if (!visitor) return json({ 오류: '잘못된 요청' }, env, 400);
  await d1(env.DB).run(
    'INSERT OR IGNORE INTO owner (visitor, added) VALUES (?, ?)',
    [visitor, kstDay(Date.now())]);
  return json({ ok: true }, env);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return new Response(null, { headers: cors(env) });
    if (url.pathname === '/api/health') return json({ ok: true }, env);
    if (url.pathname === '/api/hit' && request.method === 'POST') return 수집(request, env);
    if (url.pathname === '/api/stats' && request.method === 'GET')
      return 집계(request, env, url);
    if (url.pathname === '/api/owner' && request.method === 'POST')
      return 주인등록(request, env);
    return json({ 오류: '없는 경로' }, env, 404);
  },
};

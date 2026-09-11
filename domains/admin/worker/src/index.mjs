import { d1 } from './core/db.mjs';
import { isBot, 정규화, kstDay } from './core/hit.mjs';
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

  try { await 기록(d1(env.DB), row); } catch { /* 통계가 죽어도 조용하다 */ }
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

// 허용 목록으로 접는다 — 음수나 NaN 이 그대로 들어가면 창 계산이 뒤집힌다.
// v 가 없을 때(파라미터를 아예 안 줬을 때) 를 먼저 가려야 한다 — 안 그러면
// Number(null) 이 0 이 되어 "생략" 이 "전 기간(days=0)" 과 같아져 버린다.
const 허용일수 = new Set([0, 7, 30, 90]);
const 일수읽기 = (v) => {
  if (v === null) return 30;
  const n = Number(v);
  return 허용일수.has(n) ? n : 30;
};

async function 집계(request, env, url) {
  const auth = request.headers.get('authorization') ?? '';
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : null;
  if (!env.METRICS_TOKEN || !같은토큰(token, env.METRICS_TOKEN)) {
    return json({ 오류: '인증' }, env, 401);
  }
  try {
    return json(await 통계(d1(env.DB), 일수읽기(url.searchParams.get('days')),
      kstDay(Date.now())), env);
  } catch {
    return json({ 오류: '집계 실패' }, env, 500);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return new Response(null, { headers: cors(env) });
    if (url.pathname === '/api/health') return json({ ok: true }, env);
    if (url.pathname === '/api/hit' && request.method === 'POST') return 수집(request, env);
    if (url.pathname === '/api/stats' && request.method === 'GET')
      return 집계(request, env, url);
    return json({ 오류: '없는 경로' }, env, 404);
  },
};

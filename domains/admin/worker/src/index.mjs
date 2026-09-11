import { d1 } from './core/db.mjs';
import { isBot, 정규화 } from './core/hit.mjs';
import { 기록 } from './core/write.mjs';

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

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return new Response(null, { headers: cors(env) });
    if (url.pathname === '/api/health') return json({ ok: true }, env);
    if (url.pathname === '/api/hit' && request.method === 'POST') return 수집(request, env);
    return json({ 오류: '없는 경로' }, env, 404);
  },
};

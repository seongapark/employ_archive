import { d1 } from './core/db.mjs';
import { makeLlm } from './llm/openrouter.mjs';
import { handleAsk } from './api/routes.mjs';
import { route as routeSlots } from './core/route.mjs';

const cors = (env) => ({
  'access-control-allow-origin': env.ASK_ALLOWED_ORIGIN,
  'access-control-allow-headers': 'content-type',
  'access-control-allow-methods': 'POST, OPTIONS',
});
const json = (body, env, status = 200) =>
  new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json; charset=utf-8', ...cors(env) } });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return new Response(null, { headers: cors(env) });
    if (url.pathname === '/api/health') return json({ ok: true }, env);
    if (url.pathname !== '/api/ask' || request.method !== 'POST')
      return json({ error: 'not found' }, env, 404);

    try {
      const body = await request.json().catch(() => ({}));
      const deps = {
        db: d1(env.DB),
        kv: env.QUOTA,
        quota: Number(env.ASK_DAILY_QUOTA ?? 30),
        // OPENROUTER_API_KEY 는 wrangler secret 으로만 들어온다 — 여기서도 값 자체는
        // 절대 리터럴로 쓰지 않고 env 를 통해서만 읽는다.
        llm: makeLlm({ apiKey: env.OPENROUTER_API_KEY, model: env.ASK_MODEL }),
      };
      const ip = request.headers.get('cf-connecting-ip') ?? '0.0.0.0';
      const today = new Date().toISOString().slice(0, 10);

      const 카드 = await handleAsk(deps, {
        질문: body.q, 유형: body.유형, 슬롯: body.슬롯, ip, today });

      // 후속질문도 route 를 태워 가능·부분만 남긴다 — 눌렀을 때 "못 합니다" 가 나오면 배신이다
      const 후보 = 카드.후속질문 ?? [];
      카드.후속질문 = [];
      for (const s of 후보) {
        const r = await routeSlots(deps, 카드.슬롯 ?? {});
        if (r.가능.length || r.부분.length) 카드.후속질문.push(s);
      }
      return json(카드, env);
    } catch {
      // handleAsk·route·D1·KV 어디서든 미처리 예외가 올라올 수 있다 — classify/compose
      // 예외·검증실패·한도초과는 전부 안에서 막혀 있지만, 여기가 마지막 방어선이다.
      // raw exception 을 그대로 흘리면 CORS 헤더도 JSON 도 없는 원시 오류가 나가
      // 화면(fetch)이 아예 파싱하지 못한다 — 최소한의 JSON 으로 응답한다.
      return json({ 오류: true, 답변: null }, env, 500);
    }
  },
};

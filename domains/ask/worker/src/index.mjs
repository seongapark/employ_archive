import { d1 } from './core/db.mjs';
import { makeLlm } from './llm/openrouter.mjs';
import { handleAsk } from './api/routes.mjs';

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

      // 후속질문은 **거르지 않고 그대로 낸다.**
      //
      // 스펙 §6 은 "route 를 태워 가능·부분만" 이라 적었고 여기에 그런 루프가 있었지만,
      // 그 루프는 매 반복 **같은 입력**(카드.슬롯)으로 route 를 다시 돌아 전부 남기거나
      // 전부 버리는 이분법이었다 — 후속질문 하나하나를 판정하는 게 아니라 D1 왕복만
      // N 배로 늘렸다. 계획 문서의 결함이지 구현의 실수가 아니다.
      //
      // **후속질문은 자연어 문자열이라 슬롯이 없다.** 문자열마다 제대로 필터하려면
      // 1패스(LLM 슬롯 분해)가 또 필요하고, 그건 할당량과 지연을 후속질문 개수만큼
      // 곱한다. 그래서 지금은 그대로 낸다 — 아무 일도 안 하면서 D1 을 N 번 때리는
      // 코드보다 없는 편이 정직하다. 스펙 §6 도 이 동작에 맞게 고쳤다.
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

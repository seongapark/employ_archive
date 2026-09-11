import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker from '../../worker/src/index.mjs';
import { 열린DB } from './fixtures/sqlitedb.mjs';

const ORIGIN = 'https://seongapark.github.io';
const CHROME = 'Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/140 Safari/537.36';

// 실물 D1 바인딩 모양(prepare().bind().all()/run())을 진짜 SQLite 위에 씌운다.
function 바인딩(raw) {
  return {
    prepare: (sql) => ({
      bind: (...params) => ({
        all: async () => ({ results: raw.prepare(sql).all(...params) }),
        run: async () => { raw.prepare(sql).run(...params); },
      }),
    }),
  };
}

function 환경() {
  const { raw } = 열린DB();
  return { env: { DB: 바인딩(raw), ALLOWED_ORIGIN: ORIGIN, METRICS_TOKEN: 'secret' }, raw };
}

// **`new Request(url, { cf })` 는 cf 를 안 들고 있다** — node 의 Request 는 모르는
// init 항목을 조용히 버려서, 그대로 쓰면 request.cf 가 undefined 이고 국가 테스트가
// 통과할 수 없다(실제로 돌려 확인했다). Cloudflare 런타임이 붙여 주는 속성이므로
// 여기서는 직접 붙인다.
const 비콘 = (body, { origin = ORIGIN, ua = CHROME, country = 'KR' } = {}) => {
  const req = new Request('https://m.workers.dev/api/hit', {
    method: 'POST',
    headers: { origin, 'user-agent': ua, 'cf-connecting-ip': '1.2.3.4' },
    body: JSON.stringify(body),
  });
  Object.defineProperty(req, 'cf', { value: { country } });
  return req;
};

const 몸통 = { d: 'employment', p: '/overview', v: 'v1', s: 's1', m: 'browser' };

test('정상 비콘은 줄을 쌓고 204 를 낸다', async () => {
  const { env, raw } = 환경();
  const res = await worker.fetch(비콘(몸통), env);
  assert.equal(res.status, 204);
  assert.equal(raw.prepare('SELECT COUNT(*) n FROM hit').get().n, 1);
});

// 거부 사유를 알려 주면 우회하는 법을 같이 알려 주는 셈이다. 셋 다 204 로 같다.
test('봇·남의 오리진·엉터리 몸통도 전부 204 이고 아무것도 안 쌓는다', async () => {
  for (const [이름, req] of [
    ['봇', 비콘(몸통, { ua: 'Googlebot/2.1' })],
    ['남의 오리진', 비콘(몸통, { origin: 'https://evil.example' })],
    ['모르는 도메인', 비콘({ ...몸통, d: 'admin' })],
  ]) {
    const { env, raw } = 환경();
    const res = await worker.fetch(req, env);
    assert.equal(res.status, 204, 이름);
    assert.equal(raw.prepare('SELECT COUNT(*) n FROM hit').get().n, 0, 이름);
  }
});

test('JSON 이 아닌 몸통에도 안 죽는다', async () => {
  const { env } = 환경();
  const res = await worker.fetch(new Request('https://m.workers.dev/api/hit', {
    method: 'POST', headers: { origin: ORIGIN, 'user-agent': CHROME }, body: '깨진몸통',
  }), env);
  assert.equal(res.status, 204);
});

test('국가는 cf 에서 온다', async () => {
  const { env, raw } = 환경();
  await worker.fetch(비콘(몸통, { country: 'JP' }), env);
  assert.equal(raw.prepare('SELECT country FROM hit').get().country, 'JP');
});

test('health 는 토큰 없이 열려 있다', async () => {
  const { env } = 환경();
  const res = await worker.fetch(new Request('https://m.workers.dev/api/health'), env);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { ok: true });
});

test('모르는 경로는 404 다', async () => {
  const { env } = 환경();
  const res = await worker.fetch(new Request('https://m.workers.dev/nope'), env);
  assert.equal(res.status, 404);
});

test('OPTIONS 에 CORS 헤더를 낸다', async () => {
  const { env } = 환경();
  const res = await worker.fetch(new Request('https://m.workers.dev/api/hit',
    { method: 'OPTIONS', headers: { origin: ORIGIN } }), env);
  assert.equal(res.headers.get('access-control-allow-origin'), ORIGIN);
});

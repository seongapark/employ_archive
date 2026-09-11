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

// token 을 생략하면(기존 테스트 전부) 'secret' 그대로다. null 을 넘기면
// METRICS_TOKEN 키 자체를 안 만든다 — secret 을 아예 안 넣은 배포(undefined)를
// 흉내 낸다.
function 환경(token = 'secret') {
  const { raw } = 열린DB();
  const env = { DB: 바인딩(raw), ALLOWED_ORIGIN: ORIGIN };
  if (token !== null) env.METRICS_TOKEN = token;
  return { env, raw };
}

// D1 자체가 장애일 때(네트워크·용량·일시적 5xx 등) 를 흉내 낸다. run() 에서
// 던지게 해 실제 장애에 가까운 자리(쓰기 시점)를 고른다.
function 깨진바인딩() {
  return {
    prepare: () => ({
      bind: () => ({
        all: async () => { throw new Error('D1 장애'); },
        run: async () => { throw new Error('D1 장애'); },
      }),
    }),
  };
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

// **통계가 다른 것을 못 건드린다** 가 이 설계의 불변식이다 — D1 이 죽어도 비콘을
// 보낸 페이지는 아무 것도 몰라야 한다. index.mjs 의 `try { await 기록(...) } catch {}`
// 가 그 마지막 방어선이고, 이 테스트가 그 방어선을 지킨다. 나중에 누가 그 catch 를
// 지우거나 기록()을 await 밖으로 옮기면(예: 응답을 먼저 보내고 나서야 실행되게
// 바꾸면) 여기서 예외가 워커 밖으로 새어 나가 잡아낸다.
test('D1 이 죽어도 204 가 나가고 예외가 새어 나오지 않는다', async () => {
  const env = { DB: 깨진바인딩(), ALLOWED_ORIGIN: ORIGIN, METRICS_TOKEN: 'secret' };
  const 응답 = worker.fetch(비콘(몸통), env);
  await assert.doesNotReject(응답);
  const res = await 응답;
  assert.equal(res.status, 204);
});

const 통계요청 = (token, qs = '?days=30') =>
  new Request(`https://m.workers.dev/api/stats${qs}`, {
    headers: token ? { origin: ORIGIN, authorization: `Bearer ${token}` } : { origin: ORIGIN },
  });

// 끝에 공백을 붙인 토큰('secret ')은 여기 없다 — WHATWG Headers 가 값의 앞뒤
// 공백을 정규화해서 버리므로 그런 값은 애초에 서버에 도달하지 않는다(직접 확인:
// `{ authorization: 'Bearer secret ' }` 로 만든 Request 의 headers.get() 이 이미
// "Bearer secret"). 브라우저도 Workers 도 같은 명세라 실제 클라이언트가 이 값을
// 보내는 시나리오 자체가 성립하지 않는다 — 다시 넣지 마라.
test('토큰이 없거나 틀리면 401 이고 숫자가 한 톨도 안 나간다', async () => {
  // 'secretx' 는 올바른 토큰을 접두사로 품은 더 긴 값이다 — 누가 비교를
  // startsWith 로 바꾸는 사고를 잡는다.
  for (const t of [null, '', 'wrong', 'secretx', 'SECRET']) {
    const { env } = 환경();
    const res = await worker.fetch(통계요청(t), env);
    assert.equal(res.status, 401, String(t));
    assert.deepEqual(await res.json(), { 오류: '인증' });
  }
});

test('맞는 토큰이면 집계를 낸다', async () => {
  const { env } = 환경();
  await worker.fetch(비콘(몸통), env);
  const res = await worker.fetch(통계요청('secret'), env);
  assert.equal(res.status, 200);
  const s = await res.json();
  assert.equal(s.요약.조회, 1);
  assert.equal(s.도메인[0].도메인, 'employment');
});

// days 를 그대로 믿으면 음수·NaN 이 창 계산을 뒤집는다.
test('days 를 허용 목록으로 접는다', async () => {
  const { env } = 환경();
  for (const [qs, 일수] of [['?days=7', 7], ['?days=0', 0], ['', 30],
    ['?days=-5', 30], ['?days=abc', 30], ['?days=9999', 30], ['?days=', 30]]) {
    const res = await worker.fetch(통계요청('secret', qs), env);
    assert.equal((await res.json()).기간.일수, 일수, qs);
  }
});

// `같은토큰('', '')` 은 길이가 같고(0) XOR 루프가 한 번도 안 돌아 diff 가 그대로
// 0 이라 true 를 낸다. 그래서 `if (!env.METRICS_TOKEN || !같은토큰(...))` 에서
// **앞의 `!env.METRICS_TOKEN` 가드가 사실상 유일한 방어선**이다 — 이 가드가
// 없어지거나 `||` 의 순서가 바뀌면, secret 을 안 넣은 배포(wrangler secret put 을
// 빠뜨린 경우, env.METRICS_TOKEN 이 '' 이거나 아예 undefined)가 아무 토큰에나
// 통계를 통째로 내주게 된다. 이 저장소는 ask 배포에서 절차를 하나 빠뜨리는 사고를
// 이미 겪었으므로, 이 보증은 테스트로 묶어 둔다.
test('METRICS_TOKEN 을 안 넣은 배포는 무슨 토큰을 보내도 401 이다', async () => {
  for (const 시크릿 of ['', null]) {
    const { env } = 환경(시크릿);
    for (const t of [null, '']) {
      const res = await worker.fetch(통계요청(t), env);
      assert.equal(res.status, 401,
        `METRICS_TOKEN=${JSON.stringify(env.METRICS_TOKEN)} token=${JSON.stringify(t)}`);
      assert.deepEqual(await res.json(), { 오류: '인증' });
    }
  }
});

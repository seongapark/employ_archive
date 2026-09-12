import { test } from 'node:test';
import assert from 'node:assert/strict';
import { 불러오기, 미배포, 주인등록, 주인상태, 현황불러오기 } from '../../app/js/api.js';

const 저장소 = (seed = {}) => {
  const m = new Map(Object.entries(seed));
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k), _m: m };
};

test('토큰이 없으면 부르지도 않는다', async () => {
  let 불렀나 = false;
  const r = await 불러오기(30, { fetch: async () => { 불렀나 = true; }, store: 저장소() });
  assert.equal(r.상태, '인증');
  assert.equal(불렀나, false);
});

// 배포가 안 끝난 것과 네트워크가 죽은 것은 다른 사실이다. ask 에서 이 구분이 없어
// 배포 미완료를 네트워크 장애로 읽은 적이 있다(domains/ask/DEPLOY.md).
test('엔드포인트가 자리표시자면 미배포라고 말한다', () => {
  assert.equal(미배포('https://REPLACE-AFTER-DEPLOY.workers.dev/api/stats'), true);
  assert.equal(미배포('https://employ-archive-metrics.x.workers.dev/api/stats'), false);
});

// 아래 세 테스트는 "fetch 가 실제로 어떻게 분기하는가"만 본다 — 그래서 url 을
// 명시적으로 넘긴다. 기본값(API 상수)에 기대지 않는 이유는, 그 값이 배포 전후로
// 바뀌는 **코드 바깥의 사실**이기 때문이다. 실제로 2026-09-12 배포로 그 상수가
// 자리표시자에서 실제 주소가 되면서 기본값에 기대던 테스트가 저 혼자 빨개졌다.
const 배포됨 = 'https://employ-archive-metrics.x.workers.dev/api/stats';

test('401 이면 저장한 토큰을 지운다', async () => {
  const store = 저장소({ 'ea:token': '틀린값' });
  const r = await 불러오기(30, {
    fetch: async () => ({ ok: false, status: 401, json: async () => ({ 오류: '인증' }) }),
    store, url: 배포됨 });
  assert.equal(r.상태, '인증');
  assert.equal(store.getItem('ea:token'), null);
});

test('네트워크 실패는 연결실패다', async () => {
  const store = 저장소({ 'ea:token': 'secret' });
  const r = await 불러오기(30, { fetch: async () => { throw new Error('offline'); },
    store, url: 배포됨 });
  assert.equal(r.상태, '연결실패');
});

test('성공하면 통계를 그대로 준다', async () => {
  const store = 저장소({ 'ea:token': 'secret' });
  let 받은 = null;
  const r = await 불러오기(7, {
    fetch: async (url, opt) => { 받은 = { url, opt };
      return { ok: true, status: 200, json: async () => ({ 요약: { 조회: 3 } }) }; },
    store, url: 배포됨 });
  assert.equal(r.상태, 'ok');
  assert.equal(r.통계.요약.조회, 3);
  assert.match(받은.url, /days=7/);
  assert.equal(받은.opt.headers.authorization, 'Bearer secret');
});

// 토큰 검사 뒤, fetch 를 부르기 전에 미배포() 가 가로챈다는 것 자체를 확인한다.
// 이 순서가 깨지면 배포가 안 끝난 상태가 "서버에 연결하지 못했다" 로 잘못 보인다 —
// ask 도메인에서 실제로 겪은 혼동이다.
//
// **자리표시자 URL 을 명시적으로 넘긴다.** 예전에는 `url` 을 생략해 기본 상수(`API`)가
// 자리표시자라는 데 기댔는데, 2026-09-12 배포로 그 상수가 실제 주소가 되면서 이 테스트가
// 저 혼자 빨개졌다. 전제를 코드 바깥(배포 상태)에 두면 테스트가 배포 한 번에 무너진다.
test('자리표시자 url 이면 fetch 없이 미배포다', async () => {
  const store = 저장소({ 'ea:token': 'secret' });
  let 불렀나 = false;
  const r = await 불러오기(30, {
    fetch: async () => { 불렀나 = true; },
    store,
    url: 'https://REPLACE-AFTER-DEPLOY.workers.dev/api/stats',
  });
  assert.equal(r.상태, '미배포');
  assert.equal(불렀나, false);
});

// 도메인 현황은 워커가 아니라 같은 사이트의 상대경로에서 정적 JSON 을
// 읽는다 — 절대경로를 박으면 배포 경로 접두사가 바뀔 때마다 깨진다.
test('현황불러오기는 상대경로로 도메인별 JSON 을 읽는다', async () => {
  const 본요청 = [];
  const fetch = async (url) => {
    본요청.push(url);
    return { ok: true, json: async () => ({ run_at: 'x' }) };
  };
  const 결과 = await 현황불러오기({ fetch, 목록: ['employment', 'reports'] });
  assert.deepEqual(본요청.sort(), ['../employment/data/last_run.json', '../reports/data/last_run.json']);
  assert.deepEqual(결과.employment, { run_at: 'x' });
  assert.deepEqual(결과.reports, { run_at: 'x' });
});

// 하나가 404 여도(그 도메인 배포가 안 끝났거나 자동 수집이 한 번도 안 돈
// 경우) 나머지는 그대로 보여야 한다 — 하나가 없다고 전체가 죽으면 안 된다.
test('한 도메인이 404 여도 다른 도메인은 그대로 온다', async () => {
  const fetch = async (url) => {
    if (url.includes('press')) return { ok: false, status: 404 };
    return { ok: true, json: async () => ({ run_at: 'x' }) };
  };
  const 결과 = await 현황불러오기({ fetch, 목록: ['press', 'ask'] });
  assert.equal(결과.press, null);
  assert.deepEqual(결과.ask, { run_at: 'x' });
});

test('네트워크 예외도 그 도메인만 null 로 처리하고 나머지는 살린다', async () => {
  const fetch = async (url) => {
    if (url.includes('forecast')) throw new Error('offline');
    return { ok: true, json: async () => ({ run_at: 'x' }) };
  };
  const 결과 = await 현황불러오기({ fetch, 목록: ['forecast', 'ask'] });
  assert.equal(결과.forecast, null);
  assert.deepEqual(결과.ask, { run_at: 'x' });
});

// 주인 등록 — 관리자 화면이 집계를 성공적으로 받은 뒤 자동으로 시도한다.
const 등록됨 = 'https://employ-archive-metrics.x.workers.dev/api/owner';

test('ea:owner 표식이 있으면 다시 보내지 않는다', async () => {
  const store = 저장소({ 'ea:owner': '1', 'ea:v': 'v1', 'ea:token': 'secret' });
  let 불렀나 = false;
  await 주인등록(store, { fetch: async () => { 불렀나 = true; }, url: 등록됨 });
  assert.equal(불렀나, false);
});

// 관리자 화면만 먼저 연 기기(예: 노트북)는 ea:v 가 없다 — 이 화면엔 비콘이 없다.
// 그냥 돌아가면 그 기기가 **나중에** 사이트를 둘러보는 순간 새 id 로 남처럼 세어지고,
// 관리자 화면을 다시 열기 전까지 계속 세어진다. 그래서 여기서 만들어 등록해 둔다 —
// 비콘이 나중에 같은 값을 그대로 쓰므로 첫 방문부터 제외된다.
test('ea:v 가 없으면 만들어서 등록한다', async () => {
  const store = 저장소({ 'ea:token': 'secret' });
  let 받은 = null;
  await 주인등록(store, {
    fetch: async (url, opt) => { 받은 = opt; return { ok: true, status: 200 }; },
    url: 등록됨 });
  const 만든id = store.getItem('ea:v');
  assert.ok(만든id, 'ea:v 를 안 만들었다');
  assert.deepEqual(JSON.parse(받은.body), { v: 만든id }, '만든 id 를 그대로 보내야 한다');
  assert.equal(store.getItem('ea:owner'), '1');
});

test('이미 있는 ea:v 는 새로 만들지 않고 그대로 쓴다', async () => {
  const store = 저장소({ 'ea:token': 'secret', 'ea:v': '원래값' });
  let 받은 = null;
  await 주인등록(store, {
    fetch: async (url, opt) => { 받은 = opt; return { ok: true, status: 200 }; },
    url: 등록됨 });
  assert.equal(store.getItem('ea:v'), '원래값');
  assert.deepEqual(JSON.parse(받은.body), { v: '원래값' });
});

test('토큰이 없으면 보내지 않는다', async () => {
  const store = 저장소({ 'ea:v': 'v1' });
  let 불렀나 = false;
  await 주인등록(store, { fetch: async () => { 불렀나 = true; }, url: 등록됨 });
  assert.equal(불렀나, false);
});

test('처음이면 ea:v 를 보내고 성공하면 표식을 남긴다', async () => {
  const store = 저장소({ 'ea:v': 'v1', 'ea:token': 'secret' });
  let 받은 = null;
  await 주인등록(store, {
    fetch: async (url, opt) => { 받은 = { url, opt }; return { ok: true, status: 200 }; },
    url: 등록됨,
  });
  assert.equal(받은.url, 등록됨);
  assert.equal(받은.opt.headers.authorization, 'Bearer secret');
  assert.deepEqual(JSON.parse(받은.opt.body), { v: 'v1' });
  assert.equal(store.getItem('ea:owner'), '1');
});

test('실패해도 던지지 않고 표식을 남기지 않는다 — 다음에 다시 시도한다', async () => {
  const store = 저장소({ 'ea:v': 'v1', 'ea:token': 'secret' });
  await assert.doesNotReject(주인등록(store,
    { fetch: async () => { throw new Error('offline'); }, url: 등록됨 }));
  assert.equal(store.getItem('ea:owner'), null);
});

test('서버가 200 이 아니면(예: 401) 표식을 남기지 않는다', async () => {
  const store = 저장소({ 'ea:v': 'v1', 'ea:token': 'secret' });
  await 주인등록(store, { fetch: async () => ({ ok: false, status: 401 }), url: 등록됨 });
  assert.equal(store.getItem('ea:owner'), null);
});

// 상태는 둘뿐이다. 'ea:v 가 없어서 등록 못 함' 은 없앴다 — 없으면 만들기 때문이다.
test('주인상태는 등록됨과 보류 둘이다', () => {
  assert.equal(주인상태(저장소({ 'ea:owner': '1' })), '등록됨');
  assert.equal(주인상태(저장소()), '보류');
  assert.equal(주인상태(저장소({ 'ea:v': 'v1' })), '보류');
});

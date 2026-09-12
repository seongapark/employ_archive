import { test } from 'node:test';
import assert from 'node:assert/strict';
import { 불러오기, 미배포, 주인등록, 주인상태 } from '../../app/js/api.js';

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

// 아래 세 테스트는 "배포가 끝난 뒤 fetch 가 실제로 어떻게 분기하는가"만 본다 —
// 그래서 자리표시자가 아닌 url 을 명시한다. 기본값(API 상수)은 아직 자리표시자라
// 그걸 그대로 넘기면 fetch 를 부르기도 전에 미배포() 사전 검사에 걸리는 게
// 맞다 — 그 사전 검사 자체는 바로 아래 별도 테스트에서 확인한다.
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

// 주인 등록 — 관리자 화면이 집계를 성공적으로 받은 뒤 자동으로 시도한다.
const 등록됨 = 'https://employ-archive-metrics.x.workers.dev/api/owner';

test('ea:owner 표식이 있으면 다시 보내지 않는다', async () => {
  const store = 저장소({ 'ea:owner': '1', 'ea:v': 'v1', 'ea:token': 'secret' });
  let 불렀나 = false;
  await 주인등록(store, { fetch: async () => { 불렀나 = true; }, url: 등록됨 });
  assert.equal(불렀나, false);
});

test('ea:v 가 없으면 뺄 방문자가 없으니 보내지 않는다', async () => {
  const store = 저장소({ 'ea:token': 'secret' });
  let 불렀나 = false;
  await 주인등록(store, { fetch: async () => { 불렀나 = true; }, url: 등록됨 });
  assert.equal(불렀나, false);
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

test('주인상태는 등록됨·없음·보류 셋을 구분한다', () => {
  assert.equal(주인상태(저장소({ 'ea:owner': '1' })), '등록됨');
  assert.equal(주인상태(저장소()), '없음');
  assert.equal(주인상태(저장소({ 'ea:v': 'v1' })), '보류');
});

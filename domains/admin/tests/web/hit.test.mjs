import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isBot, kstDay, refKind, deviceOf, 정규화, DOMAINS } from '../../worker/src/core/hit.mjs';

const CHROME = 'Mozilla/5.0 (Macintosh) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36';
const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) AppleWebKit/605.1 Mobile/15E148 Safari/604.1';

test('자칭 봇과 빈 UA 를 거른다', () => {
  assert.equal(isBot('Googlebot/2.1'), true);
  assert.equal(isBot('HeadlessChrome/140'), true);
  assert.equal(isBot('python-requests/2.32'), true);
  assert.equal(isBot(''), true);
  assert.equal(isBot(null), true);
  assert.equal(isBot(CHROME), false);
});

// 워커는 UTC 로 돈다. 이 경계가 틀리면 한국 자정~오전 9시 조회가 전날로 붙는다.
test('KST 날짜는 UTC 15:00 에 넘어간다', () => {
  assert.equal(kstDay(Date.parse('2026-09-11T14:59:59Z')), '2026-09-11');
  assert.equal(kstDay(Date.parse('2026-09-11T15:00:00Z')), '2026-09-12');
});

test('유입을 네 갈래로 나눈다', () => {
  assert.equal(refKind(null), 'direct');
  assert.equal(refKind('google.com'), 'search');
  assert.equal(refKind('search.naver.com'), 'search');
  assert.equal(refKind('x.com'), 'social');
  assert.equal(refKind('t.co'), 'social');
  assert.equal(refKind('somebody.tistory.com'), 'link');
});

// 이름이 검색엔진으로 시작할 뿐인 남의 사이트를 검색 유입으로 세면 안 된다.
test('googleblog.com 은 검색이 아니다', () => {
  assert.equal(refKind('googleblog.com'), 'link');
});

test('기기를 UA 로 가른다', () => {
  assert.equal(deviceOf(IPHONE), 'mobile');
  assert.equal(deviceOf('Mozilla/5.0 (iPad; CPU OS 18_0)'), 'tablet');
  assert.equal(deviceOf(CHROME), 'desktop');
});

test('도메인 목록에 admin 은 없다', () => {
  assert.deepEqual(DOMAINS, ['hub', 'employment', 'press', 'forecast', 'reports', 'ask']);
});

// 도메인을 화이트리스트로 막지 않으면 아무나 아무 이름의 줄을 쌓을 수 있다.
test('모르는 도메인은 통째로 버린다', () => {
  const body = { d: 'admin', p: '/', v: 'v1', s: 's1' };
  assert.equal(정규화(body, { ua: CHROME, country: 'KR', nowMs: 0 }), null);
  assert.equal(정규화({ ...body, d: 'nonsense' }, { ua: CHROME, country: 'KR', nowMs: 0 }), null);
});

test('방문자나 세션이 없으면 버린다', () => {
  const 기본 = { ua: CHROME, country: 'KR', nowMs: 0 };
  assert.equal(정규화({ d: 'hub', p: '/', s: 's1' }, 기본), null);
  assert.equal(정규화({ d: 'hub', p: '/', v: 'v1' }, 기본), null);
});

test('정규화는 서버가 아는 것으로 채운다', () => {
  const row = 정규화(
    { d: 'employment', p: '/b/industry/:id', v: 'v1', s: 's1', r: 'google.com', m: 'standalone' },
    { ua: IPHONE, country: 'KR', nowMs: Date.parse('2026-09-11T15:30:00Z') });
  assert.deepEqual(row, {
    ts: '2026-09-11T15:30:00Z',
    day: '2026-09-12',
    domain: 'employment',
    path: '/b/industry/:id',
    visitor: 'v1',
    session: 's1',
    ref: 'google.com',
    ref_kind: 'search',
    mode: 'standalone',
    device: 'mobile',
    country: 'KR',
  });
});

// 클라이언트가 보낸 mode 를 그대로 믿으면 아무 문자열이나 열에 들어간다.
test('모르는 표시모드는 browser 로 접는다', () => {
  const row = 정규화({ d: 'hub', p: '/', v: 'v1', s: 's1', m: '<script>' },
    { ua: CHROME, country: 'KR', nowMs: 0 });
  assert.equal(row.mode, 'browser');
});

test('경로가 없으면 루트로 본다', () => {
  const row = 정규화({ d: 'hub', v: 'v1', s: 's1' }, { ua: CHROME, country: null, nowMs: 0 });
  assert.equal(row.path, '/');
  assert.equal(row.ref, null);
  assert.equal(row.ref_kind, 'direct');
  assert.equal(row.country, null);
});

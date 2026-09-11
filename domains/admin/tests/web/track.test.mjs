import { test } from 'node:test';
import assert from 'node:assert/strict';
import { 경로정규화, 유입호스트, 보낼까, 페이로드 } from '../../../../core/track.js';

// 라우트 이름에는 숫자가 없고 값(산업코드·연도·보고서 id)에는 있다 — 그 비대칭이
// 규칙의 근거다. 안 묶으면 개별 산업·개별 보고서가 수백 줄로 흩어진다.
test('숫자를 품은 세그먼트를 :id 로 묶는다', () => {
  assert.equal(경로정규화('#/b/industry/300'), '/b/industry/:id');
  assert.equal(경로정규화('#/overview'), '/overview');
  assert.equal(경로정규화('#/r/kdi/2026-01-15-4412'), '/r/kdi/:id');
  assert.equal(경로정규화(''), '/');
  assert.equal(경로정규화('#/'), '/');
  assert.equal(경로정규화(null), '/');
});

test('세그먼트는 넷까지만 남긴다', () => {
  assert.equal(경로정규화('#/a/b/c/d/e/f'), '/a/b/c/d');
});

test('유입은 호스트만 남기고 검색어는 안 가져간다', () => {
  assert.equal(유입호스트('https://www.google.com/search?q=취업자', 'seongapark.github.io'),
    'google.com');
  assert.equal(유입호스트('https://seongapark.github.io/employ_archive/', 'seongapark.github.io'),
    null);
  assert.equal(유입호스트('', 'seongapark.github.io'), null);
  assert.equal(유입호스트('깨진값', 'seongapark.github.io'), null);
});

// 창 대역. localStorage 를 던지게 만들어 사생활 보호 모드를 흉내낸다.
function 창({ hash = '#/', host = 'seongapark.github.io', hostname = 'seongapark.github.io',
  referrer = '', off = null, standalone = false, 저장소죽음 = false } = {}) {
  const m = new Map(off === null ? [] : [['ea:off', off]]);
  const store = 저장소죽음
    ? { getItem() { throw new Error('막힘'); }, setItem() { throw new Error('막힘'); } }
    : { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) };
  return {
    location: { hash, host, hostname },
    document: { referrer },
    localStorage: store,
    sessionStorage: store,
    matchMedia: () => ({ matches: standalone }),
  };
}

test('제외 스위치가 켜져 있으면 안 보낸다', () => {
  assert.equal(보낼까(창()), true);
  assert.equal(보낼까(창({ off: '1' })), false);
});

test('로컬 개발은 안 보낸다', () => {
  assert.equal(보낼까(창({ hostname: 'localhost' })), false);
  assert.equal(보낼까(창({ hostname: '127.0.0.1' })), false);
});

// 통계가 화면을 못 건드린다 — 이 파일의 유일한 불변식이다.
test('저장소가 막혀 있어도 던지지 않는다', () => {
  assert.equal(보낼까(창({ 저장소죽음: true })), true);
  const p = 페이로드(창({ 저장소죽음: true }), 'hub');
  assert.equal(typeof p.v, 'string');
  assert.ok(p.v.length > 0);
});

test('페이로드는 여섯 개다', () => {
  const p = 페이로드(창({ hash: '#/b/industry/300', referrer: 'https://x.com/someone',
    standalone: true }), 'employment');
  assert.deepEqual(Object.keys(p).sort(), ['d', 'm', 'p', 'r', 's', 'v']);
  assert.equal(p.d, 'employment');
  assert.equal(p.p, '/b/industry/:id');
  assert.equal(p.r, 'x.com');
  assert.equal(p.m, 'standalone');
});

test('같은 창에서 방문자 ID 는 유지된다', () => {
  const w = 창();
  assert.equal(페이로드(w, 'hub').v, 페이로드(w, 'hub').v);
});

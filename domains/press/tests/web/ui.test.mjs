import { test } from 'node:test';
import assert from 'node:assert/strict';
import { roundSwitchHtml, barGroup, articleRow } from '../../app/js/ui.js';

const CTX = {
  rounds: [
    { release: '2026-09-07', label: "'26.8월분" },
    { release: '2026-08-10', label: "'26.7월분" },
    { release: '2026-07-13', label: "'26.6월분" },
  ],
  state: { release: '2026-08-10' },
};

test('회차 스위치는 지금 보는 회차를 selected 로 표시한다', () => {
  const h = roundSwitchHtml(CTX);
  assert.match(h, /<option value="2026-08-10" selected>/);
  assert.equal((h.match(/selected/g) || []).length, 1);
});

test('회차 스위치는 배포일까지 보여준다 — 라벨만으로는 언제 나온 회차인지 모른다', () => {
  // 라벨의 작은따옴표는 이스케이프된다(&#39;) — 회차 라벨도 데이터에서 온다.
  assert.match(roundSwitchHtml(CTX), /&#39;26\.8월분 · 09\.07 배포/);
});

test('회차 스위치는 모든 회차를 데이터 순서대로 싣는다', () => {
  const h = roundSwitchHtml(CTX);
  assert.equal((h.match(/<option/g) || []).length, 3);
  assert.ok(h.indexOf('2026-09-07') < h.indexOf('2026-07-13'));
});

test('고른 회차가 목록에 없으면 아무것도 selected 되지 않는다 — 틀린 회차를 고른 척하지 않는다', () => {
  const h = roundSwitchHtml({ ...CTX, state: { release: '2099-01-01' } });
  assert.ok(!h.includes('selected'));
});

test('barGroup: 0건은 빗금 트랙으로 남고 채움 막대가 없다', () => {
  const h = barGroup('산업', [{ name: '제조업', n: 4 }, { name: '도소매업', n: 0 }]);
  assert.equal((h.match(/bar-row__track--zero/g) || []).length, 1);
  assert.equal((h.match(/bar-row__fill/g) || []).length, 1);
});

test('articleRow: 링크가 없으면 a 대신 div 로 그린다', () => {
  const a = { title: 't', press: 'p', pub: '2026-09-07 12:00', cites: true, kw: [], url: '' };
  assert.ok(articleRow(a).startsWith('<div class="art'));
  assert.ok(articleRow({ ...a, url: 'https://x' }).startsWith('<a class="art'));
});

test('articleRow: 인용이 아닌 기사는 흐리게 표시하고 판정 이유를 붙인다', () => {
  const h = articleRow({
    title: 't', press: 'p', pub: '2026-09-07 12:00',
    cites: false, why: '국회 심의 기사', kw: [], url: '',
  });
  assert.match(h, /art--other/);
  assert.match(h, /국회 심의 기사/);
});

test('articleRow: 제목 속 꺾쇠는 이스케이프된다', () => {
  const h = articleRow({
    title: '<script>x</script>', press: 'p', pub: '', cites: true, kw: [], url: '',
  });
  assert.ok(!h.includes('<script>'));
});

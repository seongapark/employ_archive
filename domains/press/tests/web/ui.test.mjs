import { test } from 'node:test';
import assert from 'node:assert/strict';
import { roundSwitchHtml, columnChart, articleRow } from '../../app/js/ui.js';

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

test('columnChart: 0건은 빗금 기둥으로 남고 채움이 없다', () => {
  // 행이 사라지면 '안 다뤄졌다'는 사실이 화면에서 없어진다.
  const h = columnChart('산업', [{ name: '제조업', n: 4 }, { name: '도소매업', n: 0 }]);
  assert.equal((h.match(/vcol__track--zero/g) || []).length, 1);
  assert.equal((h.match(/vcol__fill/g) || []).length, 1);
  assert.ok(h.includes('도소매업'));
});

test('columnChart: 기둥 높이는 그 축의 최댓값 기준이다', () => {
  const h = columnChart('연령', [{ name: 'a', n: 10 }, { name: 'b', n: 5 }]);
  assert.ok(h.includes('height:100%'));
  assert.ok(h.includes('height:50%'));
});

test('columnChart: 1건은 0건과 다르게 그린다 — 채움이 있고 빗금이 아니다', () => {
  // 높이는 0% 에 가깝지만 채움 요소가 있어야 한다(보이는 최소 높이는 CSS 가 준다).
  const h = columnChart('연령', [{ name: 'a', n: 400 }, { name: 'b', n: 1 }]);
  assert.equal((h.match(/vcol__fill/g) || []).length, 2);
  assert.ok(!h.includes('vcol__track--zero'));
});

test('columnChart: 값을 기둥마다 직접 적는다 — 계열이 하나라 범례가 없다', () => {
  const h = columnChart('산업', [{ name: '제조업', n: 4 }]);
  assert.ok(h.includes('>4<'));
  assert.ok(h.includes('title="제조업 4건"'));
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

test('articleRow: 제목 줄에는 제목만 둔다 — 한 줄로 자르면 태그가 먼저 잘린다', () => {
  const h = articleRow({
    title: '아주 긴 기사 제목', press: 'p', pub: '2026-09-07 12:00',
    cites: true, kw: ['반등', '호황'], url: '',
  });
  const title = h.slice(h.indexOf('art__title'), h.indexOf('art__meta'));
  assert.ok(!title.includes('art__tag'));
  assert.equal((h.match(/art__tag/g) || []).length, 2);
});

test('articleRow: 제목 전문은 title 속성으로 남는다 — 잘린 뒤에도 읽을 수 있다', () => {
  const h = articleRow({
    title: '아주 긴 기사 제목', press: 'p', pub: '', cites: true, kw: [], url: '',
  });
  assert.ok(h.includes('title="아주 긴 기사 제목"'));
});

test('articleRow: 제목 속 꺾쇠는 이스케이프된다', () => {
  const h = articleRow({
    title: '<script>x</script>', press: 'p', pub: '', cites: true, kw: [], url: '',
  });
  assert.ok(!h.includes('<script>'));
});

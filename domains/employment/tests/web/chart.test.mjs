import { test } from 'node:test';
import assert from 'node:assert/strict';
import { barsSvg, timelineSvg, sheetTable } from '../../app/js/chart.js';

const NAMES = { eaps: '경제활동인구조사', est: '사업체노동력조사', ei: '고용행정통계' };

test('every bar carries its value label — the contrast mitigation is not optional', () => {
  const snapshot = [
    { source: 'eaps', state: 'value', yoy: 107.6 },
    { source: 'est', state: 'notProvided', yoy: null },
    { source: 'ei', state: 'value', yoy: 277.0 },
  ];
  const svg = barsSvg(snapshot, { width: 320, sourceNames: NAMES });
  assert.match(svg, /\+10\.8만명/);
  assert.match(svg, /\+27\.7만명/);
  assert.match(svg, /― 미제공/);
});

test('bars extend both ways from the zero line', () => {
  const svg = barsSvg([
    { source: 'eaps', state: 'value', yoy: -200 },
    { source: 'ei', state: 'value', yoy: 100 },
  ], { width: 300, sourceNames: NAMES });
  const rects = [...svg.matchAll(/<rect[^>]*x="([\d.]+)"[^>]*width="([\d.]+)"/g)]
    .map(m => ({ x: Number(m[1]), w: Number(m[2]) }));
  assert.equal(rects.length, 2);
  assert.ok(rects[0].x < rects[1].x, '음수 막대는 0선 왼쪽에서 시작한다');
});

test('a source with no points draws no polyline but keeps its color assignment', () => {
  const svg = timelineSvg(
    { eaps: [{ period: '2026-06', yoy: 1 }, { period: '2026-07', yoy: 2 }], est: [], ei: [] },
    { width: 320, height: 160, selected: '2026-07' },
  );
  assert.match(svg, /#2a78d6/);
  assert.doesNotMatch(svg, /#eb6834/);
});

test('the selected month gets a marker line', () => {
  const svg = timelineSvg(
    { eaps: [{ period: '2026-05', yoy: 1 }, { period: '2026-07', yoy: 2 }], est: [], ei: [] },
    { width: 320, height: 160, selected: '2026-05' },
  );
  assert.match(svg, /class="chart__marker"/);
});

test('sheetTable is a real table with every source as a row', () => {
  const html = sheetTable(
    [{ source: 'eaps', state: 'value', yoy: 107.6 }, { source: 'est', state: 'notProvided', yoy: null }],
    { eaps: [{ period: '2026-07', yoy: 107.6 }], est: [] },
    { sourceNames: NAMES },
  );
  assert.match(html, /<table/);
  assert.match(html, /경제활동인구조사/);
  assert.match(html, /사업체노동력조사/);
  assert.match(html, /미제공/);
});

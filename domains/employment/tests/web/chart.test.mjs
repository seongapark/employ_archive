import { test } from 'node:test';
import assert from 'node:assert/strict';
import { barsSvg, timelineSvg, sheetTable, LABEL_W } from '../../app/js/chart.js';

// 한국어 값 라벨(`+27.7만명` 류)이 11px 기준으로 실제 차지하는 폭의 하한.
// chart.js 의 VALUE_GUTTER 를 그대로 들여오면 여백이 좁아져도 이 테스트가
// 항상 자기 자신과 비교해 통과해 버린다 — 그래서 숫자를 여기 다시 박아 둔다.
const MIN_VALUE_GUTTER = 55;

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

test('the widest label at maximum magnitude neither overruns the name column nor gets clipped', () => {
  const width = 320;
  const svg = barsSvg([
    { source: 'eaps', state: 'value', yoy: -1000 },
    { source: 'ei', state: 'value', yoy: 1000 },
  ], { width, sourceNames: NAMES });
  const rects = [...svg.matchAll(/<rect[^>]*x="([\d.]+)"[^>]*width="([\d.]+)"/g)]
    .map(m => ({ x: Number(m[1]), w: Number(m[2]) }));
  assert.equal(rects.length, 2);
  const [neg, pos] = rects;
  assert.ok(neg.x >= LABEL_W + MIN_VALUE_GUTTER,
    `음수 막대 x(${neg.x})는 LABEL_W+MIN_VALUE_GUTTER(${LABEL_W + MIN_VALUE_GUTTER}) 이상이어야 라벨이 출처명 열을 침범하지 않는다`);
  assert.ok(pos.x + pos.w <= width - MIN_VALUE_GUTTER,
    `양수 막대 오른쪽 끝(${pos.x + pos.w})은 width-MIN_VALUE_GUTTER(${width - MIN_VALUE_GUTTER}) 이하여야 라벨이 잘리지 않는다`);
});

test('sheetTable is a real table with every source as a row', () => {
  const html = sheetTable(
    [{ source: 'eaps', state: 'value', value: 29136.1, yoy: 107.6 },
      { source: 'est', state: 'notProvided', value: null, yoy: null }],
    { eaps: [{ period: '2026-07', yoy: 107.6 }], est: [] },
    { sourceNames: NAMES },
  );
  assert.match(html, /<table/);
  assert.match(html, /경제활동인구조사/);
  assert.match(html, /사업체노동력조사/);
  assert.match(html, /미제공/);
});

test('the table carries the level too — the alternative view must not be thinner than the chart', () => {
  const html = sheetTable(
    [{ source: 'eaps', state: 'value', value: 29136.1, yoy: 107.6 }],
    { eaps: [{ period: '2026-07', yoy: 107.6 }] },
    { sourceNames: NAMES },
  );
  assert.match(html, /<th scope="col">수준<\/th>/);
  assert.match(html, /2,913\.6만명/);   // 수준
  assert.match(html, /\+10\.8만명/);    // 증감
});

test('an empty-state row keeps its wording in both the level and the delta column', () => {
  const html = sheetTable(
    [{ source: 'est', state: 'notProvided', value: null, yoy: null },
      { source: 'ei', state: 'unpublished', value: null, yoy: null }],
    { est: [], ei: [] },
    { sourceNames: NAMES },
  );
  assert.equal((html.match(/― 미제공/g) || []).length, 2);
  assert.equal((html.match(/― 미발표/g) || []).length, 2);
});

test('a noDelta row shows its level but never a fabricated delta', () => {
  const html = sheetTable(
    [{ source: 'est', state: 'noDelta', value: 20419.1, yoy: null }],
    { est: [{ period: '2024-08', yoy: null }] },
    { sourceNames: NAMES },
  );
  assert.match(html, /2,041\.9만명/);
  assert.match(html, /― 증감없음/);
  assert.doesNotMatch(html, /0\.0만명/);
});

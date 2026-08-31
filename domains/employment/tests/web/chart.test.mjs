import { test } from 'node:test';
import assert from 'node:assert/strict';
import { barsSvg, timelineSvg, sheetTable, LABEL_W, timelinePeriods, periodAtRatio } from '../../app/js/chart.js';

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
    { sourceNames: NAMES },
  );
  assert.match(html, /<table/);
  assert.match(html, /경제활동인구조사/);
  assert.match(html, /사업체노동력조사/);
  assert.match(html, /미제공/);
  // 시계열 개월 수 열은 뺐다 — 표에서 알고 싶은 것은 수준과 증감이다
  assert.doesNotMatch(html, /개월/);
  assert.doesNotMatch(html, /시계열/);
});

test('the table carries the level too — the alternative view must not be thinner than the chart', () => {
  const html = sheetTable(
    [{ source: 'eaps', state: 'value', value: 29136.1, yoy: 107.6 }],
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
    { sourceNames: NAMES },
  );
  assert.equal((html.match(/― 미제공/g) || []).length, 2);
  assert.equal((html.match(/― 미발표/g) || []).length, 2);
});

test('a noDelta row shows its level but never a fabricated delta', () => {
  const html = sheetTable(
    [{ source: 'est', state: 'noDelta', value: 20419.1, yoy: null }],
    { sourceNames: NAMES },
  );
  assert.match(html, /2,041\.9만명/);
  assert.match(html, /― 증감없음/);
  assert.doesNotMatch(html, /0\.0만명/);
});

// 드래그는 이 두 함수 위에 얹힌다. 좌표 계산이 틀리면 끌었을 때 엉뚱한 달로
// 튀는데, 브라우저 없이 잡을 수 있는 곳은 여기뿐이다.
const TL = {
  eaps: [
    { period: '2024-07', yoy: 1 }, { period: '2024-08', yoy: 2 },
    { period: '2024-09', yoy: 3 }, { period: '2024-10', yoy: 4 },
  ],
  est: [{ period: '2024-09', yoy: 9 }],
  ei: [],
};

test('timelinePeriods unions the sources and sorts ascending', () => {
  assert.deepEqual(timelinePeriods(TL), ['2024-07', '2024-08', '2024-09', '2024-10']);
});

test('periodAtRatio maps the two ends to the first and last month', () => {
  const periods = timelinePeriods(TL);
  assert.equal(periodAtRatio(periods, 0), '2024-07');
  assert.equal(periodAtRatio(periods, 1), '2024-10');
});

test('periodAtRatio snaps to the nearest month and never runs off the ends', () => {
  const periods = timelinePeriods(TL);
  // 왼쪽 여백(8/320)과 오른쪽 여백을 뺀 구간을 3등분한 지점들
  assert.equal(periodAtRatio(periods, 8 / 320), '2024-07');
  assert.equal(periodAtRatio(periods, (8 + 304 / 3) / 320), '2024-08');
  assert.equal(periodAtRatio(periods, (8 + 304 * 2 / 3) / 320), '2024-09');
  // 그래프 밖으로 끌어도 양 끝에서 멈춘다
  assert.equal(periodAtRatio(periods, -5), '2024-07');
  assert.equal(periodAtRatio(periods, 5), '2024-10');
  assert.equal(periodAtRatio([], 0.5), null);
});

test('bars show the level next to the delta', () => {
  const svg = barsSvg([
    { source: 'eaps', state: 'value', value: 29136.1, yoy: 107.6 },
    { source: 'est', state: 'notProvided', value: null, yoy: null },
  ], { width: 320, sourceNames: NAMES });
  assert.match(svg, /2,913\.6만명/);   // 수준
  assert.match(svg, /\+10\.8만명/);    // 증감
  assert.match(svg, /― 미제공/);
});

test('the marker carries a grip so it reads as draggable', () => {
  const svg = timelineSvg(TL, { width: 320, height: 160, selected: '2024-09' });
  assert.match(svg, /class="chart__marker"/);
  assert.match(svg, /class="chart__grip"/);
});

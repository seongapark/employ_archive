import { test } from 'node:test';
import assert from 'node:assert/strict';
import { kpiBlockHtml, trendSection } from '../../app/js/screens/release.js';

function rate(over = {}) {
  return {
    id: 'x', source: 'eaps', series: 'employment_rate', breakdown: 'total',
    category: null, period: '2026-08', value: 63.3, unit: '%', yoy: 0.0,
    released_at: '2026-09-09', release_url: 'https://mods.go.kr/x',
    attachments: [], collected_at: '2026-09-11T09:00:00+09:00', ...over,
  };
}

// 2026년 8월 실측값. 행이 지표(고용률·실업률), 열이 연령 기준이다.
const SERIES = [
  rate({ value: 63.3, yoy: 0.0 }),
  rate({ value: 70.4, yoy: 0.5, breakdown: 'scope', category: '15-64' }),
  rate({ value: 44.1, yoy: -1.0, breakdown: 'scope', category: '15-29' }),
  rate({ series: 'unemployment_rate', value: 2.0, yoy: 0.0 }),
  rate({ series: 'unemployment_rate', value: 2.2, yoy: 0.0,
         breakdown: 'scope', category: '15-64' }),
  rate({ series: 'unemployment_rate', value: 5.4, yoy: 0.5,
         breakdown: 'scope', category: '15-29' }),
];

function values(html) {
  return [...html.matchAll(/class="kpi__value num[^"]*">([^<]+)</g)].map(m => m[1]);
}

test('the grid reads as two rows of three', () => {
  // 행이 지표, 열이 연령 기준이다. 같은 열끼리 세로로 읽으면 같은 연령대의
  // 고용률과 실업률이 나란히 오고, 같은 행끼리 가로로 읽으면 한 지표가 연령에
  // 따라 어떻게 갈리는지가 보인다.
  const html = kpiBlockHtml(SERIES, { source: 'eaps', period: '2026-08' });
  assert.deepEqual(values(html), ['63.3%', '70.4%', '44.1%', '2.0%', '2.2%', '5.4%']);
});

test('each row is named once, not on every tile', () => {
  const html = kpiBlockHtml(SERIES, { source: 'eaps', period: '2026-08' });
  assert.equal((html.match(/고용률/g) || []).length, 1);
  assert.equal((html.match(/실업률/g) || []).length, 1);
});

test('every column says which ages it counts', () => {
  const html = kpiBlockHtml(SERIES, { source: 'eaps', period: '2026-08' });
  for (const label of ['15세 이상', '15~64세', '15~29세']) {
    assert.equal((html.match(new RegExp(label, 'g')) || []).length, 2,
      `${label} 이 두 행에 한 번씩 나와야 한다`);
  }
});

test('the changes keep percentage points and their signs', () => {
  const html = kpiBlockHtml(SERIES, { source: 'eaps', period: '2026-08' });
  assert.ok(html.includes('+0.5%p'));
  assert.ok(html.includes('-1.0%p'));
  assert.ok(html.includes('0.0%p') && !html.includes('+0.0%p'), '0 에는 부호를 안 단다');
});

test('a month the survey has not published yet shows no invented numbers', () => {
  const html = kpiBlockHtml(SERIES, { source: 'eaps', period: '2026-09' });
  assert.deepEqual(values(html), []);
  assert.equal((html.match(/미발표/g) || []).length, 6);
});

test('a source with no indicators of its own gets no grid at all', () => {
  assert.equal(kpiBlockHtml(SERIES, { source: 'est', period: '2026-08' }), '');
});

// ── 행정통계 KPI ──────────────────────────────────────────────────────

function ei(over = {}) {
  return {
    id: 'x', source: 'ei', series: 'acquired', breakdown: 'total',
    category: null, period: '2026-07', value: 660.0, unit: '천명', yoy: 33.0,
    released_at: '2026-08-11', release_url: 'https://www.moel.go.kr/x',
    attachments: [], collected_at: '2026-09-21T09:00:00+09:00', ...over,
  };
}

// 2026년 7월 실측값.
const EI_SERIES = [
  ei({ series: 'acquired', value: 660.0, yoy: 33.0 }),
  ei({ series: 'separated', value: 634.0, yoy: 23.0 }),
  ei({ series: 'benefit_new', value: 109.0, yoy: -2.0 }),
  ei({ series: 'benefit_paid', value: 643.0, yoy: -31.0 }),
  ei({ series: 'benefit_amount', value: 10904.0, unit: '억원', yoy: -218.0 }),
];

test('the administrative grid is two rows of two and three', () => {
  const html = kpiBlockHtml(EI_SERIES, { source: 'ei', period: '2026-07' });
  assert.deepEqual(values(html),
    ['66.0만명', '63.4만명', '10.9만명', '64.3만명', '10,904억원']);
  assert.ok(html.includes('--cols:2'), '고용보험 행은 두 칸이다');
  assert.ok(html.includes('--cols:3'), '구직급여 행은 세 칸이다');
});

test('the insured headcount is not repeated under the card that already shows it', () => {
  // 화면 맨 위 카드가 이미 상시가입자수와 증감을 말한다.
  const html = kpiBlockHtml(
    [...EI_SERIES, ei({ series: 'headcount', value: 15877.0, yoy: 277.0 })],
    { source: 'ei', period: '2026-07' });
  assert.ok(!html.includes('1,587.7만명'));
});

test('the payout keeps its own unit inside the grid', () => {
  const html = kpiBlockHtml(EI_SERIES, { source: 'ei', period: '2026-07' });
  assert.ok(html.includes('10,904억원'));
  assert.ok(html.includes('-218억원'));
});

// ── 추이의 연령 범위 스위치 ────────────────────────────────────────────

function level(over = {}) {
  return {
    id: 'x', source: 'eaps', series: 'headcount', breakdown: 'total',
    category: null, period: '2026-08', value: 29151.0, unit: '천명', yoy: 184.0,
    released_at: '2026-09-09', release_url: 'https://mods.go.kr/x',
    attachments: [], collected_at: '2026-09-11T09:00:00+09:00', ...over,
  };
}

// 세 범위가 같은 지표를 저마다 들고 있다(실측: 18개 조합이 25개월씩 연속).
const TRENDS = ['2026-07', '2026-08'].flatMap(period => [
  level({ period, value: 29151.0 }),
  level({ period, value: 24540.2, breakdown: 'scope', category: '15-64' }),
  level({ period, value: 3428.0, breakdown: 'scope', category: '15-29' }),
  level({ period, series: 'unemployed', value: 588.1 }),
  level({ period, series: 'unemployed', value: 540.9, breakdown: 'scope', category: '15-64' }),
  level({ period, series: 'unemployed', value: 195.0, breakdown: 'scope', category: '15-29' }),
]);

test('the switch offers the three age ranges and marks the one in use', () => {
  const { html } = trendSection(TRENDS, { source: 'eaps', scope: '15-64' });
  for (const label of ['15세 이상', '15~64세', '청년']) assert.ok(html.includes(label));
  const active = [...html.matchAll(/data-scope="([^"]+)"[^>]*class="[^"]*scopes__tab--active/g)];
  const marked = [...html.matchAll(/class="[^"]*scopes__tab--active[^"]*"[^>]*data-scope="([^"]+)"/g)];
  assert.equal(active.length + marked.length, 1, '활성 탭은 하나뿐이어야 한다');
});

test('picking an age range changes the numbers the charts show', () => {
  const all = trendSection(TRENDS, { source: 'eaps', scope: 'total' });
  const young = trendSection(TRENDS, { source: 'eaps', scope: '15-29' });
  assert.equal(all.byIndicator.get('headcount').at(-1).value, 29151.0);
  assert.equal(young.byIndicator.get('headcount').at(-1).value, 3428.0);
  assert.ok(all.html.includes('2,915.1만명'));
  assert.ok(young.html.includes('342.8만명'));
});

test('every age range draws the same set of charts', () => {
  const counts = ['total', '15-64', '15-29'].map(scope =>
    trendSection(TRENDS, { source: 'eaps', scope }).byIndicator.size);
  assert.deepEqual(counts, [2, 2, 2]);
});

test('an indicator the age range never publishes is simply absent', () => {
  // 빈 그림을 그리면 그 범위에서 그 지표를 안 낸다는 사실이 사라진다.
  const only = [level({ breakdown: 'scope', category: '15-29', value: 3428.0 })];
  const { byIndicator } = trendSection(only, { source: 'eaps', scope: '15-29' });
  assert.deepEqual([...byIndicator.keys()], ['headcount']);
});

test('a source with no indicators of its own gets no trend section', () => {
  // ei 는 이제 아홉 지표를 갖는다. 아직 넓히지 않은 출처는 사업체노동력조사다.
  const { html, byIndicator } = trendSection(TRENDS, { source: 'est', scope: 'total' });
  assert.equal(html, '');
  assert.equal(byIndicator.size, 0);
});

// ── 행정통계 범위 탭 ──────────────────────────────────────────────────

// 2026-07 실측값. 전체는 아홉, 제조업은 넷, 서비스업은 하나만 있다.
const EI_TRENDS = ['2026-06', '2026-07'].flatMap(period => [
  ei({ period, series: 'headcount', value: 15877.0, yoy: 277.0 }),
  ei({ period, series: 'acquired', value: 660.0, yoy: 33.0 }),
  ei({ period, series: 'separated', value: 634.0, yoy: 23.0 }),
  ei({ period, series: 'benefit_new', value: 109.0, yoy: -2.0 }),
  ei({ period, series: 'benefit_paid', value: 643.0, yoy: -31.0 }),
  ei({ period, series: 'benefit_amount', value: 10904.0, unit: '억원', yoy: -218.0 }),
  ei({ period, series: 'job_openings', value: 177.0, yoy: 12.8 }),
  ei({ period, series: 'job_seekers', value: 399.0, yoy: -11.5 }),
  ei({ period, series: 'openings_ratio', value: 0.44, unit: '배', yoy: 0.04 }),
  ei({ period, series: 'headcount', value: 3844.0, breakdown: 'industry', category: 'C' }),
  ei({ period, series: 'benefit_new', value: 16.0, yoy: -1.1, breakdown: 'industry', category: 'C' }),
  ei({ period, series: 'benefit_paid', value: 110.0, yoy: -3.6, breakdown: 'industry', category: 'C' }),
  ei({ period, series: 'job_openings', value: 56.0, yoy: 3.3, breakdown: 'industry', category: 'C' }),
  ei({ period, series: 'headcount', value: 11139.0, breakdown: 'scope', category: 'services' }),
]);

test('the administrative screen draws no range tabs at all', () => {
  // 범위가 전산업 하나뿐이다(2026-09-22 사용자 판단). 누를 데가 없는 탭 줄은
  // 눌러도 아무 일이 없는 버튼이라 아예 그리지 않는다.
  const { html } = trendSection(EI_TRENDS, { source: 'ei', scope: 'total' });
  assert.ok(!html.includes('scopes__tab'), '탭 줄이 없어야 한다');
  for (const label of ['제조업', '서비스업']) {
    assert.ok(!html.includes(label), `${label} 탭이 남아 있다`);
  }
});

test('the administrative screen draws all nine indicators', () => {
  const { byIndicator } = trendSection(EI_TRENDS, { source: 'ei', scope: 'total' });
  assert.equal(byIndicator.size, 9);
});

test('a stale range key from another source falls back to the whole economy', () => {
  // 경활에서 `15-64` 를 들고 넘어와도 행정통계에는 그 범위가 없다.
  const { byIndicator } = trendSection(EI_TRENDS, { source: 'ei', scope: '15-64' });
  assert.equal(byIndicator.size, 9);
  assert.equal(byIndicator.get('headcount').at(-1).value, 15877.0);
});

test('the ratio keeps its own unit in the trend head', () => {
  const { html } = trendSection(EI_TRENDS, { source: 'ei', scope: 'total' });
  assert.ok(html.includes('0.44배'));
  assert.ok(html.includes('+0.04배'));
});

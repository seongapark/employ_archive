import { test } from 'node:test';
import assert from 'node:assert/strict';
import { kpiBlockHtml } from '../../app/js/screens/release.js';

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
  return [...html.matchAll(/class="kpi__value num">([^<]+)</g)].map(m => m[1]);
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

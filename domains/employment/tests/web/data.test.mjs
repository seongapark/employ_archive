import { test } from 'node:test';
import assert from 'node:assert/strict';
import { monthOptions, overviewCards, fmtLevel, fmtDelta, monthLabel, esc } from '../../app/js/data.js';

function rec(over = {}) {
  return {
    id: 'x', source: 'eaps', series: 'headcount', breakdown: 'total', category: null,
    period: '2026-07', value: 29136.1, unit: '천명', yoy: 107.6, status: '잠정',
    released_at: '2026-08-12', release_url: 'https://mods.go.kr/x', attachments: [],
    collected_at: '2026-08-30T20:56:40+09:00', ...over,
  };
}

const SOURCES = [
  { code: 'eaps', name_ko: '경제활동인구조사', headline_ko: '취업자수', coverage: 'c1', caveat: 'v1', board_url: 'https://a' },
  { code: 'est', name_ko: '사업체노동력조사', headline_ko: '종사자수', coverage: 'c2', caveat: 'v2', board_url: 'https://b' },
  { code: 'ei', name_ko: '고용행정통계', headline_ko: '상시가입자수', coverage: 'c3', caveat: 'v3', board_url: 'https://c' },
];

test('monthOptions starts where all three sources have a total', () => {
  const series = [
    rec({ source: 'eaps', period: '2023-07' }), rec({ source: 'ei', period: '2023-07' }),
    rec({ source: 'eaps', period: '2024-06' }), rec({ source: 'ei', period: '2024-06' }),
    rec({ source: 'eaps', period: '2024-07' }), rec({ source: 'ei', period: '2024-07' }),
    rec({ source: 'est', period: '2024-07' }),
    rec({ source: 'eaps', period: '2026-07' }), rec({ source: 'ei', period: '2026-07' }),
  ];
  const opts = monthOptions(series);
  assert.deepEqual(opts.years, [2024, 2025, 2026]);
  assert.deepEqual(opts.monthsByYear[2024], [7, 8, 9, 10, 11, 12]);
  assert.deepEqual(opts.monthsByYear[2026], [1, 2, 3, 4, 5, 6, 7]);
  assert.equal(opts.latest, '2026-07');
});

test('monthOptions ignores non-total records when finding the floor', () => {
  const series = [
    rec({ source: 'eaps', period: '2024-01', breakdown: 'industry', category: 'C' }),
    rec({ source: 'est', period: '2024-01', breakdown: 'industry', category: 'C' }),
    rec({ source: 'ei', period: '2024-01', breakdown: 'industry', category: 'C' }),
    rec({ source: 'eaps', period: '2024-07' }), rec({ source: 'est', period: '2024-07' }),
    rec({ source: 'ei', period: '2024-07' }),
  ];
  assert.deepEqual(monthOptions(series).years, [2024]);
  assert.deepEqual(monthOptions(series).monthsByYear[2024], [7]);
});

test('overviewCards marks a source unpublished and carries its latest month', () => {
  const series = [
    rec({ source: 'eaps', period: '2026-07', value: 29136.1, yoy: 107.6 }),
    rec({ source: 'ei', period: '2026-07', value: 15877.0, yoy: 277.0 }),
    rec({ source: 'est', period: '2026-06', value: 20714.2, yoy: 248.0, released_at: '2026-08-31' }),
  ];
  const cards = overviewCards(series, SOURCES, '2026-07');
  assert.deepEqual(cards.map(c => c.code), ['eaps', 'est', 'ei']);
  const est = cards[1];
  assert.equal(est.state, 'unpublished');
  assert.equal(est.value, null);
  assert.deepEqual(
    { period: est.fallback.period, value: est.fallback.value, yoy: est.fallback.yoy },
    { period: '2026-06', value: 20714.2, yoy: 248.0 },
  );
  assert.equal(cards[0].state, 'value');
  assert.equal(cards[0].fallback, null);
});

test('formatters convert 천명 to 만명', () => {
  assert.equal(fmtLevel(29136.1), '2,913.6만명');
  assert.equal(fmtDelta(107.6), '+10.8만명');
  assert.equal(fmtDelta(-57.2), '-5.7만명');
  assert.equal(fmtDelta(0), '0.0만명');
  assert.equal(monthLabel('2026-07'), '2026.07');
  assert.equal(esc('<b>&'), '&lt;b&gt;&amp;');
});

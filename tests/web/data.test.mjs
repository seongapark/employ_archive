import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  latestRecords, summarize, seriesFor, orgIndicators, compareSet,
  timelineGroups, fmtValue, fmtDelta, dateLabel, isNew, esc, SHORT_LABELS,
} from '../../web/js/data.js';

const INDICATOR_CODES = ['emp_change', 'emp_rate', 'unemp_rate', 'gdp_growth', 'cpi', 'emp_rate_youth', 'labor_force'];

const ORGS = [
  { org: 'OECD', name_ko: 'OECD', method: 'api', track: 'A' },
  { org: 'BOK', name_ko: '한국은행', method: 'pdf', track: 'A' },
];

function rec(over = {}) {
  return {
    id: 'oecd-2026-08-gdp_growth-2027', org: 'OECD', org_name_ko: 'OECD',
    report_title: 'Economic Outlook 119', published_at: '2026-08-29',
    target_year: 2027, target_period: 'annual', indicator: 'gdp_growth',
    value: 1.9, unit: '%', prev_value: null, revision: null,
    rationale: '', rationale_tags: [], source_url: 'https://x/a',
    source_page: null, landing_url: 'https://x', confidence: 'verified',
    collected_at: '2026-08-29T16:00:00+09:00', ...over,
  };
}

test('latestRecords picks newest per org, sorted by date desc', () => {
  const rs = [
    rec({ org: 'BOK', published_at: '2026-05-28', value: 1.8, id: 'a' }),
    rec({ org: 'BOK', published_at: '2026-08-28', value: 2.1, id: 'b' }),
    rec({ published_at: '2026-08-29', id: 'c' }),
  ];
  const latest = latestRecords(rs, { indicator: 'gdp_growth', targetYear: 2027 });
  assert.deepEqual(latest.map((r) => r.id), ['c', 'b']);
});

test('summarize computes count/avg/max/min', () => {
  const latest = [rec({ value: 2.1, org: 'BOK' }), rec({ value: 1.9 })];
  const s = summarize(latest);
  assert.equal(s.count, 2);
  assert.equal(s.avg, 2.0);
  assert.equal(s.max.value, 2.1);
  assert.equal(s.min.value, 1.9);
  assert.equal(summarize([]), null);
});

test('seriesFor sorts ascending', () => {
  const rs = [rec({ published_at: '2026-08-29', id: 'b' }), rec({ published_at: '2026-02-10', id: 'a' })];
  assert.deepEqual(seriesFor(rs, { org: 'OECD', indicator: 'gdp_growth', targetYear: 2027 }).map((r) => r.id), ['a', 'b']);
});

test('orgIndicators returns ordered present indicators', () => {
  const rs = [rec(), rec({ indicator: 'emp_change', value: 12.3, unit: '만명', id: 'x' })];
  assert.deepEqual(orgIndicators(rs, 'OECD'), ['emp_change', 'gdp_growth']);
});

test('compareSet sorts desc, flags stale >90d, filters intl', () => {
  const rs = [
    rec({ org: 'BOK', published_at: '2026-08-28', value: 2.1 }),
    rec({ published_at: '2026-04-01', value: 2.4 }),
  ];
  const set = compareSet(rs, { indicator: 'gdp_growth', targetYear: 2027, today: '2026-08-29', orgsMeta: ORGS, filter: 'all' });
  assert.deepEqual(set.map((e) => e.rec.value), [2.4, 2.1]);
  assert.equal(set[0].stale, true);
  assert.equal(set[1].stale, false);
  assert.equal(set[0].monthLabel, '04.01');
  const intl = compareSet(rs, { indicator: 'gdp_growth', targetYear: 2027, today: '2026-08-29', orgsMeta: ORGS, filter: 'intl' });
  assert.deepEqual(intl.map((e) => e.rec.org), ['OECD']);
});

test('timelineGroups groups by month then org+date', () => {
  const rs = [
    rec({ id: 'a', indicator: 'gdp_growth' }),
    rec({ id: 'b', indicator: 'emp_change', value: 12.3, unit: '만명' }),
    rec({ id: 'c', org: 'BOK', published_at: '2026-05-28' }),
  ];
  const g = timelineGroups(rs);
  assert.deepEqual(g.map((m) => m.month), ['2026.08', '2026.05']);
  assert.equal(g[0].events.length, 1);
  assert.equal(g[0].events[0].items.length, 2);
});

test('fmtValue / fmtDelta formats', () => {
  assert.equal(fmtValue(rec({ value: 12.3, unit: '만명', indicator: 'emp_change' })), '12.3만명');
  assert.equal(fmtValue(rec()), '1.9%');
  assert.deepEqual(fmtDelta(rec()), { dir: 'flat', text: '—' });
  assert.deepEqual(fmtDelta(rec({ revision: 0.2 })), { dir: 'up', text: '+0.2%p' });
  assert.deepEqual(fmtDelta(rec({ revision: -3, unit: '만명', indicator: 'emp_change' })), { dir: 'down', text: '-3만명' });
});

test('dateLabel: api org → 수집, else 발표', () => {
  assert.equal(dateLabel(rec(), ORGS), '2026.08.29 수집');
  assert.equal(dateLabel(rec({ org: 'BOK', published_at: '2026-08-28' }), ORGS), '2026.08.28 발표');
});

test('isNew within 7 days', () => {
  assert.equal(isNew(rec({ published_at: '2026-08-25' }), '2026-08-29'), true);
  assert.equal(isNew(rec({ published_at: '2026-08-10' }), '2026-08-29'), false);
});

test('esc escapes html', () => {
  assert.equal(esc('<b>&"'), '&lt;b&gt;&amp;&quot;');
});

test('compareSet cross-month stale boundary', () => {
  const rs = [
    rec({ published_at: '2026-01-01', value: 2.4 }),
    rec({ published_at: '2026-06-01', value: 2.1 }),
  ];
  const set = compareSet(rs, { indicator: 'gdp_growth', targetYear: 2027, today: '2026-04-02', orgsMeta: ORGS, filter: 'all' });
  assert.equal(set[0].rec.published_at, '2026-01-01');
  assert.equal(set[0].stale, true);
  assert.equal(set[1].rec.published_at, '2026-06-01');
  assert.equal(set[1].stale, false);
});

test('isNew cross-month boundary', () => {
  assert.equal(isNew(rec({ published_at: '2026-01-22' }), '2026-02-01'), false);
  assert.equal(isNew(rec({ published_at: '2026-08-22' }), '2026-08-29'), true);
});

test('esc escapes single quotes', () => {
  assert.equal(esc("a'b"), 'a&#39;b');
});

test('SHORT_LABELS covers all 7 indicator codes', () => {
  for (const code of INDICATOR_CODES) {
    assert.equal(typeof SHORT_LABELS[code], 'string');
    assert.ok(SHORT_LABELS[code].length > 0, `missing short label for ${code}`);
  }
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  latestRecords, summarize, seriesFor, orgIndicators, compareSet,
  timelineGroups, fmtValue, fmtDelta, dateLabel, isNew, esc, SHORT_LABELS,
  halfYears, halfYearLabel, fmtNumber, isOcrSourced,
} from '../../app/js/data.js';

const INDICATOR_CODES = ['emp_change', 'emp_rate', 'unemp_rate', 'gdp_growth', 'cpi', 'emp_rate_youth', 'labor_force'];

const ORGS = [
  { org: 'OECD', name_ko: 'OECD', method: 'api', track: 'A' },
  { org: 'BOK', name_ko: '한국은행', method: 'pdf', track: 'A' },
  { org: 'KEIS', name_ko: '한국고용정보원', method: 'ocr', track: 'B' },
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
    rec({ org: 'BOK', published_at: '2026-06-01', value: 2.1 }),
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

test('isOcrSourced flags an org whose method is ocr', () => {
  assert.equal(isOcrSourced(rec({ org: 'KEIS' }), ORGS), true);
});

test('isOcrSourced does not flag a non-OCR org', () => {
  assert.equal(isOcrSourced(rec({ org: 'BOK' }), ORGS), false);
  assert.equal(isOcrSourced(rec({ org: 'OECD' }), ORGS), false);
});

test('isOcrSourced does not throw for an unknown org', () => {
  assert.equal(isOcrSourced(rec({ org: 'UNKNOWN' }), ORGS), false);
  assert.equal(isOcrSourced(rec({ org: 'UNKNOWN' }), []), false);
});

test('fmtDelta: revision 0 is flat, not down', () => {
  assert.deepEqual(fmtDelta(rec({ revision: 0 })), { dir: 'flat', text: '—' });
});

test('compareSet reduces to latest edition per org (F1)', () => {
  const rs = [
    rec({ org: 'BOK', published_at: '2026-05-01', value: 1.8, id: 'old' }),
    rec({ org: 'BOK', published_at: '2026-08-01', value: 2.2, id: 'new' }),
  ];
  const set = compareSet(rs, { indicator: 'gdp_growth', targetYear: 2027, today: '2026-08-29', orgsMeta: ORGS, filter: 'all' });
  assert.equal(set.length, 1);
  assert.equal(set[0].rec.id, 'new');
  assert.equal(set[0].rec.value, 2.2);
});

test('latestRecords and seriesFor ignore non-annual target_period (F5)', () => {
  const rs = [
    rec({ id: 'annual', target_period: 'annual' }),
    rec({ id: 'h1', target_period: 'h1', published_at: '2026-08-30', value: 5 }),
  ];
  const latest = latestRecords(rs, { indicator: 'gdp_growth', targetYear: 2027 });
  assert.deepEqual(latest.map((r) => r.id), ['annual']);

  const series = seriesFor(rs, { org: 'OECD', indicator: 'gdp_growth', targetYear: 2027 });
  assert.deepEqual(series.map((r) => r.id), ['annual']);
});

test('compareSet stale boundary at exactly 90/91 days', () => {
  const rs = [
    rec({ org: 'OECD', published_at: '2026-05-31', value: 2.0, id: 'boundary90' }),
    rec({ org: 'BOK', published_at: '2026-05-30', value: 2.1, id: 'boundary91' }),
  ];
  const set = compareSet(rs, { indicator: 'gdp_growth', targetYear: 2027, today: '2026-08-29', orgsMeta: ORGS, filter: 'all' });
  const byId = Object.fromEntries(set.map((e) => [e.rec.id, e]));
  assert.equal(byId.boundary90.stale, false);
  assert.equal(byId.boundary91.stale, true);
});


test('fmtValue keeps one decimal on percent indicators', () => {
  assert.equal(fmtValue(rec({ indicator: 'emp_rate', value: 63, unit: '%' })), '63.0%');
  assert.equal(fmtValue(rec({ indicator: 'emp_rate', value: 62.9, unit: '%' })), '62.9%');
});

test('fmtValue leaves 만명 counts as published', () => {
  assert.equal(fmtValue(rec({ indicator: 'emp_change', value: 20, unit: '만명' })), '20만명');
  assert.equal(fmtValue(rec({ indicator: 'emp_change', value: 12.3, unit: '만명' })), '12.3만명');
});

function halfSet() {
  const base = { org: 'BOK', indicator: 'emp_change', target_year: 2026,
    published_at: '2026-08-27', unit: '만명' };
  return [
    rec({ ...base, id: 'a', target_period: 'annual', value: 14 }),
    rec({ ...base, id: 'b', target_period: 'h1', value: 11 }),
    rec({ ...base, id: 'c', target_period: 'h2', value: 18 }),
  ];
}

test('halfYears finds the halves of the same round', () => {
  const rs = halfSet();
  assert.deepEqual(halfYears(rs, rs[0]), { h1: 11, h2: 18 });
});

test('halfYears ignores other rounds and other orgs', () => {
  const rs = halfSet().concat([
    rec({ org: 'BOK', indicator: 'emp_change', target_year: 2026, published_at: '2026-05-28',
      target_period: 'h1', value: 18, id: 'old' }),
    rec({ org: 'KDI', indicator: 'emp_change', target_year: 2026, published_at: '2026-08-27',
      target_period: 'h1', value: 11, id: 'other' }),
  ]);
  assert.deepEqual(halfYears(rs, rs[0]), { h1: 11, h2: 18 });
});

test('halfYears returns nulls when the org publishes annual figures only', () => {
  const only = [rec({ org: 'OECD', target_period: 'annual', value: 1.9 })];
  assert.deepEqual(halfYears(only, only[0]), { h1: null, h2: null });
});

test('halfYearLabel writes a dash for a half the org does not publish', () => {
  const only = [rec({ org: 'OECD', indicator: 'gdp_growth', value: 1.9, unit: '%' })];
  assert.equal(halfYearLabel(only, only[0]), '상반 - · 하반 -');
  const rs = halfSet();
  assert.equal(halfYearLabel(rs, rs[0]), '상반 11 · 하반 18');
});

test('halfYearLabel can carry the unit for the detail view', () => {
  const rs = halfSet();
  assert.equal(halfYearLabel(rs, rs[0], { unit: true }), '상반 11만명 · 하반 18만명');
  const only = [rec({ org: 'OECD', indicator: 'gdp_growth', value: 1.9, unit: '%' })];
  assert.equal(halfYearLabel(only, only[0], { unit: true }), '상반 - · 하반 -');
});

test('halfYears keeps halves whose value did not change since an earlier round', () => {
  // 수집기는 직전 회차와 값이 같은 반기를 다시 저장하지 않는다(drop_unchanged).
  // 발표일이 정확히 같은 것만 찾으면, 기관이 실제로 낸 반기가 미발표로 지워진다.
  const rs = [
    rec({ org: 'BOK', indicator: 'emp_rate', target_year: 2027, unit: '%',
      published_at: '2026-05-28', target_period: 'h1', value: 62.8, id: 'h1-may' }),
    rec({ org: 'BOK', indicator: 'emp_rate', target_year: 2027, unit: '%',
      published_at: '2026-05-28', target_period: 'h2', value: 63.3, id: 'h2-may' }),
    rec({ org: 'BOK', indicator: 'emp_rate', target_year: 2027, unit: '%',
      published_at: '2026-08-27', target_period: 'annual', value: 63.0, id: 'annual-aug' }),
  ];
  const annual = rs[2];
  assert.deepEqual(halfYears(rs, annual), { h1: 62.8, h2: 63.3 });
  assert.equal(halfYearLabel(rs, annual), '상반 62.8 · 하반 63.3');
});

test('halfYears does not borrow halves published after the round', () => {
  // 5월호 카드에 8월호 반기가 새어 들어오면 회차 스냅샷이 아니게 된다.
  const rs = [
    rec({ org: 'BOK', indicator: 'emp_rate', target_year: 2027, unit: '%',
      published_at: '2026-05-28', target_period: 'annual', value: 63.1, id: 'annual-may' }),
    rec({ org: 'BOK', indicator: 'emp_rate', target_year: 2027, unit: '%',
      published_at: '2026-08-27', target_period: 'h1', value: 62.8, id: 'h1-aug' }),
  ];
  assert.deepEqual(halfYears(rs, rs[0]), { h1: null, h2: null });
});

test('fmtNumber pins percent figures to one decimal', () => {
  assert.equal(fmtNumber(63, '%'), '63.0');
  assert.equal(fmtNumber(62.9, '%'), '62.9');
  assert.equal(fmtNumber(2, '%p'), '2.0');
});

test('fmtNumber leaves 만명 counts as published', () => {
  assert.equal(fmtNumber(20, '만명'), '20');
  assert.equal(fmtNumber(12.3, '만명'), '12.3');
});

test('fmtDelta pins a whole-number percent revision to one decimal', () => {
  // 카드가 63.0% 인데 옆의 수정폭이 +1%p 면 정밀도가 달라 보인다
  assert.deepEqual(fmtDelta(rec({ revision: 1, unit: '%' })), { dir: 'up', text: '+1.0%p' });
  assert.deepEqual(fmtDelta(rec({ revision: -2, unit: '%' })), { dir: 'down', text: '-2.0%p' });
});

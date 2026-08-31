import { test } from 'node:test';
import assert from 'node:assert/strict';
import { monthOptions, overviewCards, fmtLevel, fmtDelta, deltaTone, monthLabel, esc, segmentsOf, breakdownMatrix, categoryTimeline, sheetData, EMPTY_LABEL, emptyLabel } from '../../app/js/data.js';

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
  // 카드는 조회한 달(period)과 그 출처의 최신 달(fallback.period)을 모두 들고 있어야
  // 한다. 이 둘이 다른 것 자체가 "미발표" 카드가 존재하는 이유다 — period가 없으면
  // 화면이 fallback.period를 잘못 "선택월"로 표시하는 사고가 난다.
  assert.equal(est.period, '2026-07');
  assert.equal(est.fallback.period, '2026-06');
  assert.equal(cards[0].state, 'value');
  assert.equal(cards[0].period, '2026-07');
  assert.equal(cards[0].fallback, null);
});

test('a card whose record has no yoy is noDelta, not a +0.0만명 increase', () => {
  // 실제 사례: 사업체노동력조사 total 은 2024-01~12 의 yoy 가 null 인데
  // 그 달들이 월 스위처에서 선택 가능하다. state 를 'value' 로 못박으면
  // 화면이 fmtDelta(null) 을 `0.0만명 증가` 로 그려 없는 숫자를 지어낸다.
  const series = [
    rec({ source: 'eaps', period: '2024-08', value: 28800.8, yoy: 122.8 }),
    rec({ source: 'est', period: '2024-08', value: 20419.1, yoy: null }),
    rec({ source: 'ei', period: '2024-08', value: 15445.0, yoy: 220.0 }),
  ];
  const est = overviewCards(series, SOURCES, '2024-08')[1];
  assert.equal(est.state, 'noDelta');
  assert.equal(est.value, 20419.1);   // 수준은 그대로 있다 — 없는 것은 증감뿐이다
  assert.equal(est.yoy, null);
  assert.equal(est.fallback, null);
  // 같은 사실을 시트는 이미 `― 증감없음` 으로 그린다. 두 화면이 한 사실에
  // 다른 답을 주면 안 된다.
  assert.equal(sheetData(series, { period: '2024-08' }).snapshot[1].state, 'noDelta');
});

test('an unpublished card carries the state of its fallback month too', () => {
  const series = [
    rec({ source: 'est', period: '2024-08', value: 20419.1, yoy: null }),
  ];
  const est = overviewCards(series, SOURCES, '2026-07')[1];
  assert.equal(est.state, 'unpublished');
  assert.equal(est.fallback.state, 'noDelta');
});

test('formatters convert 천명 to 만명', () => {
  assert.equal(fmtLevel(29136.1), '2,913.6만명');
  assert.equal(fmtDelta(107.6), '+10.8만명');
  assert.equal(fmtDelta(-57.2), '-5.7만명');
  assert.equal(fmtDelta(0), '0.0만명');
  assert.equal(monthLabel('2026-07'), '2026.07');
  assert.equal(esc('<b>&'), '&lt;b&gt;&amp;');
});

const INDUSTRIES = [
  { code: 'A', name_ko: '농업, 임업 및 어업', provided: { eaps: true, est: false, ei: true } },
  { code: 'C', name_ko: '제조업', provided: { eaps: true, est: true, ei: true } },
];
const SEGMENTS = [
  { breakdown: 'sex', name_ko: '성별', categories: [
    { code: 'M', name_ko: '남자', provided: { eaps: true, est: false, ei: true } },
    { code: 'F', name_ko: '여자', provided: { eaps: true, est: false, ei: true } },
  ] },
];

test('segmentsOf puts industry first and keeps the rest', () => {
  const segments = segmentsOf(INDUSTRIES, SEGMENTS);
  assert.deepEqual(segments.map(s => s.breakdown), ['industry', 'sex']);
  assert.equal(segments[0].name_ko, '산업별');
  assert.deepEqual(segments[0].categories.map(c => c.code), ['A', 'C']);
});

test('breakdownMatrix tells the four empty states apart', () => {
  const series = [
    // A: est 는 미제공, eaps 는 값, ei 는 그 달 미발표
    rec({ source: 'eaps', breakdown: 'industry', category: 'A', period: '2026-07', yoy: 11.5 }),
    rec({ source: 'ei', breakdown: 'industry', category: 'A', period: '2026-06', yoy: 3.0 }),
    // C: est 는 값이 있지만 증감을 낼 수 없다
    rec({ source: 'eaps', breakdown: 'industry', category: 'C', period: '2026-07', yoy: -20.1 }),
    rec({ source: 'est', breakdown: 'industry', category: 'C', period: '2026-07', yoy: null }),
    rec({ source: 'ei', breakdown: 'industry', category: 'C', period: '2026-07', yoy: 5.5 }),
  ];
  const rows = breakdownMatrix(series, INDUSTRIES, '2026-07', { sort: 'code', breakdown: 'industry' });
  assert.deepEqual(rows.map(r => r.code), ['A', 'C']);
  assert.deepEqual(rows[0].cells.est, { state: 'notProvided', yoy: null, value: null });
  assert.deepEqual(rows[0].cells.ei, { state: 'unpublished', yoy: null, value: null });
  assert.deepEqual(rows[0].cells.eaps, { state: 'value', yoy: 11.5, value: 29136.1 });
  // 값이 있는데 증감만 못 내는 칸은 수준을 지킨다 — 화면이 그 밑에 작게 적는다
  assert.deepEqual(rows[1].cells.est, { state: 'noDelta', yoy: null, value: 29136.1 });
});

test('breakdownMatrix sorts by delta magnitude, empty rows last', () => {
  const series = [
    rec({ source: 'eaps', breakdown: 'industry', category: 'A', period: '2026-07', yoy: 11.5 }),
    rec({ source: 'eaps', breakdown: 'industry', category: 'C', period: '2026-07', yoy: -200.3 }),
  ];
  const rows = breakdownMatrix(series, INDUSTRIES, '2026-07', { sort: 'delta', breakdown: 'industry' });
  assert.deepEqual(rows.map(r => r.code), ['C', 'A']);
});

test('breakdownMatrix works unchanged for sex', () => {
  const series = [
    rec({ source: 'eaps', breakdown: 'sex', category: 'M', period: '2026-07', yoy: 47.9 }),
    rec({ source: 'ei', breakdown: 'sex', category: 'M', period: '2026-07', yoy: 90.0 }),
  ];
  const rows = breakdownMatrix(series, SEGMENTS[0].categories, '2026-07', { sort: 'code', breakdown: 'sex' });
  assert.equal(rows[0].cells.est.state, 'notProvided');
  assert.equal(rows[0].cells.eaps.yoy, 47.9);
});

test('a sex row never picks up the industry record with the same code', () => {
  const series = [
    rec({ source: 'eaps', breakdown: 'industry', category: 'F', period: '2026-07', yoy: -57.1 }),
    rec({ source: 'eaps', breakdown: 'sex', category: 'F', period: '2026-07', yoy: 59.7 }),
    rec({ source: 'ei', breakdown: 'industry', category: 'M', period: '2026-07', yoy: 23 }),
    rec({ source: 'ei', breakdown: 'sex', category: 'M', period: '2026-07', yoy: 90 }),
  ];
  const sexCats = [
    { code: 'M', name_ko: '남자', provided: { eaps: true, est: false, ei: true } },
    { code: 'F', name_ko: '여자', provided: { eaps: true, est: false, ei: true } },
  ];
  const rows = breakdownMatrix(series, sexCats, '2026-07', { sort: 'code', breakdown: 'sex' });
  assert.equal(rows[1].cells.eaps.yoy, 59.7);   // 여자, not 건설업
  assert.equal(rows[0].cells.ei.yoy, 90);       // 남자, not 전문·과학·기술
});

test('categoryTimeline keeps the last N months per source, ascending', () => {
  const series = [];
  for (const m of [5, 6, 7]) {
    series.push(rec({ source: 'eaps', breakdown: 'industry', category: 'C', period: `2026-0${m}`, yoy: m }));
  }
  series.push(rec({ source: 'est', breakdown: 'industry', category: 'C', period: '2026-06', yoy: 1 }));
  const t = categoryTimeline(series, { breakdown: 'industry', category: 'C', months: 2 });
  assert.deepEqual(t.eaps.map(p => p.period), ['2026-06', '2026-07']);
  assert.deepEqual(t.est.map(p => p.period), ['2026-06']);
  assert.deepEqual(t.ei, []);
});

test('sheetData snapshot keeps every source in fixed order, notProvided included', () => {
  const series = [
    rec({ source: 'eaps', breakdown: 'sex', category: 'F', period: '2026-07', yoy: 59.7 }),
    rec({ source: 'ei', breakdown: 'sex', category: 'F', period: '2026-07', yoy: 188.0 }),
  ];
  const segments = [{ code: 'F', name_ko: '여자', provided: { eaps: true, est: false, ei: true } }];
  const d = sheetData(series, { period: '2026-07', breakdown: 'sex', category: 'F', categories: segments });
  assert.deepEqual(d.snapshot.map(s => s.source), ['eaps', 'est', 'ei']);
  assert.equal(d.snapshot[1].state, 'notProvided');
  assert.equal(d.snapshot[2].yoy, 188.0);
  // 수준도 같이 온다 — `표로 보기` 가 증감만 보여주면 대체 뷰가 원본보다 빈약해진다.
  assert.equal(d.snapshot[0].value, 29136.1);
  assert.equal(d.snapshot[1].value, null);
});

test('deltaTone gives zero a neutral token, not the increase colour', () => {
  assert.equal(deltaTone(12), 'is-up');
  assert.equal(deltaTone(-12), 'is-down');
  assert.equal(deltaTone(0), 'is-flat');
});

test('EMPTY_LABEL has one home and emptyLabel adds the placeholder dash', () => {
  assert.equal(EMPTY_LABEL.unpublished, '미발표');
  assert.equal(emptyLabel('unpublished'), '― 미발표');
  assert.equal(emptyLabel('notProvided'), '― 미제공');
  assert.equal(emptyLabel('value'), '―');
});

test('sheetData falls back to the total cut when no category is given', () => {
  const series = [
    rec({ source: 'eaps', breakdown: 'total', category: null, period: '2026-07', yoy: 107.6 }),
    rec({ source: 'ei', breakdown: 'total', category: null, period: '2026-07', yoy: 277.0 }),
    rec({ source: 'est', breakdown: 'total', category: null, period: '2026-06', yoy: 248.0 }),
  ];
  const d = sheetData(series, { period: '2026-07', breakdown: null, category: null });
  assert.equal(d.snapshot[0].yoy, 107.6);
  assert.equal(d.snapshot[1].state, 'unpublished');
  assert.equal(d.latest, '2026-07');
});

test('timeline always runs to the newest month even when an older month is selected', () => {
  const series = [
    rec({ source: 'eaps', breakdown: 'total', category: null, period: '2026-05', yoy: 1 }),
    rec({ source: 'eaps', breakdown: 'total', category: null, period: '2026-07', yoy: 3 }),
  ];
  const d = sheetData(series, { period: '2026-05', breakdown: null, category: null });
  assert.deepEqual(d.timeline.eaps.map(p => p.period), ['2026-05', '2026-07']);
});

test('matrix cells carry the level so the screen can show it under the delta', () => {
  const series = [
    rec({ source: 'eaps', breakdown: 'industry', category: 'C', period: '2026-07', value: 4327.4, yoy: -68.4 }),
  ];
  const rows = breakdownMatrix(series, INDUSTRIES, '2026-07', { sort: 'code', breakdown: 'industry' });
  const c = rows.find(r => r.code === 'C');
  assert.equal(c.cells.eaps.value, 4327.4);
  assert.equal(c.cells.eaps.yoy, -68.4);
  // 미제공은 수준도 없다 — 그 출처가 그 분류를 아예 안 잡는다
  assert.equal(c.cells.est.value, null);
});

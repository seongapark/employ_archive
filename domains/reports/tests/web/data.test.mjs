import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  dateLabel, monthKey, monthLabel, groupTimeline, filterReports, yearsOf, labelOf,
} from '../../app/js/data.js';

const BOARDS = [
  { id: 'kli-research', series: '연구보고서', collapse: true },
  { id: 'kli-brief', series: '고용노동브리프', collapse: false },
];

const many = (n, board, org = 'kli') =>
  Array.from({ length: n }, (_, i) => ({
    id: `${org}-${board}-${i}`,
    org,
    board,
    series: board === 'kli-research' ? '연구보고서' : '고용노동브리프',
    title: `제목${i}`,
    published: '2026-01-15',
    date_precision: 'day',
  }));

test('날짜는 정밀도보다 자세히 적지 않는다', () => {
  assert.equal(dateLabel('2025-12-03', 'day'), '2025.12.03');
  assert.equal(dateLabel('2025-12-31', 'month'), '2025.12');
  assert.equal(dateLabel('2025-12-31', 'year'), '2025년');
  assert.equal(dateLabel('', 'day'), '');
});

test('월 키로 끊는다', () => {
  assert.equal(monthKey('2026-08-27'), '2026-08');
  assert.equal(monthLabel('2026-08'), '2026년 8월');
});

test('같은 달·기관·시리즈가 기준을 넘으면 접는다', () => {
  const groups = groupTimeline(many(27, 'kli-research'), BOARDS, { min: 5 });
  const jan = groups.find((g) => g.month === '2026-01');
  assert.equal(jan.rows.length, 1);
  assert.equal(jan.rows[0].kind, 'collapsed');
  assert.equal(jan.rows[0].count, 27);
  assert.equal(jan.rows[0].label, 'KLI 연구보고서');
});

test('접힌 묶음을 펼치면 그 안이 보인다', () => {
  const rows = many(27, 'kli-research');
  const id = '2026-01|kli|연구보고서';
  const groups = groupTimeline(rows, BOARDS, { min: 5, expanded: new Set([id]) });
  const jan = groups.find((g) => g.month === '2026-01');
  assert.equal(jan.rows[0].open, true);
  assert.equal(jan.rows.filter((r) => r.kind === 'report').length, 27);
});

test('브리프류는 접지 않는다', () => {
  const groups = groupTimeline(many(27, 'kli-brief'), BOARDS, { min: 5 });
  const jan = groups.find((g) => g.month === '2026-01');
  assert.equal(jan.rows.length, 27);
  assert.ok(jan.rows.every((r) => r.kind === 'report'));
});

test('기준 이하면 접기 대상이라도 펼친다', () => {
  const groups = groupTimeline(many(4, 'kli-research'), BOARDS, { min: 5 });
  assert.equal(groups[0].rows.length, 4);
});

test('달이 다르면 따로 센다', () => {
  const rows = [...many(4, 'kli-research')];
  const older = many(4, 'kli-research').map((r) => ({ ...r, id: `x${r.id}`, published: '2025-12-01' }));
  const groups = groupTimeline([...rows, ...older], BOARDS, { min: 5 });
  assert.deepEqual(groups.map((g) => g.month), ['2026-01', '2025-12']);
});

test('기관 칩과 연도 칩이 함께 걸린다', () => {
  const rows = [
    { id: 'a', org: 'kli', published: '2026-01-01' },
    { id: 'b', org: 'kdi', published: '2026-01-01' },
    { id: 'c', org: 'kli', published: '2022-01-01' },
  ];
  assert.deepEqual(filterReports(rows, { orgs: ['kli'], years: [2026] }).map((r) => r.id), ['a']);
  assert.equal(filterReports(rows, { orgs: [], years: [] }).length, 3);
  assert.deepEqual(yearsOf(rows), [2026, 2022]);
});

test('접힘 라벨은 기관 코드를 대문자로 올린 것이다', () => {
  assert.equal(labelOf({ org: 'keis', series: '고용이슈' }), 'KEIS 고용이슈');
});

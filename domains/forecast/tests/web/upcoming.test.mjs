import { test } from 'node:test';
import assert from 'node:assert/strict';
import { upcomingGroups, whenText, nextEntry, renderList } from '../../app/js/screens/upcoming.js';

const ENTRIES = [
  { org: 'IMF', org_name_ko: 'IMF', report: '세계경제전망', start: '2026-10-11', end: '2026-10-25', date: null, basis: '예상' },
  { org: 'BOK', org_name_ko: 'BOK', report: '경제전망보고서', start: '2026-11-25', end: '2026-12-01', date: '2026-11-26', basis: '공지' },
  { org: 'KDI', org_name_ko: 'KDI', report: '경제전망(하반기)', start: '2026-11-08', end: '2026-11-15', date: null, basis: '예상' },
  { org: 'OECD', org_name_ko: 'OECD', report: '경제전망', start: '2026-11-29', end: '2026-12-07', date: null, basis: '예상' },
];

test('a dated round shows its day, an expected one only the part of the month', () => {
  assert.equal(whenText(ENTRIES[1]), '11.26');
  // 구간의 가운데 날로 초(1~10일)·중순(11~20일)·말(21일~)을 정한다
  assert.equal(whenText(ENTRIES[0]), '10월 중순');                 // 10.11~10.25 → 18일
  assert.equal(whenText(ENTRIES[3]), '12월 초');                   // 11.29~12.07 → 3일
  assert.equal(whenText({ start: '2027-02-22', end: '2027-03-01' }), '2월 말');
});

test('rounds are grouped by month in order of their day or window start', () => {
  const groups = upcomingGroups(ENTRIES);
  // OECD(11.29~12.07)는 가운데 날이 12월이라 12월에 묶인다
  assert.deepEqual(groups.map(g => g.month), ['2026년 10월', '2026년 11월', '2026년 12월']);
  assert.deepEqual(groups[1].entries.map(e => e.org), ['KDI', 'BOK']);
});

test('the banner points at the nearest round that has not passed', () => {
  assert.equal(nextEntry(ENTRIES, '2026-10-02').org, 'IMF');
  // 구간이 이미 지났으면 다음 회차로 넘어간다
  assert.equal(nextEntry(ENTRIES, '2026-10-26').org, 'KDI');
  assert.equal(nextEntry([], '2026-10-02'), null);
});

test('the list says which dates are announced and which are expected', () => {
  const html = renderList(ENTRIES);
  assert.equal((html.match(/>공지</g) || []).length, 1);
  assert.equal((html.match(/>예상</g) || []).length, 3);
  assert.ok(html.includes('경제전망(하반기)'));
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { groupByAxis, render } from '../../app/js/screens/picks.js';

const REPORTS = [
  { id: 'a', org: 'bok', title: 'ㄱ', published: '2026-01-01' },
  { id: 'b', org: 'bok', title: 'ㄴ', published: '2026-03-01' },
  { id: 'c', org: 'kli', title: 'ㄷ', published: '2026-02-01' },
];

test('축은 건수 순, 축 안은 최신 순', () => {
  const picks = {
    a: { pick: true, axis: '청년 고용', why: 'ㄱ' },
    b: { pick: true, axis: '청년 고용', why: 'ㄴ' },
    c: { pick: true, axis: '임금·근로조건', why: 'ㄷ' },
  };
  const got = groupByAxis(REPORTS, picks);
  assert.deepEqual(got.map((g) => g.axis), ['청년 고용', '임금·근로조건']);
  assert.deepEqual(got[0].rows.map((r) => r.id), ['b', 'a']);
});

test('고르지 않은 보고서는 없다', () => {
  const picks = { a: { pick: false, axis: '', why: '무관' } };
  assert.deepEqual(groupByAxis(REPORTS, picks), []);
});

test('이유가 행에 실려 온다', () => {
  const picks = { a: { pick: true, axis: '청년 고용', why: '경력 사다리 분해' } };
  assert.equal(groupByAxis(REPORTS, picks)[0].rows[0].why, '경력 사다리 분해');
});

test('추천이 아직 없어도 죽지 않는다', () => {
  assert.deepEqual(groupByAxis(REPORTS, undefined), []);
  assert.deepEqual(groupByAxis(undefined, {}), []);
});

test('축마다 최신 3건만 내놓고, 나머지는 건수로 알린다', () => {
  const reports = Array.from({ length: 5 }, (_, i) => ({
    id: `x${i}`, org: 'bok', title: `제목${i}`, published: `2026-0${i + 1}-01`,
  }));
  const picks = Object.fromEntries(
    reports.map((r) => [r.id, { pick: true, axis: '청년 고용', why: 'ㄱ' }]),
  );
  const el = { innerHTML: '' };
  render(el, { reports, picks });
  const shown = reports.filter((r) => el.innerHTML.includes(r.title)).map((r) => r.id);
  assert.deepEqual(shown, ['x2', 'x3', 'x4']);  // 최신 3건만, 옛것 둘은 없다
  assert.match(el.innerHTML, /그 밖 2건/);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  esc, roundOf, dayLabel, timeLabel, daysSince, scale,
  filterArticles, youthShare, citeRate,
} from '../../app/js/data.js';

const ROUNDS = [
  {
    release: '2026-09-07', label: "'26.8월분",
    regular: { cited: 73, kept: 81, press: 59 },
    coverage: { age: [{ name: '29세이하·청년', n: 13 }] },
  },
  {
    release: '2026-07-13', label: "'26.6월분",
    regular: { cited: 45, kept: 56, press: 40 },
    coverage: { age: [{ name: '29세이하·청년', n: 16 }] },
  },
];

const ARTS = [
  { title: '고용보험 가입자 27만8천명 증가', cites: true },
  { title: '반등이라 부르기 이른 제조업', cites: true },
  { title: '육아휴직 급여 상한 심의', cites: false },
];

test('esc는 제목 속 꺾쇠를 막는다 — 기사 제목은 외부 입력이다', () => {
  assert.equal(esc('<b>"고용"</b>'), '&lt;b&gt;&quot;고용&quot;&lt;/b&gt;');
});

test('roundOf는 못 찾으면 첫 회차로 떨어진다 — 빈 화면보다 낫다', () => {
  assert.equal(roundOf(ROUNDS, '2026-07-13').label, "'26.6월분");
  assert.equal(roundOf(ROUNDS, '없는날짜').label, "'26.8월분");
  assert.equal(roundOf([], 'x'), null);
});

test('dayLabel·timeLabel은 하루 안의 순서까지 보여준다', () => {
  assert.equal(dayLabel('2026-09-07'), '09.07');
  assert.equal(timeLabel('2026-09-07 17:02'), '09.07 17:02');
  assert.equal(timeLabel('2026-09-07'), '09.07');
  assert.equal(timeLabel(''), '');
});

test('daysSince는 배포일 기준 며칠째인지 센다', () => {
  assert.equal(daysSince('2026-09-07', '2026-09-07'), 0);
  assert.equal(daysSince('2026-09-07', '2026-09-22'), 15);
  assert.equal(daysSince('', '2026-09-22'), null);
  assert.equal(daysSince('2026-09-07', '망가진값'), null);
});

test('scale은 축 안에서만 비교한다 — 최댓값이 100%', () => {
  const rows = scale([{ name: 'a', n: 56 }, { name: 'b', n: 28 }, { name: 'c', n: 0 }]);
  assert.deepEqual(rows.map((r) => r.pct), [100, 50, 0]);
});

test('scale은 전부 0이어도 나누기로 죽지 않는다', () => {
  assert.deepEqual(scale([{ name: 'a', n: 0 }]).map((r) => r.pct), [0]);
});

test('filterArticles: 인용만 보기와 프레임 필터가 함께 걸린다', () => {
  assert.equal(filterArticles(ARTS).length, 2);
  assert.equal(filterArticles(ARTS, { onlyCited: false }).length, 3);
  assert.equal(filterArticles(ARTS, { kw: '반등' }).length, 1);
  assert.equal(filterArticles(ARTS, { onlyCited: false, kw: '급여' }).length, 1);
});

test('youthShare·citeRate는 인용 기사를 분모로 쓴다', () => {
  assert.equal(youthShare(ROUNDS[0]), 18);   // 13 / 73
  assert.equal(citeRate(ROUNDS[0]), 90);     // 73 / 81
});

test('인용 기사가 0건이어도 비율이 NaN 이 되지 않는다', () => {
  const empty = { regular: { cited: 0, kept: 0 }, coverage: { age: [] } };
  assert.equal(youthShare(empty), 0);
  assert.equal(citeRate(empty), 0);
});

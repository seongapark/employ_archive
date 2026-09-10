import { test } from 'node:test';
import assert from 'node:assert/strict';
import { barGeometry } from '../../app/js/screens/home.js';

// 이 그래프가 존재하는 이유 자체가 축 규칙이다. 규칙이 무너지면 그래프는
// 틀린 말을 하지 (비어 보이지) 않으므로, 눈으로는 못 잡는다.

test('취업자 증감은 0 을 기준선으로 잡는다', () => {
  const geo = barGeometry('emp_change', [21, 20.5, 14.6, 14, 11]);
  assert.equal(geo.signed, true);
  assert.equal(geo.zeroAt, 0);
  // 최댓값이 축 전체, 나머지는 그에 비례 — 길이를 값으로 읽어도 되는 축이다
  assert.equal(geo.fractions[0], 1);
  assert.ok(Math.abs(geo.fractions[4] - 11 / 21) < 1e-9);
});

test('취업자 증감에 음수가 섞이면 기준선이 그림 안으로 들어온다', () => {
  const geo = barGeometry('emp_change', [20, -5]);
  assert.equal(geo.signed, true);
  // 축은 -5~20 이므로 0 은 바닥에서 1/5 지점
  assert.ok(Math.abs(geo.zeroAt - 0.2) < 1e-9);
  assert.ok(geo.fractions[1] < 0, '음수 막대는 기준선 아래로 뻗어야 한다');
});

test('비율 지표는 0 이 아니라 최저~최고에 축을 맞춘다', () => {
  // 실측값: 2026년 실업률 여섯 기관
  const geo = barGeometry('unemp_rate', [2.9, 2.9, 2.9, 2.8, 2.8, 2.8]);
  assert.equal(geo.signed, false);
  assert.equal(geo.fractions[0], 1);
  // 0 기준이었다면 0.966 이라 눈으로 구별이 안 된다. 축을 좁혀 차이를 벌린다.
  assert.ok(geo.fractions[5] < 0.5, `최저 막대가 ${geo.fractions[5]} — 너무 길어 차이가 안 보인다`);
});

test('비율 지표의 최저 기관도 막대가 남는다', () => {
  const geo = barGeometry('gdp_growth', [3.3, 3.2, 2.6, 2.5, 1.9]);
  // 바닥에 딱 붙으면 0 이 되어 '자료 없음'처럼 보인다
  assert.ok(geo.fractions[4] > 0.15, `최저 막대가 ${geo.fractions[4]} — 사라진 것처럼 보인다`);
});

test('전 기관이 같은 값이면 없는 차이를 그리지 않는다', () => {
  const geo = barGeometry('cpi', [2.5, 2.5, 2.5]);
  assert.deepEqual(geo.fractions, [0.5, 0.5, 0.5]);
});

test('기관이 하나뿐이어도 죽지 않는다', () => {
  assert.deepEqual(barGeometry('cpi', [2.5]).fractions, [0.5]);
  assert.equal(barGeometry('emp_change', [12]).fractions[0], 1);
});

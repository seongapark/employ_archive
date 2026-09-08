import { test } from 'node:test';
import assert from 'node:assert/strict';
import { verify, extractNumbers, numbersInText } from '../../worker/src/core/verify.mjs';
import { buildEvidence } from '../../worker/src/core/query.mjs';

const 근거 = [buildEvidence({ 지표: 'IND_청년사무직취업자', compare_basis: '수준' },
  [{ 기간: '2025S1', 값: 744.3 }, { 기간: '2025S2', 값: 727.4 }])];

test('숫자를 부호와 소수점까지 뽑는다', () => {
  assert.deepEqual(extractNumbers('744.3에서 727.4로 −16.9천명(-2.3%)'),
    [744.3, 727.4, -16.9, -2.3]);
});

test('연도와 기간 표기는 숫자로 세지 않는다', () => {
  // 2025S1·2026-07 같은 기간 토큰까지 대조하면 정상 답변이 전부 튕긴다
  assert.deepEqual(extractNumbers('2025S1 대비 2025S2 는 727.4천명'), [727.4]);
});

test('집단 라벨은 숫자로 세지 않는다 — 값이 아니라 이름이다', () => {
  // 카테고리를 정확히 집어도 답변이 "30대 취업자" 라고 쓰면 30 이 잡히던 자리
  assert.deepEqual(extractNumbers('30대 취업자는 600천명이다'), [600]);
  assert.deepEqual(extractNumbers('30~39세 취업자는 600천명'), [600]);
  assert.deepEqual(extractNumbers('30-39세 취업자는 600천명'), [600]);
  assert.deepEqual(extractNumbers('15세 이상 인구 중 600천명'), [600]);
  assert.deepEqual(extractNumbers('65세 미만 600천명'), [600]);
  const 근거600 = [buildEvidence({ 지표: 'X', compare_basis: '수준' },
    [{ 기간: '2026-07', 값: 600 }])];
  assert.equal(verify({ 답변: '30대 취업자는 600천명이다', 근거: [] }, 근거600).ok, true);
  assert.equal(verify({ 답변: '15세 이상 30~39세는 600천명', 근거: [] }, 근거600).ok, true);
});

test('시점 라벨도 숫자로 세지 않는다 — 월·분기·반기·년', () => {
  // 2026-07 을 가리면서 7월만 안 가리는 건 일관성이 없다. 월도 좌표지 값이 아니다.
  assert.deepEqual(extractNumbers('7월 취업자는 600천명이다'), [600]);
  assert.deepEqual(extractNumbers('2026년 7월'), []);          // 두 패턴이 겹쳐도 전부 가려진다
  assert.deepEqual(extractNumbers('2026-07 과 12월'), []);
  assert.deepEqual(extractNumbers('3분기'), []);
  assert.deepEqual(extractNumbers('4반기 연속 감소'), []);
  assert.deepEqual(extractNumbers('3년 연속 증가'), []);       // PERIOD 는 4자리 연도만 문다
  const 근거600 = [buildEvidence({ 지표: 'X', compare_basis: '수준' },
    [{ 기간: '2026-07', 값: 600 }])];
  // 허용텍스트 없이 통과한다
  assert.equal(verify({ 답변: '2026년 7월 3분기 4반기 연속 600천명', 근거: [] }, 근거600).ok, true);
});

test('소수의 뒷자리가 라벨로 먹히지 않는다', () => {
  // 가드가 없으면 1.5년 이 '5년' 만 가려져 1 이 남고, 원래 값 1.5 가 사라진다
  assert.deepEqual(extractNumbers('1.5년'), [1.5]);
  assert.deepEqual(extractNumbers('2.3대'), [2.3]);
  assert.deepEqual(extractNumbers('-2.3% 와 7월'), [-2.3]);
});

test('집단 라벨을 가려도 측정값은 그대로 잡힌다 — 단위가 붙은 숫자는 안 가린다', () => {
  // 마스킹을 넓히면서 환각 방어에 구멍을 내지 않았음을 증명하는 회귀 테스트다
  const 근거600 = [buildEvidence({ 지표: 'X', compare_basis: '수준' },
    [{ 기간: '2026-07', 값: 600 }])];
  const r = verify({ 답변: '30대 취업자는 700천명이다', 근거: [] }, 근거600);
  assert.equal(r.ok, false);
  assert.deepEqual(r.위반, [700]);
  // 시점 라벨을 가려도 마찬가지다
  assert.deepEqual(verify({ 답변: '7월 취업자는 700천명이다', 근거: [] }, 근거600).위반, [700]);
  // 건·% 도 그대로 잡힌다
  assert.deepEqual(extractNumbers('30대 구인 1200건, 전년비 -2.3%'), [1200, -2.3]);
  assert.deepEqual(extractNumbers('2026년 7월 3분기 1200건 -2.3%'), [1200, -2.3]);
  assert.deepEqual(verify({ 답변: '30대는 -2.3% 줄었다', 근거: [] }, 근거600).위반, [-2.3]);
});

test('파생값을 쓴 답변은 통과한다', () => {
  const r = verify({ 답변: '744.3천명에서 727.4천명으로 -16.9천명(-2.3%) 줄었다', 근거: [] }, 근거);
  assert.equal(r.ok, true);
});

test('근거에 없는 숫자가 하나라도 섞이면 실패한다', () => {
  const r = verify({ 답변: '744.3천명에서 700.0천명으로 줄었다', 근거: [] }, 근거);
  assert.equal(r.ok, false);
  assert.deepEqual(r.위반, [700]);
});

test('근거 배열 안의 값도 대조한다', () => {
  const r = verify({ 답변: '줄었다', 근거: [{ 지표: 'X', 값: 999 }] }, 근거);
  assert.equal(r.ok, false);
  assert.deepEqual(r.위반, [999]);
});

test('증감률만 지표는 수준값을 쓰면 실패한다', () => {
  // 관측을 아예 안 넘기므로 744.3 은 근거 집합에 없다
  const 증감만 = [buildEvidence({ 지표: 'IND_KGJ피보험자', compare_basis: '증감률만' },
    [{ 기간: '2025S1', 값: 744.3 }, { 기간: '2025S2', 값: 727.4 }])];
  const r = verify({ 답변: '744.3천명이다', 근거: [] }, 증감만);
  assert.equal(r.ok, false);
});

// 우리가 LLM 에게 준 문장(근거서술 등)을 그대로 인용한 답변은 환각이 아니다.
// domains/ask/data/ontology.json 의 실제 근거서술 문구.
const 근거서술 = '2023하 818.3천명 → 2025하 727.4천명, 4반기 연속 감소';

test('허용텍스트에 준 문장을 인용하면 통과한다', () => {
  // 근거서술이 인용한 수준값(818.3)은 근거묶음(744.3·727.4)에 없다 — 허용텍스트가 받는다.
  // ('4반기' 는 이제 라벨로 마스킹되므로 허용텍스트가 필요한 문장이 못 된다)
  const r = verify({ 답변: '818.3천명에서 727.4천명으로 줄었다', 근거: [] }, 근거, [근거서술]);
  assert.equal(r.ok, true);
});

test('허용텍스트를 안 주면 같은 답변이 실패한다 — 넓힘은 명시적이다', () => {
  const r = verify({ 답변: '818.3천명에서 727.4천명으로 줄었다', 근거: [] }, 근거);
  assert.equal(r.ok, false);
  assert.deepEqual(r.위반, [818.3]);
});

test('반기 개수는 라벨이라 허용텍스트 없이도 통과한다', () => {
  // "4반기 연속" 의 4 는 기간을 세는 라벨이지 측정값이 아니다
  assert.equal(verify({ 답변: '4반기 연속 감소했다', 근거: [] }, 근거).ok, true);
});

test('허용텍스트를 줘도 거기 없는 숫자는 여전히 위반이다', () => {
  const r = verify({ 답변: '818.3천명이 아니라 999.9천명으로 감소했다', 근거: [] }, 근거, [근거서술]);
  assert.equal(r.ok, false);
  assert.deepEqual(r.위반, [999.9]);
});

test('numbersInText 도 기간 토큰은 숫자로 세지 않는다', () => {
  // 2023하·2025하 는 기간, '4반기' 는 시점 라벨 — 남는 것은 측정값 둘뿐이다
  assert.deepEqual([...numbersInText([근거서술])].sort((a, b) => a - b),
    [727.4, 818.3]);
});

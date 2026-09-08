import { test } from 'node:test';
import assert from 'node:assert/strict';
import { derive, buildEvidence, numbersIn } from '../../worker/src/core/query.mjs';

const 관측 = [{ 기간: '2025S1', 값: 744.3 }, { 기간: '2025S2', 값: 727.4 }]; // 시계열
const 횡단면관측 = [{ 기간: '2026-07', 값: 100 }, { 기간: '2026-07', 값: 300 }]; // 같은 기간, 여러 계열

test('차이와 증감률을 계산한다', () => {
  const d = derive(관측, { compare_basis: '수준' });
  assert.equal(d.차이, -16.9);
  assert.equal(d.증감률, -2.3);
  assert.equal(d.기준기간, '2025S1→2025S2');
});

test('반올림 오차를 남기지 않는다', () => {
  // 744.3 - 727.4 는 부동소수점에서 16.900000000000034 가 된다
  const d = derive(관측, { compare_basis: '수준' });
  assert.equal(String(d.차이), '-16.9');
});

test('횡단면에는 합계·비중이 있고 차이·증감률·기여도는 없다', () => {
  // 같은 기간의 두 계열(예: 20대와 40대)에서 "차이 200 / 증감률 200%" 를 만들면
  // 아무 뜻 없는 숫자가 numbersIn 을 타고 허용 집합에 들어가, LLM 이 그걸 인용해도
  // verify 가 통과시킨다. 기여도(=차이/전체)도 같은 이유로 만들지 않는다.
  const d = derive(횡단면관측, { compare_basis: '수준', 전체: 800 });
  assert.equal(d.합계, 400);
  assert.equal(d.비중, 50);
  assert.equal('차이' in d, false);
  assert.equal('증감률' in d, false);
  assert.equal('기여도' in d, false);
});

test('시계열에는 기여도가 있다 — 변화의 기여도만 뜻이 있다', () => {
  const d = derive(관측, { compare_basis: '수준', 전체: 800 });
  assert.equal(d.차이, -16.9);
  assert.equal(d.기여도, -2.1); // 차이(-16.9)/전체(800)*100
  assert.equal('합계' in d, false);
});

test('혼합(계열 × 기간)에는 합계도 차이도 만들지 않는다', () => {
  const 혼합 = [
    { 기간: '2026-06', 값: 100 }, { 기간: '2026-06', 값: 200 },
    { 기간: '2026-07', 값: 110 }, { 기간: '2026-07', 값: 190 },
  ];
  const d = derive(혼합, { compare_basis: '수준' });
  assert.equal('합계' in d, false);
  assert.equal('차이' in d, false);
  assert.equal('증감률' in d, false);
});

test('관측이 하나면 차이를 만들지 않는다', () => {
  const d = derive([{ 기간: '2026-07', 값: 1 }], { compare_basis: '수준' });
  assert.equal('차이' in d, false);
  assert.equal('증감률' in d, false);
  assert.equal(d.합계, 1); // 관측 하나는 횡단면이다
});

test('시계열 관측(기간이 서로 다름)에는 합계가 없다', () => {
  const d = derive(관측, { compare_basis: '수준' });
  assert.equal('합계' in d, false);
});

test('횡단면 관측(기간이 모두 같음)에는 합계가 있다', () => {
  const d = derive(횡단면관측, { compare_basis: '수준' });
  assert.equal(d.합계, 400);
});

test('단위를 넘기면 파생에 그대로 실리고, 안 넘기면 단위 키가 없다', () => {
  const withUnit = derive(관측, { compare_basis: '수준', 단위: '건' });
  assert.equal(withUnit.단위, '건');
  const noUnit = derive(관측, { compare_basis: '수준' });
  assert.equal('단위' in noUnit, false); // '천명' 을 지어내지 않는다
});

test('증감률만 지표는 관측 배열을 아예 싣지 않는다', () => {
  // 비교 금지가 프롬프트 훈계가 아니라 넘기지 않는 데이터로 강제된다
  const e = buildEvidence({ 지표: 'IND_KGJ피보험자', compare_basis: '증감률만' }, 관측);
  assert.equal(e.관측, undefined);
  assert.equal(e.파생.증감률, -2.3);
  assert.equal(e.파생.차이, undefined);
});

test('증감률만 지표는 차이·합계·비중·기여도가 모두 없고 증감률만 남는다', () => {
  // 전체 를 줘서 합계·비중·기여도가 계산될 조건을 일부러 만든 뒤, 그래도 지워지는지 본다.
  // 기여도(=차이/전체*100)를 남기면 전체를 아는 쪽이 차이를 역산해 수준값이 샌다.
  // 시계열로 둔다 — 횡단면이면 차이·기여도가 애초에 안 만들어져 지워지는지를 못 본다.
  const e = buildEvidence({ 지표: 'IND_KGJ피보험자', compare_basis: '증감률만' }, 관측, { 전체: 800 });
  assert.equal(e.파생.차이, undefined);
  assert.equal(e.파생.합계, undefined);
  assert.equal(e.파생.비중, undefined);
  assert.equal(e.파생.기여도, undefined);
  assert.equal(e.파생.증감률, -2.3);
});

test('수준 지표는 관측과 파생을 모두 싣는다', () => {
  const e = buildEvidence({ 지표: 'IND_청년사무직취업자', compare_basis: '수준' }, 관측);
  assert.equal(e.관측.length, 2);
  assert.equal(e.파생.차이, -16.9);
});

test('rse 가 없으면 유의성은 불명이다', () => {
  const e = buildEvidence({ 지표: 'X', compare_basis: '수준' }, 관측);
  assert.equal(e.유의성, '불명');
  assert.match(e.유의성사유, /RSE/);
});

test('numbersIn 은 관측과 파생을 모두 모은다', () => {
  const e = buildEvidence({ 지표: 'X', compare_basis: '수준' }, 관측);
  const s = numbersIn([e]);
  assert.ok(s.has(744.3) && s.has(727.4) && s.has(-16.9) && s.has(-2.3));
});

test('numbersIn 은 시계열 관측에서 합계를 근거 집합에 넣지 않는다', () => {
  // 744.3 + 727.4 = 1471.7 은 통계적으로 의미 없는 숫자라 근거 집합에 있으면 안 된다
  const e = buildEvidence({ 지표: 'X', compare_basis: '수준' }, 관측);
  const s = numbersIn([e]);
  assert.equal(s.has(1471.7), false);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { derive, buildEvidence, numbersIn } from '../../worker/src/core/query.mjs';

const 관측 = [{ 기간: '2025S1', 값: 744.3 }, { 기간: '2025S2', 값: 727.4 }];

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

test('합계·비중·기여도를 계산한다', () => {
  const d = derive([{ 기간: '2026-07', 값: 100 }, { 기간: '2026-07', 값: 300 }],
                   { compare_basis: '수준', 전체: 800 });
  assert.equal(d.합계, 400);
  assert.equal(d.비중, 50);
});

test('관측이 하나면 차이를 만들지 않는다', () => {
  assert.equal(derive([{ 기간: '2026-07', 값: 1 }], { compare_basis: '수준' }).차이, null);
});

test('증감률만 지표는 관측 배열을 아예 싣지 않는다', () => {
  // 비교 금지가 프롬프트 훈계가 아니라 넘기지 않는 데이터로 강제된다
  const e = buildEvidence({ 지표: 'IND_KGJ피보험자', compare_basis: '증감률만' }, 관측);
  assert.equal(e.관측, undefined);
  assert.equal(e.파생.증감률, -2.3);
  assert.equal(e.파생.차이, undefined);
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

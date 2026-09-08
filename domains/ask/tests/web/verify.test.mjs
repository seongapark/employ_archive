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
  const r = verify({ 답변: '4반기 연속 감소했다', 근거: [] }, 근거, [근거서술]);
  assert.equal(r.ok, true);
});

test('허용텍스트를 안 주면 같은 답변이 실패한다 — 넓힘은 명시적이다', () => {
  const r = verify({ 답변: '4반기 연속 감소했다', 근거: [] }, 근거);
  assert.equal(r.ok, false);
  assert.deepEqual(r.위반, [4]);
});

test('허용텍스트를 줘도 거기 없는 숫자는 여전히 위반이다', () => {
  const r = verify({ 답변: '4반기 연속 999.9천명으로 감소했다', 근거: [] }, 근거, [근거서술]);
  assert.equal(r.ok, false);
  assert.deepEqual(r.위반, [999.9]);
});

test('numbersInText 도 기간 토큰은 숫자로 세지 않는다', () => {
  assert.deepEqual([...numbersInText([근거서술])].sort((a, b) => a - b),
    [4, 727.4, 818.3]);
});

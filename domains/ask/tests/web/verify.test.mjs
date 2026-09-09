import { test } from 'node:test';
import assert from 'node:assert/strict';
import { verify, extractNumbers, numbersInText } from '../../worker/src/core/verify.mjs';
import { 숫자모음 } from '../../worker/src/core/query.mjs';
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

// ── 천 단위 구분자 (2026-09-09 실측 오탐) ────────────────────────────────
// 라이브에서 근거값이 29151 인데 LLM 이 `29,151` 이라고 써서 위반 [29, 151] 이
// 잡혔다. 정상 답변이 통째로 버려지던 경로다.

test('쉼표로 끊어 쓴 수는 한 숫자로 읽는다', () => {
  assert.deepEqual(extractNumbers('취업자는 29,151천명이다'), [29151]);
});

test('쉼표 답변이 근거값과 대조에 성공한다', () => {
  const 근거묶음 = [{ 파생: { 합계: 29151 }, 관측: [{ 기간: '2026-08', 값: 29151 }] }];
  const r = verify({ 답변: '2026년 8월 취업자는 29,151천명이다', 근거: [] }, 근거묶음);
  assert.equal(r.ok, true);
});

test('쉼표가 여러 번 들어가도 한 숫자다', () => {
  assert.deepEqual(extractNumbers('1,234,567 건'), [1234567]);
});

test('나열의 쉼표는 묶지 않는다 — 띄어쓰기가 경계다', () => {
  assert.deepEqual(extractNumbers('20, 151'), [20, 151]);
});

test('세 자리가 아니면 천 단위가 아니다', () => {
  // `29,15` 는 구분자가 아니므로 두 숫자로 남는다 — 묶어 버리면 없는 값을 만든다
  assert.deepEqual(extractNumbers('29,15'), [29, 15]);
});

test('천 단위 뒷자리가 집단 라벨로 먹히지 않는다', () => {
  // `1,234대` 의 `234대` 가 가려지면 남은 1 만 뽑혀 원래 값이 사라진다
  assert.deepEqual(extractNumbers('1,234대'), [1234]);
});

test('진짜 연령대는 여전히 라벨로 가린다', () => {
  assert.deepEqual(extractNumbers('30대 취업자'), []);
});

test('쉼표 수의 소수점도 살아 있다', () => {
  assert.deepEqual(extractNumbers('29,151.5천명'), [29151.5]);
});

// ── 전망 수치 (실배포 화면 검증) ───────────────────────────────────────────
// 전망 유형은 근거가 비어 있고 수치가 `카드.전망` 에 있는데, verify 는 근거만
// 봤다. **전망 답변의 모든 숫자가 근거 밖으로 판정돼 문장이 늘 버려졌다.**
// 실측(2026-09-09): 위반 [17, 12.3] — 17 은 BOK 2024 연간 전망값 그 자체였다.

const 전망행 = [
  { org: 'KDI', published_at: '2024-11-12', target_period: 'annual',
    value: 18, unit: '만명', prev_value: null, revision: null },
  { org: 'BOK', published_at: '2024-11-28', target_period: 'annual',
    value: 17, unit: '만명', prev_value: 20, revision: -3 },
];

test('전망값을 인용한 답변은 통과한다', () => {
  const r = verify({ 답변: 'KDI는 18만명, BOK는 17만명을 전망한다', 근거: [] },
    [], [], 숫자모음(전망행));
  assert.equal(r.ok, true);
});

test('전망의 이전값·조정폭도 인용할 수 있다', () => {
  const r = verify({ 답변: '20만명에서 17만명으로 3만명 하향 조정됐다', 근거: [] },
    [], [], 숫자모음(전망행));
  assert.equal(r.ok, true);
});

test('전망에 없는 숫자는 여전히 위반이다', () => {
  const r = verify({ 답변: 'KDI는 18만명, BOK는 99만명을 전망한다', 근거: [] },
    [], [], 숫자모음(전망행));
  assert.equal(r.ok, false);
  assert.deepEqual(r.위반, [99]);
});

test('허용숫자를 안 주면 전망값도 위반이다 — 넓힘은 명시적이다', () => {
  const r = verify({ 답변: 'KDI는 18만명을 전망한다', 근거: [] }, []);
  assert.equal(r.ok, false);
  assert.deepEqual(r.위반, [18]);
});

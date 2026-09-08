import { test } from 'node:test';
import assert from 'node:assert/strict';
import { handleAsk, quotaKey, checkQuota } from '../../worker/src/api/routes.mjs';
import { verify } from '../../worker/src/core/verify.mjs';
import { makeFakeDb } from './fixtures/fakedb.mjs';

function memKv(seed = {}) {
  const m = new Map(Object.entries(seed));
  return { get: async (k) => m.get(k) ?? null,
           put: async (k, v) => void m.set(k, String(v)) };
}
const 슬롯 = { 주제: '취업자', 집단축: ['연령'], 지역입도: '전국', 시간입도: '월',
              기간: { from: '2026-07', to: '2026-07' }, 출처: [] };

// ── 할당량 ───────────────────────────────────────────────────────────────
test('할당량 키는 IP 와 날짜로 만든다', () => {
  assert.equal(quotaKey('1.2.3.4', '2026-09-08'), 'q:1.2.3.4:2026-09-08');
});

test('한도 안이면 허용하고 남은 수를 준다', async () => {
  const r = await checkQuota(memKv(), '1.2.3.4', '2026-09-08', 30);
  assert.equal(r.허용, true);
  assert.equal(r.남음, 29);
});

test('한도를 넘으면 막는다', async () => {
  const kv = memKv({ 'q:1.2.3.4:2026-09-08': '30' });
  const r = await checkQuota(kv, '1.2.3.4', '2026-09-08', 30);
  assert.equal(r.허용, false);
});

// ── 자가확인 1: 슬롯을 직접 주면 1패스를 건너뛴다 ──────────────────────────
test('슬롯을 직접 주면 1패스를 건너뛴다 — 완전히 결정적이다', async () => {
  let 호출 = 0;
  const llm = { classify: async () => { 호출 += 1; return {}; },
                compose: async () => ({ 답변: '', 근거: [] }) };
  await handleAsk({ db: makeFakeDb(), kv: memKv(), llm, quota: 30 },
    { 유형: '수치조회', 슬롯, ip: '7.7.7.7', today: '2026-09-08' });
  assert.equal(호출, 0);
});

// ── 자가확인 2: 한도 초과여도 카드는 나온다 ────────────────────────────────
test('한도 초과여도 카드는 나온다 — 기능이 죽지 않는다', async () => {
  const kv = memKv({ 'q:1.2.3.4:2026-09-08': '30' });
  const r = await handleAsk(
    { db: makeFakeDb(), kv, llm: { compose: async () => '문장' }, quota: 30 },
    { 유형: '수치조회', 슬롯, ip: '1.2.3.4', today: '2026-09-08' });
  assert.equal(r.한도초과, true);
  assert.equal(r.답변, null);
  assert.ok(r.배지.includes('한도초과'));
  assert.ok(r.라우팅);           // 카드(라우팅·한계)는 그대로 나온다
  assert.ok(Array.isArray(r.한계));
});

// ── 자가확인 3: 근거에 없는 숫자를 쓰면 답변만 버리고 근거는 남긴다 ────────
test('LLM 이 근거에 없는 숫자를 쓰면 답변을 버리고 카드만 남긴다 — 근거는 남는다', async () => {
  const db = makeFakeDb({ observation: [
    { source: 'eaps', breakdown: 'age', category: '30-39', period: '2026-07',
      value: 600, unit: '천명', yoy: null, rse: null, rse_flag: null },
  ] });
  const llm = { compose: async () => ({ 답변: '취업자는 12345.6천명이다', 근거: [] }) };
  const r = await handleAsk(
    { db, kv: memKv(), llm, quota: 30 },
    { 유형: '수치조회', 슬롯, ip: '9.9.9.9', today: '2026-09-08' });
  assert.equal(r.답변, null);
  assert.equal(r.검증실패, true);
  assert.ok(r.배지.includes('검증실패'));
  assert.equal(r.근거.length, 1);            // 근거는 남는다 — 지워지지 않는다
  assert.equal(r.근거[0].파생.합계, 600);
});

// ── 자가확인 4: LLM 이 던져도 카드는 나온다 ────────────────────────────────
test('LLM 이 compose 에서 던져도 카드는 나온다(수치조회)', async () => {
  const llm = { compose: async () => { throw new Error('502'); } };
  const r = await handleAsk(
    { db: makeFakeDb(), kv: memKv(), llm, quota: 30 },
    { 유형: '수치조회', 슬롯, ip: '8.8.8.1', today: '2026-09-08' });
  assert.equal(r.답변, null);
  assert.ok(Array.isArray(r.근거));
  assert.ok(Array.isArray(r.한계));
});

test('LLM 이 classify 에서 던져도 메타한계로 결정적으로 떨어진다', async () => {
  const llm = {
    classify: async () => { throw new Error('timeout'); },
    compose: async () => { throw new Error('메타한계는 compose 를 안 부른다 — 불렸다면 버그'); },
  };
  const r = await handleAsk({ db: makeFakeDb(), kv: memKv(), llm, quota: 30 },
    { 질문: '아무 질문', ip: '5.5.5.5', today: '2026-09-08' });
  assert.equal(r.유형, '메타한계');
  assert.equal(r.저확신, true);
  assert.equal(r.답변, null);
});

// ── 규칙 2: 메타한계·범위밖은 1회, 나머지 넷은 2회 ─────────────────────────
test('메타한계·범위밖은 compose 를 부르지 않는다 — 던져도 확인할 필요조차 없다', async () => {
  const llm = { compose: async () => { throw new Error('502'); } };
  const r1 = await handleAsk(
    { db: makeFakeDb(), kv: memKv(), llm, quota: 30 },
    { 유형: '메타한계', 슬롯: { ...슬롯, 출처: ['est'] }, ip: '8.8.8.8', today: '2026-09-08' });
  assert.equal(r1.답변, null);
  assert.ok(Array.isArray(r1.한계));

  const r2 = await handleAsk(
    { db: makeFakeDb(), kv: memKv(), llm, quota: 30 },
    { 유형: '범위밖', 슬롯: {}, ip: '8.8.8.9', today: '2026-09-08' });
  assert.equal(r2.답변, null);
  assert.ok(Array.isArray(r2.한계));
});

test('원본 질문에서 시작하면 수치조회·출처비교·전망·원인탐색은 2회, 메타한계·범위밖은 1회 부른다', async () => {
  async function 세보기(응답유형, ip) {
    let classify호출 = 0;
    let compose호출 = 0;
    const llm = {
      classify: async () => {
        classify호출 += 1;
        return {
          유형: 응답유형,
          슬롯: { 주제: '취업', 집단축: [], 지역입도: '전국', 시간입도: '월',
                  기간: { from: '', to: '' }, 출처: [] },
          확신도: 0.9,
        };
      },
      compose: async () => { compose호출 += 1; return { 답변: '', 근거: [] }; },
    };
    await handleAsk({ db: makeFakeDb(), kv: memKv(), llm, quota: 30 },
      { 질문: '아무 질문', ip, today: '2026-09-08' });
    return { classify호출, compose호출, 합계: classify호출 + compose호출 };
  }
  const 수치조회결과 = await 세보기('수치조회', 'c1');
  assert.equal(수치조회결과.합계, 2);
  const 출처비교결과 = await 세보기('출처비교', 'c2');
  assert.equal(출처비교결과.합계, 2);
  const 전망결과 = await 세보기('전망', 'c3');
  assert.equal(전망결과.합계, 2);
  const 원인탐색결과 = await 세보기('원인탐색', 'c4');
  assert.equal(원인탐색결과.합계, 2);
  const 메타한계결과 = await 세보기('메타한계', 'c5');
  assert.equal(메타한계결과.합계, 1);
  assert.equal(메타한계결과.compose호출, 0);
  const 범위밖결과 = await 세보기('범위밖', 'c6');
  assert.equal(범위밖결과.합계, 1);
  assert.equal(범위밖결과.compose호출, 0);
});

// ── 규칙 3: 원문슬롯을 응답에 싣는다 ───────────────────────────────────────
test('원문슬롯을 응답에 싣는다 — 매핑된 슬롯과 함께, 서로 다르게', async () => {
  const llm = {
    classify: async () => ({
      유형: '수치조회',
      슬롯: { 주제: '취업', 집단축: ['연령'], 지역입도: '전국', 시간입도: '월',
              기간: { from: '2026-07', to: '2026-07' }, 출처: [] },
      확신도: 0.9,
    }),
    compose: async () => ({ 답변: '', 근거: [] }),
  };
  const r = await handleAsk({ db: makeFakeDb(), kv: memKv(), llm, quota: 30 },
    { 질문: '2026년 7월 30대 취업자 몇 명', ip: '4.4.4.4', today: '2026-09-08' });
  assert.equal(r.슬롯.주제, '취업자수');   // 카탈로그 원어로 매핑됨
  assert.equal(r.원문슬롯.주제, '취업');   // LLM 원문 그대로, 매핑 전
});

test('사용자가 슬롯을 직접 주면 원문슬롯은 그 슬롯 자체다', async () => {
  const llm = { compose: async () => ({ 답변: '', 근거: [] }) };
  const r = await handleAsk({ db: makeFakeDb(), kv: memKv(), llm, quota: 30 },
    { 유형: '수치조회', 슬롯, ip: '4.4.4.5', today: '2026-09-08' });
  assert.deepEqual(r.원문슬롯, 슬롯);
});

test('할당량 초과로 1패스조차 못 돌리면 원문슬롯은 null 이다', async () => {
  const kv = memKv({ 'q:2.2.2.2:2026-09-08': '30' });
  const llm = { classify: async () => { throw new Error('불려선 안 된다'); } };
  const r = await handleAsk({ db: makeFakeDb(), kv, llm, quota: 30 },
    { 질문: '아무 질문', ip: '2.2.2.2', today: '2026-09-08' });
  assert.equal(r.원문슬롯, null);
  assert.equal(r.한도초과, true);
});

// ── 규칙 4: 어휘는 capability 카탈로그에서 온다 — 하드코딩이 아니다 ────────
test('어휘는 capability 카탈로그에서 뽑는다 — classify.mjs 의 동의어 표에 없어도 매핑된다', async () => {
  const base = makeFakeDb().표.capability;
  const db = makeFakeDb({ capability: [...base, {
    source_id: 'test_src',
    주제: JSON.stringify(['테스트주제']),
    집단축: JSON.stringify([]),
    지역입도: JSON.stringify(['전국']),
    시간입도: JSON.stringify(['월']),
    기간_from: null, 기간_to: null,
  }] });
  const llm = {
    classify: async () => ({
      유형: '메타한계',
      슬롯: { 주제: '테스트주제', 집단축: [], 지역입도: '전국', 시간입도: '월',
              기간: { from: '', to: '' }, 출처: [] },
      확신도: 0.9,
    }),
  };
  const r = await handleAsk({ db, kv: memKv(), llm, quota: 30 },
    { 질문: '테스트주제 관련 질문', ip: '3.3.3.3', today: '2026-09-08' });
  // '테스트주제' 는 classify.mjs 의 주제_SYN 표에 없다 — 카탈로그(capability)에만 있다.
  // 그런데도 저확신 없이 그대로 매핑됐다는 것은 어휘가 실제로 capability 에서 왔다는 뜻이다.
  assert.equal(r.저확신, false);
  assert.equal(r.슬롯.주제, '테스트주제');
});

// ── 규칙 1: verify 에 카드.허용텍스트 를 넘긴다 — 넘김의 효과가 실제로 다르다 ─
test('허용텍스트를 넘겼을 때와 안 넘겼을 때 verify 결과가 실제로 달라진다', async () => {
  const 원인탐색슬롯 = {
    주제: '취업자', 집단축: ['연령', '직업'], 지역입도: '전국', 시간입도: '반기',
    기간: { from: '2023S1', to: '2025S2' }, 출처: [],
  };
  const 답변문장 = '청년 사무직 취업자는 2023하 818.3천명에서 2025하 727.4천명으로 줄었다';
  const llm = { compose: async () => ({ 답변: 답변문장, 근거: [] }) };
  const r = await handleAsk({ db: makeFakeDb(), kv: memKv(), llm, quota: 30 },
    { 유형: '원인탐색', 슬롯: 원인탐색슬롯, ip: '6.6.6.6', today: '2026-09-08' });

  // routes.mjs 는 카드.허용텍스트 를 verify 세 번째 인자로 넘긴다 — 현상 근거서술의
  // 818.3·727.4 를 인용한 것이 통과한다(관측이 비어 있어 근거 집합만으로는 못 넘긴다).
  assert.equal(r.검증실패, undefined);
  assert.equal(r.답변, 답변문장);
  assert.ok(r.허용텍스트.some((t) => t.includes('818.3')));

  // 같은 답변·근거를 허용텍스트 없이 대조하면 위반으로 잡힌다 — 경계가 실제로 효과가 있다는 증거
  const 문장 = { 답변: 답변문장, 근거: [] };
  const 없이 = verify(문장, r.근거 ?? [], []);
  const 함께 = verify(문장, r.근거 ?? [], r.허용텍스트 ?? []);
  assert.equal(없이.ok, false);
  assert.equal(함께.ok, true);
});

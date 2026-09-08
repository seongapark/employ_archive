import { test } from 'node:test';
import assert from 'node:assert/strict';
import { handleAsk, quotaKey, checkQuota } from '../../worker/src/api/routes.mjs';
import { verify } from '../../worker/src/core/verify.mjs';
import { makeFakeDb } from './fixtures/fakedb.mjs';

// 가짜가 실물보다 관대하면 테스트가 거짓 안심을 준다 — 이번 사고의 교훈이다.
// 예전 이 가짜는 `m.set(k, String(v))` 로 **실물 바인딩이 하지 않는 문자열 변환**을
// 대신 해 줬고, 그래서 `kv.put(k, used + 1)`(숫자)이 프로덕션에서만 TypeError 를
// 던져 IP 할당량이 통째로 무효가 된 것을 아무 테스트도 잡지 못했다.
// 지금은 실물 Workers KV 와 같은 계약을 지킨다 — 값은
// string | ArrayBuffer | ArrayBufferView | ReadableStream 만 받고, 그 밖이면 던진다.
function memKv(seed = {}) {
  const m = new Map(Object.entries(seed));
  return {
    get: async (k) => m.get(k) ?? null,
    put: async (k, v) => {
      if (typeof v !== 'string' && !(v instanceof ArrayBuffer) && !ArrayBuffer.isView(v)) {
        throw new TypeError(
          `KV put() 에 넘길 수 있는 값은 string|ArrayBuffer|ArrayBufferView|ReadableStream 뿐이다: ${typeof v}`);
      }
      m.set(k, v);
    },
    // 테스트가 저장된 원값을 직접 들여다볼 수 있게 한다(카운트가 실제로 느는지 확인용)
    _raw: m,
  };
}
// KV 장애를 흉내낸다 — get·put 을 독립적으로 던지게 할 수 있다.
function 죽은Kv({ get: 죽은get = false, put: 죽은put = false } = {}) {
  return {
    get: async () => { if (죽은get) throw new Error('KV get 타임아웃'); return null; },
    put: async () => { if (죽은put) throw new Error('KV put 타임아웃'); },
  };
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

// ── Critical 1(최종 리뷰): 카운트가 **실제로** 는다 ───────────────────────
// 예전엔 put 에 숫자를 넘겼고 실물 KV 가 TypeError 를 던졌지만 checkQuota 의
// catch 가 그것을 삼켜 "이번 요청은 통과" 로 처리했다 — 모든 요청에서 카운트가
// 안 늘어 확정사항 #5(IP 별 하루 할당량)가 통째로 작동하지 않았다.
test('같은 IP 로 거듭 물으면 카운트가 실제로 는다 — 할당량이 진짜로 센다', async () => {
  const kv = memKv();
  const a = await checkQuota(kv, '1.2.3.4', '2026-09-08', 3);
  const b = await checkQuota(kv, '1.2.3.4', '2026-09-08', 3);
  const c = await checkQuota(kv, '1.2.3.4', '2026-09-08', 3);
  const d = await checkQuota(kv, '1.2.3.4', '2026-09-08', 3);
  assert.deepEqual([a.허용, b.허용, c.허용, d.허용], [true, true, true, false]);
  assert.deepEqual([a.남음, b.남음, c.남음, d.남음], [2, 1, 0, 0]);
  // 저장된 값은 문자열이다 — 실물 KV 가 받는 형태 그대로
  assert.equal(kv._raw.get('q:1.2.3.4:2026-09-08'), '3');
});

test('가짜 KV 는 실물처럼 숫자를 거부한다 — 가짜가 더 관대하면 테스트가 거짓 안심을 준다', async () => {
  const kv = memKv();
  await assert.rejects(() => kv.put('q:x:2026-09-08', 1), TypeError);
  await assert.doesNotReject(() => kv.put('q:x:2026-09-08', '1'));
});

// ── KV 장애 — 관대한 기본값(허용: true)으로 열지 않는다 ───────────────────
test('kv.get 이 던지면 막되, 한도초과와 다른 신호(확인불가)를 낸다', async () => {
  const r = await checkQuota(죽은Kv({ get: true }), '1.2.3.4', '2026-09-08', 30);
  assert.equal(r.허용, false);
  assert.equal(r.남음, 0);
  assert.equal(r.확인불가, true);
});

test('kv.put 이 던져도 이번 요청은 통과시킨다 — get 으로 이미 한도 안임을 확인했다', async () => {
  const r = await checkQuota(죽은Kv({ put: true }), '1.2.3.4', '2026-09-08', 30);
  assert.equal(r.허용, true);
  assert.equal(r.남음, 29);
  assert.equal(r.확인불가, undefined);
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

// ── KV 장애 — checkQuota 가 던지지 않아도 handleAsk 가 그 신호를 카드에 반영해야 한다 ─
test('kv.get 이 던져도 카드는 나온다 — 할당량확인불가, 한도초과와는 다른 배지, 근거·라우팅은 그대로', async () => {
  const db = makeFakeDb({ observation: [
    { source: 'eaps', breakdown: 'age', category: '30-39', period: '2026-07',
      value: 600, unit: '천명', yoy: null, rse: null, rse_flag: null },
  ] });
  const llm = { compose: async () => { throw new Error('불려선 안 된다 — LLM 은 건너뛴다'); } };
  const r = await handleAsk(
    { db, kv: 죽은Kv({ get: true }), llm, quota: 30 },
    { 유형: '수치조회', 슬롯, ip: '1.2.3.9', today: '2026-09-08' });
  assert.equal(r.답변, null);
  assert.equal(r.할당량확인불가, true);
  assert.equal(r.한도초과, false);          // 진짜 초과가 아니다 — 뭉개지 않는다
  assert.ok(r.한계.includes('이용량 확인에 실패해 문장 생성을 건너뛴다'));
  assert.ok(r.배지.includes('할당량확인불가'));
  assert.ok(!r.배지.includes('한도초과'));  // 다른 배지로 난다
  assert.ok(r.라우팅);                      // 카드는 그대로 — 라우팅
  assert.equal(r.근거.length, 1);           // 카드는 그대로 — 근거
  assert.equal(r.근거[0].파생.합계, 600);
});

test('kv.put 이 던져도 정상 요청처럼 통과한다(설계상 판단) — 확인불가로 잘못 표시하지 않는다', async () => {
  const llm = { compose: async () => ({ 답변: '', 근거: [] }) };
  const r = await handleAsk(
    { db: makeFakeDb(), kv: 죽은Kv({ put: true }), llm, quota: 30 },
    { 유형: '수치조회', 슬롯, ip: '1.2.3.10', today: '2026-09-08' });
  assert.equal(r.할당량확인불가, undefined);
  assert.equal(r.한도초과, false);
  // compose 가 정상 실행됐다는 것 자체가 "LLM 을 건너뛰지 않았다" 는 증거다
  assert.equal(r.답변, '');
});

test('한도초과와 할당량확인불가는 서로 다른 필드·다른 배지다 — 뭉개지지 않는다', async () => {
  const 초과kv = memKv({ 'q:1.2.3.4:2026-09-08': '30' });
  const 죽은kv = 죽은Kv({ get: true });
  const llm = { compose: async () => { throw new Error('불려선 안 된다'); } };
  const 초과카드 = await handleAsk({ db: makeFakeDb(), kv: 초과kv, llm, quota: 30 },
    { 유형: '수치조회', 슬롯, ip: '1.2.3.4', today: '2026-09-08' });
  const 확인불가카드 = await handleAsk({ db: makeFakeDb(), kv: 죽은kv, llm, quota: 30 },
    { 유형: '수치조회', 슬롯, ip: '1.2.3.11', today: '2026-09-08' });

  assert.equal(초과카드.한도초과, true);
  assert.equal(초과카드.할당량확인불가, undefined);
  assert.ok(초과카드.배지.includes('한도초과'));
  assert.ok(!초과카드.배지.includes('할당량확인불가'));

  assert.equal(확인불가카드.한도초과, false);
  assert.equal(확인불가카드.할당량확인불가, true);
  assert.ok(확인불가카드.배지.includes('할당량확인불가'));
  assert.ok(!확인불가카드.배지.includes('한도초과'));
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
    // classify 가 실패해도 compose(2패스)는 그대로 시도된다 — 이것도 던지면 카드만 남는다.
    compose: async () => { throw new Error('502'); },
  };
  const r = await handleAsk({ db: makeFakeDb(), kv: memKv(), llm, quota: 30 },
    { 질문: '아무 질문', ip: '5.5.5.5', today: '2026-09-08' });
  assert.equal(r.유형, '메타한계');
  assert.equal(r.저확신, true);
  assert.equal(r.답변, null);
});

// ── 규칙 2 (수정 라운드 1) — LLM 호출 횟수는 유형과 무관하다 ───────────────
// 설계 §5-1 의 "LLM" 열은 core 조회 왕복 횟수였지, "문장을 만들지 않는다" 가 아니었다.
// 메타한계·범위밖이야말로 "왜 못 주는지" 를 문장으로 설명해야 하는 자리라 compose 를
// 생략하면 안 된다(확정사항 #4 "LLM 이 답변 전체를 쓴다" 는 유형을 가리지 않는다).
test('메타한계·범위밖도 compose 를 부른다 — 서술이 이 도구의 핵심 산출물이다', async () => {
  const llm = { compose: async () => ({ 답변: '이런 이유로 이 통계는 못 준다', 근거: [] }) };
  const r1 = await handleAsk(
    { db: makeFakeDb(), kv: memKv(), llm, quota: 30 },
    { 유형: '메타한계', 슬롯: { ...슬롯, 출처: ['est'] }, ip: '8.8.8.8', today: '2026-09-08' });
  assert.equal(r1.답변, '이런 이유로 이 통계는 못 준다');
  assert.ok(Array.isArray(r1.한계));

  const r2 = await handleAsk(
    { db: makeFakeDb(), kv: memKv(), llm, quota: 30 },
    { 유형: '범위밖', 슬롯: {}, ip: '8.8.8.9', today: '2026-09-08' });
  assert.equal(r2.답변, '이런 이유로 이 통계는 못 준다');
  assert.ok(Array.isArray(r2.한계));
});

test('메타한계·범위밖도 compose 가 던지면 카드만 남긴다 — 서술이 없어도 죽지 않는다', async () => {
  const llm = { compose: async () => { throw new Error('502'); } };
  const r1 = await handleAsk(
    { db: makeFakeDb(), kv: memKv(), llm, quota: 30 },
    { 유형: '메타한계', 슬롯: { ...슬롯, 출처: ['est'] }, ip: '8.8.8.10', today: '2026-09-08' });
  assert.equal(r1.답변, null);
  assert.ok(Array.isArray(r1.한계));

  const r2 = await handleAsk(
    { db: makeFakeDb(), kv: memKv(), llm, quota: 30 },
    { 유형: '범위밖', 슬롯: {}, ip: '8.8.8.11', today: '2026-09-08' });
  assert.equal(r2.답변, null);
  assert.ok(Array.isArray(r2.한계));
});

test('호출 횟수는 유형과 무관하다 — 슬롯 미제공 2회(6종 전부), 슬롯 직접 제공 1회(6종 전부)', async () => {
  const 유형들 = ['수치조회', '출처비교', '메타한계', '전망', '원인탐색', '범위밖'];

  async function 세보기(응답유형, { 슬롯주기, ip }) {
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
    const 입력 = 슬롯주기
      ? { 유형: 응답유형, 슬롯: { ...슬롯, 출처: [] }, ip, today: '2026-09-08' }
      : { 질문: '아무 질문', ip, today: '2026-09-08' };
    await handleAsk({ db: makeFakeDb(), kv: memKv(), llm, quota: 30 }, 입력);
    return { classify호출, compose호출, 합계: classify호출 + compose호출 };
  }

  const 표 = [];
  for (const 유형 of 유형들) {
    const 미제공 = await 세보기(유형, { 슬롯주기: false, ip: `nogive-${유형}` });
    const 제공 = await 세보기(유형, { 슬롯주기: true, ip: `give-${유형}` });
    표.push({ 유형, 미제공, 제공 });
    // 슬롯 미제공: classify 1 + compose 1 = 2, 유형과 무관
    assert.deepEqual(미제공, { classify호출: 1, compose호출: 1, 합계: 2 });
    // 슬롯 직접 제공: classify 0 + compose 1 = 1, 유형과 무관
    assert.deepEqual(제공, { classify호출: 0, compose호출: 1, 합계: 1 });
  }
  console.log('호출 횟수 표(유형 × 슬롯제공여부):', JSON.stringify(표, null, 1));
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

// 질문 문자열에서 슬롯을 뽑고 어느 도메인을 보여줄지 정한다.
// **LLM 을 부르지 않는다** — classify.mjs 의 동의어 표를 코드로 훑는다.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { slotsFromText, 도메인적용 } from '../../worker/src/lookup/applies.mjs';

// ── 주제 ────────────────────────────────────────────────────────────────

test('질문에서 주제를 카탈로그 어휘로 뽑는다', () => {
  assert.equal(slotsFromText('청년 고용률이 왜 떨어졌나').주제, '취업자수');
  assert.equal(slotsFromText('종사자 수 알려줘').주제, '종사자수');
});

test('긴 낱말이 짧은 낱말에 먹히지 않는다', () => {
  // '고용보험' 안에 '고용' 이 들어 있다. 짧은 것부터 맞히면 상시가입자수가
  // 취업자수로 둔갑해 엉뚱한 통계를 조회한다.
  assert.equal(slotsFromText('고용보험 가입자 수').주제, '상시가입자수');
  assert.equal(slotsFromText('피보험자 추이').주제, '상시가입자수');
});

test('아는 낱말이 없으면 주제가 빈다', () => {
  assert.equal(slotsFromText('카페 매출이 궁금해').주제, '');
});

// ── 집단축과 카테고리 ────────────────────────────────────────────────────

test('연령·성·산업 값을 축과 코드로 함께 뽑는다', () => {
  const s = slotsFromText('30대 여성 취업자');
  assert.deepEqual(s.집단축.sort(), ['성', '연령']);
  assert.equal(s.category.연령, '30-39');
  assert.equal(s.category.성, 'F');
});

test('산업 이름을 KSIC 코드로 뽑는다', () => {
  const s = slotsFromText('제조업 취업자가 줄었나');
  assert.deepEqual(s.집단축, ['산업']);
  assert.equal(s.category.산업, 'C');
});

test('관측에 없는 축도 값을 살린다', () => {
  // 직업 축은 관측이 한 건도 없다. 그래도 버리지 않는다 — 버리면 "못 준다" 가
  // "무슨 말인지 모르겠다" 로 뭉개지고, 사용자가 할 수 있는 일이 달라진다.
  const s = slotsFromText('사무직 취업자');
  assert.deepEqual(s.집단축, ['직업']);
  assert.equal(s.category.직업, '3');
});

// ── 기간 ────────────────────────────────────────────────────────────────

test('연-월을 집으면 그 한 달로 좁힌다', () => {
  const s = slotsFromText('2026년 7월 취업자는 몇 명인가');
  assert.deepEqual(s.기간, { from: '2026-07', to: '2026-07' });
});

test('연도만 있으면 그 해 전체다', () => {
  assert.deepEqual(slotsFromText('2025년 취업자').기간, { from: '2025-01', to: '2025-12' });
});

test('기간을 안 집으면 비워 둔다', () => {
  // 비면 조회가 최신 한 시점을 낸다. 여기서 오늘 날짜를 지어내지 않는다.
  assert.deepEqual(slotsFromText('취업자 몇 명').기간, { from: '', to: '' });
});

// ── 도메인 판정 ──────────────────────────────────────────────────────────

test('주제를 알아들으면 고용동향을 보여준다', () => {
  const d = 도메인적용('30대 취업자');
  assert.equal(d.find((x) => x.도메인 === 'employment').적용, true);
});

test('주제를 못 알아들으면 고용동향은 해당 없음이고 이유를 남긴다', () => {
  // 조용히 빠지는 것이 가장 나쁜 실패다.
  const e = 도메인적용('카페 매출').find((x) => x.도메인 === 'employment');
  assert.equal(e.적용, false);
  assert.match(e.사유, /어떤 통계/);
});

test('글로 찾는 도메인은 주제를 몰라도 찾아본다', () => {
  // 보고서·전망근거·카탈로그는 질문 원문을 색인에 그대로 던진다 — 주제 어휘에
  // 없는 말(정년·최저임금 같은 정책 낱말)이 오히려 여기서 걸린다.
  const d = 도메인적용('정년 연장 논의');
  for (const 도메인 of ['reports', 'forecast', 'catalog']) {
    assert.equal(d.find((x) => x.도메인 === 도메인).적용, true, 도메인);
  }
});

test('질문이 비면 아무 도메인도 부르지 않는다', () => {
  assert.equal(도메인적용('   ').every((x) => x.적용 === false), true);
});


// ── 워커 배선: /api/ask 가 lookup 을 태운다 ────────────────────────────────

import { handleLookup } from '../../worker/src/api/routes.mjs';

const 빈DB = { all: async () => [] };
const memKv = (seed = {}) => {
  const m = new Map(Object.entries(seed));
  return {
    get: async (k) => m.get(k) ?? null,
    put: async (k, v) => {
      // 실물 Workers KV 는 문자열만 받는다. 가짜가 관대하면 거짓 안심을 준다.
      if (typeof v !== 'string') throw new TypeError('KV 는 문자열만 받는다');
      m.set(k, v);
    },
  };
};

test('질문을 넣으면 도메인별 묶음이 돌아온다', async () => {
  const r = await handleLookup({ db: 빈DB, kv: memKv(), quota: 30 },
                               { 질문: '청년 고용률', ip: '1.1.1.1', today: '2026-09-10' });
  assert.equal(r.질문, '청년 고용률');
  assert.ok(Array.isArray(r.묶음));
  assert.equal(r.답변, undefined, '이 기능은 문장을 만들지 않는다');
});

test('LLM 을 주입해도 부르지 않는다', async () => {
  // 이 경로에는 LLM 이 없다. 있으면 언젠가 슬그머니 쓰게 된다.
  const llm = { classify: () => { throw new Error('불렀다'); },
                compose: () => { throw new Error('불렀다'); } };
  const r = await handleLookup({ db: 빈DB, kv: memKv(), quota: 30, llm },
                               { 질문: '청년 고용률', ip: '1.1.1.1', today: '2026-09-10' });
  assert.ok(r.묶음);
});

test('한도를 넘으면 배지를 달되 찾기는 한다', async () => {
  // 할당량은 LLM 비용을 막으려고 둔 장치다. 찾기만 하는 지금은 카드를 그대로 낸다 —
  // "초과하면 LLM 만 건너뛰고 카드는 낸다" 는 이 설계의 원칙과 같다.
  const kv = memKv({ 'q:1.1.1.1:2026-09-10': '30' });
  const r = await handleLookup({ db: 빈DB, kv, quota: 30 },
                               { 질문: '청년 고용률', ip: '1.1.1.1', today: '2026-09-10' });
  assert.ok(r.배지.includes('한도초과'), JSON.stringify(r.배지));
  assert.ok(r.묶음.length);
});

test('이용량을 셀 수 없으면 한도초과와 다른 배지를 단다', async () => {
  // 오늘 몫을 다 쓴 것(내일 다시)과 우리 저장소가 죽은 것(잠시 뒤 다시)은 다른 사실이다.
  const 죽은Kv = { get: async () => { throw new Error('KV 죽음'); }, put: async () => {} };
  const r = await handleLookup({ db: 빈DB, kv: 죽은Kv, quota: 30 },
                               { 질문: '청년 고용률', ip: '1.1.1.1', today: '2026-09-10' });
  assert.ok(r.배지.includes('할당량확인불가'), JSON.stringify(r.배지));
  assert.equal(r.배지.includes('한도초과'), false);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makeLlm, sysClassify } from '../../worker/src/llm/provider.mjs';

// ── 오늘 날짜 주입 ─────────────────────────────────────────────────────────
// 실배포 화면에서 "8월" 이 2023-08 로, "내년" 이 2024 로 풀렸다. 프롬프트에 오늘이
// 없으면 LLM 은 학습 시점을 현재로 가정한다. 2027년 전망 11건이 D1 에 있는데도
// 못 꺼내던 원인이다.

test('프롬프트가 오늘 날짜를 담는다', () => {
  const s = sysClassify(new Date('2026-09-09T04:00:00Z'));
  assert.ok(s.includes('2026-09'), '오늘이 YYYY-MM 으로 들어가야 한다');
});

test('올해·내년·작년을 오늘 기준으로 못박는다', () => {
  const s = sysClassify(new Date('2026-09-09T04:00:00Z'));
  assert.ok(s.includes('올해=2026'));
  assert.ok(s.includes('내년=2027'));
  assert.ok(s.includes('작년=2025'));
});

test('날짜는 하드코딩이 아니다 — 다른 날짜를 주면 따라 바뀐다', () => {
  const s = sysClassify(new Date('2031-01-15T00:00:00Z'));
  assert.ok(s.includes('2031-01'));
  assert.ok(s.includes('내년=2032'));
  assert.ok(!s.includes('2026-09'));
});

test('한국 시각 기준이다 — UTC 로 전날이어도 KST 날짜를 쓴다', () => {
  // 2026-08-31T20:00Z 는 KST 로 2026-09-01 이다. UTC 로 읽으면 달이 하나 밀린다.
  const s = sysClassify(new Date('2026-08-31T20:00:00Z'));
  assert.ok(s.includes('2026-09'), 'KST 로 9월이어야 한다');
});

test('연도 없는 월과 전망 기본값 규칙이 프롬프트에 있다', () => {
  const s = sysClassify(new Date('2026-09-09T04:00:00Z'));
  assert.ok(s.includes('가장 최근에 지난'), '연도 없는 월 규칙');
  assert.ok(/전망[^\n]*내년/.test(s), '전망 기본값 규칙');
});

test('classify 는 호출 시점의 날짜를 쓴다 — 워커가 오래 살아도 굳지 않는다', async () => {
  const 보낸것 = [];
  const fake = async (url, opts) => {
    보낸것.push(JSON.parse(opts.body).messages[0].content);
    return { ok: true, json: async () => ({ choices: [{ message: { content: '{}' } }] }) };
  };
  let 시각 = new Date('2026-09-09T04:00:00Z');
  const llm = makeLlm({ apiKey: 'k', model: 'm', baseUrl: 'https://x/v1',
                        fetch: fake, now: () => 시각 });
  await llm.classify('내년 취업자 전망');
  시각 = new Date('2027-03-01T04:00:00Z');
  await llm.classify('내년 취업자 전망');

  assert.ok(보낸것[0].includes('2026-09'));
  assert.ok(보낸것[1].includes('2027-03'), '두 번째 호출은 새 날짜를 써야 한다');
});

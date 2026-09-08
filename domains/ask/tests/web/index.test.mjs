import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker from '../../worker/src/index.mjs';

// handleAsk 안의 classify/compose 예외·검증실패·한도초과는 routes.mjs 가 전부 막는다.
// 여기서는 그 아래(D1·KV 자체)에서 온 예상 밖 예외가 fetch() 를 통째로 죽이지 않는지만 문다.
function badEnv() {
  return {
    DB: { prepare() { throw new Error('D1 이 죽었다'); } },
    QUOTA: { get: async () => null, put: async () => {} },
    ASK_DAILY_QUOTA: '30',
    ASK_MODEL: 'test-model',
    ASK_ALLOWED_ORIGIN: 'http://example.test',
    // OPENROUTER_API_KEY 는 일부러 안 준다 — 이 경로는 D1 단계에서 이미 던지므로
    // llm 이 실제로 불릴 일이 없다. 키 문자열은 테스트에도 두지 않는다.
  };
}

test('handleAsk 아래에서 예상 밖 예외가 나도 index.mjs 는 raw exception 대신 JSON 을 돌려준다', async () => {
  // 유형·슬롯을 직접 줘 1패스(classify, 실제 네트워크 호출)를 건너뛴다 — ask() 가
  // capability 를 조회하는 순간(route()) D1 이 던지므로, 이 테스트는 네트워크 없이도
  // "D1 자체가 죽었을 때" 를 결정적으로 재현한다.
  const req = new Request('http://worker.test/api/ask', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      유형: '수치조회',
      슬롯: { 주제: '취업자수', 집단축: [], 지역입도: '전국', 시간입도: '월',
              기간: { from: '2026-07', to: '2026-07' }, 출처: [] },
    }),
  });
  const res = await worker.fetch(req, badEnv());
  assert.equal(res.status, 500);
  const body = await res.json();
  assert.equal(body.오류, true);
  assert.equal(body.답변, null);
});

test('/api/health 는 D1 이 죽어 있어도 영향받지 않는다', async () => {
  const req = new Request('http://worker.test/api/health');
  const res = await worker.fetch(req, badEnv());
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.ok, true);
});

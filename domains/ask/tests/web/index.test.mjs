import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker from '../../worker/src/index.mjs';

// handleLookup 안의 할당량 확인 실패는 routes.mjs 가 막는다.
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

test('handleLookup 아래에서 예상 밖 예외가 나도 index.mjs 는 raw exception 대신 JSON 을 돌려준다', async () => {
  // 이 경로에는 LLM 이 없다 — 슬롯을 코드가 질문 원문에서 뽑는다. 그래서 질문
  // 하나만 주면 색인 조회에서 D1 이 던지고, 네트워크 없이 "D1 이 죽었을 때" 가
  // 결정적으로 재현된다.
  const req = new Request('http://worker.test/api/ask', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ q: '청년 고용률이 왜 떨어졌나' }),
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

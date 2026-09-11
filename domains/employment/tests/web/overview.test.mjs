import { test } from 'node:test';
import assert from 'node:assert/strict';
import { cardHtml } from '../../app/js/screens/overview.js';

function card(over = {}) {
  return {
    code: 'eaps', name_ko: '경제활동인구조사', headline_ko: '취업자수',
    coverage: '15세 이상 인구 · 조사대상주간 1시간 이상 취업',
    period: '2026-08', state: 'value', value: 29151.0, yoy: 184.0,
    releasedAt: '2026-09-09', origin: 'press',
    releaseUrl: 'https://mods.go.kr/x', kosisUrl: null, attachments: [],
    summaryLines: [], fallback: null, ...over,
  };
}

test('the card names the number it is showing', () => {
  // 세 출처가 저마다 다른 것을 센다 — 취업자수·종사자수·상시가입자수. 이름을
  // 안 달면 숫자 밑의 포괄범위 줄(`15세 이상 인구 …`)이 숫자의 이름표처럼
  // 읽혀서, 취업자수를 인구수로 보게 된다.
  const html = cardHtml(card());
  const beforeValue = html.slice(0, html.indexOf('2,915.1만명'));
  assert.ok(beforeValue.includes('취업자수'), '수치 이름이 숫자보다 먼저 나와야 한다');
});

test('each source is named by what it actually counts', () => {
  assert.ok(cardHtml(card({ code: 'est', name_ko: '사업체노동력조사', headline_ko: '종사자수' }))
    .includes('종사자수'));
  assert.ok(cardHtml(card({ code: 'ei', headline_ko: '상시가입자수' }))
    .includes('상시가입자수'));
});

test('an unpublished month still says what it would have counted', () => {
  // 이름이 상태와 함께 사라지면 `미발표` 가 무엇의 미발표인지 알 수 없다.
  const html = cardHtml(card({ state: 'unpublished', value: null, yoy: null }));
  assert.ok(html.includes('취업자수'));
  assert.ok(html.includes('미발표'));
});

test('a source with no headline of its own draws no empty label', () => {
  const html = cardHtml(card({ headline_ko: null }));
  assert.equal(html.includes('card__headline'), false);
});

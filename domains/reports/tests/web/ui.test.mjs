import { test } from 'node:test';
import assert from 'node:assert/strict';
import { reportRow } from '../../app/js/ui.js';

const REPORT = { id: 'a', org: 'kli', title: '청년고용 연구', published: '2026-01-01' };

// 추천 이유를 카드 밖 형제 요소로 그렸더니 "어느 카드 것인지" 안 읽혔다
// (사용자 지적). 카드 <a> 태그 안에 들어가야 그 카드 것임이 분명해진다.
test('추천 이유는 카드 안에 들어간다', () => {
  const html = reportRow(REPORT, { why: '경력 사다리 분해' });
  const aOpen = html.indexOf('<a');
  const aClose = html.lastIndexOf('</a>');
  const whyAt = html.indexOf('row__why');
  assert.ok(whyAt > aOpen && whyAt < aClose, '.row__why 가 <a>...</a> 안에 있어야 한다');
  assert.ok(html.includes('경력 사다리 분해'));
});

test('이유가 없으면 상자를 그리지 않는다', () => {
  const html = reportRow(REPORT, {});
  assert.ok(!html.includes('row__why'));
});

test('이유는 발췌문과 구분되는 표시를 단다', () => {
  const html = reportRow(REPORT, { why: '이유', snippet: '발췌' });
  assert.ok(html.includes('row__why-label'));
  assert.ok(html.includes('row__snippet'));
  assert.notEqual(html.indexOf('row__why'), html.indexOf('row__snippet'));
});

test('LLM 이 만든 문자열이라 esc 를 거친다', () => {
  const html = reportRow(REPORT, { why: '<script>alert(1)</script>' });
  assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('&lt;script&gt;'));
});

// 출처 탐색 화면. 순수 함수라 DOM 없이 돈다.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { 묶음HTML, 도메인이름 } from '../../app/js/lookup.js';

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const 결과 = (over = {}) => ({
  제목: '청년 고용 연구', 스니펫: '청년 고용률이 하락했다', 링크: 'https://kli.re.kr/1',
  근거유형: '초록', ...over,
});

test('도메인을 한글 이름으로 보여준다', () => {
  const html = 묶음HTML({ 묶음: [{ 도메인: 'reports', 결과: [결과()] }], 해당없음: [] }, { esc });
  assert.match(html, /연구보고서/);
  assert.equal(도메인이름.employment, '고용동향');
});

test('제목·근거유형·스니펫을 함께 그린다', () => {
  const html = 묶음HTML({ 묶음: [{ 도메인: 'reports', 결과: [결과()] }], 해당없음: [] }, { esc });
  assert.match(html, /청년 고용 연구/);
  assert.match(html, /초록/);
  assert.match(html, /청년 고용률이 하락했다/);
});

test('링크는 새 창으로 열고 rel 을 붙인다', () => {
  const html = 묶음HTML({ 묶음: [{ 도메인: 'reports', 결과: [결과()] }], 해당없음: [] }, { esc });
  assert.match(html, /href="https:\/\/kli\.re\.kr\/1"/);
  assert.match(html, /rel="noopener"/);
});

test('링크가 없으면 링크를 그리지 않는다', () => {
  // 카탈로그의 충돌·한계는 갈 곳이 없다. 빈 링크를 그리면 눌러도 아무 일이 없다.
  const html = 묶음HTML({ 묶음: [{ 도메인: 'catalog', 결과: [결과({ 링크: '' })] }], 해당없음: [] },
                        { esc });
  assert.equal(/<a /.test(html), false, html);
});

test('결과가 없으면 그 사유를 그린다', () => {
  const html = 묶음HTML({ 묶음: [{ 도메인: 'forecast', 결과: [], 사유: '이 질문으로 걸리는 글이 없다' }],
                         해당없음: [] }, { esc });
  assert.match(html, /걸리는 글이 없다/);
});

test('해당 없는 도메인도 사유와 함께 남긴다', () => {
  // 조용히 빠지는 것이 가장 나쁜 실패다.
  const html = 묶음HTML({ 묶음: [], 해당없음: [{ 도메인: 'employment', 사유: '어떤 통계를 볼지 정할 낱말이 없다' }] },
                        { esc });
  assert.match(html, /고용동향/);
  assert.match(html, /어떤 통계를 볼지/);
});

test('제목에 든 태그를 그대로 넣지 않는다', () => {
  const html = 묶음HTML({ 묶음: [{ 도메인: 'reports', 결과: [결과({ 제목: '<script>x</script>' })] }],
                         해당없음: [] }, { esc });
  assert.equal(html.includes('<script>'), false);
});

test('아무 도메인도 없으면 빈손이라고 말한다', () => {
  const html = 묶음HTML({ 묶음: [], 해당없음: [] }, { esc });
  assert.match(html, /찾지 못했다|없다/);
});

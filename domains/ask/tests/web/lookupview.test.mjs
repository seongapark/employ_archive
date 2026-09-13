// 출처 탐색 화면. 순수 함수라 DOM 없이 돈다.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { 묶음HTML, 답변HTML, 질문해시, 도메인이름 } from '../../app/js/lookup.js';
import { badgeLabel } from '../../app/js/badge.js';

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

// ── 요약 문장 ──────────────────────────────────────────────────────────────

test('문장이 있으면 그리고, 기계가 썼다는 것을 밝힌다', () => {
  const h = 답변HTML({ 답변: '취업자는 29151천명이다.' }, { esc: (s) => String(s) });
  assert.ok(h.includes('취업자는 29151천명이다.'));
  assert.match(h, /자동 작성한 요약/);
});

test('문장이 없으면 빈 문자열이다 — 왜 없는지는 배지가 말한다', () => {
  const esc = (s) => String(s);
  assert.equal(답변HTML({}, { esc }), '');
  assert.equal(답변HTML({ 답변: '   ' }, { esc }), '');
});

test('문장도 이스케이프한다 — LLM 출력이 그대로 HTML 이 되면 안 된다', () => {
  const esc = (s) => String(s).replace(/</g, '&lt;');
  const h = 답변HTML({ 답변: '<script>x</script>' }, { esc });
  assert.equal(h.includes('<script>'), false, h);
});

test('요약실패 배지에 제 라벨이 있다', () => {
  assert.match(badgeLabel('요약실패').라벨, /잠시 후 다시/);
});

test('질문 해시는 되풀이해도 같다 — 그래야 한 번 눌러 한 번만 보낸다', () => {
  // 실측: 제출 때 해시를 바꾸고 go 도 직접 불러서 POST 가 2건 나갔다(LLM 비용 두 배).
  const q = '최근 고용상황은?';
  assert.equal(질문해시(q), 질문해시(q));
  assert.equal(질문해시(` ${q} `), 질문해시(q), '앞뒤 공백이 다른 주소를 만들면 또 두 번 보낸다');
  assert.equal(decodeURIComponent(질문해시(q).replace('#/q=', '')), q);
});

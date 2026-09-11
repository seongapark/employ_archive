import { test } from 'node:test';
import assert from 'node:assert/strict';
import { 요약HTML, 도메인HTML, 화면HTML, 유입HTML, 분포HTML, 잠금HTML } from '../../app/js/render.js';

const 통계 = {
  기간: { 시작: '2026-09-01', 끝: '2026-09-30', 일수: 30 },
  요약: { 방문자: 10, 세션: 14, 조회: 40, 신규: 6, 재방문: 4 },
  직전: { 방문자: 8, 세션: 10, 조회: 30 },
  도메인: [{ 도메인: 'employment', 방문자: 7, 세션: 9, 조회: 25 },
           { 도메인: 'press', 방문자: 4, 세션: 5, 조회: 15 }],
  일별: [], 화면: [{ 도메인: 'employment', 경로: '/overview', 조회: 12, 방문자: 6 }],
  유입: { 종류: [{ 종류: 'search', 세션: 9 }], 호스트: [{ 호스트: 'google.com', 세션: 9 }] },
  기기: [{ 값: 'mobile', 방문자: 7 }], 표시모드: [{ 값: 'standalone', 방문자: 3 }],
  국가: [{ 값: 'KR', 방문자: 9 }],
};

test('요약은 직전 대비 증감을 함께 보인다', () => {
  const html = 요약HTML(통계);
  assert.match(html, /10/);
  assert.match(html, /delta-up/);
});

test('도메인은 한글 이름으로 나온다', () => {
  const html = 도메인HTML(통계);
  assert.match(html, /고용동향/);
  assert.match(html, /행통 모니터링/);
  assert.ok(!html.includes('employment<'), '슬러그가 그대로 새어 나왔다');
});

// 방문자를 다 더하면 전체보다 크다. 이건 정의상 그런 것이고, 화면이 말해야 한다.
test('합계가 전체보다 큰 이유를 화면이 말한다', () => {
  assert.match(도메인HTML(통계), /양쪽에 세어진다/);
});

test('직전이 없으면 증감을 안 그린다', () => {
  const html = 요약HTML({ ...통계, 직전: null });
  assert.ok(!html.includes('delta-up'));
  assert.ok(!html.includes('delta-down'));
});

test('데이터가 없으면 빈 줄이 아니라 안내를 낸다', () => {
  for (const [f, 빈값] of [[화면HTML, { ...통계, 화면: [] }],
    [유입HTML, { ...통계, 유입: { 종류: [], 호스트: [] } }]]) {
    assert.match(f(빈값), /아직 기록이 없다/);
  }
});

test('분포 셋을 한 번에 그린다', () => {
  const html = 분포HTML(통계);
  assert.match(html, /모바일/);
  assert.match(html, /설치앱/);
  assert.match(html, /KR/);
});

test('잠금 화면은 숫자를 하나도 안 보인다', () => {
  const html = 잠금HTML();
  assert.match(html, /password/);
  assert.ok(!/\d{2,}/.test(html.replace(/[^\d]/g, ' ')), '잠금 화면에 숫자가 있다');
});

// 유입 호스트는 남이 정한 문자열이다 — 그대로 붙이면 스크립트가 실린다.
test('호스트를 이스케이프한다', () => {
  const html = 유입HTML({ ...통계,
    유입: { 종류: [], 호스트: [{ 호스트: '<img src=x onerror=1>', 세션: 1 }] } });
  assert.ok(!html.includes('<img'));
  assert.match(html, /&lt;img/);
});

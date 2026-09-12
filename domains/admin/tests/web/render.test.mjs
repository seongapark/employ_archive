import { test } from 'node:test';
import assert from 'node:assert/strict';
import { 요약HTML, 도메인HTML, 화면HTML, 유입HTML, 분포HTML, 잠금HTML, 도구HTML, 현황HTML }
  from '../../app/js/render.js';

const 통계 = {
  기간: { 시작: '2026-09-01', 끝: '2026-09-30', 일수: 30 },
  요약: { 방문자: 10, 세션: 14, 조회: 40, 신규: 6, 재방문: 4 },
  직전: { 방문자: 8, 세션: 10, 조회: 30 },
  도메인: [{ 도메인: 'employment', 방문자: 7, 세션: 9, 조회: 25, 직전방문자: 5 },
           { 도메인: 'press', 방문자: 4, 세션: 5, 조회: 15, 직전방문자: 4 }],
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

// design §6.2·§7.2 — 도메인 카드도 요약처럼 직전 대비 증감을 보인다. employment
// 는 5 → 7 이라 up, press 는 4 → 4 라 증감이 없다(0%도 flat 으로는 그려진다 —
// 여기서는 up 만 확인한다).
test('도메인 카드도 직전 대비 증감을 보인다', () => {
  const html = 도메인HTML(통계);
  assert.match(html, /delta-up/);
});

// 직전방문자 필드가 아예 없으면(전 기간, days=0) 증감을 안 그린다 — 0 으로
// 지어내지 않는다는 stats.mjs 쪽 약속을 화면이 그대로 지킨다.
test('직전방문자가 없으면 도메인 카드에 증감을 안 그린다', () => {
  const html = 도메인HTML({ ...통계,
    도메인: 통계.도메인.map(({ 직전방문자, ...d }) => d) });
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

// 오류 화면(미배포·연결실패)도 이 블록을 그대로 쓴다 — 잠금 화면으로 돌아갈
// 길이 오직 토큰 지우기 버튼뿐이라, 어느 화면에서든 빠뜨리면 갇힌다.
//
// 제외 스위치(체크박스)는 더 이상 없다 — 본인 방문은 이제 관리자 화면이 자동으로
// 등록하는 주인 표(owner)로 빠지고, 여기는 그 상태를 문장으로만 보여준다.
test('도구 블록에는 체크박스가 없고 토큰 지우기가 있다', () => {
  const html = 도구HTML('등록됨');
  assert.ok(!html.includes('type="checkbox"'));
  assert.ok(!html.includes('id="off"'));
  assert.match(html, /id="logout"/);
});

test('등록됐으면 모든 숫자에서 빠진다고 말한다', () => {
  assert.match(도구HTML('등록됨'), /빠진다/);
});

// 버튼 이름이 '토큰 지우기' 였을 때 사용자가 두 번 물었다 — 무엇을 지우는지도,
// 지우면 무슨 일이 나는지도 이름만으로는 안 보였다. 이름과 설명을 함께 지킨다.
test('로그아웃 버튼과 그 설명이 있다', () => {
  const html = 도구HTML('등록됨');
  assert.match(html, /로그아웃/);
  assert.match(html, /기억한 비밀번호를 지우고/);
  assert.ok(!html.includes('토큰 지우기'), '옛 이름이 남아 있다');
});

test('등록을 아직 못 했으면(보류) 그 사실을 말한다', () => {
  assert.match(도구HTML('보류'), /올리지 못했다/);
});

// 유입 호스트는 남이 정한 문자열이다 — 그대로 붙이면 스크립트가 실린다.
test('호스트를 이스케이프한다', () => {
  const html = 유입HTML({ ...통계,
    유입: { 종류: [], 호스트: [{ 호스트: '<img src=x onerror=1>', 세션: 1 }] } });
  assert.ok(!html.includes('<img'));
  assert.match(html, /&lt;img/);
});

// ── 도메인 현황 ──────────────────────────────────────────────────────
// model.js 의 도메인현황() 이 만드는 모양을 그대로 흉내낸다 — render.js 는
// 이 모양을 안다고만 가정하고 정규화 로직 자체는 모른다.
const 정상카드 = { 키: 'forecast', 이름: '고용전망', 형식오류: false, 이유: null,
  실행시각: '2026-09-11T16:40:23+09:00', 경과시간: 19.3,
  지표: [{ 라벨: '수집기 실패', 값: 1 }, { 라벨: '오류', 값: 1 }], 경고: [] };
const 경고카드 = { 키: 'reports', 이름: '연구보고서', 형식오류: false, 이유: null,
  실행시각: '2026-09-11T23:36:32+09:00', 경과시간: 12.4,
  지표: [{ 라벨: '미판정', 값: 2216 }], 경고: ['미판정 2216건'] };
const 오류카드 = { 키: 'ask', 이름: '질의응답', 형식오류: true, 이유: '형식을 못 읽음',
  실행시각: null, 경과시간: null, 지표: [], 경고: [] };

test('현황은 다섯 도메인의 한글 이름을 낸다', () => {
  const html = 현황HTML([정상카드, 경고카드]);
  assert.match(html, /고용전망/);
  assert.match(html, /연구보고서/);
});

test('큰 숫자는 천단위로 끊어서 낸다 — 356건 미판정 같은 값이 그대로 보여야 한다', () => {
  const html = 현황HTML([경고카드]);
  assert.match(html, /2,216/);
});

test('경고가 있는 카드가 먼저 온다', () => {
  const html = 현황HTML([정상카드, 경고카드]);
  assert.ok(html.indexOf('연구보고서') < html.indexOf('고용전망'),
    '경고 없는 forecast 가 경고 있는 reports 보다 먼저 나왔다');
});

test('경고 카드에는 status__card--warn 클래스가 붙는다', () => {
  const html = 현황HTML([경고카드]);
  assert.match(html, /status__card--warn/);
});

test('경고가 없는 카드에는 status__card--warn 이 안 붙는다', () => {
  const html = 현황HTML([정상카드]);
  assert.ok(!html.includes('status__card--warn'));
});

test('형식오류 카드는 지표 없이 이유만 보인다', () => {
  const html = 현황HTML([오류카드]);
  assert.match(html, /형식을 못 읽음/);
  assert.match(html, /status__card--warn/);
});

test('경고 목록은 한 줄씩 이스케이프해서 낸다', () => {
  const 악성 = { ...경고카드, 경고: ['<script>alert(1)</script>'] };
  const html = 현황HTML([악성]);
  assert.ok(!html.includes('<script>'));
  assert.match(html, /&lt;script&gt;/);
});

test('빈 목록이면 안내 문구를 낸다', () => {
  assert.match(현황HTML([]), /아직 기록이 없다/);
});

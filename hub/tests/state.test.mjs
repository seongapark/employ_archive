import { test } from 'node:test';
import assert from 'node:assert/strict';
import { domainState, updatedLabel, DOMAINS, askHref } from '../js/state.js';

test('DOMAINS는 주요 도메인 넷을 고정 순서로 갖는다', () => {
  // 질의응답은 카드가 아니라 맨 위 검색창이다 — 넷의 자료에서 출처를 찾아 주는
  // 창구이지 나란한 다섯째 도메인이 아니다.
  // supply(인력수급)는 카드만 있고 도메인 폴더가 없어 늘 '준비중' 이었다.
  // reports(연구보고서)는 맨 뒤다 — 수치가 아니라 문헌 축이라 성격이 다르다.
  assert.deepEqual(DOMAINS.map(d => d.slug),
    ['forecast', 'employment', 'press', 'reports']);
});

test('질의응답은 카드 목록에 없다', () => {
  // 카드로도 두면 같은 것이 화면에 두 번 나온다.
  assert.equal(DOMAINS.some(d => d.slug === 'ask'), false);
});

test('허브는 질문 문자열만 넘긴다 — 내용을 해석하지 않는다', () => {
  assert.equal(askHref('청년 사무직'), './ask/#/q=%EC%B2%AD%EB%85%84%20%EC%82%AC%EB%AC%B4%EC%A7%81');
});

test('빈 질문은 넘기지 않는다', () => {
  assert.equal(askHref('   '), null);
});

test('last_run이 없으면 준비중이다', () => {
  assert.equal(domainState(null), 'pending');
});

test('last_run이 있으면 준비됨이다', () => {
  assert.equal(domainState({ run_at: '2026-08-29T15:06:55.311583+09:00' }), 'ready');
});

test('updatedLabel은 월.일 갱신 형태를 만든다', () => {
  assert.equal(updatedLabel({ run_at: '2026-08-29T15:06:55.311583+09:00' }), '08.29 갱신');
});

test('updatedLabel은 값이 없으면 준비중을 돌려준다', () => {
  assert.equal(updatedLabel(null), '준비중');
});

test('updatedLabel은 날짜 필드가 비어도 준비중으로 떨어진다', () => {
  assert.equal(updatedLabel({}), '준비중');
});


test('연구보고서의 at 필드도 실행 시각으로 읽는다', () => {
  // 시각 필드가 도메인마다 다르다(run_at / at). 한쪽만 읽으면 그 카드가 늘
  // '준비중' 으로 그려진다 — 실제로 연구보고서가 그랬다.
  assert.equal(updatedLabel({ at: '2026-09-10T11:30:00+09:00' }), '09.10 갱신');
  assert.equal(domainState({ at: '2026-09-10T11:30:00+09:00' }), 'ready');
});

test('시각이 없는 객체는 준비중이다', () => {
  // {} 를 ready 로 보면 수집이 한 번도 안 돈 도메인이 갱신된 것처럼 보인다.
  assert.equal(domainState({}), 'pending');
});

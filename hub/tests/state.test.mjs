import { test } from 'node:test';
import assert from 'node:assert/strict';
import { domainState, updatedLabel, DOMAINS, askHref } from '../js/state.js';

test('DOMAINS는 여섯 영역을 고정 순서로 갖는다', () => {
  // ask(질의응답)를 맨 앞에 둔다 — 다른 도메인으로 가는 입구 역할을 겸한다.
  // economy(경제동향) 자리는 press(행통 모니터링)로 바뀌었다 — 거시 지표 동향은
  // 이 아카이브가 다루는 축이 아니었고, 고용행정통계 보도 모니터링이
  // 앞의 세 도메인과 같은 원자료(고용노동부 보도자료)를 쓴다.
  // reports(연구보고서)는 맨 뒤에 붙였다 — 수치가 아니라 문헌 축이라
  // 앞의 다섯과 성격이 다르고, 나중에 붙은 순서 그대로가 읽기 쉽다.
  assert.deepEqual(DOMAINS.map(d => d.slug),
    ['ask', 'forecast', 'employment', 'supply', 'press', 'reports']);
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

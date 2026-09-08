import { test } from 'node:test';
import assert from 'node:assert/strict';
import { domainState, updatedLabel, DOMAINS } from '../js/state.js';

test('DOMAINS는 네 영역을 고정 순서로 갖는다', () => {
  // economy(경제동향) 자리는 press(행통 모니터링)로 바뀌었다 — 거시 지표 동향은
  // 이 아카이브가 다루는 축이 아니었고, 고용행정통계 보도 모니터링이
  // 앞의 세 도메인과 같은 원자료(고용노동부 보도자료)를 쓴다.
  assert.deepEqual(DOMAINS.map(d => d.slug),
    ['forecast', 'employment', 'supply', 'press']);
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

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { domainState, updatedLabel, DOMAINS, askHref } from '../js/state.js';

test('DOMAINS는 주요 도메인 넷을 고정 순서로 갖는다', () => {
  // 질의응답은 카드가 아니라 맨 위 검색창이다 — 넷의 자료에서 출처를 찾아 주는
  // 창구이지 나란한 다섯째 도메인이 아니다.
  // supply(인력수급)는 카드만 있고 도메인 폴더가 없어 늘 '준비중' 이었다.
  // 순서는 사용자가 정했다: 지금 수치 → 그 수치가 어떻게 보도됐나 → 앞으로의
  // 전망 → 관련 연구. 알파벳순도 추가순도 아니라 고치기 쉬워서 여기서 못 박는다.
  assert.deepEqual(DOMAINS.map(d => d.slug),
    ['employment', 'press', 'forecast', 'reports']);
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


// ── 카드가 한꺼번에 뜨는가 ──────────────────────────────────────────────

import { cardModel, 갱신상태 } from '../js/state.js';

test('네 요청이 동시에 나간다', async () => {
  // 예전에는 for 루프 안에서 하나씩 await 해서 왕복이 직렬로 네 번 일어났다 —
  // 카드가 뚝뚝 끊어지며 나타난 이유다.
  const 부른순서 = [];
  const 풀기 = [];
  const load = (path) => {
    부른순서.push(path);
    return new Promise((res) => 풀기.push(res));
  };
  const p = 갱신상태(load);
  // 아직 아무것도 응답하지 않았는데 네 번 다 불렸어야 한다.
  assert.equal(부른순서.length, 4, JSON.stringify(부른순서));
  풀기.forEach((res) => res(null));
  assert.equal((await p).length, 4);
});

test('요청 주소는 도메인마다 자기 last_run 이다', async () => {
  const 본것 = [];
  await 갱신상태((p) => { 본것.push(p); return Promise.resolve(null); });
  assert.deepEqual(본것, [
    './employment/data/last_run.json',
    './press/data/last_run.json',
    './forecast/data/last_run.json',
    './reports/data/last_run.json',
  ]);
});

test('아직 안 받은 카드는 링크가 없다', () => {
  // 뼈대를 먼저 그리므로 last_run 이 null 인 순간이 반드시 있다. 그때 링크를 걸면
  // 수집이 한 번도 안 돈 도메인의 빈 화면으로 사람을 보낸다.
  const m = cardModel({ slug: 'reports', name: '연구보고서', desc: '설명' }, null);
  assert.equal(m.href, null);
  assert.equal(m.ready, false);
  assert.equal(m.meta, '준비중');
});

test('받고 나면 링크와 날짜가 채워진다', () => {
  const m = cardModel({ slug: 'reports', name: '연구보고서', desc: '설명' },
                      { at: '2026-09-10T11:30:00+09:00' });
  assert.equal(m.href, './reports/');
  assert.equal(m.ready, true);
  assert.equal(m.meta, '09.10 갱신');
});

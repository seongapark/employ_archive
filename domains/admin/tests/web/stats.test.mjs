import { test } from 'node:test';
import assert from 'node:assert/strict';
import { 기간, 통계 } from '../../worker/src/core/stats.mjs';
import { 열린DB, 줄 } from './fixtures/sqlitedb.mjs';
import { 기록 } from '../../worker/src/core/write.mjs';

test('30일 창은 오늘을 포함해 30일이고 직전은 그 앞 30일이다', () => {
  const w = 기간(30, '2026-09-30');
  assert.equal(w.끝, '2026-09-30');
  assert.equal(w.시작, '2026-09-01');
  assert.equal(w.일수, 30);
  assert.equal(w.직전끝, '2026-08-31');
  assert.equal(w.직전시작, '2026-08-02');
});

// days=0 은 전 기간이다. 직전 기간은 존재하지 않으므로 비교를 지운다.
test('전 기간에는 직전이 없다', () => {
  const w = 기간(0, '2026-09-30');
  assert.equal(w.시작, '0000-01-01');
  assert.equal(w.직전시작, null);
  assert.equal(w.직전끝, null);
});

async function 채운DB() {
  const { db, raw } = 열린DB();
  const r = [
    // v1: 8월에 처음 왔고(= 재방문), 9/06 에 구글로 들어와 세 화면을 돈다
    ['v1', 's0', '2026-08-20', 'employment', '/overview', 'google.com', 'search'],
    ['v1', 's2', '2026-09-06', 'employment', '/', 'google.com', 'search'],
    ['v1', 's2', '2026-09-06', 'employment', '/b/industry/:id', null, 'direct'],
    ['v1', 's2', '2026-09-06', 'press', '/', null, 'direct'],
    // v2: 9/07 이 첫 방문(= 신규), 북마크로 직접
    ['v2', 's3', '2026-09-07', 'forecast', '/', null, 'direct'],
  ];
  for (const [v, s, day, domain, path, ref, ref_kind] of r) {
    await 기록(db, 줄({ visitor: v, session: s, day, ts: `${day}T01:00:00Z`,
      domain, path, ref, ref_kind }));
  }
  return { db, raw };
}

test('요약은 방문자·세션·조회를 구분해 센다', async () => {
  const { db } = await 채운DB();
  const s = await 통계(db, 30, '2026-09-30');
  assert.deepEqual(s.요약, { 방문자: 2, 세션: 2, 조회: 4, 신규: 1, 재방문: 1 });
});

test('직전 기간이 따로 나온다', async () => {
  const { db } = await 채운DB();
  const s = await 통계(db, 30, '2026-09-30');
  assert.deepEqual(s.직전, { 방문자: 1, 세션: 1, 조회: 1 });
});

test('도메인별은 방문자 내림차순이다', async () => {
  const { db } = await 채운DB();
  const s = await 통계(db, 30, '2026-09-30');
  assert.deepEqual(s.도메인.map((d) => d.도메인), ['employment', 'forecast', 'press']);
  assert.equal(s.도메인[0].조회, 2);
});

// design §6.2·§7.2 — 도메인 카드는 전체 증감만으로는 "어느 도메인이 늘었나"에
// 답을 못 한다. employment 는 8/20(직전 기간)에도 방문이 있었으니 직전방문자가
// 나오고, forecast 는 직전 기간에 없었으니 0 이 나와야 한다(필드 자체가 없는
// 것과는 다르다 — 아래 전 기간 테스트가 그 구분을 잡는다).
test('도메인별 직전 방문자가 나온다', async () => {
  const { db } = await 채운DB();
  const s = await 통계(db, 30, '2026-09-30');
  const 맵 = Object.fromEntries(s.도메인.map((d) => [d.도메인, d.직전방문자]));
  assert.equal(맵.employment, 1);
  assert.equal(맵.forecast, 0);
});

// 전 기간(days=0)에는 직전이 없다 — 0 으로 채우면 "직전이 없다"와 "직전이
// 0이다"가 뭉개져 델타()가 거짓으로 -100%를 그린다. 그래서 필드 자체를 뺀다.
test('전 기간에는 도메인 카드에 직전방문자가 없다', async () => {
  const { db } = await 채운DB();
  const s = await 통계(db, 0, '2026-09-30');
  for (const d of s.도메인) assert.equal('직전방문자' in d, false, d.도메인);
});

// 설계 §6.3 — 프로토타입으로 재현한 결함이다. 세션 내부 이동은 referrer 가 같은
// 사이트라 direct 로 기록되므로, 모든 줄을 세면 구글로 들어온 세션 하나가
// search 에도 direct 에도 잡혀 합이 실제 세션 수를 넘는다.
test('유입은 세션의 첫 줄만 센다 — 합이 세션 수와 같다', async () => {
  const { db } = await 채운DB();
  const s = await 통계(db, 30, '2026-09-30');
  const 종류 = Object.fromEntries(s.유입.종류.map((x) => [x.종류, x.세션]));
  assert.deepEqual(종류, { search: 1, direct: 1 });
  assert.equal(s.유입.종류.reduce((a, x) => a + x.세션, 0), s.요약.세션);
  assert.deepEqual(s.유입.호스트, [{ 호스트: 'google.com', 세션: 1 }]);
});

test('일별은 날짜와 도메인으로 나온다', async () => {
  const { db } = await 채운DB();
  const s = await 통계(db, 30, '2026-09-30');
  const d = s.일별.find((x) => x.날짜 === '2026-09-06');
  assert.deepEqual(d.도메인별, { employment: 2, press: 1 });
  assert.equal(d.방문자, 1);
});

test('화면은 조회 내림차순 상위다', async () => {
  const { db } = await 채운DB();
  const s = await 통계(db, 30, '2026-09-30');
  assert.ok(s.화면.length <= 20);
  assert.deepEqual(s.화면[0], { 도메인: 'employment', 경로: '/', 조회: 1, 방문자: 1 });
});

test('기기·표시모드·국가가 나온다', async () => {
  const { db } = await 채운DB();
  const s = await 통계(db, 30, '2026-09-30');
  assert.deepEqual(s.기기, [{ 값: 'mobile', 방문자: 2 }]);
  assert.deepEqual(s.표시모드, [{ 값: 'browser', 방문자: 2 }]);
  assert.deepEqual(s.국가, [{ 값: 'KR', 방문자: 2 }]);
});

test('빈 DB 도 모양이 같다', async () => {
  const { db } = 열린DB();
  const s = await 통계(db, 30, '2026-09-30');
  assert.deepEqual(s.요약, { 방문자: 0, 세션: 0, 조회: 0, 신규: 0, 재방문: 0 });
  assert.deepEqual(s.도메인, []);
  assert.deepEqual(s.유입.종류, []);
});

// 주인(관리자 비밀번호로 들어온 기기)의 방문은 모든 숫자에서 빠져야 한다. v1 을
// 주인으로 등록하면 채운DB() 의 트래픽 대부분(employment 8/20·9/06, press 9/06)이
// 전부 v1 소유라 통계에서 사라지고, v2(9/07 신규, forecast, direct)만 남는다.
// 질의 하나하나(요약·신규재방문·도메인·일별·화면·유입종류·유입호스트·기기·
// 표시모드·국가·직전·직전도메인)를 전부 이 하나의 시나리오로 덮는다 — 직전도메인은
// 도메인 카드의 직전방문자 필드로 드러난다.
test('주인으로 등록한 방문자는 모든 지표에서 빠진다', async () => {
  const { db, raw } = await 채운DB();
  raw.prepare('INSERT INTO owner (visitor, added) VALUES (?, ?)').run('v1', '2026-09-01');

  const s = await 통계(db, 30, '2026-09-30');

  assert.deepEqual(s.요약, { 방문자: 1, 세션: 1, 조회: 1, 신규: 1, 재방문: 0 });
  assert.deepEqual(s.직전, { 방문자: 0, 세션: 0, 조회: 0 });
  assert.deepEqual(s.도메인, [
    { 도메인: 'forecast', 방문자: 1, 세션: 1, 조회: 1, 직전방문자: 0 },
  ]);
  assert.deepEqual(s.일별, [
    { 날짜: '2026-09-07', 방문자: 1, 도메인별: { forecast: 1 } },
  ]);
  assert.deepEqual(s.화면, [{ 도메인: 'forecast', 경로: '/', 조회: 1, 방문자: 1 }]);
  assert.deepEqual(s.유입.종류, [{ 종류: 'direct', 세션: 1 }]);
  assert.deepEqual(s.유입.호스트, []);
  assert.deepEqual(s.기기, [{ 값: 'mobile', 방문자: 1 }]);
  assert.deepEqual(s.표시모드, [{ 값: 'browser', 방문자: 1 }]);
  assert.deepEqual(s.국가, [{ 값: 'KR', 방문자: 1 }]);
});

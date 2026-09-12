import { test } from 'node:test';
import assert from 'node:assert/strict';
import { 이름, 순서, 기간선택, 증감, 퍼센트, 도메인목록, 경과시간, 도메인현황 }
  from '../../app/js/model.js';

// 관리자 앱은 hub/js/state.js 를 끌어 쓸 수 없다 — 빌드가 도메인 폴더에 복사하는
// 것은 core/ 뿐이고, 그 목록에는 hub·ask 가 애초에 없다.
test('여섯 도메인의 한글 이름을 자기가 들고 있다', () => {
  assert.deepEqual(순서, ['employment', 'press', 'forecast', 'reports', 'ask', 'hub']);
  for (const s of 순서) assert.ok(이름[s], s);
  assert.equal(이름.employment, '고용동향');
  assert.equal(이름.hub, '허브');
});

test('기간은 넷이고 기본이 30일이다', () => {
  assert.deepEqual(기간선택.map((x) => x.days), [7, 30, 90, 0]);
  assert.equal(기간선택.find((x) => x.기본).days, 30);
});

test('증감은 방향과 라벨을 함께 준다', () => {
  assert.deepEqual(증감(120, 100), { 값: 20, 방향: 'up', 라벨: '+20%' });
  assert.deepEqual(증감(80, 100), { 값: -20, 방향: 'down', 라벨: '-20%' });
  assert.deepEqual(증감(100, 100), { 값: 0, 방향: 'flat', 라벨: '0%' });
});

// 직전이 0 이면 배수가 무한대다 — 숫자를 지어내지 않고 비교를 포기한다.
test('직전이 없거나 0 이면 비교하지 않는다', () => {
  assert.equal(증감(10, 0), null);
  assert.equal(증감(10, null), null);
});

test('퍼센트는 전체가 0 이어도 안 터진다', () => {
  assert.equal(퍼센트(25, 100), 25);
  assert.equal(퍼센트(1, 3), 33.3);
  assert.equal(퍼센트(5, 0), 0);
});

// ── 도메인 현황 ──────────────────────────────────────────────────────
const 지금 = Date.parse('2026-09-12T12:00:00+09:00');

test('도메인목록은 순서에서 허브만 뺀 다섯이다', () => {
  assert.deepEqual(도메인목록, ['employment', 'press', 'forecast', 'reports', 'ask']);
});

test('경과시간은 지금을 주입받아 시계에 안 매인다', () => {
  const h = 경과시간('2026-09-11T17:00:45+09:00', 지금);
  assert.ok(h > 18 && h < 20, h);
});

test('경과시간은 못 읽는 시각이면 null이다 — 0시간 전으로 지어내지 않는다', () => {
  assert.equal(경과시간('이게 시각이냐', 지금), null);
  assert.equal(경과시간(undefined, 지금), null);
  assert.equal(경과시간(null, 지금), null);
});

test('가져오기 자체가 실패한 도메인(null)은 불러오지 못함이다', () => {
  const [emp] = 도메인현황({ employment: null }, 지금);
  assert.equal(emp.형식오류, true);
  assert.equal(emp.이유, '불러오지 못함');
  assert.equal(emp.지표.length, 0);
});

test('원본 자체가 없어도(아무 도메인도 안 왔어도) 다섯 칸을 다 낸다', () => {
  const 목록 = 도메인현황({}, 지금);
  assert.equal(목록.length, 5);
  assert.ok(목록.every((s) => s.형식오류 && s.이유 === '불러오지 못함'));
});

test('employment·forecast 는 수집기 실패와 오류 수를 센다', () => {
  const 원본 = {
    employment: {
      run_at: '2026-09-11T17:00:45+09:00',
      collectors: { eaps: { ok: false }, est: { ok: false }, ei: { ok: true } },
      conflicts: [], errors: ['a', 'b'],
    },
  };
  const [emp] = 도메인현황(원본, 지금);
  assert.equal(emp.형식오류, false);
  assert.deepEqual(emp.지표, [{ 라벨: '수집기 실패', 값: 2 }, { 라벨: '오류', 값: 2 }]);
  assert.match(emp.경고[0], /eaps.*est|est.*eaps/);
});

test('forecast 도 같은 어댑터를 쓴다 — 모두 성공이면 경고가 없다', () => {
  const 원본 = {
    forecast: {
      run_at: '2026-09-11T16:40:23+09:00',
      collectors: { oecd: { ok: true }, imf: { ok: true } },
      conflicts: [], errors: [],
    },
  };
  const [, , fc] = 도메인현황(원본, 지금);
  assert.deepEqual(fc.지표, [{ 라벨: '수집기 실패', 값: 0 }, { 라벨: '오류', 값: 0 }]);
  assert.deepEqual(fc.경고, []);
});

test('run_at 이 없거나 collectors 가 배열이면 형식을 못 읽음이다', () => {
  const [emp1] = 도메인현황({ employment: { collectors: {}, errors: [] } }, 지금);
  assert.equal(emp1.형식오류, true);
  assert.equal(emp1.이유, '형식을 못 읽음');

  const [emp2] = 도메인현황(
    { employment: { run_at: 'x', collectors: [], errors: [] } }, 지금);
  assert.equal(emp2.형식오류, true);
});

test('press 는 run_at 과 rounds 만 있으면 읽는다', () => {
  const [, press] = 도메인현황(
    { press: { run_at: '2026-09-12T06:36:55+09:00', rounds: 3 } }, 지금);
  assert.equal(press.형식오류, false);
  assert.deepEqual(press.지표, [{ 라벨: '회차', 값: 3 }]);
});

test('press 는 rounds 가 숫자가 아니면 형식을 못 읽음이다', () => {
  const [, press] = 도메인현황(
    { press: { run_at: '2026-09-12T06:36:55+09:00', rounds: '3' } }, 지금);
  assert.equal(press.형식오류, true);
  assert.equal(press.이유, '형식을 못 읽음');
});

test('ask 는 카탈로그 실패를 경고로 낸다', () => {
  // run_at 을 지금과 가깝게 둬서 '하루 넘게 안 돌았다' 경고가 안 섞이게 한다
  // (그 경고는 별도 테스트에서 확인한다).
  const [, , , , ask] = 도메인현황(
    { ask: { run_at: '2026-09-12T08:00:00+09:00', catalog: { ok: false } } }, 지금);
  assert.equal(ask.형식오류, false);
  assert.deepEqual(ask.지표, [{ 라벨: '카탈로그', 값: '실패' }]);
  assert.deepEqual(ask.경고, ['카탈로그 갱신 실패']);
});

// reports 는 `at` 이고, 실측(2026-09-12)에서 2,236건 중 356건이 판정 실패로
// 미판정인 채 아무 데도 안 보이던 문제 그 자체다 — 이게 이 구역의 핵심 확인
// 사항이다.
test('reports 는 전체 대비 판정 수의 차이를 미판정으로 보인다', () => {
  const [, , , reports] = 도메인현황({
    reports: {
      at: '2026-09-11T23:36:32+09:00',
      boards: { 'kli-research': { ok: true }, 'kdi-report': { ok: true } },
      unregistered: [],
      reports: 2236,
      recommend: { judged: 1880, picked: 200, profile_version: 'abc' },
    },
  }, 지금);
  assert.equal(reports.형식오류, false);
  const 미판정지표 = reports.지표.find((m) => m.라벨 === '미판정');
  assert.equal(미판정지표.값, 356);
  assert.ok(reports.경고.some((w) => w.includes('356')));
});

test('reports 는 recommend 블록이 아예 없으면 판정 기록 없음이라 말한다', () => {
  const [, , , reports] = 도메인현황({
    reports: {
      at: '2026-09-11T23:36:32+09:00', boards: {}, unregistered: [], reports: 2236,
    },
  }, 지금);
  const 미판정지표 = reports.지표.find((m) => m.라벨 === '미판정');
  assert.equal(미판정지표.값, '판정 기록 없음');
  assert.ok(reports.경고.includes('판정 기록 없음'));
});

test('reports 는 판정 자체가 실패했으면 그 사유를 경고에 낸다', () => {
  const [, , , reports] = 도메인현황({
    reports: {
      at: '2026-09-11T23:36:32+09:00', boards: {}, unregistered: [], reports: 10,
      recommend: { judged: 5, picked: 0, profile_version: 'abc',
        error: 'API 가 429 를 돌려줬다: insufficient_quota' },
    },
  }, 지금);
  assert.ok(reports.경고.some((w) => w.includes('429')));
});

test('게시판 실패와 미등록도 reports 경고에 낸다', () => {
  const [, , , reports] = 도메인현황({
    reports: {
      at: '2026-09-11T23:36:32+09:00',
      boards: { 'kli-research': { ok: false, error: '실패' } },
      unregistered: ['https://x/새게시판'],
      reports: 5, recommend: { judged: 5, picked: 0, profile_version: 'abc' },
    },
  }, 지금);
  assert.ok(reports.경고.some((w) => w.includes('kli-research')));
  assert.ok(reports.경고.some((w) => w.includes('미등록')));
});

test('at 이 없으면(run_at 만 있으면) reports 도 형식을 못 읽음이다', () => {
  const [, , , reports] = 도메인현황({
    reports: { run_at: '2026-09-11T23:36:32+09:00', boards: {}, reports: 5 },
  }, 지금);
  assert.equal(reports.형식오류, true);
  assert.equal(reports.이유, '형식을 못 읽음');
});

test('하루 넘게 안 돌았으면 경고 맨 앞에 그 사실을 낸다', () => {
  const [, , , , ask] = 도메인현황(
    { ask: { run_at: '2026-09-08T00:00:00+09:00', catalog: { ok: true } } }, 지금);
  assert.equal(ask.형식오류, false);
  assert.ok(ask.경과시간 >= 24);
  assert.match(ask.경고[0], /시간째 안 돌았다/);
});

test('24시간 안이면 경과 경고를 안 낸다', () => {
  const [, press] = 도메인현황(
    { press: { run_at: '2026-09-12T06:36:55+09:00', rounds: 1 } }, 지금);
  assert.ok(press.경과시간 < 24);
  assert.deepEqual(press.경고, []);
});

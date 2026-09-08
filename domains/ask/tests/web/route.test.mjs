import { test } from 'node:test';
import assert from 'node:assert/strict';
import { route } from '../../worker/src/core/route.mjs';

// deps.db 가짜 — 네트워크도 D1 도 없이 돈다
function fakeDb(rows) {
  return { all: async (sql) => (sql.includes('capability_limit') ? rows.limits : rows.caps) };
}
const rows = {
  caps: [
    { source_id: 'eaps', 집단축: '["산업","성","연령"]', 시간입도: '["월"]', 지역입도: '["전국"]', 주제: '["취업자수"]' },
    { source_id: 'est',  집단축: '["산업"]',            시간입도: '["월"]', 지역입도: '["전국"]', 주제: '["종사자수"]' },
    { source_id: 'ei',   집단축: '["산업","성","연령"]', 시간입도: '["월"]', 지역입도: '["전국"]', 주제: '["상시가입자수"]' },
  ],
  limits: [
    { id: 'L1', source_id: 'est', 유형: '교차제한', axis: '연령',
      내용: '연령별을 발표하지 않는다', 사유: '공표표 없음' },
  ],
};

test('연령 축을 못 내는 출처는 불가로, 사유와 함께 나온다', async () => {
  const r = await route({ db: fakeDb(rows) }, { 집단축: ['연령'], 시간입도: '월', 지역입도: '전국' });
  assert.deepEqual(r.가능.sort(), ['eaps', 'ei']);
  assert.deepEqual(r.불가.map((x) => x.source), ['est']);
  assert.match(r.불가[0].사유, /연령별을 발표하지 않는다/);
});

test('축 일부만 되면 부분으로 나온다', async () => {
  const r = await route({ db: fakeDb(rows) }, { 집단축: ['산업', '연령'], 시간입도: '월', 지역입도: '전국' });
  assert.ok(r.부분.some((x) => x.source === 'est'));
  assert.match(r.부분.find((x) => x.source === 'est').사유, /산업/);
});

test('불가한 출처에는 우회경로가 붙는다', async () => {
  const r = await route({ db: fakeDb(rows) }, { 집단축: ['연령'], 시간입도: '월', 지역입도: '전국' });
  assert.ok(r.우회.length > 0);
  assert.match(r.우회[0].경로, /경제활동인구조사|eaps|ei/);
});

test('아무 출처도 안 걸리면 불가로 남고 증발하지 않는다', async () => {
  // C2 회귀 테스트: capability_limit 에 없는 축이라고 조용히 사라지면 안 된다 —
  // 요청축이 카탈로그 어디에도 없어도 후보(주제 필터 없음)인 이상 반드시 불가에 남는다.
  const r = await route({ db: fakeDb(rows) }, { 집단축: ['혈액형'], 시간입도: '월', 지역입도: '전국' });
  assert.deepEqual(r.가능, []);
  assert.deepEqual(r.부분, []);
  assert.deepEqual(r.불가.map((x) => x.source).sort(), ['eaps', 'ei', 'est']);
  for (const x of r.불가) {
    assert.match(x.사유, /혈액형을 낸다는 기록이 없다\(카탈로그 미등재\)/);
    assert.equal(x.limit_id, null);
  }
  // 요청 축을 내는 출처가 카탈로그 어디에도 없으므로 우회도 없다
  assert.deepEqual(r.우회, []);
});

test('주제가 안 맞는 출처는 후보가 아니다 — 불가로도 안 남고, 우회에서 주제 차이를 밝힌다', async () => {
  // C1 회귀 테스트: "종사자수를 연령별로" 물으면 취업자수·상시가입자수를 재는
  // eaps·ei 가 "가능" 이라고 답하면 안 된다. est 만 후보이고, est 는 연령을 못 낸다.
  const r = await route({ db: fakeDb(rows) },
    { 주제: '종사자수', 집단축: ['연령'], 시간입도: '월', 지역입도: '전국' });
  assert.deepEqual(r.가능, []);
  assert.deepEqual(r.부분, []);
  assert.deepEqual(r.불가.map((x) => x.source), ['est']);
  assert.match(r.불가[0].사유, /연령별을 발표하지 않는다/);
  // eaps·ei 는 주제가 다르므로 불가 목록에도 없다 — 후보 자체가 아니다
  assert.ok(!r.불가.some((x) => x.source === 'eaps'));
  assert.ok(!r.불가.some((x) => x.source === 'ei'));
  assert.equal(r.우회.length, 1);
  assert.deepEqual(r.우회[0].경로.match(/eaps|ei/g).sort(), ['eaps', 'ei']);
  assert.match(r.우회[0].제약, /주제가 다르다/);
  assert.match(r.우회[0].제약, /취업자수/);
  assert.match(r.우회[0].제약, /상시가입자수/);
});

test('주제가 맞는 출처만 후보가 된다 — 다른 주제의 출처는 등장하지 않는다', async () => {
  const r = await route({ db: fakeDb(rows) },
    { 주제: '취업자수', 집단축: ['연령'], 시간입도: '월', 지역입도: '전국' });
  assert.deepEqual(r.가능, ['eaps']);
  assert.deepEqual(r.부분, []);
  assert.deepEqual(r.불가, []);
  // est(종사자수) 는 애초에 후보가 아니므로 어느 목록에도 없다
  assert.ok(!r.가능.includes('est'));
  assert.ok(!r.불가.some((x) => x.source === 'est'));
});

test('시간입도가 안 맞는 출처는 불가에 사유와 함께 들어간다', async () => {
  const rowsTime = {
    caps: [
      { source_id: 'eaps',       집단축: '["연령"]', 시간입도: '["월"]', 지역입도: '["전국"]', 주제: '["취업자수"]' },
      { source_id: 'annual_src', 집단축: '["연령"]', 시간입도: '["연"]', 지역입도: '["전국"]', 주제: '["취업자수"]' },
    ],
    limits: [],
  };
  const r = await route({ db: fakeDb(rowsTime) },
    { 집단축: ['연령'], 시간입도: '월', 지역입도: '전국' });
  assert.deepEqual(r.가능, ['eaps']);
  assert.deepEqual(r.불가.map((x) => x.source), ['annual_src']);
  assert.match(r.불가[0].사유, /월 단위를 내지 않는다/);
});

test('지역입도가 안 맞는 출처는 불가에 사유와 함께 들어간다', async () => {
  const rowsRegion = {
    caps: [
      { source_id: 'eaps',      집단축: '["연령"]', 시간입도: '["월"]', 지역입도: '["전국"]',   주제: '["취업자수"]' },
      { source_id: 'region_src', 집단축: '["연령"]', 시간입도: '["월"]', 지역입도: '["광역시"]', 주제: '["취업자수"]' },
    ],
    limits: [],
  };
  const r = await route({ db: fakeDb(rowsRegion) },
    { 집단축: ['연령'], 시간입도: '월', 지역입도: '전국' });
  assert.deepEqual(r.가능, ['eaps']);
  assert.deepEqual(r.불가.map((x) => x.source), ['region_src']);
  assert.match(r.불가[0].사유, /전국 입도를 내지 않는다/);
});

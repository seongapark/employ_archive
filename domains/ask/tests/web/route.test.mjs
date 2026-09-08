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

test('아무 출처도 안 걸리면 전부 빈 배열이다', async () => {
  const r = await route({ db: fakeDb(rows) }, { 집단축: ['혈액형'], 시간입도: '월', 지역입도: '전국' });
  assert.deepEqual(r.가능, []);
  assert.deepEqual(r.부분, []);
});

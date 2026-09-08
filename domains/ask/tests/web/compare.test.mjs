import { test } from 'node:test';
import assert from 'node:assert/strict';
import { compare } from '../../worker/src/core/compare.mjs';

const rows = [
  { id: 'C1', source_a: 'eaps', source_b: 'ei', 차이유형: '개념',
    설명: '취업자수 vs 상시가입자수', 비교가능: '증감률만',
    evidence: '저장소', verified_at: '2026-09-08' },
  { id: 'C2', source_a: 'eaps', source_b: 'ei', 차이유형: '모집단',
    설명: '15세 이상 전체 vs 고용보험 가입자', 비교가능: '증감률만',
    evidence: '저장소', verified_at: '2026-09-08' },
];
const db = { all: async () => rows };

test('같은 쌍의 여러 차이유형을 모두 담는다', async () => {
  // 경활↔행정통계는 개념이면서 동시에 모집단 차이다. 하나로 뭉개면 안 된다
  const r = await compare({ db }, { source_a: 'eaps', source_b: 'ei' });
  assert.deepEqual(r.차이유형.sort(), ['개념', '모집단']);
  assert.equal(r.설명.length, 2);
});

test('가장 보수적인 비교가능 판정을 고른다', async () => {
  const r = await compare({ db }, { source_a: 'eaps', source_b: 'ei' });
  assert.equal(r.비교가능, '증감률만');
});

test('불가가 하나라도 있으면 불가로 떨어진다', async () => {
  const d = { all: async () => [...rows, { ...rows[0], id: 'C3', 비교가능: '불가' }] };
  const r = await compare({ db: d }, { source_a: 'eaps', source_b: 'ei' });
  assert.equal(r.비교가능, '불가');
});

test('충돌 기록이 없으면 불가로 답한다 — 모르면 비교를 허용하지 않는다', async () => {
  const r = await compare({ db: { all: async () => [] } }, { source_a: 'x', source_b: 'y' });
  assert.equal(r.비교가능, '불가');
  assert.match(r.설명[0], /기록이 없다/);
});

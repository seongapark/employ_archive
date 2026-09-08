import { test } from 'node:test';
import assert from 'node:assert/strict';
import { meta } from '../../worker/src/core/meta.mjs';

const DB = {
  source_catalog: [
    { id: 'est', name_ko: '사업체노동력조사', grade: 'B', archived: 1,
      evidence: '저장소', verified_at: '2026-09-08', evidence_status: '확인' },
    { id: 'kdi_openapi', name_ko: 'KDI OpenAPI', grade: 'B', archived: 0,
      evidence: null, verified_at: null, evidence_status: '미확인' },
    { id: 'eaps', name_ko: '경제활동인구조사', grade: 'B', archived: 1,
      evidence: '저장소', verified_at: '2026-09-08', evidence_status: '확인' },
  ],
  capability_limit: [
    { id: 'L1', source_id: 'est', 유형: '교차제한', axis: '연령',
      내용: '연령별을 발표하지 않는다', 사유: '공표표 없음', evidence_status: '확인' },
    { id: 'L2', source_id: 'eaps', 유형: '커버리지', axis: null,
      내용: '15세 이상', 사유: '군인 제외', evidence_status: '확인' },
  ],
  source_conflict: [
    { id: 'C1', source_a: 'eaps', source_b: 'est', 차이유형: '개념',
      설명: '취업자수 vs 종사자수', 비교가능: '증감률만' },
  ],
};
const db = {
  all: async (sql, p = []) => {
    const t = ['source_catalog', 'capability_limit', 'source_conflict']
      .find((n) => sql.includes(n));
    const rows = DB[t];
    if (!p.length) {
      // 하네스 결함 수정: 실제 meta() 는 출처가 없으면
      // 'SELECT * FROM source_catalog WHERE archived = 1' 를 쓴다.
      // 가짜 db 도 그 조건을 실제로 걸어야 '보유 중인 소스만' 을 검증할 수 있다.
      return sql.includes('archived = 1') ? rows.filter((r) => r.archived === 1) : rows;
    }
    return rows.filter((r) => p.includes(r.id) || p.includes(r.source_id)
                           || p.includes(r.source_a) || p.includes(r.source_b));
  },
};

test('요청한 소스만 담는다 — 카탈로그 전체를 넣지 않는다', async () => {
  const m = await meta({ db }, { 출처: ['est'] });
  assert.deepEqual(m.소스.map((s) => s.id), ['est']);
  assert.deepEqual(m.한계.map((l) => l.id), ['L1']);
});

test('여러 소스를 주면 그 소스들의 충돌까지 담는다', async () => {
  const m = await meta({ db }, { 출처: ['eaps', 'est'] });
  assert.equal(m.충돌.length, 1);
});

test('미확인 소스는 별도 목록으로 갈라 담는다', async () => {
  // "안 됩니다" 와 "아직 확인 못 했습니다" 는 다른 답이다
  const m = await meta({ db }, { 출처: ['kdi_openapi'] });
  assert.deepEqual(m.미확인.map((s) => s.id), ['kdi_openapi']);
});

test('출처를 안 주면 보유 중인 소스만 담는다', async () => {
  const m = await meta({ db }, { 출처: [] });
  assert.deepEqual(m.소스.map((s) => s.id).sort(), ['eaps', 'est']);
});

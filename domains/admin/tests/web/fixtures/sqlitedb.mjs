// 실제 SQLite 에 실제 마이그레이션을 적용하고, 워커가 쓰는 {all,one,run} 모양만
// 씌운다. D1 도 SQLite 라서 이 대역은 실물보다 관대할 수 없다 — 문법 오류도
// 제약 위반도 여기서 그대로 터진다.
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const 여기 = dirname(fileURLToPath(import.meta.url));
const 마이그레이션 = join(여기, '..', '..', '..', 'worker', 'migrations', '0001_init.sql');

export function 열린DB() {
  const raw = new DatabaseSync(':memory:');
  raw.exec(readFileSync(마이그레이션, 'utf8'));
  // node:sqlite 는 행을 프로토타입이 null 인 객체로 낸다. 실물 D1 은 JSON 으로
  // 직렬화된 평범한 객체를 낸다 — 여기서 맞춰 주지 않으면 집계 코드가 그대로
  // 돌려주는 행이 `assert.deepEqual` 에서 값은 같아도 프로토타입이 달라 깨진다.
  const db = {
    all: async (sql, params = []) => raw.prepare(sql).all(...params).map((r) => ({ ...r })),
    one: async (sql, params = []) => {
      const r = raw.prepare(sql).get(...params);
      return r ? { ...r } : null;
    },
    run: async (sql, params = []) => { raw.prepare(sql).run(...params); },
  };
  return { db, raw };
}

export function 줄(덮어쓰기 = {}) {
  return {
    ts: '2026-09-11T01:00:00Z', day: '2026-09-11', domain: 'employment',
    path: '/', visitor: 'v1', session: 's1', ref: null, ref_kind: 'direct',
    mode: 'browser', device: 'mobile', country: 'KR', ...덮어쓰기,
  };
}

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { 기록, 일일상한 } from '../../worker/src/core/write.mjs';
import { 열린DB, 줄 } from './fixtures/sqlitedb.mjs';

test('첫 방문은 hit 과 visitor 를 함께 만든다', async () => {
  const { db, raw } = 열린DB();
  assert.equal(await 기록(db, 줄()), true);
  assert.equal(raw.prepare('SELECT COUNT(*) n FROM hit').get().n, 1);
  const v = raw.prepare('SELECT * FROM visitor WHERE id = ?').get('v1');
  assert.equal(v.first_day, '2026-09-11');
  assert.equal(v.last_day, '2026-09-11');
  assert.equal(v.hits, 1);
  assert.equal(v.day_hits, 1);
});

test('같은 날 다시 오면 day_hits 가 는다', async () => {
  const { db, raw } = 열린DB();
  await 기록(db, 줄());
  await 기록(db, 줄({ path: '/b/industry' }));
  const v = raw.prepare('SELECT * FROM visitor WHERE id = ?').get('v1');
  assert.equal(v.hits, 2);
  assert.equal(v.day_hits, 2);
});

// 이 초기화가 없으면 오래 쓴 방문자가 언젠가 상한에 걸려 영영 안 세어진다.
test('날이 바뀌면 day_hits 가 1 로 돌아가고 first_day 는 안 변한다', async () => {
  const { db, raw } = 열린DB();
  await 기록(db, 줄());
  await 기록(db, 줄({ day: '2026-09-20', ts: '2026-09-20T01:00:00Z' }));
  const v = raw.prepare('SELECT * FROM visitor WHERE id = ?').get('v1');
  assert.equal(v.first_day, '2026-09-11');
  assert.equal(v.last_day, '2026-09-20');
  assert.equal(v.hits, 2);
  assert.equal(v.day_hits, 1);
});

test('일일 상한을 넘으면 hit 을 안 쌓는다', async () => {
  const { db, raw } = 열린DB();
  for (let i = 0; i < 일일상한; i += 1) assert.equal(await 기록(db, 줄()), true);
  assert.equal(await 기록(db, 줄()), false);
  assert.equal(raw.prepare('SELECT COUNT(*) n FROM hit').get().n, 일일상한);
});

test('상한을 넘겨도 다음 날에는 다시 쌓는다', async () => {
  const { db, raw } = 열린DB();
  for (let i = 0; i <= 일일상한; i += 1) await 기록(db, 줄());
  assert.equal(await 기록(db, 줄({ day: '2026-09-12', ts: '2026-09-12T01:00:00Z' })), true);
  assert.equal(raw.prepare('SELECT COUNT(*) n FROM hit WHERE day = ?').get('2026-09-12').n, 1);
});

test('스키마가 인덱스를 갖춘다', () => {
  const { raw } = 열린DB();
  const names = raw.prepare("SELECT name FROM sqlite_master WHERE type='index'").all()
    .map((r) => r.name);
  for (const n of ['hit_day', 'hit_domain_day', 'visitor_first']) assert.ok(names.includes(n), n);
});

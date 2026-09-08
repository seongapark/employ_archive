// 골든 6건을 LLM 없이 돌린다. 슬롯이 고정 입력이라 1패스를 건너뛰고,
// `llm: null` 이라 2패스도 없다 — 완전히 결정적이다.
//
// **어느 기대를 단언하고 어느 기대를 안 하는지 여기 적어 둔다.** 조용히 빼면 골든이
// 무의미해진다.
//   단언한다: 유형 · 라우팅(가능·부분·불가) · 한계포함 · 배지 · 판정 · 현상 · 가설 ·
//             지지/반증 증거 · 비교가능 · 차이유형 · 답변 null
//   조건부로 단언한다:
//     · `근거지표` — 관측이 실제로 실린 근거가 있을 때만. `observation` 이 비어 있는
//       지금은 모든 골든에서 건너뛰고, 적재기가 붙으면 저절로 켜진다.
//   단언하지 않는다:
//     · `한계유형` · `답할수있는질문` — 코드가 그 형태로 내지 않는 문서용 필드다.
//     · `우회경로` 의 **문구** — 기대는 소스를 한글 이름으로 적었고(`경제활동인구조사 ·
//       고용행정통계`), route() 는 소스 id 로 적는다(`eaps·ei`). 문구를 맞추려고
//       route 를 고치면 Task 7 의 테스트와 부딪히고, 기대를 고치면 골든이 무뎌진다.
//       그래서 **문구 대신 존재**를 단언한다 — "못 준다로 끝내지 않는다" 가 이 기대의
//       내용이고, 그건 지금도 검사된다.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ask } from '../../worker/src/core/ask.mjs';
import { makeFakeDb } from './fixtures/fakedb.mjs';

const DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'golden');

// 가설의 "증거" 는 buildEvidence 를 탄 행이다 — data_status 가 '보유' 라 실제로
// 조회가 일어난 행만 `유의성` 을 단다. 미보유 지표는 값 대신 확보 경로를 낸다.
const 증거인가 = (x) => x.유의성 !== undefined;

for (const f of readdirSync(DIR).filter((n) => n.endsWith('.json'))) {
  const c = JSON.parse(readFileSync(join(DIR, f), 'utf8'));
  test(`골든: ${c.이름}`, async () => {
    // llm: null — 1패스를 건너뛰고 LLM 없이 돈다. 완전히 결정적이다
    const r = await ask({ db: makeFakeDb(), llm: null },
                        { 유형: c.유형, 슬롯: c.슬롯 });
    assert.equal(r.유형, c.유형);

    if (c.기대.라우팅) {
      assert.deepEqual([...r.라우팅.가능].sort(), [...c.기대.라우팅.가능].sort());
      assert.deepEqual(r.라우팅.부분.map((x) => x.source).sort(),
                       [...(c.기대.라우팅.부분 ?? [])].sort());
      assert.deepEqual(r.라우팅.불가.map((x) => x.source).sort(),
                       [...c.기대.라우팅.불가].sort());
    }

    for (const 문구 of c.기대.한계포함 ?? []) {
      assert.ok(r.한계.some((l) => l.includes(문구)),
                `한계에 "${문구}" 가 없다: ${JSON.stringify(r.한계)}`);
    }
    // 배지는 **집합 일치**로 단언한다. 포함 검사면 `배지: []` 가 아무것도 검사하지 않아
    // "붙으면 안 되는 배지가 붙었다" 를 통째로 놓친다.
    if (c.기대.배지) assert.deepEqual([...r.배지].sort(), [...c.기대.배지].sort());

    // 근거지표는 **관측이 실제로 실렸을 때만** 단언한다. `observation` 이 비어 있는
    // 지금은 모든 골든에서 건너뛴다 — 적재기가 붙는 날 저절로 켜진다. 억지로 단언하면
    // 근거가 0개라 항상 참이 되는 공허한 검사가 된다.
    if ((c.기대.근거지표 ?? []).length && r.근거?.length) {
      const 실제 = new Set(r.근거.flatMap(
        (e) => (e.관측 ?? []).map((o) => `${e.지표}:${o.기간}`)));
      for (const k of c.기대.근거지표) {
        assert.ok(실제.has(k), `근거지표 ${k} 없음: ${JSON.stringify([...실제])}`);
      }
    }

    if (c.기대.현상) assert.equal(r.현상?.id, c.기대.현상);
    for (const id of c.기대.가설 ?? []) {
      assert.ok(r.가설?.some((h) => h.id === id), `가설 ${id} 없음`);
    }
    if (c.기대.판정) {
      for (const [id, exp] of Object.entries(c.기대.판정)) {
        const h = r.가설.find((x) => x.id === id);
        assert.ok(h, `가설 ${id} 없음`);
        assert.equal(h.판정.verdict_capable, exp.verdict_capable);
        assert.equal(h.판정.verdict_blocked_by, exp.verdict_blocked_by);
      }
    }
    if (c.기대.지지증거_비어있지않음) {
      assert.ok(r.가설.some((h) => h.지지.some(증거인가)), '지지 증거가 하나도 없다');
    }
    if (c.기대.반증증거_비어있음) {
      assert.ok(r.가설.every((h) => !h.반증.some(증거인가)),
                '반증 증거가 비어 있어야 하는데 값이 실렸다');
    }

    if (c.기대.비교가능) assert.equal(r.비교.비교가능, c.기대.비교가능);
    if (c.기대.차이유형) {
      assert.deepEqual([...r.비교.차이유형].sort(), [...c.기대.차이유형].sort());
    }
    if ((c.기대.우회경로 ?? []).length) {
      assert.ok((r.우회경로 ?? []).length > 0, '우회경로를 내지 않았다');
    }

    // LLM 이 없으면 답변 문장은 없고 카드만 남는다
    assert.equal(r.답변, null);
  });
}

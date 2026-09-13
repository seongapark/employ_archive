// 비슷한 말. **표로 푼다 — LLM 을 부르지 않는다.**
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { 확장, 무리 } from '../../worker/src/lookup/synonyms.mjs';
import { lookup } from '../../worker/src/lookup/search.mjs';

test('같은 무리의 말을 서로 찾는다', () => {
  // trigram 은 글자가 그대로 맞아야 걸린다 — '정년' 을 물으면 '계속고용' 이라고 쓴
  // 보고서가 한 건도 안 걸렸다.
  assert.ok(확장(['정년', '연장']).includes('계속고용'));
  assert.ok(확장(['계속고용']).includes('정년'));
  assert.ok(확장(['고용상황']).includes('취업'));
});

test('원어는 확장어에 넣지 않는다 — 같은 조회를 두 번 돌리는 셈이다', () => {
  const out = 확장(['고용', '일자리']);
  assert.equal(out.includes('고용'), false, JSON.stringify(out));
  assert.equal(out.includes('일자리'), false, JSON.stringify(out));
});

test('낱말을 품는 관계도 만난 것으로 센다', () => {
  // '청년고용률' 은 '청년고용' 을 품는다.
  assert.ok(확장(['청년고용률']).length, '무리를 못 찾았다');
});

test('상한을 둔다 — 두 글자 확장어는 전수 훑기를 탄다', () => {
  assert.ok(확장(['고용', '임금', '청년', '정년', '여성', '실업']).length <= 8);
});

test('아무 무리에도 안 닿으면 빈손이다', () => {
  assert.deepEqual(확장(['카페', '매출']), []);
  assert.deepEqual(확장([]), []);
});

test('무리 안에 같은 말을 두 번 적지 않는다', () => {
  const 전부 = 무리.flat();
  assert.equal(전부.length, new Set(전부).size, '중복된 낱말이 있다');
});

// ── 보충은 대체가 아니다 ──────────────────────────────────────────────────

test('원어로 자리가 차면 보충 조회를 던지지 않는다', async () => {
  // 회귀 방어: 잘 되던 질문의 순위가 확장 때문에 바뀌면 안 되고, D1 왕복도 안 늘어야 한다.
  const 행 = (i) => ({ doc_id: `reports:a${i}:초록:0`, 종류: '초록', 링크: '', 날짜: '2026-01-01',
                      제목: `정년 연장 연구 ${i}`, 본문: '정년 연장을 다룬다' });
  let 횟수 = 0;
  const deps = { db: { all: async (sql) => {
    if (!/doc_fts/.test(sql)) return [];
    횟수 += 1;
    return [1, 2, 3, 4, 5].map(행);
  } } };
  await lookup(deps, '정년 연장', { limit: 5 });
  // 도메인 넷 × 조회 한 번. 보충이 돌았다면 더 늘어난다.
  assert.equal(횟수, 4, `조회가 ${횟수}번 나갔다`);
});

test('자리가 남으면 비슷한 말로 채우고, 그 사실을 밝힌다', async () => {
  const deps = { db: { all: async (sql, p) => {
    if (!/doc_fts/.test(sql)) return [];
    const 보충 = String(p.join(' ')).includes('계속고용');
    if (!보충) return [];
    return [{ doc_id: 'reports:b:초록:0', 종류: '초록', 링크: '', 날짜: '2025-05-01',
              제목: '계속고용 제도 연구', 본문: '계속고용 제도를 검토한다' }];
  } } };
  const r = await lookup(deps, '정년 연장');
  const 보고서 = r.묶음.find((g) => g.도메인 === 'reports');
  assert.equal(보고서.결과.length, 1, JSON.stringify(보고서));
  assert.equal(보고서.결과[0].비슷한말, true);
  assert.match(보고서.사유, /비슷한 말로 찾았다/);
  // 비슷한 말로 걸린 글은 점수 0 이라 원어로 걸린 글 뒤에 선다.
  assert.equal(보고서.결과[0].점수, 0);
});

test('비슷한 말로 걸린 글도 스니펫이 걸린 자리를 보여준다', async () => {
  const deps = { db: { all: async (sql, p) => {
    if (!/doc_fts/.test(sql)) return [];
    if (!String(p.join(' ')).includes('계속고용')) return [];
    return [{ doc_id: 'reports:b:초록:0', 종류: '초록', 링크: '', 날짜: '2025-05-01',
              제목: '연구', 본문: `${'가'.repeat(200)} 계속고용 제도를 검토한다` }];
  } } };
  const r = await lookup(deps, '정년 연장');
  const 스니펫 = r.묶음.find((g) => g.도메인 === 'reports').결과[0].스니펫;
  assert.ok(스니펫.includes('계속고용'), 스니펫);
});

// ── 기사: 제목만 있다는 사실을 결과가 있을 때도 말한다 ────────────────────

test('기사는 제목만 색인됐다는 안내를 결과와 함께 낸다', async () => {
  const deps = { db: { all: async (sql, p) => {
    if (!/doc_fts/.test(sql)) return [];
    const 도메인 = /MATCH/.test(sql) ? p[1] : p[0];
    if (도메인 !== 'press') return [];
    return [{ doc_id: 'press:1:기사:0', 종류: '기사', 링크: 'https://x/1', 날짜: '2026-09-07',
              제목: '2026-09-07 한국일보 정규', 본문: '취업자 증가폭 확대' }];
  } } };
  const r = await lookup(deps, '취업자');
  const 기사 = r.묶음.find((g) => g.도메인 === 'press');
  assert.equal(기사.결과.length, 1);
  // 결과가 있을 때가 더 위험하다 — 요약이 내용을 아는 척할 수 있다.
  assert.match(기사.사유, /제목만 색인/);
});

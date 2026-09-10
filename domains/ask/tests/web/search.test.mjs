// FTS 조회·스니펫·도메인별 묶기. 네트워크에 나가지 않는다 — 가짜 D1 을 넣는다.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { 용어뽑기, 매치식, 스니펫, lookup } from '../../worker/src/lookup/search.mjs';

// ── 용어 뽑기: 질문을 통째로 던지면 아무것도 안 걸린다 ──────────────────────

test('질문을 낱말로 끊는다', () => {
  // "청년고용률이왜떨어졌나" 를 한 덩어리로 던지면 색인에 그런 글이 없어 0건이다.
  const t = 용어뽑기('청년 고용률이 왜 떨어졌나');
  assert.ok(t.includes('청년'), t);
  assert.ok(t.some((x) => x.startsWith('고용률')), t);
});

test('조사를 뗀다', () => {
  // trigram 은 글자 그대로 맞춰서, '고용률이' 로 던지면 '고용률을' 이 안 걸린다.
  assert.ok(용어뽑기('고용률이').includes('고용률'));
  assert.ok(용어뽑기('제조업에서').includes('제조업'));
  assert.ok(용어뽑기('청년의').includes('청년'));
});

test('두 글자 미만은 버린다', () => {
  // trigram 은 세 글자가 최소 단위다. '왜'·'수' 는 색인에 걸리지 않는다.
  assert.deepEqual(용어뽑기('왜 그럴까'), ['그럴까']);
});

test('같은 용어를 두 번 넣지 않는다', () => {
  assert.deepEqual(용어뽑기('고용 고용률 고용'), ['고용', '고용률']);
});

// ── 매치식 ──────────────────────────────────────────────────────────────

test('용어를 OR 로 묶고 따옴표로 감싼다', () => {
  // 따옴표가 없으면 FTS5 가 용어를 문법으로 읽어 구문 오류가 난다.
  assert.equal(매치식(['청년', '고용률']), '"청년" OR "고용률"');
});

test('용어가 없으면 빈 문자열이다', () => {
  assert.equal(매치식([]), '');
});

// ── 스니펫: 공백을 지운 색인에서 걸렸어도 원문 위치를 찾아야 한다 ──────────

test('걸린 자리를 원문에서 찾아 앞뒤를 보여준다', () => {
  const 본문 = '이 연구는 청년 고용률 하락의 원인을 인구구조 변화에서 찾는다. 그리고 정책을 제언한다.';
  const s = 스니펫(본문, ['인구구조'], 12);
  assert.ok(s.includes('인구구조'), s);
  assert.ok(s.length < 본문.length, s);
});

test('원문에 공백이 끼어 있어도 찾는다', () => {
  // 색인은 공백을 지운 사본이라 "청년 고용" 이 "청년고용" 으로 걸린다.
  // 원문에서 그 자리를 못 찾으면 스니펫이 엉뚱한 데서 잘린다.
  const s = 스니펫('앞말이다. 청년 고용 실태를 본다. 뒷말이다.', ['청년고용'], 10);
  assert.ok(s.includes('청년 고용'), s);
});

test('아무 용어도 안 걸리면 앞부분을 준다', () => {
  const s = 스니펫('가나다라마바사아자차카타파하'.repeat(10), ['없는말'], 10);
  assert.ok(s.startsWith('가나다라'), s);
});

// ── 묶기 ────────────────────────────────────────────────────────────────

const 가짜DB = (rows) => ({
  all: async (sql, p) => {
    if (/doc_fts/.test(sql)) {
      const 도메인 = p[p.length - 2];
      return (rows[도메인] ?? []).map((r) => ({ ...r, 도메인 }));
    }
    return rows.observation ?? [];
  },
});

test('도메인별로 묶어 낸다', async () => {
  const deps = { db: 가짜DB({
    reports: [{ 종류: '초록', 제목: '청년 고용 연구', 본문: '청년 고용률이 하락했다',
                링크: 'https://kli/1' }],
    forecast: [{ 종류: '전망근거', 제목: 'KDI 2026-05', 본문: '취업자 증가폭이 둔화된다',
                 링크: 'https://kdi/1' }],
  }) };
  const r = await lookup(deps, '청년 고용률');
  const 보고서 = r.묶음.find((g) => g.도메인 === 'reports');
  assert.equal(보고서.결과[0].제목, '청년 고용 연구');
  assert.equal(보고서.결과[0].근거유형, '초록');
  assert.equal(보고서.결과[0].링크, 'https://kli/1');
  assert.ok(보고서.결과[0].스니펫);
});

test('해당 없는 도메인은 사유와 함께 따로 낸다', async () => {
  const r = await lookup({ db: 가짜DB({}) }, '정년 연장 논의');
  assert.ok(r.해당없음.some((x) => x.도메인 === 'employment' && /어떤 통계/.test(x.사유)),
            JSON.stringify(r.해당없음));
});

test('걸린 게 없으면 빈손이라고 말한다', async () => {
  const r = await lookup({ db: 가짜DB({}) }, '청년 고용률');
  const 보고서 = r.묶음.find((g) => g.도메인 === 'reports');
  assert.deepEqual(보고서.결과, []);
  assert.match(보고서.사유, /걸리는 글이 없다/);
});

test('LLM 을 부르지 않는다', async () => {
  // deps.llm 을 아예 안 넣어도 돌아야 한다 — 넣으면 언젠가 쓰게 된다.
  const r = await lookup({ db: 가짜DB({}) }, '청년 고용률');
  assert.ok(r.묶음.length >= 3);
});

test('세 글자 미만 질의는 LIKE 로 훑는다', async () => {
  // trigram 은 세 글자가 최소 단위라 '고용' 이 색인으로는 0건이다.
  const 본 = [];
  const deps = { db: { all: async (sql, p) => { 본.push(sql); return []; } } };
  await lookup(deps, '고용');
  assert.ok(본.some((s) => /LIKE/.test(s)), 본.join('\n'));
  assert.equal(본.some((s) => /MATCH/.test(s)), false);
});


// ── 두 글자 낱말: 한국어에서 가장 중요한 말들이 여기 있다 ──────────────────

test('두 글자 낱말도 함께 찾는다', async () => {
  // '청년'·'정년'·'임금' 은 trigram 최소 길이(3)에 걸려 색인으로는 못 찾는다.
  // 버리면 질문의 핵심어가 통째로 사라진다 — LIKE 로 함께 훑는다.
  const 본 = [];
  const deps = { db: { all: async (sql, p) => { 본.push({ sql, p }); return []; } } };
  await lookup(deps, '청년 고용률');
  const match = 본.filter((x) => /MATCH/.test(x.sql));
  const like = 본.filter((x) => /LIKE/.test(x.sql));
  assert.ok(match.length, '세 글자 이상은 색인으로 찾아야 한다');
  assert.ok(like.length, '두 글자는 LIKE 로 찾아야 한다');
  assert.ok(like.some((x) => x.p.some((v) => String(v).includes('청년'))),
            JSON.stringify(like.map((x) => x.p)));
});

test('같은 글이 두 경로로 걸려도 한 번만 낸다', async () => {
  const row = { 종류: '초록', 제목: '청년 고용 연구', 본문: '청년 고용률이 하락했다', 링크: '' };
  const deps = { db: { all: async (sql, p) => (/doc_fts/.test(sql) ? [row] : []) } };
  const r = await lookup(deps, '청년 고용률');
  const 보고서 = r.묶음.find((g) => g.도메인 === 'reports');
  assert.equal(보고서.결과.length, 1, JSON.stringify(보고서.결과));
});


test('여러 낱말이 걸린 글이 위로 온다', async () => {
  // '정년 연장이 고용에 미치는 영향' 은 낱말이 전부 두 글자라 LIKE 로만 찾는데,
  // '고용' 은 거의 모든 글에 있다. 걸린 낱말 수로 정렬하지 않으면 '고용' 하나만
  // 걸린 글이 '정년+연장+고용' 이 다 걸린 글보다 위로 온다.
  let sql = '';
  const deps = { db: { all: async (s, p) => { if (/LIKE/.test(s)) sql = s; return []; } } };
  await lookup(deps, '정년 연장이 고용에 미치는 영향');
  assert.match(sql, /ORDER BY/);
  // 걸린 낱말 수를 더해 내림차순으로 세운다
  assert.match(sql, /LIKE \?\)\s*\+/);
});


test('낱말이 여럿이면 하나만 걸린 글은 버린다', async () => {
  // '고용' 은 이 저장소의 거의 모든 글에 있다. 그것 하나만 걸린 글을 "정년 연장"
  // 질문의 답으로 내밀면 묻지 않은 것을 답한 셈이다.
  let p = null;
  const deps = { db: { all: async (s, q) => { if (/LIKE/.test(s)) p = { s, q }; return []; } } };
  await lookup(deps, '정년 연장이 고용에 미치는 영향');
  assert.match(p.s, />=\s*\?/);
  assert.ok(p.q.includes(2), JSON.stringify(p.q));
});

test('낱말이 하나뿐이면 그 하나로 찾는다', async () => {
  let p = null;
  const deps = { db: { all: async (s, q) => { if (/LIKE/.test(s)) p = { s, q }; return []; } } };
  await lookup(deps, '임금');
  assert.ok(p.q.includes(1), JSON.stringify(p.q));
});


test('같은 문서의 다른 조각을 두 번 내지 않는다', async () => {
  // 초록 한 건이 여러 청크로 쪼개져 있다. 조각 단위로 추리면 다섯 자리가 같은
  // 보고서로 다 차서, 다른 보고서를 볼 기회가 사라진다(실측: "고령 노동과 소득 크레바스").
  const 조각 = (i) => ({ doc_id: `reports:kli-1:초록:${i}`, 종류: '초록',
                        제목: '같은 보고서', 본문: `${i}번째 조각이다`, 링크: '' });
  const 다른 = { doc_id: 'reports:kli-2:초록:0', 종류: '초록',
                제목: '다른 보고서', 본문: '다른 글이다', 링크: '' };
  // 같은 보고서가 게시판 둘에 올라가 **id 는 다른데 제목이 같은** 경우가 실제로 있다.
  const 쌍둥이 = { doc_id: 'reports:kli-3:초록:0', 종류: '초록',
                  제목: '같은 보고서', 본문: '또 같은 글이다', 링크: '' };
  const deps = { db: { all: async (s) => (/doc_fts/.test(s) ? [조각(0), 조각(1), 쌍둥이, 다른] : []) } };
  const r = await lookup(deps, '청년 고용률');
  const 보고서 = r.묶음.find((g) => g.도메인 === 'reports');
  assert.deepEqual(보고서.결과.map((x) => x.제목), ['같은 보고서', '다른 보고서']);
});

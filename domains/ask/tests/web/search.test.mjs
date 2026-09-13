// FTS 조회·스니펫·도메인별 묶기. 네트워크에 나가지 않는다 — 가짜 D1 을 넣는다.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { 용어뽑기, 매치식, 스니펫, 점수, lookup } from '../../worker/src/lookup/search.mjs';

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
  // 원어 조회는 도메인마다 먼저 한 번 나간다 — 그 첫 조회에 MATCH 가 없어야 한다.
  // (그 뒤 자리가 안 차면 비슷한 말로 보충하는데, 그쪽은 세 글자 말을 담아 MATCH 를 쓴다.)
  const 본 = [];
  const deps = { db: { all: async (sql, p) => { 본.push(sql); return []; } } };
  await lookup(deps, '고용');
  const 색인조회 = 본.filter((s) => /doc_fts/.test(s));
  assert.ok(색인조회.some((s) => /LIKE/.test(s)), 색인조회.join('\n'));
  assert.equal(/MATCH/.test(색인조회[0]), false, 색인조회[0]);
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
  // **첫 LIKE 조회만 본다.** 뒤따르는 보충 조회는 비슷한 말로 던지는 다른 조회다.
  const deps = { db: { all: async (s, p) => { if (/LIKE/.test(s) && !sql) sql = s; return []; } } };
  await lookup(deps, '정년 연장이 고용에 미치는 영향');
  assert.match(sql, /ORDER BY/);
  // 걸린 낱말 수를 더해 내림차순으로 세운다
  assert.match(sql, /LIKE \?\)\s*\+/);
});


test('낱말이 여럿이면 하나만 걸린 글은 버린다', async () => {
  // '고용' 은 이 저장소의 거의 모든 글에 있다. 그것 하나만 걸린 글을 "정년 연장"
  // 질문의 답으로 내밀면 묻지 않은 것을 답한 셈이다.
  let p = null;
  // 원어 조회에만 걸리는 규칙이다. 보충 조회는 하나만 걸려도 받는다(점수 0 으로 뒤에 선다).
  const deps = { db: { all: async (s, q) => { if (/LIKE/.test(s) && !p) p = { s, q }; return []; } } };
  await lookup(deps, '정년 연장이 고용에 미치는 영향');
  assert.match(p.s, />=\s*\?/);
  assert.ok(p.q.includes(2), JSON.stringify(p.q));
});

test('낱말이 하나뿐이면 그 하나로 찾는다', async () => {
  let p = null;
  const deps = { db: { all: async (s, q) => { if (/LIKE/.test(s) && !p) p = { s, q }; return []; } } };
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


test('관측이 가진 축을 고르고, 못 내는 축은 말한다', async () => {
  // "청년 사무직" 은 축이 둘(연령·직업)이다. 직업은 관측이 한 건도 없어서,
  // 첫 축만 보면 고용동향이 통째로 0건이 된다 — 연령으로는 낼 수 있는데도.
  const 본 = [];
  const deps = { db: { all: async (sql, p) => {
    본.push({ sql, p });
    if (!/observation/.test(sql)) return [];
    // queryObservations 는 최신만일 때 MAX(period) 를 먼저 묻고, 그 값으로 다시 묻는다.
    if (/MAX\(period\)/.test(sql)) return [{ 최신: '2026-08' }];
    return [{ source: 'eaps', breakdown: 'age', category: '15-29', period: '2026-08',
              value: 3428, unit: '천명', yoy: -142.7, release_url: '' }];
  } } };
  const r = await lookup(deps, '청년 사무직 취업자가 왜 줄었나');
  const 고용 = r.묶음.find((g) => g.도메인 === 'employment');
  assert.equal(고용.결과.length, 1, JSON.stringify(고용));
  assert.match(고용.사유 ?? '', /직업/);
});

// ── 순위: 도메인을 가로질러 견준다 ────────────────────────────────────────

test('점수는 제목에 걸린 낱말을 더 세게 본다', () => {
  const 제목걸림 = 점수({ 제목: '청년 고용 연구', 본문: '무관한 본문' }, ['청년']);
  const 본문걸림 = 점수({ 제목: '무관한 제목', 본문: '청년이 나온다' }, ['청년']);
  assert.ok(제목걸림 > 본문걸림, `${제목걸림} vs ${본문걸림}`);
});

test('점수는 공백을 무시한다 — 색인과 같은 규칙이다', () => {
  assert.ok(점수({ 제목: '', 본문: '청년 고용 실태' }, ['청년고용']) > 0);
});

test('잘 걸린 도메인이 위로 온다 — 배열 순서가 아니다', async () => {
  // 전에는 `글도메인` 배열 순서가 곧 화면 순서라 연구보고서가 늘 맨 위였다.
  const deps = { db: { all: async (sql, p) => {
    if (!/doc_fts/.test(sql)) return [];
    // MATCH 경로는 (식, 도메인, ...), LIKE 경로는 (도메인, ...) 이다. 두 글자 낱말만
    // 있는 질문은 LIKE 로만 간다 — 자리를 하나로 가정하면 가짜가 빈손을 준다.
    const 도메인 = /MATCH/.test(sql) ? p[1] : p[0];
    if (도메인 === 'press') {
      return [{ doc_id: 'press:1:기사:0', 종류: '기사', 링크: '', 날짜: '2026-09-07',
                제목: '정년 연장 합의', 본문: '정년 연장 논의가 이어진다' }];
    }
    if (도메인 === 'reports') {
      return [{ doc_id: 'reports:kli-1:초록:0', 종류: '초록', 링크: '', 날짜: '2019-03-01',
                제목: '무관한 보고서', 본문: '정년 이야기가 한 번 나온다' }];
    }
    return [];
  } } };
  const r = await lookup(deps, '정년 연장');
  const 글순서 = r.묶음.filter((g) => g.도메인 !== 'employment').map((g) => g.도메인);
  assert.equal(글순서[0], 'press', JSON.stringify(글순서));
});

test('점수가 같으면 새 글이 위다', async () => {
  const 행 = (id, 날짜) => ({ doc_id: id, 종류: '초록', 링크: '', 날짜,
                             제목: '정년 연장 연구', 본문: '같은 본문이다' });
  const deps = { db: { all: async (sql) => (/doc_fts/.test(sql)
    ? [행('reports:a:초록:0', '2014-05-01'), 행('reports:b:초록:0', '2026-05-01')] : []) } };
  const r = await lookup(deps, '정년 연장');
  const 보고서 = r.묶음.find((g) => g.도메인 === 'reports');
  assert.equal(보고서.결과[0].날짜, '2026-05-01', JSON.stringify(보고서.결과));
});

// ── 기간: 날짜 열로 거른다 ────────────────────────────────────────────────

test('기간을 물으면 날짜로 거르고, 날짜 없는 글은 남긴다', async () => {
  const 본 = [];
  const deps = { db: { all: async (sql, p) => { 본.push({ sql, p }); return []; } } };
  await lookup(deps, '2025년 정년 연장 논의');
  const 조회 = 본.filter((x) => /doc_fts/.test(x.sql));
  assert.ok(조회.length, '색인 조회가 없다');
  assert.ok(조회.every((x) => /날짜 = ''/.test(x.sql)), 조회[0].sql);
  // **자리수를 맞춘 값이어야 한다.** `'2025-12-15' <= '2025-12'` 는 거짓이라
  // 안 맞추면 12월 글이 통째로 빠진다.
  assert.ok(조회[0].p.includes('2025-01-01'), JSON.stringify(조회[0].p));
  assert.ok(조회[0].p.includes('2025-12-31'), JSON.stringify(조회[0].p));
});

// ── 넓은 질문: 한 점이 아니라 창 ──────────────────────────────────────────

const 관측DB = (본) => ({
  all: async (sql, p) => {
    본.push({ sql, p });
    if (!/observation/.test(sql)) return [];
    if (/MAX\(period\)/.test(sql)) return [{ 최신: '2026-08' }];
    const 창 = /period >= \?/.test(sql);
    const 행 = (period, value) => ({ source: 'eaps', breakdown: 'total', category: null,
                                    period, value, unit: '천명', yoy: 12.3, release_url: '' });
    return 창 ? [행('2025-08', 28000), 행('2026-07', 28900), 행('2026-08', 29151)]
              : [행('2026-08', 29151)];
  },
});

test('넓은 질문에는 추세 창을 열고 파생을 만든다', async () => {
  const 본 = [];
  const r = await lookup({ db: 관측DB(본) }, '최근 고용상황은?');
  const 고용 = r.묶음.find((g) => g.도메인 === 'employment');
  assert.equal(고용.관측.length, 3, JSON.stringify(고용.관측));
  // 차이·증감률은 두 점부터 생긴다. 한 점만 주면 여기가 늘 빈손이 된다.
  assert.equal(고용.파생.차이, 1151);
  assert.ok(고용.파생.증감률 != null);
  assert.match(고용.사유 ?? '', /추세를 본다/);
  // 화면은 최신부터 본다 — 조회는 period 오름차순이라 그대로 자르면 가장 오래된 게 박힌다.
  assert.match(고용.결과[0].제목, /2026-08/, JSON.stringify(고용.결과));
});

test('축을 집은 질문에는 창을 열지 않는다 — 단면이 사라진다', async () => {
  const 본 = [];
  const r = await lookup({ db: 관측DB(본) }, '30대 취업자');
  const 고용 = r.묶음.find((g) => g.도메인 === 'employment');
  assert.equal(고용.관측.length, 1, JSON.stringify(고용.관측));
  assert.equal(본.some((x) => /period >= \?/.test(x.sql)), false);
});

test('고용동향은 순위와 무관하게 맨 앞이다', async () => {
  const deps = { db: { all: async (sql, p) => {
    if (/MAX\(period\)/.test(sql)) return [{ 최신: '2026-08' }];
    if (/observation/.test(sql)) {
      return [{ source: 'eaps', breakdown: 'total', period: '2026-08', value: 1,
                unit: '천명', yoy: null, release_url: '' }];
    }
    if (/doc_fts/.test(sql) && p[1] === 'press') {
      return [{ doc_id: 'press:1:기사:0', 종류: '기사', 링크: '', 날짜: '2026-09-07',
                제목: '취업자 급증', 본문: '취업자가 늘었다' }];
    }
    return [];
  } } };
  const r = await lookup(deps, '취업자');
  assert.equal(r.묶음[0].도메인, 'employment', JSON.stringify(r.묶음.map((g) => g.도메인)));
});

// ── 계열: 안 걸러면 한 출처의 아홉 계열이 섞인다 ──────────────────────────

test('주제가 출처와 계열을 정한다', async () => {
  const 본 = [];
  const deps = { db: { all: async (sql, p) => {
    본.push({ sql, p });
    if (/MAX\(period\)/.test(sql)) return [{ 최신: '2026-08' }];
    return [];
  } } };
  await lookup(deps, '종사자 수 알려줘');
  const 관측 = 본.filter((x) => /observation/.test(x.sql));
  assert.ok(관측.length, '관측 조회가 없다');
  // 전에는 source 가 'eaps' 로 박혀 있어 종사자수를 물어도 경활을 읽었다.
  assert.ok(관측.every((x) => x.p.includes('est')), JSON.stringify(관측[0].p));
  // 계열을 안 걸면 취업자·실업자·인구·고용률이 같은 시점에 나란히 걸린다.
  assert.ok(관측.every((x) => /series = \?/.test(x.sql)), 관측[0].sql);
  assert.ok(관측.every((x) => x.p.includes('headcount')), JSON.stringify(관측[0].p));
});

test('계열을 걸러 한 시점에 한 줄만 남는다', async () => {
  // 실물에서 같은 제목(`2026-08 전체`)이 다섯 번 찍혔다. 계열이 다른 지표들이었다.
  const deps = { db: { all: async (sql, p) => {
    if (/MAX\(period\)/.test(sql)) return [{ 최신: '2026-08' }];
    if (!/observation/.test(sql)) return [];
    assert.ok(p.includes('headcount'), '계열 없이 조회했다');
    return [{ source: 'eaps', series: 'headcount', breakdown: 'total', category: null,
              period: '2026-08', value: 29151, unit: '천명', yoy: 12.3, release_url: '' }];
  } } };
  const r = await lookup(deps, '2026년 8월 취업자');
  const 고용 = r.묶음.find((g) => g.도메인 === 'employment');
  assert.equal(고용.결과.length, 1, JSON.stringify(고용.결과));
});

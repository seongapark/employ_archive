// 골든 세트는 6건의 대표 질문을 통째로 돌린다. 여기서는 그 아래에 깔린 규칙들을
// 하나씩 문다 — 골든이 초록인데 규칙이 깨져 있는 상태를 만들지 않기 위해서다.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask, verify, 관측축, 축_BREAKDOWN, 전망지표 } from '../../worker/src/core/ask.mjs';
import { makeFakeDb } from './fixtures/fakedb.mjs';

const 관측 = (unit) => [
  { source: 'eaps', breakdown: 'age', category: '30-39', period: '2026-06',
    value: 5300.1, ...(unit ? { unit } : {}), yoy: null, rse: null, rse_flag: null },
  { source: 'eaps', breakdown: 'age', category: '30-39', period: '2026-07',
    value: 5280.4, ...(unit ? { unit } : {}), yoy: null, rse: null, rse_flag: null },
];
const 수치슬롯 = {
  주제: '취업자수', 집단축: ['연령'], 지역입도: '전국', 시간입도: '월',
  기간: { from: '2026-06', to: '2026-07' }, 출처: [],
};

// ── 규칙 1: 가짜 db 의 표 선택 ───────────────────────────────────────────────
test('표 이름 13개 중 어느 것도 다른 표 이름에 단어경계로 걸리지 않는다', () => {
  const 이름들 = Object.keys(makeFakeDb().표);
  assert.equal(이름들.length, 13); // 표 12 + 판정 뷰 1
  const 오매칭 = [];
  for (const a of 이름들) {
    for (const b of 이름들) {
      if (a !== b && new RegExp(`\\b${a}\\b`).test(b)) 오매칭.push(`${a} ⊂ ${b}`);
    }
  }
  assert.deepEqual(오매칭, []);
});

test('WHERE 절의 열 이름이 표 이름과 같아도 엉뚱한 표를 읽지 않는다', async () => {
  const db = makeFakeDb({ forecast: [{ id: 'f1', org: 'KDI', indicator: 'emp_change' }] });
  // `phenomenon_id` 는 phenomenon 이 아니라 hypothesis 를 읽어야 한다
  const h = await db.all('SELECT * FROM hypothesis WHERE phenomenon_id = ?', ['청년사무직감소']);
  assert.ok(h.length > 0);
  assert.ok(h.every((x) => x.phenomenon_id === '청년사무직감소'));
  assert.ok(h.every((x) => 'name_ko' in x && '대립가설' in x));
  // `indicator` 는 열 이름이자 표 이름이다 — FROM 절이 forecast 라고 말한다
  const f = await db.all('SELECT * FROM forecast WHERE indicator = ?', ['emp_change']);
  assert.deepEqual(f.map((x) => x.id), ['f1']);
  // hypothesis_verdict 를 물으면 hypothesis 가 오면 안 된다
  const v = await db.all('SELECT * FROM hypothesis_verdict');
  assert.ok(v.every((x) => 'verdict_capable' in x));
});

test('WHERE 절을 실제로 적용한다 — 안 하면 걸러야 할 소스가 다 실린다', async () => {
  const db = makeFakeDb();
  const 전체 = await db.all('SELECT * FROM source_catalog');
  const 하나 = await db.all('SELECT * FROM source_catalog WHERE id IN (?)', ['est']);
  const 보관 = await db.all('SELECT * FROM source_catalog WHERE archived = 1');
  assert.ok(전체.length > 3);
  assert.deepEqual(하나.map((s) => s.id), ['est']);
  assert.deepEqual(보관.map((s) => s.id).sort(), ['eaps', 'ei', 'est']);
  // compare() 가 쓰는 괄호 + OR 형태
  const c = await db.all(
    `SELECT * FROM source_conflict
      WHERE (source_a = ? AND source_b = ?) OR (source_a = ? AND source_b = ?)`,
    ['eaps', 'ei', 'ei', 'eaps']);
  assert.deepEqual(c.map((x) => x.id).sort(), ['CONF-eaps-ei-개념', 'CONF-eaps-ei-모집단']);
});

// ── 규칙 2: 단위는 데이터가 준 것만 ─────────────────────────────────────────
test('관측 행의 unit 을 그대로 파생 단위로 싣는다', async () => {
  const db = makeFakeDb({ observation: 관측('천명') });
  const r = await ask({ db, llm: null }, { 유형: '수치조회', 슬롯: 수치슬롯 });
  assert.equal(r.근거.length, 1);
  assert.equal(r.근거[0].파생.단위, '천명');
});

test('unit 이 없으면 단위 키를 만들지 않는다 — null 로도 채우지 않는다', async () => {
  const db = makeFakeDb({ observation: 관측(null) });
  const r = await ask({ db, llm: null }, { 유형: '수치조회', 슬롯: 수치슬롯 });
  assert.equal(r.근거.length, 1);
  assert.equal('단위' in r.근거[0].파생, false);
});

// ── 규칙 3: 전망 지표 코드 매핑 ─────────────────────────────────────────────
test('주제를 전망 지표 코드로 옮겨 조회한다', async () => {
  const db = makeFakeDb({
    forecast: [{ id: 'f1', org: 'KDI', indicator: 'emp_change', target_year: 2027,
                 value: 12, unit: '만명', published_at: '2026-05-01' }],
  });
  for (const 주제 of ['취업자', '취업자수']) {  // 짧은 정규형·카탈로그 원어 둘 다
    const r = await ask({ db, llm: null }, { 유형: '전망', 슬롯: { 주제, 기간: { from: '2027', to: '2027' } } });
    assert.equal(r.지표코드, 'emp_change');
    assert.deepEqual(r.전망.map((x) => x.id), ['f1']);
  }
});

test('매핑에 없는 주제는 빈 결과가 아니라 한계를 낸다', async () => {
  const db = makeFakeDb();
  const r = await ask({ db, llm: null }, { 유형: '전망', 슬롯: { 주제: '종사자수' } });
  assert.equal(r.지표코드, null);
  assert.deepEqual(r.전망, []);
  assert.ok(r.한계.some((l) => l.includes('아직 다루지 않는다')),
            `한계가 비었다: ${JSON.stringify(r.한계)}`);
  // 매핑표는 실측 코드만 담는다 (domains/forecast/data/indicators.json)
  assert.equal(전망지표.취업자수, 'emp_change');
  assert.equal('종사자수' in 전망지표, false);
  assert.equal('상시가입자수' in 전망지표, false);
});

// ── 규칙 4: 허용텍스트는 우리가 준 카드 텍스트만 ───────────────────────────
test('허용텍스트에 현상 근거서술과 한계가 실리고, 카탈로그 산문은 안 실린다', async () => {
  const db = makeFakeDb();
  const r = await ask({ db, llm: null }, {
    유형: '원인탐색',
    슬롯: { 주제: '취업자', 집단축: ['연령', '직업'], 지역입도: '전국', 시간입도: '반기',
            기간: { from: '2023S1', to: '2025S2' }, 출처: [] },
  });
  assert.ok(r.허용텍스트.includes(r.현상.근거서술));
  assert.ok(r.허용텍스트.includes(r.현상.정의));   // "15~29세 …" 에도 숫자가 있다
  for (const l of r.한계) assert.ok(r.허용텍스트.includes(l));
  for (const h of r.가설) for (const m of h.missing_for_verdict) assert.ok(r.허용텍스트.includes(m));
  // 카드에 실리지 않는 산문(지표 카탈로그의 정의)은 허용텍스트에 없어야 한다
  assert.equal(r.허용텍스트.some((t) => t.includes('경제활동인구조사 기준 전체 취업자수')), false);
  // 식별자·열거값도 문장이 아니라 담지 않는다
  for (const 금지 of ['H1_AI대체', '청년사무직감소', '반기', '증감률만']) {
    assert.equal(r.허용텍스트.includes(금지), false, `허용텍스트에 ${금지} 가 있다`);
  }
});

test('범위밖의 예시 질문도 우리가 준 문장이라 허용텍스트에 담는다', async () => {
  const db = makeFakeDb();
  const r = await ask({ db, llm: null }, {
    유형: '범위밖',
    슬롯: { 주제: '매출', 집단축: [], 지역입도: '시군구', 시간입도: '월',
            기간: { from: '', to: '' }, 출처: [] },
  });
  assert.equal(r.답할수있는질문.length, 3);
  for (const q of r.답할수있는질문) assert.ok(r.허용텍스트.includes(q));
  // 예시 질문을 그대로 인용한 답변이 튕기지 않는다. 지금은 이 세 질문의 숫자가 전부
  // 라벨(2026년·7월·30대)이라 마스킹만으로도 통과하지만, 예시 질문이 측정값을 품는 날
  // 받아 주는 것은 허용텍스트다 — 그래서 경계는 마스킹이 아니라 "우리가 준 문장" 이다.
  const 답변객체 = { 답변: '대신 "2026년 7월 30대 취업자는 몇 명인가" 는 답할 수 있다.', 근거: [] };
  assert.equal(verify(답변객체, r.근거, r.허용텍스트).ok, true);
  const 값품은질문 = { 답변: '대신 "600천명이 맞나" 는 답할 수 있다.', 근거: [] };
  assert.deepEqual(verify(값품은질문, r.근거).위반, [600]);
  assert.equal(verify(값품은질문, r.근거, ['600천명이 맞나']).ok, true);
});

test('메타한계 카드의 라우팅 불가 사유도 허용텍스트에 담는다', async () => {
  const db = makeFakeDb();
  const r = await ask({ db, llm: null }, {
    유형: '메타한계',
    슬롯: { 주제: '종사자수', 집단축: ['연령'], 지역입도: '전국', 시간입도: '월',
            기간: { from: '', to: '' }, 출처: ['est'] },
  });
  // 이 경로에서는 라우팅 사유가 한계로 접히지 않고 라우팅 안에 실려 나간다
  assert.ok(r.라우팅.불가.length > 0);
  for (const x of r.라우팅.불가) assert.ok(r.허용텍스트.includes(x.사유));
});

test('허용텍스트가 있으면 근거서술을 인용한 숫자가 환각으로 튕기지 않는다', async () => {
  const db = makeFakeDb();
  const r = await ask({ db, llm: null }, {
    유형: '원인탐색',
    슬롯: { 주제: '취업자', 지역입도: '전국', 시간입도: '반기',
            기간: { from: '2023S1', to: '2025S2' }, 출처: [] },
  });
  // 근거서술의 수준값(818.3·727.4)은 관측이 안 실려 근거묶음에 없다 — 허용텍스트가 받는다.
  // ('4반기' 의 4 는 이제 시점 라벨로 마스킹되므로 이 인자가 필요한 문장이 못 된다)
  const 답변객체 = { 답변: '818.3천명에서 727.4천명으로 줄었다.', 근거: [] };
  assert.equal(verify(답변객체, r.근거, r.허용텍스트).ok, true);
  // 허용텍스트를 안 넘기면 같은 답변이 위반으로 잡힌다 — 이 인자가 왜 필요한지의 근거
  assert.deepEqual(verify(답변객체, r.근거).위반, [818.3, 727.4]);
});

// ── 규칙 5: 집단축 → breakdown 매핑 ─────────────────────────────────────────
test('축 매핑은 실측 breakdown 만 담는다', () => {
  assert.deepEqual(축_BREAKDOWN, { 연령: 'age', 성: 'sex', 산업: 'industry' });
  assert.equal(관측축([]).breakdown, 'total');
  assert.equal(관측축(['연령']).breakdown, 'age');
  assert.equal(관측축(['성']).breakdown, 'sex');
  assert.equal(관측축(['산업']).breakdown, 'industry');
});

test('매핑에 없는 축은 total 로 떨어지지 않고 한계가 된다', async () => {
  const { breakdown, 한계 } = 관측축(['직업']);
  assert.equal(breakdown, null);
  assert.ok(한계.some((l) => l.includes('직업')));

  const db = makeFakeDb({ observation: 관측('천명') });
  const r = await ask({ db, llm: null }, {
    유형: '수치조회',
    슬롯: { ...수치슬롯, 주제: '취업자수', 집단축: ['직업'] },
  });
  // 전체값을 대신 내놓지 않는다
  assert.deepEqual(r.근거, []);
  assert.ok(r.한계.some((l) => l.includes('직업')));
});

// ── C1: 카테고리 소실과 날조된 파생 ─────────────────────────────────────────
const 연령횡단면 = ['15-29', '30-39', '40-49'].map((c, i) => ({
  source: 'eaps', breakdown: 'age', category: c, period: '2026-07',
  value: 400 + i * 200, unit: '천명', rse: null, rse_flag: null,
}));

test('연령대를 못 집으면 전 구간이 나오지만 차이·증감률을 날조하지 않는다', async () => {
  const db = makeFakeDb({ observation: 연령횡단면 });
  const r = await ask({ db, llm: null }, {
    유형: '수치조회',
    슬롯: { ...수치슬롯, 기간: { from: '2026-07', to: '2026-07' } },  // category 없음
  });
  const 파생 = r.근거[0].파생;
  // 20대와 40대 사이의 "차이 400 / 증감률 100%" 는 아무 뜻이 없다 — 만들지 않는다
  assert.equal('차이' in 파생, false);
  assert.equal('증감률' in 파생, false);
  assert.equal(파생.합계, 1800);
  // 그리고 조용히 넘어가지 않는다
  assert.ok(r.한계.includes('연령대를 지목하지 못해 전 구간을 함께 보여준다'),
            `한계: ${JSON.stringify(r.한계)}`);
});

test('연령대를 집으면 그 구간만 조회하고 지목 한계도 사라진다', async () => {
  const db = makeFakeDb({
    observation: [
      ...연령횡단면,
      { source: 'eaps', breakdown: 'age', category: '30-39', period: '2026-08',
        value: 620, unit: '천명', rse: null, rse_flag: null },
    ],
  });
  const r = await ask({ db, llm: null }, {
    유형: '수치조회',
    슬롯: { ...수치슬롯, 기간: { from: '2026-07', to: '2026-08' },
            category: { 연령: '30-39' } },
  });
  // 카드가 어느 연령대인지 말한다 — 골든이 적어 둔 근거지표 형식과 같다
  assert.equal(r.근거[0].지표, 'eaps:age:30-39');
  assert.deepEqual(r.근거[0].관측, [{ 기간: '2026-07', 값: 600 }, { 기간: '2026-08', 값: 620 }]);
  assert.equal(r.근거[0].파생.차이, 20);   // 이제는 진짜 시계열이다
  assert.equal(r.한계.some((l) => l.includes('지목하지 못해')), false);
});

// ── I1·I2: 모르면 보수적으로, 쌍 판정을 근거에 물린다 ───────────────────────
test('비교기준이 카탈로그에 없으면 수준이 아니라 증감률만으로 떨어진다', async () => {
  // est 는 ontology.indicators 에 행이 없다 — conflicts.json 이 증감률만으로 못박은 소스다
  const db = makeFakeDb({
    observation: [
      { source: 'est', breakdown: 'industry', category: 'C', period: '2026-06', value: 100, unit: '천명' },
      { source: 'est', breakdown: 'industry', category: 'C', period: '2026-07', value: 110, unit: '천명' },
    ],
  });
  const r = await ask({ db, llm: null }, {
    유형: '수치조회',
    슬롯: { 주제: '종사자수', 집단축: ['산업'], 지역입도: '전국', 시간입도: '월',
            기간: { from: '2026-06', to: '2026-07' }, 출처: [] },
  });
  assert.deepEqual(r.라우팅.가능, ['est']);
  assert.equal(r.근거[0].compare_basis, '증감률만');
  assert.equal(r.근거[0].관측, undefined);          // 수준값이 안 실린다
  assert.ok(r.한계.some((l) => l.includes('증감률만으로 인용한다')));
});

test('출처비교의 쌍 판정이 근거에 그대로 물린다', async () => {
  const db = makeFakeDb({
    observation: [
      { source: 'eaps', breakdown: 'total', category: null, period: '2026-07', value: 28000, unit: '천명' },
      { source: 'ei', breakdown: 'total', category: null, period: '2026-07', value: 15000, unit: '천명' },
    ],
  });
  const r = await ask({ db, llm: null }, {
    유형: '출처비교',
    슬롯: { 주제: '취업자', 집단축: [], 지역입도: '전국', 시간입도: '월',
            기간: { from: '2026-07', to: '2026-07' }, 출처: ['eaps', 'ei'] },
  });
  assert.equal(r.비교.비교가능, '증감률만');
  // eaps 는 카탈로그상 '수준'(IND_전직종취업자)이지만, 쌍 판정이 더 보수적이라 그쪽을 따른다
  assert.equal(r.근거.length, 2);
  for (const e of r.근거) {
    assert.equal(e.compare_basis, '증감률만');
    assert.equal(e.관측, undefined);
  }
});

// ── I3: 라우팅이 통째로 비면 밝힌다 ─────────────────────────────────────────
test('짧은 정규형 주제도 route 앞에서 카탈로그 원어로 접힌다', async () => {
  const db = makeFakeDb();
  const r = await ask({ db, llm: null }, {
    유형: '수치조회', 슬롯: { ...수치슬롯, 주제: '취업자' },
  });
  assert.deepEqual(r.라우팅.가능, ['eaps']);
});

test('라우팅이 통째로 비면 빈 카드가 아니라 한계를 낸다', async () => {
  const db = makeFakeDb();
  const r = await ask({ db, llm: null }, {
    유형: '수치조회',
    슬롯: { 주제: '매출', 집단축: [], 지역입도: '전국', 시간입도: '월',
            기간: { from: '', to: '' }, 출처: [] },
  });
  assert.deepEqual([r.라우팅.가능, r.라우팅.부분, r.라우팅.불가], [[], [], []]);
  assert.ok(r.한계.includes('이 주제·축 조합을 내는 출처가 카탈로그에 없다'));
});

test('축을 둘 물으면 하나만 조회한다고 밝힌다', () => {
  const { breakdown, 한계 } = 관측축(['연령', '산업']);
  assert.equal(breakdown, 'age');
  assert.ok(한계.some((l) => l.includes('산업')));
});

// ── 현상 매칭 (실배포 화면 검증) ───────────────────────────────────────────
// "제조업 감소 이유" 에 "청년 사무직 감소" 를 답했다. 등록 현상이 하나뿐인데
// 정의에 "취업자수" 가 들어 있어 **취업자를 묻는 모든 질문에 걸렸다.**
// 주제 단어 하나로 맞히면 현상이 늘수록 오답이 늘어난다.

test('축 값이 어긋나는 현상은 고르지 않는다', async () => {
  const r = await ask({ db: makeFakeDb() }, {
    유형: '원인탐색',
    슬롯: { 주제: '취업자수', 집단축: ['산업'], category: { 산업: 'C' },
            지역입도: '전국', 시간입도: '월', 기간: { from: '2026-08', to: '2026-08' } },
  });
  // 등록 현상은 연령=15-29 · 직업=3 이다. 산업 C 를 물었으니 맞는 현상이 없다.
  assert.equal(r.현상 ?? null, null);
  // 없다는 사실을 **말한다** — 조용히 빈 카드를 내지 않는다
  assert.equal(r.판정없음, true);
  assert.ok(r.한계.includes('현상이 등록돼 있지 않아 판정하지 않는다'));
});

test('축 값이 맞으면 그 현상을 고른다', async () => {
  const r = await ask({ db: makeFakeDb() }, {
    유형: '원인탐색',
    슬롯: { 주제: '취업자수', 집단축: ['연령', '직업'],
            category: { 연령: '15-29', 직업: '3' },
            지역입도: '전국', 시간입도: '반기', 기간: { from: '', to: '' } },
  });
  assert.equal(r.현상?.id, '청년사무직감소');
});

test('축 값을 하나도 안 주면 주제만으로 고른다 — "왜 줄었어" 를 막지 않는다', async () => {
  const r = await ask({ db: makeFakeDb() }, {
    유형: '원인탐색',
    슬롯: { 주제: '취업자수', 집단축: [], category: {},
            지역입도: '전국', 시간입도: '월', 기간: { from: '', to: '' } },
  });
  assert.equal(r.현상?.id, '청년사무직감소');
});

test('축 값 일부만 맞아도 어긋나면 안 고른다', async () => {
  const r = await ask({ db: makeFakeDb() }, {
    유형: '원인탐색',
    슬롯: { 주제: '취업자수', 집단축: ['연령', '직업'],
            category: { 연령: '30-39', 직업: '3' },   // 연령이 다르다
            지역입도: '전국', 시간입도: '반기', 기간: { from: '', to: '' } },
  });
  assert.equal(r.현상 ?? null, null);
  assert.ok(r.한계.includes('현상이 등록돼 있지 않아 판정하지 않는다'));
});

test('현상이 선언하지 않은 축을 물으면 안 고른다', async () => {
  // 현상은 성을 선언하지 않는다 = 성을 가리지 않는 이야기다. "여성 청년이 왜
  // 줄었냐" 에 성 구분 없는 현상을 내밀면 묻지 않은 것을 답한 것이 된다.
  // 산업=C 를 거르는 규칙과 같은 규칙이어야 한다 — 둘 다 현상이 말한 적 없는 축이다.
  const r = await ask({ db: makeFakeDb() }, {
    유형: '원인탐색',
    슬롯: { 주제: '취업자수', 집단축: ['연령', '성'],
            category: { 연령: '15-29', 성: 'F' },
            지역입도: '전국', 시간입도: '반기', 기간: { from: '', to: '' } },
  });
  assert.equal(r.현상 ?? null, null);
  assert.ok(r.한계.includes('현상이 등록돼 있지 않아 판정하지 않는다'));
});

test('현상이 선언한 축의 일부만 물어도 고른다 — "청년 취업자 어때" 를 막지 않는다', async () => {
  // 현상은 연령·직업을 선언한다. 질문이 연령만 지목해도 어긋나지 않는다.
  const r = await ask({ db: makeFakeDb() }, {
    유형: '원인탐색',
    슬롯: { 주제: '취업자수', 집단축: ['연령'], category: { 연령: '15-29' },
            지역입도: '전국', 시간입도: '반기', 기간: { from: '', to: '' } },
  });
  assert.equal(r.현상?.id, '청년사무직감소');
});

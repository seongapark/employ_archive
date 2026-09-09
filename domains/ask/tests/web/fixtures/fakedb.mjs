// 정본 JSON 을 그대로 읽어 D1 인터페이스만 흉내낸다. 네트워크도 D1 도 없다.
//
// 두 가지를 진짜로 흉내낸다. 둘 중 하나라도 빼면 러너가 **조용히 거짓말을 한다** —
// 엉뚱한 표를 읽거나 거르지 않은 표 전체를 읽고도 테스트는 초록으로 통과한다.
//
// 1) 표 선택 — 단어경계 정규식으로 대조하되 대상은 `FROM` 절 토큰이다.
//    `sql.includes(name)` 은 두 군데서 깨진다.
//    · `WHERE phenomenon_id = ?` 가 `phenomenon` 을 부분문자열로 품는다.
//      키를 길이순으로 정렬해도 `hypothesis`(10)와 `phenomenon`(10)이 같은 길이라
//      순서가 미정이다 (Task 9 에서 이 버그로 테스트 5/6 이 깨졌다).
//      `_` 는 단어문자라 `\bphenomenon\b` 는 `phenomenon_id` 에 걸리지 않는다.
//    · 단어경계만으로도 못 거르는 자리가 하나 남는다:
//      `SELECT * FROM forecast WHERE indicator = ?` 는 **열 이름**이 다른 표 이름
//      (`indicator`)과 같아서 SQL 전체를 훑으면 두 표가 동시에 걸린다.
//      그래서 대조 대상을 `FROM` 절로 좁힌다.
//
// 2) WHERE 절 — 실제로 적용한다. 적용하지 않으면 `meta({출처:['est']})` 가 소스
//    30개를 전부 돌려줘 `evidence_status !== '확인'` 인 12개가 `미확인` 에 실리고,
//    `근거 미확인` 배지가 붙을 이유가 없는데 붙는다.
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const D = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'data');
const j = (n) => JSON.parse(readFileSync(join(D, n), 'utf8'));

// SQLite 에는 boolean 이 없다 — INTEGER 0/1 이다. `WHERE archived = 1` 이 정본 JSON 의
// `true` 와 맞물리게 하려면 적재 시점에 접어 둬야 한다(d1_sync 가 하는 일과 같다).
const 정규 = (v) => (typeof v === 'boolean' ? (v ? 1 : 0) : v);
const 행정규화 = (rows) =>
  rows.map((r) => Object.fromEntries(Object.entries(r).map(([k, v]) => [k, 정규(v)])));

// ── 아주 작은 SQL 조각 해석기 ────────────────────────────────────────────────
// 지원 범위: FROM 한 표 · WHERE (= <> != > >= < <= IN) · AND/OR/괄호 · ORDER BY 오름차순.
// 모르는 연산자는 조용히 통과시키지 않고 던진다.
const TOKEN =
  /\(|\)|,|\?|>=|<=|<>|!=|=|<|>|'[^']*'|[A-Za-z_가-힣][A-Za-z0-9_가-힣]*|-?\d+(?:\.\d+)?/g;

const 같음 = (a, b) => 정규(a) === 정규(b);

function 견줌(a, op, b) {
  const x = 정규(a);
  const y = 정규(b);
  switch (op) {
    case '=': return x === y;
    case '<>': case '!=': return x !== y;
    case '>': return x > y;
    case '>=': return x >= y;
    case '<': return x < y;
    case '<=': return x <= y;
    default: throw new Error(`가짜 db 가 모르는 연산자: ${op}`);
  }
}

function 조건식(sql, params) {
  const i = sql.search(/\bWHERE\b/i);
  if (i < 0) return null;
  const tail = sql.slice(i + 5).replace(/\b(ORDER\s+BY|GROUP\s+BY|LIMIT)\b[\s\S]*$/i, '');
  const toks = tail.match(TOKEN) ?? [];
  let t = 0;
  let p = 0;
  const up = (x) => String(x ?? '').toUpperCase();
  // 바인딩은 **파싱 시점에 등장 순서대로** 소비한다 — SQLite 가 ? 를 채우는 순서와 같다.
  const 값 = () => {
    const x = toks[t++];
    if (x === '?') return params[p++];
    if (x[0] === "'") return x.slice(1, -1);
    return Number(x);
  };
  const 비교 = () => {
    const col = toks[t++];
    const op = up(toks[t++]);
    if (op === 'IN') {
      t++; // (
      const vs = [];
      while (toks[t] !== ')') { if (toks[t] === ',') t++; else vs.push(값()); }
      t++; // )
      return (r) => vs.some((v) => 같음(r[col], v));
    }
    const v = 값();
    return (r) => 견줌(r[col], op, v);
  };
  const 인자 = () => {
    if (toks[t] === '(') { t++; const e = 식(); t++; return e; }
    return 비교();
  };
  const 항 = () => {
    let a = 인자();
    while (up(toks[t]) === 'AND') { t++; const b = 인자(); const x = a; a = (r) => x(r) && b(r); }
    return a;
  };
  const 식 = () => {
    let a = 항();
    while (up(toks[t]) === 'OR') { t++; const b = 항(); const x = a; a = (r) => x(r) || b(r); }
    return a;
  };
  return 식();
}

function 정렬(sql, rows) {
  const m = /\bORDER\s+BY\b\s+([\s\S]+?)(?:\s+LIMIT\b|$)/i.exec(sql);
  if (!m) return rows;
  const cols = m[1].split(',').map((c) => c.trim().split(/\s+/)[0]);
  return [...rows].sort((a, b) => {
    for (const c of cols) {
      if (a[c] === b[c]) continue;
      return a[c] < b[c] ? -1 : 1;
    }
    return 0;
  });
}

export function makeFakeDb(덮어쓰기 = {}) {
  const cap = j('capabilities.json');
  const ont = j('ontology.json');
  const T = {
    source_catalog: j('sources.json'),
    capability: cap.capabilities.map((c) => ({
      ...c,
      주제: JSON.stringify(c.주제), 집단축: JSON.stringify(c.집단축),
      지역입도: JSON.stringify(c.지역입도), 시간입도: JSON.stringify(c.시간입도),
    })),
    capability_limit: cap.limits,
    source_conflict: j('conflicts.json'),
    // 집단축은 D1 에서 **TEXT** 다 — 정본 JSON 은 객체로 들고 있으므로 여기서
    // 문자열로 만든다. 안 하면 대역이 실물과 달라져, 객체를 그냥 읽는 구현도
    // 통과해 버린다(같은 함정에 이미 두 번 당했다: 가짜 KV 의 String(), 손으로
    // 적은 어휘).
    phenomenon: ont.phenomena.map((p) => ({
      ...p,
      집단축: p.집단축 == null ? null : JSON.stringify(p.집단축),
    })),
    hypothesis: ont.hypotheses.map((h) => ({
      ...h,
      대립가설: JSON.stringify(h.대립가설),
      missing_for_verdict: JSON.stringify(h.missing_for_verdict ?? []),
    })),
    indicator: ont.indicators,
    hyp_indicator: ont.hyp_indicators,
    // 관측·전망은 이 저장소에 아직 적재돼 있지 않다. 비워 두는 것이 실제 상태다 —
    // 여기에 지어낸 행을 넣으면 골든이 없는 데이터를 있다고 통과시킨다.
    observation: [], forecast: [], forecast_rationale: [], release: [],
    // 뷰를 JS 로 같은 규칙으로 계산한다 (SQL 뷰와 규칙이 어긋나면 Task 4 테스트가 잡는다)
    hypothesis_verdict: ont.hypotheses.map((h) => {
      const f = ont.hyp_indicators.filter(
        (x) => x.hypothesis_id === h.id && x.role === 'falsifies');
      const ind = Object.fromEntries(ont.indicators.map((i) => [i.id, i]));
      const ph = ont.phenomena.find((p) => p.id === h.phenomenon_id);
      const n_missing = f.filter((x) => ind[x.indicator_id]?.data_status !== '보유').length;
      const n_weak = f.filter((x) => ind[x.indicator_id]?.time_grain !== ph?.time_grain
        || ind[x.indicator_id]?.compare_basis === '증감률만').length;
      const capable = f.length > 0 && n_missing === 0;
      return {
        id: h.id, verdict_capable: capable ? 1 : 0,
        verdict_strength: !capable ? null : (n_weak > 0 ? 'weak' : 'strong'),
        verdict_blocked_by: f.length === 0 ? '반증미설계'
          : (n_missing > 0 ? '데이터미보유' : null),
        n_falsify: f.length, n_missing,
      };
    }),
    ...덮어쓰기,
  };
  for (const k of Object.keys(T)) T[k] = 행정규화(T[k]);

  const 표이름 = (sql) => {
    const from = /\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)/i.exec(sql)?.[1] ?? sql;
    return Object.keys(T).find((n) => new RegExp(`\\b${n}\\b`).test(from)) ?? null;
  };

  return {
    표: T,
    all: async (sql, params = []) => {
      const name = 표이름(sql);
      // 모르는 표를 빈 배열로 돌려주면 "데이터가 없다" 와 구분되지 않는다 — 던진다.
      if (!name) throw new Error(`가짜 db 가 표를 못 찾았다: ${sql}`);
      const pred = 조건식(sql, params);
      return 정렬(sql, pred ? T[name].filter(pred) : T[name]);
    },
  };
}

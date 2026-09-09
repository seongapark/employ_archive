// 숫자가 만들어지는 유일한 자리. LLM 은 여기서 나온 값만 인용하고,
// verify 는 여기서 나온 집합으로만 대조한다.

const r1 = (n) => Math.round(n * 10) / 10;

export function derive(관측, { compare_basis, 전체, 단위 } = {}) {
  if (!관측?.length) return null;
  const 값 = 관측.map((o) => o.값);
  const out = {};
  if (단위 !== undefined) out.단위 = 단위; // 데이터가 준 단위만 싣는다 — 추측하지 않는다

  // 파생은 **관측의 모양**을 따른다. 모양에 안 맞는 파생은 만들지 않는다 —
  // 만들면 뜻 없는 숫자가 numbersIn 을 통해 허용 집합에 들어가고, LLM 이 그걸 인용해도
  // verify 가 통과시킨다.
  //   횡단면(기간이 전부 같다, 여러 계열)  → 합계·비중.  차이·증감률은 뜻이 없다
  //                                          ("20대와 40대의 차이" 는 아무것도 아니다)
  //   시계열(기간이 전부 다르다)            → 차이·증감률·기여도. 합계는 뜻이 없다
  //   혼합(계열 × 기간)                     → 둘 다 안 만든다
  const 기간들 = 관측.map((o) => o.기간);
  const 횡단면 = 기간들.every((p) => p === 기간들[0]);
  const 시계열 = 관측.length >= 2 && new Set(기간들).size === 관측.length;

  if (횡단면) out.합계 = r1(값.reduce((a, b) => a + b, 0));
  if (시계열) {
    const a = 값[0], b = 값[값.length - 1];
    out.차이 = r1(b - a);
    out.증감률 = a === 0 ? null : r1(((b - a) / a) * 100);
    out.기준기간 = `${기간들[0]}→${기간들[기간들.length - 1]}`;
  }
  if (전체) {
    if (out.합계 !== undefined) out.비중 = r1((out.합계 / 전체) * 100);
    // 기여도는 차이가 있을 때만 있다 — 차이가 없는데 기여도를 내면 같은 날조가 된다
    if (out.차이 != null) out.기여도 = r1((out.차이 / 전체) * 100);
  }
  return out;
}

export function buildEvidence({ 지표, compare_basis, 단위, rse, rse_flag, 출처 }, 관측, opts = {}) {
  const 파생 = derive(관측, { compare_basis, 단위, ...opts }) ?? {};
  const e = { 지표, compare_basis, 출처, 파생 };
  if (compare_basis === '증감률만') {
    // 수준 비교 금지를 데이터로 강제한다 — 관측도 파생 수준값도 넘기지 않는다.
    // 기여도(=차이/전체*100)를 남기면 전체를 아는 쪽에서 차이를 역산할 수 있어 같이 지운다.
    delete e.파생.차이;
    delete e.파생.합계;
    delete e.파생.비중;
    delete e.파생.기여도;
  } else {
    e.관측 = 관측;
  }
  if (rse == null) {
    e.유의성 = '불명';
    e.유의성사유 = rse_flag ? `RSE 미공표(${rse_flag})` : 'RSE 미보유';
  } else {
    e.유의성 = '유의';          // 실제 판정은 지표가 rse 를 실제로 낼 때 채운다
    e.유의성사유 = `RSE ${rse}%`;
  }
  return e;
}

export function numbersIn(근거묶음) {
  const s = new Set();
  for (const e of 근거묶음) {
    for (const o of e.관측 ?? []) s.add(o.값);
    for (const v of Object.values(e.파생 ?? {})) {
      if (typeof v === 'number') s.add(v);
    }
  }
  return s;
}

// 전망 카드의 **수치**를 숫자 집합으로 모은다. 전망 유형은 `근거` 가 비어 있고
// 값이 `전망` 에 있는데, verify 는 근거만 봤다 — **전망 답변의 모든 숫자가 근거
// 밖으로 판정돼 문장이 늘 버려졌다**(2026-09-09 실측: 위반 [17, 12.3] 의 17 은
// BOK 2024 연간 전망값 그 자체였다).
//
// 행 배열과 보고서 묶음(수치: [...]) 두 모양을 다 받는다 — 결함 6에서 응답이
// 묶음 형태로 바뀌는데, 그때 이 함수가 조용히 빈손이 되면 같은 결함이 재발한다.
export function 숫자모음(전망 = []) {
  const s = new Set();
  const 담기 = (r) => {
    for (const k of ['value', 'prev_value']) {
      if (typeof r?.[k] === 'number') s.add(r[k]);
    }
    // 조정폭은 **부호 없는 형태도 담는다.** "-3" 과 "3만명 하향" 은 같은 양을
    // 말하는데, 한국어는 방향을 낱말("하향")로 쓰고 숫자에는 부호를 안 붙인다.
    // verify 는 애초에 낱말을 안 보므로 부호를 강제해도 방향 오류를 못 잡는다 —
    // 잡지도 못하면서 정상 문장만 버리는 엄격함이라 푼다.
    if (typeof r?.revision === 'number') { s.add(r.revision); s.add(Math.abs(r.revision)); }
  };
  for (const r of 전망 ?? []) {
    담기(r);
    for (const v of r?.수치 ?? []) 담기(v);
  }
  return s;
}

// **`최신만` 은 호출부가 켠다 — 여기서 몰래 켜지 않는다.**
// 수치조회는 기간을 안 주면 "지금" 을 묻는 것이라 최신 한 시점이 맞다(안 그러면
// "취업자 몇 명이야" 에 5년치가 쏟아진다). 하지만 원인탐색의 근거는 **추세**라
// 같은 기본값을 먹이면 한 점으로 접혀 차이·증감률이 통째로 사라진다. 두 부름의
// 뜻이 다르므로 기본값도 다르다 — 그 선택을 부르는 쪽이 하게 둔다.
//
// **최신은 나머지 조건 안에서 구한다.** 전역 MAX(period) 를 쓰면 가장 늦게 발표하는
// 출처가 전체 기준이 되어, 그보다 이른 출처는 조용히 빈손이 된다 — 실제로 est 는
// eaps 보다 한 달 늦다. 그래서 source·breakdown·category 를 그대로 물고 MAX 를 뽑는다.
async function 최신시점(deps, where, p) {
  const rows = await deps.db.all(
    `SELECT MAX(period) AS 최신 FROM observation WHERE ${where.join(' AND ')}`, p);
  return rows?.[0]?.최신 ?? null;
}

export async function queryObservations(deps,
  { source, breakdown, category, from, to, 최신만 = false }) {
  const where = ['source = ?', 'breakdown = ?'];
  const p = [source, breakdown];
  if (category) { where.push('category = ?'); p.push(category); }

  if (최신만 && !from && !to) {
    const 최신 = await 최신시점(deps, where, p);
    if (!최신) return [];          // 관측이 아예 없다 — 지어내지 않는다
    where.push('period = ?'); p.push(최신);
  } else {
    if (from) { where.push('period >= ?'); p.push(from); }
    if (to) { where.push('period <= ?'); p.push(to); }
  }

  return deps.db.all(
    `SELECT source, breakdown, category, period, value, unit, yoy, rse, rse_flag,
            released_at, release_url
       FROM observation WHERE ${where.join(' AND ')} ORDER BY period`, p);
}

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

export async function queryObservations(deps, { source, breakdown, category, from, to }) {
  const where = ['source = ?', 'breakdown = ?'];
  const p = [source, breakdown];
  if (category) { where.push('category = ?'); p.push(category); }
  if (from) { where.push('period >= ?'); p.push(from); }
  if (to) { where.push('period <= ?'); p.push(to); }
  return deps.db.all(
    `SELECT source, breakdown, category, period, value, unit, yoy, rse, rse_flag,
            released_at, release_url
       FROM observation WHERE ${where.join(' AND ')} ORDER BY period`, p);
}

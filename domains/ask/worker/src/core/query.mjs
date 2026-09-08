// 숫자가 만들어지는 유일한 자리. LLM 은 여기서 나온 값만 인용하고,
// verify 는 여기서 나온 집합으로만 대조한다.

const r1 = (n) => Math.round(n * 10) / 10;

export function derive(관측, { compare_basis, 전체 } = {}) {
  if (!관측?.length) return null;
  const 값 = 관측.map((o) => o.값);
  const 합계 = r1(값.reduce((a, b) => a + b, 0));
  const out = { 합계, 단위: '천명' };
  if (관측.length >= 2) {
    const a = 값[0], b = 값[값.length - 1];
    out.차이 = r1(b - a);
    out.증감률 = a === 0 ? null : r1(((b - a) / a) * 100);
    out.기준기간 = `${관측[0].기간}→${관측[관측.length - 1].기간}`;
  } else {
    out.차이 = null;
    out.증감률 = null;
  }
  if (전체) {
    out.비중 = r1((합계 / 전체) * 100);
    out.기여도 = out.차이 == null ? null : r1((out.차이 / 전체) * 100);
  }
  return out;
}

export function buildEvidence({ 지표, compare_basis, rse, rse_flag, 출처 }, 관측, opts = {}) {
  const 파생 = derive(관측, { compare_basis, ...opts }) ?? {};
  const e = { 지표, compare_basis, 출처, 파생 };
  if (compare_basis === '증감률만') {
    // 수준 비교 금지를 데이터로 강제한다 — 관측도 차이도 넘기지 않는다
    delete e.파생.차이;
    delete e.파생.합계;
    delete e.파생.비중;
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

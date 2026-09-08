// 같은 쌍에 여러 행이 있다(개념·모집단·시의성…). 유형마다 근거·확인일이 달라
// 배열 컬럼이 아니라 행으로 갈라 뒀으므로, 여기서 모아 가장 보수적인 판정을 고른다.

const RANK = { 불가: 0, 증감률만: 1, 수준: 2 };

export async function compare(deps, { source_a, source_b }) {
  const rows = await deps.db.all(
    `SELECT * FROM source_conflict
      WHERE (source_a = ? AND source_b = ?) OR (source_a = ? AND source_b = ?)`,
    [source_a, source_b, source_b, source_a]);

  if (!rows.length) {
    // 모르면 비교를 허용하지 않는다 — 조용히 통과시키면 이 앱의 존재 이유가 사라진다
    return { 비교가능: '불가', 차이유형: [],
             설명: [`${source_a} 와 ${source_b} 의 비교가능 기록이 없다`], 근거: [] };
  }
  const 비교가능 = rows.reduce(
    (worst, r) => (RANK[r.비교가능] < RANK[worst] ? r.비교가능 : worst), '수준');
  return {
    비교가능,
    차이유형: [...new Set(rows.map((r) => r.차이유형))],
    설명: rows.map((r) => r.설명),
    근거: rows.map((r) => ({ id: r.id, evidence: r.evidence, verified_at: r.verified_at })),
  };
}

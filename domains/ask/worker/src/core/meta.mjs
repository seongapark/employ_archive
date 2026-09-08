// 소스 단위 필터. 카탈로그를 통째로 프롬프트에 넣으면 토큰이 매번 낭비되고,
// 질문과 무관한 소스가 답변에 섞인다.

const ph = (n) => Array(n).fill('?').join(', ');

export async function meta(deps, { 출처 = [] } = {}) {
  const 소스전체 = 출처.length
    ? await deps.db.all(
        `SELECT * FROM source_catalog WHERE id IN (${ph(출처.length)})`, 출처)
    : (await deps.db.all('SELECT * FROM source_catalog WHERE archived = 1'));

  const ids = 소스전체.map((s) => s.id);
  const 한계 = ids.length
    ? await deps.db.all(
        `SELECT * FROM capability_limit WHERE source_id IN (${ph(ids.length)})`, ids)
    : [];
  const 충돌 = ids.length > 1
    ? await deps.db.all(
        `SELECT * FROM source_conflict
          WHERE source_a IN (${ph(ids.length)}) AND source_b IN (${ph(ids.length)})`,
        [...ids, ...ids])
    : [];

  return {
    소스: 소스전체.filter((s) => s.evidence_status === '확인'),
    미확인: 소스전체.filter((s) => s.evidence_status !== '확인'),
    한계, 충돌,
  };
}

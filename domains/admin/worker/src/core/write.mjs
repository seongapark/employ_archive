// 정상 사용으로는 닿지 않는다 — 하루에 화면을 500번 전환해야 한다. 스크립트로
// 부풀리는 것만 막는다.
//
// **KV 로 세지 않는다.** Workers KV 는 무료 쓰기가 하루 1,000회뿐이라 조회마다 쓰면
// D1 한도(10만)보다 백 배 먼저 걸린다. ask 워커가 KV 를 쓰는 것은 요청이 훨씬 드문
// LLM 호출이기 때문이고, 그 패턴을 여기 그대로 옮기면 안 된다.
export const 일일상한 = 500;

// day_hits 는 last_day 가 그대로일 때만 는다 — 날이 바뀌면 1 로 돌아간다.
// 이 CASE 가 없으면 오래 쓴 방문자가 언젠가 상한에 걸려 영영 안 세어진다.
const UPSERT = `
INSERT INTO visitor (id, first_day, last_day, hits, day_hits) VALUES (?1, ?2, ?2, 1, 1)
ON CONFLICT(id) DO UPDATE SET
  last_day = ?2,
  hits     = hits + 1,
  day_hits = CASE WHEN visitor.last_day = ?2 THEN visitor.day_hits + 1 ELSE 1 END
RETURNING day_hits`;

const INSERT = `
INSERT INTO hit (ts, day, domain, path, visitor, session, ref, ref_kind, mode, device, country)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`;

// 순서가 중요하다: 먼저 방문자를 갱신해 그날 몇 번째인지 받고, 상한 안일 때만 줄을
// 쌓는다. 반대로 하면 상한을 넘은 줄이 이미 들어간 뒤에 알게 된다.
export async function 기록(db, r) {
  const row = await db.one(UPSERT, [r.visitor, r.day]);
  if (!row || row.day_hits > 일일상한) return false;
  await db.run(INSERT, [r.ts, r.day, r.domain, r.path, r.visitor, r.session,
    r.ref, r.ref_kind, r.mode, r.device, r.country]);
  return true;
}

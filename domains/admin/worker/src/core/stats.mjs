// 집계. SQL 은 여기 문자열로만 있고 실행은 주입받은 db 가 한다 — 테스트가 진짜
// SQLite 에 진짜 마이그레이션을 적용해 이 SQL 을 그대로 돌린다.

const 날짜더하기 = (day, n) => {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

// days=0 은 전 기간이다. 시작을 SQLite 문자열 비교에서 어떤 날짜보다 작은 값으로
// 두면 `BETWEEN` 하나로 두 경우를 다 쓴다 — 질의를 갈래로 나누지 않는다.
export function 기간(days, todayKst) {
  if (!days) {
    return { 시작: '0000-01-01', 끝: todayKst, 일수: 0, 직전시작: null, 직전끝: null };
  }
  const 시작 = 날짜더하기(todayKst, -(days - 1));
  return {
    시작, 끝: todayKst, 일수: days,
    직전끝: 날짜더하기(시작, -1),
    직전시작: 날짜더하기(시작, -days),
  };
}

// 유입만 세션의 첫 줄로 좁힌다(설계 §6.3). MIN(id) 옆의 열은 **최솟값이 나온 그
// 행의 값**이다 — SQLite 가 min()/max() 단일 집계에 보장하는 동작이고 D1 은
// SQLite 다. 다른 DB 로 옮기면 깨지는 자리라 옮길 일이 생기면 여기부터 본다.
const 세션첫줄 = `SELECT session, ref, ref_kind, MIN(id) FROM hit
  WHERE day BETWEEN ?1 AND ?2 GROUP BY session`;

export function 질의목록(창) {
  const p = [창.시작, 창.끝];
  const 목록 = [
    { 키: '요약', sql: `SELECT COUNT(DISTINCT visitor) 방문자, COUNT(DISTINCT session) 세션,
        COUNT(*) 조회 FROM hit WHERE day BETWEEN ?1 AND ?2`, params: p },
    { 키: '신규', sql: `SELECT
        SUM(CASE WHEN v.first_day >= ?1 THEN 1 ELSE 0 END) 신규,
        SUM(CASE WHEN v.first_day <  ?1 THEN 1 ELSE 0 END) 재방문
      FROM (SELECT DISTINCT visitor FROM hit WHERE day BETWEEN ?1 AND ?2) h
      JOIN visitor v ON v.id = h.visitor`, params: p },
    // 마지막 `domain` 은 동점을 깨는 기준이다. 없으면 방문자·조회가 같은 도메인의
    // 순서가 미정이라 테스트가 운에 기댄다(실제로 실행해 보니 우연히 맞았다).
    { 키: '도메인', sql: `SELECT domain 도메인, COUNT(DISTINCT visitor) 방문자,
        COUNT(DISTINCT session) 세션, COUNT(*) 조회 FROM hit WHERE day BETWEEN ?1 AND ?2
      GROUP BY domain ORDER BY 방문자 DESC, 조회 DESC, domain`, params: p },
    { 키: '일별', sql: `SELECT day 날짜, domain 도메인, COUNT(DISTINCT visitor) 방문자,
        COUNT(*) 조회 FROM hit WHERE day BETWEEN ?1 AND ?2
      GROUP BY day, domain ORDER BY day`, params: p },
    { 키: '화면', sql: `SELECT domain 도메인, path 경로, COUNT(*) 조회,
        COUNT(DISTINCT visitor) 방문자 FROM hit WHERE day BETWEEN ?1 AND ?2
      GROUP BY domain, path ORDER BY 조회 DESC, 도메인, 경로 LIMIT 20`, params: p },
    { 키: '유입종류', sql: `SELECT ref_kind 종류, COUNT(*) 세션 FROM (${세션첫줄})
      GROUP BY ref_kind ORDER BY 세션 DESC`, params: p },
    { 키: '유입호스트', sql: `SELECT ref 호스트, COUNT(*) 세션 FROM (${세션첫줄})
      WHERE ref IS NOT NULL GROUP BY ref ORDER BY 세션 DESC LIMIT 10`, params: p },
    { 키: '기기', sql: `SELECT device 값, COUNT(DISTINCT visitor) 방문자
      FROM hit WHERE day BETWEEN ?1 AND ?2 GROUP BY device ORDER BY 방문자 DESC`, params: p },
    { 키: '표시모드', sql: `SELECT mode 값, COUNT(DISTINCT visitor) 방문자
      FROM hit WHERE day BETWEEN ?1 AND ?2 GROUP BY mode ORDER BY 방문자 DESC`, params: p },
    { 키: '국가', sql: `SELECT country 값, COUNT(DISTINCT visitor) 방문자
      FROM hit WHERE day BETWEEN ?1 AND ?2 AND country IS NOT NULL
      GROUP BY country ORDER BY 방문자 DESC LIMIT 10`, params: p },
  ];
  if (창.직전시작) {
    목록.push({ 키: '직전', sql: `SELECT COUNT(DISTINCT visitor) 방문자,
        COUNT(DISTINCT session) 세션, COUNT(*) 조회 FROM hit WHERE day BETWEEN ?1 AND ?2`,
      params: [창.직전시작, 창.직전끝] });
  }
  return 목록;
}

const 수 = (v) => Number(v ?? 0);

export function 조립(창, r) {
  const 요약 = r.요약?.[0] ?? {};
  const 신규 = r.신규?.[0] ?? {};
  const 직전 = r.직전?.[0] ?? null;

  // 일별은 (날짜, 도메인) 쌍으로 오므로 날짜로 접는다. 그날 0 인 도메인은 아예
  // 행이 없다 — 화면이 0 으로 채운다.
  const 날짜별 = new Map();
  for (const row of r.일별 ?? []) {
    if (!날짜별.has(row.날짜)) 날짜별.set(row.날짜, { 날짜: row.날짜, 방문자: 0, 도메인별: {} });
    const d = 날짜별.get(row.날짜);
    d.도메인별[row.도메인] = 수(row.조회);
    d.방문자 = Math.max(d.방문자, 수(row.방문자));
  }

  return {
    기간: { 시작: 창.시작, 끝: 창.끝, 일수: 창.일수 },
    요약: {
      방문자: 수(요약.방문자), 세션: 수(요약.세션), 조회: 수(요약.조회),
      신규: 수(신규.신규), 재방문: 수(신규.재방문),
    },
    직전: 직전 ? { 방문자: 수(직전.방문자), 세션: 수(직전.세션), 조회: 수(직전.조회) } : null,
    도메인: r.도메인 ?? [],
    일별: [...날짜별.values()],
    화면: r.화면 ?? [],
    유입: { 종류: r.유입종류 ?? [], 호스트: r.유입호스트 ?? [] },
    기기: r.기기 ?? [],
    표시모드: r.표시모드 ?? [],
    국가: r.국가 ?? [],
  };
}

export async function 통계(db, days, todayKst) {
  const 창 = 기간(days, todayKst);
  const 목록 = 질의목록(창);
  const 결과 = await Promise.all(목록.map((q) => db.all(q.sql, q.params)));
  return 조립(창, Object.fromEntries(목록.map((q, i) => [q.키, 결과[i]])));
}
